# -*- coding: utf-8 -*-
"""
Système d'apprentissage pour améliorer la détection basé sur les retours utilisateur
"""
import json
import os
import time
import cv2
import numpy as np
from datetime import datetime
from utils import log_info, log_debug, log_error, ensure_directory_exists

class DetectionLearningSystem:
    """
    Système d'apprentissage qui stocke les validations utilisateur
    et adapte les paramètres de détection
    """
    
    def __init__(self, data_dir="learning_data"):
        self.data_dir = data_dir
        self.learning_file = os.path.join(data_dir, "detection_learning.json")
        self.false_positives_dir = os.path.join(data_dir, "false_positives")
        self.true_positives_dir = os.path.join(data_dir, "true_positives")
        
        # Créer les dossiers nécessaires
        ensure_directory_exists(data_dir)
        ensure_directory_exists(self.false_positives_dir)
        ensure_directory_exists(self.true_positives_dir)
        
        # Charger les données d'apprentissage existantes
        self.learning_data = self.load_learning_data()
        
        # Cache des patterns de faux positifs
        self.false_positive_patterns = {}
        self.load_false_positive_patterns()
    
    def load_learning_data(self):
        """Charge les données d'apprentissage depuis le fichier"""
        if os.path.exists(self.learning_file):
            try:
                with open(self.learning_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    log_info(f"Données d'apprentissage chargées: {len(data.get('validations', []))} validations")
                    return data
            except Exception as e:
                log_error(f"Erreur chargement données apprentissage: {e}")
        
        # Structure par défaut
        return {
            'validations': [],
            'alert_stats': {},
            'threshold_adjustments': {},
            'last_update': datetime.now().isoformat()
        }
    
    def save_learning_data(self):
        """Sauvegarde les données d'apprentissage"""
        try:
            self.learning_data['last_update'] = datetime.now().isoformat()
            with open(self.learning_file, 'w', encoding='utf-8') as f:
                json.dump(self.learning_data, f, indent=2, ensure_ascii=False)
            log_debug("Données d'apprentissage sauvegardées")
        except Exception as e:
            log_error(f"Erreur sauvegarde données apprentissage: {e}")
    
    def record_validation(self, alert_name, detection_params, is_valid, screenshot_region=None):
        """
        Enregistre une validation utilisateur
        
        Args:
            alert_name: Nom de l'alerte
            detection_params: Paramètres de la détection (confidence, scale, ratio, etc.)
            is_valid: True si l'utilisateur valide, False si faux positif
            screenshot_region: Région de l'image détectée
        """
        validation = {
            'timestamp': datetime.now().isoformat(),
            'alert_name': alert_name,
            'is_valid': is_valid,
            'confidence': detection_params.get('confidence', 0),
            'scale': detection_params.get('scale', 1.0),
            'aspect_ratio': detection_params.get('aspect_ratio', 1.0),
            'threshold': detection_params.get('threshold', 0.7)
        }
        
        # Ajouter à l'historique
        self.learning_data['validations'].append(validation)
        
        # Mettre à jour les statistiques par alerte
        if alert_name not in self.learning_data['alert_stats']:
            self.learning_data['alert_stats'][alert_name] = {
                'true_positives': 0,
                'false_positives': 0,
                'avg_confidence_valid': 0,
                'avg_confidence_invalid': 0,
                'min_valid_confidence': 1.0,
                'max_invalid_confidence': 0.0
            }
        
        stats = self.learning_data['alert_stats'][alert_name]
        
        if is_valid:
            stats['true_positives'] += 1
            # Mise à jour de la moyenne de confiance pour les vrais positifs
            n = stats['true_positives']
            stats['avg_confidence_valid'] = ((n-1) * stats['avg_confidence_valid'] + validation['confidence']) / n
            stats['min_valid_confidence'] = min(stats['min_valid_confidence'], validation['confidence'])
        else:
            stats['false_positives'] += 1
            # Mise à jour de la moyenne de confiance pour les faux positifs
            n = stats['false_positives']
            stats['avg_confidence_invalid'] = ((n-1) * stats['avg_confidence_invalid'] + validation['confidence']) / n
            stats['max_invalid_confidence'] = max(stats['max_invalid_confidence'], validation['confidence'])
            
            # Sauvegarder l'image du faux positif pour analyse
            if screenshot_region is not None:
                self.save_false_positive_sample(alert_name, screenshot_region, detection_params)
        
        # Calculer un nouvel ajustement de seuil suggéré
        self.calculate_threshold_adjustment(alert_name)
        
        # Sauvegarder
        self.save_learning_data()
        
        log_info(f"Validation enregistrée pour {alert_name}: {'✓ Valide' if is_valid else '✗ Faux positif'}")
        
        # Garder seulement les 1000 dernières validations
        if len(self.learning_data['validations']) > 1000:
            self.learning_data['validations'] = self.learning_data['validations'][-1000:]
    
    def calculate_threshold_adjustment(self, alert_name):
        """Calcule un ajustement de seuil basé sur les validations"""
        stats = self.learning_data['alert_stats'].get(alert_name)
        if not stats:
            return
        
        tp = stats['true_positives']
        fp = stats['false_positives']
        
        if tp + fp < 5:  # Pas assez de données
            return
        
        # Si trop de faux positifs, suggérer un seuil plus élevé
        false_positive_rate = fp / (tp + fp)
        
        if false_positive_rate > 0.3:  # Plus de 30% de faux positifs
            # Le nouveau seuil devrait être entre la confiance moyenne des vrais positifs
            # et la confiance maximale des faux positifs
            if stats['max_invalid_confidence'] < stats['min_valid_confidence']:
                # Cas idéal : on peut séparer parfaitement
                new_threshold = (stats['max_invalid_confidence'] + stats['min_valid_confidence']) / 2
            else:
                # Cas difficile : chevauchement
                # Prendre un seuil qui favorise la précision
                new_threshold = stats['avg_confidence_valid'] * 0.95
            
            self.learning_data['threshold_adjustments'][alert_name] = {
                'original_threshold': 0.7,  # À adapter selon votre config
                'suggested_threshold': min(0.95, max(0.5, new_threshold)),
                'confidence': 1.0 - false_positive_rate,
                'samples': tp + fp,
                'reason': f"FP rate: {false_positive_rate:.1%}"
            }
            
            log_info(f"Nouveau seuil suggéré pour {alert_name}: {new_threshold:.3f} "
                    f"(FP: {fp}, TP: {tp})")
    
    def save_false_positive_sample(self, alert_name, screenshot_region, detection_params):
        """Sauvegarde un échantillon de faux positif pour analyse"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            confidence = detection_params.get('confidence', 0)
            
            filename = f"{alert_name}_{timestamp}_conf{confidence:.2f}.png"
            filepath = os.path.join(self.false_positives_dir, filename)
            
            cv2.imwrite(filepath, screenshot_region)
            
            # Sauvegarder aussi les métadonnées
            metadata_file = filepath.replace('.png', '_metadata.json')
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(detection_params, f, indent=2)
            
            log_debug(f"Faux positif sauvegardé: {filename}")
            
            # Analyser le pattern du faux positif
            self.analyze_false_positive_pattern(alert_name, screenshot_region)
            
        except Exception as e:
            log_error(f"Erreur sauvegarde faux positif: {e}")
    
    def load_false_positive_patterns(self):
        """Charge les patterns de faux positifs pour filtrage"""
        try:
            pattern_file = os.path.join(self.data_dir, "false_positive_patterns.json")
            if os.path.exists(pattern_file):
                with open(pattern_file, 'r', encoding='utf-8') as f:
                    self.false_positive_patterns = json.load(f)
        except Exception as e:
            log_error(f"Erreur chargement patterns FP: {e}")
    
    def analyze_false_positive_pattern(self, alert_name, screenshot_region):
        """Analyse un faux positif pour identifier des patterns communs"""
        try:
            # Calculer des caractéristiques de l'image
            gray = cv2.cvtColor(screenshot_region, cv2.COLOR_BGR2GRAY)
            
            # Histogramme de luminosité
            hist = cv2.calcHist([gray], [0], None, [16], [0, 256]).flatten()
            hist = hist / hist.sum()  # Normaliser
            
            # Caractéristiques de texture
            mean_brightness = np.mean(gray)
            std_brightness = np.std(gray)
            
            # Détection de contours
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            pattern = {
                'histogram': hist.tolist(),
                'mean_brightness': float(mean_brightness),
                'std_brightness': float(std_brightness),
                'edge_density': float(edge_density)
            }
            
            if alert_name not in self.false_positive_patterns:
                self.false_positive_patterns[alert_name] = []
            
            self.false_positive_patterns[alert_name].append(pattern)
            
            # Garder seulement les 20 derniers patterns
            if len(self.false_positive_patterns[alert_name]) > 20:
                self.false_positive_patterns[alert_name] = self.false_positive_patterns[alert_name][-20:]
            
            # Sauvegarder
            pattern_file = os.path.join(self.data_dir, "false_positive_patterns.json")
            with open(pattern_file, 'w', encoding='utf-8') as f:
                json.dump(self.false_positive_patterns, f, indent=2)
            
        except Exception as e:
            log_error(f"Erreur analyse pattern FP: {e}")
    
    def get_adjusted_threshold(self, alert_name, default_threshold):
        """
        Retourne le seuil ajusté basé sur l'apprentissage
        """
        adjustment = self.learning_data['threshold_adjustments'].get(alert_name)
        
        if adjustment and adjustment['samples'] >= 10:  # Au moins 10 échantillons
            suggested = adjustment['suggested_threshold']
            confidence = adjustment['confidence']
            
            # Appliquer progressivement l'ajustement selon la confiance
            adjusted = default_threshold * (1 - confidence * 0.3) + suggested * (confidence * 0.3)
            
            log_debug(f"Seuil ajusté pour {alert_name}: {default_threshold:.3f} -> {adjusted:.3f}")
            return adjusted
        
        return default_threshold
    
    def should_filter_detection(self, alert_name, screenshot_region, detection_params):
        """
        Vérifie si une détection devrait être filtrée basée sur les patterns de faux positifs
        """
        if alert_name not in self.false_positive_patterns:
            return False
        
        try:
            # Calculer les caractéristiques de la région détectée
            gray = cv2.cvtColor(screenshot_region, cv2.COLOR_BGR2GRAY)
            
            hist = cv2.calcHist([gray], [0], None, [16], [0, 256]).flatten()
            hist = hist / hist.sum()
            
            mean_brightness = np.mean(gray)
            std_brightness = np.std(gray)
            
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            # Comparer avec les patterns de faux positifs connus
            for fp_pattern in self.false_positive_patterns[alert_name]:
                # Similarité d'histogramme
                hist_similarity = cv2.compareHist(
                    np.array(fp_pattern['histogram'], dtype=np.float32),
                    hist.astype(np.float32),
                    cv2.HISTCMP_CORREL
                )
                
                # Similarité de caractéristiques
                brightness_diff = abs(mean_brightness - fp_pattern['mean_brightness']) / 255
                std_diff = abs(std_brightness - fp_pattern['std_brightness']) / 255
                edge_diff = abs(edge_density - fp_pattern['edge_density'])
                
                # Si très similaire à un faux positif connu
                if (hist_similarity > 0.9 and 
                    brightness_diff < 0.1 and 
                    std_diff < 0.1 and 
                    edge_diff < 0.1):
                    
                    log_debug(f"Détection filtrée (similaire à FP connu): {alert_name}")
                    return True
            
        except Exception as e:
            log_error(f"Erreur filtrage détection: {e}")
        
        return False
    
    def get_statistics(self):
        """Retourne les statistiques d'apprentissage"""
        total_validations = len(self.learning_data['validations'])
        
        stats = {
            'total_validations': total_validations,
            'alerts': {}
        }
        
        for alert_name, alert_stats in self.learning_data['alert_stats'].items():
            tp = alert_stats['true_positives']
            fp = alert_stats['false_positives']
            total = tp + fp
            
            stats['alerts'][alert_name] = {
                'true_positives': tp,
                'false_positives': fp,
                'total': total,
                'precision': (tp / total * 100) if total > 0 else 0,
                'avg_confidence_valid': alert_stats['avg_confidence_valid'],
                'avg_confidence_invalid': alert_stats['avg_confidence_invalid'],
                'threshold_adjustment': self.learning_data['threshold_adjustments'].get(alert_name)
            }
        
        return stats

# Instance globale
learning_system = DetectionLearningSystem()

def validate_detection(alert_name, detection_params, is_valid, screenshot_region=None):
    """Interface simple pour valider une détection"""
    learning_system.record_validation(alert_name, detection_params, is_valid, screenshot_region)

def get_adjusted_threshold(alert_name, default_threshold):
    """Interface pour obtenir le seuil ajusté"""
    return learning_system.get_adjusted_threshold(alert_name, default_threshold)

def should_filter_detection(alert_name, screenshot_region, detection_params):
    """Interface pour vérifier si une détection doit être filtrée"""
    return learning_system.should_filter_detection(alert_name, screenshot_region, detection_params)

def get_learning_statistics():
    """Interface pour obtenir les statistiques"""
    return learning_system.get_statistics()