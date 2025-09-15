# -*- coding: utf-8 -*-
import cv2
import pytesseract
import numpy as np
import time
import os
from utils import log_error, log_debug, log_warning, log_info, ensure_directory_exists
from config import DEBUG_SAVE_SCREENSHOTS, DEBUG_SCREENSHOT_PATH, DEBUG_SHOW_DETECTION_AREAS

# Configuration for Tesseract OCR
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class DetectionStats:
    """Classe pour suivre les statistiques de détection"""
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.total_detections = 0
        self.successful_detections = 0
        self.false_positives = 0
        self.template_cache = {}
        self.detection_times = []
        self.confidence_history = []
    
    def add_detection(self, success, confidence, duration_ms):
        self.total_detections += 1
        if success:
            self.successful_detections += 1
        self.detection_times.append(duration_ms)
        self.confidence_history.append(confidence)
    
    @property
    def average_detection_time(self):
        return sum(self.detection_times) / len(self.detection_times) if self.detection_times else 0
    
    @property
    def average_confidence(self):
        return sum(self.confidence_history) / len(self.confidence_history) if self.confidence_history else 0

# Instance globale pour les statistiques
detection_stats = DetectionStats()


def cleanup_template_cache_if_needed():
    """Nettoie le cache si trop volumineux"""
    global detection_stats
    if len(detection_stats.template_cache) > 10:
        # Garder seulement les 5 plus récents
        items = list(detection_stats.template_cache.items())
        detection_stats.template_cache = dict(items[-5:])
        log_debug("Cache des templates nettoyé")


def load_template_cached(template_path):
    """Charge un template avec mise en cache pour optimiser les performances"""
    if template_path in detection_stats.template_cache:
        return detection_stats.template_cache[template_path]
    
    try:
        if not os.path.exists(template_path):
            log_error(f"Template introuvable: {template_path}")
            return None
        
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            log_error(f"Impossible de charger le template: {template_path}")
            return None
        
        # Vérification de la taille du template
        h, w = template.shape[:2]
        if h < 10 or w < 10:
            log_warning(f"Template très petit ({w}x{h}): {template_path}")
        elif h > 500 or w > 500:
            log_warning(f"Template très grand ({w}x{h}): {template_path}")
        
        detection_stats.template_cache[template_path] = template
        log_debug(f"Template chargé en cache: {template_path} ({w}x{h})")
        return template
        
    except Exception as e:
        log_error(f"Erreur chargement template {template_path}: {e}")
        return None


def preprocess_image_for_detection(image, method='template'):
    """Prétraitement de l'image pour améliorer la détection"""
    if image is None:
        return None
    
    try:
        if method == 'template':
            # Pour la détection de template, on peut garder l'image couleur
            # mais améliorer le contraste
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l_channel, a, b = cv2.split(lab)
            
            # CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            cl = clahe.apply(l_channel)
            
            enhanced = cv2.merge((cl, a, b))
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
            return enhanced
            
        elif method == 'ocr':
            # Pour l'OCR, conversion en niveaux de gris avec amélioration
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Réduction du bruit
            denoised = cv2.fastNlMeansDenoising(gray)
            
            # Amélioration du contraste
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(denoised)
            
            return enhanced
        
        return image
        
    except Exception as e:
        log_error(f"Erreur prétraitement image: {e}")
        return image


