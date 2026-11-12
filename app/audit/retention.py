"""Audit retention CLI (lane 2 / Stream B).

Usage:
    python -m app.audit.retention --days 365 [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from app.audit.repository import AuditRepository
from app.config import get_audit_retention_days


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Purge Tijori audit logs older than a retention threshold.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=get_audit_retention_days(),
        help="Retention period in days (rows older than this are purged; default from env/config).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the number of eligible rows without deleting them.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Optional path to SQLite audit database.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo = AuditRepository(db_path=args.db_path)
    count = repo.purge_older_than(days=args.days, dry_run=args.dry_run)

    if args.dry_run:
        print(f"audit retention (dry run): would purge {count} rows older than {args.days} days")
    else:
        print(f"audit retention: purged {count} rows older than {args.days} days")

    return 0


if __name__ == "__main__":
    sys.exit(main())
