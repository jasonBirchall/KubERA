import requests
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class PrometheusTool:
    """Tool for fetching and analyzing data from Prometheus."""
    
    def __init__(self, base_url: str = "http://localhost:9090"):
        """
        Initialize the Prometheus tool with the API base URL.
        
        Args:
            base_url: The base URL for Prometheus API (default: http://localhost:9090)
        """
        self.base_url = base_url
        self.api_url = f"{base_url}/api/v1"
    
    def query(self, query: str, time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Execute an instant query against Prometheus.
        
        Args:
            query: The PromQL query string
            time: Optional timestamp for the query (default: now)
            
        Returns:
            Dictionary containing the query results
        """
        endpoint = f"{self.api_url}/query"
        
        params = {"query": query}
        if time:
            params["time"] = time.timestamp()
            
        try:
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error querying Prometheus: {e}")
            return {"status": "error", "error": str(e)}
    
    def query_range(self, query: str, start: datetime, end: datetime, step: str = "1m") -> Dict[str, Any]:
        """
        Execute a range query against Prometheus.
        
        Args:
            query: The PromQL query string
            start: Start time for the range query
            end: End time for the range query
            step: Query resolution step width (e.g., 1m, 30s)
            
        Returns:
            Dictionary containing the query results
        """
        endpoint = f"{self.api_url}/query_range"
        
        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step
        }
            
        try:
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error querying Prometheus range: {e}")
            return {"status": "error", "error": str(e)}
    
    def get_pod_alerts(self, hours: int = 6, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get alerts for failing pods from Prometheus.
        
        Args:
            hours: Number of hours to look back
            namespace: Optional namespace to filter alerts
            
        Returns:
            List of alert objects with timestamps and metadata
        """
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)
        
        # Basic query to find failing pods
        # We'll look for pods that have been restarting
        namespace_filter = f',namespace="{namespace}"' if namespace else ''
        query = f'changes(kube_pod_container_status_restarts_total{{pod!=""{namespace_filter}}}[5m]) > 0'
        
        # Also check for pods that are in a non-ready state
        ready_query = f'kube_pod_status_ready{{condition="false"{namespace_filter}}}'
        
        # Execute the range queries
        restart_data = self.query_range(query, start_time, end_time, "1m")
        ready_data = self.query_range(ready_query, start_time, end_time, "1m")
        
        # Process the results
        issue_groups = {}
        
        # Helper function to process results
        def process_results(results, issue_type):
            if results.get("status") != "success":
                logger.error(f"Query failed: {results.get('error', 'Unknown error')}")
                return
                
            for result in results.get("data", {}).get("result", []):
                metric = result.get("metric", {})
                pod_name = metric.get("pod", "unknown")
                namespace = metric.get("namespace", "default")
                
                # Extract timestamps and values
                values = result.get("values", [])
                if not values:
                    continue
                    
                timestamps = [datetime.fromtimestamp(float(v[0]), tz=timezone.utc) for v in values]
                first_seen = min(timestamps)
                last_seen = max(timestamps)
                
                # Determine if the issue is still ongoing
                # If the most recent value is non-zero, consider it ongoing
                is_ongoing = float(values[-1][1]) > 0 if values else False
                
                if issue_type not in issue_groups:
                    issue_groups[issue_type] = {
                        "name": issue_type,
                        "severity": self.determine_severity(issue_type),
                        "pods": [],
                        "count": 0
                    }
                
                issue_groups[issue_type]["pods"].append({
                    "name": pod_name,
                    "namespace": namespace,
                    "start": first_seen.isoformat(),
                    "end": None if is_ongoing else last_seen.isoformat()
                })
                issue_groups[issue_type]["count"] += 1
        
        # Process both query results
        process_results(restart_data, "PodRestarting")
        process_results(ready_data, "PodNotReady")
        
        return list(issue_groups.values())
    
    def determine_severity(self, issue_type: str) -> str:
        """
        Maps issue types to severity levels (high, medium, low).
        
        Args:
            issue_type: The type of issue/alert
            
        Returns:
            Severity level as string ("high", "medium", or "low")
        """
        high_severity = ["PodCrashLooping", "PodOOMKilled"]
        medium_severity = ["PodRestarting", "PodNotReady", "ContainerWaiting"]
        
        if issue_type in high_severity:
            return "high"
        elif issue_type in medium_severity:
            return "medium"
        else:
            return "low"
    
    def generate_synthetic_data(self) -> List[Dict[str, Any]]:
        """
        Generate synthetic alert data for demonstration purposes.
        
        Returns:
            List of synthetic alert objects
        """
        now = datetime.now(timezone.utc)
        
        # Create some synthetic data with various alert types
        synthetic_alerts = [
            {
                "name": "HighCPUUsage",
                "severity": "medium",
                "pods": [
                    {
                        "name": "api-server-6d4f8cb9b5-abc12",
                        "namespace": "default",
                        "start": (now - timedelta(hours=2)).isoformat(),
                        "end": (now - timedelta(hours=1, minutes=30)).isoformat()
                    },
                    {
                        "name": "worker-7f6b8d95c4-def34",
                        "namespace": "default",
                        "start": (now - timedelta(minutes=45)).isoformat(),
                        "end": None  # ongoing
                    }
                ],
                "count": 2
            },
            {
                "name": "MemoryPressure",
                "severity": "high",
                "pods": [
                    {
                        "name": "database-primary-0",
                        "namespace": "default",
                        "start": (now - timedelta(hours=3)).isoformat(),
                        "end": (now - timedelta(hours=2, minutes=45)).isoformat()
                    }
                ],
                "count": 1
            },
            {
                "name": "SlowHTTPResponses",
                "severity": "low",
                "pods": [
                    {
                        "name": "frontend-5c7f9b88d7-ghi56",
                        "namespace": "default",
                        "start": (now - timedelta(hours=1)).isoformat(),
                        "end": None  # ongoing
                    },
                    {
                        "name": "api-gateway-6d5f7cb8a4-jkl78",
                        "namespace": "default",
                        "start": (now - timedelta(hours=1, minutes=15)).isoformat(),
                        "end": (now - timedelta(minutes=30)).isoformat()
                    }
                ],
                "count": 2
            }
        ]
        
        return synthetic_alerts
