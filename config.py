# -*- coding: utf-8 -*-
import os
from collections import deque


# Constantes pour les méthodes de capture (copie locale)
CAPTURE_METHODS = {
    "WIN32_GDI": "win32_gdi",
    "WIN32_PRINT_WINDOW": "print_window", 
    "MSS_MONITOR": "mss_monitor",
    "PIL_IMAGEGRAB": "pil_imagegrab"
}

# Configuration des fenêtres avec paramètres spécifiques
SOURCE_WINDOWS = [
    {
        "source_name": "last war!",
        "window_title": "Last War-Survival Game", 
        "notification_cooldown": 30,
        "priority": 1,
        "capture_method": CAPTURE_METHODS["WIN32_PRINT_WINDOW"]  # Force PrintWindow
    },
    {
        "source_name": "bluestack",
        "window_title": "BlueStacks App Player",
        "notification_cooldown": 45,
        "priority": 2,
        "capture_method": CAPTURE_METHODS["WIN32_GDI"]  # GDI pour BlueStacks
    },
]

# Intervalles de temps (en secondes)
CHECK_INTERVAL = 2
COOLDOWN_PERIOD = 30
OBS_RECONNECT_INTERVAL = 10

# Paramètres de performance
MAX_CAPTURE_TIME_MS = 5000
MAX_CONSECUTIVE_FAILURES = 10  # Laisser plus de tentatives
WINDOW_RETRY_INTERVAL = 3  # Attendre 3 secondes entre les tentatives

# Paramètres de détection
HISTORY_LEN = 20  # Augmenté pour de meilleures statistiques
CONSECUTIVE_DETECTIONS_REQUIRED = 3  # Détections consécutives avant notification

# Paramètres de performance
MAX_CAPTURE_TIME_MS = 5000  # Timeout de capture
MAX_CONSECUTIVE_FAILURES = 10  # Échecs avant pause longue
STATISTICS_SAVE_INTERVAL = 300  # Sauvegarde toutes les 5 minutes

# Configuration des alertes avec support multi-images
ALERTS = [
    {
        # NOUVEAU: Support multi-images - peut être une liste
        "imgs": ["DIG.png", "DIG_v2.png"],  # Plusieurs variantes de l'image DIG
        "name": "Dig!",
        "threshold": 0.7,
        "debug": False,
        "history": deque(maxlen=HISTORY_LEN),
        "priority": "high",
        "color": "\033[92m",  # Vert
        "sound_file": None,  # Optionnel: fichier son
        "min_area": 100,  # Aire minimale de détection
        "match_strategy": "best",  # "best", "first", "all" - stratégie de correspondance
    },
    {
        # Format classique avec une seule image (rétrocompatibilité)
        "img": "egg.png", 
        "name": "EGGGGGG!",
        "threshold": 0.8,
        "debug": False,
        "history": deque(maxlen=HISTORY_LEN),
        "priority": "critical", 
        "color": "\033[91m",  # Rouge
        "sound_file": None,
        "min_area": 150,
    },
    {
        # Exemple avec plusieurs images pour différentes résolutions
        "imgs": ["titanium_1080p.png", "titanium_1440p.png", "titanium_4k.png"],
        "name": "TITANIUM!",
        "threshold": 0.75,
        "debug": False,
        "history": deque(maxlen=HISTORY_LEN),
        "priority": "medium",
        "color": "\033[94m",  # Bleu
        "sound_file": None,
        "min_area": 120,
        "match_strategy": "first",  # Arrêter à la première correspondance
        "enabled": False,  # Désactivée par défaut
    },
    # Alertes OCR inchangées
    {
        "ocr": "alliage",
        "name": "ALLIAGE DÉTECTÉ!",
        "threshold": 0.8,
        "debug": False,
        "history": deque(maxlen=HISTORY_LEN),
        "priority": "medium",
        "color": "\033[94m",  # Bleu
        "enabled": False,  # Désactivée par défaut
        "language": "fra",
        "ocr_config": "--oem 3 --psm 6",
    },
    {
        "ocr": "Fournitures",
        "name": "FOURNITURES!",
        "threshold": 0.8,
        "debug": False,
        "history": deque(maxlen=HISTORY_LEN),
        "priority": "medium",
        "color": "\033[93m",  # Jaune
        "enabled": False,
        "language": "fra",
        "ocr_config": "--oem 3 --psm 6",
    },
    {
        "ocr": "charbon",
        "name": "CHARBON!",
        "threshold": 0.8,
        "debug": False,
        "history": deque(maxlen=HISTORY_LEN),
        "priority": "low",
        "color": "\033[90m",  # Gris
        "enabled": False,
        "language": "fra", 
        "ocr_config": "--oem 3 --psm 6",
    },
]

