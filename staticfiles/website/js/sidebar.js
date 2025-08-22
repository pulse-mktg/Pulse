document.addEventListener('DOMContentLoaded', function() {
  const sidebar = document.getElementById('sidebar');
  const wrapper = document.querySelector('.wrapper');

  // Custom layout adjustment function
  function adjustLayout() {
    const windowWidth = window.innerWidth;
    
    // Check if sidebar is completely hidden
    const isSidebarHidden = sidebar.classList.contains('hide');

    if (isSidebarHidden) {
      // Sidebar is hidden, content should take full width
      wrapper.style.cssText = `
        margin-left: 0;
        width: 100%;
        position: relative;
        display: flex;
        flex-direction: column;
        min-height: 100vh;
      `;
    } else {
      // Sidebar is visible
      const isNarrow = sidebar.classList.contains('sidebar-narrow');
      wrapper.style.cssText = `
        margin-left: ${isNarrow ? '60px' : '256px'};
        width: ${isNarrow ? `calc(${windowWidth}px - 60px)` : `calc(${windowWidth}px - 256px)`};
        position: relative;
        display: flex;
        flex-direction: column;
        min-height: 100vh;
      `;
    }
  }

  // Override CoreUI's Sidebar initialization
  const originalSidebarInit = coreui.Sidebar.prototype.init;
  coreui.Sidebar.prototype.init = function() {
    originalSidebarInit.apply(this);
    
    // Add custom event listener to prevent unwanted style setting
    this._element.addEventListener('sidebar-show', adjustLayout);
    this._element.addEventListener('sidebar-hide', adjustLayout);
  };

  // Modify existing sidebar instances
  const sidebarInstances = document.querySelectorAll('[data-coreui-toggle="sidebar"]');
  sidebarInstances.forEach(el => {
    const sidebar = new coreui.Sidebar(el);
    
    // Add event listeners to existing instances
    el.addEventListener('sidebar-show', adjustLayout);
    el.addEventListener('sidebar-hide', adjustLayout);
  });

  // Initial layout adjustment
  adjustLayout();

  // Adjust on window resize
  window.addEventListener('resize', adjustLayout);

  // Observe sidebar class changes
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
        adjustLayout();
      }
    });
  });

  observer.observe(sidebar, { 
    attributes: true, 
    attributeFilter: ['class'] 
  });
  
  // Client dropdown functionality
  // Handle client search
  const searchInput = document.getElementById('clientSearchInput');
  if (searchInput) {
    searchInput.addEventListener('input', function() {
      const searchTerm = this.value.toLowerCase().trim();
      const clientItems = document.querySelectorAll('.client-item');
      
      clientItems.forEach(item => {
        const clientName = item.querySelector('.sidebar-nav-link-text').textContent.toLowerCase();
        if (clientName.includes(searchTerm)) {
          item.style.display = '';
        } else {
          item.style.display = 'none';
        }
      });
    });
    
    // Clear search when dropdown closes
    document.querySelectorAll('.nav-group-toggle').forEach(toggle => {
      toggle.addEventListener('click', function() {
        // Check if this toggle is closing the dropdown
        setTimeout(() => {
          const isExpanded = this.parentElement.classList.contains('show');
          if (!isExpanded) {
            searchInput.value = '';
            document.querySelectorAll('.client-item').forEach(item => {
              item.style.display = '';
            });
          }
        }, 300);
      });
    });
  }

  // Highlight active client based on URL
  const highlightActiveClient = () => {
    const currentPath = window.location.pathname;
    if (currentPath.includes('/client/')) {
      // Extract client ID from the URL
      const matches = currentPath.match(/\/client\/(\d+)/);
      if (matches && matches[1]) {
        const clientId = matches[1];
        document.querySelectorAll('.client-item .sidebar-nav-link').forEach(link => {
          if (link.getAttribute('href').includes(`/client/${clientId}`)) {
            link.classList.add('active');
            
            // Also expand the dropdown if it's not already expanded
            const navGroup = link.closest('.nav-group');
            if (navGroup && !navGroup.classList.contains('show')) {
              const toggle = navGroup.querySelector('.nav-group-toggle');
              if (toggle) {
                // Use CoreUI's API to show the nav group
                const navGroupInstance = new coreui.Collapse(navGroup.querySelector('.nav-group-items'));
                navGroupInstance.show();
                navGroup.classList.add('show');
              }
            }
          }
        });
      }
    }
  };

  // Call on page load
  highlightActiveClient();
});