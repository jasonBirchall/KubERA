import hashlib
import os
from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect, text

DB_URL = "sqlite:///kubera.db"
engine = create_engine(DB_URL, future=True, echo=False)


def create_event_hash(namespace, name, issue_type, source="kubernetes"):
    """
    Create a unique hash for an event based on its identifying attributes.
    This helps with deduplication regardless of timestamp.

    Args:
        namespace: The kubernetes namespace (can be None for ArgoCD)
        name: The pod name or app name depending on source
        issue_type: The type of issue/alert
        source: The data source ('kubernetes', 'prometheus', 'argocd')

    Returns:
        A hex digest hash string
    """
    # Create a consistent string to hash
    if namespace:
        hash_string = f"{namespace}:{name}:{issue_type}:{source}".lower()
    else:
        # ArgoCD doesn't use namespace
        hash_string = f"{name}:{issue_type}:{source}".lower()
    # Use MD5 for speed and sufficient uniqueness for our purposes
    return hashlib.md5(hash_string.encode()).hexdigest()


def check_if_table_exists(conn, table_name):
    """Check if a table exists in the database"""
    inspector = inspect(engine)
    return inspector.has_table(table_name)


def init_db() -> None:
    """Initialize the database with the new multi-table structure if tables don't exist yet."""
    with engine.begin() as conn:
        # Only create tables if they don't exist
        if not check_if_table_exists(conn, 'k8s_alerts'):
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

        if not check_if_table_exists(conn, 'prometheus_alerts'):
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

        if not check_if_table_exists(conn, 'argocd_alerts'):
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

        # Create the view if it doesn't exist
        # SQLite doesn't have CREATE VIEW IF NOT EXISTS, so we drop first
        try:
            conn.execute(text("DROP VIEW IF EXISTS all_alerts;"))
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
        except Exception as e:
            print(f"Error creating view: {e}")


def record_k8s_failure(namespace: str,
                       pod_name: str,
                       issue: str,
                       severity: str,
                       first_dt,
                       last_dt) -> None:
    """
    Records a Kubernetes failure event.

    Args:
        namespace: The kubernetes namespace
        pod_name: The name of the pod
        issue: The type of issue (e.g., "CrashLoopBackOff")
        severity: Severity level ("high", "medium", "low")
        first_dt: When the issue was first seen (datetime object)
        last_dt: When the issue was last seen or None if still ongoing
    """
    first_iso = first_dt.replace(tzinfo=None).isoformat() + "Z"
    last_iso = None if last_dt is None else last_dt.isoformat() + "Z"

    # Generate the event hash
    event_hash = create_event_hash(namespace, pod_name, issue, "kubernetes")

    with engine.begin() as conn:
        # Check if we have an existing record with the same hash
        existing = conn.execute(text("""
            SELECT id, first_seen, last_seen
            FROM k8s_alerts
            WHERE event_hash = :hash
            LIMIT 1
        """), {'hash': event_hash}).fetchone()

        if existing:
            # Update the existing record to extend the time range if needed
            conn.execute(text("""
                UPDATE k8s_alerts
                SET last_seen = :last
                WHERE id = :id
            """), {'last': last_iso, 'id': existing[0]})
        else:
            # Insert a new record
            conn.execute(text("""
                INSERT INTO k8s_alerts (
                    namespace, pod_name, issue_type, severity,
                    first_seen, last_seen, event_hash
                )
                VALUES (
                    :ns, :pod, :issue, :sev,
                    :first, :last, :hash
                )
            """), {
                'ns': namespace,
                'pod': pod_name,
                'issue': issue,
                'sev': severity,
                'first': first_iso,
                'last': last_iso,
                'hash': event_hash
            })


