# -*- coding: utf-8 -*-
"""
Module de capture unifié - Capture directe avec support Last War optimisé
Remplace OBS avec capture Windows native
"""

import time
import numpy as np
import cv2
import win32gui
import win32ui
import win32con
import win32api
import win32process
import psutil
from ctypes import windll, wintypes
import ctypes
from PIL import Image, ImageGrab
import mss
from collections import deque
from utils import log_error, log_debug, log_warning, log_info, ensure_directory_exists
from config import MAX_CAPTURE_TIME_MS, DEBUG_SAVE_SCREENSHOTS, DEBUG_SCREENSHOT_PATH

# ==================== CONSTANTES ====================

# APIs Windows
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
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

# ==================== ÉNUMÉRATION MÉTHODES ====================

class CaptureMethod:
    """Méthodes de capture disponibles"""
    WIN32_GDI = "win32_gdi"
    WIN32_PRINT_WINDOW = "print_window"
    MSS_MONITOR = "mss_monitor"
    PIL_IMAGEGRAB = "pil_imagegrab"
    OBS_MODERN_PRINTWINDOW = "obs_modern_printwindow"

# ==================== STATISTIQUES ====================

class CaptureStats:
    """Statistiques de capture"""
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.total_attempts = 0
        self.successful_captures = 0
        self.failed_captures = 0
        self.total_time_ms = 0
        self.min_time_ms = float('inf')
        self.max_time_ms = 0
        self.last_error = None
        
    def add_attempt(self, success, duration_ms, error=None):
        self.total_attempts += 1
        self.total_time_ms += duration_ms
        
        if success:
            self.successful_captures += 1
            self.min_time_ms = min(self.min_time_ms, duration_ms)
            self.max_time_ms = max(self.max_time_ms, duration_ms)
        else:
            self.failed_captures += 1
            self.last_error = error
    
    @property
    def success_rate(self):
        if self.total_attempts == 0:
            return 0
        return (self.successful_captures / self.total_attempts) * 100
    
    @property
    def average_time_ms(self):
        if self.successful_captures == 0:
            return 0
        return self.total_time_ms / self.successful_captures

# Instance globale
capture_stats = CaptureStats()

# ==================== UTILITAIRES ====================

def check_window_state(hwnd):
    """Détermine l'état de la fenêtre"""
    try:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement and len(placement) >= 2:
            show_cmd = placement[1]
            is_minimized = (show_cmd == 2 or show_cmd == SW_MINIMIZE)
            is_maximized = (show_cmd == 3 or show_cmd == SW_MAXIMIZE)
            
            return {
                'is_minimized': is_minimized,
                'is_maximized': is_maximized,
                'show_cmd': show_cmd,
                'method': 'GetWindowPlacement'
            }
    except Exception as e:
        log_debug(f"GetWindowPlacement échoué: {e}")
    
    # Fallback avec dimensions
    try:
        rect = win32gui.GetWindowRect(hwnd)
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        
        window_width = rect[2] - rect[0]
        window_height = rect[3] - rect[1]
        
        is_minimized = (rect[0] < -1000 or rect[1] < -1000 or 
                       window_width < 10 or window_height < 10)
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
    
    return {
        'is_minimized': False,
        'is_maximized': False,
        'show_cmd': 'unknown',
        'method': 'default_assumption'
    }

def get_system_info():
    """Récupère les informations système"""
    try:
        import sys, subprocess
        
        info = {
            'python_version': sys.version.split()[0],
            'platform': sys.platform,
        }
        
        # Version pywin32
        try:
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
        
        return info
        
    except Exception as e:
        return {'error': str(e)}

# ==================== CLASSE PRINCIPALE ====================

