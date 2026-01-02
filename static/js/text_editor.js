/**
 * Text Editor Class - Implements dual-panel interface for text input
 */
class TextEditor {
    constructor(leftCanvasId, rightCanvasId, filename, snapDist = 15) {
        this.filename = filename;
        this.snapDist = snapDist;
        this.currentRegionIndex = -1;
        this.regions = [];
        this.texts = {};
        this.imageList = [];
        
        // Initialize both canvases
        this.leftCanvas = new fabric.Canvas(leftCanvasId, {
            fireRightClick: true,
            stopContextMenu: true,
            preserveObjectStacking: true,
            uniformScaling: false,
            selection: true,
            backgroundColor: "#151515"
        });
        
        this.rightCanvas = new fabric.Canvas(rightCanvasId, {
            fireRightClick: true,
            stopContextMenu: true,
            preserveObjectStacking: true,
            uniformScaling: false,
            selection: false,
            backgroundColor: "#ffffff" // White background for the right canvas
        });
        
        this.init();
    }

    async init() {
        this.imageList = await API.listImages();
        this.resize();
        window.addEventListener('resize', () => this.resize());
        window.addEventListener('keydown', (e) => this.handleKeyDown(e));
        
        // Setup canvas events
        this.setupCanvasEvents();
        
        // Load image and data
        await this.loadImageAndData();
    }

    resize() {
        const el = document.getElementById('workspace');
        if (el) {
            const panelWidth = el.clientWidth / 2;
            const panelHeight = el.clientHeight;
            
            this.leftCanvas.setWidth(panelWidth);
            this.leftCanvas.setHeight(panelHeight);
            
            this.rightCanvas.setWidth(panelWidth);
            this.rightCanvas.setHeight(panelHeight);
        }
    }

    // Configure polygon for both canvases
    _configurePolygon(obj, isRightCanvas = false) {
        const fill = isRightCanvas ? 'rgba(0, 0, 255, 0.2)' : 'rgba(0, 255, 0, 0.2)';
        const stroke = isRightCanvas ? 'blue' : 'green';
        const cornerColor = isRightCanvas ? 'red' : 'blue';

        obj.set({
            fill: fill,
            stroke: stroke,
            strokeWidth: 2,
            objectCaching: false,
            transparentCorners: false,
            cornerColor: cornerColor,
            selectable: false, // Disable selection and movement of polygons
            evented: true,
            perPixelTargetFind: true,
            hasControls: false, // Disable control points
            lockMovementX: true, // Lock horizontal movement
            lockMovementY: true, // Lock vertical movement
            lockRotation: true, // Lock rotation
            lockScalingX: true, // Lock horizontal scaling
            lockScalingY: true, // Lock vertical scaling
            lockUniScaling: true, // Lock uniform scaling
            // Add custom properties for text association
            hasText: false,
            textContent: ''
        });

        // Ensure the polygon can receive events
        obj.set({
            hoverCursor: 'pointer'
        });

        // Add mouse event handlers directly to the polygon
        obj.on('mousedown', (e) => {
            if (e.button === 0) { // Left click
                console.log("Polygon clicked directly - index:", obj.index); // Debug print
                this.openTextModal(obj.index);
            }
        });
    }

    async loadImageAndData() {
        const infoSpan = document.querySelector('.file-info');
        if (infoSpan) infoSpan.textContent = this.filename;

        // Clear both canvases
        this.leftCanvas.clear();
        this.rightCanvas.clear();
        
        // Load image on left canvas
        const timestamp = new Date().getTime();
        const imgUrl = `/data/images/${this.filename}?t=${timestamp}`;

        const imgEl = new Image();
        imgEl.onload = () => {
            const fabricImg = new fabric.Image(imgEl);

            this.leftCanvas.setBackgroundImage(fabricImg, () => {
                const scale = (this.leftCanvas.width / fabricImg.width) * 0.9;
                this.leftCanvas.setZoom(scale);
                const newW = fabricImg.width * scale;
                this.leftCanvas.viewportTransform[4] = (this.leftCanvas.width - newW) / 2;
                this.leftCanvas.viewportTransform[5] = 20;

                this.leftCanvas.requestRenderAll();
                this.loadRegions();
            });
        };
        imgEl.onerror = () => {
            alert("Image load error.");
        };
        imgEl.src = imgUrl;

        // Set white background for right canvas
        this.rightCanvas.setBackgroundColor("#ffffff", this.rightCanvas.renderAll.bind(this.rightCanvas));
    }

