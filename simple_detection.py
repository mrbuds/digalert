# -*- coding: utf-8 -*-
import cv2
import os
from config_manager import config_manager
from utils import log_info, log_debug, log_warning

class SimpleDetector:
    def __init__(self):
        self.config = config_manager.config
        self.last_detection_info = {}
    
    def check_screenshot(self, screenshot, source_name):
        """Vérifie toutes les alertes sur un screenshot"""
        results = {}
        
        print(f"\n=== DÉTECTION DEBUG ===")
        print(f"Source reçue: '{source_name}'")
        print(f"Type de source: {type(source_name)}")
        print(f"Taille screenshot: {screenshot.shape if screenshot is not None else 'None'}")
        
        # Vérifier les alertes configurées
        enabled_alerts = [(name, len(cfg.get('templates', []))) 
                        for name, cfg in self.config["alerts"].items() 
                        if cfg.get("enabled", False)]
        print(f"Alertes actives: {enabled_alerts}")
        
        for alert_name, alert_config in self.config["alerts"].items():
            if not alert_config["enabled"]:
                continue
            
            templates = alert_config.get("templates", [])
            if not templates:
                print(f"  ⚠️ {alert_name}: Aucun template")
                continue
            
            print(f"  Vérification {alert_name}: {len(templates)} template(s)")
            
            result = self.check_alert(screenshot, alert_name, source_name)
            if result and result["found"]:
                print(f"  ✓ TROUVÉ: {alert_name} (conf: {result['confidence']:.3f})")
                results[alert_name] = result
            else:
                print(f"  ✗ Non détecté")
        
        print(f"Résultat final: {len(results)} détection(s)")
        print("===================\n")
        
        return results
    
    def check_alert(self, screenshot, alert_name, source_name):
        """Vérifie une alerte spécifique avec traçabilité du template"""
        if alert_name not in self.config["alerts"]:
            return None
        
        alert_config = self.config["alerts"][alert_name]
        if not alert_config["enabled"]:
            return None
        
        best_match = None
        
        for template in alert_config["templates"]:
            if not os.path.exists(template["path"]):
                continue
            
            template_img = cv2.imread(template["path"])
            if template_img is None:
                continue
            
            try:
                result = cv2.matchTemplate(screenshot, template_img, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                
                threshold = template.get("threshold", alert_config["threshold"])
                
                if max_val >= threshold:
                    if not best_match or max_val > best_match["confidence"]:
                        h, w = template_img.shape[:2]
                        best_match = {
                            "found": True,
                            "alert_name": alert_name,
                            "confidence": max_val,
                            "threshold": threshold,
                            "x": max_loc[0],
                            "y": max_loc[1],
                            "width": w,
                            "height": h,
                            "template_id": template["id"],
                            "template_path": template["path"]
                        }
                        log_debug(f"Match trouvé: {alert_name} avec template {template['id']} (conf: {max_val:.3f})")
            
            except Exception as e:
                log_warning(f"Erreur template matching pour {template['id']}: {e}")
                continue
        
        if best_match:
            # Enregistrer la détection dans les stats
            config_manager.record_detection(
                alert_name, 
                best_match["template_id"], 
                best_match["confidence"]
            )
            
            # AJOUTER À L'HISTORIQUE WEB
            try:
                from webapp import webapp_manager
                
                detection_area = {
                    'x': best_match['x'],
                    'y': best_match['y'],
                    'width': best_match['width'],
                    'height': best_match['height']
                }
                
                # Ajouter à l'historique
                webapp_manager.add_alert(
                    source_name=source_name,
                    alert_name=alert_name,
                    confidence=best_match["confidence"],
                    screenshot=screenshot,
                    detection_area=detection_area
                )
                
                # Mettre à jour aussi l'état de la fenêtre
                if source_name in webapp_manager.windows_state:
                    webapp_manager.windows_state[source_name]['last_alert_name'] = alert_name
                    webapp_manager.windows_state[source_name]['last_alert_state'] = True
                    webapp_manager.windows_state[source_name]['last_confidence'] = best_match["confidence"]
                    webapp_manager.windows_state[source_name]['total_detections'] = \
                        webapp_manager.windows_state[source_name].get('total_detections', 0) + 1
                
                log_info(f"✓ Alerte ajoutée à l'historique: {alert_name} sur {source_name} ({best_match['confidence']:.1%})")
                
            except Exception as e:
                log_warning(f"Impossible d'ajouter à l'historique web: {e}")
            
            self.last_detection_info[f"{source_name}_{alert_name}"] = best_match
        
        return best_match
    
    def mark_false_positive(self, source_name, alert_name):
        """Marque la dernière détection comme faux positif"""
        key = f"{source_name}_{alert_name}"
        
        if key in self.last_detection_info:
            detection = self.last_detection_info[key]
            
            config_manager.record_detection(
                alert_name,
                detection["template_id"],
                detection["confidence"],
                is_false_positive=True
            )
            
            log_info(f"Faux positif enregistré: {alert_name} / template {detection['template_id']}")
            
            return {
                "template_id": detection["template_id"],
                "confidence": detection["confidence"]
            }
        
        return None
    
    def test_threshold_change(self, screenshot, alert_name, template_id, new_threshold):
        """Teste l'effet d'un changement de seuil"""
        return config_manager.predict_threshold_effect(
            alert_name, 
            template_id, 
            new_threshold, 
            screenshot
        )

# Instance globale
detector = SimpleDetector()