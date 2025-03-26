/**
 * Google Ads Campaign Detail JavaScript
 * Handles chart visualization for campaign detail page
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize daily performance chart
    initDailyPerformanceChart();
});

/**
 * Initialize the daily performance chart
 */
function initDailyPerformanceChart() {
    const ctx = document.getElementById('dailyPerformanceChart');
    if (!ctx) return;
    
    // Get data from the data attribute
    const dailyDataElement = document.getElementById('daily-performance-data');
    if (!dailyDataElement) return;
    
    try {
        const dailyData = JSON.parse(dailyDataElement.getAttribute('data-performance'));
        
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: dailyData.dates,
                datasets: [
                    {
                        label: 'Impressions',
                        data: dailyData.impressions,
                        borderColor: 'rgba(50, 31, 219, 1)',
                        backgroundColor: 'rgba(50, 31, 219, 0.1)',
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: 'Clicks',
                        data: dailyData.clicks,
                        borderColor: 'rgba(39, 174, 96, 1)',
                        backgroundColor: 'rgba(39, 174, 96, 0.1)',
                        fill: true,
                        tension: 0.4,
                        hidden: true
                    },
                    {
                        label: 'Cost ($)',
                        data: dailyData.cost,
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
        const metricButtons = document.querySelectorAll('.btn-group button[data-metric]');
        metricButtons.forEach(button => {
            button.addEventListener('click', function() {
                // Update active button
                metricButtons.forEach(btn => btn.classList.remove('active'));
                this.classList.add('active');
                
                const metric = this.dataset.metric;
                
                // Show only selected metric
                chart.data.datasets.forEach(dataset => {
                    if (dataset.label.toLowerCase().includes(metric)) {
                        dataset.hidden = false;
                    } else {
                        dataset.hidden = true;
                    }
                });
                
                chart.update();
            });
        });
    } catch (error) {
        console.error('Error initializing daily performance chart:', error);
    }
}