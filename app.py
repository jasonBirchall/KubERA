import logging
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
import openai
import json

from flask import Flask, jsonify, render_template, request, send_from_directory
from sqlalchemy import text

from agent.llm_agent import LlmAgent
from agent.tools.argocd_tool import ArgoCDTool
from agent.tools.k8s_tool import K8sTool
from agent.tools.prometheus_tool import PrometheusTool
from db import (cleanup_old_alerts, cleanup_stale_ongoing_alerts, engine,
                get_active_alerts, get_active_alerts_deduplicated,
                get_all_alerts, get_all_alerts_deduplicated, init_db,
                migrate_db, record_argocd_alert, record_k8s_failure,
                record_prometheus_alert)

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

k8s_tool = K8sTool()
prometheus_tool = PrometheusTool()  # Using default localhost:9090
argocd_tool = ArgoCDTool(base_url="http://localhost:8501")
llm_agent = LlmAgent(enable_react=True)  # Enable ReAct by default

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

migrate_db()
init_db()


def collect_and_store_data():
    """
    Collect data from K8s, Prometheus, and ArgoCD and store it in the database.
    This runs in a background thread to ensure the database is populated.
    """
    logger.info("Collecting data from K8s, Prometheus, and ArgoCD...")
    try:
        # Set time horizon for data collection (last 6 hours)
        hours = 6
        # Make horizon timezone-aware with UTC timezone
        horizon = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Helper function to validate datetime
        def validate_datetime(dt):
            if not dt:
                return None
            if not isinstance(dt, datetime):
                logger.error(f"Invalid datetime value: {dt}")
                return None
            # Ensure UTC timezone
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        # Collect Kubernetes data
        k8s_count = 0
        namespaces = k8s_tool.get_namespaces()
        logger.debug(f"Found {len(namespaces)} namespaces: {namespaces}")

        for ns in namespaces:
            broken_pods = k8s_tool.list_broken_pods(ns)
            logger.debug(
                f"Found {len(broken_pods)} broken pods in namespace {ns}: {broken_pods}")

            for pod in broken_pods:
                # Get the failure window for this pod
                first_seen, last_seen = k8s_tool.failure_window(
                    ns, pod, horizon)

                # Validate first_seen
                first_seen = validate_datetime(first_seen)
                if not first_seen:
                    logger.warning(
                        f"Skipping K8s pod {ns}/{pod} due to missing first_seen timestamp")
                    continue

                # Validate last_seen (can be None)
                last_seen = validate_datetime(last_seen)

                issue = k8s_tool.determine_issue_type(
                    k8s_tool.gather_metadata(ns, pod))
                severity = k8s_tool.determine_severity(issue)

                logger.debug(
                    f"Recording K8s failure: {ns}/{pod}, issue={issue}, severity={severity}, first_seen={first_seen}, last_seen={last_seen}")
                # Record in the database
                record_k8s_failure(ns, pod, issue, severity,
                                   first_seen, last_seen)
                k8s_count += 1

        logger.info(f"Recorded {k8s_count} Kubernetes alerts in the database")

        # Collect ArgoCD data
        argocd_count = 0
        argocd_alerts = argocd_tool.get_application_alerts(hours)
        logger.debug(
            f"Found {len(argocd_alerts)} ArgoCD alerts: {argocd_alerts}")

        for alert in argocd_alerts:
            issue_type = alert.get("name")
            severity = alert.get("severity", "medium")

            for app in alert.get("pods", []):
                app_name = app.get("name")
                if not app_name:
                    logger.warning(
                        "Skipping ArgoCD alert due to missing app name")
                    continue

                try:
                    start_time = datetime.fromisoformat(
                        app.get("start").replace("Z", "+00:00"))
                    start_time = validate_datetime(start_time)
                    if not start_time:
                        continue
                except (ValueError, AttributeError) as e:
                    logger.warning(
                        f"Skipping ArgoCD alert for {app_name} due to invalid start time: {e}")
                    continue

                end_iso = app.get("end")
                try:
                    end_time = None if end_iso is None else datetime.fromisoformat(
                        end_iso.replace("Z", "+00:00"))
                    end_time = validate_datetime(end_time)
                except ValueError as e:
                    logger.warning(
                        f"Invalid end time for {app_name}, setting to None: {e}")
                    end_time = None

                # Get sync and health status if available
                sync_status = app.get("sync_status")
                health_status = app.get("health_status")

                logger.debug(
                    f"Recording ArgoCD alert: app={app_name}, issue={issue_type}, severity={severity}, first_seen={start_time}, last_seen={end_time}")
                # Record in the database
                if issue_type and start_time:  # Ensure required fields are present
                    record_argocd_alert(app_name, issue_type, severity,
                                        start_time, end_time,
                                        sync_status, health_status)
                    argocd_count += 1

        logger.info(f"Recorded {argocd_count} ArgoCD alerts in the database")

        # Collect Prometheus data
        prom_count = 0
        prom_alerts = prometheus_tool.get_pod_alerts(hours)
        logger.debug(
            f"Found {len(prom_alerts)} Prometheus alerts: {prom_alerts}")

        for alert in prom_alerts:
            alert_name = alert["name"]
            severity = alert["severity"]

            for pod in alert.get("pods", []):
                pod_name = pod.get("name")
                pod_namespace = pod.get("namespace", "default")

                try:
                    start_time = datetime.fromisoformat(
                        pod.get("start").replace("Z", "+00:00"))
                    start_time = validate_datetime(start_time)
                    if not start_time:
                        continue
                except (ValueError, AttributeError) as e:
                    logger.warning(
                        f"Skipping Prometheus alert for {pod_name} due to invalid start time: {e}")
                    continue

                end_iso = pod.get("end")
                try:
                    end_time = None if end_iso is None else datetime.fromisoformat(
                        end_iso.replace("Z", "+00:00"))
                    end_time = validate_datetime(end_time)
                except ValueError as e:
                    logger.warning(
                        f"Invalid end time for {pod_name}, setting to None: {e}")
                    end_time = None

                # Get the metric value if available
                metric_value = pod.get("value")

                logger.debug(
                    f"Recording Prometheus alert: {pod_namespace}/{pod_name}, alert={alert_name}, severity={severity}, first_seen={start_time}, last_seen={end_time}")
                # Record in the database
                if pod_name and start_time:  # Validate required fields
                    record_prometheus_alert(pod_namespace, pod_name, alert_name, severity,
                                            start_time, end_time, metric_value)
                    prom_count += 1
                else:
                    logger.warning(
                        f"Skipping Prometheus alert due to missing required fields: pod_name={pod_name}, start_time={start_time}")

        logger.info(f"Recorded {prom_count} Prometheus alerts in the database")

        # Check total count in the database after collection
        with engine.connect() as conn:
            total_count = conn.execute(
                text("SELECT COUNT(*) FROM all_alerts")).fetchone()[0]
            logger.info(
                f"Total alerts in database after collection: {total_count}")

        logger.info("Finished collecting and storing data")
    except Exception as e:
        logger.error(f"Error collecting data: {str(e)}", exc_info=True)


