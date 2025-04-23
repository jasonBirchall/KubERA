from datetime import datetime
import os
from sqlalchemy import create_engine, text, inspect

DB_URL = "sqlite:///kubera.db"
engine = create_engine(DB_URL, future=True, echo=False)


def check_if_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def migrate_db():
    """
    Check if we need to migrate the database schema to add the source column.
    This handles updating an existing database without losing data.
    """
    with engine.begin() as conn:
        # Check if the pod_alerts table exists
        if not inspect(engine).has_table('pod_alerts'):
            print("Creating new database from scratch")
            init_db()
            return
        
        # Check if the source column already exists
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
            
            print("Database migration completed successfully")


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
                UNIQUE (namespace, pod_name, issue_type, first_seen, source)
            );
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_unique
                ON pod_alerts(namespace, pod_name, issue_type, first_seen, source);
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

    with engine.begin() as conn:
        # INSERT … ON CONFLICT … DO UPDATE (SQLite ≥ 3.24)
        conn.execute(text("""
            INSERT INTO pod_alerts (namespace, pod_name, issue_type,
                                    severity, first_seen, last_seen, source)
            VALUES (:ns, :pod, :issue, :sev, :first, :last, :source)
            ON CONFLICT(namespace, pod_name, issue_type, first_seen, source)
            DO UPDATE SET last_seen = excluded.last_seen;
        """),
        dict(ns=namespace, pod=pod_name, issue=issue,
             sev=severity, first=first_iso, last=last_iso, source=source))


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
