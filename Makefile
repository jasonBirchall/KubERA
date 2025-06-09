CLUSTER_NAME := kubera-local
BROKEN_DEMO_APP_DEPLOYMENT := hello-world-broken
BROKEN_DEMO_APP_IMAGE := nginxdemos/hellos # Obviously broken image
DEMO_APP_DEPLOYMENT := hello-world
DEMO_APP_IMAGE := nginxdemos/hello
DEMO_APP_PORT := 8080
NODE_PORT := 30080
KUBE_PORT := 80
DASHBOARD_PORT := 8501
DASHBOARD_CONTAINER := 0.0.1

.PHONY: cluster-up cluster-down demo-app-up demo-app-expose up dashboard dashboard-build dashboard-docker db-reset playground check-dependencies run help

## Show help information
help:
	@echo "🎯 KubERA - Kubernetes Error Root-cause Analysis"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  make playground          Set up complete testing environment"
	@echo "  make run                 Start the KubERA application"
	@echo ""
	@echo "🔧 Environment Management:"
	@echo "  make check-dependencies  Check and install required tools"
	@echo "  make cluster-up          Create kind cluster with registry"
	@echo "  make cluster-down        Delete the kind cluster"
	@echo "  make destroy-all         Clean up everything"
	@echo ""
	@echo "📊 Component Installation:"
	@echo "  make install-prometheus  Install Prometheus monitoring"
	@echo "  make install-argocd      Install ArgoCD (simplified)"
	@echo "  make install-argocd-full Install ArgoCD (full official)"
	@echo ""
	@echo "🧪 Testing & Demo:"
	@echo "  make demo-app-up         Deploy demo applications"
	@echo "  make create-many-failures Create test failing pods"
	@echo "  make create-demo-apps    Create ArgoCD demo applications"
	@echo ""
	@echo "🗄️  Database Management:"
	@echo "  make reset-db            Reset KubERA database"
	@echo "  make cleanup-db          Clean up old database entries"
	@echo ""
	@echo "🔗 Port Forwarding:"
	@echo "  make prometheus-port-forward  Forward Prometheus to localhost:9090"
	@echo "  make argocd-port-forward      Forward ArgoCD to localhost:8080"
	@echo ""
	@echo "📚 Documentation:"
	@echo "  See PLAYGROUND.md for detailed setup guide"
	@echo "  See README.md for complete documentation"
	@echo ""
	@echo "💡 Tip: Set OPENAI_API_KEY environment variable before starting"

## Check if OPENAI_API_KEY is set
check-api-key:
	@if [ -z "$$OPENAI_API_KEY" ]; then \
		echo "OPENAI_API_KEY environment variable is not set. Please set it before running."; \
		exit 1; \
	fi

## Check and install all required dependencies
check-dependencies:
	@echo "🔍 Checking required dependencies..."
	@echo ""
	@# Check for Homebrew
	@if ! command -v brew >/dev/null 2>&1; then \
		echo "❌ Homebrew is not installed."; \
		echo "📥 Please install Homebrew from https://brew.sh/"; \
		echo "   Run: /bin/bash -c \"\$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""; \
		exit 1; \
	else \
		echo "✅ Homebrew is installed"; \
	fi
	@# Check for kind
	@if ! command -v kind >/dev/null 2>&1; then \
		echo "❌ kind (Kubernetes in Docker) is not installed."; \
		echo "📥 Installing kind via Homebrew..."; \
		brew install kind; \
		echo "✅ kind installed successfully"; \
	else \
		echo "✅ kind is installed (version: $$(kind version 2>/dev/null | head -1))"; \
	fi
	@# Check for kubectl
	@if ! command -v kubectl >/dev/null 2>&1; then \
		echo "❌ kubectl is not installed."; \
		echo "📥 Installing kubectl via Homebrew..."; \
		brew install kubectl; \
		echo "✅ kubectl installed successfully"; \
	else \
		echo "✅ kubectl is installed (version: $$(kubectl version --client --short 2>/dev/null || echo "version check failed"))"; \
	fi
	@# Check for Docker
	@if ! command -v docker >/dev/null 2>&1; then \
		echo "❌ Docker is not installed."; \
		echo "📥 Please install Docker Desktop from https://docs.docker.com/desktop/"; \
		echo "   Or install via Homebrew: brew install --cask docker"; \
		exit 1; \
	else \
		echo "✅ Docker is installed"; \
	fi
	@# Check if Docker daemon is running
	@if ! docker info >/dev/null 2>&1; then \
		echo "❌ Docker daemon is not running."; \
		echo "🔧 Please start Docker Desktop or the Docker daemon"; \
		exit 1; \
	else \
		echo "✅ Docker daemon is running"; \
	fi
	@# Check for uv (Python package manager)
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "❌ uv (Python package manager) is not installed."; \
		echo "📥 Installing uv via Homebrew..."; \
		brew install uv; \
		echo "✅ uv installed successfully"; \
	else \
		echo "✅ uv is installed (version: $$(uv --version 2>/dev/null || echo "version check failed"))"; \
	fi
	@echo ""
	@echo "🎉 All dependencies are installed and ready!"

