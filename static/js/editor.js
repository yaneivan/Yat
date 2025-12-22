/**
 * Класс для управления Историей (Undo/Redo)
 * Изолирует логику сохранения состояний и предотвращает зацикливание.
 */
class HistoryManager {
    constructor(canvas, onHistoryChange) {
        this.canvas = canvas;
        this.onHistoryChange = onHistoryChange; // callback для сохранения на сервер
        
        this.undoStack = [];
        this.redoStack = [];
        this.locked = false; // Блокировка во время загрузки состояния
        this.maxHistory = 50;
    }

    /**
     * Сохраняет текущее состояние. Вызывать ПЕРЕД или ПОСЛЕ изменения.
     * В Fabric обычно удобнее сохранять после modification.
     */
    save() {
        if (this.locked) return;

        // Если мы сделали новое действие, ветка Redo теряется
        if (this.redoStack.length > 0) {
            this.redoStack = [];
        }

        const json = this.canvas.toObject(['class', 'selectable', 'evented']);
        
        // Лимит стека
        if (this.undoStack.length >= this.maxHistory) this.undoStack.shift();
        
        this.undoStack.push(JSON.stringify(json));
    }

    undo() {
        if (this.undoStack.length <= 1 || this.locked) return; // Нужно хотя бы 2 состояния (начальное + 1)

        this.locked = true;

        // 1. Текущее состояние переносим в Redo
        const current = this.undoStack.pop();
        this.redoStack.push(current);

        // 2. Достаем предыдущее состояние
        const prev = this.undoStack[this.undoStack.length - 1];

        this._loadState(prev);
    }

    redo() {
        if (this.redoStack.length === 0 || this.locked) return;

        this.locked = true;

        // 1. Достаем состояние из Redo
        const next = this.redoStack.pop();
        
        // 2. Возвращаем его в Undo
        this.undoStack.push(next);

        this._loadState(next);
    }

    reset() {
        this.undoStack = [];
        this.redoStack = [];
        this.save(); // Сохраняем начальное "пустое" состояние
    }

    _loadState(jsonState) {
        this.canvas.loadFromJSON(jsonState, () => {
            // Восстанавливаем настройки объектов, которые не сохраняются в JSON
            this.canvas.getObjects().forEach(obj => {
                if (obj.type === 'polygon') {
                    obj.set({
                        objectCaching: false, 
                        transparentCorners: false, 
                        cornerColor: 'blue', 
                        strokeWidth: 2
                    });
                }
            });
            
            this.canvas.requestRenderAll();
            this.locked = false;
            
            // Сообщаем редактору, что данные изменились (обновить UI и автосейв)
            if (this.onHistoryChange) this.onHistoryChange();
        });
    }
}


/**
 * Основной класс редактора
 */
class HTREditor {
    constructor(canvasId, filename, snapDist = 15) {
        this.filename = filename;
        this.snapDist = snapDist;
        this.canvas = new fabric.Canvas(canvasId, {
            fireRightClick: true, 
            stopContextMenu: true, 
            preserveObjectStacking: true,
            uniformScaling: false, 
            selection: true, 
            backgroundColor: "#151515"
        });
        
        // State
        this.currentMode = null; 
        this.drawPoints = [];
        this.activeLine = null;
        this.editPointsMode = false;
        this.imageList = [];
        this.autoSaveTimer = null;

        // Sub-modules
        this.history = new HistoryManager(this.canvas, () => {
            this.updateSelectionUI();
            this.triggerAutoSave();
        });

        this.init();
    }

    async init() {
        this.imageList = await API.listImages();
        this.resize();
        window.addEventListener('resize', () => this.resize());
        
        // SPA Back button handler
        window.addEventListener('popstate', (event) => {
            if (event.state && event.state.filename) {
                this.filename = event.state.filename;
                this.loadImageAndData();
            }
        });

        this.setupInputHandlers();
        this.setupCanvasEvents();
        await this.loadImageAndData();
    }

    resize() {
        const el = document.getElementById('workspace');
        this.canvas.setWidth(el.clientWidth);
        this.canvas.setHeight(el.clientHeight);
    }

    // --- Loading Logic ---

