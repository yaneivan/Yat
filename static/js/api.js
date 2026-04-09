// Get CSRF token from meta tag
function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

// Headers with CSRF token for POST/PUT/DELETE requests
// contentType: 'application/json' для JSON, null для FormData (браузер сам поставит multipart/form-data)
function getCsrfHeaders(contentType = 'application/json') {
    const headers = {
        'X-CSRFToken': getCsrfToken()
    };
    if (contentType) {
        headers['Content-Type'] = contentType;
    }
    return headers;
}

const API = {
    // CSRF helper functions (exported for use in other scripts)
    getCsrfToken,
    getCsrfHeaders,

    async listImages(project = null) {
        const url = project
            ? `/api/images_list?project=${encodeURIComponent(project)}`
            : '/api/images_list';
        const res = await fetch(url);
        return res.json();
    },
    async loadAnnotation(filename, projectName = null) {
        const url = projectName 
            ? `/api/load/${filename}?project=${encodeURIComponent(projectName)}`
            : `/api/load/${filename}`;
        const res = await fetch(url);
        return res.json();
    },
    async saveAnnotation(filename, regions, projectName = null) {
        const url = projectName 
            ? `/api/save?project=${encodeURIComponent(projectName)}`
            : '/api/save';
        return fetch(url, {
            method: 'POST',
            headers: getCsrfHeaders(),
            body: JSON.stringify({
                image_name: filename,
                regions
            })
        });
    },
    async saveAnnotationWithTexts(filename, regions, texts = {}, projectName = null) {
        const data = {
            image_name: filename,
            regions: regions || [],
            texts: texts
        };

        const url = projectName 
            ? `/api/save?project=${encodeURIComponent(projectName)}`
            : '/api/save';

        const response = await fetch(url, {
            method: 'POST',
            headers: getCsrfHeaders(),
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    },
    async getUserRole() {
        const res = await fetch('/api/auth/me');
        if (!res.ok) return null;
        const data = await res.json();
        return data.role;
    },
    async deleteProject(name) {
        return fetch(`/api/projects/${name}`, {
            method: 'DELETE',
            headers: getCsrfHeaders()
        });
    },
    async createProject(data) {
        return fetch('/api/projects', {
            method: 'POST',
            headers: getCsrfHeaders(),
            body: JSON.stringify(data)
        });
    },
    async updateProject(name, data) {
        return fetch(`/api/projects/${name}`, {
            method: 'PUT',
            headers: getCsrfHeaders(),
            body: JSON.stringify(data)
        });
    },
    async uploadImages(projectName, formData) {
        return fetch(`/api/projects/${projectName}/upload_images`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
                // Content-Type не указываем — браузер сам поставит multipart/form-data с boundary
            },
            body: formData
        });
    },
    async deleteImage(projectName, filename) {
        return fetch(`/api/projects/${projectName}/images?filename=${encodeURIComponent(filename)}`, {
            method: 'DELETE',
            headers: getCsrfHeaders()
        });
    },
    async getImageStatus(projectName, filename) {
        return fetch(`/api/projects/${projectName}/images/${encodeURIComponent(filename)}/status`);
    },
    async updateImageStatus(projectName, filename, status, comment) {
        return fetch(`/api/projects/${projectName}/images/${encodeURIComponent(filename)}/status`, {
            method: 'PUT',
            headers: getCsrfHeaders(),
            body: JSON.stringify({ status, comment })
        });
    },
    async importZip(formData) {
        return fetch('/api/import_zip', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            body: formData
        });
    },
    async batchDetect(projectName) {
        return fetch(`/api/projects/${projectName}/batch_detect`, {
            method: 'POST',
            headers: getCsrfHeaders()
        });
    },
    async batchRecognize(projectName) {
        return fetch(`/api/projects/${projectName}/batch_recognize`, {
            method: 'POST',
            headers: getCsrfHeaders()
        });
    }
};

const AuthAPI = {
    async getUserRole() {
        try {
            const res = await fetch('/api/auth/me');
            if (!res.ok) return 'admin'; // Open access mode
            const data = await res.json();
            // If role is 'none' (not logged in), redirect to login
            if (data.role === 'none') {
                window.location.href = '/login';
                return 'admin'; // Default while redirecting
            }
            return data.role || 'admin';
        } catch (e) {
            return 'admin';
        }
    }
};