# Filtrer les alertes activées
ACTIVE_ALERTS = [alert for alert in ALERTS if alert.get("enabled", True)]

# Configuration OBS WebSocket
OBS_WS_HOST = "localhost"
OBS_WS_PORT = 4455
OBS_WS_PASSWORD = ""
OBS_CONNECTION_TIMEOUT = 10

# Configuration des logs
LOG_LEVEL = "DEBUG"  # DEBUG, INFO, WARN, ERROR
LOG_TO_FILE = True
LOG_FILE = "last_war_alerts.log"
LOG_MAX_SIZE_MB = 10
LOG_BACKUP_COUNT = 3

# Configuration de l'affichage
DISPLAY_REFRESH_RATE = 1.0  # Hz
SHOW_PERFORMANCE_STATS = True
SHOW_CONFIDENCE_HISTORY = True
CONSOLE_WIDTH = 120

# Configuration des notifications
NOTIFICATION_QUEUE_SIZE = 10
NOTIFICATION_RETRY_ATTEMPTS = 3
NOTIFICATION_RETRY_DELAY = 2
BLACK_SCREEN_NOTIFICATION_COOLDOWN = 60  # Cooldown pour notifications d'écran noir (secondes)

# Paramètres de debugging avancé
DEBUG_SAVE_SCREENSHOTS = False  # Sauvegarde des captures pour debug
DEBUG_SCREENSHOT_PATH = "debug_screenshots/"
DEBUG_SAVE_FAILED_DETECTIONS = False
DEBUG_SHOW_DETECTION_AREAS = False

# Configuration de la récupération automatique
AUTO_RESTART_ON_CRITICAL_ERROR = True
MAX_RESTART_ATTEMPTS = 3
RESTART_DELAY = 30

# Seuils de performance et alertes
PERFORMANCE_THRESHOLDS = {
    "max_capture_time_ms": 2000,
    "min_success_rate": 0.8,
    "max_error_rate": 0.1,
    "max_queue_size": 5
}

# Configuration des statistiques
STATISTICS = {
    "save_interval": 300,  # 5 minutes
    "keep_history_hours": 24,
    "export_csv": False,
    "export_path": "statistics/"
}

# Messages personnalisés
MESSAGES = {
    "startup": "🎮 Système de détection Last War démarré",
    "shutdown": "🛑 Arrêt du système de détection",
    "obs_connected": "✅ Connexion OBS établie",
    "obs_disconnected": "❌ Connexion OBS perdue",
    "alert_detected": "🚨 Alerte détectée",
    "notification_sent": "📬 Notification envoyée",
    "error_occurred": "⚠️ Erreur détectée"
}

# Couleurs pour l'affichage console
COLORS = {
    "RESET": "\033[0m",
    "RED": "\033[91m",
    "GREEN": "\033[92m", 
    "YELLOW": "\033[93m",
    "BLUE": "\033[94m",
    "PURPLE": "\033[95m",
    "CYAN": "\033[96m",
    "WHITE": "\033[97m",
    "BOLD": "\033[1m"
}

# Configuration de récupération d'erreurs
ERROR_RECOVERY = {
    "obs_connection": {
        "max_retries": 5,
        "retry_delay": 5,
        "exponential_backoff": True
    },
    "capture_failure": {
        "max_consecutive": 10,
        "pause_duration": 30,
        "reset_threshold": 3
    },
    "notification_failure": {
        "max_retries": 3,
        "retry_delay": 2,
        "fallback_method": "console"  # console, file, none
    }
}


