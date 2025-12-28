// Project page state
const projectState = {};

function showNewProjectModal() {
    document.getElementById('newProjectModal').style.display = 'block';
}

function closeModal() {
    document.getElementById('newProjectModal').style.display = 'none';
    document.getElementById('newProjectForm').reset();
}

function switchTab(tab) {
    const tabs = document.querySelectorAll('.tab-content');
    const btns = document.querySelectorAll('.tab-btn');

    tabs.forEach(t => t.classList.remove('active'));
    btns.forEach(b => b.classList.remove('active'));

    if (tab === 'manual') {
        document.getElementById('manualTab').classList.add('active');
        btns[0].classList.add('active');
    } else {
        document.getElementById('csvTab').classList.add('active');
        btns[1].classList.add('active');
    }
}

// Bulk selection functions
function toggleSelectAll(checkbox) {
    const checkboxes = document.querySelectorAll('.project-checkbox');
    checkboxes.forEach(cb => cb.checked = checkbox.checked);
    updateBulkDeleteButton();
}

function updateBulkDeleteButton() {
    const checkboxes = document.querySelectorAll('.project-checkbox:checked');
    const bulkDeleteBtn = document.getElementById('bulkDeleteBtn');
    const selectedCount = document.getElementById('selectedCount');

    if (checkboxes.length > 0) {
        bulkDeleteBtn.style.display = 'inline-block';
        selectedCount.textContent = checkboxes.length;
    } else {
        bulkDeleteBtn.style.display = 'none';
    }

    const allCheckboxes = document.querySelectorAll('.project-checkbox');
    const selectAllCheckbox = document.getElementById('selectAllProjects');
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = checkboxes.length === allCheckboxes.length && allCheckboxes.length > 0;
    }
}

function bulkDeleteProjects() {
    const checkboxes = document.querySelectorAll('.project-checkbox:checked');
    const projectIds = Array.from(checkboxes).map(cb => parseInt(cb.dataset.projectId));

    if (projectIds.length === 0) {
        showAlert('No projects selected', 'error');
        return;
    }

    if (!confirm(`Are you sure you want to delete ${projectIds.length} project(s)? This action cannot be undone.`)) {
        return;
    }

    fetch('/api/projects/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_ids: projectIds })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(`Deleted ${data.deleted} project(s)`, 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showAlert('Error: ' + (data.error || 'Unknown error'), 'error');
        }
    })
    .catch(error => showAlert('Error: ' + error, 'error'));
}

document.getElementById('newProjectForm').addEventListener('submit', function(e) {
    e.preventDefault();

    const formData = new FormData(this);

    fetch('/api/projects', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showAlert('Error: ' + data.error, 'error');
        } else {
            closeModal();
            if (data.message) showAlert(data.message, 'success');
            setTimeout(() => location.reload(), 1500);
        }
    })
    .catch(error => showAlert('Error: ' + error, 'error'));
});

function refreshProject(projectId) {
    fetch(`/api/projects/${projectId}`)
    .then(response => response.json())
    .then(data => {
        const formatNumber = (num) => num.toLocaleString('en-US');

        document.getElementById(`progress-${projectId}`).style.width = data.progress + '%';
        document.getElementById(`progress-text-${projectId}`).textContent =
            `${formatNumber(data.processed_urls)} of ${formatNumber(data.total_urls)} (${data.progress}%)`;
        document.getElementById(`processed-${projectId}`).textContent =
            `${formatNumber(data.processed_urls)} / ${formatNumber(data.total_urls)}`;
        document.getElementById(`emails-${projectId}`).textContent = formatNumber(data.emails_found);

        const projectItem = document.getElementById(`project-${projectId}`);
        const badge = projectItem.querySelector('.badge');
        badge.textContent = data.status.charAt(0).toUpperCase() + data.status.slice(1);
        badge.className = 'badge badge-' + data.status;
    })
    .catch(error => console.error('Error refreshing:', error));
}