class WindowCapture:
    """Capture de fenêtres Windows avec méthodes multiples"""
    
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
        
        # Initialiser stats par méthode
        for method in [CaptureMethod.WIN32_GDI, CaptureMethod.WIN32_PRINT_WINDOW, 
                      CaptureMethod.MSS_MONITOR, CaptureMethod.PIL_IMAGEGRAB,
                      CaptureMethod.OBS_MODERN_PRINTWINDOW]:
            self.capture_stats['method_stats'][method] = {
                'attempts': 0,
                'successes': 0,
                'avg_time_ms': 0,
                'total_time_ms': 0
            }
        
        self._log_system_compatibility()
    
    def _log_system_compatibility(self):
        """Log des informations de compatibilité"""
        info = self.capture_stats['system_info']
        if not info.get('error'):
            log_debug(f"Système: Python {info.get('python_version')}, "
                     f"pywin32 {info.get('pywin32_version')}")
    
    def find_window(self):
        """Trouve le handle de la fenêtre - VERSION AMÉLIORÉE"""
        def enum_callback(hwnd, results):
            try:
                # Filtrer les fenêtres invisibles d'entrée
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                
                window_text = win32gui.GetWindowText(hwnd)
                if self.window_title.lower() in window_text.lower():
                    # Vérifier que la fenêtre a des dimensions valides
                    try:
                        rect = win32gui.GetClientRect(hwnd)
                        width = rect[2] - rect[0]
                        height = rect[3] - rect[1]
                        
                        if width > 0 and height > 0:
                            # Vérifier aussi que ce n'est pas une fenêtre minimisée
                            try:
                                placement = win32gui.GetWindowPlacement(hwnd)
                                if placement and len(placement) >= 2:
                                    show_cmd = placement[1]
                                    is_minimized = (show_cmd == 2 or show_cmd == 6)
                                    
                                    # Accepter même si minimisée (PrintWindow peut capturer)
                                    # mais noter l'état
                                    results.append((hwnd, window_text, width * height, is_minimized))
                                else:
                                    results.append((hwnd, window_text, width * height, False))
                            except:
                                results.append((hwnd, window_text, width * height, False))
                        else:
                            log_debug(f"Fenêtre {window_text} ignorée (dimensions nulles)")
                    except:
                        pass
            except:
                pass
            return True
        
        results = []
        try:
            win32gui.EnumWindows(enum_callback, results)
        except Exception as e:
            log_error(f"Erreur EnumWindows: {e}")
            return False
        
        if results:
            # Trier par surface (la plus grande en premier)
            # Puis par état (non minimisée en priorité)
            results.sort(key=lambda x: (not x[3], x[2]), reverse=True)
            
            # Correspondance exacte prioritaire
            exact_match = next((hwnd for hwnd, title, _, _ in results 
                            if title.lower() == self.window_title.lower()), None)
            
            if exact_match:
                old_hwnd = self.hwnd
                self.hwnd = exact_match
                if old_hwnd and old_hwnd != exact_match:
                    log_info(f"✅ Fenêtre trouvée (exacte): {self.window_title} - Handle changé: {old_hwnd} → {exact_match}")
                else:
                    log_debug(f"Fenêtre trouvée (exacte): {self.window_title}")
            else:
                old_hwnd = self.hwnd
                self.hwnd = results[0][0]
                if old_hwnd and old_hwnd != self.hwnd:
                    log_info(f"✅ Fenêtre trouvée (partielle): {results[0][1]} - Handle changé: {old_hwnd} → {self.hwnd}")
                else:
                    log_debug(f"Fenêtre trouvée (partielle): {results[0][1]}")
            
            return True
        
        log_warning(f"Fenêtre introuvable: {self.window_title}")
        self.hwnd = None
        return False

    def recreate_capturer(window_title):
        """Recrée complètement un capturer"""
        try:
            # Supprimer l'ancien
            if window_title in multi_capture.capturers:
                old_capturer = multi_capture.capturers[window_title]
                old_capturer.cleanup() if hasattr(old_capturer, 'cleanup') else None
                del multi_capture.capturers[window_title]
                log_debug(f"Ancien capturer supprimé pour {window_title}")
            
            # Déterminer la méthode optimale
            if "last war" in window_title.lower():
                preferred_method = CaptureMethod.OBS_MODERN_PRINTWINDOW
            else:
                preferred_method = CaptureMethod.WIN32_PRINT_WINDOW
            
            # Créer le nouveau
            new_capturer = WindowCapture(window_title, preferred_method)
            multi_capture.capturers[window_title] = new_capturer
            
            # Tester immédiatement
            if new_capturer.find_window():
                log_info(f"✅ Nouveau capturer créé pour {window_title}")
                return True
            else:
                log_warning(f"⚠️ Capturer créé mais fenêtre non trouvée: {window_title}")
                return False
                
        except Exception as e:
            log_error(f"Erreur recréation capturer: {e}")
            return False

    def get_window_info(self):
        """Récupère les informations de la fenêtre - VERSION AMÉLIORÉE"""
        if not self.hwnd:
            return None
        
        try:
            info = {
                'hwnd': self.hwnd,
                'can_capture_hidden': True,
                'capture_method_available': True
            }
            
            # Titre
            try:
                info['title'] = win32gui.GetWindowText(self.hwnd)
            except:
                info['title'] = 'Error'
            
            # CORRECTION: Utiliser GetClientRect au lieu de GetWindowRect
            try:
                # Essayer d'abord GetClientRect pour les dimensions réelles
                client_rect = win32gui.GetClientRect(self.hwnd)
                client_width = client_rect[2] - client_rect[0]
                client_height = client_rect[3] - client_rect[1]
                
                # Si les dimensions client sont valides, les utiliser
                if client_width > 0 and client_height > 0:
                    info.update({
                        'width': client_width,
                        'height': client_height,
                        'client_width': client_width,
                        'client_height': client_height
                    })
                else:
                    # Fallback sur GetWindowRect
                    rect = win32gui.GetWindowRect(self.hwnd)
                    info.update({
                        'width': rect[2] - rect[0],
                        'height': rect[3] - rect[1]
                    })
            except Exception as e:
                log_debug(f"Erreur dimensions: {e}")
                # Essayer de forcer des dimensions minimales
                info.update({
                    'width': 800,  # Valeur par défaut
                    'height': 600,
                    'rect': (0, 0, 800, 600)
                })
            
            # CORRECTION: Améliorer la détection de visibilité
            try:
                # Vérifier plusieurs indicateurs de visibilité
                is_visible = win32gui.IsWindowVisible(self.hwnd)
                is_iconic = win32gui.IsIconic(self.hwnd)  # Minimisée?
                
                # Une fenêtre est considérée "visible" si:
                # - Elle n'est pas minimisée OU
                # - Elle a des dimensions valides
                info['is_visible'] = (is_visible or not is_iconic) and info.get('width', 0) > 0
                info['is_iconic'] = is_iconic
            except:
                info['is_visible'] = True  # Assumer visible par défaut
            
            # État
            window_state = check_window_state(self.hwnd)
            info.update({
                'is_minimized': window_state['is_minimized'],
                'is_maximized': window_state['is_maximized'],
                'state_detection_method': window_state['method']
            })
            
            # Processus
            try:
                _, process_id = win32process.GetWindowThreadProcessId(self.hwnd)
                info['process_id'] = process_id
                try:
                    process = psutil.Process(process_id)
                    info['process_name'] = process.name()
                except:
                    info['process_name'] = 'Unknown'
            except:
                info.update({'process_id': 0, 'process_name': 'Unknown'})
            
            # DWM cloaked
            try:
                info['is_cloaked'] = self._is_window_cloaked()
            except:
                info['is_cloaked'] = False
            
            return info
            
        except Exception as e:
            log_error(f"Erreur get_window_info: {e}")
            return {
                'hwnd': self.hwnd,
                'error': str(e),
                'title': 'Error',
                'width': 0,
                'height': 0
            }

    def _is_window_cloaked(self):
        """Vérifie si la fenêtre est masquée par DWM"""
        if not dwmapi:
            return False
        try:
            cloaked = wintypes.DWORD()
            result = dwmapi.DwmGetWindowAttribute(
                self.hwnd, DWMWA_CLOAKED,
                ctypes.byref(cloaked), ctypes.sizeof(cloaked)
            )
            return result == 0 and cloaked.value != 0
        except:
            return False
    
    # ==================== MÉTHODES DE CAPTURE ====================
    
    def capture_with_obs_modern(self):
        """Capture OBS moderne (PrintWindow 0x00000003) pour Last War"""
        start_time = time.time()
        method = CaptureMethod.OBS_MODERN_PRINTWINDOW
        
        try:
            if not self.hwnd:
                raise Exception("Handle invalide")
            
            rect = win32gui.GetWindowRect(self.hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            if width <= 0 or height <= 0:
                raise Exception(f"Dimensions invalides: {width}x{height}")
            
            hwndDC = win32gui.GetWindowDC(self.hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            # FLAG OBS: 0x00000003 (PW_CLIENTONLY | PW_RENDERFULLCONTENT)
            result = user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 0x00000003)
            
            if result:
                bmpstr = saveBitMap.GetBitmapBits(True)
                img = np.frombuffer(bmpstr, dtype='uint8')
                img.shape = (height, width, 4)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                # Nettoyage
                win32gui.DeleteObject(saveBitMap.GetHandle())
                saveDC.DeleteDC()
                mfcDC.DeleteDC()
                win32gui.ReleaseDC(self.hwnd, hwndDC)
                
                duration_ms = (time.time() - start_time) * 1000
                self._update_method_stats(method, True, duration_ms)
                log_debug(f"OBS moderne: {width}x{height} en {duration_ms:.1f}ms")
                return img
            else:
                raise Exception("PrintWindow OBS échoué")
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, False, duration_ms)
            log_debug(f"OBS moderne échoué: {e}")
            return None
    
    def capture_with_print_window(self):
        """PrintWindow standard"""
        start_time = time.time()
        method = CaptureMethod.WIN32_PRINT_WINDOW
        
        try:
            if not self.hwnd:
                log_debug("PrintWindow: Handle invalide")
                raise Exception("Handle invalide")
            
            rect = win32gui.GetWindowRect(self.hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            if width <= 0 or height <= 0:
                log_debug(f"PrintWindow: Dimensions invalides {width}x{height}")
                raise Exception(f"Dimensions invalides: {width}x{height}")
            
            log_debug(f"PrintWindow: Création contexte DC pour {width}x{height}")
            hwndDC = win32gui.GetWindowDC(self.hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            log_debug("PrintWindow: Appel PrintWindow")
            result = user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 0)
            
            if result:
                log_debug("PrintWindow: Extraction bitmap")
                bmpstr = saveBitMap.GetBitmapBits(True)
                img = np.frombuffer(bmpstr, dtype='uint8')
                img.shape = (height, width, 4)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                # Nettoyage
                win32gui.DeleteObject(saveBitMap.GetHandle())
                saveDC.DeleteDC()
                mfcDC.DeleteDC()
                win32gui.ReleaseDC(self.hwnd, hwndDC)
                
                duration_ms = (time.time() - start_time) * 1000
                self._update_method_stats(method, True, duration_ms)
                log_debug(f"PrintWindow: SUCCESS {width}x{height} en {duration_ms:.1f}ms")
                return img
            else:
                log_warning(f"PrintWindow: result=0 (échec PrintWindow API)")
                # Nettoyage même en cas d'échec
                try:
                    win32gui.DeleteObject(saveBitMap.GetHandle())
                    saveDC.DeleteDC()
                    mfcDC.DeleteDC()
                    win32gui.ReleaseDC(self.hwnd, hwndDC)
                except:
                    pass
                raise Exception("PrintWindow retourné 0")
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, False, duration_ms)
            log_debug(f"PrintWindow échoué: {e}")
            return None
        
    def capture_with_gdi(self):
        """GDI BitBlt classique"""
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
                raise Exception(f"Dimensions invalides")
            
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
                log_debug(f"GDI: {width}x{height} en {duration_ms:.1f}ms")
                return img
            else:
                raise Exception("BitBlt échoué")
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, False, duration_ms)
            log_debug(f"GDI échoué: {e}")
            return None
    
    def capture_with_mss(self):
        """MSS pour fenêtres visibles"""
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
                log_debug(f"MSS: {monitor['width']}x{monitor['height']} en {duration_ms:.1f}ms")
                return img
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, False, duration_ms)
            log_debug(f"MSS échoué: {e}")
            return None
    
    def capture_with_pil(self):
        """PIL ImageGrab"""
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
            log_debug(f"PIL: {img.shape[1]}x{img.shape[0]} en {duration_ms:.1f}ms")
            return img
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self._update_method_stats(method, False, duration_ms)
            log_debug(f"PIL échoué: {e}")
            return None
    
    def capture(self, method=None):
        """Capture principale avec validation du handle - VERSION OPTIMISÉE"""
        self.capture_stats['total_attempts'] += 1
        
        # ÉTAPE 1: Valider le handle existant
        if self.hwnd and not is_window_valid(self.hwnd):
            log_warning(f"Handle invalide détecté pour {self.window_title}, réinitialisation...")
            self.hwnd = None
            self.capture_stats['last_error'] = "Handle invalide (fenêtre fermée?)"
        
        # ÉTAPE 2: Chercher la fenêtre si nécessaire
        if not self.hwnd:
            if not self.find_window():
                self.capture_stats['last_error'] = "Fenêtre introuvable"
                log_debug(f"Fenêtre {self.window_title} introuvable")
                return None
            else:
                log_info(f"✅ Fenêtre {self.window_title} retrouvée avec nouveau handle")
        
        # ÉTAPE 3: Vérifier les dimensions
        window_info = self.get_window_info()
        if window_info:
            width = window_info.get('width', 0)
            height = window_info.get('height', 0)
            
            if width == 0 or height == 0:
                log_warning(f"Dimensions invalides ({width}x{height}), recherche de la fenêtre...")
                self.hwnd = None
                if not self.find_window():
                    self.capture_stats['last_error'] = "Impossible de réobtenir le handle"
                    return None
                window_info = self.get_window_info()
        
        # ÉTAPE 4: Si on a une méthode qui marche, l'utiliser DIRECTEMENT (early return)
        if self.last_successful_method and self.last_successful_method != CaptureMethod.OBS_MODERN_PRINTWINDOW:
            log_debug(f"🎯 Utilisation méthode qui marche: {self.last_successful_method}")
            
            try:
                img = self._try_capture_method(self.last_successful_method)
                
                if img is not None:
                    self.capture_stats['successful_captures'] += 1
                    self.capture_stats['last_error'] = None
                    return img
                else:
                    # La méthode qui marchait a échoué, on va essayer les autres
                    log_warning(f"⚠️ La méthode habituelle a échoué, rotation vers autres méthodes")
                    self.last_successful_method = None
            except Exception as e:
                log_warning(f"⚠️ Erreur avec méthode habituelle: {e}, rotation")
                self.last_successful_method = None
        
        # ÉTAPE 5: SPÉCIAL LAST WAR - OBS moderne (seulement si pas de méthode qui marche déjà)
        if "last war" in self.window_title.lower() and not self.last_successful_method:
            log_debug("🎮 Last War - Test OBS moderne (première fois)")
            img = self.capture_with_obs_modern()
            if img is not None:
                self.capture_stats['successful_captures'] += 1
                self.last_successful_method = CaptureMethod.OBS_MODERN_PRINTWINDOW
                self.capture_stats['last_error'] = None
                log_info(f"✅ OBS moderne réussie: {img.shape}")
                return img
            log_debug("OBS moderne échouée, essai méthodes standard")
        
        # ÉTAPE 6: Essayer toutes les méthodes dans l'ordre
        methods_order = [
            CaptureMethod.WIN32_PRINT_WINDOW,
            CaptureMethod.WIN32_GDI,
            CaptureMethod.MSS_MONITOR,
            CaptureMethod.PIL_IMAGEGRAB
        ]
        
        # Essayer chaque méthode
        for i, capture_method in enumerate(methods_order):
            try:
                method_name = capture_method.split('.')[-1] if '.' in capture_method else capture_method
                log_debug(f"Tentative {i+1}/{len(methods_order)}: {method_name}")
                
                img = self._try_capture_method(capture_method)
                
                if img is not None:
                    self.capture_stats['successful_captures'] += 1
                    self.last_successful_method = capture_method
                    self.capture_stats['last_error'] = None
                    log_info(f"✅ Capture réussie avec {method_name}: {img.shape}")
                    return img
                else:
                    log_debug(f"❌ {method_name} a retourné None")
                    
            except Exception as e:
                log_debug(f"❌ Méthode {capture_method} exception: {e}")
                continue
        
        # Échec complet
        self.capture_stats['last_error'] = "Toutes les méthodes ont échoué"
        log_error(f"💥 ÉCHEC TOTAL pour {self.window_title}")
        
        # Forcer reset pour rotation complète au prochain essai
        self.last_successful_method = None
        
        return None

    def _try_capture_method(self, capture_method):
        """Essaie une méthode de capture spécifique"""
        if capture_method == CaptureMethod.WIN32_PRINT_WINDOW:
            return self.capture_with_print_window()
        elif capture_method == CaptureMethod.WIN32_GDI:
            return self.capture_with_gdi()
        elif capture_method == CaptureMethod.MSS_MONITOR:
            return self.capture_with_mss()
        elif capture_method == CaptureMethod.PIL_IMAGEGRAB:
            return self.capture_with_pil()
        elif capture_method == CaptureMethod.OBS_MODERN_PRINTWINDOW:
            return self.capture_with_obs_modern()
        return None

    def cleanup(self):
        """Nettoie les ressources Windows internes"""
        try:
            log_debug(f"Nettoyage ressources pour {self.window_title}")
            
            # Forcer le garbage collector Python
            import gc
            gc.collect()
            
            # Réinitialiser toutes les stats
            self.hwnd = None
            self.last_successful_method = None
            
            # Vider le cache des templates si nécessaire
            self.capture_stats['method_stats'] = {}
            for method in [CaptureMethod.WIN32_GDI, CaptureMethod.WIN32_PRINT_WINDOW, 
                        CaptureMethod.MSS_MONITOR, CaptureMethod.PIL_IMAGEGRAB,
                        CaptureMethod.OBS_MODERN_PRINTWINDOW]:
                self.capture_stats['method_stats'][method] = {
                    'attempts': 0,
                    'successes': 0,
                    'avg_time_ms': 0,
                    'total_time_ms': 0
                }
            
            log_debug(f"Nettoyage terminé pour {self.window_title}")
            return True
            
        except Exception as e:
            log_error(f"Erreur nettoyage: {e}")
            return False
    
    def _update_method_stats(self, method, success, duration_ms):
        """Met à jour les statistiques"""
        stats = self.capture_stats['method_stats'][method]
        stats['attempts'] += 1
        
        if success:
            stats['successes'] += 1
            stats['total_time_ms'] += duration_ms
            stats['avg_time_ms'] = stats['total_time_ms'] / stats['successes']
    
    def get_capture_statistics(self):
        """Retourne les statistiques"""
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

