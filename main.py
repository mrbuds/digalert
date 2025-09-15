# -*- coding: utf-8 -*-
from obswebsocket import obsws
from win10toast import ToastNotifier
import time
import threading
import numpy as np  # AJOUTÉ : import manquant
from queue import Queue
from collections import defaultdict
import json

from config import ALERTS, COOLDOWN_PERIOD, CHECK_INTERVAL, OBS_WS_HOST, OBS_WS_PASSWORD, OBS_WS_PORT, WINDOW_RETRY_INTERVAL, SOURCE_WINDOWS
from capture import capture_window
from detection import check_for_alert, cleanup_template_cache_if_needed
from webapp import init_webapp, start_webapp, update_webapp_data, add_webapp_alert, stop_webapp, update_webapp_screenshot
from utils import log_error, log_info, log_debug


def is_black_screen(screenshot, threshold=10):
    """Détecte si l'écran est noir de manière plus robuste"""
    if screenshot is None:
        return False
    
    try:
        # Vérifier la moyenne ET l'écart-type
        mean_val = np.mean(screenshot)
        std_val = np.std(screenshot)
        
        # Écran noir si très sombre ET peu de variation
        return mean_val < threshold and std_val < 5
    except Exception as e:
        log_error(f"Erreur détection écran noir: {e}")
        return False


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
                    time.sleep(2)  # Délai entre notifications
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


class OBSManager:
    def __init__(self):
        self.ws = None
        self.connected = False
        
    def connect(self, max_retries=3):
        for attempt in range(max_retries):
            try:
                if self.ws:
                    self.disconnect()
                    
                self.ws = obsws(OBS_WS_HOST, OBS_WS_PORT, OBS_WS_PASSWORD)
                self.ws.connect()
                self.connected = True
                log_info("Connexion OBS établie")
                return True
            except Exception as e:
                log_error(f"Tentative connexion OBS {attempt + 1}/{max_retries}: {e}")
                time.sleep(2)
                
        return False
        
    def disconnect(self):
        if self.ws:
            try:
                self.ws.disconnect()
                log_info("Déconnexion OBS réussie")
            except:
                pass
            finally:
                self.connected = False
                
    def is_connected(self):
        return self.connected and self.ws


