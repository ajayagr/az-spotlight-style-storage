/**
 * Azure File Explorer - Main Application
 * Uses native JavaScript features (ES6+)
 */

// DOM Elements - cached for performance
const elements = {
    apiKey: document.getElementById('apiKey'),
    fileInput: document.getElementById('fileInput'),
    fileView: document.getElementById('fileView'),
    folderView: document.getElementById('folderView'),
    viewToggle: document.getElementById('viewToggle'),
    uploadOverlay: document.getElementById('uploadOverlay'),
    statusIcon: document.getElementById('statusIcon'),
    uploadTitle: document.getElementById('uploadTitle'),
    uploadStatus: document.getElementById('uploadStatus'),
    uploadDetails: document.getElementById('uploadDetails'),
    progressFill: document.getElementById('progressFill'),
    closeModalBtn: document.getElementById('closeModalBtn'),
    styleSyncToggle: document.getElementById('styleSyncToggle'),
    toastContainer: document.getElementById('toastContainer'),
    styleSyncBanner: document.getElementById('styleSyncBanner'),
    bannerStatus: document.getElementById('bannerStatus'),
    stylesModal: document.getElementById('stylesModal'),
    stylesContent: document.getElementById('stylesContent')
};

// Image file extension pattern
const IMAGE_EXTENSIONS = /\.(png|jpg|jpeg|gif|bmp|webp)$/i;

// Icon mapping for file types
const FILE_ICONS = {
    pdf: { class: 'fa-file-pdf', color: '#ff4040' },
    txt: { class: 'fa-file-alt', color: '#0078d4' },
    md: { class: 'fa-file-alt', color: '#0078d4' },
    zip: { class: 'fa-file-archive', color: '#fce100' },
    rar: { class: 'fa-file-archive', color: '#fce100' },
    default: { class: 'fa-file', color: '#8a8886' }
};

// Toast icon mapping
const TOAST_ICONS = {
    success: 'fa-check-circle',
    error: 'fa-exclamation-circle',
    info: 'fa-info-circle'
};

/**
 * Build the folder view from existing file cards
 */
