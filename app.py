from flask import Flask, render_template, request, redirect, url_for
import random

app = Flask(__name__)

# Simulate Tools or Data
# In reality, you'd import your K8sTool / ToolManager to get actual data
def get_cluster_overview():
    """
    Return cluster-wide info: 
    - total nodes/pods
    - list of all namespaces
    - which namespaces have failing pods
    """
    cluster_info = {
        "nodes": 3,
        "pods": 15,
        "namespaces": [
            {
                "name": "default",
                "broken_pods": True,   # Let's say there's an error
                "failing_count": 2
            },
            {
                "name": "kube-system",
                "broken_pods": False,
                "failing_count": 0
            },
            {
                "name": "monitoring",
                "broken_pods": True,
                "failing_count": 1
            },
            {
                "name": "application",
                "broken_pods": False,
                "failing_count": 0
            }
        ]
    }
    return cluster_info


def get_broken_pods_in_namespace(namespace):
    """
    Return a list of failing pods for the chosen namespace.
    Real logic might call a K8sTool to find CrashLoopBackOff pods, etc.
    """
    if namespace == "default":
        return ["payment-service", "auth-service"]
    elif namespace == "monitoring":
        return ["prometheus-deployment-xyz"]
    else:
        return []


@app.route("/")
def index():
    """Show the cluster overview page, including any failing namespaces."""
    cluster = get_cluster_overview()
    return render_template("index.html", cluster=cluster)

@app.route("/analyze/<namespace>")
def analyze_namespace(namespace):
    """Show detail view for the chosen namespace, listing broken pods."""
    broken_pods = get_broken_pods_in_namespace(namespace)
    return render_template("analyze.html", 
                           namespace=namespace, 
                           broken_pods=broken_pods)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
