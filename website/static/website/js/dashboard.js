/**
 * dashboard.js - Shared dashboard functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    // Performance chart metric toggles
    initMetricToggles();
    
    // Make client rows in tables clickable
    initClickableRows();
    
    // Initialize dropdowns
    initDropdowns();
});

/**
 * Initialize metric toggle buttons for charts
 */
function initMetricToggles() {
    const metricButtons = document.querySelectorAll('[data-metric]');
    
    if (metricButtons.length > 0) {
        // Get the chart
        const chartId = metricButtons[0].closest('.card').querySelector('canvas').id;
        const chartInstance = Chart.getChart(chartId);
        
        if (chartInstance) {
            metricButtons.forEach(button => {
                button.addEventListener('click', function() {
                    // Update active button
                    metricButtons.forEach(btn => btn.classList.remove('active'));
                    this.classList.add('active');
                    
                    const metric = this.dataset.metric;
                    
                    // Show only selected metric
                    chartInstance.data.datasets.forEach(dataset => {
                        if (dataset.label.toLowerCase() === metric) {
                            dataset.hidden = false;
                        } else {
                            dataset.hidden = true;
                        }
                    });
                    
                    chartInstance.update();
                });
            });
        }
    }
}

/**
 * Make rows with data-client-id clickable to navigate to client dashboard
 */
function initClickableRows() {
    const clientRows = document.querySelectorAll('.client-row[data-client-id]');
    
    clientRows.forEach(row => {
        row.addEventListener('click', function() {
            const clientId = this.dataset.clientId;
            window.location.href = `/client/${clientId}/dashboard/`;
        });
        
        // Change cursor to pointer to indicate clickable
        row.style.cursor = 'pointer';
    });
}

/**
 * Initialize dropdown functionality
 */
function initDropdowns() {
    const dateRangeDropdowns = document.querySelectorAll('.dropdown-menu a[data-date-range]');
    
    dateRangeDropdowns.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Update dropdown button text
            const dropdownButton = this.closest('.dropdown').querySelector('.dropdown-toggle');
            dropdownButton.innerHTML = `<i class="bi bi-calendar-event"></i> ${this.textContent}`;
            
            // Update active class
            this.closest('.dropdown-menu').querySelectorAll('a').forEach(link => {
                link.classList.remove('active');
            });
            this.classList.add('active');
            
            // Get the date range value
            const dateRange = this.dataset.dateRange;
            
            // Add date range to current URL as query parameter
            const url = new URL(window.location.href);
            url.searchParams.set('date_range', dateRange);
            
            // Navigate to new URL
            window.location.href = url.toString();
        });
    });
}

/**
 * Format number with commas
 */
function formatNumber(number) {
    return number.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/**
 * Format currency
 */
function formatCurrency(number) {
    return '$' + number.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/**
 * Format percentage
 */
function formatPercentage(number) {
    return number.toFixed(2) + '%';
}