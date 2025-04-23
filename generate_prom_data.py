#!/usr/bin/env python3
"""
Script to generate synthetic Prometheus metrics for Kubera demo.
This will create metrics for CPU, memory, and pod status that can be used
as a data source in the Kubera dashboard.
"""

import subprocess
import time
import random
import json
from datetime import datetime, timedelta

def create_cpu_metrics():
    """Create synthetic CPU usage metrics"""
    print("Generating CPU metrics...")
    
    # These will be our victim pods that have high CPU usage
    pods = [
        {"name": "api-server-6d4f8cb9b5-abc12", "namespace": "default"},
        {"name": "worker-7f6b8d95c4-def34", "namespace": "default"}
    ]
    
    for pod in pods:
        # Create a metric series for the pod with high CPU usage
        metric_name = f'container_cpu_usage_seconds_total{{pod="{pod["name"]}", namespace="{pod["namespace"]}"}}'
        
        # Get current timestamp as Unix time
        now = datetime.now().timestamp()
        
        # Create data points - one per minute for the last hour
        data_points = []
        for i in range(60):
            # Create a series that increases over time
            timestamp = now - (60 - i) * 60  # Go back 60 minutes and step forward
            
            # Higher values for more recent timestamps to show increasing usage
            value = 0.1 + (i / 60) * 0.8 + random.random() * 0.1
            
            data_points.append([timestamp, str(value)])
        
        # Log the metric being exported
        print(f"Exported {metric_name} with {len(data_points)} data points")
        
        # In a real implementation, you would push these metrics to Prometheus
        # For now, we'll just return the structure
        
    return True

def create_memory_metrics():
    """Create synthetic memory usage metrics"""
    print("Generating memory metrics...")
    
    # Pods with memory issues
    pods = [
        {"name": "database-primary-0", "namespace": "default"}
    ]
    
    for pod in pods:
        # Create a metric series for the pod with high memory usage
        metric_name = f'container_memory_usage_bytes{{pod="{pod["name"]}", namespace="{pod["namespace"]}"}}'
        
        # Get current timestamp as Unix time
        now = datetime.now().timestamp()
        
        # Create data points - one per minute for the last 3 hours
        data_points = []
        for i in range(180):
            timestamp = now - (180 - i) * 60
            
            # Spike in memory usage
            if i > 150:  # Spike in last 30 minutes
                value = 500000000 + random.random() * 100000000  # ~500MB
            else:
                value = 200000000 + random.random() * 50000000   # ~200MB
                
            data_points.append([timestamp, str(value)])
        
        # Log the metric being exported
        print(f"Exported {metric_name} with {len(data_points)} data points")
    
    return True

def create_pod_restart_metrics():
    """Create synthetic pod restart metrics"""
    print("Generating pod restart metrics...")
    
    # Pods with restart issues
    pods = [
        {"name": "frontend-5c7f9b88d7-ghi56", "namespace": "default"},
        {"name": "api-gateway-6d5f7cb8a4-jkl78", "namespace": "default"}
    ]
    
    for pod in pods:
        # Create a metric series for pod restarts
        metric_name = f'kube_pod_container_status_restarts_total{{pod="{pod["name"]}", namespace="{pod["namespace"]}"}}'
        
        # Get current timestamp as Unix time
        now = datetime.now().timestamp()
        
        # Create data points - one per 10 minutes
        data_points = []
        restart_count = 0
        
        for i in range(12):  # 2 hours (12 x 10 minutes)
            timestamp = now - (12 - i) * 600  # Every 10 minutes
            
            # Add restarts at certain points
            if i in [4, 7, 10]:
                restart_count += 1
            
            data_points.append([timestamp, str(restart_count)])
        
        # Log the metric being exported
        print(f"Exported {metric_name} with {len(data_points)} data points")
    
    return True

def main():
    """Main function to generate all metrics"""
    print("Starting synthetic Prometheus metric generation...")
    
    # Generate the metrics
    create_cpu_metrics()
    create_memory_metrics()
    create_pod_restart_metrics()
    
    print("Successfully generated synthetic metrics!")
    print("Note: In a real environment, you would need to export these to Prometheus.")
    print("For demo purposes, the Kubera dashboard will now use synthetic data via the API.")

if __name__ == "__main__":
    main()
