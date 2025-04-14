import streamlit as st
import subprocess
import json
import time
import re

# Set page configuration
st.set_page_config(
    page_title="K8s RCA Assistant", 
    page_icon="🤖", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Function to call your CLI tool (adapt as needed)
def call_k8s_cli(query):
    # Replace this with actual CLI command that connects to your GPT API
    # Example: result = subprocess.run(["python", "your_cli.py", query], capture_output=True, text=True)
    # For now, we'll simulate a response
    time.sleep(1)  # Simulate processing time
    return f"Analyzing query: '{query}'...\n\nPossible root cause: Pod 'payment-service' is experiencing OOMKilled errors due to memory limits."

# Function to get cluster health
def get_cluster_status():
    # Replace with actual kubectl commands to get cluster status
    # Example: result = subprocess.run(["kubectl", "get", "nodes"], capture_output=True, text=True)
    # Simulated response for prototype
    return {
        "nodes": 3,
        "nodes_ready": 3,
        "pods": 15,
        "pods_healthy": 14,
        "recent_events": 2
    }

# Application state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# Sidebar - Cluster Overview
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/3/39/Kubernetes_logo_without_workmark.svg", width=100)
    st.title("K8s RCA Assistant")
    st.markdown("---")
    
    st.subheader("Cluster Health")
    status = get_cluster_status()
    
    col1, col2 = st.columns(2)
    col1.metric("Nodes", f"{status['nodes_ready']}/{status['nodes']}")
    col2.metric("Pods", f"{status['pods_healthy']}/{status['pods']}")
    
    st.progress(status['pods_healthy'] / status['pods'])
    
    st.markdown("---")
    st.subheader("Recent Events")
    st.info(f"{status['recent_events']} new events detected")
    
    # API Configuration (placeholder)
    with st.expander("Configure API"):
        st.text_input("API Key", type="password")
        st.selectbox("Model", ["gpt-4", "claude-3.5-sonnet", "claude-3-opus"])
        st.slider("Temperature", 0.0, 1.0, 0.7)

# Main content area - Chat Interface
st.title("Kubernetes Root Cause Analysis Assistant")
st.markdown("Ask me about any issues in your Kubernetes cluster, and I'll help diagnose the root cause.")

# Chat history display
chat_container = st.container()
with chat_container:
    for message in st.session_state.chat_history:
        if message["role"] == "user":
            st.markdown(f"**You:** {message['content']}")
        else:
            st.markdown(f"**K8s Assistant:** {message['content']}")
    
# Input area
user_query = st.text_area("Your question:", placeholder="e.g., Why is the payment-service pod crashing?", height=100)
if st.button("Ask Assistant"):
    if user_query:
        # Add user message to chat
        st.session_state.chat_history.append({"role": "user", "content": user_query})
        
        # Get response from CLI tool
        with st.spinner("Analyzing your cluster..."):
            response = call_k8s_cli(user_query)
        
        # Add assistant response to chat
        st.session_state.chat_history.append({"role": "assistant", "content": response})
        
        # Rerun to update the display
        st.experimental_rerun()

# Bottom section - Debugging Tools
st.markdown("---")
with st.expander("Debug Tools"):
    tab1, tab2, tab3 = st.tabs(["Logs", "Resources", "Traces"])
    
    with tab1:
        st.text_area("Recent Logs", height=150, value="2023-04-14T10:15:32 payment-service-5d4f9b8c76-2xkvp OOMKilled", disabled=True)
    
    with tab2:
        st.bar_chart({"payment-service": 95, "auth-service": 40, "frontend": 30})
    
    with tab3:
        st.text("Tracing data will appear here...")

# Footer
st.markdown("---")
st.markdown("*K8s RCA Assistant - A project by Jason Birchall*")
