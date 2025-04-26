#!/usr/bin/env python3
"""
Reset the KubERA database and establish new multi-table structure.
"""

import os

from sqlalchemy import create_engine, text

DB_URL = "sqlite:///kubera.db"


def reset_db():
    """Remove the existing database file and create new tables with proper schema"""
    # Remove existing database
    db_file = 'kubera.db'
    if os.path.exists(db_file):
        print(f"Removing existing database: {db_file}")
        os.remove(db_file)

    # Create new database with updated schema
    engine = create_engine(DB_URL, future=True)

    with engine.begin() as conn:
        # Create Kubernetes alerts table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS k8s_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace   TEXT NOT NULL,
                pod_name    TEXT NOT NULL,
                issue_type  TEXT NOT NULL,
                severity    TEXT NOT NULL,
                first_seen  TEXT NOT NULL,      -- iso‑string
                last_seen   TEXT,               -- NULL ⇒ ongoing
                event_hash  TEXT UNIQUE,
                UNIQUE (namespace, pod_name, issue_type, first_seen)
            );
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_k8s_event_hash
                ON k8s_alerts(event_hash);
        """))

        # Create Prometheus alerts table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS prometheus_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace   TEXT NOT NULL,
                pod_name    TEXT NOT NULL,
                alert_name  TEXT NOT NULL,
                severity    TEXT NOT NULL,
                first_seen  TEXT NOT NULL,
                last_seen   TEXT,
                event_hash  TEXT UNIQUE,
                metric_value REAL,
                UNIQUE (namespace, pod_name, alert_name, first_seen)
            );
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_prometheus_event_hash
                ON prometheus_alerts(event_hash);
        """))

        # Create ArgoCD alerts table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS argocd_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                application_name TEXT NOT NULL,
                issue_type  TEXT NOT NULL,
                severity    TEXT NOT NULL,
                first_seen  TEXT NOT NULL,
                last_seen   TEXT,
                event_hash  TEXT UNIQUE,
                sync_status TEXT,
                health_status TEXT,
                UNIQUE (application_name, issue_type, first_seen)
            );
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_argocd_event_hash
                ON argocd_alerts(event_hash);
        """))

        # Create a view that combines all alerts
        conn.execute(text("""
            CREATE VIEW all_alerts AS
            SELECT
                id, namespace, pod_name as name, issue_type, severity,
                first_seen, last_seen, 'kubernetes' as source, event_hash
            FROM k8s_alerts

            UNION ALL

            SELECT
                id, namespace, pod_name as name, alert_name as issue_type, severity,
                first_seen, last_seen, 'prometheus' as source, event_hash
            FROM prometheus_alerts

            UNION ALL

            SELECT
                id, NULL as namespace, application_name as name, issue_type, severity,
                first_seen, last_seen, 'argocd' as source, event_hash
            FROM argocd_alerts;
        """))

    print("Database reset successfully with new multi-table structure")


if __name__ == "__main__":
    reset_db()