    async loadRegions() {
        try {
            const data = await API.loadAnnotation(this.filename);
            this.regions = data.regions || [];

            // Add regions to both canvases
            this.regions.forEach((region, index) => {
                if (region.points && region.points.length >= 3) {
                    // Add to left canvas (original image)
                    const leftPoly = new fabric.Polygon(region.points);
                    this._configurePolygon(leftPoly, false);
                    leftPoly.set({
                        index: index // Store the index for reference
                    });
                    this.leftCanvas.add(leftPoly);

                    // Add to right canvas (white background)
                    const rightPoly = new fabric.Polygon(region.points);
                    this._configurePolygon(rightPoly, true);
                    rightPoly.set({
                        index: index // Store the index for reference
                    });
                    this.rightCanvas.add(rightPoly);
                }
            });

            // Load existing text data if available
            this.loadTextData();

            this.leftCanvas.requestRenderAll();
            this.rightCanvas.requestRenderAll();
        } catch (error) {
            console.error('Error loading regions:', error);
        }
    }

    async loadTextData() {
        try {
            const data = await API.loadAnnotation(this.filename);
            if (data.texts) {
                this.texts = data.texts;

                // Update regions with text content
                this.regions.forEach((region, index) => {
                    const textContent = this.texts[index] || '';
                    if (textContent) {
                        // Find the corresponding polygon on the left canvas
                        const leftPoly = this.leftCanvas.getObjects().find(obj => obj.index === index);
                        if (leftPoly) {
                            leftPoly.set({ hasText: true, textContent: textContent });
                            // Update color to indicate text is entered
                            leftPoly.set({ fill: 'rgba(0, 128, 0, 0.3)', stroke: '#00cc66' });
                        }

                        // Find the corresponding polygon on the right canvas
                        const rightPoly = this.rightCanvas.getObjects().find(obj => obj.index === index);
                        if (rightPoly) {
                            rightPoly.set({ hasText: true, textContent: textContent });
                            // Update color to indicate text is entered
                            rightPoly.set({ fill: 'rgba(0, 0, 255, 0.3)', stroke: '#0066ff' });
                        }
                    }
                });

                this.leftCanvas.requestRenderAll();
                this.rightCanvas.requestRenderAll();
            }
        } catch (error) {
            console.error('Error loading text data:', error);
        }
    }

