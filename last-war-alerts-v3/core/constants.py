# -*- coding: utf-8 -*-
"""
Constantes globales pour Last War Alerts
Extraites de l'ancien config.py
"""

# Intervalles de temps (en secondes)
CHECK_INTERVAL = 2
COOLDOWN_PERIOD = 300
WINDOW_RETRY_INTERVAL = 5

# Paramètres de détection
DEFAULT_THRESHOLD = 0.7
CONSECUTIVE_DETECTIONS_REQUIRED = 3
MAX_CAPTURE_TIME_MS = 5000
MAX_CONSECUTIVE_FAILURES = 10

# Configuration des logs
LOG_LEVEL = "INFO"
LOG_TO_FILE = True
LOG_MAX_SIZE_MB = 10
LOG_BACKUP_COUNT = 3

# Configuration des notifications
NOTIFICATION_QUEUE_SIZE = 10
NOTIFICATION_RETRY_ATTEMPTS = 3
BLACK_SCREEN_NOTIFICATION_COOLDOWN = 60

# Paramètres de performance
STATISTICS_SAVE_INTERVAL = 300
HISTORY_LEN = 20

# Couleurs pour l'affichage
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
