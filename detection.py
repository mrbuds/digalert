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

def advanced_template_matching(screenshot, template, threshold):
    """
    Détection de template améliorée avec variations automatiques d'échelle et d'aspect ratio
    Sans avoir besoin de configuration manuelle
    """
    best_match = None
    best_confidence = 0
    
    template_h, template_w = template.shape[:2]
    screenshot_h, screenshot_w = screenshot.shape[:2]
    
    # Calculer automatiquement les échelles pertinentes basées sur les tailles
    min_scale = max(0.5, min(50.0 / template_w, 50.0 / template_h))  # Template min 50px
    max_scale = min(2.0, min(screenshot_w * 0.8 / template_w, screenshot_h * 0.8 / template_h))
    
    # Générer automatiquement des échelles adaptatives
    # Plus de précision autour de 1.0, moins aux extrêmes
    scales = []
    
    # Échelles fines autour de 1.0 (±30%)
    for s in np.arange(0.7, 1.31, 0.05):
        if min_scale <= s <= max_scale:
            scales.append(s)
    
    # Échelles plus grossières pour les extrêmes
    if min_scale < 0.7:
        for s in np.arange(min_scale, 0.7, 0.1):
            scales.append(s)
    if max_scale > 1.3:
        for s in np.arange(1.4, min(max_scale, 2.0) + 0.1, 0.1):
            scales.append(s)
    
    # Variations d'aspect ratio automatiques (déformation commune dans les jeux)
    aspect_ratios = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]
    
    # Utiliser plusieurs méthodes de matching pour plus de robustesse
    methods = [
        (cv2.TM_CCOEFF_NORMED, 1.0),    # Méthode principale
        (cv2.TM_CCORR_NORMED, 0.9),      # Méthode secondaire avec poids réduit
    ]
    
    log_debug(f"Testing {len(scales)} scales x {len(aspect_ratios)} ratios = {len(scales) * len(aspect_ratios)} combinations")
    
    for scale in scales:
        for aspect_ratio in aspect_ratios:
            try:
                # Calculer les nouvelles dimensions
                new_w = int(template_w * scale * aspect_ratio)
                new_h = int(template_h * scale)
                
                # Vérifications de sécurité
                if new_w < 20 or new_h < 20:  # Minimum 20px
                    continue
                if new_w > screenshot_w * 0.9 or new_h > screenshot_h * 0.9:
                    continue
                
                # Redimensionner le template avec interpolation de qualité
                scaled_template = cv2.resize(template, (new_w, new_h), 
                                            interpolation=cv2.INTER_LINEAR)
                
                # Essayer différentes méthodes de matching
                for method, weight in methods:
                    result = cv2.matchTemplate(screenshot, scaled_template, method)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    
                    # Appliquer le poids de la méthode
                    weighted_confidence = max_val * weight
                    
                    if weighted_confidence > best_confidence:
                        best_confidence = weighted_confidence
                        best_match = {
                            'confidence': max_val,  # Garder la confiance non pondérée pour le rapport
                            'weighted_confidence': weighted_confidence,
                            'location': max_loc,
                            'scale': scale,
                            'aspect_ratio': aspect_ratio,
                            'template_size': (new_w, new_h),
                            'method': method,
                            'original_template_size': (template_w, template_h)
                        }
                
            except Exception as e:
                log_debug(f"Erreur test scale={scale:.2f}, ratio={aspect_ratio:.2f}: {e}")
                continue
    
    # Validation supplémentaire par comparaison de features
    if best_match and best_match['confidence'] >= threshold * 0.8:
        # Valider avec une méthode complémentaire
        validation_score = validate_match_with_features(
            screenshot, template, best_match, threshold
        )
        if validation_score > 0:
            best_match['feature_validation'] = validation_score
            best_match['confidence'] = min(1.0, best_match['confidence'] * (1 + validation_score * 0.2))
    
    return best_match if best_match and best_match['confidence'] >= threshold else None

