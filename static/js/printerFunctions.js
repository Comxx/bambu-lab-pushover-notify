// Status class mapping
const STATUS_CLASSES = {
    'PRINTING': 'bg-primary',
    'FINISH': 'bg-success',
    'FAILED': 'bg-danger',
    'IDLE': 'bg-secondary',
    'PAUSE': 'bg-warning'
};

// Global functions for printer card management
window.createPrinterCard = function(printer) {
    const statusClass = STATUS_CLASSES[printer.status.gcode_state] || 'bg-secondary';
    const progressPercentage = printer.status.percent_done || 0;
    
    return `
        <div class="col-12 col-md-6 col-lg-4" id="printer-${printer.printer_id}">
            <div class="card printer-card" style="border-left: 4px solid ${printer.printer_color}">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="printer-title mb-0">${printer.printer_title}</h5>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-outline-secondary" onclick="reconnectPrinter('${printer.printer_id}')">
                            <i class="bi bi-arrow-clockwise"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deletePrinter('${printer.printer_id}')">
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
                        <div class="progress-bar" role="progressbar" style="width: ${progressPercentage}%" 
                            aria-valuenow="${progressPercentage}" aria-valuemin="0" aria-valuemax="100">
                            ${progressPercentage}%
                        </div>
                    </div>
                    <div class="printer-details">
                        ${createPrinterDetails(printer)}
                    </div>
                </div>
            </div>
        </div>
    `;
};

window.updatePrinterCard = function(data) {
    const cardElement = document.getElementById(`printer-${data.printer_id}`);
    if (cardElement) {
        const printer = {
            printer_id: data.printer_id,
            printer_title: data.printer,
            status: {
                gcode_state: data.state,
                percent_done: data.percent,
                layer_num: data.lines,
                total_layer_num: data.lines_total,
                subtask_name: data.project_name
            },
            current_stage: data.current_stage,
            error_messages: data.error_messages
        };
        cardElement.outerHTML = createPrinterCard(printer);
    }
};

window.reconnectPrinter = async function(printerId) {
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
};

window.deletePrinter = async function(printerId) {
    if (confirm('Are you sure you want to delete this printer?')) {
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
};

function createPrinterDetails(printer) {
    let details = `
        <p class="mb-1"><strong>Project:</strong> ${printer.status.subtask_name || 'None'}</p>
        <p class="mb-1"><strong>Layer:</strong> ${printer.status.layer_num || 0}/${printer.status.total_layer_num || 0}</p>
        <p class="mb-1"><strong>Stage:</strong> ${printer.current_stage || 'Unknown'}</p>
    `;
    
    if (printer.error_messages && printer.error_messages.length > 0) {
        details += `
            <div class="alert alert-danger mt-2 mb-0">
                ${printer.error_messages.map(msg => `<p class="mb-1">${msg}</p>`).join('')}
            </div>
        `;
    }
    
    return details;
}

// Toast notification function
window.showToast = function(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    const toastHtml = `
        <div class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header bg-${type} text-white">
                <strong class="me-auto">${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">${message}</div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = toastContainer.lastElementChild;
    const toast = new bootstrap.Toast(toastElement);
    toast.show();
    
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
};