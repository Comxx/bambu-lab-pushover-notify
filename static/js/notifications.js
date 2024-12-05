// Toast notifications and alerts
class NotificationManager {
    constructor() {
        this.toastContainer = document.getElementById('toastContainer');
        this.toasts = new Map();
        this.toastCounter = 0;
    }

    showToast(message, type = 'info', duration = 5000) {
        const toastId = `toast-${this.toastCounter++}`;
        const toastHtml = this.createToastHtml(toastId, message, type);
        
        this.toastContainer.insertAdjacentHTML('beforeend', toastHtml);
        const toastElement = document.getElementById(toastId);
        
        // Initialize Bootstrap toast
        const toast = new bootstrap.Toast(toastElement, {
            autohide: true,
            delay: duration
        });
        
        // Store toast instance
        this.toasts.set(toastId, toast);
        
        // Show toast
        toast.show();
        
        // Remove toast after it's hidden
        toastElement.addEventListener('hidden.bs.toast', () => {
            this.toasts.delete(toastId);
            toastElement.remove();
        });
    }

    createToastHtml(id, message, type) {
        const icons = {
            success: 'bi-check-circle-fill',
            error: 'bi-exclamation-circle-fill',
            warning: 'bi-exclamation-triangle-fill',
            info: 'bi-info-circle-fill'
        };

        const bgColors = {
            success: 'bg-success',
            error: 'bg-danger',
            warning: 'bg-warning',
            info: 'bg-info'
        };

        return `
            <div class="toast" role="alert" aria-live="assertive" aria-atomic="true" id="${id}">
                <div class="toast-header ${bgColors[type]} text-white">
                    <i class="bi ${icons[type]} me-2"></i>
                    <strong class="me-auto">${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
                <div class="toast-body">
                    ${message}
                </div>
            </div>
        `;
    }

    showAlert(message, type = 'info', containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const alertHtml = this.createAlertHtml(message, type);
        container.insertAdjacentHTML('beforeend', alertHtml);

        // Auto-remove after 5 seconds for non-error alerts
        if (type !== 'error') {
            setTimeout(() => {
                const alerts = container.getElementsByClassName('alert');
                if (alerts.length > 0) {
                    alerts[0].remove();
                }
            }, 5000);
        }
    }

    createAlertHtml(message, type) {
        const alertClass = {
            success: 'alert-success',
            error: 'alert-danger',
            warning: 'alert-warning',
            info: 'alert-info'
        };

        return `
            <div class="alert ${alertClass[type]} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;
    }

    // Handle authentication-related notifications
    showAuthNotification(status, printerId) {
        const messages = {
            'email_verification_required': 'Email verification required. Please check your email.',
            '2fa_required': 'Two-factor authentication required.',
            'cloudflare_blocked': 'Connection blocked by Cloudflare protection.',
            'connected': 'Successfully connected to printer.',
            'error': 'Authentication error occurred.'
        };

        const types = {
            'email_verification_required': 'warning',
            '2fa_required': 'warning',
            'cloudflare_blocked': 'error',
            'connected': 'success',
            'error': 'error'
        };

        this.showToast(messages[status], types[status]);
    }

    // Clear all notifications
    clearAll() {
        this.toasts.forEach(toast => toast.hide());
        this.toasts.clear();
        this.toastContainer.innerHTML = '';
    }
}

// Initialize notification manager
const notificationManager = new NotificationManager();

// Global helper function for showing toasts
function showToast(message, type = 'info', duration = 5000) {
    notificationManager.showToast(message, type, duration);
}

// Export for use in other files
window.notificationManager = notificationManager;
window.showToast = showToast;