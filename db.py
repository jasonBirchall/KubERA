import hashlib
import os
from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect, text

DB_URL = "sqlite:///kubera.db"
engine = create_engine(DB_URL, future=True, echo=False)


def create_event_hash(namespace, pod_name, issue_type, source="kubernetes"):
    """
    Create a unique hash for a pod event based on its identifying attributes.
    This helps with deduplication regardless of timestamp.

    Args:
        namespace: The kubernetes namespace
        pod_name: The name of the pod
        issue_type: The type of issue/alert
        source: The data source ('kubernetes', 'prometheus', etc.)

    Returns:
        A hex digest hash string
    """
    # Create a consistent string to hash
    hash_string = f"{namespace}:{pod_name}:{issue_type}:{source}".lower()
    # Use MD5 for speed and sufficient uniqueness for our purposes
    return hashlib.md5(hash_string.encode()).hexdigest()


def check_if_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def migrate_db():
    """
    Check if we need to migrate the database schema to add new columns.
    This handles updating an existing database without losing data.
    """
    with engine.begin() as conn:
        # Check if the pod_alerts table exists
        if not inspect(engine).has_table('pod_alerts'):
            print("Creating new database from scratch")
            init_db()
            return

        # Check and add source column if needed
        if not check_if_column_exists(conn, 'pod_alerts', 'source'):
            print("Migrating database: Adding 'source' column")

            # 1. Create a backup of the current table data
            conn.execute(text("""
                CREATE TABLE pod_alerts_backup AS
                SELECT * FROM pod_alerts;
            """))

            # 2. Drop the old table and recreate with new schema
            conn.execute(text("DROP TABLE pod_alerts;"))

            # 3. Create the new table with the updated schema
            conn.execute(text("""
                CREATE TABLE pod_alerts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace   TEXT NOT NULL,
                    pod_name    TEXT NOT NULL,
                    issue_type  TEXT NOT NULL,
                    severity    TEXT NOT NULL,
                    first_seen  TEXT NOT NULL,      -- iso‑string
                    last_seen   TEXT,               -- NULL ⇒ ongoing
                    source      TEXT DEFAULT 'kubernetes',  -- 'kubernetes' or 'prometheus'
                    UNIQUE (namespace, pod_name, issue_type, first_seen, source)
                );
            """))

            # 4. Copy the data back, setting a default value for the source column
            conn.execute(text("""
                INSERT INTO pod_alerts (id, namespace, pod_name, issue_type, severity, first_seen, last_seen, source)
                SELECT id, namespace, pod_name, issue_type, severity, first_seen, last_seen, 'kubernetes' FROM pod_alerts_backup;
            """))

            # 5. Drop the backup table
            conn.execute(text("DROP TABLE pod_alerts_backup;"))

            # 6. Create the new index
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_unique
                    ON pod_alerts(namespace, pod_name, issue_type, first_seen, source);
            """))

            print("Source column migration completed successfully")

        # Check and add event_hash column if needed
        if not check_if_column_exists(conn, 'pod_alerts', 'event_hash'):
            print("Migrating database: Adding 'event_hash' column")

            # 1. Add the event_hash column
            conn.execute(text("""
                ALTER TABLE pod_alerts
                ADD COLUMN event_hash TEXT;
            """))

            # 2. Update existing records to add the hash
            conn.execute(text("""
                UPDATE pod_alerts
                SET event_hash = LOWER(
                    HEX(
                        RANDOMBLOB(16)
                    )
                );
            """))

            # 3. Create an index on the hash for faster lookups
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_event_hash
                    ON pod_alerts(event_hash);
            """))

            print("Event hash column migration completed successfully")

            # 4. Calculate proper hash values for existing records
            rows = conn.execute(text("""
                SELECT id, namespace, pod_name, issue_type, source
                FROM pod_alerts
            """)).fetchall()

            for row in rows:
                # Handle both dictionary-like and tuple-like results
                try:
                    # Dictionary-like access
                    row_id = row['id']
                    namespace = row['namespace']
                    pod_name = row['pod_name']
                    issue_type = row['issue_type']
                    source = row['source']
                except (TypeError, KeyError):
                    # Tuple-like access - use indices
                    row_id = row[0]
                    namespace = row[1]
                    pod_name = row[2]
                    issue_type = row[3]
                    source = row[4] if len(row) > 4 else 'kubernetes'

                event_hash = create_event_hash(
                    namespace,
                    pod_name,
                    issue_type,
                    source
                )

                conn.execute(text("""
                    UPDATE pod_alerts
                    SET event_hash = :hash
                    WHERE id = :id
                """), {'hash': event_hash, 'id': row_id})

            print(f"Updated hash values for {len(rows)} existing records")


def init_db() -> None:
    """Create table + unique index if they don't exist yet."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pod_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace   TEXT NOT NULL,
                pod_name    TEXT NOT NULL,
                issue_type  TEXT NOT NULL,
                severity    TEXT NOT NULL,
                first_seen  TEXT NOT NULL,      -- iso‑string
                last_seen   TEXT,               -- NULL ⇒ ongoing
                source      TEXT DEFAULT 'kubernetes',  -- 'kubernetes' or 'prometheus'
                event_hash  TEXT,               -- Hash of namespace:pod_name:issue_type:source
                UNIQUE (namespace, pod_name, issue_type, first_seen, source)
            );
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_unique
                ON pod_alerts(namespace, pod_name, issue_type, first_seen, source);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_event_hash
                ON pod_alerts(event_hash);
        """))


