/**
 * home.js - Simple client management scripts
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Home.js loaded successfully');
    
    // Find all action buttons
    const actionButtons = document.querySelectorAll('button[data-client-id]');
    console.log(`Found ${actionButtons.length} action buttons`);
    
    // Add click handlers to action buttons
    actionButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            // Get client ID from button
            const clientId = this.getAttribute('data-client-id');
            console.log(`Action button clicked for client ID: ${clientId}`);
            
            // Create dropdown menu
            const menu = document.createElement('div');
            menu.className = 'action-menu';
            menu.style.position = 'absolute';
            menu.style.backgroundColor = '#fff';
            menu.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
            menu.style.borderRadius = '4px';
            menu.style.padding = '8px 0';
            menu.style.zIndex = '10000';
            menu.style.minWidth = '160px';
            
            // Common styles for links
            const linkStyle = 'display: block; padding: 8px 16px; text-decoration: none; color: #333;';
            
            // Add menu items
            menu.innerHTML = `
                <a href="/client/${clientId}/" style="${linkStyle}">
                    <i class="bi bi-eye me-2"></i>View Details
                </a>
                <a href="/client/${clientId}/edit/" style="${linkStyle}">
                    <i class="bi bi-pencil me-2"></i>Edit
                </a>
                <div style="height: 1px; background-color: #e5e5e5; margin: 8px 0;"></div>
                <a href="/client/${clientId}/archive/" style="${linkStyle} color: #dc3545;" 
                   onclick="return confirm('Are you sure you want to archive this client?');">
                    <i class="bi bi-trash me-2"></i>Archive
                </a>
            `;
            
            // Add hover effects
            menu.querySelectorAll('a').forEach(link => {
                link.addEventListener('mouseover', function() {
                    this.style.backgroundColor = '#f5f5f5';
                });
                link.addEventListener('mouseout', function() {
                    this.style.backgroundColor = '';
                });
            });
            
            // Position the menu
            const rect = this.getBoundingClientRect();
            menu.style.top = (rect.bottom + window.scrollY) + 'px';
            menu.style.left = (rect.left + window.scrollX) + 'px';
            
            // Add to document
            document.body.appendChild(menu);
            
            // Close when clicking outside
            const closeMenu = function(event) {
                if (!menu.contains(event.target) && event.target !== button) {
                    document.body.removeChild(menu);
                    document.removeEventListener('click', closeMenu);
                }
            };
            
            setTimeout(() => {
                document.addEventListener('click', closeMenu);
            }, 0);
        });
    });
});