    setupCanvasEvents() {
        // Variables for panning
        let isRightClickPanning = false;
        let lastPosX, lastPosY;

        // Left canvas events
        this.leftCanvas.on('mouse:down', (opt) => {
            if (opt.e.button === 0) { // Left click
                // Check if we clicked on a polygon using a more robust method
                const target = this.getPolygonAtCoords(opt.e.clientX, opt.e.clientY, this.leftCanvas);
                console.log("Left canvas click - target:", target); // Debug print
                if (target && target.type === 'polygon') {
                    console.log("Opening modal for region index:", target.index); // Debug print
                    this.openTextModal(target.index);
                } else {
                    console.log("Clicked on canvas but not on a polygon"); // Debug print
                }
            } else if (opt.e.button === 2) { // Right click
                isRightClickPanning = true;
                lastPosX = opt.e.clientX;
                lastPosY = opt.e.clientY;
                this.leftCanvas.defaultCursor = 'grab';
                opt.e.preventDefault();
            }
        });

        this.leftCanvas.on('mouse:move', (opt) => {
            if (isRightClickPanning) {
                const e = opt.e;
                const deltaX = e.clientX - lastPosX;
                const deltaY = e.clientY - lastPosY;

                // Pan the canvas
                const vpt = this.leftCanvas.viewportTransform;
                vpt[4] += deltaX; // tx
                vpt[5] += deltaY; // ty
                this.leftCanvas.requestRenderAll();

                lastPosX = e.clientX;
                lastPosY = e.clientY;
            }
        });

        this.leftCanvas.on('mouse:up', () => {
            isRightClickPanning = false;
            this.leftCanvas.defaultCursor = 'default';
        });

        // Prevent default context menu on canvas
        this.leftCanvas.wrapperEl.addEventListener('contextmenu', (e) => {
            if (e.target.closest('.upper-canvas')) {
                e.preventDefault();
            }
        });

        // Add mouse wheel zoom to left canvas
        this.leftCanvas.wrapperEl.addEventListener('wheel', (e) => {
            e.preventDefault();

            const delta = e.deltaY;
            const zoom = this.leftCanvas.getZoom();
            const zoomFactor = delta > 0 ? 0.9 : 1.1; // Zoom out or in
            const newZoom = zoom * zoomFactor;

            // Limit zoom range
            if (newZoom < 0.1 || newZoom > 10) return;

            // Calculate new viewport transform
            const vpt = this.leftCanvas.viewportTransform;
            const rect = this.leftCanvas.wrapperEl.getBoundingClientRect();
            const offsetX = e.clientX - rect.left;
            const offsetY = e.clientY - rect.top;

            // Calculate the point over which we're zooming
            const point = {
                x: (offsetX - vpt[4]) / vpt[0],
                y: (offsetY - vpt[5]) / vpt[3]
            };

            // Apply new zoom
            vpt[0] = newZoom; // scaleX
            vpt[3] = newZoom; // scaleY

            // Adjust translation to zoom towards mouse position
            vpt[4] = offsetX - point.x * newZoom; // tx
            vpt[5] = offsetY - point.y * newZoom; // ty

            this.leftCanvas.requestRenderAll();
        });

        // Right canvas events
        this.rightCanvas.on('mouse:down', (opt) => {
            if (opt.e.button === 0) { // Left click
                // Check if we clicked on a polygon using a more robust method
                const target = this.getPolygonAtCoords(opt.e.clientX, opt.e.clientY, this.rightCanvas);
                console.log("Right canvas click - target:", target); // Debug print
                if (target && target.type === 'polygon') {
                    console.log("Opening modal for region index:", target.index); // Debug print
                    this.openTextModal(target.index);
                } else {
                    console.log("Clicked on right canvas but not on a polygon"); // Debug print
                }
            } else if (opt.e.button === 2) { // Right click for panning
                isRightClickPanning = true;
                lastPosX = opt.e.clientX;
                lastPosY = opt.e.clientY;
                this.rightCanvas.defaultCursor = 'grab';
                opt.e.preventDefault();
            }
        });

        this.rightCanvas.on('mouse:move', (opt) => {
            if (isRightClickPanning) {
                const e = opt.e;
                const deltaX = e.clientX - lastPosX;
                const deltaY = e.clientY - lastPosY;

                // Pan the canvas
                const vpt = this.rightCanvas.viewportTransform;
                vpt[4] += deltaX; // tx
                vpt[5] += deltaY; // ty
                this.rightCanvas.requestRenderAll();

                lastPosX = e.clientX;
                lastPosY = e.clientY;
            }
        });

        this.rightCanvas.on('mouse:up', () => {
            isRightClickPanning = false;
            this.rightCanvas.defaultCursor = 'default';
        });

        // Prevent default context menu on canvas
        this.rightCanvas.wrapperEl.addEventListener('contextmenu', (e) => {
            if (e.target.closest('.upper-canvas')) {
                e.preventDefault();
            }
        });

        // Add mouse wheel zoom to right canvas
        this.rightCanvas.wrapperEl.addEventListener('wheel', (e) => {
            e.preventDefault();

            const delta = e.deltaY;
            const zoom = this.rightCanvas.getZoom();
            const zoomFactor = delta > 0 ? 0.9 : 1.1; // Zoom out or in
            const newZoom = zoom * zoomFactor;

            // Limit zoom range
            if (newZoom < 0.1 || newZoom > 10) return;

            // Calculate new viewport transform
            const vpt = this.rightCanvas.viewportTransform;
            const rect = this.rightCanvas.wrapperEl.getBoundingClientRect();
            const offsetX = e.clientX - rect.left;
            const offsetY = e.clientY - rect.top;

            // Calculate the point over which we're zooming
            const point = {
                x: (offsetX - vpt[4]) / vpt[0],
                y: (offsetY - vpt[5]) / vpt[3]
            };

            // Apply new zoom
            vpt[0] = newZoom; // scaleX
            vpt[3] = newZoom; // scaleY

            // Adjust translation to zoom towards mouse position
            vpt[4] = offsetX - point.x * newZoom; // tx
            vpt[5] = offsetY - point.y * newZoom; // ty

            this.rightCanvas.requestRenderAll();
        });
    }

