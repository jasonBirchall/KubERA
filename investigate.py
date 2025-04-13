from openai import OpenAI

import subprocess
import json
from rich.console import Console
from rich.markdown import Markdown

client = OpenAI()
console = Console()

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
      - Container names & images
      - Environment variables (naive line-based approach)
      - Events
    Returns a dictionary with something like:
      {
        "raw_describe": "...",
        "containers": [
          {
            "name": "my-container",
            "image": "ubuntu:latest",
            "env": [
              {"name": "FOO", "value": "bar"},
              ...
            ]
          },
          ...
        ],
        "events": [
          "Last event lines or reason",
          ...
        ]
      }
    If there's an error running 'kubectl describe', we store it in {"error_describe": "..."}.
    """

    try:
        output = subprocess.check_output(
            f"kubectl describe pod {pod_name} -n {namespace}",
            shell=True,
            stderr=subprocess.STDOUT
        ).decode()
    except subprocess.CalledProcessError as e:
        return {"error_describe": e.output.decode()}

    lines = output.splitlines()
    metadata = {
        "raw_describe": output,
        "containers": [],
        "events": []
    }

    current_container = None
    in_environment = False
    in_events = False

    for line in lines:
        line_stripped = line.strip()

        # Detect the "Events:" heading. We'll store subsequent lines as events
        if line_stripped.startswith("Events:"):
            in_events = True
            continue

        # If we are in the events section, parse or store each line until we hit a blank line
        # or the next big heading. We'll just store them as strings for simplicity.
        if in_events:
            if not line_stripped:
                # blank line might end the events section
                in_events = False
            else:
                # store the event line as is
                metadata["events"].append(line_stripped)
            continue

        # If we see a blank line or another heading, end environment parsing
        if not line_stripped or line_stripped.endswith(":"):
            in_environment = False

        # For environment, we do a naive approach:
        if in_environment:
            # Typically environment lines might look like:
            # "FOO:    bar"
            # or "FOO=bar"
            # We'll handle a couple patterns
            if current_container is not None:
                parts = line_stripped.split(":", 1)
                if len(parts) == 2:
                    env_name = parts[0].strip()
                    env_value = parts[1].strip()
                    # If there's a '=' in the name, we handle that
                    if '=' in env_name:
                        # e.g. "FOO=bar"
                        eq_parts = env_name.split('=', 1)
                        env_name = eq_parts[0].strip()
                        env_value = eq_parts[1].strip()
                    current_container.setdefault("env", []).append({
                        "name": env_name,
                        "value": env_value
                    })

        # Look for environment heading
        if line_stripped.startswith("Environment:"):
            in_environment = True
            continue

        # Look for "Name:" line indicating a container name
        # e.g. "    Name:         my-container"
        if line_stripped.startswith("Name:"):
            name_val = line_stripped.split(":", 1)[1].strip()
            # Start a new container record
            current_container = {"name": name_val, "env": []}
            metadata["containers"].append(current_container)

        # Example match: "    Image:          ubuntu:latest"
        if line_stripped.startswith("Image:"):
            image_val = line_stripped.split(":", 1)[1].strip()
            if current_container:
                current_container["image"] = image_val

    for container in metadata["containers"]:
        image_name = container.get("image")
        if image_name:
            exists = check_docker_image_exists(image_name)
            container["image_valid"] = exists

    return metadata

def llm_diagnose(metadata):
    """
    Given a dictionary 'metadata' which might include:
      - "containers": [
          {
            "name": str,
            "image": str,
            "image_valid": bool,    # if you do Docker checks
            "env": [ { "name": ..., "value": ... }, ... ]
          },
          ...
        ]
      - "events": [str, ...]
      - "raw_describe": str
      - Possibly other fields you add

    We pass it all to the LLM. A single conversation:
      1) System message: "Here's how to interpret each field..."
      2) Assistant message: "Here is the metadata: ... (the JSON dump)."
      3) User message: "Given this data, what's the likely root cause & fix?"

    The LLM can handle many potential issues (image invalid, environment problems, CrashLoopBackOff, etc.)
    """

    # 1) Summarise or define the meaning of each field for the LLM in the system prompt
    #    This ensures it knows how to interpret, e.g. "image_valid: false => the image might be missing."
    system_prompt = (
        "You are an AI diagnosing K8s pods. We have some metadata fields:\n"
        "- 'containers': a list of containers in this pod.\n"
        "   Each container can have:\n"
        "      name: container name.\n"
        "      image: the Docker image string.\n"
        "      image_valid: a boolean we derived from checking if the image exists in a registry.\n"
        "         (true means we verified the image can be pulled, false means it's likely invalid or private.)\n"
        "      env: environment variables in that container.\n"
        "- 'events': lines from 'kubectl describe' that show warnings or error messages.\n"
        "- 'raw_describe': the entire text from 'kubectl describe pod'.\n"
        "If 'image_valid' is false, it might indicate an invalid or non-existent container image.\n"
        "If 'events' mention CrashLoopBackOff, or ErrImagePull, that's also relevant.\n"
        "Use these clues to figure out potential root causes.\n"
        "Finally, propose recommended fixes or next steps.\n"
    )

    # 2) Turn your metadata into a JSON string. That can be 'assistant' role,
    #    so the LLM sees it as data it can parse or read.
    metadata_json = json.dumps(metadata, indent=2)

    # 3) We'll define a user prompt that instructs the LLM to provide a diagnosis
    user_prompt = (
        "Given the above metadata, please diagnose the likely cause(s) of any issues. "
        "Propose how to fix them or what next steps to take. If everything looks fine, say so."
    )

    # Build the conversation
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "assistant",
            "content": f"Here is the metadata:\n{metadata_json}"
        },
        {"role": "user", "content": user_prompt}
    ]
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.7,
    )
    return response.choices[0].message.content


def check_docker_image_exists(image_name: str) -> bool:
    """
    Returns True if 'docker manifest inspect <image_name>' succeeds,
    otherwise returns False.
    Note: requires Docker installed and a running Docker daemon.
    """
    cmd = ["docker", "manifest", "inspect", image_name]
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError as e:
        # Non-zero exit code indicates the image probably doesn't exist
        # or there's some networking/credential issue
        return False

def inspect_docker_image(image_name: str) -> str:
    """
    Attempts to run 'docker manifest inspect <image_name>'.
    Returns the output as a string if successful,
    or an error message if not.
    """
    cmd = ["docker", "manifest", "inspect", image_name]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
        return output
    except subprocess.CalledProcessError as e:
        return f"Error inspecting image '{image_name}': {e.output.decode()}"

def main():
    namespace = "default"
    pod_name = "hello-world-8477844756-wqc4m" # Broken pod
    # pod_name = "hello-world-797766869f-5tnlc" # Working pod

    console.print(f"[bold cyan]Checking pod [yellow]{pod_name}[/yellow] in namespace [magenta]{namespace}[/magenta]...[/bold cyan]")

    if not is_pod_failing(namespace, pod_name):
        console.print("[bold green]Pod is healthy! No issues found.[/bold green]")
        return

    console.print("[bold red]Pod appears to be in an error state. Gathering metadata...[/bold red]")
    metadata = gather_metadata(namespace, pod_name)

    console.print("[bold blue]Metadata gathered. Now calling the LLM for a diagnosis...[/bold blue]")
    result = llm_diagnose(metadata)

    console.print("[bold white on magenta]\nLLM DIAGNOSIS:[/bold white on magenta]")
    # We can render the LLM's result as Markdown for nice formatting
    console.print(Markdown(result))

    console.print("[bold green]\nDone![/bold green]")

if __name__ == "__main__":
    main()
