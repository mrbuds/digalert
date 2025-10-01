# -*- coding: utf-8 -*-
import cv2
import numpy as np
import time
import os
from collections import deque
from utils import log_error, log_debug, log_warning, log_info, ensure_directory_exists
from config import DEBUG_SAVE_SCREENSHOTS, DEBUG_SCREENSHOT_PATH, DEBUG_SHOW_DETECTION_AREAS

class DetectionStats:
    """Classe pour suivre les statistiques de détection avec thread-safety"""
    def __init__(self):
        self.reset()
        self._lock = None
    
    def reset(self):
        self.total_detections = 0
        self.successful_detections = 0
        self.false_positives = 0
        self.template_cache = {}
        self.detection_times = deque(maxlen=1000)  # Limiter la mémoire
        self.confidence_history = deque(maxlen=1000)
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
                    'min_confidence': 1.0,
                    'avg_confidence': 0.0
                }
            
            stats = self.multi_image_stats[alert_name][matched_image]
            stats['detections'] += 1
            stats['total_confidence'] += confidence
            stats['max_confidence'] = max(stats['max_confidence'], confidence)
            stats['min_confidence'] = min(stats['min_confidence'], confidence)
            stats['avg_confidence'] = stats['total_confidence'] / stats['detections']
    
    @property
    def average_detection_time(self):
        return sum(self.detection_times) / len(self.detection_times) if self.detection_times else 0
    
    @property
    def average_confidence(self):
        return sum(self.confidence_history) / len(self.confidence_history) if self.confidence_history else 0

# Instance globale
detection_stats = DetectionStats()