def template_matching_multi_scale(screenshot, template, threshold, scales=[0.8, 0.9, 1.0, 1.1, 1.2]):
    """
    Détection de template multi-échelle pour gérer les différences de taille
    """
    best_match = None
    best_confidence = 0
    best_location = None
    best_scale = 1.0
    
    template_h, template_w = template.shape[:2]
    
    for scale in scales:
        try:
            # Redimensionnement du template
            if scale != 1.0:
                new_w = int(template_w * scale)
                new_h = int(template_h * scale)
                
                if new_w < 10 or new_h < 10 or new_w > screenshot.shape[1] or new_h > screenshot.shape[0]:
                    continue
                    
                scaled_template = cv2.resize(template, (new_w, new_h))
            else:
                scaled_template = template
            
            # Template matching
            result = cv2.matchTemplate(screenshot, scaled_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            if max_val > best_confidence:
                best_confidence = max_val
                best_location = max_loc
                best_scale = scale
                best_match = {
                    'confidence': max_val,
                    'location': max_loc,
                    'scale': scale,
                    'template_size': scaled_template.shape[:2]
                }
                
        except Exception as e:
            log_debug(f"Erreur template matching à l'échelle {scale}: {e}")
            continue
    
    return best_match


def save_detection_debug(screenshot, alert, match_result, detection_success):
    """Sauvegarde les informations de debug pour une détection"""
    if not DEBUG_SAVE_SCREENSHOTS:
        return
    
    try:
        ensure_directory_exists(DEBUG_SCREENSHOT_PATH)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        alert_name = alert.get('name', 'unknown').replace('!', '').replace(' ', '_')
        status = "detected" if detection_success else "missed"
        
        # Sauvegarde de la capture
        screenshot_file = f"{DEBUG_SCREENSHOT_PATH}/{alert_name}_{timestamp}_{status}_screenshot.png"
        cv2.imwrite(screenshot_file, screenshot)
        
        # Si détection réussie, marquer la zone
        if detection_success and match_result and DEBUG_SHOW_DETECTION_AREAS:
            marked_screenshot = screenshot.copy()
            
            if 'img' in alert and 'location' in match_result:
                x, y = match_result['location']
                h, w = match_result['template_size']
                
                # Rectangle de détection
                cv2.rectangle(marked_screenshot, (x, y), (x + w, y + h), (0, 255, 0), 2)
                
                # Texte avec confidence
                confidence = match_result.get('confidence', 0)
                text = f"{alert['name']}: {confidence:.3f}"
                cv2.putText(marked_screenshot, text, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                marked_file = f"{DEBUG_SCREENSHOT_PATH}/{alert_name}_{timestamp}_marked.png"
                cv2.imwrite(marked_file, marked_screenshot)
        
        # Sauvegarde des métadonnées
        metadata_file = f"{DEBUG_SCREENSHOT_PATH}/{alert_name}_{timestamp}_metadata.txt"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            f.write(f"Alert: {alert.get('name', 'N/A')}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Detection: {detection_success}\n")
            f.write(f"Threshold: {alert.get('threshold', 'N/A')}\n")
            
            if match_result:
                f.write(f"Confidence: {match_result.get('confidence', 'N/A')}\n")
                f.write(f"Location: {match_result.get('location', 'N/A')}\n")
                f.write(f"Scale: {match_result.get('scale', 'N/A')}\n")
            
            f.write(f"Screenshot shape: {screenshot.shape}\n")
        
        log_debug(f"Debug détection sauvé: {alert_name}_{timestamp}")
        
    except Exception as e:
        log_error(f"Erreur sauvegarde debug détection: {e}")


def check_for_alert(screenshot, alert, return_confidence=False, return_area=False):
    """
    Détection d'alerte améliorée avec support multi-méthode et zone de détection
    """
    start_time = time.time()
    
    try:
        if screenshot is None:
            log_debug("Screenshot null fourni à check_for_alert")
            if return_area:
                return (0.0, None) if return_confidence else (False, None)
            return 0.0 if return_confidence else False

        # Vérification si l'alerte est activée
        if not alert.get('enabled', True):
            if return_area:
                return (0.0, None) if return_confidence else (False, None)
            return 0.0 if return_confidence else False

        confidence = 0.0
        detection_success = False
        match_result = None
        detection_area = None

        # Méthode 1: Détection par template matching
        if 'img' in alert:
            template = load_template_cached(alert['img'])
            if template is None:
                log_error(f"Impossible de charger le template {alert['img']}")
                if return_area:
                    return (0.0, None) if return_confidence else (False, None)
                return 0.0 if return_confidence else False

            # Prétraitement de l'image
            processed_screenshot = preprocess_image_for_detection(screenshot, 'template')
            processed_template = preprocess_image_for_detection(template, 'template')

            # Template matching multi-échelle
            match_result = template_matching_multi_scale(
                processed_screenshot, 
                processed_template, 
                alert['threshold']
            )
            
            if match_result:
                confidence = match_result['confidence']
                detection_success = confidence >= alert['threshold']
                
                # NOUVEAU : Créer la zone de détection
                if detection_success and 'location' in match_result:
                    x, y = match_result['location']
                    h, w = match_result['template_size']
                    detection_area = {
                        'x': x,
                        'y': y,
                        'width': w,
                        'height': h
                    }
                
                log_debug(f"Template matching {alert['name']}: "
                         f"confidence={confidence:.3f}, threshold={alert['threshold']}, "
                         f"scale={match_result.get('scale', 1.0)}")
            
            # Ajout à l'historique
            alert["history"].append(confidence)

        # Méthode 2: Détection par OCR
        elif 'ocr' in alert:
            try:
                # Prétraitement pour OCR
                processed_screenshot = preprocess_image_for_detection(screenshot, 'ocr')
                
                # Configuration OCR
                ocr_config = alert.get('ocr_config', '--oem 3 --psm 6')
                language = alert.get('language', 'fra')
                
                # OCR
                ocr_result = pytesseract.image_to_string(
                    processed_screenshot, 
                    lang=language, 
                    config=ocr_config
                )
                
                # Recherche du texte cible
                target_text = alert['ocr'].lower()
                found_text = ocr_result.lower()
                
                if target_text in found_text:
                    confidence = 1.0  # Pour OCR, on considère que c'est binaire
                    detection_success = True
                    
                    log_debug(f"OCR détection {alert['name']}: texte trouvé dans '{found_text.strip()}'")
                    
                    match_result = {
                        'confidence': confidence,
                        'ocr_result': ocr_result.strip(),
                        'target_text': target_text
                    }
                    
                    # Pour OCR, pas de zone précise, on peut créer une zone générale
                    if detection_success:
                        detection_area = {
                            'x': 0,
                            'y': 0,
                            'width': screenshot.shape[1],
                            'height': screenshot.shape[0],
                            'type': 'ocr'
                        }
                else:
                    confidence = 0.0
                    log_debug(f"OCR {alert['name']}: texte '{target_text}' non trouvé dans '{found_text.strip()}'")
                
                alert["history"].append(confidence)
                
            except Exception as e:
                log_error(f"Erreur OCR pour {alert['name']}: {e}")
                confidence = 0.0
                alert["history"].append(confidence)
        
        else:
            log_error(f"Alerte {alert['name']} n'a pas de méthode de détection valide (img ou ocr)")
            if return_area:
                return (0.0, None) if return_confidence else (False, None)
            return 0.0 if return_confidence else False

        # Statistiques de performance
        duration_ms = (time.time() - start_time) * 1000
        detection_stats.add_detection(detection_success, confidence, duration_ms)
        
        # Debug avancé si activé
        if alert.get("debug", False) or DEBUG_SAVE_SCREENSHOTS:
            save_detection_debug(screenshot, alert, match_result, detection_success)
            
        # Affichage debug temps réel si activé
        if alert.get("debug", False) and DEBUG_SHOW_DETECTION_AREAS and detection_success and match_result:
            debug_screenshot = screenshot.copy()
            
            if 'img' in alert and 'location' in match_result:
                x, y = match_result['location']
                h, w = match_result['template_size']
                cv2.rectangle(debug_screenshot, (x, y), (x + w, y + h), (0, 255, 0), 2)
                
                cv2.imshow(f"DEBUG: {alert['name']}", debug_screenshot)
                cv2.waitKey(1)  # Non-bloquant
        
        log_debug(f"Détection {alert['name']}: confidence={confidence:.3f}, "
                 f"success={detection_success}, duration={duration_ms:.1f}ms")

        # Retour selon les paramètres demandés
        if return_area:
            if return_confidence:
                return confidence, detection_area
            return detection_success, detection_area
        
        return confidence if return_confidence else detection_success

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(f"Erreur de détection ({alert.get('name', 'unknown')}): {e}")
        detection_stats.add_detection(False, 0.0, duration_ms)
        
        # Ajout d'une valeur d'erreur à l'historique
        if hasattr(alert, 'history'):
            alert["history"].append(0.0)
        
        if return_area:
            return (0.0, None) if return_confidence else (False, None)
        return 0.0 if return_confidence else False


def validate_detection_setup():
    """Valide la configuration de détection"""
    issues = []
    
    # Vérification de Tesseract
    try:
        pytesseract.get_tesseract_version()
        log_debug("Tesseract OCR disponible")
    except Exception as e:
        issues.append(f"Tesseract OCR non disponible: {e}")
    
    # Vérification des templates
    from config import ALERTS
    for alert in ALERTS:
        if 'img' in alert:
            if not os.path.exists(alert['img']):
                issues.append(f"Template manquant: {alert['img']} pour {alert['name']}")
            else:
                # Test de chargement
                template = cv2.imread(alert['img'])
                if template is None:
                    issues.append(f"Template invalide: {alert['img']} pour {alert['name']}")
                else:
                    h, w = template.shape[:2]
                    if h < 5 or w < 5:
                        issues.append(f"Template trop petit ({w}x{h}): {alert['img']}")
    
    if issues:
        for issue in issues:
            log_warning(f"Validation détection: {issue}")
    else:
        log_info("Configuration de détection validée")
    
    return len(issues) == 0, issues


def get_detection_statistics():
    """Retourne les statistiques de détection"""
    return {
        'total_detections': detection_stats.total_detections,
        'successful_detections': detection_stats.successful_detections,
        'success_rate': (detection_stats.successful_detections / detection_stats.total_detections * 100) if detection_stats.total_detections > 0 else 0,
        'average_detection_time': detection_stats.average_detection_time,
        'average_confidence': detection_stats.average_confidence,
        'templates_cached': len(detection_stats.template_cache),
        'confidence_history': detection_stats.confidence_history[-100:]  # Dernières 100 détections
    }


def reset_detection_statistics():
    """Remet à zéro les statistiques de détection"""
    detection_stats.reset()
    log_debug("Statistiques de détection remises à zéro")


def clear_template_cache():
    """Vide le cache des templates"""
    detection_stats.template_cache.clear()
    log_debug("Cache des templates vidé")


def benchmark_detection_methods(screenshot, iterations=100):
    """
    Benchmark des différentes méthodes de détection
    """
    if screenshot is None:
        log_error("Screenshot requis pour le benchmark")
        return None
    
    log_info(f"Benchmark détection démarré ({iterations} itérations)")
    
    from config import ALERTS
    results = {}
    
    for alert in ALERTS:
        if not alert.get('enabled', True):
            continue
            
        alert_name = alert['name']
        method = 'template' if 'img' in alert else 'ocr' if 'ocr' in alert else 'unknown'
        
        if method == 'unknown':
            continue
        
        times = []
        confidences = []
        
        log_debug(f"Benchmark {alert_name} ({method})...")
        
        for i in range(iterations):
            start_time = time.time()
            
            try:
                confidence = check_for_alert(screenshot, alert, return_confidence=True)
                if isinstance(confidence, tuple):
                    confidence = confidence[0]  # Si retour avec area
                duration = (time.time() - start_time) * 1000
                
                times.append(duration)
                confidences.append(confidence)
                
            except Exception as e:
                log_error(f"Erreur benchmark {alert_name} iteration {i}: {e}")
                continue
        
        if times:
            results[alert_name] = {
                'method': method,
                'iterations': len(times),
                'avg_time_ms': sum(times) / len(times),
                'min_time_ms': min(times),
                'max_time_ms': max(times),
                'avg_confidence': sum(confidences) / len(confidences),
                'max_confidence': max(confidences),
                'detections': sum(1 for c in confidences if c >= alert.get('threshold', 0.5))
            }
            
            log_info(f"Benchmark {alert_name}: "
                    f"{results[alert_name]['avg_time_ms']:.1f}ms avg, "
                    f"{results[alert_name]['detections']} détections")
    
    return results


def optimize_detection_thresholds(screenshot, alerts, test_iterations=50):
    """
    Optimise automatiquement les seuils de détection
    """
    log_info("Optimisation des seuils de détection...")
    
    optimized_alerts = []
    
    for alert in alerts:
        if not alert.get('enabled', True) or 'img' not in alert:
            optimized_alerts.append(alert)
            continue
        
        original_threshold = alert['threshold']
        confidences = []
        
        # Test avec plusieurs itérations pour avoir une moyenne stable
        for i in range(test_iterations):
            try:
                confidence = check_for_alert(screenshot, alert, return_confidence=True)
                if isinstance(confidence, tuple):
                    confidence = confidence[0]  # Si retour avec area
                confidences.append(confidence)
            except:
                continue
        
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            max_confidence = max(confidences)
            
            # Stratégie d'optimisation conservative
            # Nouveau seuil = 80% du max ou 90% de la moyenne, selon ce qui est le plus bas
            suggested_threshold = min(max_confidence * 0.8, avg_confidence * 0.9)
            
            # S'assurer que le nouveau seuil n'est pas trop bas
            suggested_threshold = max(suggested_threshold, 0.3)
            
            # Mise à jour si l'amélioration est significative
            if abs(suggested_threshold - original_threshold) > 0.05:
                alert_copy = alert.copy()
                alert_copy['threshold'] = suggested_threshold
                alert_copy['original_threshold'] = original_threshold
                
                log_info(f"Seuil optimisé pour {alert['name']}: "
                        f"{original_threshold:.3f} -> {suggested_threshold:.3f}")
                
                optimized_alerts.append(alert_copy)
            else:
                optimized_alerts.append(alert)
        else:
            log_warning(f"Impossible d'optimiser {alert['name']}: aucune donnée")
            optimized_alerts.append(alert)
    
    return optimized_alerts