function buildFolderView() {
    const cards = elements.fileView.querySelectorAll('.file-card');
    const folders = new Map();
    const rootFiles = [];

    cards.forEach(card => {
        const folder = card.dataset.folder;
        const clone = card.cloneNode(true);
        
        // Re-attach event listeners using delegation pattern
        const cardContent = clone.querySelector('.card-content');
        const deleteBtn = clone.querySelector('.btn-delete');
        
        cardContent.addEventListener('click', () => downloadFile(card.dataset.path));
        deleteBtn.addEventListener('click', (e) => deleteFile(card.dataset.path, e));

        if (folder) {
            if (!folders.has(folder)) folders.set(folder, []);
            folders.get(folder).push(clone);
        } else {
            rootFiles.push(clone);
        }
    });

    // Clear and rebuild folder view
    elements.folderView.replaceChildren();

    // Add collapse all / expand all controls
    if (folders.size > 0 || rootFiles.length > 0) {
        const controls = document.createElement('div');
        controls.style.cssText = 'display: flex; gap: 10px; margin-bottom: 20px;';
        controls.innerHTML = `
            <button class="collapse-all-btn" data-action="collapse">
                <i class="fas fa-compress-alt"></i> Collapse All
            </button>
            <button class="collapse-all-btn" data-action="expand">
                <i class="fas fa-expand-alt"></i> Expand All
            </button>
        `;
        
        // Event delegation for collapse buttons
        controls.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (btn) {
                toggleAllFolders(btn.dataset.action === 'collapse');
            }
        });
        
        elements.folderView.append(controls);
    }

    // Root Files First
    if (rootFiles.length > 0) {
        const section = createFolderSection('', 'Root', 'fa-home', rootFiles.length);
        const grid = section.querySelector('.folder-content');
        rootFiles.forEach(f => grid.append(f));
        elements.folderView.append(section);
    }

    // Sorted Folders
    [...folders.keys()].sort().forEach(folderName => {
        const files = folders.get(folderName);
        const section = createFolderSection(folderName, folderName, 'fa-folder', files.length);
        const grid = section.querySelector('.folder-content');
        files.forEach(f => grid.append(f));
        elements.folderView.append(section);
    });

    // Empty state
    if (cards.length === 0) {
        elements.folderView.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-box-open" style="font-size: 64px; margin-bottom: 20px; opacity: 0.5;"></i>
                <h3>No files yet</h3>
                <p>Upload a file to get started.</p>
            </div>
        `;
    }
}

/**
 * Create a folder section element
 */
function createFolderSection(folderPath, displayName, iconClass, fileCount) {
    const section = document.createElement('div');
    section.className = 'folder-section';
    section.innerHTML = `
        <div class="folder-header" data-folder="${folderPath}">
            <i class="fas ${iconClass} folder-icon"></i> ${displayName}
            <span class="folder-file-count">${fileCount} files</span>
            <button class="folder-delete-btn" data-delete-folder="${folderPath}" title="Delete ${folderPath ? 'entire folder' : 'all root files'}">
                <i class="fas fa-trash-alt"></i>
            </button>
            <i class="fas fa-chevron-down collapse-icon"></i>
        </div>
        <div class="file-grid folder-content"></div>
    `;
    
    // Event delegation for header
    const header = section.querySelector('.folder-header');
    header.addEventListener('click', (e) => {
        // Don't toggle if clicking delete button
        if (e.target.closest('.folder-delete-btn')) {
            e.stopPropagation();
            deleteFolder(folderPath, e);
            return;
        }
        toggleFolder(header);
    });
    
    return section;
}

/**
 * Toggle between file and folder view
 */
function toggleView() {
    const showFolders = elements.viewToggle.checked;
    elements.fileView.classList.toggle('hidden', showFolders);
    elements.folderView.classList.toggle('hidden', !showFolders);
}

/**
 * Toggle individual folder collapse state
 */
function toggleFolder(headerEl) {
    const content = headerEl.nextElementSibling;
    const isCollapsed = headerEl.classList.toggle('collapsed');
    content.classList.toggle('collapsed', isCollapsed);
}

/**
 * Toggle all folders collapse/expand
 */
function toggleAllFolders(collapse) {
    elements.folderView.querySelectorAll('.folder-header').forEach(header => {
        const content = header.nextElementSibling;
        if (content?.classList.contains('folder-content')) {
            header.classList.toggle('collapsed', collapse);
            content.classList.toggle('collapsed', collapse);
        }
    });
}

/**
 * Show upload overlay with status
 */
function showOverlay(title, status, isLoading = true) {
    elements.uploadOverlay.classList.remove('hidden');
    elements.uploadTitle.textContent = title;
    elements.uploadStatus.textContent = status;
    elements.statusIcon.className = isLoading 
        ? 'fas fa-spinner status-icon loading' 
        : 'fas fa-check-circle status-icon success';
    elements.closeModalBtn.classList.toggle('hidden', isLoading);
}

/**
 * Update progress bar
 */
function updateProgress(percent, details = '') {
    elements.progressFill.style.width = `${percent}%`;
    if (details) elements.uploadDetails.textContent = details;
}

/**
 * Show success state in overlay
 */
function showSuccess(title, status) {
    elements.statusIcon.className = 'fas fa-check-circle status-icon success';
    elements.uploadTitle.textContent = title;
    elements.uploadStatus.textContent = status;
    elements.closeModalBtn.classList.remove('hidden');
}

/**
 * Show error state in overlay
 */
function showError(title, status) {
    elements.statusIcon.className = 'fas fa-exclamation-circle status-icon error';
    elements.uploadTitle.textContent = title;
    elements.uploadStatus.textContent = status;
    elements.closeModalBtn.classList.remove('hidden');
}

/**
 * Close modal and refresh file list
 */
function closeModalAndRefresh() {
    elements.uploadOverlay.classList.add('hidden');
    refreshFileList();
}

/**
 * Fetch files from API and update the page dynamically
 */
async function refreshFileList() {
    try {
        const response = await fetch('/files');
        if (!response.ok) throw new Error('Failed to fetch files');
        
        const { files = [] } = await response.json();
        
        // Clear existing content
        elements.fileView.replaceChildren();
        
        if (files.length === 0) {
            elements.fileView.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-box-open" style="font-size: 64px; margin-bottom: 20px; opacity: 0.5;"></i>
                    <h3>No files yet</h3>
                    <p>Upload a file to get started.</p>
                </div>
            `;
        } else {
            // Use DocumentFragment for batch DOM updates
            const fragment = document.createDocumentFragment();
            
            files.forEach(file => {
                const parts = file.split('/');
                const fileName = parts.at(-1);
                const folder = parts.length > 1 ? parts.slice(0, -1).join('/') : '';
                
                fragment.append(createFileCard(file, fileName, folder));
            });
            
            elements.fileView.append(fragment);
        }
        
        // Rebuild folder view
        buildFolderView();
        
    } catch (error) {
        console.error('Error refreshing file list:', error);
        showToast('Error', 'Failed to refresh file list', 'error');
    }
}