def data_collection_thread_function():
    """Background thread that collects and stores data every minute."""
    while True:
        try:
            collect_and_store_data()
            # Sleep for 1 minute
            time.sleep(60)
        except Exception as e:
            logger.error(f"Error in data collection thread: {str(e)}")
            # Sleep for 30 seconds before trying again
            time.sleep(30)


def cleanup_duplicate_pod_events():
    """
    Identify duplicate pod events and remove the oldest ones.
    Only one event per pod name and source should be kept (the most recent one).
    """
    logger.info("Running duplicate pod event cleanup...")
    try:
        with engine.connect() as conn:
            # Clean up Kubernetes alerts
            k8s_query = """
            DELETE FROM k8s_alerts
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM k8s_alerts
                GROUP BY namespace, pod_name, issue_type
            )
            """
            k8s_result = conn.execute(text(k8s_query))

            # Clean up Prometheus alerts
            prom_query = """
            DELETE FROM prometheus_alerts
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM prometheus_alerts
                GROUP BY namespace, pod_name, alert_name
            )
            """
            prom_result = conn.execute(text(prom_query))

            # Clean up ArgoCD alerts
            argocd_query = """
            DELETE FROM argocd_alerts
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM argocd_alerts
                GROUP BY application_name, issue_type
            )
            """
            argocd_result = conn.execute(text(argocd_query))

            conn.commit()

            total_cleaned = k8s_result.rowcount + \
                prom_result.rowcount + argocd_result.rowcount
            logger.info(
                f"Cleaned up {total_cleaned} duplicate events (K8s: {k8s_result.rowcount}, Prometheus: {prom_result.rowcount}, ArgoCD: {argocd_result.rowcount})")
    except Exception as e:
        logger.error(f"Error cleaning up duplicate pod events: {str(e)}")


def cleanup_thread_function():
    """Background thread that runs the cleanup function every two minutes."""
    while True:
        try:
            cleanup_duplicate_pod_events()
            # Sleep for 2 minutes
            time.sleep(120)
        except Exception as e:
            logger.error(f"Error in cleanup thread: {str(e)}")
            # Sleep for a minute before trying again
            time.sleep(60)


# Start the data collection thread when the app starts
data_collection_thread = threading.Thread(
    target=data_collection_thread_function, daemon=True)
data_collection_thread.start()

# Start the cleanup thread when the app starts
cleanup_thread = threading.Thread(target=cleanup_thread_function, daemon=True)
cleanup_thread.start()

# Run initial data collection to populate the database
collect_and_store_data()


def determine_issue_type(pod_metadata):
    """
    Analyze pod metadata to determine the type of issue
    Returns a string like "CrashLoopBackOff", "PodOOMKilled", etc.
    """
    events = pod_metadata.get("events", [])

    # Look for common patterns in the events
    for event in events:
        event_lower = event.lower()
        if "oomkilled" in event_lower:
            return "PodOOMKilled"
        elif "crashloopbackoff" in event_lower:
            return "CrashLoopBackOff"
        elif "pulled" in event_lower and "image" in event_lower:
            return "ImagePullError"
        elif "schedulingfailed" in event_lower or "failedscheduling" in event_lower:
            return "FailedScheduling"

    # Check containers for image validity
    # containers = pod_metadata.get("containers", [])
    # for container in containers:
    #     if container.get("image_valid") is False:
    #         return "ImagePullError"

    # Default to a generic issue type
    return "PodFailure"


def determine_severity(issue_type):
    """Maps issue types to severity levels (high, medium, low)"""
    high_severity = ["PodOOMKilled", "CrashLoopBackOff",
                     "HighLatencyForCustomerCheckout", "MemoryPressure"]
    medium_severity = ["ImagePullError", "KubeDeploymentReplicasMismatch", "TargetDown", "KubePodCrashLooping",
                       "HighCPUUsage", "PodRestarting", "PodNotReady"]

    if issue_type in high_severity:
        return "high"
    elif issue_type in medium_severity:
        return "medium"
    else:
        return "low"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/namespaces')
def get_namespaces():
    """
    Returns a list of all namespaces in the current Kubernetes context
    """
    cmd = "kubectl get namespaces -o=jsonpath='{.items[*].metadata.name}'"
    output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)

    namespaces = output.decode().split()
    logger.debug(f"Namespaces identified for filter = {namespaces}")

    return jsonify(namespaces)


@app.route('/api/kube-contexts')
def get_kube_contexts():
    """
    Returns a list of available Kubernetes contexts from kubectl config
    """
    try:
        # Get current context
        current_context_cmd = "kubectl config current-context"
        current_context = subprocess.check_output(
            current_context_cmd, shell=True).decode().strip()

        # Get all contexts
        contexts_cmd = "kubectl config get-contexts -o name"
        contexts_output = subprocess.check_output(
            contexts_cmd, shell=True).decode().strip()

        # Parse the output
        context_list = []
        if contexts_output:
            all_contexts = contexts_output.split('\n')
            for context in all_contexts:
                context_name = context.strip()
                context_list.append({
                    "name": context_name,
                    "current": context_name == current_context
                })

        return jsonify(context_list)

    except subprocess.CalledProcessError as e:
        logger.error(f"Error fetching Kubernetes contexts: {str(e)}")
        # Return sample contexts as fallback
        fallback_contexts = [
            {"name": "kubera-local", "current": True},
            {"name": "prod-cluster", "current": False},
            {"name": "staging-cluster", "current": False},
            {"name": "minikube", "current": False}
        ]
        return jsonify(fallback_contexts)