# ==================== GESTIONNAIRE MULTI-FENÊTRES ====================

class MultiWindowCapture:
    """Gestionnaire multi-fenêtres"""
    
    def __init__(self):
        self.capturers = {}
        self.global_stats = {
            'total_windows': 0,
            'active_windows': 0,
            'total_captures': 0,
            'successful_captures': 0,
            'system_info': get_system_info(),
            'lastwar_obs_support': True
        }
        
        info = self.global_stats['system_info']
        if not info.get('error'):
            log_info(f"Capture directe: Python {info.get('python_version')}, "
                    f"pywin32 {info.get('pywin32_version')}, Support Last War OBS")
    
    def add_window(self, window_title, preferred_method=CaptureMethod.WIN32_PRINT_WINDOW):
        """Ajoute une fenêtre"""
        if window_title not in self.capturers:
            # Optimisation Last War
            if "last war" in window_title.lower():
                preferred_method = CaptureMethod.OBS_MODERN_PRINTWINDOW
                log_info(f"Last War détecté - Méthode OBS moderne")
            
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

# ==================== FONCTIONS D'INTERFACE ====================

DIRECT_CAPTURE_INITIALIZED = False

def initialize_capture_system(source_windows):
    """Initialise le système de capture"""
    global DIRECT_CAPTURE_INITIALIZED
    
    log_info("🚀 Initialisation capture directe")
    log_info("✨ Support Last War avec méthode OBS moderne")
    
    success_count = 0
    total_windows = len(source_windows)
    
    for window_config in source_windows:
        window_title = window_config.get('window_title')
        source_name = window_config.get('source_name', window_title)
        if window_title:
            log_info(f"📋 Ajout fenêtre: {source_name} -> '{window_title}'")
            
            # Ajouter la fenêtre
            multi_capture.add_window(window_title)
            
            # Test immédiat
            capturer = multi_capture.capturers[window_title]
            window_found = capturer.find_window()

            if window_found:
                window_info = capturer.get_window_info()
                if window_info and not window_info.get('error'):
                    success_count += 1
                    log_info(f"✅ {source_name}: {window_info['title']}")
                    log_info(f"   📐 Taille: {window_info['width']}x{window_info['height']}")
                    log_info(f"   ⚙️  Processus: {window_info['process_name']}")
                    log_info(f"   👁️  Visible: {window_info['is_visible']}")
                    log_info(f"   📦 Minimisée: {window_info['is_minimized']}")
                    
                    if "Last War" in window_title:
                        log_info(f"   🎮 Méthode OBS moderne activée")
                    
                    # Test de capture
                    test_img = multi_capture.capture_window(window_title)
                    if test_img is not None:
                        log_info(f"   🎯 Test capture: Succès {test_img.shape}")
                    else:
                        log_info(f"   ⚠️  Test capture: Échec (mais fenêtre détectée)")
            else:
                log_error(f"❌ {source_name}: Fenêtre '{window_title}' non détectée")
                if window_info and window_info.get('error'):
                    log_error(f"   Erreur: {window_info['error']}")
        else:
            log_error(f"❌ Configuration invalide: window_title manquant")
    
    log_info(f"🎯 Résultat: {success_count}/{total_windows} fenêtres détectées")
    
    if success_count > 0:
        DIRECT_CAPTURE_INITIALIZED = True
        log_info("✅ Initialisation réussie")
        return True
    else:
        log_error("❌ Aucune fenêtre détectée")
        log_error("🔍 Configuration reçue:")
        for i, config in enumerate(source_windows):
            log_error(f"   {i+1}. {config}")
        return False