def main():
    notification_queue = NotificationQueue()
    obs_manager = OBSManager()

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
            "last_black_screen_notification": 0  # Nouveau : suivi des notifications d'écran noir
        }

    # Statistiques globales
    global_stats = {
        "start_time": time.time(),
        "total_cycles": 0,
        "obs_reconnections": 0,
        "last_status_save": 0
    }

    try:
        # Initialisation de l'interface web
        webapp = init_webapp(port=5000, debug=False)
        start_webapp()
        log_info("🌐 Interface web disponible sur http://localhost:5000")
        
        # Connexion initiale OBS
        if not obs_manager.connect():
            log_error("Impossible de se connecter à OBS. Arrêt du programme.")
            return

        log_info("=== Démarrage du système de détection d'alertes ===")
        
        while True:
            try:
                cycle_start = time.time()
                current_time = time.time()
                global_stats["total_cycles"] += 1

                # Nettoyage périodique (toutes les 100 itérations)
                if global_stats["total_cycles"] % 100 == 0:
                    cleanup_template_cache_if_needed()

                # Vérification connexion OBS
                if not obs_manager.is_connected():
                    log_error("Connexion OBS perdue, tentative de reconnexion...")
                    if obs_manager.connect():
                        global_stats["obs_reconnections"] += 1
                    else:
                        log_error("Échec reconnexion OBS, attente...")
                        time.sleep(WINDOW_RETRY_INTERVAL)
                        continue

                for win in SOURCE_WINDOWS:
                    source_name = win["source_name"]
                    window_title = win["window_title"]
                    state = windows_state[source_name]
                    
                    capture_start = time.time()
                    state["total_captures"] += 1

                    try:
                        screenshot = capture_window(obs_manager.ws, source_name, window_title)
                        capture_time = (time.time() - capture_start) * 1000
                        state["performance_ms"] = capture_time

                        # CORRECTION : Vérification None AVANT utilisation
                        if screenshot is None:
                            state["consecutive_failures"] += 1
                            state["last_error"] = "Capture échouée"
                            state["error_count"] += 1
                            log_debug(f"Capture échouée pour {source_name} (échecs consécutifs: {state['consecutive_failures']})")
                            
                            # Si trop d'échecs consécutifs, augmenter l'intervalle
                            if state["consecutive_failures"] >= 5:
                                log_error(f"Trop d'échecs pour {source_name}, pause longue")
                                time.sleep(WINDOW_RETRY_INTERVAL)
                            continue  # IMPORTANT : passer à la source suivante

                        # Toujours sauvegarder le dernier screenshot (même sans alerte)
                        update_webapp_screenshot(source_name, screenshot, False, None)

                        # AMÉLIORATION : Vérification d'écran noir plus robuste
                        if is_black_screen(screenshot):
                            current_black_screen_time = current_time
                            last_black_screen_notification = state.get("last_black_screen_notification", 0)
                            
                            # Notification d'écran noir (cooldown de 60 secondes)
                            if current_black_screen_time - last_black_screen_notification > 60:
                                black_screen_title = f"⚫ Écran Noir - {source_name}"
                                black_screen_message = f"Écran noir détecté sur {source_name}. Vérifiez la capture OBS."
                                
                                if notification_queue.add_notification(black_screen_title, black_screen_message, 8):
                                    state["last_black_screen_notification"] = current_black_screen_time
                                    log_info(f"📢 Notification écran noir envoyée pour {source_name}")
                                
                            # Marquer comme problématique mais continuer la détection
                            state["consecutive_failures"] += 1
                            state["last_error"] = f"Écran noir détecté"
                        else:
                            # Écran normal, reset des échecs liés à l'écran noir
                            last_error = state.get("last_error")
                            if last_error and "écran noir" in last_error.lower():
                                state["consecutive_failures"] = 0
                                state["last_error"] = None

                        state["successful_captures"] += 1
                        state["last_error"] = None  # Reset de l'erreur si capture réussie

                        # Détection d'alertes avec zone de détection
                        alert_detected = False
                        current_alert = None
                        max_confidence = 0.0
                        detection_area = None

                        # Vérifier chaque alerte configurée
                        for alert in ALERTS:
                            # Vérifier que l'alerte est activée
                            if not alert.get('enabled', True):
                                continue
                                
                            try:
                                # AMÉLIORATION : Récupérer aussi la zone de détection
                                result = check_for_alert(screenshot, alert, return_confidence=True, return_area=True)
                                
                                if isinstance(result, tuple) and len(result) == 2:
                                    confidence, area = result
                                else:
                                    confidence = result
                                    area = None
                                
                                if confidence > max_confidence:
                                    max_confidence = confidence
                                    detection_area = area
                                    
                                # Utiliser le threshold spécifique de l'alerte
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

                        # Logique de notification améliorée
                        should_notify = False
                        if alert_detected:
                            time_since_last = current_time - state["last_notification_time"]
                            cooldown = state["notification_cooldown"]
                            
                            # Notification si:
                            # 1. Première détection (transition False -> True)
                            # 2. OU cooldown écoulé et détection stable (3+ consécutives)
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
                                
                                # CORRECTION : Ajouter la zone de détection à l'interface web
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

                # Affichage du tableau de bord (remplacé par interface web)
                update_webapp_data(windows_state, global_stats)
                
                # Affichage console simplifié (optionnel)
                if global_stats["total_cycles"] % 10 == 0:  # Toutes les 10 itérations
                    cycle_duration = time.time() - cycle_start
                    active_sources = sum(1 for state in windows_state.values() 
                                       if state.get('consecutive_failures', 0) < 5)
                    total_detections = sum(state.get('total_detections', 0) 
                                         for state in windows_state.values())
                    
                    log_info(f"📊 Cycle {global_stats['total_cycles']}: "
                           f"{active_sources}/{len(windows_state)} sources actives, "
                           f"{total_detections} détections, "
                           f"{cycle_duration:.2f}s")
                
                # Sauvegarde périodique des statistiques
                if current_time - global_stats["last_status_save"] > 300:  # 5 minutes
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
        notification_queue.stop()
        obs_manager.disconnect()
        stop_webapp()
        save_statistics(windows_state, global_stats)
        
        log_info("=== Arrêt du système ===")
        print("\n🎮 Last War Alerts arrêté")
        print("Interface web fermée")
        input("Appuyez sur Entrée pour quitter...")


def save_statistics(windows_state, global_stats):
    """Sauvegarde les statistiques dans un fichier JSON"""
    try:
        stats_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "global_stats": {},
            "windows_state": {}
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
                # Filtrer les types non-sérialisables
                if isinstance(value, (int, float, str, type(None))):
                    clean_state[key] = value
                elif isinstance(value, bool):
                    clean_state[key] = value
                elif isinstance(value, (list, tuple)):
                    # Nettoyer les listes
                    clean_list = []
                    for item in value:
                        if isinstance(item, (int, float, str, bool, type(None))):
                            clean_list.append(item)
                        else:
                            clean_list.append(str(item))
                    clean_state[key] = clean_list
                else:
                    # Convertir en string pour les autres types
                    clean_state[key] = str(value)
            
            stats_data["windows_state"][source] = clean_state
        
        with open("alert_statistics.json", "w", encoding="utf-8") as f:
            json.dump(stats_data, f, indent=2, ensure_ascii=False)
            
        log_debug("Statistiques sauvegardées")
    except Exception as e:
        log_error(f"Erreur sauvegarde statistiques: {e}")
        # Sauvegarde de debug pour identifier le problème
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