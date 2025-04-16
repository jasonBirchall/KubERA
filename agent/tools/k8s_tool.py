import subprocess
import json
from rich.console import Console
import logging

logger = logging.getLogger(__name__)
console = Console()

class K8sTool:
    """Tool for interacting with Kubernetes cluster via kubectl."""

    def get_namespaces(self):
        """Get all available namespaces in the cluster"""
        try:
            output = subprocess.check_output("kubectl get namespaces -o=jsonpath='{.items[*].metadata.name}'", 
                                            shell=True, stderr=subprocess.STDOUT)
            namespaces = output.decode().split()
            return namespaces
        except subprocess.CalledProcessError as e:
            logger.error(f"Error getting namespaces: {e.output.decode()}")
            return ["default"]  # Fallback to default namespace

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

    def gather_metadata(self, namespace: str, pod_name: str) -> dict:
        """
        Returns a dictionary with:
          {
            "namespace": str,
            "pod_name": str,
            "raw_describe": str,   # the text output from 'kubectl describe pod'
            "events": [str, ...], # lines extracted from the 'Events:' section
            "containers": [       # array of container info (name, image, waiting reason, etc.)
              {
                "name": str,
                "image": str,
                "waitingReason": str,
                "terminatedReason": str
              }, ...
            ]
          }
        """
        metadata = {
            "namespace": namespace,
            "pod_name": pod_name,
            "raw_describe": "",
            "events": [],
            "containers": []
        }

        # 1) Parse 'kubectl describe pod' for events, environment, etc.
        describe_output = self._run_command(f"kubectl describe pod {pod_name} -n {namespace}")
        if describe_output is not None:
            metadata["raw_describe"] = describe_output
            self._extract_events_from_describe(describe_output, metadata)

        # 2) Parse 'kubectl get pod -o json' for container statuses
        json_output = self._run_command(f"kubectl get pod {pod_name} -n {namespace} -o json")
        if json_output is not None:
            try:
                pod_obj = json.loads(json_output)
                container_statuses = pod_obj["status"].get("containerStatuses", [])
                for cs in container_statuses:
                    cinfo = {
                        "name": cs["name"],
                        "image": cs.get("image", ""),
                        "waitingReason": cs.get("state", {}).get("waiting", {}).get("reason", ""),
                        "terminatedReason": cs.get("state", {}).get("terminated", {}).get("reason", "")
                    }
                    metadata["containers"].append(cinfo)
            except json.JSONDecodeError as e:
                logger.warning(f"Error decoding JSON for {pod_name}: {e}")

        return metadata

    def determine_issue_type(self, metadata: dict) -> str:
        """
        Infers the type of issue (CrashLoopBackOff, PodOOMKilled, ImagePullError, 
        FailingLiveness, etc.)
        """

        events = metadata.get("events", [])
        containers = metadata.get("containers", [])

        # 1) Inspect events for known patterns
        for event_line in events:
            low = event_line.lower()

            # OOMKilled might show up in events as well,
            # but often it's only in container's 'terminated.reason'
            if "oomkilled" in low:
                return "PodOOMKilled"

            # If there's a line about liveness probe failing => 
            # label it "FailingLiveness" (or "LivenessProbeFailure")
            if "liveness probe failed" in low:
                return "FailingLiveness"

            # Some readiness messages might show up similarly
            # if "readiness probe failed" in low:
            #    return "FailingReadiness"

            # CrashLoopBackOff can show up in events directly
            if "crashloopbackoff" in low:
                return "CrashLoopBackOff"

            # Image errors
            if "errimagepull" in low or "imagepullbackoff" in low:
                return "ImagePullError"

            # Scheduling
            if "failedscheduling" in low or "schedulingfailed" in low:
                return "FailedScheduling"

        # 2) Inspect containers for waiting/terminated reasons
        for cinfo in containers:
            wreason = cinfo.get("waitingReason", "")
            treason = cinfo.get("terminatedReason", "")

            # OOM specifically
            if treason == "OOMKilled":
                return "PodOOMKilled"

            # If liveness probe fails repeatedly, eventually might appear as CrashLoopBackOff,
            # but if you want to differentiate, you can do so here
            # if wreason == "RunContainerError" or something else => ???

            # CrashLoopBackOff
            if wreason == "CrashLoopBackOff":
                return "CrashLoopBackOff"

            # Image pull
            if wreason in ["ErrImagePull", "ImagePullBackOff"]:
                return "ImagePullError"

        # 3) If we get here, none of the checks matched
        return "PodFailure"

    def determine_severity(self, issue_type: str) -> str:
        """
        Assigns a severity level ("high", "medium", "low") based on the issue type.
        """
        high_severity = [
            "PodOOMKilled",
            "CrashLoopBackOff",
            "HighLatencyForCustomerCheckout",
        ]
        medium_severity = [
            "ImagePullError",
            "KubeDeploymentReplicasMismatch",
            "TargetDown",
            "KubePodCrashLooping",
        ]

        if issue_type in high_severity:
            return "high"
        elif issue_type in medium_severity:
            return "medium"
        return "low"

    # ---------------------------------------------------------
    # Internal Helper Methods
    # ---------------------------------------------------------

    def _run_command(self, cmd: str) -> str or None:
        """
        Runs a shell command, returns the decoded stdout if successful,
        or logs a warning and returns None on error.
        """
        try:
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
            return output.decode()
        except subprocess.CalledProcessError as e:
            logger.warning(f"Command failed: {cmd}\nError output: {e.output.decode()}")
            return None

    def _extract_events_from_describe(self, describe_output: str, metadata: dict) -> None:
        """
        Parses the lines under the "Events:" section in 'kubectl describe' output,
        storing them in metadata["events"].
        """
        lines = describe_output.splitlines()
        in_events = False
        for line in lines:
            line_stripped = line.strip()
            # Detect the "Events:" heading
            if line_stripped.startswith("Events:"):
                in_events = True
                continue

            if in_events:
                # If blank line or next heading, events section ended
                if not line_stripped or line_stripped.endswith(":"):
                    in_events = False
                else:
                    metadata["events"].append(line_stripped)

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

    def is_pod_failing(self, namespace, pod_name):
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
