#!/bin/bash

# KubERA Playground Setup Script
# This script provides an interactive setup experience for new users

set -e

echo "🎯 Welcome to KubERA Playground Setup!"
echo "======================================"
echo ""
echo "This script will help you set up a complete KubERA testing environment."
echo ""

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "⚠️  This script is designed for macOS with Homebrew."
    echo "For other platforms, please run 'make playground' directly."
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check for OpenAI API key
echo "🔑 Checking OpenAI API key..."
if [[ -z "${OPENAI_API_KEY}" ]]; then
    echo ""
    echo "❌ OPENAI_API_KEY environment variable is not set."
    echo ""
    echo "To get an API key:"
    echo "1. Visit https://platform.openai.com/api-keys"
    echo "2. Create a new API key"
    echo "3. Set it in your shell:"
    echo ""
    echo "   export OPENAI_API_KEY=\"your-api-key-here\""
    echo ""
    echo "You can also add it to your ~/.bashrc or ~/.zshrc file to persist it."
    echo ""
    read -p "Do you have an API key ready to set now? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        read -p "Enter your OpenAI API key: " -r
        export OPENAI_API_KEY="$REPLY"
        echo "✅ API key set for this session."
        echo ""
        echo "💡 To persist this, add the following to your ~/.zshrc or ~/.bashrc:"
        echo "   export OPENAI_API_KEY=\"$REPLY\""
        echo ""
    else
        echo ""
        echo "Please set your API key and run this script again."
        exit 1
    fi
else
    echo "✅ OpenAI API key is set."
fi

echo ""
echo "🏗️  Starting playground setup..."
echo ""
echo "This will:"
echo "  • Check and install dependencies (kind, kubectl, Docker, etc.)"
echo "  • Create a local Kubernetes cluster"
echo "  • Install Prometheus and ArgoCD"
echo "  • Deploy sample applications for testing"
echo "  • Set up the KubERA database"
echo ""
echo "⏱️  Estimated setup time: 5-10 minutes"
echo ""

read -p "Ready to proceed? (Y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "Setup cancelled."
    exit 0
fi

echo ""
echo "🚀 Running: make playground"
echo ""

# Run the playground setup
if make playground; then
    echo ""
    echo "🎉 Playground setup complete!"
    echo ""
    echo "🌐 Access URLs:"
    echo "  KubERA Dashboard: http://localhost:8501"
    echo "  Prometheus:       http://localhost:9090"
    echo "  ArgoCD:           http://localhost:8080"
    echo ""
    echo "🚀 To start KubERA:"
    echo "  make run"
    echo ""
    echo "Or if you prefer the interactive way:"
    read -p "Would you like to start KubERA now? (Y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        echo ""
        echo "🚀 Starting KubERA..."
        echo "Access the dashboard at: http://localhost:8501"
        echo "Press Ctrl+C to stop when you're done testing."
        echo ""
        make run
    else
        echo ""
        echo "You can start KubERA later with: make run"
    fi
else
    echo ""
    echo "❌ Playground setup failed."
    echo ""
    echo "🔧 Troubleshooting:"
    echo "  • Make sure Docker Desktop is running"
    echo "  • Check that ports 8501, 9090, 8080 are available"
    echo "  • Try: make destroy-all && make playground"
    echo ""
    echo "📚 For more help, see:"
    echo "  • PLAYGROUND.md"
    echo "  • README.md"
    echo "  • make help"
    exit 1
fi