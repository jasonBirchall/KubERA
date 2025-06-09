"""
ReAct Hypothesis System for Kubernetes Troubleshooting

This module defines the hypothesis structure and scoring system used by the ReAct agent
to iteratively diagnose Kubernetes pod failures.
"""

import json
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class HypothesisType(Enum):
    """Types of Kubernetes issues that can be diagnosed"""
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    IMAGE_REGISTRY_ISSUES = "image_registry_issues"
    CONFIGURATION_ERRORS = "configuration_errors"
    NETWORK_CONNECTIVITY = "network_connectivity"
    SECURITY_PERMISSIONS = "security_permissions"
    LIVENESS_READINESS = "liveness_readiness"
    SCHEDULING_ISSUES = "scheduling_issues"


@dataclass
class Hypothesis:
    """Represents a diagnostic hypothesis with confidence scoring"""
    id: str
    type: HypothesisType
    description: str
    confidence: float  # 0.0 to 10.0
    evidence_for: List[str]
    evidence_against: List[str]
    needed_data: List[str]
    kubectl_commands: List[str]
    severity_score: float  # Impact if this hypothesis is correct
    ease_of_validation: float  # How easy it is to test this hypothesis
    priority_score: float = 0.0  # Calculated dynamically
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert hypothesis to dictionary for JSON serialization"""
        result = asdict(self)
        result['type'] = self.type.value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Hypothesis':
        """Create hypothesis from dictionary"""
        data['type'] = HypothesisType(data['type'])
        return cls(**data)


class KubernetesHypotheses:
    """Knowledge base of Kubernetes failure patterns and diagnostic strategies"""
    
    HYPOTHESIS_PATTERNS = {
        HypothesisType.RESOURCE_EXHAUSTION: {
            "indicators": [
                "oomkilled", "evicted", "resource_pressure", "memory", "cpu",
                "diskpressure", "pidpressure", "limits", "requests"
            ],
            "kubectl_commands": [
                "kubectl top pod {pod_name} -n {namespace}",
                "kubectl top node",
                "kubectl describe pod {pod_name} -n {namespace} | grep -A10 'Limits:'",
                "kubectl get events -n {namespace} --field-selector involvedObject.name={pod_name}",
                "kubectl describe node {node_name}",
                "kubectl get hpa -n {namespace}"
            ],
            "severity_base": 8.5,
            "validation_ease": 7.0
        },
        
        HypothesisType.IMAGE_REGISTRY_ISSUES: {
            "indicators": [
                "errimagepull", "imagepullbackoff", "authentication", "registry",
                "pull", "image", "unauthorized", "forbidden", "not found"
            ],
            "kubectl_commands": [
                "kubectl describe pod {pod_name} -n {namespace} | grep -A10 'Events:'",
                "kubectl get pods {pod_name} -n {namespace} -o jsonpath='{{.spec.containers[*].image}}'",
                "kubectl get secrets -n {namespace}",
                "kubectl get pod {pod_name} -n {namespace} -o yaml | grep -A5 -B5 imagePullSecrets",
                "kubectl describe pod {pod_name} -n {namespace} | grep -A5 'Failed to pull image'"
            ],
            "severity_base": 6.0,
            "validation_ease": 8.5
        },
        
        HypothesisType.CONFIGURATION_ERRORS: {
            "indicators": [
                "createcontainerconfigerror", "invalidimagename", "configmap",
                "secret", "environment", "volume", "mount", "config"
            ],
            "kubectl_commands": [
                "kubectl get pod {pod_name} -n {namespace} -o yaml",
                "kubectl get configmaps -n {namespace}",
                "kubectl get secrets -n {namespace}",
                "kubectl describe pod {pod_name} -n {namespace} | grep -A20 'Environment:'",
                "kubectl describe pod {pod_name} -n {namespace} | grep -A10 'Mounts:'"
            ],
            "severity_base": 7.0,
            "validation_ease": 6.5
        },
        
        HypothesisType.NETWORK_CONNECTIVITY: {
            "indicators": [
                "network", "connectivity", "dns", "service", "endpoint",
                "timeout", "connection refused", "unreachable"
            ],
            "kubectl_commands": [
                "kubectl get svc -n {namespace}",
                "kubectl get endpoints -n {namespace}",
                "kubectl get networkpolicies -n {namespace}",
                "kubectl describe svc -n {namespace}",
                "kubectl get pod {pod_name} -n {namespace} -o wide"
            ],
            "severity_base": 7.5,
            "validation_ease": 5.0
        },
        
        HypothesisType.SECURITY_PERMISSIONS: {
            "indicators": [
                "forbidden", "unauthorized", "rbac", "serviceaccount",
                "permission", "access denied", "security", "policy"
            ],
            "kubectl_commands": [
                "kubectl get serviceaccounts -n {namespace}",
                "kubectl get rolebindings -n {namespace}",
                "kubectl get clusterrolebindings",
                "kubectl describe pod {pod_name} -n {namespace} | grep serviceAccount",
                "kubectl auth can-i --list --as=system:serviceaccount:{namespace}:default"
            ],
            "severity_base": 8.0,
            "validation_ease": 4.0
        },
        
        HypothesisType.LIVENESS_READINESS: {
            "indicators": [
                "liveness", "readiness", "probe", "health", "healthcheck",
                "startup", "failed", "unhealthy"
            ],
            "kubectl_commands": [
                "kubectl describe pod {pod_name} -n {namespace} | grep -A10 'Liveness:'",
                "kubectl describe pod {pod_name} -n {namespace} | grep -A10 'Readiness:'",
                "kubectl get pod {pod_name} -n {namespace} -o yaml | grep -A20 livenessProbe",
                "kubectl get events -n {namespace} --field-selector involvedObject.name={pod_name}"
            ],
            "severity_base": 6.5,
            "validation_ease": 7.5
        },
        
        HypothesisType.SCHEDULING_ISSUES: {
            "indicators": [
                "unschedulable", "scheduling", "node", "affinity", "taint",
                "toleration", "resource", "insufficient", "pending"
            ],
            "kubectl_commands": [
                "kubectl describe pod {pod_name} -n {namespace} | grep -A10 'Events:'",
                "kubectl get nodes -o wide",
                "kubectl describe nodes",
                "kubectl get pod {pod_name} -n {namespace} -o yaml | grep -A10 nodeSelector",
                "kubectl get pod {pod_name} -n {namespace} -o yaml | grep -A10 affinity"
            ],
            "severity_base": 7.0,
            "validation_ease": 6.0
        }
    }
    
    @classmethod
    def generate_initial_hypotheses(cls, metadata: Dict[str, Any]) -> List[Hypothesis]:
        """Generate initial hypotheses based on pod metadata"""
        hypotheses = []
        
        # Extract text content for analysis
        text_content = cls._extract_text_content(metadata)
        
        for hypothesis_type, pattern in cls.HYPOTHESIS_PATTERNS.items():
            # Calculate initial confidence based on indicator matching
            confidence = cls._calculate_initial_confidence(text_content, pattern["indicators"])
            
            if confidence > 2.0:  # Only include hypotheses with some initial evidence
                hypothesis = Hypothesis(
                    id=f"hyp_{hypothesis_type.value}_{len(hypotheses)}",
                    type=hypothesis_type,
                    description=cls._generate_description(hypothesis_type, metadata),
                    confidence=confidence,
                    evidence_for=[],
                    evidence_against=[],
                    needed_data=cls._get_needed_data(hypothesis_type),
                    kubectl_commands=cls._format_kubectl_commands(
                        pattern["kubectl_commands"], metadata
                    ),
                    severity_score=pattern["severity_base"],
                    ease_of_validation=pattern["validation_ease"]
                )
                hypotheses.append(hypothesis)
        
        # Sort by initial confidence
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses[:4]  # Return top 4 hypotheses
    
    @classmethod
    def _extract_text_content(cls, metadata: Dict[str, Any]) -> str:
        """Extract all text content from metadata for analysis"""
        content_parts = []
        
        # Add various metadata fields
        for key, value in metadata.items():
            if isinstance(value, str):
                content_parts.append(value)
            elif isinstance(value, list):
                content_parts.extend([str(item) for item in value if item])
            elif isinstance(value, dict):
                content_parts.extend([str(v) for v in value.values() if v])
        
        return " ".join(content_parts).lower()
    
    @classmethod
    def _calculate_initial_confidence(cls, text_content: str, indicators: List[str]) -> float:
        """Calculate initial confidence based on indicator matching"""
        matches = sum(1 for indicator in indicators if indicator.lower() in text_content)
        max_confidence = 7.0  # Cap initial confidence
        return min(max_confidence, matches * 1.5 + 1.0)
    
    @classmethod
    def _generate_description(cls, hypothesis_type: HypothesisType, metadata: Dict[str, Any]) -> str:
        """Generate human-readable description for hypothesis"""
        pod_name = metadata.get('pod_name', 'pod')
        namespace = metadata.get('namespace', 'namespace')
        
        descriptions = {
            HypothesisType.RESOURCE_EXHAUSTION: f"Pod {pod_name} is failing due to resource constraints (CPU/Memory/Storage)",
            HypothesisType.IMAGE_REGISTRY_ISSUES: f"Pod {pod_name} cannot pull required container images from registry",
            HypothesisType.CONFIGURATION_ERRORS: f"Pod {pod_name} has configuration issues with ConfigMaps, Secrets, or environment variables",
            HypothesisType.NETWORK_CONNECTIVITY: f"Pod {pod_name} is experiencing network connectivity or DNS resolution issues",
            HypothesisType.SECURITY_PERMISSIONS: f"Pod {pod_name} lacks necessary RBAC permissions or security policies are blocking it",
            HypothesisType.LIVENESS_READINESS: f"Pod {pod_name} is failing liveness or readiness probe health checks",
            HypothesisType.SCHEDULING_ISSUES: f"Pod {pod_name} cannot be scheduled due to node constraints or resource availability"
        }
        
        return descriptions.get(hypothesis_type, f"Unknown issue with pod {pod_name}")
    
    @classmethod
    def _get_needed_data(cls, hypothesis_type: HypothesisType) -> List[str]:
        """Get list of data needed to validate this hypothesis"""
        needed_data_map = {
            HypothesisType.RESOURCE_EXHAUSTION: [
                "Current resource usage", "Resource limits and requests", 
                "Node capacity", "Resource-related events"
            ],
            HypothesisType.IMAGE_REGISTRY_ISSUES: [
                "Image pull events", "Registry authentication", 
                "Image availability", "Pull secrets configuration"
            ],
            HypothesisType.CONFIGURATION_ERRORS: [
                "ConfigMap contents", "Secret availability", 
                "Environment variables", "Volume mounts"
            ],
            HypothesisType.NETWORK_CONNECTIVITY: [
                "Service endpoints", "Network policies", 
                "DNS resolution", "Pod networking configuration"
            ],
            HypothesisType.SECURITY_PERMISSIONS: [
                "ServiceAccount configuration", "RBAC bindings", 
                "Security policies", "Permission validation"
            ],
            HypothesisType.LIVENESS_READINESS: [
                "Probe configuration", "Health check results", 
                "Probe failure events", "Application startup logs"
            ],
            HypothesisType.SCHEDULING_ISSUES: [
                "Node availability", "Resource requirements", 
                "Node selectors and affinity", "Taints and tolerations"
            ]
        }
        
        return needed_data_map.get(hypothesis_type, ["Additional pod information"])
    
    @classmethod
    def _format_kubectl_commands(cls, commands: List[str], metadata: Dict[str, Any]) -> List[str]:
        """Format kubectl commands with actual values from metadata"""
        formatted_commands = []
        
        pod_name = metadata.get('pod_name', 'unknown-pod')
        namespace = metadata.get('namespace', 'default')
        
        # Try to extract node name from metadata if available
        node_name = "unknown-node"
        if 'raw_describe' in metadata:
            import re
            node_match = re.search(r'Node:\s+(\S+)', metadata['raw_describe'])
            if node_match:
                node_name = node_match.group(1)
        
        for command in commands:
            try:
                formatted_cmd = command.format(
                    pod_name=pod_name,
                    namespace=namespace,
                    node_name=node_name
                )
                formatted_commands.append(formatted_cmd)
            except (KeyError, ValueError) as e:
                logger.warning(f"Could not format command '{command}': {e}")
                # Add command without formatting as fallback
                formatted_commands.append(command)
        
        return formatted_commands


class HypothesisScorer:
    """Handles confidence scoring and hypothesis refinement"""
    
    @staticmethod
    def update_confidence(hypothesis: Hypothesis, new_evidence: Dict[str, Any]) -> float:
        """Update hypothesis confidence based on new evidence"""
        confidence_adjustments = HypothesisScorer._get_confidence_adjustments()
        
        adjustment = 0.0
        evidence_found = []
        
        for evidence_type, evidence_data in new_evidence.items():
            if evidence_type in confidence_adjustments.get(hypothesis.type, {}):
                adjustments = confidence_adjustments[hypothesis.type][evidence_type]
                
                for evidence_pattern, adjustment_value in adjustments.items():
                    if HypothesisScorer._evidence_matches(evidence_data, evidence_pattern):
                        adjustment += adjustment_value
                        evidence_found.append(f"{evidence_type}: {evidence_pattern}")
        
        # Update hypothesis
        hypothesis.evidence_for.extend(evidence_found)
        hypothesis.confidence = max(0.0, min(10.0, hypothesis.confidence + adjustment))
        
        return hypothesis.confidence
    
    @staticmethod
    def _get_confidence_adjustments() -> Dict[HypothesisType, Dict[str, Dict[str, float]]]:
        """Define confidence adjustments for different evidence types"""
        return {
            HypothesisType.RESOURCE_EXHAUSTION: {
                "resource_usage": {
                    "memory_usage_high": +2.5,
                    "cpu_usage_high": +2.0,
                    "memory_usage_normal": -1.5,
                    "cpu_usage_normal": -1.0,
                },
                "events": {
                    "oom_events_found": +3.0,
                    "eviction_events_found": +3.0,
                    "resource_quota_exceeded": +2.5,
                    "no_resource_events": -2.0,
                },
                "limits": {
                    "no_resource_limits": +1.5,
                    "resource_limits_adequate": -1.0,
                }
            },
            
            HypothesisType.IMAGE_REGISTRY_ISSUES: {
                "events": {
                    "image_pull_errors_found": +3.5,
                    "authentication_errors": +3.0,
                    "registry_unreachable": +2.5,
                    "successful_image_pulls": -2.0,
                },
                "image_config": {
                    "invalid_image_name": +2.0,
                    "missing_pull_secrets": +2.5,
                    "valid_image_config": -1.5,
                }
            },
            
            HypothesisType.CONFIGURATION_ERRORS: {
                "config": {
                    "missing_configmap": +3.0,
                    "missing_secret": +3.0,
                    "invalid_environment_vars": +2.0,
                    "configuration_valid": -2.0,
                },
                "mounts": {
                    "volume_mount_errors": +2.5,
                    "successful_mounts": -1.5,
                }
            },
            
            HypothesisType.LIVENESS_READINESS: {
                "probes": {
                    "liveness_probe_failing": +3.0,
                    "readiness_probe_failing": +2.5,
                    "probe_configuration_invalid": +2.0,
                    "probes_passing": -2.5,
                },
                "health": {
                    "health_check_timeouts": +2.0,
                    "application_healthy": -2.0,
                }
            }
        }
    
    @staticmethod
    def _evidence_matches(evidence_data: Any, pattern: str) -> bool:
        """Check if evidence data matches a pattern"""
        if isinstance(evidence_data, str):
            return pattern.lower() in evidence_data.lower()
        elif isinstance(evidence_data, dict):
            return any(
                pattern.lower() in str(value).lower() 
                for value in evidence_data.values()
            )
        elif isinstance(evidence_data, list):
            return any(
                pattern.lower() in str(item).lower() 
                for item in evidence_data
            )
        return False
    
    @staticmethod
    def prioritize_hypotheses(hypotheses: List[Hypothesis]) -> List[Hypothesis]:
        """Calculate priority scores and sort hypotheses"""
        for hypothesis in hypotheses:
            # Priority factors
            confidence_factor = hypothesis.confidence * 0.4
            severity_factor = hypothesis.severity_score * 0.3
            ease_factor = hypothesis.ease_of_validation * 0.2
            uncertainty_factor = (10 - hypothesis.confidence) * 0.1  # Investigate uncertain ones
            
            hypothesis.priority_score = (
                confidence_factor + severity_factor + 
                ease_factor + uncertainty_factor
            )
        
        return sorted(hypotheses, key=lambda h: h.priority_score, reverse=True)