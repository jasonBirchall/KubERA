#!/usr/bin/env python3
"""
Script to clean up the KubERA database by removing old entries
across all data source tables.
"""

import argparse

from db import cleanup_old_alerts


def main():
    parser = argparse.ArgumentParser(
        description="Clean up the KubERA database by removing old entries"
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
            f"DRY RUN: Would clean up events older than {args.max_age} days")
        return

    result = cleanup_old_alerts(max_age_days=args.max_age)

    print("Database cleanup complete!")
    print(f"- Removed {result.get('k8s_alerts', 0)} Kubernetes alert records")
    print(
        f"- Removed {result.get('prometheus_alerts', 0)} Prometheus alert records")
    print(f"- Removed {result.get('argocd_alerts', 0)} ArgoCD alert records")
    print(f"- Total reduction: {sum(result.values())} records")


if __name__ == "__main__":
    main()
