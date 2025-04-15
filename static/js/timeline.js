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
  
  // Fetch timeline data from API
  function fetchTimelineData() {
    // In a real implementation, this would be an actual API call
    // For now, we'll simulate it
    console.log('Fetching timeline data...');
    
    // Simulated API response delay
    setTimeout(() => {
      // We're using the hard-coded data from the HTML for now
      // In reality, this would come from your Flask backend
      processTimelineData();
    }, 500);
  }
  
  // Process timeline data
  function processTimelineData() {
    // For now, we'll just use the timeline tracks that are already in the HTML
    console.log('Processing timeline data...');
    
    // Apply any active filters
    applyFilters();
  }
  
  // Apply filters to timeline data
  function applyFilters() {
    // Get active filters
    const activeApp = document.querySelector('.filter-section:nth-child(2) .filter-tag.active').textContent;
    const activeAlert = document.querySelector('.filter-section:nth-child(3) .filter-tag.active').textContent;
    const activePriority = document.querySelector('.filter-section:nth-child(4) .filter-tag.active').textContent;
    const activeSource = document.querySelector('.filter-section:nth-child(5) .filter-tag.active').textContent;
    
    console.log('Active filters:', { activeApp, activeAlert, activePriority, activeSource });
    
    // In a real implementation, you would filter the timeline data based on these values
    // For now, we're just logging them
  }
  
  // Handle filter tag clicks
  filterTags.forEach(tag => {
    tag.addEventListener('click', function() {
      // Remove active class from siblings
      const siblings = Array.from(this.parentNode.children);
      siblings.forEach(sibling => sibling.classList.remove('active'));
      
      // Add active class to clicked tag
      this.classList.add('active');
      
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
          break;
        case 'all':
        default:
          // Reset filters
          document.querySelectorAll('.filter-section .filter-tag:first-child').forEach(tag => {
            tag.click();
          });
          // Reset time range
          timeRange.start = new Date(Date.now() - 6 * 60 * 60 * 1000); // 6 hours ago
          break;
      }
    });
  }
  
  // Event handlers for analysis panel
  window.openAnalysisPanel = function(alertType) {
    const title = document.getElementById('analysisTitle');
    if (title) {
      title.textContent = 'Investigating alert ' + alertType;
    }
    
    // In a real implementation, you would fetch the analysis data for this alert
    // For now, we'll just open the panel with the static content
    
    if (analysisPanel) {
      analysisPanel.classList.add('open');
    }
  };
  
  window.closeAnalysisPanel = function() {
    if (analysisPanel) {
      analysisPanel.classList.remove('open');
    }
  };
  
  // Initialize timeline
  fetchTimelineData();
});
