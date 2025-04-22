// Kubera Timeline Component
// Simplified version that uses the shared utility functions

document.addEventListener('DOMContentLoaded', function() {
  // Use the shared state from KuberaUtils
  const state = KuberaUtils.state;
  
  // Initialize local DOM elements
  const presetSelector = document.getElementById('presetSelector');
  const analysisPanel = document.getElementById('analysisPanel');
  const filterTags = document.querySelectorAll('.filter-tag');
  const refreshTimelineButton = document.getElementById('refreshTimelineButton');
  const timeRangeButton = document.getElementById('timeRangeButton');
  const timeRangeDropdown = document.getElementById('timeRangeDropdown');

  // Skip initialization if already loaded by dashboard.js
  if (window.kuberaTimelineInitialized) {
    console.debug("Skipping timeline.js initialization as it's already loaded");
    return;
  }
  window.kuberaTimelineInitialized = true;

  // Initialize timeline component
  function init() {
    // Set default values
    timeRangeButton.innerHTML = `<i class="fas fa-clock btn-icon"></i> Last ${state.selectedHours} hrs ▾`;

    // Highlight default item in time range dropdown
    const defaultItem = timeRangeDropdown?.querySelector(`[data-hours="${state.selectedHours}"]`);
    if (defaultItem) {
      defaultItem.classList.add('active');
    }

    // Set up event listeners
    setupEventListeners();
    
    // Fetch initial data
    fetchData();
    
    // Start auto-refresh
    KuberaUtils.startAutoRefresh(fetchData);
  }

  // Fetch all needed data
  function fetchData() {
    // Determine which timeline endpoint to use based on hours
    if (state.selectedHours <= 6) {
      KuberaUtils.fetchTimelineData()
        .then(data => {
          KuberaUtils.renderTimelineTracks(data);
          KuberaUtils.updateTimelineRuler();
          applyFilters(data);
        });
    } else {
      KuberaUtils.fetchTimelineHistory()
        .then(data => {
          KuberaUtils.renderTimelineTracks(data);
          KuberaUtils.updateTimelineRuler();
          applyFilters(data);
        });
    }
  }

  // Apply filters to timeline data
  function applyFilters(data) {
    if (!data) return;
    
    // Get active filters
    const activeApp = document.querySelector('.filter-section:nth-child(2) .filter-tag.active')?.textContent;
    const activeAlert = document.querySelector('.filter-section:nth-child(3) .filter-tag.active')?.textContent;
    const activePriority = document.querySelector('.filter-section:nth-child(4) .filter-tag.active')?.textContent;
    const activeSource = document.querySelector('.filter-section:nth-child(5) .filter-tag.active')?.textContent;
    
    console.log('Active filters:', { activeApp, activeAlert, activePriority, activeSource });
    
    // Filter the timeline data
    const filteredData = data.filter(item => {
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
    KuberaUtils.renderTimelineTracks(filteredData);
  }

  // Set up event listeners
  function setupEventListeners() {
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
          
          // Store in shared state
          state.activePriority = this.textContent;
        } else {
          // For other filters, just toggle the active class
          const siblings = Array.from(this.parentNode.children);
          siblings.forEach(sibling => sibling.classList.remove('active'));
          this.classList.add('active');
        }
        
        // Re-fetch and apply filters
        fetchData();
      });
    });
    
    // Handle preset selector change if present
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
            state.selectedHours = 1;
            timeRangeButton.innerHTML = `<i class="fas fa-clock btn-icon"></i> Last 1 hr ▾`;
            KuberaUtils.updateTimelineRuler();
            fetchData();
            break;
          case 'all':
          default:
            // Reset filters
            document.querySelectorAll('.filter-section .filter-tag:first-child').forEach(tag => {
              tag.click();
            });
            // Reset time range
            state.selectedHours = 6;
            timeRangeButton.innerHTML = `<i class="fas fa-clock btn-icon"></i> Last 6 hrs ▾`;
            KuberaUtils.updateTimelineRuler();
            fetchData();
            break;
        }
      });
    }
    
    // Add refresh button handler
    if (refreshTimelineButton) {
      refreshTimelineButton.addEventListener('click', fetchData);
    }
    
    // Handle time range dropdown
    if (timeRangeButton && timeRangeDropdown) {
      timeRangeButton.addEventListener('click', function() {
        timeRangeDropdown.style.display = 
          timeRangeDropdown.style.display === 'block' ? 'none' : 'block';
      });
      
      timeRangeDropdown.querySelectorAll('.dropdown-item').forEach(item => {
        item.addEventListener('click', function() {
          // Update active class
          timeRangeDropdown.querySelectorAll('.dropdown-item').forEach(i => 
            i.classList.remove('active')
          );
          this.classList.add('active');
          
          // Update hour setting and button text
          state.selectedHours = parseInt(this.getAttribute('data-hours'), 10);
          timeRangeButton.innerHTML = 
            `<i class="fas fa-clock btn-icon"></i> Last ${state.selectedHours} hrs ▾`;
          
          // Hide dropdown
          timeRangeDropdown.style.display = 'none';
          
          // Refresh data
          fetchData();
        });
      });
      
      // Close dropdown when clicking elsewhere
      document.addEventListener('click', function(e) {
        if (!timeRangeButton.contains(e.target) && !timeRangeDropdown.contains(e.target)) {
          timeRangeDropdown.style.display = 'none';
        }
      });
    }
  }

  // Start initialization
  init();
});