def record_prometheus_alert(namespace: str,
                            pod_name: str,
                            alert_name: str,
                            severity: str,
                            first_dt,
                            last_dt,
                            metric_value: float = None) -> None:
    """
    Records a Prometheus alert.

    Args:
        namespace: The kubernetes namespace
        pod_name: The name of the pod
        alert_name: The name of the Prometheus alert
        severity: Severity level ("high", "medium", "low")
        first_dt: When the issue was first seen (datetime object)
        last_dt: When the issue was last seen or None if still ongoing
        metric_value: The value of the metric that triggered the alert
    """
    first_iso = first_dt.replace(tzinfo=None).isoformat() + "Z"
    last_iso = None if last_dt is None else last_dt.isoformat() + "Z"

    # Generate the event hash
    event_hash = create_event_hash(
        namespace, pod_name, alert_name, "prometheus")

    with engine.begin() as conn:
        # Check if we have an existing record with the same hash
        existing = conn.execute(text("""
            SELECT id, first_seen, last_seen
            FROM prometheus_alerts
            WHERE event_hash = :hash
            LIMIT 1
        """), {'hash': event_hash}).fetchone()

        if existing:
            # Update the existing record
            conn.execute(text("""
                UPDATE prometheus_alerts
                SET last_seen = :last,
                    metric_value = COALESCE(:metric_value, metric_value)
                WHERE id = :id
            """), {
                'last': last_iso,
                'metric_value': metric_value,
                'id': existing[0]
            })
        else:
            # Insert a new record
            conn.execute(text("""
                INSERT INTO prometheus_alerts (
                    namespace, pod_name, alert_name, severity,
                    first_seen, last_seen, event_hash, metric_value
                )
                VALUES (
                    :ns, :pod, :alert, :sev,
                    :first, :last, :hash, :metric_value
                )
            """), {
                'ns': namespace,
                'pod': pod_name,
                'alert': alert_name,
                'sev': severity,
                'first': first_iso,
                'last': last_iso,
                'hash': event_hash,
                'metric_value': metric_value
            })


def record_argocd_alert(application_name: str,
                        issue_type: str,
                        severity: str,
                        first_dt,
                        last_dt,
                        sync_status: str = None,
                        health_status: str = None) -> None:
    """
    Records an ArgoCD alert.

    Args:
        application_name: The name of the ArgoCD application
        issue_type: The type of issue
        severity: Severity level ("high", "medium", "low")
        first_dt: When the issue was first seen (datetime object)
        last_dt: When the issue was last seen or None if still ongoing
        sync_status: The sync status of the application
        health_status: The health status of the application
    """
    first_iso = first_dt.replace(tzinfo=None).isoformat() + "Z"
    last_iso = None if last_dt is None else last_dt.isoformat() + "Z"

    # Generate the event hash - ArgoCD doesn't use namespace
    event_hash = create_event_hash(
        None, application_name, issue_type, "argocd")

    with engine.begin() as conn:
        # Check if we have an existing record with the same hash
        existing = conn.execute(text("""
            SELECT id, first_seen, last_seen
            FROM argocd_alerts
            WHERE event_hash = :hash
            LIMIT 1
        """), {'hash': event_hash}).fetchone()

        if existing:
            # Update the existing record
            conn.execute(text("""
                UPDATE argocd_alerts
                SET last_seen = :last,
                    sync_status = COALESCE(:sync, sync_status),
                    health_status = COALESCE(:health, health_status)
                WHERE id = :id
            """), {
                'last': last_iso,
                'sync': sync_status,
                'health': health_status,
                'id': existing[0]
            })
        else:
            # Insert a new record
            conn.execute(text("""
                INSERT INTO argocd_alerts (
                    application_name, issue_type, severity,
                    first_seen, last_seen, event_hash,
                    sync_status, health_status
                )
                VALUES (
                    :app, :issue, :sev,
                    :first, :last, :hash,
                    :sync, :health
                )
            """), {
                'app': application_name,
                'issue': issue_type,
                'sev': severity,
                'first': first_iso,
                'last': last_iso,
                'hash': event_hash,
                'sync': sync_status,
                'health': health_status
            })