    openTextModal(regionIndex) {
        if (regionIndex < 0 || regionIndex >= this.regions.length) return;

        this.currentRegionIndex = regionIndex;

        // Update modal content
        const modal = document.getElementById('text-modal');
        const textInput = document.getElementById('text-input');
        const currentIndexSpan = document.getElementById('current-region-index');
        const totalRegionsSpan = document.getElementById('total-regions');
        const regionPreview = document.getElementById('region-preview-img');

        // Set current text if exists
        const currentText = this.texts[regionIndex] || '';
        textInput.value = currentText;

        // Update counters
        currentIndexSpan.textContent = regionIndex + 1;
        totalRegionsSpan.textContent = this.regions.length;

        // Create a temporary canvas to extract the region image
        this.extractRegionImage(regionIndex, regionPreview);

        // Show modal
        modal.style.display = 'flex';
        textInput.focus();

        // Store the event handler so we can remove it later
        this.modalClickHandler = (event) => {
            if (event.target === modal) {
                this.closeModal();
            }
        };

        // Add event listener to close modal when clicking outside
        document.addEventListener('click', this.modalClickHandler, true);
    }

    extractRegionImage(regionIndex, imgElement) {
        // Get the region polygon
        const region = this.regions[regionIndex];
        if (!region || !region.points || region.points.length < 3) {
            imgElement.src = `/data/images/${this.filename}?t=${new Date().getTime()}`;
            return;
        }

        // Load the main image
        const img = new Image();
        img.crossOrigin = 'Anonymous'; // Handle potential CORS issues
        img.onload = () => {
            // Create a temporary canvas to extract the region
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');

            // Calculate the bounding box of the region
            const xs = region.points.map(p => p.x);
            const ys = region.points.map(p => p.y);
            const minX = Math.min(...xs);
            const maxX = Math.max(...xs);
            const minY = Math.min(...ys);
            const maxY = Math.max(...ys);

            // Add a small padding
            const padding = 10;
            const width = maxX - minX + padding * 2;
            const height = maxY - minY + padding * 2;

            canvas.width = width;
            canvas.height = height;

            // Set background to white
            ctx.fillStyle = 'white';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Create a clipping path for the polygon
            ctx.beginPath();
            ctx.moveTo(region.points[0].x - minX + padding, region.points[0].y - minY + padding);
            for (let i = 1; i < region.points.length; i++) {
                ctx.lineTo(region.points[i].x - minX + padding, region.points[i].y - minY + padding);
            }
            ctx.closePath();
            ctx.clip();

            // Draw the main image at the correct position
            ctx.drawImage(img, -minX + padding, -minY + padding);

            // Set the src of the preview image to the data URL of the canvas
            imgElement.src = canvas.toDataURL('image/png');
        };
        img.onerror = () => {
            imgElement.src = `/data/images/${this.filename}?t=${new Date().getTime()}`;
        };
        img.src = `/data/images/${this.filename}?t=${new Date().getTime()}`;
    }

