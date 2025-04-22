// Kubera Dashboard Application
// Main JavaScript file to handle dashboard functionality

(function() {
  // Use the shared state from KuberaUtils
  const state = KuberaUtils.state;
  const elements = KuberaUtils.elements;

  // Initialize the application
  function init() {
    // Cache DOM elements
    cacheElements();
    
    // Initialize KuberaUtils with refresh callback
    KuberaUtils.initialize(refreshData);
    
    // Set up event listeners
    setupEventListeners();
    
    // Initial data fetch
    fetchInitialData();
    
    // Start auto-refresh
    KuberaUtils.startAutoRefresh(refreshData);
  }

  // Fetch all initial data needed
  function fetchInitialData() {
    KuberaUtils.fetchKubeContexts()
      .then(contexts => renderKubeContexts(contexts));
    
    KuberaUtils.fetchNamespaces()
      .then(namespaces => renderNamespaceFilters(namespaces));
    
    refreshData();
  }

  // Refresh dashboard data
  function refreshData() {
    // Determine which timeline endpoint to use based on time range
    const timelinePromise = (state.selectedHours <= 6) 
      ? KuberaUtils.fetchTimelineData()
      : KuberaUtils.fetchTimelineHistory();
    
    // Fetch timeline data
    timelinePromise.then(data => {
      KuberaUtils.renderTimelineTracks(data);
      KuberaUtils.updateTimelineRuler();
    });
    
    // Fetch cluster issues
    KuberaUtils.fetchClusterIssues()
      .then(issues => {
        processClusterIssues(issues);
      });
  }

  // Cache frequently used DOM elements
  function cacheElements() {
    elements.groupedEventsTab = document.getElementById('groupedEventsTab');
    elements.eventStreamTab = document.getElementById('eventStreamTab');
    elements.tableBody = document.getElementById('eventsTableBody');
    elements.tableHead = document.querySelector('.events-table thead tr');
    elements.clusterSelectorBtn = document.getElementById('clusterSelectorBtn');
    elements.clusterDropdown = document.getElementById('clusterDropdown');
    elements.currentClusterName = document.getElementById('currentClusterName');
    elements.timeRangeButton = document.getElementById('timeRangeButton');
    elements.timeRangeDropdown = document.getElementById('timeRangeDropdown');
    elements.namespaceFilterTags = document.getElementById('namespaceFilterTags');
    elements.priorityFilterTags = document.querySelector('.filter-section:nth-child(4) .filter-tags');
    elements.refreshTimelineButton = document.getElementById('refreshTimelineButton');
    
    // All filter tags
    elements.filterInput = document.querySelector('.filter-input');
    elements.clearSearchBtn = document.getElementById('clearSearchBtn');
    elements.filterTags = document.querySelectorAll('.filter-tag');
  }

  function applySearchFilter(searchTerm) {
    if (!searchTerm) {
      // If search term is empty, just apply regular filters
      applyFilters();
      return;
    }
    
    // Starting with filtered data from regular filters
    let filteredGroupEvents;
    let filteredIndividualEvents;
    
    // Apply namespace and priority filters first
    if (state.activeNamespace !== 'All' || state.activePriority !== 'All') {
      // If other filters are active, start with that filtered set
      filteredGroupEvents = [...state.groupedEvents];
      filteredIndividualEvents = [...state.individualEvents];
    } else {
      // Otherwise start with all data
      filteredGroupEvents = [...state.allGroupedEvents];
      filteredIndividualEvents = [...state.allIndividualEvents];
    }
    
    // Apply search term filter to grouped events
    filteredGroupEvents = filteredGroupEvents.filter(group => {
      // Search in name
      if (group.name.toLowerCase().includes(searchTerm)) {
        return true;
      }
      
      // Search in pods
      if (group.pods && group.pods.length > 0) {
        return group.pods.some(pod => 
          pod.name.toLowerCase().includes(searchTerm) || 
          pod.namespace.toLowerCase().includes(searchTerm)
        );
      }
      
      return false;
    });
    
    // Apply search term filter to individual events
    filteredIndividualEvents = filteredIndividualEvents.filter(event => 
      event.alertType.toLowerCase().includes(searchTerm) ||
      event.pod.toLowerCase().includes(searchTerm) ||
      event.namespace.toLowerCase().includes(searchTerm)
    );
    
    // Update the state
    state.groupedEvents = filteredGroupEvents;
    state.individualEvents = filteredIndividualEvents;
    
    // Update tab labels with filtered counts
    elements.groupedEventsTab.textContent = `Grouped Events (${state.groupedEvents.length})`;
    elements.eventStreamTab.textContent = `Event Stream (${state.individualEvents.length})`;
    
    // Re-render the current view
    if (state.activeTab === 'grouped') {
      renderGroupedEvents();
    } else {
      renderEventStream();
    }
    
    // Update timeline with filtered data
    KuberaUtils.renderTimelineTracks(state.groupedEvents);
  }

  function clearSearchFilter() {
    KuberaUtils.clearSearchFilter(elements.filterInput, elements.clearSearchBtn);
    applyFilters(); // Reset to normal filters
  }

  // Set up event listeners
  function setupEventListeners() {
    // Tab switching
    if (elements.groupedEventsTab) {
      elements.groupedEventsTab.addEventListener('click', () => switchTab('grouped'));
    }
    
    if (elements.eventStreamTab) {
      elements.eventStreamTab.addEventListener('click', () => switchTab('stream'));
    }
    
    // Cluster dropdown toggle
    if (elements.clusterSelectorBtn && elements.clusterDropdown) {
      elements.clusterSelectorBtn.addEventListener('click', () => {
        elements.clusterDropdown.style.display = (elements.clusterDropdown.style.display === 'none') ? 'block' : 'none';
      });
      
      // Close dropdown when clicking outside
      document.addEventListener('click', (event) => {
        if (!elements.clusterSelectorBtn.contains(event.target) && !elements.clusterDropdown.contains(event.target)) {
          elements.clusterDropdown.style.display = 'none';
        }
      });
    }
    
    // Time range dropdown is now handled by KuberaUtils
    
    // Filter tag clicks
    elements.filterTags.forEach(tag => {
      tag.addEventListener('click', function() {
        // Skip the "more/less" tag
        if (this.classList.contains('more-tag')) return;
        
        // Get parent filter section
        const filterSection = this.closest('.filter-section');
        if (!filterSection) return;
        
        // Get the filter title to determine which filter this is
        const filterTitle = filterSection.querySelector('.filter-title').textContent;
        
        // Handle namespace filter 
        if (filterTitle === 'Namespace') {
          elements.namespaceTags.forEach(t => {
            t.classList.remove('active');
            t.style.color = '#d8d9da';
            t.style.backgroundColor = '#2a2a36';
          });
          
          this.classList.add('active');
          this.style.backgroundColor = '#3872f2';
          this.style.color = 'white';
          
          state.activeNamespace = this.textContent;
        } 
        // Handle priority filter
        else if (filterTitle === 'Priority') {
          // First reset all priority tags
          filterSection.querySelectorAll('.filter-tag').forEach(t => {
            t.classList.remove('active');
            t.style.color = '#d8d9da';
            t.style.backgroundColor = '#2a2a36';
          });
          
          // Set the active tag
          this.classList.add('active');
          this.style.backgroundColor = '#3872f2';
          this.style.color = 'white';
          
          // Update state
          state.activePriority = this.textContent;
        } 
        else {
          // For other filters, just toggle the active class on this section
          const siblings = Array.from(this.parentNode.children);
          siblings.forEach(sibling => sibling.classList.remove('active'));
          this.classList.add('active');
        }
        
        // Apply filters
        applyFilters();
      });
    });
    
    // Refresh button
    if (elements.refreshTimelineButton) {
      elements.refreshTimelineButton.addEventListener('click', refreshData);
    }
    
    // Filter input event listeners
    if (elements.filterInput) {
      // Focus on '/' key press
      document.addEventListener('keydown', function(event) {
        if (event.key === '/' && document.activeElement !== elements.filterInput) {
          event.preventDefault();
          elements.filterInput.focus();
        }
      });
      
      // Handle input changes
      elements.filterInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase().trim();
        state.filterTerm = searchTerm;
        
        // Show/hide clear button
        if (searchTerm.length > 0) {
          elements.clearSearchBtn.style.display = 'block';
          elements.filterInput.classList.add('filter-active');
        } else {
          elements.clearSearchBtn.style.display = 'none';
          elements.filterInput.classList.remove('filter-active');
        }
        
        applySearchFilter(searchTerm);
      });
      
      // Clear on Escape key
      elements.filterInput.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
          clearSearchFilter();
        }
      });
    }
    
    // Clear button click
    if (elements.clearSearchBtn) {
      elements.clearSearchBtn.addEventListener('click', clearSearchFilter);
    }
  }

  // Render the namespace filters with "more +" feature
  function renderNamespaceFilters(namespaces) {
    if (!elements.namespaceFilterTags) return;
    
    // Log the namespaces we're trying to render
    console.log('Rendering namespaces:', namespaces);
    
    // Clear all existing tags
    elements.namespaceFilterTags.innerHTML = '';
    
    // Add the "All" option with proper click handler
    const allTag = document.createElement('div');
    allTag.className = 'filter-tag active';
    allTag.textContent = 'All';
    allTag.style.backgroundColor = '#3872f2';
    allTag.style.color = 'white';
    
    allTag.addEventListener('click', function() {
      // Remove active class from all namespace tags
      document.querySelectorAll('#namespaceFilterTags .filter-tag').forEach(t => {
        t.classList.remove('active');
        t.style.color = '#d8d9da';
        t.style.backgroundColor = '#2a2a36';
      });
      
      // Activate this tag
      this.classList.add('active');
      this.style.backgroundColor = '#3872f2';
      this.style.color = 'white';
      
      state.activeNamespace = 'All';
      applyFilters();
    });
    
    elements.namespaceFilterTags.appendChild(allTag);
    
    // Function to render a limited or full set of namespaces
    function renderNamespaceSet(showAll = false) {
      // Clear current tags except "All"
      const tags = Array.from(elements.namespaceFilterTags.querySelectorAll('.filter-tag:not(:first-child)'));
      tags.forEach(tag => tag.remove());
      
      // Determine how many namespaces to show
      const displayCount = showAll ? namespaces.length : Math.min(5, namespaces.length);
      
      // Add namespace tags
      for (let i = 0; i < displayCount; i++) {
        const namespace = namespaces[i];
        const tag = document.createElement('div');
        tag.className = 'filter-tag';
        tag.textContent = namespace;
        tag.style.color = '#d8d9da';
        tag.style.backgroundColor = '#2a2a36';
        
        tag.addEventListener('click', function() {
          document.querySelectorAll('#namespaceFilterTags .filter-tag').forEach(t => {
            t.classList.remove('active');
            t.style.color = '#d8d9da';
            t.style.backgroundColor = '#2a2a36';
          });
          
          this.classList.add('active');
          this.style.backgroundColor = '#3872f2';
          this.style.color = 'white';
          
          state.activeNamespace = this.textContent;
          applyFilters();
        });
        
        elements.namespaceFilterTags.appendChild(tag);
      }
      
      // If there are more than 5 namespaces, add a "more +" or "less -" tag
      if (namespaces.length > 5) {
        const moreTag = document.createElement('div');
        moreTag.className = 'filter-tag more-tag';
        moreTag.textContent = showAll ? 'less -' : 'more +';
        moreTag.style.color = '#3872f2';
        moreTag.style.backgroundColor = 'transparent';
        moreTag.style.border = '1px dashed #3872f2';
        
        moreTag.addEventListener('click', function(e) {
          // Prevent this click from triggering filters
          e.stopPropagation();
          
          state.showingAllNamespaces = !state.showingAllNamespaces;
          renderNamespaceSet(state.showingAllNamespaces);
        });
        
        elements.namespaceFilterTags.appendChild(moreTag);
      }
      
      // Update reference to namespace tags
      elements.namespaceTags = document.querySelectorAll('#namespaceFilterTags .filter-tag:not(.more-tag)');
    }
    
    // Initial render with limited namespaces
    renderNamespaceSet(state.showingAllNamespaces);
  }

  // Set up priority filter
  function setupPriorityFilter() {
    if (!elements.priorityFilterTags) return;
    
    // Get all priority tags
    elements.priorityTags = elements.priorityFilterTags.querySelectorAll('.filter-tag');
    
    // For each priority tag, set the initial styling
    elements.priorityTags.forEach(tag => {
      if (tag.textContent === state.activePriority) {
        tag.classList.add('active');
        tag.style.backgroundColor = '#3872f2';
        tag.style.color = 'white';
      } else {
        tag.classList.remove('active');
        tag.style.color = '#d8d9da';
        tag.style.backgroundColor = '#2a2a36';
      }
    });
  }

  // Render Kubernetes contexts in the dropdown
  function renderKubeContexts(contexts) {
    if (!elements.clusterDropdown) return;
    
    elements.clusterDropdown.innerHTML = '';
    
    if (!contexts || contexts.length === 0) {
      elements.clusterDropdown.innerHTML = '<div class="dropdown-item">No contexts available</div>';
      return;
    }
    
    contexts.forEach(context => {
      const item = document.createElement('div');
      item.className = 'dropdown-item' + (context.current ? ' active' : '');
      item.textContent = context.name;
      
      if (context.current) {
        state.currentCluster = context.name;
        elements.currentClusterName.textContent = context.name;
      }
      
      item.addEventListener('click', function() {
        // In a real implementation, you would call an API to switch contexts
        document.querySelectorAll('#clusterDropdown .dropdown-item').forEach(i => i.classList.remove('active'));
        this.classList.add('active');
        elements.currentClusterName.textContent = context.name;
        state.currentCluster = context.name;
        
        // Update the page title to include cluster name
        document.title = `KubERA - ${context.name}`;
        
        // Close the dropdown
        elements.clusterDropdown.style.display = 'none';
        
        // Reload data for the new cluster
        refreshData();
      });
      
      elements.clusterDropdown.appendChild(item);
    });
  }

  // Function to switch between tabs
  function switchTab(tabName) {
    state.activeTab = tabName;
    
    // Update active tab styling
    elements.groupedEventsTab.classList.toggle('active', tabName === 'grouped');
    elements.eventStreamTab.classList.toggle('active', tabName === 'stream');
    
    // Update table headers for the appropriate view
    if (tabName === 'grouped') {
      elements.tableHead.innerHTML = `
        <th>Priority</th>
        <th>Alert</th>
        <th>Events</th>
        <th>Latest</th>
        <th>Latest event</th>
      `;
      renderGroupedEvents();
    } else {
      elements.tableHead.innerHTML = `
        <th>Priority</th>
        <th>Alert Type</th>
        <th>Pod</th>
        <th>Namespace</th>
        <th>Timestamp</th>
      `;
      renderEventStream();
    }
  }

  // Filter data based on active filters
  function applyFilters() {
    // Starting with all data
    let filteredGroupEvents = [...state.allGroupedEvents];
    let filteredIndividualEvents = [...state.allIndividualEvents];
    
    // Apply namespace filter
    if (state.activeNamespace !== 'All') {
      // Filter individual events by namespace
      filteredIndividualEvents = filteredIndividualEvents.filter(event => 
        event.namespace === state.activeNamespace
      );
      
      // Then recreate grouped events based on filtered individual events
      const groupMap = {};
      
      filteredIndividualEvents.forEach(event => {
        if (!groupMap[event.alertType]) {
          // Find the original group to get its severity
          const originalGroup = state.allGroupedEvents.find(g => g.name === event.alertType);
          
          groupMap[event.alertType] = {
            name: event.alertType,
            severity: originalGroup ? originalGroup.severity : 'low',
            pods: [],
            count: 0
          };
        }
        
        groupMap[event.alertType].pods.push({
          name: event.pod,
          namespace: event.namespace,
          timestamp: event.timestamp
        });
        
        groupMap[event.alertType].count++;
      });
      
      filteredGroupEvents = Object.values(groupMap);
    }
    
    // Apply priority filter
    if (state.activePriority !== 'All') {
      const priorityLower = state.activePriority.toLowerCase();
      
      // Filter groups by priority/severity
      filteredGroupEvents = filteredGroupEvents.filter(group => 
        group.severity === priorityLower
      );
      
      // Filter individual events by priority/severity
      filteredIndividualEvents = filteredIndividualEvents.filter(event => 
        event.severity === priorityLower
      );
    }
    
    // Update the filtered state
    state.groupedEvents = filteredGroupEvents;
    state.individualEvents = filteredIndividualEvents;
    
    const searchTerm = elements.filterInput?.value.toLowerCase().trim();
    if (searchTerm) {
      applySearchFilter(searchTerm);
      return;
    }

    // Update tab labels with filtered counts
    elements.groupedEventsTab.textContent = `Grouped Events (${state.groupedEvents.length})`;
    elements.eventStreamTab.textContent = `Event Stream (${state.individualEvents.length})`;
    
    // Re-render the current view
    if (state.activeTab === 'grouped') {
      renderGroupedEvents();
    } else {
      renderEventStream();
    }
    
    // Update timeline with filtered data
    KuberaUtils.renderTimelineTracks(state.groupedEvents);
  }

  // Process cluster issues data
  function processClusterIssues(issues) {
    // Store the original grouped events
    state.allGroupedEvents = issues;
    
    // Process all individual events
    state.allIndividualEvents = [];
    let totalEvents = 0;
    
    // Also collect unique namespaces to potentially update filter options
    const namespaces = new Set();
    namespaces.add('All'); // Always include "All"
    
    issues.forEach(issue => {
      totalEvents += issue.count;
      
      if (issue.pods) {
        issue.pods.forEach(pod => {
          // Add namespace to our set of unique namespaces
          if (pod.namespace) {
            namespaces.add(pod.namespace);
          }
          
          state.allIndividualEvents.push({
            severity: issue.severity,
            alertType: issue.name,
            pod: pod.name,
            namespace: pod.namespace || 'default',
            timestamp: pod.timestamp
          });
        });
      }
    });
    
    // Sort by timestamp, newest first
    state.allIndividualEvents.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    // Update namespace filter tags if they're missing any namespaces
    // This ensures all available namespaces show in the filter
    updateNamespaceFilters(namespaces);
    
    // Set up priority filter
    setupPriorityFilter();
    
    // Apply initial filters (which defaults to "All")
    applyFilters();
  }

  // Function to update namespace filters with any missing namespaces
  function updateNamespaceFilters(namespaces) {
    const namespaceSection = document.querySelector('.filter-section:nth-child(2) .filter-tags');
    if (!namespaceSection) return;
    
    // Get existing namespace filter tags
    const existingNamespaces = new Set();
    if (elements.namespaceTags) {
      elements.namespaceTags.forEach(tag => {
        existingNamespaces.add(tag.textContent);
      });
    }
    
    // Add any missing namespaces
    namespaces.forEach(namespace => {
      if (!existingNamespaces.has(namespace)) {
        const newTag = document.createElement('div');
        newTag.className = 'filter-tag';
        newTag.textContent = namespace;
        newTag.addEventListener('click', function() {
          // Remove active class from all namespace tags
          document.querySelectorAll('.filter-section:nth-child(2) .filter-tag').forEach(t => {
            t.classList.remove('active');
          });
          
          // Add active class to clicked tag
          this.classList.add('active');
          
          // Update active namespace and apply filter
          state.activeNamespace = this.textContent;
          applyFilters();
        });
        
        namespaceSection.appendChild(newTag);
      }
    });
  }

  // Function to render grouped events
  function renderGroupedEvents() {
    if (!elements.tableBody) return;
    
    elements.tableBody.innerHTML = '';
    
    if (state.groupedEvents.length === 0) {
      elements.tableBody.innerHTML = `<tr><td colspan="5" style="text-align: center;">No events found for the selected filters</td></tr>`;
      return;
    }
    
    state.groupedEvents.forEach(issue => {
      // Determine badge class based on severity
      const severityText = (issue.severity || '').toUpperCase();
      let badgeClass = 'badge-low'; // default
      if (issue.severity === 'high') {
        badgeClass = 'badge-high';
      } else if (issue.severity === 'medium') {
        badgeClass = 'badge-medium';
      }

      // Find the latest timestamp from the pods
      let latestPod = null;
      if (issue.pods && issue.pods.length > 0) {
        latestPod = issue.pods.reduce((acc, p) => {
          if (!acc) return p;
          const accTime = new Date(acc.timestamp);
          const pTime = new Date(p.timestamp);
          return pTime > accTime ? p : acc;
        }, null);
      }

      // Build the row
      const row = document.createElement('tr');
      row.setAttribute('onclick', `openAnalysisPanel('${issue.name}')`);
      row.innerHTML = `
        <td><span class="badge ${badgeClass}">${severityText}</span></td>
        <td>${issue.name}</td>
        <td>View ${issue.count} events</td>
        <td>${latestPod ? KuberaUtils.formatTimestamp(latestPod.timestamp) : '-'}</td>
        <td>${latestPod ? 'Pod ' + latestPod.name : '-'}</td>
      `;

      elements.tableBody.appendChild(row);
    });
  }

  // Function to render individual event stream
  function renderEventStream() {
    if (!elements.tableBody) return;
    
    elements.tableBody.innerHTML = '';
    
    if (state.individualEvents.length === 0) {
      elements.tableBody.innerHTML = `<tr><td colspan="5" style="text-align: center;">No events found for the selected filters</td></tr>`;
      return;
    }
    
    state.individualEvents.forEach(event => {
      // Determine badge class based on severity
      const severityText = (event.severity || '').toUpperCase();
      let badgeClass = 'badge-low'; // default
      if (event.severity === 'high') {
        badgeClass = 'badge-high';
      } else if (event.severity === 'medium') {
        badgeClass = 'badge-medium';
      }
      
      // Build the row
      const row = document.createElement('tr');
      row.setAttribute('onclick', `openAnalysisPanel('${event.alertType}')`);
      row.innerHTML = `
        <td><span class="badge ${badgeClass}">${severityText}</span></td>
        <td>${event.alertType}</td>
        <td>${event.pod}</td>
        <td>${event.namespace}</td>
        <td>${KuberaUtils.formatTimestamp(event.timestamp)}</td>
      `;

      elements.tableBody.appendChild(row);
    });
  }

  // Initialize when DOM is fully loaded
  document.addEventListener('DOMContentLoaded', init);
})();

