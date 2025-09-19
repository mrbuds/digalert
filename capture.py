# -*- coding: utf-8 -*-
"""
Module de capture intégré - Remplacement complet d'OBS
Conserve l'interface existante pour une migration transparente
"""

import time
import numpy as np
import cv2
from utils import log_error, log_debug, log_warning, log_info, ensure_directory_exists
from config import MAX_CAPTURE_TIME_MS, DEBUG_SAVE_SCREENSHOTS, DEBUG_SCREENSHOT_PATH
from capture_direct import (
    multi_capture, CaptureMethod, WindowCapture, 
    capture_window_direct, initialize_direct_capture,
    get_capture_statistics as get_direct_capture_statistics
)

class CaptureStats:
    """Classe pour suivre les statistiques de capture (compatible avec l'ancienne version)"""
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.total_attempts = 0
        self.successful_captures = 0
        self.failed_captures = 0
        self.total_time_ms = 0
        self.min_time_ms = float('inf')
        self.max_time_ms = 0
        self.last_error = None
        
    def add_attempt(self, success, duration_ms, error=None):
        self.total_attempts += 1
        self.total_time_ms += duration_ms
        
        if success:
            self.successful_captures += 1
            self.min_time_ms = min(self.min_time_ms, duration_ms)
            self.max_time_ms = max(self.max_time_ms, duration_ms)
        else:
            self.failed_captures += 1
            self.last_error = error
    
    @property
    def success_rate(self):
        if self.total_attempts == 0:
            return 0
        return (self.successful_captures / self.total_attempts) * 100
    
    @property
    def average_time_ms(self):
        if self.successful_captures == 0:
            return 0
        return self.total_time_ms / self.successful_captures

# Instance globale pour compatibilité
capture_stats = CaptureStats()

# Variable pour suivre l'état d'initialisation
DIRECT_CAPTURE_INITIALIZED = False


def initialize_capture_system(source_windows):
    """
    Initialise le système de capture directe
    Remplace la connexion OBS
    """
    global DIRECT_CAPTURE_INITIALIZED
    
    log_info("🚀 Initialisation du système de capture directe (sans OBS)")
    
    # Convertir la configuration SOURCE_WINDOWS vers le format attendu
    windows_config = []
    for window in source_windows:
        windows_config.append({
            'window_title': window.get('window_title'),
            'source_name': window.get('source_name'),
            'capture_method': window.get('capture_method', CaptureMethod.WIN32_PRINT_WINDOW),
            'priority': window.get('priority', 1)
        })
    
    # Initialiser le système
    success = initialize_direct_capture(windows_config)
    
    if success:
        DIRECT_CAPTURE_INITIALIZED = True
        log_info("✅ Système de capture directe initialisé avec succès")
        log_info("🎯 Avantages: Capture des fenêtres cachées/minimisées activée")
        
        # Afficher les méthodes de capture par fenêtre
        for window in source_windows:
            window_title = window.get('window_title')
            info = multi_capture.get_window_info(window_title)
            if info:
                log_info(f"📋 {window.get('source_name')} ({window_title}):")
                log_info(f"   Processus: {info['process_name']}")
                log_info(f"   État: {'Minimisée' if info['is_minimized'] else 'Normale'}")
                log_info(f"   ✅ Capture fenêtres cachées supportée")
    else:
        log_error("❌ Échec d'initialisation du système de capture directe")
        log_error("💡 Vérifiez que les fenêtres cibles sont ouvertes")
    
    return success


