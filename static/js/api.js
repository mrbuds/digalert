// Gestion centralisée des appels API
export class API {
    constructor() {
        this.baseUrl = '';
    }
    
    async request(url, options = {}) {
        try {
            const response = await fetch(url, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error(`API Error (${url}):`, error);
            throw error;
        }
    }
    
    // Status et monitoring
    async getStatus() {
        return this.request('/api/status');
    }
    
    async togglePause() {
        return this.request('/api/toggle_pause', { method: 'POST' });
    }
    
    async resetStats() {
        return this.request('/api/reset_stats', { method: 'POST' });
    }
    
    // Configuration
    async getConfig() {
        return this.request('/api/config');
    }
    
    async saveConfig(config) {
        return this.request('/api/config/save', {
            method: 'POST',
            body: JSON.stringify(config)
        });
    }
    
    async exportConfig() {
        return this.request('/api/config/export');
    }
    
    async importConfig(data) {
        return this.request('/api/config/import', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
    
    // Alertes
    async addAlert(name, threshold = 0.7, cooldown = 300) {
        return this.request('/api/config/alert', {
            method: 'POST',
            body: JSON.stringify({ name, threshold, cooldown })
        });
    }
    
    async updateAlert(name, data) {
        return this.request(`/api/config/alert/${name}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }
    
    async deleteAlert(name) {
        return this.request(`/api/config/alert/${name}`, { method: 'DELETE' });
    }
    
    async toggleAlert(name) {
        return this.request(`/api/config/alert/${name}/toggle`, { method: 'POST' });
    }
    
    // Templates
    async addTemplate(sourceName, alertName, bbox, threshold) {
        return this.request('/api/config/template', {
            method: 'POST',
            body: JSON.stringify({
                source_name: sourceName,
                alert_name: alertName,
                bbox: bbox,
                threshold: threshold
            })
        });
    }
    
    async deleteTemplate(alertName, templateId) {
        return this.request(`/api/config/template/${alertName}/${templateId}`, {
            method: 'DELETE'
        });
    }
    
    async updateTemplateThreshold(alertName, templateId, threshold) {
        return this.request(`/api/config/template/${alertName}/${templateId}/threshold`, {
            method: 'POST',
            body: JSON.stringify({ threshold })
        });
    }
    
    // Sources
    async getSources() {
        return this.request('/api/config/sources');
    }
    
    async addSource(name, window_title, enabled = true) {
        return this.request('/api/config/source', {
            method: 'POST',
            body: JSON.stringify({ name, window_title, enabled })
        });
    }
    
    async updateSource(name, data) {
        return this.request(`/api/config/source/${name}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }
    
    async deleteSource(name) {
        return this.request(`/api/config/source/${name}`, { method: 'DELETE' });
    }
    
    // Paramètres globaux
    async saveSettings(settings) {
        return this.request('/api/config/settings', {
            method: 'POST',
            body: JSON.stringify(settings)
        });
    }
    
    // Détection
    async markFalsePositive(sourceName, alertName) {
        return this.request('/api/detection/false_positive', {
            method: 'POST',
            body: JSON.stringify({
                source_name: sourceName,
                alert_name: alertName
            })
        });
    }
    
    // Training
    async getTrainingStats() {
        return this.request('/api/training/statistics');
    }
}