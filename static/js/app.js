// Main application JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Load modals into the container
    fetch('modals.html')
        .then(response => response.text())
        .then(html => {
            document.getElementById('modalsContainer').innerHTML = html;
            initializeModals();
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
});

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

// Error handling
function handleError(error) {
    console.error('Error:', error);
    showToast(error.message || 'An error occurred', 'error');
}

// Initialize event listeners
function initializeEventListeners() {
    // Add form submission handler
    document.getElementById('printerForm')?.addEventListener('submit', handlePrinterFormSubmit);
    
    // Add delete printer handlers
    document.querySelectorAll('.delete-printer-btn').forEach(btn => {
        btn.addEventListener('click', handleDeletePrinter);
    });
}