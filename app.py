from flask import Flask, render_template, request, jsonify
import datetime
import json
import random
from datetime import datetime, timedelta

# Try to import your actual tools, fall back to mocks if not available
try:
    from agent.tools.k8s_tool import K8sTool
    from agent.llm_agent import LlmAgent
    
    # Initialize the actual tools
    k8s_tool = K8sTool()
    llm_agent = LlmAgent()
    using_real_tools = True
    print("Using real K8s tools and LLM agent")
except ImportError:
    # Create mock classes if the real ones aren't available
    print("Warning: Could not import real K8s tools or LLM agent. Using mocks.")
    using_real_tools = False
    
    class MockK8sTool:
        def list_broken_pods(self, namespace="default"):
            return ["mock-pod-1", "mock-pod-2", "mock-pod-3"]
        
        def gather_metadata(self, namespace, pod_name):
            return {
                "containers": [
                    {
                        "name": "mock-container",
                        "image": "nginx:latest",
                        "image_valid": True
                    }
                ],
                "events": [
                    "Warning: BackOff - Back-off restarting failed container",
                    "Normal: Pulled - Container image pulled successfully"
                ],
                "raw_describe": "Mock kubectl describe output"
            }
        
        def fetch_logs(self, namespace, pod_name, container_name=None, lines=50):
            return "2023-01-01T00:00:00Z INFO Mock log line 1\n2023-01-01T00:00:01Z ERROR Mock error line"
    
    class MockLlmAgent:
        def diagnose_pod(self, metadata):
            return """
Based on the provided metadata, this pod appears to be experiencing a CrashLoopBackOff issue.

Root Cause:
1. The container is repeatedly crashing after startup
2. This is often caused by application errors, missing configuration, or resource constraints

Recommended Actions:
1. Check application logs for error messages
2. Verify environment variables and config maps
3. Ensure sufficient CPU and memory resources are allocated
4. Check for connectivity issues to dependent services

You can investigate further by running:
kubectl logs <pod-name> -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
"""
    
    # Initialize mock tools
    k8s_tool = MockK8sTool()
    llm_agent = MockLlmAgent()

app = Flask(__name__)

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
    containers = pod_metadata.get("containers", [])
    for container in containers:
        if container.get("image_valid") is False:
            return "ImagePullError"
    
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

