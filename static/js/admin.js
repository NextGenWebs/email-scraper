/**
 * Admin Panel JavaScript
 * Comprehensive user, project, and system management
 */

// State management
let currentUserPage = 1;
let currentProjectPage = 1;
let currentSearch = '';
let currentUserFilter = 'all';
let currentProjectFilter = 'all';
let healthRefreshInterval = null;
let systemRefreshInterval = null;
let currentTab = 'users';

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    loadHealthStatus();
    loadStats();
    loadUsers();

    // Setup search
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(function() {
            currentSearch = this.value;
            currentUserPage = 1;
            loadUsers();
        }, 500));
    }

    // Setup user filter
    const statusFilter = document.getElementById('statusFilter');
    if (statusFilter) {
        statusFilter.addEventListener('change', function() {
            currentUserFilter = this.value;
            currentUserPage = 1;
            loadUsers();
        });
    }

    // Setup project filter
    const projectStatusFilter = document.getElementById('projectStatusFilter');
    if (projectStatusFilter) {
        projectStatusFilter.addEventListener('change', function() {
            currentProjectFilter = this.value;
            currentProjectPage = 1;
            loadProjects();
        });
    }

    // Start health refresh interval
    startHealthRefresh();
});

// ============================================
// TAB MANAGEMENT
// ============================================

function switchTab(tabName) {
    currentTab = tabName;

    // Hide all tab panels
    document.querySelectorAll('.tab-panel').forEach(tab => {
        tab.style.display = 'none';
        tab.classList.remove('active');
    });

    // Remove active class from all tab buttons
    document.querySelectorAll('.admin-tab').forEach(btn => {
        btn.classList.remove('active');
    });

    // Show selected tab panel
    const tabElement = document.getElementById(tabName + 'Tab');
    if (tabElement) {
        tabElement.style.display = 'block';
        tabElement.classList.add('active');
    }

    // Add active class to clicked button
    if (event && event.target) {
        // Handle click on icon inside button
        const btn = event.target.closest('.admin-tab');
        if (btn) {
            btn.classList.add('active');
        }
    }

    // Stop system refresh if leaving system/queues tab
    stopSystemRefresh();

    // Load data for tab
    switch(tabName) {
        case 'users':
            loadUsers();
            break;
        case 'projects':
            loadProjects();
            break;
        case 'system':
            loadSystemHealth();
            startSystemRefresh();  // Auto-refresh system stats every 5 seconds
            break;
        case 'queues':
            loadQueueStatus();
            startSystemRefresh();  // Also refresh queue stats
            break;
    }
}

// ============================================
// HEALTH STATUS
// ============================================

function loadHealthStatus() {
    fetch('/admin/api/system-health')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateHealthCards(data);
            }
        })
        .catch(error => {
            console.error('Error loading health status:', error);
            setHealthCardError('database');
            setHealthCardError('redis');
            setHealthCardError('workers');
            setHealthCardError('system');
        });
}

function updateHealthCards(data) {
    const health = data.health || data;

    // Database health
    const dbCard = document.getElementById('dbHealth');
    if (dbCard) {
        const dbStatus = health.database?.healthy;
        dbCard.className = `health-card health-status ${dbStatus ? 'health-ok' : 'health-error'}`;
        dbCard.querySelector('.status-text').textContent = dbStatus ? 'Connected' : 'Error';
    }

    // Redis health
    const redisCard = document.getElementById('redisHealth');
    if (redisCard) {
        const redisStatus = health.redis?.healthy;
        redisCard.className = `health-card health-status ${redisStatus ? 'health-ok' : 'health-error'}`;
        redisCard.querySelector('.status-text').textContent = redisStatus ? 'Connected' : 'Error';
    }

    // Workers health
    const workersCard = document.getElementById('workersHealth');
    if (workersCard) {
        const workerCount = health.workers?.count || 0;
        const hasWorkers = workerCount > 0;
        workersCard.className = `health-card health-status ${hasWorkers ? 'health-ok' : 'health-warning'}`;
        workersCard.querySelector('.status-text').textContent = hasWorkers ? `${workerCount} Active` : 'None';
    }

    // System health
    const systemCard = document.getElementById('systemHealth');
    if (systemCard && health.system) {
        const cpuOk = (health.system.cpu_percent || 0) < 90;
        const memOk = (health.system.memory_percent || 0) < 90;
        const allOk = cpuOk && memOk;
        systemCard.className = `health-card health-status ${allOk ? 'health-ok' : 'health-warning'}`;
        systemCard.querySelector('.status-text').textContent = allOk ? 'Normal' : 'High Load';
    }
}