// Social media icon generator
function getSocialIcons(item) {
    const socials = [
        { key: 'facebook_link', icon: 'fab fa-facebook', color: '#1877F2', title: 'Facebook' },
        { key: 'twitter_link', icon: 'fab fa-twitter', color: '#1DA1F2', title: 'Twitter/X' },
        { key: 'linkedin_link', icon: 'fab fa-linkedin', color: '#0A66C2', title: 'LinkedIn' },
        { key: 'instagram_link', icon: 'fab fa-instagram', color: '#E4405F', title: 'Instagram' },
        { key: 'youtube_link', icon: 'fab fa-youtube', color: '#FF0000', title: 'YouTube' },
        { key: 'pinterest_link', icon: 'fab fa-pinterest', color: '#BD081C', title: 'Pinterest' },
        { key: 'tiktok_link', icon: 'fab fa-tiktok', color: '#000000', title: 'TikTok' },
    ];

    let icons = '';
    socials.forEach(s => {
        if (item[s.key]) {
            icons += `<a href="${escapeHtml(item[s.key])}" target="_blank" title="${s.title}" style="margin-right: 8px; color: ${s.color}; font-size: 18px;"><i class="${s.icon}"></i></a>`;
        }
    });

    return icons || '<span style="color: #999;">-</span>';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getDomainFromUrl(url) {
    try {
        const parsed = new URL(url.startsWith('http') ? url : 'https://' + url);
        return parsed.hostname.replace('www.', '');
    } catch {
        return url;
    }
}

function viewResults(projectId) {
    const resultsDiv = document.getElementById(`results-${projectId}`);

    if (resultsDiv.style.display === 'block') {
        resultsDiv.style.display = 'none';
        return;
    }

    // Always reset state when opening results (start from page 1)
    projectState[projectId] = { page: 1, perPage: 50, loading: false, hasNext: false, hasPrev: false };

    // Disable buttons initially until data loads
    const prevBtn = document.getElementById(`prev-${projectId}`);
    const nextBtn = document.getElementById(`next-${projectId}`);
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;

    resultsDiv.style.display = 'block';
    loadResultsPage(projectId, 'current');
}

function loadResultsPage(projectId, direction) {
    if (!projectState[projectId]) {
        projectState[projectId] = { page: 1, perPage: 50, loading: false, hasNext: false, hasPrev: false };
    }

    const state = projectState[projectId];

    // Prevent multiple simultaneous requests
    if (state.loading) {
        return;
    }

    // Calculate new page based on direction
    let newPage = state.page;
    if (direction === 'next' && state.hasNext) {
        newPage = state.page + 1;
    } else if (direction === 'prev' && state.hasPrev) {
        newPage = state.page - 1;
    } else if (direction !== 'current') {
        // Can't go in requested direction, ignore click
        return;
    }

    // Set loading state
    state.loading = true;
    const prevBtn = document.getElementById(`prev-${projectId}`);
    const nextBtn = document.getElementById(`next-${projectId}`);
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;

    // Show loading indicator
    const tbody = document.querySelector(`#table-${projectId} tbody`);
    tbody.innerHTML = '<tr><td colspan="6" class="text-center"><i class="fas fa-spinner fa-spin"></i> Loading...</td></tr>';

    fetch(`/api/projects/${projectId}/results?page=${newPage}&per_page=${state.perPage}`)
    .then(response => response.json())
    .then(response => {
        tbody.innerHTML = '';

        const data = response.items || [];

        // Update pagination state
        state.page = response.page || newPage;
        state.hasNext = response.has_next || false;
        state.hasPrev = response.has_prev || false;
        state.totalPages = response.pages || 1;
        state.loading = false;

        // Update pagination UI
        const totalPages = Math.max(response.pages || 1, 1);
        document.getElementById(`page-info-${projectId}`).textContent =
            `Page ${state.page} of ${totalPages} (${response.total || 0} results)`;
        if (prevBtn) prevBtn.disabled = !state.hasPrev;
        if (nextBtn) nextBtn.disabled = !state.hasNext;

        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center">No data scraped yet.</td></tr>';
        } else {
            data.forEach(item => {
                const row = tbody.insertRow();

                // Domain
                const domain = getDomainFromUrl(item.homepage_url);

                // Emails display
                const emails = item.emails_list || [];
                let emailsHtml = '';
                if (emails.length === 0) {
                    emailsHtml = '<span style="color: #999;">-</span>';
                } else if (emails.length === 1) {
                    emailsHtml = `<span style="color: #27AE60;">${escapeHtml(emails[0])}</span>`;
                } else {
                    emailsHtml = `<span style="color: #27AE60;">${escapeHtml(emails[0])}</span>
                        <button class="btn btn-sm" onclick='showAllEmails(${item.id}, ${JSON.stringify(emails)})'
                        style="font-size: 10px; padding: 2px 6px; margin-left: 5px; background: #27AE60; color: white;">
                        +${emails.length - 1}</button>`;
                }

                // Social icons
                const socialIcons = getSocialIcons(item);

                // Contact page
                const contactHtml = item.contact_page_url
                    ? `<a href="${escapeHtml(item.contact_page_url)}" target="_blank" style="color: #3498DB;"><i class="fas fa-envelope"></i></a>`
                    : '<span style="color: #999;">-</span>';

                // Internal links
                const linksHtml = `<span>${item.internal_links_checked}</span>
                    <button class="btn btn-sm" onclick='showAllLinks(${item.id}, ${JSON.stringify(item.internal_links_list || [])})'
                    style="font-size: 10px; padding: 2px 6px; margin-left: 5px;"><i class="fas fa-link"></i></button>`;

                // Status with method
                const methodIcon = item.scrape_method === 'playwright' || item.scrape_method === 'selenium'
                    ? '<i class="fas fa-globe" style="color: #27AE60;" title="JavaScript Rendered"></i>'
                    : '<i class="fas fa-bolt" style="color: #3498DB;" title="Fast Request"></i>';
                const statusHtml = `${methodIcon} <span style="color: ${item.http_status === 200 ? '#27AE60' : '#E74C3C'}">${item.http_status || '-'}</span>`;

                row.innerHTML = `
                    <td><a href="${escapeHtml(item.homepage_url)}" target="_blank" style="color: #2C3E50;">${escapeHtml(domain)}</a></td>
                    <td>${emailsHtml}</td>
                    <td>${socialIcons}</td>
                    <td>${contactHtml}</td>
                    <td>${linksHtml}</td>
                    <td>${statusHtml}</td>
                `;
            });
        }
    })
    .catch(error => {
        // Reset loading state on error
        state.loading = false;
        if (prevBtn) prevBtn.disabled = !state.hasPrev;
        if (nextBtn) nextBtn.disabled = !state.hasNext;
        tbody.innerHTML = '<tr><td colspan="6" class="text-center" style="color: #E74C3C;">Error loading results. Please try again.</td></tr>';
        showAlert('Error loading results: ' + error, 'error');
    });
}

