from datetime import datetime
from sqlalchemy import create_engine, text

DB_URL = "sqlite:///kubera.db"
engine  = create_engine(DB_URL, future=True, echo=False)


def init_db() -> None:
    """Create table + unique index if they don’t exist yet."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pod_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace   TEXT NOT NULL,
                pod_name    TEXT NOT NULL,
                issue_type  TEXT NOT NULL,
                severity    TEXT NOT NULL,
                first_seen  TEXT NOT NULL,      -- iso‑string
                last_seen   TEXT                -- NULL ⇒ ongoing
            );
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_unique
                ON pod_alerts(namespace, pod_name, issue_type, first_seen);
        """))


def record_failure(namespace: str,
                   pod_name:  str,
                   issue:     str,
                   severity:  str,
                   first_dt,
                   last_dt) -> None:
    """
    Inserts or updates one failure episode.
    last_dt == None  ⇒ still running.
    """
    first_iso = first_dt.replace(tzinfo=None).isoformat() + "Z"
    last_iso  = None if last_dt is None else last_dt.isoformat()

    with engine.begin() as conn:
        # INSERT … ON CONFLICT … DO UPDATE (SQLite ≥ 3.24)
        conn.execute(text("""
            INSERT INTO pod_alerts (namespace, pod_name, issue_type,
                                    severity, first_seen, last_seen)
            VALUES (:ns, :pod, :issue, :sev, :first, :last)
            ON CONFLICT(namespace, pod_name, issue_type, first_seen)
            DO UPDATE SET last_seen = excluded.last_seen;
        """),
        dict(ns=namespace, pod=pod_name, issue=issue,
             sev=severity, first=first_iso, last=last_iso))
