/**
 * History Manager Class
 */
class HistoryManager {
    constructor(canvas, onHistoryChange) {
        this.canvas = canvas;
        this.onHistoryChange = onHistoryChange;
        
        this.undoStack = [];
        this.redoStack = [];
        this.locked = false; 
        this.maxHistory = 50;
    }

    save() {
        if (this.locked) return;
        if (this.redoStack.length > 0) this.redoStack = [];

        const objects = this.canvas.getObjects().map(o => o.toObject(['class', 'selectable', 'evented']));
        
        if (this.undoStack.length >= this.maxHistory) this.undoStack.shift();
        this.undoStack.push(JSON.stringify(objects));
    }

    undo() {
        if (this.undoStack.length <= 1 || this.locked) return;
        this.locked = true;

        const current = this.undoStack.pop();
        this.redoStack.push(current);
        const prev = this.undoStack[this.undoStack.length - 1];

        this._loadObjects(prev);
    }

    redo() {
        if (this.redoStack.length === 0 || this.locked) return;
        this.locked = true;

        const next = this.redoStack.pop();
        this.undoStack.push(next);
        
        this._loadObjects(next);
    }

    reset() {
        this.undoStack = [];
        this.redoStack = [];
        this.save(); 
    }

    _loadObjects(jsonString) {
        const objectsData = JSON.parse(jsonString);
        // Используем HTREditor._configurePolygon для единообразия, но так как доступа нет, дублируем логику
        const configurePolygon = (obj) => {
             obj.set({
                objectCaching: false,
                transparentCorners: false,
                cornerColor: 'blue',
                strokeWidth: 2,
                perPixelTargetFind: true // ВАЖНО: Включаем точный клик
            });
        };

        const currentObjects = this.canvas.getObjects().filter(o => o.type === 'polygon'); 
        this.canvas.remove(...currentObjects);

        fabric.util.enlivenObjects(objectsData, (enlivenedObjects) => {
            enlivenedObjects.forEach((obj) => {
                if (obj.type === 'polygon') {
                    configurePolygon(obj);
                }
                this.canvas.add(obj);
            });
            
            this.canvas.requestRenderAll();
            this.locked = false;
            if (this.onHistoryChange) this.onHistoryChange();
        });
    }
}

