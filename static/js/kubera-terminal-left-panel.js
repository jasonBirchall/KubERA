// kubera-terminal-left-panel.js
// A hacker terminal for Kubera's UI that integrates with the left Pod Details panel

(function() {
  // Terminal class - create a self-contained terminal UI
  class HackerTerminal {
    constructor(container, options = {}) {
      this.container = container;
      this.options = Object.assign({
        height: '300px',
        theme: {
          background: '#0c0c0c',
          text: '#33ff33', // Matrix green
          header: '#33ff99',
          error: '#ff3333',
          warning: '#ffcc00',
          info: '#33ccff',
          success: '#00ff00'
        },
        scanlines: true,
        glow: true,
        typeDelay: 50
      }, options);
      
      this.lines = [];
      this.isAnalyzing = false;
      this.metadata = null;
      this.cursorInterval = null;
      
      this.init();
    }
    
    init() {
      // Create terminal elements
      this.terminalEl = document.createElement('div');
      this.terminalEl.className = 'kubera-terminal';
      
      // Create terminal output container
      this.outputEl = document.createElement('div');
      this.outputEl.className = 'terminal-output';
      
      // Create blinking cursor
      this.cursorEl = document.createElement('span');
      this.cursorEl.className = 'terminal-cursor';
      this.cursorEl.innerHTML = '&nbsp;';
      
      // Add to terminal
      this.terminalEl.appendChild(this.outputEl);
      this.terminalEl.appendChild(this.cursorEl);
      
      // Add special effects if enabled
      if (this.options.scanlines) {
        const scanlines = document.createElement('div');
        scanlines.className = 'terminal-scanlines';
        this.terminalEl.appendChild(scanlines);
      }
      
      if (this.options.glow) {
        const glow = document.createElement('div');
        glow.className = 'terminal-glow';
        this.terminalEl.appendChild(glow);
      }
      
      // Add terminal to container
      this.container.appendChild(this.terminalEl);
      
      // Add styles
      this.addStyles();
      
      // Start cursor blinking
      this.startCursorBlink();
    }
    
    addStyles() {
      const style = document.createElement('style');
      const theme = this.options.theme;
      
      style.textContent = `
        .kubera-terminal {
          background-color: ${theme.background};
          color: ${theme.text};
          font-family: 'Courier New', monospace;
          font-size: 14px;
          padding: 16px;
          height: ${this.options.height};
          overflow-y: auto;
          border-radius: 6px;
          position: relative;
          margin-top: 20px;
        }
        
        .terminal-output {
          position: relative;
          z-index: 5;
        }
        
        .terminal-line {
          margin: 0;
          padding: 1px 0;
          line-height: 1.4;
          white-space: pre-wrap;
        }
        
        .terminal-line.header {
          color: ${theme.header};
          font-weight: bold;
        }
        
        .terminal-line.prompt {
          color: ${theme.text};
          font-weight: bold;
        }
        
        .terminal-line.error {
          color: ${theme.error};
        }
        
        .terminal-line.warning {
          color: ${theme.warning};
        }
        
        .terminal-line.info {
          color: ${theme.info};
        }
        
        .terminal-line.success {
          color: ${theme.success};
        }
        
        .terminal-cursor {
          display: inline-block;
          background-color: ${theme.text};
          width: 8px;
          height: 16px;
          position: relative;
          top: 3px;
        }
        
        .terminal-cursor.hidden {
          background-color: transparent;
        }
        
        .terminal-scanlines {
          background-image: linear-gradient(
            transparent 0%, 
            rgba(32, 128, 32, 0.2) 2%, 
            transparent 3%, 
            transparent 97%, 
            rgba(32, 128, 32, 0.2) 98%, 
            transparent 100%
          );
          background-size: 100% 6px;
          position: absolute;
          pointer-events: none;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          z-index: 2;
        }
        
        .terminal-glow {
          box-shadow: inset 0 0 20px rgba(51, 255, 51, 0.5), 0 0 10px rgba(51, 255, 51, 0.3);
          border-radius: 6px;
          position: absolute;
          pointer-events: none;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          z-index: 1;
        }
        
        .progress-bar {
          width: 100%;
          height: 4px;
          background-color: #111;
          border-radius: 2px;
          margin-top: 4px;
          overflow: hidden;
        }
        
        .progress-bar-fill {
          height: 100%;
          background-color: #ffffff;
          border-radius: 2px;
          transition: width 0.1s ease-in-out;
        }
        
        .terminal-title-bar {
          display: flex;
          justify-content: space-between;
          padding: 5px 10px;
          background-color: #0a0a0a;
          border-top-left-radius: 5px;
          border-top-right-radius: 5px;
          border-bottom: 1px solid #33ff33;
        }
        
        .terminal-title {
          color: #33ff33;
          font-family: 'Courier New', monospace;
          font-weight: bold;
          font-size: 12px;
        }
        
        .terminal-toggle {
          background: none;
          border: none;
          color: #33ff33;
          cursor: pointer;
          font-size: 16px;
        }
      `;
      
      document.head.appendChild(style);
    }
    
    startCursorBlink() {
      // Clear any existing interval
      if (this.cursorInterval) {
        clearInterval(this.cursorInterval);
      }
      
      // Start new blink interval
      this.cursorInterval = setInterval(() => {
        this.cursorEl.classList.toggle('hidden');
      }, 600);
    }
    
    stopCursorBlink() {
      if (this.cursorInterval) {
        clearInterval(this.cursorInterval);
        this.cursorInterval = null;
        this.cursorEl.classList.add('hidden');
      }
    }
    
    addLine(content, type = 'text', delay = this.options.typeDelay) {
      return new Promise(resolve => {
        // Create the line element
        const line = document.createElement('div');
        line.className = `terminal-line ${type}`;
        
        // For immediate display (no typing effect)
        if (delay <= 0) {
          line.textContent = content;
          this.outputEl.appendChild(line);
          this.scrollToBottom();
          resolve();
          return;
        }
        
        // For typing effect
        let charIndex = 0;
        const typeChar = () => {
          if (charIndex < content.length) {
            line.textContent = content.substring(0, charIndex + 1);
            charIndex++;
            setTimeout(typeChar, delay);
          } else {
            resolve();
          }
        };
        
        // Start typing and add to output
        this.outputEl.appendChild(line);
        typeChar();
        this.scrollToBottom();
      });
    }
    
    async addProgressBar(message, duration = 2000, steps = 20) {
      // Add the message
      await this.addLine(message, 'info', 0);
      
      // Create progress bar container
      const progressContainer = document.createElement('div');
      progressContainer.className = 'progress-bar';
      
      // Create progress bar fill
      const progressFill = document.createElement('div');
      progressFill.className = 'progress-bar-fill';
      progressFill.style.width = '0%';
      
      // Add to container
      progressContainer.appendChild(progressFill);
      this.outputEl.appendChild(progressContainer);
      this.scrollToBottom();
      
      // Animate the progress bar
      const stepTime = duration / steps;
      for (let i = 1; i <= steps; i++) {
        await new Promise(resolve => setTimeout(resolve, stepTime));
        progressFill.style.width = `${Math.floor((i / steps) * 100)}%`;
      }
      
      // Add completion message
      return this.addLine('Done', 'success', 0);
    }
    
    scrollToBottom() {
      this.terminalEl.scrollTop = this.terminalEl.scrollHeight;
    }
    
    async analyze(metadata) {
      try {
        this.isAnalyzing = true;
        this.metadata = metadata;
        
        // Introduction
        await this.addLine('K3R4 Terminal v1.0.0', 'header');
        await this.addLine('Kubernetes Error Root-cause Analysis System', 'info');
        await this.addLine('', 'text');
        await this.addLine('> Initializing diagnostic sequence...', 'prompt', 100);
        
        // Parse and display metadata
        await this.addLine('> Extracting metadata from event...', 'prompt', 100);
        const parsedData = this.parseMetadata();
        
        // Show metadata
        await this.addLine(`NAMESPACE: ${parsedData.namespace}`, 'text', 30);
        await this.addLine(`POD: ${parsedData.podName}`, 'text', 30);
        await this.addLine(`ALERT: ${parsedData.issueType}`, 'text', 30);
        await this.addLine(`SEVERITY: ${parsedData.severity}`, 'text', 30);
        
        // Loading animations
        await this.addProgressBar('> Scanning for known error patterns...', 1800);
        await this.addProgressBar('> Analyzing pod lifecycle events...', 1200);
        await this.addProgressBar('> Processing container status information...', 1500);
        
        // Contact "AI"
        await this.addLine('> Connecting to central neural network...', 'prompt', 100);
        await this.addLine('Transmitting data payload...', 'info', 80);
        
        // Simulate or call API
        await this.addLine('> Running deep analysis on issue pattern...', 'prompt', 100);
        const results = await this.simulateApiCall(parsedData);
        
        // Display results
        await this.addLine('', 'text');
        await this.addLine('=== ANALYSIS COMPLETE ===', 'header');
        await this.addLine('', 'text');
        await this.addLine('ROOT CAUSE:', 'header');
        await this.addLine(results.rootCause, 'text', 20);
        await this.addLine('', 'text');
        await this.addLine('RECOMMENDED ACTIONS:', 'header');
        
        for (const recommendation of results.recommendations) {
          await this.addLine(`· ${recommendation}`, 'text', 30);
        }
        
        await this.addLine('', 'text');
        await this.addLine('> Analysis completed successfully', 'success');
        
      } catch (error) {
        await this.addLine(`ERROR: ${error.message || 'Unknown error during analysis'}`, 'error', 0);
      } finally {
        this.isAnalyzing = false;
        this.scrollToBottom();
      }
    }
    
    parseMetadata() {
      // Extract data from metadata
      return {
        namespace: this.metadata.namespace || 'unknown',
        podName: this.metadata.pod_name || this.metadata.name || 'unknown',
        source: this.metadata.source || 'kubernetes',
        issueType: this.metadata.issue_type || 'unknown',
        severity: this.metadata.severity || 'low',
        timestamp: this.metadata.timestamp || this.metadata.first_seen || new Date().toISOString()
      };
    }
    
    simulateApiCall(formattedData) {
      // This would be replaced with a real API call in production
      return new Promise(resolve => {
        setTimeout(() => {
          // Mock responses
          const responses = {
            'CrashLoopBackOff': {
              rootCause: 'Application is crashing immediately after startup. This could be due to misconfiguration, invalid environment variables, or application bugs.',
              recommendations: [
                'Check application logs for error messages',
                'Verify environment variables are correctly set',
                'Ensure dependent services (databases, etc.) are accessible',
                'Inspect liveness probe configuration if used'
              ]
            },
            'PodOOMKilled': {
              rootCause: 'Container was terminated due to exceeding memory limits (Out Of Memory).',
              recommendations: [
                'Increase memory limits in pod specification',
                'Optimize application to use less memory',
                'Check for memory leaks in the application code',
                'Consider implementing a horizontal pod autoscaler'
              ]
            },
            'ImagePullError': {
              rootCause: 'Kubernetes cannot pull the specified container image, possibly due to missing credentials or incorrect image name.',
              recommendations: [
                'Verify image name and tag are correct',
                'Check if image exists in the repository',
                'Ensure pull secrets are configured correctly',
                'Verify network connectivity to the image registry'
              ]
            },
            'default': {
              rootCause: 'Multiple potential causes for this issue were found, requiring further investigation.',
              recommendations: [
                'Check pod logs for detailed error messages',
                'Inspect pod events with kubectl describe pod',
                'Verify resource requirements are properly set',
                'Check network policies if applicable'
              ]
            }
          };
          
          // Select response based on issue type or use default
          const issueType = formattedData.issueType;
          resolve(responses[issueType] || responses.default);
        }, 2000);
      });
    }
  }
  
  // Create a MutationObserver to detect when the Pod Details panel appears
  function setupPodDetailsPanelObserver() {
    // Add Fira Code font for better terminal look
    const fontLink = document.createElement('link');
    fontLink.href = 'https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&display=swap';
    fontLink.rel = 'stylesheet';
    document.head.appendChild(fontLink);
    
    // Look for the Pod Details panel
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'childList') {
          const podDetailsPanel = document.querySelector('.pod-detail-panel, [id*="pod-detail"], [class*="pod-detail"]');
          
          // If Pod Details panel exists and doesn't already have a terminal
          if (podDetailsPanel && !podDetailsPanel.querySelector('.kubera-terminal-container')) {
            // Extract metadata from the panel
            const metadata = extractPodDetailsMetadata(podDetailsPanel);
            
            // Add terminal to the panel
            addTerminalToPodDetailsPanel(podDetailsPanel, metadata);
            
            // We found and processed the panel, can disconnect observer
            observer.disconnect();
          }
        }
      }
    });
    
    // Start observing the document body for added nodes
    observer.observe(document.body, { childList: true, subtree: true });
    
    // Also try to find the panel immediately
    const podDetailsPanel = document.querySelector('.pod-detail-panel, [id*="pod-detail"], [class*="pod-detail"]');
    if (podDetailsPanel && !podDetailsPanel.querySelector('.kubera-terminal-container')) {
      const metadata = extractPodDetailsMetadata(podDetailsPanel);
      addTerminalToPodDetailsPanel(podDetailsPanel, metadata);
    }
  }
  
  // Extract metadata from Pod Details panel
  function extractPodDetailsMetadata(panel) {
    // This function attempts to extract pod metadata from the panel content
    // Adjust the selectors based on your actual HTML structure
    const metadata = {
      pod_name: '',
      namespace: '',
      issue_type: '',
      severity: 'unknown',
      source: 'kubernetes'
    };
    
    // Try to find elements containing pod info
    // These selectors need to match your actual HTML structure
    try {
      // Look for table rows or labeled fields
      const rows = panel.querySelectorAll('tr, .detail-row, .field-row');
      rows.forEach(row => {
        const label = row.querySelector('.label, th, .field-label');
        const value = row.querySelector('.value, td, .field-value');
        
        if (label && value) {
          const labelText = label.textContent.trim().toLowerCase();
          const valueText = value.textContent.trim();
          
          if (labelText.includes('pod') || labelText.includes('name')) {
            metadata.pod_name = valueText;
          } else if (labelText.includes('namespace')) {
            metadata.namespace = valueText;
          } else if (labelText.includes('issue') || labelText.includes('alert') || labelText.includes('type')) {
            metadata.issue_type = valueText;
          } else if (labelText.includes('severity')) {
            metadata.severity = valueText.toLowerCase();
          } else if (labelText.includes('source')) {
            metadata.source = valueText.toLowerCase();
          }
        }
      });
      
      // If we still don't have a pod name, try to find it in headers or titles
      if (!metadata.pod_name) {
        const header = panel.querySelector('h1, h2, h3, .panel-title, .header');
        if (header) {
          metadata.pod_name = header.textContent.trim();
        }
      }
      
      // Direct targeting of specific fields (adjust as needed)
      if (!metadata.pod_name) {
        const podNameEl = panel.querySelector('[id*="pod-name"], [class*="pod-name"]');
        if (podNameEl) metadata.pod_name = podNameEl.textContent.trim();
      }
      
      if (!metadata.namespace) {
        const namespaceEl = panel.querySelector('[id*="namespace"], [class*="namespace"]');
        if (namespaceEl) metadata.namespace = namespaceEl.textContent.trim();
      }
      
      // Extract issue type from the main UI if not found in the panel
      if (!metadata.issue_type) {
        const issueTypeEl = document.querySelector('.badge-high, .badge-medium, .badge-low, [class*="issue-type"]');
        if (issueTypeEl) metadata.issue_type = issueTypeEl.textContent.trim();
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
  
  // Add terminal to Pod Details panel
  function addTerminalToPodDetailsPanel(panel, metadata) {
    // Create container for terminal
    const terminalContainer = document.createElement('div');
    terminalContainer.className = 'kubera-terminal-container';
    
    // Add title bar
    const titleBar = document.createElement('div');
    titleBar.className = 'terminal-title-bar';
    
    const title = document.createElement('div');
    title.className = 'terminal-title';
    title.textContent = 'K3R4 - Kubernetes Error Root-cause Analysis';
    
    const toggle = document.createElement('button');
    toggle.className = 'terminal-toggle';
    toggle.innerHTML = '−'; // Minus sign
    toggle.title = 'Minimize terminal';
    
    // Minimize/expand functionality
    let terminalVisible = true;
    const terminalContent = document.createElement('div');
    terminalContent.className = 'terminal-content';
    
    toggle.onclick = function() {
      terminalVisible = !terminalVisible;
      terminalContent.style.display = terminalVisible ? 'block' : 'none';
      this.innerHTML = terminalVisible ? '−' : '+';
      this.title = terminalVisible ? 'Minimize terminal' : 'Expand terminal';
    };
    
    titleBar.appendChild(title);
    titleBar.appendChild(toggle);
    
    // Add to container
    terminalContainer.appendChild(titleBar);
    terminalContainer.appendChild(terminalContent);
    
    // Find the right place to insert the terminal
    // This could be at the end of the panel or after a specific section
    
    // Try to find a good insertion point - after "Recent Activities" or similar section
    let inserted = false;
    const sections = panel.querySelectorAll('h3, h4, .section-title, .panel-section');
    
    for (const section of sections) {
      if (section.textContent.toLowerCase().includes('activit') || 
          section.textContent.toLowerCase().includes('event') ||
          section.textContent.toLowerCase().includes('detail')) {
        // Find the section container
        let sectionContainer = section.parentElement;
        
        // Try to insert after this section
        sectionContainer.parentNode.insertBefore(terminalContainer, sectionContainer.nextSibling);
        inserted = true;
        break;
      }
    }
    
    // If we couldn't find a good section, just append to the panel
    if (!inserted) {
      panel.appendChild(terminalContainer);
    }
    
    // Create the terminal instance
    const terminal = new HackerTerminal(terminalContent, {
      height: '300px',
      typeDelay: 30 // Speed up typing for better UX
    });
    
    // Start analysis
    terminal.analyze(metadata);
  }
  
  // Wait for either Pod Details panel to appear or other triggering event
  document.addEventListener('DOMContentLoaded', () => {
    // Initial setup for MutationObserver
    setupPodDetailsPanelObserver();
    
    // Also listen for clicks on pods in the main UI
    document.addEventListener('click', event => {
      // This may need adjustment based on your UI's click handlers
      const clickedRow = event.target.closest('tr');
      if (clickedRow && !event.target.closest('.terminal-container')) {
        // A table row was clicked, set up observer to catch panel creation
        setTimeout(() => {
          setupPodDetailsPanelObserver();
        }, 100);
      }
    });
  });
})();
