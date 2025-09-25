# -*- coding: utf-8 -*-
import cv2
import pytesseract
import numpy as np
import time
import os
from utils import log_error, log_debug, log_warning, log_info, ensure_directory_exists
from config import DEBUG_SAVE_SCREENSHOTS, DEBUG_SCREENSHOT_PATH, DEBUG_SHOW_DETECTION_AREAS, get_alert_images
from learning_system import get_adjusted_threshold, should_filter_detection

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
        self.multi_image_stats = {}
    
    def add_detection(self, success, confidence, duration_ms, alert_name=None, matched_image=None):
        self.total_detections += 1
        if success:
            self.successful_detections += 1
        self.detection_times.append(duration_ms)
        self.confidence_history.append(confidence)
        
        if alert_name and matched_image:
            if alert_name not in self.multi_image_stats:
                self.multi_image_stats[alert_name] = {}
            
            if matched_image not in self.multi_image_stats[alert_name]:
                self.multi_image_stats[alert_name][matched_image] = {
                    'detections': 0,
                    'total_confidence': 0.0,
                    'max_confidence': 0.0,
                    'avg_confidence': 0.0
                }
            
            stats = self.multi_image_stats[alert_name][matched_image]
            stats['detections'] += 1
            stats['total_confidence'] += confidence
            stats['max_confidence'] = max(stats['max_confidence'], confidence)
            stats['avg_confidence'] = stats['total_confidence'] / stats['detections']
    
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
    if len(detection_stats.template_cache) > 20:
        items = list(detection_stats.template_cache.items())
        detection_stats.template_cache = dict(items[-10:])
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
            # Pour la détection de template, améliorer le contraste
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

