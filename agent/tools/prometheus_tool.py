import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
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
        self.connected = self._check_connection()

        if not self.connected:
            logger.warning(
                f"⚠️ Could not connect to Prometheus at {base_url}. Will use synthetic data.")
        else:
            logger.info(
                f"✅ Successfully connected to Prometheus at {base_url}")

    def _check_connection(self):
        """Check if Prometheus is accessible"""
        try:
            response = requests.get(f"{self.api_url}/status/config")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to connect to Prometheus: {e}")
            return False

    def query(self, query: str, time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Execute an instant query against Prometheus.

        Args:
            query: The PromQL query string
            time: Optional timestamp for the query (default: now)

        Returns:
            Dictionary containing the query results
        """
        if not self.connected:
            logger.warning(
                f"Not connected to Prometheus. Would have queried: {query}")
            return {"status": "error", "error": "Not connected to Prometheus"}

        endpoint = f"{self.api_url}/query"

        params = {"query": query}
        if time:
            params["time"] = time.timestamp()

        try:
            logger.info(f"Executing Prometheus query: {query}")
            response = requests.get(endpoint, params=params)
            if response.status_code != 200:
                logger.error(
                    f"Query failed: {response.status_code} - {response.text}")
                return {"status": "error", "error": response.text}
            return response.json()
        except Exception as e:
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
        if not self.connected:
            logger.warning(
                f"Not connected to Prometheus. Would have queried: {query}")
            return {"status": "error", "error": "Not connected to Prometheus"}

        endpoint = f"{self.api_url}/query_range"

        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step
        }

        try:
            logger.info(f"Executing Prometheus range query: {query}")
            logger.info(f"Parameters: {params}")
            response = requests.get(endpoint, params=params)

            if response.status_code != 200:
                logger.error(
                    f"Query failed: {response.status_code} - {response.text}")
                return {"status": "error", "error": response.text}

            return response.json()
        except Exception as e:
            logger.error(f"Error querying Prometheus: {e}")
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
        restart_query = f'changes(kube_pod_container_status_restarts_total{{pod!=""{namespace_filter}}}[5m]) > 0'

        # Also check for pods that are in a non-ready state
        ready_query = f'kube_pod_status_ready{{condition="false"{namespace_filter}}}'

        # Also check for pods that have failed
        failed_query = f'kube_pod_status_phase{{phase="Failed"{namespace_filter}}}'

        # Also check for pods that are pending for too long
        pending_query = f'kube_pod_status_phase{{phase="Pending"{namespace_filter}}}'

        # Execute the range queries
        restart_data = self.query_range(
            restart_query, start_time, end_time, "1m")
        ready_data = self.query_range(ready_query, start_time, end_time, "1m")
        failed_data = self.query_range(
            failed_query, start_time, end_time, "1m")
        pending_data = self.query_range(
            pending_query, start_time, end_time, "1m")

        # Process the results
        issue_groups = {}

        # Helper function to process results
        def process_results(results, issue_type):
            if results.get("status") != "success":
                logger.error(
                    f"Query failed for {issue_type}: {results.get('error', 'Unknown error')}")
                return

            result_data = results.get("data", {}).get("result", [])
            logger.info(
                f"Got {len(result_data)} results for {issue_type} query")

            for result in result_data:
                metric = result.get("metric", {})
                pod_name = metric.get("pod", "unknown")
                namespace = metric.get("namespace", "default")

                # Extract timestamps and values
                values = result.get("values", [])
                if not values:
                    continue

                # For Prometheus pod status metrics, we need to check if the value is actually 1
                # A value of 0 means the pod is NOT in that state
                if issue_type in ["PodFailed", "PodNotReady", "PodPending"]:
                    # Check if the latest value is 1 (meaning the pod is actually in that state)
                    latest_value = float(values[-1][1])
                    if latest_value <= 0:
                        # Skip this pod as it's not actually in that state
                        continue

                timestamps = [datetime.fromtimestamp(
                    float(v[0]), tz=timezone.utc) for v in values]
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
                        "count": 0,
                        "source": "prometheus"
                    }

                issue_groups[issue_type]["pods"].append({
                    "name": pod_name,
                    "namespace": namespace,
                    "start": first_seen.isoformat(),
                    "end": None if is_ongoing else last_seen.isoformat(),
                    "source": "prometheus"
                })
                issue_groups[issue_type]["count"] += 1

        # Process all query results
        process_results(restart_data, "PodRestarting")
        process_results(ready_data, "PodNotReady")
        process_results(failed_data, "PodFailed")
        process_results(pending_data, "PodPending")


        return list(issue_groups.values())

    def determine_severity(self, issue_type: str) -> str:
        """
        Maps issue types to severity levels (high, medium, low).

        Args:
            issue_type: The type of issue/alert

        Returns:
            Severity level as string ("high", "medium", or "low")
        """
        high_severity = ["PodCrashLooping",
                         "PodOOMKilled", "PodFailed", "MemoryPressure"]
        medium_severity = ["PodRestarting", "PodNotReady",
                           "ContainerWaiting", "HighCPUUsage"]

        if issue_type in high_severity:
            return "high"
        elif issue_type in medium_severity:
            return "medium"
        else:
            return "low"

    def list_pods(self, namespace=None):
        """Get a list of pod names in the specified namespace or all namespaces if None"""
        try:
            # Build query with or without namespace filter
            namespace_filter = f',namespace="{namespace}"' if namespace else ''
            query = f'kube_pod_info{{pod!=""{namespace_filter}}}'

            result = self.query(query)
            pods = []

            if result.get("status") == "success":
                for metric in result.get("data", {}).get("result", []):
                    pod_name = metric.get("metric", {}).get("pod")
                    if pod_name:
                        pods.append(pod_name)

            return pods
        except Exception as e:
            logger.error(f"Error listing pods: {e}")
            return []
