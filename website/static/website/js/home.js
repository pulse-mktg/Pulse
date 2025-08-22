/**
 * home.js - Client management scripts
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
    
    // Initialize action buttons on page load
    initializeActionButtons();
    
    // Initialize column customization
    initializeColumnCustomization();
});

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
            window.updateClientTable(data.clients);
        }
    })
    .catch(error => {
        console.error('Error fetching clients:', error);
    });
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

// Initialize action buttons - Adding this function definition
window.initializeActionButtons = function() {
    // Find all action buttons
    const actionButtons = document.querySelectorAll('button[data-client-id]');
    console.log(`Found ${actionButtons.length} action buttons`);
    
    // Remove any existing event listeners by cloning and replacing
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
};

// Column customization functionality
function initializeColumnCustomization() {
    console.log('Initializing column customization');
    
    // Get the column settings button and add click handler
    const columnSettingsBtn = document.getElementById('columnSettingsBtn');
    if (columnSettingsBtn) {
        console.log('Column settings button found');
        columnSettingsBtn.addEventListener('click', function() {
            console.log('Column settings button clicked');
            
            // Get the modal element
            const modalElement = document.getElementById('columnSettingsModal');
            
            // Direct DOM manipulation to show the modal instead of relying on CoreUI
            modalElement.classList.add('show');
            modalElement.style.display = 'block';
            document.body.classList.add('modal-open');
            
            // Create backdrop if it doesn't exist
            let backdrop = document.querySelector('.modal-backdrop');
            if (!backdrop) {
                backdrop = document.createElement('div');
                backdrop.className = 'modal-backdrop fade show';
                document.body.appendChild(backdrop);
            }
            
            // Load saved column preferences from localStorage
            loadColumnPreferences();
        });
    } else {
        console.error('Column settings button not found!');
    }
    
    // Close modal when clicking the close button
    const closeButtons = document.querySelectorAll('[data-coreui-dismiss="modal"]');
    closeButtons.forEach(button => {
        button.addEventListener('click', function() {
            closeColumnSettingsModal();
        });
    });
    
    // Save column settings when button is clicked
    const saveColumnSettingsBtn = document.getElementById('saveColumnSettings');
    if (saveColumnSettingsBtn) {
        saveColumnSettingsBtn.addEventListener('click', function() {
            saveColumnPreferences();
            
            // Show toast notification
            showToast('Column settings saved', 'Your column preferences have been saved.');
            
            // Hide the modal
            closeColumnSettingsModal();
        });
    }
    
    // Function to close the modal
    function closeColumnSettingsModal() {
        const modalElement = document.getElementById('columnSettingsModal');
        modalElement.classList.remove('show');
        modalElement.style.display = 'none';
        document.body.classList.remove('modal-open');
        
        // Remove backdrop
        const backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) {
            backdrop.remove();
        }
    }
    
    // Apply saved column preferences on page load
    applyColumnPreferences();
}

// Function to save column preferences to localStorage
function saveColumnPreferences() {
    const checkboxes = document.querySelectorAll('.column-checkbox');
    const preferences = {};
    
    checkboxes.forEach(checkbox => {
        const column = checkbox.getAttribute('data-column');
        preferences[column] = checkbox.checked;
    });
    
    localStorage.setItem('clientTableColumns', JSON.stringify(preferences));
    applyColumnPreferences();
}

// Function to load column preferences from localStorage
function loadColumnPreferences() {
    const storedPreferences = localStorage.getItem('clientTableColumns');
    if (!storedPreferences) return;
    
    const preferences = JSON.parse(storedPreferences);
    const checkboxes = document.querySelectorAll('.column-checkbox');
    
    checkboxes.forEach(checkbox => {
        const column = checkbox.getAttribute('data-column');
        if (preferences.hasOwnProperty(column)) {
            checkbox.checked = preferences[column];
        }
    });
}

// Function to apply column preferences to the table
function applyColumnPreferences() {
    const storedPreferences = localStorage.getItem('clientTableColumns');
    if (!storedPreferences) return;
    
    const preferences = JSON.parse(storedPreferences);
    
    // Update column visibility in the table
    Object.entries(preferences).forEach(([column, isVisible]) => {
        const tableHeaders = document.querySelectorAll(`th.column-toggle[data-column="${column}"]`);
        const tableData = document.querySelectorAll(`td.column-data[data-column="${column}"]`);
        
        tableHeaders.forEach(header => {
            header.style.display = isVisible ? '' : 'none';
        });
        
        tableData.forEach(cell => {
            cell.style.display = isVisible ? '' : 'none';
        });
    });
}

// Function to show toast notification
function showToast(title, message) {
    const toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        console.error('Toast container not found!');
        return;
    }
    
    console.log('Showing toast:', title);
    
    const toastHtml = `
        <div class="toast show" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header">
                <strong class="me-auto">${title}</strong>
                <button type="button" class="btn-close toast-close"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toast = toastContainer.lastElementChild;
    
    // Add event listener to close button
    const closeBtn = toast.querySelector('.toast-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', function() {
            toast.remove();
        });
    }
    
    // Auto-remove the toast after 3 seconds
    setTimeout(() => {
        if (toast && toast.parentNode) {
            toast.classList.remove('show');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }
    }, 3000);
}

// Make updateClientTable global so it can be used by other scripts
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
    const activeClientsCountElement = document.querySelector('.active_clients_count');
    const totalClientsCountElement = document.querySelector('.total_clients_count');
    
    if (activeClientsCountElement && totalClientsCountElement) {
        let activeCount = 0;
        clients.forEach(client => {
            if (client.is_active) {
                activeCount++;
            }
        });
        
        activeClientsCountElement.textContent = activeCount;
        totalClientsCountElement.textContent = clients.length;
    }
    
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
        
        // Create metrics cells
        const impressionsCell = document.createElement('td');
        impressionsCell.className = 'column-data';
        impressionsCell.setAttribute('data-column', 'impressions');
        impressionsCell.textContent = client.metrics ? client.metrics.impressions.toLocaleString() : '0';
        
        const clicksCell = document.createElement('td');
        clicksCell.className = 'column-data';
        clicksCell.setAttribute('data-column', 'clicks');
        clicksCell.textContent = client.metrics ? client.metrics.clicks.toLocaleString() : '0';
        
        const ctrCell = document.createElement('td');
        ctrCell.className = 'column-data';
        ctrCell.setAttribute('data-column', 'ctr');
        ctrCell.textContent = client.metrics ? `${client.metrics.ctr}%` : '0%';
        
        const conversionsCell = document.createElement('td');
        conversionsCell.className = 'column-data';
        conversionsCell.setAttribute('data-column', 'conversions');
        conversionsCell.textContent = client.metrics ? Math.round(client.metrics.conversions).toLocaleString() : '0';
        
        const convRateCell = document.createElement('td');
        convRateCell.className = 'column-data';
        convRateCell.setAttribute('data-column', 'conversion_rate');
        convRateCell.textContent = client.metrics ? `${client.metrics.conversion_rate}%` : '0%';
        
        // Create actions cell
        const actionsCell = document.createElement('td');
        actionsCell.innerHTML = `
            <button class="btn btn-sm btn-outline-secondary" type="button" data-client-id="${client.id}">
                Actions
            </button>
        `;
        
        // Append all cells to row
        row.appendChild(nameCell);
        row.appendChild(impressionsCell);
        row.appendChild(clicksCell);
        row.appendChild(ctrCell);
        row.appendChild(conversionsCell);
        row.appendChild(convRateCell);
        row.appendChild(actionsCell);
        
        // Add row to table
        tableBody.appendChild(row);
    });
    
    // Apply saved column preferences
    applyColumnPreferences();
    
    // Reinitialize action buttons
    window.initializeActionButtons();
};