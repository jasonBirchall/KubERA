import re
import json
import hashlib
from typing import Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class DataAnonymizer:
    """
    Anonymizes sensitive data before sending to OpenAI API and provides deanonymization
    capabilities to restore original values in responses.
    """
    
    def __init__(self):
        self.anonymization_map = {}
        self.reverse_map = {}
        self.counter = 1
    
    def anonymize_data(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Anonymize sensitive data in the input dictionary.
        
        Args:
            data: Dictionary containing potentially sensitive data
            
        Returns:
            Tuple of (anonymized_data, anonymization_mapping)
        """
        # Convert to JSON string for easier regex processing
        data_str = json.dumps(data, indent=2)
        
        # Store original mappings for this session
        session_map = {}
        
        # Anonymize different types of sensitive data
        data_str = self._anonymize_pod_names(data_str, session_map)
        data_str = self._anonymize_namespaces(data_str, session_map)
        data_str = self._anonymize_container_names(data_str, session_map)
        data_str = self._anonymize_image_names(data_str, session_map)
        data_str = self._anonymize_ip_addresses(data_str, session_map)
        data_str = self._anonymize_urls(data_str, session_map)
        data_str = self._anonymize_secrets_and_tokens(data_str, session_map)
        data_str = self._anonymize_file_paths(data_str, session_map)
        
        # Convert back to dictionary
        try:
            anonymized_data = json.loads(data_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse anonymized JSON, returning string in data field")
            anonymized_data = {"anonymized_content": data_str}
        
        return anonymized_data, session_map
    
    def deanonymize_response(self, response: str, session_map: Dict[str, str]) -> str:
        """
        Restore original values in the LLM response using the session mapping.
        
        Args:
            response: LLM response string containing anonymized tokens
            session_map: Mapping from anonymized tokens to original values
            
        Returns:
            Response with original values restored
        """
        deanonymized_response = response
        
        # Replace anonymized tokens with original values
        for anonymized_token, original_value in session_map.items():
            deanonymized_response = deanonymized_response.replace(anonymized_token, original_value)
        
        return deanonymized_response
    
    def _anonymize_pod_names(self, text: str, session_map: Dict[str, str]) -> str:
        """Anonymize Kubernetes pod names."""
        # Pattern for pod names (typically alphanumeric with hyphens and random suffixes)
        pod_pattern = r'\b([a-z0-9-]+)-[a-z0-9]{8,10}-[a-z0-9]{5}\b'
        
        def replace_pod(match):
            original = match.group(0)
            if original not in self.anonymization_map:
                anonymous_name = f"pod-{self.counter:03d}-{self._generate_suffix()}"
                self.anonymization_map[original] = anonymous_name
                self.reverse_map[anonymous_name] = original
                self.counter += 1
            
            session_map[self.anonymization_map[original]] = original
            return self.anonymization_map[original]
        
        return re.sub(pod_pattern, replace_pod, text)
    
    def _anonymize_namespaces(self, text: str, session_map: Dict[str, str]) -> str:
        """Anonymize Kubernetes namespaces."""
        # Common namespace patterns
        namespace_patterns = [
            r'\b(namespace["\s:]+)([a-z0-9-]+)',
            r'\b(-n\s+)([a-z0-9-]+)',
            r'\b(--namespace[=\s]+)([a-z0-9-]+)',
        ]
        
        def replace_namespace(match):
            prefix = match.group(1)
            original = match.group(2)
            
            # Skip common system namespaces
            if original in ['default', 'kube-system', 'kube-public', 'kube-node-lease']:
                return match.group(0)
            
            if original not in self.anonymization_map:
                anonymous_name = f"namespace-{self.counter:02d}"
                self.anonymization_map[original] = anonymous_name
                self.reverse_map[anonymous_name] = original
                self.counter += 1
            
            session_map[self.anonymization_map[original]] = original
            return prefix + self.anonymization_map[original]
        
        result = text
        for pattern in namespace_patterns:
            result = re.sub(pattern, replace_namespace, result)
        
        return result
    
    def _anonymize_container_names(self, text: str, session_map: Dict[str, str]) -> str:
        """Anonymize container names."""
        # Pattern for container names in describe output or JSON
        container_pattern = r'(container["\s:]+)([a-z0-9-]+)'
        
        def replace_container(match):
            prefix = match.group(1)
            original = match.group(2)
            
            if original not in self.anonymization_map:
                anonymous_name = f"container-{self.counter:02d}"
                self.anonymization_map[original] = anonymous_name
                self.reverse_map[anonymous_name] = original
                self.counter += 1
            
            session_map[self.anonymization_map[original]] = original
            return prefix + self.anonymization_map[original]
        
        return re.sub(container_pattern, replace_container, text, flags=re.IGNORECASE)
    
    def _anonymize_image_names(self, text: str, session_map: Dict[str, str]) -> str:
        """Anonymize Docker image names."""
        # Pattern for Docker images (registry/namespace/image:tag)
        image_patterns = [
            r'\b([a-z0-9.-]+/[a-z0-9.-]+/[a-z0-9.-]+:[a-z0-9.-]+)\b',  # full registry path
            r'\b([a-z0-9.-]+/[a-z0-9.-]+:[a-z0-9.-]+)\b',  # namespace/image:tag
            r'\b([a-z0-9.-]+:[a-z0-9.-]+)\b',  # image:tag
        ]
        
        def replace_image(match):
            original = match.group(1)
            
            # Skip common base images
            if any(base in original.lower() for base in ['nginx', 'alpine', 'ubuntu', 'redis', 'postgres']):
                return original
            
            if original not in self.anonymization_map:
                anonymous_name = f"registry.example.com/app-{self.counter:02d}:v1.0.0"
                self.anonymization_map[original] = anonymous_name
                self.reverse_map[anonymous_name] = original
                self.counter += 1
            
            session_map[self.anonymization_map[original]] = original
            return self.anonymization_map[original]
        
        result = text
        for pattern in image_patterns:
            result = re.sub(pattern, replace_image, result)
        
        return result
    
    def _anonymize_ip_addresses(self, text: str, session_map: Dict[str, str]) -> str:
        """Anonymize IP addresses."""
        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
        
        def replace_ip(match):
            original = match.group(0)
            
            # Skip common local/reserved IPs
            if original.startswith(('127.', '10.', '192.168.', '172.')):
                return original
            
            if original not in self.anonymization_map:
                anonymous_ip = f"10.0.{self.counter // 255}.{self.counter % 255}"
                self.anonymization_map[original] = anonymous_ip
                self.reverse_map[anonymous_ip] = original
                self.counter += 1
            
            session_map[self.anonymization_map[original]] = original
            return self.anonymization_map[original]
        
        return re.sub(ip_pattern, replace_ip, text)
    
    def _anonymize_urls(self, text: str, session_map: Dict[str, str]) -> str:
        """Anonymize URLs and domains."""
        url_pattern = r'https?://[a-zA-Z0-9.-]+(?:/[^\s]*)?'
        domain_pattern = r'\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
        
        def replace_url(match):
            original = match.group(0)
            
            if original not in self.anonymization_map:
                if original.startswith('http'):
                    anonymous_url = f"https://app-{self.counter:02d}.example.com/api"
                else:
                    anonymous_url = f"app-{self.counter:02d}.example.com"
                
                self.anonymization_map[original] = anonymous_url
                self.reverse_map[anonymous_url] = original
                self.counter += 1
            
            session_map[self.anonymization_map[original]] = original
            return self.anonymization_map[original]
        
        result = re.sub(url_pattern, replace_url, text)
        result = re.sub(domain_pattern, replace_url, result)
        
        return result
    
    def _anonymize_secrets_and_tokens(self, text: str, session_map: Dict[str, str]) -> str:
        """Anonymize potential secrets and tokens."""
        # Patterns for potential secrets
        secret_patterns = [
            r'\b[A-Za-z0-9+/]{20,}={0,2}\b',  # Base64-like strings
            r'\b[a-f0-9]{32,}\b',  # Hex strings (tokens, hashes)
            r'\btoken["\s:]+[A-Za-z0-9+/=]+',  # Explicit token fields
            r'\bsecret["\s:]+[A-Za-z0-9+/=]+',  # Explicit secret fields
        ]
        
        def replace_secret(match):
            original = match.group(0)
            
            # Skip very short strings
            if len(original) < 10:
                return original
            
            if original not in self.anonymization_map:
                anonymous_secret = f"***REDACTED-SECRET-{self.counter:02d}***"
                self.anonymization_map[original] = anonymous_secret
                self.reverse_map[anonymous_secret] = original
                self.counter += 1
            
            session_map[self.anonymization_map[original]] = original
            return self.anonymization_map[original]
        
        result = text
        for pattern in secret_patterns:
            result = re.sub(pattern, replace_secret, result, flags=re.IGNORECASE)
        
        return result
    
    def _anonymize_file_paths(self, text: str, session_map: Dict[str, str]) -> str:
        """Anonymize file paths that might contain sensitive information."""
        # Pattern for file paths
        path_pattern = r'(/[a-zA-Z0-9._-]+)+/?'
        
        def replace_path(match):
            original = match.group(0)
            
            # Skip common system paths
            if any(common in original for common in ['/usr/', '/bin/', '/etc/', '/var/log/', '/tmp/']):
                return original
            
            if original not in self.anonymization_map:
                anonymous_path = f"/app/data/file-{self.counter:02d}"
                self.anonymization_map[original] = anonymous_path
                self.reverse_map[anonymous_path] = original
                self.counter += 1
            
            session_map[self.anonymization_map[original]] = original
            return self.anonymization_map[original]
        
        return re.sub(path_pattern, replace_path, text)
    
    def _generate_suffix(self) -> str:
        """Generate a random-looking suffix for anonymized names."""
        import random
        import string
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
    
    def get_anonymization_summary(self, session_map: Dict[str, str]) -> str:
        """
        Generate a human-readable summary of what was anonymized.
        
        Args:
            session_map: The anonymization mapping for this session
            
        Returns:
            String summary of anonymized data
        """
        if not session_map:
            return "No sensitive data was anonymized in this request."
        
        summary_lines = ["The following data was anonymized before sending to AI:"]
        
        # Group by type
        pods = [k for k in session_map.keys() if k.startswith('pod-')]
        namespaces = [k for k in session_map.keys() if k.startswith('namespace-')]
        containers = [k for k in session_map.keys() if k.startswith('container-')]
        images = [k for k in session_map.keys() if 'registry.example.com' in k]
        secrets = [k for k in session_map.keys() if 'REDACTED-SECRET' in k]
        
        if pods:
            summary_lines.append(f"• {len(pods)} pod name(s)")
        if namespaces:
            summary_lines.append(f"• {len(namespaces)} namespace(s)")
        if containers:
            summary_lines.append(f"• {len(containers)} container name(s)")
        if images:
            summary_lines.append(f"• {len(images)} Docker image(s)")
        if secrets:
            summary_lines.append(f"• {len(secrets)} potential secret(s)")
        
        summary_lines.append("\nOriginal values have been restored in this response.")
        
        return "\n".join(summary_lines)
    
    def clear_session(self):
        """Clear the current session's anonymization mapping."""
        self.anonymization_map.clear()
        self.reverse_map.clear()
        self.counter = 1