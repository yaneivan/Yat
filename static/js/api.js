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

    async listImages(projectId = null) {
        const url = projectId
            ? `/api/images_list?project_id=${projectId}`
            : '/api/images_list';
        const res = await fetch(url);
        const data = await res.json();
        return data.map(img => typeof img === 'object' ? img.name : img);
    },
    async loadAnnotation(filename, projectId = null) {
        const url = projectId 
            ? `/api/load/${filename}?project_id=${projectId}`
            : `/api/load/${filename}`;
        const res = await fetch(url);
        return res.json();
    },
    async saveAnnotation(filename, regions, projectId = null) {
        const url = projectId 
            ? `/api/save?project_id=${projectId}`
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
    async saveAnnotationWithTexts(filename, regions, texts = {}, projectId = null) {
        const data = {
            image_name: filename,
            regions: regions || [],
            texts: texts
        };

        const url = projectId 
            ? `/api/save?project_id=${projectId}`
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
    async deleteProject(projectId) {
        return fetch(`/api/projects/${projectId}`, {
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
    async updateProject(projectId, data) {
        return fetch(`/api/projects/${projectId}`, {
            method: 'PUT',
            headers: getCsrfHeaders(),
            body: JSON.stringify(data)
        });
    },
    async uploadImages(projectId, formData) {
        return fetch(`/api/projects/${projectId}/upload_images`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            body: formData
        });
    },
    async deleteImage(projectId, filename) {
        return fetch(`/api/projects/${projectId}/images?filename=${encodeURIComponent(filename)}`, {
            method: 'DELETE',
            headers: getCsrfHeaders()
        });
    },
    async getImageStatus(projectId, filename) {
        return fetch(`/api/projects/${projectId}/images/${encodeURIComponent(filename)}/status`);
    },
    async updateImageStatus(projectId, filename, status, comment) {
        return fetch(`/api/projects/${projectId}/images/${encodeURIComponent(filename)}/status`, {
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
    async batchDetect(projectId) {
        return fetch(`/api/projects/${projectId}/batch_detect`, {
            method: 'POST',
            headers: getCsrfHeaders()
        });
    },
    async batchRecognize(projectId) {
        return fetch(`/api/projects/${projectId}/batch_recognize`, {
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