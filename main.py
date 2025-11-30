# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Main.py modifié pour utiliser le système unifié de configuration
Compatible avec l'interface web et config_manager
"""

from win10toast import ToastNotifier
import time
import threading
import numpy as np
from queue import Queue
from collections import defaultdict
import json

# Import du système unifié
from config_manager import config_manager
from webapp import webapp_manager, init_webapp, start_webapp, update_webapp_data, stop_webapp, register_pause_callback, is_webapp_paused, set_webapp_pause_state, update_webapp_screenshot, update_webapp_screenshot_with_detection
# Imports existants
from config import CHECK_INTERVAL, WINDOW_RETRY_INTERVAL, SOURCE_WINDOWS
from capture import (
    capture_window, initialize_capture_system, is_obs_connected, 
    cleanup_capture_system, get_capture_statistics, get_window_capture_info,
    optimize_capture_method, is_window_valid
)
from detection import check_for_alert, cleanup_template_cache_if_needed
from webapp import (init_webapp, start_webapp, update_webapp_data, 
                   stop_webapp, register_pause_callback, 
                   is_webapp_paused, set_webapp_pause_state)
from utils import log_error, log_info, log_debug, log_warning

# Variables globales pour la gestion de pause
SYSTEM_PAUSED = False
PAUSE_LOCK = threading.Lock()


def is_black_screen(screenshot, threshold=10):
    """Détecte si l'écran est noir de manière plus robuste"""
    if screenshot is None:
        return False
    
    try:
        mean_val = np.mean(screenshot)
        std_val = np.std(screenshot)
        return mean_val < threshold and std_val < 5
    except Exception as e:
        log_error(f"Erreur détection écran noir: {e}")
        return False


def pause_system():
    """Met le système en pause"""
    global SYSTEM_PAUSED
    with PAUSE_LOCK:
        SYSTEM_PAUSED = True
        set_webapp_pause_state(True)
        log_info("🛑 Système mis en PAUSE - Détections arrêtées")


def resume_system():
    """Reprend le système"""
    global SYSTEM_PAUSED
    with PAUSE_LOCK:
        SYSTEM_PAUSED = False
        set_webapp_pause_state(False)
        log_info("▶️ Système REPRIS - Détections actives")


def is_system_paused():
    """Vérifie si le système est en pause (local ou webapp)"""
    global SYSTEM_PAUSED
    with PAUSE_LOCK:
        webapp_paused = is_webapp_paused()
        return SYSTEM_PAUSED or webapp_paused


def toggle_pause():
    """Bascule entre pause et reprise"""
    if is_system_paused():
        resume_system()
        return False
    else:
        pause_system()
        return True


def webapp_pause_callback(paused):
    """Callback appelé quand l'état de pause change dans l'interface web"""
    global SYSTEM_PAUSED
    with PAUSE_LOCK:
        SYSTEM_PAUSED = paused
        status = "pause" if paused else "repris"
        icon = "🛑" if paused else "▶️"
        log_info(f"{icon} Système {status} via interface web")


class NotificationQueue:
    def __init__(self):
        self.queue = Queue()
        self.toaster = ToastNotifier()
        self.active = True
        self.thread = threading.Thread(target=self._process_notifications, daemon=True)
        self.thread.start()
        
    def _process_notifications(self):
        while self.active:
            try:
                if not self.queue.empty():
                    notification = self.queue.get(timeout=1)
                    self.toaster.show_toast(
                        notification['title'],
                        notification['message'],
                        duration=notification.get('duration', 10)
                    )
                    time.sleep(2)
                else:
                    time.sleep(0.1)
            except Exception as e:
                log_error(f"Erreur notification queue: {e}")
                
    def add_notification(self, title, message, duration=10, priority=5):
        try:
            self.queue.put({
                'title': title,
                'message': message,
                'duration': duration
            }, timeout=1)
            return True
        except:
            log_error("Queue de notifications pleine")
            return False
            
    def stop(self):
        self.active = False


