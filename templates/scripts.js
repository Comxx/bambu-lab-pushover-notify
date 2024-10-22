// scripts.js

// WebSocket connection
let ws;
function connectWebSocket() {
    ws = new WebSocket(`ws://${window.location.host}/ws`);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
        // Reconnect all active printers after connection established
        document.querySelectorAll('[id$="_card"]').forEach(card => {
            const printerId = card.id.replace('_card', '');
            reconnectPrinter(printerId);
        });
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected. Attempting to reconnect...');
        setTimeout(connectWebSocket, 5000); // Retry connection after 5 seconds
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updatePrinterStatus(data);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

// Update printer status with live data
function updatePrinterStatus(data) {
    const { printer_id, status, progress, remaining_time, temperature } = data;
    
    // Update progress bar
    const progressBar = document.getElementById(`${printer_id}_percent`);
    if (progressBar) {
        progressBar.style.width = `${progress}%`;
        progressBar.textContent = `${progress}%`;
        progressBar.setAttribute('aria-valuenow', progress);
    }

    // Update remaining time
    if (remaining_time) {
        const days = Math.floor(remaining_time / (24 * 60));
        const hours = Math.floor((remaining_time % (24 * 60)) / 60);
        const minutes = remaining_time % 60;

        document.getElementById(`${printer_id}_remaining_days`).textContent = days;
        document.getElementById(`${printer_id}_remaining_hours`).textContent = hours;
        document.getElementById(`${printer_id}_remaining_minutes`).textContent = minutes;
    }

    // Update status information
    const statusDiv = document.querySelector(`#${printer_id}_card .status-info`);
    if (statusDiv) {
        let statusHTML = `<strong>Status:</strong> ${status}<br>`;
        if (temperature) {
            statusHTML += `<strong>Nozzle:</strong> ${temperature.nozzle}°C<br>`;
            statusHTML += `<strong>Bed:</strong> ${temperature.bed}°C<br>`;
            statusHTML += `<strong>Chamber:</strong> ${temperature.chamber}°C`;
        }
        statusDiv.innerHTML = statusHTML;
    }

    // Update card appearance based on status
    const card = document.getElementById(`${printer_id}_card`);
    if (card) {
        // Remove all status classes
        card.classList.remove('printer-idle', 'printer-printing', 'printer-error', 'printer-offline');
        
        // Add appropriate status class
        switch (status.toLowerCase()) {
            case 'printing':
                card.classList.add('printer-printing');
                break;
            case 'idle':
                card.classList.add('printer-idle');
                break;
            case 'error':
                card.classList.add('printer-error');
                break;
            case 'offline':
                card.classList.add('printer-offline');
                break;
        }
    }
}

// Existing printer management functions
function addNewPrinter() {
    // Clear form fields
    document.getElementById('printerHost').value = '';
    document.getElementById('printerPort').value = '';
    document.getElementById('printerUser').value = '';
    document.getElementById('printerPassword').value = '';
    document.getElementById('deviceId').value = '';
    document.getElementById('printerTitle').value = '';
    document.getElementById('pushoverSound').value = '';
    document.getElementById('userKey').value = '';
    document.getElementById('appKey').value = '';
    document.getElementById('ledControl').checked = false;
    document.getElementById('wledIp').value = '';
    document.getElementById('printerColor').value = '#000000';
}

function editPrinter(printerId) {
    // Fetch printer data
    fetch(`/api/printers/${printerId}`)
        .then(response => response.json())
        .then(data => {
            document.getElementById('printerHost').value = data.host;
            document.getElementById('printerPort').value = data.port;
            document.getElementById('printerUser').value = data.user;
            document.getElementById('deviceId').value = data.device_id;
            document.getElementById('printerTitle').value = data.title;
            document.getElementById('pushoverSound').value = data.pushover_sound;
            document.getElementById('userKey').value = data.user_key;
            document.getElementById('appKey').value = data.app_key;
            document.getElementById('ledControl').checked = data.led_control;
            document.getElementById('wledIp').value = data.wled_ip;
            document.getElementById('printerColor').value = data.color;
            
            // Show modal
            const modal = new bootstrap.Modal(document.getElementById('configModal'));
            modal.show();
        })
        .catch(error => console.error('Error fetching printer data:', error));
}

function deletePrinter(printerId) {
    if (confirm('Are you sure you want to delete this printer?')) {
        fetch(`/api/printers/${printerId}`, {
            method: 'DELETE',
        })
        .then(response => {
            if (response.ok) {
                // Remove printer card from DOM
                const card = document.querySelector(`#${printerId}_card`).closest('.col-12');
                card.remove();
            } else {
                throw new Error('Failed to delete printer');
            }
        })
        .catch(error => console.error('Error deleting printer:', error));
    }
}

function reconnectPrinter(printerId) {
    fetch(`/api/printers/${printerId}/reconnect`, {
        method: 'POST',
    })
    .then(response => {
        if (!response.ok) throw new Error('Failed to reconnect printer');
    })
    .catch(error => console.error('Error reconnecting printer:', error));
}

function savePrinter() {
    const printerData = {
        host: document.getElementById('printerHost').value,
        port: document.getElementById('printerPort').value,
        user: document.getElementById('printerUser').value,
        password: document.getElementById('printerPassword').value,
        device_id: document.getElementById('deviceId').value,
        title: document.getElementById('printerTitle').value,
        pushover_sound: document.getElementById('pushoverSound').value,
        user_key: document.getElementById('userKey').value,
        app_key: document.getElementById('appKey').value,
        led_control: document.getElementById('ledControl').checked,
        wled_ip: document.getElementById('wledIp').value,
        color: document.getElementById('printerColor').value
    };

    // Determine if this is a new printer or edit
    const editId = document.getElementById('configModal').getAttribute('data-printer-id');
    const url = editId ? `/api/printers/${editId}` : '/api/printers';
    const method = editId ? 'PUT' : 'POST';

    fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(printerData),
    })
    .then(response => response.json())
    .then(data => {
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('configModal'));
        modal.hide();
        
        // Refresh page to show new/updated printer
        window.location.reload();
    })
    .catch(error => console.error('Error saving printer:', error));
}

// Initialize WebSocket connection when page loads
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
});