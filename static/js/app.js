// Point d'entrée principal de l'application
import { API } from './api.js';
import { UIManager } from './ui-manager.js';
import { ConfigManager } from './config-manager.js';
import { AlertsManager } from './alerts-manager.js';
import { TrainingManager } from './training-manager.js';
import { Utils } from './utils.js';

class LastWarAlertsApp {
    constructor() {
        this.api = new API();
        this.ui = new UIManager();
        this.config = new ConfigManager(this.api, this.ui);
        this.alerts = new AlertsManager(this.api, this.ui);
        this.training = new TrainingManager(this.api, this.ui);
        this.utils = Utils;
        
        this.updateInterval = null;
        this.systemPaused = false;
    }
    
    async init() {
        console.log('Initialisation de l\'application...');
        
        try {
            // Charger les composants HTML
            await this.ui.loadComponents();
            
            // Initialiser les gestionnaires
            await this.config.init();
            await this.alerts.init();
            await this.training.init();
            
            // Attacher les événements globaux
            this.attachEventListeners();
            
            // Démarrer la mise à jour automatique
            this.startAutoUpdate();
            
            // Première mise à jour
            await this.updateDashboard();
            
            this.ui.showToast('Application chargée', 'success');
            
        } catch (error) {
            console.error('Erreur initialisation:', error);
            this.ui.showToast('Erreur de chargement', 'error');
        }
    }
    
    attachEventListeners() {
        // Pause/Resume
        window.togglePause = () => this.togglePause();
        
        // Configuration
        window.toggleConfigPanel = () => this.config.togglePanel();
        window.showAddAlertDialog = () => this.config.showAddAlertDialog();
        window.deleteAlert = (name) => this.config.deleteAlert(name);
        window.toggleAlert = (name) => this.config.toggleAlert(name);
        
        // Training
        window.toggleTrainingMode = () => this.training.toggleMode();
        window.saveAnnotation = () => this.training.saveCurrentAnnotation();
        window.clearAnnotation = () => this.training.clearAnnotation();
        
        // Gestion des faux positifs
        window.markFalsePositive = (source, alert) => this.handleFalsePositive(source, alert);
        
        // Raccourcis clavier
        document.addEventListener('keydown', (e) => this.handleKeyPress(e));
    }
    
    async updateDashboard() {
        try {
            const status = await this.api.getStatus();
            
            // Mettre à jour les différentes sections
            this.ui.updateSourcesStatus(status.windows_state);
            this.ui.updateAlertsHistory(status.alerts_history);
            
            // Mettre à jour l'état de pause si nécessaire
            if (status.system_paused !== undefined) {
                this.systemPaused = status.system_paused;
                this.ui.updatePauseState(this.systemPaused);
            }
            
        } catch (error) {
            console.error('Erreur mise à jour dashboard:', error);
        }
    }
    
    startAutoUpdate() {
        this.updateInterval = setInterval(() => {
            this.updateDashboard();
        }, 2000);
    }
    
    stopAutoUpdate() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }
    
    async togglePause() {
        try {
            const result = await this.api.togglePause();
            if (result.success) {
                this.systemPaused = result.paused;
                this.ui.updatePauseState(this.systemPaused);
                this.ui.showToast(result.message, 'info');
            }
        } catch (error) {
            console.error('Erreur toggle pause:', error);
            this.ui.showToast('Erreur lors du changement d\'état', 'error');
        }
    }
    
    async handleFalsePositive(sourceName, alertName) {
        try {
            const result = await this.api.markFalsePositive(sourceName, alertName);
            
            if (result.success) {
                let message = `Faux positif enregistré (Template: ${result.template_id})`;
                
                if (result.recommendation) {
                    message += `\nSeuil recommandé: ${result.recommendation.recommended}`;
                    
                    const apply = await this.ui.confirmDialog(
                        'Recommandation de seuil',
                        `${message}\n\nRaison: ${result.recommendation.reason}\n\nAppliquer ce seuil ?`
                    );
                    
                    if (apply) {
                        await this.config.updateTemplateThreshold(
                            alertName,
                            result.template_id,
                            result.recommendation.recommended
                        );
                        this.ui.showToast('Seuil mis à jour', 'success');
                    }
                }
                
                this.ui.showToast(message, 'info');
            }
        } catch (error) {
            console.error('Erreur faux positif:', error);
            this.ui.showToast('Erreur lors de l\'enregistrement', 'error');
        }
    }
    
    handleKeyPress(e) {
        // Espace ou P pour pause
        if (e.code === 'Space' || e.key === 'p') {
            if (!e.target.matches('input, textarea')) {
                e.preventDefault();
                this.togglePause();
            }
        }
        // C pour configuration
        else if (e.key === 'c' && e.ctrlKey) {
            e.preventDefault();
            this.config.togglePanel();
        }
        // T pour training
        else if (e.key === 't' && e.ctrlKey) {
            e.preventDefault();
            this.training.toggleMode();
        }
        // F11 ou F pour fullscreen
        else if (e.key === 'F11' || (e.key === 'f' && e.ctrlKey)) {
            e.preventDefault();
            this.utils.toggleFullscreen();
        }
    }
}

// Initialiser l'application au chargement
document.addEventListener('DOMContentLoaded', () => {
    window.app = new LastWarAlertsApp();
    window.app.init();
});