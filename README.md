# K8s REACT Root Cause Analysis Agent

## Overview
This repository demonstrates how to create a local Kubernetes cluster using [kind](https://kind.sigs.k8s.io/) and deploy a simple “Hello World” application. We use the `nginxdemos/hello` container image, which listens on port 80 and serves a basic “Welcome to NGINX” page.

## Prerequisites
1. **Docker** installed and running.  
2. **kubectl** installed (v1.19+ recommended).  
3. **kind** installed (v0.17+ recommended).  
4. A Unix-like shell with `make` installed (for running the provided Makefile).

## Files
- **kind-config.yaml**: Defines the local cluster configuration.  
- **Makefile**: Contains helpful commands for cluster lifecycle management, app deployment, and teardown.

## Quick Start

1. **Create the Cluster**  
   ```bash
   make cluster
   ```
   This command uses the configuration in `kind-config.yaml` to create a local cluster named `demo-cluster`.

2. **Deploy the Hello World Application**  
   ```bash
   make deploy
   ```
   This creates a Kubernetes Deployment called `hello-world`, pulling the `nginxdemos/hello` image.

3. **Expose the App**  
   ```bash
   make expose
   ```
   This exposes the deployment as a NodePort service on port 80 inside the cluster, mapped to nodePort 30080 by default.

4. **Verify and Test**  
   - Run:
     ```bash
     kubectl get pods
     kubectl get svc
     ```
   - Look for `hello-world` in the list of pods and services.  
   - If your **kind-config.yaml** maps the cluster’s port 30080 to `localhost:8080`, open a browser or run:
     ```bash
     curl http://localhost:8080
     ```
     You should see the Hello World page from `nginxdemos/hello`.

5. **Cleaning Up**  
   ```bash
   make teardown
   ```
   This deletes the kind cluster, removing all related containers and networks. Alternatively, you can delete just the application objects and keep the cluster if you wish.

## Troubleshooting
1. **Empty Reply from Server**  
   - Ensure your `kind-config.yaml` includes the correct `extraPortMappings`.  
   - Double-check that the service `nodePort` and the cluster port are consistent.  
   - If necessary, run:
     ```bash
     kubectl port-forward deployment/hello-world 8081:80
     curl http://localhost:8081
     ```
     If this succeeds, your container is working internally and you may need to adjust your NodePort or port mapping configuration.

2. **Pod Errors**  
   - Check logs:
     ```bash
     kubectl logs deployment/hello-world
     ```
   - Describe pods or events to see if there’s a crash:
     ```bash
     kubectl describe pod <pod-name>
     ```

3. **Removing Just the App**  
   - You can remove the deployment and service without deleting the cluster:
     ```bash
     kubectl delete deployment hello-world
     kubectl delete svc hello-world
     ```