function setHealthCardError(cardId) {
    const card = document.getElementById(cardId + 'Health');
    if (card) {
        card.className = 'health-card health-status health-error';
        const statusText = card.querySelector('.status-text');
        if (statusText) {
            statusText.textContent = 'Error';
        }
    }
}

function startHealthRefresh() {
    // Refresh health every 30 seconds
    healthRefreshInterval = setInterval(loadHealthStatus, 30000);
}

function stopHealthRefresh() {
    if (healthRefreshInterval) {
        clearInterval(healthRefreshInterval);
        healthRefreshInterval = null;
    }
}

function startSystemRefresh() {
    // Refresh system/queue stats every 2 seconds for real-time monitoring
    stopSystemRefresh();  // Clear any existing interval
    systemRefreshInterval = setInterval(() => {
        if (currentTab === 'system') {
            loadSystemHealth();
        } else if (currentTab === 'queues') {
            loadQueueStatus();
        }
    }, 2000);
}

function stopSystemRefresh() {
    if (systemRefreshInterval) {
        clearInterval(systemRefreshInterval);
        systemRefreshInterval = null;
    }
}

// ============================================
// STATS
// ============================================

function loadStats() {
    fetch('/admin/api/stats')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const stats = data.stats;

                // Update stat cards (matching HTML element IDs)
                updateStatCard('totalUsers', stats.users?.total || 0);
                updateStatCard('totalProjects', stats.projects?.total || 0);
                updateStatCard('totalEmails', stats.scraping?.total_emails || 0);
                updateStatCard('processedUrls', stats.scraping?.processed_urls || 0);

                // Update badges
                const pendingCount = stats.users?.pending || 0;
                const pendingBadge = document.getElementById('pendingBadge');
                if (pendingBadge) {
                    pendingBadge.textContent = `${pendingCount} pending`;
                    pendingBadge.style.display = pendingCount > 0 ? 'inline-block' : 'none';
                }

                const runningCount = stats.projects?.active || 0;
                const runningBadge = document.getElementById('runningBadge');
                if (runningBadge) {
                    runningBadge.textContent = `${runningCount} running`;
                    runningBadge.style.display = runningCount > 0 ? 'inline-block' : 'none';
                }
            }
        })
        .catch(error => console.error('Error loading stats:', error));
}

function updateStatCard(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = formatNumber(value);
    }
}

// ============================================
// USER MANAGEMENT
// ============================================

