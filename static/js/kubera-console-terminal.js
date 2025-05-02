// kubera-console-terminal.js
// A simple console-style terminal for Kubera's Pod Details panel

(function() {
  // Terminal class - create a self-contained terminal UI
  class ConsoleTerminal {
    constructor(container, options = {}) {
      this.container = container;
      this.options = Object.assign({
        height: '300px',
        theme: {
          prompt: '#f0d780',           // Yellowish prompt
          command: '#f0d780',          // Yellowish command text
          output: '#a0a0a0',           // Medium gray for output
          header: '#c0c0c0',           // Light gray for headers
          important: '#8eb4e6',        // Light blue for important info
          error: '#ff7b7b',            // Light red for errors
          success: '#a8e6a8'           // Light green for success
        },
        fontSize: '14px',
        promptText: '~//kubERA $ ',
        typeDelay: 7                  // Faster typing for better UX
      }, options);
      
      this.lines = [];
      this.isAnalyzing = false;
      this.metadata = null;
      
      this.init();
    }
    
    init() {
      // Create terminal elements
      this.terminalEl = document.createElement('div');
      this.terminalEl.className = 'kubera-console-terminal';
      this.terminalEl.style.backgroundColor = this.options.theme.background;
      this.terminalEl.style.color = this.options.theme.text;
      this.terminalEl.style.fontFamily = 'Consolas, "Courier New", monospace';
      this.terminalEl.style.fontSize = this.options.fontSize;
      this.terminalEl.style.padding = '8px';
      this.terminalEl.style.overflowY = 'auto';
      this.terminalEl.style.marginTop = '10px';
      this.terminalEl.style.border = '1px solid #444';
      
      // Create terminal output container
      this.outputEl = document.createElement('pre');
      this.outputEl.className = 'terminal-output';
      this.outputEl.style.margin = '0';
      this.outputEl.style.fontFamily = 'inherit';
      this.outputEl.style.whiteSpace = 'pre-wrap';
      this.outputEl.style.lineHeight = '1.3';
      
      // Add to terminal
      this.terminalEl.appendChild(this.outputEl);
      
      // Add terminal to container
      this.container.appendChild(this.terminalEl);
    }
    
    addLine(content, type = 'text', delay = this.options.typeDelay) {
      return new Promise(resolve => {
        // For prompt lines, prepend prompt
        let displayContent = content;
        if (type === 'command') {
          displayContent = this.options.promptText + content;
        }
        
        // For immediate display (no typing effect)
        if (delay <= 0 || type === 'raw') {
          this.appendToOutput(displayContent, type);
          this.scrollToBottom();
          resolve();
          return;
        }
        
        // For typing effect
        let charIndex = 0;
        const typeChar = () => {
          if (charIndex < displayContent.length) {
            // Display up to current character
            this.appendToOutput(displayContent.substring(0, charIndex + 1), type, true);
            charIndex++;
            setTimeout(typeChar, delay);
          } else {
            resolve();
          }
        };
        
        // Start typing
        typeChar();
      });
    }
    
    appendToOutput(text, type = 'text', isPartial = false) {
      // If partial, replace the last line
      if (isPartial && this.outputEl.lastChild) {
        this.outputEl.lastChild.textContent = text;
        return;
      }
      
      // Create a new line
      const line = document.createElement('div');
      line.textContent = text;
      
      // Apply styles based on line type
      switch (type) {
        case 'command':
          line.style.color = this.options.theme.command;
          break;
        case 'header':
          line.style.color = this.options.theme.header;
          line.style.fontWeight = 'bold';
          break;
        case 'important':
          line.style.color = this.options.theme.important;
          break;
        case 'error':
          line.style.color = this.options.theme.error;
          break;
        case 'success':
          line.style.color = this.options.theme.success;
          break;
        case 'raw':
          // No special styling for raw output
          break;
        default:
          line.style.color = this.options.theme.output;
      }
      
      this.outputEl.appendChild(line);
      this.scrollToBottom();
    }
    
    scrollToBottom() {
      this.terminalEl.scrollTop = this.terminalEl.scrollHeight;
    }
    
    async analyze(metadata) {
      try {
        this.isAnalyzing = true;
        this.metadata = metadata;
        
        // Show initial command
        await this.addLine('kubectl describe pod ' + metadata.pod_name, 'command');
        
        // Parse and display metadata in a simple kubectl-like format
        await this.addLine('Name:         ' + metadata.pod_name, 'output', 0);
        await this.addLine('Namespace:    ' + metadata.namespace, 'output', 0);
        await this.addLine('Alert Type:   ' + metadata.issue_type, 'output', 0);
        await this.addLine('Severity:     ' + metadata.severity, 'output', 0);
        
        // Brief pause before analysis
        await new Promise(resolve => setTimeout(resolve, 800));
        
        // Start analysis with another command
        await this.addLine('kubera analyze pod ' + metadata.pod_name, 'command');
        
        // Processing message
        await this.addLine('Analyzing pod issues...', 'output', 0);
        
        // Brief pause to simulate work
        await new Promise(resolve => setTimeout(resolve, 1200));
        
        // Get analysis results
        const results = await this.getAnalysisData(metadata);
        
        // Output header
        await this.addLine('\nROOT CAUSE ANALYSIS', 'header', 0);
        await this.addLine('----------------', 'header', 0);
        
        // Output root cause
        await this.addLine('ISSUE DETECTED: ' + metadata.issue_type, 'important', 0);
        await this.addLine(results.rootCause, 'output', 0);
        
        // Output recommendations
        await this.addLine('\nRECOMMENDED ACTIONS:', 'header', 0);
        await this.addLine('-------------------', 'header', 0);
        
        for (let i = 0; i < results.recommendations.length; i++) {
          await this.addLine(`${i+1}. ${results.recommendations[i]}`, 'output', 0);
        }
        
        // Completion message
        await this.addLine('\nAnalysis complete.', 'success', 0);
        await this.addLine(this.options.promptText, 'command', 0);
        
      } catch (error) {
        await this.addLine('Error during analysis: ' + error.message, 'error', 0);
      } finally {
        this.isAnalyzing = false;
        this.scrollToBottom();
      }
    }
    
    getAnalysisData(metadata) {
      // This would be replaced with a real API call in production
      return new Promise(resolve => {
        setTimeout(() => {
          // Mock responses based on issue type
          const responses = {
            'CrashLoopBackOff': {
              rootCause: 'The pod is repeatedly crashing immediately after startup. This is typically caused by application errors, misconfiguration, or issues with dependent services.',
              recommendations: [
                'Check application logs with: kubectl logs ' + metadata.pod_name + ' -n ' + metadata.namespace,
                'Verify environment variables and configuration',
                'Check if required services are accessible from the pod',
                'Examine the liveness probe configuration, it may be failing too quickly'
              ]
            },
            'PodOOMKilled': {
              rootCause: 'The container was terminated because it exceeded its memory limits (Out Of Memory). The application is using more memory than allocated.',
              recommendations: [
                'Increase memory limits in pod specification',
                'Check for memory leaks in the application',
                'Review recent changes that might have increased memory usage',
                'Consider implementing horizontal pod autoscaling'
              ]
            },
            'ImagePullError': {
              rootCause: 'Kubernetes cannot pull the specified container image. This may be due to incorrect image name, missing credentials, or network issues.',
              recommendations: [
                'Verify image name and tag are correct in deployment spec',
                'Check if the image exists in the repository',
                'Ensure pull secrets are correctly configured',
                'Verify network connectivity to the image registry'
              ]
            },
            'FailedScheduling': {
              rootCause: 'The Kubernetes scheduler cannot find a suitable node to place the pod. This might be due to insufficient resources or node constraints.',
              recommendations: [
                'Check node resources with: kubectl describe nodes',
                'Review resource requests and limits in the pod spec',
                'Check for node taints that might be preventing scheduling',
                'Verify node affinity/anti-affinity rules if configured'
              ]
            },
            'default': {
              rootCause: 'Multiple potential causes for this issue were identified, requiring further investigation.',
              recommendations: [
                'Examine pod events: kubectl describe pod ' + metadata.pod_name + ' -n ' + metadata.namespace,
                'Check pod logs: kubectl logs ' + metadata.pod_name + ' -n ' + metadata.namespace,
                'Verify resource requirements are properly set',
                'Check network policies and service dependencies'
              ]
            }
          };
          
          // Select response based on issue type or use default
          const issueType = metadata.issue_type;
          resolve(responses[issueType] || responses.default);
        }, 1000);
      });
    }
  }
  
  // Function to add the terminal to the Pod Details panel
  function addTerminalToPodDetailsPanel() {
    // Use MutationObserver to detect when the Pod Details panel appears
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'childList') {
          // Look for Pod Details panel - adjust selectors to match your UI
          const podDetailsPanel = document.querySelector('.pod-detail-panel, #pod-details, .pod-details');
          
          // If Panel exists and doesn't already have a terminal
          if (podDetailsPanel && !podDetailsPanel.querySelector('.kubera-console-terminal')) {
            // Extract metadata from the panel
            const metadata = extractPodDetailsMetadata(podDetailsPanel);
            
            // Create a container for the terminal
            const terminalContainer = document.createElement('div');
            terminalContainer.className = 'console-terminal-container';
            
            // Add a simple header
            const header = document.createElement('div');
            header.style.marginTop = '20px';
            header.style.fontWeight = 'bold';
            header.style.color = '#c0c0c0';
            header.textContent = 'Terminal';
            terminalContainer.appendChild(header);
            
            // Find a good place to insert the terminal
            let inserted = false;
            const sections = podDetailsPanel.querySelectorAll('h3, h4, .section-title');
            
            for (const section of sections) {
              if (section.textContent.includes('Activities') || 
                  section.textContent.includes('Events') ||
                  section.textContent.includes('Recent')) {
                // Insert after this section container
                let sectionContainer = section.closest('div');
                if (sectionContainer) {
                  sectionContainer.parentNode.insertBefore(terminalContainer, sectionContainer.nextSibling);
                  inserted = true;
                  break;
                }
              }
            }
            
            // If we couldn't find a good section, just append to the panel
            if (!inserted) {
              podDetailsPanel.appendChild(terminalContainer);
            }
            
            // Create and start the terminal
            const terminal = new ConsoleTerminal(terminalContainer, {
              height: '250px',
              promptText: 'kubera> '
            });
            
            terminal.analyze(metadata);
            
            // Once we've added the terminal, disconnect the observer
            observer.disconnect();
          }
        }
      }
    });
    
    // Start observing the whole document
    observer.observe(document.body, { childList: true, subtree: true });
    
    // Also check immediately in case the panel is already present
    const podDetailsPanel = document.querySelector('.pod-detail-panel, #pod-details, .pod-details');
    if (podDetailsPanel && !podDetailsPanel.querySelector('.kubera-console-terminal')) {
      const metadata = extractPodDetailsMetadata(podDetailsPanel);
      
      const terminalContainer = document.createElement('div');
      terminalContainer.className = 'console-terminal-container';
      
      const header = document.createElement('div');
      header.style.marginTop = '20px';
      header.style.fontWeight = 'bold';
      header.style.color = '#c0c0c0';
      header.textContent = 'Terminal';
      terminalContainer.appendChild(header);
      
      podDetailsPanel.appendChild(terminalContainer);
      
      const terminal = new ConsoleTerminal(terminalContainer, {
        height: '250px',
        promptText: 'kubera> '
      });
      
      terminal.analyze(metadata);
    }
  }
  
  // Extract metadata from Pod Details panel
  function extractPodDetailsMetadata(panel) {
    // This function attempts to extract pod metadata from the panel content
    const metadata = {
      pod_name: '',
      namespace: '',
      issue_type: '',
      severity: 'unknown',
      source: 'kubernetes'
    };
    
    // Try to find elements containing pod info
    try {
      // Look for direct value elements
      const podNameEl = panel.querySelector('[data-field="pod-name"], .pod-name, [id*="pod-name"]');
      if (podNameEl) metadata.pod_name = podNameEl.textContent.trim();
      
      const namespaceEl = panel.querySelector('[data-field="namespace"], .namespace, [id*="namespace"]');
      if (namespaceEl) metadata.namespace = namespaceEl.textContent.trim();
      
      const issueTypeEl = panel.querySelector('[data-field="issue-type"], .issue-type, [id*="issue-type"]');
      if (issueTypeEl) metadata.issue_type = issueTypeEl.textContent.trim();
      
      // If we couldn't find them directly, look for labeled fields
      if (!metadata.pod_name || !metadata.namespace || !metadata.issue_type) {
        const labelElements = panel.querySelectorAll('dt, th, [class*="label"], [class*="key"]');
        
        for (const labelEl of labelElements) {
          const labelText = labelEl.textContent.trim().toLowerCase();
          const valueEl = labelEl.nextElementSibling;
          
          if (valueEl) {
            const value = valueEl.textContent.trim();
            
            if (!metadata.pod_name && (labelText.includes('pod') || labelText.includes('name'))) {
              metadata.pod_name = value;
            }
            
            if (!metadata.namespace && labelText.includes('namespace')) {
              metadata.namespace = value;
            }
            
            if (!metadata.issue_type && (labelText.includes('issue') || labelText.includes('alert') || labelText.includes('type'))) {
              metadata.issue_type = value;
            }
            
            if (!metadata.severity && labelText.includes('severity')) {
              metadata.severity = value.toLowerCase();
            }
          }
        }
      }
      
      // If still no pod name, look for it in any heading
      if (!metadata.pod_name) {
        const header = panel.querySelector('h1, h2, h3, h4, [class*="title"]');
        if (header) metadata.pod_name = header.textContent.trim();
      }
      
      // If no issue type, try to get it from URL or any available context
      if (!metadata.issue_type) {
        // Check for badges or status elements
        const badge = document.querySelector('.badge, [class*="status"], [class*="badge"]');
        if (badge) metadata.issue_type = badge.textContent.trim();
      }
      
    } catch (e) {
      console.error('Error extracting pod metadata:', e);
    }
    
    // Set fallbacks for any missing values
    if (!metadata.pod_name) metadata.pod_name = 'unknown-pod';
    if (!metadata.namespace) metadata.namespace = 'default';
    if (!metadata.issue_type) metadata.issue_type = 'CrashLoopBackOff'; // Default to common issue
    
    return metadata;
  }
  
  // Initialize when the document is ready
  document.addEventListener('DOMContentLoaded', () => {
    // Start looking for Pod Details panel
    addTerminalToPodDetailsPanel();
    
    // Also listen for clicks that might trigger the panel to appear
    document.addEventListener('click', () => {
      // Wait a short time for any panel to appear
      setTimeout(() => {
        addTerminalToPodDetailsPanel();
      }, 300);
    });
  });
})();