# Add this route if you want to support switching contexts


@app.route('/api/kube-contexts/<context_name>', methods=['POST'])
def switch_kube_context(context_name):
    """
    Switches the current Kubernetes context
    """
    try:
        # Switch context
        switch_cmd = f"kubectl config use-context {context_name}"
        subprocess.check_output(switch_cmd, shell=True)

        return jsonify({
            "success": True,
            "message": f"Switched to context {context_name}"
        })

    except subprocess.CalledProcessError as e:
        logger.error(f"Error switching Kubernetes context: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Failed to switch context: {str(e)}"
        }), 500


@app.route('/api/timeline_data')
def get_timeline_data():
    hours = request.args.get('hours', 6, type=int)
    namespace = request.args.get('namespace', None)
    # 'kubernetes', 'prometheus', or 'all'
    data_source = request.args.get('source', 'all')
    # Check if we should deduplicate by namespace/pod
    deduplicate = request.args.get('deduplicate', 'false').lower() == 'true'
    # Allow overriding the reference date (for testing/debugging)
    reference_date_str = request.args.get('reference_date', None)

    logger.debug(
        f"timeline_data called with hours={hours}, namespace={namespace}, source={data_source}")

    # Use the reference date if provided, otherwise use system date
    if reference_date_str:
        try:
            # Try to parse the provided date (supports various formats)
            current_date = datetime.fromisoformat(
                reference_date_str.replace('Z', '+00:00'))
            logger.debug(f"Using provided reference date: {current_date}")
        except ValueError:
            # If invalid format, fall back to system date
            current_date = datetime.now()
            logger.warning(
                f"Invalid reference_date format: {reference_date_str}, using system date")
    else:
        current_date = datetime.now()

    cutoff = current_date - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat() + "Z"

    with engine.connect() as conn:
        conditions = []
        params = {}

        # Apply time filtering using the reference date
        conditions.append("(first_seen >= :cutoff AND last_seen IS NULL)")
        params["cutoff"] = cutoff_iso

        if namespace:
            conditions.append("namespace = :namespace")
            params["namespace"] = namespace

        if data_source and data_source != 'all':
            conditions.append("source = :source")
            params["source"] = data_source

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT * FROM all_alerts
            WHERE {where_clause}
            ORDER BY first_seen DESC
        """
        rows = [dict(row) for row in conn.execute(
            text(query), params).mappings().all()]

    logger.debug(f"get_active_alerts returned {len(rows)} rows")

    # Build the response using the results from active alerts
    issue_groups = {}
    for r in rows:
        # Create a unique key using issue_type and source
        group_key = f"{r['issue_type']}_{r['source']}"

        grp = issue_groups.setdefault(group_key, {
            "name": r["issue_type"],
            "severity": r["severity"],
            "pods": [],
            "count": 0,
            "source": r["source"]
        })
        grp["pods"].append({
            "name": r["name"],
            "namespace": r["namespace"],
            "start": r["first_seen"],
            "end": r["last_seen"],
            "source": r["source"]
        })
        grp["count"] += 1

    result = list(issue_groups.values())
    logger.debug(f"Returning {len(result)} timeline groups: {result}")
    return jsonify(result)


@app.route('/api/timeline_history')
def timeline_history():
    hours = request.args.get('hours', 24, type=int)
    # 'kubernetes', 'prometheus', or 'all'
    source = request.args.get('source', 'all')
    namespace = request.args.get('namespace', None)
    # Check if we should deduplicate by namespace/pod
    deduplicate = request.args.get('deduplicate', 'false').lower() == 'true'
    # Check if we should show only active alerts or include resolved ones
    show_resolved = request.args.get(
        'show_resolved', 'false').lower() == 'true'
    # Allow overriding the reference date (for testing/debugging)
    reference_date_str = request.args.get('reference_date', None)

    # Use the reference date if provided, otherwise use system date
    if reference_date_str:
        try:
            # Try to parse the provided date (supports various formats)
            current_date = datetime.fromisoformat(
                reference_date_str.replace('Z', '+00:00'))
            logger.debug(f"Using provided reference date: {current_date}")
        except ValueError:
            # If invalid format, fall back to system date
            current_date = datetime.now()
            logger.warning(
                f"Invalid reference_date format: {reference_date_str}, using system date")
    else:
        current_date = datetime.now()

    cutoff = current_date - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat() + "Z"

    with engine.connect() as conn:
        conditions = []
        params = {}

        # Apply time filtering using the reference date
        if show_resolved:
            conditions.append("(first_seen >= :cutoff OR last_seen IS NULL)")
        else:
            conditions.append("first_seen >= :cutoff AND last_seen IS NULL")
        params["cutoff"] = cutoff_iso

        if namespace:
            conditions.append("namespace = :namespace")
            params["namespace"] = namespace

        if source and source != 'all':
            conditions.append("source = :source")
            params["source"] = source

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT * FROM all_alerts
            WHERE {where_clause}
            ORDER BY first_seen DESC
        """
        rows = [dict(row) for row in conn.execute(
            text(query), params).mappings().all()]

    # Build the response using the results
    issue_groups = {}
    for r in rows:
        # Create a unique key using issue_type and source
        group_key = f"{r['issue_type']}_{r['source']}"

        grp = issue_groups.setdefault(group_key, {
            "name": r["issue_type"],
            "severity": r["severity"],
            "pods": [],
            "count": 0,
            "source": r["source"]
        })
        grp["pods"].append({
            "name": r["name"],
            "namespace": r["namespace"],
            "start": r["first_seen"],
            "end": r["last_seen"],
            "source": r["source"]
        })
        grp["count"] += 1

    return jsonify(list(issue_groups.values()))


