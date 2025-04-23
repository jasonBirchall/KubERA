// Function to open ArgoCD analysis panel
function openArgoCDAnalysisPanel(appName) {
  const panel = document.getElementById('analysisPanel');
  const title = panel.querySelector('.analysis-title');
  const content = panel.querySelector('.analysis-content');
  
  title.textContent = `Investigating ArgoCD application: ${appName}`;
  content.innerHTML = '<div style="text-align: center; padding: 20px;"><i class="fas fa-spinner fa-spin fa-2x"></i><p>Loading analysis...</p></div>';
  
  // Show the panel
  panel.classList.add('open');
  
  // Fetch analysis data for this ArgoCD application
  fetch(`/api/analyze/argocd/${appName}`)
    .then(response => response.json())
    .then(data => {
      renderArgoCDAnalysis(data);
    })
    .catch(error => {
      content.innerHTML = `<div class="error-message">Error loading analysis: ${error.message}</div>`;
    });
}

// Render the ArgoCD analysis data in the panel
function renderArgoCDAnalysis(data) {
  const content = document.querySelector('.analysis-content');
  
  if (!data || !data.analysis) {
    content.innerHTML = `<div class="error-message">No analysis data available</div>`;
    return;
  }
  
  const result = data.analysis;
  
  // Create health and sync status badges
  const healthClass = getHealthStatusClass(result.health_status);
  const syncClass = getSyncStatusClass(result.sync_status);
  
  const healthBadge = `<span class="health-status ${healthClass}">${result.health_status}</span>`;
  const syncBadge = `<span class="sync-status ${syncClass}">${result.sync_status}</span>`;
  
  let html = `
    <div class="analysis-section argocd-source">
      <div class="app-details">
        <div class="app-details-title">
          <div>
            Application: ${result.app_name}
            ${healthBadge}
            ${syncBadge}
          </div>
        </div>
      </div>
      
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
        <h4>Recent Events</h4>
        <div class="logs-container">
          ${result.app_events && result.app_events.length > 0 
            ? result.app_events.map(event => `<div class="log-line">${event}</div>`).join('')
            : '<div class="log-line">No events available</div>'}
        </div>
      </div>
    </div>
  `;
  
  content.innerHTML = html;
}

// Helper function to get health status class
function getHealthStatusClass(status) {
  switch (status.toLowerCase()) {
    case 'healthy':
      return 'healthy';
    case 'degraded':
      return 'degraded';
    case 'progressing':
      return 'progressing';
    default:
      return '';
  }
}

// Helper function to get sync status class
function getSyncStatusClass(status) {
  switch (status.toLowerCase()) {
    case 'synced':
      return 'synced';
    case 'outofsync':
    case 'out of sync':
      return 'out-of-sync';
    default:
      return '';
  }
}

// Make functions available globally
window.openArgoCDAnalysisPanel = openArgoCDAnalysisPanel;
window.renderArgoCDAnalysis = renderArgoCDAnalysis;
