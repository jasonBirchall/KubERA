// Kubera Shared Utility Functions
// Common functionality used by both dashboard.js and timeline.js

const KuberaUtils = (function() {
  // Shared state variables that will be accessible to both modules
  let state = {
    allGroupedEvents: [],
    allIndividualEvents: [],
    groupedEvents: [], // Filtered data
    individualEvents: [], // Filtered data
    activeTab: 'grouped', // Default active tab
    activeNamespace: 'All', // Default namespace filter
    activePriority: 'All', // Default priority filter
    activeSource: 'all', // Default data source filter - 'all', 'kubernetes', 'prometheus'
    currentCluster: '', // Current selected cluster
    showingAllNamespaces: false, // Whether we're showing all namespaces or just the first few
    selectedHours: 6, // Default time range
    filterTerm: ''
  };

  // DOM elements cache
  let elements = {};
  
  // Initialization flags
  let initialized = false;
  let dropdownsInitialized = false;

  // Configure auto-refresh
  let refreshInterval;

  // Helper to format timestamp
  function formatTimestamp(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    return date.toLocaleString();
  }

  // Helper to calculate percentage along timeline
  function percentAlong(rangeStart, rangeEnd, t) {
    return ((t - rangeStart) / (rangeEnd - rangeStart)) * 100;
  }

  // Fetch timeline data from API
  function fetchTimelineData() {
    console.log('Fetching timeline data...');
    return fetch(`/api/timeline_data?hours=${state.selectedHours}&source=${state.activeSource}`)
      .then(response => response.json())
      .then(data => {
        console.log('Timeline data received:', data);
        return data;
      })
      .catch(error => {
        console.error('Error fetching timeline data:', error);
        return [];
      });
  }

  // Fetch timeline history
  function fetchTimelineHistory() {
    return fetch(`/api/timeline_history?hours=${state.selectedHours}&source=${state.activeSource}`)
      .then(r => r.json())
      .then(data => {
        return data;
      })
      .catch(err => {
        console.error('Error fetching timeline history:', err);
        return [];
      });
  }

  // Fetch Prometheus data
  function fetchPrometheusData() {
    return fetch(`/api/prometheus_data?hours=${state.selectedHours}`)
      .then(response => response.json())
      .then(data => {
        console.log('Prometheus data received:', data);
        return data;
      })
      .catch(error => {
        console.error('Error fetching Prometheus data:', error);
        return [];
      });
  }

  // Fetch cluster issues
  function fetchClusterIssues() {
    return fetch(`/api/cluster_issues?source=${state.activeSource}`)
      .then(response => response.json())
      .then(issues => {
        return issues;
      })
      .catch(error => {
        console.error('Error fetching cluster issues:', error);
        return [];
      });
  }

  // Fetch available data sources
  function fetchDataSources() {
    return fetch('/api/sources')
      .then(response => response.json())
      .then(sources => {
        return sources;
      })
      .catch(error => {
        console.error('Error fetching data sources:', error);
        // Fallback sources
        return [
          {id: 'all', name: 'All Sources'},
          {id: 'kubernetes', name: 'Kubernetes'},
          {id: 'prometheus', name: 'Prometheus'}
        ];
      });
  }

  // Fetch available Kubernetes contexts
  function fetchKubeContexts() {
    return fetch('/api/kube-contexts')
      .then(response => response.json())
      .then(contexts => {
        return contexts;
      })
      .catch(error => {
        console.error('Error fetching Kubernetes contexts:', error);
        // Fallback to default sample contexts in case of error
        return [
          { name: 'kubera-local', current: true },
          { name: 'prod-cluster', current: false },
          { name: 'staging-cluster', current: false },
          { name: 'minikube', current: false }
        ];
      });
  }

  // Fetch namespaces
  function fetchNamespaces() {
    return fetch('/api/namespaces')
      .then(response => response.json())
      .then(namespaces => {
        return namespaces;
      })
      .catch(error => {
        console.error('Error fetching Kubernetes namespaces:', error);
        return [];
      });
  }

  // Render timeline tracks
  function renderTimelineTracks(issues) {
    const tracks = document.querySelector('.timeline-tracks');
    if (!tracks) return;
    
    tracks.innerHTML = '';

    if (!issues || issues.length === 0) {
      tracks.innerHTML = '<div style="padding:15px;color:#7e7e8f;">No issues detected</div>';
      return;
    }

    const windowStart = Date.now() - state.selectedHours * 60 * 60 * 1000;
    const windowEnd   = Date.now();

    issues.forEach(issue => {
      const track = document.createElement('div');
      track.className = 'timeline-track';

       // Add source indicator to the title based on source
      let sourceIndicator = '';
      if (issue.source === 'prometheus') {
        sourceIndicator = ' [Prometheus]';
      } else if (issue.source === 'argocd') {
        sourceIndicator = ' [ArgoCD]';
      }     

      const title = document.createElement('div');
      title.className = 'timeline-track-title';
      title.textContent = `${issue.name}${sourceIndicator} (${issue.count})`;
      track.appendChild(title);

      if (issue.pods?.length) {
        issue.pods.forEach(pod => {
          const ev       = document.createElement('div');
          const start    = new Date(pod.start).getTime();
          const end      = pod.end ? new Date(pod.end).getTime()
                                  : Date.now();          // still occurring
          const leftPct  = percentAlong(windowStart, windowEnd, start);
          const widthPct = Math.max(
                            percentAlong(windowStart, windowEnd, end) - leftPct,
                            0.8                                      // min width so it's clickable
                          );

          ev.className = `timeline-event ${issue.severity || 'low'}`
                      + (pod.end ? '' : ' ongoing');
          
          // Add a special class for Prometheus events
          if (pod.source === 'prometheus' || issue.source === 'prometheus') {
            ev.classList.add('prometheus-event');
          } else if (pod.source === 'argocd' || issue.source === 'argocd') {
            ev.classList.add('argocd-event');
          }

           let tooltipContent = [
            `Pod: ${pod.name}`,
            `Namespace: ${pod.namespace}`,
            `Source: ${pod.source || issue.source || 'kubernetes'}`,
            `Started: ${new Date(pod.start).toLocaleString()}`,
            pod.end ? `Ended: ${new Date(pod.end).toLocaleString()}`
                    : 'Still occurring'
          ];
          
          // Add ArgoCD-specific details if available
          if (pod.details && (pod.source === 'argocd' || issue.source === 'argocd')) {
            tooltipContent.push('');
            tooltipContent.push(`Health: ${pod.details.healthStatus || 'Unknown'}`);
            tooltipContent.push(`Sync: ${pod.details.syncStatus || 'Unknown'}`);
          }         

          ev.style.left  = `${leftPct}%`;
          ev.style.width = `${widthPct}%`;
          ev.title = tooltipContent.join('\n');

          // click handler that includes source info
          ev.addEventListener('click', function() {
            // Extract issue type from timeline
              const sourceParam = (pod.source === 'prometheus' || issue.source === 'prometheus') 
              ? 'prometheus' : (pod.source === 'argocd' || issue.source === 'argocd')
              ? 'argocd' : 'kubernetes';
            if (sourceParam === 'argocd') {
              openArgoCDAnalysisPanel(pod.name);
            } else {
              openAnalysisPanel(issue.name, sourceParam);
            }
          });

          track.appendChild(ev);
        });
      }

      tracks.appendChild(track);
    });
  }

  // Update timeline ruler with accurate time markers
  function updateTimelineRuler() {
    const ruler = document.querySelector('.timeline-ruler');
    if (!ruler) return;
    
    ruler.innerHTML = '';

    const segments = 7;
    for (let i = 0; i < segments; i++) {
      const marker = document.createElement('div');
      const time = new Date(Date.now() - (state.selectedHours * 60 * 60 * 1000) + (i * state.selectedHours * 60 * 60 * 1000 / (segments - 1)));
      marker.textContent = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      ruler.appendChild(marker);
    }
  }

  // Start auto-refresh
  function startAutoRefresh(callback, intervalSeconds = 30) {
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
    
    refreshInterval = setInterval(() => {
      if (callback && typeof callback === 'function') {
        callback();
      }
      console.log('Auto-refreshed data');
    }, intervalSeconds * 1000);

    return refreshInterval;
  }

  // Stop auto-refresh
  function stopAutoRefresh() {
    if (refreshInterval) {
      clearInterval(refreshInterval);
      refreshInterval = null;
    }
  }

  // Clear search filter
  function clearSearchFilter(inputElement, clearBtnElement) {
    if (inputElement) {
      inputElement.value = '';
      state.filterTerm = '';
      inputElement.classList.remove('filter-active');
      if (clearBtnElement) {
        clearBtnElement.style.display = 'none';
      }
    }
  }
  
  // Initialize dropdowns (time range, cluster)
  function initializeDropdowns(refreshCallback) {
    if (dropdownsInitialized) return;
    
    // Time range dropdown handling
    const timeRangeButton = document.getElementById('timeRangeButton');
    const timeRangeDropdown = document.getElementById('timeRangeDropdown');
    
    if (timeRangeButton && timeRangeDropdown) {
      // Set initial text
      timeRangeButton.innerHTML = `<i class="fas fa-clock btn-icon"></i> Last ${state.selectedHours} hrs ▾`;
      
      // Set active item
      const defaultItem = timeRangeDropdown.querySelector(`[data-hours="${state.selectedHours}"]`);
      if (defaultItem) {
        defaultItem.classList.add('active');
      }
      
      // Toggle dropdown
      timeRangeButton.addEventListener('click', () => {
        timeRangeDropdown.style.display = (timeRangeDropdown.style.display === 'none' || !timeRangeDropdown.style.display) 
          ? 'block' 
          : 'none';
      });
      
      // Handle dropdown item selection
      timeRangeDropdown.querySelectorAll('.dropdown-item').forEach(item => {
        item.addEventListener('click', function() {
          // Remove active from all
          timeRangeDropdown.querySelectorAll('.dropdown-item').forEach(i => i.classList.remove('active'));
          
          // Set new active item
          this.classList.add('active');
          
          // Update selected hours and UI
          state.selectedHours = parseInt(this.getAttribute('data-hours'), 10);
          timeRangeButton.innerHTML = `<i class="fas fa-clock btn-icon"></i> Last ${state.selectedHours} hrs ▾`;
          timeRangeDropdown.style.display = 'none';
          
          // Call refresh callback if provided
          if (refreshCallback && typeof refreshCallback === 'function') {
            refreshCallback();
          }
        });
      });
      
      // Hide dropdown if clicked elsewhere
      document.addEventListener('click', (event) => {
        if (!timeRangeButton.contains(event.target) && !timeRangeDropdown.contains(event.target)) {
          timeRangeDropdown.style.display = 'none';
        }
      });
    }
    
    // Initialize data source filters
    initializeDataSources(refreshCallback);
    
    // Mark as initialized
    dropdownsInitialized = true;
  }
  
  // Initialize data source filters
  function initializeDataSources(refreshCallback) {
    // Fetch available data sources
    fetchDataSources().then(sources => {
      // Find the source filter section
      const sourceFilterSection = document.querySelector('.filter-section:nth-child(5)');
      if (!sourceFilterSection) return;
      
      const filterTagsContainer = sourceFilterSection.querySelector('.filter-tags');
      if (!filterTagsContainer) return;
      
      // Clear existing tags
      filterTagsContainer.innerHTML = '';
      
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
        
        tag.addEventListener('click', function() {
          // Update active state for all tags
          filterTagsContainer.querySelectorAll('.filter-tag').forEach(t => {
            t.classList.remove('active');
            t.style.backgroundColor = '';
            t.style.color = '';
          });
          
          // Activate this tag
          this.classList.add('active');
          this.style.backgroundColor = '#3872f2';
          this.style.color = 'white';
          
          // Update state
          state.activeSource = this.dataset.sourceId;
          
          // Refresh data if callback provided
          if (refreshCallback && typeof refreshCallback === 'function') {
            refreshCallback();
          }
        });
        
        filterTagsContainer.appendChild(tag);
      });
    });
  }

  function addArgoCDStyles() {
    const style = document.createElement('style');
    style.textContent = `
      .argocd-event {
        border: 2px dashed #9966cc;
        opacity: 0.9;
      }
      .badge-argocd {
        background-color: rgba(102, 51, 153, 0.15);
        color: #9966cc;
      }
      .timeline-event.argocd {
        border: 2px dashed #9966cc;
        opacity: 0.9;
      }
    `;
    document.head.appendChild(style);
  }

  // Initialize utility module
  function initialize(refreshCallback) {
    if (initialized) return;
    
    // Initialize dropdowns
    initializeDropdowns(refreshCallback);
    
    // Add CSS for Prometheus events
    addPrometheusStyles();
    
    // Add CSS for ArgoCD events
    addArgoCDStyles();

    // Mark as initialized
    initialized = true;
  }
  
  function fetchArgoCDData() {
    return fetch(`/api/argocd_data?hours=${state.selectedHours}`)
      .then(response => response.json())
      .then(data => {
        console.log('ArgoCD data received:', data);
        return data;
      })
      .catch(error => {
        console.error('Error fetching ArgoCD data:', error);
        return [];
      });
  }

  // Add CSS styles for Prometheus events
  function addPrometheusStyles() {
    const style = document.createElement('style');
    style.textContent = `
      .prometheus-event {
        border: 2px dashed white;
        opacity: 0.9;
      }
      .badge-prometheus {
        background-color: rgba(240, 96, 40, 0.15);
        color: #f06028;
      }
      .source-tag {
        display: inline-block;
        font-size: 10px;
        margin-left: 4px;
        padding: 1px 4px;
        border-radius: 3px;
        background-color: rgba(240, 96, 40, 0.1);
        color: #f06028;
      }
    `;
    document.head.appendChild(style);
  }

  // Public API
  return {
    state,
    elements,
    formatTimestamp,
    percentAlong,
    fetchTimelineData,
    fetchTimelineHistory,
    fetchPrometheusData,
    fetchClusterIssues,
    fetchKubeContexts,
    fetchNamespaces,
    fetchDataSources,
    renderTimelineTracks,
    updateTimelineRuler,
    startAutoRefresh,
    stopAutoRefresh,
    clearSearchFilter,
    initialize,
    initializeDropdowns,
    initializeDataSources
  };
})();