    closeModal() {
        const modal = document.getElementById('text-modal');
        modal.style.display = 'none';
        this.currentRegionIndex = -1;

        // Remove the event listener that was added when opening the modal
        if (this.modalClickHandler) {
            document.removeEventListener('click', this.modalClickHandler, true);
            this.modalClickHandler = null;
        }
    }

    saveTextAndNext() {
        this.saveCurrentText();

        // Move to next region
        this.nextRegion();
    }

    nextRegion() {
        if (this.regions.length === 0) return;
        
        this.currentRegionIndex = (this.currentRegionIndex + 1) % this.regions.length;
        this.openTextModal(this.currentRegionIndex);
    }

    previousRegion() {
        if (this.regions.length === 0) return;

        this.currentRegionIndex = (this.currentRegionIndex - 1 + this.regions.length) % this.regions.length;
        this.openTextModal(this.currentRegionIndex);
    }

    navigateToNextRegion() {
        if (this.regions.length === 0) return;

        // If no current region is selected, start with the first one
        if (this.currentRegionIndex < 0) {
            this.currentRegionIndex = 0;
        } else {
            // Move to the next region
            this.currentRegionIndex = (this.currentRegionIndex + 1) % this.regions.length;
        }

        this.openTextModal(this.currentRegionIndex);
    }

    // Helper method to get polygon at specific coordinates, accounting for viewport transformations
    getPolygonAtCoords(clientX, clientY, canvas) {
        // Get the canvas element's position and size
        const canvasEl = canvas.wrapperEl;
        const rect = canvasEl.getBoundingClientRect();

        // Calculate the position relative to the canvas
        const x = clientX - rect.left;
        const y = clientY - rect.top;

        // Transform the coordinates according to the current viewport transformation
        const vpt = canvas.viewportTransform;
        if (!vpt) return null;

        // Invert the transformation to get the original coordinates
        const invertedVpt = fabric.util.invertTransform(vpt);
        const originalX = invertedVpt[0] * x + invertedVpt[2] * y + invertedVpt[4];
        const originalY = invertedVpt[1] * x + invertedVpt[3] * y + invertedVpt[5];

        // Check each polygon to see if the point is inside it
        const objects = canvas.getObjects();
        for (let i = 0; i < objects.length; i++) {
            const obj = objects[i];
            if (obj.type === 'polygon') {
                // Check if the point is inside the polygon
                if (this.isPointInPolygon(originalX, originalY, obj)) {
                    return obj;
                }
            }
        }

        return null;
    }

    // Helper method to check if a point is inside a polygon
    isPointInPolygon(x, y, polygon) {
        const points = polygon.points;
        let inside = false;

        for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
            const xi = points[i].x;
            const yi = points[i].y;
            const xj = points[j].x;
            const yj = points[j].y;

            const intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
            if (intersect) inside = !inside;
        }

