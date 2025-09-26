# -*- coding: utf-8 -*-
"""
Module de détection unifié - Version refactorisée
Combine detection.py et simple_detection.py
"""

import cv2
import numpy as np
import os
try:
    from .constants import DEFAULT_THRESHOLD
except ImportError:
    DEFAULT_THRESHOLD = 0.7

class AlertDetector:
    """Détecteur d'alertes unifié"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.template_cache = {}
        
    def check_alert(self, screenshot, alert_name, source_name=None):
        """Vérifie une alerte sur un screenshot"""
        if alert_name not in self.config_manager.config["alerts"]:
            return None
            
        alert_config = self.config_manager.config["alerts"][alert_name]
        if not alert_config.get("enabled", False):
            return None
            
        templates = alert_config.get("templates", [])
        if not templates:
            return None
            
        best_match = None
        best_confidence = 0.0
        
        for template_data in templates:
            result = self._match_template(screenshot, template_data)
            if result and result['confidence'] > best_confidence:
                best_match = result
                best_confidence = result['confidence']
                
        return best_match
        
    def _match_template(self, screenshot, template_data):
        """Effectue le template matching"""
        template_path = template_data.get("path", "")
        threshold = template_data.get("threshold", DEFAULT_THRESHOLD)
        
        # Gestion des chemins
        if template_path.startswith("/static/"):
            template_path = template_path.replace("/static/", "data/")
        elif not template_path.startswith("data/"):
            template_path = f"data/{template_path}"
            
        if not os.path.exists(template_path):
            return None
            
        # Cache des templates
        if template_path not in self.template_cache:
            template_img = cv2.imread(template_path)
            if template_img is None:
                return None
            self.template_cache[template_path] = template_img
            
        template_img = self.template_cache[template_path]
        
        # Template matching
        result = cv2.matchTemplate(screenshot, template_img, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= threshold:
            h, w = template_img.shape[:2]
            return {
                'found': True,
                'confidence': float(max_val),
                'x': int(max_loc[0]),
                'y': int(max_loc[1]),
                'width': int(w),
                'height': int(h),
                'template_id': template_data.get("id", "unknown")
            }
            
        return None
        
    def check_all_alerts(self, screenshot, source_name):
        """Vérifie toutes les alertes actives"""
        results = {}
        
        for alert_name in self.config_manager.config["alerts"]:
            result = self.check_alert(screenshot, alert_name, source_name)
            if result:
                results[alert_name] = result
                
        return results

# Fonction de compatibilité
def check_for_alert(screenshot, alert_name, source_name=None):
    """Fonction de compatibilité avec l'ancien système"""
    from .config_manager import config_manager
    detector = AlertDetector(config_manager)
    return detector.check_alert(screenshot, alert_name, source_name)
