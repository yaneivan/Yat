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
        this.notepadMode = false; // Notepad mode state
        this.notepadFocusedIndex = -1; // Currently focused line in notepad mode
        this.textsHistory = []; // History of text states for undo
        this.historyIndex = -1; // Current position in history
        this.maxHistoryLength = 50; // Maximum history entries
        this.saveHistoryTimeout = null; // Timeout for debounced history saving
        this.isSaving = false; // Флаг блокировки сохранения при переключении
        this.isSwitching = false; // Флаг блокировки переключения при сохранении

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
        this.imageList = await API.listImages(this.project);
        this.resize();
        window.addEventListener('resize', () => this.resize());
        window.addEventListener('keydown', (e) => this.handleKeyDown(e));

        // Initialize save indicator
        this.setSaveIndicator('idle');

        // Save on page unload/reload
        window.addEventListener('beforeunload', () => {
            if (this.autoSaveTimeout) {
                clearTimeout(this.autoSaveTimeout);
                this.saveData(); // Save immediately before unload
            }
        });

        // Setup canvas events
        this.setupCanvasEvents();

        // Initialize viewport synchronization
        this.initViewportSync();

        // Load image and data (also caches image for preview)
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

            // Parse text for formatting and create an IText object with styled text
            const styledText = this.parseFormats(text);

            // Create a text object with better styling for visibility
            const textObj = new fabric.IText(styledText.text, {
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
                evented: false,
                // Apply styles from parsed formatting
                styles: styledText.styles
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

    // Parse text for formatting markers: [текст] and ~текст~
    parseFormats(text) {
        const styles = {};
        let processedText = text;

        // First pass: find all formatting markers and their positions
        // Strong strikethrough: [текст]
        const strongRegex = /\[([^\]]+)\]/g;
        let match;

        while ((match = strongRegex.exec(text)) !== null) {
            const startIndex = match.index;
            const endIndex = startIndex + match[0].length;
            const innerStart = startIndex + 1;
            const innerEnd = endIndex - 1;

            // Mark characters for removal (brackets)
            for (let i = startIndex; i < endIndex; i++) {
                if (!styles[i]) styles[i] = {};
                styles[i].remove = true;
            }

            // Apply strong strikethrough to inner text
            for (let i = innerStart; i < innerEnd; i++) {
                if (!styles[i]) styles[i] = {};
                styles[i].stroke = 'black';
                styles[i].strokeWidth = 2;
            }
        }

        // Weak strikethrough: ~текст~
        const weakRegex = /~([^~]+)~/g;
        while ((match = weakRegex.exec(text)) !== null) {
            const startIndex = match.index;
            const endIndex = startIndex + match[0].length;
            const innerStart = startIndex + 1;
            const innerEnd = endIndex - 1;

            // Mark characters for removal (tildes)
            for (let i = startIndex; i < endIndex; i++) {
                if (!styles[i]) styles[i] = {};
                styles[i].remove = true;
            }

            // Apply weak strikethrough to inner text
            for (let i = innerStart; i < innerEnd; i++) {
                if (!styles[i]) styles[i] = {};
                styles[i].stroke = 'black';
                styles[i].strokeWidth = 1;
            }
        }

        // Build the final text and adjust styles for removed characters
        let finalText = '';
        const finalStyles = {};
        let offset = 0;

        for (let i = 0; i < processedText.length; i++) {
            if (styles[i] && styles[i].remove) {
                offset++;
                continue;
            }
            finalText += processedText[i];
            if (styles[i]) {
                finalStyles[i - offset] = { ...styles[i] };
                delete finalStyles[i - offset].remove;
            }
        }

        // Convert styles to fabric.js format
        const fabricStyles = {};
        for (const [index, style] of Object.entries(finalStyles)) {
            fabricStyles[index] = {};
            if (style.stroke) {
                fabricStyles[index].stroke = style.stroke;
            }
            if (style.strokeWidth) {
                fabricStyles[index].strokeWidth = style.strokeWidth;
            }
        }

        return { text: finalText, styles: fabricStyles };
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
        // Sync on zoom (wheel) — left to right
        this.leftCanvas.on('mouse:wheel', () => {
            this.syncViewports(this.leftCanvas, this.rightCanvas);
        });

        // Sync on zoom (wheel) — right to left
        this.rightCanvas.on('mouse:wheel', () => {
            this.syncViewports(this.rightCanvas, this.leftCanvas);
        });

        // Sync on mouse up (after panning) — left to right
        this.leftCanvas.on('mouse:up', () => {
            this.syncViewports(this.leftCanvas, this.rightCanvas);
        });

        // Sync on mouse up (after panning) — right to left
        this.rightCanvas.on('mouse:up', () => {
            this.syncViewports(this.rightCanvas, this.leftCanvas);
        });
    }

    async loadImageAndData() {
        const infoSpan = document.querySelector('.file-info');
        if (infoSpan) infoSpan.textContent = this.filename;

        // Load image on both canvases
        const timestamp = new Date().getTime();
        const projectParam = this.project ? `&project=${this.project}` : '';
        const imgUrl = `/data/images/${this.filename}?t=${timestamp}${projectParam}`;

        // Сохраняем версию загрузки для обнаружения race condition
        const loadVersion = this._loadVersion = (this._loadVersion || 0) + 1;

        const imgEl = new Image();
        imgEl.crossOrigin = 'Anonymous';
        imgEl.onload = () => {
            // Проверяем что версия всё ещё актуальна
            if (loadVersion !== this._loadVersion) {
                console.log(`Image load skipped: version ${loadVersion} != ${this._loadVersion}`);
                return;
            }
            const fabricImg = new fabric.Image(imgEl);

            // Load image on left canvas
            this.leftCanvas.setBackgroundImage(fabricImg, () => {
                if (loadVersion !== this._loadVersion) return;
                const scale = (this.leftCanvas.width / fabricImg.width) * 0.9;
                this.leftCanvas.setZoom(scale);
                const newW = fabricImg.width * scale;
                this.leftCanvas.viewportTransform[4] = (this.leftCanvas.width - newW) / 2;
                this.leftCanvas.viewportTransform[5] = 20;

                if (typeof zoomCtrl !== 'undefined') {
                    zoomCtrl.setBaseZoom(scale);
                }

                this.leftCanvas.requestRenderAll();
            });

            // Load image on right canvas with white background
            this.rightCanvas.setBackgroundImage(fabricImg, () => {
                if (loadVersion !== this._loadVersion) return;
                const scale = (this.rightCanvas.width / fabricImg.width) * 0.9;
                this.rightCanvas.setZoom(scale);
                const newW = fabricImg.width * scale;
                this.rightCanvas.viewportTransform[4] = (this.rightCanvas.width - newW) / 2;
                this.rightCanvas.viewportTransform[5] = 20;

                // Set white background for right canvas
                this.rightCanvas.backgroundColor = "#ffffff";
                this.rightCanvas.requestRenderAll();

                // Cache the loaded image for region preview (avoid double loading)
                this.cachedPreviewImage = imgEl;

                // Load regions after both images are loaded
                // loadRegions() handles its own cleanup
                this.loadRegions(loadVersion);
            });
        };
        imgEl.onerror = () => {
            alert("Image load error.");
        };
        imgEl.src = imgUrl;
    }

    async loadRegions(expectedVersion) {
        // === ОЧИСТКА СТАРЫХ ДАННЫХ ===
        this.regions = [];
        this.texts = {};

        // Очищаем левый канвас от полигонов
        const leftObjects = this.leftCanvas.getObjects('polygon');
        this.leftCanvas.remove(...leftObjects);

        // Очищаем правый канвас от ВСЕХ объектов (полигоны, текст, прямоугольники)
        const rightObjects = this.rightCanvas.getObjects();
        this.rightCanvas.remove(...rightObjects);

        // Сбрасываем notepad mode
        if (this.notepadMode) {
            this.toggleNotepadMode();
        }
        // ===============================

        try {
            const data = await API.loadAnnotation(this.filename, this.project);
            
            // Проверяем что версия всё ещё актуальна
            if (expectedVersion !== this._loadVersion) {
                console.log(`Regions load skipped: version ${expectedVersion} != ${this._loadVersion}`);
                return;
            }
            
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

        // Обновляем статус при переключении изображения
        if (window.statusWidget && typeof window.statusWidget.loadStatus === 'function') {
            window.statusWidget.filename = this.filename;
            window.statusWidget.loadStatus();
            window.statusWidget.render();
        }

        // Update notepad if in notepad mode (in case regions changed)
        this.updateNotepadOnRegionsChange();
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
            const data = await API.loadAnnotation(this.filename, this.project);
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

                // Update notepad if in notepad mode
                this.updateNotepadOnRegionsChange();
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

    // ==================== NOTEPAD MODE METHODS ====================

    // Save current state to history
    saveToHistory() {
        // Debounce history saving - don't save too frequently
        if (this.saveHistoryTimeout) {
            clearTimeout(this.saveHistoryTimeout);
        }
        
        this.saveHistoryTimeout = setTimeout(() => {
            this._saveToHistoryInternal();
        }, 300); // Save to history after 300ms of inactivity
    }
    
    // Internal method to save to history (called after debounce)
    _saveToHistoryInternal() {
        // Clone current texts
        const currentState = JSON.parse(JSON.stringify(this.texts));

        // Remove any future states if we're in the middle of history
        if (this.historyIndex < this.textsHistory.length - 1) {
            this.textsHistory = this.textsHistory.slice(0, this.historyIndex + 1);
        }

        // Add current state to history
        this.textsHistory.push(currentState);

        // Limit history length
        if (this.textsHistory.length > this.maxHistoryLength) {
            this.textsHistory.shift();
        } else {
            this.historyIndex++;
        }
    }

    // Undo last action
    undo() {
        if (this.historyIndex > 0) {
            this.historyIndex--;
            const previousState = this.textsHistory[this.historyIndex];
            this.texts = JSON.parse(JSON.stringify(previousState));

            // Update UI
            this.renderNotepad();

            // Update polygons
            this.updatePolygonsWithTexts();

            this.showNotification('Действие отменено', 'undo');
        } else if (this.historyIndex === 0) {
            // First state - restore to initial state (not clear all!)
            this.historyIndex = 0;
            const initialState = this.textsHistory[0];
            this.texts = JSON.parse(JSON.stringify(initialState));
            this.renderNotepad();
            this.updatePolygonsWithTexts();
            this.showNotification('Нет действий для отмены', 'info');
        }
    }

    // Toggle notepad mode on/off
    toggleNotepadMode() {
        this.notepadMode = !this.notepadMode;

        const notepadContainer = document.getElementById('notepad-container');
        const rightCanvasContainer = document.getElementById('right-canvas-container');
        const btn = document.getElementById('btn-notepad-mode');

        if (this.notepadMode) {
            notepadContainer.classList.add('active');
            rightCanvasContainer.classList.add('hidden');
            btn.classList.add('active');
            // Save initial state when opening notepad
            this.saveToHistory();
            this.renderNotepad();
        } else {
            notepadContainer.classList.remove('active');
            rightCanvasContainer.classList.remove('hidden');
            btn.classList.remove('active');
            // Update polygons with current text data
            this.updatePolygonsWithTexts();
            // Auto-save text changes when exiting notepad mode
            this.autoSave();
        }
    }

    // Render notepad lines from sorted regions
    renderNotepad() {
        const linesContainer = document.getElementById('notepad-lines');
        if (!linesContainer) return;

        linesContainer.innerHTML = '';

        this.regions.forEach((region, index) => {
            const lineDiv = document.createElement('div');
            lineDiv.className = 'notepad-line';
            lineDiv.dataset.index = index;

            const textContent = this.texts[index] || '';
            if (textContent) {
                lineDiv.classList.add('has-text');
            }

            // Line number
            const numberSpan = document.createElement('span');
            numberSpan.className = 'notepad-line-number';
            numberSpan.textContent = index + 1;

            // Text input
            const input = document.createElement('input');
            input.type = 'text';
            input.value = textContent;
            input.placeholder = `Сегмент ${index + 1}`;
            input.dataset.index = index;

            // Focus event - highlight polygon on canvas
            input.addEventListener('focus', (e) => this.onNotepadLineFocus(e, index));
            input.addEventListener('blur', () => this.onNotepadLineBlur(index));

            // Key events for Enter and Backspace logic
            input.addEventListener('keydown', (e) => this.onNotepadKeyDown(e, index));

            // Input event to update text in memory
            input.addEventListener('input', (e) => {
                const oldValue = this.texts[index];
                const newValue = e.target.value;

                this.texts[index] = newValue;
                if (newValue) {
                    lineDiv.classList.add('has-text');
                } else {
                    lineDiv.classList.remove('has-text');
                }

                // Save to history if text actually changed (for undo support)
                if (oldValue !== newValue) {
                    this.saveToHistory();
                }

                // Auto-save after text change (with visual feedback)
                this.autoSave();
            });

            lineDiv.appendChild(numberSpan);
            lineDiv.appendChild(input);
            linesContainer.appendChild(lineDiv);
        });
    }

    // Update save indicator status
    setSaveIndicator(status) {
        const indicator = document.getElementById('save-indicator');
        if (!indicator) return;
        
        // Remove all status classes
        indicator.classList.remove('saving', 'saved', 'error');
        
        // Add new status (idle is default - no class needed)
        if (status && status !== 'idle') {
            indicator.classList.add(status);
        }
        
        // Update tooltip
        const titles = {
            'idle': 'Сохранено',
            'saving': 'Сохранение...',
            'saved': 'Сохранено',
            'error': 'Ошибка сохранения'
        };
        indicator.title = titles[status] || titles['idle'];
    }

    // Handle focus on notepad line - highlight corresponding polygon
    onNotepadLineFocus(e, index) {
        this.notepadFocusedIndex = index;

        // Update visual focus
        const lines = document.querySelectorAll('.notepad-line');
        lines.forEach(line => line.classList.remove('focused'));
        e.target.closest('.notepad-line').classList.add('focused');

        // Highlight polygon on left canvas
        this.highlightPolygonOnCanvas(index, true);

        // Center polygon on canvas (scroll into view)
        this.centerPolygonOnCanvas(index);
    }

    // Handle blur on notepad line
    onNotepadLineBlur(index) {
        this.notepadFocusedIndex = -1;
        // Remove highlight from polygon
        this.highlightPolygonOnCanvas(index, false);
    }

    // Highlight polygon on both canvases
    highlightPolygonOnCanvas(index, highlight) {
        const leftPoly = this.leftCanvas.getObjects().find(obj => obj.index === index);
        const rightPoly = this.rightCanvas.getObjects().find(obj => obj.index === index);

        if (leftPoly) {
            if (highlight) {
                leftPoly.set({
                    fill: 'rgba(255, 165, 0, 0.5)',
                    stroke: '#ff8800',
                    strokeWidth: 3
                });
            } else {
                // Restore original color based on whether it has text
                const hasText = this.texts[index] && this.texts[index].trim() !== '';
                leftPoly.set({
                    fill: hasText ? 'rgba(0, 128, 0, 0.3)' : 'rgba(0, 255, 0, 0.2)',
                    stroke: hasText ? '#00cc66' : 'green',
                    strokeWidth: 2
                });
            }
            this.leftCanvas.requestRenderAll();
        }

        if (rightPoly) {
            if (highlight) {
                rightPoly.set({
                    fill: 'rgba(255, 165, 0, 0.5)',
                    stroke: '#ff8800',
                    strokeWidth: 3
                });
            } else {
                const hasText = this.texts[index] && this.texts[index].trim() !== '';
                rightPoly.set({
                    fill: hasText ? 'rgba(255, 255, 255, 1.0)' : 'rgba(0, 0, 255, 0.2)',
                    stroke: hasText ? '#0066ff' : 'blue',
                    strokeWidth: 2
                });
            }
            this.rightCanvas.requestRenderAll();
        }
    }

    // Center polygon on canvas
    centerPolygonOnCanvas(index) {
        const region = this.regions[index];
        if (!region || !region.points) return;

        // Calculate center of polygon
        const xs = region.points.map(p => p.x);
        const ys = region.points.map(p => p.y);
        const centerX = (Math.min(...xs) + Math.max(...xs)) / 2;
        const centerY = (Math.min(...ys) + Math.max(...ys)) / 2;

        // Center on left canvas
        const leftVpt = this.leftCanvas.viewportTransform;
        const leftCanvasWidth = this.leftCanvas.getWidth() / leftVpt[0];
        const leftCanvasHeight = this.leftCanvas.getHeight() / leftVpt[3];

        leftVpt[4] = (leftCanvasWidth / 2) * leftVpt[0] - centerX * leftVpt[0];
        leftVpt[5] = (leftCanvasHeight / 2) * leftVpt[3] - centerY * leftVpt[3];
        this.leftCanvas.setViewportTransform(leftVpt);

        // Center on right canvas
        const rightVpt = this.rightCanvas.viewportTransform;
        const rightCanvasWidth = this.rightCanvas.getWidth() / rightVpt[0];
        const rightCanvasHeight = this.rightCanvas.getHeight() / rightVpt[3];

        rightVpt[4] = (rightCanvasWidth / 2) * rightVpt[0] - centerX * rightVpt[0];
        rightVpt[5] = (rightCanvasHeight / 2) * rightVpt[3] - centerY * rightVpt[3];
        this.rightCanvas.setViewportTransform(rightVpt);
    }

    // Handle keydown in notepad input
    onNotepadKeyDown(e, index) {
        if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey) {
            e.preventDefault();
            this.handleNotepadEnter(index);
        } else if (e.key === 'Backspace' && !e.shiftKey && !e.ctrlKey && !e.altKey) {
            // Handle Backspace at beginning of input
            const input = e.target;
            if (input.selectionStart === 0 && input.selectionEnd === 0) {
                e.preventDefault();
                this.handleNotepadBackspace(index);
            }
        }
    }

    // Handle Enter key - move text after cursor to next line
    handleNotepadEnter(index) {
        // Save state before making changes
        this.saveToHistory();

        const input = document.querySelector(`.notepad-line input[data-index="${index}"]`);
        if (!input) return;

        const cursorPos = input.selectionStart;
        const text = input.value;

        // Text before cursor stays, text after cursor moves to next line
        const textBeforeCursor = text.substring(0, cursorPos);
        const textAfterCursor = text.substring(cursorPos);

        // Check if there's a next line
        if (index >= this.regions.length - 1) {
            this.showNotification('Нет свободного сегмента для переноса текста', 'error');
            return;
        }

        // Update current line
        this.texts[index] = textBeforeCursor;

        // Get next line input
        const nextInput = document.querySelector(`.notepad-line input[data-index="${index + 1}"]`);
        if (nextInput) {
            // Prepend text to next line
            const nextText = this.texts[index + 1] || '';
            this.texts[index + 1] = textAfterCursor + nextText;

            // Update UI
            input.value = textBeforeCursor;
            nextInput.value = this.texts[index + 1];

            // Update line styles
            const currentLine = input.closest('.notepad-line');
            const nextLine = nextInput.closest('.notepad-line');
            if (!textBeforeCursor) currentLine.classList.remove('has-text');
            else currentLine.classList.add('has-text');
            nextLine.classList.add('has-text');

            // Move focus to next line with cursor at the beginning
            nextInput.focus();
            nextInput.setSelectionRange(0, 0);
            
            // Auto-save after text change
            this.autoSave();
        }
    }

    // Handle Backspace at beginning - merge with previous line
    handleNotepadBackspace(index) {
        // Save state before making changes
        this.saveToHistory();

        // Check if there's a previous line
        if (index <= 0) return; // Nothing to merge with

        const input = document.querySelector(`.notepad-line input[data-index="${index}"]`);
        if (!input) return;

        const currentText = input.value;

        // Get previous line input
        const prevInput = document.querySelector(`.notepad-line input[data-index="${index - 1}"]`);
        if (prevInput) {
            // Append current text to previous line
            const prevText = this.texts[index - 1] || '';
            this.texts[index - 1] = prevText + currentText;

            // Clear current line
            this.texts[index] = '';

            // Update UI
            prevInput.value = this.texts[index - 1];
            input.value = '';

            // Update line styles
            const prevLine = prevInput.closest('.notepad-line');
            const currentLine = input.closest('.notepad-line');
            prevLine.classList.add('has-text');
            currentLine.classList.remove('has-text');

            // Move focus to previous line
            prevInput.focus();
            prevInput.setSelectionRange(prevText.length, prevText.length);
            
            // Auto-save after text change
            this.autoSave();
        }
    }

    // Show notification
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    // Update notepad UI when regions change
    updateNotepadOnRegionsChange() {
        if (this.notepadMode) {
            this.renderNotepad();
        }
    }

    // Update all polygons with current text data (used when switching from notepad mode)
    updatePolygonsWithTexts() {
        this.regions.forEach((region, index) => {
            const textContent = this.texts[index] || '';

            // Update left canvas polygon
            const leftPoly = this.leftCanvas.getObjects().find(obj => obj.index === index);
            if (leftPoly) {
                leftPoly.set({ hasText: textContent !== '', textContent: textContent });
                if (textContent) {
                    leftPoly.set({ fill: 'rgba(0, 128, 0, 0.3)', stroke: '#00cc66' });
                } else {
                    leftPoly.set({ fill: 'rgba(0, 255, 0, 0.2)', stroke: 'green' });
                }
            }

            // Update right canvas polygon
            const rightPoly = this.rightCanvas.getObjects().find(obj => obj.index === index);
            if (rightPoly) {
                rightPoly.set({ hasText: textContent !== '', textContent: textContent });
                if (textContent) {
                    rightPoly.set({ fill: 'rgba(255, 255, 255, 1.0)', stroke: '#0066ff' });
                    this.updatePolygonText(rightPoly, textContent);
                } else {
                    rightPoly.set({ fill: 'rgba(0, 0, 255, 0.2)', stroke: 'blue' });
                    this.updatePolygonText(rightPoly, '');
                }
            }
        });

        this.leftCanvas.requestRenderAll();
        this.rightCanvas.requestRenderAll();
    }

    // ==================== END NOTEPAD MODE METHODS ====================

    setupCanvasEvents() {
        // Variables for panning — separate for each canvas to avoid conflicts
        let leftPanning = false;
        let leftLastPosX, leftLastPosY;
        let rightPanning = false;
        let rightLastPosX, rightLastPosY;

        // Left canvas events
        this.leftCanvas.on('mouse:down', (opt) => {
            if (opt.e.button === 0) { // Left click
                // Не обрабатываем клик при Space+drag (pan)
                if (typeof zoomCtrl !== 'undefined' && zoomCtrl.spaceHeld) return;
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
                leftPanning = true;
                leftLastPosX = opt.e.clientX;
                leftLastPosY = opt.e.clientY;
                this.leftCanvas.defaultCursor = 'grab';
                opt.e.preventDefault();
            }
        });

        this.leftCanvas.on('mouse:move', (opt) => {
            if (leftPanning) {
                const e = opt.e;
                const deltaX = e.clientX - leftLastPosX;
                const deltaY = e.clientY - leftLastPosY;

                // Pan the canvas
                const vpt = this.leftCanvas.viewportTransform;
                vpt[4] += deltaX; // tx
                vpt[5] += deltaY; // ty
                this.leftCanvas.requestRenderAll();

                // Sync right canvas in real-time
                this.syncViewports(this.leftCanvas, this.rightCanvas);

                leftLastPosX = e.clientX;
                leftLastPosY = e.clientY;
            }
        });

        this.leftCanvas.on('mouse:up', () => {
            leftPanning = false;
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
            const zoomFactor = delta > 0 ? 0.95 : 1.05; // Zoom out or in
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

            // Sync right canvas
            this.syncViewports(this.leftCanvas, this.rightCanvas);
        });

        // Right canvas events
        this.rightCanvas.on('mouse:down', (opt) => {
            if (opt.e.button === 0) { // Left click
                // Не обрабатываем клик при Space+drag (pan)
                if (typeof zoomCtrl !== 'undefined' && zoomCtrl.spaceHeld) return;
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
                rightPanning = true;
                rightLastPosX = opt.e.clientX;
                rightLastPosY = opt.e.clientY;
                this.rightCanvas.defaultCursor = 'grab';
                opt.e.preventDefault();
            }
        });

        this.rightCanvas.on('mouse:move', (opt) => {
            if (rightPanning) {
                const e = opt.e;
                const deltaX = e.clientX - rightLastPosX;
                const deltaY = e.clientY - rightLastPosY;

                // Pan the canvas
                const vpt = this.rightCanvas.viewportTransform;
                vpt[4] += deltaX; // tx
                vpt[5] += deltaY; // ty
                this.rightCanvas.requestRenderAll();

                // Sync left canvas in real-time
                this.syncViewports(this.rightCanvas, this.leftCanvas);

                rightLastPosX = e.clientX;
                rightLastPosY = e.clientY;
            }
        });

        this.rightCanvas.on('mouse:up', () => {
            rightPanning = false;
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
            const zoomFactor = delta > 0 ? 0.95 : 1.05; // Zoom out or in
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

            // Sync left canvas
            this.syncViewports(this.rightCanvas, this.leftCanvas);
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
            const projectParam = this.project ? `?project=${this.project}` : '';
            imgElement.src = `/data/images/${this.filename}?t=${new Date().getTime()}${projectParam}`;
            return;
        }

        // If cached image is not available or not loaded yet, load it first
        if (!this.cachedPreviewImage || !this.cachedPreviewImage.complete) {
            // Create and cache the image
            this.cachedPreviewImage = new Image();
            this.cachedPreviewImage.crossOrigin = 'Anonymous';
            this.cachedPreviewImage.onload = () => {
                // Re-call after image is loaded (will use cached image this time)
                this.extractRegionImage(regionIndex, imgElement);
            };
            const projectParam = this.project ? `?project=${this.project}` : '';
            this.cachedPreviewImage.src = `/data/images/${this.filename}?t=${new Date().getTime()}${projectParam}`;

            // Show placeholder while loading
            imgElement.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
            return;
        }

        // Use cached image (guaranteed to be loaded)
        const img = this.cachedPreviewImage;

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
    }

    closeModal() {
        // Сохраняем текст перед закрытием
        this.saveCurrentText();

        const modal = document.getElementById('text-modal');
        modal.style.display = 'none';
        this.currentRegionIndex = -1;

        // Clear history timeout to prevent saving after close
        if (this.saveHistoryTimeout) {
            clearTimeout(this.saveHistoryTimeout);
            this.saveHistoryTimeout = null;
        }

        // Remove the event listener that was added when opening the modal
        if (this.modalClickHandler) {
            document.removeEventListener('click', this.modalClickHandler, true);
            this.modalClickHandler = null;
        }
    }

    applyFormat(formatType) {
        const textInput = document.getElementById('text-input');
        const start = textInput.selectionStart;
        const end = textInput.selectionEnd;
        const text = textInput.value;

        if (formatType === 'strong') {
            // Strong strikethrough: [текст]
            if (start === end) {
                // No selection - insert template with cursor inside
                textInput.value = text.substring(0, start) + '[]' + text.substring(end);
                textInput.setSelectionRange(start + 1, start + 1); // Cursor inside brackets
            } else {
                // Wrap selected text
                const selectedText = text.substring(start, end);
                textInput.value = text.substring(0, start) + `[${selectedText}]` + text.substring(end);
                const newCursorPos = start + selectedText.length + 2;
                textInput.setSelectionRange(newCursorPos, newCursorPos);
            }
        } else if (formatType === 'weak') {
            // Weak strikethrough: ~текст~
            if (start === end) {
                // No selection - do nothing for weak format
                return;
            }
            const selectedText = text.substring(start, end);
            textInput.value = text.substring(0, start) + `~${selectedText}~` + text.substring(end);
            const newCursorPos = start + selectedText.length + 2;
            textInput.setSelectionRange(newCursorPos, newCursorPos);
        }

        textInput.focus();
    }

    saveTextAndNext() {
        // nextRegion() уже вызывает saveCurrentText()
        this.nextRegion();
    }

    nextRegion() {
        if (this.regions.length === 0) return;

        this.saveCurrentText();
        this.currentRegionIndex = (this.currentRegionIndex + 1) % this.regions.length;
        this.openTextModal(this.currentRegionIndex);
    }

    previousRegion() {
        if (this.regions.length === 0) return;

        this.saveCurrentText();
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
        const modal = document.getElementById('text-modal');
        const isModalOpen = modal && modal.style.display === 'flex';
        const textInput = document.getElementById('text-input');
        const isTextInputFocused = textInput && document.activeElement === textInput;

        // Notepad mode: Ctrl+Z for undo
        if (this.notepadMode && (e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
            e.preventDefault();
            this.undo();
            return;
        }

        // Handle Enter key to save and go to next region (only when modal is open)
        if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey && !e.altKey && isModalOpen) {
            e.preventDefault();
            this.saveTextAndNext();
        }
        // Handle Ctrl+Enter to save and stay on the same region
        else if (e.key === 'Enter' && e.ctrlKey && isModalOpen) {
            e.preventDefault();
            this.saveCurrentText();
        }
        // Handle Escape key to close modal
        else if (e.key === 'Escape' && isModalOpen) {
            this.closeModal();
        }
        // Handle Ctrl+Left/Right for region navigation (when modal is open)
        else if (e.ctrlKey && e.key === 'ArrowLeft' && isModalOpen) {
            e.preventDefault();
            this.previousRegion();
        }
        else if (e.ctrlKey && e.key === 'ArrowRight' && isModalOpen) {
            e.preventDefault();
            this.nextRegion();
        }
        // Handle Ctrl+S for saving
        else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            this.saveData();
        }
        // Handle Ctrl+Left/Right for image navigation (when not in modal)
        else if (e.ctrlKey && e.key === 'ArrowLeft' && !isModalOpen) {
            e.preventDefault();
            this.goImage(-1);
        }
        else if (e.ctrlKey && e.key === 'ArrowRight' && !isModalOpen) {
            e.preventDefault();
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

    async goImage(dir) {
        // Если уже идёт переключение - игнорируем запрос
        if (this.isSwitching) {
            return;
        }

        // Проверяем, открыта ли модалка - если да, закрываем (saveCurrentText вызовется внутри closeModal)
        const modal = document.getElementById('text-modal');
        if (modal && modal.style.display === 'flex') {
            this.closeModal();
        }

        this.isSwitching = true;

        try {
            if (this.autoSaveTimeout) {
                clearTimeout(this.autoSaveTimeout);
                await this.saveData(); // Сохраняем введенный текст немедленно и ЖДЁМ завершения
            }

            const idx = this.imageList.indexOf(this.filename);
            if (idx === -1) return;

            // Вычисляем новое имя файла
            const newFilename = this.imageList[(idx + dir + this.imageList.length) % this.imageList.length];

            // 1. Обновляем переменную класса
            this.filename = newFilename;

            // 1.5. Очищаем кэш превью (новое изображение загрузится в loadImageAndData)
            this.cachedPreviewImage = null;

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

            // 5. Очищаем старые данные перед загрузкой новых
            this.regions = [];
            this.texts = {};
            this.textsHistory = [];
            this.historyIndex = -1;
            this.notepadFocusedIndex = -1;
            
            // Clear history timeout to prevent saving after switch
            if (this.saveHistoryTimeout) {
                clearTimeout(this.saveHistoryTimeout);
                this.saveHistoryTimeout = null;
            }

            // 6. Загружаем новые данные
            this.loadImageAndData();
        } finally {
            this.isSwitching = false;
        }
    }

    async saveData() {
        // Если уже идёт сохранение или переключение - пропускаем
        if (this.isSaving || this.isSwitching) {
            console.log('[saveData] Skipped - isSaving:', this.isSaving, 'isSwitching:', this.isSwitching);
            // Don't change indicator - keep showing 'saving'
            return;
        }

        this.isSaving = true;
        
        console.log('[saveData] Saving...', this.filename, 'texts:', Object.keys(this.texts).length);

        try {
            // Prepare data to save - we need to map the texts back to the original region order
            // Get the original regions to create the mapping
            const originalData = await API.loadAnnotation(this.filename, this.project);
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
                status: 'recognized' // Status for text recognition completed
            };

            await API.saveAnnotationWithTexts(this.filename, saveData.regions, saveData.texts, this.project);

            // Show saved indicator
            this.setSaveIndicator('saved');
            console.log('[saveData] Saved successfully');
            
            // Reset to idle after 2 seconds
            setTimeout(() => this.setSaveIndicator('idle'), 2000);
        } catch (error) {
            console.error('[saveData] Error:', error);
            this.setSaveIndicator('error');
            
            // Reset to idle after 3 seconds
            setTimeout(() => this.setSaveIndicator('idle'), 3000);
        } finally {
            this.isSaving = false;
        }
    }

    // Auto-save functionality
    autoSave() {
        // Save data automatically after a delay to avoid excessive requests
        if (this.autoSaveTimeout) {
            clearTimeout(this.autoSaveTimeout);
        }

        // Show saving indicator immediately
        this.setSaveIndicator('saving');

        this.autoSaveTimeout = setTimeout(() => {
            this.saveData();
        }, 2000); // Auto-save after 2 seconds of inactivity
    }

    async recognizeText() {
        const btn = document.getElementById('btn-recognize');
        if (!btn) return;

        // Сохраняем оригинальный текст кнопки
        const originalText = btn.textContent;
        
        // Блокируем кнопку и показываем прогресс
        btn.disabled = true;
        btn.textContent = 'Распознавание... (0%)';

        try {
            // Get the original unsorted regions to send to the backend
            const originalData = await API.loadAnnotation(this.filename, this.project);
            const originalRegions = originalData.regions || [];

            const response = await fetch('/api/recognize_text', {
                method: 'POST',
                headers: API.getCsrfHeaders(),
                body: JSON.stringify({
                    image_name: this.filename,
                    regions: originalRegions,
                    project: this.project
                })
            });

            const data = await response.json();

            if (data.status === 'success') {
                // Poll for completion with progress updates
                this.pollForRecognitionResults(btn, originalText);
            } else {
                console.error('Recognition error:', data.msg);
                btn.disabled = false;
                btn.textContent = originalText;
            }
        } catch (error) {
            console.error('Recognition API error:', error);
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }

    pollForRecognitionResults(btn, originalText) {
        // Check recognition progress using the new endpoint
        const checkStatus = async () => {
            try {
                const progressData = await fetch(`/api/recognize_progress/${encodeURIComponent(this.filename)}`);
                const progress = await progressData.json();

                if (progress.status === 'completed') {
                    // Recognition complete, update UI
                    btn.textContent = '✓ Распознано';
                    
                    // Update the local texts data
                    const data = await API.loadAnnotation(this.filename, this.project);
                    // Load the text data with the original regions to map correctly to sorted order
                    const originalData = await API.loadAnnotation(this.filename, this.project);
                    const originalRegions = originalData.regions || [];
                    this.loadTextData(originalRegions);

                    // Auto-save after recognition is complete
                    this.autoSave();
                    
                    // Разблокируем кнопку через 2 секунды
                    setTimeout(() => {
                        btn.disabled = false;
                        btn.textContent = originalText;
                    }, 2000);
                } else {
                    // Update progress indicator
                    btn.textContent = `Распознавание... (${progress.percentage}%)`;

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
        // Use saveAnnotationWithTexts with project support
        // Note: 'this' refers to the TextEditor instance when called as API.saveAnnotation
        // We need to get project from the TextEditor instance
        const project = window.textEditor ? window.textEditor.project : null;
        return await API.saveAnnotationWithTexts(filename, regions, texts, project);
    };
}