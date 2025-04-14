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

.PHONY: cluster-up cluster-down demo-app-up demo-app-expose up dashboard dashboard-build dashboard-docker

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

## Bring up everything in one command:
## 1) Create cluster, 2) Deploy app, 3) Expose service
up: cluster-up demo-app-up demo-app-expose
	@echo "================================================="
	@echo "All done! The cluster is up, and the service is running."
	@echo "You can try it by visiting: http://localhost:$(LOCAL_PORT)"
	@echo "================================================="

