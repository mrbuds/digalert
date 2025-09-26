#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Last War Alerts - Version 3.0 Refactorisée
Point d'entrée principal - VERSION CORRIGÉE
"""

import sys
import time
import threading
import os
from pathlib import Path

# Ajouter le dossier racine au path AVANT les imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Imports après ajout du path
from core.constants import CHECK_INTERVAL
from utils.logging import setup_logging, get_logger

# Import conditionnel pour éviter les erreurs circulaires
try:
    from core.config_manager import config_manager
except ImportError as e:
    print(f"Erreur import config_manager: {e}")
    # Créer un config_manager minimal
    class ConfigManager:
        def __init__(self):
            self.config = {
                "sources": [],
                "alerts": {}
            }
    config_manager = ConfigManager()

try:
    from core.capture import capture_manager
except ImportError as e:
    print(f"Erreur import capture_manager: {e}")
    # Créer un capture_manager minimal
    class CaptureManager:
        def __init__(self):
            self.capturers = {}
        def add_source(self, name, title): pass
        def capture_source(self, name): return None
    capture_manager = CaptureManager()

try:
    from core.detection import AlertDetector
except ImportError as e:
    print(f"Erreur import AlertDetector: {e}")
    # Créer un AlertDetector minimal
    class AlertDetector:
        def __init__(self, config): pass
        def check_all_alerts(self, screenshot, source): return {}
    AlertDetector = AlertDetector

try:
    from web.app import web_app
except ImportError as e:
    print(f"Erreur import web_app: {e}")
    # Créer un web_app minimal
    class WebApp:
        def update_state(self, windows, alerts): pass
        def run(self, debug=False): 
            print("Interface web non disponible")
            import time
            time.sleep(1)
    web_app = WebApp()

class LastWarApplication:
    """Application principale refactorisée"""
    
    def __init__(self):
        try:
            self.logger = setup_logging()
        except Exception as e:
            print(f"Erreur setup logging: {e}")
            import logging
            self.logger = logging.getLogger()
            
        try:
            self.detector = AlertDetector(config_manager)
        except Exception as e:
            print(f"Erreur création detector: {e}")
            self.detector = None
            
        self.running = False
        
        # États
        self.windows_state = {}
        self.alerts_history = []
        
    def initialize(self):
        """Initialise l'application"""
        try:
            self.logger.info("INIT - Initialisation de Last War Alerts v3.0")
        except:
            print("INIT - Initialisation de Last War Alerts v3.0")
        
        # Vérifier la configuration
        try:
            if not hasattr(config_manager, 'config') or not config_manager.config:
                print("CONFIG - Création configuration par défaut")
                config_manager.config = {
                    "sources": [{
                        "name": "lastwar1",
                        "window_title": "Last War-Survival Game", 
                        "enabled": True
                    }],
                    "alerts": {
                        "Dig!": {"enabled": True, "threshold": 0.7},
                        "EGGGGGG!": {"enabled": True, "threshold": 0.8}
                    }
                }
                
            # Initialiser les sources de capture
            for source_config in config_manager.config.get('sources', []):
                if source_config.get('enabled', True):
                    try:
                        capture_manager.add_source(
                            source_config['name'],
                            source_config['window_title']
                        )
                        print(f"SOURCE - Ajoutée: {source_config['name']}")
                    except Exception as e:
                        print(f"ERREUR - Source {source_config['name']}: {e}")
                        
        except Exception as e:
            print(f"CONFIG - Erreur configuration: {e}")
            return False
            
        print("SUCCESS - Application initialisée avec succès")
        return True
        
    def run_detection_loop(self):
        """Boucle principale de détection"""
        print("LOOP - Démarrage de la boucle de détection")
        
        cycle_count = 0
        
        while self.running:
            try:
                cycle_count += 1
                
                # Affichage périodique d'activité
                if cycle_count % 10 == 0:
                    print(f"CYCLE - Cycle #{cycle_count} - Système actif")
                
                # Capturer toutes les sources
                for source_name in getattr(capture_manager, 'capturers', {}):
                    try:
                        screenshot = capture_manager.capture_source(source_name)
                        
                        if screenshot is not None:
                            print(f"CAPTURE - {source_name}: {screenshot.shape}")
                            
                            # Détecter les alertes si possible
                            if self.detector:
                                try:
                                    results = self.detector.check_all_alerts(screenshot, source_name)
                                    
                                    # Traiter les résultats
                                    for alert_name, result in results.items():
                                        self.handle_detection(source_name, alert_name, result)
                                        
                                    # Mettre à jour l'état
                                    self.update_window_state(source_name, screenshot, results)
                                except Exception as e:
                                    print(f"DETECTION - Erreur détection: {e}")
                        else:
                            if cycle_count % 20 == 0:  # Moins de spam
                                print(f"CAPTURE - {source_name}: Échec")
                                
                    except Exception as e:
                        print(f"ERROR - Erreur source {source_name}: {e}")
                        
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"ERROR - Erreur dans la boucle: {e}")
                time.sleep(1)
                
        print("STOP - Boucle de détection arrêtée")
        
    def handle_detection(self, source_name, alert_name, result):
        """Gère une détection d'alerte"""
        confidence = result.get('confidence', 0)
        print(f"ALERT - {alert_name} sur {source_name} ({confidence:.1%})")
        
        # Ajouter à l'historique
        self.alerts_history.append({
            'timestamp': time.time(),
            'source_name': source_name,
            'alert_name': alert_name,
            'confidence': confidence,
            'detection_area': {
                'x': result.get('x', 0),
                'y': result.get('y', 0),
                'width': result.get('width', 0),
                'height': result.get('height', 0)
            }
        })
        
        # Garder seulement les 100 dernières
        if len(self.alerts_history) > 100:
            self.alerts_history = self.alerts_history[-100:]
            
    def update_window_state(self, source_name, screenshot, results):
        """Met à jour l'état d'une fenêtre"""
        if source_name not in self.windows_state:
            self.windows_state[source_name] = {
                'total_captures': 0,
                'successful_captures': 0,
                'total_detections': 0,
                'last_capture_time': None,
                'last_alert_name': None,
                'last_confidence': 0.0
            }
            
        state = self.windows_state[source_name]
        state['total_captures'] += 1
        state['successful_captures'] += 1
        state['last_capture_time'] = time.time()
        
        if results:
            best_result = max(results.values(), key=lambda x: x.get('confidence', 0))
            state['last_alert_name'] = list(results.keys())[0]
            state['last_confidence'] = best_result.get('confidence', 0)
            state['total_detections'] += len(results)
        else:
            state['last_alert_name'] = None
            state['last_confidence'] = 0.0
            
        # Mettre à jour l'interface web
        try:
            web_app.update_state(self.windows_state, self.alerts_history)
        except Exception as e:
            print(f"WEB - Erreur mise à jour: {e}")
        
    def start_web_interface(self):
        """Démarre l'interface web dans un thread séparé"""
        def run_web():
            try:
                web_app.run(debug=False)
            except Exception as e:
                print(f"WEB - Erreur interface web: {e}")
                print("WEB - Interface web non disponible, continuant sans interface")
        
        web_thread = threading.Thread(target=run_web, daemon=True)
        web_thread.start()
        print("WEB - Interface web démarrée sur http://localhost:5000")
        
    def run(self):
        """Lance l'application complète"""
        if not self.initialize():
            return False
            
        try:
            # Démarrer l'interface web
            self.start_web_interface()
            
            # Attendre un peu que l'interface démarre
            time.sleep(2)
            
            print("="*50)
            print("🎮 LAST WAR ALERTS v3.0 - DÉMARRÉ")
            print("="*50)
            print("🌐 Interface web: http://localhost:5000")
            print("🎯 Sources configurées:")
            for source in config_manager.config.get('sources', []):
                status = "✅" if source.get('enabled') else "❌"
                print(f"   {status} {source['name']}: {source['window_title']}")
            print("⚡ Alertes configurées:")
            for alert_name, alert_config in config_manager.config.get('alerts', {}).items():
                status = "✅" if alert_config.get('enabled') else "❌"
                print(f"   {status} {alert_name}")
            print("🛑 Ctrl+C pour arrêter")
            print("="*50)
            
            # Lancer la boucle de détection
            self.running = True
            self.run_detection_loop()
            
        except KeyboardInterrupt:
            print("\nSTOP - Arrêt demandé par l'utilisateur")
        except Exception as e:
            print(f"ERROR - Erreur fatale: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.running = False
            
        return True

def main():
    """Point d'entrée principal"""
    print("🚀 Démarrage Last War Alerts v3.0...")
    
    app = LastWarApplication()
    success = app.run()
    
    if success:
        print("\n✅ Application terminée avec succès")
    else:
        print("\n❌ Application terminée avec des erreurs")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    input("\nAppuyez sur Entrée pour quitter...")
    sys.exit(exit_code)