/**
 * Get file extension
 */
function getFileExtension(filename) {
    return filename.split('.').pop()?.toLowerCase() ?? '';
}

/**
 * Create a file card element
 */
function createFileCard(filePath, fileName, folder) {
    const card = document.createElement('div');
    card.className = 'file-card';
    card.dataset.folder = folder;
    card.dataset.path = filePath;
    
    const isImage = IMAGE_EXTENSIONS.test(filePath);
    const ext = getFileExtension(filePath);
    const iconInfo = FILE_ICONS[ext] ?? FILE_ICONS.default;
    
    const thumbContent = isImage
        ? `<img src="/files/${filePath}" class="thumb-img" alt="${fileName}" loading="lazy">`
        : `<i class="fas ${iconInfo.class} file-icon" style="color: ${iconInfo.color};"></i>`;
    
    const folderBadge = folder 
        ? `<div class="file-folder-badge" title="${folder}"><i class="far fa-folder"></i> ${folder}</div>` 
        : '';
    
    card.innerHTML = `
        <div class="card-content">
            <div class="thumb-container">${thumbContent}</div>
            <div class="card-info">
                ${folderBadge}
                <div class="file-name" title="${fileName}">${fileName}</div>
            </div>
        </div>
        <button class="btn-delete" title="Delete File">
            <i class="far fa-trash-alt"></i>
        </button>
    `;
    
    // Attach event listeners
    card.querySelector('.card-content').addEventListener('click', () => downloadFile(filePath));
    card.querySelector('.btn-delete').addEventListener('click', (e) => deleteFile(filePath, e));
    
    return card;
}

/**
 * Upload multiple files
 */
async function uploadFiles(files) {
    const key = elements.apiKey.value;
    const folder = document.getElementById('folderName').value.trim();
    const runStyleSync = elements.styleSyncToggle.checked;
    
    if (!key) {
        alert('Please enter an API Key to upload.');
        return;
    }

    showOverlay('Uploading Files...', `0 of ${files.length} files uploaded`);
    updateProgress(0, '');

    let uploaded = 0;
    let failed = 0;
    const uploadedFiles = [];

    for (const [index, file] of files.entries()) {
        elements.uploadStatus.textContent = `Uploading: ${file.name}`;
        
        const formData = new FormData();
        formData.append('file', file);
        
        const url = folder ? `/files?folder=${encodeURIComponent(folder)}` : '/files';

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'X-API-Key': key },
                body: formData
            });
            
            if (response.ok) {
                uploaded++;
                const result = await response.json();
                uploadedFiles.push(result.filename);
            } else {
                failed++;
            }
        } catch (error) {
            console.error(error);
            failed++;
        }
        
        const progress = Math.round(((index + 1) / files.length) * 100);
        updateProgress(progress, `${uploaded} uploaded, ${failed} failed`);
    }

    // Run StyleSync if enabled and files were uploaded to source folder
    const isSourceFolder = !folder || folder.toLowerCase().startsWith('source');
    
    if (runStyleSync && uploaded > 0 && isSourceFolder) {
        await triggerStyleSync(key, folder, `${uploaded} file(s) uploaded`);
    } else if (uploaded > 0) {
        showSuccess('Upload Complete!', `${uploaded} file(s) uploaded successfully.${failed > 0 ? ` ${failed} failed.` : ''}`);
    } else {
        showError('Upload Failed', 'No files were uploaded successfully.');
    }

    // Reset file input
    elements.fileInput.value = '';
}