def capture_window(ws_dummy, source_name, window_title, timeout_ms=MAX_CAPTURE_TIME_MS):
    """
    Fonction de capture compatible avec l'interface existante
    
    Args:
        ws_dummy: Ignoré (compatibilité OBS)
        source_name: Nom de la source (logs)
        window_title: Titre de la fenêtre
        timeout_ms: Timeout
    
    Returns:
        numpy.ndarray: Image ou None
    """
    global DIRECT_CAPTURE_INITIALIZED
    
    start_time = time.time()
    error_msg = None
    
    try:
        if not DIRECT_CAPTURE_INITIALIZED:
            error_msg = "Système non initialisé"
            log_error(error_msg)
            capture_stats.add_attempt(False, 0, error_msg)
            return None
        
        log_debug(f"🎯 Capture: {source_name} ({window_title})")
        
        # Ajouter fenêtre si non enregistrée
        if window_title not in multi_capture.capturers:
            multi_capture.add_window(window_title)
            log_debug(f"Fenêtre ajoutée: {window_title}")
        
        # Capturer
        img = multi_capture.capture_window(window_title)
        
        capture_time = (time.time() - start_time) * 1000
        
        if img is not None:
            capture_stats.add_attempt(True, capture_time)
            
            if capture_time > timeout_ms:
                log_warning(f"Capture {source_name} lente: {capture_time:.1f}ms > {timeout_ms}ms")
            
            # Amélioration qualité
            try:
                img = enhance_image_quality(img)
            except Exception as e:
                log_debug(f"Erreur amélioration: {e}")
            
            log_debug(f"✅ Capture {source_name}: {img.shape} en {capture_time:.1f}ms")
            
            # Debug save
            save_debug_screenshot(img, source_name, True)
            
            return img
        else:
            error_msg = "Capture échouée"
            capture_stats.add_attempt(False, capture_time, error_msg)
            
            # Diagnostics
            capturer = multi_capture.capturers.get(window_title)
            if capturer:
                window_info = capturer.get_window_info()
                if window_info:
                    log_error(f"❌ Échec {source_name}:")
                    log_error(f"   Fenêtre: {window_info['title']}")
                    log_error(f"   Visible: {window_info['is_visible']}")
                    log_error(f"   Minimisée: {window_info['is_minimized']}")
                    log_error(f"   Taille: {window_info['width']}x{window_info['height']}")
                    
                    if window_info['width'] <= 0 or window_info['height'] <= 0:
                        log_error("💡 Problème: Dimensions invalides")
                    elif window_info['is_minimized']:
                        log_info("📝 Note: Fenêtre minimisée - capture directe devrait fonctionner")
                    
                    stats = capturer.get_capture_statistics()
                    last_method = stats.get('last_successful_method', 'aucune')
                    log_debug(f"Dernière méthode réussie: {last_method}")
                else:
                    log_error(f"❌ Infos fenêtre non disponibles pour {window_title}")
            else:
                log_error(f"❌ Aucun capturer pour {window_title}")
            
            save_debug_screenshot(None, source_name, False, error_msg)
            return None

    except Exception as e:
        capture_time = (time.time() - start_time) * 1000
        error_msg = f"Erreur capture ({source_name}): {e}"
        log_error(error_msg)
        capture_stats.add_attempt(False, capture_time, error_msg)
        save_debug_screenshot(None, source_name, False, error_msg)
        return None

