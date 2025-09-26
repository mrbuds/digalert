# -*- coding: utf-8 -*-
"""
Gestionnaire de configuration FONCTIONNEL
"""

import json
import os
from pathlib import Path

class ConfigManager:
    """Gestionnaire de configuration simple et efficace"""
    
    def __init__(self):
        self.config_file = Path('data/config.json')
        self.config = self.load_config()
    
    def load_config(self):
        """Charge la configuration depuis le fichier"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    print(f"CONFIG - Configuration chargée: {len(config.get('sources', []))} sources")
                    return config
            else:
                print("CONFIG - Fichier config.json non trouvé, création config par défaut")
                return self.create_default_config()
        except Exception as e:
            print(f"CONFIG - Erreur chargement: {e}")
            return self.create_default_config()
    
    def create_default_config(self):
        """Crée une configuration par défaut"""
        default_config = {
            "version": "3.0",
            "sources": [
                {
                    "name": "lastwar1",
                    "window_title": "Last War-Survival Game",
                    "enabled": True
                }
            ],
            "alerts": {
                "Dig!": {
                    "enabled": True,
                    "threshold": 0.7,
                    "cooldown": 300,
                    "templates": []
                }
            },
            "settings": {
                "check_interval": 2.0,
                "default_threshold": 0.7
            }
        }
        
        # Sauvegarder immédiatement
        self.save_config(default_config)
        return default_config
    
    def save_config(self, config=None):
        """Sauvegarde la configuration"""
        if config is None:
            config = self.config
        
        try:
            # S'assurer que le dossier existe
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Sauvegarder
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # Mettre à jour la config en mémoire
            self.config = config
            
            print("CONFIG - Configuration sauvegardée avec succès")
            return True
        except Exception as e:
            print(f"CONFIG - Erreur sauvegarde: {e}")
            return False
    
    def add_source(self, name, window_title, enabled=True):
        """Ajoute une nouvelle source"""
        if "sources" not in self.config:
            self.config["sources"] = []
        
        # Vérifier si existe déjà
        for source in self.config["sources"]:
            if source.get("name") == name:
                return False, "Source déjà existante"
        
        # Ajouter la nouvelle source
        new_source = {
            "name": name,
            "window_title": window_title,
            "enabled": enabled
        }
        
        self.config["sources"].append(new_source)
        
        # Sauvegarder
        if self.save_config():
            print(f"CONFIG - Source ajoutée: {name}")
            return True, "Source ajoutée avec succès"
        else:
            # Rollback en cas d'erreur
            self.config["sources"].pop()
            return False, "Erreur lors de la sauvegarde"
    
    def remove_source(self, name):
        """Supprime une source"""
        if "sources" not in self.config:
            return False, "Aucune source configurée"
        
        # Trouver et supprimer
        for i, source in enumerate(self.config["sources"]):
            if source.get("name") == name:
                removed_source = self.config["sources"].pop(i)
                
                # Sauvegarder
                if self.save_config():
                    print(f"CONFIG - Source supprimée: {name}")
                    return True, "Source supprimée avec succès"
                else:
                    # Rollback
                    self.config["sources"].insert(i, removed_source)
                    return False, "Erreur lors de la sauvegarde"
        
        return False, "Source non trouvée"
    
    def toggle_source(self, name):
        """Active/désactive une source"""
        if "sources" not in self.config:
            return False, "Aucune source configurée"
        
        for source in self.config["sources"]:
            if source.get("name") == name:
                source["enabled"] = not source.get("enabled", True)
                
                # Sauvegarder
                if self.save_config():
                    status = "activée" if source["enabled"] else "désactivée"
                    print(f"CONFIG - Source {status}: {name}")
                    return True, f"Source {status} avec succès"
                else:
                    # Rollback
                    source["enabled"] = not source["enabled"]
                    return False, "Erreur lors de la sauvegarde"
        
        return False, "Source non trouvée"
    
    def get_sources(self):
        """Retourne la liste des sources"""
        return self.config.get("sources", [])
    
    def reload_config(self):
        """Recharge la configuration depuis le disque"""
        self.config = self.load_config()
        return self.config

# Instance globale
config_manager = ConfigManager()