## Set up complete playground environment for testing KubERA
playground: check-api-key check-dependencies
	@echo "🏗️  Setting up KubERA playground environment..."
	@echo "This will create a complete testing environment with:"
	@echo "  • kind Kubernetes cluster"
	@echo "  • Prometheus monitoring"
	@echo "  • ArgoCD for GitOps"
	@echo "  • Sample broken pods for testing"
	@echo "  • KubERA database and application"
	@echo ""
	@# Clean up any existing environment
	@echo "🧹 Cleaning up any existing environment..."
	@$(MAKE) destroy-all 2>/dev/null || true
	@echo ""
	@# Reset and prepare database
	@echo "🗄️  Preparing KubERA database..."
	@$(MAKE) reset-db
	@echo ""
	@# Set up the cluster
	@echo "🔧 Creating kind cluster with local registry..."
	@$(MAKE) cluster-up
	@echo ""
	@# Wait for cluster to be ready
	@echo "⏳ Waiting for cluster to be ready..."
	@kubectl wait --for=condition=Ready nodes --all --timeout=60s
	@echo ""
	@# Install Prometheus
	@echo "📊 Installing Prometheus monitoring..."
	@$(MAKE) install-prometheus
	@echo ""
	@# Wait for Prometheus to be ready
	@echo "⏳ Waiting for Prometheus to start..."
	@kubectl wait --for=condition=available --timeout=120s deployment/prometheus-deployment -n monitoring || true
	@echo ""
	@# Install ArgoCD
	@echo "🔄 Installing ArgoCD..."
	@$(MAKE) install-argocd-core
	@$(MAKE) wait-for-argocd
	@$(MAKE) install-argocd-apps
	@echo ""
	@# Create demo applications and broken pods
	@echo "🚀 Creating demo applications..."
	@$(MAKE) demo-app-up
	@$(MAKE) create-many-failures
	@$(MAKE) create-demo-apps 2>/dev/null || true
	@echo ""
	@# Generate some test data
	@echo "📈 Generating test data for Prometheus..."
	@sleep 10  # Let pods start and generate some events
	@echo ""
	@# Final setup
	@echo "🏁 Finishing setup..."
	@sleep 5
	@echo ""
	@echo "================================================="
	@echo "🎉 KubERA Playground is ready!"
	@echo "================================================="
	@echo ""
	@echo "🌐 Access URLs:"
	@echo "  KubERA Dashboard:           http://localhost:$(DASHBOARD_PORT)"
	@echo "  Prometheus:                 http://localhost:9090"
	@echo "  ArgoCD:                     http://localhost:8080"
	@echo ""
	@echo "🔑 ArgoCD Credentials:"
	@echo "  Username: admin"
	@echo "  Password: Run this command to get it:"
	@echo "    kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath=\"{.data.password}\" | base64 -d && echo"
	@echo ""
	@echo "🚀 To start the KubERA application:"
	@echo "  make run"
	@echo ""
	@echo "🔧 Useful commands:"
	@echo "  Port forward Prometheus: make prometheus-port-forward"
	@echo "  Port forward ArgoCD:     make argocd-port-forward"
	@echo "  Check cluster status:    kubectl get pods -A"
	@echo "  Clean everything:        make destroy-all"
	@echo ""
	@echo "📚 What's running:"
	@kubectl get pods -A | head -20
	@echo ""
	@echo "Happy testing! 🎯"

