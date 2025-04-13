from openai import OpenAI

client = OpenAI()
import subprocess
import json

# Suppose you have a function that calls the LLM
def call_llm(messages):
    response = client.chat.completions.create(model="gpt-4",
    messages=messages)
    return response.choices[0].message.content

def fetch_logs(namespace, pod_name, container_name=None, lines=50):
    """
    Attempt to fetch logs. If container_name isn't specified, omits -c
    """
    cmd = f"kubectl logs {pod_name} -n {namespace} --tail={lines}"
    if container_name:
        cmd += f" -c {container_name}"
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode()
    except subprocess.CalledProcessError as e:
        return f"Error fetching logs:\n{e.output.decode()}"

def is_pod_failing(namespace, pod_name):
    """
    Returns True if the pod has a known error state (like CrashLoopBackOff),
    or if the overall phase is 'Failed'.
    Otherwise returns False.
    """
    try:
        # We'll do a 'kubectl get' with -o json to parse the states
        output = subprocess.check_output(
            f"kubectl get pod {pod_name} -n {namespace} -o json",
            shell=True
        )
    except subprocess.CalledProcessError:
        # If the command fails, the pod might not exist at all
        return True  # or return None to indicate "Pod not found"

    pod_json = json.loads(output.decode())
    phase = pod_json["status"].get("phase", "")
    if phase == "Failed":
        return True

    # Check container statuses for CrashLoopBackOff or similar
    container_statuses = pod_json["status"].get("containerStatuses", [])
    for cstatus in container_statuses:
        waiting_reason = cstatus.get("state", {}).get("waiting", {}).get("reason", "")
        if waiting_reason in ["CrashLoopBackOff", "ErrImagePull", "ImagePullBackOff"]:
            return True
    return False

def gather_metadata(namespace, pod_name):
    """
    Runs 'kubectl describe pod' and parses out relevant fields:
      - Containers, images
      - Environment variables
      - Last events
      - Possibly logs or error messages
    Returns a dictionary or multiline string summarising it.
    """
    try:
        output = subprocess.check_output(
            f"kubectl describe pod {pod_name} -n {namespace}",
            shell=True,
            stderr=subprocess.STDOUT
        ).decode()
    except subprocess.CalledProcessError as e:
        # If there's an error, we can store it
        return {"error_describe": e.output.decode()}

    # Optionally parse out certain fields with a simple approach:
    # For example, get "Image:", "Environment", "Events:"
    # This is naive text matching; for production, consider better parsing or direct JSON from 'kubectl get -o json'
    lines = output.splitlines()
    metadata = {"raw_describe": output, "containers": []}

    # We'll store a minimal approach: container->image, environment lines, events
    current_container = None
    for line in lines:
        line_stripped = line.strip()
        # Container name line looks like "Container ID:   hello-container"
        # or "Name:hello", depending on the version. This is not standardized in every environment
        # We'll just look for something like "Container ID" or "Container Name"
        
        # Example match: "    Image:          ubuntu:latest"
        if line_stripped.startswith("Image:"):
            image = line_stripped.split(":", 1)[1].strip()
            if current_container:
                current_container["image"] = image
        elif line_stripped.startswith("Name:"):
            name_val = line_stripped.split(":", 1)[1].strip()
            # Start a new container record
            current_container = {"name": name_val}
            metadata["containers"].append(current_container)
        elif line_stripped.startswith("Environment:"):
            # subsequent lines might be env vars until next blank line or next heading
            # This is simplistic
            pass
        # ... etc. for environment variables or events
        # For brevity, we'll skip advanced parsing

    # You could parse "Events:" for the last lines that show an error or reasons
    # Then store them in metadata["events"] or something

    return metadata

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

def llm_diagnose(pod_data):
    """
    Calls an LLM with a prompt that includes:
     - The error or status
     - The relevant fields (image, container name, events)
    Then asks: "What is the likely cause, and how can we fix it?"
    """
    # Build the system prompt or conversation
    # Assume pod_data is a dictionary from gather_metadata
    # We'll pass the container info as context
    containers_info = pod_data.get("containers", [])
    raw_describe = pod_data.get("raw_describe", "")
    error = pod_data.get("error_describe", "")

    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI diagnosing issues with a Kubernetes pod. "
                "You have partial metadata from 'kubectl describe', possibly logs. "
                "Provide a short root cause analysis and possible fix."
            )
        }
    ]

    # If there's an error describing the pod, we pass that along
    if error:
        messages.append({
            "role": "assistant",
            "content": f"Error from describe:\n{error}"
        })
    else:
        # Insert relevant container info, events, etc. You can be creative:
        container_summaries = "\n".join(
            f"Container name: {c.get('name')}, image: {c.get('image','')}"
            for c in containers_info
        )
        # We'll keep it basic
        messages.append({
            "role": "assistant",
            "content": (
                f"Describe data:\n{container_summaries}\n\n"
                f"Raw describe snippet:\n{raw_describe[:1000]}..."
                "\n(Truncated for brevity, parse more if needed.)"
            )
        })

    # Finally, the user "asks" for a diagnosis
    messages.append({
        "role": "user",
        "content": (
            "Please summarise the likely cause of any errors and propose a fix. "
            "If you see nothing relevant, state that the pod might be healthy. "
            "Be concise but mention relevant container or image details."
        )
    })

    # response = client.chat.completions.create(model="gpt-4",
    # messages=messages)
    # Call the model
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.7,
    )
    return response.choices[0].message.content

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
    # 1) Check if failing
    failing = is_pod_failing(namespace, pod_name)
    if not failing:
        print(f"Pod {pod_name} doesn't appear to be failing. All good!")
        return

    # 2) If failing, gather metadata
    pod_data = gather_metadata(namespace, pod_name)

    # 3) Optionally fetch logs from a known container
    # logs = fetch_logs(namespace, pod_name, container_name="mycontainer")
    # we could store it in pod_data if we want the LLM to see logs, too
    # e.g. pod_data["some_logs"] = logs

    # 4) Diagnose
    result = llm_diagnose(pod_data)
    print("=== LLM DIAGNOSIS ===")
    print(result)

if __name__ == "__main__":
    main()