def get_capture_method(method_name):
    """Convertit une chaîne en CaptureMethod (évite l'import circulaire)"""
    if method_name == "WIN32_PRINT_WINDOW":
        # Import local pour éviter l'import circulaire
        from capture_direct import CaptureMethod
        return CaptureMethod.WIN32_PRINT_WINDOW
    elif method_name == "WIN32_GDI":
        from capture_direct import CaptureMethod
        return CaptureMethod.WIN32_GDI
    elif method_name == "MSS_MONITOR":
        from capture_direct import CaptureMethod
        return CaptureMethod.MSS_MONITOR
    elif method_name == "PIL_IMAGEGRAB":
        from capture_direct import CaptureMethod
        return CaptureMethod.PIL_IMAGEGRAB
    else:
        # Par défaut
        from capture_direct import CaptureMethod
        return CaptureMethod.WIN32_PRINT_WINDOW

def get_alert_images(alert):
    """Retourne la liste des images pour une alerte (nouveau format ou ancien)"""
    images = []
    
    # Nouveau format : liste d'images
    if "imgs" in alert:
        if isinstance(alert["imgs"], list):
            images.extend(alert["imgs"])
        else:
            images.append(alert["imgs"])
    
    # Ancien format : image unique (rétrocompatibilité)
    elif "img" in alert:
        images.append(alert["img"])
    
    return images


def normalize_alert_config(alert):
    """Normalise la configuration d'une alerte pour le nouveau format"""
    normalized = alert.copy()
    
    # Convertir le format ancien vers le nouveau
    if "img" in alert and "imgs" not in alert:
        normalized["imgs"] = [alert["img"]]
        # Garder l'ancienne clé pour la rétrocompatibilité
    
    # Valeurs par défaut
    if "match_strategy" not in normalized:
        normalized["match_strategy"] = "best"  # Stratégie par défaut
    
    if "min_area" not in normalized:
        normalized["min_area"] = 100
    
    return normalized


def validate_configuration():
    """Valide la configuration au démarrage"""
    errors = []
    warnings = []
    
    # Vérifier les images d'alerte (nouveau système)
    for alert in ALERTS:
        alert_name = alert.get('name', 'Alerte inconnue')
        
        # Alertes avec images
        if 'imgs' in alert or 'img' in alert:
            images = get_alert_images(alert)
            
            if not images:
                errors.append(f"Aucune image spécifiée pour {alert_name}")
                continue
            
            # Vérifier chaque image
            valid_images = []
            for img_path in images:
                if not os.path.exists(img_path):
                    warnings.append(f"Image manquante: {img_path} pour {alert_name}")
                else:
                    # Vérifier que le fichier est lisible
                    try:
                        with open(img_path, 'rb') as f:
                            header = f.read(8)
                            if not (header.startswith(b'\x89PNG') or 
                                   header.startswith(b'\xff\xd8\xff') or
                                   header.startswith(b'GIF')):
                                warnings.append(f"Fichier {img_path} n'est peut-être pas une image valide")
                            else:
                                valid_images.append(img_path)
                    except Exception as e:
                        errors.append(f"Impossible de lire {img_path}: {e}")
            
            if not valid_images:
                errors.append(f"Aucune image valide pour {alert_name}")
            elif len(valid_images) != len(images):
                warnings.append(f"Certaines images manquantes pour {alert_name} ({len(valid_images)}/{len(images)} valides)")
    
    # Vérifier et créer les dossiers nécessaires
    required_dirs = [
        'logs',
        'static/screenshots', 
        'debug_screenshots',
        'statistics',
        'templates'
    ]
    
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
                warnings.append(f"Dossier créé: {dir_path}")
            except Exception as e:
                errors.append(f"Impossible de créer le dossier {dir_path}: {e}")
    
    # Vérifier la configuration OBS
    if not isinstance(OBS_WS_PORT, int) or OBS_WS_PORT < 1 or OBS_WS_PORT > 65535:
        errors.append(f"Port OBS invalide: {OBS_WS_PORT}")
    
    # Vérifier les intervalles de temps
    if CHECK_INTERVAL <= 0:
        errors.append("CHECK_INTERVAL doit être > 0")
    
    if COOLDOWN_PERIOD <= 0:
        errors.append("COOLDOWN_PERIOD doit être > 0")
    
    # Vérifier les seuils
    for alert in ALERTS:
        threshold = alert.get('threshold', 0)
        if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
            errors.append(f"Seuil invalide pour {alert.get('name', 'unknown')}: {threshold}")
        
        # Vérifier la stratégie de correspondance
        strategy = alert.get('match_strategy', 'best')
        if strategy not in ['best', 'first', 'all']:
            warnings.append(f"Stratégie de correspondance inconnue pour {alert.get('name', 'unknown')}: {strategy}")
    
    # Vérifier les sources configurées
    if not SOURCE_WINDOWS:
        warnings.append("Aucune fenêtre source configurée")
    
    for window in SOURCE_WINDOWS:
        if not window.get('source_name'):
            errors.append("source_name manquant dans la configuration de fenêtre")
        if not window.get('window_title'):
            errors.append("window_title manquant dans la configuration de fenêtre")
    
    # Vérifier la taille de l'historique
    if HISTORY_LEN < 5:
        warnings.append("HISTORY_LEN très petit, cela peut affecter les statistiques")
    
    return len(errors) == 0, errors, warnings