class CaptureSystemManager:
    """
    Gestionnaire du système de capture directe
    Remplace l'OBSManager pour une interface compatible
    """
    def __init__(self):
        self.connected = False
        self.reconnection_attempts = 0
        self.max_reconnection_attempts = 5
        
    def connect(self, max_retries=3):
        """Initialise le système de capture directe"""
        for attempt in range(max_retries):
            try:
                log_info(f"🔌 Initialisation système de capture (tentative {attempt + 1}/{max_retries})")
                
                success = initialize_capture_system(SOURCE_WINDOWS)
                
                if success:
                    self.connected = True
                    self.reconnection_attempts = 0
                    log_info("✅ Système de capture directe initialisé")
                    return True
                else:
                    log_error(f"❌ Échec initialisation système capture (tentative {attempt + 1})")
                    time.sleep(2)
                    
            except Exception as e:
                log_error(f"Erreur initialisation capture: {e}")
                time.sleep(2)
                
        log_error("❌ Impossible d'initialiser le système de capture")
        return False
        
    def disconnect(self):
        """Nettoie le système de capture"""
        if self.connected:
            try:
                cleanup_capture_system()
                log_info("✅ Système de capture nettoyé")
            except Exception as e:
                log_error(f"Erreur nettoyage système capture: {e}")
            finally:
                self.connected = False
                
    def is_connected(self):
        """Vérifie l'état de connexion"""
        if self.connected:
            return is_obs_connected()
        return False
    
    def reconnect(self):
        """Tente une reconnexion"""
        if self.reconnection_attempts >= self.max_reconnection_attempts:
            log_error(f"❌ Trop de tentatives de reconnexion")
            return False
        
        self.reconnection_attempts += 1
        log_info(f"🔄 Reconnexion système capture")
        
        self.disconnect()
        time.sleep(1)
        
        success = self.connect(max_retries=2)
        if success:
            log_info("✅ Reconnexion réussie")
        
        return success


def get_sources_from_webapp():
    """Récupère les sources depuis webapp_manager ou utilise SOURCE_WINDOWS par défaut"""
    try:
        # Si webapp_manager existe et a windows_state
        if webapp_manager and hasattr(webapp_manager, 'windows_state') and webapp_manager.windows_state:
            sources = []
            for source_name in webapp_manager.windows_state.keys():
                # Trouver le titre de fenêtre correspondant
                window_title = source_name  # Par défaut
                for win in SOURCE_WINDOWS:
                    if win["source_name"] == source_name:
                        window_title = win["window_title"]
                        break
                
                sources.append({
                    "source_name": source_name,
                    "window_title": window_title
                })
            return sources
    except:
        pass
    
    # Sinon, utiliser SOURCE_WINDOWS par défaut
    return SOURCE_WINDOWS


