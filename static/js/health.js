/**
 * System Health Monitor
 * Checks Redis/Worker status and shows warnings
 */

let lastHealthCheck = null;
let healthCheckInterval = null;

// Check health on page load
document.addEventListener('DOMContentLoaded', function() {
    checkSystemHealth();
    // Check every 30 seconds
    healthCheckInterval = setInterval(checkSystemHealth, 30000);
});

function checkSystemHealth() {
    fetch('/api/health')
        .then(response => response.json())
        .then(data => {
            lastHealthCheck = data;
            updateHealthUI(data);
        })
        .catch(error => {
            console.error('Health check failed:', error);
            showSystemWarning('Unable to check system status', 'error');
        });
}

function updateHealthUI(health) {
    // Remove existing warnings
    removeSystemWarning();
    
    if (health.status === 'unhealthy') {
        showSystemWarning(
            '🔴 System Offline: Redis is not available. Cannot create new projects. Contact administrator.',
            'error',
            true
        );
    } else if (health.status === 'degraded') {
        if (!health.workers.active) {
            showSystemWarning(
                `⚠️ No Workers Running: Projects will be queued but not processed until workers start. <a href="#" onclick="showWorkerHelp(); return false;">How to fix</a>`,
                'warning',
                true
            );
        }
    } else {
        // System healthy - show brief success message only if there was a previous issue
        if (lastHealthCheck && lastHealthCheck.status !== 'healthy') {
            showSystemWarning('✅ System is now healthy and operational', 'success', false);
            setTimeout(removeSystemWarning, 5000);
        }
    }
    
    // Update any health indicators on the page
    updateHealthIndicators(health);
}

function showSystemWarning(message, type, persistent) {
    removeSystemWarning();
    
    const banner = document.createElement('div');
    banner.id = 'system-health-banner';
    banner.className = `health-banner health-${type}`;
    banner.innerHTML = `
        <div class="health-banner-content">
            <span class="health-banner-message">${message}</span>
            ${!persistent ? '<button class="health-banner-close" onclick="removeSystemWarning()">&times;</button>' : ''}
        </div>
    `;
    
    document.body.insertBefore(banner, document.body.firstChild);
}

function removeSystemWarning() {
    const existing = document.getElementById('system-health-banner');
    if (existing) {
        existing.remove();
    }
}

function showWorkerHelp() {
    alert(`To start workers:

Windows:
  python start_workers.py

Linux/Mac:
  python start_workers.py

Or use the one-click startup:
  .\\start.bat (Windows)
  ./start.sh (Linux/Mac)

Contact your administrator if you don't have access to start workers.`);
}

function updateHealthIndicators(health) {
    // Update any health indicators in the UI
    const indicators = document.querySelectorAll('[data-health-indicator]');
    indicators.forEach(indicator => {
        const type = indicator.getAttribute('data-health-indicator');
        
        if (type === 'redis') {
            indicator.className = health.redis.available ? 'status-healthy' : 'status-unhealthy';
            indicator.textContent = health.redis.available ? 'Online' : 'Offline';
        } else if (type === 'workers') {
            indicator.className = health.workers.active ? 'status-healthy' : 'status-warning';
            indicator.textContent = `${health.workers.count} worker(s)`;
        }
    });
}

// Expose functions globally
window.checkSystemHealth = checkSystemHealth;
window.removeSystemWarning = removeSystemWarning;
window.showWorkerHelp = showWorkerHelp;
