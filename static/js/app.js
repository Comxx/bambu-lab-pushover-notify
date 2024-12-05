// Wait for all required scripts to load
// Wait for all required scripts to load
async function loadDependencies() {
    const scripts = [
        'https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/js/bootstrap.bundle.min.js',
        'https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.min.js'
        // Remove the printerFunctions.js from here as it's now loaded in the HTML
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

// Initialize application
async function initializeApp() {
    try {
        // First load all dependencies
        await loadDependencies();
        
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