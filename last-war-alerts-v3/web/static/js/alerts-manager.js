// Gestion des alertes et de l'historique
export class AlertsManager {
    constructor(api, ui) {
        this.api = api;
        this.ui = ui;
        this.alertsHistory = [];
        this.validatedAlerts = new Set();
    }
    
    async init() {
        // Charger l'historique initial
        await this.loadHistory();
        
        // Activer les notifications si supportées
        this.requestNotificationPermission();
    }
    
    async loadHistory() {
        try {
            const status = await this.api.getStatus();
            if (status.alerts_history) {
                this.alertsHistory = status.alerts_history;
                this.updateHistoryDisplay();
            }
        } catch (error) {
            console.error('Erreur chargement historique:', error);
        }
    }
    
    updateHistoryDisplay() {
        const container = document.getElementById('alerts-history-list');
        if (!container) return;
        
        if (this.alertsHistory.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted p-4">
                    <i class="fas fa-clock fa-3x mb-3"></i>
                    <p>Aucune alerte récente</p>
                </div>`;
            return;
        }
        
        let html = '<div class="alerts-list">';
        
        // Afficher les 20 dernières alertes
        const recentAlerts = this.alertsHistory.slice(-20).reverse();
        
        recentAlerts.forEach(alert => {
            const alertId = alert.id || `${alert.source_name}_${alert.alert_name}_${Date.now()}`;
            const time = new Date(alert.timestamp);
            const timeStr = time.toLocaleTimeString();
            const isRecent = (Date.now() - time) < 60000; // Moins d'1 minute
            const isValidated = this.validatedAlerts.has(alertId);
            
            html += `
                <div class="alert-history-item ${isRecent ? 'recent' : ''} ${isValidated ? 'validated' : ''}">
                    <div class="alert-main-info">
                        <div class="alert-header">
                            <strong class="alert-name">
                                <i class="fas fa-bell"></i> ${alert.alert_name}
                            </strong>
                            <span class="alert-time">${timeStr}</span>
                        </div>
                        <div class="alert-details">
                            <span class="badge bg-secondary">${alert.source_name}</span>
                            <span class="badge bg-${this.getConfidenceBadgeColor(alert.confidence)}">
                                ${(alert.confidence * 100).toFixed(1)}%
                            </span>
                        </div>
                    </div>`;
            
            // Ajouter l'image et les boutons si disponibles
            if (alert.screenshot_url || alert.has_screenshot) {
                html += `
                    <div class="alert-actions">`;
                
                if (alert.screenshot_url) {
                    html += `
                        <img src="${alert.screenshot_url}" 
                             class="alert-screenshot-thumb"
                             onclick="window.app.ui.showScreenshot('${alert.source_name}')"
                             alt="Screenshot">`;
                }
                
                if (!isValidated && alert.template_id) {
                    html += `
                        <div class="validation-buttons" id="val_${alertId}">
                            <button class="btn btn-sm btn-success" 
                                    onclick="window.app.alerts.validateAlert('${alertId}', '${alert.alert_name}', '${alert.source_name}', true)"
                                    title="Détection correcte">
                                <i class="fas fa-check"></i>
                            </button>
                            <button class="btn btn-sm btn-danger"
                                    onclick="window.app.alerts.validateAlert('${alertId}', '${alert.alert_name}', '${alert.source_name}', false)"
                                    title="Faux positif">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>`;
                } else if (isValidated) {
                    html += `
                        <div class="validation-status">
                            <span class="badge bg-success">
                                <i class="fas fa-check-circle"></i> Validé
                            </span>
                        </div>`;
                }
                
                html += `</div>`;
            }
            
            // Informations sur le template utilisé
            if (alert.template_id) {
                html += `
                    <div class="template-info">
                        <small class="text-muted">
                            Template: ${alert.template_id}
                            ${alert.detection_area ? ` | Zone: ${alert.detection_area.width}×${alert.detection_area.height}px` : ''}
                        </small>
                    </div>`;
            }
            
            html += `</div>`;
        });
        
        html += '</div>';
        
        // Ajouter les statistiques résumées
        html += this.generateStatsSummary();
        
        container.innerHTML = html;
    }
    
    generateStatsSummary() {
        if (this.alertsHistory.length === 0) return '';
        
        // Calculer les statistiques
        const alertCounts = {};
        const sourceCounts = {};
        let totalAlerts = this.alertsHistory.length;
        
        this.alertsHistory.forEach(alert => {
            alertCounts[alert.alert_name] = (alertCounts[alert.alert_name] || 0) + 1;
            sourceCounts[alert.source_name] = (sourceCounts[alert.source_name] || 0) + 1;
        });
        
        // Trouver les plus fréquents
        const topAlert = Object.entries(alertCounts)
            .sort((a, b) => b[1] - a[1])[0];
        const topSource = Object.entries(sourceCounts)
            .sort((a, b) => b[1] - a[1])[0];
        
        return `
            <div class="alert-stats-summary mt-3 p-3">
                <h6 class="text-muted mb-2">Résumé</h6>
                <div class="row">
                    <div class="col-4 text-center">
                        <div class="stat-mini">
                            <div class="stat-value">${totalAlerts}</div>
                            <div class="stat-label">Total</div>
                        </div>
                    </div>
                    <div class="col-4 text-center">
                        <div class="stat-mini">
                            <div class="stat-value">${topAlert ? topAlert[0] : '-'}</div>
                            <div class="stat-label">Plus fréquente</div>
                        </div>
                    </div>
                    <div class="col-4 text-center">
                        <div class="stat-mini">
                            <div class="stat-value">${topSource ? topSource[0] : '-'}</div>
                            <div class="stat-label">Source active</div>
                        </div>
                    </div>
                </div>
            </div>`;
    }
    
    async validateAlert(alertId, alertName, sourceName, isCorrect) {
        // Éviter les validations multiples
        if (this.validatedAlerts.has(alertId)) {
            this.ui.showToast('Déjà validé', 'warning');
            return;
        }
        
        this.validatedAlerts.add(alertId);
        
        // Masquer les boutons
        const buttonsDiv = document.getElementById(`val_${alertId}`);
        if (buttonsDiv) {
            buttonsDiv.innerHTML = '<span class="text-muted"><i class="fas fa-spinner fa-spin"></i></span>';
        }
        
        try {
            if (!isCorrect) {
                // Si c'est un faux positif
                const result = await this.api.markFalsePositive(sourceName, alertName);
                
                if (result.success) {
                    this.ui.showToast('Faux positif enregistré', 'info');
                    
                    // Proposer d'ajuster le seuil si recommandé
                    if (result.recommendation && result.template_id) {
                        const adjust = await this.ui.confirmDialog(
                            'Ajustement recommandé',
                            `Seuil recommandé: ${result.recommendation.recommended}\nRaison: ${result.recommendation.reason}\n\nAppliquer ?`
                        );
                        
                        if (adjust) {
                            await window.app.config.updateTemplateThreshold(
                                alertName,
                                result.template_id,
                                result.recommendation.recommended
                            );
                            this.ui.showToast('Seuil ajusté', 'success');
                        }
                    }
                }
            } else {
                // Validation positive
                this.ui.showToast('Détection validée', 'success');
                // Ici on pourrait enregistrer la validation positive côté serveur
            }
            
            // Mettre à jour l'affichage
            if (buttonsDiv) {
                buttonsDiv.innerHTML = `
                    <span class="badge bg-${isCorrect ? 'success' : 'warning'}">
                        <i class="fas fa-check-circle"></i> 
                        ${isCorrect ? 'Validé' : 'Faux positif'}
                    </span>`;
            }
            
        } catch (error) {
            console.error('Erreur validation:', error);
            this.ui.showToast('Erreur de validation', 'error');
            this.validatedAlerts.delete(alertId);
            
            // Réafficher les boutons en cas d'erreur
            await this.loadHistory();
        }
    }
    
    getConfidenceBadgeColor(confidence) {
        if (confidence >= 0.8) return 'success';
        if (confidence >= 0.6) return 'warning';
        return 'danger';
    }
    
    requestNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    console.log('Notifications activées');
                }
            });
        }
    }
    
    showNotification(title, message, iconUrl = null) {
        if ('Notification' in window && Notification.permission === 'granted') {
            const options = {
                body: message,
                icon: iconUrl || '/static/favicon.ico',
                badge: '/static/badge.png',
                vibrate: [200, 100, 200],
                timestamp: Date.now(),
                requireInteraction: false
            };
            
            const notification = new Notification(title, options);
            
            // Auto-fermer après 5 secondes
            setTimeout(() => notification.close(), 5000);
            
            // Clic sur la notification
            notification.onclick = () => {
                window.focus();
                notification.close();
            };
        }
    }
    
    playAlertSound(alertName) {
        // Son différent selon le type d'alerte
        const audio = new Audio();
        
        // Sons encodés en base64 (vous pouvez les remplacer par des fichiers)
        const sounds = {
            default: 'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBTGH0fPTgjMGHm7A7+OZURE',
            critical: 'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBTGH0fPTgjMGHm7A7+OZURE'
        };
        
        // Sélectionner le son approprié
        if (alertName && alertName.includes('EGGGGGG')) {
            audio.src = sounds.critical;
            audio.volume = 0.5;
        } else {
            audio.src = sounds.default;
            audio.volume = 0.3;
        }
        
        // Jouer le son
        audio.play().catch(e => console.log('Audio non disponible:', e));
    }
    
    async exportHistory() {
        const filename = `alerts_history_${new Date().toISOString().split('T')[0]}.json`;
        
        const exportData = {
            exported_at: new Date().toISOString(),
            total_alerts: this.alertsHistory.length,
            alerts: this.alertsHistory,
            statistics: this.generateExportStats()
        };
        
        // Utiliser la fonction utilitaire pour télécharger
        window.app.utils.downloadJSON(exportData, filename);
        this.ui.showToast('Historique exporté', 'success');
    }
    
    generateExportStats() {
        const stats = {
            by_alert: {},
            by_source: {},
            by_hour: {},
            confidence_distribution: {
                high: 0,    // >= 0.8
                medium: 0,  // 0.6 - 0.8
                low: 0      // < 0.6
            }
        };
        
        this.alertsHistory.forEach(alert => {
            // Par alerte
            stats.by_alert[alert.alert_name] = (stats.by_alert[alert.alert_name] || 0) + 1;
            
            // Par source
            stats.by_source[alert.source_name] = (stats.by_source[alert.source_name] || 0) + 1;
            
            // Par heure
            const hour = new Date(alert.timestamp).getHours();
            stats.by_hour[hour] = (stats.by_hour[hour] || 0) + 1;
            
            // Distribution de confiance
            if (alert.confidence >= 0.8) stats.confidence_distribution.high++;
            else if (alert.confidence >= 0.6) stats.confidence_distribution.medium++;
            else stats.confidence_distribution.low++;
        });
        
        return stats;
    }
    
    clearHistory() {
        if (confirm('Effacer tout l\'historique des alertes ?')) {
            this.alertsHistory = [];
            this.validatedAlerts.clear();
            this.updateHistoryDisplay();
            this.ui.showToast('Historique effacé', 'info');
        }
    }
}