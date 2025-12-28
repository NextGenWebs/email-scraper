function showAddProxyModal() {
    document.getElementById('addProxyModal').style.display = 'block';
}

function closeModal() {
    document.getElementById('addProxyModal').style.display = 'none';
    document.getElementById('addProxyForm').reset();
}

function showBulkUploadModal() {
    document.getElementById('bulkUploadModal').style.display = 'block';
}

function closeBulkModal() {
    document.getElementById('bulkUploadModal').style.display = 'none';
    document.getElementById('bulkUploadForm').reset();
}

function switchProxyTab(tab) {
    const tabs = document.querySelectorAll('#bulkUploadModal .tab-content');
    const btns = document.querySelectorAll('#bulkUploadModal .tab-btn');
    
    tabs.forEach(t => t.classList.remove('active'));
    btns.forEach(b => b.classList.remove('active'));
    
    if (tab === 'text') {
        document.getElementById('textTab').classList.add('active');
        btns[0].classList.add('active');
    } else {
        document.getElementById('fileTab').classList.add('active');
        btns[1].classList.add('active');
    }
}

document.getElementById('addProxyForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const formData = {
        proxy_url: document.getElementById('proxyUrl').value,
        proxy_type: document.getElementById('proxyType').value
    };
    
    fetch('/api/proxies', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
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
        showAlert('Error adding proxy: ' + error, 'error');
    });
});

function toggleProxy(proxyId) {
    fetch(`/api/proxies/${proxyId}/toggle`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            location.reload();
        }
    })
    .catch(error => {
        showAlert('Error toggling proxy: ' + error, 'error');
    });
}

function deleteProxy(proxyId) {
    showConfirm('Are you sure you want to delete this proxy?', () => {
        fetch(`/api/proxies/${proxyId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                location.reload();
            }
        })
        .catch(error => {
            showAlert('Error deleting proxy: ' + error, 'error');
        });
    });
}

document.getElementById('bulkUploadForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const formData = new FormData(this);
    
    fetch('/api/proxies/bulk', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showAlert('Error: ' + data.error, 'error');
        } else {
            let message = `Successfully added ${data.added} out of ${data.total} proxies.`;
            if (data.errors && data.errors.length > 0) {
                message += '<br><br>Some errors occurred:<br>' + data.errors.join('<br>');
            }
            showAlert(message, 'success');
            closeBulkModal();
            setTimeout(() => location.reload(), 1500);
        }
    })
    .catch(error => {
        showAlert('Error uploading proxies: ' + error, 'error');
    });
});

window.onclick = function(event) {
    const modal1 = document.getElementById('addProxyModal');
    const modal2 = document.getElementById('bulkUploadModal');
    if (event.target == modal1) {
        closeModal();
    } else if (event.target == modal2) {
        closeBulkModal();
    }
}

function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.proxy-checkbox');
    checkboxes.forEach(cb => cb.checked = selectAll.checked);
}

function getSelectedProxies() {
    const checkboxes = document.querySelectorAll('.proxy-checkbox:checked');
    return Array.from(checkboxes).map(cb => parseInt(cb.value));
}

function bulkDeleteProxies() {
    const proxyIds = getSelectedProxies();
    
    if (proxyIds.length === 0) {
        showAlert('Please select at least one proxy to delete', 'info');
        return;
    }
    
    showConfirm(`Are you sure you want to delete ${proxyIds.length} selected proxies?`, () => {
        fetch('/api/proxies/bulk-delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({proxy_ids: proxyIds})
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert(`Successfully deleted ${data.deleted} proxies`, 'success');
                setTimeout(() => location.reload(), 1500);
            } else {
                showAlert('Error: ' + data.error, 'error');
            }
        })
        .catch(error => {
            showAlert('Error deleting proxies: ' + error, 'error');
        });
    });
}

function bulkExportProxies() {
    const proxyIds = getSelectedProxies();
    
    if (proxyIds.length === 0) {
        showAlert('Please select at least one proxy to export', 'info');
        return;
    }
    
    fetch('/api/proxies/bulk-export', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({proxy_ids: proxyIds})
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const blob = new Blob([data.proxies.join('\n')], {type: 'text/plain'});
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `proxies_export_${Date.now()}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } else {
            showAlert('Error: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showAlert('Error exporting proxies: ' + error, 'error');
    });
}

function testProxy(id) {
    fetch(`/api/proxies/test/${id}`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Proxy test started. Refresh the page in a few seconds to see the results.', 'info');
        } else {
            showAlert('Error: ' + data.error, 'error');
        }
    })
    .catch(error => {
        showAlert('Error testing proxy: ' + error, 'error');
    });
}

function testAllProxies() {
    showConfirm('This will test all proxies. It may take a few minutes. Continue?', () => {
        fetch('/api/proxies/test-all', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert(data.message + '. Refresh the page in a few minutes to see the results.', 'info');
            } else {
                showAlert('Error: ' + data.error, 'error');
            }
        })
        .catch(error => {
            showAlert('Error testing proxies: ' + error, 'error');
        });
    });
}

function activateAllProxies() {
    showConfirm('This will activate ALL offline proxies. Continue?', () => {
        fetch('/api/proxies/bulk-activate', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert(data.message, 'success');
                setTimeout(() => location.reload(), 1000);
            } else {
                showAlert('Error: ' + data.error, 'error');
            }
        })
        .catch(error => {
            showAlert('Error activating proxies: ' + error, 'error');
        });
    });
}