def record_failure(namespace: str,
                   pod_name: str,
                   issue: str,
                   severity: str,
                   first_dt,
                   last_dt,
                   source: str = "kubernetes") -> None:
    """
    Inserts or updates one failure episode.
    last_dt == None  ⇒ still running.

    Args:
        namespace: The kubernetes namespace
        pod_name: The name of the pod
        issue: The type of issue (e.g., "CrashLoopBackOff")
        severity: Severity level ("high", "medium", "low")
        first_dt: When the issue was first seen (datetime object)
        last_dt: When the issue was last seen or None if still ongoing
        source: Data source ("kubernetes" or "prometheus")
    """
    first_iso = first_dt.replace(tzinfo=None).isoformat() + "Z"
    last_iso = None if last_dt is None else last_dt.isoformat()

    # Generate the event hash
    event_hash = create_event_hash(namespace, pod_name, issue, source)

    with engine.begin() as conn:
        # First, check if we have an existing record with the same hash
        existing = conn.execute(text("""
            SELECT id, first_seen, last_seen
            FROM pod_alerts
            WHERE event_hash = :hash
            ORDER BY first_seen ASC
            LIMIT 1
        """), {'hash': event_hash}).fetchone()

        if existing:
            # Handle both dictionary-like and tuple-like results
            try:
                # Dictionary-like access
                existing_id = existing['id']
            except (TypeError, KeyError):
                # Tuple-like access
                existing_id = existing[0]

            # Update the existing record to extend the time range if needed
            conn.execute(text("""
                UPDATE pod_alerts
                SET last_seen = :last
                WHERE id = :id
            """), {'last': last_iso, 'id': existing_id})
        else:
            # Insert a new record
            conn.execute(text("""
                INSERT INTO pod_alerts (
                    namespace, pod_name, issue_type, severity,
                    first_seen, last_seen, source, event_hash
                )
                VALUES (
                    :ns, :pod, :issue, :sev,
                    :first, :last, :source, :hash
                )
            """), {
                'ns': namespace,
                'pod': pod_name,
                'issue': issue,
                'sev': severity,
                'first': first_iso,
                'last': last_iso,
                'source': source,
                'hash': event_hash
            })


def reset_db():
    """Remove the existing database file to start fresh"""
    db_file = 'kubera.db'
    if os.path.exists(db_file):
        print(f"Removing existing database: {db_file}")
        os.remove(db_file)
        print("Database reset successfully")
    else:
        print("No existing database found to reset")

    # Initialize a new database
    init_db()


def cleanup_duplicate_events(max_age_days=30):
    """
    Cleanup the database by:
    1. Removing entries older than max_age_days
    2. Merging duplicates that have the same event_hash

    Args:
        max_age_days: Maximum age of records to keep in days
    """
    with engine.begin() as conn:
        # First, remove old records
        cutoff_date = (datetime.now() -
                       timedelta(days=max_age_days)).isoformat()
        delete_query = """
            DELETE FROM pod_alerts
            WHERE first_seen < :cutoff_date
        """
        result = conn.execute(text(delete_query), {"cutoff_date": cutoff_date})
        old_records_removed = result.rowcount
        print(f"Removed {old_records_removed} old events from database")

        # Check if event_hash column exists before trying to use it
        has_event_hash = check_if_column_exists(
            conn, 'pod_alerts', 'event_hash')

        if not has_event_hash:
            print("event_hash column doesn't exist - skipping duplicate cleanup")
            return {
                "old_records_removed": old_records_removed,
                "duplicates_merged": 0
            }

        # Find duplicates based on event_hash
        duplicates = conn.execute(text("""
            SELECT event_hash, COUNT(*) as count
            FROM pod_alerts
            GROUP BY event_hash
            HAVING COUNT(*) > 1
        """)).fetchall()

        total_merged = 0
        for dup in duplicates:
            # Handle both dictionary-like and tuple-like results
            try:
                # Dictionary-like access
                event_hash = dup['event_hash']
            except (TypeError, KeyError):
                # Tuple-like access
                event_hash = dup[0]

            # Get all records with this hash
            records = conn.execute(text("""
                SELECT id, first_seen, last_seen
                FROM pod_alerts
                WHERE event_hash = :hash
                ORDER BY first_seen ASC
            """), {'hash': event_hash}).fetchall()

            if not records:
                continue

            # Handle both dictionary-like and tuple-like results for records
            try:
                # Dictionary-like access
                earliest_id = records[0]['id']
                earliest_first_seen = records[0]['first_seen']
            except (TypeError, KeyError):
                # Tuple-like access
                earliest_id = records[0][0]
                earliest_first_seen = records[0][1]

            # Find the earliest first_seen and latest last_seen
            latest_last_seen = None

            for record in records:
                try:
                    # Dictionary-like access
                    last_seen = record['last_seen']
                except (TypeError, KeyError):
                    # Tuple-like access
                    last_seen = record[2]

                if last_seen is None:
                    latest_last_seen = None
                    break
                if latest_last_seen is None or last_seen > latest_last_seen:
                    latest_last_seen = last_seen

            # Update the earliest record with the combined time range
            conn.execute(text("""
                UPDATE pod_alerts
                SET last_seen = :last_seen
                WHERE id = :id
            """), {'last_seen': latest_last_seen, 'id': earliest_id})

            # Delete the other records
            delete_result = conn.execute(text("""
                DELETE FROM pod_alerts
                WHERE event_hash = :hash AND id != :id
            """), {'hash': event_hash, 'id': earliest_id})

            total_merged += delete_result.rowcount

        print(f"Merged {total_merged} duplicate events")

        # Vacuum the database to reclaim space - must be outside a transaction
        # End the current transaction

    # Execute VACUUM outside of any transaction
    with engine.connect() as conn:
        conn.execute(text("VACUUM"))
        conn.commit()

    return {
        "old_records_removed": old_records_removed,
        "duplicates_merged": total_merged
    }