def capture_window(ws_dummy, source_name, window_title, timeout_ms=MAX_CAPTURE_TIME_MS):
    """
    Fonction de capture compatible avec l'interface OBS existante
    
    Args:
        ws_dummy: Paramètre ignoré (compatibilité OBS)
        source_name: Nom de la source (pour logs/debug)
        window_title: Titre de la fenêtre à capturer
        timeout_ms: Timeout de capture
    
    Returns:
        numpy.ndarray: Image capturée ou None si échec
    """
    global DIRECT_CAPTURE_INITIALIZED
    
    start_time = time.time()
    error_msg = None
    
    try:
        # Vérifier l'initialisation
        if not DIRECT_CAPTURE_INITIALIZED:
            error_msg = "Système de capture non initialisé"
            log_error(error_msg)
            capture_stats.add_attempt(False, 0, error_msg)
            return None
        
        log_debug(f"🎯 Capture directe: {source_name} ({window_title})")
        
        # Ajouter la fenêtre si pas encore enregistrée
        if window_title not in multi_capture.capturers:
            multi_capture.add_window(window_title)
            log_debug(f"Fenêtre ajoutée à la surveillance: {window_title}")
        
        # Capturer l'image
        img = capture_window_direct(window_title)
        
        capture_time = (time.time() - start_time) * 1000
        
        if img is not None:
            # Succès
            capture_stats.add_attempt(True, capture_time)
            
            # Vérification de timeout
            if capture_time > timeout_ms:
                log_warning(f"Capture {source_name} lente: {capture_time:.1f}ms > {timeout_ms}ms")
            
            # Amélioration de la qualité (optionnel - déjà fait dans l'ancien code)
            try:
                img = enhance_image_quality(img)
            except Exception as e:
                log_debug(f"Erreur amélioration image: {e}")
                # Continuer avec l'image non-améliorée
            
            log_debug(f"✅ Capture {source_name} réussie: {img.shape} en {capture_time:.1f}ms")
            
            # Sauvegarde debug si activée
            save_debug_screenshot(img, source_name, True)
            
            return img
        else:
            # Échec de capture
            error_msg = "Capture directe échouée"
            capture_stats.add_attempt(False, capture_time, error_msg)
            
            # Diagnostics détaillés
            capturer = multi_capture.capturers.get(window_title)
            if capturer:
                window_info = capturer.get_window_info()
                if window_info:
                    log_error(f"❌ Échec capture {source_name}:")
                    log_error(f"   Fenêtre: {window_info['title']}")
                    log_error(f"   Visible: {window_info['is_visible']}")
                    log_error(f"   Minimisée: {window_info['is_minimized']}")
                    log_error(f"   Taille: {window_info['width']}x{window_info['height']}")
                    log_error(f"   Processus: {window_info['process_name']}")
                    
                    # Suggérer des solutions
                    if window_info['width'] <= 0 or window_info['height'] <= 0:
                        log_error("💡 Problème: Dimensions de fenêtre invalides")
                    elif window_info['is_minimized']:
                        log_info("📝 Note: Fenêtre minimisée - capture directe devrait fonctionner")
                    
                    # Afficher les stats de la méthode de capture
                    stats = capturer.get_capture_statistics()
                    last_method = stats.get('last_successful_method', 'aucune')
                    log_debug(f"Dernière méthode réussie: {last_method}")
                else:
                    log_error(f"❌ Impossible d'obtenir les infos de fenêtre pour {window_title}")
            else:
                log_error(f"❌ Aucun capturer trouvé pour {window_title}")
            
            # Sauvegarde debug de l'erreur
            save_debug_screenshot(None, source_name, False, error_msg)
            
            return None

    except Exception as e:
        capture_time = (time.time() - start_time) * 1000
        error_msg = f"Erreur capture_window ({source_name}): {e}"
        log_error(error_msg)
        
        capture_stats.add_attempt(False, capture_time, error_msg)
        save_debug_screenshot(None, source_name, False, error_msg)
        
        return None


def enhance_image_quality(image):
    """Améliore la qualité de l'image pour une meilleure détection (conservé de l'ancienne version)"""
    if image is None:
        log_debug("Image None fournie à enhance_image_quality")
        return None
    
    try:
        # Vérification que c'est bien un numpy array
        if not isinstance(image, np.ndarray):
            log_error(f"Type d'image invalide: {type(image)}")
            return None
            
        # Vérification des dimensions
        if len(image.shape) != 3:
            log_error(f"Dimensions d'image invalides: {image.shape}")
            return None
            
        # Vérification que l'image n'est pas vide
        if image.size == 0:
            log_debug("Image vide dans enhance_image_quality")
            return None
        
        # Détection d'écran noir (moyenne des pixels très faible)
        gray_mean = np.mean(image)
        if gray_mean < 5:  # Seuil pour écran noir
            log_warning(f"Écran noir détecté (moyenne: {gray_mean:.1f})")
            return image  # Retourner quand même l'image
        
        # Conversion en niveaux de gris pour analyse
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Vérification de la qualité de l'image (netteté)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        if laplacian_var < 100:  # Image probablement floue
            log_debug(f"Image floue détectée (variance: {laplacian_var:.1f}), amélioration...")
            # Sharpen kernel
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            enhanced = cv2.filter2D(image, -1, kernel)
            return enhanced
        
        return image
        
    except Exception as e:
        log_error(f"Erreur amélioration image: {e}")
        log_debug(f"Type image: {type(image)}, Shape: {getattr(image, 'shape', 'N/A')}")
        return image  # Retourner l'image originale en cas d'erreur