/**
 * Trigger StyleSync after upload/delete
 */
async function triggerStyleSync(key, sourcePath = '', successMessage) {
    try {
        const response = await fetch('/stylesync/async', {
            method: 'POST',
            headers: { 'X-API-Key': key, 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_path: sourcePath || '' })
        });

        if (response.ok) {
            const result = await response.json();
            elements.uploadOverlay.classList.add('hidden');
            showToast('Upload Complete', `${successMessage}. StyleSync started.`, 'success');
            refreshFileList();
            pollStyleSyncStatus(result.job_id);
        } else {
            showSuccess('Upload Complete!', `${successMessage}. StyleSync failed to start.`);
        }
    } catch (error) {
        console.error('StyleSync error:', error);
        showSuccess('Upload Complete!', `${successMessage}. StyleSync encountered an error.`);
    }
}

/**
 * Download or view a file
 */
function downloadFile(filename) {
    const url = `/files/${filename}`;
    
    if (IMAGE_EXTENSIONS.test(filename)) {
        window.open(url, '_blank');
        return;
    }
    
    const key = elements.apiKey.value;
    if (!key && !confirm('This file may require an API Key. Continue without one?')) {
        return;
    }
    
    window.location.href = key ? `${url}?api_key=${encodeURIComponent(key)}` : url;
}

/**
 * Delete a file
 */
async function deleteFile(filename, event) {
    event?.stopPropagation();
    
    const key = elements.apiKey.value;
    const runStyleSync = elements.styleSyncToggle.checked;
    
    if (!key) {
        alert('Please enter an API Key to delete.');
        return;
    }
    
    if (!confirm(`Are you sure you want to delete "${filename}"?`)) return;
    
    const isImage = IMAGE_EXTENSIONS.test(filename);
    const isSourceFolder = !filename.includes('/') || filename.toLowerCase().startsWith('source');
    
    try {
        showOverlay('Deleting File...', filename);
        updateProgress(50, 'Removing file...');
        
        const response = await fetch(`/files/${filename}`, {
            method: 'DELETE',
            headers: { 'X-API-Key': key }
        });
        
        if (response.ok) {
            updateProgress(100, 'File deleted');
            
            if (runStyleSync && isImage && isSourceFolder) {
                await runStyleSyncAfterDelete(key, 'File deleted');
            } else {
                showSuccess('Delete Complete!', 'File deleted successfully.');
                elements.uploadDetails.textContent = '';
            }
        } else {
            const err = await response.json();
            showError('Delete Failed', err.detail || response.statusText);
        }
    } catch (error) {
        console.error(error);
        showError('Delete Failed', 'Error deleting file.');
    }
}

/**
 * Delete a folder
 */
