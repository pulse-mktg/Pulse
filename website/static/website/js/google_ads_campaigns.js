/**
 * Google Ads Campaigns JavaScript
 * Handles campaign filtering and chart visualization
 */

document.addEventListener('DOMContentLoaded', function() {
    // Filter campaigns by status
    initCampaignFilters();
    
    // Initialize performance chart
    initPerformanceChart();
});

/**
 * Initialize campaign status filters
 */
function initCampaignFilters() {
    const statusFilters = document.querySelectorAll('.status-filter button[data-status]');
    const campaignRows = document.querySelectorAll('.campaign-row');
    
    statusFilters.forEach(button => {
        button.addEventListener('click', function() {
            // Update active button
            statusFilters.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            
            const status = this.dataset.status;
            
            // Filter rows
            campaignRows.forEach(row => {
                if (status === 'all' || row.dataset.status === status) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    });
}

/**
 * Initialize the performance chart
 */
function initPerformanceChart() {
    const ctx = document.getElementById('performanceChart');
    if (!ctx) return;
    
    // Get data from the data attribute
    const performanceDataElement = document.getElementById('performance-data');
    if (!performanceDataElement) return;
    
    try {
        const performanceData = JSON.parse(performanceDataElement.getAttribute('data-performance'));
        
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: performanceData.dates,
                datasets: [
                    {
                        label: 'Impressions',
                        data: performanceData.impressions,
                        borderColor: 'rgba(50, 31, 219, 1)',
                        backgroundColor: 'rgba(50, 31, 219, 0.1)',
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: 'Clicks',
                        data: performanceData.clicks,
                        borderColor: 'rgba(39, 174, 96, 1)',
                        backgroundColor: 'rgba(39, 174, 96, 0.1)',
                        fill: true,
                        tension: 0.4,
                        hidden: true
                    },
                    {
                        label: 'Cost',
                        data: performanceData.cost,
                        borderColor: 'rgba(231, 76, 60, 1)',
                        backgroundColor: 'rgba(231, 76, 60, 0.1)',
                        fill: true,
                        tension: 0.4,
                        hidden: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
        
        // Toggle between different metrics
        const metricButtons = document.querySelectorAll('.status-filter button[data-metric]');
        metricButtons.forEach(button => {
            button.addEventListener('click', function() {
                // Update active button
                metricButtons.forEach(btn => btn.classList.remove('active'));
                this.classList.add('active');
                
                const metric = this.dataset.metric;
                
                // Show only selected metric
                chart.data.datasets.forEach(dataset => {
                    if (dataset.label.toLowerCase() === metric) {
                        dataset.hidden = false;
                    } else {
                        dataset.hidden = true;
                    }
                });
                
                chart.update();
            });
        });
    } catch (error) {
        console.error('Error initializing performance chart:', error);
    }
}