"""SQLAlchemy Core repository for durable ServiceNow linkage retry state."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Iterator

from sqlalchemy import and_, insert, or_, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError, InvariantViolation
from aiops_triage_pipeline.linkage.schema import (
    LinkageRetryRecordV1,
    create_sn_linkage_retry_table,
    sn_linkage_retry_table,
)
from aiops_triage_pipeline.linkage.state_machine import create_pending_linkage_retry_record


class ServiceNowLinkageRetrySqlRepository:
    """Persist and transition SN linkage retry rows with source-state guards."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        self._run_ddl()

    def get_or_create_pending(
        self,
        *,
        case_id: str,
        pd_incident_id: str,
        incident_sys_id: str | None,
        retry_window_minutes: int,
        now: datetime | None = None,
    ) -> LinkageRetryRecordV1:
        pending = create_pending_linkage_retry_record(
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            incident_sys_id=incident_sys_id,
            retry_window_minutes=retry_window_minutes,
            now=now,
        )
        try:
            with self._tx() as conn:
                existing = self._get_by_case_id(conn=conn, case_id=case_id)
                if existing is not None:
                    self._assert_linkage_identity(existing=existing, pd_incident_id=pd_incident_id)
                    return existing
                try:
                    result = conn.execute(
                        insert(sn_linkage_retry_table)
                        .values(**_record_to_db_dict(pending))
                        .returning(*_returning_columns())
                    )
                    return _row_to_record(result.mappings().one())
                except IntegrityError:
                    raced = self._require_by_case_id(conn=conn, case_id=case_id)
                    self._assert_linkage_identity(existing=raced, pd_incident_id=pd_incident_id)
                    return raced
        except CriticalDependencyError:
            raise
        except InvariantViolation:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def persist_transition(
        self,
        *,
        case_id: str,
        next_record: LinkageRetryRecordV1,
        expected_source_statuses: set[str],
    ) -> LinkageRetryRecordV1:
        """Persist a computed transition when current state matches expected source states."""
        try:
            with self._tx() as conn:
                result = conn.execute(
                    update(sn_linkage_retry_table)
                    .where(
                        and_(
                            sn_linkage_retry_table.c.case_id == case_id,
                            sn_linkage_retry_table.c.state.in_(
                                tuple(sorted(expected_source_statuses))
                            ),
                        )
                    )
                    .values(**_record_to_db_dict(next_record))
                    .returning(*_returning_columns())
                )
                row = result.mappings().one_or_none()
                if row is not None:
                    return _row_to_record(row)

                latest = self._require_by_case_id(conn=conn, case_id=case_id)
                if latest.state == next_record.state:
                    return latest
                raise InvariantViolation(
                    "sn linkage retry transition source-state guard failed "
                    f"for case_id={case_id}; expected one of {sorted(expected_source_statuses)} "
                    f"but found {latest.state}"
                )
        except CriticalDependencyError:
            raise
        except InvariantViolation:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def get_by_case_id(self, *, case_id: str) -> LinkageRetryRecordV1 | None:
        try:
            with self._tx() as conn:
                return self._get_by_case_id(conn=conn, case_id=case_id)
        except CriticalDependencyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def select_retry_candidates(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[LinkageRetryRecordV1]:
        """Select FAILED_TEMP rows that are due for another SEARCHING attempt."""
        resolved_now = _resolve_now(now)
        try:
            with self._tx() as conn:
                stmt = (
                    select(*_returning_columns())
                    .where(
                        and_(
                            sn_linkage_retry_table.c.state == "FAILED_TEMP",
                            or_(
                                sn_linkage_retry_table.c.next_attempt_at.is_(None),
                                sn_linkage_retry_table.c.next_attempt_at <= resolved_now,
                            ),
                        )
                    )
                    .order_by(
                        sn_linkage_retry_table.c.next_attempt_at.asc(),
                        sn_linkage_retry_table.c.updated_at.asc(),
                    )
                    .limit(limit)
                )
                rows = conn.execute(stmt).mappings().all()
                return [_row_to_record(row) for row in rows]
        except CriticalDependencyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def _run_ddl(self) -> None:
        try:
            create_sn_linkage_retry_table(self._engine)
        except CriticalDependencyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    @contextmanager
    def _tx(self) -> Iterator[Connection]:
        try:
            with self._engine.begin() as conn:
                yield conn
        except SQLAlchemyError as exc:
            raise self._wrap_repo_exc(exc) from exc

    def _get_by_case_id(self, *, conn: Connection, case_id: str) -> LinkageRetryRecordV1 | None:
        stmt = select(*_returning_columns()).where(sn_linkage_retry_table.c.case_id == case_id)
        row = conn.execute(stmt).mappings().one_or_none()
        if row is None:
            return None
        return _row_to_record(row)

    def _require_by_case_id(self, *, conn: Connection, case_id: str) -> LinkageRetryRecordV1:
        record = self._get_by_case_id(conn=conn, case_id=case_id)
        if record is None:
            raise InvariantViolation(f"sn linkage retry record not found for case_id={case_id}")
        return record

    @staticmethod
    def _assert_linkage_identity(*, existing: LinkageRetryRecordV1, pd_incident_id: str) -> None:
        if existing.pd_incident_id != pd_incident_id:
            raise InvariantViolation(
                "existing sn linkage retry case_id has different pd_incident_id"
            )

    @staticmethod
    def _wrap_repo_exc(exc: Exception) -> CriticalDependencyError:
        return CriticalDependencyError(f"sn linkage retry repository operation failed: {exc}")


def _record_to_db_dict(record: LinkageRetryRecordV1) -> dict[str, object]:
    return {
        "case_id": record.case_id,
        "pd_incident_id": record.pd_incident_id,
        "incident_sys_id": record.incident_sys_id,
        "state": record.state,
        "attempt_count": record.attempt_count,
        "retry_window_minutes": record.retry_window_minutes,
        "first_attempt_at": record.first_attempt_at,
        "updated_at": record.updated_at,
        "deadline_at": record.deadline_at,
        "next_attempt_at": record.next_attempt_at,
        "request_id": record.request_id,
        "last_error_code": record.last_error_code,
        "last_error_message": record.last_error_message,
        "last_retry_after_seconds": record.last_retry_after_seconds,
        "last_reason_metadata": json.dumps(record.last_reason_metadata, sort_keys=True),
    }


def _row_to_record(row: dict[str, object]) -> LinkageRetryRecordV1:
    raw_metadata = row["last_reason_metadata"]
    if raw_metadata is None:
        parsed_metadata: dict[str, object] = {}
    elif isinstance(raw_metadata, str):
        parsed = json.loads(raw_metadata)
        parsed_metadata = parsed if isinstance(parsed, dict) else {}
    else:
        parsed_metadata = {}
    return LinkageRetryRecordV1(
        case_id=str(row["case_id"]),
        pd_incident_id=str(row["pd_incident_id"]),
        incident_sys_id=row["incident_sys_id"],
        state=str(row["state"]),
        attempt_count=int(row["attempt_count"]),
        retry_window_minutes=int(row["retry_window_minutes"]),
        first_attempt_at=_as_aware_datetime(row["first_attempt_at"]),
        updated_at=_as_aware_datetime(row["updated_at"]),
        deadline_at=_as_aware_datetime(row["deadline_at"]),
        next_attempt_at=_as_aware_datetime_or_none(row["next_attempt_at"]),
        request_id=row["request_id"],
        last_error_code=row["last_error_code"],
        last_error_message=row["last_error_message"],
        last_retry_after_seconds=(
            int(row["last_retry_after_seconds"])
            if row["last_retry_after_seconds"] is not None
            else None
        ),
        last_reason_metadata=parsed_metadata,
    )


def _resolve_now(now: datetime | None) -> datetime:
    resolved = now or datetime.now(tz=UTC)
    if resolved.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return resolved


def _returning_columns() -> tuple:
    return (
        sn_linkage_retry_table.c.case_id,
        sn_linkage_retry_table.c.pd_incident_id,
        sn_linkage_retry_table.c.incident_sys_id,
        sn_linkage_retry_table.c.state,
        sn_linkage_retry_table.c.attempt_count,
        sn_linkage_retry_table.c.retry_window_minutes,
        sn_linkage_retry_table.c.first_attempt_at,
        sn_linkage_retry_table.c.updated_at,
        sn_linkage_retry_table.c.deadline_at,
        sn_linkage_retry_table.c.next_attempt_at,
        sn_linkage_retry_table.c.request_id,
        sn_linkage_retry_table.c.last_error_code,
        sn_linkage_retry_table.c.last_error_message,
        sn_linkage_retry_table.c.last_retry_after_seconds,
        sn_linkage_retry_table.c.last_reason_metadata,
    )


def _as_aware_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"expected datetime, got {type(value).__name__}")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _as_aware_datetime_or_none(value: object) -> datetime | None:
    if value is None:
        return None
    return _as_aware_datetime(value)