def get_all_alerts(hours=24, namespace=None, source=None):
    """
    Retrieve alerts from the all_alerts view with optional filtering.

    Args:
        hours: Number of hours to look back
        namespace: Filter by namespace (optional)
        source: Filter by source (optional)

    Returns:
        List of dictionary-like objects with alert data
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat() + "Z"

    conditions = ["(first_seen >= :cutoff OR last_seen IS NULL)"]
    params = {"cutoff": cutoff_iso}

    if namespace:
        conditions.append("namespace = :namespace")
        params["namespace"] = namespace

    if source:
        conditions.append("source = :source")
        params["source"] = source

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT *
        FROM all_alerts
        WHERE {where_clause}
        ORDER BY first_seen DESC
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), params).mappings().all()
        return [dict(row) for row in result]


def cleanup_old_alerts(max_age_days=30):
    """
    Remove alerts older than the specified number of days from all tables.

    Args:
        max_age_days: Maximum age of records to keep in days

    Returns:
        Dictionary with counts of records removed from each table
    """
    cutoff_date = (datetime.now() - timedelta(days=max_age_days)
                   ).isoformat() + "Z"

    removed_counts = {}

    with engine.begin() as conn:
        # Clean up Kubernetes alerts
        k8s_result = conn.execute(text("""
            DELETE FROM k8s_alerts
            WHERE first_seen < :cutoff_date AND (last_seen IS NOT NULL)
        """), {"cutoff_date": cutoff_date})
        removed_counts["k8s_alerts"] = k8s_result.rowcount

        # Clean up Prometheus alerts
        prom_result = conn.execute(text("""
            DELETE FROM prometheus_alerts
            WHERE first_seen < :cutoff_date AND (last_seen IS NOT NULL)
        """), {"cutoff_date": cutoff_date})
        removed_counts["prometheus_alerts"] = prom_result.rowcount

        # Clean up ArgoCD alerts
        argocd_result = conn.execute(text("""
            DELETE FROM argocd_alerts
            WHERE first_seen < :cutoff_date AND (last_seen IS NOT NULL)
        """), {"cutoff_date": cutoff_date})
        removed_counts["argocd_alerts"] = argocd_result.rowcount

    # Vacuum the database to reclaim space
    with engine.connect() as conn:
        conn.execute(text("VACUUM"))
        conn.commit()

    return removed_counts


def reset_db():
    """Call the standalone reset_db.py script"""
    from reset_db import reset_db as reset_db_function
    reset_db_function()


def migrate_db():
    """
    For compatibility with existing code.
    Initialize the new database structure.
    """
    init_db()


# Legacy function for backward compatibility
def record_failure(namespace: str,
                   pod_name: str,
                   issue: str,
                   severity: str,
                   first_dt,
                   last_dt,
                   source: str = "kubernetes") -> None:
    """
    Legacy compatibility function that routes to the appropriate record function.
    """
    if source == "kubernetes":
        record_k8s_failure(namespace, pod_name, issue,
                           severity, first_dt, last_dt)
    elif source == "prometheus":
        record_prometheus_alert(namespace, pod_name,
                                issue, severity, first_dt, last_dt)
    elif source == "argocd":
        record_argocd_alert(pod_name, issue, severity, first_dt, last_dt)


def get_active_alerts(hours=24, namespace=None, source=None):
    """
    Retrieve only active/ongoing alerts (where last_seen is NULL) from the all_alerts view
    with optional filtering.

    Args:
        hours: Number of hours to look back
        namespace: Filter by namespace (optional)
        source: Filter by source (optional)

    Returns:
        List of dictionary-like objects with alert data
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat() + "Z"

    conditions = ["first_seen >= :cutoff AND last_seen IS NULL"]
    params = {"cutoff": cutoff_iso}

    if namespace:
        conditions.append("namespace = :namespace")
        params["namespace"] = namespace

    if source:
        conditions.append("source = :source")
        params["source"] = source

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT *
        FROM all_alerts
        WHERE {where_clause}
        ORDER BY first_seen DESC
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), params).mappings().all()
        return [dict(row) for row in result]


