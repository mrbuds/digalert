// Gestion de l'interface utilisateur
export class UIManager {
    constructor() {
        this.components = {};
        this.toastContainer = null;
    }
    
    async loadComponents() {
        // Charger les composants HTML
        const components = [
            { id: 'pause-controls-container', file: 'pause-controls.html' },
            { id: 'header-container', file: 'header.html' },
            { id: 'sources-status-container', file: 'sources-status.html' },
            { id: 'alerts-history-container', file: 'alerts-history.html' },
            { id: 'config-panel-container', file: 'config-panel.html' },
            { id: 'training-panel-container', file: 'training-panel.html' }
        ];
        
        for (const component of components) {
            try {
                const response = await fetch(`/static/components/${component.file}`);
                const html = await response.text();
                const container = document.getElementById(component.id);
                if (container) {
                    container.innerHTML = html;
                    this.components[component.id] = container;
                }
            } catch (error) {
                console.error(`Erreur chargement composant ${component.file}:`, error);
            }
        }
        
        // Créer le container pour les toasts
        this.createToastContainer();
    }
    
    createToastContainer() {
        this.toastContainer = document.createElement('div');
        this.toastContainer.id = 'toast-container';
        this.toastContainer.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
        `;
        document.body.appendChild(this.toastContainer);
    }
    
    showToast(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast-notification ${type}`;
        toast.textContent = message;
        
        this.toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => {
                this.toastContainer.removeChild(toast);
            }, 300);
        }, duration);
    }
    
    updateSourcesStatus(windowsState) {
        const container = document.getElementById('sources-list');
        if (!container) return;
        
        let html = '';
        let totalAlerts = 0;
        
        for (const [sourceName, source] of Object.entries(windowsState || {})) {
            totalAlerts += source.total_detections || 0;
            
            const statusIcon = this.getStatusIcon(source.status);
            const statusColor = source.status_color || 'secondary';
            const hasDetection = source.has_detection && source.last_alert_name !== 'Aucune';
            
            html += `
                <div class="status-card ${statusColor}">
                    <div class="row align-items-center">
                        <div class="col-md-3">
                            <h5>${statusIcon} ${sourceName}</h5>
                            <span class="badge bg-${statusColor}">${source.status || 'Inconnu'}</span>
                        </div>
                        <div class="col-md-2 text-center">
                            <div class="metric-value" style="font-size: 1.2rem;">
                                ${source.last_capture_relative || 'Jamais'}
                            </div>
                            <div class="metric-label">Dernière capture</div>
                        </div>
                        <div class="col-md-2 text-center">
                            <div class="metric-value" style="font-size: 1.2rem; color: ${this.getConfidenceColor(source.last_confidence)};">
                                ${source.confidence_percent || '0%'}
                            </div>
                            <div class="metric-label">Confiance</div>
                        </div>
                        <div class="col-md-2 text-center">
                            <div class="metric-value" style="font-size: 1.2rem;">
                                ${source.total_detections || 0}
                            </div>
                            <div class="metric-label">Détections</div>
                        </div>
                        <div class="col-md-3">
                            ${source.has_screenshot ? `
                                <img src="/api/screenshot/${sourceName}?marked=${hasDetection}&t=${Date.now()}" 
                                     class="screenshot-thumbnail ${hasDetection ? 'has-detection' : ''}"
                                     onclick="window.app.ui.showScreenshot('${sourceName}')"
                                     alt="${sourceName}">
                                ${hasDetection ? `
                                    <div class="detection-info">
                                        <span class="badge bg-warning">${source.last_alert_name}</span>
                                        <button class="btn btn-sm btn-danger ms-2" 
                                                onclick="window.markFalsePositive('${sourceName}', '${source.last_alert_name}')">
                                            <i class="fas fa-times"></i> Faux positif
                                        </button>
                                    </div>
                                ` : ''}
                            ` : '<div class="text-muted">Pas de capture</div>'}
                        </div>
                    </div>
                </div>`;
        }
        
        container.innerHTML = html;
        
        // Mettre à jour le compteur total
        const totalElem = document.getElementById('total-alerts');
        if (totalElem) totalElem.textContent = totalAlerts;
    }
    
    updateAlertsHistory(alerts) {
        const container = document.getElementById('alerts-list');
        if (!container) return;
        
        if (!alerts || alerts.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted">
                    <i class="fas fa-clock fa-2x mb-3"></i>
                    <p>Aucune alerte récente</p>
                </div>`;
            return;
        }
        
        let html = '';
        alerts.slice(-10).reverse().forEach(alert => {
            const time = new Date(alert.timestamp).toLocaleTimeString();
            const isRecent = (Date.now() - new Date(alert.timestamp)) < 60000;
            
            html += `
                <div class="alert-item ${isRecent ? 'recent' : ''}">
                    <div>
                        <strong>${alert.alert_name}</strong><br>
                        <small class="text-muted">${alert.source_name}</small>
                    </div>
                    <div class="text-end">
                        <span class="badge bg-success">${alert.confidence_percent}</span><br>
                        <small>${time}</small>
                    </div>
                </div>`;
        });
        
        container.innerHTML = html;
    }
    
    updatePauseState(isPaused) {
        const btn = document.getElementById('pauseBtn');
        const status = document.getElementById('pauseStatus');
        
        if (btn) {
            btn.className = isPaused ? 'pause-btn active' : 'pause-btn inactive';
            btn.innerHTML = isPaused ? '<i class="fas fa-pause"></i>' : '<i class="fas fa-play"></i>';
        }
        
        if (status) {
            status.textContent = isPaused ? 'En Pause' : 'Actif';
            status.className = isPaused ? 'pause-status paused' : 'pause-status running';
        }
    }
    
    getStatusIcon(status) {
        const icons = {
            'OK': '<i class="fas fa-check-circle text-success"></i>',
            'ALERTE': '<i class="fas fa-exclamation-triangle text-warning"></i>',
            'ERREUR': '<i class="fas fa-times-circle text-danger"></i>',
            'PAUSE': '<i class="fas fa-pause-circle text-secondary"></i>',
            'Instable': '<i class="fas fa-question-circle text-info"></i>'
        };
        return icons[status] || '<i class="fas fa-circle"></i>';
    }
    
    getConfidenceColor(confidence) {
        if (confidence >= 0.8) return '#28a745';
        if (confidence >= 0.5) return '#ffc107';
        return '#dc3545';
    }
    
    async confirmDialog(title, message) {
        return new Promise((resolve) => {
            const result = confirm(`${title}\n\n${message}`);
            resolve(result);
        });
    }
    
    showScreenshot(sourceName) {
        // Créer une modal Bootstrap
        const modalHtml = `
            <div class="modal fade" id="screenshotModal" tabindex="-1">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content" style="background: rgba(40, 40, 50, 0.98);">
                        <div class="modal-header">
                            <h5 class="modal-title text-white">
                                <i class="fas fa-image"></i> Screenshot - ${sourceName}
                                <span id="zoom-info" class="ms-3 badge bg-info">Zoom: 100%</span>
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row">
                                <div class="col-md-8">
                                    <div style="position: relative; overflow: auto; max-height: 600px;">
                                        <canvas id="screenshotCanvas" style="border: 2px solid #444; border-radius: 5px; cursor: crosshair;"></canvas>
                                    </div>
                                    <div class="mt-2 text-center">
                                        <small class="text-muted">
                                            <i class="fas fa-info-circle"></i> 
                                            Cliquez et glissez pour sélectionner | 
                                            Molette pour zoomer | 
                                            Double-clic pour réinitialiser
                                        </small>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="annotation-controls">
                                        <h6 class="text-white">Ajouter comme template</h6>
                                        <div class="mb-3">
                                            <label class="form-label text-white">Alerte</label>
                                            <select id="modal-alert-select" class="form-select">
                                                <option value="">-- Choisir --</option>
                                            </select>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label text-white">Seuil</label>
                                            <input type="number" id="modal-threshold" class="form-control" 
                                                  value="0.7" min="0.3" max="0.95" step="0.05">
                                        </div>
                                        <button class="btn btn-success w-100" onclick="window.app.ui.saveModalSelection('${sourceName}')">
                                            <i class="fas fa-save"></i> Sauvegarder la sélection
                                        </button>
                                        <button class="btn btn-warning w-100 mt-2" onclick="window.app.ui.clearModalCanvas()">
                                            <i class="fas fa-undo"></i> Effacer
                                        </button>
                                        <div id="selection-info" class="mt-3 p-2 bg-dark rounded text-center text-muted">
                                            Aucune sélection
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>`;
        
        // Supprimer la modal existante si elle existe
        const existingModal = document.getElementById('screenshotModal');
        if (existingModal) {
            existingModal.remove();
        }
        
        // Ajouter la nouvelle modal
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Initialiser la modal
        const modalElement = document.getElementById('screenshotModal');
        const modal = new bootstrap.Modal(modalElement);
        
        // Charger l'image dans le canvas
        const img = new Image();
        img.onload = () => {
            const canvas = document.getElementById('screenshotCanvas');
            const ctx = canvas.getContext('2d');
            
            canvas.width = img.width;
            canvas.height = img.height;
            ctx.drawImage(img, 0, 0);
            
            // Ajouter les event listeners pour dessiner (version simplifiée)
            this.setupSimpleCanvas(canvas, sourceName, img);
            
            // Remplir le select des alertes
            this.fillModalAlertSelect();
        };
        
        img.src = `/api/screenshot/${sourceName}?marked=false&t=${Date.now()}`;
        
        // Nettoyer quand la modal se ferme
        modalElement.addEventListener('hidden.bs.modal', () => {
            modalElement.remove();
        });
        
        modal.show();
    }

    setupSimpleCanvas(canvas, sourceName, originalImage) {
        const ctx = canvas.getContext('2d');
        let isDrawing = false;
        let isPanning = false;
        let startX, startY;
        let panStartX, panStartY;
        let offsetX = 0, offsetY = 0;
        let scale = 1;  // Commencer à 100%
        let selection = null;
        
        // Fonction pour redessiner
        function redraw() {
            // Taille du canvas selon le zoom
            canvas.width = originalImage.width * scale;
            canvas.height = originalImage.height * scale;
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // Sauvegarder le contexte
            ctx.save();
            
            // Appliquer le décalage (pan)
            ctx.translate(offsetX * scale, offsetY * scale);
            
            // Dessiner l'image avec le zoom
            ctx.drawImage(originalImage, 0, 0, canvas.width, canvas.height);
            
            // Restaurer le contexte pour dessiner la sélection
            ctx.restore();
            
            // Dessiner la sélection si elle existe
            if (selection) {
                ctx.strokeStyle = '#00ff00';
                ctx.lineWidth = 2;
                ctx.setLineDash([5, 5]);
                
                ctx.strokeRect(
                    (selection.x + offsetX) * scale,
                    (selection.y + offsetY) * scale,
                    selection.width * scale,
                    selection.height * scale
                );
                
                ctx.fillStyle = 'rgba(0, 255, 0, 0.2)';
                ctx.fillRect(
                    (selection.x + offsetX) * scale,
                    (selection.y + offsetY) * scale,
                    selection.width * scale,
                    selection.height * scale
                );
            }
        }
        
        // Empêcher le menu contextuel
        canvas.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            return false;
        });
        
        // Gestion de la souris
        canvas.addEventListener('mousedown', (e) => {
            const rect = canvas.getBoundingClientRect();
            const mouseX = (e.clientX - rect.left) / scale - offsetX;
            const mouseY = (e.clientY - rect.top) / scale - offsetY;
            
            if (e.button === 0) {  // Clic gauche - Sélection
                startX = mouseX;
                startY = mouseY;
                isDrawing = true;
                isPanning = false;
                selection = null;
                canvas.style.cursor = 'crosshair';
                
            } else if (e.button === 2) {  // Clic droit - Pan
                panStartX = e.clientX;
                panStartY = e.clientY;
                isPanning = true;
                isDrawing = false;
                canvas.style.cursor = 'move';
            }
        });
        
        canvas.addEventListener('mousemove', (e) => {
            if (isPanning) {
                // Mode déplacement
                const deltaX = (e.clientX - panStartX) / scale;
                const deltaY = (e.clientY - panStartY) / scale;
                
                offsetX += deltaX;
                offsetY += deltaY;
                
                panStartX = e.clientX;
                panStartY = e.clientY;
                
                redraw();
                
            } else if (isDrawing) {
                // Mode sélection
                const rect = canvas.getBoundingClientRect();
                const currentX = (e.clientX - rect.left) / scale - offsetX;
                const currentY = (e.clientY - rect.top) / scale - offsetY;
                
                selection = {
                    x: Math.min(startX, currentX),
                    y: Math.min(startY, currentY),
                    width: Math.abs(currentX - startX),
                    height: Math.abs(currentY - startY)
                };
                
                redraw();
                
                // Afficher les dimensions
                document.getElementById('selection-info').innerHTML = 
                    `Sélection: ${Math.round(selection.width)}×${Math.round(selection.height)}px`;
            }
        });
        
        canvas.addEventListener('mouseup', (e) => {
            if (isPanning) {
                isPanning = false;
                canvas.style.cursor = 'crosshair';
                
            } else if (isDrawing) {
                isDrawing = false;
                
                if (selection && selection.width > 20 && selection.height > 20) {
                    // Stocker les coordonnées réelles (sans offset)
                    canvas.dataset.selection = JSON.stringify({
                        x: selection.x,
                        y: selection.y,
                        width: selection.width,
                        height: selection.height
                    });
                } else if (selection) {
                    document.getElementById('selection-info').innerHTML = 
                        '<span class="text-warning">Zone trop petite (min 20×20px)</span>';
                    selection = null;
                    redraw();
                }
            }
        });
        
        // Zoom avec la molette
        canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            
            const rect = canvas.getBoundingClientRect();
            const mouseX = (e.clientX - rect.left) / scale - offsetX;
            const mouseY = (e.clientY - rect.top) / scale - offsetY;
            
            // Calculer le nouveau zoom
            const delta = e.deltaY < 0 ? 1.1 : 0.9;
            const oldScale = scale;
            scale = Math.min(Math.max(scale * delta, 0.3), 5);  // Entre 30% et 500%
            
            if (scale !== oldScale) {
                // Ajuster l'offset pour zoomer sur la position de la souris
                const scaleRatio = scale / oldScale;
                offsetX = mouseX - (mouseX - offsetX) * scaleRatio;
                offsetY = mouseY - (mouseY - offsetY) * scaleRatio;
                
                redraw();
                
                // Mettre à jour l'affichage du zoom
                document.getElementById('zoom-info').textContent = `Zoom: ${Math.round(scale * 100)}%`;
                
                // Si on zoom/dézoom, effacer la sélection
                if (selection) {
                    selection = null;
                    canvas.dataset.selection = null;
                    document.getElementById('selection-info').innerHTML = 'Aucune sélection';
                }
            }
        });
        
        // Double-clic pour réinitialiser
        canvas.addEventListener('dblclick', (e) => {
            e.preventDefault();
            scale = 1;
            offsetX = 0;
            offsetY = 0;
            selection = null;
            canvas.dataset.selection = null;
            redraw();
            document.getElementById('zoom-info').textContent = 'Zoom: 100%';
            document.getElementById('selection-info').innerHTML = 'Aucune sélection';
        });
        
        // Gérer le relâchement de la souris en dehors du canvas
        document.addEventListener('mouseup', () => {
            if (isDrawing) isDrawing = false;
            if (isPanning) {
                isPanning = false;
                canvas.style.cursor = 'crosshair';
            }
        });
        
        // Empêcher la sélection de texte pendant le drag
        canvas.addEventListener('selectstart', (e) => {
            e.preventDefault();
        });
        
        // Mettre à jour les instructions
        const existingInstructions = document.getElementById('canvas-instructions');
        if (existingInstructions) {
            existingInstructions.remove();
        }
        
        const instructions = document.createElement('div');
        instructions.id = 'canvas-instructions';
        instructions.className = 'text-muted text-center mt-2';
        instructions.innerHTML = `
            <small>
                <i class="fas fa-info-circle"></i> 
                <strong>Clic gauche:</strong> Sélectionner | 
                <strong>Clic droit:</strong> Déplacer | 
                <strong>Molette:</strong> Zoomer | 
                <strong>Double-clic:</strong> Réinitialiser
            </small>
        `;
        canvas.parentElement.appendChild(instructions);
        
        // Dessiner initialement à 100%
        redraw();
        document.getElementById('zoom-info').textContent = 'Zoom: 100%';
    }

    fillModalAlertSelect() {
        const select = document.getElementById('modal-alert-select');
        if (!select || !window.app.config.config) return;
        
        select.innerHTML = '<option value="">-- Choisir une alerte --</option>';
        
        for (const alertName of Object.keys(window.app.config.config.alerts || {})) {
            const option = document.createElement('option');
            option.value = alertName;
            option.textContent = alertName;
            select.appendChild(option);
        }
    }

    async saveModalSelection(sourceName) {
        const canvas = document.getElementById('screenshotCanvas');
        const selection = canvas.dataset.selection ? JSON.parse(canvas.dataset.selection) : null;
        const alertName = document.getElementById('modal-alert-select').value;
        const threshold = parseFloat(document.getElementById('modal-threshold').value);
        
        if (!selection || selection.width < 20 || selection.height < 20) {
            this.showToast('Sélectionnez une zone valide (minimum 20x20px)', 'warning');
            return;
        }
        
        if (!alertName) {
            this.showToast('Choisissez une alerte', 'warning');
            return;
        }
        
        try {
            const result = await window.app.api.addTemplate(
                sourceName,
                alertName,
                selection,
                threshold
            );
            
            if (result.success) {
                this.showToast('Template ajouté avec succès', 'success');
                
                // Fermer la modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('screenshotModal'));
                if (modal) modal.hide();
                
                // Recharger la config
                await window.app.config.loadConfig();
            }
        } catch (error) {
            this.showToast('Erreur lors de l\'ajout', 'error');
        }
    }

    clearModalCanvas() {
        const canvas = document.getElementById('screenshotCanvas');
        const ctx = canvas.getContext('2d');
        
        // Recharger l'image originale
        const img = new Image();
        img.onload = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0);
        };
        
        const sourceName = document.querySelector('.modal-title').textContent.split(' - ')[1];
        img.src = `/api/screenshot/${sourceName}?marked=false&t=${Date.now()}`;
        
        // Effacer la sélection
        delete canvas.dataset.selection;
    }
}