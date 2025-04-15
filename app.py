from flask import Flask, render_template, request, redirect, url_for, jsonify
import datetime
import json
import random
import time
from datetime import datetime, timedelta

# Import necessary components - we'll try to use your existing functions
# If investigate.py doesn't exist yet, we'll mock these functions
try:
    from investigate import list_broken_pods, gather_metadata, llm_diagnose
except ImportError:
    # Mock functions if the real ones aren't available
    def list_broken_pods(namespace="default"):
        return ["pod-1", "pod-2", "pod-3"]
    
    def gather_metadata(namespace, pod_name):
        return {"containers": [], "events": [], "raw_describe": "Mock data"}
    
    def llm_diagnose(metadata):
        return "Mock diagnosis for demonstration purposes."

app = Flask(__name__)

# Mock data for timeline visualization
def generate_mock_timeline_data():
    """Generate mock timeline data for demonstration purposes"""
    event_types = [
        {"name": "HighLatencyForCustomerCheckout", "count": 12, "severity": "high"},
        {"name": "KubeDeploymentReplicasMismatch", "count": 3, "severity": "medium"},
        {"name": "KubePodCrashLooping", "count": 2, "severity": "high"},
        {"name": "TargetDown", "count": 1, "severity": "medium"},
        {"name": "MinishopHighLatency", "count": 1, "severity": "high"},
        {"name": "PodOOMKilled", "count": 5, "severity": "high"},
        {"name": "CrashLoopBackOff", "count": 3, "severity": "high"},
        {"name": "SchedulingWarning", "count": 2, "severity": "low"},
    ]
    
    # Generate time range for the past 6 hours
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=6)
    
    # Create timeline data with events positioned along the timeline
    timeline_data = []
    for event_type in event_types:
        events = []
        for i in range(event_type["count"]):
            # Random timestamp within the past 6 hours
            event_time = start_time + timedelta(minutes=random.randint(0, 360))
            # Convert to Unix timestamp in milliseconds for frontend
            timestamp = int(event_time.timestamp() * 1000)
            # Generate random duration between 30 seconds and 5 minutes
            duration = random.randint(30, 300)
            
            events.append({
                "id": f"{event_type['name']}-{i}",
                "timestamp": timestamp,
                "duration": duration,
                "severity": event_type["severity"],
                "pod_name": f"pod-{random.randint(1000, 9999)}",
                "message": f"Event {i+1} for {event_type['name']}"
            })
        
        timeline_data.append({
            "name": event_type["name"],
            "events": events,
            "count": event_type["count"],
            "severity": event_type["severity"]
        })
    
    return timeline_data

def generate_mock_event_details():
    """Generate mock event details for the table view"""
    clusters = ["nicolas-multi-node-cluster", "production-cluster", "staging-cluster"]
    priorities = ["HIGH", "MEDIUM", "LOW"]
    
    events = []
    for i in range(8):
        priority_level = i % 3  # 0=HIGH, 1=MEDIUM, 2=LOW
        events.append({
            "id": f"event-{i}",
            "priority": priorities[priority_level],
            "alert_type": f"AlertType-{i}",
            "cluster": random.choice(clusters),
            "event_count": random.randint(1, 12),
            "latest_time": (datetime.now() - timedelta(minutes=random.randint(5, 120))).strftime("%b %d, %y %H:%M"),
            "latest_message": f"This is a sample message for event {i}"
        })
    
    return events

def get_mock_analysis_data(alert_id):
    """Generate mock root cause analysis data"""
    root_causes = [
        "Database query performance issue detected. The latency is likely caused by inefficient queries.",
        "Container memory limit exceeded resulting in OOMKilled status.",
        "Image pull failure due to non-existent image tag or repository.",
        "Liveness probe failing, causing container restarts.",
        "Network connectivity issues between services."
    ]
    
    runbooks = [
        "Check database indexes and query optimization.",
        "Increase container memory limits or optimize application memory usage.",
        "Verify image name and tag, ensure repository access.",
        "Check liveness probe configuration and service health endpoints.",
        "Investigate network policies and service connectivity."
    ]
    
    sample_logs = [
        '{"timestamp":"2025-03-21T10:15:32Z","level":"ERROR","message":"Connection timeout to database"}',
        '{"timestamp":"2025-03-21T10:16:11Z","level":"WARN","message":"Memory usage above 85% threshold"}',
        '{"timestamp":"2025-03-21T10:17:45Z","level":"ERROR","message":"Image pull failed: ImagePullBackOff"}'
    ]
    
    return {
        "alert_id": alert_id,
        "root_cause": random.choice(root_causes),
        "runbook": random.choice(runbooks),
        "logs": sample_logs,
        "metrics": {
            "cpu": random.randint(60, 95),
            "memory": random.randint(70, 99),
            "latency": random.randint(200, 2000)
        }
    }

@app.route("/")
def index():
    """Main dashboard page with timeline view"""
    return render_template("index.html")

@app.route("/api/timeline")
def timeline_data():
    """API endpoint for timeline data"""
    return jsonify(generate_mock_timeline_data())

@app.route("/api/events")
def events_data():
    """API endpoint for events table data"""
    return jsonify(generate_mock_event_details())

@app.route("/api/analysis/<alert_id>")
def analysis_data(alert_id):
    """API endpoint for root cause analysis data"""
    return jsonify(get_mock_analysis_data(alert_id))

@app.route("/analyze/<namespace>")
def analyze_namespace(namespace):
    """Show detailed analysis for a namespace"""
    broken_pods = list_broken_pods(namespace=namespace)
    
    # For each broken pod, gather metadata and analyze
    results = []
    for pod in broken_pods:
        try:
            metadata = gather_metadata(namespace, pod)
            diagnosis = llm_diagnose(metadata)
            results.append({
                "pod_name": pod,
                "metadata": metadata,
                "diagnosis": diagnosis
            })
        except Exception as e:
            results.append({
                "pod_name": pod,
                "error": str(e)
            })
    
    return render_template(
        "analyze.html", 
        namespace=namespace, 
        broken_pods=broken_pods,
        results=results
    )

@app.route("/api/broken_pods/<namespace>")
def get_broken_pods(namespace):
    """API endpoint to get broken pods in a namespace"""
    broken_pods = list_broken_pods(namespace=namespace)
    return jsonify({"namespace": namespace, "broken_pods": broken_pods})

@app.route("/api/diagnose", methods=["POST"])
def diagnose_pod():
    """API endpoint to diagnose a pod"""
    data = request.json
    namespace = data.get("namespace")
    pod_name = data.get("pod_name")
    
    if not namespace or not pod_name:
        return jsonify({"error": "namespace and pod_name are required"}), 400
    
    try:
        metadata = gather_metadata(namespace, pod_name)
        diagnosis = llm_diagnose(metadata)
        return jsonify({
            "pod_name": pod_name,
            "diagnosis": diagnosis
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
