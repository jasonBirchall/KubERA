from agent.tools import k8s_tool
from flask import Flask, request, jsonify
from agent.tools.k8s_tool import K8sTool
from agent.llm_agent import LlmAgent

app = Flask(__name__)

# Instantiate the manager + agent
agent = LlmAgent(model="gpt-4")
k8s = K8sTool()

@app.route("/api/investigate", methods=["POST"])
def investigate():
    """
    Expects JSON like: { "namespace": "default" }
    Or no body => default 'default'.
    """
    data = request.json or {}
    namespace = data.get("namespace", "default")

    broken_pods = k8s.list_broken_pods()
    if not broken_pods:
        return jsonify({"message": "No broken pods found."})

    # 2. For each broken pod, gather metadata and call the LLM
    results = []
    for pod in broken_pods:
        meta = k8s.gather_metadata(pod_name=pod, namespace=namespace)
        diagnosis = agent.diagnose_pod(meta)
        results.append({
            "pod_name": pod,
            "diagnosis": diagnosis
        })

    return jsonify({"broken_pods": len(broken_pods), "results": results})

@app.route("/", methods=["GET"])
def index():
    return "<h1>Hello from Flask!</h1>"

if __name__ == "__main__":
    app.run(debug=True, port=5000)