// These functions need to be in global scope as they're called from HTML onclick attributes
function openAnalysisPanel(issueType) {
  const panel = document.getElementById('analysisPanel');
  const title = panel.querySelector('.analysis-title');
  const content = panel.querySelector('.analysis-content');
  
  title.textContent = `Investigating alert: ${issueType}`;
  content.innerHTML = '<div style="text-align: center; padding: 20px;"><i class="fas fa-spinner fa-spin fa-2x"></i><p>Loading analysis...</p></div>';
  
  // Show the panel
  panel.classList.add('open');
  
  // Fetch analysis data for this issue type
  fetch(`/api/analyze/${issueType}`)
    .then(response => response.json())
    .then(data => {
      renderAnalysis(data);
    })
    .catch(error => {
      content.innerHTML = `<div class="error-message">Error loading analysis: ${error.message}</div>`;
    });
}

// Close the analysis panel
function closeAnalysisPanel() {
  const panel = document.getElementById('analysisPanel');
  panel.classList.remove('open');
}

// Render the analysis data in the panel
function renderAnalysis(data) {
  const content = document.querySelector('.analysis-content');
  
  if (!data || !data.analysis || data.analysis.length === 0) {
    content.innerHTML = `<div class="error-message">No analysis data available</div>`;
    return;
  }
  
  let html = '';
  
  data.analysis.forEach(result => {
    html += `
      <div class="analysis-section">
        <div class="section-title">Pod: ${result.pod_name}</div>
        
        <div class="analysis-subsection">
          <h4>Root Cause</h4>
          <ul class="root-cause-list">
            ${result.root_cause.map(cause => `<li>${cause}</li>`).join('')}
          </ul>
        </div>
        
        <div class="analysis-subsection">
          <h4>Recommended Actions</h4>
          <ul class="root-cause-list">
            ${result.recommended_actions.map(action => `<li>${action}</li>`).join('')}
          </ul>
        </div>
        
        <div class="analysis-subsection">
          <h4>Events</h4>
          <div class="logs-container">
            ${result.pod_events.map(event => `<div class="log-line">${event}</div>`).join('')}
          </div>
        </div>
        
        <div class="analysis-subsection">
          <h4>Recent Logs</h4>
          <div class="logs-container">
            ${result.logs_excerpt.map(log => `<div class="log-line">${log}</div>`).join('')}
          </div>
        </div>
      </div>
    `;
  });
  
  content.innerHTML = html;
}
