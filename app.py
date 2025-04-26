import logging
import subprocess
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, render_template, request
from sqlalchemy import text

from agent.llm_agent import LlmAgent
from agent.tools.argocd_tool import ArgoCDTool
from agent.tools.k8s_tool import K8sTool
from agent.tools.prometheus_tool import PrometheusTool
from db import engine, init_db, migrate_db, record_failure

k8s_tool = K8sTool()
prometheus_tool = PrometheusTool()  # Using default localhost:9090
argocd_tool = ArgoCDTool(base_url="http://localhost:8501")
llm_agent = LlmAgent()

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

migrate_db()
init_db()


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
    app.logger.debug(
        f"[DEBUG] Namespaces identified for filter = {namespaces}")

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
        app.logger.error(f"Error fetching Kubernetes contexts: {str(e)}")
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
        app.logger.error(f"Error switching Kubernetes context: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Failed to switch context: {str(e)}"
        }), 500


@app.route('/api/timeline_data')
def get_timeline_data():
    hours = request.args.get('hours', 6, type=int)
    namespace = request.args.get('namespace', 'default')
    # 'kubernetes', 'prometheus', or 'all'
    data_source = request.args.get('source', 'all')
    horizon = datetime.now(timezone.utc) - timedelta(hours=hours)

    issue_groups = {}

    # Get Kubernetes data if requested
    if data_source in ['all', 'kubernetes']:
        for pod in k8s_tool.list_broken_pods(namespace):
            # Get the failure window for this pod
            first_seen, last_seen = k8s_tool.failure_window(
                namespace, pod, horizon)
            issue = k8s_tool.determine_issue_type(
                k8s_tool.gather_metadata(namespace, pod))
            severity = k8s_tool.determine_severity(issue)

            grp = issue_groups.setdefault(f"{issue}_k8s", {
                "name": issue,
                "severity": severity,
                "pods": [],
                "count": 0,
                "source": "kubernetes"
            })

            grp["pods"].append({
                "name": pod,
                "namespace": namespace,
                "start": first_seen.isoformat(),
                "end": None if last_seen is None else last_seen.isoformat(),  # None → still occurring
                "source": "kubernetes"
            })
            grp["count"] += 1

            record_failure(namespace, pod, issue, severity,
                           first_seen, last_seen, source="kubernetes")

    if data_source in ['all', 'argocd']:
        # Get ArgoCD alerts
        argocd_alerts = argocd_tool.get_application_alerts(hours)
        app.logger.debug(f"[DEBUG] ArgoCD alerts = {argocd_alerts}")

        # Verify alerts have the correct source
        for alert in argocd_alerts:
            # Make sure the alert has the source set to 'argocd'
            if alert.get('source') != 'argocd':
                alert['source'] = 'argocd'

            # Make sure all pods have the source set to 'argocd'
            for pod in alert.get('pods', []):
                if pod.get('source') != 'argocd':
                    pod['source'] = 'argocd'

    # Similar check in the get_cluster_issues function:
    if data_source in ['all', 'argocd']:
        argocd_alerts = argocd_tool.get_application_alerts(hours=1)
        app.logger.debug(f"[DEBUG] ArgoCD alerts = {argocd_alerts}")

        # Verify alerts have the correct source
        for alert in argocd_alerts:
            # Make sure the alert has the source set to 'argocd'
            if alert.get('source') != 'argocd':
                alert['source'] = 'argocd'

            # Make sure all pods have the source set to 'argocd'
            for pod in alert.get('pods', []):
                if pod.get('source') != 'argocd':
                    pod['source'] = 'argocd'

    # Get Prometheus data if requested
    if data_source in ['all', 'prometheus']:
        # Attempt to get real Prometheus data
        prom_alerts = prometheus_tool.get_pod_alerts(hours, namespace)
        app.logger.debug(f"[DEBUG] Prometheus alerts = {prom_alerts}")

        # Process Prometheus alerts
        for alert in prom_alerts:
            alert_name = alert["name"]
            severity = alert["severity"]

            grp = issue_groups.setdefault(f"{alert_name}_prom", {
                "name": alert_name,
                "severity": severity,
                "pods": [],
                "count": 0,
                "source": "prometheus"
            })

            for pod in alert.get("pods", []):
                pod_name = pod.get("name")
                pod_namespace = pod.get("namespace", namespace)
                start_time = datetime.fromisoformat(
                    pod.get("start").replace("Z", "+00:00"))

                end_iso = pod.get("end")
                end_time = None if end_iso is None else datetime.fromisoformat(
                    end_iso.replace("Z", "+00:00"))

                grp["pods"].append({
                    "name": pod_name,
                    "namespace": pod_namespace,
                    "start": pod.get("start"),
                    "end": pod.get("end"),
                    "source": "prometheus"
                })
                grp["count"] += 1

                record_failure(pod_namespace, pod_name, alert_name, severity,
                               start_time, end_time, source="prometheus")

    return jsonify(list(issue_groups.values()))


