# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request, send_file
import json
import time
import threading
from datetime import datetime, timedelta
import os
import cv2
import numpy as np
from utils import log_error, log_debug, log_info, log_warning

class WebAppManager:
    """Gestionnaire de l'interface web avec historique des alertes"""
    
    def __init__(self, port=5000, debug=False):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.port = port
        self.debug = debug
        self.windows_state = {}
        self.global_stats = {}
        self.alerts_history = []
        self.alerts_with_screenshots = []  # NOUVEAU: Historique avec screenshots
        self.server_thread = None
        self.running = False
        self.latest_screenshots = {}  # Screenshots sans alerte
        self.latest_detections = {}   # Screenshots avec détection
        
        # Créer les dossiers nécessaires
        self._ensure_directories()
        
        self.setup_routes()
        
    def _ensure_directories(self):
        """Crée les dossiers nécessaires"""
        required_dirs = [
            'static',
            'static/screenshots',
            'static/alerts',  # NOUVEAU: Dossier spécifique aux alertes
            'templates'
        ]
        
        for directory in required_dirs:
            try:
                os.makedirs(directory, exist_ok=True)
                log_debug(f"Dossier créé/vérifié: {directory}")
            except Exception as e:
                log_error(f"Erreur création dossier {directory}: {e}")
        
    def setup_routes(self):
        """Configuration des routes Flask"""
        
        @self.app.route('/')
        def index():
            return render_template('index.html')
        
        @self.app.route('/api/status')
        def api_status():
            """API pour récupérer le statut en temps réel"""
            return jsonify({
                'timestamp': datetime.now().isoformat(),
                'windows_state': self.format_windows_state(),
                'global_stats': self.format_global_stats(),
                'alerts_history': self.alerts_history[-20:],  # 20 dernières alertes simples
                'uptime': self.calculate_uptime()
            })
        
        @self.app.route('/api/alerts/history')
        def api_alerts_history():
            """API pour l'historique complet des alertes avec screenshots"""
            return jsonify({
                'alerts': self.alerts_history[-50:],
                'alerts_with_screenshots': self.alerts_with_screenshots[-10:],  # 10 dernières avec screenshots
                'latest_detections': self.latest_detections
            })
        
        @self.app.route('/api/screenshot/<source_name>')
        def api_screenshot(source_name):
            """API pour récupérer le screenshot d'une source"""
            if source_name in self.latest_screenshots:
                screenshot_path = self.latest_screenshots[source_name].get('screenshot_path')
                if screenshot_path and os.path.exists(screenshot_path):
                    return send_file(screenshot_path, mimetype='image/png')
            
            return jsonify({'error': 'Screenshot non trouvé'}), 404
        
        @self.app.route('/api/alert_screenshot/<filename>')
        def api_alert_screenshot(filename):
            """API pour récupérer un screenshot d'alerte spécifique"""
            filepath = f"static/alerts/{filename}"
            if os.path.exists(filepath):
                return send_file(filepath, mimetype='image/png')
            
            return jsonify({'error': 'Screenshot d\'alerte non trouvé'}), 404
        
        @self.app.route('/api/detection/<source_name>')
        def api_detection_screenshot(source_name):
            """API pour récupérer le screenshot avec zone de détection"""
            if source_name in self.latest_detections:
                detection_path = self.latest_detections[source_name].get('marked_screenshot_path')
                if detection_path and os.path.exists(detection_path):
                    return send_file(detection_path, mimetype='image/png')
            
            return jsonify({'error': 'Screenshot de détection non trouvé'}), 404
        
        @self.app.route('/api/reset_stats', methods=['POST'])
        def api_reset_stats():
            """API pour réinitialiser les statistiques"""
            try:
                # Reset des stats par fenêtre
                for source_name in self.windows_state:
                    state = self.windows_state[source_name]
                    state.update({
                        'total_captures': 0,
                        'successful_captures': 0,
                        'total_detections': 0,
                        'notifications_sent': 0,
                        'error_count': 0,
                        'consecutive_failures': 0
                    })
                
                # Reset historiques
                self.alerts_history = []
                self.alerts_with_screenshots = []
                self.latest_detections = {}
                
                log_info("Statistiques réinitialisées via interface web")
                return jsonify({'success': True, 'message': 'Statistiques réinitialisées'})
            except Exception as e:
                log_error(f"Erreur réinitialisation stats: {e}")
                return jsonify({'success': False, 'error': str(e)})
    
    def format_windows_state(self):
        """Formate l'état des fenêtres pour l'API"""
        formatted = {}
        
        for source_name, state in self.windows_state.items():
            total_captures = state.get('total_captures', 0)
            successful_captures = state.get('successful_captures', 0)
            
            formatted[source_name] = {
                'source_name': source_name,
                'status': self.get_status_text(state),
                'status_color': self.get_status_color(state),
                'last_capture_time': state.get('last_capture_time'),
                'last_capture_relative': self.get_relative_time(state.get('last_capture_time')),
                'last_alert_name': state.get('last_alert_name', 'Aucune'),
                'last_alert_state': state.get('last_alert_state', False),
                'last_confidence': state.get('last_confidence', 0.0),
                'confidence_percent': f"{state.get('last_confidence', 0.0):.1%}",
                'total_detections': state.get('total_detections', 0),
                'notifications_sent': state.get('notifications_sent', 0),
                'success_rate': (successful_captures / max(total_captures, 1)) * 100,
                'error_count': state.get('error_count', 0),
                'last_error': state.get('last_error'),
                'performance_ms': state.get('performance_ms', 0),
                'consecutive_failures': state.get('consecutive_failures', 0),
                'has_screenshot': source_name in self.latest_screenshots,
                'has_detection': source_name in self.latest_detections,
                'screenshot_url': f"/api/screenshot/{source_name}?t={int(time.time())}",
                'detection_url': f"/api/detection/{source_name}?t={int(time.time())}"
            }
            
        return formatted
    
    def get_status_text(self, state):
        """Détermine le texte de statut"""
        consecutive_failures = state.get('consecutive_failures', 0)
        alert_state = state.get('last_alert_state', False)
        
        if consecutive_failures >= 5:
            return 'ERREUR'
        elif alert_state:
            return 'ALERTE'
        elif consecutive_failures > 0:
            return 'Instable'
        else:
            return 'OK'
    
    def get_status_color(self, state):
        """Détermine la couleur de statut"""
        consecutive_failures = state.get('consecutive_failures', 0)
        alert_state = state.get('last_alert_state', False)
        
        if consecutive_failures >= 5:
            return 'danger'
        elif alert_state:
            return 'warning'
        elif consecutive_failures > 0:
            return 'info'
        else:
            return 'success'
    
    def get_relative_time(self, timestamp_str):
        """Convertit un timestamp en temps relatif"""
        if not timestamp_str:
            return 'Jamais'
            
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            diff = now - timestamp
            
            if diff.total_seconds() < 60:
                return f"{int(diff.total_seconds())}s"
            elif diff.total_seconds() < 3600:
                return f"{int(diff.total_seconds() // 60)}min"
            else:
                return f"{int(diff.total_seconds() // 3600)}h"
        except:
            return timestamp_str
    
    def format_global_stats(self):
        """Formate les statistiques globales"""
        return {
            'start_time': self.global_stats.get('start_time'),
            'total_cycles': self.global_stats.get('total_cycles', 0),
            'obs_reconnections': self.global_stats.get('obs_reconnections', 0),
            'uptime_seconds': time.time() - self.global_stats.get('start_time', time.time())
        }
    
    def calculate_uptime(self):
        """Calcule le temps de fonctionnement"""
        start_time = self.global_stats.get('start_time', time.time())
        uptime_seconds = time.time() - start_time
        
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def update_data(self, windows_state, global_stats):
        """Met à jour les données depuis le thread principal"""
        self.windows_state = windows_state
        self.global_stats = global_stats
    
    def add_alert(self, source_name, alert_name, confidence, screenshot=None, detection_area=None):
        """Ajoute une alerte à l'historique avec screenshot obligatoire"""
        timestamp = datetime.now()
        
        # Alerte simple pour l'historique rapide
        alert_entry = {
            'timestamp': timestamp.isoformat(),
            'source_name': source_name,
            'alert_name': alert_name,
            'confidence': confidence,
            'confidence_percent': f"{confidence:.1%}",
            'detection_area': detection_area
        }
        
        self.alerts_history.append(alert_entry)
        
        # NOUVEAU: Alerte avec screenshot pour l'historique détaillé
        if screenshot is not None:
            screenshot_filename = self._save_alert_screenshot(source_name, screenshot, alert_name, detection_area, timestamp)
            
            if screenshot_filename:
                alert_with_screenshot = {
                    'timestamp': timestamp.isoformat(),
                    'source_name': source_name,
                    'alert_name': alert_name,
                    'confidence': confidence,
                    'confidence_percent': f"{confidence:.1%}",
                    'detection_area': detection_area,
                    'screenshot_filename': screenshot_filename,
                    'screenshot_url': f"/api/alert_screenshot/{screenshot_filename}",
                    'relative_time': '0s'  # Sera mis à jour côté client
                }
                
                self.alerts_with_screenshots.append(alert_with_screenshot)
                
                # Garder seulement les 10 dernières alertes avec screenshots
                if len(self.alerts_with_screenshots) > 10:
                    # Supprimer les anciens fichiers
                    old_alert = self.alerts_with_screenshots[0]
                    old_filepath = f"static/alerts/{old_alert['screenshot_filename']}"
                    try:
                        if os.path.exists(old_filepath):
                            os.remove(old_filepath)
                    except Exception as e:
                        log_debug(f"Erreur suppression ancien screenshot: {e}")
                    
                    self.alerts_with_screenshots = self.alerts_with_screenshots[-10:]
                
                log_info(f"Alerte avec screenshot ajoutée: {alert_name} - {screenshot_filename}")
        
        # Garder seulement les 1000 dernières alertes simples
        if len(self.alerts_history) > 1000:
            self.alerts_history = self.alerts_history[-1000:]
    
    def _save_alert_screenshot(self, source_name, screenshot, alert_name, detection_area, timestamp):
        """Sauvegarde un screenshot d'alerte avec zone de détection"""
        try:
            clean_source = source_name.replace(' ', '_').replace('!', '')
            clean_alert = alert_name.replace(' ', '_').replace('!', '')
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Inclure millisecondes
            
            # Créer une copie du screenshot avec la zone marquée
            marked_screenshot = screenshot.copy()
            
            if detection_area and 'x' in detection_area:
                x = detection_area['x']
                y = detection_area['y']
                w = detection_area['width']
                h = detection_area['height']
                
                # Dessiner un rectangle vert épais autour de la zone détectée
                cv2.rectangle(marked_screenshot, (x, y), (x + w, y + h), (0, 255, 0), 4)
                
                # Ajouter le nom de l'alerte avec fond semi-transparent
                text = f"{alert_name} ({timestamp.strftime('%H:%M:%S')})"
                text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
                
                # Fond semi-transparent pour le texte
                overlay = marked_screenshot.copy()
                cv2.rectangle(overlay, (x, y-35), (x + text_size[0] + 10, y), (0, 255, 0), -1)
                cv2.addWeighted(overlay, 0.7, marked_screenshot, 0.3, 0, marked_screenshot)
                
                # Texte par-dessus
                cv2.putText(marked_screenshot, text, (x + 5, y-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
            
            # Nom de fichier unique
            filename = f"{clean_source}_{clean_alert}_{timestamp_str}.png"
            filepath = f"static/alerts/{filename}"
            
            success = cv2.imwrite(filepath, marked_screenshot)
            if success:
                log_debug(f"Screenshot d'alerte sauvé: {filepath}")
                return filename
            else:
                log_error(f"Échec sauvegarde screenshot alerte: {filepath}")
                
        except Exception as e:
            log_error(f"Erreur sauvegarde screenshot alerte: {e}")
            
        return None
    
    def update_screenshot(self, source_name, screenshot, has_alert=False, alert_name=None):
        """Met à jour le screenshot pour une source (même sans alerte)"""
        try:
            if screenshot is None:
                return None
                
            timestamp = datetime.now()
            clean_source = source_name.replace(' ', '_').replace('!', '')
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"{clean_source}_latest.png"  # MODIFIÉ: nom de fichier constant
            
            # Sauvegarder l'image
            filepath = f"static/screenshots/{filename}"
            
            success = cv2.imwrite(filepath, screenshot)
            if not success:
                log_error(f"Échec cv2.imwrite pour {filepath}")
                return None
            
            # Mettre à jour le dernier screenshot pour cette source
            self.latest_screenshots[source_name] = {
                'timestamp': timestamp.isoformat(),
                'screenshot_path': filepath,
                'has_alert': has_alert
            }
            
            return filename
            
        except Exception as e:
            log_error(f"Erreur mise à jour screenshot: {e}")
            return None
    
    def cleanup_old_screenshots(self, max_files=20):
        """Nettoie les anciens screenshots des sources (pas les alertes)"""
        try:
            screenshots_dir = "static/screenshots"
            if not os.path.exists(screenshots_dir):
                return
            
            # Lister tous les fichiers PNG sauf les _latest.png
            files = [f for f in os.listdir(screenshots_dir) 
                    if f.endswith('.png') and not f.endswith('_latest.png')]
            
            # Trier par date de modification
            files.sort(key=lambda f: os.path.getmtime(os.path.join(screenshots_dir, f)))
            
            # Supprimer les plus anciens
            files_to_delete = files[:-max_files] if len(files) > max_files else []
            
            for old_file in files_to_delete:
                try:
                    os.remove(os.path.join(screenshots_dir, old_file))
                except Exception as e:
                    log_debug(f"Erreur suppression {old_file}: {e}")
                    
            if files_to_delete:
                log_debug(f"Nettoyage screenshots: {len(files_to_delete)} fichiers supprimés")
                        
        except Exception as e:
            log_error(f"Erreur nettoyage screenshots: {e}")
    
    def start(self):
        """Démarre le serveur web dans un thread séparé"""
        if not self.running:
            self.running = True
            self.server_thread = threading.Thread(
                target=self._run_server,
                daemon=True
            )
            self.server_thread.start()
            log_info(f"Interface web démarrée sur http://localhost:{self.port}")
    
    def _run_server(self):
        """Lance le serveur Flask"""
        try:
            # Désactiver les logs Flask en mode non-debug
            if not self.debug:
                import logging
                flask_log = logging.getLogger('werkzeug')
                flask_log.setLevel(logging.ERROR)
            
            self.app.run(
                host='0.0.0.0',
                port=self.port,
                debug=False,
                use_reloader=False,
                threaded=True
            )
        except Exception as e:
            log_error(f"Erreur serveur web: {e}")
    
    def stop(self):
        """Arrête le serveur web"""
        self.running = False
        log_info("Arrêt du serveur web demandé")

# Instance globale
webapp_manager = None

def init_webapp(port=5000, debug=False):
    """Initialise l'interface web"""
    global webapp_manager
    webapp_manager = WebAppManager(port, debug)
    return webapp_manager

def start_webapp():
    """Démarre l'interface web"""
    global webapp_manager
    if webapp_manager:
        webapp_manager.start()

def update_webapp_data(windows_state, global_stats):
    """Met à jour les données de l'interface web"""
    global webapp_manager
    if webapp_manager:
        webapp_manager.update_data(windows_state, global_stats)

def add_webapp_alert(source_name, alert_name, confidence, screenshot=None, detection_area=None):
    """Ajoute une alerte à l'interface web avec screenshot obligatoire"""
    global webapp_manager
    if webapp_manager:
        webapp_manager.add_alert(source_name, alert_name, confidence, screenshot, detection_area)

def update_webapp_screenshot(source_name, screenshot, has_alert=False, alert_name=None):
    """Met à jour le screenshot pour une source"""
    global webapp_manager
    if webapp_manager:
        result = webapp_manager.update_screenshot(source_name, screenshot, has_alert, alert_name)
        return result
    return None

def stop_webapp():
    """Arrête l'interface web"""
    global webapp_manager
    if webapp_manager:
        webapp_manager.stop()