function exportData(projectId, format) {
    window.location.href = `/api/projects/${projectId}/export/${format}`;
}

function deleteProject(projectId) {
    showConfirm('Are you sure you want to delete this project? All data will be permanently removed.', () => {
        fetch(`/api/projects/${projectId}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('Project deleted', 'success');
                setTimeout(() => location.reload(), 1000);
            } else {
                showAlert('Error: ' + (data.error || 'Failed'), 'error');
            }
        })
        .catch(error => showAlert('Error: ' + error, 'error'));
    });
}

function pauseProject(projectId) {
    fetch(`/api/projects/${projectId}/pause`, { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Project paused', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showAlert('Error: ' + (data.error || 'Failed'), 'error');
        }
    })
    .catch(error => showAlert('Error: ' + error, 'error'));
}

function resumeProject(projectId) {
    fetch(`/api/projects/${projectId}/resume`, { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Project resumed', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showAlert('Error: ' + (data.error || 'Failed'), 'error');
        }
    })
    .catch(error => showAlert('Error: ' + error, 'error'));
}

function showAllEmails(itemId, emailsArray) {
    const emailList = emailsArray.map(email => `<li style="padding: 5px 0; border-bottom: 1px solid #eee;">${escapeHtml(email)}</li>`).join('');
    showAlert(`<div style="text-align: left; max-height: 400px; overflow-y: auto;"><ul style="list-style: none; padding: 0; margin: 0;">${emailList}</ul></div>`, 'info');
}

function showAllLinks(itemId, linksArray) {
    const linksList = linksArray.map(link =>
        `<li style="padding: 5px 0; border-bottom: 1px solid #eee;"><a href="${escapeHtml(link)}" target="_blank" style="word-break: break-all;">${escapeHtml(link)}</a></li>`
    ).join('');
    showAlert(`<div style="text-align: left; max-height: 400px; overflow-y: auto;"><ul style="list-style: none; padding: 0; margin: 0;">${linksList}</ul></div>`, 'info');
}

window.onclick = function(event) {
    const modal = document.getElementById('newProjectModal');
    if (event.target == modal) {
        closeModal();
    }
}

// Auto-refresh running projects every 5 seconds
setInterval(function() {
    const runningProjects = document.querySelectorAll('.badge-running');
    runningProjects.forEach(badge => {
        const projectItem = badge.closest('.project-item');
        const projectId = projectItem.id.replace('project-', '');
        refreshProject(projectId);
    });
}, 5000);
