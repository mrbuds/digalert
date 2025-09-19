# -*- coding: utf-8 -*-
"""
Module de capture directe pour remplacer OBS
Version finale avec support Last War optimisé
"""

import win32gui
import win32ui
import win32con
import win32api
import win32process
import psutil
import cv2
import numpy as np
import time
from PIL import Image, ImageGrab
import mss
import ctypes
from ctypes import wintypes
from utils import log_error, log_debug, log_warning, log_info
from config import MAX_CAPTURE_TIME_MS

# Import des APIs Windows directement
user32 = ctypes.windll.user32
try:
    dwmapi = ctypes.windll.dwmapi
except:
    dwmapi = None
gdi32 = ctypes.windll.gdi32

# Constantes Windows
SW_HIDE = 0
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
SW_SHOW = 5
SW_SHOWDEFAULT = 10
SW_SHOWMAXIMIZED = 3
SW_SHOWMINIMIZED = 2
SW_SHOWMINNOACTIVE = 7
SW_SHOWNA = 8
SW_SHOWNOACTIVATE = 4
SW_SHOWNORMAL = 1

# Constantes pour DWM
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

class CaptureMethod:
    """Énumération des méthodes de capture disponibles"""
    WIN32_GDI = "win32_gdi"
    WIN32_PRINT_WINDOW = "print_window"
    MSS_MONITOR = "mss_monitor"
    PIL_IMAGEGRAB = "pil_imagegrab"
    OBS_MODERN_PRINTWINDOW = "obs_modern_printwindow"  # NOUVEAU

def check_window_state(hwnd):
    """
    Détermine l'état de la fenêtre en utilisant GetWindowPlacement
    Cette méthode fonctionne avec toutes les versions de pywin32
    """
    try:
        # Méthode 1: GetWindowPlacement - toujours disponible
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement and len(placement) >= 2:
            show_cmd = placement[1]
            
            is_minimized = (show_cmd == SW_SHOWMINIMIZED or show_cmd == SW_MINIMIZE)
            is_maximized = (show_cmd == SW_SHOWMAXIMIZED or show_cmd == SW_MAXIMIZE)
            
            return {
                'is_minimized': is_minimized,
                'is_maximized': is_maximized,
                'show_cmd': show_cmd,
                'method': 'GetWindowPlacement'
            }
    except Exception as e:
        log_debug(f"GetWindowPlacement échoué: {e}")
    
    # Méthode 2: Fallback avec vérification des dimensions
    try:
        rect = win32gui.GetWindowRect(hwnd)
        screen_width = win32api.GetSystemMetrics(0)  # SM_CXSCREEN
        screen_height = win32api.GetSystemMetrics(1)  # SM_CYSCREEN
        
        window_width = rect[2] - rect[0]
        window_height = rect[3] - rect[1]
        
        # Considérer comme minimisée si hors écran ou très petit
        is_minimized = (rect[0] < -1000 or rect[1] < -1000 or 
                       window_width < 10 or window_height < 10)
        
        # Considérer comme maximisée si proche de la taille de l'écran
        is_maximized = (window_width >= screen_width * 0.95 and 
                       window_height >= screen_height * 0.9)
        
        return {
            'is_minimized': is_minimized,
            'is_maximized': is_maximized,
            'show_cmd': 'unknown',
            'method': 'dimensions_fallback'
        }
    except Exception as e:
        log_debug(f"Fallback dimensions échoué: {e}")
    
    # Méthode 3: Derniers recours - supposer état normal
    return {
        'is_minimized': False,
        'is_maximized': False,
        'show_cmd': 'unknown',
        'method': 'default_assumption'
    }

