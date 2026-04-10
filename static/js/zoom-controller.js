/**
 * ZoomController — единый модуль зума и панорамирования для всех редакторов.
 *
 * Возможности:
 *  - Space + drag для пана (работает поверх существующего ПКМ/Alt pan)
 *  - Overlay с кнопками +/- и ползунком поверх canvas (как на картах)
 *  - Индикатор текущего зума (%) — относительно baseZoom (fit-to-screen)
 *  - Горячие клавиши: + / - / 0 (сброс к baseZoom)
 *
 * Использование:
 *   const zoomCtrl = new ZoomController(canvas, {
 *       wrapper: document.getElementById('workspace'),
 *       baseZoom: canvas.getZoom()  // масштаб "вместить в экран" = 100%
 *   });
 *   zoomCtrl.dispose()
 */
class ZoomController {
    constructor(fabricCanvas, options = {}) {
        this.canvas = fabricCanvas;
        this.syncCanvas = options.syncCanvas || null; // второй canvas для text_editor
        this.baseZoom = options.baseZoom ?? fabricCanvas.getZoom() ?? 1;
        this.minZoom = this.baseZoom * 0.4;
        this.maxZoom = this.baseZoom * 7;

        this.isPanning = false;
        this.spaceHeld = false;
        this.lastMouse = null;

        this._onKeyDownBound = this._onKeyDown.bind(this);
        this._onKeyUpBound = this._onKeyUp.bind(this);
        this._updatingSlider = false;

        this.wrapper = options.wrapper || null;

        this._attach();
    }

    /* ── Public ── */

    setBaseZoom(zoom) {
        this.baseZoom = zoom;
        this.minZoom = zoom * 0.4;
        this.maxZoom = zoom * 7;
        this._updateUI();
    }

    zoomIn() {
        this._zoomBy(1.3);
        this._syncCanvasZoom();
    }

    zoomOut() {
        this._zoomBy(1 / 1.3);
        this._syncCanvasZoom();
    }

    resetZoom() {
        // Зум к центру экрана с baseZoom
        const rect = this.canvas.getElement().getBoundingClientRect();
        this.canvas.zoomToPoint({ x: rect.width / 2, y: rect.height / 2 }, this.baseZoom);
        this._syncCanvasZoom();
        this._updateUI();
    }

    _syncCanvasZoom() {
        if (!this.syncCanvas) return;
        this.syncCanvas.setViewportTransform([...this.canvas.viewportTransform]);
        this.syncCanvas.requestRenderAll();
    }

    dispose() {
        document.removeEventListener('keydown', this._onKeyDownBound);
        document.removeEventListener('keyup', this._onKeyUpBound);
        this._unbindMousePan();
        this._removeOverlay();
        if (this._secondaryUnbind) this._secondaryUnbind();
    }

    /**
     * Включить Space+drag на дополнительном canvas (для правого холста text_editor).
     * Когда юзер жмёт Space и тащит на этом canvas, pan идёт от него,
     * а syncCanvas (left) синхронизируется.
     */
    enableSecondaryPan(secondaryCanvas, syncTarget) {
        if (!secondaryCanvas) return;
        const self = this;
        let isPanning = false;
        let lastMouse = null;

        function onDown(opt) {
            if (!self.spaceHeld) return;
            if (opt.e.button !== 0) return;
            isPanning = true;
            secondaryCanvas.selection = false;
            lastMouse = { x: opt.e.clientX, y: opt.e.clientY };
            secondaryCanvas.defaultCursor = 'grabbing';
            secondaryCanvas.upperCanvasEl.style.cursor = 'grabbing';
        }

        function onMove(opt) {
            if (!isPanning) return;
            const dx = opt.e.clientX - lastMouse.x;
            const dy = opt.e.clientY - lastMouse.y;
            secondaryCanvas.relativePan(new fabric.Point(dx, dy));
            // Sync to the other canvas
            if (syncTarget) {
                syncTarget.setViewportTransform([...secondaryCanvas.viewportTransform]);
                syncTarget.requestRenderAll();
            }
            lastMouse = { x: opt.e.clientX, y: opt.e.clientY };
        }

        function onUp() {
            if (isPanning) {
                isPanning = false;
                if (!self.spaceHeld) {
                    secondaryCanvas.defaultCursor = 'default';
                    secondaryCanvas.selection = true;
                    secondaryCanvas.upperCanvasEl.style.cursor = 'default';
                } else {
                    secondaryCanvas.defaultCursor = 'grab';
                    secondaryCanvas.upperCanvasEl.style.cursor = 'grab';
                }
            }
        }

        secondaryCanvas.on('mouse:down', onDown);
        secondaryCanvas.on('mouse:move', onMove);
        secondaryCanvas.on('mouse:up', onUp);

        this._secondaryUnbind = function () {
            secondaryCanvas.off('mouse:down', onDown);
            secondaryCanvas.off('mouse:move', onMove);
            secondaryCanvas.off('mouse:up', onUp);
        };
    }

