// Kubera Dashboard Application
// Main JavaScript file to handle dashboard functionality

(function () {
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

    // Fetch initial data
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

    // Fetch data sources
    KuberaUtils.fetchDataSources()
      .then(sources => renderDataSourceFilters(sources));

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
    elements.sourceFilterTags = document.querySelector('.filter-section:nth-child(5) .filter-tags');
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

    // Apply namespace, priority, and source filters first
    if (state.activeNamespace !== 'All' || state.activePriority !== 'All' || state.activeSource !== 'all') {
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
      event.namespace.toLowerCase().includes(searchTerm) ||
      (event.source && event.source.toLowerCase().includes(searchTerm))
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
      tag.addEventListener('click', function () {
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
        // Handle source filter (new)
        else if (filterTitle === 'Source') {
          // First reset all source tags
          filterSection.querySelectorAll('.filter-tag').forEach(t => {
            t.classList.remove('active');
            t.style.color = '#d8d9da';
            t.style.backgroundColor = '#2a2a36';
          });

          // Set the active tag
          this.classList.add('active');
          this.style.backgroundColor = '#3872f2';
          this.style.color = 'white';

          // Update state using data-source-id if available, otherwise text
          state.activeSource = this.dataset.sourceId || this.textContent.toLowerCase();
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
      document.addEventListener('keydown', function (event) {
        if (event.key === '/' && document.activeElement !== elements.filterInput) {
          event.preventDefault();
          elements.filterInput.focus();
        }
      });

      // Handle input changes
      elements.filterInput.addEventListener('input', function () {
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
      elements.filterInput.addEventListener('keydown', function (event) {
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

  // Render Data Source Filters
  function renderDataSourceFilters(sources) {
    if (!elements.sourceFilterTags) return;

    // Clear existing tags
    elements.sourceFilterTags.innerHTML = '';

    // Add source tags
    sources.forEach(source => {
      const tag = document.createElement('div');
      tag.className = 'filter-tag' + (source.id === state.activeSource ? ' active' : '');
      tag.textContent = source.name;
      tag.dataset.sourceId = source.id;

      if (source.id === state.activeSource) {
        tag.style.backgroundColor = '#3872f2';
        tag.style.color = 'white';
      }

      // Add tooltips if descriptions are available
      if (source.description) {
        tag.title = source.description;
      }

      tag.addEventListener('click', function () {
        // Update active state for all tags
        elements.sourceFilterTags.querySelectorAll('.filter-tag').forEach(t => {
          t.classList.remove('active');
          t.style.backgroundColor = '#2a2a36';
          t.style.color = '#d8d9da';
        });

        // Activate this tag
        this.classList.add('active');
        this.style.backgroundColor = '#3872f2';
        this.style.color = 'white';

        // Update state
        state.activeSource = this.dataset.sourceId;

        // Apply filters
        applyFilters();
      });

      elements.sourceFilterTags.appendChild(tag);
    });
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

    allTag.addEventListener('click', function () {
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

        tag.addEventListener('click', function () {
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

        moreTag.addEventListener('click', function (e) {
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

      item.addEventListener('click', function () {
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
        // Create a unique key using alertType and source
        const groupKey = `${event.alertType}_${event.source || 'kubernetes'}`;

        if (!groupMap[groupKey]) {
          // Find the original group to get its severity
          const originalGroup = state.allGroupedEvents.find(g =>
            g.name === event.alertType &&
            (g.source || 'kubernetes') === (event.source || 'kubernetes')
          );

          groupMap[groupKey] = {
            name: event.alertType,
            severity: originalGroup ? originalGroup.severity : 'low',
            pods: [],
            count: 0,
            source: event.source || 'kubernetes'
          };
        }

        groupMap[groupKey].pods.push({
          name: event.pod,
          namespace: event.namespace,
          timestamp: event.timestamp,
          source: event.source || 'kubernetes'
        });

        groupMap[groupKey].count++;
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

    // Apply source filter
    if (state.activeSource !== 'all') {
      // Filter groups by source
      filteredGroupEvents = filteredGroupEvents.filter(group =>
        (group.source || 'kubernetes') === state.activeSource
      );

      // Filter individual events by source
      filteredIndividualEvents = filteredIndividualEvents.filter(event =>
        (event.source || 'kubernetes') === state.activeSource
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
        <th>Source</th>
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
        <th>Source</th>
        <th>Timestamp</th>
      `;
      renderEventStream();
    }
  }

  function renderGroupedEvents() {
    if (!elements.tableBody) return;

    elements.tableBody.innerHTML = '';

    if (state.groupedEvents.length === 0) {
      elements.tableBody.innerHTML = `<tr><td colspan="6" style="text-align: center;">No events found for the selected filters</td></tr>`;
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
          const accTime = new Date(acc.timestamp || acc.start);
          const pTime = new Date(p.timestamp || p.start);
          return pTime > accTime ? p : acc;
        }, null);
      }

      // Format source for display - UPDATED TO HANDLE ARGOCD
      let sourceText = '';
      if (issue.source === 'prometheus') {
        sourceText = '<span class="badge-prometheus">Prometheus</span>';
      } else if (issue.source === 'argocd') {
        sourceText = '<span class="badge-argocd">ArgoCD</span>';
      } else {
        sourceText = '<span class="badge-kubernetes">Kubernetes</span>';
      }

      // Set up the onclick with source info - UPDATED TO HANDLE ARGOCD
      const sourceParam = issue.source || 'kubernetes';

      // Set up the correct function to call - UPDATED FOR ARGOCD
      let onClickFunction = `openAnalysisPanel('${issue.name}', '${sourceParam}')`;

      // For ArgoCD, we need to use a different function and pass the app name
      if (sourceParam === 'argocd' && latestPod) {
        onClickFunction = `openArgoCDAnalysisPanel('${latestPod.name}')`;
      }

      // Build the row
      const row = document.createElement('tr');
      row.setAttribute('onclick', onClickFunction);
      row.innerHTML = `
        <td><span class="badge ${badgeClass}">${severityText}</span></td>
        <td>${issue.name}</td>
        <td>${sourceText}</td>
        <td>View ${issue.count} events</td>
        <td>${latestPod ? KuberaUtils.formatTimestamp(latestPod.timestamp || latestPod.start) : '-'}</td>
        <td>${latestPod ? 'Pod ' + latestPod.name : '-'}</td>
      `;

      elements.tableBody.appendChild(row);
    });
  }

  function renderEventStream() {
    if (!elements.tableBody) return;

    elements.tableBody.innerHTML = '';

    if (state.individualEvents.length === 0) {
      elements.tableBody.innerHTML = `<tr><td colspan="6" style="text-align: center;">No events found for the selected filters</td></tr>`;
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

      // Format source for display - UPDATED TO HANDLE ARGOCD
      let sourceText = '';
      if (event.source === 'prometheus') {
        sourceText = '<span class="badge-prometheus">Prometheus</span>';
      } else if (event.source === 'argocd') {
        sourceText = '<span class="badge-argocd">ArgoCD</span>';
      } else {
        sourceText = '<span class="badge-kubernetes">Kubernetes</span>';
      }

      // Set up the onclick with source info - UPDATED FOR ARGOCD
      let onClickFunction = `openAnalysisPanel('${event.alertType}', '${event.source || 'kubernetes'}')`;

      // For ArgoCD, use a different function
      if (event.source === 'argocd') {
        onClickFunction = `openArgoCDAnalysisPanel('${event.pod}')`;
      }

      // Build the row
      const row = document.createElement('tr');
      row.setAttribute('onclick', onClickFunction);
      row.innerHTML = `
        <td><span class="badge ${badgeClass}">${severityText}</span></td>
        <td>${event.alertType}</td>
        <td>${event.pod}</td>
        <td>${event.namespace}</td>
        <td>${sourceText}</td>
        <td>${KuberaUtils.formatTimestamp(event.timestamp)}</td>
      `;

      elements.tableBody.appendChild(row);
    });
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
        newTag.addEventListener('click', function () {
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

          // Include source information in the individual events
          state.allIndividualEvents.push({
            severity: issue.severity,
            alertType: issue.name,
            pod: pod.name,
            namespace: pod.namespace || 'default',
            timestamp: pod.timestamp || pod.start,
            source: pod.source || issue.source || 'kubernetes'
          });
        });
      }
    });

    // Sort by timestamp, newest first
    state.allIndividualEvents.sort((a, b) => {
      const dateA = a.timestamp ? new Date(a.timestamp) : new Date();
      const dateB = b.timestamp ? new Date(b.timestamp) : new Date();
      return dateB - dateA;
    });

    // Update namespace filter tags if they're missing any namespaces
    // This ensures all available namespaces show in the filter
    updateNamespaceFilters(namespaces);

    // Set up priority filter
    setupPriorityFilter();

    // Apply initial filters (which defaults to "All")
    applyFilters();
  }

  // Initialize when DOM is fully loaded
  document.addEventListener('DOMContentLoaded', init);
})();

// These functions need to be in global scope as they're called from HTML onclick attributes
function openAnalysisPanel(issueType, source = 'kubernetes') {
  const panel = document.getElementById('analysisPanel');
  const title = panel.querySelector('.analysis-title');
  const content = panel.querySelector('.analysis-content');

  const sourceLabel = source === 'prometheus' ? ' [Prometheus]' : '';
  title.textContent = `Investigating alert: ${issueType}${sourceLabel}`;
  content.innerHTML = '<div style="text-align: center; padding: 20px;"><i class="fas fa-spinner fa-spin fa-2x"></i><p>Loading analysis...</p></div>';

  // Show the panel
  panel.classList.add('open');

  // Fetch analysis data for this issue type
  fetch(`/api/analyze/${issueType}?source=${source}&include_description=true&include_metadata=true`)
    .then(response => response.json())
    .then(data => {
      // If description is not provided by the backend, request it from AI service
      if (!data.description && issueType) {
        fetch(`/api/generate-description?alert=${issueType}&source=${source}`)
          .then(response => {
            if (!response.ok) {
              throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
          })
          .then(descriptionData => {
            if (descriptionData.success) {
              data.description = descriptionData.description;
              data.source = descriptionData.source || 'fallback';
            } else {
              data.description = `${issueType}: Alert description unavailable. Check the event details below.`;
              data.source = 'error';
            }
            renderAnalysis(data, source);
          })
          .catch(error => {
            console.error('Error fetching description:', error);
            data.description = `${issueType}: Failed to load description. Check the event details below.`;
            data.source = 'error';
            renderAnalysis(data, source);
          });
      } else {
        renderAnalysis(data, source);
      }
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
function renderAnalysis(data, source = 'kubernetes') {
  const content = document.querySelector('.analysis-content');

  if (!data || !data.analysis || data.analysis.length === 0) {
    content.innerHTML = `<div class="error-message">No analysis data available</div>`;
    return;
  }

  let html = '';

  // Add source indicator if it's from Prometheus
  const sourceClass = source === 'prometheus' ? 'prometheus-source' : '';
  const sourceInfo = source === 'prometheus' ?
    `<div class="section-info" style="margin-bottom: 15px; color: #f06028;">
      <i class="fas fa-chart-line"></i> This analysis is based on Prometheus metrics data.
     </div>` : '';

  // Add alert description section at the top
  html += `
    <div class="analysis-section alert-description">
      <div class="analysis-subsection">
        <h4>Alert Summary</h4>
        <div class="alert-summary">
          ${data.description || 'No description available for this alert.'}
          ${data.source === 'fallback' ?
      '<div class="description-source">Using predefined description</div>' :
      (data.source === 'llm' ?
        '<div class="description-source">AI-generated description</div>' :
        '')}
        </div>
      </div>

      <div class="analysis-subsection">
        <h4>Events Overview</h4>
        <div class="events-metadata">
          <table class="metadata-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Namespace</th>
                <th>Pod</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              ${data.events_metadata ?
      data.events_metadata.map(event => `
                  <tr>
                    <td>${event.source || source}</td>
                    <td>${event.namespace || '-'}</td>
                    <td>${event.pod_name || '-'}</td>
                    <td>${KuberaUtils.formatTimestamp(event.timestamp)}</td>
                  </tr>
                `).join('') :
      '<tr><td colspan="4">No event metadata available</td></tr>'
    }
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  data.analysis.forEach(result => {
    html += `
      <div class="analysis-section ${sourceClass}">
        <div class="section-title">Pod: ${result.pod_name}</div>
        ${sourceInfo}

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
            ${result.pod_events && result.pod_events.length > 0
        ? result.pod_events.map(event => `<div class="log-line">${event}</div>`).join('')
        : '<div class="log-line">No events available</div>'}
          </div>
        </div>

        <div class="analysis-subsection">
          <h4>Recent Logs</h4>
          <div class="logs-container">
            ${result.logs_excerpt && result.logs_excerpt.length > 0
        ? result.logs_excerpt.map(log => `<div class="log-line">${log}</div>`).join('')
        : '<div class="log-line">No logs available</div>'}
          </div>
        </div>
      </div>
    `;
  });

  content.innerHTML = html;
}