@app.route('/api/prometheus_data')
def get_prometheus_data():
    """
    Returns data from Prometheus.
    This can be used to get specific metrics
    """
    hours = request.args.get('hours', 6, type=int)
    namespace = request.args.get('namespace', None)

    # Get real data from Prometheus
    data = prometheus_tool.get_pod_alerts(hours, namespace)

    return jsonify(data)


@app.route('/api/cluster_issues')
def get_cluster_issues():
    # Get namespace from query params, or check all namespaces if not specified
    namespace = request.args.get('namespace', None)
    # 'kubernetes', 'prometheus', 'argocd', or 'all'
    data_source = request.args.get('source', 'all')
    issue_groups = {}

    # Get Kubernetes data if requested
    if data_source in ['all', 'kubernetes']:
        # Get list of all namespaces if none specified
        namespaces_to_check = [
            namespace] if namespace else k8s_tool.get_namespaces()

        for ns in namespaces_to_check:
            broken_pods = k8s_tool.list_broken_pods(namespace=ns)
            logger.debug(f"Broken pods in namespace {ns} = {broken_pods}")

            for pod_name in broken_pods:
                metadata = k8s_tool.gather_metadata(ns, pod_name)
                issue_type = k8s_tool.determine_issue_type(metadata)
                severity = k8s_tool.determine_severity(issue_type)

                if issue_type not in issue_groups:
                    issue_groups[issue_type] = {
                        "name": issue_type,
                        "severity": severity,
                        "pods": [],
                        "count": 0,
                        "source": "kubernetes"
                    }

                issue_groups[issue_type]["pods"].append({
                    "name": pod_name,
                    "namespace": ns,
                    "timestamp": datetime.now().isoformat(),
                    "source": "kubernetes"
                })
                issue_groups[issue_type]["count"] += 1

    # Get Prometheus data if requested
    if data_source in ['all', 'prometheus']:
        # Get alerts from Prometheus for specific namespace or all namespaces
        prom_alerts = prometheus_tool.get_pod_alerts(
            hours=1, namespace=namespace)
        # Process Prometheus alerts
        for alert in prom_alerts:
            alert_name = alert["name"]
            severity = alert["severity"]

            if f"{alert_name}_prom" not in issue_groups:
                issue_groups[f"{alert_name}_prom"] = {
                    "name": alert_name,
                    "severity": severity,
                    "pods": [],
                    "count": 0,
                    "source": "prometheus"
                }

            for pod in alert.get("pods", []):
                issue_groups[f"{alert_name}_prom"]["pods"].append({
                    "name": pod.get("name"),
                    "namespace": pod.get("namespace", namespace or "default"),
                    "timestamp": datetime.now().isoformat(),
                    "source": "prometheus"
                })
                issue_groups[f"{alert_name}_prom"]["count"] += 1

    # Get ArgoCD data if requested
    if data_source in ['all', 'argocd']:
        argocd_alerts = argocd_tool.get_application_alerts(hours=1)
        logger.debug(f"ArgoCD alerts = {argocd_alerts}")

        # Process ArgoCD alerts
        for alert in argocd_alerts:
            alert_name = alert.get("name")
            severity = alert.get("severity", "medium")

            if f"{alert_name}_argocd" not in issue_groups:
                issue_groups[f"{alert_name}_argocd"] = {
                    "name": alert_name,
                    "severity": severity,
                    "pods": [],
                    "count": 0,
                    "source": "argocd"
                }

            for app in alert.get("pods", []):
                issue_groups[f"{alert_name}_argocd"]["pods"].append({
                    "name": app.get("name"),
                    "namespace": None,  # ArgoCD doesn't use namespace
                    "timestamp": datetime.now().isoformat(),
                    "source": "argocd"
                })
                issue_groups[f"{alert_name}_argocd"]["count"] += 1

    return jsonify(list(issue_groups.values()))


