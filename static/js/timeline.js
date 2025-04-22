document.addEventListener('DOMContentLoaded', function() {
  // Initialize variables
  let timelineData = [];
  let filteredData = [];
  let timeRange = {
    start: new Date(Date.now() - 6 * 60 * 60 * 1000), // 6 hours ago
    end: new Date() // now
  };
  
  // DOM elements
  const presetSelector = document.getElementById('presetSelector');
  const analysisPanel = document.getElementById('analysisPanel');
  const filterTags = document.querySelectorAll('.filter-tag');

  let selectedHours = 6; // default time range
  let activePriority = 'All'; // default priority filter

  const timeRangeButton = document.getElementById('timeRangeButton');
  const timeRangeDropdown = document.getElementById('timeRangeDropdown');
  timeRangeButton.innerHTML = `<i class="fas fa-clock btn-icon"></i> Last ${selectedHours} hrs ▾`;

  // Highlight default item (6 hours)
  const defaultItem = timeRangeDropdown.querySelector(`[data-hours="${selectedHours}"]`);
  if (defaultItem) {
    defaultItem.classList.add('active');
  }

  if (timeRangeButton && timeRangeDropdown) {
    timeRangeButton.addEventListener('click', () => {
      timeRangeDropdown.style.display = (timeRangeDropdown.style.display === 'none') ? 'block' : 'none';
    });

    timeRangeDropdown.querySelectorAll('.dropdown-item').forEach(item => {
      item.addEventListener('click', function () {
        // Remove active from all
        timeRangeDropdown.querySelectorAll('.dropdown-item').forEach(i => i.classList.remove('active'));
        
        // Set new active item
        this.classList.add('active');

        // Update selected hours and UI
        selectedHours = parseInt(this.getAttribute('data-hours'), 10);
        timeRangeButton.innerHTML = `<i class="fas fa-clock btn-icon"></i> Last ${selectedHours} hrs ▾`;
        timeRangeDropdown.style.display = 'none';

        fetchTimelineData();
        fetchClusterIssues();
      });
    });

    // Hide dropdown if clicked elsewhere
    document.addEventListener('click', (event) => {
      if (!timeRangeButton.contains(event.target) && !timeRangeDropdown.contains(event.target)) {
        timeRangeDropdown.style.display = 'none';
      }
    });
  }

  function percentAlong(rangeStart, rangeEnd, t) {
    return ((t - rangeStart) / (rangeEnd - rangeStart)) * 100;
  }

  function renderTimelineTracks(issues) {
    const tracks = document.querySelector('.timeline-tracks');
    tracks.innerHTML = '';

    if (!issues || issues.length === 0) {
      tracks.innerHTML = '<div style="padding:15px;color:#7e7e8f;">No issues detected</div>';
      return;
    }

    const windowStart = Date.now() - selectedHours * 60 * 60 * 1000;
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
                            0.8                                      // min width so it’s clickable
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

  // Fetch timeline data from API
  function fetchTimelineData() {
    console.log('Fetching timeline data...');
    fetch(`/api/timeline_data?hours=${selectedHours}`)
      .then(response => response.json())
      .then(data => {
        timelineData = data;
        console.log('Timeline data received:', timelineData);
        processTimelineData();
      })
      .catch(error => {
        console.error('Error fetching timeline data:', error);
      });
  }
  
  // Process timeline data
  function processTimelineData() {
    console.log('Processing timeline data...');
    
    // Apply any active filters
    applyFilters();
  }

  // Update timeline ruler with accurate time markers
  function updateTimelineRuler() {
    const ruler = document.querySelector('.timeline-ruler');
    ruler.innerHTML = '';

    const segments = 7;
    for (let i = 0; i < segments; i++) {
      const marker = document.createElement('div');
      const time = new Date(Date.now() - (selectedHours * 60 * 60 * 1000) + (i * selectedHours * 60 * 60 * 1000 / (segments - 1)));
      marker.textContent = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      ruler.appendChild(marker);
    }
  }

  // Apply filters to timeline data
  function applyFilters() {
    // Get active filters
    const activeApp = document.querySelector('.filter-section:nth-child(2) .filter-tag.active')?.textContent;
    const activeAlert = document.querySelector('.filter-section:nth-child(3) .filter-tag.active')?.textContent;
    const activePriority = document.querySelector('.filter-section:nth-child(4) .filter-tag.active')?.textContent;
    const activeSource = document.querySelector('.filter-section:nth-child(5) .filter-tag.active')?.textContent;
    
    console.log('Active filters:', { activeApp, activeAlert, activePriority, activeSource });
    
    // Filter the timeline data
    filteredData = timelineData.filter(item => {
      // If namespace filter is not "All", filter by namespace
      if (activeApp && activeApp !== "All") {
        // Check if any pod in this item is in the selected namespace
        const podsInNamespace = item.pods?.filter(pod => pod.namespace === activeApp);
        if (!podsInNamespace || podsInNamespace.length === 0) {
          return false;
        }
      }
      
      // Filter by priority/severity if not "All"
      if (activePriority && activePriority !== "All") {
        const priority = activePriority.toLowerCase();
        if (item.severity !== priority) {
          return false;
        }
      }
      
      return true;
    });
    
    // Render filtered data
    renderTimelineTracks(filteredData);
    updateTimelineRuler();
  }
  
  // Auto-refresh functionality
  let refreshInterval;

  function startAutoRefresh(intervalSeconds = 30) {
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
    
    refreshInterval = setInterval(() => {
      fetchTimelineData();
      fetchClusterIssues();
      console.log('Auto-refreshed data');
    }, intervalSeconds * 1000);
  }
  
  // Handle filter tag clicks
  filterTags.forEach(tag => {
    tag.addEventListener('click', function() {
      // Get parent filter section
      const filterSection = this.closest('.filter-section');
      if (!filterSection) return;
      
      // Get the filter title to identify which filter this is
      const filterTitle = filterSection.querySelector('.filter-title').textContent;
      
      // Handle different filters
      if (filterTitle === 'Priority') {
        // Remove active class from all priority tags
        filterSection.querySelectorAll('.filter-tag').forEach(t => {
          t.classList.remove('active');
          t.style.color = '#d8d9da';
          t.style.backgroundColor = '#2a2a36';
        });
        
        // Activate the clicked tag
        this.classList.add('active');
        this.style.backgroundColor = '#3872f2';
        this.style.color = 'white';
      } else {
        // For other filters, just toggle the active class
        const siblings = Array.from(this.parentNode.children);
        siblings.forEach(sibling => sibling.classList.remove('active'));
        this.classList.add('active');
      }
      
      // Apply filters
      applyFilters();
    });
  });
  
  // Handle preset selector change
  if (presetSelector) {
    presetSelector.addEventListener('change', function() {
      const preset = this.value;
      console.log('Selected preset:', preset);
      
      // Apply preset filters
      switch (preset) {
        case 'high-priority':
          // Select 'High' priority filter
          const highPriorityTag = document.querySelector('.filter-section:nth-child(4) .filter-tag:nth-child(2)');
          if (highPriorityTag) {
            highPriorityTag.click();
          }
          break;
        case 'recent':
          // Adjust time range to last hour
          timeRange.start = new Date(Date.now() - 60 * 60 * 1000); // 1 hour ago
          updateTimelineRuler();
          break;
        case 'all':
        default:
          // Reset filters
          document.querySelectorAll('.filter-section .filter-tag:first-child').forEach(tag => {
            tag.click();
          });
          // Reset time range
          timeRange.start = new Date(Date.now() - 6 * 60 * 60 * 1000); // 6 hours ago
          updateTimelineRuler();
          break;
      }
    });
  }
  
  // Add sync button handler
  const refreshTimelineButton = document.getElementById('refreshTimelineButton');
  if (refreshTimelineButton) {
    refreshTimelineButton.addEventListener('click', function () {
      fetchTimelineData();
      fetchClusterIssues();
    });
  }

  // Initialize timeline
  fetchTimelineData();
  updateTimelineRuler();
  startAutoRefresh();
});
