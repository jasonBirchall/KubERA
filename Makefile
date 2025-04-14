CLUSTER_NAME := demo-cluster
DEPLOYMENT_NAME := hello-world
SERVICE_NAME := hello-world
IMAGE_NAME := nginxdemos/hello
LOCAL_PORT := 8080
NODE_PORT := 30080
KUBE_PORT := 80
DASHBOARD_PORT := 8501
DASHBOARD_CONTAINER := 0.0.1

.PHONY: cluster deploy expose status teardown up dashboard dashboard-build dashboard-docker
## Check if OPENAI_API_KEY is set
check-api-key:
	@if [ -z "$$OPENAI_API_KEY" ]; then \
		echo "OPENAI_API_KEY environment variable is not set. Please set it before running."; \
		exit 1; \
	fi

## Create the kind cluster using the specified config.
cluster:
	@echo "Creating kind cluster named '$(CLUSTER_NAME)'..."
	kind create cluster --config kind-config.yaml

## Deploy the Hello World application.
deploy:
	@echo "Deploying '$(DEPLOYMENT_NAME)' using image '$(IMAGE_NAME)'..."
	kubectl create deployment $(DEPLOYMENT_NAME) --image=$(IMAGE_NAME)
	@echo "Waiting briefly for pods to start..."
	# Optional short sleep to allow the Deployment to initialise
	sleep 5

## Expose the deployment as a NodePort service.
expose:
	@echo "Exposing service '$(SERVICE_NAME)' on port $(KUBE_PORT) -> NodePort $(NODE_PORT)..."
	kubectl expose deployment $(DEPLOYMENT_NAME) \
		--name=$(SERVICE_NAME) \
		--type=NodePort \
		--port=$(KUBE_PORT) \
		--overrides='{"spec":{"ports":[{"port":'$(KUBE_PORT)',"nodePort":'$(NODE_PORT)',"protocol":"TCP"}]}}'

## Display the cluster status (pods, services).
status:
	@echo "Cluster info:"
	kubectl cluster-info
	@echo "\nPods:"
	kubectl get pods -o wide
	@echo "\nServices:"
	kubectl get svc -o wide

dashboard-local:
	@echo "Starting K8s Assistant dashboard on port $(DASHBOARD_PORT)..."
	uv run streamlit run app.py

## Build the dashboard Docker image
dashboard-build:
	@echo "Building K8s Assistant dashboard Docker image..."
	docker buildx build --platform linux/amd64 . -t json0/kubera:$(DASHBOARD_CONTAINER)

dashboard-docker: check-api-key dashboard-build
	@echo "Running K8s Assistant dashboard in Docker on port $(DASHBOARD_PORT)..."
	docker run -p $(DASHBOARD_PORT):8501 -e OPENAI_API_KEY=$${OPENAI_API_KEY} json0/kubera:$(DASHBOARD_CONTAINER)

## Teardown the entire kind cluster.
teardown:
	@echo "Deleting kind cluster named '$(CLUSTER_NAME)'..."
	kind delete cluster --name $(CLUSTER_NAME)

## Bring up everything in one command:
## 1) Create cluster, 2) Deploy app, 3) Expose service
up: cluster deploy expose
	@echo "================================================="
	@echo "All done! The cluster is up, and the service is running."
	@echo "You can try it by visiting: http://localhost:$(LOCAL_PORT)"
	@echo "================================================="

