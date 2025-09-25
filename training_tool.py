# -*- coding: utf-8 -*-
import os
import json
from datetime import datetime
from utils import log_info, log_error, ensure_directory_exists

class InteractiveTrainingTool:
    def __init__(self):
        self.training_data_dir = "training_data"
        self.annotations_file = os.path.join(self.training_data_dir, "manual_annotations.json")
        
        ensure_directory_exists(self.training_data_dir)
        self.annotations = self.load_annotations()
    
    def load_annotations(self):
        if os.path.exists(self.annotations_file):
            try:
                with open(self.annotations_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {'annotations': [], 'templates': {}}
    
    def save_annotations(self):
        try:
            with open(self.annotations_file, 'w') as f:
                json.dump(self.annotations, f, indent=2)
        except Exception as e:
            log_error(f"Erreur sauvegarde annotations: {e}")
    
    def get_training_statistics(self):
        return {
            'total_annotations': len(self.annotations['annotations']),
            'manual_annotations': len([a for a in self.annotations['annotations'] if a.get('is_manual')]),
            'alerts_with_templates': len(self.annotations['templates'])
        }

# Instance globale
training_tool = InteractiveTrainingTool()