## Start the KubERA application
run: check-api-key
	@echo "🚀 Starting KubERA application..."
	@echo "Access the dashboard at: http://localhost:$(DASHBOARD_PORT)"
	@echo "Press Ctrl+C to stop"
	@echo ""
	uv run python app.py

## Set up the local registry and kind cluster
cluster-up:
	@echo "Setting up local registry and kind cluster..."
	chmod +x setup-kind-registry.sh
	./setup-kind-registry.sh

## Teardown the entire kind cluster.
cluster-down:
	@echo "Deleting kind cluster named '$(CLUSTER_NAME)'..."
	kind delete cluster --name $(CLUSTER_NAME)

## Deploy the Hello World application.
demo-app-up:
	@echo "Deploying '$(DEMO_APP_DEPLOYMENT)' using image '$(DEMO_APP_IMAGE)'..."
	kubectl create deployment $(DEMO_APP_DEPLOYMENT) --image=$(DEMO_APP_IMAGE)
	kubectl create deployment $(BROKEN_DEMO_APP_DEPLOYMENT) --image=$(BROKEN_DEMO_APP_IMAGE)
	@echo "Waiting briefly for pods to start..."
	# Optional short sleep to allow the Deployment to initialise
	sleep 5

demo-app-down:
	@echo "Deleting deployment '$(DEMO_APP_DEPLOYMENT)'..."
	kubectl delete deployment $(DEMO_APP_DEPLOYMENT)
	kubectl delete deployment $(BROKEN_DEMO_APP_DEPLOYMENT)

## Expose the deployment as a NodePort service.
demo-app-expose:
	kubectl expose deployment $(DEMO_APP_DEPLOYMENT) \
		--name=$(DEMO_APP_DEPLOYMENT) \
		--type=NodePort \
		--port=$(KUBE_PORT) \
		--overrides='{"spec":{"ports":[{"port":'$(KUBE_PORT)',"nodePort":'$(NODE_PORT)',"protocol":"TCP"}]}}'

create-many-failures:
	@echo "Create multiple failing pods in the 'default' namespace..."
	kubectl apply -f k8s/broken-pod.yaml

destroy-many-failures:
	@echo "Destroying multiple failing pods in the 'default' namespace..."
	kubectl delete -f k8s/broken-pod.yaml

dashboard-local:
	@echo "Starting Kubera Assistant dashboard on port $(DASHBOARD_PORT)..."
	uv run streamlit run app.py

## Build the dashboard Docker image
dashboard-build:
	@echo "Building Kubera Assistant dashboard Docker image..."
	docker buildx build --platform linux/amd64 . -t json0/kubera:$(DASHBOARD_CONTAINER)

dashboard-docker: check-api-key dashboard-build
	@echo "Running Kubera Assistant dashboard in Docker on port $(DASHBOARD_PORT)..."
	docker run -p $(DASHBOARD_PORT):8501 -e OPENAI_API_KEY=$${OPENAI_API_KEY} json0/kubera:$(DASHBOARD_CONTAINER)

install-prometheus:
	@echo "Installing Prometheus in 'monitoring' namespace..."
	kubectl apply -f k8s/prometheus.yaml

destroy-prometheus:
	@echo "Removing Prometheus from the cluster..."
	kubectl delete -f k8s/prometheus.yaml

prometheus-port-forward:
	kubectl port-forward -n monitoring service/prometheus-service 9090:9090

test-prometheus:
	@echo "Testing Prometheus connection and metrics..."
	uv run test_prometheus.py

## Reset the database to apply schema changes
reset-db:
	@echo "Resetting Kubera database..."
	uv run python reset_db.py
	@echo "✅ Database reset complete"

## Clean up the database by removing old entries and merging duplicates
cleanup-db:
	@echo "Cleaning up Kubera database..."
	uv run python cleanup_db.py
	@echo "✅ Database cleanup complete"

install-argocd:
	@echo "Installing ArgoCD in 'argocd' namespace..."
	kubectl apply -f k8s/argocd.yaml
	@echo "Waiting for ArgoCD components to start..."
	kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd
	@echo "✅ ArgoCD installed successfully"
	@echo "ArgoCD UI is available at http://localhost:30080"
	@echo "Default admin username: admin"
	@echo "Run 'kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath=\"{.data.password}\" | base64 -d' to get the password"