def cleanup_template_cache_if_needed(max_size=50):
    """Nettoie le cache si trop volumineux - optimisé"""
    global detection_stats
    cache_size = len(detection_stats.template_cache)
    
    if cache_size > max_size:
        # Garder seulement les templates les plus récents
        items = list(detection_stats.template_cache.items())
        detection_stats.template_cache = dict(items[-max_size//2:])
        log_debug(f"Cache nettoyé: {cache_size} → {len(detection_stats.template_cache)} templates")


def load_template_cached(template_path):
    """Charge un template avec mise en cache optimisée"""
    if template_path in detection_stats.template_cache:
        return detection_stats.template_cache[template_path]
    
    try:
        if not os.path.exists(template_path):
            log_error(f"Template introuvable: {template_path}")
            return None
        
        # Lecture optimisée
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            log_error(f"Impossible de charger: {template_path}")
            return None
        
        h, w = template.shape[:2]
        
        # Validation taille
        if h < 10 or w < 10:
            log_warning(f"Template très petit ({w}x{h}): {template_path}")
        elif h > 800 or w > 800:
            log_warning(f"Template très grand ({w}x{h}): {template_path}")
        
        # Stocker dans le cache
        detection_stats.template_cache[template_path] = template
        log_debug(f"Template chargé: {os.path.basename(template_path)} ({w}x{h})")
        
        return template
        
    except Exception as e:
        log_error(f"Erreur chargement template {template_path}: {e}")
        return None


def preprocess_image_for_detection(image, enhance=True):
    """Prétraitement optimisé de l'image"""
    if image is None:
        return None
    
    if not enhance:
        return image
    
    try:
        # Conversion LAB pour amélioration contraste
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a, b = cv2.split(lab)
        
        # CLAHE optimisé
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l_channel)
        
        enhanced = cv2.merge((cl, a, b))
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        
        return enhanced
        
    except Exception as e:
        log_debug(f"Erreur prétraitement: {e}")
        return image


def template_matching_multi_scale(screenshot, template, threshold, scales=None):
    """
    Détection multi-échelle optimisée avec early stopping
    """
    if scales is None:
        # Échelles optimisées pour éviter trop de calculs
        scales = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]
    
    template_h, template_w = template.shape[:2]
    screenshot_h, screenshot_w = screenshot.shape[:2]
    
    best_match = None
    best_confidence = 0
    
    for scale in scales:
        try:
            # Calculer nouvelles dimensions
            new_w = int(template_w * scale)
            new_h = int(template_h * scale)
            
            # Validation taille
            if new_w < 20 or new_h < 20:
                continue
            
            if new_w > screenshot_w or new_h > screenshot_h:
                continue
            
            # Redimensionnement
            scaled_template = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            
            # Template matching
            result = cv2.matchTemplate(screenshot, scaled_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            # Early stopping si excellente correspondance
            if max_val > 0.95:
                return {
                    'confidence': max_val,
                    'location': max_loc,
                    'scale': scale,
                    'template_size': (new_w, new_h)
                }
            
            # Garder le meilleur
            if max_val > best_confidence:
                best_confidence = max_val
                best_match = {
                    'confidence': max_val,
                    'location': max_loc,
                    'scale': scale,
                    'template_size': (new_w, new_h)
                }
                
        except Exception as e:
            log_debug(f"Erreur matching échelle {scale}: {e}")
            continue
    
    return best_match


def check_multiple_templates(screenshot, template_paths, threshold, match_strategy="best", preprocessed_screenshot=None):
    """
    Vérifie plusieurs templates de manière optimisée
    """
    if not template_paths:
        return None
    
    # Utiliser screenshot prétraité si fourni
    if preprocessed_screenshot is None:
        processed_screenshot = preprocess_image_for_detection(screenshot, enhance=True)
    else:
        processed_screenshot = preprocessed_screenshot
    
    if processed_screenshot is None:
        return None
    
    results = []
    
    for template_path in template_paths:
        try:
            # Chargement depuis cache
            template = load_template_cached(template_path)
            if template is None:
                continue
            
            # Prétraitement template (léger)
            processed_template = preprocess_image_for_detection(template, enhance=True)
            if processed_template is None:
                continue
            
            # Matching multi-échelle
            match_result = template_matching_multi_scale(
                processed_screenshot, 
                processed_template, 
                threshold
            )
            
            if match_result and match_result['confidence'] >= threshold:
                match_result['template_path'] = template_path
                match_result['template_name'] = os.path.basename(template_path)
                results.append(match_result)
                
                log_debug(f"✓ Match: {match_result['template_name']} "
                         f"({match_result['confidence']:.3f}, échelle: {match_result['scale']:.2f})")
                
                # Early stopping pour stratégie "first"
                if match_strategy == "first":
                    break
                
                # Early stopping si excellente correspondance
                if match_result['confidence'] > 0.95 and match_strategy == "best":
                    break
        
        except Exception as e:
            log_error(f"Erreur template {template_path}: {e}")
            continue
    
    if not results:
        return None
    
    # Retourner selon stratégie
    if match_strategy == "best":
        return max(results, key=lambda x: x['confidence'])
    elif match_strategy == "first":
        return results[0]
    elif match_strategy == "all":
        return {
            'matches': results,
            'best_confidence': max(r['confidence'] for r in results),
            'match_count': len(results),
            'strategy': 'all'
        }
    
    return max(results, key=lambda x: x['confidence'])


def save_detection_debug(screenshot, alert, match_result, detection_success):
    """Sauvegarde debug optimisée"""
    if not DEBUG_SAVE_SCREENSHOTS:
        return
    
    try:
        ensure_directory_exists(DEBUG_SCREENSHOT_PATH)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        alert_name = alert.get('name', 'unknown').replace('!', '').replace(' ', '_')
        status = "detected" if detection_success else "missed"
        
        # Sauvegarde screenshot
        screenshot_file = f"{DEBUG_SCREENSHOT_PATH}/{alert_name}_{timestamp}_{status}.png"
        cv2.imwrite(screenshot_file, screenshot)
        
        # Marquer les zones détectées
        if detection_success and match_result and DEBUG_SHOW_DETECTION_AREAS:
            marked_screenshot = screenshot.copy()
            
            matches = match_result.get('matches', [match_result]) if 'matches' in match_result else [match_result]
            
            for i, match in enumerate(matches):
                if 'location' in match:
                    x, y = match['location']
                    w, h = match['template_size']
                    
                    # Couleurs variées
                    colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0)]
                    color = colors[i % len(colors)]
                    
                    cv2.rectangle(marked_screenshot, (x, y), (x + w, y + h), color, 2)
                    
                    # Annotations
                    confidence = match.get('confidence', 0)
                    template_name = match.get('template_name', 'unknown')
                    scale = match.get('scale', 1.0)
                    
                    text = f"{template_name}: {confidence:.3f} (s:{scale:.2f})"
                    cv2.putText(marked_screenshot, text, (x, y-10), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            
            marked_file = f"{DEBUG_SCREENSHOT_PATH}/{alert_name}_{timestamp}_marked.png"
            cv2.imwrite(marked_file, marked_screenshot)
        
        # Métadonnées compactes
        metadata_file = f"{DEBUG_SCREENSHOT_PATH}/{alert_name}_{timestamp}_meta.json"
        import json
        with open(metadata_file, 'w', encoding='utf-8') as f:
            meta = {
                'alert': alert.get('name'),
                'timestamp': timestamp,
                'detected': detection_success,
                'threshold': alert.get('threshold'),
                'screenshot_shape': screenshot.shape[:2] if screenshot is not None else None
            }
            if match_result:
                if 'matches' in match_result:
                    meta['matches'] = [
                        {
                            'template': m.get('template_name'),
                            'confidence': m.get('confidence'),
                            'scale': m.get('scale')
                        } for m in match_result['matches']
                    ]
                else:
                    meta['match'] = {
                        'template': match_result.get('template_name'),
                        'confidence': match_result.get('confidence'),
                        'scale': match_result.get('scale')
                    }
            json.dump(meta, f, indent=2)
        
    except Exception as e:
        log_error(f"Erreur sauvegarde debug: {e}")


def check_for_alert(screenshot, alert_name, source_name=None):
    """
    Vérifie la présence d'une alerte - VERSION OPTIMISÉE
    """
    if screenshot is None:
        return None
    
    start_time = time.time()
    
    try:
        from config_manager import config_manager
        
        # Vérifications rapides
        if alert_name not in config_manager.config["alerts"]:
            return None
        
        alert_config = config_manager.config["alerts"][alert_name]
        if not alert_config.get("enabled", False):
            return None
        
        templates = alert_config.get("templates", [])
        if not templates:
            return None
        
        # Prétraitement une seule fois
        processed_screenshot = preprocess_image_for_detection(screenshot, enhance=True)
        
        best_match = None
        best_confidence = 0.0
        
        # Récupérer tous les chemins de templates
        template_paths = []
        for template_data in templates:
            template_path = template_data.get("path", "")
            
            # Normaliser le chemin
            if template_path.startswith("/static/"):
                template_path = template_path.replace("/static/", "static/")
            elif template_path.startswith("/"):
                template_path = template_path[1:]
            
            # Vérifier existence
            if not os.path.exists(template_path):
                # Essayer chemins alternatifs
                possible_paths = [
                    f"static/{template_path}",
                    f"static/alert_templates/{os.path.basename(template_path)}"
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        template_path = path
                        break
                else:
                    continue
            
            template_paths.append((template_path, template_data))
        
        # Vérifier chaque template
        for template_path, template_data in template_paths:
            try:
                template_img = load_template_cached(template_path)
                if template_img is None:
                    continue
                
                # Validation dimensions
                if template_img.shape[0] > screenshot.shape[0] or template_img.shape[1] > screenshot.shape[1]:
                    continue
                
                # Template matching optimisé
                result = cv2.matchTemplate(processed_screenshot, template_img, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                
                confidence = max_val
                threshold = template_data.get("threshold", alert_config.get("threshold", 0.7))
                
                # Vérifier seuil et garder le meilleur
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
                        'template_id': template_data.get("id", "unknown"),
                        'template_path': template_path
                    }
                    best_confidence = confidence
                    
                    # Early stopping si excellente correspondance
                    if confidence > 0.95:
                        break
            
            except Exception as e:
                log_debug(f"Erreur matching template: {e}")
                continue
        
        # Enregistrer statistiques
        duration_ms = (time.time() - start_time) * 1000
        detection_stats.add_detection(
            best_match is not None,
            best_confidence,
            duration_ms,
            alert_name,
            best_match.get('template_path') if best_match else None
        )
        
        # Si match trouvé
        if best_match:
            log_info(f"✓ Alerte détectée: {alert_name} sur {source_name} "
                    f"({best_confidence:.1%}) en {duration_ms:.1f}ms")
            
            # Enregistrer dans config_manager
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
                from webapp import webapp_manager
                
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
                
                # Mettre à jour état fenêtre
                if source_name and source_name in webapp_manager.windows_state:
                    webapp_manager.windows_state[source_name].update({
                        'last_alert_name': alert_name,
                        'last_alert_state': True,
                        'last_confidence': best_match['confidence'],
                        'total_detections': webapp_manager.windows_state[source_name].get('total_detections', 0) + 1
                    })
                
            except Exception as e:
                log_debug(f"Erreur ajout historique: {e}")
            
            return best_match
        
        return None
    
    except Exception as e:
        log_error(f"Erreur dans check_for_alert: {e}")
        return None


def validate_detection_setup():
    """Valide la configuration de détection - optimisé"""
    issues = []
    warnings = []
    
    from config_manager import config_manager
    
    total_templates = 0
    valid_templates = 0
    
    for alert_name, alert_config in config_manager.config.get("alerts", {}).items():
        templates = alert_config.get("templates", [])
        total_templates += len(templates)
        
        for template in templates:
            template_path = template.get("path", "")
            
            if template_path.startswith("/"):
                template_path = template_path[1:]
            
            if os.path.exists(template_path):
                # Vérifier lisibilité
                try:
                    img = cv2.imread(template_path)
                    if img is not None:
                        valid_templates += 1
                        h, w = img.shape[:2]
                        if h < 20 or w < 20:
                            warnings.append(f"Template très petit ({w}x{h}): {alert_name}")
                    else:
                        issues.append(f"Template illisible: {template_path}")
                except:
                    issues.append(f"Erreur lecture: {template_path}")
            else:
                warnings.append(f"Template manquant: {template_path}")
    
    if issues:
        for issue in issues:
            log_warning(f"Validation: {issue}")
    
    if valid_templates > 0:
        log_info(f"✓ Configuration validée - {valid_templates}/{total_templates} templates valides")
    else:
        log_warning(f"Aucun template valide trouvé")
    
    return len(issues) == 0, issues, warnings


def get_detection_statistics():
    """Retourne les statistiques de détection"""
    stats = {
        'total_detections': detection_stats.total_detections,
        'successful_detections': detection_stats.successful_detections,
        'success_rate': (detection_stats.successful_detections / detection_stats.total_detections * 100) 
                       if detection_stats.total_detections > 0 else 0,
        'average_detection_time': detection_stats.average_detection_time,
        'average_confidence': detection_stats.average_confidence,
        'templates_cached': len(detection_stats.template_cache),
        'confidence_history': list(detection_stats.confidence_history),
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
                'max_confidence': img_stats['max_confidence'],
                'min_confidence': img_stats['min_confidence']
            }
    
    return performance