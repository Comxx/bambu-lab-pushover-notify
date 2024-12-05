class ModalHandler {
    constructor() {
        this.configModal = null;
        this.confirmDialog = null;
        this.printerForm = null;
        this.init();
    }

    init() {
        // Initialize modal instances
        this.configModal = new bootstrap.Modal(document.getElementById('configModal'));
        this.confirmDialog = new bootstrap.Modal(document.getElementById('confirmDialog'));
        this.printerForm = document.getElementById('printerForm');
        
        this.setupEventListeners();
        this.setupFormValidation();
    }

    setupEventListeners() {
        // Save printer button handler
        document.getElementById('savePrinter')?.addEventListener('click', () => this.handleSavePrinter());
        
        // Reset form when modal is hidden
        document.getElementById('configModal')?.addEventListener('hidden.bs.modal', () => {
            this.resetForm();
        });

        // Confirm action button handler
        document.getElementById('confirmAction')?.addEventListener('click', () => {
            if (this.currentConfirmCallback) {
                this.currentConfirmCallback();
                this.confirmDialog.hide();
            }
        });
    }

    setupFormValidation() {
        // Add form validation
        this.printerForm?.addEventListener('submit', (event) => {
            event.preventDefault();
            event.stopPropagation();
            
            if (this.printerForm.checkValidity()) {
                this.handleSavePrinter();
            }
            
            this.printerForm.classList.add('was-validated');
        });
    }

    async handleSavePrinter() {
        if (!this.printerForm.checkValidity()) {
            this.printerForm.classList.add('was-validated');
            return;
        }

        const formData = {
            host: document.getElementById('host').value,
            port: parseInt(document.getElementById('port').value),
            user: document.getElementById('user').value,
            password: document.getElementById('password').value,
            device_id: document.getElementById('deviceId').value,
            Printer_Title: document.getElementById('printerTitle').value,
            printer_type: document.getElementById('printerType').value,
            PO_SOUND: document.getElementById('pushoverSound').value,
            my_pushover_user: document.getElementById('pushoverUserKey').value,
            my_pushover_app: document.getElementById('pushoverAppKey').value,
            ledlight: document.getElementById('ledControl').checked,
            wled_ip: document.getElementById('wledIp').value,
            color: document.getElementById('printerColor').value
        };

        try {
            const response = await fetch('/save_printer_settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

            if (!response.ok) {
                throw new Error('Failed to save printer settings');
            }

            showToast('Printer settings saved successfully', 'success');
            this.configModal.hide();
            fetchPrinters(); // Refresh printer list
        } catch (error) {
            showToast('Error saving printer settings', 'error');
            console.error('Error:', error);
        }
    }

    showConfirmDialog(message, callback) {
        document.getElementById('confirmMessage').textContent = message;
        this.currentConfirmCallback = callback;
        this.confirmDialog.show();
    }

    loadPrinterData(printerData) {
        Object.entries(printerData).forEach(([key, value]) => {
            const element = document.getElementById(key);
            if (element) {
                if (element.type === 'checkbox') {
                    element.checked = value;
                } else {
                    element.value = value;
                }
            }
        });
    }

    resetForm() {
        this.printerForm.reset();
        this.printerForm.classList.remove('was-validated');
    }
}

// Initialize modal handler
let modalHandler;
document.addEventListener('DOMContentLoaded', () => {
    modalHandler = new ModalHandler();
});

// Export for use in other files
window.modalHandler = modalHandler;