/**
 * Editor Class
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
        
        this.currentMode = null; 
        this.drawPoints = [];
        this.activeLine = null;
        this.editPointsMode = false;
        this.imageList = [];
        this.autoSaveTimer = null;
        this.savedState = null; 

        this.history = new HistoryManager(this.canvas, () => {
            this.restoreSelectionState();
            this.updateSelectionUI();
            this.triggerAutoSave();
        });

        this.init();
    }

    async init() {
        this.imageList = await API.listImages();
        this.resize();
        window.addEventListener('resize', () => this.resize());
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.filename) {
                this.filename = e.state.filename;
                this.loadImageAndData();
            }
        });
        this.setupInputHandlers();
        this.setupCanvasEvents();
        await this.loadImageAndData();
    }

    resize() {
        const el = document.getElementById('workspace');
        if (el) {
            this.canvas.setWidth(el.clientWidth);
            this.canvas.setHeight(el.clientHeight);
            this.canvas.calcOffset(); 
        }
    }

    // Единая функция для настройки ВСЕХ полигонов
    _configurePolygon(obj) {
        obj.set({
            fill: 'rgba(0, 255, 0, 0.2)', 
            stroke: 'green', 
            strokeWidth: 2,
            objectCaching: false, 
            transparentCorners: false, 
            cornerColor: 'blue',
            selectable: true, 
            evented: true,
            // Включаем нативный точный поиск. Это решает проблему клика по "пустоте"
            perPixelTargetFind: true
        });
    }

    async loadImageAndData() {
        const infoSpan = document.querySelector('.file-info');
        if (infoSpan) infoSpan.textContent = this.filename;

        this.canvas.clear();
        this.canvas.setBackgroundColor("#151515", this.canvas.renderAll.bind(this.canvas));
        
        const timestamp = new Date().getTime();
        const imgUrl = `/data/images/${this.filename}?t=${timestamp}`;
        
        const imgEl = new Image();
        imgEl.onload = () => {
            const fabricImg = new fabric.Image(imgEl);
            
            this.canvas.setBackgroundImage(fabricImg, () => {
                const scale = (this.canvas.width / fabricImg.width) * 0.9;
                this.canvas.setZoom(scale);
                const newW = fabricImg.width * scale;
                this.canvas.viewportTransform[4] = (this.canvas.width - newW) / 2;
                this.canvas.viewportTransform[5] = 20;
                
                this.canvas.requestRenderAll(); 
                this.setMode('edit');
                this.history.reset();
                this.preloadNeighbors();
            });
        };
        imgEl.onerror = () => {
            alert("Image load error.");
        };
        imgEl.src = imgUrl;

        const data = await API.loadAnnotation(this.filename);
        if (data.regions) {
            data.regions.forEach(r => {
                const p = new fabric.Polygon(r.points);
                this._configurePolygon(p); // Применяем единые настройки
                this.canvas.add(p);
            });
            this.history.save(); 
        }
    }

    preloadNeighbors() {
        const idx = this.imageList.indexOf(this.filename);
        if (idx === -1) return;
        [(idx + 1) % this.imageList.length, (idx - 1 + this.imageList.length) % this.imageList.length].forEach(i => {
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

    captureSelectionState() {
        const active = this.canvas.getActiveObject();
        this.savedState = {
            index: active ? this.canvas.getObjects().indexOf(active) : -1,
            isEditPoints: this.editPointsMode
        };
    }

    restoreSelectionState() {
        if (!this.savedState || this.savedState.index === -1) {
            this.editPointsMode = false;
            return;
        }
        const objects = this.canvas.getObjects();
        if (this.savedState.index < objects.length) {
            const obj = objects[this.savedState.index];
            this.canvas.setActiveObject(obj);
            if (this.savedState.isEditPoints && obj.type === 'polygon') {
                this.editPointsMode = true;
                this.enablePolyEdit(obj);
            } else {
                this.editPointsMode = false;
            }
        }
        this.savedState = null;
    }

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

    handleDrawClick(pointer) {
        if (this.drawPoints.length > 2) {
            const p0 = this.drawPoints[0];
            const dist = Math.hypot(p0.x - pointer.x, p0.y - pointer.y) * this.canvas.getZoom();
            if (dist < this.snapDist) { this.finishPolygon(); return; }
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
        const poly = new fabric.Polygon(finalPoints);
        this._configurePolygon(poly); // Применяем единые настройки
        poly.set({ selectable: false, evented: false }); 
        this.canvas.add(poly);
        this.canvas.requestRenderAll();
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

    toggleEditPoints() {
        const poly = this.canvas.getActiveObject();
        if (!poly || poly.type !== 'polygon' || poly._objects) return;
        this.editPointsMode = !this.editPointsMode;
        if (this.editPointsMode) {
            this.enablePolyEdit(poly);
        } else {
            this.disablePolyEdit(poly);
        }
        this.canvas.requestRenderAll();
        this.updateSelectionUI();
    }

    enablePolyEdit(poly) {
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
    }

    disablePolyEdit(poly) {
        if(poly) {
            poly.controls = fabric.Object.prototype.controls;
            poly.hasBorders = true;
        }
    }
    
    setupCanvasEvents() {
        let isPanning = false;
        let lastMouse = {x:0, y:0};

        // --- ДВОЙНОЙ КЛИК: ЦИКЛИЧЕСКИЙ ВЫБОР СЛОЕВ (ПРОСТОЙ И РАБОЧИЙ) ---
        this.canvas.on('mouse:dblclick', (opt) => {
            if (this.currentMode !== 'edit' || !opt.target) return;

            const clickedObject = opt.target;
            if (clickedObject.type !== 'polygon') return;

            // Находим все объекты под курсором. Fabric уже сделал это за нас (opt.target),
            // но нам нужны и те, что лежат глубже.
            const targets = this.canvas.getObjects().filter(obj => {
                // Используем встроенный метод, т.к. perPixelTargetFind включен
                return obj.selectable && obj.visible && obj.containsPoint(opt.pointer);
            });

            if (targets.length < 2) return;

            // Ищем индекс текущего объекта в стеке (визуально он верхний)
            const topDownTargets = [...targets].reverse();
            const currentIndex = topDownTargets.indexOf(clickedObject);

            if (currentIndex === -1) return; // На всякий случай

            // Выбираем следующий
            const nextIndex = (currentIndex + 1) % topDownTargets.length;
            const nextObject = topDownTargets[nextIndex];

            this.canvas.setActiveObject(nextObject);
            this.canvas.requestRenderAll();
        });

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
                if (this.drawPoints.length > 0) {
                    if (!this.activeLine) {
                        this.activeLine = new fabric.Line([this.drawPoints[this.drawPoints.length-1].x, this.drawPoints[this.drawPoints.length-1].y, pointer.x, pointer.y], {
                            stroke:'red', strokeWidth: 2/this.canvas.getZoom(), selectable:false, evented:false, class:'temp'
                        });
                        this.canvas.add(this.activeLine);
                    } else {
                        this.activeLine.set({ x1: this.drawPoints[this.drawPoints.length-1].x, y1: this.drawPoints[this.drawPoints.length-1].y, x2: pointer.x, y2: pointer.y, strokeWidth: 2/this.canvas.getZoom() });
                    }
                    this.canvas.requestRenderAll();
                }
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

        const onSelectionChange = (e) => {
            if (e.deselected) {
                e.deselected.forEach(obj => this.disablePolyEdit(obj));
            }
            this.editPointsMode = false;
            this.updateSelectionUI();
        };

        this.canvas.on('selection:created', onSelectionChange);
        this.canvas.on('selection:updated', onSelectionChange);
        this.canvas.on('selection:cleared', (e) => {
            if (e.deselected) {
                e.deselected.forEach(obj => this.disablePolyEdit(obj));
            }
            this.editPointsMode = false;
            this.updateSelectionUI();
        });
        
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
            const isCtrl = e.ctrlKey || e.metaKey;
            const key = e.key.toLowerCase();
            const active = this.canvas.getActiveObject();

            if (isCtrl) {
                if (e.shiftKey && (key === 'z' || key === 'я')) {
                    e.preventDefault(); this.captureSelectionState(); this.history.redo(); return;
                }
                if (key === 'z' || key === 'я') {
                    e.preventDefault(); this.captureSelectionState(); this.history.undo(); return;
                }
                if (key === 'a' || key === 'ф') {
                    e.preventDefault(); if (this.currentMode === 'edit') this.selectAll(); return;
                }
                if (e.key === 'ArrowRight') this.goImage(1);
                if (e.key === 'ArrowLeft') this.goImage(-1);
                
                if (e.key === 'ArrowUp' && active && this.currentMode === 'edit') {
                    e.preventDefault(); active.bringForward(); this.history.save(); return;
                }
                if (e.key === 'ArrowDown' && active && this.currentMode === 'edit') {
                    e.preventDefault(); active.sendBackwards(); this.history.save(); return;
                }
            }

            if (e.key === 'PageUp' && active && this.currentMode === 'edit') {
                active.bringToFront(); this.history.save();
            }
            if (e.key === 'PageDown' && active && this.currentMode === 'edit') {
                active.sendToBack(); this.history.save();
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

    async detectTextLines() {
        const statusEl = document.getElementById('status');
        if (statusEl) statusEl.textContent = 'Обнаружение строк...';

        try {
            const response = await fetch('/api/detect_lines', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ image_name: this.filename })
            });

            const data = await response.json();

            if (data.status === 'success') {
                const existingPolygons = this.canvas.getObjects().filter(obj => obj.type === 'polygon' && !obj.class);
                this.canvas.remove(...existingPolygons);

                data.regions.forEach(region => {
                    if (region.points && region.points.length >= 3) {
                        const poly = new fabric.Polygon(region.points);
                        this._configurePolygon(poly); // Применяем единые настройки
                        this.canvas.add(poly);
                    }
                });

                this.canvas.requestRenderAll();

                this.history.save();
                this.triggerAutoSave();

                if (statusEl) statusEl.textContent = `Найдено ${data.regions.length} строк`;
            } else {
                if (statusEl) statusEl.textContent = 'Ошибка: ' + (data.msg || 'Неизвестная ошибка');
                console.error('Detection error:', data.msg);
            }
        } catch (error) {
            console.error('Detection API error:', error);
            if (statusEl) statusEl.textContent = 'Ошибка при обнаружении строк';
        }
    }
}