def validate_match_with_features(screenshot, template, match_result, threshold):
    """
    Validation supplémentaire d'un match en utilisant des features locales
    Retourne un score de validation entre 0 et 1
    """
    try:
        x, y = match_result['location']
        w, h = match_result['template_size']
        
        # Extraire la région détectée
        roi = screenshot[y:y+h, x:x+w]
        
        # Redimensionner le template à la même taille que le ROI pour comparaison
        template_resized = cv2.resize(template, (w, h), interpolation=cv2.INTER_LINEAR)
        
        # Méthode 1: Comparaison d'histogrammes de couleur
        hist_score = compare_color_histograms(roi, template_resized)
        
        # Méthode 2: Comparaison de gradients/contours
        edge_score = compare_edge_patterns(roi, template_resized)
        
        # Méthode 3: Comparaison de la structure locale (SSIM simplifié)
        structure_score = compare_local_structure(roi, template_resized)
        
        # Score combiné
        validation_score = (hist_score * 0.3 + edge_score * 0.4 + structure_score * 0.3)
        
        log_debug(f"Validation scores - Hist: {hist_score:.2f}, Edge: {edge_score:.2f}, Structure: {structure_score:.2f}")
        
        return validation_score if validation_score > 0.5 else 0
        
    except Exception as e:
        log_debug(f"Erreur validation features: {e}")
        return 0

def compare_color_histograms(img1, img2):
    """Compare les histogrammes de couleur de deux images"""
    try:
        # Calculer les histogrammes pour chaque canal
        hist1 = []
        hist2 = []
        
        for i in range(3):  # BGR channels
            hist1.append(cv2.calcHist([img1], [i], None, [32], [0, 256]))
            hist2.append(cv2.calcHist([img2], [i], None, [32], [0, 256]))
        
        # Normaliser et comparer
        scores = []
        for h1, h2 in zip(hist1, hist2):
            h1 = cv2.normalize(h1, h1).flatten()
            h2 = cv2.normalize(h2, h2).flatten()
            score = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
            scores.append(max(0, score))  # Garder seulement les scores positifs
        
        return sum(scores) / len(scores)
        
    except Exception:
        return 0

def compare_edge_patterns(img1, img2):
    """Compare les patterns de contours entre deux images"""
    try:
        # Convertir en niveaux de gris
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        
        # Détecter les contours
        edges1 = cv2.Canny(gray1, 50, 150)
        edges2 = cv2.Canny(gray2, 50, 150)
        
        # Comparer la densité et distribution des contours
        edge_density1 = np.sum(edges1 > 0) / edges1.size
        edge_density2 = np.sum(edges2 > 0) / edges2.size
        
        # Score basé sur la similarité de densité
        density_score = 1.0 - abs(edge_density1 - edge_density2) * 10
        density_score = max(0, min(1, density_score))
        
        # Template matching sur les contours
        if edges1.shape == edges2.shape:
            result = cv2.matchTemplate(edges1, edges2, cv2.TM_CCOEFF_NORMED)
            edge_match_score = result[0][0]
        else:
            edge_match_score = density_score
        
        return (density_score + edge_match_score) / 2
        
    except Exception:
        return 0

def compare_local_structure(img1, img2):
    """Compare la structure locale des images (version simplifiée de SSIM)"""
    try:
        # Convertir en niveaux de gris
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY).astype(np.float64)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY).astype(np.float64)
        
        # Calculer moyennes et variances
        mu1 = cv2.GaussianBlur(gray1, (11, 11), 1.5)
        mu2 = cv2.GaussianBlur(gray2, (11, 11), 1.5)
        
        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2
        
        sigma1_sq = cv2.GaussianBlur(gray1 ** 2, (11, 11), 1.5) - mu1_sq
        sigma2_sq = cv2.GaussianBlur(gray2 ** 2, (11, 11), 1.5) - mu2_sq
        sigma12 = cv2.GaussianBlur(gray1 * gray2, (11, 11), 1.5) - mu1_mu2
        
        # Constantes pour la stabilité
        c1 = 0.01 ** 2
        c2 = 0.03 ** 2
        
        # SSIM
        ssim = ((2 * mu1_mu2 + c1) * (2 * sigma12 + c2)) / \
               ((mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2))
        
        return np.mean(ssim)
        
    except Exception:
        return 0