@app.route('/api/timeline_history')
def timeline_history():
    hours = request.args.get('hours', 24, type=int)
    # 'kubernetes', 'prometheus', or 'all'
    source = request.args.get('source', 'all')
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Build the source filter condition
    source_filter = ""
    if source == 'kubernetes':
        source_filter = "AND source = 'kubernetes'"
    elif source == 'prometheus':
        source_filter = "AND source = 'prometheus'"

    # ---- open a connection and run the query ----
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT namespace, pod_name, issue_type, severity,
                       first_seen, last_seen, source
                  FROM pod_alerts
                 WHERE (first_seen >= :cutoff
                    OR last_seen IS NULL)
                    {source_filter}
            """),
            {"cutoff": cutoff.isoformat()}
        ).mappings().all()          # .mappings() → rows as dict‑like objects

    # ---- build the response exactly as before, but including source ----
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
            "name": r["pod_name"],
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
    namespace = "default"
    # 'kubernetes', 'prometheus', 'argocd', or 'all'
    data_source = request.args.get('source', 'all')
    issue_groups = {}

    # Get Kubernetes data if requested
    if data_source in ['all', 'kubernetes']:
        broken_pods = k8s_tool.list_broken_pods(namespace=namespace)
        app.logger.debug(f"[DEBUG] Broken pods = {broken_pods}")

        for pod_name in broken_pods:
            metadata = k8s_tool.gather_metadata(namespace, pod_name)
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
                "namespace": namespace,
                "timestamp": datetime.now().isoformat(),
                "source": "kubernetes"
            })
            issue_groups[issue_type]["count"] += 1

    # Get Prometheus data if requested
    if data_source in ['all', 'prometheus']:
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
                    "namespace": pod.get("namespace", namespace),
                    "timestamp": datetime.now().isoformat(),
                    "source": "prometheus"
                })
                issue_groups[f"{alert_name}_prom"]["count"] += 1

    # Get ArgoCD data if requested
    if data_source in ['all', 'argocd']:
        argocd_alerts = argocd_tool.get_application_alerts(hours=1)

        # Process ArgoCD alerts
        for alert in argocd_alerts:
            alert_name = alert["name"]
            severity = alert["severity"]

            if f"{alert_name}_argo" not in issue_groups:
                issue_groups[f"{alert_name}_argo"] = {
                    "name": alert_name,
                    "severity": severity,
                    "pods": [],
                    "count": 0,
                    "source": "argocd"
                }

            for pod in alert.get("pods", []):
                issue_groups[f"{alert_name}_argo"]["pods"].append({
                    "name": pod.get("name"),
                    "namespace": pod.get("namespace", namespace),
                    "timestamp": datetime.now().isoformat(),
                    "source": "argocd",
                    "details": pod.get("details", {})
                })
                issue_groups[f"{alert_name}_argo"]["count"] += 1

    app.logger.debug(f"[DEBUG] Issue groups = {issue_groups}")
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
        app.logger.error(
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
            app.logger.info(
                f"Fetching metadata from database for issue type: {compare_issue}, source: {source}")

            # Query the SQLite database for events with this issue type
            with engine.connect() as conn:
                # Build query based on source and issue type
                query = """
                    SELECT namespace, pod_name, issue_type, severity,
                           first_seen, last_seen, source
                    FROM pod_alerts
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

            app.logger.info(f"Found {len(events_metadata)} events in database")

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
                app.logger.info(
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
                    app.logger.error(
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
        print(f"Error analyzing issue '{issue_type}': {str(e)}")
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
            app.logger.info(
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
        app.logger.error(f"Error generating alert description: {str(e)}")

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


if __name__ == '__main__':
    app.run(debug=True)
