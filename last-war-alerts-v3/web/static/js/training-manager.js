// Gestion du mode entraînement et annotations
export class TrainingManager {
    constructor(api, ui) {
        this.api = api;
        this.ui = ui;
        this.trainingMode = false;
        this.canvas = null;
        this.ctx = null;
        this.isDrawing = false;
        this.selection = null;
        this.currentSource = null;
        this.currentImage = null;
    }
    
    async init() {
        await this.loadStats();
        this.setupCanvas();
    }
    
    async loadStats() {
        try {
            const stats = await this.api.getTrainingStats();
            this.updateStatsDisplay(stats);
        } catch (error) {
            console.error('Erreur chargement stats training:', error);
        }
    }
    
    setupCanvas() {
        const container = document.getElementById('training-canvas-container');
        if (!container) return;
        
        this.canvas = document.createElement('canvas');
        this.canvas.id = 'annotation-canvas';
        this.canvas.style.cssText = `
            border: 2px solid #444;
            border-radius: 5px;
            cursor: crosshair;
            max-width: 100%;
        `;
        
        container.appendChild(this.canvas);
        this.ctx = this.canvas.getContext('2d');
        
        // Event listeners
        this.canvas.addEventListener('mousedown', (e) => this.startDrawing(e));
        this.canvas.addEventListener('mousemove', (e) => this.updateDrawing(e));
        this.canvas.addEventListener('mouseup', (e) => this.endDrawing(e));
        
        // Touch events pour mobile
        this.canvas.addEventListener('touchstart', (e) => this.handleTouch(e, 'start'));
        this.canvas.addEventListener('touchmove', (e) => this.handleTouch(e, 'move'));
        this.canvas.addEventListener('touchend', (e) => this.handleTouch(e, 'end'));
    }
    
    toggleMode() {
        this.trainingMode = !this.trainingMode;
        const btn = document.getElementById('training-toggle-btn');
        const panel = document.getElementById('training-panel');
        
        if (this.trainingMode) {
            if (btn) {
                btn.innerHTML = '<i class="fas fa-times"></i> Désactiver';
                btn.classList.remove('btn-primary');
                btn.classList.add('btn-danger');
            }
            
            if (panel) {
                panel.style.display = 'block';
            }
            
            this.updateSourcesList();
            this.ui.showToast('Mode entraînement activé', 'success');
            
        } else {
            if (btn) {
                btn.innerHTML = '<i class="fas fa-pencil-alt"></i> Mode Entraînement';
                btn.classList.remove('btn-danger');
                btn.classList.add('btn-primary');
            }
            
            if (panel) {
                panel.style.display = 'none';
            }
            
            this.clearCanvas();
            this.ui.showToast('Mode entraînement désactivé', 'info');
        }
    }
    
    async updateSourcesList() {
        const select = document.getElementById('training-source-select');
        if (!select) return;
        
        try {
            const status = await this.api.getStatus();
            
            select.innerHTML = '<option value="">-- Sélectionner une source --</option>';
            
            if (status.windows_state) {
                for (const sourceName of Object.keys(status.windows_state)) {
                    const option = document.createElement('option');
                    option.value = sourceName;
                    option.textContent = sourceName;
                    select.appendChild(option);
                }
            }
        } catch (error) {
            console.error('Erreur chargement sources:', error);
        }
    }
    
    async loadSourceCapture() {
        const sourceSelect = document.getElementById('training-source-select');
        const alertSelect = document.getElementById('training-alert-select');
        
        if (!sourceSelect || !alertSelect) return;
        
        this.currentSource = sourceSelect.value;
        const alertName = alertSelect.value;
        
        if (!this.currentSource) {
            this.ui.showToast('Sélectionnez une source', 'error');
            return;
        }
        
        if (!alertName) {
            this.ui.showToast('Sélectionnez une alerte', 'error');
            return;
        }
        
        // Charger l'image
        const img = new Image();
        img.crossOrigin = 'anonymous';
        
        img.onload = () => {
            this.currentImage = img;
            this.canvas.width = img.width;
            this.canvas.height = img.height;
            
            // Adapter l'affichage
            const maxWidth = 800;
            if (img.width > maxWidth) {
                const scale = maxWidth / img.width;
                this.canvas.style.width = maxWidth + 'px';
                this.canvas.style.height = (img.height * scale) + 'px';
            } else {
                this.canvas.style.width = img.width + 'px';
                this.canvas.style.height = img.height + 'px';
            }
            
            this.ctx.drawImage(img, 0, 0);
            this.ui.showToast('Image chargée - Dessinez une zone', 'success');
        };
        
        img.onerror = () => {
            this.ui.showToast('Erreur de chargement de l\'image', 'error');
        };
        
        img.src = `/api/screenshot/${this.currentSource}?marked=false&t=${Date.now()}`;
    }
    
    startDrawing(e) {
        if (!this.currentImage) return;
        
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        
        this.isDrawing = true;
        this.selection = {
            startX: (e.clientX - rect.left) * scaleX,
            startY: (e.clientY - rect.top) * scaleY,
            endX: 0,
            endY: 0
        };
        
        // Sauvegarder l'état actuel
        this.imageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
    }
    
