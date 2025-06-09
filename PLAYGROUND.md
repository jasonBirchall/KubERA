# 🎯 KubERA Playground Setup

Welcome to KubERA! This guide will help you set up a complete testing environment in just one command.

## 🚀 Quick Start

For new users who want to try KubERA immediately:

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="your-api-key-here"

# Set up the entire playground environment
make playground

# Start the KubERA application
make run
```

That's it! The playground command will:
- ✅ Check and install all required dependencies
- 🔧 Create a local Kubernetes cluster with kind
- 📊 Install Prometheus for metrics monitoring
- 🔄 Install ArgoCD for GitOps workflows
- 🚀 Deploy sample applications and test workloads for testing
- 🗄️ Initialize the KubERA database

## 📋 What Gets Installed

### Dependencies Automatically Checked/Installed:
- **Homebrew** (package manager for macOS)
- **kind** (Kubernetes in Docker)
- **kubectl** (Kubernetes CLI)
- **Docker** (container runtime)
- **uv** (Python package manager)

### Kubernetes Components:
- **Local kind cluster** named `kubera-local`
- **Prometheus** monitoring stack (namespace: `monitoring`)
- **ArgoCD** GitOps platform (namespace: `argocd`)
- **Sample applications** (working and test workloads)
- **Local registry** for container images

## 🌐 Access URLs

After running `make playground`, you'll have access to:

| Service | URL | Description |
|---------|-----|-------------|
| **KubERA Dashboard** | http://localhost:8501 | Main application interface |
| **Prometheus** | http://localhost:9090 | Metrics and monitoring |
| **ArgoCD** | http://localhost:8080 | GitOps deployments |

## 🔑 Default Credentials

### ArgoCD Login:
- **Username:** `admin`
- **Password:** Run this command:
  ```bash
  kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
  ```

## 📚 Useful Commands

### Application Management:
```bash
# Start KubERA application
make run

# Check cluster status
kubectl get pods -A

# View KubERA database
sqlite3 kubera.db ".tables"
```

### Service Access:
```bash
# Port forward Prometheus (if needed)
make prometheus-port-forward

# Port forward ArgoCD (if needed)
make argocd-port-forward
```

### Environment Management:
```bash
# Clean up everything
make destroy-all

# Reset just the database
make reset-db

# Rebuild from scratch
make destroy-all && make playground
```

## 🧪 What to Test

Once your playground is running, try these scenarios:

### 1. **Pod Failure Analysis**
- Click on problematic pods in the KubERA dashboard
- Observe the AI-powered analysis in the terminal
- Check the anonymization privacy notices

### 2. **Timeline View**
- Explore the timeline of events
- Filter by namespace, priority, or source
- Toggle between grouped events and event stream

### 3. **Multi-Source Monitoring**
- View events from Kubernetes, Prometheus, and ArgoCD
- Compare different data sources
- Test the source filtering functionality

### 4. **Real-time Updates**
- Create new failing pods: `kubectl run test-fail --image=nonexistent:latest`
- Watch them appear in the dashboard
- Delete pods and see them resolve

## 🔧 Troubleshooting

### Common Issues:

**1. "OPENAI_API_KEY not set"**
```bash
export OPENAI_API_KEY="your-api-key-here"
```

**2. "Docker daemon not running"**
- Start Docker Desktop
- Or run: `open /Applications/Docker.app`

**3. "kind cluster already exists"**
```bash
make destroy-all
make playground
```

**4. "Port already in use"**
- Check for existing services on ports 8501, 9090, 8080
- Kill processes or use different ports

**5. "kubectl context not set"**
```bash
kubectl config use-context kind-kubera-local
```

### Debug Commands:
```bash
# Check cluster nodes
kubectl get nodes

# Check all pods
kubectl get pods -A

# Check KubERA logs
docker logs kind-registry

# Verify port forwards
netstat -an | grep -E '8501|9090|8080'
```

## 🔄 Development Workflow

For developers working on KubERA:

```bash
# Initial setup
make playground

# Make code changes...

# Restart application
# Stop with Ctrl+C, then:
make run

# Test with fresh data
make reset-db
make run

# Clean environment for testing
make destroy-all
make playground
```

## 🎯 Next Steps

Once your playground is running:

1. **Explore the Interface:** Navigate through the timeline and analysis panels
2. **Create Test Scenarios:** Deploy failing applications to see KubERA in action
3. **Monitor Real Issues:** Connect to your actual clusters for real-world testing
4. **Customize Configuration:** Modify the Kubernetes YAML files in the `k8s/` directory

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review logs: `kubectl logs -n <namespace> <pod-name>`
3. Consult the main README.md for detailed documentation
4. Create an issue in the repository with error details

---

**Happy testing with KubERA! 🎉**

The playground environment gives you a complete Kubernetes observability stack in minutes, letting you focus on exploring KubERA's capabilities rather than setup complexity.