def check_multiple_templates(screenshot, template_paths, threshold, match_strategy="best"):
    """
    Vérifie plusieurs templates avec la détection améliorée
    """
    if not template_paths:
        return None
    
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
            
            # Utiliser la détection améliorée
            match_result = advanced_template_matching(
                processed_screenshot, 
                processed_template, 
                threshold
            )
            
            if match_result and match_result['confidence'] >= threshold:
                match_result['template_path'] = template_path
                match_result['template_name'] = os.path.basename(template_path)
                results.append(match_result)
                
                log_debug(f"Match trouvé: {template_path} "
                         f"(conf: {match_result['confidence']:.3f}, "
                         f"scale: {match_result['scale']:.2f}, "
                         f"ratio: {match_result['aspect_ratio']:.2f})")
                
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

def check_for_alert(screenshot, alert, return_confidence=False, return_area=False):
    """
    Détection d'alerte avec système d'apprentissage intégré
    """
    start_time = time.time()
    
    try:
        if screenshot is None:
            log_debug("Screenshot null fourni à check_for_alert")
            if return_area:
                return (0.0, None) if return_confidence else (False, None)
            return 0.0 if return_confidence else False

        if not alert.get('enabled', True):
            if return_area:
                return (0.0, None) if return_confidence else (False, None)
            return 0.0 if return_confidence else False

        confidence = 0.0
        detection_success = False
        match_result = None
        detection_area = None
        matched_template = None
        alert_name = alert.get('name', 'unknown')

        # Détection par template matching
        if 'imgs' in alert or 'img' in alert:
            template_paths = get_alert_images(alert)
            
            if not template_paths:
                log_error(f"Aucune image spécifiée pour {alert_name}")
                if return_area:
                    return (0.0, None) if return_confidence else (False, None)
                return 0.0 if return_confidence else False

            match_strategy = alert.get('match_strategy', 'best')
            
            # NOUVEAU: Obtenir le seuil ajusté basé sur l'apprentissage
            original_threshold = alert['threshold']
            adjusted_threshold = get_adjusted_threshold(alert_name, original_threshold)
            
            # Utiliser la détection améliorée
            match_result = check_multiple_templates(
                screenshot, 
                template_paths, 
                adjusted_threshold,  # Utiliser le seuil ajusté
                match_strategy
            )
            
            if match_result:
                if 'matches' in match_result:  # Stratégie "all"
                    confidence = match_result['best_confidence']
                    matched_template = f"Multiple ({match_result['match_count']})"
                    
                    best_match = max(match_result['matches'], key=lambda x: x['confidence'])
                    if 'location' in best_match:
                        x, y = best_match['location']
                        h, w = best_match['template_size']
                        detection_area = {
                            'x': x, 'y': y, 'width': w, 'height': h,
                            'match_count': match_result['match_count'],
                            'scale': best_match.get('scale', 1.0),
                            'aspect_ratio': best_match.get('aspect_ratio', 1.0),
                            'strategy': 'all'
                        }
                
                else:  # Stratégies "best" ou "first"
                    confidence = match_result['confidence']
                    matched_template = match_result.get('template_name', 'unknown')
                    
                    if 'location' in match_result:
                        x, y = match_result['location']
                        h, w = match_result['template_size']
                        detection_area = {
                            'x': x, 'y': y, 'width': w, 'height': h,
                            'template': matched_template,
                            'scale': match_result.get('scale', 1.0),
                            'aspect_ratio': match_result.get('aspect_ratio', 1.0),
                            'feature_validation': match_result.get('feature_validation', 0)
                        }
                
                # NOUVEAU: Vérifier si cette détection ressemble à un faux positif connu
                if confidence >= adjusted_threshold and detection_area:
                    # Extraire la région détectée
                    x, y = detection_area['x'], detection_area['y']
                    w, h = detection_area['width'], detection_area['height']
                    
                    # S'assurer que les coordonnées sont valides
                    if (x >= 0 and y >= 0 and 
                        x + w <= screenshot.shape[1] and 
                        y + h <= screenshot.shape[0]):
                        
                        screenshot_region = screenshot[y:y+h, x:x+w]
                        
                        detection_params = {
                            'confidence': confidence,
                            'threshold': adjusted_threshold,
                            'scale': detection_area.get('scale', 1.0),
                            'aspect_ratio': detection_area.get('aspect_ratio', 1.0)
                        }
                        
                        # Filtrer si ça ressemble à un faux positif connu
                        if should_filter_detection(alert_name, screenshot_region, detection_params):
                            log_info(f"Détection filtrée (faux positif probable): {alert_name}")
                            confidence *= 0.5  # Réduire drastiquement la confiance
                
                # Décider si c'est une détection valide
                detection_success = confidence >= adjusted_threshold
                
                if detection_success:
                    log_debug(f"Detection {alert_name}: "
                             f"conf={confidence:.3f}, "
                             f"seuil original={original_threshold:.3f}, "
                             f"seuil ajusté={adjusted_threshold:.3f}, "
                             f"template={matched_template}")
                
            alert["history"].append(confidence)

        # Méthode OCR (reste identique)
        elif 'ocr' in alert:
            try:
                processed_screenshot = preprocess_image_for_detection(screenshot, 'ocr')
                
                ocr_config = alert.get('ocr_config', '--oem 3 --psm 6')
                language = alert.get('language', 'fra')
                
                ocr_result = pytesseract.image_to_string(
                    processed_screenshot, 
                    lang=language, 
                    config=ocr_config
                )
                
                target_text = alert['ocr'].lower()
                found_text = ocr_result.lower()
                
                if target_text in found_text:
                    confidence = 1.0
                    detection_success = True
                    matched_template = "OCR"
                    
                    match_result = {
                        'confidence': confidence,
                        'ocr_result': ocr_result.strip(),
                        'target_text': target_text
                    }
                    
                    if detection_success:
                        detection_area = {
                            'x': 0, 'y': 0,
                            'width': screenshot.shape[1],
                            'height': screenshot.shape[0],
                            'type': 'ocr'
                        }
                else:
                    confidence = 0.0
                
                alert["history"].append(confidence)
                
            except Exception as e:
                log_error(f"Erreur OCR pour {alert_name}: {e}")
                confidence = 0.0
                alert["history"].append(confidence)
        
        else:
            log_error(f"Alerte {alert_name} n'a pas de méthode de détection valide")
            if return_area:
                return (0.0, None) if return_confidence else (False, None)
            return 0.0 if return_confidence else False

        # Statistiques
        duration_ms = (time.time() - start_time) * 1000
        detection_stats.add_detection(detection_success, confidence, duration_ms, 
                                    alert_name, matched_template)
        
        # Debug si activé
        if alert.get("debug", False) or DEBUG_SAVE_SCREENSHOTS:
            save_detection_debug(screenshot, alert, match_result, detection_success)

        log_debug(f"Détection {alert_name}: conf={confidence:.3f}, "
                 f"success={detection_success}, duration={duration_ms:.1f}ms")

        if return_area:
            if return_confidence:
                return confidence, detection_area
            return detection_success, detection_area
        
        return confidence if return_confidence else detection_success

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_error(f"Erreur de détection ({alert.get('name', 'unknown')}): {e}")
        detection_stats.add_detection(False, 0.0, duration_ms)
        
        if hasattr(alert, 'history'):
            alert["history"].append(0.0)
        
        if return_area:
            return (0.0, None) if return_confidence else (False, None)
        return 0.0 if return_confidence else False

