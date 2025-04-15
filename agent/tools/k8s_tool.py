import subprocess
import json
from rich.console import Console
from agent.tools.docker_tool import DockerTool

console = Console()

class K8sTool:
    """Tool for interacting with Kubernetes cluster via kubectl."""
    
    def __init__(self):
        pass  # or inject config if needed
    
    def list_broken_pods(self, namespace="default"):
        """
        Return a list of pod names in the given namespace that appear to be failing 
        (i.e. CrashLoopBackOff, ErrImagePull, etc.).
        """
        failing_pods = []
        try:
            cmd = f"kubectl get pods -n {namespace} -o json"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
            data = json.loads(output.decode())
            
            for item in data.get("items", []):
                pod_name = item["metadata"]["name"]
                phase = item["status"].get("phase", "")
                if phase == "Failed":
                    failing_pods.append(pod_name)
                    continue

                container_statuses = item["status"].get("containerStatuses", [])
                for cstatus in container_statuses:
                    wait_reason = cstatus.get("state", {}).get("waiting", {}).get("reason", "")
                    if wait_reason in ["CrashLoopBackOff", "ErrImagePull", "ImagePullBackOff"]:
                        failing_pods.append(pod_name)
                        break
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Error listing pods:[/red] {e.output.decode()}")
        return failing_pods

    def gather_metadata(self, namespace, pod_name):
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
                exists = DockerTool(image_name).check_docker_image_exists()
                container["image_valid"] = exists

        return metadata


    def fetch_logs(self, namespace, pod_name, container_name=None, lines=50):
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
