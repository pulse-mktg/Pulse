/**
 * home.js - Client management scripts with client loading functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Home.js loaded successfully');
    
    // Check if we have clients on the page
    const clientTable = document.querySelector('table.table tbody');
    const clientTableExists = document.querySelector('table.table');
    
    // If the client table exists but has no rows, load clients via AJAX
    if (clientTableExists && (!clientTable || clientTable.children.length === 0)) {
        console.log('No clients found on initial load, fetching via AJAX...');
        fetchClients();
    }
    
    // Function to fetch clients via AJAX
    function fetchClients() {
        fetch('/api/clients/', {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && data.clients) {
                updateClientTable(data.clients);
            }
        })
        .catch(error => {
            console.error('Error fetching clients:', error);
        });
    }
    
    // Function to update the client table with fetched data
    window.updateClientTable = function(clients) {
        if (clients.length === 0) {
            return;
        }
        
        const tableBody = document.querySelector('table.table tbody');
        if (!tableBody) {
            console.error('Could not find table body to update');
            return;
        }
        
        // Update stats counters
        document.querySelector('.total_clients_count').textContent = clients.length;
        
        let activeCount = 0;
        clients.forEach(client => {
            if (client.is_active) {
                activeCount++;
            }
        });
        document.querySelector('.active_clients_count').textContent = activeCount;
        
        // Clear existing rows
        tableBody.innerHTML = '';
        
        // Add client rows
        clients.forEach(client => {
            const row = document.createElement('tr');
            
            // Create client name cell with logo
            const nameCell = document.createElement('td');
            nameCell.innerHTML = `
                <div class="d-flex align-items-center">
                    ${client.logo ? 
                        `<div class="me-3" style="width: 32px; height: 32px;">
                            <img src="${client.logo}" alt="${client.name} logo" class="img-fluid rounded">
                        </div>` : 
                        `<div class="me-3 bg-light d-flex align-items-center justify-content-center rounded" style="width: 32px; height: 32px;">
                            <i class="bi bi-person" style="font-size: 1rem; color: #8a93a2;"></i>
                        </div>`
                    }
                    ${client.name}
                </div>
            `;
            
            // Create date cell
            const dateCell = document.createElement('td');
            dateCell.textContent = client.created_at;
            
            // Create status cell
            const statusCell = document.createElement('td');
            statusCell.innerHTML = client.is_active ? 
                '<span class="badge bg-success">Active</span>' : 
                '<span class="badge bg-secondary">Inactive</span>';
            
            // Create groups cell
            const groupsCell = document.createElement('td');
            if (client.groups && client.groups.length > 0) {
                let groupsHtml = '<div class="d-flex flex-wrap gap-1">';
                for (let i = 0; i < Math.min(client.groups.length, 2); i++) {
                    const group = client.groups[i];
                    groupsHtml += `
                        <span class="badge" style="background-color: ${group.color};">
                            <i class="bi ${group.icon_class} me-1"></i>
                            ${group.name}
                        </span>
                    `;
                }
                if (client.groups.length > 2) {
                    groupsHtml += `<span class="badge bg-secondary">+${client.groups.length - 2}</span>`;
                }
                groupsHtml += '</div>';
                groupsCell.innerHTML = groupsHtml;
            } else {
                groupsCell.innerHTML = '<span class="text-muted">None</span>';
            }
            
            // Create actions cell
            const actionsCell = document.createElement('td');
            actionsCell.innerHTML = `
                <button class="btn btn-sm btn-outline-secondary" type="button" data-client-id="${client.id}">
                    Actions
                </button>
            `;
            
            // Append all cells to row
            row.appendChild(nameCell);
            row.appendChild(dateCell);
            row.appendChild(statusCell);
            row.appendChild(groupsCell);
            row.appendChild(actionsCell);
            
            // Add row to table
            tableBody.appendChild(row);
        });
        
        // Reinitialize action buttons
        initializeActionButtons();
    }
    
    // Function to get CSRF token
    function getCsrfToken() {
        const csrfCookie = document.cookie
            .split(';')
            .map(cookie => cookie.trim())
            .find(cookie => cookie.startsWith('csrftoken='));
        
        if (csrfCookie) {
            return csrfCookie.split('=')[1];
        }
        
        // Fallback to the CSRF token in the DOM
        const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return csrfInput ? csrfInput.value : '';
    }
    
    // Initialize action buttons
    window.initializeActionButtons() = function() {
        // Find all action buttons
        const actionButtons = document.querySelectorAll('button[data-client-id]');
        console.log(`Found ${actionButtons.length} action buttons`);
        
        // Remove any existing event listeners
        actionButtons.forEach(button => {
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);
        });
        
        // Add click handlers to action buttons
        document.querySelectorAll('button[data-client-id]').forEach(button => {
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
    }
    
    // Initialize action buttons on page load
    initializeActionButtons();
});