#!/usr/bin/env python3
"""
Test script to verify Prometheus connection and data.
This script will check the connection to Prometheus and
execute some test queries to verify that data is available.
"""

import requests
import json
import sys
from datetime import datetime, timedelta

PROMETHEUS_URL = "http://localhost:9090"

def check_prometheus():
    """Check if Prometheus is reachable"""
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/status/config")
        if response.status_code == 200:
            print("✅ Prometheus is accessible")
            return True
        else:
            print(f"❌ Prometheus returned status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Could not connect to Prometheus: {e}")
        return False

def get_available_metrics():
    """Get a list of available metrics"""
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/label/__name__/values")
        if response.status_code == 200:
            metrics = response.json().get("data", [])
            print(f"✅ Found {len(metrics)} available metrics")
            
            # Print some of the kubernetes metrics if available
            kube_metrics = [m for m in metrics if m.startswith("kube_")]
            if kube_metrics:
                print(f"Kubernetes metrics examples:")
                for metric in kube_metrics[:10]:
                    print(f"  - {metric}")
            return True
        else:
            print(f"❌ Error getting metrics: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def check_pod_metrics():
    """Check if pod metrics are available"""
    try:
        query = "kube_pod_info"
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                results = data.get("data", {}).get("result", [])
                if results:
                    print(f"✅ Found {len(results)} pods in Prometheus")
                    
                    # Print some pod names
                    print("Pod examples:")
                    for i, result in enumerate(results[:5]):
                        pod = result.get("metric", {}).get("pod", "unknown")
                        namespace = result.get("metric", {}).get("namespace", "unknown")
                        print(f"  {i+1}. {namespace}/{pod}")
                    
                    return True
                else:
                    print("❌ No pods found in Prometheus data")
            else:
                print(f"❌ Query failed: {data.get('error', 'Unknown error')}")
        else:
            print(f"❌ Query request failed: {response.status_code}")
        
        return False
    except Exception as e:
        print(f"❌ Error checking pod metrics: {e}")
        return False

def check_specific_metrics():
    """Check some specific metrics useful for the dashboard"""
    metrics_to_check = [
        ("kube_pod_container_status_restarts_total", "Pod restarts"),
        ("kube_pod_status_ready", "Pod readiness"),
        ("kube_pod_status_phase", "Pod phases")
    ]
    
    success = True
    
    for query, description in metrics_to_check:
        print(f"\nChecking {description} metrics...")
        try:
            response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    results = data.get("data", {}).get("result", [])
                    if results:
                        print(f"✅ Found {len(results)} {description} metrics")
                    else:
                        print(f"❌ No {description} metrics found")
                        success = False
                else:
                    print(f"❌ Query failed: {data.get('error', 'Unknown error')}")
                    success = False
            else:
                print(f"❌ Query request failed: {response.status_code}")
                success = False
                
        except Exception as e:
            print(f"❌ Error: {e}")
            success = False
    
    return success

def check_broken_pods():
    """Check if any broken pods are detected in Prometheus"""
    try:
        # Query for pods in non-ready state
        query = 'kube_pod_status_ready{condition="false"}'
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                results = data.get("data", {}).get("result", [])
                if results:
                    print(f"✅ Found {len(results)} pods in non-ready state:")
                    for result in results[:5]:  # Show up to 5 examples
                        pod = result.get("metric", {}).get("pod", "unknown")
                        namespace = result.get("metric", {}).get("namespace", "unknown")
                        print(f"  - {namespace}/{pod}")
                    return True
                else:
                    print("❌ No non-ready pods found in Prometheus")
        else:
            print(f"❌ Query request failed: {response.status_code}")
        
        # Also check for pods with restarts
        query = 'changes(kube_pod_container_status_restarts_total[5m]) > 0'
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                results = data.get("data", {}).get("result", [])
                if results:
                    print(f"✅ Found {len(results)} pods with recent restarts:")
                    for result in results[:5]:  # Show up to 5 examples
                        pod = result.get("metric", {}).get("pod", "unknown")
                        namespace = result.get("metric", {}).get("namespace", "unknown")
                        print(f"  - {namespace}/{pod}")
                    return True
                else:
                    print("❌ No pods with recent restarts found in Prometheus")
        
        return False
    except Exception as e:
        print(f"❌ Error checking for broken pods: {e}")
        return False

def check_range_query():
    """Test a range query to make sure it works"""
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)
        
        query = 'kube_pod_info'
        params = {
            "query": query,
            "start": start_time.timestamp(),
            "end": end_time.timestamp(),
            "step": "1m"
        }
        
        print(f"\nTesting range query...")
        print(f"URL: {PROMETHEUS_URL}/api/v1/query_range")
        print(f"Parameters: {params}")
        
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params=params)
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data)[:500]}...")  # Show first 500 chars
            
            if data.get("status") == "success":
                results = data.get("data", {}).get("result", [])
                if results:
                    print(f"✅ Range query successful, got {len(results)} series")
                    return True
                else:
                    print("❌ Range query returned no data")
            else:
                print(f"❌ Range query failed: {data.get('error', 'Unknown error')}")
        else:
            print(f"❌ Range query request failed: {response.status_code} - {response.text}")
        
        return False
    except Exception as e:
        print(f"❌ Error testing range query: {e}")
        return False

def main():
    print("Prometheus Test Script")
    print("=====================\n")
    
    print(f"Testing connection to Prometheus at {PROMETHEUS_URL}...")
    if not check_prometheus():
        print("\n❌ Cannot proceed - please make sure Prometheus is running and accessible at {PROMETHEUS_URL}")
        sys.exit(1)
    
    print("\nChecking for available metrics...")
    get_available_metrics()
    
    print("\nChecking for pod information...")
    check_pod_metrics()
    
    print("\nChecking for specific metrics needed by the dashboard...")
    check_specific_metrics()
    
    print("\nChecking for broken pods...")
    check_broken_pods()
    
    print("\nTesting range query functionality...")
    check_range_query()
    
    print("\nTest complete!")

if __name__ == "__main__":
    main()