async function deleteFolder(folderPath, event) {
    event?.stopPropagation();
    event?.preventDefault();
    
    const key = elements.apiKey.value;
    const runStyleSync = elements.styleSyncToggle.checked;
    const folderDisplay = folderPath || 'Root';
    
    if (!key) {
        alert('Please enter an API Key to delete.');
        return;
    }
    
    if (!confirm(`Are you sure you want to delete ALL files in "${folderDisplay}"? This cannot be undone.`)) return;
    
    const isSourceFolder = !folderPath || folderPath.toLowerCase().startsWith('source');
    
    try {
        showOverlay('Deleting Folder...', `Removing all files in ${folderDisplay}`);
        updateProgress(30, 'Deleting files...');
        
        if (!folderPath) {
            // Delete root files individually
            const cards = elements.fileView.querySelectorAll('.file-card');
            const rootFiles = [...cards].filter(card => !card.dataset.folder);
            let deleted = 0;
            
            for (const card of rootFiles) {
                try {
                    const response = await fetch(`/files/${card.dataset.path}`, {
                        method: 'DELETE',
                        headers: { 'X-API-Key': key }
                    });
                    if (response.ok) deleted++;
                } catch (e) {
                    console.error('Failed to delete:', card.dataset.path);
                }
                updateProgress(30 + (deleted / rootFiles.length * 50), `Deleted ${deleted} of ${rootFiles.length} files`);
            }
            
            updateProgress(100, `Deleted ${deleted} files`);
            
            if (runStyleSync && isSourceFolder) {
                await runStyleSyncAfterDelete(key, folderDisplay);
            } else {
                showSuccess('Folder Deleted!', `${deleted} file(s) deleted from ${folderDisplay}.`);
                elements.uploadDetails.textContent = '';
            }
        } else {
            const response = await fetch(`/folders/${folderPath}`, {
                method: 'DELETE',
                headers: { 'X-API-Key': key }
            });
            
            if (response.ok) {
                const result = await response.json();
                updateProgress(100, `Deleted ${result.deleted_count} files`);
                
                if (runStyleSync && isSourceFolder) {
                    await runStyleSyncAfterDelete(key, folderDisplay);
                } else {
                    showSuccess('Folder Deleted!', `${result.deleted_count} file(s) deleted from ${folderDisplay}.`);
                    elements.uploadDetails.textContent = '';
                }
            } else {
                const err = await response.json();
                showError('Delete Failed', err.detail || response.statusText);
            }
        }
    } catch (error) {
        console.error(error);
        showError('Delete Failed', 'Error deleting folder.');
    }
}

/**
 * Run StyleSync after delete operation
 */