def get_system_info():
    """Récupère les informations système pour diagnostic"""
    try:
        import sys
        
        info = {
            'python_version': sys.version.split()[0],
            'platform': sys.platform,
        }
        
        # Version pywin32
        try:
            import subprocess
            result = subprocess.run([sys.executable, "-m", "pip", "show", "pywin32"], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('Version:'):
                        info['pywin32_version'] = line.split(':', 1)[1].strip()
                        break
            else:
                info['pywin32_version'] = 'unknown'
        except:
            info['pywin32_version'] = 'detection_failed'
        
        # Test des fonctions disponibles
        available_functions = []
        test_functions = [
            'GetWindowRect', 'GetWindowText', 'EnumWindows', 'IsWindowVisible',
            'GetWindowPlacement', 'GetClientRect', 'GetWindowDC'
        ]
        
        for func_name in test_functions:
            if hasattr(win32gui, func_name):
                available_functions.append(func_name)
        
        info['win32gui_functions'] = available_functions
        info['functions_count'] = len(available_functions)
        
        return info
        
    except Exception as e:
        return {'error': str(e)}

class WindowCapture:
    """Classe principale pour la capture de fenêtres - version finale optimisée"""
    
    def __init__(self, window_title, preferred_method=CaptureMethod.WIN32_PRINT_WINDOW):
        self.window_title = window_title
        self.preferred_method = preferred_method
        self.hwnd = None
        self.last_successful_method = None
        self.capture_stats = {
            'total_attempts': 0,
            'successful_captures': 0,
            'method_stats': {},
            'last_error': None,
            'system_info': get_system_info()
        }
        
        # Initialiser les statistiques par méthode
        for method in [CaptureMethod.WIN32_GDI, CaptureMethod.WIN32_PRINT_WINDOW, 
                      CaptureMethod.MSS_MONITOR, CaptureMethod.PIL_IMAGEGRAB,
                      CaptureMethod.OBS_MODERN_PRINTWINDOW]:
            self.capture_stats['method_stats'][method] = {
                'attempts': 0,
                'successes': 0,
                'avg_time_ms': 0,
                'total_time_ms': 0
            }
        
        # Log des informations système au premier démarrage
        self._log_system_compatibility()
    
    def _log_system_compatibility(self):
        """Log des informations de compatibilité"""
        info = self.capture_stats['system_info']
        if not info.get('error'):
            log_debug(f"Système détecté: Python {info.get('python_version')}, "
                     f"pywin32 {info.get('pywin32_version')}, "
                     f"{info.get('functions_count')} fonctions win32gui disponibles")
    
    def find_window(self):
        """Trouve le handle de la fenêtre par son titre"""
        def enum_window_callback(hwnd, results):
            try:
                if win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    if self.window_title.lower() in window_text.lower():
                        results.append((hwnd, window_text))
            except Exception:
                pass  # Ignorer les erreurs sur des fenêtres individuelles
            return True
        
        results = []
        try:
            win32gui.EnumWindows(enum_window_callback, results)
        except Exception as e:
            log_error(f"Erreur EnumWindows: {e}")
            return False
        
        if results:
            # Correspondance exacte en priorité
            exact_match = next((hwnd for hwnd, title in results 
                              if title.lower() == self.window_title.lower()), None)
            
            if exact_match:
                self.hwnd = exact_match
                log_debug(f"Fenêtre trouvée (exacte): {self.window_title}")
            else:
                self.hwnd = results[0][0]
                log_debug(f"Fenêtre trouvée (partielle): {results[0][1]}")
            
            return True
        
        log_warning(f"Fenêtre introuvable: {self.window_title}")
        self.hwnd = None
        return False
    
    def get_window_info(self):
        """Récupère les informations de la fenêtre avec méthodes robustes"""
        if not self.hwnd:
            return None
        
        try:
            # Informations de base toujours disponibles
            info = {
                'hwnd': self.hwnd,
                'can_capture_hidden': True,
                'capture_method_available': True
            }
            
            # Titre de la fenêtre
            try:
                info['title'] = win32gui.GetWindowText(self.hwnd)
            except Exception as e:
                info['title'] = f'Error: {e}'
            
            # Coordonnées de la fenêtre
            try:
                rect = win32gui.GetWindowRect(self.hwnd)
                info.update({
                    'rect': rect,
                    'width': rect[2] - rect[0],
                    'height': rect[3] - rect[1]
                })
            except Exception as e:
                log_debug(f"Erreur GetWindowRect: {e}")
                info.update({
                    'rect': (0, 0, 0, 0),
                    'width': 0,
                    'height': 0
                })
            
            # Zone client
            try:
                client_rect = win32gui.GetClientRect(self.hwnd)
                info.update({
                    'client_rect': client_rect,
                    'client_width': client_rect[2] - client_rect[0],
                    'client_height': client_rect[3] - client_rect[1]
                })
            except Exception as e:
                log_debug(f"Erreur GetClientRect: {e}")
                info.update({
                    'client_rect': (0, 0, 0, 0),
                    'client_width': 0,
                    'client_height': 0
                })
            
            # État de la fenêtre avec méthode robuste
            window_state = check_window_state(self.hwnd)
            info.update({
                'is_minimized': window_state['is_minimized'],
                'is_maximized': window_state['is_maximized'],
                'state_detection_method': window_state['method']
            })
            
            # Visibilité
            try:
                info['is_visible'] = win32gui.IsWindowVisible(self.hwnd)
            except Exception as e:
                log_debug(f"Erreur IsWindowVisible: {e}")
                info['is_visible'] = True  # Assumption par défaut
            
            # Informations processus
            try:
                _, process_id = win32process.GetWindowThreadProcessId(self.hwnd)
                info['process_id'] = process_id
                
                try:
                    process = psutil.Process(process_id)
                    info['process_name'] = process.name()
                except Exception:
                    info['process_name'] = 'Unknown'
                    
            except Exception as e:
                log_debug(f"Erreur process info: {e}")
                info.update({
                    'process_id': 0,
                    'process_name': 'Unknown'
                })
            
            # Vérification DWM (optionnel)
            try:
                info['is_cloaked'] = self._is_window_cloaked()
            except Exception:
                info['is_cloaked'] = False
            
            return info
            
        except Exception as e:
            log_error(f"Erreur get_window_info: {e}")
            return {
                'hwnd': self.hwnd,
                'error': str(e),
                'title': 'Error',
                'width': 0,
                'height': 0,
                'can_capture_hidden': True
            }
    
    def _is_window_cloaked(self):
        """Vérifie si la fenêtre est masquée par DWM"""
        if not dwmapi:
            return False
        
        try:
            cloaked = wintypes.DWORD()
            result = dwmapi.DwmGetWindowAttribute(
                self.hwnd,
                DWMWA_CLOAKED,
                ctypes.byref(cloaked),
                ctypes.sizeof(cloaked)
            )
            return result == 0 and cloaked.value != 0
        except Exception:
            return False
    
    def capture_with_obs_modern(self):
        """
        NOUVEAU: Capture avec méthode OBS moderne
        Utilise PrintWindow avec flag 0x00000003 (comme OBS Windows 10 1903+)
        """
        start_time = time.time()
        method = CaptureMethod.OBS_MODERN_PRINTWINDOW
        
        try:
            if not self.hwnd:
                raise Exception("Handle de fenêtre invalide")
            
            # Obtenir les dimensions
            rect = win32gui.GetWindowRect(self.hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            if width <= 0 or height <= 0:
                raise Exception(f"Dimensions invalides: {width}x{height}")
            
            # Créer le contexte de périphérique
            hwndDC = win32gui.GetWindowDC(self.hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            
            # Créer le bitmap
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            # FLAG MAGIQUE OBS: 0x00000003 (PW_CLIENTONLY | PW_RENDERFULLCONTENT)
            result = user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 0x00000003)
            
            if result:
                # Convertir en numpy array
                bmpstr = saveBitMap.GetBitmapBits(True)
                img = np.frombuffer(bmpstr, dtype='uint8')
                img.shape = (height, width, 4)  # BGRA
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                # Nettoyage
                win32gui.DeleteObject(saveBitMap.GetHandle())
                saveDC.DeleteDC()
                mfcDC.DeleteDC()
                win32gui.ReleaseDC(self.hwnd, hwndDC)
                
                duration_ms = (time.time() - start_time) * 1000
                self._update_method_stats(method, True, duration_ms)
                
                log_debug(f"OBS moderne réussi: {width}x{height} en {duration_ms:.1f}ms")
                return img
            else:
                raise Exception("PrintWindow OBS moderne a échoué")
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, False, duration_ms)
            log_debug(f"OBS moderne échoué: {e}")
            return None
    
    def capture_with_print_window(self):
        """Capture avec PrintWindow - Méthode principale pour fenêtres cachées"""
        start_time = time.time()
        method = CaptureMethod.WIN32_PRINT_WINDOW
        
        try:
            if not self.hwnd:
                raise Exception("Handle de fenêtre invalide")
            
            # Obtenir les dimensions
            rect = win32gui.GetWindowRect(self.hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            if width <= 0 or height <= 0:
                raise Exception(f"Dimensions invalides: {width}x{height}")
            
            # Créer le contexte de périphérique
            hwndDC = win32gui.GetWindowDC(self.hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            
            # Créer le bitmap
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            # PrintWindow - capture même les fenêtres cachées
            result = user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 0)
            
            if result:
                # Convertir en numpy array
                bmpstr = saveBitMap.GetBitmapBits(True)
                img = np.frombuffer(bmpstr, dtype='uint8')
                img.shape = (height, width, 4)  # BGRA
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                # Nettoyage
                win32gui.DeleteObject(saveBitMap.GetHandle())
                saveDC.DeleteDC()
                mfcDC.DeleteDC()
                win32gui.ReleaseDC(self.hwnd, hwndDC)
                
                duration_ms = (time.time() - start_time) * 1000
                self._update_method_stats(method, True, duration_ms)
                
                log_debug(f"PrintWindow réussi: {width}x{height} en {duration_ms:.1f}ms")
                return img
            else:
                raise Exception("PrintWindow a échoué")
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, False, duration_ms)
            log_debug(f"PrintWindow échoué: {e}")
            return None
    
    def capture_with_gdi(self):
        """Capture avec GDI classique"""
        start_time = time.time()
        method = CaptureMethod.WIN32_GDI
        
        try:
            if not self.hwnd:
                raise Exception("Handle invalide")
            
            hwndDC = win32gui.GetWindowDC(self.hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            
            rect = win32gui.GetWindowRect(self.hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            if width <= 0 or height <= 0:
                raise Exception(f"Dimensions invalides: {width}x{height}")
            
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            result = saveDC.BitBlt((0, 0), (width, height), mfcDC, (0, 0), win32con.SRCCOPY)
            
            if result:
                bmpstr = saveBitMap.GetBitmapBits(True)
                img = np.frombuffer(bmpstr, dtype='uint8')
                img.shape = (height, width, 4)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                win32gui.DeleteObject(saveBitMap.GetHandle())
                saveDC.DeleteDC()
                mfcDC.DeleteDC()
                win32gui.ReleaseDC(self.hwnd, hwndDC)
                
                duration_ms = (time.time() - start_time) * 1000
                self._update_method_stats(method, True, duration_ms)
                
                log_debug(f"GDI réussi: {width}x{height} en {duration_ms:.1f}ms")
                return img
            else:
                raise Exception("BitBlt échoué")
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, False, duration_ms)
            log_debug(f"GDI échoué: {e}")
            return None
    
    def capture_with_mss(self):
        """Capture avec MSS - fenêtres visibles seulement"""
        start_time = time.time()
        method = CaptureMethod.MSS_MONITOR
        
        try:
            if not self.hwnd:
                raise Exception("Handle invalide")
            
            rect = win32gui.GetWindowRect(self.hwnd)
            
            if not win32gui.IsWindowVisible(self.hwnd):
                raise Exception("Fenêtre non visible")
            
            monitor = {
                "top": rect[1],
                "left": rect[0],
                "width": rect[2] - rect[0],
                "height": rect[3] - rect[1]
            }
            
            if monitor["width"] <= 0 or monitor["height"] <= 0:
                raise Exception("Dimensions invalides")
            
            with mss.mss() as sct:
                screenshot = sct.grab(monitor)
                img = np.array(screenshot)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                duration_ms = (time.time() - start_time) * 1000
                self._update_method_stats(method, True, duration_ms)
                
                log_debug(f"MSS réussi: {monitor['width']}x{monitor['height']} en {duration_ms:.1f}ms")
                return img
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, False, duration_ms)
            log_debug(f"MSS échoué: {e}")
            return None
    
    def capture_with_pil(self):
        """Capture avec PIL"""
        start_time = time.time()
        method = CaptureMethod.PIL_IMAGEGRAB
        
        try:
            if not self.hwnd:
                raise Exception("Handle invalide")
            
            rect = win32gui.GetWindowRect(self.hwnd)
            screenshot = ImageGrab.grab(bbox=rect)
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, True, duration_ms)
            
            log_debug(f"PIL réussi: {img.shape[1]}x{img.shape[0]} en {duration_ms:.1f}ms")
            return img
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, False, duration_ms)
            log_debug(f"PIL échoué: {e}")
            return None
    
    def capture(self, method=None):
        """Capture principale avec fallback intelligent et support Last War"""
        self.capture_stats['total_attempts'] += 1
        
        if not self.hwnd:
            if not self.find_window():
                self.capture_stats['last_error'] = "Fenêtre introuvable"
                return None
        
        # SPÉCIAL LAST WAR : utiliser OBS moderne en priorité
        if "last war" in self.window_title.lower():
            log_debug("Détection Last War - Utilisation méthode OBS moderne")
            img = self.capture_with_obs_modern()
            if img is not None:
                self.capture_stats['successful_captures'] += 1
                self.last_successful_method = CaptureMethod.OBS_MODERN_PRINTWINDOW
                self.capture_stats['last_error'] = None
                log_debug(f"Last War capturé avec méthode OBS moderne")
                return img
            else:
                log_debug("Méthode OBS moderne échouée pour Last War, essai méthodes standard")
        
        # Ordre de priorité optimisé
        methods_order = [
            CaptureMethod.WIN32_PRINT_WINDOW,  # Meilleur pour fenêtres cachées
            CaptureMethod.WIN32_GDI,           # Alternative solide
            CaptureMethod.MSS_MONITOR,         # Rapide si visible
            CaptureMethod.PIL_IMAGEGRAB        # Dernier recours
        ]
        
        # Commencer par la méthode préférée si spécifiée
        if method and method in methods_order:
            methods_order.remove(method)
            methods_order.insert(0, method)
        elif self.last_successful_method and self.last_successful_method in methods_order:
            methods_order.remove(self.last_successful_method)
            methods_order.insert(0, self.last_successful_method)
        
        # Essayer chaque méthode
        for capture_method in methods_order:
            try:
                img = None
                
                if capture_method == CaptureMethod.WIN32_PRINT_WINDOW:
                    img = self.capture_with_print_window()
                elif capture_method == CaptureMethod.WIN32_GDI:
                    img = self.capture_with_gdi()
                elif capture_method == CaptureMethod.MSS_MONITOR:
                    img = self.capture_with_mss()
                elif capture_method == CaptureMethod.PIL_IMAGEGRAB:
                    img = self.capture_with_pil()
                
                if img is not None:
                    self.capture_stats['successful_captures'] += 1
                    self.last_successful_method = capture_method
                    self.capture_stats['last_error'] = None
                    
                    log_debug(f"Capture réussie avec: {capture_method}")
                    return img
                    
            except Exception as e:
                log_debug(f"Méthode {capture_method} échouée: {e}")
                continue
        
        # Échec complet
        self.capture_stats['last_error'] = "Toutes les méthodes ont échoué"
        log_warning(f"Échec capture {self.window_title}")
        return None
    
    def _update_method_stats(self, method, success, duration_ms):
        """Met à jour les statistiques"""
        stats = self.capture_stats['method_stats'][method]
        stats['attempts'] += 1
        
        if success:
            stats['successes'] += 1
            stats['total_time_ms'] += duration_ms
            stats['avg_time_ms'] = stats['total_time_ms'] / stats['successes']
    
    def get_capture_statistics(self):
        """Retourne les statistiques complètes"""
        stats = self.capture_stats.copy()
        
        for method, method_stats in stats['method_stats'].items():
            if method_stats['attempts'] > 0:
                method_stats['success_rate'] = (method_stats['successes'] / method_stats['attempts']) * 100
            else:
                method_stats['success_rate'] = 0
        
        if stats['total_attempts'] > 0:
            stats['global_success_rate'] = (stats['successful_captures'] / stats['total_attempts']) * 100
        else:
            stats['global_success_rate'] = 0
        
        stats['preferred_method'] = self.preferred_method
        stats['last_successful_method'] = self.last_successful_method
        
        return stats