@app.route('/api/analyze/argocd/<app_name>')
def analyze_argocd_app(app_name):
    """
    Returns a structured JSON describing the analysis for an ArgoCD application.
    """
    try:
        # Get application status
        status = argocd_tool.get_application_status(app_name)

        # Get recent events
        events = argocd_tool.get_application_events(app_name, hours=6)

        # Call LLM for a diagnosis
        metadata = {
            "app_name": app_name,
            "status": status,
            "events": events
        }
        llm_response = llm_agent.diagnose_argocd_app(metadata)

        # For demonstration, we'll do a quick naive parse
        # of the LLM's text to separate root causes & recommended actions.
        root_cause = []
        runbook = []

        if "Root Cause:" in llm_response and "Recommended Actions:" in llm_response:
            # naive splitting
            root_cause_text = llm_response.split(
                "Root Cause:")[1].split("Recommended Actions:")[0]
            runbook_text = llm_response.split("Recommended Actions:")[1]

            root_cause = [line.strip()
                          for line in root_cause_text.strip().split("\n") if line.strip()]
            runbook = [line.strip()
                       for line in runbook_text.strip().split("\n") if line.strip()]
        else:
            # fallback if we can't parse properly
            root_cause = [llm_response]
            runbook = ["No structured runbook found."]

        # Build the analysis result
        analysis_result = {
            "app_name": app_name,
            "health_status": status.get("health", {}).get("status", "Unknown"),
            "sync_status": status.get("sync", {}).get("status", "Unknown"),
            "root_cause": root_cause,
            "recommended_actions": runbook,
            "app_events": [event.get("message", "") for event in events],
            "operation_state": status.get("operationState", {}),
            "raw_llm_output": llm_response
        }

        return jsonify({"analysis": analysis_result})
    except Exception as e:
        logger.error(
            f"Error analyzing ArgoCD application '{app_name}': {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/analyze/<issue_type>')
def analyze_issue(issue_type):
    """
    Returns a structured JSON describing the analysis for *all* pods
    in the cluster that exhibit this `issue_type`.
    """
    try:
        namespace = request.args.get('namespace', 'default')
        # The data source to analyze
        source = request.args.get('source', 'kubernetes')
        include_metadata = request.args.get(
            'include_metadata', 'false').lower() == 'true'
        include_description = request.args.get(
            'include_description', 'false').lower() == 'true'

        # For Prometheus sources, remove the "_prom" suffix if present
        compare_issue = issue_type
        if source == 'prometheus' and issue_type.endswith("_prom"):
            compare_issue = issue_type[:-5]  # Remove "_prom" suffix

        analysis_results = []
        events_metadata = []

        # Get events metadata from the database instead of querying the cluster directly
        if include_metadata:
            logger.info(
                f"Fetching metadata from database for issue type: {compare_issue}, source: {source}")

            # Query the SQLite database using the all_alerts view
            with engine.connect() as conn:
                # Build query based on source and issue type
                query = """
                    SELECT namespace, name as pod_name, issue_type, severity,
                           first_seen, last_seen, source
                    FROM all_alerts
                    WHERE issue_type = :issue_type
                """

                # Add source filter if not 'all'
                if source != 'all':
                    query += " AND source = :source"

                # Add namespace filter if not 'all'
                if namespace != 'all':
                    query += " AND namespace = :namespace"

                # Order by most recent first
                query += " ORDER BY first_seen DESC"

                # Execute the query
                params = {
                    "issue_type": compare_issue,
                    "source": source,
                    "namespace": namespace
                }

                rows = conn.execute(text(query), params).mappings().all()

                # Process the results
                for row in rows:
                    events_metadata.append({
                        "pod_name": row["pod_name"],
                        "namespace": row["namespace"],
                        "source": row["source"],
                        "timestamp": row["first_seen"],
                        "last_seen": row["last_seen"],
                        "severity": row["severity"]
                    })

            logger.info(f"Found {len(events_metadata)} events in database")

        # For the analysis part, we still query K8s directly if needed
        # (though we're not showing this in the UI anymore)
        broken_pods = []
        if source == 'kubernetes':
            broken_pods = k8s_tool.list_broken_pods(namespace=namespace)

        for pod_name in broken_pods:
            # 1) Gather metadata
            if source == 'kubernetes':
                metadata = k8s_tool.gather_metadata(namespace, pod_name)
                found_issue = determine_issue_type(metadata)
            else:
                # For Prometheus, we'd have different metadata
                metadata = {"source": "prometheus",
                            "pod_name": pod_name, "issue": issue_type}
                found_issue = issue_type

            # 2) Determine if it actually matches the requested issue_type
            if found_issue != compare_issue:
                continue  # Skip pods that are failing for different reasons

            # Collect event metadata for the table display - REMOVED SINCE WE NOW GET FROM DB

            # 3) Fetch logs for context (only for Kubernetes source)
            if source == 'kubernetes':
                logs = k8s_tool.fetch_logs(namespace, pod_name, lines=100)
                # store logs inside metadata before LLM call
                metadata["logs"] = logs
            else:
                # For Prometheus alerts, we might not have direct logs, but we can provide metrics context
                logs = "Prometheus metrics indicate issues for this pod."

            # 4) Call LLM for a diagnosis
            llm_response = llm_agent.diagnose_pod(metadata)

            # For demonstration, we'll do a quick naive parse
            # of the LLM's text to separate root causes & recommended actions.
            root_cause = []
            runbook = []

            if "Root Cause:" in llm_response and "Recommended Actions:" in llm_response:
                # naive splitting
                root_cause_text = llm_response.split(
                    "Root Cause:")[1].split("Recommended Actions:")[0]
                runbook_text = llm_response.split("Recommended Actions:")[1]

                root_cause = [line.strip()
                              for line in root_cause_text.strip().split("\n") if line.strip()]
                runbook = [line.strip()
                           for line in runbook_text.strip().split("\n") if line.strip()]
            else:
                # fallback if we can't parse properly
                root_cause = [llm_response]
                runbook = ["No structured runbook found."]

            # 5) Build a single record for this pod
            analysis_results.append({
                "pod_name": pod_name,
                "issue_type": found_issue,  # same as request, but good to confirm
                "root_cause": root_cause,
                "recommended_actions": runbook,
                "pod_events": metadata.get("events", []),
                # last 10 lines
                "logs_excerpt": logs.splitlines()[-10:] if isinstance(logs, str) else [],
                "source": source,
                "raw_llm_output": llm_response  # optional, might be large
            })

        # Try to get a description if requested
        description = None
        if include_description:
            # Fallback descriptions (using the same dictionary from generate_alert_description)
            fallback_descriptions = {
                "CrashLoopBackOff": "Indicates a pod repeatedly crashes after starting. This could be due to application errors, configuration issues, or resource constraints that prevent the container from running properly.",
                "PodOOMKilled": "Signals that a pod was terminated due to Out Of Memory. The container exceeded its memory limit or the node ran out of memory, causing the kernel to kill the process.",
                "ImagePullError": "Occurs when Kubernetes cannot pull the specified container image. This could be due to invalid image names, missing credentials for private repositories, or network issues.",
                "FailedScheduling": "Indicates that the Kubernetes scheduler cannot find a suitable node to place a pod. This may be due to insufficient resources, node taints, or pod constraints.",
                "PodFailure": "A generic alert indicating a pod has failed. This could be for various reasons including application crashes, configuration errors, or infrastructure issues.",
                "KubePodCrashLooping": "Similar to CrashLoopBackOff, indicates that pods are repeatedly crashing shortly after starting, suggesting application or configuration problems.",
                "TargetDown": "Prometheus alert indicating a monitored target is unreachable. This could mean the service is down or there are network connectivity issues.",
                "HighCPUUsage": "Prometheus alert for excessive CPU consumption, which may indicate application inefficiency, unexpected load, or insufficient resources.",
                "KubeDeploymentReplicasMismatch": "Indicates a discrepancy between desired and current replica counts in a deployment, suggesting scaling or scheduling issues."
            }

            # Check if we have a fallback for this issue type
            compare_issue = issue_type
            if source == 'prometheus' and issue_type.endswith("_prom"):
                compare_issue = issue_type[:-5]  # Remove "_prom" suffix

            if compare_issue in fallback_descriptions:
                logger.info(
                    f"Using fallback description for issue type: {compare_issue}")
                description = fallback_descriptions[compare_issue]
            else:
                try:
                    # Format the prompt for the LLM agent
                    prompt = f"""
                    Generate a short, concise explanation (40-60 words) of what the following Kubernetes/cloud alert means:

                    Alert: {issue_type}
                    Source: {source}

                    Explain in plain language what this alert typically indicates, potential impacts, and the general category of issue.
                    Keep it technical but accessible to DevOps engineers.
                    """

                    # Get the description from the LLM agent
                    description = llm_agent.generate_text(prompt).strip()

                    # Limit description length if needed
                    if len(description) > 500:
                        description = description[:497] + "..."
                except Exception as e:
                    logger.error(
                        f"Error generating description for issue_type '{issue_type}': {str(e)}")
                    # Default description if no fallback found
                    description = f"{issue_type}: This alert may indicate a problem with your Kubernetes resources or applications. Check the pod events and logs for more details."

        # Return a single JSON with all pods for that issue_type
        response = {
            "issue_type": issue_type,
            "analysis": analysis_results
        }

        # Add description and events_metadata if available
        if description:
            response["description"] = description
        if events_metadata:
            response["events_metadata"] = events_metadata

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error analyzing issue '{issue_type}': {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/sources')
def get_data_sources():
    """
    Returns available data sources that can be used for filtering.
    """
    sources = [
        {"id": "all", "name": "All Sources",
            "description": "Data from all available sources"},
        {"id": "kubernetes", "name": "Kubernetes",
            "description": "Pod events from Kubernetes API"},
        {"id": "prometheus", "name": "Prometheus",
            "description": "Metrics and alerts from Prometheus"},
        {"id": "argocd", "name": "ArgoCD",
            "description": "Application deployments and sync status from ArgoCD"}
    ]
    return jsonify(sources)


@app.route('/api/generate-description')
def generate_alert_description():
    """
    Generates a concise description for an alert using the LLM agent
    """
    alert_type = request.args.get('alert', '')
    source = request.args.get('source', 'kubernetes')

    if not alert_type:
        return jsonify({
            "success": False,
            "message": "Missing alert parameter",
            "description": "Unknown alert type"
        }), 400

    # Fallback descriptions for common alerts
    fallback_descriptions = {
        "CrashLoopBackOff": "Indicates a pod repeatedly crashes after starting. This could be due to application errors, configuration issues, or resource constraints that prevent the container from running properly.",
        "PodOOMKilled": "Signals that a pod was terminated due to Out Of Memory. The container exceeded its memory limit or the node ran out of memory, causing the kernel to kill the process.",
        "ImagePullError": "Occurs when Kubernetes cannot pull the specified container image. This could be due to invalid image names, missing credentials for private repositories, or network issues.",
        "FailedScheduling": "Indicates that the Kubernetes scheduler cannot find a suitable node to place a pod. This may be due to insufficient resources, node taints, or pod constraints.",
        "PodFailure": "A generic alert indicating a pod has failed. This could be for various reasons including application crashes, configuration errors, or infrastructure issues.",
        "KubePodCrashLooping": "Similar to CrashLoopBackOff, indicates that pods are repeatedly crashing shortly after starting, suggesting application or configuration problems.",
        "TargetDown": "Prometheus alert indicating a monitored target is unreachable. This could mean the service is down or there are network connectivity issues.",
        "HighCPUUsage": "Prometheus alert for excessive CPU consumption, which may indicate application inefficiency, unexpected load, or insufficient resources.",
        "KubeDeploymentReplicasMismatch": "Indicates a discrepancy between desired and current replica counts in a deployment, suggesting scaling or scheduling issues."
    }

    try:
        # Check if we have a fallback for this alert type
        if alert_type in fallback_descriptions:
            logger.info(
                f"Using fallback description for alert type: {alert_type}")
            return jsonify({
                "success": True,
                "description": fallback_descriptions[alert_type],
                "source": "fallback"
            })

        # Format the prompt for the LLM agent
        prompt = f"""
        Generate a short, concise explanation (40-60 words) of what the following Kubernetes/cloud alert means:

        Alert: {alert_type}
        Source: {source}

        Explain in plain language what this alert typically indicates, potential impacts, and the general category of issue.
        Keep it technical but accessible to DevOps engineers.
        """

        # Get the description from the LLM agent
        description = llm_agent.generate_text(prompt).strip()

        # Limit description length if needed
        if len(description) > 500:
            description = description[:497] + "..."

        return jsonify({
            "success": True,
            "description": description,
            "source": "llm"
        })

    except Exception as e:
        logger.error(f"Error generating alert description: {str(e)}")

        # Try to use fallback if available, otherwise return a generic message
        if alert_type in fallback_descriptions:
            return jsonify({
                "success": True,
                "description": fallback_descriptions[alert_type],
                "source": "fallback"
            })

        return jsonify({
            "success": False,
            "message": f"Failed to generate description: {str(e)}",
            "description": f"{alert_type}: This alert may indicate a problem with your Kubernetes resources or applications. Check the pod events and logs for more details.",
            "source": "fallback"
        }), 200  # Return 200 instead of 500 to avoid UI errors

@app.route('/api/anonymization/preview', methods=['POST'])
def preview_anonymization():
    """
    Preview what data would be anonymized before sending to OpenAI.
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        preview_result = llm_agent.preview_anonymization(data)
        
        return jsonify({
            "success": True,
            "preview": preview_result
        })
        
    except Exception as e:
        logger.error(f"Error previewing anonymization: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/anonymization/toggle', methods=['POST'])
def toggle_anonymization():
    """
    Enable or disable anonymization for the LLM agent.
    """
    try:
        data = request.json
        enabled = data.get('enabled', True)
        
        llm_agent.set_anonymization(enabled)
        
        return jsonify({
            "success": True,
            "anonymization_enabled": enabled,
            "message": f"Anonymization {'enabled' if enabled else 'disabled'}"
        })
        
    except Exception as e:
        logger.error(f"Error toggling anonymization: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/react/status', methods=['GET'])
def get_react_status():
    """
    Get current ReAct agent status and configuration.
    """
    try:
        status = llm_agent.get_react_status()
        return jsonify({
            "success": True,
            "react_status": status
        })
        
    except Exception as e:
        logger.error(f"Error getting ReAct status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/react/configure', methods=['POST'])
def configure_react():
    """
    Configure ReAct agent settings.
    """
    try:
        data = request.json
        enabled = data.get('enabled', True)
        
        # Extract ReAct configuration
        react_config = {}
        if 'max_iterations' in data:
            react_config['max_iterations'] = int(data['max_iterations'])
        if 'confidence_threshold' in data:
            react_config['confidence_threshold'] = float(data['confidence_threshold'])
        if 'command_timeout' in data:
            react_config['command_timeout'] = int(data['command_timeout'])
        
        # Update ReAct configuration
        llm_agent.set_react_mode(enabled, **react_config)
        
        return jsonify({
            "success": True,
            "message": f"ReAct mode {'enabled' if enabled else 'disabled'}",
            "react_status": llm_agent.get_react_status()
        })
        
    except Exception as e:
        logger.error(f"Error configuring ReAct: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/terminal/analyze', methods=['POST'])
def terminal_analyze():
    """
    Endpoint to analyze pod/event metadata using LLM for the terminal interface
    """
    try:
        # Get request data
        data = request.json
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Extract metadata
        metadata = data.get('metadata', {})
        
        # Use the LLM agent if it's available (from your existing code)
        if 'llm_agent' in globals():
            analysis_result = analyze_with_llm_agent(metadata)
        else:
            # Fallback to direct OpenAI call
            analysis_result = analyze_with_openai(metadata)
            
        return jsonify(analysis_result)
    
    except Exception as e:
        logger.error(f"Error in terminal analysis: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "rootCause": "Analysis failed due to a server error.",
            "recommendations": [
                "Try again later",
                "Check server logs for more details"
            ]
        }), 500

@app.route('/api/pod-diagnosis/<namespace>/<pod_name>')
def diagnose_pod_failure(namespace, pod_name):
    """
    Diagnose a specific pod failure using real kubectl data and LLM analysis.
    Returns structured diagnosis with root cause analysis and recommendations.
    """
    try:
        # Gather real metadata using k8s_tool
        metadata = k8s_tool.gather_metadata(namespace, pod_name)
        
        if not metadata or not metadata.get('raw_describe'):
            return jsonify({
                "error": f"Pod '{pod_name}' not found in namespace '{namespace}' or unable to gather metadata",
                "rootCause": "Pod not found or kubectl access issue",
                "recommendations": [
                    f"Verify pod '{pod_name}' exists in namespace '{namespace}'",
                    "Check kubectl connectivity and permissions",
                    "Try: kubectl get pods -n " + namespace
                ]
            }), 404
        
        # Use the enhanced LLM agent for diagnosis
        analysis_result = llm_agent.diagnose_pod_failure(metadata)
        
        # Parse the structured response from LLM
        parsed_result = parse_llm_diagnosis(analysis_result)
        
        # Add metadata for frontend
        parsed_result['metadata'] = {
            'namespace': namespace,
            'pod_name': pod_name,
            'timestamp': datetime.now().isoformat(),
            'containers': metadata.get('containers', []),
            'events_count': len(metadata.get('events', []))
        }
        
        return jsonify(parsed_result)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"kubectl error for pod {pod_name} in {namespace}: {str(e)}")
        return jsonify({
            "error": "Kubernetes API error",
            "rootCause": "Unable to access Kubernetes cluster",
            "recommendations": [
                "Check kubectl configuration and cluster connectivity",
                "Verify you have permissions to access the namespace",
                "Try: kubectl cluster-info"
            ]
        }), 503
        
    except Exception as e:
        logger.error(f"Error diagnosing pod {pod_name} in {namespace}: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Internal server error during diagnosis",
            "rootCause": "Server error during analysis",
            "recommendations": [
                "Try again in a few moments",
                "Check server logs for more details",
                "Contact support if the issue persists"
            ]
        }), 500

def parse_llm_diagnosis(llm_response):
    """
    Parse the structured LLM response into JSON format for frontend consumption.
    Expected format from LLM:
    === ROOT CAUSE ANALYSIS ===
    [explanation]
    
    === RECOMMENDED ACTIONS ===
    1. [action]
    2. [action]
    
    === KUBECTL COMMANDS TO RUN ===
    [commands]
    """
    try:
        sections = llm_response.split('===')
        
        root_cause = ""
        recommendations = []
        kubectl_commands = ""
        
        for i, section in enumerate(sections):
            section = section.strip()
            if 'ROOT CAUSE ANALYSIS' in section:
                # Get the next section's content
                if i + 1 < len(sections):
                    root_cause = sections[i + 1].strip()
            elif 'RECOMMENDED ACTIONS' in section:
                if i + 1 < len(sections):
                    actions_text = sections[i + 1].strip()
                    # Parse numbered actions
                    for line in actions_text.split('\n'):
                        line = line.strip()
                        if line and (line[0].isdigit() or line.startswith('-') or line.startswith('*')):
                            # Clean up numbering and bullet points
                            clean_line = line
                            if line[0].isdigit() and '. ' in line:
                                clean_line = line[line.find('. ') + 2:]
                            elif line.startswith('- '):
                                clean_line = line[2:]
                            elif line.startswith('* '):
                                clean_line = line[2:]
                            recommendations.append(clean_line)
            elif 'KUBECTL COMMANDS' in section:
                if i + 1 < len(sections):
                    kubectl_commands = sections[i + 1].strip()
        
        # Fallback parsing if structured format isn't found
        if not root_cause and not recommendations:
            lines = llm_response.split('\n')
            root_cause = "Analysis provided below"
            recommendations = [line.strip() for line in lines if line.strip()]
            
        return {
            "rootCause": root_cause or "Unable to determine root cause",
            "recommendations": recommendations or ["Check the full analysis output"],
            "kubectl_commands": kubectl_commands,
            "raw_output": llm_response
        }
        
    except Exception as e:
        logger.error(f"Error parsing LLM diagnosis: {str(e)}")
        return {
            "rootCause": "Unable to parse diagnosis",
            "recommendations": ["See raw output for full analysis"],
            "kubectl_commands": "",
            "raw_output": llm_response
        }

def analyze_with_llm_agent(metadata):
    """
    Use the existing LLM agent to analyze the metadata
    """
    try:
        # Convert metadata to a format suitable for the LLM agent
        analysis_metadata = {
            "namespace": metadata.get("namespace", "unknown"),
            "pod_name": metadata.get("podName", metadata.get("name", "unknown")),
            "issue_type": metadata.get("issueType", "unknown"),
            "severity": metadata.get("severity", "unknown"),
            "source": metadata.get("source", "kubernetes"),
            "events": metadata.get("events", []),
            "raw_describe": metadata.get("rawDescribe", "")
        }
        
        # Use the existing diagnose_pod method from your LLM agent
        llm_response = llm_agent.diagnose_pod(analysis_metadata)
        
        # Parse the response to extract root cause and recommendations
        root_cause = []
        recommendations = []
        
        if "Root Cause:" in llm_response and "Recommended Actions:" in llm_response:
            # Split the response
            root_cause_text = llm_response.split("Root Cause:")[1].split("Recommended Actions:")[0]
            recommendations_text = llm_response.split("Recommended Actions:")[1]
            
            # Process root cause
            root_cause = root_cause_text.strip()
            
            # Process recommendations into a list
            raw_recommendations = [line.strip() for line in recommendations_text.strip().split("\n") if line.strip()]
            recommendations = []
            for rec in raw_recommendations:
                # Remove bullet points if present
                clean_rec = rec
                if rec.startswith("- "):
                    clean_rec = rec[2:]
                elif rec.startswith("* "):
                    clean_rec = rec[2:]
                elif rec.startswith("• "):
                    clean_rec = rec[2:]
                elif rec.startswith("· "):
                    clean_rec = rec[2:]
                # Check for numbered list
                elif rec[0].isdigit() and rec[1:].startswith(". "):
                    clean_rec = rec[rec.find(" ")+1:]
                
                recommendations.append(clean_rec)
        else:
            # Fallback if structured format isn't found
            root_cause = "Analysis could not be structured properly. See full output below."
            recommendations = [llm_response]
        
        return {
            "rootCause": root_cause,
            "recommendations": recommendations,
            "raw_output": llm_response
        }
        
    except Exception as e:
        logger.error(f"Error analyzing with LLM agent: {str(e)}", exc_info=True)
        return {
            "rootCause": "Error during analysis",
            "recommendations": [f"Error: {str(e)}"],
            "raw_output": str(e)
        }

def analyze_with_openai(metadata):
    """
    Direct call to OpenAI API for analysis
    """
    try:
        client = openai.OpenAI()  # Uses OPENAI_API_KEY environment variable
        
        # Format the issue details for the prompt
        issue_details = json.dumps(metadata, indent=2)
        
        system_prompt = """
        You are K3R4 (Kubernetes Error Root-cause Analysis), an expert system for diagnosing Kubernetes issues.
        When presented with metadata about a Kubernetes error or alert, you will:
        1. Analyze the most likely root causes based on the issue type, namespace, pod name, and any other available information
        2. Provide clear, actionable recommendations for resolving the issue
        
        FORMAT YOUR RESPONSE EXACTLY AS FOLLOWS:
        - Start with a concise explanation of the root cause(s)
        - Follow with a numbered list of recommended actions, in order of priority
        - Be specific and technical, but clear
        - Focus on practical solutions that a DevOps engineer can implement immediately
        """
        
        user_prompt = f"""
        Please analyze this Kubernetes issue:
        
        {issue_details}
        
        Determine the most likely root cause and recommend specific actions to resolve it.
        """
        
        response = client.chat.completions.create(
            model="gpt-4",  # You can switch to a different model if needed
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,  # Lower temperature for more focused, technical responses
        )
        
        analysis_text = response.choices[0].message.content
        
        # Try to parse the response into our expected format
        root_cause = ""
        recommendations = []
        
        # Split by lines and process
        lines = analysis_text.strip().split('\n')
        
        # The first paragraph is likely the root cause
        root_cause_lines = []
        i = 0
        while i < len(lines) and not lines[i].strip().startswith("1."):
            if lines[i].strip():
                root_cause_lines.append(lines[i].strip())
            i += 1
        
        root_cause = " ".join(root_cause_lines)
        
        # The rest should be numbered recommendations
        current_rec = ""
        for j in range(i, len(lines)):
            line = lines[j].strip()
            if not line:
                continue
            
            # Check if this is a new numbered item
            if line[0].isdigit() and line[1:].startswith("."):
                if current_rec:
                    recommendations.append(current_rec)
                current_rec = line[line.find(" ")+1:].strip()
            else:
                current_rec += " " + line
        
        # Add the last recommendation if it exists
        if current_rec:
            recommendations.append(current_rec)
        
        # Fallback if we couldn't parse properly
        if not root_cause:
            root_cause = "Analysis could not be structured properly. See full output below."
            recommendations = [analysis_text]
        
        return {
            "rootCause": root_cause,
            "recommendations": recommendations,
            "raw_output": analysis_text
        }
        
    except Exception as e:
        logger.error(f"Error analyzing with OpenAI: {str(e)}", exc_info=True)
        return {
            "rootCause": "Error during OpenAI analysis",
            "recommendations": [f"Error: {str(e)}"],
            "raw_output": str(e)
        }

if __name__ == '__main__':
    app.run(debug=True)
