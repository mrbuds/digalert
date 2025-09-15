# -*- coding: utf-8 -*-
import base64
import re
import time
import numpy as np
import cv2
from obswebsocket import requests
import pygetwindow as gw
import win32gui
from utils import log_error, log_debug, log_warning, log_info, ensure_directory_exists
from config import MAX_CAPTURE_TIME_MS, DEBUG_SAVE_SCREENSHOTS, DEBUG_SCREENSHOT_PATH

class CaptureStats:
    """Classe pour suivre les statistiques de capture"""
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

# Instance globale pour les statistiques
capture_stats = CaptureStats()

def get_game_window_bbox(window_title, retry_count=3):
    """
    Récupère les coordonnées de la fenêtre de jeu
    Avec système de retry amélioré
    """
    for attempt in range(retry_count):
        try:
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                if attempt == 0:  # Log seulement au premier essai
                    log_debug(f"Fenêtre introuvable: {window_title} (tentative {attempt + 1}/{retry_count})")
                
                if attempt < retry_count - 1:
                    time.sleep(0.5)  # Attente courte entre les tentatives
                continue
                
            window = windows[0]
            
            # Vérification si la fenêtre est minimisée
            if win32gui.IsIconic(window._hWnd):
                log_debug(f"Fenêtre minimisée détectée: {window_title}")
                try:
                    # Tentative de récupération des coordonnées depuis le placement
                    placement = win32gui.GetWindowPlacement(window._hWnd)
                    if placement and len(placement) > 4:
                        bbox = placement[4]  # RECT de la position normale
                        log_debug(f"Coordonnées récupérées depuis placement: {bbox}")
                        return validate_bbox(bbox, window_title)
                except Exception as e:
                    log_warning(f"Erreur récupération placement fenêtre {window_title}: {e}")
            
            # Fenêtre normale - récupération des coordonnées standard
            bbox = (window.left, window.top, window.right, window.bottom)
            log_debug(f"Coordonnées fenêtre {window_title}: {bbox}")
            return validate_bbox(bbox, window_title)
            
        except Exception as e:
            log_error(f"Erreur get_game_window_bbox (tentative {attempt + 1}): {e}")
            if attempt < retry_count - 1:
                time.sleep(1)
    
    log_error(f"Impossible de récupérer les coordonnées de {window_title} après {retry_count} tentatives")
    return None


def validate_bbox(bbox, window_title):
    """Valide et corrige les coordonnées de la fenêtre"""
    if not bbox or len(bbox) != 4:
        log_error(f"BBOX invalide pour {window_title}: {bbox}")
        return None
    
    left, top, right, bottom = bbox
    
    # Vérification des dimensions minimales
    width = right - left
    height = bottom - top
    
    if width <= 0 or height <= 0:
        log_error(f"Dimensions invalides pour {window_title}: {width}x{height}")
        return None
    
    # Vérification des dimensions trop petites (probablement une erreur)
    if width < 100 or height < 100:
        log_warning(f"Dimensions très petites pour {window_title}: {width}x{height}")
        return None
    
    # Vérification des coordonnées négatives (fenêtre hors écran)
    if left < -1000 or top < -1000:
        log_warning(f"Fenêtre probablement hors écran {window_title}: ({left}, {top})")
        # On peut quand même essayer de capturer
    
    log_debug(f"BBOX validée pour {window_title}: {bbox} ({width}x{height})")
    return bbox


def fix_base64_padding(data):
    """Corrige le padding Base64 manquant"""
    if not data:
        return data
        
    pad = len(data) % 4
    if pad > 0:
        data += '=' * (4 - pad)
    return data