def template_matching_multi_scale(screenshot, template, threshold, scales=None):
    """
    Détection de template multi-échelle pour gérer les différences de taille
    CORRIGÉ: Limites de scale plus strictes pour éviter les faux positifs
    """
    best_match = None
    best_confidence = 0
    best_location = None
    best_scale = 1.0
    
    template_h, template_w = template.shape[:2]
    
    # IMPORTANT: Limiter les échelles pour éviter les templates trop petits
    if scales is None:
        # NE PAS descendre en dessous de 0.8 pour éviter la perte de détails
        scales = [0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2]
    
    for scale in scales:
        try:
            # Redimensionnement du template
            new_w = int(template_w * scale)
            new_h = int(template_h * scale)
            
            # IMPORTANT: Ne pas permettre des templates trop petits
            if new_w < max(30, template_w * 0.5) or new_h < max(30, template_h * 0.5):
                continue
                
            if new_w > screenshot.shape[1] or new_h > screenshot.shape[0]:
                continue
                
            scaled_template = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            
            # Template matching
            result = cv2.matchTemplate(screenshot, scaled_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            # NOUVEAU: Pénaliser les échelles extrêmes
            scale_penalty = 1.0
            if scale < 0.9 or scale > 1.1:
                scale_penalty = 0.95  # Réduire légèrement la confiance pour les échelles extrêmes
            
            adjusted_confidence = max_val * scale_penalty
            
            if adjusted_confidence > best_confidence:
                best_confidence = adjusted_confidence
                best_location = max_loc
                best_scale = scale
                best_match = {
                    'confidence': max_val,  # Garder la confiance originale
                    'adjusted_confidence': adjusted_confidence,
                    'location': max_loc,
                    'scale': scale,
                    'template_size': (new_w, new_h)
                }
                
        except Exception as e:
            log_debug(f"Erreur template matching à l'échelle {scale}: {e}")
            continue
    
    return best_match

def check_alert_with_trained_templates(screenshot, alert_name, threshold=0.7):
    """
    Vérifie d'abord les templates entraînés manuellement
    """
    try:
        from training_tool import training_tool
        
        # Récupérer les templates annotés pour cette alerte
        trained_templates = training_tool.get_alert_templates(alert_name, min_confidence=0.7)
        
        if trained_templates:
            log_debug(f"Utilisation de {len(trained_templates)} templates entraînés pour {alert_name}")
            
            best_match = None
            best_confidence = 0
            
            for template_path in trained_templates:
                if not os.path.exists(template_path):
                    continue
                    
                template = cv2.imread(template_path)
                if template is None:
                    continue
                
                # Essayer le template matching
                result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                
                if max_val > best_confidence:
                    best_confidence = max_val
                    h, w = template.shape[:2]
                    best_match = {
                        'confidence': max_val,
                        'location': max_loc,
                        'size': (w, h),
                        'template_path': template_path
                    }
            
            if best_match and best_match['confidence'] >= threshold:
                log_info(f"Match trouvé avec template entraîné: {alert_name} (confiance: {best_match['confidence']:.2f})")
                return {
                    'found': True,
                    'confidence': best_match['confidence'],
                    'x': best_match['location'][0],
                    'y': best_match['location'][1],
                    'width': best_match['size'][0],
                    'height': best_match['size'][1],
                    'method': 'trained_template'
                }
    
    except Exception as e:
        log_debug(f"Erreur vérification templates entraînés: {e}")
    
    return None

def check_multiple_templates(screenshot, template_paths, threshold, match_strategy="best"):
    """
    Vérifie plusieurs templates et retourne le(s) meilleur(s) résultat(s)
    Inclut les templates entraînés manuellement
    """
    if not template_paths:
        return None
    
    # NOUVEAU : Ajouter les templates entraînés
    alert_name = None  # Vous devrez passer cette info
    if alert_name:
        trained_templates = load_trained_templates(alert_name)
        if trained_templates:
            template_paths = list(template_paths) + trained_templates
            log_debug(f"Utilisation de {len(trained_templates)} templates entraînés en plus")

    processed_screenshot = preprocess_image_for_detection(screenshot, 'template')
    if processed_screenshot is None:
        return None
    
    results = []
    
    for template_path in template_paths:
        try:
            template = load_template_cached(template_path)
            if template is None:
                log_debug(f"Template non chargé: {template_path}")
                continue
            
            processed_template = preprocess_image_for_detection(template, 'template')
            if processed_template is None:
                continue
            
            # Template matching multi-échelle avec limites strictes
            match_result = template_matching_multi_scale(
                processed_screenshot, 
                processed_template, 
                threshold
            )
            
            if match_result and match_result['confidence'] >= threshold:
                match_result['template_path'] = template_path
                match_result['template_name'] = os.path.basename(template_path)
                results.append(match_result)
                
                log_debug(f"Correspondance trouvée: {template_path} "
                         f"(confiance: {match_result['confidence']:.3f}, "
                         f"échelle: {match_result['scale']:.2f})")
                
                if match_strategy == "first":
                    break
        
        except Exception as e:
            log_error(f"Erreur vérification template {template_path}: {e}")
            continue
    
    if not results:
        return None
    
    if match_strategy == "best":
        best_result = max(results, key=lambda x: x['confidence'])
        return best_result
    elif match_strategy == "first":
        return results[0]
    elif match_strategy == "all":
        return {
            'matches': results,
            'best_confidence': max(r['confidence'] for r in results),
            'match_count': len(results),
            'strategy': 'all'
        }
    else:
        log_warning(f"Stratégie de correspondance inconnue: {match_strategy}")
        return max(results, key=lambda x: x['confidence'])

def save_detection_debug(screenshot, alert, match_result, detection_success):
    """Sauvegarde les informations de debug pour une détection"""
    if not DEBUG_SAVE_SCREENSHOTS:
        return
    
    try:
        ensure_directory_exists(DEBUG_SCREENSHOT_PATH)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        alert_name = alert.get('name', 'unknown').replace('!', '').replace(' ', '_')
        status = "detected" if detection_success else "missed"
        
        screenshot_file = f"{DEBUG_SCREENSHOT_PATH}/{alert_name}_{timestamp}_{status}_screenshot.png"
        cv2.imwrite(screenshot_file, screenshot)
        
        if detection_success and match_result and DEBUG_SHOW_DETECTION_AREAS:
            marked_screenshot = screenshot.copy()
            
            matches_to_mark = []
            if 'matches' in match_result:
                matches_to_mark = match_result['matches']
            else:
                matches_to_mark = [match_result]
            
            for i, match in enumerate(matches_to_mark):
                if 'location' in match:
                    x, y = match['location']
                    h, w = match['template_size']
                    
                    colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0)]
                    color = colors[i % len(colors)]
                    
                    cv2.rectangle(marked_screenshot, (x, y), (x + w, y + h), color, 2)
                    
                    confidence = match.get('confidence', 0)
                    template_name = match.get('template_name', 'unknown')
                    scale = match.get('scale', 1.0)
                    
                    text = f"{template_name}: {confidence:.3f} (s:{scale:.2f})"
                    cv2.putText(marked_screenshot, text, (x, y-10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                
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
                if 'matches' in match_result:
                    f.write(f"Multiple matches: {match_result['match_count']}\n")
                    for i, match in enumerate(match_result['matches']):
                        f.write(f"  Match {i+1}:\n")
                        f.write(f"    Template: {match.get('template_name', 'N/A')}\n")
                        f.write(f"    Confidence: {match.get('confidence', 'N/A')}\n")
                        f.write(f"    Scale: {match.get('scale', 'N/A')}\n")
                else:
                    f.write(f"Template: {match_result.get('template_name', 'N/A')}\n")
                    f.write(f"Confidence: {match_result.get('confidence', 'N/A')}\n")
                    f.write(f"Scale: {match_result.get('scale', 'N/A')}\n")
            
            f.write(f"Screenshot shape: {screenshot.shape}\n")
        
        log_debug(f"Debug détection sauvé: {alert_name}_{timestamp}")
        
    except Exception as e:
        log_error(f"Erreur sauvegarde debug détection: {e}")

def check_for_alert(screenshot, alert_name, source_name=None):
    """
    Vérifie la présence d'une alerte en utilisant le système de templates unifié
    
    Args:
        screenshot: Image capturée (numpy array)
        alert_name: Nom de l'alerte à détecter
        source_name: Nom de la source (fenêtre)
    
    Returns:
        Dict avec les infos de détection si trouvé, None sinon
    """
    if screenshot is None:
        return None
    
    try:
        from config_manager import config_manager
        from webapp import webapp_manager
        
        # Vérifier si l'alerte existe et est activée
        if alert_name not in config_manager.config["alerts"]:
            return None
        
        alert_config = config_manager.config["alerts"][alert_name]
        if not alert_config.get("enabled", False):
            return None
        
        templates = alert_config.get("templates", [])
        if not templates:
            return None
        
        best_match = None
        best_confidence = 0.0
        
        # Essayer chaque template
        for template_data in templates:
            template_path = template_data.get("path", "")
            
            # Gérer différents formats de chemins
            if template_path.startswith("/static/"):
                template_path = template_path.replace("/static/", "static/")
            elif template_path.startswith("/"):
                template_path = template_path[1:]
            
            # Vérifier si le fichier existe
            if not os.path.exists(template_path):
                possible_paths = [
                    f"static/{template_path}",
                    f"static/alert_templates/{os.path.basename(template_path)}",
                    f"alert_templates/{os.path.basename(template_path)}"
                ]
                
                found = False
                for path in possible_paths:
                    if os.path.exists(path):
                        template_path = path
                        found = True
                        break
                
                if not found:
                    continue
            
            # Charger le template
            template_img = cv2.imread(template_path)
            if template_img is None:
                continue
            
            # Vérifier les dimensions
            if template_img.shape[0] > screenshot.shape[0] or template_img.shape[1] > screenshot.shape[1]:
                continue
            
            # Template matching
            result = cv2.matchTemplate(screenshot, template_img, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            confidence = max_val
            threshold = template_data.get("threshold", alert_config.get("threshold", 0.7))
            
            # Si la confiance est suffisante et meilleure que les précédentes
            if confidence >= threshold and confidence > best_confidence:
                h, w = template_img.shape[:2]
                
                best_match = {
                    'found': True,
                    'alert_name': alert_name,
                    'confidence': float(confidence),
                    'x': int(max_loc[0]),
                    'y': int(max_loc[1]),
                    'width': int(w),
                    'height': int(h),
                    'template_id': template_data.get("id", "unknown")
                }
                best_confidence = confidence
        
        # Si un match a été trouvé
        if best_match:
            log_info(f"✓ Alerte détectée: {alert_name} sur {source_name} ({best_confidence:.1%})")
            
            # Enregistrer dans les statistiques
            try:
                config_manager.record_detection(
                    alert_name,
                    best_match['template_id'],
                    best_match['confidence']
                )
            except:
                pass
            
            # Ajouter à l'historique web
            try:
                detection_area = {
                    'x': best_match['x'],
                    'y': best_match['y'],
                    'width': best_match['width'],
                    'height': best_match['height']
                }
                
                webapp_manager.add_alert(
                    source_name=source_name or "unknown",
                    alert_name=alert_name,
                    confidence=best_match['confidence'],
                    screenshot=screenshot,
                    detection_area=detection_area
                )
                
                # Mettre à jour l'état de la fenêtre
                if source_name and source_name in webapp_manager.windows_state:
                    webapp_manager.windows_state[source_name]['last_alert_name'] = alert_name
                    webapp_manager.windows_state[source_name]['last_alert_state'] = True
                    webapp_manager.windows_state[source_name]['last_confidence'] = best_match['confidence']
                    webapp_manager.windows_state[source_name]['total_detections'] = \
                        webapp_manager.windows_state[source_name].get('total_detections', 0) + 1
                
            except Exception as e:
                log_error(f"Erreur ajout historique: {e}")
            
            return best_match
        
        return None
    
    except Exception as e:
        log_error(f"Erreur dans check_for_alert: {e}")
        return None

def validate_detection_setup():
    """Valide la configuration de détection"""
    issues = []
    
    try:
        pytesseract.get_tesseract_version()
        log_debug("Tesseract OCR disponible")
    except Exception as e:
        issues.append(f"Tesseract OCR non disponible: {e}")
    
    from config import ALERTS, get_alert_images
    total_templates = 0
    
    for alert in ALERTS:
        if 'imgs' in alert or 'img' in alert:
            images = get_alert_images(alert)
            total_templates += len(images)
            
            valid_images = 0
            for img_path in images:
                if not os.path.exists(img_path):
                    issues.append(f"Template manquant: {img_path} pour {alert['name']}")
                else:
                    template = cv2.imread(img_path)
                    if template is None:
                        issues.append(f"Template invalide: {img_path} pour {alert['name']}")
                    else:
                        valid_images += 1
                        h, w = template.shape[:2]
                        if h < 5 or w < 5:
                            issues.append(f"Template trop petit ({w}x{h}): {img_path}")
            
            if valid_images == 0:
                issues.append(f"Aucune image valide pour {alert['name']}")
            elif valid_images < len(images):
                log_warning(f"Seulement {valid_images}/{len(images)} images valides pour {alert['name']}")
    
    if issues:
        for issue in issues:
            log_warning(f"Validation détection: {issue}")
    else:
        log_info(f"Configuration de détection validée - {total_templates} templates chargés")
    
    return len(issues) == 0, issues

def get_detection_statistics():
    """Retourne les statistiques de détection"""
    stats = {
        'total_detections': detection_stats.total_detections,
        'successful_detections': detection_stats.successful_detections,
        'success_rate': (detection_stats.successful_detections / detection_stats.total_detections * 100) if detection_stats.total_detections > 0 else 0,
        'average_detection_time': detection_stats.average_detection_time,
        'average_confidence': detection_stats.average_confidence,
        'templates_cached': len(detection_stats.template_cache),
        'confidence_history': detection_stats.confidence_history[-100:],
        'multi_image_stats': detection_stats.multi_image_stats
    }
    
    return stats

def reset_detection_statistics():
    """Remet à zéro les statistiques de détection"""
    detection_stats.reset()
    log_debug("Statistiques de détection remises à zéro")

def clear_template_cache():
    """Vide le cache des templates"""
    detection_stats.template_cache.clear()
    log_debug("Cache des templates vidé")

def get_multi_image_performance():
    """Retourne les performances par image utilisée"""
    performance = {}
    
    for alert_name, images_stats in detection_stats.multi_image_stats.items():
        total_detections = sum(img_stats['detections'] for img_stats in images_stats.values())
        
        performance[alert_name] = {
            'total_detections': total_detections,
            'images_count': len(images_stats),
            'images_performance': {}
        }
        
        for img_name, img_stats in images_stats.items():
            performance[alert_name]['images_performance'][img_name] = {
                'detections': img_stats['detections'],
                'percentage': (img_stats['detections'] / total_detections * 100) if total_detections > 0 else 0,
                'avg_confidence': img_stats['avg_confidence'],
                'max_confidence': img_stats['max_confidence']
            }
    
    return performance

def load_trained_templates(alert_name):
    """Charge les templates entraînés manuellement"""
    try:
        from training_tool import training_tool
        
        # Récupérer les templates annotés
        trained_templates = training_tool.get_alert_templates(alert_name, min_confidence=0.8)
        
        if trained_templates:
            log_info(f"Chargé {len(trained_templates)} templates entraînés pour {alert_name}")
            return trained_templates
        
    except Exception as e:
        log_debug(f"Pas de templates entraînés pour {alert_name}: {e}")
    
    return []

