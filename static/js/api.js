const API = {
    async listImages() {
        const res = await fetch('/api/images_list');
        return res.json();
    },
    async loadAnnotation(filename) {
        const res = await fetch(`/api/load/${filename}`);
        return res.json();
    },
    async saveAnnotation(filename, regions) {
        return fetch('/api/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ image_name: filename, regions })
        });
    },
    async deleteFiles(filenames) {
        return fetch('/api/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ filenames })
        });
    }
};