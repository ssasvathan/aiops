"""Entry point for aiops-triage-pipeline."""

import argparse


def main() -> None:
    """Parse --mode argument and dispatch to the appropriate pipeline mode."""
    parser = argparse.ArgumentParser(description="AIOps Triage Pipeline")
    parser.add_argument(
        "--mode",
        choices=["hot-path", "cold-path", "outbox-publisher"],
        required=True,
        help="Pipeline mode to run",
    )
    args = parser.parse_args()
    print(f"Starting {args.mode} mode...")


if __name__ == "__main__":
    main()
