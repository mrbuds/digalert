# -*- coding: utf-8 -*-
import json
import os
import shutil
from datetime import datetime
from utils import log_info, log_error, ensure_directory_exists
import cv2

class ConfigManager:
    def __init__(self):
        self.config_file = "unified_config.json"
        self.templates_dir = "static/alert_templates"
        self.backup_dir = "config_backups"
        
        ensure_directory_exists(self.templates_dir)
        ensure_directory_exists(self.backup_dir)
        
        self.config = self.load_or_migrate_config()
    
    def load_or_migrate_config(self):
        """Charge la config ou migre depuis l'ancien système"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    log_info(f"Configuration chargée: {len(config.get('alerts', {}))} alertes")
                    return config
            except Exception as e:
                log_error(f"Erreur chargement config: {e}")
        
        # Config par défaut
        return self.create_default_config()
    
    def create_default_config(self):
        """Crée une configuration par défaut"""
        config = {
            "version": "2.0",
            "sources": {},
            "alerts": {
                "Dig!": {
                    "enabled": True,
                    "threshold": 0.7,
                    "cooldown": 300,
                    "templates": []
                },
                "EGGGGGG!": {
                    "enabled": True,
                    "threshold": 0.7,
                    "cooldown": 300,
                    "templates": []
                },
                "TITANIUM!": {
                    "enabled": True,
                    "threshold": 0.7,
                    "cooldown": 300,
                    "templates": []
                }
            },
            "global_settings": {
                "default_threshold": 0.7,
                "check_interval": 2.0,
                "notification_cooldown": 300
            }
        }
        
        self.save_config(config)
        return config
    
    def save_config(self, config=None):
        """Sauvegarde la configuration"""
        if config is None:
            config = self.config
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            log_info("Configuration sauvegardée")
            return True
        except Exception as e:
            log_error(f"Erreur sauvegarde config: {e}")
            return False
    
    def add_alert(self, alert_name, threshold=0.7):
        """Ajoute une nouvelle alerte"""
        if alert_name not in self.config["alerts"]:
            self.config["alerts"][alert_name] = {
                "enabled": True,
                "threshold": threshold,
                "cooldown": 300,
                "templates": []
            }
            self.save_config()
            return True
        return False
    
    def add_template(self, alert_name, image_region, source_name=None, threshold=None):
        """Ajoute un template à une alerte"""
        if alert_name not in self.config["alerts"]:
            self.add_alert(alert_name)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"{alert_name}_{timestamp}.png"
        filepath = os.path.join(self.templates_dir, filename)
        
        cv2.imwrite(filepath, image_region)
        
        template_id = f"{alert_name}_{timestamp}"
        template_data = {
            "id": template_id,
            "path": f"/static/alert_templates/{filename}",
            "threshold": threshold or self.config["alerts"][alert_name]["threshold"],
            "created": datetime.now().isoformat(),
            "source": source_name or "manual",
            "size": {"width": image_region.shape[1], "height": image_region.shape[0]},
            "stats": {
                "detections": 0,
                "false_positives": 0,
                "last_used": None,
                "confidence_history": []
            }
        }
        
        self.config["alerts"][alert_name]["templates"].append(template_data)
        self.save_config()
        
        return template_id
    
    def remove_template(self, alert_name, template_id):
        """Supprime un template"""
        if alert_name in self.config["alerts"]:
            templates = self.config["alerts"][alert_name]["templates"]
            
            for i, template in enumerate(templates):
                if template["id"] == template_id:
                    if os.path.exists(template["path"]):
                        try:
                            os.remove(template["path"])
                        except:
                            pass
                    templates.pop(i)
                    self.save_config()
                    return True
        return False
    
    def update_template_threshold(self, alert_name, template_id, new_threshold):
        """Met à jour le seuil d'un template"""
        if alert_name in self.config["alerts"]:
            for template in self.config["alerts"][alert_name]["templates"]:
                if template["id"] == template_id:
                    template["threshold"] = new_threshold
                    self.save_config()
                    return True
        return False
    
    def record_detection(self, alert_name, template_id, confidence, is_false_positive=False):
        """Enregistre une détection ou un faux positif"""
        if alert_name in self.config["alerts"]:
            for template in self.config["alerts"][alert_name]["templates"]:
                if template["id"] == template_id:
                    if is_false_positive:
                        template["stats"]["false_positives"] += 1
                    else:
                        template["stats"]["detections"] += 1
                    
                    template["stats"]["last_used"] = datetime.now().isoformat()
                    template["stats"]["confidence_history"].append({
                        "confidence": confidence,
                        "timestamp": datetime.now().isoformat(),
                        "false_positive": is_false_positive
                    })
                    
                    if len(template["stats"]["confidence_history"]) > 100:
                        template["stats"]["confidence_history"] = template["stats"]["confidence_history"][-100:]
                    
                    self.save_config()
                    return True
        return False
    
    def predict_threshold_effect(self, alert_name, template_id, new_threshold, test_screenshot=None):
        """Prédit si un nouveau seuil détecterait quelque chose"""
        if not test_screenshot or alert_name not in self.config["alerts"]:
            return None
        
        for template in self.config["alerts"][alert_name]["templates"]:
            if template["id"] == template_id:
                if not os.path.exists(template["path"]):
                    return None
                
                template_img = cv2.imread(template["path"])
                if template_img is None:
                    return None
                
                result = cv2.matchTemplate(test_screenshot, template_img, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                
                return {
                    "current_confidence": max_val,
                    "would_detect_current": max_val >= template["threshold"],
                    "would_detect_new": max_val >= new_threshold
                }
        return None

# Instance globale
config_manager = ConfigManager()