// Export for global use
window.KuberaUtils = KuberaUtils;

// These functions need to be in global scope as they're called from HTML onclick attributes
function openAnalysisPanel(issueType, source = 'kubernetes') {
  const panel = document.getElementById('analysisPanel');
  const title = panel.querySelector('.analysis-title');
  const content = panel.querySelector('.analysis-content');
  
  // Handle different sources with appropriate labels
  let sourceLabel = '';
  if (source === 'prometheus') {
    sourceLabel = ' [Prometheus]';
  } else if (source === 'argocd') {
    sourceLabel = ' [ArgoCD]';
  } else {
    sourceLabel = ''; // Kubernetes is the default, no need for a label
  }
  
  title.textContent = `Investigating alert: ${issueType}${sourceLabel}`;
  content.innerHTML = '<div style="text-align: center; padding: 20px;"><i class="fas fa-spinner fa-spin fa-2x"></i><p>Loading analysis...</p></div>';
  
  // Show the panel
  panel.classList.add('open');
  
  // For ArgoCD events, direct to the ArgoCD-specific endpoint
  if (source === 'argocd') {
    fetch(`/api/analyze/argocd/${issueType}`)
      .then(response => response.json())
      .then(data => {
        renderArgoCDAnalysis(data);
      })
      .catch(error => {
        content.innerHTML = `<div class="error-message">Error loading analysis: ${error.message}</div>`;
      });
    return;
  }
  
  // For Kubernetes and Prometheus, use the regular endpoint
  fetch(`/api/analyze/${issueType}?source=${source}`)
    .then(response => response.json())
    .then(data => {
      renderAnalysis(data, source);
    })
    .catch(error => {
      content.innerHTML = `<div class="error-message">Error loading analysis: ${error.message}</div>`;
    });
}

// Render the analysis data in the panel
function renderAnalysis(data, source = 'kubernetes') {
  const content = document.querySelector('.analysis-content');
  
  if (!data || !data.analysis || data.analysis.length === 0) {
    content.innerHTML = `<div class="error-message">No analysis data available</div>`;
    return;
  }
  
  let html = '';
  
  // Add source indicator based on the source
  let sourceClass = '';
  let sourceInfo = '';
  
  if (source === 'prometheus') {
    sourceClass = 'prometheus-source';
    sourceInfo = `<div class="section-info" style="margin-bottom: 15px; color: #f06028;">
      <i class="fas fa-chart-line"></i> This analysis is based on Prometheus metrics data.
     </div>`;
  } else if (source === 'argocd') {
    sourceClass = 'argocd-source';
    sourceInfo = `<div class="section-info" style="margin-bottom: 15px; color: #9966cc;">
      <i class="fas fa-code-branch"></i> This analysis is based on ArgoCD application data.
     </div>`;
  }
  
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

function closeAnalysisPanel() {
  const panel = document.getElementById('analysisPanel');
  panel.classList.remove('open');
}
