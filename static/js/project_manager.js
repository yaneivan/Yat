/**
 * Project Manager API Functions
 */

// Use centralized CSRF functions from api.js
// Import is handled by script tag order in HTML

const ProjectAPI = {
    // Projects
    async getProjects() {
        const response = await fetch('/api/projects');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        return data.projects;
    },

    async createProject(name, description = "") {
        const response = await fetch('/api/projects', {
            method: 'POST',
            headers: API.getCsrfHeaders(),
            body: JSON.stringify({name, description})
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    },

    async getProject(projectId) {
        const response = await fetch(`/api/projects/${projectId}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        return data.project;
    },

    async updateProject(projectId, name, description = "") {
        const response = await fetch(`/api/projects/${projectId}`, {
            method: 'PUT',
            headers: API.getCsrfHeaders(),
            body: JSON.stringify({name, description})
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    },

    async deleteProject(projectId) {
        const response = await fetch(`/api/projects/${projectId}`, {
            method: 'DELETE',
            headers: API.getCsrfHeaders()
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    },

    // Project Images
    async getProjectImages(projectId) {
        const response = await fetch(`/api/projects/${projectId}/images`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        return data.images;
    },

    async addImageToProject(projectId, imageName) {
        const response = await fetch(`/api/projects/${projectId}/images`, {
            method: 'POST',
            headers: API.getCsrfHeaders(),
            body: JSON.stringify({image_name: imageName})
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    },

    async removeImageFromProject(projectId, imageName) {
        const response = await fetch(`/api/projects/${projectId}/images`, {
            method: 'DELETE',
            headers: API.getCsrfHeaders(),
            body: JSON.stringify({image_name: imageName})
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    },

    // Batch Processing
    async startBatchDetection(projectId, settings = {}) {
        const response = await fetch(`/api/projects/${projectId}/batch_detect`, {
            method: 'POST',
            headers: API.getCsrfHeaders(),
            body: JSON.stringify({settings})
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    },

    async startBatchRecognition(projectId) {
        const response = await fetch(`/api/projects/${projectId}/batch_recognize`, {
            method: 'POST',
            headers: API.getCsrfHeaders()
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        return await response.json();
    }
};

/**
 * Task Manager API Functions
 */
const TaskAPI = {
    async getTasks() {
        const response = await fetch('/api/tasks');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        return data.tasks;
    },

    async getTask(taskId) {
        const response = await fetch(`/api/tasks/${taskId}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        return data.task;
    }
};

/**
 * Project Manager Class
 */
class ProjectManager {
    constructor() {
        this.projects = [];
        this.tasks = [];
        this.images = [];
        this.currentSection = 'projects';
        this.userRole = 'admin'; // Default to admin
    }

    async init() {
        // Get user role first
        this.userRole = await AuthAPI.getUserRole();
        console.log('User role:', this.userRole);

        await this.loadProjects();
        await this.loadTasks();
        await this.loadImages();
        this.updateStats();
        this.setupEventListeners();

        // Render projects in the preferred view
        this.restoreViewPreference();
    }

    restoreViewPreference() {
        const container = document.getElementById('projects-container');
        if (!container) return;

        // Always use list view
        container.classList.remove('projects-grid');
        container.classList.add('projects-container-list');

        // Render projects in list view
        this.renderProjectsAsList();
    }

    async loadProjects() {
        try {
            const basicProjects = await ProjectAPI.getProjects();

            // Fetch detailed information for each project to get image statuses
            // Use Promise.all to make API calls in parallel for better performance
            const projectPromises = basicProjects.map(async (basicProject) => {
                try {
                    const [detailedProject, imagesResponse] = await Promise.all([
                        ProjectAPI.getProject(basicProject.id),
                        ProjectAPI.getProjectImages(basicProject.id)
                    ]);
                    detailedProject.images = imagesResponse; // imagesResponse is already an array of image objects
                    return detailedProject;
                } catch (error) {
                    console.error(`Error loading details for project ${basicProject.id}:`, error);
                    // Add the basic project info if detailed load fails
                    return basicProject;
                }
            });

            this.projects = await Promise.all(projectPromises);
            // Don't render here - restoreViewPreference() will render after checking view preference
        } catch (error) {
            console.error('Error loading projects:', error);
            this.showError('Ошибка при загрузке проектов');
        }
    }

    async loadTasks() {
        try {
            this.tasks = await TaskAPI.getTasks();
            this.renderTasks();
        } catch (error) {
            console.error('Error loading tasks:', error);
            // Don't show error for tasks as they might not be implemented yet
        }
    }

    async loadImages() {
        try {
            const response = await fetch('/api/images_list');
            this.images = await response.json();
            // Don't render images here, they're rendered in the images section
        } catch (error) {
            console.error('Error loading images:', error);
            this.showError('Ошибка при загрузке изображений');
        }
    }

    renderProjects() {
        const container = document.getElementById('projects-container');
        if (!container) return;

        container.innerHTML = '';

        this.projects.forEach(project => {
            const projectCard = this.createProjectCard(project);
            container.appendChild(projectCard);
        });
    }

    createProjectCard(project) {
        const projectCard = document.createElement('div');
        projectCard.className = 'project-card';

        // Calculate stats for the project
        const totalImages = project.images ? project.images.length : 0;

        // Count annotated images by checking their status ('segmented', 'cropped', or 'recognized')
        let annotatedImages = 0;
        if (project.images && Array.isArray(project.images)) {
            annotatedImages = project.images.filter(img => ['segmented', 'cropped', 'recognized'].includes(img.status)).length;
        }

        // Create elements safely to prevent XSS
        const projectHeader = document.createElement('div');
        projectHeader.className = 'project-header';

        const projectTitle = document.createElement('h3');
        projectTitle.className = 'project-title';
        projectTitle.textContent = project.name;  // Safe: textContent escapes HTML

        projectHeader.appendChild(projectTitle);

        const projectDescription = document.createElement('div');
        projectDescription.className = 'project-description';
        projectDescription.textContent = project.description || 'Без описания';  // Safe

        const projectStats = document.createElement('div');
        projectStats.className = 'project-stats';

        const statsSpan = document.createElement('span');
        statsSpan.textContent = `${totalImages} изображений`;

        projectStats.appendChild(statsSpan);

        const projectActions = document.createElement('div');
        projectActions.className = 'project-actions';

        const openLink = document.createElement('a');
        openLink.href = `/project/${project.id}`;
        openLink.className = 'action-btn';
        openLink.textContent = 'Открыть';

        projectActions.appendChild(openLink);

        // Only show delete button for admin
        if (this.userRole === 'admin') {
            const deleteButton = document.createElement('button');
            deleteButton.className = 'action-btn';
            deleteButton.textContent = 'Удалить';
            deleteButton.onclick = () => projectManager.deleteProject(project.id);
            projectActions.appendChild(deleteButton);
        }

        projectCard.appendChild(projectHeader);
        projectCard.appendChild(projectDescription);
        projectCard.appendChild(projectStats);
        projectCard.appendChild(projectActions);

        return projectCard;
    }

    renderTasks() {
        const container = document.getElementById('task-list');
        if (!container) return;

        container.innerHTML = '';

        if (this.tasks.length === 0) {
            container.innerHTML = '<p>Нет активных заданий</p>';
            return;
        }

        this.tasks.forEach(task => {
            const taskItem = this.createTaskItem(task);
            container.appendChild(taskItem);
        });
    }

    createTaskItem(task) {
        const taskItem = document.createElement('div');
        taskItem.className = 'task-item';

        // Create elements safely to prevent XSS
        const taskHeader = document.createElement('div');
        taskHeader.className = 'task-header';

        const typeSpan = document.createElement('span');
        typeSpan.textContent = `${task.type} - ${task.project_name}`;  // Safe

        const statusSpan = document.createElement('span');
        statusSpan.textContent = task.status;  // Safe

        taskHeader.appendChild(typeSpan);
        taskHeader.appendChild(statusSpan);

        const progressDiv = document.createElement('div');
        progressDiv.textContent = `Прогресс: ${task.completed}/${task.total}`;  // Safe

        const progressBar = document.createElement('div');
        progressBar.className = 'task-progress-bar';

        const progressInner = document.createElement('div');
        progressInner.className = 'task-progress';
        progressInner.style.width = `${task.progress}%`;  // Safe: number value

        progressBar.appendChild(progressInner);

        taskItem.appendChild(taskHeader);
        taskItem.appendChild(progressDiv);
        taskItem.appendChild(progressBar);

        return taskItem;
    }

    renderImages() {
        const container = document.getElementById('images-container');
        if (!container) return;

        container.innerHTML = '';

        this.images.forEach(image => {
            const imageCard = this.createImageCard(image);
            container.appendChild(imageCard);
        });
    }

    createImageCard(image) {
        const imageCard = document.createElement('div');
        imageCard.className = 'file-card';

        // Support both string (filename) and object (from updated API)
        const filename = typeof image === 'string' ? image : image.name;
        const projectName = typeof image === 'object' ? image.project_name : null;

        // Create elements safely to prevent XSS
        const imageContainer = document.createElement('div');
        imageContainer.style.position = 'relative';

        const img = document.createElement('img');
        const projectParam = projectName ? `?project=${encodeURIComponent(projectName)}` : '';
        img.src = `/data/images/${encodeURIComponent(filename)}${projectParam}`;
        img.className = 'thumb';
        img.loading = 'lazy';
        img.style.cursor = 'pointer';

        imageContainer.appendChild(img);

        const metaDiv = document.createElement('div');
        metaDiv.className = 'meta';

        const nameSpan = document.createElement('span');
        nameSpan.title = filename;  // Safe: attribute
        nameSpan.style.whiteSpace = 'nowrap';
        nameSpan.style.overflow = 'hidden';
        nameSpan.style.textOverflow = 'ellipsis';
        nameSpan.style.maxWidth = '80px';
        nameSpan.textContent = filename;  // Safe: textContent

        metaDiv.appendChild(nameSpan);

        const cardActions = document.createElement('div');
        cardActions.className = 'card-actions';

        const cropLink = document.createElement('a');
        cropLink.href = `/cropper?image=${encodeURIComponent(image)}`;
        cropLink.className = 'action-btn action-crop';
        cropLink.title = 'Кадрировать';
        cropLink.textContent = '✂️ Crop';

        const segmentLink = document.createElement('a');
        segmentLink.href = `/editor?image=${encodeURIComponent(image)}`;
        segmentLink.className = 'action-btn action-segment';
        segmentLink.title = 'Размечать';
        segmentLink.textContent = '✏️ Seg';

        const textLink = document.createElement('a');
        textLink.href = `/text_editor?image=${encodeURIComponent(image)}`;
        textLink.className = 'action-btn';
        textLink.title = 'Распознавание текста';
        textLink.textContent = '📝 Расп';

        cardActions.appendChild(cropLink);
        cardActions.appendChild(segmentLink);
        cardActions.appendChild(textLink);

        imageCard.appendChild(imageContainer);
        imageCard.appendChild(metaDiv);
        imageCard.appendChild(cardActions);

        return imageCard;
    }

    updateStats() {
        const projectsCount = document.getElementById('projects-count');
        const imagesCount = document.getElementById('images-count');
        const tasksCount = document.getElementById('tasks-count');

        if (projectsCount) projectsCount.textContent = this.projects.length;
        if (imagesCount) imagesCount.textContent = this.images.length;
        if (tasksCount) tasksCount.textContent = this.tasks.length;
    }

    async createProject(name, description = "") {
        if (!name || name.trim() === '') {
            this.showError('Введите название проекта');
            return false;
        }

        try {
            console.log('Creating project:', name, description); // Debug log
            const result = await ProjectAPI.createProject(name, description);
            console.log('Project creation result:', result); // Debug log

            if (result.status === 'success') {
                this.showSuccess('Проект создан успешно');
                // Reload the page to maintain view state
                location.reload();
                return true;
            } else {
                this.showError('Ошибка: ' + result.msg);
                return false;
            }
        } catch (error) {
            console.error('Error creating project:', error);
            this.showError('Ошибка при создании проекта: ' + error.message);
            return false;
        }
    }

    async deleteProject(projectId) {
        const project = this.projects.find(p => p.id === projectId);
        const projectName = project ? project.name : projectId;
        if (!confirm(`Удалить проект "${projectName}"?`)) {
            return false;
        }

        try {
            const result = await ProjectAPI.deleteProject(projectId);
            if (result.status === 'success') {
                this.showSuccess('Проект удален успешно');
                // Reload the page to maintain view state
                location.reload();
                return true;
            } else {
                this.showError('Ошибка: ' + result.msg);
                return false;
            }
        } catch (error) {
            console.error('Error deleting project:', error);
            this.showError('Ошибка при удалении проекта');
            return false;
        }
    }

    async startBatchDetection() {
        if (!confirm('Запустить детекцию полигонов для всех проектов? Это может занять некоторое время.')) {
            return false;
        }

        // For now, we'll just show a message - in a real implementation, we'd call an API
        // that processes all projects
        this.showSuccess('Пакетная детекция запущена. Следите за прогрессом в разделе "Задания".');
        // In a real implementation, we would call an API endpoint to start batch processing
        // for all projects
    }

    async startBatchRecognition() {
        if (!confirm('Запустить распознавание текста для всех проектов? Это может занять некоторое время.')) {
            return false;
        }

        // For now, we'll just show a message - in a real implementation, we'd call an API
        // that processes all projects
        this.showSuccess('Пакетное распознавание запущено. Следите за прогрессом в разделе "Задания".');
        // In a real implementation, we would call an API endpoint to start batch processing
        // for all projects
    }

    showSection(sectionName) {
        // Hide all sections
        document.querySelectorAll('.section').forEach(el => {
            el.classList.remove('active');
        });

        // Show selected section
        const sectionElement = document.getElementById(`${sectionName}-section`);
        if (sectionElement) {
            sectionElement.classList.add('active');
        }

        // Update active nav item
        document.querySelectorAll('.sidebar-nav a').forEach(el => {
            el.classList.remove('active');
        });

        // Find the link that corresponds to the section and mark it as active
        // We need to find the link that has the onclick with showSection
        const links = document.querySelectorAll('.sidebar-nav a');
        for (let link of links) {
            if (link.getAttribute('onclick') && link.getAttribute('onclick').includes(`showSection('${sectionName}')`)) {
                link.classList.add('active');
                break;
            }
        }

        // Special handling for images section
        if (sectionName === 'images') {
            this.renderImages();
        }

        this.currentSection = sectionName;
    }

    setupEventListeners() {
        // Handle Enter key in project creation modal
        const projectNameInput = document.getElementById('project-name');
        const projectDescriptionInput = document.getElementById('project-description');
        
        if (projectNameInput) {
            projectNameInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.createProjectFromModal();
                }
            });
        }
        
        if (projectDescriptionInput) {
            projectDescriptionInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && e.ctrlKey) {
                    this.createProjectFromModal();
                }
            });
        }
    }

    async createProjectFromModal() {
        const nameInput = document.getElementById('project-name');
        const descriptionInput = document.getElementById('project-description');

        if (!nameInput || !descriptionInput) {
            this.showError('Не найдены элементы формы');
            return;
        }

        const name = nameInput.value.trim();
        const description = descriptionInput.value.trim();

        console.log('Input values:', {name, description}); // Debug log

        if (await this.createProject(name, description)) {
            this.closeCreateProjectModal();
        }
    }

    openAddImagesModal(projectId) {
        this.currentProjectId = projectId;
        const modal = document.getElementById('addImagesModal');
        if (modal) {
            modal.style.display = 'block';
            // Load available images to add to the project
            this.loadAvailableImagesForProject(projectId);
        }
    }

    closeAddImagesModal() {
        const modal = document.getElementById('addImagesModal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    async loadAvailableImagesForProject(projectId) {
        try {
            // Get all images
            const allImagesResponse = await fetch('/api/images_list');
            const allImages = await allImagesResponse.json();

            // Get project images
            const projectImagesResponse = await fetch(`/api/projects/${projectId}/images`);
            const projectImagesData = await projectImagesResponse.json();
            const projectImages = projectImagesData.images.map(img => img.name);

            // Find images not in the project
            const availableImages = allImages.filter(img => !projectImages.includes(img));

            // Render available images
            this.renderAvailableImages(availableImages, projectId);
        } catch (error) {
            console.error('Error loading available images:', error);
            this.showError('Ошибка при загрузке изображений');
        }
    }

    renderAvailableImages(images, projectId) {
        const container = document.getElementById('available-images-container');
        if (!container) return;

        container.innerHTML = '';

        if (images.length === 0) {
            container.innerHTML = '<p>Нет доступных изображений для добавления</p>';
            return;
        }

        images.forEach(image => {
            const imageCard = document.createElement('div');
            imageCard.className = 'file-card';

            // Create elements safely to prevent XSS
            const imageContainer = document.createElement('div');
            imageContainer.style.position = 'relative';

            const img = document.createElement('img');
            img.src = `/data/images/${encodeURIComponent(image)}`;
            img.className = 'thumb';
            img.loading = 'lazy';
            img.style.cursor = 'pointer';

            imageContainer.appendChild(img);

            const metaDiv = document.createElement('div');
            metaDiv.className = 'meta';

            const nameSpan = document.createElement('span');
            nameSpan.title = image;
            nameSpan.style.whiteSpace = 'nowrap';
            nameSpan.style.overflow = 'hidden';
            nameSpan.style.textOverflow = 'ellipsis';
            nameSpan.style.maxWidth = '80px';
            nameSpan.textContent = image;  // Safe: textContent

            metaDiv.appendChild(nameSpan);

            const cardActions = document.createElement('div');
            cardActions.className = 'card-actions';

            const addButton = document.createElement('button');
            addButton.className = 'action-btn';
            addButton.textContent = 'Добавить';
            addButton.onclick = () => this.addImageToProject(projectId, image);  // Safe: closure

            cardActions.appendChild(addButton);

            imageCard.appendChild(imageContainer);
            imageCard.appendChild(metaDiv);
            imageCard.appendChild(cardActions);

            container.appendChild(imageCard);
        });
    }

    async addImageToProject(projectId, image) {
        try {
            const response = await fetch(`/api/projects/${projectId}/images`, {
                method: 'POST',
                headers: API.getCsrfHeaders(),
                body: JSON.stringify({image_name: image})
            });

            const result = await response.json();

            if (result.status === 'success') {
                this.showSuccess(`Изображение ${image} добавлено в проект`);
                // Reload the available images to update the list
                this.loadAvailableImagesForProject(projectId);
                // Also reload projects to update stats
                await this.loadProjects();
                this.updateStats();
            } else {
                this.showError('Ошибка: ' + result.msg);
            }
        } catch (error) {
            console.error('Error adding image to project:', error);
            this.showError('Ошибка при добавлении изображения в проект');
        }
    }


    renderProjectsAsList() {
        const container = document.getElementById('projects-container');
        if (!container) return;

        container.innerHTML = '';

        this.projects.forEach(project => {
            const projectItem = this.createProjectListItem(project);
            container.appendChild(projectItem);
        });
    }

    createProjectListItem(project) {
        const projectItem = document.createElement('div');
        projectItem.className = 'project-item';

        // Calculate stats for the project
        const totalImages = project.images ? project.images.length : 0;

        // Count annotated images by checking their status ('segmented', 'cropped', or 'recognized')
        let annotatedImages = 0;
        if (project.images && Array.isArray(project.images)) {
            annotatedImages = project.images.filter(img => ['segmented', 'cropped', 'recognized'].includes(img.status)).length;
        }

        // Create elements safely to prevent XSS
        const projectInfo = document.createElement('div');
        projectInfo.className = 'project-info';

        const title = document.createElement('h3');
        title.className = 'project-title';
        title.textContent = project.name;  // Safe: textContent

        const description = document.createElement('p');
        description.className = 'project-description';
        description.textContent = project.description || 'Без описания';  // Safe

        const stats = document.createElement('div');
        stats.className = 'project-stats';

        const statsSpan = document.createElement('span');
        statsSpan.textContent = `${totalImages} изображений`;  // Safe

        stats.appendChild(statsSpan);

        projectInfo.appendChild(title);
        projectInfo.appendChild(description);
        projectInfo.appendChild(stats);

        const projectActions = document.createElement('div');
        projectActions.className = 'project-actions';

        const openLink = document.createElement('a');
        openLink.href = `/project/${project.id}`;
        openLink.className = 'btn';
        openLink.textContent = 'Открыть';

        projectActions.appendChild(openLink);

        // Only show delete button for admin
        if (this.userRole === 'admin') {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'btn danger delete-project-btn';
            deleteBtn.textContent = 'Удалить';
            deleteBtn.onclick = (event) => {
                event.stopPropagation();
                this.deleteProject(project.id);
            };
            projectActions.appendChild(deleteBtn);
        }

        projectItem.appendChild(projectInfo);
        projectItem.appendChild(projectActions);

        // Make the entire card clickable
        projectItem.addEventListener('click', function() {
            window.location.href = `/project/${project.id}`;
        });

        return projectItem;
    }

    openCreateProjectModal() {
        document.getElementById('createProjectModal').classList.add('active');
        document.getElementById('project-name').focus();
    }

    closeCreateProjectModal() {
        document.getElementById('createProjectModal').classList.remove('active');
        document.getElementById('project-name').value = '';
        document.getElementById('project-description').value = '';
    }

    openImportModal() {
        document.getElementById('importModal').classList.add('active');
    }

    closeImportModal() {
        document.getElementById('importModal').classList.remove('active');
    }

    async submitZipImport() {
        console.log('[ZIP Import] Starting import from project_manager.js...');
        
        // Попробуем найти элементы с разными возможными ID
        let fileInput = document.getElementById('zipInput');
        if (!fileInput) {
            fileInput = document.getElementById('zipFile');
        }

        let simplifyInput = document.getElementById('simplifyInput');
        if (!simplifyInput) {
            // Если не найден, пробуем другой возможный ID
            simplifyInput = document.getElementById('simplify');
        }

        const submitButton = document.querySelector('#importModal .btn-primary');

        console.log('[ZIP Import] fileInput:', fileInput);
        console.log('[ZIP Import] fileInput.id:', fileInput?.id);
        console.log('[ZIP Import] fileInput.files:', fileInput?.files);
        console.log('[ZIP Import] fileInput.files[0]:', fileInput?.files?.[0]);

        if (!fileInput || !fileInput.files[0]) {
            console.error('[ZIP Import] No file selected');
            this.showError('Пожалуйста, выберите ZIP файл');
            return;
        }

        // Сделать кнопку неактивной и изменить текст для индикации загрузки
        submitButton.disabled = true;
        const originalButtonText = submitButton.textContent;
        submitButton.textContent = 'Импортируется...';

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('simplify', simplifyInput ? simplifyInput.value : 5);

        console.log('[ZIP Import] FormData entries:');
        for (let [key, value] of formData.entries()) {
            console.log('  ', key, ':', value);
        }

        // Проверяем, находимся ли мы на странице проекта
        const pathParts = window.location.pathname.split('/');
        const isProjectPage = pathParts.length >= 3 && pathParts[1] === 'project';
        if (isProjectPage) {
            const projectId = parseInt(pathParts[2], 10);
            formData.append('project_id', projectId);
            console.log('[ZIP Import] Project page, project_id:', projectId);
        } else {
            console.log('[ZIP Import] Main page, no project_id');
        }

        try {
            console.log('[ZIP Import] Sending request...');
            const response = await fetch('/api/import_zip', {
                method: 'POST',
                headers: API.getCsrfHeaders(null),  // null = браузер сам поставит multipart/form-data
                body: formData
            });

            console.log('[ZIP Import] Response status:', response.status);
            const result = await response.json();
            console.log('[ZIP Import] Response data:', result);

            if (result.status === 'success') {
                if (isProjectPage) {
                    this.showSuccess(`Изображения успешно добавлены в проект (${result.count} файлов)`);
                } else {
                    this.showSuccess(`Проект успешно импортирован (${result.count} файлов)`);
                }
                this.closeImportModal();
                location.reload();
            } else {
                this.showError('Ошибка: ' + result.msg);
            }
        } catch (error) {
            console.error('[ZIP Import] Error:', error);
            this.showError('Ошибка при импорте проекта');
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = originalButtonText;
        }
    }

    showError(message) {
        // Create a simple error notification
        this.createNotification(message, 'error');
    }

    showSuccess(message) {
        // Create a simple success notification
        this.createNotification(message, 'success');
    }

    createNotification(message, type) {
        // Remove any existing notifications
        const existingNotifications = document.querySelectorAll('.notification');
        existingNotifications.forEach(note => note.remove());

        // Create new notification
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 20px;
            border-radius: 4px;
            color: white;
            z-index: 10000;
            ${type === 'error' ? 'background: #dc3545;' : 'background: #28a745;'}
        `;

        document.body.appendChild(notification);

        // Remove notification after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    async editProjectInfo() {
        const projectNameElement = document.getElementById('project-title');
        const projectDescriptionElement = document.getElementById('project-description');

        if (!projectNameElement || !projectDescriptionElement) {
            this.showError('Элементы проекта не найдены');
            return;
        }

        // Находим кнопку редактирования (теперь она вне элемента названия)
        const projectTitleContainer = projectNameElement.parentElement;
        const editButton = projectTitleContainer.querySelector('button[onclick*="editProjectInfo"]');
        if (editButton) {
            editButton.style.display = 'none';
        }

        // Получаем текущие значения
        // Теперь название проекта хранится в атрибуте data-original-name
        const currentName = projectNameElement.getAttribute('data-original-name') || projectNameElement.textContent.trim();
        const currentDescription = projectDescriptionElement.dataset.originalDescription || projectDescriptionElement.textContent;

        // Сохраняем оригинальные значения как атрибуты данных
        projectNameElement.dataset.originalName = currentName;
        projectDescriptionElement.dataset.originalDescription = currentDescription;

        // Создаём поля ввода для редактирования
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.value = currentName;
        nameInput.className = 'form-control';
        nameInput.style.marginRight = '10px';
        nameInput.style.verticalAlign = 'middle';

        const descriptionInput = document.createElement('textarea');
        descriptionInput.value = currentDescription;
        descriptionInput.className = 'form-control';

        // Заменяем текст названия на поле ввода
        projectNameElement.innerHTML = '';
        projectNameElement.appendChild(nameInput);

        // Заменяем текст описания на поле ввода
        projectDescriptionElement.innerHTML = '';
        projectDescriptionElement.appendChild(descriptionInput);

        // Создаём кнопку "Сохранить"
        const saveButton = document.createElement('button');
        saveButton.className = 'btn btn-primary';
        saveButton.textContent = 'Сохранить';
        saveButton.style.marginRight = '10px';
        saveButton.onclick = async () => {
            await this.saveProjectInfo(nameInput.value, descriptionInput.value);
        };

        // Создаём кнопку "Отмена"
        const cancelButton = document.createElement('button');
        cancelButton.className = 'btn btn-secondary';
        cancelButton.textContent = 'Отмена';
        cancelButton.onclick = () => {
            this.cancelEdit();
        };

        // Добавляем кнопки под заголовком проекта
        const projectInfoDiv = projectNameElement.parentElement;
        const buttonContainer = document.createElement('div');
        buttonContainer.id = 'edit-buttons-container';
        buttonContainer.style.marginTop = '10px';
        buttonContainer.appendChild(saveButton);
        buttonContainer.appendChild(cancelButton);
        projectInfoDiv.appendChild(buttonContainer);
    }

    cancelEdit() {
        const projectNameElement = document.getElementById('project-title');
        const projectDescriptionElement = document.getElementById('project-description');

        if (!projectNameElement || !projectDescriptionElement) {
            this.showError('Элементы проекта не найдены');
            return;
        }

        // Восстанавливаем оригинальные значения
        const originalName = projectNameElement.dataset.originalName || '';
        const originalDescription = projectDescriptionElement.dataset.originalDescription || '';

        projectNameElement.textContent = originalName;

        // Восстанавливаем кнопку редактирования
        const projectTitleContainer = projectNameElement.parentElement;
        const editButton = projectTitleContainer.querySelector('button[onclick*="editProjectInfo"]');
        if (editButton) {
            editButton.style.display = 'inline-block'; // Показываем кнопку редактирования
        }

        projectDescriptionElement.textContent = originalDescription;

        // Удаляем контейнер с кнопками "Сохранить" и "Отмена"
        const buttonContainer = document.getElementById('edit-buttons-container');
        if (buttonContainer && buttonContainer.parentNode) {
            buttonContainer.parentNode.removeChild(buttonContainer);
        }
    }

    async saveProjectInfo(newName, newDescription) {
        // Get the current project id from the URL
        const pathParts = window.location.pathname.split('/');
        const currentProjectId = parseInt(pathParts[2], 10);

        try {
            const result = await ProjectAPI.updateProject(currentProjectId, newName, newDescription);
            if (result.status === 'success') {
                // Reload the page to reflect changes
                location.reload();
            } else {
                // В случае ошибки восстанавливаем исходное состояние
                this.cancelEdit();
                this.showError('Ошибка при сохранении: ' + result.msg);
            }
        } catch (error) {
            // В случае ошибки восстанавливаем исходное состояние
            this.cancelEdit();
            console.error('Error saving project info:', error);
            this.showError('Ошибка при сохранении изменений');
        }
    }
}

// Initialize the project manager when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.projectManager = new ProjectManager();
    window.projectManager.init();
});

// Global function for view toggle

// Global function for editing project info (for use in HTML onclick)
function editProjectInfo() {
    if (window.projectManager) {
        window.projectManager.editProjectInfo();
    }
}

// Global function for creating project (for use in HTML onclick)
function openCreateProjectModal() {
    if (window.projectManager) {
        window.projectManager.openCreateProjectModal();
    }
}

// Global function for closing create project modal (for use in HTML onclick)
function closeCreateProjectModal() {
    if (window.projectManager) {
        window.projectManager.closeCreateProjectModal();
    }
}

// Global function for opening import modal (for use in HTML onclick)
function openImportModal() {
    if (window.projectManager) {
        window.projectManager.openImportModal();
    }
}

// Global function for closing import modal (for use in HTML onclick)
function closeImportModal() {
    if (window.projectManager) {
        window.projectManager.closeImportModal();
    }
}

// Global function for submitting ZIP import (for use in HTML onclick)
async function submitZipImport() {
    if (window.projectManager) {
        await window.projectManager.submitZipImport();
    }
}

/* ═══════════════════════════════════════════════
   User Management (Admin)
   ═══════════════════════════════════════════════ */

let _currentPermUserId = null;

async function openUserManagement() {
    document.getElementById('userManagementModal').classList.add('active');
    await loadUsersList();
}

function closeUserManagement() {
    document.getElementById('userManagementModal').classList.remove('active');
}

async function loadUsersList() {
    try {
        const resp = await fetch('/api/users');
        const data = await resp.json();
        const tbody = document.getElementById('users-tbody');
        tbody.innerHTML = '';

        for (const user of (data.users || [])) {
            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid #ddd';
            tr.innerHTML = `
                <td style="padding:8px;">${user.id}</td>
                <td style="padding:8px;">${user.username}</td>
                <td style="padding:8px;">${user.is_admin ? 'Админ' : 'Пользователь'}</td>
                <td style="padding:8px;"><button class="btn" style="padding:2px 8px;" onclick="openUserPermissions(${user.id}, '${user.username}')">Настроить</button></td>
                <td style="padding:8px; text-align:center;">
                    <button class="btn" style="padding:2px 8px; color:#ffc107;" onclick="openAdminResetPassword(${user.id}, '${user.username}')">🔑</button>
                    <button class="btn" style="padding:2px 8px; color:#dc3545;" onclick="deleteUser(${user.id}, '${user.username}')">Удалить</button>
                </td>
            `;
            tbody.appendChild(tr);
        }
    } catch (e) {
        console.error('Load users error:', e);
    }
}

async function createUser() {
    const username = document.getElementById('new-username').value.trim();
    const password = document.getElementById('new-password').value;
    const isAdmin = document.getElementById('new-is-admin').checked;

    if (!username || !password) {
        alert('Заполни имя и пароль');
        return;
    }

    try {
        const resp = await fetch('/api/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, is_admin: isAdmin })
        });
        const data = await resp.json();

        if (resp.ok) {
            document.getElementById('new-username').value = '';
            document.getElementById('new-password').value = '';
            document.getElementById('new-is-admin').checked = false;
            await loadUsersList();
        } else {
            alert(data.error || 'Ошибка создания пользователя');
        }
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function deleteUser(userId, username) {
    if (!confirm(`Удалить пользователя ${username}?`)) return;

    try {
        const resp = await fetch(`/api/users/${userId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (resp.ok) {
            await loadUsersList();
        } else {
            alert(data.error || 'Ошибка удаления');
        }
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

/* ── User Permissions ── */

async function openUserPermissions(userId, username) {
    _currentPermUserId = userId;
    document.getElementById('userPermissionsModal').classList.add('active');
    document.getElementById('perms-title').textContent = `Права: ${username}`;

    // Load projects dropdown
    try {
        const projectsResp = await fetch('/api/projects');
        const projectsData = await projectsResp.json();
        const select = document.getElementById('perm-project');
        select.innerHTML = '';
        for (const proj of (projectsData.projects || [])) {
            const opt = document.createElement('option');
            opt.value = proj.id;
            opt.textContent = proj.name;
            select.appendChild(opt);
        }
    } catch (e) {
        console.error('Load projects:', e);
    }

    await loadUserPermissions();
}

function closeUserPermissions() {
    document.getElementById('userPermissionsModal').classList.remove('active');
}

async function loadUserPermissions() {
    try {
        const resp = await fetch(`/api/users/${_currentPermUserId}/permissions`);
        const data = await resp.json();
        const list = document.getElementById('perms-list');
        list.innerHTML = '';

        for (const perm of (data.permissions || [])) {
            const li = document.createElement('li');
            li.style.cssText = 'display:flex; justify-content:space-between; padding:8px; border-bottom:1px solid #eee;';
            li.innerHTML = `
                <span><b>${perm.project_name}</b> — ${perm.role}</span>
                <button class="btn" style="padding:2px 8px; color:#dc3545;" onclick="revokePermission(${perm.project_id})">Отозвать</button>
            `;
            list.appendChild(li);
        }

        if (data.permissions.length === 0) {
            list.innerHTML = '<li style="padding:10px; color:#666;">Нет назначенных проектов</li>';
        }
    } catch (e) {
        console.error('Load perms:', e);
    }
}

async function grantPermission() {
    const projectId = parseInt(document.getElementById('perm-project').value, 10);
    const role = document.getElementById('perm-role').value;

    if (!projectId) { alert('Выбери проект'); return; }

    try {
        const resp = await fetch(`/api/projects/${projectId}/permissions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: _currentPermUserId, role })
        });
        if (resp.ok) {
            await loadUserPermissions();
        } else {
            const data = await resp.json();
            alert(data.error || 'Ошибка');
        }
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

async function revokePermission(projectId) {
    if (!confirm(`Отозвать доступ к проекту?`)) return;

    try {
        const resp = await fetch(`/api/projects/${projectId}/permissions/${_currentPermUserId}`, {
            method: 'DELETE'
        });
        if (resp.ok) {
            await loadUserPermissions();
        } else {
            const data = await resp.json();
            alert(data.error || 'Ошибка');
        }
    } catch (e) {
        alert('Ошибка: ' + e.message);
    }
}

/* ═══════════════════════════════════════════════
   Statistics Dashboard
   ═══════════════════════════════════════════════ */



/* ═══════════════════════════════════════════════
   Password Change (Self)
   ═══════════════════════════════════════════════ */

function openChangePasswordModal() {
    document.getElementById('changePasswordModal').classList.add('active');
    document.getElementById('cp-current').value = '';
    document.getElementById('cp-new').value = '';
    document.getElementById('cp-confirm').value = '';
    document.getElementById('cp-error').style.display = 'none';
}

function closeChangePassword() {
    document.getElementById('changePasswordModal').classList.remove('active');
}

async function changePassword() {
    const current = document.getElementById('cp-current').value;
    const newPass = document.getElementById('cp-new').value;
    const confirm = document.getElementById('cp-confirm').value;
    const errorEl = document.getElementById('cp-error');
    errorEl.style.display = 'none';

    if (!current || !newPass) {
        errorEl.textContent = 'Заполни все поля';
        errorEl.style.display = 'block';
        return;
    }
    if (newPass !== confirm) {
        errorEl.textContent = 'Пароли не совпадают';
        errorEl.style.display = 'block';
        return;
    }

    try {
        const resp = await fetch('/api/users/me/password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: current, new_password: newPass })
        });
        const data = await resp.json();
        if (resp.ok) {
            closeChangePassword();
            alert('Пароль изменён!');
        } else {
            errorEl.textContent = data.error || 'Ошибка';
            errorEl.style.display = 'block';
        }
    } catch (e) {
        errorEl.textContent = 'Ошибка: ' + e.message;
        errorEl.style.display = 'block';
    }
}

/* ═══════════════════════════════════════════════
   Admin Reset Password
   ═══════════════════════════════════════════════ */

let _resetUserId = null;
let _resetUsername = null;

function openAdminResetPassword(userId, username) {
    _resetUserId = userId;
    _resetUsername = username;
    document.getElementById('adminResetPasswordModal').classList.add('active');
    document.getElementById('rp-title').textContent = `Сбросить пароль: ${username}`;
    document.getElementById('rp-new').value = '';
    document.getElementById('rp-error').style.display = 'none';
}

function closeAdminResetPassword() {
    document.getElementById('adminResetPasswordModal').classList.remove('active');
}

async function adminResetPassword() {
    const newPass = document.getElementById('rp-new').value;
    const errorEl = document.getElementById('rp-error');
    errorEl.style.display = 'none';

    if (!newPass) {
        errorEl.textContent = 'Введи пароль';
        errorEl.style.display = 'block';
        return;
    }

    try {
        const resp = await fetch(`/api/users/${_resetUserId}/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: newPass })
        });
        const data = await resp.json();
        if (resp.ok) {
            closeAdminResetPassword();
            alert(`Пароль для ${_resetUsername} сброшен`);
        } else {
            errorEl.textContent = data.error || 'Ошибка';
            errorEl.style.display = 'block';
        }
    } catch (e) {
        errorEl.textContent = 'Ошибка: ' + e.message;
        errorEl.style.display = 'block';
    }
}

/* ═══════════════════════════════════════════════
   Global: Close modals on Escape
   ═══════════════════════════════════════════════ */
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;

    const modals = [
        'createProjectModal',
        'importModal',
        'userManagementModal',
        'userPermissionsModal',
        'changePasswordModal',
        'adminResetPasswordModal',
        'addImagesModal'
    ];

    for (const id of modals) {
        const el = document.getElementById(id);
        if (el && el.classList.contains('active')) {
            el.classList.remove('active');
            break;
        }
    }
});