    /* ── Private: attach ── */

    _attach() {
        document.addEventListener('keydown', this._onKeyDownBound);
        document.addEventListener('keyup', this._onKeyUpBound);
        this._enableMousePan();
        this._createOverlay();
        this._updateUI();
    }

    /* ── Private: overlay UI ── */

    _createOverlay() {
        if (!this.wrapper) return;

        this.overlay = document.createElement('div');
        this.overlay.className = 'zoom-overlay';
        this.overlay.innerHTML = `
            <button class="zoom-overlay-btn" id="zoom-in-btn" title="Увеличить (+)">+</button>
            <input type="range" id="zoom-slider" min="0" max="100" value="50" class="zoom-slider" orient="vertical">
            <button class="zoom-overlay-btn" id="zoom-out-btn" title="Уменьшить (-)">−</button>
            <span id="zoom-indicator" class="zoom-indicator">100%</span>
        `;

        this.wrapper.appendChild(this.overlay);

        document.getElementById('zoom-in-btn').addEventListener('click', () => this.zoomIn());
        document.getElementById('zoom-out-btn').addEventListener('click', () => this.zoomOut());

        const slider = document.getElementById('zoom-slider');
        slider.addEventListener('input', () => {
            this._updatingSlider = true;
            const val = parseInt(slider.value);
            const zoom = this._sliderToZoom(val);
            const rect = this.canvas.getElement().getBoundingClientRect();
            this.canvas.zoomToPoint({ x: rect.width / 2, y: rect.height / 2 }, zoom);
            this._syncCanvasZoom();
            this._updateIndicator();
            this._updatingSlider = false;
        });

        document.getElementById('zoom-indicator').addEventListener('click', () => this.resetZoom());
    }

    _removeOverlay() {
        if (this.overlay) {
            this.overlay.remove();
            this.overlay = null;
        }
    }

    _updateUI() {
        this._updateIndicator();
        this._updateSlider();
    }

    /* ── Slider ↔ Zoom (логарифмическая шкала от minZoom до maxZoom) ── */

    _sliderToZoom(val) {
        const logMin = Math.log(this.minZoom);
        const logMax = Math.log(this.maxZoom);
        const logZoom = logMin + (val / 100) * (logMax - logMin);
        return Math.exp(logZoom);
    }

    _zoomToSlider(zoom) {
        const logMin = Math.log(this.minZoom);
        const logMax = Math.log(this.maxZoom);
        const logZoom = Math.log(zoom);
        return Math.round(((logZoom - logMin) / (logMax - logMin)) * 100);
    }

    /* ── Indicator ── */

    _updateIndicator() {
        const el = document.getElementById('zoom-indicator');
        if (el) {
            const pct = Math.round((this.canvas.getZoom() / this.baseZoom) * 100);
            el.textContent = `${pct}%`;
        }
    }

    _updateSlider() {
        const slider = document.getElementById('zoom-slider');
        if (!slider || this._updatingSlider) return;
        slider.value = this._zoomToSlider(this.canvas.getZoom());
    }

    /* ── Private: keyboard ── */

