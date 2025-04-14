import streamlit as st
import random

class K8sAssistantPersona:
    def __init__(self):
        self.name = "KubeBot"
        self.avatar = "🤖"
        self.personality_traits = ["helpful", "technical", "precise", "friendly"]
        
        self.greetings = [
            "Hello! I'm KubeBot, your Kubernetes troubleshooter.",
            "KubeBot online and ready to diagnose your cluster issues!",
            "Greetings! How can I help with your Kubernetes environment today?"
        ]
        
        self.thinking_phrases = [
            "Scanning your cluster...",
            "Analyzing pod metrics and logs...",
            "Checking node conditions...",
            "Investigating service connections...",
            "Examining recent deployments..."
        ]
        
        self.success_phrases = [
            "I've identified the issue!",
            "Root cause detected.",
            "Analysis complete. Here's what I found:",
            "Diagnosis finished. The problem appears to be:"
        ]
        
    def get_greeting(self):
        return random.choice(self.greetings)
    
    def get_thinking_phrase(self):
        return random.choice(self.thinking_phrases)
    
    def get_success_phrase(self):
        return random.choice(self.success_phrases)
    
    def format_response(self, raw_analysis):
        """Format the raw analysis into a more personable response"""
        # Add persona flair to the response
        formatted = f"{self.get_success_phrase()}\n\n"
        
        # Process and format the raw analysis
        # For a simple prototype, we'll just add some structure
        if "OOMKilled" in raw_analysis:
            formatted += "📈 **Resource Issue Detected**\n\n"
        elif "connection" in raw_analysis.lower():
            formatted += "🔌 **Network Issue Detected**\n\n"
        elif "configuration" in raw_analysis.lower():
            formatted += "⚙️ **Configuration Issue Detected**\n\n"
        else:
            formatted += "🔍 **Analysis Results**\n\n"
        
        formatted += raw_analysis
        
        # Add a helpful suggestion if possible
        if "OOMKilled" in raw_analysis:
            formatted += "\n\n**Recommendation:** Consider increasing the memory limits for this pod or investigate memory leaks in the application."
        
        return formatted