        return inside;
    }

    navigateToPreviousRegion() {
        if (this.regions.length === 0) return;

        // If no current region is selected, start with the last one
        if (this.currentRegionIndex < 0) {
            this.currentRegionIndex = this.regions.length - 1;
        } else {
            // Move to the previous region
            this.currentRegionIndex = (this.currentRegionIndex - 1 + this.regions.length) % this.regions.length;
        }

        this.openTextModal(this.currentRegionIndex);
    }

    handleKeyDown(e) {
        // Handle Enter key to save and go to next region (only when modal is open)
        if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey && !e.altKey) {
            const modal = document.getElementById('text-modal');
            if (modal.style.display === 'flex') {
                e.preventDefault();
                this.saveTextAndNext();
            }
        }
        // Handle Ctrl+Enter to save and stay on the same region
        else if (e.key === 'Enter' && e.ctrlKey) {
            e.preventDefault();
            this.saveCurrentText();
        }
        // Handle Escape key to close modal
        else if (e.key === 'Escape') {
            const modal = document.getElementById('text-modal');
            if (modal.style.display === 'flex') {
                this.closeModal();
            }
        }
        // Handle arrow keys for navigation
        else if (e.key === 'ArrowRight') {
            this.nextRegion();
        }
        else if (e.key === 'ArrowLeft') {
            this.previousRegion();
        }
        // Handle Ctrl+S for saving
        else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            this.saveData();
        }
        // Handle Ctrl+Left/Right for image navigation
        else if (e.ctrlKey && e.key === 'ArrowLeft') {
            this.goImage(-1);
        }
        else if (e.ctrlKey && e.key === 'ArrowRight') {
            this.goImage(1);
        }
    }

    saveCurrentText() {
        if (this.currentRegionIndex < 0) return;

        const textInput = document.getElementById('text-input');
        const text = textInput.value.trim();

        // Save text for current region
        this.texts[this.currentRegionIndex] = text;

        // Update the polygon objects to reflect that they have text
        const leftPoly = this.leftCanvas.getObjects().find(obj => obj.index === this.currentRegionIndex);
        const rightPoly = this.rightCanvas.getObjects().find(obj => obj.index === this.currentRegionIndex);

        if (leftPoly) {
            leftPoly.set({ hasText: text !== '', textContent: text });
            // Change color based on whether text exists
            if (text) {
                // Text exists - green
                leftPoly.set({ fill: 'rgba(0, 128, 0, 0.3)', stroke: '#00cc66' });
            } else {
                // No text - original green
                leftPoly.set({ fill: 'rgba(0, 255, 0, 0.2)', stroke: 'green' });
            }
        }

        if (rightPoly) {
            rightPoly.set({ hasText: text !== '', textContent: text });
            // Change color based on whether text exists
            if (text) {
                // Text exists - blue
                rightPoly.set({ fill: 'rgba(0, 0, 255, 0.3)', stroke: '#0066ff' });
            } else {
                // No text - original blue
                rightPoly.set({ fill: 'rgba(0, 0, 255, 0.2)', stroke: 'blue' });
            }
        }

        this.leftCanvas.requestRenderAll();
        this.rightCanvas.requestRenderAll();
    }

    goImage(dir) {
        const idx = this.imageList.indexOf(this.filename);
        if (idx === -1) return;
        const newFilename = this.imageList[(idx + dir + this.imageList.length) % this.imageList.length];
        const newUrl = `${window.location.pathname}?image=${newFilename}`;
        history.pushState({ filename: newFilename }, '', newUrl);
        this.filename = newFilename;
        this.loadImageAndData();
    }

    async saveData() {
        const statusEl = document.getElementById('status');
        if (statusEl) statusEl.textContent = 'Сохранение...';

        try {
            // Prepare data to save
            const saveData = {
                image_name: this.filename,
                regions: this.regions,
                texts: this.texts,
                status: 'texted' // New status for text input completed
            };

            await API.saveAnnotation(this.filename, saveData.regions, saveData.texts);
            
            if (statusEl) statusEl.textContent = 'Сохранено';
        } catch (error) {
            console.error('Save error:', error);
            if (statusEl) statusEl.textContent = 'Ошибка сохранения';
        }
    }
}

// Extend the API object to support text data
if (typeof API !== 'undefined') {
    API.saveAnnotation = async function(filename, regions, texts = {}) {
        const data = {
            image_name: filename,
            regions: regions || [],
            texts: texts
        };
        
        const response = await fetch('/api/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    };
}