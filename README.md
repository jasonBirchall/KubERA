# KubERA

## Data Structure

### Database Overview
KubERA uses **SQLite** as its local database (`kubera.db`) with SQLAlchemy ORM for operations.

### Main Tables

#### k8s_alerts - Kubernetes Alert Data
```sql
CREATE TABLE k8s_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace   TEXT NOT NULL,
    pod_name    TEXT NOT NULL,
    issue_type  TEXT NOT NULL,           -- e.g., "CrashLoopBackOff", "ImagePullError"
    severity    TEXT NOT NULL,           -- "high", "medium", "low"
    first_seen  TEXT NOT NULL,           -- ISO timestamp string
    last_seen   TEXT,                    -- NULL means ongoing
    event_hash  TEXT UNIQUE,             -- MD5 hash for deduplication
    UNIQUE (namespace, pod_name, issue_type, first_seen)
);
```

#### prometheus_alerts - Prometheus Monitoring Data
```sql
CREATE TABLE prometheus_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace   TEXT NOT NULL,
    pod_name    TEXT NOT NULL,
    alert_name  TEXT NOT NULL,           -- e.g., "PodRestarting", "HighCPUUsage"
    severity    TEXT NOT NULL,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT,
    event_hash  TEXT UNIQUE,
    metric_value REAL,                   -- Associated metric value
    UNIQUE (namespace, pod_name, alert_name, first_seen)
);
```

#### argocd_alerts - ArgoCD Application Deployment Data
```sql
CREATE TABLE argocd_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_name TEXT NOT NULL,      -- ArgoCD application name
    issue_type      TEXT NOT NULL,       -- e.g., "ArgoCDDegradedAlert"
    severity        TEXT NOT NULL,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT,
    event_hash      TEXT UNIQUE,
    sync_status     TEXT,                -- ArgoCD sync status
    health_status   TEXT,                -- ArgoCD health status
    UNIQUE (application_name, issue_type, first_seen)
);
```

#### all_alerts - Unified View
A view that combines all alert sources:
```sql
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
```

### Key Features

- **Event Hash System**: Unique MD5 hash based on `namespace:name:issue_type:source` prevents duplicates
- **Time-based Tracking**: 
  - `first_seen`: When the issue first occurred
  - `last_seen`: When resolved (NULL = still ongoing)
- **Source Segregation**: Data separated by source (kubernetes, prometheus, argocd)
- **Severity Classification**: Three-tier system (high/medium/low)

### Alert Types

#### Kubernetes Issues
- `CrashLoopBackOff` (high severity)
- `ImagePullError` (medium severity)
- `PodOOMKilled` (high severity)
- `FailedScheduling` (medium severity)
- `FailingLiveness` (low severity)

#### Prometheus Alerts
- `PodRestarting` (medium severity)
- `PodNotReady` (medium severity)
- `HighCPUUsage` (medium severity)
- `KubeDeploymentReplicasMismatch` (medium severity)
- `TargetDown` (medium severity)

#### ArgoCD Issues
- `ArgoCDDegradedAlert` (high severity)
- Sync status issues
- Health status problems

### Database Operations

Key functions in `db.py`:
- `record_k8s_failure()` - Insert Kubernetes alerts
- `record_prometheus_alert()` - Insert Prometheus alerts
- `record_argocd_alert()` - Insert ArgoCD alerts
- `get_all_alerts()` - Retrieve unified alert data
- `get_active_alerts()` - Get only ongoing alerts
- `cleanup_old_alerts()` - Remove old alerts
- `cleanup_stale_ongoing_alerts()` - Remove stale ongoing alerts