def main():
    notification_queue = NotificationQueue()
    capture_manager = CaptureSystemManager()

    # Initialisation de l'interface web EN PREMIER
    webapp = init_webapp(port=5000, debug=False)
    register_pause_callback(webapp_pause_callback)
    start_webapp()
    log_info("🌐 Interface web disponible sur http://localhost:5000")
    
    # Attendre un peu que webapp_manager soit initialisé
    time.sleep(1)
    
    # MAINTENANT on peut récupérer les sources
    initial_sources = get_sources_from_webapp()
    
    # État par fenêtre
    windows_state = {}
    
    for win in initial_sources:
        source_name = win["source_name"]
        windows_state[source_name] = {
            "last_notification_time": 0,
            "last_alert_state": False,
            "last_alert_name": None,
            "last_capture_time": None,
            "last_confidence": 0.0,
            "consecutive_detections": 0,
            "consecutive_failures": 0,
            "total_captures": 0,
            "successful_captures": 0,
            "total_detections": 0,
            "notifications_sent": 0,
            "last_error": None,
            "error_count": 0,
            "performance_ms": 0,
            "last_black_screen_notification": 0,
            "window_title": win.get("window_title"),
            "capture_method": win.get("capture_method", "auto")
        }
        
        # Ajouter un état par alerte pour les cooldowns
        for alert_name in config_manager.config.get("alerts", {}).keys():
            windows_state[source_name][f"last_{alert_name}_time"] = 0

    # Statistiques globales
    global_stats = {
        "start_time": time.time(),
        "total_cycles": 0,
        "capture_reconnections": 0,
        "last_status_save": 0,
        "pause_count": 0,
        "total_paused_time": 0,
        "capture_mode": "direct_capture"
    }

    pause_start_time = None

    try:
        # Initialisation système de capture
        if not capture_manager.connect():
            log_error("❌ Impossible d'initialiser le système de capture")
            return

        log_info("=== Démarrage du système de détection d'alertes ===")
        log_info("🚀 Mode: Système unifié avec config_manager")
        log_info(f"📊 {len(config_manager.config.get('alerts', {}))} alertes configurées")
        log_info(f"🎯 {len(windows_state)} sources actives: {', '.join(windows_state.keys())}")
        
        # Afficher les alertes actives
        log_info("\n📋 Alertes configurées:")
        for alert_name, alert_config in config_manager.config.get("alerts", {}).items():
            if alert_config.get("enabled", False):
                templates_count = len(alert_config.get("templates", []))
                log_info(f"   ✅ {alert_name}: {templates_count} template(s), seuil: {alert_config.get('threshold', 0.7)}")
        
        while True:
            try:
                cycle_start = time.time()
                current_time = time.time()
                global_stats["total_cycles"] += 1

                # Gestion de la pause
                if is_system_paused():
                    if pause_start_time is None:
                        pause_start_time = current_time
                        global_stats["pause_count"] += 1
                        log_info("⏸️ Système en pause")
                    
                    update_webapp_data(windows_state, global_stats)
                    time.sleep(1)
                    continue
                else:
                    if pause_start_time is not None:
                        pause_duration = current_time - pause_start_time
                        global_stats["total_paused_time"] += pause_duration
                        log_info(f"▶️ Reprise après {pause_duration:.1f}s de pause")
                        pause_start_time = None

                # Nettoyage périodique
                if global_stats["total_cycles"] % 100 == 0:
                    cleanup_template_cache_if_needed()

                # Vérification système de capture
                if not capture_manager.is_connected():
                    log_error("❌ Système de capture déconnecté")
                    if capture_manager.reconnect():
                        global_stats["capture_reconnections"] += 1
                    else:
                        time.sleep(WINDOW_RETRY_INTERVAL)
                        continue

                # Récupérer les sources actuelles
                current_sources = get_sources_from_webapp()
                
                for win in current_sources:
                    source_name = win["source_name"]
                    window_title = win["window_title"]
                    
                    # Créer l'état si nouvelle source
                    if source_name not in windows_state:
                        windows_state[source_name] = {
                            "last_notification_time": 0,
                            "last_alert_state": False,
                            "last_alert_name": None,
                            "last_capture_time": None,
                            "last_confidence": 0.0,
                            "consecutive_detections": 0,
                            "consecutive_failures": 0,
                            "total_captures": 0,
                            "successful_captures": 0,
                            "total_detections": 0,
                            "notifications_sent": 0,
                            "last_error": None,
                            "error_count": 0,
                            "performance_ms": 0,
                            "last_black_screen_notification": 0,
                            "window_title": window_title,
                            "capture_method": "auto"
                        }
                        for alert_name in config_manager.config.get("alerts", {}).keys():
                            windows_state[source_name][f"last_{alert_name}_time"] = 0
                    
                    state = windows_state[source_name]
                    
                    capture_start = time.time()
                    state["total_captures"] += 1

                    try:
                        # Capture
                        screenshot = capture_window(None, source_name, window_title)
                        capture_time = (time.time() - capture_start) * 1000
                        state["performance_ms"] = capture_time

                        if screenshot is None:
                            state["consecutive_failures"] += 1
                            state["last_error"] = "Capture échouée"
                            state["error_count"] += 1
                            
                            # DIAGNOSTIC DÉTAILLÉ
                            log_warning(f"Échec capture {source_name}")
                            log_error(f"❌ Échec {source_name}:")
                            log_error(f"   Fenêtre: {window_title}")
                            log_error(f"   Échecs consécutifs: {state['consecutive_failures']}")
                            
                            # Obtenir infos détaillées
                            try:
                                from capture import multi_capture
                                if window_title in multi_capture.capturers:
                                    capturer = multi_capture.capturers[window_title]
                                    window_info = capturer.get_window_info()
                                    
                                    if window_info:
                                        log_error(f"   Visible: {window_info.get('is_visible')}")
                                        log_error(f"   Minimisée: {window_info.get('is_minimized')}")
                                        log_error(f"   Taille: {window_info.get('width')}x{window_info.get('height')}")
                                        log_error(f"   Handle: {capturer.hwnd}")
                                        log_error(f"   Dernière méthode réussie: {capturer.last_successful_method}")
                                        
                                        # Vérifier les stats de chaque méthode
                                        method_stats = capturer.capture_stats.get('method_stats', {})
                                        log_error(f"   Stats méthodes:")
                                        for method, stats in method_stats.items():
                                            if stats.get('attempts', 0) > 0:
                                                success_rate = (stats['successes'] / stats['attempts']) * 100
                                                log_error(f"      {method}: {success_rate:.0f}% ({stats['successes']}/{stats['attempts']})")
                            except Exception as e:
                                log_error(f"   Erreur diagnostic: {e}")
                            
                            # Réinitialisation progressive
                            if state["consecutive_failures"] == 3:
                                log_error(f"   🔄 Tentative 1: Réinitialisation méthode + handle...")
                                try:
                                    from capture import multi_capture
                                    if window_title in multi_capture.capturers:
                                        capturer = multi_capture.capturers[window_title]
                                        old_hwnd = capturer.hwnd
                                        
                                        # FORCER rotation méthodes
                                        capturer.last_successful_method = None
                                        log_info(f"   🔄 Réinitialisation méthode de capture")
                                        
                                        # Réinitialiser handle
                                        capturer.hwnd = None
                                        
                                        if capturer.find_window():
                                            log_info(f"   ✅ Handle: {old_hwnd} → {capturer.hwnd}")
                                            state["consecutive_failures"] = 0
                                        else:
                                            log_warning(f"   ❌ Fenêtre introuvable")
                                except Exception as e:
                                    log_error(f"   Erreur: {e}")
                            
                            elif state["consecutive_failures"] == 6:
                                log_error(f"   🔄 Tentative 2: Recréation complète du capturer...")
                                try:
                                    from capture import recreate_capturer
                                    if recreate_capturer(window_title):
                                        log_info(f"   ✅ Capturer recréé")
                                        state["consecutive_failures"] = 0
                                    else:
                                        log_warning(f"   ❌ Échec recréation")
                                except Exception as e:
                                    log_error(f"   Erreur recréation: {e}")
                            
                            elif state["consecutive_failures"] >= 10:
                                log_error(f"   ⏸️ Tentative 3: Pause de 15 secondes...")
                                time.sleep(15)
                                state["consecutive_failures"] = 0
                                
                                try:
                                    from capture import recreate_capturer
                                    recreate_capturer(window_title)
                                    log_info(f"   🔄 Capturer recréé après pause")
                                except Exception as e:
                                    log_error(f"   Erreur: {e}")
                            
                            time.sleep(WINDOW_RETRY_INTERVAL)
                            continue

                        # Variables de détection
                        alert_detected = False
                        current_alert_name = None
                        max_confidence = 0.0
                        detection_area = None

                        # Vérification écran noir
                        if is_black_screen(screenshot):
                            current_black_screen_time = current_time
                            last_black_screen_notification = state.get("last_black_screen_notification", 0)
                            
                            if current_black_screen_time - last_black_screen_notification > 60:
                                notification_queue.add_notification(
                                    f"⚫ Écran Noir - {source_name}",
                                    f"Écran noir détecté sur {source_name}",
                                    8
                                )
                                state["last_black_screen_notification"] = current_black_screen_time
                            
                            state["consecutive_failures"] += 1
                            state["last_error"] = "Écran noir"
                            
                            # Mettre à jour le screenshot
                            update_webapp_screenshot_with_detection(source_name, screenshot)
                        else:
                            # Reset erreurs
                            if state.get("last_error") and "noir" in state.get("last_error", "").lower():
                                state["consecutive_failures"] = 0
                                state["last_error"] = None

                            state["successful_captures"] += 1

                            # DÉTECTION AVEC SYSTÈME UNIFIÉ
                            for alert_name, alert_config in config_manager.config.get("alerts", {}).items():
                                if not alert_config.get("enabled", True):
                                    continue
                                
                                try:
                                    # Appel à la nouvelle fonction
                                    result = check_for_alert(screenshot, alert_name, source_name=source_name)
                                    
                                    if result:
                                        confidence = result.get('confidence', 0.0)
                                        
                                        if confidence > max_confidence:
                                            alert_detected = True
                                            current_alert_name = alert_name
                                            max_confidence = confidence
                                            detection_area = {
                                                'x': result.get('x', 0),
                                                'y': result.get('y', 0),
                                                'width': result.get('width', 100),
                                                'height': result.get('height', 100)
                                            }
                                        
                                        # Gestion du cooldown
                                        last_alert_time = state.get(f"last_{alert_name}_time", 0)
                                        cooldown = alert_config.get("cooldown", 300)
                                        
                                        if current_time - last_alert_time > cooldown:
                                            # Notification
                                            title = f"🚨 {alert_name} - {source_name}"
                                            message = f"Détection: {confidence:.1%}"
                                            
                                            notification_queue.add_notification(title, message, priority=5)
                                            state[f"last_{alert_name}_time"] = current_time
                                            state["notifications_sent"] += 1
                                            state["total_detections"] += 1
                                            
                                            log_info(f"✅ ALERTE: {alert_name} sur {source_name} ({confidence:.1%})")
                                
                                except Exception as e:
                                    log_error(f"Erreur vérification {alert_name}: {e}")

                            state["last_confidence"] = max_confidence
                            state["last_alert_state"] = alert_detected
                            state["last_alert_name"] = current_alert_name
                            state["last_capture_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Réinitialiser les échecs après succès
                            if state["consecutive_failures"] > 0:
                                log_debug(f"Réinitialisation échecs pour {source_name}")
                                state["consecutive_failures"] = 0
                                state["last_error"] = None

                            # Mettre à jour le screenshot avec détection
                            if alert_detected and detection_area:
                                update_webapp_screenshot_with_detection(
                                    source_name,
                                    screenshot,
                                    detection_area if alert_detected else None,
                                    current_alert_name if alert_detected else None,
                                    max_confidence if alert_detected else 0.0
                                )
                            else:
                                update_webapp_screenshot_with_detection(source_name, screenshot)

                    except Exception as e:
                        state["error_count"] += 1
                        state["last_error"] = str(e)
                        log_error(f"Erreur traitement {source_name}: {e}")

                # Mise à jour interface web
                update_webapp_data(windows_state, global_stats)
                
                # Affichage console
                if global_stats["total_cycles"] % 10 == 0:
                    active_sources = sum(1 for s in windows_state.values() 
                                       if s.get('consecutive_failures', 0) < 5)
                    total_detections = sum(s.get('total_detections', 0) 
                                         for s in windows_state.values())
                    
                    log_info(f"📊 Cycle {global_stats['total_cycles']}: "
                           f"{active_sources}/{len(windows_state)} sources, "
                           f"{total_detections} détections")
                
                # Sauvegarde périodique
                if current_time - global_stats["last_status_save"] > 300:
                    save_statistics(windows_state, global_stats)
                    global_stats["last_status_save"] = current_time

                # Attente
                cycle_duration = time.time() - cycle_start
                sleep_time = max(0.1, CHECK_INTERVAL - cycle_duration)
                time.sleep(sleep_time)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                log_error(f"Erreur boucle principale: {e}")
                time.sleep(WINDOW_RETRY_INTERVAL)

    except KeyboardInterrupt:
        log_info("Arrêt demandé")
    except Exception as e:
        log_error(f"Erreur critique: {e}")
    finally:
        log_info("🛑 Arrêt du système...")
        
        if pause_start_time is not None:
            global_stats["total_paused_time"] += time.time() - pause_start_time
        
        notification_queue.stop()
        capture_manager.disconnect()
        stop_webapp()
        save_statistics(windows_state, global_stats)
        
        log_info("=== Arrêt du système ===")
        print("\n🎮 Last War Alerts arrêté")
        input("Appuyez sur Entrée pour quitter...")


def save_statistics(windows_state, global_stats):
    """Sauvegarde les statistiques"""
    try:
        stats_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "global_stats": global_stats,
            "windows_state": {},
            "system_paused": is_system_paused()
        }
        
        for source, state in windows_state.items():
            clean_state = {}
            for key, value in state.items():
                if isinstance(value, (int, float, str, bool, type(None))):
                    clean_state[key] = value
            stats_data["windows_state"][source] = clean_state
        
        with open("alert_statistics.json", "w", encoding="utf-8") as f:
            json.dump(stats_data, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        log_error(f"Erreur sauvegarde: {e}")


if __name__ == "__main__":
    main()