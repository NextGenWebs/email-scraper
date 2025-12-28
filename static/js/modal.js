function showAlert(message, type = 'info') {
    const modal = document.createElement('div');
    modal.className = 'custom-modal';
    modal.innerHTML = `
        <div class="custom-modal-content alert-modal">
            <div class="custom-modal-header ${type === 'error' ? 'error' : type === 'success' ? 'success' : 'info'}">
                <i class="fas ${type === 'error' ? 'fa-exclamation-circle' : type === 'success' ? 'fa-check-circle' : 'fa-info-circle'}"></i>
                <h3>${type === 'error' ? 'Error' : type === 'success' ? 'Success' : 'Information'}</h3>
            </div>
            <div class="custom-modal-body">
                <div>${message}</div>
            </div>
            <div class="custom-modal-footer">
                <button class="btn btn-primary modal-ok-btn">OK</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('show'), 10);
    
    const okBtn = modal.querySelector('.modal-ok-btn');
    okBtn.focus();
    
    const closeModal = () => {
        modal.classList.remove('show');
        setTimeout(() => modal.remove(), 300);
    };
    
    okBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });
    
    document.addEventListener('keydown', function escHandler(e) {
        if (e.key === 'Escape') {
            closeModal();
            document.removeEventListener('keydown', escHandler);
        }
    });
}

function showConfirm(message, onConfirm, onCancel = null) {
    const modal = document.createElement('div');
    modal.className = 'custom-modal';
    modal.innerHTML = `
        <div class="custom-modal-content confirm-modal">
            <div class="custom-modal-header warning">
                <i class="fas fa-question-circle"></i>
                <h3>Confirm Action</h3>
            </div>
            <div class="custom-modal-body">
                <div>${message}</div>
            </div>
            <div class="custom-modal-footer">
                <button class="btn btn-secondary modal-cancel-btn">Cancel</button>
                <button class="btn btn-danger modal-confirm-btn">Confirm</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('show'), 10);
    
    const confirmBtn = modal.querySelector('.modal-confirm-btn');
    const cancelBtn = modal.querySelector('.modal-cancel-btn');
    cancelBtn.focus();
    
    const closeModal = () => {
        modal.classList.remove('show');
        setTimeout(() => modal.remove(), 300);
    };
    
    confirmBtn.addEventListener('click', () => {
        closeModal();
        if (onConfirm) onConfirm();
    });
    
    cancelBtn.addEventListener('click', () => {
        closeModal();
        if (onCancel) onCancel();
    });
    
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
            if (onCancel) onCancel();
        }
    });
    
    document.addEventListener('keydown', function escHandler(e) {
        if (e.key === 'Escape') {
            closeModal();
            if (onCancel) onCancel();
            document.removeEventListener('keydown', escHandler);
        }
    });
}
