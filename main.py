# -*- coding: utf-8 -*-
"""
Main.py modifié pour utiliser la capture directe au lieu d'OBS
Compatible avec les fenêtres cachées et minimisées
"""

from win10toast import ToastNotifier
import time
import threading
import numpy as np
from queue import Queue
from collections import defaultdict
import json

from config import ALERTS, COOLDOWN_PERIOD, CHECK_INTERVAL, WINDOW_RETRY_INTERVAL, SOURCE_WINDOWS
from capture import (
    capture_window, initialize_capture_system, is_obs_connected, 
    cleanup_capture_system, get_capture_statistics
)
from detection import check_for_alert, cleanup_template_cache_if_needed
from webapp import (init_webapp, start_webapp, update_webapp_data, add_webapp_alert, 
                   stop_webapp, update_webapp_screenshot, register_pause_callback, 
                   is_webapp_paused, set_webapp_pause_state)
from utils import log_error, log_info, log_debug


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
                
    def add_notification(self, title, message, duration=10):
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
                
                # Initialiser le système de capture directe
                success = initialize_capture_system(SOURCE_WINDOWS)
                
                if success:
                    self.connected = True
                    self.reconnection_attempts = 0
                    log_info("✅ Système de capture directe initialisé")
                    log_info("🎯 Fonctionnalités activées:")
                    log_info("   • Capture de fenêtres minimisées/cachées")
                    log_info("   • Pas de dépendance OBS")
                    log_info("   • Méthodes de capture multiples avec fallback")
                    return True
                else:
                    log_error(f"❌ Échec initialisation système capture (tentative {attempt + 1})")
                    time.sleep(2)
                    
            except Exception as e:
                log_error(f"Erreur initialisation capture (tentative {attempt + 1}/{max_retries}): {e}")
                time.sleep(2)
                
        log_error("❌ Impossible d'initialiser le système de capture après toutes les tentatives")
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
            # Vérification périodique de l'état
            return is_obs_connected()  # Fonction de compatibilité
        return False
    
    def reconnect(self):
        """Tente une reconnexion"""
        if self.reconnection_attempts >= self.max_reconnection_attempts:
            log_error(f"❌ Trop de tentatives de reconnexion ({self.reconnection_attempts})")
            return False
        
        self.reconnection_attempts += 1
        log_info(f"🔄 Reconnexion système capture (tentative {self.reconnection_attempts})")
        
        self.disconnect()
        time.sleep(1)
        
        success = self.connect(max_retries=2)
        if success:
            log_info("✅ Reconnexion système capture réussie")
        else:
            log_error("❌ Échec reconnexion système capture")
        
        return success