# Gestionnaire global
class MultiWindowCapture:
    """Gestionnaire multi-fenêtres avec support Last War optimisé"""
    
    def __init__(self):
        self.capturers = {}
        self.global_stats = {
            'total_windows': 0,
            'active_windows': 0,
            'total_captures': 0,
            'successful_captures': 0,
            'system_info': get_system_info(),
            'lastwar_obs_support': True  # NOUVEAU
        }
        
        # Log info système
        info = self.global_stats['system_info']
        if not info.get('error'):
            log_info(f"🔧 Capture directe finale: Python {info.get('python_version')}, "
                    f"pywin32 {info.get('pywin32_version')}, Support Last War OBS")
    
    def add_window(self, window_title, preferred_method=CaptureMethod.WIN32_PRINT_WINDOW):
        """Ajoute une fenêtre avec méthode optimisée selon le type"""
        if window_title not in self.capturers:
            # Optimisation automatique pour Last War
            if "last war" in window_title.lower():
                preferred_method = CaptureMethod.OBS_MODERN_PRINTWINDOW
                log_info(f"🎮 Last War détecté - Méthode OBS moderne sélectionnée")
            
            self.capturers[window_title] = WindowCapture(window_title, preferred_method)
            self.global_stats['total_windows'] += 1
            log_info(f"Fenêtre ajoutée: {window_title}")
    
    def capture_window(self, window_title, method=None):
        """Capture une fenêtre"""
        if window_title not in self.capturers:
            log_error(f"Fenêtre non enregistrée: {window_title}")
            return None
        
        self.global_stats['total_captures'] += 1
        img = self.capturers[window_title].capture(method)
        
        if img is not None:
            self.global_stats['successful_captures'] += 1
        
        return img
    
    def get_window_info(self, window_title):
        """Info d'une fenêtre"""
        if window_title not in self.capturers:
            return None
        return self.capturers[window_title].get_window_info()
    
    def get_all_windows_info(self):
        """Info de toutes les fenêtres"""
        info = {}
        for window_title, capturer in self.capturers.items():
            window_info = capturer.get_window_info()
            if window_info:
                info[window_title] = window_info
        return info
    
    def get_global_statistics(self):
        """Statistiques globales"""
        stats = self.global_stats.copy()
        stats['windows'] = {}
        
        for window_title, capturer in self.capturers.items():
            stats['windows'][window_title] = capturer.get_capture_statistics()
        
        # Compter fenêtres actives
        active_count = sum(1 for capturer in self.capturers.values() 
                          if capturer.hwnd and capturer.get_window_info())
        stats['active_windows'] = active_count
        
        if stats['total_captures'] > 0:
            stats['global_success_rate'] = (stats['successful_captures'] / stats['total_captures']) * 100
        else:
            stats['global_success_rate'] = 0
        
        return stats


