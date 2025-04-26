#!/usr/bin/env python3
"""
Script to clean up the KubERA database by removing old entries
and merging duplicate events that occur close together in time.
"""

import argparse

from db import cleanup_duplicate_events


def main():
    parser = argparse.ArgumentParser(
        description="Clean up the KubERA database by removing old entries and merging duplicates"
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=30,
        help="Maximum age in days for events to keep (default: 30)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without making changes"
    )
    args = parser.parse_args()

    if args.dry_run:
        print(
            f"DRY RUN: Would clean up events older than {args.max_age} days and merge duplicates")
        return

    result = cleanup_duplicate_events(max_age_days=args.max_age)

    print("Database cleanup complete!")
    print(f"- Removed {result['old_records_removed']} old records")
    print(f"- Merged {result['duplicates_merged']} duplicate records")
    print(
        f"- Total reduction: {result['old_records_removed'] + result['duplicates_merged']} records")


if __name__ == "__main__":
    main()