async function runStyleSyncAfterDelete(key, contextMessage) {
    try {
        const response = await fetch('/stylesync/async', {
            method: 'POST',
            headers: { 'X-API-Key': key, 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        if (response.ok) {
            const result = await response.json();
            elements.uploadOverlay.classList.add('hidden');
            showToast('Delete Complete', `${contextMessage}. StyleSync started.`, 'success');
            refreshFileList();
            pollStyleSyncStatus(result.job_id);
        } else {
            showSuccess('Delete Complete!', `${contextMessage}. StyleSync failed to start.`);
        }
    } catch (error) {
        console.error('StyleSync error:', error);
        showSuccess('Delete Complete!', `${contextMessage}. StyleSync encountered an error.`);
    }
}

/**
 * Show toast notification
 */
function showToast(title, message, type = 'info', duration = 10000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    toast.innerHTML = `
        <i class="fas ${TOAST_ICONS[type]} toast-icon"></i>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close">&times;</button>
    `;
    
    // Close button handler
    toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
    
    elements.toastContainer.append(toast);
    
    // Auto remove after duration
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.25s ease-out forwards';
        toast.addEventListener('animationend', () => toast.remove(), { once: true });
    }, duration);
    
    return toast;
}

/**
 * Show StyleSync banner
 */
function showStyleSyncBanner(status = 'Starting...') {
    elements.styleSyncBanner.classList.remove('hidden');
    elements.bannerStatus.textContent = status;
}

/**
 * Update StyleSync banner status
 */
function updateStyleSyncBanner(status) {
    elements.bannerStatus.textContent = status;
}

/**
 * Hide StyleSync banner with animation
 */
function hideStyleSyncBanner() {
    elements.styleSyncBanner.style.animation = 'slideUp 0.25s ease-out forwards';
    elements.styleSyncBanner.addEventListener('animationend', () => {
        elements.styleSyncBanner.classList.add('hidden');
        elements.styleSyncBanner.style.animation = '';
    }, { once: true });
}

/**
 * Poll StyleSync job status
 */
async function pollStyleSyncStatus(jobId, maxAttempts = 60) {
    let attempts = 0;
    showStyleSyncBanner('Initializing...');
    
    const poll = async () => {
        try {
            attempts++;
            updateStyleSyncBanner(`Checking status... (${attempts * 10}s)`);
            
            const response = await fetch(`/stylesync/status/${jobId}`);
            
            if (response.ok) {
                const result = await response.json();
                const processedCount = result.processed?.length ?? 0;
                
                if (result.status === 'running') {
                    updateStyleSyncBanner(`Processing... ${processedCount} images styled`);
                }
                
                if (result.status === 'completed' || result.status === 'failed') {
                    hideStyleSyncBanner();
                    
                    const failedCount = result.failed?.length ?? 0;
                    const skippedCount = result.skipped?.length ?? 0;
                    const deletedCount = result.deleted?.length ?? 0;
                    
                    if (result.status === 'completed') {
                        let message = `✓ ${processedCount} processed, ${skippedCount} skipped`;
                        if (deletedCount > 0) message += `, ${deletedCount} cleaned up`;
                        if (failedCount > 0) message += `, ${failedCount} failed`;
                        
                        showToast('StyleSync Complete', message, 'success');
                        refreshFileList();
                    } else {
                        showToast('StyleSync Failed', result.error || 'An error occurred during processing', 'error');
                    }
                    return;
                }
                
                // Still running, continue polling
                if (attempts < maxAttempts) {
                    setTimeout(poll, 10000);
                } else {
                    hideStyleSyncBanner();
                    showToast('StyleSync Timeout', 'Job is taking longer than expected. Check back later.', 'info');
                }
            } else {
                hideStyleSyncBanner();
                showToast('StyleSync Error', 'Failed to check job status', 'error');
            }
        } catch (error) {
            console.error('Error polling StyleSync status:', error);
            hideStyleSyncBanner();
            showToast('StyleSync Error', 'Connection error while checking status', 'error');
        }
    };
    
    // Start polling after brief delay
    setTimeout(poll, 3000);
}

/**
 * Show styles modal
 */
async function showStylesModal() {
    elements.stylesModal.classList.remove('hidden');
    elements.stylesContent.innerHTML = '<p style="text-align: center; color: var(--text-secondary);"><i class="fas fa-spinner fa-spin"></i> Loading styles...</p>';
    
    try {
        const response = await fetch('/stylesync/styles');
        
        if (response.ok) {
            const { styles = [] } = await response.json();
            
            if (styles.length > 0) {
                elements.stylesContent.innerHTML = styles.map(style => `
                    <div class="style-card">
                        <div class="style-header">
                            <span class="style-name">
                                <i class="fas fa-paint-brush" style="color: var(--primary-color); margin-right: 6px;"></i>
                                ${style.name}
                            </span>
                            <span class="style-strength">Strength: ${(style.strength * 100).toFixed(0)}%</span>
                        </div>
                        <div class="style-prompt">${style.prompt_text}</div>
                    </div>
                `).join('');
            } else {
                elements.stylesContent.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">No styles configured. Add styles to styles.json file.</p>';
            }
        } else {
            elements.stylesContent.innerHTML = '<p style="text-align: center; color: #d13438;">Failed to load styles.</p>';
        }
    } catch (error) {
        console.error('Error loading styles:', error);
        elements.stylesContent.innerHTML = '<p style="text-align: center; color: #d13438;">Error loading styles.</p>';
    }
}

/**
 * Hide styles modal
 */
function hideStylesModal() {
    elements.stylesModal.classList.add('hidden');
}

// ============================================
// Event Listeners & Initialization
// ============================================

// File input change handler
elements.fileInput.addEventListener('change', async (e) => {
    if (e.target.files.length > 0) {
        await uploadFiles([...e.target.files]);
    }
});

// View toggle handler
elements.viewToggle.addEventListener('change', toggleView);

// Styles modal close on outside click
elements.stylesModal.addEventListener('click', (e) => {
    if (e.target === elements.stylesModal) hideStylesModal();
});

// Initialize folder view on load
buildFolderView();

// Expose functions to global scope for inline handlers
Object.assign(window, {
    toggleView,
    downloadFile,
    deleteFile,
    deleteFolder,
    showStylesModal,
    hideStylesModal,
    closeModalAndRefresh,
    toggleAllFolders
});