# Instance globale
multi_capture = MultiWindowCapture()

# Fonctions d'interface pour compatibilité
def capture_window_direct(window_title, method=None):
    """Fonction de capture compatible OBS avec support Last War"""
    if window_title not in multi_capture.capturers:
        multi_capture.add_window(window_title)
    return multi_capture.capture_window(window_title, method)

def initialize_direct_capture(windows_config):
    """Initialise la capture directe avec support Last War optimisé"""
    log_info("🔧 Initialisation capture directe finale")
    
    success_count = 0
    total_windows = len(windows_config)
    
    for window_config in windows_config:
        window_title = window_config.get('window_title')
        source_name = window_config.get('source_name', window_title)
        
        if window_title:
            log_info(f"📋 Ajout fenêtre: {source_name} -> '{window_title}'")
            
            # Ajouter la fenêtre au gestionnaire multi-capture
            multi_capture.add_window(window_title)
            
            # Test immédiat de la fenêtre
            capturer = multi_capture.capturers[window_title]
            window_found = capturer.find_window()

            if window_found:
                # Maintenant récupérer les infos
                window_info = capturer.get_window_info()
                if window_info and not window_info.get('error'):
                    success_count += 1
                    log_info(f"✅ {source_name}: {window_info['title']}")
                    log_info(f"   📐 Taille: {window_info['width']}x{window_info['height']}")
                    log_info(f"   ⚙️  Processus: {window_info['process_name']}")
                    log_info(f"   👁️  Visible: {window_info['is_visible']}")
                    log_info(f"   📦 Minimisée: {window_info['is_minimized']}")
                    
                    # Spécial Last War
                    if "Last War" in window_title:
                        log_info(f"   🎮 Méthode OBS moderne activée pour Last War")
                    
                    # Test de capture pour être sûr
                    test_img = multi_capture.capture_window(window_title)
                    if test_img is not None:
                        log_info(f"   🎯 Test capture: Succès {test_img.shape}")
                    else:
                        log_info(f"   ⚠️  Test capture: Échec (mais fenêtre détectée)")
                        # NE PAS décrémenter success_count, la fenêtre existe
            else:
                log_error(f"❌ {source_name}: Fenêtre '{window_title}' non détectée")
                if window_info and window_info.get('error'):
                    log_error(f"   Erreur: {window_info['error']}")
        else:
            log_error(f"❌ Configuration invalide: window_title manquant")
    
    log_info(f"🎯 Résultat final: {success_count}/{total_windows} fenêtres détectées")
    
    # CORRECTION: Accepter même un succès partiel
    if success_count > 0:
        log_info("✅ Initialisation réussie (au moins une fenêtre détectée)")
        return True
    else:
        log_error("❌ Aucune fenêtre détectée - vérifiez la configuration")
        
        # Debug: afficher la configuration reçue
        log_error("🔍 Configuration reçue:")
        for i, config in enumerate(windows_config):
            log_error(f"   {i+1}. {config}")
        
        return False

