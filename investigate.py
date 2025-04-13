from openai import OpenAI

client = OpenAI()
import subprocess
import json

# Suppose you have a function that calls the LLM
def call_llm(messages):
    response = client.chat.completions.create(model="gpt-4",
    messages=messages)
    return response.choices[0].message.content

def fetch_logs(namespace, pod):
    """
    Attempt to fetch logs. If kubectl logs fails (e.g., container waiting),
    catch CalledProcessError and parse the error so we can feed it to the agent.
    """
    cmd = f"kubectl logs {pod} -n {namespace} --tail=50"
    try:
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
        return output.decode()
    except subprocess.CalledProcessError as e:
        # e.output will contain the stderr/stdout from the kubectl command
        # we feed that error text to the agent, so it can see what's going on
        error_text = e.output.decode()
        return f"Error fetching logs:\n{error_text}"

def is_pod_crashing(namespace, pod) -> bool:
    cmd = f"kubectl get pod {pod} -n {namespace} -o json"
    pod_data = subprocess.check_output(cmd, shell=True).decode()
    pod_json = json.loads(pod_data)
    statuses = pod_json["status"]["containerStatuses"]
    for s in statuses:
        if s.get("state", {}).get("waiting", {}).get("reason") == "CrashLoopBackOff":
            return True
    return False

def get_pod_status(namespace: str, pod_name: str) -> str:
    """
    Returns the pod's phase (e.g. 'Running', 'Pending', 'Succeeded', 'Failed', or 'Unknown').
    You could also parse containerStatuses for CrashLoopBackOff, etc.
    """
    cmd = f"kubectl get pod {pod_name} -n {namespace} -o json"
    output = subprocess.check_output(cmd, shell=True).decode()
    pod_json = json.loads(output)

    # Basic check of the top-level phase:
    phase = pod_json["status"].get("phase", "Unknown")

    # If you specifically want to see if containers are in CrashLoopBackOff, you can do:
    # container_statuses = pod_json["status"].get("containerStatuses", [])
    # for cs in container_statuses:
    #     waiting_state = cs.get("state", {}).get("waiting", {})
    #     reason = waiting_state.get("reason", "")
    #     if reason == "CrashLoopBackOff":
    #         return "CrashLoopBackOff"

    return phase


def investigate_issue(namespace: str, pod_name: str) -> str:
    """
    Very naive logic:
    - Start a conversation describing the crash
    - If the LLM mentions "FETCH_LOGS", we provide logs
    - Otherwise, we return the LLM's final output
    """
    conversation = [
        {"role": "system", "content":
            "You are an AI diagnosing a K8s pod that may be unhealthy. "
            "If you need logs, respond with 'FETCH_LOGS'. "
            "Eventually provide a final root cause if any."},
        {"role": "user", "content": f"The pod {pod_name} in {namespace} might be failing. Please investigate."},
    ]

    for step in range(5):  # up to 5 steps
        llm_reply = call_llm(conversation)

        if "FETCH_LOGS" in llm_reply.upper():
            logs = fetch_logs(namespace, pod_name)
            conversation.append({"role": "assistant", "content": f"Here are logs:\n{logs}"})
        else:
            # No more tool requests, so we consider this final
            return llm_reply

    return "Reached max steps without conclusion"

def main():
    namespace = "default"
    pod_name = "hello-world-8477844756-wqc4m"

    # 1) Check if the pod is healthy
    pod_status = get_pod_status(namespace, pod_name)
    print(f"Pod {pod_name} status: {pod_status}")

    # 2) If healthy (Running/Succeeded), no need to investigate further
    if pod_status in ["Running", "Succeeded"]:
        print("Pod seems okay, no deeper investigation needed.")
    else:
        # 3) If not healthy, call the agent-based approach
        print(f"Pod not healthy (status={pod_status}), investigating...")
        result = investigate_issue(namespace, pod_name)
        print("Investigation result:\n", result)

if __name__ == "__main__":
    main()
