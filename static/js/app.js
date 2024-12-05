// Main application JavaScript
document.addEventListener('DOMContentLoaded', function() {
    loadRequiredScripts().then(() => {
        initializeApp();
    }).catch(error => {
        console.error('Error loading scripts:', error);
    });
});

function loadRequiredScripts() {
    return new Promise((resolve, reject) => {
        const scripts = [
            'https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/js/bootstrap.bundle.min.js',
            'https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.min.js'
        ];

        let loaded = 0;
        scripts.forEach(src => {
            const script = document.createElement('script');
            script.src = src;
            script.onload = () => {
                loaded++;
                if (loaded === scripts.length) {
                    resolve();
                }
            };
            script.onerror = reject;
            document.head.appendChild(script);
        });
    });
}

function initializeApp() {
    // Load modals into the container
    fetch('/modals.html')
        .then(response => response.text())
        .then(html => {
            document.getElementById('modalsContainer').innerHTML = html;
            initializeModals();
        })
        .catch(error => {
            console.error('Error loading modals:', error);
            showToast('Error loading printer interface', 'error');
        });

    // Initialize Socket.IO connection
    const socket = io();
    
    // Connection status handling
    socket.on('connect', () => {
        updateConnectionStatus(true);
    });
    
    socket.on('disconnect', () => {
        updateConnectionStatus(false);
    });
    
    // Printer updates handling
    socket.on('printer_update', (data) => {
        updatePrinterCard(data);
    });
    
    // Initialize printer data
    fetchPrinters();
}

// Connection status update
function updateConnectionStatus(connected) {
    const statusBadge = document.getElementById('globalConnectionStatus');
    const connectionBanner = document.getElementById('connectionBanner');
    const connectionMessage = document.getElementById('connectionMessage');
    
    if (connected) {
        statusBadge.classList.add('d-none');
        connectionBanner.classList.add('d-none');
    } else {
        statusBadge.classList.remove('d-none');
        connectionBanner.classList.remove('d-none');
        connectionMessage.textContent = 'Connection lost. Reconnecting...';
    }
}

// Create printer card HTML
function createPrinterCard(printer) {
    const statusClass = getStatusClass(printer.status.gcode_state);
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
}

// Update existing printer card
function updatePrinterCard(data) {
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
}

// Helper functions
function getStatusClass(state) {
    const statusClasses = {
        'PRINTING': 'bg-primary',
        'FINISH': 'bg-success',
        'FAILED': 'bg-danger',
        'IDLE': 'bg-secondary',
        'PAUSE': 'bg-warning'
    };
    return statusClasses[state] || 'bg-secondary';
}

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

// Fetch printers from the server
async function fetchPrinters() {
    try {
        const response = await fetch('/api/printers');
        const data = await response.json();
        
        if (data.printers) {
            renderPrinterGrid(data.printers);
        }
    } catch (error) {
        showToast('Error fetching printers', 'error');
        console.error('Error:', error);
    }
}

// Render the printer grid
function renderPrinterGrid(printers) {
    const grid = document.getElementById('printerGrid');
    const loadingPlaceholder = document.getElementById('loadingPlaceholder');
    
    loadingPlaceholder.classList.add('d-none');
    grid.innerHTML = printers.map(printer => createPrinterCard(printer)).join('');
}

// Initialize Bootstrap tooltips and popovers
function initializeModals() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
}