def get_configuration_summary():
    """Retourne un résumé de la configuration"""
    total_images = 0
    for alert in ALERTS:
        if alert.get('enabled', True) and ('imgs' in alert or 'img' in alert):
            total_images += len(get_alert_images(alert))
    
    return {
        'sources_configured': len(SOURCE_WINDOWS),
        'alerts_total': len(ALERTS),
        'alerts_active': len(ACTIVE_ALERTS),
        'total_template_images': total_images,
        'check_interval': CHECK_INTERVAL,
        'debug_mode': DEBUG_SAVE_SCREENSHOTS,
        'log_to_file': LOG_TO_FILE,
        'obs_host': OBS_WS_HOST,
        'obs_port': OBS_WS_PORT
    }


def create_default_config_file():
    """Crée un fichier de configuration par défaut si nécessaire"""
    config_file = "config_backup.py"
    
    if not os.path.exists(config_file):
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                f.write("""# Configuration de sauvegarde pour Last War Alerts
# Ce fichier est généré automatiquement

# Pour restaurer cette configuration, copiez ce fichier vers config.py

SOURCE_WINDOWS = [
    {
        "source_name": "last war!",
        "window_title": "Last War-Survival Game",
        "notification_cooldown": 30,
        "priority": 1
    },
    {
        "source_name": "bluestack", 
        "window_title": "bluestack",
        "notification_cooldown": 45,
        "priority": 2
    }
]

# Exemple de configuration multi-images
ALERTS = [
    {
        "imgs": ["DIG.png", "DIG_v2.png"],  # Plusieurs variantes
        "name": "Dig!",
        "threshold": 0.7,
        "match_strategy": "best",  # Prendre la meilleure correspondance
    },
    {
        "img": "egg.png",  # Format classique (rétrocompatible)
        "name": "EGGGGGG!",
        "threshold": 0.8,
    }
]
""")
            return True
        except Exception as e:
            print(f"Erreur création fichier config: {e}")
            return False
    
    return True


# Validation automatique au chargement du module
if __name__ == "__main__":
    valid, errors, warnings = validate_configuration()
    
    if errors:
        print("❌ Erreurs de configuration:")
        for error in errors:
            print(f"  - {error}")
    
    if warnings:
        print("⚠️ Avertissements:")
        for warning in warnings:
            print(f"  - {warning}")
    
    if valid:
        print("✅ Configuration valide")
        summary = get_configuration_summary()
        print(f"📊 Résumé: {summary['alerts_active']}/{summary['alerts_total']} alertes actives, "
              f"{summary['sources_configured']} sources, "
              f"{summary['total_template_images']} images de template")
    else:
        print("❌ Configuration invalide - corrigez les erreurs avant de continuer")