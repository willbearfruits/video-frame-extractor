const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const settingsSection = document.getElementById('settings-section');
const startBtn = document.getElementById('start-btn');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');
const statusMsg = document.getElementById('status-msg');
const gallery = document.getElementById('gallery');
const countBadge = document.getElementById('count-badge');
const openFolderBtn = document.getElementById('open-folder-btn');

let currentFilename = null;
let currentOutputFolder = null;
let mode = 'interval';

// --- Drag & Drop ---
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if(e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', (e) => {
    if(e.target.files.length) handleFile(e.target.files[0]);
});

function handleFile(file) {
    // UI Update
    document.getElementById('file-info').classList.remove('hidden');
    document.getElementById('filename-display').textContent = file.name;
    statusMsg.textContent = "Uploading...";
    
    // Upload
    const formData = new FormData();
    formData.append('file', file);
    
    fetch('/upload', {
        method: 'POST',
        body: formData
    })
    .then(r => r.json())
    .then(data => {
        if(data.error) {
            statusMsg.textContent = "Error: " + data.error;
        } else {
            currentFilename = data.filename;
            statusMsg.textContent = "Ready to extract.";
            settingsSection.classList.remove('opacity-50', 'pointer-events-none');
        }
    })
    .catch(e => statusMsg.textContent = "Upload failed.");
}

// --- Mode Selection ---
window.setMode = function(newMode) {
    mode = newMode;
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.remove('bg-blue-600', 'text-white');
        btn.classList.add('bg-gray-700', 'text-gray-300');
    });
    document.getElementById('btn-' + mode).classList.remove('bg-gray-700', 'text-gray-300');
    document.getElementById('btn-' + mode).classList.add('bg-blue-600', 'text-white');

    const label = document.getElementById('mode-label');
    const input = document.getElementById('mode-value');
    
    if(mode === 'interval') {
        label.textContent = "Extract every X seconds";
        input.value = "1.0";
        input.step = "0.1";
    } else if (mode === 'count') {
        label.textContent = "Total frames to extract";
        input.value = "100";
        input.step = "1";
    } else if (mode === 'every_n') {
        label.textContent = "Extract every Nth frame";
        input.value = "10";
        input.step = "1";
    }
};

// --- Execution ---
startBtn.addEventListener('click', () => {
    if(!currentFilename) return;

    // Reset UI
    gallery.innerHTML = '';
    progressBar.style.width = '0%';
    progressText.textContent = '0%';
    countBadge.textContent = '0';
    startBtn.disabled = true;
    startBtn.classList.add('opacity-50');
    openFolderBtn.classList.add('hidden');
    
    // Connect WS
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/process`);
    
    ws.onopen = () => {
        statusMsg.textContent = "Starting extraction...";
        ws.send(JSON.stringify({
            filename: currentFilename,
            mode: mode,
            value: parseFloat(document.getElementById('mode-value').value),
            blur_threshold: parseFloat(document.getElementById('blur-threshold').value)
        }));
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if(data.status === 'progress' || data.status === 'skipped') {
            progressBar.style.width = data.progress + '%';
            progressText.textContent = Math.round(data.progress) + '%';
            
            if(data.status === 'progress') {
                statusMsg.textContent = `Extracted: ${data.extracted}`;
                countBadge.textContent = data.extracted;
                addImageToGallery(data.latest_image, data.score);
            } else {
                statusMsg.textContent = `Skipped (Blurry)`;
            }
        }
        else if (data.status === 'complete') {
            statusMsg.textContent = "Complete!";
            progressBar.style.width = '100%';
            startBtn.disabled = false;
            startBtn.classList.remove('opacity-50');
            currentOutputFolder = data.directory;
            openFolderBtn.classList.remove('hidden');
        }
        else if (data.status === 'error') {
            statusMsg.textContent = "Error: " + data.message;
            startBtn.disabled = false;
            startBtn.classList.remove('opacity-50');
        }
        else if (data.status === 'info') {
            statusMsg.textContent = data.message;
        }
    };
    
    ws.onerror = () => {
        statusMsg.textContent = "Connection error.";
        startBtn.disabled = false;
        startBtn.classList.remove('opacity-50');
    };
});

function addImageToGallery(url, score) {
    const div = document.createElement('div');
    div.className = "relative group aspect-video bg-gray-800 rounded overflow-hidden border border-gray-700";
    div.innerHTML = `
        <img src="${url}" class="w-full h-full object-cover">
        <div class="absolute bottom-0 left-0 right-0 bg-black/70 text-[10px] text-gray-300 p-1 opacity-0 group-hover:opacity-100 transition-opacity">
            Score: ${score.toFixed(0)}
        </div>
    `;
    gallery.insertBefore(div, gallery.firstChild);
}

openFolderBtn.addEventListener('click', () => {
    if(currentOutputFolder) {
        fetch(`/open-folder?path=${encodeURIComponent(currentOutputFolder)}`);
    }
});
