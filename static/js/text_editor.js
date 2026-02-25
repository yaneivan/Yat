/**
 * Text Editor Class - Implements dual-panel interface for text input
 */
class TextEditor {
    constructor(leftCanvasId, rightCanvasId, filename, project = null, snapDist = 15) {
        this.filename = filename;
        this.project = project; 
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

        // Initialize viewport synchronization
        this.initViewportSync();

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

    // Метод для перехода к другим инструментам с сохранением контекста
    navigateTo(toolName) {
        let url = `/${toolName}?image=${this.filename}`;
        if (this.project) {
            url += `&project=${this.project}`;
        }
        window.location.href = url;
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

    // Update text inside a polygon
    updatePolygonText(polygon, text) {
        // Remove existing text and background objects if they exist
        if (polygon.textObject) {
            this.rightCanvas.remove(polygon.textObject);
            polygon.textObject = null;
        }

        if (polygon.bgRectObject) {
            this.rightCanvas.remove(polygon.bgRectObject);
            polygon.bgRectObject = null;
        }

        if (text && text.trim() !== '') {
            // Calculate the bounding box of the polygon to determine appropriate font size
            const minX = Math.min(...polygon.points.map(p => p.x));
            const maxX = Math.max(...polygon.points.map(p => p.x));
            const minY = Math.min(...polygon.points.map(p => p.y));
            const maxY = Math.max(...polygon.points.map(p => p.y));
            const polygonWidth = maxX - minX;
            const polygonHeight = maxY - minY;

            // Use 30% of the smaller dimension for the font size, with a minimum of 12 and maximum of 60 for better readability
            const fontSize = Math.max(12, Math.min(60, Math.round(Math.min(polygonWidth, polygonHeight) * 0.3)));

            // Create a text object with better styling for visibility
            const textObj = new fabric.Text(text, {
                fontSize: fontSize,
                fill: '#000000', // Black text for contrast
                originX: 'center',
                originY: 'center',
                fontFamily: 'Arial, sans-serif',
                fontWeight: 'bold',
                // Add text wrapping if needed
                width: polygonWidth * 0.8, // Use 80% of polygon width for text wrapping
                textAlign: 'center',
                // Make text non-interactive to prevent direct dragging on canvas
                selectable: false,
                evented: false
            });

            // Position the text in the center of the polygon
            const center = this.getPolygonCenter(polygon);

            // Set the position for the text
            textObj.set({
                left: center.x,
                top: center.y,
            });

            // Update coordinates after setting position
            textObj.setCoords();

            // Calculate text dimensions to create a background rectangle
            // We need to add the text temporarily to get accurate dimensions
            this.rightCanvas.add(textObj);
            textObj.bringToFront(); // Ensure text is on top for accurate measurements
            textObj.setCoords(); // Update coordinates after adding to canvas

            // Create a background rectangle for better visibility against white polygon
            const bgRect = new fabric.Rect({
                left: textObj.aCoords.tl.x - 5, // Add padding
                top: textObj.aCoords.tl.y - 5, // Add padding
                width: (textObj.aCoords.tr.x - textObj.aCoords.tl.x) + 10, // Add padding
                height: (textObj.aCoords.bl.y - textObj.aCoords.tl.y) + 10, // Add padding
                fill: 'rgba(255, 255, 0, 0.4)', // Light yellow semi-transparent background for contrast
                stroke: '#000000',
                strokeWidth: 1,
                rx: 8, // More rounded corners
                ry: 8,
                originX: 'left',
                originY: 'top',
                // Make background non-interactive to prevent direct dragging on canvas
                selectable: false,
                evented: false
            });

            // Remove the text temporarily to add the background first
            this.rightCanvas.remove(textObj);

            // Add the background rectangle and then the text object to the canvas
            this.rightCanvas.add(bgRect);
            this.rightCanvas.add(textObj);

            // Move both objects to the top to ensure they're visible
            this.rightCanvas.bringToFront(bgRect);
            this.rightCanvas.bringToFront(textObj);

            // Ensure the polygon is below the text and background
            this.rightCanvas.sendToBack(polygon);

            // Store reference to both objects
            polygon.textObject = textObj;
            polygon.bgRectObject = bgRect;
        }

        this.rightCanvas.requestRenderAll();
    }

    // Calculate the center of a polygon
    getPolygonCenter(polygon) {
        const points = polygon.points;
        let xSum = 0;
        let ySum = 0;

        for (let i = 0; i < points.length; i++) {
            xSum += points[i].x;
            ySum += points[i].y;
        }

        return {
            x: xSum / points.length,
            y: ySum / points.length
        };
    }

    // Synchronize viewport between left and right canvases
    syncViewports(sourceCanvas, targetCanvas) {
        // Copy the viewport transformation matrix
        targetCanvas.setViewportTransform([...sourceCanvas.viewportTransform]);
        targetCanvas.requestRenderAll();
    }

    // Initialize viewport synchronization
    initViewportSync() {
        // Add event listeners to synchronize viewport changes
        this.leftCanvas.on('mouse:wheel', (opt) => {
            // Synchronize zoom on mouse wheel
            this.syncViewports(this.leftCanvas, this.rightCanvas);
        });

        this.leftCanvas.on('mouse:up', (opt) => {
            // Synchronize panning after mouse release
            this.syncViewports(this.leftCanvas, this.rightCanvas);
        });

        this.leftCanvas.on('mouse:down', (opt) => {
            // Set up continuous synchronization during dragging
            this.leftCanvas.on('after:render', () => {
                this.syncViewports(this.leftCanvas, this.rightCanvas);
            });
        });

        this.leftCanvas.on('mouse:up', (opt) => {
            // Stop continuous synchronization after dragging
            this.leftCanvas.off('after:render');
            this.syncViewports(this.leftCanvas, this.rightCanvas);
        });

        this.rightCanvas.on('mouse:wheel', (opt) => {
            // Synchronize zoom on mouse wheel
            this.syncViewports(this.rightCanvas, this.leftCanvas);
        });

        this.rightCanvas.on('mouse:up', (opt) => {
            // Synchronize panning after mouse release
            this.syncViewports(this.rightCanvas, this.leftCanvas);
        });

        this.rightCanvas.on('mouse:down', (opt) => {
            // Set up continuous synchronization during dragging
            this.rightCanvas.on('after:render', () => {
                this.syncViewports(this.rightCanvas, this.leftCanvas);
            });
        });

        this.rightCanvas.on('mouse:up', (opt) => {
            // Stop continuous synchronization after dragging
            this.rightCanvas.off('after:render');
            this.syncViewports(this.rightCanvas, this.leftCanvas);
        });
    }

    async loadImageAndData() {
        const infoSpan = document.querySelector('.file-info');
        if (infoSpan) infoSpan.textContent = this.filename;

        // Clear both canvases
        this.leftCanvas.clear();
        this.rightCanvas.clear();

        // Load image on both canvases
        const timestamp = new Date().getTime();
        const imgUrl = `/data/images/${this.filename}?t=${timestamp}`;

        const imgEl = new Image();
        imgEl.onload = () => {
            const fabricImg = new fabric.Image(imgEl);

            // Load image on left canvas
            this.leftCanvas.setBackgroundImage(fabricImg, () => {
                const scale = (this.leftCanvas.width / fabricImg.width) * 0.9;
                this.leftCanvas.setZoom(scale);
                const newW = fabricImg.width * scale;
                this.leftCanvas.viewportTransform[4] = (this.leftCanvas.width - newW) / 2;
                this.leftCanvas.viewportTransform[5] = 20;

                this.leftCanvas.requestRenderAll();
            });

            // Load image on right canvas with white background
            this.rightCanvas.setBackgroundImage(fabricImg, () => {
                const scale = (this.rightCanvas.width / fabricImg.width) * 0.9;
                this.rightCanvas.setZoom(scale);
                const newW = fabricImg.width * scale;
                this.rightCanvas.viewportTransform[4] = (this.rightCanvas.width - newW) / 2;
                this.rightCanvas.viewportTransform[5] = 20;

                // Set white background for right canvas
                this.rightCanvas.backgroundColor = "#ffffff";
                this.rightCanvas.requestRenderAll();

                // Load regions after both images are loaded
                this.loadRegions();
            });
        };
        imgEl.onerror = () => {
            alert("Image load error.");
        };
        imgEl.src = imgUrl;
    }

    async loadRegions() {
        try {
            const data = await API.loadAnnotation(this.filename);
            let originalRegions = data.regions || [];

            // Create a mapping from sorted indices back to original indices
            let sortedRegions = this.sortRegionsTopToBottom([...originalRegions]); // Create a copy to sort

            // Store the sorted regions
            this.regions = sortedRegions;

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

            this.leftCanvas.requestRenderAll();
            this.rightCanvas.requestRenderAll();

            // Load existing text data if available, with mapping to sorted order
            this.loadTextData(originalRegions);
        } catch (error) {
            console.error('Error loading regions:', error);
        }
    }

    // Function to sort regions from top to bottom based on their vertical position
    sortRegionsTopToBottom(regions) {
        return regions.sort((a, b) => {
            // Calculate the top position (minimum Y coordinate) of each region
            const aTop = Math.min(...a.points.map(p => p.y));
            const bTop = Math.min(...b.points.map(p => p.y));

            // If top positions are similar (within 10 pixels), sort by left position
            if (Math.abs(aTop - bTop) < 10) {
                const aLeft = Math.min(...a.points.map(p => p.x));
                const bLeft = Math.min(...b.points.map(p => p.x));
                return aLeft - bLeft;
            }

            return aTop - bTop;
        });
    }

    async loadTextData(originalRegions = null) {
        try {
            const data = await API.loadAnnotation(this.filename);
            if (data.texts) {
                // If originalRegions is provided, we need to map the texts from original indices to sorted indices
                if (originalRegions) {
                    // Create a mapping from sorted regions back to original indices
                    this.texts = {};

                    // For each region in the sorted order, find its original index and get the corresponding text
                    for (let sortedIndex = 0; sortedIndex < this.regions.length; sortedIndex++) {
                        // Find the original index of this region in the originalRegions array
                        const sortedRegion = this.regions[sortedIndex];

                        // Find the original index by comparing the region points
                        let originalIndex = -1;
                        for (let origIndex = 0; origIndex < originalRegions.length; origIndex++) {
                            const origRegion = originalRegions[origIndex];

                            // Compare if the regions are the same by checking if they have the same points
                            if (this.regionsAreEqual(sortedRegion, origRegion)) {
                                originalIndex = origIndex;
                                break;
                            }
                        }

                        // Get the text for the original index and assign it to the sorted index
                        this.texts[sortedIndex] = data.texts[originalIndex] || '';
                    }
                } else {
                    // Fallback: just copy the texts as they are (for backward compatibility)
                    this.texts = data.texts;
                }

                // Update regions with text content
                this.regions.forEach((region, index) => {
                    const textContent = this.texts[index] || '';

                    // Find the corresponding polygon on the left canvas
                    const leftPoly = this.leftCanvas.getObjects().find(obj => obj.index === index);
                    if (leftPoly) {
                        leftPoly.set({ hasText: textContent !== '', textContent: textContent });
                        // Update color to indicate text is entered
                        if (textContent) {
                            leftPoly.set({ fill: 'rgba(0, 128, 0, 0.3)', stroke: '#00cc66' });
                        } else {
                            leftPoly.set({ fill: 'rgba(0, 255, 0, 0.2)', stroke: 'green' });
                        }
                    }

                    // Find the corresponding polygon on the right canvas
                    const rightPoly = this.rightCanvas.getObjects().find(obj => obj.index === index);
                    if (rightPoly) {
                        rightPoly.set({ hasText: textContent !== '', textContent: textContent });
                        // Update color based on whether text exists
                        if (textContent) {
                            // Text exists - white background to match the white canvas
                            rightPoly.set({ fill: 'rgba(255, 255, 255, 1.0)', stroke: '#0066ff' });

                            // Add text inside the right polygon if text exists
                            this.updatePolygonText(rightPoly, textContent);
                        } else {
                            // No text - blue transparent background to show the image underneath
                            rightPoly.set({ fill: 'rgba(0, 0, 255, 0.2)', stroke: 'blue' });

                            // Remove text if it exists
                            this.updatePolygonText(rightPoly, '');
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

    // Helper function to compare if two regions are equal based on their points
    regionsAreEqual(region1, region2) {
        if (!region1.points || !region2.points || region1.points.length !== region2.points.length) {
            return false;
        }

        for (let i = 0; i < region1.points.length; i++) {
            if (region1.points[i].x !== region2.points[i].x || region1.points[i].y !== region2.points[i].y) {
                return false;
            }
        }

        return true;
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

            // Add a larger padding to show context around the polygon
            const padding = 50;
            const width = maxX - minX + padding * 2;
            const height = maxY - minY + padding * 2;

            canvas.width = width;
            canvas.height = height;

            // Draw the main image at the correct position to show context
            ctx.drawImage(img, -minX + padding, -minY + padding);

            // Draw the polygon with a semi-transparent fill and border to highlight the region
            ctx.beginPath();
            ctx.moveTo(region.points[0].x - minX + padding, region.points[0].y - minY + padding);
            for (let i = 1; i < region.points.length; i++) {
                ctx.lineTo(region.points[i].x - minX + padding, region.points[i].y - minY + padding);
            }
            ctx.closePath();

            // Fill with semi-transparent color to highlight the polygon
            ctx.fillStyle = 'rgba(0, 100, 255, 0.3)';
            ctx.fill();

            // Draw a border around the polygon
            ctx.strokeStyle = 'rgba(0, 0, 255, 0.8)';
            ctx.lineWidth = 2;
            ctx.stroke();

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
                // Text exists - white background to match the white canvas
                rightPoly.set({ fill: 'rgba(255, 255, 255, 1.0)', stroke: '#0066ff' });

                // Add text inside the right polygon if text exists
                this.updatePolygonText(rightPoly, text);
            } else {
                // No text - blue transparent background to show the image underneath
                rightPoly.set({ fill: 'rgba(0, 0, 255, 0.2)', stroke: 'blue' });

                // Remove text if it exists
                this.updatePolygonText(rightPoly, '');
            }
        }

        this.leftCanvas.requestRenderAll();
        this.rightCanvas.requestRenderAll();

        // Trigger auto-save after saving text
        this.autoSave();
    }

    goImage(dir) {
        const idx = this.imageList.indexOf(this.filename);
        if (idx === -1) return;
        
        // Вычисляем новое имя файла
        const newFilename = this.imageList[(idx + dir + this.imageList.length) % this.imageList.length];
        
        // 1. Обновляем переменную класса
        this.filename = newFilename;
        
        // 2. Обновляем текст в тулбаре (визуально)
        const display = document.getElementById('filename-display');
        if (display) display.textContent = newFilename;

        // 3. Формируем URL, сохраняя параметр project, если он есть
        let newUrl = `${window.location.pathname}?image=${newFilename}`;
        if (this.project) {
            newUrl += `&project=${this.project}`;
        }
        
        // 4. Обновляем адресную строку без перезагрузки
        history.pushState({ filename: newFilename }, '', newUrl);
        
        // 5. Загружаем новые данные
        this.loadImageAndData();
    }

    async saveData() {
        const saveStatusEl = document.getElementById('save-status');
        if (saveStatusEl) saveStatusEl.textContent = 'Сохранение...';

        try {
            // Prepare data to save - we need to map the texts back to the original region order
            // Get the original regions to create the mapping
            const originalData = await API.loadAnnotation(this.filename);
            const originalRegions = originalData.regions || [];

            // Create a mapping of texts in the original region order
            const textsInOriginalOrder = {};

            for (let sortedIndex = 0; sortedIndex < this.regions.length; sortedIndex++) {
                const sortedRegion = this.regions[sortedIndex];

                // Find the original index of this region
                let originalIndex = -1;
                for (let origIndex = 0; origIndex < originalRegions.length; origIndex++) {
                    if (this.regionsAreEqual(sortedRegion, originalRegions[origIndex])) {
                        originalIndex = origIndex;
                        break;
                    }
                }

                // Map the text from sorted index to original index
                if (originalIndex !== -1) {
                    textsInOriginalOrder[originalIndex] = this.texts[sortedIndex] || '';
                }
            }

            // Prepare data to save
            const saveData = {
                image_name: this.filename,
                regions: originalRegions, // Use original regions order
                texts: textsInOriginalOrder,
                status: 'texted' // New status for text input completed
            };

            await API.saveAnnotationWithTexts(this.filename, saveData.regions, saveData.texts);

            if (saveStatusEl) saveStatusEl.textContent = 'Сохранено';
        } catch (error) {
            console.error('Save error:', error);
            if (saveStatusEl) saveStatusEl.textContent = 'Ошибка сохранения';
        }
    }

    // Auto-save functionality
    autoSave() {
        // Save data automatically after a delay to avoid excessive requests
        if (this.autoSaveTimeout) {
            clearTimeout(this.autoSaveTimeout);
        }

        this.autoSaveTimeout = setTimeout(() => {
            this.saveData();
        }, 2000); // Auto-save after 2 seconds of inactivity
    }

    async recognizeText() {
        const recognitionStatusEl = document.getElementById('recognition-status');
        if (recognitionStatusEl) recognitionStatusEl.textContent = 'Распознавание... (0%)';

        try {
            // Get the original unsorted regions to send to the backend
            const originalData = await API.loadAnnotation(this.filename);
            const originalRegions = originalData.regions || [];

            const response = await fetch('/api/recognize_text', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    image_name: this.filename,
                    regions: originalRegions  // Send original unsorted regions
                })
            });

            const data = await response.json();

            if (data.status === 'success') {
                // Poll for completion with progress updates
                this.pollForRecognitionResults(recognitionStatusEl);
            } else {
                console.error('Recognition error:', data.msg);
                if (recognitionStatusEl) recognitionStatusEl.textContent = 'Ошибка распознавания';
            }
        } catch (error) {
            console.error('Recognition API error:', error);
            if (recognitionStatusEl) recognitionStatusEl.textContent = 'Ошибка распознавания';
        }
    }

    pollForRecognitionResults(recognitionStatusEl) {
        // Check recognition progress using the new endpoint
        const checkStatus = async () => {
            try {
                const progressData = await fetch(`/api/recognize_progress/${encodeURIComponent(this.filename)}`);
                const progress = await progressData.json();

                if (progress.status === 'completed') {
                    // Recognition complete, update UI
                    if (recognitionStatusEl) recognitionStatusEl.textContent = 'Распознано (100%)';

                    // Update the local texts data
                    const data = await API.loadAnnotation(this.filename);
                    // Load the text data with the original regions to map correctly to sorted order
                    const originalData = await API.loadAnnotation(this.filename);
                    const originalRegions = originalData.regions || [];
                    this.loadTextData(originalRegions);

                    // Auto-save after recognition is complete
                    this.autoSave();
                } else {
                    // Update progress indicator
                    if (recognitionStatusEl) recognitionStatusEl.textContent = `Распознавание... (${progress.percentage}%)`;

                    // Continue polling
                    setTimeout(checkStatus, 1000); // Check every second
                }
            } catch (error) {
                console.error('Error checking recognition status:', error);
                // Continue polling even if there's an error
                setTimeout(checkStatus, 1000);
            }
        };

        checkStatus();
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