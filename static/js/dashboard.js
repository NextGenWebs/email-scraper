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
            location.reload();
        }
    })
    .catch(error => {
        showAlert('Error creating project: ' + error, 'error');
    });
});

function exportData(projectId, format) {
    window.location.href = `/api/projects/${projectId}/export/${format}`;
}

function deleteProject(projectId) {
    showConfirm('Are you sure you want to delete this project? All scraped data will be permanently removed.', () => {
        fetch(`/api/projects/${projectId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('Project deleted successfully', 'success');
                setTimeout(() => location.reload(), 1500);
            } else {
                showAlert('Error: ' + (data.error || 'Failed to delete project'), 'error');
            }
        })
        .catch(error => {
            showAlert('Error deleting project: ' + error, 'error');
        });
    });
}

window.onclick = function(event) {
    const modal = document.getElementById('newProjectModal');
    if (event.target == modal) {
        closeModal();
    }
}

function updateProjectProgress() {
    const projectCards = document.querySelectorAll('[data-project-id]');
    
    projectCards.forEach(card => {
        const projectId = card.dataset.projectId;
        const statusBadge = card.querySelector('.status-badge');
        
        if (statusBadge && statusBadge.textContent.toLowerCase() === 'running') {
            fetch(`/api/projects/${projectId}`)
                .then(response => response.json())
                .then(data => {
                    const progressBar = card.querySelector('.progress-fill');
                    if (progressBar) {
                        progressBar.style.width = data.progress + '%';
                    }
                    
                    const progressText = card.querySelector('.progress-text');
                    if (progressText) {
                        progressText.textContent = `${data.processed_urls}/${data.total_urls} URLs (${data.progress}%)`;
                    }
                    
                    const emailsFound = card.querySelector('.stat-value');
                    if (emailsFound) {
                        emailsFound.textContent = data.emails_found.toLocaleString();
                    }
                    
                    if (data.status !== 'running') {
                        statusBadge.textContent = data.status.charAt(0).toUpperCase() + data.status.slice(1);
                        statusBadge.className = 'status-badge status-' + data.status;
                        
                        if (data.status === 'completed') {
                            setTimeout(() => location.reload(), 2000);
                        }
                    }
                })
                .catch(error => {
                    console.error('Error updating project:', error);
                });
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    updateProjectProgress();
    setInterval(updateProjectProgress, 5000);
});
