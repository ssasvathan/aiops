"""SQLAlchemy Core repository for durable outbox state transitions."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterator

from sqlalchemy import and_, insert, or_, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError, InvariantViolation
from aiops_triage_pipeline.outbox.schema import (
    OUTBOX_STATES,
    OutboxReadyCasefileV1,
    OutboxRecordV1,
    create_outbox_table,
    outbox_table,
)
from aiops_triage_pipeline.outbox.state_machine import (
    mark_outbox_record_publish_failure,
    mark_outbox_record_ready,
    mark_outbox_record_sent,
    retention_cutoff_for_state,
)


class OutboxSqlRepository:
    """Persist and transition outbox rows with strict source-state guards."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        self._run_ddl()

    def insert_pending_object(
        self,
        *,
        confirmed_casefile: OutboxReadyCasefileV1,
        now: datetime | None = None,
    ) -> OutboxRecordV1:
        resolved_now = _resolve_now(now)
        try:
            with self._tx() as conn:
                existing = self._get_by_case_id(conn=conn, case_id=confirmed_casefile.case_id)
                if existing is not None:
                    self._assert_casefile_payload_match(
                        existing=existing, confirmed_casefile=confirmed_casefile
                    )
                    return existing

                try:
                    result = conn.execute(
                        insert(outbox_table)
                        .values(
                            case_id=confirmed_casefile.case_id,
                            casefile_object_path=confirmed_casefile.object_path,
                            triage_hash=confirmed_casefile.triage_hash,
                            status="PENDING_OBJECT",
                            created_at=resolved_now,
                            updated_at=resolved_now,
                            delivery_attempts=0,
                            next_attempt_at=None,
                            last_error_code=None,
                            last_error_message=None,
                        )
                        .returning(*_returning_columns())
                    )
                    return _row_to_record(result.mappings().one())
                except IntegrityError:
                    # Another worker inserted the same case_id between the read and insert.
                    raced = self._require_by_case_id(conn=conn, case_id=confirmed_casefile.case_id)
                    self._assert_casefile_payload_match(
                        existing=raced, confirmed_casefile=confirmed_casefile
                    )
                    return raced
        except CriticalDependencyError:
            raise
        except InvariantViolation:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def transition_to_ready(
        self,
        *,
        case_id: str,
        now: datetime | None = None,
    ) -> OutboxRecordV1:
        resolved_now = _resolve_now(now)
        try:
            with self._tx() as conn:
                current = self._require_by_case_id(conn=conn, case_id=case_id)
                if current.status == "READY":
                    return current
                next_record = mark_outbox_record_ready(record=current, now=resolved_now)
                return self._write_transition(
                    conn=conn,
                    case_id=case_id,
                    next_record=next_record,
                    expected_source_statuses={"PENDING_OBJECT"},
                )
        except CriticalDependencyError:
            raise
        except InvariantViolation:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def transition_to_sent(
        self,
        *,
        case_id: str,
        now: datetime | None = None,
    ) -> OutboxRecordV1:
        resolved_now = _resolve_now(now)
        try:
            with self._tx() as conn:
                current = self._require_by_case_id(conn=conn, case_id=case_id)
                if current.status == "SENT":
                    return current
                next_record = mark_outbox_record_sent(record=current, now=resolved_now)
                return self._write_transition(
                    conn=conn,
                    case_id=case_id,
                    next_record=next_record,
                    expected_source_statuses={current.status},
                )
        except CriticalDependencyError:
            raise
        except InvariantViolation:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def transition_publish_failure(
        self,
        *,
        case_id: str,
        policy: OutboxPolicyV1,
        app_env: str,
        error_message: str,
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> OutboxRecordV1:
        resolved_now = _resolve_now(now)
        try:
            with self._tx() as conn:
                current = self._require_by_case_id(conn=conn, case_id=case_id)
                if current.status == "DEAD":
                    return current
                next_record = mark_outbox_record_publish_failure(
                    record=current,
                    policy=policy,
                    app_env=app_env,
                    error_message=error_message,
                    error_code=error_code,
                    now=resolved_now,
                )
                return self._write_transition(
                    conn=conn,
                    case_id=case_id,
                    next_record=next_record,
                    expected_source_statuses={current.status},
                )
        except CriticalDependencyError:
            raise
        except InvariantViolation:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def select_publishable(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[OutboxRecordV1]:
        resolved_now = _resolve_now(now)
        try:
            with self._tx() as conn:
                stmt = (
                    select(*_returning_columns())
                    .where(
                        or_(
                            outbox_table.c.status == "READY",
                            and_(
                                outbox_table.c.status == "RETRY",
                                or_(
                                    outbox_table.c.next_attempt_at.is_(None),
                                    outbox_table.c.next_attempt_at <= resolved_now,
                                ),
                            ),
                        )
                    )
                    .order_by(outbox_table.c.updated_at.asc())
                    .limit(limit)
                )
                rows = conn.execute(stmt).mappings().all()
                return [_row_to_record(row) for row in rows]
        except CriticalDependencyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def select_backlog_health(
        self,
        *,
        now: datetime | None = None,
    ) -> OutboxHealthSnapshot:
        resolved_now = _resolve_now(now)
        try:
            with self._tx() as conn:
                rows = (
                    conn.execute(
                        select(
                            outbox_table.c.status,
                            outbox_table.c.updated_at,
                        ).where(outbox_table.c.status.in_(OUTBOX_STATES))
                    )
                    .mappings()
                    .all()
                )

                counts_by_state = {state: 0 for state in OUTBOX_STATES}
                oldest_age_seconds_by_state = {
                    "PENDING_OBJECT": 0.0,
                    "READY": 0.0,
                    "RETRY": 0.0,
                    "DEAD": 0.0,
                }
                for row in rows:
                    status = str(row["status"])
                    if status in counts_by_state:
                        counts_by_state[status] += 1
                    if status in oldest_age_seconds_by_state:
                        updated_at = _as_aware_datetime(row["updated_at"])
                        age_seconds = max((resolved_now - updated_at).total_seconds(), 0.0)
                        oldest_age_seconds_by_state[status] = max(
                            oldest_age_seconds_by_state[status], age_seconds
                        )

                return OutboxHealthSnapshot(
                    pending_object_count=counts_by_state["PENDING_OBJECT"],
                    ready_count=counts_by_state["READY"],
                    retry_count=counts_by_state["RETRY"],
                    dead_count=counts_by_state["DEAD"],
                    sent_count=counts_by_state["SENT"],
                    oldest_pending_object_age_seconds=oldest_age_seconds_by_state["PENDING_OBJECT"],
                    oldest_ready_age_seconds=oldest_age_seconds_by_state["READY"],
                    oldest_retry_age_seconds=oldest_age_seconds_by_state["RETRY"],
                    oldest_dead_age_seconds=oldest_age_seconds_by_state["DEAD"],
                )
        except CriticalDependencyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def select_expired_for_cleanup(
        self,
        *,
        policy: OutboxPolicyV1,
        app_env: str,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[OutboxRecordV1]:
        resolved_now = _resolve_now(now)
        sent_cutoff = retention_cutoff_for_state(
            policy=policy,
            app_env=app_env,
            state="SENT",
            now=resolved_now,
        )
        dead_cutoff = retention_cutoff_for_state(
            policy=policy,
            app_env=app_env,
            state="DEAD",
            now=resolved_now,
        )
        try:
            with self._tx() as conn:
                stmt = (
                    select(*_returning_columns())
                    .where(
                        or_(
                            and_(
                                outbox_table.c.status == "SENT",
                                outbox_table.c.updated_at <= sent_cutoff,
                            ),
                            and_(
                                outbox_table.c.status == "DEAD",
                                outbox_table.c.updated_at <= dead_cutoff,
                            ),
                        )
                    )
                    .order_by(outbox_table.c.updated_at.asc())
                    .limit(limit)
                )
                rows = conn.execute(stmt).mappings().all()
                return [_row_to_record(row) for row in rows]
        except CriticalDependencyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def get_by_case_id(self, case_id: str) -> OutboxRecordV1 | None:
        try:
            with self._tx() as conn:
                return self._get_by_case_id(conn=conn, case_id=case_id)
        except CriticalDependencyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._wrap_repo_exc(exc)

    def _run_ddl(self) -> None:
        try:
            create_outbox_table(self._engine)
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

    def _get_by_case_id(self, *, conn: Connection, case_id: str) -> OutboxRecordV1 | None:
        stmt = select(*_returning_columns()).where(outbox_table.c.case_id == case_id)
        row = conn.execute(stmt).mappings().one_or_none()
        if row is None:
            return None
        return _row_to_record(row)

    def _require_by_case_id(self, *, conn: Connection, case_id: str) -> OutboxRecordV1:
        record = self._get_by_case_id(conn=conn, case_id=case_id)
        if record is None:
            raise InvariantViolation(f"outbox record not found for case_id={case_id}")
        return record

    def _write_transition(
        self,
        *,
        conn: Connection,
        case_id: str,
        next_record: OutboxRecordV1,
        expected_source_statuses: set[str],
    ) -> OutboxRecordV1:
        result = conn.execute(
            update(outbox_table)
            .where(
                and_(
                    outbox_table.c.case_id == case_id,
                    outbox_table.c.status.in_(tuple(sorted(expected_source_statuses))),
                )
            )
            .values(
                status=next_record.status,
                updated_at=next_record.updated_at,
                delivery_attempts=next_record.delivery_attempts,
                next_attempt_at=next_record.next_attempt_at,
                last_error_code=next_record.last_error_code,
                last_error_message=next_record.last_error_message,
            )
            .returning(*_returning_columns())
        )
        row = result.mappings().one_or_none()
        if row is not None:
            return _row_to_record(row)

        latest = self._require_by_case_id(conn=conn, case_id=case_id)
        if latest.status == next_record.status:
            return latest
        raise InvariantViolation(
            "outbox transition source-state guard failed "
            f"for case_id={case_id}; expected one of {sorted(expected_source_statuses)} "
            f"but found {latest.status}"
        )

    @staticmethod
    def _wrap_repo_exc(exc: Exception) -> CriticalDependencyError:
        return CriticalDependencyError(f"outbox repository operation failed: {exc}")

    @staticmethod
    def _assert_casefile_payload_match(
        *,
        existing: OutboxRecordV1,
        confirmed_casefile: OutboxReadyCasefileV1,
    ) -> None:
        if existing.casefile_object_path != confirmed_casefile.object_path:
            raise InvariantViolation("existing outbox case_id has different casefile_object_path")
        if existing.triage_hash != confirmed_casefile.triage_hash:
            raise InvariantViolation("existing outbox case_id has different triage_hash")


def _row_to_record(row: dict[str, object]) -> OutboxRecordV1:
    return OutboxRecordV1(
        case_id=str(row["case_id"]),
        status=str(row["status"]),
        casefile_object_path=str(row["casefile_object_path"]),
        triage_hash=str(row["triage_hash"]),
        created_at=_as_aware_datetime(row["created_at"]),
        updated_at=_as_aware_datetime(row["updated_at"]),
        delivery_attempts=int(row["delivery_attempts"]),
        next_attempt_at=_as_aware_datetime_or_none(row["next_attempt_at"]),
        last_error_code=row["last_error_code"],
        last_error_message=row["last_error_message"],
    )


def _resolve_now(now: datetime | None) -> datetime:
    resolved = now or datetime.now(tz=UTC)
    if resolved.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return resolved


def _returning_columns() -> tuple:
    return (
        outbox_table.c.case_id,
        outbox_table.c.status,
        outbox_table.c.casefile_object_path,
        outbox_table.c.triage_hash,
        outbox_table.c.created_at,
        outbox_table.c.updated_at,
        outbox_table.c.delivery_attempts,
        outbox_table.c.next_attempt_at,
        outbox_table.c.last_error_code,
        outbox_table.c.last_error_message,
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


@dataclass(frozen=True)
class OutboxHealthSnapshot:
    """Queue depth and oldest-age snapshot for outbox health monitoring."""

    pending_object_count: int
    ready_count: int
    retry_count: int
    dead_count: int
    sent_count: int
    oldest_pending_object_age_seconds: float
    oldest_ready_age_seconds: float
    oldest_retry_age_seconds: float
    oldest_dead_age_seconds: float