def get_capture_statistics():
    """Statistiques de capture"""
    return multi_capture.get_global_statistics()

def benchmark_capture_methods(window_title, iterations=3):
    """Benchmark avec support Last War"""
    if window_title not in multi_capture.capturers:
        multi_capture.add_window(window_title)
    
    capturer = multi_capture.capturers[window_title]
    if not capturer.find_window():
        return None
    
    # Inclure la méthode OBS moderne pour Last War
    methods = [CaptureMethod.WIN32_PRINT_WINDOW, CaptureMethod.WIN32_GDI, 
               CaptureMethod.MSS_MONITOR, CaptureMethod.PIL_IMAGEGRAB]
    
    if "last war" in window_title.lower():
        methods.insert(0, CaptureMethod.OBS_MODERN_PRINTWINDOW)  # En priorité
    
    results = {}
    for method in methods:
        successes = 0
        times = []
        
        for i in range(iterations):
            start = time.time()
            
            if method == CaptureMethod.OBS_MODERN_PRINTWINDOW:
                img = capturer.capture_with_obs_modern()
            else:
                img = capturer.capture(method)
                
            duration = (time.time() - start) * 1000
            times.append(duration)
            if img is not None:
                successes += 1
        
        results[method] = {
            'success_rate': (successes / iterations) * 100,
            'avg_time_ms': sum(times) / len(times),
            'total_successes': successes,
            'total_iterations': iterations
        }
    
    return results

