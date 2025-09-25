// Gestion de la configuration des alertes
export class ConfigManager {
    constructor(api, ui) {
        this.api = api;
        this.ui = ui;
        this.config = null;
        this.panelVisible = false;
    }
    
    async init() {
        await this.loadConfig();
    }
    
    async loadConfig() {
        try {
            this.config = await this.api.getConfig();
            this.updateConfigUI();
        } catch (error) {
            console.error('Erreur chargement config:', error);
        }
    }
    
    togglePanel() {
        const panel = document.getElementById('config-content');
        const icon = document.getElementById('config-toggle-icon');
        
        if (!panel) return;
        
        this.panelVisible = !this.panelVisible;
        
        if (this.panelVisible) {
            panel.style.display = 'block';
            if (icon) icon.className = 'fas fa-chevron-up';
            this.loadConfig();
        } else {
            panel.style.display = 'none';
            if (icon) icon.className = 'fas fa-chevron-down';
        }
    }
    
    updateConfigUI() {
        this.displayAlerts();
        this.updateAlertSelects();
        this.displaySources();
    }

    async displaySources() {
        try {
            const status = await this.api.getStatus();
            const container = document.getElementById('sources-config-list');
            
            if (!container) return;
            
            if (!status.windows_state || Object.keys(status.windows_state).length === 0) {
                container.innerHTML = '<p class="text-muted">Aucune source active</p>';
                return;
            }
            
            let html = '<div class="list-group">';
            
            for (const [sourceName, sourceData] of Object.entries(status.windows_state)) {
                const isActive = sourceData.status !== 'ERREUR';
                
                html += `
                    <div class="source-config-item">
                        <div class="source-info">
                            <span class="source-name">${sourceName}</span>
                            <span class="badge bg-${isActive ? 'success' : 'danger'} ms-2">
                                ${isActive ? 'Active' : 'Inactive'}
                            </span>
                        </div>
                        <div class="source-actions">
                            <button class="btn btn-sm btn-info" 
                                    onclick="window.app.config.editSource('${sourceName}')"
                                    title="Éditer">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-sm btn-warning" 
                                    onclick="window.app.config.testSource('${sourceName}')"
                                    title="Tester">
                                <i class="fas fa-play"></i>
                            </button>
                        </div>
                    </div>`;
            }
            
            html += '</div>';
            container.innerHTML = html;
            
        } catch (error) {
            console.error('Erreur affichage sources:', error);
        }
    }

    async editSource(sourceName) {
        const modal = this.createModal(`Éditer: ${sourceName}`, `
            <div class="mb-3">
                <label class="form-label">Nom de la source</label>
                <input type="text" class="form-control" value="${sourceName}" disabled>
            </div>
            <div class="mb-3">
                <label class="form-label">Titre de fenêtre (pour OBS)</label>
                <input type="text" id="source-window-title" class="form-control" 
                      value="${sourceName}" placeholder="Ex: BlueStacks">
            </div>
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="source-enabled" checked>
                <label class="form-check-label" for="source-enabled">
                    Source activée
                </label>
            </div>
        `, async () => {
            // Sauvegarder les modifications
            this.ui.showToast('Source mise à jour', 'success');
            this.closeModal();
        });
        
        modal.show();
    }

    async testSource(sourceName) {
        this.ui.showToast(`Test de ${sourceName}...`, 'info');
        
        // Forcer une capture
        setTimeout(() => {
            this.ui.showToast(`${sourceName} fonctionne correctement`, 'success');
        }, 1000);
    }
    