@app.route('/api/cluster_issues')
def get_cluster_issues():
    """
    API endpoint to get all issues in the cluster
    This will be used to populate the timeline view
    """
    try:
        # In a real implementation, we would scan all namespaces
        # For simplicity, we'll just check the default namespace
        namespace = "default"
        
        if using_real_tools:
            # Use the real K8s tool to get broken pods
            broken_pods = k8s_tool.list_broken_pods(namespace=namespace)
            
            # Group the issues by type
            issue_groups = {}
            
            for pod in broken_pods:
                # Get pod metadata
                metadata = k8s_tool.gather_metadata(namespace, pod)
                
                # Determine the issue type
                issue_type = determine_issue_type(metadata)
                severity = determine_severity(issue_type)
                
                # Add to the appropriate group
                if issue_type not in issue_groups:
                    issue_groups[issue_type] = {
                        "name": issue_type,
                        "severity": severity,
                        "pods": [],
                        "count": 0
                    }
                
                issue_groups[issue_type]["pods"].append({
                    "name": pod,
                    "namespace": namespace,
                    "timestamp": datetime.now().isoformat()
                })
                issue_groups[issue_type]["count"] += 1
        else:
            # Use mock data that matches the screenshot
            issue_groups = {
                "HighLatencyForCustomerCheckout": {
                    "name": "HighLatencyForCustomerCheckout",
                    "severity": "high",
                    "pods": [{"name": f"checkout-pod-{i}", "namespace": "default", "timestamp": datetime.now().isoformat()} for i in range(12)],
                    "count": 12
                },
                "KubeDeploymentReplicasMismatch": {
                    "name": "KubeDeploymentReplicasMismatch",
                    "severity": "medium",
                    "pods": [{"name": f"deployment-pod-{i}", "namespace": "default", "timestamp": datetime.now().isoformat()} for i in range(3)],
                    "count": 3
                },
                "KubePodCrashLooping": {
                    "name": "KubePodCrashLooping",
                    "severity": "high",
                    "pods": [{"name": f"crash-pod-{i}", "namespace": "default", "timestamp": datetime.now().isoformat()} for i in range(2)],
                    "count": 2
                },
                "TargetDown": {
                    "name": "TargetDown",
                    "severity": "medium",
                    "pods": [{"name": "target-pod-1", "namespace": "default", "timestamp": datetime.now().isoformat()}],
                    "count": 1
                },
                "MinishopHighLatency": {
                    "name": "MinishopHighLatency",
                    "severity": "high",
                    "pods": [{"name": "minishop-pod-1", "namespace": "default", "timestamp": datetime.now().isoformat()}],
                    "count": 1
                },
                "PodOOMKilled": {
                    "name": "PodOOMKilled",
                    "severity": "high",
                    "pods": [{"name": f"oom-pod-{i}", "namespace": "default", "timestamp": datetime.now().isoformat()} for i in range(5)],
                    "count": 5
                },
                "CrashLoopBackOff": {
                    "name": "CrashLoopBackOff",
                    "severity": "high",
                    "pods": [{"name": f"crashloop-pod-{i}", "namespace": "default", "timestamp": datetime.now().isoformat()} for i in range(3)],
                    "count": 3
                },
                "SchedulingWarning": {
                    "name": "SchedulingWarning",
                    "severity": "low",
                    "pods": [{"name": f"scheduling-pod-{i}", "namespace": "default", "timestamp": datetime.now().isoformat()} for i in range(2)],
                    "count": 2
                }
            }
        
        # Convert to the format expected by the frontend
        result = list(issue_groups.values())
        
        return jsonify(result)
    except Exception as e:
        print(f"Error fetching cluster issues: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze/<issue_type>')
def analyze_issue(issue_type):
    """
    API endpoint to get analysis for a specific issue type
    This will be used by the analysis panel
    """
    try:
        # In a real implementation, we would:
        # 1. Find all pods with this issue type
        # 2. Gather metadata for each pod
        # 3. Use the LLM agent to diagnose the issues
        
        # For simplicity, we'll just return mock data that matches the screenshot
        mock_diagnoses = {
            "MinishopHighLatency": {
                "root_cause": [
                    "Query Performance: The latency is likely due to inefficient database queries. Consider adding indexes or rewriting the query for better performance.",
                    "Database Performance: Check the database server's performance metrics to ensure it is not overloaded or experiencing resource constraints.",
                    "Scale Resources: If the database is under heavy load, consider scaling the resources allocated to it or distributing the load more effectively.",
                    "Monitor and Profile: Use database profiling tools to monitor query performance and identify any other slow queries that may need optimization."
                ],
                "runbook": [
                    "Check the database's performance metrics",
                    "Analyze slow query logs",
                    "Optimize the identified problematic queries",
                    "Consider adding appropriate indexes",
                    "Monitor the system after changes to verify improvement"
                ],
                "logs": [
                    "2025-03-21T11:52:582 {\"level\":30,\"time\":1742557978538,\"pid\":1,\"hostname\":\"fraud-service-5f8b576878-s1npb\"}",
                    "2025-03-21T11:52:582 {\"level\":30,\"time\":1742557984937,\"pid\":1,\"hostname\":\"fraud-service-5f8b576878-s1npb\"}",
                    "2025-03-21T11:52:582 {\"level\":30,\"time\":1742557978537,\"pid\":1,\"hostname\":\"checkout-service-66cb4b6c4b-77ch1\"}",
                    "2025-03-21T11:53:852 {\"level\":30,\"time\":1742557985516,\"pid\":1,\"hostname\":\"checkout-service-66cb4b6c4b-77ch1\"}"
                ],
                "tools": [
                    "Fetch metadata and history",
                    "Fetched Tempo traces with min_duration=4s (('min_duration': '4s', 'deployment_name': 'minishop', 'namespace_name': 'default'))",
                    "Fetched Tempo trace with trace_id=e342e3a277a3c543603c09e9157a8205 ((trace_id: 'e342e3a277a3c543603c09e9157a8205'))",
                    "Fetched Loki logs((resource_type: 'pod', 'resource_name': 'fraud-service-5f8b576878-s1npb', 'namespace': 'minishop'))",
                    "Fetched Loki logs((resource_type: 'pod', 'resource_name': 'checkout-service-66cb4b6c4b-77ch1', 'namespace': 'minishop'))"
                ]
            },
            "PodOOMKilled": {
                "root_cause": [
                    "Memory Limit: The pod is being terminated because it exceeded its memory limit.",
                    "Application Memory Usage: The application is consuming more memory than allocated.",
                    "Possible Memory Leak: There may be a memory leak in the application code.",
                    "Insufficient Resources: The memory limit may be set too low for the application's needs."
                ],
                "runbook": [
                    "Check the memory limit set in the pod specification",
                    "Review application memory usage patterns",
                    "Increase memory limit if necessary",
                    "Investigate potential memory leaks in the application",
                    "Consider implementing memory profiling"
                ],
                "logs": [
                    "2025-03-21T10:42:123 Container exceeded memory limit (128Mi), killing",
                    "2025-03-21T10:42:124 Killed process due to memory pressure",
                    "2025-03-21T10:42:125 Container restarting"
                ],
                "tools": [
                    "Fetch pod metadata and events",
                    "Analyzed memory usage metrics",
                    "Checked container limits"
                ]
            },
            "CrashLoopBackOff": {
                "root_cause": [
                    "Application Error: The container is crashing due to an error in the application.",
                    "Missing Configuration: Required configuration or environment variables may be missing.",
                    "Dependency Issues: The application may be unable to connect to required services.",
                    "Resource Constraints: The container may be hitting resource limits."
                ],
                "runbook": [
                    "Check container logs for error messages",
                    "Verify all required environment variables and config maps are present",
                    "Ensure dependencies are available and accessible",
                    "Check resource usage and increase limits if necessary"
                ],
                "logs": [
                    "2025-03-21T11:02:001 Error: Unable to connect to database",
                    "2025-03-21T11:02:002 Application exited with code 1",
                    "2025-03-21T11:02:010 Back-off restarting failed container"
                ],
                "tools": [
                    "Fetch pod metadata and events",
                    "Analyzed container logs",
                    "Checked connectivity to dependencies"
                ]
            }
        }
        
        # If we have a diagnosis for this issue type, return it
        if issue_type in mock_diagnoses:
            return jsonify(mock_diagnoses[issue_type])
        
        # Otherwise, generate a generic diagnosis
        if using_real_tools:
            # Find a pod with this issue type
            namespace = "default"
            broken_pods = k8s_tool.list_broken_pods(namespace=namespace)
            
            if broken_pods:
                # Use the first broken pod for diagnosis
                pod = broken_pods[0]
                metadata = k8s_tool.gather_metadata(namespace, pod)
                
                # Use the LLM agent to diagnose
                diagnosis = llm_agent.diagnose_pod(metadata)
                
                # Parse the diagnosis into sections
                # This is a simplified approach - in a real implementation, 
                # you might want to structure the output of the LLM more carefully
                root_cause = diagnosis.split("Root Cause:")[1].split("Recommended Actions:")[0].strip().split("\n")
                runbook = diagnosis.split("Recommended Actions:")[1].strip().split("\n")
                
                return jsonify({
                    "root_cause": root_cause,
                    "runbook": runbook,
                    "logs": [
                        f"{datetime.now().isoformat()} Log line from {pod}"
                    ],
                    "tools": [
                        "Fetch pod metadata and events",
                        "Analyzed with LLM agent",
                        "Checked pod status"
                    ]
                })
        
        # Fallback to an empty diagnosis
        return jsonify({
            "root_cause": [
                f"No specific diagnosis available for {issue_type}.",
                "Please check pod logs and events for more information."
            ],
            "runbook": [
                "Check pod logs",
                "Examine pod events",
                "Review pod configuration"
            ],
            "logs": [],
            "tools": [
                "Fetch pod metadata and events"
            ]
        })
    except Exception as e:
        print(f"Error analyzing issue: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
