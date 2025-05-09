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

.PHONY: cluster-up cluster-down demo-app-up demo-app-expose up dashboard dashboard-build dashboard-docker db-reset

## Check if OPENAI_API_KEY is set
check-api-key:
	@if [ -z "$$OPENAI_API_KEY" ]; then \
		echo "OPENAI_API_KEY environment variable is not set. Please set it before running."; \
		exit 1; \
	fi

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