function loadUsers(page = currentUserPage) {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px;"><i class="fas fa-spinner fa-spin"></i> Loading...</td></tr>';

    fetch(`/admin/api/users?page=${page}&per_page=20&search=${encodeURIComponent(currentSearch)}&status=${currentUserFilter}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                displayUsers(data.users);
                displayPagination(data.pagination, 'userPagination', loadUsers);
            }
        })
        .catch(error => {
            console.error('Error loading users:', error);
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px; color: #dc3545;"><i class="fas fa-exclamation-triangle"></i> Error loading users</td></tr>';
        });
}

function displayUsers(users) {
    const tbody = document.getElementById('usersTableBody');

    if (users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px; color: #666;">No users found</td></tr>';
        return;
    }

    tbody.innerHTML = users.map(user => `
        <tr>
            <td>${escapeHtml(user.email)}</td>
            <td>
                <span class="status-badge status-${user.status}">
                    ${user.status.toUpperCase()}
                </span>
            </td>
            <td>
                <span class="role-badge ${user.is_admin ? 'role-admin' : 'role-user'}">
                    ${user.is_admin ? '<i class="fas fa-crown"></i> Admin' : 'User'}
                </span>
            </td>
            <td>${user.project_count}</td>
            <td>${formatNumber(user.emails_found)}</td>
            <td>${formatDate(user.created_at)}</td>
            <td>${user.last_login ? formatDate(user.last_login) : 'Never'}</td>
            <td>
                <div class="action-btns">
                    <button class="action-btn btn-view" onclick="viewUserDetails(${user.id})" title="View Details">
                        <i class="fas fa-eye"></i>
                    </button>
                    ${getUserActionButtons(user)}
                </div>
            </td>
        </tr>
    `).join('');
}

function getUserActionButtons(user) {
    let buttons = [];

    if (user.status === 'pending') {
        buttons.push(`<button class="action-btn btn-approve" onclick="approveUser(${user.id})" title="Approve"><i class="fas fa-check"></i></button>`);
    }

    if (user.status === 'active' || user.status === 'pending') {
        if (!user.is_admin) {
            buttons.push(`<button class="action-btn btn-block" onclick="blockUser(${user.id})" title="Block"><i class="fas fa-ban"></i></button>`);
        }
    }

    if (user.status === 'blocked') {
        buttons.push(`<button class="action-btn btn-approve" onclick="unblockUser(${user.id})" title="Unblock"><i class="fas fa-unlock"></i></button>`);
    }

    if (user.status === 'suspended') {
        buttons.push(`<button class="action-btn btn-approve" onclick="unsuspendUser(${user.id})" title="Unsuspend"><i class="fas fa-play"></i></button>`);
    }

    if (!user.is_admin && user.status === 'active') {
        buttons.push(`<button class="action-btn btn-promote" onclick="promoteUser(${user.id})" title="Promote to Admin"><i class="fas fa-arrow-up"></i></button>`);
    }

    if (user.is_admin) {
        buttons.push(`<button class="action-btn btn-demote" onclick="demoteUser(${user.id})" title="Demote"><i class="fas fa-arrow-down"></i></button>`);
    }

    return buttons.join('');
}

function viewUserDetails(userId) {
    const modal = document.getElementById('userDetailsModal');
    const content = document.getElementById('userDetailsContent');

    if (!modal || !content) return;

    content.innerHTML = '<div style="text-align: center; padding: 40px;"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';
    modal.style.display = 'block';

    fetch(`/admin/api/users/${userId}/details`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                displayUserDetails(data.user);
            } else {
                content.innerHTML = '<div style="text-align: center; padding: 40px; color: #dc3545;">Error loading user details</div>';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            content.innerHTML = '<div style="text-align: center; padding: 40px; color: #dc3545;">Error loading user details</div>';
        });
}

function displayUserDetails(data) {
    const content = document.getElementById('userDetailsContent');
    const user = data.user || data;
    const stats = data.stats || {};
    const projects = data.projects || [];

    // Determine user status from flags
    let status = 'active';
    if (user.is_blocked) status = 'blocked';
    else if (user.is_suspended) status = 'suspended';
    else if (!user.is_approved) status = 'pending';

    const projectsList = projects.length > 0
        ? projects.map(p => `
            <tr>
                <td>${escapeHtml(p.name)}</td>
                <td><span class="status-badge status-${getProjectStatusClass(p.status)}">${p.status}</span></td>
                <td>${p.progress}%</td>
                <td>${formatNumber(p.emails_found)}</td>
                <td>${formatDate(p.created_at)}</td>
            </tr>
        `).join('')
        : '<tr><td colspan="5" style="text-align: center; padding: 20px;">No projects</td></tr>';

    content.innerHTML = `
        <div class="user-detail-header">
            <h3>${escapeHtml(user.email)}</h3>
            <span class="status-badge status-${status}">${status.toUpperCase()}</span>
            ${user.is_admin ? '<span class="role-badge role-admin"><i class="fas fa-crown"></i> Admin</span>' : ''}
        </div>

        <div class="user-detail-grid">
            <div class="detail-item">
                <label>User ID</label>
                <span>${user.id}</span>
            </div>
            <div class="detail-item">
                <label>Created</label>
                <span>${formatDate(user.created_at)}</span>
            </div>
            <div class="detail-item">
                <label>Last Login</label>
                <span>${user.last_login ? formatDate(user.last_login) : 'Never'}</span>
            </div>
            <div class="detail-item">
                <label>Total Projects</label>
                <span>${stats.total_projects || 0}</span>
            </div>
            <div class="detail-item">
                <label>Total Emails Found</label>
                <span>${formatNumber(stats.total_emails || 0)}</span>
            </div>
            <div class="detail-item">
                <label>Total URLs</label>
                <span>${formatNumber(stats.total_urls || 0)}</span>
            </div>
            <div class="detail-item">
                <label>Proxies Configured</label>
                <span>${stats.total_proxies || 0}</span>
            </div>
        </div>

        <h4 style="margin-top: 20px;">User's Projects (Last 20)</h4>
        <table class="data-table">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Progress</th>
                    <th>Emails</th>
                    <th>Created</th>
                </tr>
            </thead>
            <tbody>
                ${projectsList}
            </tbody>
        </table>
    `;
}

function closeUserDetailsModal() {
    const modal = document.getElementById('userDetailsModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// User action functions
function approveUser(userId) {
    if (!confirm('Approve this user?')) return;
    userAction(userId, 'approve');
}

function blockUser(userId) {
    if (!confirm('Block this user permanently? They will not be able to login.')) return;
    userAction(userId, 'block');
}

function unblockUser(userId) {
    if (!confirm('Unblock this user?')) return;
    userAction(userId, 'unblock');
}

function suspendUser(userId) {
    const days = prompt('Suspend for how many days?', '7');
    if (!days) return;

    fetch(`/admin/api/users/${userId}/suspend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days: parseInt(days) })
    })
        .then(response => response.json())
        .then(data => {
            showNotification(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                loadUsers();
                loadStats();
            }
        })
        .catch(error => showNotification('Error suspending user', 'error'));
}

