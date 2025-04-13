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
    # or use the python kubernetes library
    cmd = f"kubectl logs {pod} -n {namespace} --tail=50"
    return subprocess.check_output(cmd, shell=True).decode()

def is_pod_crashing(namespace, pod) -> bool:
    cmd = f"kubectl get pod {pod} -n {namespace} -o json"
    pod_data = subprocess.check_output(cmd, shell=True).decode()
    pod_json = json.loads(pod_data)
    statuses = pod_json["status"]["containerStatuses"]
    for s in statuses:
        if s.get("state", {}).get("waiting", {}).get("reason") == "CrashLoopBackOff":
            return True
    return False

def investigate_issue(namespace, pod):
    if not is_pod_crashing(namespace, pod):
        return "Pod is not in CrashLoopBackOff or has recovered - system is OK."
    conversation = [
        {
            "role": "system",
            "content": (
                "You are an AI diagnosing a K8s pod crash. "
                "If the system is actually healthy or not showing errors, reply 'SYSTEM_OK'. "
                "If you need logs or describes, say 'FETCH_LOGS' or 'DESCRIBE_POD', etc. "
                "Otherwise, explain the root cause or final result."
            )
        },
        {
            "role": "user",
            "content": f"The pod {pod} in {namespace} is in CrashLoopBackOff state."
        }
    ]
    # We'll do a simple loop: ask the LLM, see if it requests logs, gather logs, feed them back
    for step in range(5):  # up to 5 steps
        llm_output = call_llm(conversation)

        # parse llm_output to see if it says "fetch logs" or "describe pod" etc.
        if "FETCH_LOGS" in llm_output:
            logs = fetch_logs(namespace, pod)
            conversation.append({"role": "assistant", "content": "Here are the logs:\n" + logs})
        else:
            # if no more tools needed, we assume final answer
            return llm_output

    return "Reached max steps without conclusion"

# Finally, do something to call investigate_issue. For example, if you see a pod failing:
if __name__ == "__main__":
    print(investigate_issue("default", "hello-world-797766869f-klj4p"))