    async loadImageAndData() {
        // UI Update
        const infoSpan = document.querySelector('.file-info');
        if (infoSpan) infoSpan.textContent = this.filename;

        // Canvas Reset
        this.canvas.clear();
        this.canvas.setBackgroundColor("#151515", this.canvas.renderAll.bind(this.canvas));
        
        // 1. Load Image
        fabric.Image.fromURL(`/data/images/${this.filename}`, img => {
            this.canvas.setBackgroundImage(img, this.canvas.renderAll.bind(this.canvas));
            
            const scale = (this.canvas.width / img.width) * 0.9;
            this.canvas.setZoom(scale);
            
            const newW = img.width * scale;
            this.canvas.viewportTransform[4] = (this.canvas.width - newW) / 2;
            this.canvas.viewportTransform[5] = 20;

            this.setMode('edit');
            
            // Инициализируем историю (начальное состояние)
            this.history.reset();
            
            this.preloadNeighbors();
        });

        // 2. Load Data
        const data = await API.loadAnnotation(this.filename);
        if (data.regions) {
            data.regions.forEach(r => {
                const p = new fabric.Polygon(r.points, {
                    fill: 'rgba(0, 255, 0, 0.2)', stroke: 'green', strokeWidth: 2,
                    objectCaching: false, transparentCorners: false, cornerColor: 'blue',
                    selectable: true, evented: true
                });
                this.canvas.add(p);
            });
            // Сохраняем состояние после загрузки полигонов
            this.history.save(); 
        }
    }