install-argocd-full:
	@echo "Installing official ArgoCD in 'argocd' namespace..."
	kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
	@echo "Waiting for ArgoCD components to start (this may take a few minutes)..."
	kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd || true
	@echo "✅ ArgoCD installed successfully"
	@echo "To access ArgoCD UI, run: kubectl port-forward svc/argocd-server -n argocd 8080:443"
	@echo "Default admin username: admin"
	@echo "Run 'kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath=\"{.data.password}\" | base64 -d' to get the password"

uninstall-argocd:
	@echo "Removing ArgoCD from the cluster..."
	kubectl delete -f k8s/argocd.yaml
	@echo "✅ ArgoCD removed"

argocd-port-forward:
	@echo "Forwarding ArgoCD server to http://localhost:8080 (Ctrl+C to stop)"
	kubectl port-forward svc/argocd-server -n argocd 8080:80

create-demo-apps:
	@echo "Creating demo ArgoCD applications..."
	kubectl apply -f k8s/argocd-demo-apps.yaml
	@echo "✅ Demo applications created"

## Set up entire environment with cluster, apps, Prometheus, and ArgoCD
setup-all: check-api-key reset-db cluster-up install-prometheus install-argocd-core wait-for-argocd install-argocd-apps create-demo-apps demo-app-up create-many-failures
	@echo "================================================="
	@echo "✅ All done! Your complete environment is ready."
	@echo ""
	@echo "Access the dashboard:           http://localhost:$(DASHBOARD_PORT)"
	@echo "Access Prometheus:              http://localhost:30090"
	@echo "Access ArgoCD:                  http://localhost:30080"
	@echo "ArgoCD admin username:          admin"
	@echo "For ArgoCD password, run:       kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath=\"{.data.password}\" | base64 -d"
	@echo ""
	@echo "To port-forward services:"
	@echo "  Prometheus: make prometheus-port-forward"
	@echo "  ArgoCD:     make argocd-port-forward"
	@echo "================================================="

## Install just the core ArgoCD components without applications
install-argocd-core:
	@echo "Installing core ArgoCD components in 'argocd' namespace..."
	@kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
	@kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
	@echo "Core ArgoCD components installation initiated"

## Install the demo app in ArgoCD after CRDs are available
install-argocd-apps:
	@echo "Installing ArgoCD demo applications..."
	@kubectl apply -f k8s/argocd.yaml || true
	@echo "ArgoCD demo applications installed"

## Wait for ArgoCD components to be ready
wait-for-argocd:
	@echo "Waiting for ArgoCD components to start (this may take a few minutes)..."
	@kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd || true
	@kubectl wait --for=condition=available --timeout=300s deployment/argocd-repo-server -n argocd || true
	@kubectl wait --for=condition=available --timeout=300s deployment/argocd-application-controller -n argocd || true
	@echo "✅ ArgoCD components are ready"

## Destroy the entire environment and clean up all resources
destroy-all:
	@echo "Starting clean-up of all resources..."
	@echo "Removing failing pods..."
	@kubectl delete -f k8s/broken-pod.yaml || true
	@echo "Removing demo applications..."
	@kubectl delete deployment $(DEMO_APP_DEPLOYMENT) || true
	@kubectl delete deployment $(BROKEN_DEMO_APP_DEPLOYMENT) || true
	@kubectl delete service $(DEMO_APP_DEPLOYMENT) || true
	@echo "Removing ArgoCD applications..."
	@kubectl delete -f k8s/argocd-demo-apps.yaml || true
	@echo "Uninstalling ArgoCD..."
	@kubectl delete -f k8s/argocd.yaml || true
	@echo "Removing Prometheus..."
	@kubectl delete -f k8s/prometheus.yaml || true
	@echo "Deleting kind cluster named '$(CLUSTER_NAME)'..."
	@kind delete cluster --name $(CLUSTER_NAME)
	@echo "Resetting database..."
	@rm -f kubera.db || true
	@echo "✅ Environment destroyed successfully"

