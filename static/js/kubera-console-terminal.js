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
      this.cache = new Map(); // Simple in-memory cache for API responses
      this.cacheTimeout = 5 * 60 * 1000; // 5 minutes cache timeout
      
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
        await this.addLine('kubectl describe pod ' + metadata.pod_name + ' -n ' + metadata.namespace, 'command');
        
        // Show loading animation while fetching real data
        await this.addLine('Fetching pod details...', 'output', 0);
        
        // Get real analysis results from the API
        const results = await this.getRealAnalysisData(metadata);
        
        // Clear loading message and show real kubectl-style output
        this.clearLastLine();
        
        // Display basic pod info from real metadata
        if (results.metadata) {
          await this.addLine('Name:         ' + results.metadata.pod_name, 'output', 0);
          await this.addLine('Namespace:    ' + results.metadata.namespace, 'output', 0);
          await this.addLine('Containers:   ' + results.metadata.containers.length, 'output', 0);
          await this.addLine('Events:       ' + results.metadata.events_count + ' recent events', 'output', 0);
        }
        
        // Brief pause before analysis
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Start AI analysis
        await this.addLine('\nkubera analyze pod ' + metadata.pod_name, 'command');
        await this.addLine('🤖 Analyzing with AI...', 'output', 0);
        
        // Brief pause to show AI is working
        await new Promise(resolve => setTimeout(resolve, 800));
        
        // Clear AI message and show results
        this.clearLastLine();
        
        // Add separator line for visual clarity
        await this.addLine('─'.repeat(60), 'separator', 0);
        
        // Output root cause analysis with enhanced formatting
        await this.addLine('\n🔍 ROOT CAUSE ANALYSIS', 'analysis-header', 0);
        await this.addLine('─'.repeat(25), 'separator', 0);
        
        // Format root cause with better line breaks
        const rootCauseText = results.rootCause || 'Unable to determine root cause';
        const rootCauseLines = this.wrapText(rootCauseText, 80);
        for (const line of rootCauseLines) {
          await this.addLine(line, 'analysis-content', 0);
        }
        
        // Output recommendations with enhanced formatting
        await this.addLine('\n🛠️  RECOMMENDED ACTIONS', 'analysis-header', 0);
        await this.addLine('─'.repeat(25), 'separator', 0);
        
        if (results.recommendations && results.recommendations.length > 0) {
          for (let i = 0; i < results.recommendations.length; i++) {
            const recommendation = results.recommendations[i];
            await this.addLine(`\n${i+1}. ${recommendation}`, 'recommendation', 0);
            
            // Add subtle spacing between recommendations
            if (i < results.recommendations.length - 1) {
              await this.addLine('', 'output', 0);
            }
          }
        } else {
          await this.addLine('No specific recommendations available', 'analysis-content', 0);
        }
        
        // Show kubectl commands if available with copy functionality
        if (results.kubectl_commands) {
          await this.addLine('\n⚡ KUBECTL COMMANDS TO RUN', 'analysis-header', 0);
          await this.addLine('─'.repeat(30), 'separator', 0);
          
          const commands = results.kubectl_commands.split('\n');
          for (const cmd of commands) {
            const trimmedCmd = cmd.trim();
            if (trimmedCmd) {
              // Check if this is an actual kubectl command or just explanatory text
              if (this.isKubectlCommand(trimmedCmd)) {
                // Remove any markdown backticks and add with copy functionality
                const cleanCmd = this.cleanMarkdownFromCommand(trimmedCmd);
                await this.addCommandWithCopy(cleanCmd);
              } else {
                // This is explanatory text, add as regular output without copy button
                await this.addLine(trimmedCmd, 'output', 0);
              }
            }
          }
        }
        
        // Enhanced completion message with summary
        await this.addLine('\n' + '─'.repeat(60), 'separator', 0);
        await this.addLine('✅ AI-powered analysis complete', 'success', 0);
        
        // Add performance metrics if available
        if (results.metadata) {
          const analysisTime = new Date(results.metadata.timestamp);
          await this.addLine(`📊 Analysis completed at ${analysisTime.toLocaleTimeString()}`, 'metadata-info', 0);
        }
        
        await this.addLine('\n' + this.options.promptText, 'command', 0);
        
      } catch (error) {
        console.error('Analysis error:', error);
        await this.addLine('\n❌ Error during analysis: ' + error.message, 'error', 0);
        await this.addLine('Falling back to basic troubleshooting...', 'output', 0);
        
        // Provide basic fallback recommendations
        await this.addLine('\nBasic troubleshooting steps:', 'header', 0);
        await this.addLine('1. Check pod logs: kubectl logs ' + metadata.pod_name + ' -n ' + metadata.namespace, 'output', 0);
        await this.addLine('2. Check pod events: kubectl describe pod ' + metadata.pod_name + ' -n ' + metadata.namespace, 'output', 0);
        await this.addLine('3. Check pod status: kubectl get pod ' + metadata.pod_name + ' -n ' + metadata.namespace + ' -o yaml', 'output', 0);
        
      } finally {
        this.isAnalyzing = false;
        this.scrollToBottom();
      }
    }
    
    async getRealAnalysisData(metadata) {
      // Create cache key based on namespace and pod name
      const cacheKey = `${metadata.namespace}:${metadata.pod_name}`;
      
      // Check cache first
      const cachedResult = this.cache.get(cacheKey);
      if (cachedResult && (Date.now() - cachedResult.timestamp) < this.cacheTimeout) {
        console.log('Using cached analysis result');
        return cachedResult.data;
      }
      
      // Make real API call to the pod diagnosis endpoint
      try {
        const namespace = metadata.namespace;
        const podName = metadata.pod_name;
        
        const response = await fetch(`/api/pod-diagnosis/${namespace}/${podName}`);
        
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        // Cache the successful result
        this.cache.set(cacheKey, {
          data: data,
          timestamp: Date.now()
        });
        
        // Clean up old cache entries
        this.cleanupCache();
        
        return data;
        
      } catch (error) {
        console.error('API call failed:', error);
        throw new Error(`Failed to get AI analysis: ${error.message}`);
      }
    }
    
    cleanupCache() {
      // Remove entries older than cache timeout
      const now = Date.now();
      for (const [key, value] of this.cache.entries()) {
        if (now - value.timestamp > this.cacheTimeout) {
          this.cache.delete(key);
        }
      }
    }
    
    clearLastLine() {
      // Helper method to remove the last line (useful for clearing loading messages)
      const lines = this.outputEl.querySelectorAll('.line');
      if (lines.length > 0) {
        const lastLine = lines[lines.length - 1];
        lastLine.remove();
      }
    }
    
    wrapText(text, maxLength) {
      // Helper method to wrap long text into multiple lines
      const words = text.split(' ');
      const lines = [];
      let currentLine = '';
      
      for (const word of words) {
        if ((currentLine + word).length <= maxLength) {
          currentLine += (currentLine ? ' ' : '') + word;
        } else {
          if (currentLine) {
            lines.push(currentLine);
            currentLine = word;
          } else {
            // Word is longer than maxLength, just add it
            lines.push(word);
          }
        }
      }
      
      if (currentLine) {
        lines.push(currentLine);
      }
      
      return lines;
    }
    
    async addCommandWithCopy(command) {
      // Add a command line with copy-to-clipboard functionality
      const line = document.createElement('div');
      line.className = 'line command-with-copy';
      
      const commandText = document.createElement('span');
      commandText.className = 'command-text';
      commandText.textContent = '$ ' + command;
      
      const copyButton = document.createElement('button');
      copyButton.className = 'copy-button';
      copyButton.innerHTML = '📋';
      copyButton.title = 'Copy to clipboard';
      copyButton.onclick = () => this.copyToClipboard(command, copyButton);
      
      line.appendChild(commandText);
      line.appendChild(copyButton);
      
      this.outputEl.appendChild(line);
      this.scrollToBottom();
      
      // Small delay for visual effect
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    async copyToClipboard(text, button) {
      try {
        await navigator.clipboard.writeText(text);
        const originalText = button.innerHTML;
        button.innerHTML = '✅';
        button.title = 'Copied!';
        
        setTimeout(() => {
          button.innerHTML = originalText;
          button.title = 'Copy to clipboard';
        }, 2000);
      } catch (err) {
        console.error('Failed to copy text: ', err);
        button.innerHTML = '❌';
        setTimeout(() => {
          button.innerHTML = '📋';
        }, 1000);
      }
    }
    
    isKubectlCommand(text) {
      // Helper method to determine if a line is an actual kubectl command
      const trimmed = text.trim();
      
      // Remove common markdown markers first
      const cleaned = trimmed.replace(/^```\w*\s*/, '').replace(/```$/, '').replace(/^`|`$/g, '').trim();
      
      // Check if it starts with kubectl or common shell patterns
      return cleaned.startsWith('kubectl ') || 
             cleaned.startsWith('$ kubectl ') ||
             cleaned.startsWith('# kubectl ') ||
             (cleaned.includes('kubectl ') && (cleaned.startsWith('$') || cleaned.startsWith('#')));
    }
    
    cleanMarkdownFromCommand(text) {
      // Helper method to clean markdown formatting from kubectl commands
      let cleaned = text.trim();
      
      // Remove markdown code block markers
      cleaned = cleaned.replace(/^```\w*\s*/, '').replace(/```$/, '');
      
      // Remove inline code markers
      cleaned = cleaned.replace(/^`|`$/g, '');
      
      // Remove shell prompt markers but preserve the command
      cleaned = cleaned.replace(/^\$\s*/, '').replace(/^#\s*/, '');
      
      return cleaned.trim();
    }
    
    // Legacy method - kept for backwards compatibility
    getAnalysisData(metadata) {
      // Redirect to real analysis
      return this.getRealAnalysisData(metadata);
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