def save_debug_screenshot(image, source_name, success=True, error=None):
    """Sauvegarde une capture pour debugging"""
    if not DEBUG_SAVE_SCREENSHOTS or image is None:
        return
    
    try:
        ensure_directory_exists(DEBUG_SCREENSHOT_PATH)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        status = "success" if success else "failed"
        filename = f"{source_name}_{timestamp}_{status}.png"
        filepath = f"{DEBUG_SCREENSHOT_PATH}/{filename}"
        
        cv2.imwrite(filepath, image)
        log_debug(f"Screenshot debug sauvé: {filepath}")
        
        if error:
            # Sauvegarde aussi les infos d'erreur
            error_file = filepath.replace('.png', '_error.txt')
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(f"Erreur: {error}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write(f"Source: {source_name}\n")
                
    except Exception as e:
        log_error(f"Erreur sauvegarde debug screenshot: {e}")


def enhance_image_quality(image):
    """Améliore la qualité de l'image pour une meilleure détection"""
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


def capture_window(ws, source_name, window_title, timeout_ms=MAX_CAPTURE_TIME_MS):
    """
    Capture une fenêtre via OBS WebSocket avec gestion d'erreurs améliorée
    """
    start_time = time.time()
    error_msg = None
    
    try:
        # Étape 1: Récupération des coordonnées de la fenêtre
        bbox = get_game_window_bbox(window_title)
        if bbox is None:
            error_msg = "Impossible de localiser la fenêtre"
            capture_stats.add_attempt(False, 0, error_msg)
            return None

        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        
        log_debug(f"Capture {source_name}: {width}x{height}")
        
        # Étape 2: Vérification que la source existe dans OBS
        try:
            # Test d'existence de la source
            source_list_response = ws.call(requests.GetSceneItemList(sceneName=None))
            if hasattr(source_list_response, 'datain') and source_list_response.datain:
                sources = source_list_response.datain.get('sceneItems', [])
                source_names = [item.get('sourceName', '') for item in sources]
                
                if source_name not in source_names:
                    log_warning(f"Source '{source_name}' non trouvée dans OBS. Sources disponibles: {source_names}")
                    # Continuer quand même, peut-être dans une autre scène
        except Exception as e:
            log_debug(f"Impossible de vérifier la liste des sources: {e}")
            # Continuer quand même
        
        # Étape 3: Requête à OBS
        try:
            log_debug(f"Requête screenshot pour '{source_name}' ({width}x{height})")
            response = ws.call(requests.GetSourceScreenshot(
                sourceName=source_name,
                imageFormat="png",
                imageWidth=width,
                imageHeight=height
            ))
        except Exception as e:
            error_msg = f"Erreur requête OBS: {str(e)}"
            log_error(error_msg)
            
            # Diagnostic spécifique selon le type d'erreur
            error_lower = str(e).lower()
            if "source not found" in error_lower or "not found" in error_lower:
                log_error(f"❌ Source '{source_name}' introuvable dans OBS")
                log_error("💡 Vérifiez que:")
                log_error("   1. La source existe dans OBS")
                log_error("   2. Le nom de la source correspond exactement")
                log_error("   3. La source est dans la scène active")
            elif "connection" in error_lower or "timeout" in error_lower:
                error_msg = "Connexion OBS perdue"
            elif "invalid" in error_lower:
                log_error(f"❌ Paramètres invalides pour '{source_name}'")
                log_error(f"   Dimensions: {width}x{height}")
            
            capture_stats.add_attempt(False, (time.time() - start_time) * 1000, error_msg)
            return None

        # Étape 4: Validation de la réponse - DIAGNOSTIC DÉTAILLÉ
        if not response:
            error_msg = f"Réponse OBS nulle pour {source_name}"
            log_error(error_msg)
            capture_stats.add_attempt(False, (time.time() - start_time) * 1000, error_msg)
            return None
            
        if not hasattr(response, 'datain'):
            error_msg = f"Réponse OBS sans attribut 'datain' pour {source_name}"
            log_error(error_msg)
            log_debug(f"Type de réponse: {type(response)}")
            log_debug(f"Attributs disponibles: {dir(response) if response else 'Aucun'}")
            capture_stats.add_attempt(False, (time.time() - start_time) * 1000, error_msg)
            return None
            
        if not response.datain:
            error_msg = f"Réponse OBS avec datain vide pour {source_name}"
            log_error(error_msg)
            log_debug(f"response.datain = {response.datain}")
            capture_stats.add_attempt(False, (time.time() - start_time) * 1000, error_msg)
            return None

        # Diagnostic du contenu de datain
        datain_keys = list(response.datain.keys()) if isinstance(response.datain, dict) else []
        log_debug(f"Clés dans response.datain: {datain_keys}")
        
        if "imageData" not in response.datain:
            error_msg = f"Données image manquantes dans la réponse OBS pour {source_name}"
            log_error(error_msg)
            log_error(f"Clés disponibles dans la réponse: {datain_keys}")
            
            # Diagnostics supplémentaires
            if "error" in response.datain:
                log_error(f"Erreur OBS: {response.datain['error']}")
            if "status" in response.datain:
                log_error(f"Statut OBS: {response.datain['status']}")
                
            capture_stats.add_attempt(False, (time.time() - start_time) * 1000, error_msg)
            return None

        # Étape 5: Décodage des données image
        img_data = response.datain["imageData"]
        
        if not img_data:
            error_msg = f"Données Base64 vides pour {source_name}"
            log_error(error_msg)
            log_error("💡 Causes possibles:")
            log_error("   1. La source est masquée ou invisible")
            log_error("   2. La fenêtre n'est pas capturée par OBS")
            log_error("   3. Problème de permissions")
            capture_stats.add_attempt(False, (time.time() - start_time) * 1000, error_msg)
            return None
        
        # Informations sur la taille des données
        log_debug(f"Données image reçues: {len(img_data)} caractères")
        
        # Nettoyage du préfixe Base64
        original_length = len(img_data)
        img_data = re.sub(r'^data:image/.+;base64,', '', img_data)
        img_data = fix_base64_padding(img_data)
        
        log_debug(f"Après nettoyage: {len(img_data)} caractères (supprimé: {original_length - len(img_data)})")

        # Étape 6: Décodage Base64 et création de l'image
        try:
            img_bytes = base64.b64decode(img_data)
            log_debug(f"Bytes décodés: {len(img_bytes)}")
            
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception as e:
            error_msg = f"Erreur décodage image {source_name}: {e}"
            log_error(error_msg)
            log_error("💡 Vérifiez que les données Base64 sont valides")
            capture_stats.add_attempt(False, (time.time() - start_time) * 1000, error_msg)
            return None

        if img is None:
            error_msg = f"Décodage image échoué pour {source_name}"
            log_error(error_msg)
            log_error("💡 L'image reçue n'est pas dans un format valide")
            capture_stats.add_attempt(False, (time.time() - start_time) * 1000, error_msg)
            return None

        # Étape 7: Validation et diagnostic de l'image
        if img.size == 0:
            error_msg = f"Image vide pour {source_name}"
            log_error(error_msg)
            capture_stats.add_attempt(False, (time.time() - start_time) * 1000, error_msg)
            return None

        # Diagnostic d'écran noir
        img_mean = np.mean(img)
        if img_mean < 5:  # Pixels très sombres
            log_warning(f"⚫ Écran noir détecté pour {source_name} (moyenne: {img_mean:.1f})")
            log_warning("💡 Causes possibles:")
            log_warning("   1. La fenêtre est minimisée ou masquée")
            log_warning("   2. Le jeu affiche un écran noir")
            log_warning("   3. Problème de capture de la source OBS")
            log_warning("   4. La source pointe vers une mauvaise fenêtre")
            # Continuer quand même avec l'image noire pour debug
        elif img_mean < 50:
            log_debug(f"Image très sombre pour {source_name} (moyenne: {img_mean:.1f})")

        # Étape 8: Amélioration de la qualité (avec protection)
        try:
            img = enhance_image_quality(img)
        except Exception as e:
            log_error(f"Erreur dans enhance_image_quality: {e}")
            # Continuer avec l'image non-améliorée
        
        # Étape 9: Calcul des statistiques
        duration_ms = (time.time() - start_time) * 1000
        capture_stats.add_attempt(True, duration_ms)
        
        # Vérification du timeout
        if duration_ms > timeout_ms:
            log_warning(f"Capture {source_name} lente: {duration_ms:.1f}ms > {timeout_ms}ms")
        
        log_debug(f"✅ Capture {source_name} réussie: {img.shape} en {duration_ms:.1f}ms")
        
        # Sauvegarde debug si activée
        save_debug_screenshot(img, source_name, True)
        
        return img

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        error_msg = f"Erreur capture_window ({source_name}): {e}"
        log_error(error_msg)
        
        capture_stats.add_attempt(False, duration_ms, error_msg)
        
        # Sauvegarde debug de l'erreur
        save_debug_screenshot(None, source_name, False, error_msg)
        
        return None


def get_capture_statistics():
    """Retourne les statistiques de capture"""
    return {
        'total_attempts': capture_stats.total_attempts,
        'successful_captures': capture_stats.successful_captures,
        'failed_captures': capture_stats.failed_captures,
        'success_rate': capture_stats.success_rate,
        'average_time_ms': capture_stats.average_time_ms,
        'min_time_ms': capture_stats.min_time_ms if capture_stats.min_time_ms != float('inf') else 0,
        'max_time_ms': capture_stats.max_time_ms,
        'last_error': capture_stats.last_error
    }


def reset_capture_statistics():
    """Remet à zéro les statistiques de capture"""
    capture_stats.reset()
    log_debug("Statistiques de capture remises à zéro")


def test_capture_performance(ws, source_name, window_title, iterations=10):
    """
    Test de performance de capture
    Utile pour diagnostiquer les problèmes
    """
    log_info(f"Test de performance capture pour {source_name} ({iterations} itérations)")
    
    results = []
    success_count = 0
    
    for i in range(iterations):
        start_time = time.time()
        img = capture_window(ws, source_name, window_title)
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
    
    # Calcul des statistiques
    durations = [r['duration_ms'] for r in results if r['success']]
    
    stats = {
        'source_name': source_name,
        'total_iterations': iterations,
        'successful_captures': success_count,
        'success_rate': (success_count / iterations) * 100,
        'average_duration_ms': sum(durations) / len(durations) if durations else 0,
        'min_duration_ms': min(durations) if durations else 0,
        'max_duration_ms': max(durations) if durations else 0,
        'results': results
    }
    
    log_info(f"Test terminé - Succès: {success_count}/{iterations} ({stats['success_rate']:.1f}%), "
             f"Temps moyen: {stats['average_duration_ms']:.1f}ms")
    
    return stats