def save_debug_screenshot(image, source_name, success=True, error=None):
    """Sauvegarde une capture pour debugging (conservé de l'ancienne version)"""
    if not DEBUG_SAVE_SCREENSHOTS:
        return
    
    try:
        ensure_directory_exists(DEBUG_SCREENSHOT_PATH)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        status = "success" if success else "failed"
        filename = f"{source_name}_{timestamp}_{status}.png"
        filepath = f"{DEBUG_SCREENSHOT_PATH}/{filename}"
        
        if image is not None:
            cv2.imwrite(filepath, image)
            log_debug(f"Screenshot debug sauvé: {filepath}")
        
        if error:
            # Sauvegarde aussi les infos d'erreur
            error_file = filepath.replace('.png', '_error.txt')
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(f"Erreur: {error}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write(f"Source: {source_name}\n")
                f.write(f"Mode: Capture directe (sans OBS)\n")
                
    except Exception as e:
        log_error(f"Erreur sauvegarde debug screenshot: {e}")


def get_capture_statistics():
    """Retourne les statistiques de capture (compatible avec l'ancienne interface)"""
    # Combiner les anciennes stats avec les nouvelles
    direct_stats = get_direct_capture_statistics()
    
    return {
        # Compatibilité ancienne interface
        'total_attempts': capture_stats.total_attempts,
        'successful_captures': capture_stats.successful_captures,
        'failed_captures': capture_stats.failed_captures,
        'success_rate': capture_stats.success_rate,
        'average_time_ms': capture_stats.average_time_ms,
        'min_time_ms': capture_stats.min_time_ms if capture_stats.min_time_ms != float('inf') else 0,
        'max_time_ms': capture_stats.max_time_ms,
        'last_error': capture_stats.last_error,
        
        # Nouvelles statistiques détaillées
        'direct_capture_stats': direct_stats,
        'capture_mode': 'direct_capture',
        'obs_required': False,
        'hidden_window_support': True
    }


def reset_capture_statistics():
    """Remet à zéro les statistiques de capture"""
    capture_stats.reset()
    
    # Reset aussi les stats du système direct
    for capturer in multi_capture.capturers.values():
        capturer.capture_stats = {
            'total_attempts': 0,
            'successful_captures': 0,
            'method_stats': {},
            'last_error': None
        }
    
    log_debug("Statistiques de capture remises à zéro")


def test_capture_performance(source_name, window_title, iterations=10):
    """
    Test de performance de capture (compatible avec l'ancienne interface)
    """
    log_info(f"Test de performance capture directe pour {source_name} ({iterations} itérations)")
    
    if window_title not in multi_capture.capturers:
        multi_capture.add_window(window_title)
    
    results = []
    success_count = 0
    
    for i in range(iterations):
        start_time = time.time()
        img = capture_window(None, source_name, window_title)  # ws_dummy = None
        duration = (time.time() - start_time) * 1000
        
        success = img is not None
        if success:
            success_count += 1
            
        results.append({
            'iteration': i + 1,
            'success': success,
            'duration_ms': duration,
            'image_shape': img.shape if img is not None else None
        })
        
        log_debug(f"Test {i+1}/{iterations}: {'OK' if success else 'FAIL'} ({duration:.1f}ms)")
        time.sleep(0.5)  # Pause entre les tests
    
    # Calculer les statistiques
    durations = [r['duration_ms'] for r in results if r['success']]
    
    stats = {
        'source_name': source_name,
        'window_title': window_title,
        'total_iterations': iterations,
        'successful_captures': success_count,
        'success_rate': (success_count / iterations) * 100,
        'average_duration_ms': sum(durations) / len(durations) if durations else 0,
        'min_duration_ms': min(durations) if durations else 0,
        'max_duration_ms': max(durations) if durations else 0,
        'results': results,
        'capture_mode': 'direct_capture'
    }
    
    log_info(f"Test terminé - Succès: {success_count}/{iterations} ({stats['success_rate']:.1f}%), "
             f"Temps moyen: {stats['average_duration_ms']:.1f}ms")
    
    return stats


def get_window_capture_info(window_title):
    """
    NOUVEAU: Récupère les informations détaillées d'une fenêtre
    """
    return multi_capture.get_window_info(window_title)


def optimize_capture_method(source_name, window_title, test_iterations=5):
    """
    NOUVEAU: Optimise automatiquement la méthode de capture pour une fenêtre
    """
    log_info(f"🎯 Optimisation méthode de capture pour {source_name}")
    
    if window_title not in multi_capture.capturers:
        multi_capture.add_window(window_title)
    
    capturer = multi_capture.capturers[window_title]
    
    # Test de toutes les méthodes
    from capture_direct import benchmark_capture_methods
    results = benchmark_capture_methods(window_title, test_iterations)
    
    if results:
        # Trouver la meilleure méthode
        best_method = max(results.items(), 
                         key=lambda x: (x[1]['success_rate'], -x[1]['avg_time_ms']))
        
        # Appliquer la meilleure méthode
        capturer.preferred_method = best_method[0]
        
        log_info(f"✅ Méthode optimisée pour {source_name}: {best_method[0]}")
        log_info(f"   Taux de succès: {best_method[1]['success_rate']:.1f}%")
        log_info(f"   Temps moyen: {best_method[1]['avg_time_ms']:.1f}ms")
        
        return best_method[0]
    
    return None


def switch_capture_method(window_title, method):
    """
    NOUVEAU: Change la méthode de capture pour une fenêtre spécifique
    """
    if window_title in multi_capture.capturers:
        multi_capture.capturers[window_title].preferred_method = method
        log_info(f"Méthode de capture changée pour {window_title}: {method}")
        return True
    
    return False


def get_available_windows():
    """
    NOUVEAU: Liste toutes les fenêtres disponibles pour capture
    """
    import win32gui
    
    def enum_window_callback(hwnd, results):
        if win32gui.IsWindowVisible(hwnd):
            window_text = win32gui.GetWindowText(hwnd)
            if window_text:  # Ignorer les fenêtres sans titre
                results.append({
                    'hwnd': hwnd,
                    'title': window_text,
                    'class_name': win32gui.GetClassName(hwnd)
                })
        return True
    
    results = []
    win32gui.EnumWindows(enum_window_callback, results)
    
    # Filtrer et trier
    filtered_results = []
    for window in results:
        title = window['title']
        # Exclure les fenêtres système communes
        if not any(skip in title.lower() for skip in ['program manager', 'task switching', 'cortana']):
            filtered_results.append(window)
    
    return sorted(filtered_results, key=lambda x: x['title'])


# Fonctions de compatibilité pour l'interface OBS
def validate_obs_connection():
    """Fonction de compatibilité - vérifie l'état du système de capture directe"""
    return DIRECT_CAPTURE_INITIALIZED


def is_obs_connected():
    """Fonction de compatibilité - retourne l'état d'initialisation"""
    return DIRECT_CAPTURE_INITIALIZED


def reconnect_obs():
    """Fonction de compatibilité - réinitialise le système de capture"""
    global DIRECT_CAPTURE_INITIALIZED
    
    log_info("🔄 Réinitialisation du système de capture directe...")
    
    # Réinitialiser les capteurs
    for capturer in multi_capture.capturers.values():
        capturer.hwnd = None  # Force la recherche de fenêtre
    
    DIRECT_CAPTURE_INITIALIZED = True
    log_info("✅ Système de capture directe réinitialisé")
    return True


def cleanup_capture_system():
    """Nettoie le système de capture"""
    global DIRECT_CAPTURE_INITIALIZED
    
    log_info("🧹 Nettoyage du système de capture directe")
    
    # Nettoyer les capteurs
    multi_capture.capturers.clear()
    multi_capture.global_stats = {
        'total_windows': 0,
        'active_windows': 0,
        'total_captures': 0,
        'successful_captures': 0
    }
    
    DIRECT_CAPTURE_INITIALIZED = False
    log_info("✅ Système de capture nettoyé")


if __name__ == "__main__":
    # Test du système intégré
    print("🧪 Test du système de capture intégré")
    
    # Configuration de test
    test_windows = [
        {
            'source_name': 'test_notepad',
            'window_title': 'Notepad',
            'notification_cooldown': 30,
            'priority': 1
        },
        {
            'source_name': 'test_calc',
            'window_title': 'Calculator',
            'notification_cooldown': 30,
            'priority': 2
        }
    ]
    
    # Initialiser
    if initialize_capture_system(test_windows):
        print("✅ Système initialisé")
        
        # Tester les captures
        for window in test_windows:
            source_name = window['source_name']
            window_title = window['window_title']
            
            print(f"\n🎯 Test capture: {source_name}")
            
            img = capture_window(None, source_name, window_title)
            if img is not None:
                print(f"   ✅ Succès: {img.shape}")
            else:
                print(f"   ❌ Échec")
        
        # Afficher les statistiques
        stats = get_capture_statistics()
        print(f"\n📊 Statistiques:")
        print(f"   Tentatives: {stats['total_attempts']}")
        print(f"   Succès: {stats['successful_captures']}")
        print(f"   Taux: {stats['success_rate']:.1f}%")
        
    else:
        print("❌ Échec d'initialisation")