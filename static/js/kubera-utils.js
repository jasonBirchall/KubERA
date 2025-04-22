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
    currentCluster: '', // Current selected cluster
    showingAllNamespaces: false, // Whether we're showing all namespaces or just the first few
    selectedHours: 6, // Default time range
    filterTerm: ''
  };

  // DOM elements cache
  let elements = {};

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
    return fetch(`/api/timeline_data?hours=${state.selectedHours}`)
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
    return fetch(`/api/timeline_history?hours=${state.selectedHours}`)
      .then(r => r.json())
      .then(data => {
        return data;
      })
      .catch(err => {
        console.error('Error fetching timeline history:', err);
        return [];
      });
  }

  // Fetch cluster issues
  function fetchClusterIssues() {
    return fetch('/api/cluster_issues')
      .then(response => response.json())
      .then(issues => {
        return issues;
      })
      .catch(error => {
        console.error('Error fetching cluster issues:', error);
        return [];
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

      const title = document.createElement('div');
      title.className = 'timeline-track-title';
      title.textContent = `${issue.name} (${issue.count})`;
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
          ev.style.left  = `${leftPct}%`;
          ev.style.width = `${widthPct}%`;
          ev.title = [
            `Pod: ${pod.name}`,
            `Namespace: ${pod.namespace}`,
            `Started: ${new Date(pod.start).toLocaleString()}`,
            pod.end ? `Ended: ${new Date(pod.end).toLocaleString()}`
                    : 'Still occurring'
          ].join('\n');

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

  // Public API
  return {
    state,
    elements,
    formatTimestamp,
    percentAlong,
    fetchTimelineData,
    fetchTimelineHistory,
    fetchClusterIssues,
    fetchKubeContexts,
    fetchNamespaces,
    renderTimelineTracks,
    updateTimelineRuler,
    startAutoRefresh,
    stopAutoRefresh,
    clearSearchFilter
  };
})();

// Export for global use
window.KuberaUtils = KuberaUtils;
