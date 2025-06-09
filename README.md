# KubERA

**Kubernetes Error Root-cause Analysis** - AI-powered Kubernetes troubleshooting and monitoring.

## 🚀 Quick Start for New Users

Want to try KubERA immediately? Choose your setup method:

### Option 1: Interactive Setup (Recommended for beginners)
```bash
./setup-playground.sh
```

### Option 2: Direct Setup
```bash
# Set your OpenAI API key
export OPENAI_API_KEY="your-api-key-here"

# Set up complete testing environment (installs dependencies automatically)
make playground

# Start KubERA
make run
```

**👉 [See the complete playground guide →](./PLAYGROUND.md)**

The playground command will automatically:
- ✅ Check and install required tools (kind, kubectl, Docker, etc.)
- 🔧 Create a local Kubernetes cluster
- 📊 Install Prometheus and ArgoCD
- 🚀 Deploy sample workloads for testing
- 🗄️ Set up the KubERA database

Access the dashboard at **http://localhost:8501** after setup completes.

---

## 📖 Quick Start Guide

### Prerequisites
- **macOS or Linux** (Windows with WSL2)
- **OpenAI API Key** - Get one from [OpenAI Platform](https://platform.openai.com/api-keys)
- **5-10 minutes** for initial setup

### Step 1: Get KubERA
```bash
git clone <repository-url>
cd KubERA
```

### Step 2: Set Your API Key
```bash
# Set for current session
export OPENAI_API_KEY="your-api-key-here"

# Or add to your shell profile for persistence
echo 'export OPENAI_API_KEY="your-api-key-here"' >> ~/.zshrc
source ~/.zshrc
```

### Step 3: Choose Your Setup Method

#### For Beginners (Interactive)
```bash
./setup-playground.sh
```
- 🤝 Guided setup with prompts
- 🔍 Automatic dependency detection
- 💡 Helpful tips and troubleshooting

#### For Experienced Users (Direct)
```bash
make playground
```
- 🚀 Automated one-command setup
- ⚡ Fastest path to running environment

### Step 4: Start KubERA
```bash
make run
```

### Step 5: Explore the Interface

1. **Open the Dashboard**: http://localhost:5000
2. **View the Timeline**: See events from all sources
3. **Click on Broken Pods**: Get AI-powered analysis
4. **Explore Filters**: Filter by namespace, severity, source
5. **Check the Terminal**: See real-time AI diagnosis

### Quick Test Scenarios

#### Test Pod Analysis
```bash
# Create a test pod with image issue
kubectl run test-workload --image=internal-registry.local/app:latest

# Watch it appear in KubERA dashboard  
# Click on it to see AI analysis
```

#### Test Multiple Sources
```bash
# View Kubernetes events
# Check Prometheus metrics at http://localhost:9090
# Explore ArgoCD at http://localhost:8080
```

### Common Commands
```bash
# Check what's running
kubectl get pods -A

# Reset database for fresh start
make reset-db

# Clean up everything
make destroy-all

# See all available commands
make help
```

### Troubleshooting Quick Fixes
```bash
# Docker not running?
open /Applications/Docker.app

# Port already in use?
make destroy-all && make playground

# Need to reset everything?
make destroy-all
make playground
make run
```

---

## 🔒 Data Privacy & Anonymization

KubERA includes built-in **data anonymization** to protect sensitive information when sending data to OpenAI's API for analysis.

### What Gets Anonymized

KubERA automatically anonymizes the following sensitive data before sending to OpenAI:

| Data Type | Example Original | Example Anonymized |
|-----------|------------------|-------------------|
| **Pod Names** | `my-app-12345-abcde` | `pod-001-xyz12` |
| **Namespaces** | `production` | `namespace-01` |
| **Container Names** | `web-server` | `container-01` |
| **Docker Images** | `myregistry.com/app:v1.2.3` | `registry.example.com/app-01:v1.0.0` |
| **IP Addresses** | `203.0.113.5` | `10.0.1.5` |
| **URLs/Domains** | `api.company.com` | `app-01.example.com` |
| **Secrets/Tokens** | `eyJhbGciOiJIUzI1...` | `***REDACTED-SECRET-01***` |
| **File Paths** | `/opt/myapp/config` | `/app/data/file-01` |

### How It Works

1. **Before AI Analysis**: Sensitive data is replaced with consistent anonymous tokens
2. **AI Processing**: OpenAI receives only anonymized data
3. **After Analysis**: Original values are restored in the response
4. **User Notification**: Terminal shows what was anonymized for transparency

### Privacy Features

- ✅ **Consistent Mapping**: Same values get same anonymous tokens
- ✅ **Reversible**: Original values restored in responses
- ✅ **Transparent**: Users see what was anonymized
- ✅ **Configurable**: Can be enabled/disabled per session
- ✅ **No Storage**: Mappings aren't persisted to disk

### Example Privacy Notice

When anonymization occurs, you'll see notices like:
```
🔒 PRIVACY & ANONYMIZATION
─────────────────────────────
The following data was anonymized before sending to AI:
• 2 pod name(s)
• 1 namespace(s)
• 3 container name(s)
• 1 Docker image(s)

Original values have been restored in this response.
```

### API Endpoints

```bash
# Preview what would be anonymized
curl -X POST http://localhost:8501/api/anonymization/preview \
  -H "Content-Type: application/json" \
  -d '{"pod_name": "my-app-123", "namespace": "production"}'

# Toggle anonymization on/off
curl -X POST http://localhost:8501/api/anonymization/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

### Configuration

Anonymization is **enabled by default** but can be controlled:

```python
# In your code
llm_agent = LlmAgent(enable_anonymization=True)  # Default

# Disable for testing
llm_agent.set_anonymization(False)

# Preview anonymization
preview = llm_agent.preview_anonymization(metadata)
```

This ensures your sensitive Kubernetes data stays private while still getting powerful AI-driven insights.

---

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