def main():
    notification_queue = NotificationQueue()
    capture_manager = CaptureSystemManager()  # Remplace OBSManager

    # État par fenêtre avec statistiques étendues
    windows_state = {}
    for win in SOURCE_WINDOWS:
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
            "notification_cooldown": win.get("notification_cooldown", COOLDOWN_PERIOD),
            "last_black_screen_notification": 0,
            "window_title": win.get("window_title"),  # NOUVEAU: Garder référence titre fenêtre
            "capture_method": win.get("capture_method", "auto")  # NOUVEAU: Méthode de capture
        }

    # Statistiques globales
    global_stats = {
        "start_time": time.time(),
        "total_cycles": 0,
        "capture_reconnections": 0,  # Remplace obs_reconnections
        "last_status_save": 0,
        "pause_count": 0,
        "total_paused_time": 0,
        "capture_mode": "direct_capture"  # NOUVEAU: Mode de capture
    }

    pause_start_time = None

    try:
        # Initialisation de l'interface web
        webapp = init_webapp(port=5000, debug=False)
        
        # Enregistrer le callback pour synchroniser les états de pause
        register_pause_callback(webapp_pause_callback)
        
        start_webapp()
        log_info("🌐 Interface web disponible sur http://localhost:5000")
        
        # Initialisation système de capture directe (remplace OBS)
        if not capture_manager.connect():
            log_error("❌ Impossible d'initialiser le système de capture. Arrêt du programme.")
            log_error("💡 Vérifiez que les fenêtres cibles sont ouvertes:")
            for win in SOURCE_WINDOWS:
                log_error(f"   - {win['window_title']} (source: {win['source_name']})")
            return

        log_info("=== Démarrage du système de détection d'alertes ===")
        log_info("🚀 Mode: Capture directe (sans OBS)")
        log_info("💡 Contrôles disponibles:")
        log_info("   - Interface web: bouton pause/reprise")
        log_info("   - Raccourci web: ESPACE ou P")
        
        # Afficher les infos des fenêtres détectées
        from capture import get_window_capture_info
        log_info("\n📋 Fenêtres détectées:")
        for win in SOURCE_WINDOWS:
            window_info = get_window_capture_info(win['window_title'])
            if window_info:
                status_icons = []
                if window_info['is_minimized']:
                    status_icons.append("📦 Minimisée")
                if not window_info['is_visible']:
                    status_icons.append("👁️‍🗨️ Cachée")
                if window_info['can_capture_hidden']:
                    status_icons.append("✅ Capture OK")
                
                status_text = " | ".join(status_icons) if status_icons else "Normal"
                
                log_info(f"   🎯 {win['source_name']} ({win['window_title']})")
                log_info(f"      Taille: {window_info['width']}x{window_info['height']}")
                log_info(f"      Processus: {window_info['process_name']}")
                log_info(f"      État: {status_text}")
            else:
                log_info(f"   ❌ {win['source_name']} ({win['window_title']}) - Non trouvée")
        
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
                        log_info("⏸️ Système en pause - En attente de reprise...")
                    
                    # Pendant la pause, maintenir l'interface web
                    update_webapp_data(windows_state, global_stats)
                    time.sleep(1)
                    continue
                else:
                    # Si on sort de pause, calculer le temps de pause
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
                    log_error("❌ Système de capture déconnecté, tentative de reconnexion...")
                    if capture_manager.reconnect():
                        global_stats["capture_reconnections"] += 1
                        log_info("✅ Reconnexion système capture réussie")
                    else:
                        log_error("❌ Échec reconnexion système capture, attente...")
                        time.sleep(WINDOW_RETRY_INTERVAL)
                        continue

                for win in SOURCE_WINDOWS:
                    source_name = win["source_name"]
                    window_title = win["window_title"]
                    state = windows_state[source_name]
                    
                    capture_start = time.time()
                    state["total_captures"] += 1

                    try:
                        # NOUVEAU: Capture directe (sans paramètre ws)
                        screenshot = capture_window(None, source_name, window_title)
                        capture_time = (time.time() - capture_start) * 1000
                        state["performance_ms"] = capture_time

                        if screenshot is None:
                            state["consecutive_failures"] += 1
                            state["last_error"] = "Capture échouée"
                            state["error_count"] += 1
                            log_debug(f"Capture échouée pour {source_name} (échecs consécutifs: {state['consecutive_failures']})")
                            
                            # AMÉLIORATION: Diagnostic spécifique pour capture directe
                            if state["consecutive_failures"] == 1:
                                window_info = get_window_capture_info(window_title)
                                if window_info:
                                    log_debug(f"État fenêtre {source_name}:")
                                    log_debug(f"   Visible: {window_info['is_visible']}")
                                    log_debug(f"   Minimisée: {window_info['is_minimized']}")
                                    log_debug(f"   Taille: {window_info['width']}x{window_info['height']}")
                                else:
                                    log_debug(f"Impossible d'obtenir infos fenêtre: {window_title}")
                            
                            if state["consecutive_failures"] >= 5:
                                log_error(f"Trop d'échecs pour {source_name}, pause longue")
                                
                                # NOUVEAU: Tentative d'optimisation automatique
                                if state["consecutive_failures"] == 5:
                                    log_info(f"🔧 Tentative d'optimisation capture pour {source_name}")
                                    from capture import optimize_capture_method
                                    new_method = optimize_capture_method(source_name, window_title)
                                    if new_method:
                                        state["capture_method"] = new_method
                                        log_info(f"✅ Méthode optimisée: {new_method}")
                                
                                time.sleep(WINDOW_RETRY_INTERVAL)
                            continue

                        # Toujours sauvegarder le dernier screenshot
                        update_webapp_screenshot(source_name, screenshot, False, None)

                        # Vérification d'écran noir (améliorée pour capture directe)
                        if is_black_screen(screenshot):
                            current_black_screen_time = current_time
                            last_black_screen_notification = state.get("last_black_screen_notification", 0)
                            
                            if current_black_screen_time - last_black_screen_notification > 60:
                                black_screen_title = f"⚫ Écran Noir - {source_name}"
                                black_screen_message = f"Écran noir détecté sur {source_name}. La fenêtre est peut-être fermée ou masquée."
                                
                                if notification_queue.add_notification(black_screen_title, black_screen_message, 8):
                                    state["last_black_screen_notification"] = current_black_screen_time
                                    log_info(f"📢 Notification écran noir envoyée pour {source_name}")
                                
                            state["consecutive_failures"] += 1
                            state["last_error"] = f"Écran noir détecté"
                        else:
                            # Reset des erreurs d'écran noir
                            last_error = state.get("last_error")
                            if last_error and "écran noir" in last_error.lower():
                                state["consecutive_failures"] = 0
                                state["last_error"] = None

                        state["successful_captures"] += 1
                        state["last_error"] = None

                        # Détection d'alertes avec zone de détection (inchangé)
                        alert_detected = False
                        current_alert = None
                        max_confidence = 0.0
                        detection_area = None

                        for alert in ALERTS:
                            if not alert.get('enabled', True):
                                continue
                                
                            try:
                                result = check_for_alert(screenshot, alert, return_confidence=True, return_area=True)
                                
                                if isinstance(result, tuple) and len(result) == 2:
                                    confidence, area = result
                                else:
                                    confidence = result
                                    area = None
                                
                                if confidence > max_confidence:
                                    max_confidence = confidence
                                    detection_area = area
                                    
                                if confidence >= alert['threshold']:
                                    alert_detected = True
                                    current_alert = alert
                                    state["last_alert_name"] = alert["name"]
                                    state["total_detections"] += 1
                                    log_info(f"Alerte détectée dans {source_name}: {alert['name']} (confiance: {confidence:.3f})")
                                    break
                            except Exception as e:
                                log_error(f"Erreur lors de la vérification de l'alerte {alert.get('name', 'inconnue')}: {e}")
                                continue

                        state["last_confidence"] = max_confidence

                        # Gestion des détections consécutives
                        if alert_detected:
                            state["consecutive_detections"] += 1
                        else:
                            state["consecutive_detections"] = 0

                        # Logique de notification
                        should_notify = False
                        if alert_detected:
                            time_since_last = current_time - state["last_notification_time"]
                            cooldown = state["notification_cooldown"]
                            
                            if (not state["last_alert_state"]) or \
                               (time_since_last > cooldown and state["consecutive_detections"] >= 3):
                                should_notify = True

                        if should_notify and current_alert:
                            title = f"{source_name} - {current_alert['name']}"
                            message = f"{current_alert['name']} (Confiance: {max_confidence:.1%})"
                            
                            if notification_queue.add_notification(title, message):
                                state["last_notification_time"] = current_time
                                state["notifications_sent"] += 1
                                log_info(f"Notification envoyée pour {source_name}: {current_alert['name']}")
                                
                                add_webapp_alert(source_name, current_alert['name'], max_confidence, 
                                                screenshot, detection_area)
                            else:
                                log_error(f"Échec envoi notification pour {source_name}")

                        state["last_alert_state"] = alert_detected
                        state["last_capture_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

                    except Exception as e:
                        state["error_count"] += 1
                        state["last_error"] = str(e)
                        log_error(f"Erreur traitement {source_name}: {e}")

                # Mise à jour interface web
                update_webapp_data(windows_state, global_stats)
                
                # Affichage console simplifié avec informations capture directe
                if global_stats["total_cycles"] % 10 == 0:
                    cycle_duration = time.time() - cycle_start
                    active_sources = sum(1 for state in windows_state.values() 
                                       if state.get('consecutive_failures', 0) < 5)
                    total_detections = sum(state.get('total_detections', 0) 
                                         for state in windows_state.values())
                    
                    pause_status = " [PAUSE]" if is_system_paused() else ""
                    capture_mode = " [DIRECT]"  # Indicateur mode direct
                    
                    if global_stats["pause_count"] > 0:
                        pause_info = f" (Pauses: {global_stats['pause_count']}, Temps pause: {global_stats['total_paused_time']:.1f}s)"
                    else:
                        pause_info = ""
                    
                    log_info(f"📊 Cycle {global_stats['total_cycles']}: "
                           f"{active_sources}/{len(windows_state)} sources actives, "
                           f"{total_detections} détections, "
                           f"{cycle_duration:.2f}s{capture_mode}{pause_status}{pause_info}")
                
                # Sauvegarde périodique
                if current_time - global_stats["last_status_save"] > 300:
                    save_statistics(windows_state, global_stats)
                    global_stats["last_status_save"] = current_time

                # Calcul du temps d'attente dynamique
                cycle_duration = time.time() - cycle_start
                sleep_time = max(0.1, CHECK_INTERVAL - cycle_duration)
                time.sleep(sleep_time)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                log_error(f"Erreur boucle principale: {e}")
                time.sleep(WINDOW_RETRY_INTERVAL)

    except KeyboardInterrupt:
        log_info("Arrêt demandé par l'utilisateur")
    except Exception as e:
        log_error(f"Erreur critique: {e}")
    finally:
        # Nettoyage
        log_info("🛑 Arrêt du système en cours...")
        
        # Calculer le temps total de pause si on est encore en pause
        if pause_start_time is not None:
            final_pause_duration = time.time() - pause_start_time
            global_stats["total_paused_time"] += final_pause_duration
        
        notification_queue.stop()
        capture_manager.disconnect()  # Remplace obs_manager.disconnect()
        stop_webapp()
        save_statistics(windows_state, global_stats)
        
        # Affichage des statistiques finales avec infos capture directe
        total_uptime = time.time() - global_stats["start_time"]
        active_time = total_uptime - global_stats["total_paused_time"]
        pause_percentage = (global_stats["total_paused_time"] / total_uptime) * 100 if total_uptime > 0 else 0
        
        # Statistiques de capture
        capture_stats = get_capture_statistics()
        
        log_info("=== Statistiques finales ===")
        log_info(f"Mode de capture: {global_stats['capture_mode']}")
        log_info(f"Temps total: {total_uptime:.1f}s")
        log_info(f"Temps actif: {active_time:.1f}s")
        log_info(f"Temps en pause: {global_stats['total_paused_time']:.1f}s ({pause_percentage:.1f}%)")
        log_info(f"Nombre de pauses: {global_stats['pause_count']}")
        log_info(f"Reconnexions capture: {global_stats['capture_reconnections']}")
        log_info(f"Captures réussies: {capture_stats['successful_captures']}/{capture_stats['total_attempts']} ({capture_stats['success_rate']:.1f}%)")
        if capture_stats.get('direct_capture_stats'):
            hidden_support = capture_stats['direct_capture_stats'].get('hidden_window_support', False)
            log_info(f"Support fenêtres cachées: {'✅ Oui' if hidden_support else '❌ Non'}")
        log_info("=== Arrêt du système ===")
        
        print("\n🎮 Last War Alerts arrêté")
        print("✅ Mode capture directe - Aucune dépendance OBS")
        print("Interface web fermée")
        input("Appuyez sur Entrée pour quitter...")


def save_statistics(windows_state, global_stats):
    """Sauvegarde les statistiques dans un fichier JSON"""
    try:
        stats_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "global_stats": {},
            "windows_state": {},
            "system_paused": is_system_paused(),
            "capture_mode": "direct_capture"  # NOUVEAU
        }
        
        # Nettoyage des stats globales
        for key, value in global_stats.items():
            if isinstance(value, (int, float, str, type(None))):
                stats_data["global_stats"][key] = value
            else:
                stats_data["global_stats"][key] = str(value)
        
        # Nettoyage des données des fenêtres
        for source, state in windows_state.items():
            clean_state = {}
            for key, value in state.items():
                if isinstance(value, (int, float, str, type(None))):
                    clean_state[key] = value
                elif isinstance(value, bool):
                    clean_state[key] = value
                elif isinstance(value, (list, tuple)):
                    clean_list = []
                    for item in value:
                        if isinstance(item, (int, float, str, bool, type(None))):
                            clean_list.append(item)
                        else:
                            clean_list.append(str(item))
                    clean_state[key] = clean_list
                else:
                    clean_state[key] = str(value)
            
            stats_data["windows_state"][source] = clean_state
        
        # NOUVEAU: Ajouter les statistiques de capture directe
        try:
            capture_stats = get_capture_statistics()
            stats_data["capture_statistics"] = capture_stats
        except Exception as e:
            log_debug(f"Erreur ajout stats capture: {e}")
        
        with open("alert_statistics.json", "w", encoding="utf-8") as f:
            json.dump(stats_data, f, indent=2, ensure_ascii=False)
            
        log_debug("Statistiques sauvegardées")
    except Exception as e:
        log_error(f"Erreur sauvegarde statistiques: {e}")
        try:
            debug_data = {
                "error": str(e),
                "global_stats_keys": list(global_stats.keys()) if global_stats else [],
                "windows_state_keys": list(windows_state.keys()) if windows_state else []
            }
            with open("stats_debug.json", "w", encoding="utf-8") as f:
                json.dump(debug_data, f, indent=2)
        except:
            log_error("Impossible de sauvegarder les données de debug")


if __name__ == "__main__":
    main()