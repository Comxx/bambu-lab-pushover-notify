// Wait for all required scripts to load
async function loadDependencies() {
    const scripts = [
        'https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/js/bootstrap.bundle.min.js',
        'https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.min.js',
        '/printerFunctions.js'
    ];

    for (const src of scripts) {
        await new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
}

// Initialize modals and Bootstrap components
window.initializeModals = function() {
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
};

// Update connection status UI
window.updateConnectionStatus = function(connected) {
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
};

// Fetch and render printers
window.fetchPrinters = async function() {
    try {
        const response = await fetch('/api/printers');
        const data = await response.json();
        
        if (data.printers) {
            const grid = document.getElementById('printerGrid');
            const loadingPlaceholder = document.getElementById('loadingPlaceholder');
            
            loadingPlaceholder.classList.add('d-none');
            grid.innerHTML = data.printers.map(printer => window.createPrinterCard(printer)).join('');
        }
    } catch (error) {
        window.showToast('Error fetching printers', 'error');
        console.error('Error:', error);
    }
};

// Initialize application
async function initializeApp() {
    try {
        // First load all dependencies
        await loadDependencies();
        
        // Then load modals
        const modalResponse = await fetch('/modals.html');
        const modalHtml = await modalResponse.text();
        document.getElementById('modalsContainer').innerHTML = modalHtml;
        
        // Initialize modals after HTML is loaded
        window.initializeModals();
        
        // Setup Socket.IO
        const socket = io();
        
        socket.on('connect', () => {
            window.updateConnectionStatus(true);
        });
        
        socket.on('disconnect', () => {
            window.updateConnectionStatus(false);
        });
        
        socket.on('printer_update', (data) => {
            if (window.updatePrinterCard) {
                window.updatePrinterCard(data);
            } else {
                console.error('updatePrinterCard function not found');
            }
        });
        // Fetch initial printer data
        await window.fetchPrinters();
        
    } catch (error) {
        console.error('Error initializing app:', error);
        window.showToast('Error initializing application', 'error');
    }
}

// Start initialization when DOM is ready
document.addEventListener('DOMContentLoaded', initializeApp);