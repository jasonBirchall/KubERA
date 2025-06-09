"""
ReAct Information Gathering System

This module handles targeted kubectl command execution and data collection
based on specific hypotheses during the ReAct diagnostic process.
"""

import asyncio
import json
import logging
import subprocess
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from .react_hypothesis import Hypothesis, HypothesisType

logger = logging.getLogger(__name__)


@dataclass
class GatheringResult:
    """Result of information gathering operation"""
    command: str
    success: bool
    output: str
    error: str
    execution_time: float
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time": self.execution_time,
            "timestamp": self.timestamp.isoformat()
        }


class InformationGatherer:
    """Executes targeted kubectl commands to gather specific evidence"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.gathered_data = {}  # Cache to avoid re-gathering same data
    
    async def gather_for_hypothesis(self, hypothesis: Hypothesis, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Gather targeted information for a specific hypothesis"""
        logger.info(f"Gathering information for hypothesis: {hypothesis.type.value}")
        
        # Get commands for this hypothesis
        commands = hypothesis.kubectl_commands
        
        # Execute commands concurrently
        tasks = []
        for command in commands[:3]:  # Limit to 3 commands per iteration for performance
            if command not in self.gathered_data:  # Avoid re-executing same commands
                tasks.append(self._execute_kubectl_command(command))
        
        if not tasks:
            logger.info("All commands already executed, using cached data")
            return self._analyze_cached_data(hypothesis, metadata)
        
        # Execute commands
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        gathered_evidence = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Command failed: {result}")
                continue
            
            if isinstance(result, GatheringResult):
                command = commands[i] if i < len(commands) else f"command_{i}"
                self.gathered_data[command] = result
                gathered_evidence[command] = result
        
        # Analyze gathered data for this hypothesis
        return self._analyze_gathered_data(hypothesis, gathered_evidence, metadata)
    
    async def _execute_kubectl_command(self, command: str) -> GatheringResult:
        """Execute a single kubectl command asynchronously"""
        start_time = datetime.now()
        
        try:
            # Use asyncio subprocess for non-blocking execution
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=self.timeout
            )
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return GatheringResult(
                command=command,
                success=process.returncode == 0,
                output=stdout.decode('utf-8', errors='ignore'),
                error=stderr.decode('utf-8', errors='ignore'),
                execution_time=execution_time,
                timestamp=datetime.now()
            )
            
        except asyncio.TimeoutError:
            execution_time = (datetime.now() - start_time).total_seconds()
            return GatheringResult(
                command=command,
                success=False,
                output="",
                error=f"Command timed out after {self.timeout} seconds",
                execution_time=execution_time,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            return GatheringResult(
                command=command,
                success=False,
                output="",
                error=f"Command execution failed: {str(e)}",
                execution_time=execution_time,
                timestamp=datetime.now()
            )
    
    def _analyze_gathered_data(self, hypothesis: Hypothesis, evidence: Dict[str, GatheringResult], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze gathered evidence for a specific hypothesis"""
        analysis = {
            "hypothesis_type": hypothesis.type.value,
            "evidence_summary": {},
            "findings": [],
            "confidence_factors": {}
        }
        
        # Dispatch to hypothesis-specific analyzers
        if hypothesis.type == HypothesisType.RESOURCE_EXHAUSTION:
            analysis.update(self._analyze_resource_evidence(evidence, metadata))
        elif hypothesis.type == HypothesisType.IMAGE_REGISTRY_ISSUES:
            analysis.update(self._analyze_image_evidence(evidence, metadata))
        elif hypothesis.type == HypothesisType.CONFIGURATION_ERRORS:
            analysis.update(self._analyze_config_evidence(evidence, metadata))
        elif hypothesis.type == HypothesisType.LIVENESS_READINESS:
            analysis.update(self._analyze_health_evidence(evidence, metadata))
        elif hypothesis.type == HypothesisType.NETWORK_CONNECTIVITY:
            analysis.update(self._analyze_network_evidence(evidence, metadata))
        elif hypothesis.type == HypothesisType.SECURITY_PERMISSIONS:
            analysis.update(self._analyze_security_evidence(evidence, metadata))
        elif hypothesis.type == HypothesisType.SCHEDULING_ISSUES:
            analysis.update(self._analyze_scheduling_evidence(evidence, metadata))
        
        return analysis
    
    def _analyze_resource_evidence(self, evidence: Dict[str, GatheringResult], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze evidence for resource exhaustion hypothesis"""
        findings = []
        confidence_factors = {}
        
        for command, result in evidence.items():
            if not result.success:
                continue
                
            output = result.output.lower()
            
            # Analyze kubectl top pod output
            if "kubectl top pod" in command:
                memory_usage, cpu_usage = self._parse_resource_usage(result.output)
                if memory_usage > 80:
                    findings.append("High memory usage detected")
                    confidence_factors["memory_usage_high"] = True
                elif memory_usage < 20:
                    confidence_factors["memory_usage_normal"] = True
                
                if cpu_usage > 80:
                    findings.append("High CPU usage detected")
                    confidence_factors["cpu_usage_high"] = True
                elif cpu_usage < 20:
                    confidence_factors["cpu_usage_normal"] = True
            
            # Analyze events for OOM kills
            elif "get events" in command:
                if "oomkilled" in output or "out of memory" in output:
                    findings.append("OOM kill events found")
                    confidence_factors["oom_events_found"] = True
                elif "evicted" in output:
                    findings.append("Pod eviction events found")
                    confidence_factors["eviction_events_found"] = True
                else:
                    confidence_factors["no_resource_events"] = True
            
            # Analyze resource limits
            elif "limits:" in output or "requests:" in output:
                if "limits:" not in output and "requests:" not in output:
                    findings.append("No resource limits configured")
                    confidence_factors["no_resource_limits"] = True
                else:
                    confidence_factors["resource_limits_adequate"] = True
        
        return {
            "resource_analysis": {
                "findings": findings,
                "confidence_factors": confidence_factors
            }
        }
    
    def _analyze_image_evidence(self, evidence: Dict[str, GatheringResult], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze evidence for image registry issues"""
        findings = []
        confidence_factors = {}
        
        for command, result in evidence.items():
            if not result.success:
                continue
                
            output = result.output.lower()
            
            # Check for image pull errors in events
            if "get events" in command or "describe pod" in command:
                if any(error in output for error in ["errimagepull", "imagepullbackoff", "failed to pull"]):
                    findings.append("Image pull errors found in events")
                    confidence_factors["image_pull_errors_found"] = True
                
                if "authentication required" in output or "unauthorized" in output:
                    findings.append("Authentication errors detected")
                    confidence_factors["authentication_errors"] = True
                
                if "network is unreachable" in output or "no route to host" in output:
                    findings.append("Registry unreachable")
                    confidence_factors["registry_unreachable"] = True
                
                if "successfully pulled" in output:
                    confidence_factors["successful_image_pulls"] = True
            
            # Check image configuration
            elif "jsonpath" in command or "grep -A5 -B5 image" in command:
                # Look for malformed image names
                if result.output and self._is_invalid_image_name(result.output):
                    findings.append("Invalid image name detected")
                    confidence_factors["invalid_image_name"] = True
                else:
                    confidence_factors["valid_image_config"] = True
            
            # Check pull secrets
            elif "get secrets" in command:
                if not result.output.strip():
                    findings.append("No pull secrets configured")
                    confidence_factors["missing_pull_secrets"] = True
        
        return {
            "image_analysis": {
                "findings": findings,
                "confidence_factors": confidence_factors
            }
        }
    
    def _analyze_config_evidence(self, evidence: Dict[str, GatheringResult], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze evidence for configuration errors"""
        findings = []
        confidence_factors = {}
        
        for command, result in evidence.items():
            if not result.success:
                continue
            
            # Check ConfigMaps
            if "get configmaps" in command:
                if not result.output.strip() or "No resources found" in result.output:
                    findings.append("No ConfigMaps found in namespace")
                    confidence_factors["missing_configmap"] = True
            
            # Check Secrets
            elif "get secrets" in command:
                if not result.output.strip() or "No resources found" in result.output:
                    findings.append("No Secrets found in namespace")
                    confidence_factors["missing_secret"] = True
            
            # Check environment variables
            elif "environment:" in result.output.lower():
                env_section = self._extract_environment_section(result.output)
                if self._has_invalid_env_vars(env_section):
                    findings.append("Invalid environment variable configuration")
                    confidence_factors["invalid_environment_vars"] = True
                else:
                    confidence_factors["configuration_valid"] = True
            
            # Check volume mounts
            elif "mounts:" in result.output.lower():
                if "mountpath" in result.output.lower():
                    mount_errors = self._check_mount_errors(result.output)
                    if mount_errors:
                        findings.extend(mount_errors)
                        confidence_factors["volume_mount_errors"] = True
                    else:
                        confidence_factors["successful_mounts"] = True
        
        return {
            "config_analysis": {
                "findings": findings,
                "confidence_factors": confidence_factors
            }
        }
    
    def _analyze_health_evidence(self, evidence: Dict[str, GatheringResult], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze evidence for liveness/readiness probe issues"""
        findings = []
        confidence_factors = {}
        
        for command, result in evidence.items():
            if not result.success:
                continue
                
            output = result.output.lower()
            
            # Check probe configuration
            if "liveness:" in output or "livenessprobe" in output:
                if "failed" in output or "unhealthy" in output:
                    findings.append("Liveness probe failures detected")
                    confidence_factors["liveness_probe_failing"] = True
                elif "successful" in output or "healthy" in output:
                    confidence_factors["probes_passing"] = True
            
            if "readiness:" in output or "readinessprobe" in output:
                if "failed" in output or "unhealthy" in output:
                    findings.append("Readiness probe failures detected")
                    confidence_factors["readiness_probe_failing"] = True
                elif "successful" in output or "healthy" in output:
                    confidence_factors["probes_passing"] = True
            
            # Check for probe configuration issues
            if "probe" in output and ("invalid" in output or "malformed" in output):
                findings.append("Invalid probe configuration")
                confidence_factors["probe_configuration_invalid"] = True
            
            # Check events for health-related failures
            if "get events" in command:
                if "liveness probe failed" in output or "readiness probe failed" in output:
                    findings.append("Health check failures in events")
                    confidence_factors["health_check_timeouts"] = True
        
        return {
            "health_analysis": {
                "findings": findings,
                "confidence_factors": confidence_factors
            }
        }
    
    def _analyze_network_evidence(self, evidence: Dict[str, GatheringResult], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze evidence for network connectivity issues"""
        findings = []
        confidence_factors = {}
        
        # Network analysis implementation
        for command, result in evidence.items():
            if not result.success:
                continue
            
            # Check services and endpoints
            if "get svc" in command or "get endpoints" in command:
                if "No resources found" in result.output:
                    findings.append("No services found in namespace")
                    confidence_factors["no_services"] = True
            
            # Check network policies
            elif "get networkpolicies" in command:
                if result.output.strip() and "No resources found" not in result.output:
                    findings.append("Network policies present - may restrict traffic")
                    confidence_factors["network_policies_present"] = True
        
        return {
            "network_analysis": {
                "findings": findings,
                "confidence_factors": confidence_factors
            }
        }
    
    def _analyze_security_evidence(self, evidence: Dict[str, GatheringResult], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze evidence for security/permissions issues"""
        findings = []
        confidence_factors = {}
        
        # Security analysis implementation
        for command, result in evidence.items():
            if not result.success:
                continue
            
            # Check service accounts
            if "get serviceaccounts" in command:
                if "No resources found" in result.output:
                    findings.append("No service accounts configured")
                    confidence_factors["missing_service_account"] = True
            
            # Check RBAC
            elif "get rolebindings" in command or "get clusterrolebindings" in command:
                if "No resources found" in result.output:
                    findings.append("No RBAC bindings found")
                    confidence_factors["missing_rbac"] = True
        
        return {
            "security_analysis": {
                "findings": findings,
                "confidence_factors": confidence_factors
            }
        }
    
    def _analyze_scheduling_evidence(self, evidence: Dict[str, GatheringResult], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze evidence for scheduling issues"""
        findings = []
        confidence_factors = {}
        
        # Scheduling analysis implementation
        for command, result in evidence.items():
            if not result.success:
                continue
                
            output = result.output.lower()
            
            # Check node availability
            if "get nodes" in command:
                if "notready" in output or "schedulingdisabled" in output:
                    findings.append("Node scheduling issues detected")
                    confidence_factors["node_scheduling_issues"] = True
            
            # Check for scheduling events
            elif "get events" in command:
                if "failedscheduling" in output or "insufficient" in output:
                    findings.append("Scheduling failures in events")
                    confidence_factors["scheduling_failures"] = True
        
        return {
            "scheduling_analysis": {
                "findings": findings,
                "confidence_factors": confidence_factors
            }
        }
    
    def _analyze_cached_data(self, hypothesis: Hypothesis, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze previously cached data for hypothesis"""
        # Filter cached data relevant to this hypothesis
        relevant_data = {}
        for command, result in self.gathered_data.items():
            if any(cmd_part in command for cmd_part in hypothesis.kubectl_commands):
                relevant_data[command] = result
        
        if relevant_data:
            return self._analyze_gathered_data(hypothesis, relevant_data, metadata)
        
        return {
            "hypothesis_type": hypothesis.type.value,
            "evidence_summary": {"cached": "No relevant cached data"},
            "findings": [],
            "confidence_factors": {}
        }
    
    # Helper methods for parsing command outputs
    
    def _parse_resource_usage(self, output: str) -> Tuple[float, float]:
        """Parse memory and CPU usage from kubectl top output"""
        memory_percent = 0.0
        cpu_percent = 0.0
        
        lines = output.strip().split('\n')
        for line in lines[1:]:  # Skip header
            parts = line.split()
            if len(parts) >= 3:
                try:
                    # Try to extract percentages or convert units
                    cpu_str = parts[1]
                    memory_str = parts[2]
                    
                    # Simple percentage extraction (this could be enhanced)
                    if '%' in cpu_str:
                        cpu_percent = float(cpu_str.replace('%', ''))
                    if '%' in memory_str:
                        memory_percent = float(memory_str.replace('%', ''))
                        
                except (ValueError, IndexError):
                    continue
        
        return memory_percent, cpu_percent
    
    def _is_invalid_image_name(self, image_output: str) -> bool:
        """Check if image name appears malformed"""
        if not image_output.strip():
            return True
        
        # Basic validation - could be enhanced
        invalid_patterns = [
            r'[A-Z]',  # Uppercase letters (usually invalid)
            r'\s',     # Whitespace
            r'[^a-zA-Z0-9\-\.\/:]',  # Invalid characters
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, image_output):
                return True
        
        return False
    
    def _extract_environment_section(self, output: str) -> str:
        """Extract environment variables section from kubectl output"""
        lines = output.split('\n')
        env_section = []
        in_env_section = False
        
        for line in lines:
            if 'environment:' in line.lower():
                in_env_section = True
                continue
            elif in_env_section:
                if line.strip() and not line.startswith(' '):
                    break  # End of environment section
                env_section.append(line)
        
        return '\n'.join(env_section)
    
    def _has_invalid_env_vars(self, env_section: str) -> bool:
        """Check for invalid environment variable configurations"""
        # Look for common configuration errors
        invalid_indicators = [
            'error', 'invalid', 'missing', 'not found', 'failed'
        ]
        
        env_lower = env_section.lower()
        return any(indicator in env_lower for indicator in invalid_indicators)
    
    def _check_mount_errors(self, output: str) -> List[str]:
        """Check for volume mount errors"""
        errors = []
        output_lower = output.lower()
        
        error_patterns = [
            ('no such file or directory', 'Mount path does not exist'),
            ('permission denied', 'Volume mount permission issues'),
            ('read-only file system', 'Volume mounted as read-only'),
            ('device or resource busy', 'Volume mount conflicts'),
        ]
        
        for pattern, error_msg in error_patterns:
            if pattern in output_lower:
                errors.append(error_msg)
        
        return errors
    
    def clear_cache(self):
        """Clear gathered data cache"""
        self.gathered_data.clear()
        logger.info("Information gathering cache cleared")