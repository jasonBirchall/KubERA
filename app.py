from flask import Flask, render_template, request, jsonify
import datetime
import random
from datetime import datetime
import logging

from agent.tools.k8s_tool import K8sTool
from agent.llm_agent import LlmAgent
    

k8s_tool = K8sTool()
llm_agent = LlmAgent()
    
app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

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
    high_severity = ["PodOOMKilled", "CrashLoopBackOff", "HighLatencyForCustomerCheckout"]
    medium_severity = ["ImagePullError", "KubeDeploymentReplicasMismatch", "TargetDown", "KubePodCrashLooping"]
    
    if issue_type in high_severity:
        return "high"
    elif issue_type in medium_severity:
        return "medium"
    else:
        return "low"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/timeline_data')
def get_timeline_data():
    """
    Return structured timeline data for K8s issues over time.
    This is separate from the cluster_issues endpoint.
    """
    # Get the time range from query parameters, default to 6 hours
    hours = request.args.get('hours', 6, type=int)
    
    namespace = request.args.get('namespace', 'default')
    broken_pods = k8s_tool.list_broken_pods(namespace=namespace)
    issue_groups = {}
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
                "timeline_position": random.randint(10, 90)  # Random position for demo
            }

        issue_groups[issue_type]["pods"].append({
            "name": pod_name,
            "namespace": namespace,
            "timestamp": datetime.now().isoformat()
        })
        issue_groups[issue_type]["count"] += 1

    app.logger.debug(f"[DEBUG] Timeline data = {issue_groups}")
    return jsonify(list(issue_groups.values()))

@app.route('/api/cluster_issues')
def get_cluster_issues():
    namespace = "default"
    broken_pods = k8s_tool.list_broken_pods(namespace=namespace)
    issue_groups = {}
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
                "count": 0
            }

        issue_groups[issue_type]["pods"].append({
            "name": pod_name,
            "namespace": namespace,
            "timestamp": datetime.now().isoformat()
        })
        issue_groups[issue_type]["count"] += 1

    app.logger.debug(f"[DEBUG] Issue groups = {issue_groups}")
    return jsonify(list(issue_groups.values()))

@app.route('/api/analyze/<issue_type>')
def analyze_issue(issue_type):
    """
    Returns a structured JSON describing the analysis for *all* pods
    in the cluster that exhibit this `issue_type`.
    """
    try:
        namespace = "default"  # or glean from request/query param
        broken_pods = k8s_tool.list_broken_pods(namespace=namespace)

        analysis_results = []
        for pod_name in broken_pods:
            # 1) Gather metadata
            metadata = k8s_tool.gather_metadata(namespace, pod_name)

            # 2) Determine if it actually matches the requested issue_type
            found_issue = determine_issue_type(metadata)
            if found_issue != issue_type:
                continue  # Skip pods that are failing for different reasons

            # 3) Fetch logs for context
            logs = k8s_tool.fetch_logs(namespace, pod_name, lines=100)  # or lines=500, up to you
            metadata["logs"] = logs  # optionally store logs inside metadata before LLM call

            # 4) Call LLM for a diagnosis
            #    The LLM can parse the logs + events in `metadata`
            llm_response = llm_agent.diagnose_pod(metadata)

            # For demonstration, we’ll do a quick naive parse
            # of the LLM's text to separate root causes & recommended actions.
            # You can refine to your liking:
            root_cause = []
            runbook = []

            if "Root Cause:" in llm_response and "Recommended Actions:" in llm_response:
                # naive splitting
                root_cause_text = llm_response.split("Root Cause:")[1].split("Recommended Actions:")[0]
                runbook_text = llm_response.split("Recommended Actions:")[1]

                root_cause = [line.strip()
                              for line in root_cause_text.strip().split("\n") if line.strip()]
                runbook = [line.strip()
                           for line in runbook_text.strip().split("\n") if line.strip()]
            else:
                # fallback if we can’t parse properly
                root_cause = [llm_response]
                runbook = ["No structured runbook found."]

            # 5) Build a single record for this pod
            analysis_results.append({
                "pod_name": pod_name,
                "issue_type": found_issue,  # same as request, but good to confirm
                "root_cause": root_cause,
                "recommended_actions": runbook,
                "pod_events": metadata.get("events", []),
                "logs_excerpt": logs.splitlines()[-10:],  # last 10 lines, for example
                "raw_llm_output": llm_response  # optional, might be large
            })

        # Return a single JSON with all pods for that issue_type
        return jsonify({
            "issue_type": issue_type,
            "analysis": analysis_results
        })

    except Exception as e:
        print(f"Error analyzing issue '{issue_type}': {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
