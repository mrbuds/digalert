# -*- coding: utf-8 -*-
import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from config import LOG_LEVEL, LOG_TO_FILE, LOG_FILE, LOG_MAX_SIZE_MB, LOG_BACKUP_COUNT, COLORS

# Configuration du système de logging
logger = None

def setup_logging():
    """Configure le système de logging"""
    global logger
    
    if logger is not None:
        return logger
        
    logger = logging.getLogger('LastWarAlerts')
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    
    # Format des logs
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler avec couleurs
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColorFormatter())
    logger.addHandler(console_handler)
    
    # File handler si activé
    if LOG_TO_FILE:
        try:
            file_handler = RotatingFileHandler(
                LOG_FILE,
                maxBytes=LOG_MAX_SIZE_MB * 1024 * 1024,
                backupCount=LOG_BACKUP_COUNT,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Erreur configuration log fichier: {e}")
    
    return logger


class ColorFormatter(logging.Formatter):
    """Formatter avec couleurs pour la console"""
    
    COLORS = {
        'DEBUG': COLORS['CYAN'],
        'INFO': COLORS['GREEN'],
        'WARNING': COLORS['YELLOW'],
        'ERROR': COLORS['RED'],
        'CRITICAL': COLORS['RED'] + COLORS['BOLD']
    }

    def format(self, record):
        # Couleur selon le niveau
        color = self.COLORS.get(record.levelname, '')
        reset = COLORS['RESET']
        
        # Format de base
        log_time = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        level = record.levelname.ljust(8)
        
        # Message avec couleur
        message = f"{color}[{log_time}] {level} {record.getMessage()}{reset}"
        
        return message


def get_logger():
    """Retourne le logger configuré"""
    if logger is None:
        setup_logging()
    return logger


def log_debug(msg):
    """Log niveau DEBUG"""
    get_logger().debug(msg)


def log_info(msg):
    """Log niveau INFO"""
    get_logger().info(msg)


def log_warning(msg):
    """Log niveau WARNING"""
    get_logger().warning(msg)


def log_error(msg):
    """Log niveau ERROR"""
    get_logger().error(msg)


def log_critical(msg):
    """Log niveau CRITICAL"""
    get_logger().critical(msg)


def normalize(val, min_val, max_val, steps):
    """Normalise une valeur entre 0 et steps-1"""
    if max_val - min_val == 0:
        return 0
    return int((val - min_val) / (max_val - min_val) * (steps - 1))


def clear_console():
    """Efface la console de manière cross-platform"""
    os.system("cls" if os.name == "nt" else "clear")


def format_duration(seconds):
    """Formate une durée en secondes vers un format lisible"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{int(minutes)}m {seconds:.0f}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{int(hours)}h {int(minutes)}m"


def format_size(bytes_size):
    """Formate une taille en bytes vers un format lisible"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"


def get_memory_usage():
    """Retourne l'utilisation mémoire du processus actuel"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        return {
            'rss': memory_info.rss,  # Resident Set Size
            'vms': memory_info.vms,  # Virtual Memory Size
            'percent': process.memory_percent()
        }
    except ImportError:
        return None
    except Exception as e:
        log_error(f"Erreur récupération mémoire: {e}")
        return None


def get_system_info():
    """Retourne des informations système basiques"""
    try:
        import platform
        import psutil
        
        return {
            'platform': platform.system(),
            'platform_release': platform.release(),
            'python_version': platform.python_version(),
            'cpu_count': os.cpu_count(),
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_total': psutil.virtual_memory().total,
            'memory_available': psutil.virtual_memory().available,
            'disk_usage': psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:\\').percent
        }
    except ImportError:
        log_warning("psutil non disponible, statistiques système limitées")
        return {
            'platform': os.name,
            'python_version': sys.version.split()[0]
        }
    except Exception as e:
        log_error(f"Erreur récupération info système: {e}")
        return {}


def safe_divide(a, b, default=0):
    """Division sécurisée évitant la division par zéro"""
    if b == 0:
        return default
    return a / b


def calculate_success_rate(successful, total):
    """Calcule un taux de succès en pourcentage"""
    if total == 0:
        return 0
    return (successful / total) * 100


def format_percentage(value, decimals=1):
    """Formate un pourcentage"""
    return f"{value:.{decimals}f}%"


def create_progress_bar(percentage, width=20, fill='█', empty='░'):
    """Crée une barre de progression ASCII"""
    if percentage > 100:
        percentage = 100
    elif percentage < 0:
        percentage = 0
        
    filled_length = int(width * percentage // 100)
    bar = fill * filled_length + empty * (width - filled_length)
    return f"[{bar}] {percentage:.1f}%"


def colorize_text(text, color_name):
    """Ajoute de la couleur à un texte"""
    color = COLORS.get(color_name.upper(), '')
    reset = COLORS['RESET']
    return f"{color}{text}{reset}"


def truncate_string(text, max_length, suffix="..."):
    """Tronque une chaîne si elle dépasse la longueur maximale"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def ensure_directory_exists(path):
    """Crée un répertoire s'il n'existe pas"""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        log_error(f"Impossible de créer le répertoire {path}: {e}")
        return False


def get_file_age_seconds(filepath):
    """Retourne l'âge d'un fichier en secondes"""
    try:
        if not os.path.exists(filepath):
            return None
        
        file_time = os.path.getmtime(filepath)
        current_time = time.time()
        return current_time - file_time
    except Exception as e:
        log_error(f"Erreur calcul âge fichier {filepath}: {e}")
        return None


def cleanup_old_files(directory, max_age_hours=24, pattern="*.log"):
    """Nettoie les anciens fichiers dans un répertoire"""
    try:
        import glob
        max_age_seconds = max_age_hours * 3600
        current_time = time.time()
        
        pattern_path = os.path.join(directory, pattern)
        files_deleted = 0
        
        for filepath in glob.glob(pattern_path):
            try:
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > max_age_seconds:
                    os.remove(filepath)
                    files_deleted += 1
                    log_debug(f"Fichier ancien supprimé: {filepath}")
            except Exception as e:
                log_error(f"Erreur suppression {filepath}: {e}")
                
        if files_deleted > 0:
            log_info(f"Nettoyage: {files_deleted} anciens fichiers supprimés")
            
        return files_deleted
    except Exception as e:
        log_error(f"Erreur nettoyage répertoire {directory}: {e}")
        return 0


def validate_config():
    """Valide la configuration"""
    errors = []
    warnings = []
    
    # Vérification des répertoires
    from config import DEBUG_SCREENSHOT_PATH, STATISTICS
    
    if not ensure_directory_exists("logs"):
        warnings.append("Impossible de créer le répertoire logs")
        
    if not ensure_directory_exists(DEBUG_SCREENSHOT_PATH):
        warnings.append("Impossible de créer le répertoire debug_screenshots")
        
    if not ensure_directory_exists(STATISTICS.get("export_path", "statistics")):
        warnings.append("Impossible de créer le répertoire statistics")
    
    # Vérification des images d'alerte
    from config import ALERTS
    for alert in ALERTS:
        if 'img' in alert and not os.path.exists(alert['img']):
            errors.append(f"Image d'alerte introuvable: {alert['img']}")
    
    # Log des résultats
    if errors:
        for error in errors:
            log_error(f"Configuration: {error}")
    
    if warnings:
        for warning in warnings:
            log_warning(f"Configuration: {warning}")
    
    return len(errors) == 0, errors, warnings


# Initialisation automatique du logging
setup_logging()