function unsuspendUser(userId) {
    if (!confirm('Remove suspension from this user?')) return;
    userAction(userId, 'unsuspend');
}

function promoteUser(userId) {
    if (!confirm('Promote this user to admin? They will have full system access.')) return;
    userAction(userId, 'promote');
}

function demoteUser(userId) {
    if (!confirm('Demote this admin to regular user?')) return;
    userAction(userId, 'demote');
}

function userAction(userId, action) {
    fetch(`/admin/api/users/${userId}/${action}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            showNotification(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                loadUsers();
                loadStats();
            }
        })
        .catch(error => showNotification(`Error: ${action} failed`, 'error'));
}

function approveAllPending() {
    if (!confirm('Approve ALL pending users? This cannot be undone.')) return;

    fetch('/admin/api/users/approve-all-pending', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            showNotification(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                loadUsers();
                loadStats();
            }
        })
        .catch(error => showNotification('Error approving users', 'error'));
}

// ============================================
// PROJECT MANAGEMENT
// ============================================

function loadProjects(page = currentProjectPage) {
    const tbody = document.getElementById('projectsTableBody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px;"><i class="fas fa-spinner fa-spin"></i> Loading...</td></tr>';

    let url = `/admin/api/projects?page=${page}&per_page=20`;
    if (currentProjectFilter !== 'all') {
        url += `&status=${currentProjectFilter}`;
    }

    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                displayProjects(data.projects);
                displayPagination(data.pagination, 'projectPagination', loadProjects);
            }
        })
        .catch(error => {
            console.error('Error loading projects:', error);
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px; color: #dc3545;"><i class="fas fa-exclamation-triangle"></i> Error loading projects</td></tr>';
        });
}

function displayProjects(projects) {
    const tbody = document.getElementById('projectsTableBody');

    if (projects.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px; color: #666;">No projects found</td></tr>';
        return;
    }

    tbody.innerHTML = projects.map(project => `
        <tr>
            <td>${project.id}</td>
            <td>${escapeHtml(project.name)}</td>
            <td>${escapeHtml(project.user_email)}</td>
            <td>
                <span class="status-badge status-${getProjectStatusClass(project.status)}">
                    ${project.status.toUpperCase()}
                    ${project.paused ? ' (PAUSED)' : ''}
                </span>
            </td>
            <td>
                <div class="progress-bar-container">
                    <div class="progress-bar" style="width: ${project.progress}%"></div>
                    <span class="progress-text">${project.progress}%</span>
                </div>
            </td>
            <td>${formatNumber(project.total_urls)}</td>
            <td>${formatNumber(project.emails_found)}</td>
            <td>
                <div class="action-btns">
                    ${getProjectActionButtons(project)}
                </div>
            </td>
        </tr>
    `).join('');
}

function getProjectStatusClass(status) {
    switch(status) {
        case 'completed': return 'active';
        case 'running': return 'running';
        case 'queued': return 'pending';
        case 'paused': return 'suspended';
        case 'error': return 'blocked';
        default: return 'pending';
    }
}

function getProjectActionButtons(project) {
    let buttons = [];

    if (project.status === 'running' && !project.paused) {
        buttons.push(`<button class="action-btn btn-suspend" onclick="pauseProject(${project.id})" title="Pause"><i class="fas fa-pause"></i></button>`);
    }

    if (project.paused || project.status === 'paused') {
        buttons.push(`<button class="action-btn btn-approve" onclick="resumeProject(${project.id})" title="Resume"><i class="fas fa-play"></i></button>`);
    }

    if (project.status === 'error' || project.status === 'completed') {
        buttons.push(`<button class="action-btn btn-reset" onclick="resetProject(${project.id})" title="Reset"><i class="fas fa-redo"></i></button>`);
    }

    buttons.push(`<button class="action-btn btn-delete" onclick="deleteProject(${project.id})" title="Delete"><i class="fas fa-trash"></i></button>`);

    return buttons.join('');
}

function pauseProject(projectId) {
    if (!confirm('Pause this project?')) return;
    projectAction(projectId, 'pause');
}

function resumeProject(projectId) {
    if (!confirm('Resume this project?')) return;
    projectAction(projectId, 'resume');
}

function resetProject(projectId) {
    if (!confirm('Reset this project? All scraped data will be cleared and it will start fresh.')) return;
    projectAction(projectId, 'reset');
}

function deleteProject(projectId) {
    if (!confirm('DELETE this project permanently? This cannot be undone.')) return;
    projectAction(projectId, 'delete');
}

function projectAction(projectId, action) {
    fetch(`/admin/api/projects/${projectId}/${action}`, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            showNotification(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                loadProjects();
                loadStats();
            }
        })
        .catch(error => showNotification(`Error: ${action} failed`, 'error'));
}

function recoverStuckProjects() {
    if (!confirm('Attempt to recover stuck projects? Projects stuck for >1 hour will be marked for recovery.')) return;

    fetch('/admin/api/recover-stuck', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            showNotification(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                loadProjects();
            }
        })
        .catch(error => showNotification('Error recovering projects', 'error'));
}

// ============================================
// SYSTEM MONITORING
// ============================================

function loadSystemHealth() {
    fetch('/admin/api/system-health')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateSystemDetails(data);
            }
        })
        .catch(error => {
            console.error('Error loading system health:', error);
        });
}

function updateSystemDetails(data) {
    const health = data.health || data;
    const system = health.system || {};
    const db = health.database || {};
    const redis = health.redis || {};
    const workers = health.workers || {};
    const projects = health.projects || {};

    // Update CPU
    const cpuPercent = Math.round(system.cpu_percent || 0);
    updateElement('cpuPercent', `${cpuPercent}%`);
    updateProgressBar('cpuBar', cpuPercent);

    // Update Memory
    const memPercent = Math.round(system.memory_percent || 0);
    const memUsed = system.memory_used_gb || 0;
    const memTotal = system.memory_total_gb || 0;
    updateElement('memoryPercent', `${memPercent}% (${memUsed}GB / ${memTotal}GB)`);
    updateProgressBar('memoryBar', memPercent);

    // Update Disk
    const diskPercent = Math.round(system.disk_percent || 0);
    const diskUsed = system.disk_used_gb || 0;
    const diskTotal = system.disk_total_gb || 0;
    updateElement('diskPercent', `${diskPercent}% (${diskUsed}GB / ${diskTotal}GB)`);
    updateProgressBar('diskBar', diskPercent);

    // Update Database status
    const dbStatus = document.getElementById('dbStatus');
    if (dbStatus) {
        dbStatus.textContent = db.healthy ? 'Connected' : 'Error';
        dbStatus.className = db.healthy ? 'health-ok' : 'health-error';
    }

    // Update Redis status
    const redisStatusEl = document.getElementById('redisStatus');
    if (redisStatusEl) {
        redisStatusEl.textContent = redis.healthy ? 'Connected' : 'Error';
        redisStatusEl.className = redis.healthy ? 'health-ok' : 'health-error';
    }

    // Update Workers
    updateElement('workerCount', workers.count || 0);
    const workerStatusEl = document.getElementById('workerStatus');
    if (workerStatusEl) {
        workerStatusEl.textContent = workers.active ? 'Running' : 'No workers detected';
        workerStatusEl.className = workers.active ? 'health-ok' : 'health-warning';
    }

    // Update Projects
    updateElement('runningProjects', projects.running || 0);
    updateElement('pausedProjects', projects.paused || 0);
}

function updateElement(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function updateProgressBar(id, percent) {
    const bar = document.getElementById(id);
    if (bar) {
        bar.style.width = `${percent}%`;
        // Update color based on usage
        if (percent >= 90) {
            bar.style.background = 'linear-gradient(90deg, #dc3545, #bd2130)';
        } else if (percent >= 70) {
            bar.style.background = 'linear-gradient(90deg, #ffc107, #fd7e14)';
        } else {
            bar.style.background = 'linear-gradient(90deg, #28a745, #20c997)';
        }
    }
}

function displaySystemDetails(data) {
    const container = document.getElementById('systemDetails');
    if (!container) return;

    const health = data.health || data;
    const system = health.system || {};
    const db = health.database || {};
    const redis = health.redis || {};
    const workers = health.workers || {};

    container.innerHTML = `
        <div class="system-section">
            <h4><i class="fas fa-server"></i> Server Resources</h4>
            <div class="resource-bars">
                <div class="resource-item">
                    <label>CPU Usage</label>
                    <div class="progress-bar-container">
                        <div class="progress-bar ${getResourceClass(system.cpu_percent)}" style="width: ${system.cpu_percent || 0}%"></div>
                        <span class="progress-text">${Math.round(system.cpu_percent || 0)}%</span>
                    </div>
                </div>
                <div class="resource-item">
                    <label>Memory Usage</label>
                    <div class="progress-bar-container">
                        <div class="progress-bar ${getResourceClass(system.memory_percent)}" style="width: ${system.memory_percent || 0}%"></div>
                        <span class="progress-text">${Math.round(system.memory_percent || 0)}% (${system.memory_used_gb || 0}GB / ${system.memory_total_gb || 0}GB)</span>
                    </div>
                </div>
                <div class="resource-item">
                    <label>Disk Usage</label>
                    <div class="progress-bar-container">
                        <div class="progress-bar ${getResourceClass(system.disk_percent)}" style="width: ${system.disk_percent || 0}%"></div>
                        <span class="progress-text">${Math.round(system.disk_percent || 0)}% (${system.disk_used_gb || 0}GB / ${system.disk_total_gb || 0}GB)</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="system-section">
            <h4><i class="fas fa-database"></i> Database</h4>
            <div class="status-row">
                <span>Status:</span>
                <span class="${db.healthy ? 'health-ok' : 'health-error'}">
                    ${db.healthy ? 'Connected' : 'Error'}
                </span>
            </div>
            <div class="status-row">
                <span>Message:</span>
                <span>${escapeHtml(db.message || 'N/A')}</span>
            </div>
        </div>

        <div class="system-section">
            <h4><i class="fas fa-bolt"></i> Redis</h4>
            <div class="status-row">
                <span>Status:</span>
                <span class="${redis.healthy ? 'health-ok' : 'health-error'}">
                    ${redis.healthy ? 'Connected' : 'Error'}
                </span>
            </div>
            <div class="status-row">
                <span>Message:</span>
                <span>${escapeHtml(redis.message || 'N/A')}</span>
            </div>
        </div>

        <div class="system-section">
            <h4><i class="fas fa-cogs"></i> Celery Workers</h4>
            <div class="status-row">
                <span>Active Workers:</span>
                <span>${workers.count || 0}</span>
            </div>
            <div class="status-row">
                <span>Status:</span>
                <span class="${workers.active ? 'health-ok' : 'health-warning'}">
                    ${workers.active ? 'Running' : 'No workers detected'}
                </span>
            </div>
        </div>

        <div class="system-section">
            <h4><i class="fas fa-folder-open"></i> Projects</h4>
            <div class="status-row">
                <span>Running:</span>
                <span>${health.projects?.running || 0}</span>
            </div>
            <div class="status-row">
                <span>Paused:</span>
                <span>${health.projects?.paused || 0}</span>
            </div>
        </div>
    `;
}

function updateResourceBar(barId, percent) {
    const bar = document.getElementById(barId);
    if (bar) {
        bar.style.width = `${percent}%`;
        bar.className = `progress-bar ${getResourceClass(percent)}`;
    }
}

function getResourceClass(percent) {
    if (percent >= 90) return 'bg-danger';
    if (percent >= 70) return 'bg-warning';
    return 'bg-success';
}

// ============================================
// QUEUE MANAGEMENT
// ============================================

function loadQueueStatus() {
    fetch('/admin/api/system-health')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateQueueDetails(data);
            }
        })
        .catch(error => {
            console.error('Error loading queue status:', error);
        });
}

function updateQueueDetails(data) {
    const health = data.health || data;
    const queues = health.queues || {};
    const projects = health.projects || {};

    // Update queue counts
    updateElement('scrapeQueueCount', `${queues.scrape || 0} tasks pending`);
    updateElement('scrapeHighQueueCount', `${queues.scrape_high || 0} tasks pending`);
    updateElement('opsQueueCount', `${queues.ops || 0} tasks pending`);

    // Update project counts
    updateElement('queueRunningProjects', projects.running || 0);
    updateElement('queuePausedProjects', projects.paused || 0);
}

function displayQueueDetails(data) {
    const container = document.getElementById('queueDetails');
    if (!container) return;

    const health = data.health || data;
    const queues = health.queues || { scrape: 0, ops: 0, scrape_high: 0 };

    container.innerHTML = `
        <div class="queue-section">
            <h4><i class="fas fa-list"></i> Task Queues</h4>

            <div class="queue-item">
                <div class="queue-info">
                    <span class="queue-name">Scrape Queue</span>
                    <span class="queue-count">${queues.scrape || 0} tasks pending</span>
                </div>
                <button class="action-btn btn-delete" onclick="clearQueue('scrape')" title="Clear Queue">
                    <i class="fas fa-trash"></i> Clear
                </button>
            </div>

            <div class="queue-item">
                <div class="queue-info">
                    <span class="queue-name">High Priority Queue</span>
                    <span class="queue-count">${queues.scrape_high || 0} tasks pending</span>
                </div>
                <button class="action-btn btn-delete" onclick="clearQueue('scrape_high')" title="Clear Queue">
                    <i class="fas fa-trash"></i> Clear
                </button>
            </div>

            <div class="queue-item">
                <div class="queue-info">
                    <span class="queue-name">Operations Queue</span>
                    <span class="queue-count">${queues.ops || 0} tasks pending</span>
                </div>
                <button class="action-btn btn-delete" onclick="clearQueue('ops')" title="Clear Queue">
                    <i class="fas fa-trash"></i> Clear
                </button>
            </div>
        </div>

        <div class="queue-section">
            <h4><i class="fas fa-folder-open"></i> Running Projects</h4>
            <div class="status-row">
                <span>Currently Running:</span>
                <span>${health.projects?.running || 0}</span>
            </div>
            <div class="status-row">
                <span>Paused:</span>
                <span>${health.projects?.paused || 0}</span>
            </div>
        </div>

        <div class="queue-section">
            <h4><i class="fas fa-tools"></i> Queue Actions</h4>
            <div class="queue-actions">
                <button class="btn btn-warning" onclick="clearQueue('all')">
                    <i class="fas fa-broom"></i> Clear All Queues
                </button>
                <button class="btn btn-primary" onclick="recoverStuckProjects()">
                    <i class="fas fa-wrench"></i> Recover Stuck Projects
                </button>
            </div>
        </div>

        <div class="queue-section">
            <h4><i class="fas fa-info-circle"></i> Queue Information</h4>
            <p style="color: #666; font-size: 14px;">
                <strong>Scrape Queue:</strong> Handles URL scraping tasks with 24-hour timeout<br>
                <strong>High Priority Queue:</strong> Priority scraping tasks<br>
                <strong>Ops Queue:</strong> Handles proxy testing and maintenance tasks with 5-minute timeout
            </p>
        </div>
    `;
}

function clearQueue(queueName) {
    const queueLabel = queueName === 'all' ? 'ALL queues' : `the ${queueName} queue`;
    if (!confirm(`Clear ${queueLabel}? This will cancel all pending tasks.`)) return;

    fetch('/admin/api/queue/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ queue: queueName })
    })
        .then(response => response.json())
        .then(data => {
            showNotification(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                loadQueueStatus();
            }
        })
        .catch(error => showNotification('Error clearing queue', 'error'));
}

// ============================================
// PAGINATION
// ============================================

function displayPagination(pagination, containerId, loadFunction) {
    const container = document.getElementById(containerId);
    if (!container || !pagination) {
        if (container) container.innerHTML = '';
        return;
    }

    if (pagination.pages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '<div class="pagination">';

    if (pagination.has_prev) {
        html += `<button class="page-btn" onclick="${loadFunction.name}(${pagination.page - 1})"><i class="fas fa-chevron-left"></i></button>`;
    }

    // Page numbers
    const startPage = Math.max(1, pagination.page - 2);
    const endPage = Math.min(pagination.pages, pagination.page + 2);

    if (startPage > 1) {
        html += `<button class="page-btn" onclick="${loadFunction.name}(1)">1</button>`;
        if (startPage > 2) html += '<span class="page-dots">...</span>';
    }

    for (let i = startPage; i <= endPage; i++) {
        html += `<button class="page-btn ${i === pagination.page ? 'active' : ''}" onclick="${loadFunction.name}(${i})">${i}</button>`;
    }

    if (endPage < pagination.pages) {
        if (endPage < pagination.pages - 1) html += '<span class="page-dots">...</span>';
        html += `<button class="page-btn" onclick="${loadFunction.name}(${pagination.pages})">${pagination.pages}</button>`;
    }

    if (pagination.has_next) {
        html += `<button class="page-btn" onclick="${loadFunction.name}(${pagination.page + 1})"><i class="fas fa-chevron-right"></i></button>`;
    }

    html += '</div>';
    container.innerHTML = html;
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return num.toLocaleString();
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func.apply(this, args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function showNotification(message, type) {
    // Create toast notification
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
        <span>${escapeHtml(message)}</span>
    `;

    // Add to page
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 10000;';
        document.body.appendChild(container);
    }

    container.appendChild(toast);

    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.classList.add('toast-fade');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('userDetailsModal');
    if (event.target === modal) {
        closeUserDetailsModal();
    }
};

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    stopHealthRefresh();
    stopSystemRefresh();
});