def get_active_alerts_deduplicated(hours=24, namespace=None, source=None):
    """
    Retrieve only active/ongoing alerts (where last_seen is NULL) from the all_alerts view,
    with deduplication based on namespace/pod name (keeping highest priority).

    Args:
        hours: Number of hours to look back
        namespace: Filter by namespace (optional)
        source: Filter by source (optional)

    Returns:
        List of dictionary-like objects with alert data, deduplicated by namespace/pod name
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat() + "Z"

    conditions = ["first_seen >= :cutoff AND last_seen IS NULL"]
    params = {"cutoff": cutoff_iso}

    if namespace:
        conditions.append("namespace = :namespace")
        params["namespace"] = namespace

    if source:
        conditions.append("source = :source")
        params["source"] = source

    where_clause = " AND ".join(conditions)

    # This query uses a window function to get the highest severity alert for each namespace/pod combination
    # We map severity to a numeric value (high=1, medium=2, low=3) for ordering
    query = f"""
        WITH ranked_alerts AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY namespace, name
                    ORDER BY
                        CASE
                            WHEN severity = 'high' THEN 1
                            WHEN severity = 'medium' THEN 2
                            WHEN severity = 'low' THEN 3
                            ELSE 4
                        END
                ) as priority_rank
            FROM all_alerts
            WHERE {where_clause}
        )
        SELECT id, namespace, name, issue_type, severity, first_seen, last_seen, source, event_hash
        FROM ranked_alerts
        WHERE priority_rank = 1
        ORDER BY first_seen DESC
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), params).mappings().all()
        return [dict(row) for row in result]


def get_all_alerts_deduplicated(hours=24, namespace=None, source=None):
    """
    Retrieve alerts from the all_alerts view with optional filtering.
    When duplicates of namespace/pod name exist, only returns the highest priority alert.

    Args:
        hours: Number of hours to look back
        namespace: Filter by namespace (optional)
        source: Filter by source (optional)

    Returns:
        List of dictionary-like objects with alert data, deduplicated by namespace/pod name
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat() + "Z"

    conditions = ["(first_seen >= :cutoff OR last_seen IS NULL)"]
    params = {"cutoff": cutoff_iso}

    if namespace:
        conditions.append("namespace = :namespace")
        params["namespace"] = namespace

    if source:
        conditions.append("source = :source")
        params["source"] = source

    where_clause = " AND ".join(conditions)

    # This query uses a window function to get the highest severity alert for each namespace/pod combination
    # We map severity to a numeric value (high=1, medium=2, low=3) for ordering
    query = f"""
        WITH ranked_alerts AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY namespace, name
                    ORDER BY
                        CASE
                            WHEN severity = 'high' THEN 1
                            WHEN severity = 'medium' THEN 2
                            WHEN severity = 'low' THEN 3
                            ELSE 4
                        END
                ) as priority_rank
            FROM all_alerts
            WHERE {where_clause}
        )
        SELECT id, namespace, name, issue_type, severity, first_seen, last_seen, source, event_hash
        FROM ranked_alerts
        WHERE priority_rank = 1
        ORDER BY first_seen DESC
    """

    with engine.connect() as conn:
        result = conn.execute(text(query), params).mappings().all()
        return [dict(row) for row in result]


def cleanup_stale_ongoing_alerts(max_minutes=10):
    """
    Remove alerts that are still marked as ongoing (last_seen is NULL)
    but have not been updated for more than the specified number of minutes.

    Args:
        max_minutes: Maximum age in minutes to consider an ongoing alert as stale

    Returns:
        Dictionary with counts of records removed from each table
    """
    # Calculate the cutoff time
    cutoff_date = (datetime.now() -
                   timedelta(minutes=max_minutes)).isoformat() + "Z"

    removed_counts = {}

    with engine.begin() as conn:
        # Clean up Kubernetes alerts
        k8s_result = conn.execute(text("""
            DELETE FROM k8s_alerts
            WHERE first_seen < :cutoff_date AND last_seen IS NULL
        """), {"cutoff_date": cutoff_date})
        removed_counts["k8s_alerts"] = k8s_result.rowcount

        # Clean up Prometheus alerts
        prom_result = conn.execute(text("""
            DELETE FROM prometheus_alerts
            WHERE first_seen < :cutoff_date AND last_seen IS NULL
        """), {"cutoff_date": cutoff_date})
        removed_counts["prometheus_alerts"] = prom_result.rowcount

        # Clean up ArgoCD alerts
        argocd_result = conn.execute(text("""
            DELETE FROM argocd_alerts
            WHERE first_seen < :cutoff_date AND last_seen IS NULL
        """), {"cutoff_date": cutoff_date})
        removed_counts["argocd_alerts"] = argocd_result.rowcount

    return removed_counts
