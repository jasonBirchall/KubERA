import json
import logging
import asyncio
from typing import Dict, Any

from openai import OpenAI
from .data_anonymizer import DataAnonymizer
from .react_agent import ReActAgent

logger = logging.getLogger(__name__)


class LlmAgent:
    def __init__(self, model="gpt-4", enable_anonymization=True, enable_react=False):
        self.client = OpenAI()
        self.model = model
        self.enable_anonymization = enable_anonymization
        self.enable_react = enable_react
        self.anonymizer = DataAnonymizer() if enable_anonymization else None
        
        # Initialize ReAct agent if enabled
        self.react_agent = None
        if enable_react:
            self.react_agent = ReActAgent(
                llm_client=self.client,
                max_iterations=3,
                confidence_threshold=8.0,
                enable_anonymization=enable_anonymization
            )

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
        
        Uses ReAct (Reasoning + Acting) loop if enabled, otherwise falls back to 
        traditional single-shot diagnosis.
        
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
        if self.enable_react and self.react_agent:
            return self._diagnose_with_react(metadata)
        else:
            return self._diagnose_traditional(metadata)
    
    def _diagnose_with_react(self, metadata: dict):
        """Diagnose using ReAct iterative reasoning and acting"""
        logger.info("Using ReAct agent for pod diagnosis")
        
        try:
            # Run ReAct diagnosis asynchronously
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an event loop, create a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.react_agent.diagnose(metadata))
                    result = future.result(timeout=120)  # 2 minute timeout
            else:
                # Run directly if no event loop is running
                result = asyncio.run(self.react_agent.diagnose(metadata))
            
            # Format ReAct result for traditional interface compatibility
            return self._format_react_result(result)
            
        except Exception as e:
            logger.error(f"ReAct diagnosis failed, falling back to traditional: {str(e)}")
            return self._diagnose_traditional(metadata)
    
    def _format_react_result(self, react_result):
        """Format ReAct result to match traditional diagnosis format"""
        output_parts = []
        
        # Add reasoning trace
        output_parts.append("=== REACT DIAGNOSIS TRACE ===")
        for trace_item in react_result.reasoning_trace:
            output_parts.append(trace_item)
        
        # Add main diagnosis
        output_parts.append(f"\n{react_result.final_diagnosis}")
        
        # Add kubectl commands
        if react_result.kubectl_commands_used:
            output_parts.append("\n=== KUBECTL COMMANDS EXECUTED ===")
            for cmd in react_result.kubectl_commands_used:
                output_parts.append(f"$ {cmd}")
        
        # Add performance metrics
        output_parts.append(f"\n=== REACT PERFORMANCE ===")
        output_parts.append(f"Iterations: {len(react_result.iterations)}")
        output_parts.append(f"Commands executed: {react_result.total_commands_executed}")
        output_parts.append(f"Total time: {react_result.total_execution_time:.2f}s")
        output_parts.append(f"Final confidence: {react_result.confidence_score:.1f}/10.0")
        
        # Add anonymization notice if applicable
        if self.enable_anonymization:
            output_parts.append(f"\n=== PRIVACY NOTICE ===")
            output_parts.append("Data was anonymized before AI analysis and restored in this response.")
        
        return "\n".join(output_parts)
    
    def _diagnose_traditional(self, metadata: dict):
        """Traditional single-shot diagnosis method"""
        # Handle anonymization if enabled
        session_map = {}
        processed_metadata = metadata
        anonymization_info = ""
        
        if self.enable_anonymization and self.anonymizer:
            processed_metadata, session_map = self.anonymizer.anonymize_data(metadata)
            anonymization_info = self.anonymizer.get_anonymization_summary(session_map)
            logger.info(f"Anonymized data for OpenAI API call: {len(session_map)} items")
        
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

        metadata_json = json.dumps(processed_metadata, indent=2)

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
        
        ai_response = response.choices[0].message.content
        
        # Deanonymize the response if anonymization was used
        if self.enable_anonymization and self.anonymizer and session_map:
            ai_response = self.anonymizer.deanonymize_response(ai_response, session_map)
            
            # Add anonymization notice to the response
            ai_response += f"\n\n=== PRIVACY NOTICE ===\n{anonymization_info}"
        
        return ai_response

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

        # Handle anonymization if enabled
        session_map = {}
        processed_prompt = prompt
        
        if self.enable_anonymization and self.anonymizer:
            # For simple text prompts, we need to wrap it in a dict for anonymization
            prompt_data = {"content": prompt}
            processed_data, session_map = self.anonymizer.anonymize_data(prompt_data)
            processed_prompt = processed_data.get("content", prompt)
            logger.info(f"Anonymized text prompt: {len(session_map)} items")

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": processed_prompt}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
        )

        ai_response = response.choices[0].message.content
        
        # Deanonymize the response if anonymization was used
        if self.enable_anonymization and self.anonymizer and session_map:
            ai_response = self.anonymizer.deanonymize_response(ai_response, session_map)

        return ai_response
    
    def preview_anonymization(self, metadata: dict) -> dict:
        """
        Preview what data would be anonymized without sending to OpenAI.
        
        Args:
            metadata: The data that would be sent to OpenAI
            
        Returns:
            Dictionary containing:
            - 'anonymized_data': The data after anonymization
            - 'mapping': The anonymization mapping
            - 'summary': Human-readable summary
        """
        if not self.enable_anonymization or not self.anonymizer:
            return {
                'anonymized_data': metadata,
                'mapping': {},
                'summary': 'Anonymization is disabled'
            }
        
        # Create a temporary anonymizer to avoid affecting the main one
        temp_anonymizer = DataAnonymizer()
        anonymized_data, session_map = temp_anonymizer.anonymize_data(metadata)
        summary = temp_anonymizer.get_anonymization_summary(session_map)
        
        return {
            'anonymized_data': anonymized_data,
            'mapping': session_map,
            'summary': summary
        }
    
    def set_anonymization(self, enabled: bool):
        """
        Enable or disable anonymization.
        
        Args:
            enabled: Whether to enable anonymization
        """
        self.enable_anonymization = enabled
        if enabled and not self.anonymizer:
            self.anonymizer = DataAnonymizer()
        elif not enabled:
            self.anonymizer = None
        
        # Update ReAct agent anonymization setting if it exists
        if self.react_agent:
            self.react_agent.enable_anonymization = enabled
            if enabled and not self.react_agent.anonymizer:
                self.react_agent.anonymizer = DataAnonymizer()
            elif not enabled:
                self.react_agent.anonymizer = None
    
    def set_react_mode(self, enabled: bool, **react_config):
        """
        Enable or disable ReAct mode.
        
        Args:
            enabled: Whether to enable ReAct mode
            **react_config: Additional ReAct configuration options
                - max_iterations: Maximum ReAct iterations (default: 3)
                - confidence_threshold: Stop when hypothesis reaches this confidence (default: 8.0)
                - command_timeout: Timeout for kubectl commands (default: 30)
        """
        self.enable_react = enabled
        
        if enabled:
            if not self.react_agent:
                self.react_agent = ReActAgent(
                    llm_client=self.client,
                    max_iterations=react_config.get('max_iterations', 3),
                    confidence_threshold=react_config.get('confidence_threshold', 8.0),
                    enable_anonymization=self.enable_anonymization,
                    command_timeout=react_config.get('command_timeout', 30)
                )
                logger.info("ReAct mode enabled")
            else:
                # Update existing ReAct agent configuration
                self.react_agent.max_iterations = react_config.get('max_iterations', self.react_agent.max_iterations)
                self.react_agent.confidence_threshold = react_config.get('confidence_threshold', self.react_agent.confidence_threshold)
                self.react_agent.command_timeout = react_config.get('command_timeout', self.react_agent.command_timeout)
                logger.info("ReAct configuration updated")
        else:
            self.react_agent = None
            logger.info("ReAct mode disabled")
    
    def get_react_status(self) -> Dict[str, Any]:
        """
        Get current ReAct configuration status.
        
        Returns:
            Dictionary with ReAct status and configuration
        """
        if not self.enable_react or not self.react_agent:
            return {
                "enabled": False,
                "reason": "ReAct mode is disabled"
            }
        
        return {
            "enabled": True,
            "max_iterations": self.react_agent.max_iterations,
            "confidence_threshold": self.react_agent.confidence_threshold,
            "command_timeout": self.react_agent.command_timeout,
            "anonymization_enabled": self.react_agent.enable_anonymization
        }