# Les autres fonctions restent identiques...
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
        log_info("Détection améliorée activée: variations automatiques d'échelle et aspect ratio")
    
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

# Garder save_detection_debug identique à l'original
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
                    
                    # Couleur différente pour chaque correspondance
                    colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0)]
                    color = colors[i % len(colors)]
                    
                    # Rectangle de détection
                    cv2.rectangle(marked_screenshot, (x, y), (x + w, y + h), color, 2)
                    
                    # Texte avec infos détaillées
                    confidence = match.get('confidence', 0)
                    scale = match.get('scale', 1.0)
                    ratio = match.get('aspect_ratio', 1.0)
                    template_name = match.get('template_name', 'unknown')
                    
                    # Afficher les infos de transformation
                    text1 = f"{template_name}: {confidence:.3f}"
                    text2 = f"S:{scale:.2f} R:{ratio:.2f}"
                    
                    cv2.putText(marked_screenshot, text1, (x, y-10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                    cv2.putText(marked_screenshot, text2, (x, y-30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                
                marked_file = f"{DEBUG_SCREENSHOT_PATH}/{alert_name}_{timestamp}_marked.png"
                cv2.imwrite(marked_file, marked_screenshot)
        
        # Sauvegarde des métadonnées avec les nouvelles infos
        metadata_file = f"{DEBUG_SCREENSHOT_PATH}/{alert_name}_{timestamp}_metadata.txt"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            f.write(f"Alert: {alert.get('name', 'N/A')}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Detection: {detection_success}\n")
            f.write(f"Threshold: {alert.get('threshold', 'N/A')}\n")
            f.write(f"Match Strategy: {alert.get('match_strategy', 'best')}\n")
            
            if match_result:
                if 'matches' in match_result:  # Stratégie "all"
                    f.write(f"Multiple matches: {match_result['match_count']}\n")
                    for i, match in enumerate(match_result['matches']):
                        f.write(f"  Match {i+1}:\n")
                        f.write(f"    Template: {match.get('template_name', 'N/A')}\n")
                        f.write(f"    Confidence: {match.get('confidence', 'N/A')}\n")
                        f.write(f"    Location: {match.get('location', 'N/A')}\n")
                        f.write(f"    Scale: {match.get('scale', 'N/A')}\n")
                        f.write(f"    Aspect Ratio: {match.get('aspect_ratio', 'N/A')}\n")
                        f.write(f"    Feature Validation: {match.get('feature_validation', 'N/A')}\n")
                else:  # Stratégies "best" ou "first"
                    f.write(f"Template: {match_result.get('template_name', 'N/A')}\n")
                    f.write(f"Confidence: {match_result.get('confidence', 'N/A')}\n")
                    f.write(f"Location: {match_result.get('location', 'N/A')}\n")
                    f.write(f"Scale: {match_result.get('scale', 'N/A')}\n")
                    f.write(f"Aspect Ratio: {match_result.get('aspect_ratio', 'N/A')}\n")
                    f.write(f"Feature Validation: {match_result.get('feature_validation', 'N/A')}\n")
                    f.write(f"Original Template Size: {match_result.get('original_template_size', 'N/A')}\n")
                    f.write(f"Matched Template Size: {match_result.get('template_size', 'N/A')}\n")
            
            f.write(f"Screenshot shape: {screenshot.shape}\n")
        
        log_debug(f"Debug détection sauvé: {alert_name}_{timestamp}")
        
    except Exception as e:
        log_error(f"Erreur sauvegarde debug détection: {e}")

def get_multi_image_performance():
    """Retourne les performances par image utilisée avec infos de transformation"""
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

def benchmark_detection_methods(screenshot, iterations=100):
    """
    Benchmark des méthodes de détection avec la nouvelle approche
    """
    if screenshot is None:
        log_error("Screenshot requis pour le benchmark")
        return None
    
    log_info(f"Benchmark détection améliorée démarré ({iterations} itérations)")
    
    from config import ALERTS
    results = {}
    
    for alert in ALERTS:
        if not alert.get('enabled', True):
            continue
            
        alert_name = alert['name']
        
        if 'imgs' in alert or 'img' in alert:
            method = 'template_adaptive'
            images_count = len(get_alert_images(alert))
        elif 'ocr' in alert:
            method = 'ocr'
            images_count = 0
        else:
            continue
        
        times = []
        confidences = []
        scales_used = []
        ratios_used = []
        
        log_debug(f"Benchmark {alert_name} ({method}, {images_count} images)...")
        
        for i in range(iterations):
            start_time = time.time()
            
            try:
                result = check_for_alert(screenshot, alert, return_confidence=True, return_area=True)
                
                if isinstance(result, tuple):
                    confidence, area = result
                else:
                    confidence = result
                    area = None
                
                duration = (time.time() - start_time) * 1000
                
                times.append(duration)
                confidences.append(confidence)
                
                if area:
                    scales_used.append(area.get('scale', 1.0))
                    ratios_used.append(area.get('aspect_ratio', 1.0))
                
            except Exception as e:
                log_error(f"Erreur benchmark {alert_name} iteration {i}: {e}")
                continue
        
        if times:
            results[alert_name] = {
                'method': method,
                'images_count': images_count,
                'iterations': len(times),
                'avg_time_ms': sum(times) / len(times),
                'min_time_ms': min(times),
                'max_time_ms': max(times),
                'avg_confidence': sum(confidences) / len(confidences),
                'max_confidence': max(confidences),
                'detections': sum(1 for c in confidences if c >= alert.get('threshold', 0.5)),
                'avg_scale': sum(scales_used) / len(scales_used) if scales_used else 1.0,
                'avg_ratio': sum(ratios_used) / len(ratios_used) if ratios_used else 1.0,
                'scale_variations': len(set(scales_used)) if scales_used else 0,
                'ratio_variations': len(set(ratios_used)) if ratios_used else 0
            }
            
            log_info(f"Benchmark {alert_name}: "
                    f"{results[alert_name]['avg_time_ms']:.1f}ms avg, "
                    f"{results[alert_name]['detections']} détections, "
                    f"scale moyen: {results[alert_name]['avg_scale']:.2f}, "
                    f"ratio moyen: {results[alert_name]['avg_ratio']:.2f}")
    
    return results

def optimize_detection_thresholds(screenshot, alerts, test_iterations=50):
    """
    Optimise automatiquement les seuils de détection avec la nouvelle méthode
    """
    log_info("Optimisation des seuils avec détection adaptative...")
    
    optimized_alerts = []
    
    for alert in alerts:
        if not alert.get('enabled', True) or not ('imgs' in alert or 'img' in alert):
            optimized_alerts.append(alert)
            continue
        
        original_threshold = alert['threshold']
        confidences = []
        successful_params = []
        
        for i in range(test_iterations):
            try:
                result = check_for_alert(screenshot, alert, return_confidence=True, return_area=True)
                
                if isinstance(result, tuple):
                    confidence, area = result
                else:
                    confidence = result
                    area = None
                
                confidences.append(confidence)
                
                if area and confidence > 0:
                    successful_params.append({
                        'scale': area.get('scale', 1.0),
                        'ratio': area.get('aspect_ratio', 1.0),
                        'confidence': confidence
                    })
                    
            except:
                continue
        
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            max_confidence = max(confidences)
            
            # Analyse des paramètres de transformation réussis
            if successful_params:
                avg_scale = sum(p['scale'] for p in successful_params) / len(successful_params)
                avg_ratio = sum(p['ratio'] for p in successful_params) / len(successful_params)
                
                log_info(f"Paramètres moyens pour {alert['name']}: "
                        f"scale={avg_scale:.2f}, ratio={avg_ratio:.2f}")
            
            # Stratégie d'optimisation conservative
            # Prendre en compte les variations de transformation
            variation_penalty = 0.05 if len(successful_params) > 1 else 0
            suggested_threshold = min(max_confidence * 0.8, avg_confidence * 0.9) - variation_penalty
            
            # S'assurer que le nouveau seuil n'est pas trop bas
            suggested_threshold = max(suggested_threshold, 0.3)
            
            if abs(suggested_threshold - original_threshold) > 0.05:
                alert_copy = alert.copy()
                alert_copy['threshold'] = suggested_threshold
                alert_copy['original_threshold'] = original_threshold
                
                # Ajouter les paramètres de transformation optimaux si trouvés
                if successful_params:
                    alert_copy['optimal_scale'] = avg_scale
                    alert_copy['optimal_ratio'] = avg_ratio
                
                log_info(f"Seuil optimisé pour {alert['name']}: "
                        f"{original_threshold:.3f} -> {suggested_threshold:.3f}")
                
                optimized_alerts.append(alert_copy)
            else:
                optimized_alerts.append(alert)
        else:
            log_warning(f"Impossible d'optimiser {alert['name']}: aucune donnée")
            optimized_alerts.append(alert)
    
    return optimized_alerts