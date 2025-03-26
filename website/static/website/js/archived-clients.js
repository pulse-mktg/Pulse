/**
 * archived-clients.js - Handles archived clients modal functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize the archived clients modal functionality
    initArchivedClientsModal();
});

/**
 * Initialize the archived clients modal
 */
function initArchivedClientsModal() {
    // Get the button that opens the modal
    const showArchivedBtn = document.getElementById('showArchivedClientsBtn');
    if (!showArchivedBtn) return;
    
    // Get the modal element
    const archivedModal = document.getElementById('archivedClientsModal');
    if (!archivedModal) return;
    
    // Initialize the CoreUI modal
    const archivedClientsModal = new coreui.Modal(archivedModal);
    
    // Add click handler to the button
    showArchivedBtn.addEventListener('click', function() {
        // Fetch archived clients when the button is clicked
        fetchArchivedClients();
        
        // Show the modal
        archivedClientsModal.show();
    });
    
    // Listen for the modal hidden event to clear the table
    archivedModal.addEventListener('hidden.coreui.modal', function() {
        const tableBody = archivedModal.querySelector('tbody');
        if (tableBody) {
            tableBody.innerHTML = '';
        }
    });
}

/**
 * Fetch archived clients via AJAX
 */
function fetchArchivedClients() {
    // Show loading indicator
    const tableBody = document.querySelector('#archivedClientsModal tbody');
    tableBody.innerHTML = `
        <tr>
            <td colspan="4" class="text-center py-4">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2 text-muted">Loading archived clients...</p>
            </td>
        </tr>
    `;
    
    // Make API request
    fetch('/api/archived-clients/', {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            updateArchivedClientsTable(data.clients);
        } else {
            // Show error message
            tableBody.innerHTML = `
                <tr>
                    <td colspan="4" class="text-center py-4">
                        <div class="alert alert-danger">
                            <i class="bi bi-exclamation-triangle me-2"></i>
                            ${data.message || 'An error occurred while fetching archived clients.'}
                        </div>
                    </td>
                </tr>
            `;
        }
    })
    .catch(error => {
        console.error('Error fetching archived clients:', error);
        // Show error message
        tableBody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center py-4">
                    <div class="alert alert-danger">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        An error occurred while fetching archived clients.
                    </div>
                </td>
            </tr>
        `;
    });
}

/**
 * Update the archived clients table with the fetched data
 */
function updateArchivedClientsTable(clients) {
    const tableBody = document.querySelector('#archivedClientsModal tbody');
    
    // Clear the table
    tableBody.innerHTML = '';
    
    // If no archived clients, show message
    if (!clients || clients.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="4" class="text-center py-4">
                    <div class="alert alert-info">
                        <i class="bi bi-info-circle me-2"></i>
                        No archived clients found.
                    </div>
                </td>
            </tr>
        `;
        return;
    }
    
    // Add client rows to the table
    clients.forEach(client => {
        const row = document.createElement('tr');
        
        // Client name cell with logo
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
                <span>${client.name}</span>
            </div>
        `;
        
        // Created date cell
        const createdCell = document.createElement('td');
        createdCell.textContent = client.created_at;
        
        // Archived date cell
        const archivedCell = document.createElement('td');
        archivedCell.textContent = client.archived_at;
        
        // Actions cell
        const actionsCell = document.createElement('td');
        actionsCell.innerHTML = `
            <button class="btn btn-sm btn-success unarchive-client" data-client-id="${client.id}">
                <i class="bi bi-arrow-counterclockwise me-1"></i> Restore
            </button>
        `;
        
        // Append cells to the row
        row.appendChild(nameCell);
        row.appendChild(createdCell);
        row.appendChild(archivedCell);
        row.appendChild(actionsCell);
        
        // Append the row to the table body
        tableBody.appendChild(row);
    });
    
    // Add event listeners for unarchive buttons
    document.querySelectorAll('.unarchive-client').forEach(button => {
        button.addEventListener('click', function() {
            const clientId = this.getAttribute('data-client-id');
            unarchiveClient(clientId, this);
        });
    });
}

/**
 * Unarchive a client via AJAX
 */
function unarchiveClient(clientId, button) {
    // Disable the button and show loading state
    button.disabled = true;
    const originalText = button.innerHTML;
    button.innerHTML = `
        <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
        Restoring...
    `;
    
    // Make API request
    fetch(`/api/client/${clientId}/unarchive/`, {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Remove the row from the table
            const row = button.closest('tr');
            row.style.backgroundColor = '#d1e7dd';
            
            // Add success checkmark and message
            button.innerHTML = `
                <i class="bi bi-check-circle me-1"></i> Restored!
            `;
            button.classList.remove('btn-success');
            button.classList.add('btn-outline-success');
            
            // After a delay, remove the row with animation
            setTimeout(() => {
                row.style.transition = 'opacity 0.5s ease';
                row.style.opacity = '0';
                setTimeout(() => {
                    row.remove();
                    
                    // If no rows left, show the "no clients" message
                    const tableBody = document.querySelector('#archivedClientsModal tbody');
                    if (tableBody.querySelectorAll('tr').length === 0) {
                        tableBody.innerHTML = `
                            <tr>
                                <td colspan="4" class="text-center py-4">
                                    <div class="alert alert-info">
                                        <i class="bi bi-info-circle me-2"></i>
                                        No archived clients found.
                                    </div>
                                </td>
                            </tr>
                        `;
                    }
                }, 500);
            }, 1500);
            
            // Show a success notification
            showNotification('success', data.message);
            
            // Optionally, refresh the active clients list
            refreshActiveClients();
            
        } else {
            // Reset the button and show error message
            button.disabled = false;
            button.innerHTML = originalText;
            showNotification('danger', data.message || 'Failed to restore client.');
        }
    })
    .catch(error => {
        console.error('Error unarchiving client:', error);
        // Reset the button
        button.disabled = false;
        button.innerHTML = originalText;
        showNotification('danger', 'An error occurred while restoring the client.');
    });
}

/**
 * Show a notification message
 */
function showNotification(type, message) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `toast align-items-center text-white bg-${type} border-0`;
    notification.setAttribute('role', 'alert');
    notification.setAttribute('aria-live', 'assertive');
    notification.setAttribute('aria-atomic', 'true');
    
    notification.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-coreui-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    // Add to container (create if it doesn't exist)
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        document.body.appendChild(container);
    }
    
    container.appendChild(notification);
    
    // Initialize and show the toast
    const toast = new coreui.Toast(notification);
    toast.show();
    
    // Remove after it's hidden
    notification.addEventListener('hidden.coreui.toast', function() {
        notification.remove();
    });
}

/**
 * Refresh the active clients list if it exists on the page
 */
function refreshActiveClients() {
    // Check if the clients table exists
    const clientTable = document.querySelector('table.table tbody');
    if (!clientTable) return;
    
    // Fetch active clients
    fetch('/api/clients/', {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success' && data.clients) {
            // Update active clients count in the stats section
            const activeClientsCount = document.querySelector('.active_clients_count');
            const totalClientsCount = document.querySelector('.total_clients_count');
            
            if (activeClientsCount && totalClientsCount) {
                activeClientsCount.textContent = data.clients.length;
                totalClientsCount.textContent = data.clients.length;
            }
            
            // Update the table - but use the global function from home.js
            if (typeof window.updateClientTable === 'function') {
                window.updateClientTable(data.clients);
            } else {
                // If the global function doesn't exist, do a manual update
                updateClientTableManually(data.clients);
            }
        }
    })
    .catch(error => {
        console.error('Error refreshing active clients:', error);
    });
}

/**
 * Manual implementation to update the client table
 * This avoids the recursive call that was causing the stack overflow
 */
function updateClientTableManually(clients) {
    // Get the table body
    const tableBody = document.querySelector('table.table tbody');
    if (!tableBody) return;
    
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
    if (typeof window.initializeActionButtons === 'function') {
        window.initializeActionButtons();
    } else if (typeof initializeActionButtons === 'function') {
        initializeActionButtons();
    }
}

/**
 * Get CSRF token from cookie or form
 */
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