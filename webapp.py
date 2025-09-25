# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request, send_file, make_response
import json
import time
import threading
from datetime import datetime, timedelta
import os
import cv2
import tempfile
import numpy as np
from utils import log_error, log_debug, log_info, log_warning
from config_manager import config_manager
from simple_detection import detector
from training_tool import training_tool

class WebAppManager:
    """Gestionnaire de l'interface web avec historique des alertes"""
    
    def __init__(self, port=5000, debug=False):
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.port = port
        self.debug = debug
        self.windows_state = {}
        self.global_stats = {}
        self.alerts_history = []
        self.alerts_with_screenshots = []
        self.server_thread = None
        self.running = False
        self.latest_screenshots = {}
        self.latest_detections = {}
        self.system_paused = False
        self.pause_callbacks = []
        
        self._ensure_directories()
        self.setup_routes()
        
    def _ensure_directories(self):
        """Crée les dossiers nécessaires"""
        required_dirs = [
            'static',
            'static/screenshots',
            'static/alerts',
            'templates'
        ]
        
        for directory in required_dirs:
            try:
                os.makedirs(directory, exist_ok=True)
                log_debug(f"Dossier créé/vérifié: {directory}")
            except Exception as e:
                log_error(f"Erreur création dossier {directory}: {e}")
    
    def register_pause_callback(self, callback):
        """Enregistre un callback pour les changements d'état de pause"""
        self.pause_callbacks.append(callback)
    
    def _notify_pause_change(self, paused):
        """Notifie tous les callbacks du changement d'état"""
        for callback in self.pause_callbacks:
            try:
                callback(paused)
            except Exception as e:
                log_error(f"Erreur callback pause: {e}")
    
    def update_screenshot_with_detection(self, source_name, screenshot, detection_area=None, 
                                        alert_name=None, confidence=0.0):
        """Met à jour le screenshot avec la zone de détection marquée"""
        try:
            if screenshot is None:
                return None
            
            timestamp = datetime.now()
            clean_source = source_name.replace(' ', '_').replace('!', '')
            
            # Créer une copie pour marquer la détection
            marked_screenshot = screenshot.copy()
            
            # Si une zone de détection existe, la dessiner
            if detection_area and 'x' in detection_area:
                x = detection_area['x']
                y = detection_area['y']
                w = detection_area['width']
                h = detection_area['height']
                
                # Dessiner le rectangle de détection
                # Couleur selon la confiance
                if confidence >= 0.8:
                    color = (0, 255, 0)  # Vert
                elif confidence >= 0.5:
                    color = (0, 165, 255)  # Orange
                else:
                    color = (0, 0, 255)  # Rouge
                
                # Rectangle principal
                cv2.rectangle(marked_screenshot, (x, y), (x + w, y + h), color, 3)
                
                # Ajouter le texte avec les infos
                if alert_name:
                    text = f"{alert_name}: {confidence:.1%}"
                    text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                    
                    # Fond pour le texte
                    cv2.rectangle(marked_screenshot, 
                                (x, y - 35), 
                                (x + text_size[0] + 10, y - 5), 
                                color, -1)
                    
                    # Texte
                    cv2.putText(marked_screenshot, text, (x + 5, y - 15),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    # Infos supplémentaires si disponibles
                    if 'scale' in detection_area:
                        info_text = f"Scale: {detection_area['scale']:.2f}"
                        cv2.putText(marked_screenshot, info_text, (x + 5, y + h + 20),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            
            # Sauvegarder deux versions : avec et sans marquage
            filename_marked = f"{clean_source}_latest_marked.png"
            filename_clean = f"{clean_source}_latest_clean.png"
            
            filepath_marked = f"static/screenshots/{filename_marked}"
            filepath_clean = f"static/screenshots/{filename_clean}"
            
            cv2.imwrite(filepath_marked, marked_screenshot)
            cv2.imwrite(filepath_clean, screenshot)
            
            # Mettre à jour avec les deux versions
            self.latest_screenshots[source_name] = {
                'timestamp': timestamp.isoformat(),
                'screenshot_path_marked': filepath_marked,
                'screenshot_path_clean': filepath_clean,
                'has_detection': detection_area is not None,
                'detection_area': detection_area,
                'alert_name': alert_name,
                'confidence': confidence
            }

            if alert_name and confidence > 0:
                # Ajouter automatiquement à l'historique quand une détection est marquée
                self.add_alert(
                    source_name=source_name,
                    alert_name=alert_name,
                    confidence=confidence,
                    screenshot=screenshot,
                    detection_area=detection_area
                )
                log_info(f"Alerte ajoutée à l'historique depuis update_screenshot_with_detection")
                
            log_debug(f"Screenshot mis à jour pour {source_name} (détection: {detection_area is not None})")
            
            return filename_marked
            
        except Exception as e:
            log_error(f"Erreur mise à jour screenshot avec détection: {e}")
            return None
        
    def setup_routes(self):
        """Configuration des routes Flask"""
        
        @self.app.route('/')
        def index():
            return render_template('index.html')
        
        @self.app.route('/api/status')
        def api_status():
            """API pour récupérer le statut en temps réel"""
            return jsonify({
                'timestamp': datetime.now().isoformat(),
                'windows_state': self.format_windows_state(),
                'global_stats': self.format_global_stats(),
                'alerts_history': self.alerts_history[-20:],
                'uptime': self.calculate_uptime(),
                'system_paused': self.system_paused
            })
        
        @self.app.route('/api/screenshot/<source_name>')
        def api_screenshot(source_name):
            """API pour récupérer le screenshot d'une source"""
            marked = request.args.get('marked', 'true').lower() == 'true'
            
            if source_name in self.latest_screenshots:
                screenshot_data = self.latest_screenshots[source_name]
                
                # Choisir la version marquée ou clean selon le paramètre
                if marked and screenshot_data.get('has_detection'):
                    screenshot_path = screenshot_data.get('screenshot_path_marked')
                else:
                    screenshot_path = screenshot_data.get('screenshot_path_clean')
                
                if screenshot_path and os.path.exists(screenshot_path):
                    return send_file(screenshot_path, mimetype='image/png')
            
            # Image par défaut si pas de screenshot
            return jsonify({'error': 'Screenshot non trouvé'}), 404
        
        @self.app.route('/api/validate_detection', methods=['POST'])
        def api_validate_detection():
            """API pour valider ou rejeter une détection"""
            try:
                data = request.json
                alert_name = data.get('alert_name')
                source_name = data.get('source_name')
                is_valid = data.get('is_valid', True)
                detection_params = data.get('detection_params', {})
                
                # Récupérer la région du screenshot si disponible
                screenshot_region = None
                if source_name in self.latest_screenshots:
                    screenshot_data = self.latest_screenshots[source_name]
                    if screenshot_data.get('has_detection'):
                        # Charger l'image et extraire la région
                        clean_path = screenshot_data.get('screenshot_path_clean')
                        if clean_path and os.path.exists(clean_path):
                            img = cv2.imread(clean_path)
                            area = screenshot_data.get('detection_area')
                            if img is not None and area and 'x' in area:
                                x = area['x']
                                y = area['y']
                                w = area['width']
                                h = area['height']
                                # Vérifier les limites
                                if (x >= 0 and y >= 0 and 
                                    x + w <= img.shape[1] and 
                                    y + h <= img.shape[0]):
                                    screenshot_region = img[y:y+h, x:x+w]
                
                # Enregistrer la validation
                validate_detection(alert_name, detection_params, is_valid, screenshot_region)
                
                # Retourner les nouvelles statistiques
                stats = get_learning_statistics()
                
                return jsonify({
                    'success': True,
                    'message': f"Détection {'validée' if is_valid else 'marquée comme faux positif'}",
                    'statistics': stats
                })
                
            except Exception as e:
                log_error(f"Erreur validation détection: {e}")
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/config/import_template', methods=['POST'])
        def api_import_template():
            """Importe un template depuis un fichier"""
            try:
                alert_name = request.form.get('alert_name')
                file = request.files.get('file')
                
                if not alert_name or not file:
                    return jsonify({'success': False, 'error': 'Paramètres manquants'})
                
                log_info(f"Import template pour {alert_name}: {file.filename}")
                
               
                # Créer un fichier temporaire avec l'extension correcte
                suffix = os.path.splitext(file.filename)[1] or '.png'
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                    file.save(tmp_file.name)
                    tmp_path = tmp_file.name
                
                try:
                    # Charger l'image
                    image = cv2.imread(tmp_path)
                    
                    if image is not None:
                        # Ajouter comme template
                        template_id = config_manager.add_template(
                            alert_name,
                            image,
                            source_name="import",
                            threshold=0.7
                        )
                        
                        log_info(f"Template créé avec ID: {template_id}")
                        
                        return jsonify({
                            'success': True,
                            'template_id': template_id,
                            'message': f'Template {file.filename} importé'
                        })
                    else:
                        return jsonify({
                            'success': False, 
                            'error': 'Image invalide ou format non supporté'
                        })
                finally:
                    # Nettoyer le fichier temporaire
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                        
            except Exception as e:
                log_error(f"Erreur import template: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/scan_windows', methods=['POST'])
        def api_scan_windows():
            """Scanne les fenêtres disponibles"""
            try:
                # Retourner les sources actuellement configurées
                sources = list(self.windows_state.keys())
                return jsonify({
                    'success': True,
                    'windows': sources
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/learning_statistics')
        def api_learning_statistics():
            """API pour récupérer les statistiques d'apprentissage"""
            try:
                stats = get_learning_statistics()
                return jsonify(stats)
            except Exception as e:
                return jsonify({'error': str(e)})
        
        @self.app.route('/api/toggle_pause', methods=['POST'])
        def api_toggle_pause():
            """API pour basculer pause/reprise"""
            try:
                self.system_paused = not self.system_paused
                self._notify_pause_change(self.system_paused)
                
                status = "pause" if self.system_paused else "repris"
                log_info(f"Système {status} via interface web")
                
                return jsonify({
                    'success': True, 
                    'paused': self.system_paused,
                    'message': f'Système {status}'
                })
            except Exception as e:
                log_error(f"Erreur bascule pause: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/reset_stats', methods=['POST'])
        def api_reset_stats():
            """API pour réinitialiser les statistiques"""
            try:
                # Reset des stats par fenêtre
                for source_name in self.windows_state:
                    state = self.windows_state[source_name]
                    state.update({
                        'total_captures': 0,
                        'successful_captures': 0,
                        'total_detections': 0,
                        'notifications_sent': 0,
                        'error_count': 0,
                        'consecutive_failures': 0
                    })
                
                # Reset historiques
                self.alerts_history = []
                self.alerts_with_screenshots = []
                self.latest_detections = {}
                
                log_info("Statistiques réinitialisées via interface web")
                return jsonify({'success': True, 'message': 'Statistiques réinitialisées'})
            except Exception as e:
                log_error(f"Erreur réinitialisation stats: {e}")
                return jsonify({'success': False, 'error': str(e)})
        
        @self.app.route('/api/alerts/history')
        def api_alerts_history():
            """API pour l'historique des alertes"""
            return jsonify({
                'alerts': self.alerts_history[-50:],
                'alerts_with_screenshots': self.alerts_with_screenshots[-10:],
                'latest_detections': self.latest_detections
            })

        @self.app.route('/api/training/annotate', methods=['POST'])
        def api_annotate_detection():
            """API pour annoter manuellement une zone de détection"""
            try:
                from training_tool import training_tool
                
                data = request.json
                source_name = data.get('source_name')
                alert_name = data.get('alert_name')
                bbox = data.get('bbox')  # {x, y, width, height}
                
                # Récupérer le screenshot actuel
                if source_name in self.latest_screenshots:
                    screenshot_data = self.latest_screenshots[source_name]
                    screenshot_path = screenshot_data.get('screenshot_path_clean')
                    
                    if screenshot_path and os.path.exists(screenshot_path):
                        screenshot = cv2.imread(screenshot_path)
                        
                        if screenshot is not None:
                            # Ajouter l'annotation
                            annotation_id = training_tool.add_annotation(
                                source_name, 
                                alert_name,
                                screenshot,
                                (bbox['x'], bbox['y'], bbox['width'], bbox['height']),
                                confidence=1.0
                            )
                            
                            if annotation_id:
                                # NOUVEAU : Déclencher immédiatement une vérification
                                # Importer le module de détection
                                try:
                                    from detection import check_alert_with_trained_templates
                                    
                                    # Vérifier immédiatement avec le nouveau template
                                    result = check_alert_with_trained_templates(screenshot, alert_name, threshold=0.7)
                                    
                                    if result and result.get('found'):
                                        # Simuler une alerte
                                        self.add_alert(source_name, alert_name, result['confidence'], screenshot, {
                                            'x': result['x'],
                                            'y': result['y'],
                                            'width': result['width'],
                                            'height': result['height']
                                        })
                                        
                                        log_info(f"Alerte déclenchée après annotation: {alert_name} sur {source_name}")
                                        
                                        # Mettre à jour l'état de la fenêtre
                                        if source_name in self.windows_state:
                                            self.windows_state[source_name]['last_alert_name'] = alert_name
                                            self.windows_state[source_name]['last_alert_state'] = True
                                            self.windows_state[source_name]['last_confidence'] = result['confidence']
                                            self.windows_state[source_name]['total_detections'] += 1
                                
                                except Exception as e:
                                    log_error(f"Erreur lors du test immédiat: {e}")
                                
                                # Récupérer les statistiques
                                stats = training_tool.get_training_statistics()
                                
                                return jsonify({
                                    'success': True,
                                    'annotation_id': annotation_id,
                                    'message': f"Zone annotée et testée pour {alert_name}",
                                    'statistics': stats,
                                    'immediate_detection': result is not None and result.get('found', False)
                                })
                
                return jsonify({
                    'success': False,
                    'error': 'Screenshot non disponible'
                })
                
            except Exception as e:
                log_error(f"Erreur annotation: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/training/annotations')
        def api_get_annotations():
            """Récupère toutes les annotations"""
            try:
                from training_tool import training_tool
                
                # Filtrer et formater les annotations pour l'affichage
                annotations = []
                for ann in training_tool.annotations['annotations']:
                    annotations.append({
                        'id': ann['id'],
                        'timestamp': ann['timestamp'],
                        'source_name': ann['source_name'],
                        'alert_name': ann['alert_name'],
                        'bbox': ann['bbox'],
                        'confidence': ann.get('confidence', 1.0),
                        'validated': ann.get('validated', True),
                        'is_manual': ann.get('is_manual', False),
                        'template_exists': os.path.exists(ann.get('template_path', ''))
                    })
                
                return jsonify({
                    'annotations': annotations,
                    'total': len(annotations)
                })
            except Exception as e:
                log_error(f"Erreur récupération annotations: {e}")
                return jsonify({'error': str(e)})

        @self.app.route('/api/training/annotation/<annotation_id>', methods=['DELETE'])
        def api_delete_annotation(annotation_id):
            """Supprime une annotation"""
            try:
                from training_tool import training_tool
                
                # Trouver et supprimer l'annotation
                annotations = training_tool.annotations['annotations']
                annotation_to_delete = None
                
                for i, ann in enumerate(annotations):
                    if ann['id'] == annotation_id:
                        annotation_to_delete = ann
                        annotations.pop(i)
                        break
                
                if annotation_to_delete:
                    # Supprimer le fichier template associé
                    template_path = annotation_to_delete.get('template_path')
                    if template_path and os.path.exists(template_path):
                        try:
                            os.remove(template_path)
                            log_info(f"Template supprimé: {template_path}")
                        except Exception as e:
                            log_error(f"Erreur suppression template: {e}")
                    
                    # Mettre à jour les templates par alerte
                    alert_name = annotation_to_delete['alert_name']
                    if alert_name in training_tool.annotations['templates']:
                        training_tool.annotations['templates'][alert_name] = [
                            t for t in training_tool.annotations['templates'][alert_name]
                            if t.get('path') != template_path
                        ]
                    
                    # Sauvegarder
                    training_tool.save_annotations()
                    
                    # Retourner les nouvelles stats
                    stats = training_tool.get_training_statistics()
                    
                    return jsonify({
                        'success': True,
                        'message': f"Annotation {annotation_id} supprimée",
                        'statistics': stats
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Annotation non trouvée'
                    })
                    
            except Exception as e:
                log_error(f"Erreur suppression annotation: {e}")
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/training/clear/<alert_name>', methods=['POST'])
        def api_clear_alert_annotations(alert_name):
            """Supprime toutes les annotations d'une alerte"""
            try:
                from training_tool import training_tool
                
                # Filtrer les annotations
                annotations_to_keep = []
                deleted_count = 0
                
                for ann in training_tool.annotations['annotations']:
                    if ann['alert_name'] != alert_name:
                        annotations_to_keep.append(ann)
                    else:
                        # Supprimer le template
                        template_path = ann.get('template_path')
                        if template_path and os.path.exists(template_path):
                            try:
                                os.remove(template_path)
                            except:
                                pass
                        deleted_count += 1
                
                training_tool.annotations['annotations'] = annotations_to_keep
                
                # Vider les templates de cette alerte
                if alert_name in training_tool.annotations['templates']:
                    del training_tool.annotations['templates'][alert_name]
                
                # Sauvegarder
                training_tool.save_annotations()
                
                return jsonify({
                    'success': True,
                    'deleted_count': deleted_count,
                    'message': f"{deleted_count} annotations supprimées pour {alert_name}"
                })
                
            except Exception as e:
                log_error(f"Erreur suppression annotations alerte: {e}")
                return jsonify({'success': False, 'error': str(e)})

        @self.app.route('/api/training/statistics')
        def api_training_statistics():
            """Retourne les statistiques d'entraînement"""
            try:
                from training_tool import training_tool
                stats = training_tool.get_training_statistics()
                return jsonify(stats)
            except Exception as e:
                return jsonify({'error': str(e)})

        @self.app.route('/api/training/templates/<alert_name>')
        def api_get_alert_templates(alert_name):
            """Retourne les templates entrainés pour une alerte"""
            try:
                from training_tool import training_tool
                templates = training_tool.get_alert_templates(alert_name)
                return jsonify({
                    'alert_name': alert_name,
                    'templates': templates,
                    'count': len(templates)
                })
            except Exception as e:
                return jsonify({'error': str(e)})

        # Routes de configuration
        @self.app.route('/api/config')
        def api_get_config():
            """Récupère la configuration complète"""
            return jsonify(config_manager.config)

        @self.app.route('/api/config/alert', methods=['POST'])
        def api_add_alert():
            """Ajoute une nouvelle alerte"""
            data = request.json
            alert_name = data.get('name')
            threshold = data.get('threshold', 0.7)
            
            if config_manager.add_alert(alert_name, threshold):
                return jsonify({'success': True, 'message': f'Alerte {alert_name} ajoutée'})
            return jsonify({'success': False, 'error': 'Alerte déjà existante'})

        @self.app.route('/api/config/alert/<alert_name>', methods=['DELETE'])
        def api_delete_alert(alert_name):
            """Supprime une alerte"""
            if alert_name in config_manager.config["alerts"]:
                del config_manager.config["alerts"][alert_name]
                config_manager.save_config()
                return jsonify({'success': True})
            return jsonify({'success': False, 'error': 'Alerte non trouvée'})

        @self.app.route('/api/config/alert/<alert_name>/toggle', methods=['POST'])
        def api_toggle_alert(alert_name):
            """Active/désactive une alerte"""
            if alert_name in config_manager.config["alerts"]:
                config_manager.config["alerts"][alert_name]["enabled"] = \
                    not config_manager.config["alerts"][alert_name]["enabled"]
                config_manager.save_config()
                return jsonify({
                    'success': True,
                    'enabled': config_manager.config["alerts"][alert_name]["enabled"]
                })
            return jsonify({'success': False})

        @self.app.route('/api/config/template', methods=['POST'])
        def api_add_template_from_capture():
            """Ajoute un template depuis la dernière capture"""
            data = request.json
            source_name = data.get('source_name')
            alert_name = data.get('alert_name')
            bbox = data.get('bbox')  # {x, y, width, height}
            threshold = data.get('threshold')
            
            if not all([source_name, alert_name, bbox]):
                return jsonify({'success': False, 'error': 'Paramètres manquants'})
            
            # Récupérer la dernière capture
            if source_name in self.latest_screenshots:
                screenshot_data = self.latest_screenshots[source_name]
                screenshot_path = screenshot_data.get('screenshot_path_clean')
                
                if screenshot_path and os.path.exists(screenshot_path):
                    import cv2
                    screenshot = cv2.imread(screenshot_path)
                    
                    if screenshot is not None and bbox:
                        # Convertir les valeurs en entiers (IMPORTANT!)
                        x = int(bbox['x'])
                        y = int(bbox['y'])
                        w = int(bbox['width'])
                        h = int(bbox['height'])
                        
                        # Vérifier les limites
                        height, width = screenshot.shape[:2]
                        
                        # S'assurer que les coordonnées sont dans les limites
                        x = max(0, min(x, width - 1))
                        y = max(0, min(y, height - 1))
                        w = min(w, width - x)
                        h = min(h, height - y)
                        
                        # Vérifier la taille minimale
                        if w < 20 or h < 20:
                            return jsonify({
                                'success': False, 
                                'error': f'Zone trop petite: {w}x{h}px (minimum 20x20)'
                            })
                        
                        # Extraire la région
                        region = screenshot[y:y+h, x:x+w]
                        
                        # Ajouter le template
                        template_id = config_manager.add_template(
                            alert_name, 
                            region, 
                            source_name, 
                            threshold
                        )
                        
                        # Tester immédiatement
                        from simple_detection import detector
                        result = detector.check_alert(screenshot, alert_name, source_name)
                        
                        log_info(f"Template ajouté: {template_id} pour {alert_name}")
                        
                        return jsonify({
                            'success': True,
                            'template_id': template_id,
                            'immediate_detection': result is not None and result.get('found', False)
                        })
                    else:
                        return jsonify({'success': False, 'error': 'Screenshot invalide'})
            
            return jsonify({'success': False, 'error': 'Capture non disponible'})

        @self.app.route('/api/config/template/<alert_name>/<template_id>', methods=['DELETE'])
        def api_delete_template(alert_name, template_id):
            """Supprime un template"""
            if config_manager.remove_template(alert_name, template_id):
                return jsonify({'success': True})
            return jsonify({'success': False})

        @self.app.route('/api/config/template/<alert_name>/<template_id>/threshold', methods=['POST'])
        def api_update_template_threshold(alert_name, template_id):
            """Met à jour le seuil d'un template avec prédiction"""
            data = request.json
            new_threshold = data.get('threshold')
            test_with_last = data.get('test_with_last', False)
            
            if config_manager.update_template_threshold(alert_name, template_id, new_threshold):
                response = {'success': True}
                
                # Si demandé, tester avec la dernière capture
                if test_with_last:
                    source_name = data.get('source_name')
                    if source_name and source_name in self.latest_screenshots:
                        screenshot_path = self.latest_screenshots[source_name].get('screenshot_path_clean')
                        if screenshot_path and os.path.exists(screenshot_path):
                            import cv2
                            screenshot = cv2.imread(screenshot_path)
                            
                            from simple_detection import detector
                            prediction = detector.test_threshold_change(
                                screenshot, alert_name, template_id, new_threshold
                            )
                            response['prediction'] = prediction
                
                return jsonify(response)
            
            return jsonify({'success': False})

        @self.app.route('/api/detection/false_positive', methods=['POST'])
        def api_mark_false_positive():
            """Marque une détection comme faux positif"""
            data = request.json
            source_name = data.get('source_name')
            alert_name = data.get('alert_name')
            
            from simple_detection import detector
            result = detector.mark_false_positive(source_name, alert_name)
            
            if result:
                # Obtenir une recommandation de seuil
                recommendation = config_manager.calculate_threshold_recommendation(
                    {"stats": result["stats"]},
                    result["confidence"]
                )
                
                return jsonify({
                    'success': True,
                    'template_id': result['template_id'],
                    'stats': result['stats'],
                    'recommendation': recommendation
                })
            
            return jsonify({'success': False, 'error': 'Détection non trouvée'})
    
    def format_windows_state(self):
        """Formate l'état des fenêtres pour l'API"""
        formatted = {}
        
        for source_name, state in self.windows_state.items():
            total_captures = state.get('total_captures', 1)  # Éviter division par 0
            successful_captures = state.get('successful_captures', 0)
            
            # Récupérer les infos de screenshot et détection
            screenshot_info = self.latest_screenshots.get(source_name, {})
            
            formatted[source_name] = {
                'source_name': source_name,
                'status': self.get_status_text(state),
                'status_color': self.get_status_color(state),
                'last_capture_time': state.get('last_capture_time'),
                'last_capture_relative': self.get_relative_time(state.get('last_capture_time')),
                'last_alert_name': state.get('last_alert_name', 'Aucune'),
                'last_alert_state': state.get('last_alert_state', False),
                'last_confidence': state.get('last_confidence', 0.0),
                'confidence_percent': f"{state.get('last_confidence', 0.0):.1%}",
                'total_detections': state.get('total_detections', 0),
                'notifications_sent': state.get('notifications_sent', 0),
                'success_rate': (successful_captures / total_captures) * 100,
                'error_count': state.get('error_count', 0),
                'last_error': state.get('last_error'),
                'performance_ms': state.get('performance_ms', 0),
                'consecutive_failures': state.get('consecutive_failures', 0),
                'has_screenshot': source_name in self.latest_screenshots,
                'has_detection': screenshot_info.get('has_detection', False),
                'detection_area': screenshot_info.get('detection_area'),
                'screenshot_url': f"/api/screenshot/{source_name}",
                'detection_confidence': screenshot_info.get('confidence', 0.0)
            }
            
        return formatted
    
    def get_status_text(self, state):
        """Détermine le texte de statut"""
        if self.system_paused:
            return 'PAUSE'
        
        # Si une capture récente existe (moins de 10 secondes), c'est OK
        last_capture = state.get('last_capture_time')
        if last_capture:
            try:
                from datetime import datetime
                capture_time = datetime.strptime(last_capture, "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - capture_time).total_seconds() < 10:
                    return 'OK'
            except:
                pass
        
        # Sinon, vérifier les erreurs
        consecutive_failures = state.get('consecutive_failures', 0)
        if consecutive_failures >= 5:
            return 'ERREUR'
        elif consecutive_failures > 0:
            return 'Instable'
        
        return 'OK'
    
    def get_status_color(self, state):
        """Détermine la couleur de statut"""
        consecutive_failures = state.get('consecutive_failures', 0)
        alert_state = state.get('last_alert_state', False)
        
        if self.system_paused:
            return 'secondary'
        elif consecutive_failures >= 5:
            return 'danger'
        elif alert_state:
            return 'warning'
        elif consecutive_failures > 0:
            return 'info'
        else:
            return 'success'
    
    def get_relative_time(self, timestamp_str):
        """Convertit un timestamp en temps relatif"""
        if not timestamp_str:
            return 'Jamais'
            
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            diff = now - timestamp
            
            if diff.total_seconds() < 60:
                return f"{int(diff.total_seconds())}s"
            elif diff.total_seconds() < 3600:
                return f"{int(diff.total_seconds() // 60)}min"
            else:
                return f"{int(diff.total_seconds() // 3600)}h"
        except:
            return timestamp_str
    
    def format_global_stats(self):
        """Formate les statistiques globales"""
        return {
            'start_time': self.global_stats.get('start_time'),
            'total_cycles': self.global_stats.get('total_cycles', 0),
            'obs_reconnections': self.global_stats.get('obs_reconnections', 0),
            'uptime_seconds': time.time() - self.global_stats.get('start_time', time.time()),
            'pause_count': self.global_stats.get('pause_count', 0),
            'total_paused_time': self.global_stats.get('total_paused_time', 0)
        }
    
    def calculate_uptime(self):
        """Calcule le temps de fonctionnement"""
        start_time = self.global_stats.get('start_time', time.time())
        uptime_seconds = time.time() - start_time
        
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def update_data(self, windows_state, global_stats):
        """Met à jour les données depuis le thread principal"""
        self.windows_state = windows_state
        self.global_stats = global_stats
    
    def add_alert(self, source_name, alert_name, confidence, screenshot=None, detection_area=None):
        """Ajoute une alerte à l'historique avec screenshot"""

        import traceback
        
        # DEBUG : voir d'où vient l'appel
        print(f"\n=== ADD_ALERT APPELÉ ===")
        print(f"Source: {source_name}")
        print(f"Alerte: {alert_name}")
        print(f"Confidence: {confidence}")
        print("Appelé depuis:")
        for line in traceback.format_stack()[:-1]:
            if "digalert" in line or "lastwar" in line:  # Adapter selon votre nom de projet
                print(line.strip())
        print("=====================\n")

        timestamp = datetime.now()
        
        # Alerte simple pour l'historique rapide
        alert_entry = {
            'timestamp': timestamp.isoformat(),
            'source_name': source_name,
            'alert_name': alert_name,
            'confidence': confidence,
            'confidence_percent': f"{confidence:.1%}",
            'detection_area': detection_area,
            'id': f"{source_name}_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"  # ID unique
        }
        
        self.alerts_history.append(alert_entry)
        
        # Sauvegarder le screenshot avec la zone marquée si disponible
        if screenshot is not None and detection_area:
            try:
                # Créer le screenshot avec la zone marquée
                marked_screenshot = screenshot.copy()
                
                if detection_area and 'x' in detection_area:
                    x = detection_area['x']
                    y = detection_area['y']
                    w = detection_area['width']
                    h = detection_area['height']
                    
                    color = (0, 255, 0) if confidence >= 0.8 else (0, 165, 255) if confidence >= 0.5 else (0, 0, 255)
                    cv2.rectangle(marked_screenshot, (x, y), (x + w, y + h), color, 3)
                    
                    text = f"{alert_name}: {confidence:.1%}"
                    cv2.rectangle(marked_screenshot, (x, y - 35), (x + 200, y - 5), color, -1)
                    cv2.putText(marked_screenshot, text, (x + 5, y - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Sauvegarder
                filename = f"alert_{alert_entry['id']}.png"
                filepath = f"static/alerts/{filename}"
                cv2.imwrite(filepath, marked_screenshot)
                
                alert_entry['screenshot_url'] = f"/static/alerts/{filename}"
                alert_entry['has_screenshot'] = True
                
                # Sauvegarder aussi la région extraite pour l'apprentissage
                if detection_area and 'x' in detection_area:
                    x, y, w, h = detection_area['x'], detection_area['y'], detection_area['width'], detection_area['height']
                    if (x >= 0 and y >= 0 and x + w <= screenshot.shape[1] and y + h <= screenshot.shape[0]):
                        region = screenshot[y:y+h, x:x+w]
                        region_filename = f"region_{alert_entry['id']}.png"
                        region_filepath = f"static/alerts/{region_filename}"
                        cv2.imwrite(region_filepath, region)
                
            except Exception as e:
                log_error(f"Erreur sauvegarde screenshot alerte: {e}")
        
        # Garder seulement les 100 dernières alertes
        if len(self.alerts_history) > 100:
            # Supprimer les vieux fichiers
            for old_alert in self.alerts_history[:-100]:
                if 'screenshot_url' in old_alert:
                    try:
                        old_file = old_alert['screenshot_url'].replace('/static/', 'static/')
                        if os.path.exists(old_file):
                            os.remove(old_file)
                    except:
                        pass
            self.alerts_history = self.alerts_history[-100:]
    
    def start(self):
        """Démarre le serveur web dans un thread séparé"""
        if not self.running:
            self.running = True
            self.server_thread = threading.Thread(
                target=self._run_server,
                daemon=True
            )
            self.server_thread.start()
            log_info(f"Interface web démarrée sur http://localhost:{self.port}")
    
    def _run_server(self):
        """Lance le serveur Flask"""
        try:
            # Désactiver les logs Flask en mode non-debug
            if not self.debug:
                import logging
                flask_log = logging.getLogger('werkzeug')
                flask_log.setLevel(logging.ERROR)
            
            self.app.run(
                host='0.0.0.0',
                port=self.port,
                debug=False,
                use_reloader=False,
                threaded=True
            )
        except Exception as e:
            log_error(f"Erreur serveur web: {e}")
    
    def stop(self):
        """Arrête le serveur web"""
        self.running = False
        log_info("Arrêt du serveur web demandé")

# Instance globale
webapp_manager = None

def init_webapp(port=5000, debug=False):
    """Initialise l'interface web"""
    global webapp_manager
    webapp_manager = WebAppManager(port, debug)
    return webapp_manager

def start_webapp():
    """Démarre l'interface web"""
    global webapp_manager
    if webapp_manager:
        webapp_manager.start()

def update_webapp_data(windows_state, global_stats):
    """Met à jour les données de l'interface web"""
    global webapp_manager
    if webapp_manager:
        webapp_manager.update_data(windows_state, global_stats)

def add_webapp_alert(source_name, alert_name, confidence, screenshot=None, detection_area=None):
    """Ajoute une alerte à l'interface web"""
    global webapp_manager
    if webapp_manager:
        webapp_manager.add_alert(source_name, alert_name, confidence, screenshot, detection_area)

def update_webapp_screenshot_with_detection(source_name, screenshot, detection_area=None, 
                                           alert_name=None, confidence=0.0):
    """Met à jour le screenshot avec zone de détection"""
    global webapp_manager
    if webapp_manager:
        return webapp_manager.update_screenshot_with_detection(
            source_name, screenshot, detection_area, alert_name, confidence
        )
    return None

def stop_webapp():
    """Arrête l'interface web"""
    global webapp_manager
    if webapp_manager:
        webapp_manager.stop()

def register_pause_callback(callback):
    """Enregistre un callback pour les changements d'état de pause"""
    global webapp_manager
    if webapp_manager:
        webapp_manager.register_pause_callback(callback)

def is_webapp_paused():
    """Vérifie si le système est en pause depuis l'interface web"""
    global webapp_manager
    if webapp_manager:
        return webapp_manager.system_paused
    return False

def set_webapp_pause_state(paused):
    """Définit l'état de pause depuis l'extérieur"""
    global webapp_manager
    if webapp_manager:
        webapp_manager.system_paused = paused

# Pour éviter l'erreur d'import dans main.py
def update_webapp_screenshot(source_name, screenshot, has_alert=False, alert_name=None):
    """Ancienne fonction pour compatibilité"""
    return update_webapp_screenshot_with_detection(source_name, screenshot, None, None, 0.0)