def test_lastwar_obs_method():
    """Test spécifique de la méthode OBS pour Last War"""
    print("🎮 TEST MÉTHODE OBS POUR LAST WAR")
    print("=" * 40)
    
    window_title = "Last War-Survival Game"
    
    # Créer un capturer spécifique
    capturer = WindowCapture(window_title, CaptureMethod.OBS_MODERN_PRINTWINDOW)
    
    if capturer.find_window():
        print(f"✅ Fenêtre Last War trouvée")
        
        # Test de la méthode OBS moderne
        for i in range(3):
            print(f"\n🧪 Test OBS moderne {i+1}/3:")
            
            start_time = time.time()
            img = capturer.capture_with_obs_modern()
            duration = (time.time() - start_time) * 1000
            
            if img is not None:
                print(f"   ✅ Succès: {img.shape} en {duration:.1f}ms")
                
                # Analyser la qualité
                mean_color = np.mean(img)
                std_color = np.std(img)
                
                print(f"   📊 Qualité: luminosité={mean_color:.1f}, variation={std_color:.1f}")
                
                if std_color > 40 and 30 < mean_color < 180:
                    print(f"   🏆 Excellente qualité!")
                
                # Sauvegarder le premier test
                if i == 0:
                    filename = f"lastwar_obs_test.png"
                    cv2.imwrite(filename, img)
                    print(f"   💾 Sauvé: {filename}")
            else:
                print(f"   ❌ Échec en {duration:.1f}ms")
        
        # Statistiques de la méthode
        stats = capturer.get_capture_statistics()
        obs_stats = stats['method_stats'].get(CaptureMethod.OBS_MODERN_PRINTWINDOW, {})
        
        print(f"\n📊 Statistiques méthode OBS:")
        print(f"   Tentatives: {obs_stats.get('attempts', 0)}")
        print(f"   Succès: {obs_stats.get('successes', 0)}")
        print(f"   Taux: {obs_stats.get('success_rate', 0):.1f}%")
        print(f"   Temps moyen: {obs_stats.get('avg_time_ms', 0):.1f}ms")
        
        return obs_stats.get('successes', 0) > 0
    else:
        print(f"❌ Fenêtre Last War non trouvée")
        return False

