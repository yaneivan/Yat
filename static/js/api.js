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
    async saveAnnotationWithTexts(filename, regions, texts = {}) {
        const data = {
            image_name: filename,
            regions: regions || [],
            texts: texts
        };

        const response = await fetch('/api/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    },
    async deleteFiles(filenames) {
        return fetch('/api/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ filenames })
        });
    }
};