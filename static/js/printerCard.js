// Printer card creation and updates
class PrinterCardManager {
    constructor() {
        this.printerCards = new Map();
    }

    createPrinterCard(printer) {
        const statusClass = this.getStatusClass(printer.status.gcode_state);
        const progressPercentage = printer.status.percent_done || 0;
        
        return `
            <div class="col-12 col-md-6 col-lg-4" id="printer-${printer.printer_id}">
                <div class="card printer-card" style="border-left: 4px solid ${printer.printer_color}">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="printer-title mb-0">${printer.printer_title}</h5>
                        <div class="btn-group">
                            <button class="btn btn-sm btn-outline-secondary" 
                                onclick="printerCardManager.reconnectPrinter('${printer.printer_id}')">
                                <i class="bi bi-arrow-clockwise"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" 
                                onclick="printerCardManager.deletePrinter('${printer.printer_id}')">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="d-flex justify-content-between mb-2">
                            <span class="status-badge badge ${statusClass}">
                                ${printer.status.gcode_state || 'Unknown'}
                            </span>
                            <span class="text-muted">${printer.printer_type}</span>
                        </div>
                        
                        <div class="progress mb-3">
                            <div class="progress-bar" role="progressbar" 
                                style="width: ${progressPercentage}%" 
                                aria-valuenow="${progressPercentage}" 
                                aria-valuemin="0" 
                                aria-valuemax="100">
                                ${progressPercentage}%
                            </div>
                        </div>
                        
                        <div class="printer-details">
                            <p class="mb-1">
                                <strong>Project:</strong> 
                                <span class="project-name">${printer.status.subtask_name || 'None'}</span>
                            </p>
                            <p class="mb-1">
                                <strong>Layer:</strong> 
                                ${printer.status.layer_num || 0}/${printer.status.total_layer_num || 0}
                            </p>
                            <p class="mb-1">
                                <strong>Stage:</strong> 
                                <span class="current-stage">${printer.current_stage || 'Unknown'}</span>
                            </p>
                            ${this.createErrorSection(printer.error_messages)}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    getStatusClass(state) {
        const statusClasses = {
            'PRINTING': 'bg-primary',
            'FINISH': 'bg-success',
            'FAILED': 'bg-danger',
            'IDLE': 'bg-secondary',
            'PAUSE': 'bg-warning'
        };
        return statusClasses[state] || 'bg-secondary';
    }

    createErrorSection(errorMessages) {
        if (!errorMessages || errorMessages.length === 0) return '';
        
        return `
            <div class="alert alert-danger mt-2 mb-0">
                ${errorMessages.map(msg => `<p class="mb-1">${msg}</p>`).join('')}
            </div>
        `;
    }

    updatePrinterCard(printer) {
        const cardElement = document.getElementById(`printer-${printer.printer_id}`);
        if (cardElement) {
            cardElement.innerHTML = this.createPrinterCard(printer).trim();
        }
    }

    async reconnectPrinter(printerId) {
        try {
            const response = await fetch('/reconnect_printer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ printer_id: printerId })
            });

            if (!response.ok) {
                throw new Error('Failed to reconnect printer');
            }

            showToast('Reconnecting printer...', 'info');
        } catch (error) {
            showToast('Error reconnecting printer', 'error');
            console.error('Error:', error);
        }
    }

    async deletePrinter(printerId) {
        modalHandler.showConfirmDialog(
            'Are you sure you want to delete this printer?',
            async () => {
                try {
                    const response = await fetch('/delete_printer', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ printer_id: printerId })
                    });

                    if (!response.ok) {
                        throw new Error('Failed to delete printer');
                    }

                    document.getElementById(`printer-${printerId}`)?.remove();
                    showToast('Printer deleted successfully', 'success');
                } catch (error) {
                    showToast('Error deleting printer', 'error');
                    console.error('Error:', error);
                }
            }
        );
    }
}

// Initialize printer card manager
const printerCardManager = new PrinterCardManager();

// Export for use in other files
window.printerCardManager = printerCardManager;