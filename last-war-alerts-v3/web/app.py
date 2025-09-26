# -*- coding: utf-8 -*-
"""
Application web FONCTIONNELLE pour Last War Alerts v3.0
"""

from flask import Flask, render_template, jsonify, request, send_file
import os
import threading
import time
from datetime import datetime
from pathlib import Path

# Imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    from core.config_manager import config_manager
    print("WEB - config_manager importé avec succès")
except ImportError as e:
    print(f"WEB - Erreur import config_manager: {e}")
    # Fallback
    class ConfigManager:
        def __init__(self):
            self.config = {"sources": [], "alerts": {}}
        def save_config(self): return True
        def get_sources(self): return []
        def add_source(self, name, title, enabled=True): return True, "OK"
        def remove_source(self, name): return True, "OK"
        def toggle_source(self, name): return True, "OK"
    config_manager = ConfigManager()

class WebApplication:
    """Application web avec TOUTES les routes nécessaires"""
    
    def __init__(self, port=5000):
        self.app = Flask(__name__, 
                        template_folder='templates', 
                        static_folder='static')
        self.port = port
        self.setup_routes()
        
        # État de l'application
        self.windows_state = {}
        self.alerts_history = []
        self.system_paused = False
        
    def setup_routes(self):
        """Configure TOUTES les routes nécessaires"""
        
        @self.app.route('/')
        def index():
            try:
                return render_template('index.html')
            except Exception as e:
                return f"""
        <html>
        <head><title>Last War Alerts v3.0</title></head>
        <body>
            <h1>🎮 Last War Alerts v3.0</h1>
            <p>Interface démarrée avec succès !</p>
            <h2>API Endpoints:</h2>
            <ul>
                <li><a href="/api/status">Status</a></li>
                <li><a href="/api/sources">Sources</a></li>
                <li><a href="/api/config">Configuration</a></li>
                <li><a href="/api/training/statistics">Training Stats</a></li>
            </ul>
            <p><small>Templates manquants: {e}</small></p>
        </body>
        </html>
        """
            
        @self.app.route('/api/status')
        def api_status():
            """Statut de l'application"""
            return jsonify({
                'timestamp': datetime.now().isoformat(),
                'windows_state': self.windows_state,
                'alerts_history': self.alerts_history[-20:],
                'system_paused': self.system_paused,
                'sources_count': len(config_manager.get_sources()),
                'version': '3.0'
            })
            
        @self.app.route('/api/config')
        def api_config():
            """Configuration complète"""
            return jsonify(config_manager.config)
        
        # ========== ROUTES SOURCES (IMPORTANTES) ==========
        
        @self.app.route('/api/sources')
        def api_sources():
            """Liste toutes les sources - ROUTE PRINCIPALE"""
            try:
                sources = config_manager.get_sources()
                print(f"API - Sources demandées: {len(sources)} trouvée(s)")
                return jsonify({
                    'success': True,
                    'sources': sources,
                    'count': len(sources)
                })
            except Exception as e:
                print(f"API - Erreur sources: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'sources': [],
                    'count': 0
                })
        
        @self.app.route('/api/config/source', methods=['POST'])
        def api_add_source():
            """Ajoute une nouvelle source - ROUTE CRITIQUE"""
            try:
                print("API - Demande d'ajout de source reçue")
                data = request.json
                print(f"API - Données reçues: {data}")
                
                if not data:
                    return jsonify({'success': False, 'error': 'Aucune donnée reçue'})
                
                name = data.get('name', '').strip()
                window_title = data.get('window_title', '').strip()
                enabled = data.get('enabled', True)
                
                print(f"API - Paramètres: name='{name}', title='{window_title}', enabled={enabled}")
                
                if not name:
                    return jsonify({'success': False, 'error': 'Nom de source requis'})
                
                if not window_title:
                    window_title = name  # Utiliser le nom comme titre par défaut
                
                # Ajouter via config_manager
                success, message = config_manager.add_source(name, window_title, enabled)
                
                print(f"API - Résultat ajout: success={success}, message='{message}'")
                
                if success:
                    return jsonify({
                        'success': True,
                        'message': message,
                        'source': {
                            'name': name,
                            'window_title': window_title,
                            'enabled': enabled
                        }
                    })
                else:
                    return jsonify({'success': False, 'error': message})
                
            except Exception as e:
                print(f"API - Erreur ajout source: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': f'Erreur serveur: {str(e)}'})
        
        @self.app.route('/api/config/source/<source_name>', methods=['DELETE'])
        def api_delete_source(source_name):
            """Supprime une source"""
            try:
                success, message = config_manager.remove_source(source_name)
                return jsonify({
                    'success': success,
                    'message': message
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/config/source/<source_name>/toggle', methods=['POST'])
        def api_toggle_source(source_name):
            """Active/désactive une source"""
            try:
                success, message = config_manager.toggle_source(source_name)
                return jsonify({
                    'success': success,
                    'message': message
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        # ========== AUTRES ROUTES ==========
        
        @self.app.route('/api/toggle_pause', methods=['POST'])
        def api_toggle_pause():
            """Bascule pause/reprise"""
            self.system_paused = not self.system_paused
            return jsonify({
                'success': True,
                'paused': self.system_paused,
                'message': f'Système {"en pause" if self.system_paused else "actif"}'
            })
        
        @self.app.route('/api/training/statistics')
        def api_training_statistics():
            """Statistiques d'entraînement (compatibilité)"""
            alerts = config_manager.config.get("alerts", {})
            total_templates = sum(len(alert.get("templates", [])) for alert in alerts.values())
            
            return jsonify({
                'total_annotations': total_templates,
                'manual_annotations': total_templates,
                'alerts_with_templates': len([a for a in alerts.values() if a.get("templates")]),
                'version': '3.0'
            })
        
        @self.app.route('/api/scan_windows', methods=['POST'])
        def api_scan_windows():
            """Scan des fenêtres disponibles"""
            common_windows = [
                'Last War-Survival Game',
                'BlueStacks App Player',
                'NoxPlayer',
                'MEmu',
                'LDPlayer'
            ]
            
            return jsonify({
                'success': True,
                'windows': common_windows,
                'count': len(common_windows)
            })
        
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({
                'error': 'Route non trouvée',
                'path': request.path,
                'available_routes': [
                    'GET /api/status',
                    'GET /api/sources',
                    'POST /api/config/source',
                    'DELETE /api/config/source/<name>',
                    'GET /api/config',
                    'POST /api/toggle_pause'
                ]
            }), 404
        
        # Test de la configuration au démarrage
        @self.app.before_first_request
        def check_config():
            """Vérification au démarrage"""
            sources = config_manager.get_sources()
            print(f"WEBAPP - {len(sources)} source(s) disponible(s) au démarrage")
            for source in sources:
                print(f"  - {source.get('name')}: {source.get('window_title')}")
    
    def update_state(self, windows_state, alerts_history=None):
        """Met à jour l'état"""
        self.windows_state = windows_state or {}
        if alerts_history:
            self.alerts_history = alerts_history
            
    def run(self, debug=False):
        """Lance l'application web"""
        print(f"WEB - Démarrage sur port {self.port}")
        print("WEB - Routes critiques configurées:")
        print("  - GET  /api/sources")  
        print("  - POST /api/config/source")
        print("  - GET  /api/config")
        
        try:
            self.app.run(host='0.0.0.0', port=self.port, debug=debug, threaded=True)
        except Exception as e:
            print(f"WEB - Erreur serveur: {e}")

# Instance globale
web_app = WebApplication()