def is_window_valid(hwnd):
    """Vérifie si un handle de fenêtre est toujours valide"""
    if not hwnd:
        return False
    
    try:
        # Vérifier si la fenêtre existe toujours
        if not win32gui.IsWindow(hwnd):
            return False
        
        # Vérifier si le processus existe toujours
        try:
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)
            if not psutil.pid_exists(process_id):
                return False
        except:
            return False
        
        # Vérifier que la fenêtre a un titre (pas vide/détruite)
        try:
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return False
        except:
            return False
        
        return True
        
    except Exception as e:
        log_debug(f"Validation handle échouée: {e}")
        return False
    
def enhance_image_quality(image):
    """Améliore la qualité de l'image"""
    if image is None:
        log_debug("Image None dans enhance_image_quality")
        return None
    
    try:
        if not isinstance(image, np.ndarray):
            log_error(f"Type invalide: {type(image)}")
            return None
            
        if len(image.shape) != 3:
            log_error(f"Dimensions invalides: {image.shape}")
            return None
            
        if image.size == 0:
            log_debug("Image vide")
            return None
        
        # Détection écran noir
        gray_mean = np.mean(image)
        if gray_mean < 5:
            log_warning(f"Écran noir détecté (moyenne: {gray_mean:.1f})")
            return image
        
        # Conversion en niveaux de gris pour analyse
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Vérification netteté
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        if laplacian_var < 100:
            log_debug(f"Image floue (variance: {laplacian_var:.1f}), amélioration...")
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            enhanced = cv2.filter2D(image, -1, kernel)
            return enhanced
        
        return image
        
    except Exception as e:
        log_error(f"Erreur amélioration: {e}")
        return image