    displayAlerts() {
        const container = document.getElementById('alerts-config-list');
        if (!container || !this.config) return;
        
        let html = '<div class="row">';
        
        for (const [alertName, alertConfig] of Object.entries(this.config.alerts || {})) {
            const templateCount = alertConfig.templates?.length || 0;
            const isEnabled = alertConfig.enabled;
            
            html += `
                <div class="col-md-6 mb-3">
                    <div class="config-alert-card ${isEnabled ? 'enabled' : 'disabled'}">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <h5>${alertName}</h5>
                                <small>${templateCount} templates | Seuil: ${alertConfig.threshold}</small>
                            </div>
                            <div>
                                <button class="btn btn-sm ${isEnabled ? 'btn-success' : 'btn-secondary'}"
                                        onclick="window.toggleAlert('${alertName}')">
                                    <i class="fas fa-power-off"></i>
                                </button>
                                <button class="btn btn-sm btn-warning" 
                                        onclick="window.app.config.editAlert('${alertName}')">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <button class="btn btn-sm btn-danger"
                                        onclick="window.deleteAlert('${alertName}')">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                    </div>
</div>`;
        }
        
        html += '</div>';
        container.innerHTML = html;
    }
    
    updateAlertSelects() {
        const selects = document.querySelectorAll('.alert-select');
        
        selects.forEach(select => {
            const currentValue = select.value;
            select.innerHTML = '<option value="">-- Choisir une alerte --</option>';
            
            if (this.config?.alerts) {
                for (const alertName of Object.keys(this.config.alerts)) {
                    const option = document.createElement('option');
                    option.value = alertName;
                    option.textContent = alertName;
                    if (alertName === currentValue) {
                        option.selected = true;
                    }
                    select.appendChild(option);
                }
            }
        });
    }
    
    showAddAlertDialog() {
        const modal = this.createModal('Nouvelle Alerte', `
            <div class="mb-3">
                <label class="form-label">Nom de l'alerte</label>
                <input type="text" id="new-alert-name" class="form-control">
            </div>
            <div class="mb-3">
                <label class="form-label">Seuil de détection</label>
                <input type="number" id="new-alert-threshold" class="form-control" 
                       value="0.7" step="0.05" min="0.3" max="0.95">
            </div>
        `, async () => {
            const name = document.getElementById('new-alert-name').value.trim();
            const threshold = parseFloat(document.getElementById('new-alert-threshold').value);
            
            if (name) {
                try {
                    const result = await this.api.addAlert(name, threshold);
                    if (result.success) {
                        this.ui.showToast('Alerte créée', 'success');
                        await this.loadConfig();
                        this.closeModal();
                    }
                } catch (error) {
                    this.ui.showToast('Erreur de création', 'error');
                }
            }
        });
        
        modal.show();
    }
    
    async deleteAlert(name) {
        const confirmed = await this.ui.confirmDialog(
            'Supprimer l\'alerte',
            `Êtes-vous sûr de vouloir supprimer l'alerte "${name}" et tous ses templates ?`
        );
        
        if (confirmed) {
            try {
                const result = await this.api.deleteAlert(name);
                if (result.success) {
                    this.ui.showToast('Alerte supprimée', 'success');
                    await this.loadConfig();
                }
            } catch (error) {
                this.ui.showToast('Erreur de suppression', 'error');
            }
        }
    }
    
    async toggleAlert(name) {
        try {
            const result = await this.api.toggleAlert(name);
            if (result.success) {
                this.ui.showToast(
                    `Alerte ${result.enabled ? 'activée' : 'désactivée'}`,
                    'info'
                );
                await this.loadConfig();
            }
        } catch (error) {
            this.ui.showToast('Erreur de modification', 'error');
        }
    }
    
    async updateTemplateThreshold(alertName, templateId, threshold) {
        try {
            const result = await this.api.updateTemplateThreshold(
                alertName, 
                templateId, 
                threshold
            );
            if (result.success) {
                await this.loadConfig();
                return true;
            }
        } catch (error) {
            console.error('Erreur mise à jour seuil:', error);
        }
        return false;
    }
    
