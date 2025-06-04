import json

from openai import OpenAI


class LlmAgent:
    def __init__(self, model="gpt-4"):
        self.client = OpenAI()
        self.model = model

    def diagnose_argocd_app(self, metadata: dict):
        """
        Given a dictionary 'metadata' which contains ArgoCD application info:
        - "app_name": The name of the application
        - "status": The application status including health, sync info, etc.
        - "events": Recent events for the application

        Returns a diagnosis of any issues with the ArgoCD application.
        """
        # Prepare a system prompt for ArgoCD application analysis
        system_prompt = (
            "You are an AI diagnosing ArgoCD application issues. We have metadata fields:\n"
            "- 'app_name': Name of the ArgoCD application.\n"
            "- 'status': Status information including:\n"
            "   - 'health': Health status (Healthy, Degraded, Progressing, Unknown).\n"
            "   - 'sync': Sync status (Synced, OutOfSync, Unknown).\n"
            "   - 'operationState': Details about the last sync operation.\n"
            "- 'events': List of recent events with fields:\n"
            "   - 'type': Normal or Warning.\n"
            "   - 'reason': Short reason for the event.\n"
            "   - 'message': Detailed message.\n"
            "   - 'lastTimestamp': When the event occurred.\n"
            "\n"
            "Common issues include:\n"
            "- Out of sync: The desired state doesn't match the actual state.\n"
            "- Degraded health: The application is running but not functioning properly.\n"
            "- Failed sync: The sync operation encountered errors.\n"
            "- Resource errors: Kubernetes resources failed to deploy.\n"
            "\n"
            "Use these clues to determine root causes and propose fixes.\n"
            "Format your response with 'Root Cause:' followed by bullet points, then 'Recommended Actions:' with steps to resolve.\n"
        )

        # Convert metadata to JSON for clarity
        metadata_json = json.dumps(metadata, indent=2)

        # Prepare a user prompt asking for diagnosis
        user_prompt = (
            "Based on the ArgoCD application metadata provided, please diagnose any issues "
            "and recommend actions to resolve them. If everything is fine, say so."
        )

        # Build the conversation
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "assistant",
                "content": f"Here is the ArgoCD application metadata:\n{metadata_json}"
            },
            {"role": "user", "content": user_prompt}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content

    def diagnose_pod_failure(self, metadata: dict):
        """
        Diagnose Kubernetes pod failures using metadata from k8s_tool.gather_metadata().
        
        Expected metadata structure:
        {
            "namespace": str,
            "pod_name": str,
            "raw_describe": str,   # Full kubectl describe pod output
            "events": [str, ...],  # Extracted event lines from kubectl describe
            "containers": [        # Container status info from kubectl get pod -o json
                {
                    "name": str,
                    "image": str,
                    "waitingReason": str,      # e.g., "CrashLoopBackOff", "ErrImagePull"
                    "terminatedReason": str    # e.g., "OOMKilled", "Error"
                }, ...
            ]
        }
        
        Returns a structured diagnosis with root cause analysis and recommendations.
        """
        system_prompt = (
            "You are a Kubernetes expert diagnosing pod failures. You will receive metadata about a failing pod including:\n"
            "\n"
            "- 'namespace' & 'pod_name': Basic pod identification\n"
            "- 'raw_describe': Complete output from 'kubectl describe pod' command\n"
            "- 'events': Extracted event messages showing warnings/errors from the Events section\n"
            "- 'containers': Array of container status information with:\n"
            "    - 'name': Container name\n"
            "    - 'image': Docker image being used\n"
            "    - 'waitingReason': Why container is waiting (CrashLoopBackOff, ErrImagePull, ImagePullBackOff, etc.)\n"
            "    - 'terminatedReason': Why container terminated (OOMKilled, Error, etc.)\n"
            "\n"
            "Common Kubernetes failure patterns:\n"
            "- CrashLoopBackOff: Container keeps crashing, usually due to application errors, missing dependencies, or configuration issues\n"
            "- ErrImagePull/ImagePullBackOff: Cannot pull the specified Docker image (wrong tag, private registry, network issues)\n"
            "- OOMKilled: Container exceeded memory limits and was killed by the kernel\n"
            "- FailedScheduling: Pod cannot be scheduled due to resource constraints or node affinity issues\n"
            "- Liveness/Readiness probe failures: Health checks are failing\n"
            "\n"
            "Analyze the provided data and respond in this format:\n"
            "=== ROOT CAUSE ANALYSIS ===\n"
            "[Detailed explanation of what's wrong]\n"
            "\n"
            "=== RECOMMENDED ACTIONS ===\n"
            "1. [Immediate action]\n"
            "2. [Follow-up action]\n"
            "3. [Prevention measures]\n"
            "\n"
            "=== KUBECTL COMMANDS TO RUN ===\n"
            "[Specific kubectl commands for debugging/fixing]\n"
            "\n"
            "Be specific and actionable. Focus on the most likely cause based on the container states and events."
        )

        metadata_json = json.dumps(metadata, indent=2)

        user_prompt = (
            "Analyze this Kubernetes pod failure and provide a comprehensive diagnosis. "
            "Focus on the container states (waitingReason, terminatedReason) and events to determine "
            "the root cause. Provide specific, actionable recommendations."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "assistant", 
                "content": f"Here is the pod failure metadata:\n```json\n{metadata_json}\n```"
            },
            {"role": "user", "content": user_prompt}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,  # Lower temperature for more consistent technical analysis
        )
        return response.choices[0].message.content

    def diagnose_pod(self, metadata: dict):
        """
        Legacy method - redirects to diagnose_pod_failure for backwards compatibility
        """
        return self.diagnose_pod_failure(metadata)

    def generate_text(self, prompt, system_message=None):
        """
        Generate text using the LLM in response to a prompt.

        Args:
            prompt (str): The prompt to send to the LLM
            system_message (str, optional): A system message to guide the LLM's response

        Returns:
            str: The generated text response
        """
        if not system_message:
            system_message = "You are a helpful AI assistant with expertise in Kubernetes, cloud infrastructure, and DevOps."

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
        )

        return response.choices[0].message.content
