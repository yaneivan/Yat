/**
 * Status Widget - reusable component for image status management.
 * Works in all three editors: cropper, editor, text_editor.
 */

class StatusWidget {
    constructor(projectId, filename) {
        this.projectId = projectId;
        this.filename = filename;
        this.currentStatus = null;
        this.currentComment = '';
        this.isOpen = false;
    }

    async init() {
        await this.loadStatus();
        this.render();
        this.attachListeners();
    }

    async loadStatus() {
        try {
            const response = await API.getImageStatus(this.projectId, this.filename);
            if (response.ok) {
                const data = await response.json();
                this.currentStatus = data.status;
                this.currentComment = data.comment || '';
            }
        } catch (error) {
            console.error('Failed to load status:', error);
        }
    }

    async updateStatus(newStatus, newComment) {
        try {
            const response = await API.updateImageStatus(this.projectId, this.filename, newStatus, newComment);
            if (response.ok) {
                const data = await response.json();
                this.currentStatus = data.status;
                this.currentComment = data.comment || '';
                this.render();
                this.showNotification('Статус обновлён', 'success');
                return true;
            } else {
                const data = await response.json();
                this.showNotification('Ошибка: ' + (data.msg || 'Неизвестная ошибка'), 'error');
                return false;
            }
        } catch (error) {
            console.error('Failed to update status:', error);
            this.showNotification('Ошибка при обновлении статуса', 'error');
            return false;
        }
    }

    render() {
        const badge = document.getElementById('status-badge');
        if (!badge || !this.currentStatus) return;

        const statusTexts = {
            'uploaded': 'Загружено',
            'cropped': 'Обрезано',
            'segmented': 'Полигоны готовы',
            'recognized': 'Текст распознан',
            'reviewed': 'Проверено'
        };

        badge.textContent = statusTexts[this.currentStatus] || this.currentStatus;
        badge.className = `status-badge status-${this.currentStatus}`;
        badge.title = this.currentComment || '';
    }

    openPopover() {
        if (this.isOpen) {
            this.closePopover();
            return;
        }

        const popover = document.getElementById('status-popover');
        if (!popover) return;

        // Set current status
        const radio = popover.querySelector(`input[name="status"][value="${this.currentStatus}"]`);
        if (radio) radio.checked = true;

        // Set comment
        const commentField = document.getElementById('status-comment');
        if (commentField) commentField.value = this.currentComment || '';

        // Position popover
        const badge = document.getElementById('status-badge');
        if (badge) {
            const rect = badge.getBoundingClientRect();
            const popoverWidth = 250;
            const popoverHeight = 350;

            // Check space on right/left
            const spaceOnRight = window.innerWidth - rect.right;
            const spaceOnLeft = rect.left;

            if (spaceOnRight >= popoverWidth) {
                popover.style.left = (rect.right) + 'px';
            } else if (spaceOnLeft >= popoverWidth) {
                popover.style.left = (rect.left - popoverWidth) + 'px';
            } else {
                popover.style.left = (rect.left - (popoverWidth - rect.width) / 2) + 'px';
            }

            // Check space below/above
            const spaceBelow = window.innerHeight - rect.bottom;

            if (spaceBelow >= popoverHeight) {
                popover.style.top = (rect.bottom + 5) + 'px';
            } else {
                popover.style.top = (rect.top - popoverHeight - 5) + 'px';
            }
        }

        popover.classList.add('show');
        this.isOpen = true;
    }

    closePopover() {
        const popover = document.getElementById('status-popover');
        if (popover) {
            popover.classList.remove('show');
        }
        this.isOpen = false;
    }

    async saveStatus() {
        const popover = document.getElementById('status-popover');
        const selectedStatus = popover.querySelector('input[name="status"]:checked')?.value;
        const comment = document.getElementById('status-comment')?.value || '';

        if (!selectedStatus) {
            this.showNotification('Выберите статус', 'error');
            return;
        }

        const success = await this.updateStatus(selectedStatus, comment);
        if (success) {
            this.closePopover();
        }
    }

    showNotification(message, type) {
        // Try to use existing showNotification if available
        if (typeof window.showNotification === 'function') {
            window.showNotification(message, type);
        } else {
            // Fallback: create notification
            const notification = document.createElement('div');
            notification.className = `notification ${type}`;
            notification.textContent = message;
            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 12px 20px;
                background: ${type === 'success' ? '#28a745' : '#dc3545'};
                color: white;
                border-radius: 4px;
                z-index: 100000;
                animation: slideIn 0.3s ease;
            `;
            document.body.appendChild(notification);
            setTimeout(() => notification.remove(), 3000);
        }
    }

    attachListeners() {
        // Close popover on click outside
        document.addEventListener('click', (e) => {
            const popover = document.getElementById('status-popover');
            const badge = e.target.closest('#status-badge');

            if (!badge && popover && !popover.contains(e.target) && this.isOpen) {
                this.closePopover();
            }
        });

        // Close popover on scroll
        window.addEventListener('scroll', () => {
            if (this.isOpen) {
                this.closePopover();
            }
        }, { passive: true });

        // Enter to save, Ctrl+Enter for newline
        const commentField = document.getElementById('status-comment');
        if (commentField) {
            commentField.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.shiftKey)) {
                    // Ctrl+Enter or Shift+Enter - insert newline
                    e.preventDefault();
                    const start = commentField.selectionStart;
                    const end = commentField.selectionEnd;
                    commentField.value = commentField.value.substring(0, start) + '\n' + commentField.value.substring(end);
                    commentField.selectionStart = commentField.selectionEnd = start + 1;
                } else if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) {
                    // Pure Enter - save status
                    e.preventDefault();
                    this.saveStatus();
                }
            });
        }

        // Save button
        const saveBtn = document.querySelector('#status-popover button');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveStatus());
        }
    }
}

// Initialize status widget if element exists
function initStatusWidget(projectId, filename) {
    const badge = document.getElementById('status-badge');
    if (badge) {
        window.statusWidget = new StatusWidget(projectId, filename);
        window.statusWidget.init();
    }
}