    preloadNeighbors() {
        const idx = this.imageList.indexOf(this.filename);
        if (idx === -1) return;
        const indices = [(idx + 1) % this.imageList.length, (idx - 1 + this.imageList.length) % this.imageList.length];
        indices.forEach(i => {
            const fname = this.imageList[i];
            new Image().src = `/data/images/${fname}`;
            fetch(`/api/load/${fname}`); 
        });
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

    // --- Modes ---

    setMode(mode) {
        this.currentMode = mode;
        this.editPointsMode = false;
        
        document.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
        if (mode === 'edit') document.getElementById('btn-edit')?.classList.add('active');
        if (mode === 'draw') document.getElementById('btn-draw')?.classList.add('active');
        
        this.updateSelectionUI();

        if (mode === 'draw') {
            this.canvas.discardActiveObject();
            this.canvas.selection = false;
            this.canvas.defaultCursor = 'crosshair';
            this.canvas.forEachObject(o => { o.selectable = false; o.evented = false; });
        } else if (mode === 'edit') {
            this.abortDrawing();
            this.canvas.selection = true;
            this.canvas.defaultCursor = 'default';
            this.canvas.forEachObject(o => { o.selectable = true; o.evented = true; });
        }
        this.canvas.requestRenderAll();
    }

    // --- Drawing Tool ---

    handleDrawClick(pointer) {
        if (this.drawPoints.length > 2) {
            const p0 = this.drawPoints[0];
            const dist = Math.hypot(p0.x - pointer.x, p0.y - pointer.y) * this.canvas.getZoom();
            if (dist < this.snapDist) {
                this.finishPolygon();
                return;
            }
        }
        
        this.drawPoints.push({x: pointer.x, y: pointer.y});
        this._renderDrawHelpers(pointer);
    }

    _renderDrawHelpers(pointer) {
        const circle = new fabric.Circle({
            radius: 3 / this.canvas.getZoom(), fill: this.drawPoints.length===1?'#00ff00':'red',
            left: pointer.x, top: pointer.y, originX:'center', originY:'center',
            selectable:false, evented:false, class:'temp'
        });
        this.canvas.add(circle);
        
        if (this.drawPoints.length > 1) {
            const p1 = this.drawPoints[this.drawPoints.length-2];
            const p2 = this.drawPoints[this.drawPoints.length-1];
            const line = new fabric.Line([p1.x, p1.y, p2.x, p2.y], {
                stroke:'red', strokeWidth: 2/this.canvas.getZoom(), selectable:false, evented:false, class:'temp'
            });
            this.canvas.add(line);
        }
    }

    finishPolygon() {
        if (this.drawPoints.length < 3) return;
        const finalPoints = this.drawPoints.map(p=>({x:p.x, y:p.y}));
        this.abortDrawing();
        const poly = new fabric.Polygon(finalPoints, {
            fill: 'rgba(0, 255, 0, 0.2)', stroke: 'green', strokeWidth: 2/this.canvas.getZoom(),
            objectCaching: false, transparentCorners: false, cornerColor: 'blue',
            selectable: false, evented: false
        });
        this.canvas.add(poly);
        this.canvas.requestRenderAll();
        // При добавлении сработает object:added -> history.save
    }

    abortDrawing() {
        const objs = this.canvas.getObjects();
        for (let i = objs.length - 1; i >= 0; i--) {
            if (objs[i].class === 'temp') this.canvas.remove(objs[i]);
        }
        if (this.activeLine) { this.canvas.remove(this.activeLine); this.activeLine = null; }
        this.drawPoints = [];
        this.canvas.requestRenderAll();
    }

    // --- Edit Tool (Points) ---

    toggleEditPoints() {
        const poly = this.canvas.getActiveObject();
        if (!poly || poly.type !== 'polygon' || poly._objects) return;

        this.editPointsMode = !this.editPointsMode;
        
        if (this.editPointsMode) {
            poly.controls = poly.points.reduce((acc, point, index) => {
                acc['p' + index] = new fabric.Control({
                    positionHandler: (dim, finalMatrix, fabricObject) => {
                        const x = (fabricObject.points[index].x - fabricObject.pathOffset.x);
                        const y = (fabricObject.points[index].y - fabricObject.pathOffset.y);
                        return fabric.util.transformPoint({ x, y }, 
                            fabric.util.multiplyTransformMatrices(fabricObject.canvas.viewportTransform, fabricObject.calcTransformMatrix())
                        );
                    },
                    actionHandler: (eventData, transform, x, y) => {
                        const polygon = transform.target;
                        const mouseLocal = polygon.toLocalPoint(new fabric.Point(x, y), 'center', 'center');
                        const polygonBaseSize = polygon._getNonTransformedDimensions();
                        const size = polygon._getTransformedDimensions(0, 0);
                        polygon.points[index] = {
                            x: mouseLocal.x * polygonBaseSize.x / size.x + polygon.pathOffset.x,
                            y: mouseLocal.y * polygonBaseSize.y / size.y + polygon.pathOffset.y
                        };
                        return true;
                    },
                    actionName: 'modifyPolygon', cursorStyle: 'crosshair',
                    render: (ctx, left, top) => {
                        ctx.save(); ctx.translate(left, top); ctx.fillStyle = '#ff00ff';
                        ctx.beginPath(); ctx.arc(0, 0, 5, 0, Math.PI * 2); ctx.fill(); ctx.restore();
                    }
                });
                return acc;
            }, {});
            poly.hasBorders = false;
        } else {
            poly.controls = fabric.Object.prototype.controls;
            poly.hasBorders = true;
        }
        this.canvas.requestRenderAll();
        this.updateSelectionUI();
    }

    // --- Event Listeners ---

    setupCanvasEvents() {
        let isPanning = false;
        let lastMouse = {x:0, y:0};

        this.canvas.on('mouse:down', (opt) => {
            const evt = opt.e;
            if (evt.button === 2 || evt.altKey) {
                isPanning = true;
                this.canvas.selection = false;
                lastMouse = { x: evt.clientX, y: evt.clientY };
                this.canvas.defaultCursor = 'grab';
                return;
            }
            if (this.currentMode === 'draw' && evt.button === 0) {
                this.handleDrawClick(this.canvas.getPointer(evt));
            }
        });

        this.canvas.on('mouse:move', (opt) => {
            if (isPanning) {
                const e = opt.e;
                this.canvas.relativePan(new fabric.Point(e.clientX - lastMouse.x, e.clientY - lastMouse.y));
                lastMouse = { x: e.clientX, y: e.clientY };
                return;
            }

            if (this.currentMode === 'draw') {
                const pointer = this.canvas.getPointer(opt.e);
                // Rubberband
                if (this.drawPoints.length > 0) {
                    if (!this.activeLine) {
                        this.activeLine = new fabric.Line([this.drawPoints[this.drawPoints.length-1].x, this.drawPoints[this.drawPoints.length-1].y, pointer.x, pointer.y], {
                            stroke:'red', strokeWidth: 2/this.canvas.getZoom(), selectable:false, evented:false, opacity:0.8, class:'temp'
                        });
                        this.canvas.add(this.activeLine);
                    } else {
                        this.activeLine.set({ x1: this.drawPoints[this.drawPoints.length-1].x, y1: this.drawPoints[this.drawPoints.length-1].y, x2: pointer.x, y2: pointer.y, strokeWidth: 2/this.canvas.getZoom() });
                    }
                    this.canvas.requestRenderAll();
                }
                // Cursor snap
                if (this.drawPoints.length > 2) {
                    const p0 = this.drawPoints[0];
                    const dist = Math.hypot(p0.x - pointer.x, p0.y - pointer.y) * this.canvas.getZoom();
                    this.canvas.defaultCursor = dist < this.snapDist ? 'copy' : 'crosshair';
                }
            }
        });

        this.canvas.on('mouse:up', () => {
            if (isPanning) {
                isPanning = false;
                this.canvas.setViewportTransform(this.canvas.viewportTransform);
                this.canvas.getObjects().forEach(o => o.setCoords());
            }
            if (this.currentMode === 'edit') {
                this.canvas.defaultCursor = 'default';
                this.canvas.selection = true;
            }
        });

        this.canvas.on('mouse:wheel', (opt) => {
            let zoom = this.canvas.getZoom();
            zoom *= 0.999 ** opt.e.deltaY;
            if (zoom > 20) zoom = 20;
            if (zoom < 0.01) zoom = 0.01;
            this.canvas.zoomToPoint({ x: opt.e.offsetX, y: opt.e.offsetY }, zoom);
            opt.e.preventDefault();
            opt.e.stopPropagation();
        });

        // UI Updates
        const updateUI = () => this.updateSelectionUI();
        this.canvas.on('selection:created', updateUI);
        this.canvas.on('selection:updated', updateUI);
        this.canvas.on('selection:cleared', updateUI);
        
        // History Hooks
        // Сохраняем ТОЛЬКО постоянные объекты (фильтруем temp/class)
        const onObjectChanged = (e) => {
            if(!e.target.class && e.target.type==='polygon') {
                this.history.save();
                this.triggerAutoSave();
            }
        };
        this.canvas.on('object:modified', onObjectChanged);
        this.canvas.on('object:added', onObjectChanged);
        this.canvas.on('object:removed', onObjectChanged);
    }

    setupInputHandlers() {
        document.addEventListener('keydown', (e) => {
            // Shortcuts
            const isCtrl = e.ctrlKey || e.metaKey;
            const key = e.key.toLowerCase();

            // Undo: Ctrl+Z
            // Redo: Ctrl+Shift+Z или Ctrl+Y (стандарт) или Ctrl+Shift+Я
            if (isCtrl) {
                if (e.shiftKey && (key === 'z' || key === 'я')) {
                    e.preventDefault();
                    this.history.redo();
                    return;
                }
                if (key === 'z' || key === 'я') {
                    e.preventDefault();
                    this.history.undo();
                    return;
                }
                if (key === 'a' || key === 'ф') { // Select All
                    e.preventDefault();
                    if (this.currentMode === 'edit') this.selectAll();
                    return;
                }
                if (e.key === 'ArrowRight') this.goImage(1);
                if (e.key === 'ArrowLeft') this.goImage(-1);
            }

            if (e.key === 'Delete') this.deleteSelected();
            if (key === 'n' || key === 'т') this.setMode('draw');
            if (key === 'v' || key === 'м') this.setMode('edit');
            if (key === 'p' || key === 'з') this.toggleEditPoints();
            if (e.key === 'Escape') {
                if (this.currentMode === 'draw' && this.drawPoints.length > 0) this.abortDrawing();
                else if (this.editPointsMode) this.toggleEditPoints();
                else if (this.currentMode === 'edit') { this.canvas.discardActiveObject(); this.canvas.requestRenderAll(); }
            }
        });
    }

    // --- Helpers ---

    updateSelectionUI() {
        const active = this.canvas.getActiveObject();
        const hasSelection = !!active;
        const isEdit = this.currentMode === 'edit';
        
        const btnPoints = document.getElementById('btn-edit-points');
        const btnDel = document.getElementById('btn-delete');
        if(!btnPoints || !btnDel) return;

        if (isEdit && hasSelection) {
            btnDel.classList.remove('disabled');
            if (active.type === 'polygon' && !active._objects) {
                btnPoints.classList.remove('disabled');
                btnPoints.classList.toggle('active', this.editPointsMode);
            } else {
                btnPoints.classList.add('disabled');
            }
        } else {
            btnPoints.classList.add('disabled');
            btnDel.classList.add('disabled');
            btnPoints.classList.remove('active');
            this.editPointsMode = false;
        }
    }

    selectAll() {
        const selectables = this.canvas.getObjects().filter(o => o.type === 'polygon' && !o.class);
        if (selectables.length) {
            this.canvas.discardActiveObject();
            const sel = new fabric.ActiveSelection(selectables, { canvas: this.canvas });
            this.canvas.setActiveObject(sel);
            this.canvas.requestRenderAll();
        }
    }

    deleteSelected() {
        const a = this.canvas.getActiveObjects();
        if(a.length) { 
            this.canvas.discardActiveObject(); 
            a.forEach(o => this.canvas.remove(o)); 
        }
    }

    triggerAutoSave() {
        const el = document.getElementById('status');
        if(el) el.textContent = 'Сохранение...';
        clearTimeout(this.autoSaveTimer);
        this.autoSaveTimer = setTimeout(() => this.saveData(), 800);
    }

    async saveData() {
        const regions = [];
        this.canvas.getObjects().forEach(obj => {
            if (obj.type === 'polygon' && !obj.class) {
                const matrix = obj.calcTransformMatrix();
                const pts = obj.points.map(p => {
                    const pCenter = new fabric.Point(p.x - obj.pathOffset.x, p.y - obj.pathOffset.y);
                    return fabric.util.transformPoint(pCenter, matrix);
                });
                regions.push({ points: pts.map(p => ({ x: Math.round(p.x), y: Math.round(p.y) })) });
            }
        });
        
        try {
            await API.saveAnnotation(this.filename, regions);
            const el = document.getElementById('status');
            if(el) el.textContent = 'Сохранено';
        } catch(e) {
            console.error(e);
        }
    }
}