    updateDrawing(e) {
        if (!this.isDrawing || !this.selection) return;
        
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        
        this.selection.endX = (e.clientX - rect.left) * scaleX;
        this.selection.endY = (e.clientY - rect.top) * scaleY;
        
        // Redessiner
        this.ctx.putImageData(this.imageData, 0, 0);
        
        // Dessiner le rectangle
        this.ctx.strokeStyle = '#00ff00';
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([5, 5]);
        
        const width = this.selection.endX - this.selection.startX;
        const height = this.selection.endY - this.selection.startY;
        
        this.ctx.strokeRect(
            this.selection.startX,
            this.selection.startY,
            width,
            height
        );
        
        // Zone semi-transparente
        this.ctx.fillStyle = 'rgba(0, 255, 0, 0.2)';
        this.ctx.fillRect(
            this.selection.startX,
            this.selection.startY,
            width,
            height
        );
        
        // Afficher les dimensions
        this.updateSelectionInfo(Math.abs(width), Math.abs(height));
    }
    
    endDrawing(e) {
        if (!this.isDrawing) return;
        
        this.isDrawing = false;
        this.updateDrawing(e);
        
        // Vérifier la taille minimale
        const bbox = this.getSelectionBBox();
        if (bbox.width < 20 || bbox.height < 20) {
            this.ui.showToast('Zone trop petite (minimum 20×20px)', 'warning');
            this.clearAnnotation();
        }
    }
    
    handleTouch(e, type) {
        e.preventDefault();
        const touch = e.touches[0] || e.changedTouches[0];
        const mouseEvent = new MouseEvent(
            type === 'start' ? 'mousedown' : 
            type === 'move' ? 'mousemove' : 'mouseup',
            {
                clientX: touch.clientX,
                clientY: touch.clientY
            }
        );
        
        if (type === 'start') this.startDrawing(mouseEvent);
        else if (type === 'move') this.updateDrawing(mouseEvent);
        else if (type === 'end') this.endDrawing(mouseEvent);
    }
    
    getSelectionBBox() {
        if (!this.selection) return null;
        
        const x = Math.min(this.selection.startX, this.selection.endX);
        const y = Math.min(this.selection.startY, this.selection.endY);
        const width = Math.abs(this.selection.endX - this.selection.startX);
        const height = Math.abs(this.selection.endY - this.selection.startY);
        
        return { x, y, width, height };
    }
    
    updateSelectionInfo(width, height) {
        const info = document.getElementById('selection-info');
        if (info) {
            info.textContent = `Sélection: ${width.toFixed(0)}×${height.toFixed(0)}px`;
        }
    }
    
    clearAnnotation() {
        if (this.currentImage && this.ctx) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            this.ctx.drawImage(this.currentImage, 0, 0);
        }
        
        this.selection = null;
        this.updateSelectionInfo(0, 0);
    }
    
    clearCanvas() {
        if (this.ctx) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }
        this.currentImage = null;
        this.selection = null;
    }
    
    async saveCurrentAnnotation() {
        const bbox = this.getSelectionBBox();
        if (!bbox) {
            this.ui.showToast('Aucune zone sélectionnée', 'error');
            return;
        }
        
        const alertSelect = document.getElementById('training-alert-select');
        const thresholdInput = document.getElementById('training-threshold');
        
        const alertName = alertSelect?.value;
        const threshold = parseFloat(thresholdInput?.value || 0.7);
        
        if (!alertName) {
            this.ui.showToast('Sélectionnez une alerte', 'error');
            return;
        }
        
        try {
            const result = await this.api.addTemplate(
                this.currentSource,
                alertName,
                bbox,
                threshold
            );
            
            if (result.success) {
                let message = '✓ Template sauvegardé';
                
                if (result.immediate_detection) {
                    message += ' - Détection immédiate réussie !';
                    this.showSuccessAnimation();
                }
                
                this.ui.showToast(message, 'success');
                
                // Recharger les stats
                await this.loadStats();
                
                // Effacer après 2 secondes
                setTimeout(() => {
                    this.clearAnnotation();
                }, 2000);
            }
        } catch (error) {
            this.ui.showToast('Erreur de sauvegarde', 'error');
        }
    }
    
    showSuccessAnimation() {
        const bbox = this.getSelectionBBox();
        if (!bbox) return;
        
        this.ctx.strokeStyle = '#00ff00';
        this.ctx.lineWidth = 4;
        this.ctx.shadowBlur = 20;
        this.ctx.shadowColor = '#00ff00';
        this.ctx.setLineDash([]);
        
        let pulseCount = 0;
        const pulseInterval = setInterval(() => {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            this.ctx.drawImage(this.currentImage, 0, 0);
            
            this.ctx.globalAlpha = 0.5 + 0.5 * Math.sin(pulseCount * 0.5);
            this.ctx.strokeRect(bbox.x, bbox.y, bbox.width, bbox.height);
            this.ctx.globalAlpha = 1;
            
            pulseCount++;
            if (pulseCount > 10) {
                clearInterval(pulseInterval);
                this.ctx.shadowBlur = 0;
            }
        }, 100);
    }
    
    updateStatsDisplay(stats) {
        const container = document.getElementById('training-stats');
        if (!container) return;
        
        let html = `
            <div class="row">
                <div class="col-md-4">
                    <div class="stat-card">
                        <div class="stat-value">${stats.total_annotations || 0}</div>
                        <div class="stat-label">Annotations totales</div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="stat-card">
                        <div class="stat-value">${stats.manual_annotations || 0}</div>
                        <div class="stat-label">Manuelles</div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="stat-card">
                        <div class="stat-value">${stats.alerts_with_templates || 0}</div>
                        <div class="stat-label">Alertes configurées</div>
                    </div>
                </div>
            </div>`;
        
        container.innerHTML = html;
    }
}