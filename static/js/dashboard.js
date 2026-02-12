document.addEventListener('DOMContentLoaded', () => {
    // --- Upload ---
    const dropArea = document.getElementById('drop-area');
    const fileElem = document.getElementById('fileElem');

    if (dropArea) {
        dropArea.addEventListener('click', () => fileElem.click());
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropArea.addEventListener(eventName, e => { e.preventDefault(); e.stopPropagation(); }, false);
        });
        ['dragenter', 'dragover'].forEach(() => dropArea.classList.add('highlight'));
        ['dragleave', 'drop'].forEach(() => dropArea.classList.remove('highlight'));
        dropArea.addEventListener('drop', e => handleFiles(e.dataTransfer.files), false);
        fileElem.addEventListener('change', function() { handleFiles(this.files); });
    }

    async function handleFiles(files) {
        if (!files.length) return;
        const formData = new FormData();
        for (let i = 0; i < files.length; i++) formData.append('files[]', files[i]);
        
        setStatus('Загрузка...');
        const resp = await fetch('/api/upload', { method: 'POST', body: formData });
        if (resp.ok) window.location.reload();
    }

    // --- ZIP Import ---
    window.handleZipImport = async function(input) {
        if (!input.files.length) return;
        const formData = new FormData();
        formData.append('file', input.files[0]);
        setStatus('Импорт...');
        
        try {
            const resp = await fetch('/api/import_zip', { method: 'POST', body: formData });
            const data = await resp.json();
            if (data.status === 'success') {
                alert(`Импортировано: ${data.count}`);
                window.location.reload();
            } else {
                alert('Ошибка: ' + data.msg);
                setStatus('');
            }
        } catch(e) { alert('Ошибка сети'); setStatus(''); }
    };

    // --- Delete ---
    window.toggleDeleteBtn = function() {
        const cnt = document.querySelectorAll('.select-chk:checked').length;
        const btn = document.getElementById('btn-delete');
        if(btn) {
            btn.style.display = cnt > 0 ? 'inline-block' : 'none';
            btn.textContent = `Удалить (${cnt})`;
        }
    };

    window.deleteSelected = async function() {
        const checkboxes = document.querySelectorAll('.select-chk:checked');
        if (!checkboxes.length || !confirm('Удалить?')) return;
        const filenames = Array.from(checkboxes).map(cb => cb.value);
        await API.deleteFiles(filenames);
        window.location.reload();
    };

    function setStatus(msg) {
        const el = document.getElementById('upload-status');
        if(el) { el.style.display = msg ? 'block' : 'none'; el.textContent = msg; }
    }
});