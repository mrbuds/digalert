// Gestion complète de la configuration
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
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <h5 class="mb-2">${alertName}</h5>
                                <div class="alert-info-grid">
                                    <small><i class="fas fa-images"></i> ${templateCount} templates</small>
                                    <small><i class="fas fa-sliders-h"></i> Seuil: ${alertConfig.threshold}</small>
                                    <small><i class="fas fa-clock"></i> Cooldown: ${alertConfig.cooldown}s</small>
                                </div>
                            </div>
                            <div class="btn-group-vertical ms-2">
                                <button class="btn btn-sm ${isEnabled ? 'btn-success' : 'btn-secondary'}"
                                        onclick="window.app.config.toggleAlert('${alertName}')"
                                        title="Activer/Désactiver">
                                    <i class="fas fa-power-off"></i>
                                </button>
                                <button class="btn btn-sm btn-warning" 
                                        onclick="window.app.config.editAlert('${alertName}')"
                                        title="Modifier">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <button class="btn btn-sm btn-danger"
                                        onclick="window.app.config.deleteAlert('${alertName}')"
                                        title="Supprimer">
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
                <input type="text" id="new-alert-name" class="form-control" placeholder="Ex: Titanium">
            </div>
            <div class="mb-3">
                <label class="form-label">Seuil de détection</label>
                <input type="number" id="new-alert-threshold" class="form-control" 
                       value="0.7" step="0.05" min="0.3" max="0.95">
            </div>
            <div class="mb-3">
                <label class="form-label">Cooldown (secondes)</label>
                <input type="number" id="new-alert-cooldown" class="form-control" 
                       value="300" step="10" min="0">
            </div>
        `, async () => {
            const name = document.getElementById('new-alert-name').value.trim();
            const threshold = parseFloat(document.getElementById('new-alert-threshold').value);
            const cooldown = parseInt(document.getElementById('new-alert-cooldown').value);
            
            if (name) {
                try {
                    const result = await this.api.addAlert(name, threshold, cooldown);
                    if (result.success) {
                        this.ui.showToast('✓ Alerte créée', 'success');
                        await this.loadConfig();
                        this.closeModal();
                    }
                } catch (error) {
                    this.ui.showToast('Erreur de création', 'error');
                }
            } else {
                this.ui.showToast('Nom requis', 'warning');
            }
        });
        
        modal.show();
    }
    
    async editAlert(alertName) {
        const alertConfig = this.config.alerts[alertName];
        if (!alertConfig) return;
        
        const modal = this.createModal(`Éditer: ${alertName}`, `
            <div class="mb-3">
                <label class="form-label">Nom de l'alerte</label>
                <input type="text" class="form-control" value="${alertName}" disabled>
            </div>
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
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="edit-alert-enabled" 
                           ${alertConfig.enabled ? 'checked' : ''}>
                    <label class="form-check-label" for="edit-alert-enabled">
                        Alerte activée
                    </label>
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label">Templates (${alertConfig.templates?.length || 0})</label>
                <div id="edit-templates-list" class="templates-mini-grid">
                    ${this.renderTemplatesMiniList(alertName, alertConfig.templates || [])}
                </div>
            </div>
        `, async () => {
            try {
                const threshold = parseFloat(document.getElementById('edit-alert-threshold').value);
                const cooldown = parseInt(document.getElementById('edit-alert-cooldown').value);
                const enabled = document.getElementById('edit-alert-enabled').checked;
                
                const response = await fetch(`/api/config/alert/${alertName}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ threshold, cooldown, enabled })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    this.ui.showToast('✓ Alerte mise à jour', 'success');
                    await this.loadConfig();
                    this.closeModal();
                } else {
                    this.ui.showToast('Erreur de mise à jour', 'error');
                }
            } catch (error) {
                this.ui.showToast('Erreur de mise à jour', 'error');
            }
        });
        
        modal.show();
    }
    
    renderTemplatesMiniList(alertName, templates) {
        if (templates.length === 0) {
            return '<p class="text-muted text-center">Aucun template</p>';
        }
        
        let html = '';
        templates.forEach((template, index) => {
            html += `
                <div class="template-mini-item">
                    <img src="${template.path}" alt="Template ${index + 1}">
                    <small>Seuil: ${template.threshold}</small>
                </div>`;
        });
        
        return html;
    }
    
    async deleteAlert(name) {
        const confirmed = confirm(`Êtes-vous sûr de vouloir supprimer l'alerte "${name}" et tous ses templates ?`);
        
        if (confirmed) {
            try {
                const result = await this.api.deleteAlert(name);
                if (result.success) {
                    this.ui.showToast('✓ Alerte supprimée', 'success');
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
    
    async loadTemplatesForAlert(alertName) {
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
                    <small class="text-muted d-block">Dernière utilisation: ${template.stats?.last_used ? new Date(template.stats.last_used).toLocaleString() : 'Jamais'}</small>
                </div>
            </div>
        `, async () => {
            const newThreshold = parseFloat(document.getElementById('edit-template-threshold').value);
            
            try {
                const result = await this.api.updateTemplateThreshold(
                    alertName,
                    templateId,
                    newThreshold
                );
                
                if (result.success) {
                    this.ui.showToast('✓ Template mis à jour', 'success');
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
    
    async deleteTemplate(alertName, templateId) {
        const confirmed = confirm('Êtes-vous sûr de vouloir supprimer ce template ?');
        
        if (!confirmed) return;
        
        const cardElement = document.querySelector(`#template-card-${alertName}-${templateId}`);
        if (cardElement) {
            cardElement.classList.add('removing');
        }
        
        try {
            const result = await this.api.deleteTemplate(alertName, templateId);
            
            if (result.success) {
                this.ui.showToast('✓ Template supprimé', 'success');
                
                setTimeout(async () => {
                    await this.loadConfig();
                    this.loadTemplatesForAlert(alertName);
                    this.displayAlerts();
                }, 300);
                
            } else {
                if (cardElement) {
                    cardElement.classList.remove('removing');
                }
                this.ui.showToast('Erreur lors de la suppression', 'error');
            }
        } catch (error) {
            console.error('Erreur suppression template:', error);
            if (cardElement) {
                cardElement.classList.remove('removing');
            }
            this.ui.showToast('Erreur de suppression', 'error');
        }
    }
    
    async importTemplates() {
        const alertSelect = document.getElementById('template-alert-select');
        if (!alertSelect || !alertSelect.value) {
            this.ui.showToast('Sélectionnez d\'abord une alerte', 'warning');
            return;
        }
        
        const alertName = alertSelect.value;
        
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
                        body: formData
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        imported++;
                    } else {
                        errors++;
                    }
                } catch (error) {
                    errors++;
                }
            }
            
            if (imported > 0) {
                this.ui.showToast(`✅ ${imported} template(s) importé(s)`, 'success');
                await this.loadConfig();
                this.loadTemplatesForAlert(alertName);
                this.displayAlerts();
            } else {
                this.ui.showToast(`❌ Aucun template importé (${errors} erreur(s))`, 'error');
            }
        };
        
        input.click();
    }
    
    async displaySources() {
        try {
            const response = await fetch('/api/config/sources');
            const data = await response.json();
            const container = document.getElementById('sources-config-list');
            
            if (!container) return;
            
            if (!data.sources || data.sources.length === 0) {
                container.innerHTML = '<p class="text-muted">Aucune source configurée</p>';
                return;
            }
            
            let html = '';
            
            for (const source of data.sources) {
                const isActive = source.status !== 'ERREUR';
                
                html += `
                    <div class="source-config-item">
                        <div class="source-info">
                            <span class="source-name">${source.name}</span>
                            <span class="badge bg-${isActive ? 'success' : 'danger'} ms-2">
                                ${isActive ? 'Active' : 'Inactive'}
                            </span>
                            <small class="text-muted d-block">Fenêtre: ${source.window_title}</small>
                        </div>
                        <div class="source-actions">
                            <button class="btn btn-sm btn-info" 
                                    onclick="window.app.config.editSource('${source.name}')"
                                    title="Éditer">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-sm btn-danger" 
                                    onclick="window.app.config.deleteSource('${source.name}')"
                                    title="Supprimer">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>`;
            }
            
            container.innerHTML = html;
            
        } catch (error) {
            console.error('Erreur affichage sources:', error);
        }
    }
    
    showAddSourceDialog() {
        const modal = this.createModal('Ajouter une source', `
            <div class="mb-3">
                <label class="form-label">Nom de la source</label>
                <input type="text" id="new-source-name" class="form-control" 
                      placeholder="Ex: LastWar1">
            </div>
            <div class="mb-3">
                <label class="form-label">Titre de la fenêtre</label>
                <input type="text" id="new-source-window" class="form-control" 
                      placeholder="Ex: Last War-Survival Game">
            </div>
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="new-source-enabled" checked>
                <label class="form-check-label" for="new-source-enabled">
                    Activer cette source
                </label>
            </div>
        `, async () => {
            const name = document.getElementById('new-source-name').value.trim();
            const window_title = document.getElementById('new-source-window').value.trim() || name;
            const enabled = document.getElementById('new-source-enabled').checked;
            
            if (!name) {
                this.ui.showToast('Nom requis', 'error');
                return;
            }
            
            try {
                const response = await fetch('/api/config/source', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, window_title, enabled })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    this.ui.showToast('✓ Source ajoutée', 'success');
                    await this.displaySources();
                    this.closeModal();
                } else {
                    this.ui.showToast(result.error || 'Erreur d\'ajout', 'error');
}
            } catch (error) {
                this.ui.showToast('Erreur d\'ajout', 'error');
            }
        });
        
        modal.show();
    }
    
    async editSource(sourceName) {
        try {
            const response = await fetch('/api/config/sources');
            const data = await response.json();
            const source = data.sources.find(s => s.name === sourceName);
            
            if (!source) {
                this.ui.showToast('Source non trouvée', 'error');
                return;
            }
            
            const modal = this.createModal(`Éditer: ${sourceName}`, `
                <div class="mb-3">
                    <label class="form-label">Nom de la source</label>
                    <input type="text" class="form-control" value="${sourceName}" disabled>
                </div>
                <div class="mb-3">
                    <label class="form-label">Titre de fenêtre (pour OBS)</label>
                    <input type="text" id="edit-source-window" class="form-control" 
                          value="${source.window_title || sourceName}">
                </div>
                <div class="mb-3">
                    <label class="form-label">Méthode de capture</label>
                    <select id="edit-source-method" class="form-select">
                        <option value="auto" ${source.capture_method === 'auto' ? 'selected' : ''}>Automatique</option>
                        <option value="print_window" ${source.capture_method === 'print_window' ? 'selected' : ''}>Print Window</option>
                        <option value="win32_gdi" ${source.capture_method === 'win32_gdi' ? 'selected' : ''}>Win32 GDI</option>
                        <option value="mss_monitor" ${source.capture_method === 'mss_monitor' ? 'selected' : ''}>MSS Monitor</option>
                    </select>
                </div>
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="edit-source-enabled" 
                           ${source.enabled ? 'checked' : ''}>
                    <label class="form-check-label" for="edit-source-enabled">
                        Source activée
                    </label>
                </div>
            `, async () => {
                const window_title = document.getElementById('edit-source-window').value.trim();
                const capture_method = document.getElementById('edit-source-method').value;
                const enabled = document.getElementById('edit-source-enabled').checked;
                
                try {
                    const response = await fetch(`/api/config/source/${sourceName}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ window_title, capture_method, enabled })
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        this.ui.showToast('✓ Source mise à jour', 'success');
                        await this.displaySources();
                        this.closeModal();
                    } else {
                        this.ui.showToast(result.error || 'Erreur de mise à jour', 'error');
                    }
                } catch (error) {
                    this.ui.showToast('Erreur de mise à jour', 'error');
                }
            });
            
            modal.show();
        } catch (error) {
            this.ui.showToast('Erreur de chargement', 'error');
        }
    }
    
    async deleteSource(sourceName) {
        const confirmed = confirm(`Êtes-vous sûr de vouloir supprimer la source "${sourceName}" ?`);
        
        if (!confirmed) return;
        
        try {
            const response = await fetch(`/api/config/source/${sourceName}`, {
                method: 'DELETE'
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.ui.showToast('✓ Source supprimée', 'success');
                await this.displaySources();
            } else {
                this.ui.showToast(result.error || 'Erreur de suppression', 'error');
            }
        } catch (error) {
            this.ui.showToast('Erreur de suppression', 'error');
        }
    }
    
    async saveSettings() {
        const settings = {
            check_interval: parseFloat(document.getElementById('check-interval')?.value || 2),
            notification_cooldown: parseInt(document.getElementById('notification-cooldown')?.value || 300),
            default_threshold: parseFloat(document.getElementById('default-threshold')?.value || 0.7)
        };
        
        try {
            const response = await fetch('/api/config/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.ui.showToast('✓ Paramètres sauvegardés', 'success');
            } else {
                this.ui.showToast('Erreur de sauvegarde', 'error');
            }
        } catch (error) {
            this.ui.showToast('Erreur de sauvegarde', 'error');
        }
    }
    
    async resetSettings() {
        const confirmed = confirm('Remettre tous les paramètres aux valeurs par défaut ?');
        
        if (!confirmed) return;
        
        document.getElementById('check-interval').value = '2';
        document.getElementById('notification-cooldown').value = '300';
        document.getElementById('default-threshold').value = '0.7';
        
        await this.saveSettings();
    }
    
    async exportAlerts() {
        try {
            const response = await fetch('/api/config/export');
            const data = await response.json();
            
            const filename = `alerts_config_${new Date().toISOString().split('T')[0]}.json`;
            
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            this.ui.showToast('✓ Configuration exportée', 'success');
        } catch (error) {
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
                
                const confirmed = confirm(
                    `Importer ${Object.keys(data.alerts).length} alerte(s) ?\n\nCela fusionnera avec la configuration actuelle.`
                );
                
                if (!confirmed) return;
                
                const response = await fetch('/api/config/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                
                if (result.success) {
                    this.ui.showToast('✓ Configuration importée', 'success');
                    await this.loadConfig();
                } else {
                    this.ui.showToast('Erreur d\'import', 'error');
                }
                
            } catch (error) {
                this.ui.showToast('Fichier invalide', 'error');
            }
        };
        
        input.click();
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
}