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
    
    async addAlert(name, threshold = 0.7) {
        return this.request('/api/config/alert', {
            method: 'POST',
            body: JSON.stringify({ name, threshold })
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
    
    async updateTemplateThreshold(alertName, templateId, threshold, testWithLast = false, sourceName = null) {
        return this.request(`/api/config/template/${alertName}/${templateId}/threshold`, {
            method: 'POST',
            body: JSON.stringify({
                threshold: threshold,
                test_with_last: testWithLast,
                source_name: sourceName
            })
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
    
    async getAnnotations() {
        return this.request('/api/training/annotations');
    }
    
    async deleteAnnotation(annotationId) {
        return this.request(`/api/training/annotation/${annotationId}`, {
            method: 'DELETE'
        });
    }
    
    async clearAlertAnnotations(alertName) {
        return this.request(`/api/training/clear/${alertName}`, {
            method: 'POST'
        });
    }
}