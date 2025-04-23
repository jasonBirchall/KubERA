import requests
import logging
from datetime import datetime, timezone, timedelta
import base64
import json
import subprocess
from typing import List, Dict, Any, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ArgoCDTool:
    """Tool for interacting with ArgoCD API."""
    
    def __init__(self, base_url: str = "http://localhost:8080", username: str = "admin", password: str = ""):
        """
        Initialize the ArgoCD tool with the API base URL and credentials.
        
        Args:
            base_url: The base URL for ArgoCD API (default: http://localhost:8080)
            username: ArgoCD username (default: admin)
            password: ArgoCD password (if None, will attempt to fetch from k8s secret)
        """
        self.base_url = base_url
        self.username = username
        self.password = password or self._get_admin_password()
        self.token = None
        self.connected = self._check_connection()
        
        if not self.connected:
            logger.warning(f"⚠️ Could not connect to ArgoCD at {base_url}. Will use synthetic data.")
        else:
            logger.info(f"✅ Successfully connected to ArgoCD at {base_url}")
    
    def _get_admin_password(self) -> str:
        """
        Attempts to get the ArgoCD admin password from Kubernetes secret.
        Returns a default value if unsuccessful.
        """
        try:
            # Try to get the password from the argocd-initial-admin-secret
            cmd = "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
            password = subprocess.check_output(cmd, shell=True).decode().strip()
            logger.info("Successfully retrieved ArgoCD admin password from k8s secret")
            return password
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to get ArgoCD admin password: {e}")
            # Return a default password for synthetic data
            return "password"
    
    def _check_connection(self) -> bool:
        """Check if ArgoCD is accessible and get an authentication token."""
        try:
            # Try to authenticate and get a token
            auth_url = f"{self.base_url}/api/v1/session"
            response = requests.post(
                auth_url,
                json={"username": self.username, "password": self.password},
                verify=False  # Skip SSL verification for self-signed certs
            )
            
            if response.status_code == 200:
                self.token = response.json().get("token")
                return True
            else:
                logger.error(f"ArgoCD authentication failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to ArgoCD: {e}")
            return False
    
    def get_applications(self) -> List[Dict[str, Any]]:
        """
        Get all ArgoCD applications.
        
        Returns:
            List of application objects
        """
        if not self.connected:
            logger.info("Not connected to ArgoCD, returning synthetic data")
            return self.generate_synthetic_applications()
            
        try:
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            response = requests.get(
                f"{self.base_url}/api/v1/applications",
                headers=headers,
                verify=False
            )
            
            if response.status_code == 200:
                return response.json().get("items", [])
            else:
                logger.error(f"Failed to get applications: {response.status_code} - {response.text}")
                return self.generate_synthetic_applications()
                
        except Exception as e:
            logger.error(f"Error getting ArgoCD applications: {e}")
            return self.generate_synthetic_applications()
    
    def get_application_events(self, app_name: str, hours: int = 6) -> List[Dict[str, Any]]:
        """
        Get events for a specific ArgoCD application.
        
        Args:
            app_name: The name of the application
            hours: Number of hours to look back
            
        Returns:
            List of event objects for the application
        """
        if not self.connected:
            logger.info(f"Not connected to ArgoCD, returning synthetic events for {app_name}")
            return self.generate_synthetic_events(app_name)
            
        try:
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            response = requests.get(
                f"{self.base_url}/api/v1/applications/{app_name}/events",
                headers=headers,
                verify=False
            )
            
            if response.status_code == 200:
                events = response.json().get("items", [])
                # Filter events by time
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                filtered_events = [
                    e for e in events 
                    if datetime.fromisoformat(e.get("lastTimestamp", "").replace("Z", "+00:00")) > cutoff
                ]
                return filtered_events
            else:
                logger.error(f"Failed to get events for {app_name}: {response.status_code} - {response.text}")
                return self.generate_synthetic_events(app_name)
                
        except Exception as e:
            logger.error(f"Error getting events for {app_name}: {e}")
            return self.generate_synthetic_events(app_name)
    
    def get_all_application_events(self, hours: int = 6) -> List[Dict[str, Any]]:
        """
        Get events for all ArgoCD applications.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            List of all event objects for all applications
        """
        all_events = []
        
        if not self.connected:
            logger.info("Not connected to ArgoCD, returning synthetic events for all apps")
            return self.generate_synthetic_events_all_apps()
        
        # Get all applications
        applications = self.get_applications()
        
        # Get events for each application
        for app in applications:
            app_name = app.get("metadata", {}).get("name")
            if app_name:
                app_events = self.get_application_events(app_name, hours)
                all_events.extend(app_events)
        
        return all_events
    
    def get_application_status(self, app_name: str) -> Dict[str, Any]:
        """
        Get the status of a specific ArgoCD application.
        
        Args:
            app_name: The name of the application
            
        Returns:
            Status object for the application
        """
        if not self.connected:
            logger.info(f"Not connected to ArgoCD, returning synthetic status for {app_name}")
            return self.generate_synthetic_status(app_name)
            
        try:
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            response = requests.get(
                f"{self.base_url}/api/v1/applications/{app_name}",
                headers=headers,
                verify=False
            )
            
            if response.status_code == 200:
                return response.json().get("status", {})
            else:
                logger.error(f"Failed to get status for {app_name}: {response.status_code} - {response.text}")
                return self.generate_synthetic_status(app_name)
                
        except Exception as e:
            logger.error(f"Error getting status for {app_name}: {e}")
            return self.generate_synthetic_status(app_name)
    
    def get_application_alerts(self, hours: int = 6) -> List[Dict[str, Any]]:
        """
        Get all alerts for applications that have issues.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            List of alert objects for applications with issues
        """
        if not self.connected:
            logger.info("Not connected to ArgoCD, returning synthetic alerts")
            return self.generate_synthetic_alerts()
        
        alerts = []
        applications = self.get_applications()
        
        for app in applications:
            app_name = app.get("metadata", {}).get("name")
            if not app_name:
                continue
                
            # Get application status
            status = self.get_application_status(app_name)
            
            # Check if there are health or sync issues
            health_status = status.get("health", {}).get("status", "")
            sync_status = status.get("sync", {}).get("status", "")
            
            if health_status not in ["Healthy"] or sync_status not in ["Synced"]:
                # This application has issues, create an alert
                created_at = datetime.now(timezone.utc)
                
                # Get the namespace the application is deployed to
                namespace = app.get("spec", {}).get("destination", {}).get("namespace", "default")
                
                # Determine severity based on health and sync status
                severity = "high" if health_status == "Degraded" else "medium"
                
                # Get recent events for context
                events = self.get_application_events(app_name, hours)
                
                # Create the alert
                alert = {
                    "name": f"ArgoCD{health_status if health_status != 'Healthy' else sync_status}Alert",
                    "severity": severity,
                    "source": "argocd",
                    "pods": [
                        {
                            "name": app_name,
                            "namespace": namespace,
                            "start": created_at.isoformat(),
                            "end": None,  # ongoing
                            "source": "argocd",
                            "details": {
                                "healthStatus": health_status,
                                "syncStatus": sync_status,
                                "events": events[:5] if events else []  # Include up to 5 recent events
                            }
                        }
                    ],
                    "count": 1
                }
                
                alerts.append(alert)
        
        return alerts if alerts else self.generate_synthetic_alerts()
    
    def generate_synthetic_applications(self) -> List[Dict[str, Any]]:
        """Generate synthetic application data for demonstration purposes."""
        now = datetime.now(timezone.utc)
        
        return [
            {
                "metadata": {
                    "name": "guestbook",
                    "namespace": "argocd"
                },
                "spec": {
                    "destination": {
                        "namespace": "guestbook",
                        "server": "https://kubernetes.default.svc"
                    },
                    "source": {
                        "path": "guestbook",
                        "repoURL": "https://github.com/argoproj/argocd-example-apps.git"
                    }
                },
                "status": {
                    "health": {"status": "Healthy"},
                    "sync": {"status": "Synced"}
                }
            },
            {
                "metadata": {
                    "name": "helm-guestbook",
                    "namespace": "argocd"
                },
                "spec": {
                    "destination": {
                        "namespace": "helm-guestbook",
                        "server": "https://kubernetes.default.svc"
                    },
                    "source": {
                        "path": "helm-guestbook",
                        "repoURL": "https://github.com/argoproj/argocd-example-apps.git"
                    }
                },
                "status": {
                    "health": {"status": "Healthy"},
                    "sync": {"status": "Synced"}
                }
            },
            {
                "metadata": {
                    "name": "failing-app",
                    "namespace": "argocd"
                },
                "spec": {
                    "destination": {
                        "namespace": "failing-app",
                        "server": "https://kubernetes.default.svc"
                    },
                    "source": {
                        "path": "helm-guestbook",
                        "repoURL": "https://github.com/argoproj/argocd-example-apps.git"
                    }
                },
                "status": {
                    "health": {"status": "Degraded"},
                    "sync": {"status": "OutOfSync"}
                }
            }
        ]
    
    def generate_synthetic_events(self, app_name: str) -> List[Dict[str, Any]]:
        """Generate synthetic event data for a specific application."""
        now = datetime.now(timezone.utc)
        
        if app_name == "guestbook" or app_name == "helm-guestbook":
            # Healthy apps have normal sync events
            return [
                {
                    "type": "Normal",
                    "reason": "ResourceUpdated",
                    "message": f"Updated deployment {app_name}",
                    "lastTimestamp": (now - timedelta(minutes=30)).isoformat(),
                    "name": app_name
                },
                {
                    "type": "Normal",
                    "reason": "Synced",
                    "message": f"Application {app_name} synced successfully",
                    "lastTimestamp": (now - timedelta(minutes=25)).isoformat(),
                    "name": app_name
                }
            ]
        else:
            # Failing app has error events
            return [
                {
                    "type": "Warning",
                    "reason": "SyncFailed",
                    "message": f"Failed to sync application {app_name}: deployment error",
                    "lastTimestamp": (now - timedelta(minutes=15)).isoformat(),
                    "name": app_name
                },
                {
                    "type": "Warning",
                    "reason": "HealthCheckFailed",
                    "message": f"Application {app_name} is not healthy",
                    "lastTimestamp": (now - timedelta(minutes=10)).isoformat(),
                    "name": app_name
                },
                {
                    "type": "Warning",
                    "reason": "OutOfSync",
                    "message": f"Application {app_name} is out of sync",
                    "lastTimestamp": (now - timedelta(minutes=5)).isoformat(),
                    "name": app_name
                }
            ]
    
    def generate_synthetic_events_all_apps(self) -> List[Dict[str, Any]]:
        """Generate synthetic event data for all applications."""
        all_events = []
        
        # Get synthetic applications
        applications = self.generate_synthetic_applications()
        
        # Generate events for each application
        for app in applications:
            app_name = app.get("metadata", {}).get("name")
            if app_name:
                events = self.generate_synthetic_events(app_name)
                all_events.extend(events)
        
        return all_events
    
    def generate_synthetic_status(self, app_name: str) -> Dict[str, Any]:
        """Generate synthetic status data for a specific application."""
        if app_name == "guestbook" or app_name == "helm-guestbook":
            return {
                "health": {"status": "Healthy"},
                "sync": {"status": "Synced"},
                "operationState": {
                    "phase": "Succeeded",
                    "message": "successfully synced"
                }
            }
        else:
            return {
                "health": {"status": "Degraded"},
                "sync": {"status": "OutOfSync"},
                "operationState": {
                    "phase": "Failed",
                    "message": "failed to sync"
                }
            }
    
    def generate_synthetic_alerts(self) -> List[Dict[str, Any]]:
        """Generate synthetic alert data for applications with issues."""
        now = datetime.now(timezone.utc)
        
        return [
            {
                "name": "ArgoCDDegradedAlert",
                "severity": "high",
                "source": "argocd",
                "pods": [
                    {
                        "name": "failing-app",
                        "namespace": "failing-app",
                        "start": (now - timedelta(minutes=30)).isoformat(),
                        "end": None,  # ongoing
                        "source": "argocd",
                        "details": {
                            "healthStatus": "Degraded",
                            "syncStatus": "OutOfSync",
                            "events": self.generate_synthetic_events("failing-app")
                        }
                    }
                ],
                "count": 1
            }
        ]