if __name__ == "__main__":
    # Test complet du système final
    print("🚀 TEST COMPLET SYSTÈME CAPTURE DIRECTE FINAL")
    print("Avec support Last War méthode OBS moderne")
    print("=" * 60)
    
    # Test 1: Méthode OBS pour Last War
    obs_success = test_lastwar_obs_method()
    
    # Test 2: Système complet
    print(f"\n" + "="*60)
    print("🔧 TEST SYSTÈME COMPLET")
    print("="*30)
    
    # Configuration de test
    test_windows = [
        {
            'window_title': 'Last War-Survival Game',
            'source_name': 'lastwar_test',
            'priority': 1
        },
        {
            'window_title': 'BlueStacks App Player',
            'source_name': 'bluestacks_test',
            'priority': 2
        }
    ]
    
    # Initialiser le système
    success = initialize_direct_capture(test_windows)
    
    if success:
        print(f"✅ Système initialisé avec succès")
        
        # Test de capture sur chaque fenêtre
        for window_config in test_windows:
            window_title = window_config['window_title']
            source_name = window_config['source_name']
            
            print(f"\n🎯 Test final {source_name} ({window_title}):")
            
            img = capture_window_direct(window_title)
            if img is not None:
                print(f"   ✅ Capture réussie: {img.shape}")
                
                # Analyser la qualité
                mean_color = np.mean(img)
                std_color = np.std(img)
                print(f"   📊 Qualité: luminosité={mean_color:.1f}, variation={std_color:.1f}")
                
                if "Last War" in window_title:
                    if std_color > 50:
                        print(f"   🎮 Last War: Qualité OBS parfaite!")
                    else:
                        print(f"   ⚠️ Last War: Vérifiez la qualité visuellement")
                
                # Sauvegarder
                filename = f"final_test_{source_name}.png"
                cv2.imwrite(filename, img)
                print(f"   💾 Sauvé: {filename}")
            else:
                print(f"   ❌ Capture échouée")
        
        # Statistiques finales
        global_stats = get_capture_statistics()
        print(f"\n📊 Statistiques finales:")
        print(f"   Fenêtres totales: {global_stats['total_windows']}")
        print(f"   Fenêtres actives: {global_stats['active_windows']}")
        print(f"   Captures totales: {global_stats['total_captures']}")
        print(f"   Captures réussies: {global_stats['successful_captures']}")
        print(f"   Support Last War OBS: {global_stats['lastwar_obs_support']}")
        
        if global_stats['total_captures'] > 0:
            success_rate = (global_stats['successful_captures'] / global_stats['total_captures']) * 100
            print(f"   Taux de succès global: {success_rate:.1f}%")
    
    else:
        print(f"❌ Échec initialisation système")
    
    print(f"\n" + "="*60)
    print("🏁 RÉSUMÉ FINAL")
    print("="*20)
    
    if obs_success:
        print("✅ Méthode OBS Last War: FONCTIONNE")
    else:
        print("❌ Méthode OBS Last War: PROBLÈME")
    
    if success:
        print("✅ Système complet: OPÉRATIONNEL")
        print("🎉 PRÊT POUR LA PRODUCTION!")
        print("💡 Cette version utilise la même technologie qu'OBS pour Last War")
    else:
        print("❌ Système complet: PROBLÈME")
    
    input(f"\nAppuyez sur Entrée pour quitter...")