def save_debug_screenshot(image, source_name, success=True, error=None):
    """Sauvegarde debug"""
    if not DEBUG_SAVE_SCREENSHOTS:
        return
    
    try:
        ensure_directory_exists(DEBUG_SCREENSHOT_PATH)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        status = "success" if success else "failed"
        filename = f"{source_name}_{timestamp}_{status}.png"
        filepath = f"{DEBUG_SCREENSHOT_PATH}/{filename}"
        
        if image is not None:
            cv2.imwrite(filepath, image)
            log_debug(f"Screenshot debug sauvé: {filepath}")
        
        if error:
            error_file = filepath.replace('.png', '_error.txt')
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(f"Erreur: {error}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write(f"Source: {source_name}\n")
                f.write(f"Mode: Capture directe avec Last War OBS\n")
                
    except Exception as e:
        log_error(f"Erreur sauvegarde debug: {e}")

def get_capture_statistics():
    """Statistiques de capture"""
    direct_stats = multi_capture.get_global_statistics()
    
    return {
        # Compatibilité ancienne interface
        'total_attempts': capture_stats.total_attempts,
        'successful_captures': capture_stats.successful_captures,
        'failed_captures': capture_stats.failed_captures,
        'success_rate': capture_stats.success_rate,
        'average_time_ms': capture_stats.average_time_ms,
        'min_time_ms': capture_stats.min_time_ms if capture_stats.min_time_ms != float('inf') else 0,
        'max_time_ms': capture_stats.max_time_ms,
        'last_error': capture_stats.last_error,
        
        # Nouvelles statistiques
        'direct_capture_stats': direct_stats,
        'capture_mode': 'direct_capture_with_obs_lastwar',
        'obs_required': False,
        'hidden_window_support': True,
        'lastwar_obs_support': True
    }

def reset_capture_statistics():
    """Reset statistiques"""
    capture_stats.reset()
    
    for capturer in multi_capture.capturers.values():
        capturer.capture_stats = {
            'total_attempts': 0,
            'successful_captures': 0,
            'method_stats': {},
            'last_error': None
        }
    
    log_debug("Statistiques remises à zéro")

def cleanup_capture_system():
    """Nettoie le système"""
    global DIRECT_CAPTURE_INITIALIZED
    
    log_info("🧹 Nettoyage système de capture")
    
    multi_capture.capturers.clear()
    multi_capture.global_stats = {
        'total_windows': 0,
        'active_windows': 0,
        'total_captures': 0,
        'successful_captures': 0
    }
    
    DIRECT_CAPTURE_INITIALIZED = False
    log_info("✅ Système nettoyé")

# ==================== FONCTIONS DE COMPATIBILITÉ ====================

def validate_obs_connection():
    """Compatibilité - vérifie l'état du système"""
    return DIRECT_CAPTURE_INITIALIZED

def is_obs_connected():
    """Compatibilité - état d'initialisation"""
    return DIRECT_CAPTURE_INITIALIZED

def reconnect_obs():
    """Compatibilité - réinitialise le système"""
    global DIRECT_CAPTURE_INITIALIZED
    
    log_info("🔄 Réinitialisation système de capture...")
    
    for capturer in multi_capture.capturers.values():
        capturer.hwnd = None
    
    DIRECT_CAPTURE_INITIALIZED = True
    log_info("✅ Système réinitialisé")
    return True

# ==================== FONCTIONS ADDITIONNELLES ====================

def get_window_capture_info(window_title):
    """Info détaillée d'une fenêtre"""
    return multi_capture.get_window_info(window_title)

def optimize_capture_method(source_name, window_title, test_iterations=5):
    """Optimise la méthode de capture"""
    log_info(f"🎯 Optimisation pour {source_name}")
    
    if "Last War" in window_title:
        log_info("🎮 Last War - Méthode OBS moderne déjà optimale")
        return "obs_modern_printwindow"
    
    if window_title not in multi_capture.capturers:
        multi_capture.add_window(window_title)
    
    capturer = multi_capture.capturers[window_title]
    
    # Test de toutes les méthodes
    results = benchmark_capture_methods(window_title, test_iterations)
    
    if results:
        best_method = max(results.items(), 
                         key=lambda x: (x[1]['success_rate'], -x[1]['avg_time_ms']))
        
        capturer.preferred_method = best_method[0]
        
        log_info(f"✅ Méthode optimisée: {best_method[0]}")
        log_info(f"   Taux: {best_method[1]['success_rate']:.1f}%")
        log_info(f"   Temps: {best_method[1]['avg_time_ms']:.1f}ms")
        
        return best_method[0]
    
    return None

def benchmark_capture_methods(window_title, iterations=3):
    """Benchmark des méthodes"""
    if window_title not in multi_capture.capturers:
        multi_capture.add_window(window_title)
    
    capturer = multi_capture.capturers[window_title]
    if not capturer.find_window():
        return None
    
    methods = [CaptureMethod.WIN32_PRINT_WINDOW, CaptureMethod.WIN32_GDI, 
               CaptureMethod.MSS_MONITOR, CaptureMethod.PIL_IMAGEGRAB]
    
    if "last war" in window_title.lower():
        methods.insert(0, CaptureMethod.OBS_MODERN_PRINTWINDOW)
    
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

def test_capture_performance(source_name, window_title, iterations=10):
    """Test de performance"""
    log_info(f"Test performance {source_name} ({iterations} itérations)")
    
    if "Last War" in window_title:
        log_info("🎮 Test spécial Last War avec méthode OBS")
    
    if window_title not in multi_capture.capturers:
        multi_capture.add_window(window_title)
    
    results = []
    success_count = 0
    
    for i in range(iterations):
        start_time = time.time()
        img = capture_window(None, source_name, window_title)
        duration = (time.time() - start_time) * 1000
        
        success = img is not None
        if success:
            success_count += 1
            
        results.append({
            'iteration': i + 1,
            'success': success,
            'duration_ms': duration,
            'image_shape': img.shape if img is not None else None
        })
        
        log_debug(f"Test {i+1}/{iterations}: {'OK' if success else 'FAIL'} ({duration:.1f}ms)")
        time.sleep(0.5)
    
    durations = [r['duration_ms'] for r in results if r['success']]
    
    stats = {
        'source_name': source_name,
        'window_title': window_title,
        'total_iterations': iterations,
        'successful_captures': success_count,
        'success_rate': (success_count / iterations) * 100,
        'average_duration_ms': sum(durations) / len(durations) if durations else 0,
        'min_duration_ms': min(durations) if durations else 0,
        'max_duration_ms': max(durations) if durations else 0,
        'results': results,
        'capture_mode': 'direct_capture_with_obs_lastwar'
    }
    
    log_info(f"Test terminé - Succès: {success_count}/{iterations} ({stats['success_rate']:.1f}%), "
             f"Temps moyen: {stats['average_duration_ms']:.1f}ms")
    
    return stats

# ==================== TEST PRINCIPAL ====================

if __name__ == "__main__":
    print("🧪 TEST SYSTÈME DE CAPTURE UNIFIÉ")
    print("=" * 60)
    
    # Configuration de test
    test_windows = [
        {
            'source_name': 'test_lastwar',
            'window_title': 'Last War-Survival Game',
            'notification_cooldown': 30,
            'priority': 1
        },
        {
            'source_name': 'test_bluestacks',
            'window_title': 'BlueStacks App Player',
            'notification_cooldown': 30,
            'priority': 2
        }
    ]
    
    # Initialiser
    if initialize_capture_system(test_windows):
        print("✅ Système initialisé")
        
        # Tester captures
        for window in test_windows:
            source_name = window['source_name']
            window_title = window['window_title']
            
            print(f"\n🎯 Test: {source_name}")
            
            if "Last War" in window_title:
                print("🎮 Test méthode OBS moderne")
            
            img = capture_window(None, source_name, window_title)
            if img is not None:
                print(f"   ✅ Succès: {img.shape}")
                
                mean_color = np.mean(img)
                std_color = np.std(img)
                print(f"   📊 Qualité: luminosité={mean_color:.1f}, variation={std_color:.1f}")
                
                if std_color > 40:
                    print(f"   🏆 Excellente qualité!")
            else:
                print(f"   ❌ Échec")
        
        # Statistiques
        stats = get_capture_statistics()
        print(f"\n📊 Statistiques:")
        print(f"   Tentatives: {stats['total_attempts']}")
        print(f"   Succès: {stats['successful_captures']}")
        print(f"   Taux: {stats['success_rate']:.1f}%")
        print(f"   Support Last War OBS: {stats['lastwar_obs_support']}")
        
    else:
        print("❌ Échec initialisation")