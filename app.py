import streamlit as st
import time
import random
import pandas as pd
import matplotlib.pyplot as plt

# Import our persona
from k8s_assistant_persona import K8sAssistantPersona

# Initialize the assistant persona
assistant = K8sAssistantPersona()

# Set page configuration
st.set_page_config(
    page_title=f"{assistant.name} - K8s RCA Assistant", 
    page_icon=assistant.avatar, 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for a more interactive look
st.markdown("""
<style>
    /* Main container styling */
    .main {
        background-color: #f5f7ff;
    }
    
    /* Chat bubbles */
    .user-bubble {
        background-color: #e6f7ff;
        border-radius: 15px;
        color: black;
        padding: 10px 15px;
        margin: 5px 0;
        border-bottom-right-radius: 0;
        display: inline-block;
        max-width: 80%;
        align-self: flex-end;
    }
    
    .assistant-bubble {
        background-color: #f0f2f6;
        color: black;
        border-radius: 15px;
        padding: 10px 15px;
        margin: 5px 0;
        border-bottom-left-radius: 0;
        display: inline-block;
        max-width: 80%;
        align-self: flex-start;
    }
    
    /* Robot avatar animation */
    .robot-container {
        text-align: center;
        margin-bottom: 20px;
    }
    
    .robot-avatar {
        font-size: 4rem;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.1); }
        100% { transform: scale(1); }
    }
    
    /* Button styling */
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        border-radius: 20px;
        padding: 10px 20px;
        font-weight: bold;
        border: none;
        transition: all 0.3s;
    }
    
    .stButton>button:hover {
        background-color: #45a049;
        transform: translateY(-2px);
    }
    
    /* Status indicators */
    .status-indicator {
        height: 10px;
        width: 10px;
        background-color: #4CAF50;
        border-radius: 50%;
        display: inline-block;
        margin-right: 5px;
    }
    
    .status-warning {
        background-color: #ff9800;
    }
    
    .status-error {
        background-color: #f44336;
    }
</style>
""", unsafe_allow_html=True)

# Function to simulate calling your CLI tool
def call_k8s_cli(query):
    # Simulate thinking/processing time
    for _ in range(3):
        time.sleep(0.7)
        st.write(assistant.get_thinking_phrase())
    
    # Here you would actually call your CLI that connects to GPT API
    # For prototype, we'll simulate different responses based on query keywords
    if "crash" in query.lower() or "error" in query.lower():
        return "Pod 'payment-service' is experiencing OOMKilled errors. Memory usage spiked to 95% before the crash. This typically happens when a container tries to use more memory than its limit. Looking at the logs, there appears to be a memory leak in the payment processing function that occurs during high transaction volume."
    elif "slow" in query.lower() or "performance" in query.lower():
        return "The 'auth-service' is experiencing high latency. Analysis shows CPU throttling due to resource limits being hit during peak usage. The service is configured with only 0.5 CPU cores, but recent traffic spikes are requiring more processing power. Consider scaling this deployment horizontally or increasing CPU limits."
    elif "network" in query.lower() or "connection" in query.lower():
        return "There appears to be network connectivity issues between the 'frontend' and 'api-gateway' services. The CoreDNS pods are functioning correctly, but there's a NetworkPolicy that may be blocking traffic. Found a policy 'restrict-traffic' that only allows connections from namespaces with label 'tier: frontend', but your frontend service is in a namespace missing this label."
    else:
        return "I've analyzed the cluster and everything seems to be running normally. All pods are in a Ready state, no recent OOMKilled events, and resource usage is within expected ranges. Is there a specific issue you're concerned about?"

# Function to get cluster health (simulated for prototype)
def get_cluster_status():
    # In a real implementation, this would use your CLI to query the cluster
    return {
        "nodes": 3,
        "nodes_ready": 3,
        "pods": 15,
        "pods_healthy": 14,
        "recent_events": 2,
        "namespaces": ["default", "kube-system", "monitoring", "application"],
        "services_status": {
            "payment-service": "Warning",
            "auth-service": "Healthy",
            "frontend": "Healthy",
            "api-gateway": "Healthy",
            "database": "Healthy"
        }
    }

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
    # Add greeting message
    st.session_state.chat_history.append({
        "role": "assistant", 
        "content": assistant.get_greeting()
    })

# Sidebar - Cluster Overview
with st.sidebar:
    st.image("https://kubernetes.io/images/kubernetes-horizontal-color.png", width=200)
    
    # Robot avatar animation
    st.markdown(f"""
    <div class="robot-container">
        <div class="robot-avatar">{assistant.avatar}</div>
        <h2>{assistant.name}</h2>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Cluster Health Section
    st.subheader("Cluster Health")
    status = get_cluster_status()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Nodes", f"{status['nodes_ready']}/{status['nodes']}")
    col2.metric("Pods", f"{status['pods_healthy']}/{status['pods']}")
    col3.metric("Events", status['recent_events'])
    
    # Service Status
    st.subheader("Service Status")
    for service, health in status['services_status'].items():
        status_color = "status-indicator"
        if health == "Warning":
            status_color += " status-warning"
        elif health == "Error":
            status_color += " status-error"
            
        st.markdown(f"""
        <div>
            <span class="{status_color}"></span>
            {service}: {health}
        </div>
        """, unsafe_allow_html=True)
    
    # Namespaces
    with st.expander("Namespaces"):
        for ns in status['namespaces']:
            st.markdown(f"• {ns}")
    
    # Configuration
    with st.expander("Configuration"):
        st.selectbox("Model", ["gpt-4", "claude-3.5-sonnet", "claude-3-opus"])
        st.slider("Temperature", 0.0, 1.0, 0.7)
        st.checkbox("Show debug info", value=False)

# Main content area
st.title(f"Kubernetes Root Cause Analysis Assistant")
st.markdown("Ask me about any issues in your Kubernetes cluster, and I'll help diagnose the root cause.")

# Chat history display with styled bubbles
for message in st.session_state.chat_history:
    if message["role"] == "user":
        st.markdown(f"""
        <div style="display: flex; justify-content: flex-end;">
            <div class="user-bubble">
                <strong>You:</strong><br>{message['content']}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="display: flex; justify-content: flex-start;">
            <div class="assistant-bubble">
                <strong>{assistant.name}:</strong><br>{message['content']}
            </div>
        </div>
        """, unsafe_allow_html=True)

# User input area
st.markdown("---")
user_query = st.text_area("Your question:", placeholder="e.g., Why is the payment-service pod crashing?", height=100)

col1, col2 = st.columns([1, 5])
with col1:
    ask_button = st.button("Ask")

# Process user input
if ask_button and user_query:
    # Add user message to chat
    st.session_state.chat_history.append({"role": "user", "content": user_query})
    
    # Get response from CLI tool with streaming effect
    with st.spinner("Processing your query..."):
        raw_response = call_k8s_cli(user_query)
        
    # Format response with our persona
    formatted_response = assistant.format_response(raw_response)
    
    # Add assistant response to chat
    st.session_state.chat_history.append({"role": "assistant", "content": formatted_response})
    
    # Rerun to update the display
    st.experimental_rerun()

# Visualizations and Debug section
st.markdown("---")
tabs = st.tabs(["Resource Usage", "Recent Logs", "Event Timeline"])

with tabs[0]:
    # Simulated resource data
    resource_data = pd.DataFrame({
        'Service': ['payment-service', 'auth-service', 'frontend', 'api-gateway', 'database'],
        'CPU (cores)': [0.85, 0.4, 0.3, 0.25, 0.6],
        'Memory (GB)': [1.8, 0.9, 0.5, 0.4, 1.2],
        'Limit CPU': [1.0, 0.5, 0.5, 0.5, 1.0],
        'Limit Memory': [2.0, 1.0, 1.0, 0.5, 2.0]
    })
    
    st.dataframe(resource_data)
    
    # Simple bar chart
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    
    # CPU Usage
    ax[0].bar(resource_data['Service'], resource_data['CPU (cores)'], color='skyblue')
    ax[0].plot(resource_data['Service'], resource_data['Limit CPU'], 'r--')
    ax[0].set_title('CPU Usage vs Limit')
    ax[0].set_ylabel('CPU (cores)')
    ax[0].tick_params(axis='x', rotation=45)
    
    # Memory Usage
    ax[1].bar(resource_data['Service'], resource_data['Memory (GB)'], color='lightgreen')
    ax[1].plot(resource_data['Service'], resource_data['Limit Memory'], 'r--')
    ax[1].set_title('Memory Usage vs Limit')
    ax[1].set_ylabel('Memory (GB)')
    ax[1].tick_params(axis='x', rotation=45)
    
    fig.tight_layout()
    st.pyplot(fig)

with tabs[1]:
    log_entries = [
        "2023-04-14T10:15:32 payment-service-5d4f9b8c76-2xkvp [INFO] Processing transaction batch #45892",
        "2023-04-14T10:15:35 payment-service-5d4f9b8c76-2xkvp [WARN] Memory usage high: 85%",
        "2023-04-14T10:15:40 payment-service-5d4f9b8c76-2xkvp [ERROR] Java heap space",
        "2023-04-14T10:15:42 payment-service-5d4f9b8c76-2xkvp [FATAL] Container killed due to OOM",
        "2023-04-14T10:16:01 kubelet-node-1 [INFO] Restarting container: payment-service"
    ]
    
    for log in log_entries:
        if "[ERROR]" in log or "[FATAL]" in log:
            st.error(log)
        elif "[WARN]" in log:
            st.warning(log)
        else:
            st.info(log)

with tabs[2]:
    events = [
        {"time": "10:14:00", "event": "Normal", "message": "auth-service scaled to 3 replicas"},
        {"time": "10:15:00", "event": "Normal", "message": "Batch job payment-processor started"},
        {"time": "10:15:42", "event": "Warning", "message": "payment-service OOMKilled"},
        {"time": "10:16:01", "event": "Normal", "message": "payment-service container restarted"},
        {"time": "10:18:30", "event": "Normal", "message": "Horizontal Pod Autoscaler increased replicas"}
    ]
    
    event_df = pd.DataFrame(events)
    st.dataframe(event_df, use_container_width=True)

# Footer
st.markdown("---")
st.markdown("*This is a prototype implementation for Jason Birchall's final project. Simulated data only.*")