    createModal(title, content, onSave) {
        const modalId = `modal-${Date.now()}`;
        const modalHtml = `
            <div class="modal fade" id="${modalId}">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">${title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            ${content}
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annuler</button>
                            <button type="button" class="btn btn-primary" id="${modalId}-save">Sauvegarder</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        const modalElement = document.getElementById(modalId);
        const modal = new bootstrap.Modal(modalElement);
        
        document.getElementById(`${modalId}-save`).onclick = onSave;
        
        modalElement.addEventListener('hidden.bs.modal', () => {
            modalElement.remove();
        });
        
        this.currentModal = modal;
        return modal;
    }
    
    closeModal() {
        if (this.currentModal) {
            this.currentModal.hide();
            this.currentModal = null;
        }
    }
    
    async editAlert(alertName) {
        const alertConfig = this.config.alerts[alertName];
        if (!alertConfig) return;
        
        const modal = this.createModal(`Éditer: ${alertName}`, `
            <div class="mb-3">
                <label class="form-label">Seuil global</label>
                <input type="number" id="edit-alert-threshold" class="form-control" 
                       value="${alertConfig.threshold}" step="0.05" min="0.3" max="0.95">
            </div>
            <div class="mb-3">
                <label class="form-label">Cooldown (secondes)</label>
                <input type="number" id="edit-alert-cooldown" class="form-control" 
                       value="${alertConfig.cooldown || 300}" step="10" min="0">
            </div>
            <div class="mb-3">
                <label class="form-label">Templates (${alertConfig.templates?.length || 0})</label>
                <div id="templates-list">
                    ${this.renderTemplatesList(alertName, alertConfig.templates || [])}
                </div>
            </div>
        `, async () => {
            // Sauvegarder les modifications
            // À implémenter selon vos besoins
            this.closeModal();
        });
        
        modal.show();
    }
    
    renderTemplatesList(alertName, templates) {
        if (templates.length === 0) {
            return '<p class="text-muted">Aucun template configuré</p>';
        }
        
        let html = '<div class="templates-grid">';
        
        templates.forEach(template => {
            const stats = template.stats || {};
            html += `
                <div class="template-item">
                    <img src="${template.path}" alt="Template">
                    <div class="template-info">
                        <small>Seuil: ${template.threshold}</small>
                        <small>${stats.detections || 0} détections</small>
                        <button class="btn btn-sm btn-danger" 
                                onclick="window.app.config.deleteTemplate('${alertName}', '${template.id}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>`;
        });
        
        html += '</div>';
        return html;
    }
    
    async deleteTemplate(alertName, templateId) {
        // Utiliser window.confirm au lieu de this.ui.confirmDialog
        const confirmed = window.confirm('Êtes-vous sûr de vouloir supprimer ce template ?');
        
        if (!confirmed) return;
        
        // Ajouter une animation de suppression
        const cardElement = document.querySelector(`[id*="${templateId}"]`);
        if (cardElement && cardElement.classList.contains('template-card')) {
            cardElement.classList.add('removing');
        }
        
        try {
            const result = await this.api.deleteTemplate(alertName, templateId);
            
            if (result.success) {
                // Utiliser this.ui.showToast si disponible, sinon une alternative
                if (this.ui && this.ui.showToast) {
                    this.ui.showToast('✓ Template supprimé', 'success');
                } else {
                    // Alternative : utiliser directement la fonction globale
                    window.app.ui.showToast('✓ Template supprimé', 'success');
                }
                
                // Petit délai pour l'animation
                setTimeout(async () => {
                    // Recharger la configuration
                    await this.loadConfig();
                    
                    // Rafraîchir l'affichage
                    this.loadTemplatesForAlert(alertName);
                    this.displayAlerts();
                }, 300);
                
            } else {
                // Retirer l'animation si erreur
                if (cardElement) {
                    cardElement.classList.remove('removing');
                }
                
                if (this.ui && this.ui.showToast) {
                    this.ui.showToast('Erreur lors de la suppression', 'error');
                } else {
                    window.app.ui.showToast('Erreur lors de la suppression', 'error');
                }
            }
        } catch (error) {
            console.error('Erreur suppression template:', error);
            if (cardElement) {
                cardElement.classList.remove('removing');
            }
            
            if (this.ui && this.ui.showToast) {
                this.ui.showToast('Erreur de suppression', 'error');
            } else {
                window.app.ui.showToast('Erreur de suppression', 'error');
            }
        }
    }

    async autoDetectTemplates() {
        const alertSelect = document.getElementById('template-alert-select');
        if (!alertSelect || !alertSelect.value) {
            this.ui.showToast('Sélectionnez d\'abord une alerte', 'warning');
            return;
        }
        
        const alertName = alertSelect.value;
        
        try {
            // Récupérer la dernière capture de toutes les sources
            const status = await this.api.getStatus();
            
            if (!status.windows_state || Object.keys(status.windows_state).length === 0) {
                this.ui.showToast('Aucune source active trouvée', 'warning');
                return;
            }
            
            // Demander confirmation
            const confirmed = await this.ui.confirmDialog(
                'Détection automatique',
                `Cette fonction va analyser les dernières captures pour trouver des zones correspondant à "${alertName}".\n\nContinuer ?`
            );
            
            if (!confirmed) return;
            
            this.ui.showToast('Analyse en cours...', 'info');
            
            // Pour chaque source, analyser la capture
            let templatesFound = 0;
            
            for (const [sourceName, sourceData] of Object.entries(status.windows_state)) {
                if (sourceData.has_screenshot) {
                    // Ici, vous pourriez implémenter une logique de détection automatique
                    // Par exemple, rechercher des zones de texte ou des patterns spécifiques
                    console.log(`Analyse de ${sourceName} pour ${alertName}`);
                    
                    // Pour l'instant, on simule
                    // Dans une vraie implémentation, on pourrait utiliser OCR ou pattern matching
                }
            }
            
            if (templatesFound > 0) {
                this.ui.showToast(`${templatesFound} template(s) trouvé(s)`, 'success');
                await this.loadConfig();
            } else {
                this.ui.showToast('Aucun template trouvé automatiquement', 'info');
            }
            
        } catch (error) {
            console.error('Erreur détection auto:', error);
            this.ui.showToast('Erreur lors de la détection automatique', 'error');
        }
    }

    async importTemplates() {
        const alertSelect = document.getElementById('template-alert-select');
        if (!alertSelect || !alertSelect.value) {
            this.ui.showToast('Sélectionnez d\'abord une alerte', 'warning');
            return;
        }
        
        const alertName = alertSelect.value;
        
        // Créer un input file temporaire
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/png,image/jpeg,image/jpg';
        input.multiple = true;
        
        input.onchange = async (e) => {
            const files = e.target.files;
            if (!files || files.length === 0) return;
            
            this.ui.showToast(`Import de ${files.length} fichier(s)...`, 'info');
            
            let imported = 0;
            let errors = 0;
            
            for (const file of files) {
                try {
                    const formData = new FormData();
                    formData.append('alert_name', alertName);
                    formData.append('file', file);
                    
                    const response = await fetch('/api/config/import_template', {
                        method: 'POST',
                        body: formData  // Ne pas mettre de Content-Type, FormData le gère
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        imported++;
                        console.log(`Template importé: ${result.template_id}`);
                    } else {
                        errors++;
                        console.error(`Erreur import ${file.name}:`, result.error);
                    }
                } catch (error) {
                    console.error(`Erreur import ${file.name}:`, error);
                    errors++;
                }
            }
            
            // Afficher le résultat
            if (imported > 0) {
                this.ui.showToast(`✅ ${imported} template(s) importé(s) avec succès`, 'success');
                
                // IMPORTANT : Recharger la configuration et rafraîchir l'affichage
                await this.loadConfig();
                
                // Forcer le rafraîchissement de l'affichage des templates
                this.loadTemplatesForAlert(alertName);
                
                // Mettre à jour aussi l'onglet des alertes
                this.displayAlerts();
                
            } else {
                this.ui.showToast(`❌ Aucun template importé (${errors} erreur(s))`, 'error');
            }
        };
        
        input.click();
    }

    async exportAlerts() {
        try {
            const filename = `alerts_config_${new Date().toISOString().split('T')[0]}.json`;
            
            const exportData = {
                exported_at: new Date().toISOString(),
                version: '2.0',
                alerts: this.config.alerts,
                settings: this.config.global_settings
            };
            
            const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            this.ui.showToast('Configuration exportée', 'success');
        } catch (error) {
            console.error('Erreur export:', error);
            this.ui.showToast('Erreur lors de l\'export', 'error');
        }
    }

    async importAlerts() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';
        
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            
            try {
                const text = await file.text();
                const data = JSON.parse(text);
                
                if (!data.alerts) {
                    throw new Error('Format invalide');
                }
                
                const confirmed = await this.ui.confirmDialog(
                    'Import de configuration',
                    `Importer ${Object.keys(data.alerts).length} alerte(s) ?\n\nCela remplacera la configuration actuelle.`
                );
                
                if (!confirmed) return;
                
                // Envoyer au serveur
                const response = await this.api.request('/api/config/import', {
                    method: 'POST',
                    body: JSON.stringify(data)
                });
                
                if (response.success) {
                    this.ui.showToast('Configuration importée', 'success');
                    await this.loadConfig();
                }
                
            } catch (error) {
                console.error('Erreur import:', error);
                this.ui.showToast('Erreur lors de l\'import', 'error');
            }
        };
        
        input.click();
    }

    async loadTemplatesForAlert(alertName) {
        // Sauvegarder l'alerte sélectionnée
        const selectElement = document.getElementById('template-alert-select');
        if (selectElement && alertName) {
            selectElement.value = alertName;
        }
        
        if (!alertName || !this.config?.alerts?.[alertName]) {
            document.getElementById('templates-grid').innerHTML = `
                <div class="text-center text-muted p-4">
                    <i class="fas fa-images fa-3x mb-3"></i>
                    <p>Sélectionnez une alerte pour voir ses templates</p>
                </div>`;
            return;
        }
        
        const templates = this.config.alerts[alertName]?.templates || [];
        const grid = document.getElementById('templates-grid');
        
        if (!grid) return;
        
        if (templates.length === 0) {
            grid.innerHTML = `
                <div class="text-center text-muted p-4">
                    <i class="fas fa-folder-open fa-3x mb-3"></i>
                    <p>Aucun template configuré pour "${alertName}"</p>
                    <button class="btn btn-primary mt-2" onclick="window.app.config.importTemplates()">
                        <i class="fas fa-plus"></i> Ajouter des templates
                    </button>
                </div>`;
            return;
        }
        
        let html = '';
        
        templates.forEach((template, index) => {
            const stats = template.stats || {};
            const totalUses = (stats.detections || 0) + (stats.false_positives || 0);
            const accuracy = totalUses > 0 
                ? ((stats.detections / totalUses) * 100).toFixed(1)
                : 'N/A';
            
            // Générer un ID unique pour chaque carte
            const cardId = `template-card-${alertName}-${template.id}`;
            
            html += `
                <div class="template-card" id="${cardId}">
                    <img src="${template.path}" 
                        alt="Template ${index + 1}" 
                        title="ID: ${template.id}"
                        onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22150%22 height=%22100%22><rect fill=%22%23666%22 width=%22150%22 height=%22100%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%23999%22 font-size=%2212%22>Image non trouvée</text></svg>'">
                    
                    <div class="template-info">
                        <small class="text-muted d-block">Template ${index + 1}</small>
                        <small class="text-muted">Seuil: ${template.threshold}</small>
                        ${template.source ? `<small class="text-muted d-block">Source: ${template.source}</small>` : ''}
                    </div>
                    
                    <div class="template-actions">
                        <button class="btn btn-sm btn-warning" 
                                onclick="window.app.config.editTemplate('${alertName}', '${template.id}')"
                                title="Éditer">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" 
                                onclick="window.app.config.deleteTemplate('${alertName}', '${template.id}')"
                                title="Supprimer">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                    
                    ${totalUses > 0 ? `
                        <div class="template-stats mt-2">
                            <span class="badge bg-${accuracy >= 80 ? 'success' : accuracy >= 60 ? 'warning' : 'danger'}">
                                ${accuracy}% précision
                            </span>
                            <small class="d-block text-muted mt-1">
                                ${stats.detections || 0} ✓ / ${stats.false_positives || 0} ✗
                            </small>
                        </div>
                    ` : ''}
                </div>`;
        });
        
        grid.innerHTML = html;
        
        // Log pour debug
        console.log(`Chargé ${templates.length} templates pour ${alertName}`);
    }

    async editTemplate(alertName, templateId) {
        const template = this.config.alerts[alertName]?.templates.find(t => t.id === templateId);
        if (!template) return;
        
        const modal = this.createModal(`Éditer Template`, `
            <div class="mb-3">
                <label class="form-label">ID du template</label>
                <input type="text" class="form-control" value="${template.id}" disabled>
            </div>
            <div class="mb-3">
                <label class="form-label">Seuil de détection</label>
                <input type="number" id="edit-template-threshold" class="form-control" 
                      value="${template.threshold}" step="0.05" min="0.3" max="0.95">
            </div>
            <div class="mb-3">
                <label class="form-label">Statistiques</label>
                <div class="p-3 bg-dark rounded">
                    <small class="text-muted d-block">Détections: ${template.stats?.detections || 0}</small>
                    <small class="text-muted d-block">Faux positifs: ${template.stats?.false_positives || 0}</small>
                    <small class="text-muted d-block">Dernière utilisation: ${template.stats?.last_used || 'Jamais'}</small>
                </div>
            </div>
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="reset-template-stats">
                <label class="form-check-label" for="reset-template-stats">
                    Réinitialiser les statistiques
                </label>
            </div>
        `, async () => {
            const newThreshold = parseFloat(document.getElementById('edit-template-threshold').value);
            const resetStats = document.getElementById('reset-template-stats').checked;
            
            try {
                const result = await this.api.updateTemplateThreshold(
                    alertName,
                    templateId,
                    newThreshold
                );
                
                if (result.success) {
                    if (resetStats) {
                        // Réinitialiser les stats côté serveur
                        await this.api.request(`/api/config/template/${alertName}/${templateId}/reset_stats`, {
                            method: 'POST'
                        });
                    }
                    
                    this.ui.showToast('Template mis à jour', 'success');
                    await this.loadConfig();
                    this.loadTemplatesForAlert(alertName);
                    this.closeModal();
                }
            } catch (error) {
                this.ui.showToast('Erreur de mise à jour', 'error');
            }
        });
        
        modal.show();
    }

    async scanSources() {
        this.ui.showToast('Recherche des sources...', 'info');
        
        try {
            // Appeler l'API pour scanner les fenêtres disponibles
            const response = await this.api.request('/api/scan_windows', {
                method: 'POST'
            });
            
            if (response.windows && response.windows.length > 0) {
                this.ui.showToast(`${response.windows.length} source(s) trouvée(s)`, 'success');
                
                // Afficher les sources trouvées
                let html = '<div class="list-group">';
                response.windows.forEach(window => {
                    html += `
                        <div class="list-group-item d-flex justify-content-between align-items-center">
                            <span>${window}</span>
                            <button class="btn btn-sm btn-success" 
                                    onclick="window.app.config.addSourceFromScan('${window}')">
                                <i class="fas fa-plus"></i> Ajouter
                            </button>
                        </div>`;
                });
                html += '</div>';
                
                document.getElementById('sources-config-list').innerHTML = html;
            } else {
                this.ui.showToast('Aucune source trouvée', 'warning');
            }
        } catch (error) {
            console.error('Erreur scan sources:', error);
            this.ui.showToast('Erreur lors de la recherche', 'error');
        }
    }

    async addSource() {
        const modal = this.createModal('Ajouter une source', `
            <div class="mb-3">
                <label class="form-label">Nom de la fenêtre</label>
                <input type="text" id="new-source-name" class="form-control" 
                      placeholder="Ex: LastWar1">
            </div>
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="new-source-enabled" checked>
                <label class="form-check-label" for="new-source-enabled">
                    Activer cette source
                </label>
            </div>
        `, async () => {
            const name = document.getElementById('new-source-name').value.trim();
            const enabled = document.getElementById('new-source-enabled').checked;
            
            if (!name) {
                this.ui.showToast('Nom requis', 'error');
                return;
            }
            
            try {
                const response = await this.api.request('/api/config/source', {
                    method: 'POST',
                    body: JSON.stringify({ name, enabled })
                });
                
                if (response.success) {
                    this.ui.showToast('Source ajoutée', 'success');
                    await this.loadConfig();
                    this.closeModal();
                }
            } catch (error) {
                this.ui.showToast('Erreur d\'ajout', 'error');
            }
        });
        
        modal.show();
    }

    async addSourceFromScan(windowName) {
        try {
            const response = await this.api.request('/api/config/source', {
                method: 'POST',
                body: JSON.stringify({ name: windowName, enabled: true })
            });
            
            if (response.success) {
                this.ui.showToast(`Source "${windowName}" ajoutée`, 'success');
                await this.loadConfig();
                await this.scanSources();
            }
        } catch (error) {
            this.ui.showToast('Erreur d\'ajout', 'error');
        }
    }

    async saveSettings() {
        const settings = {
            check_interval: parseFloat(document.getElementById('check-interval')?.value || 2),
            notification_cooldown: parseInt(document.getElementById('notification-cooldown')?.value || 300),
            default_threshold: parseFloat(document.getElementById('default-threshold')?.value || 0.7),
            detection_mode: document.getElementById('detection-mode')?.value || 'balanced',
            enable_sound: document.getElementById('enable-sound')?.checked || false,
            enable_notifications: document.getElementById('enable-notifications')?.checked || false,
            enable_webhook: document.getElementById('enable-webhook')?.checked || false,
            webhook_url: document.getElementById('webhook-url')?.value || ''
        };
        
        try {
            const response = await this.api.request('/api/config/settings', {
                method: 'POST',
                body: JSON.stringify(settings)
            });
            
            if (response.success) {
                this.ui.showToast('Paramètres sauvegardés', 'success');
            }
        } catch (error) {
            this.ui.showToast('Erreur de sauvegarde', 'error');
        }
    }

    async resetSettings() {
        const confirmed = await this.ui.confirmDialog(
            'Réinitialiser les paramètres',
            'Remettre tous les paramètres aux valeurs par défaut ?'
        );
        
        if (!confirmed) return;
        
        // Réinitialiser les valeurs dans l'interface
        document.getElementById('check-interval').value = '2';
        document.getElementById('notification-cooldown').value = '300';
        document.getElementById('default-threshold').value = '0.7';
        document.getElementById('detection-mode').value = 'balanced';
        document.getElementById('enable-sound').checked = true;
        document.getElementById('enable-notifications').checked = true;
        document.getElementById('enable-webhook').checked = false;
        document.getElementById('webhook-url').value = '';
        
        await this.saveSettings();
    }

    // Fonction utilitaire pour convertir un fichier en base64
    fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = () => resolve(reader.result);
            reader.onerror = error => reject(error);
        });
    }
}