    _onKeyDown(e) {
        if (this._isTyping(e)) return;

        if (e.code === 'Space' && !e.repeat) {
            e.preventDefault();
            this.spaceHeld = true;
            this.canvas.defaultCursor = 'grab';
            this.canvas.selection = false;
            this.canvas.upperCanvasEl.style.cursor = 'grab';
            // Обновляем и secondaryCanvas (если есть) — курсор может быть над ним
            if (this.syncCanvas) {
                this.syncCanvas.defaultCursor = 'grab';
                this.syncCanvas.selection = false;
                this.syncCanvas.upperCanvasEl.style.cursor = 'grab';
            }
            return;
        }

        if (e.key === '+' || e.key === '=') {
            e.preventDefault();
            this.zoomIn();
            return;
        }

        if (e.key === '-') {
            e.preventDefault();
            this.zoomOut();
            return;
        }

        if (e.key === '0') {
            e.preventDefault();
            this.resetZoom();
            return;
        }
    }

    _onKeyUp(e) {
        if (e.code === 'Space') {
            this.spaceHeld = false;
            if (!this.isPanning) {
                this.canvas.defaultCursor = 'default';
                this.canvas.selection = true;
                this.canvas.upperCanvasEl.style.cursor = 'default';
                if (this.syncCanvas) {
                    this.syncCanvas.defaultCursor = 'default';
                    this.syncCanvas.selection = true;
                    this.syncCanvas.upperCanvasEl.style.cursor = 'default';
                }
            }
        }
    }

    /* ── Private: mouse pan (Space+drag) ── */

    _enableMousePan() {
        const self = this;

        this._mouseDownHandler = function (opt) {
            if (!self.spaceHeld) return;
            if (opt.e.button !== 0) return;
            self.isPanning = true;
            self.canvas.selection = false;
            self.lastMouse = { x: opt.e.clientX, y: opt.e.clientY };
            self.canvas.defaultCursor = 'grabbing';
            self.canvas.upperCanvasEl.style.cursor = 'grabbing';
        };

        this._mouseMoveHandler = function (opt) {
            if (!self.isPanning) return;
            const dx = opt.e.clientX - self.lastMouse.x;
            const dy = opt.e.clientY - self.lastMouse.y;
            self.canvas.relativePan(new fabric.Point(dx, dy));
            self._syncPan(); // синхронизировать в реальном времени
            self.lastMouse = { x: opt.e.clientX, y: opt.e.clientY };
        };

        this._mouseUpHandler = function () {
            if (self.isPanning) {
                self.isPanning = false;
                if (!self.spaceHeld) {
                    self.canvas.defaultCursor = 'default';
                    self.canvas.selection = true;
                    self.canvas.upperCanvasEl.style.cursor = 'default';
                } else {
                    self.canvas.defaultCursor = 'grab';
                    self.canvas.upperCanvasEl.style.cursor = 'grab';
                }
            }
        };

        this.canvas.on('mouse:down', this._mouseDownHandler);
        this.canvas.on('mouse:move', this._mouseMoveHandler);
        this.canvas.on('mouse:up', this._mouseUpHandler);
    }

    _syncPan() {
        if (!this.syncCanvas) return;
        this.syncCanvas.setViewportTransform([...this.canvas.viewportTransform]);
        this.syncCanvas.requestRenderAll();
    }

    _unbindMousePan() {
        if (this._mouseDownHandler) this.canvas.off('mouse:down', this._mouseDownHandler);
        if (this._mouseMoveHandler) this.canvas.off('mouse:move', this._mouseMoveHandler);
        if (this._mouseUpHandler) this.canvas.off('mouse:up', this._mouseUpHandler);
    }

    /* ── Private: helpers ── */

    _zoomBy(factor) {
        const rect = this.canvas.getElement().getBoundingClientRect();
        const cx = rect.width / 2;
        const cy = rect.height / 2;
        let zoom = this.canvas.getZoom() * factor;
        zoom = Math.min(this.maxZoom, Math.max(this.minZoom, zoom));
        this.canvas.zoomToPoint({ x: cx, y: cy }, zoom);
        this._syncCanvasZoom();
        this._updateUI();
    }

    _isTyping(e) {
        const t = e.target;
        return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
    }
}
