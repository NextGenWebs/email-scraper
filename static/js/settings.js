// Load email filters on page load
document.addEventListener('DOMContentLoaded', function() {
    loadEmailFilters();
});

document.getElementById('settingsForm').addEventListener('submit', function(e) {
    e.preventDefault();

    const formData = {
        max_threads: parseInt(document.getElementById('maxThreads').value),
        request_timeout: parseInt(document.getElementById('requestTimeout').value),
        max_retries: parseInt(document.getElementById('maxRetries').value),
        max_internal_links: parseInt(document.getElementById('maxInternalLinks').value),
        url_exclusion_patterns: document.getElementById('urlExclusionPatterns').value.trim(),
        use_proxies: document.getElementById('useProxies').checked
    };
    
    fetch('/api/settings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Settings saved successfully!', 'success');
        } else {
            showAlert('Error saving settings', 'error');
        }
    })
    .catch(error => {
        showAlert('Error saving settings: ' + error, 'error');
    });
});

// Email Filters Functions
function loadEmailFilters() {
    fetch('/api/email-filters')
    .then(response => response.json())
    .then(filters => {
        const filtersList = document.getElementById('filtersList');
        
        if (filters.length === 0) {
            filtersList.innerHTML = '<p class="text-muted">No email filters configured. Click "Add Filter" to create one.</p>';
        } else {
            let html = '<table class="data-table"><thead><tr>';
            html += '<th>Pattern</th><th>Type</th><th>Description</th><th>Active</th><th>Actions</th>';
            html += '</tr></thead><tbody>';
            
            filters.forEach(filter => {
                html += `<tr>
                    <td>${escapeHtml(filter.pattern)}</td>
                    <td>${filter.filter_type}</td>
                    <td>${escapeHtml(filter.description || '-')}</td>
                    <td>
                        <label class="switch">
                            <input type="checkbox" ${filter.is_active ? 'checked' : ''} 
                                onchange="toggleFilter(${filter.id})">
                            <span class="slider"></span>
                        </label>
                    </td>
                    <td>
                        <button class="btn btn-sm btn-danger" onclick="deleteFilter(${filter.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>`;
            });
            
            html += '</tbody></table>';
            filtersList.innerHTML = html;
        }
    })
    .catch(error => {
        console.error('Error loading filters:', error);
        showAlert('Error loading email filters', 'error');
    });
}

function showAddFilterModal() {
    document.getElementById('addFilterModal').style.display = 'block';
}

function closeAddFilterModal() {
    document.getElementById('addFilterModal').style.display = 'none';
    document.getElementById('addFilterForm').reset();
}

document.getElementById('addFilterForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const formData = {
        pattern: document.getElementById('filterPattern').value,
        filter_type: document.getElementById('filterType').value,
        description: document.getElementById('filterDescription').value
    };
    
    fetch('/api/email-filters', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Filter added successfully!', 'success');
            closeAddFilterModal();
            loadEmailFilters();
        } else {
            showAlert('Error adding filter: ' + (data.error || 'Unknown error'), 'error');
        }
    })
    .catch(error => {
        showAlert('Error adding filter: ' + error, 'error');
    });
});

function toggleFilter(filterId) {
    fetch(`/api/email-filters/${filterId}/toggle`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (!data.success) {
            showAlert('Error toggling filter', 'error');
            loadEmailFilters(); // Reload to restore correct state
        }
    })
    .catch(error => {
        showAlert('Error toggling filter: ' + error, 'error');
        loadEmailFilters();
    });
}

function deleteFilter(filterId) {
    if (!confirm('Are you sure you want to delete this filter?')) {
        return;
    }

    fetch(`/api/email-filters/${filterId}`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Filter deleted successfully!', 'success');
            loadEmailFilters();
        } else {
            showAlert('Error deleting filter', 'error');
        }
    })
    .catch(error => {
        showAlert('Error deleting filter: ' + error, 'error');
    });
}

function seedDefaultFilters() {
    fetch('/api/email-filters/seed-defaults', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Default filters added!', 'success');
            loadEmailFilters();
        } else {
            showAlert('Error adding default filters', 'error');
        }
    })
    .catch(error => {
        showAlert('Error: ' + error, 'error');
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Change Password Form Handler
document.getElementById('changePasswordForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const currentPassword = document.getElementById('currentPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    
    if (newPassword !== confirmPassword) {
        showAlert('New passwords do not match', 'error');
        return;
    }
    
    if (newPassword.length < 6) {
        showAlert('Password must be at least 6 characters long', 'error');
        return;
    }
    
    fetch('/api/change-password', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword,
            confirm_password: confirmPassword
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(data.message || 'Password changed successfully!', 'success');
            document.getElementById('changePasswordForm').reset();
        } else {
            showAlert(data.error || 'Error changing password', 'error');
        }
    })
    .catch(error => {
        showAlert('Error changing password: ' + error, 'error');
    });
});
