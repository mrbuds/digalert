# -*- coding: utf-8 -*-
"""
Module de capture unifié - Version refactorisée
Combine le meilleur de capture.py et capture_direct.py
"""

import time
import numpy as np
import cv2
import win32gui
import win32ui
from ctypes import windll
try:
    from .constants import MAX_CAPTURE_TIME_MS
except ImportError:
    MAX_CAPTURE_TIME_MS = 5000

class CaptureMethod:
    """Méthodes de capture disponibles"""
    WIN32_GDI = "win32_gdi"
    WIN32_PRINT_WINDOW = "print_window"
    OBS_MODERN_PRINTWINDOW = "obs_modern_printwindow"

class WindowCapture:
    """Capture de fenêtres Windows avec support Last War optimisé"""
    
    def __init__(self, window_title, preferred_method=CaptureMethod.WIN32_PRINT_WINDOW):
        self.window_title = window_title
        self.preferred_method = preferred_method
        self.hwnd = None
        self.stats = {
            'total_attempts': 0,
            'successful_captures': 0,
            'avg_time_ms': 0
        }
        
    def find_window(self):
        """Trouve la fenêtre par son titre"""
        def enum_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                if self.window_title.lower() in window_text.lower():
                    results.append(hwnd)
            return True
        
        results = []
        win32gui.EnumWindows(enum_callback, results)
        
        if results:
            self.hwnd = results[0]
            return True
        return False
        
    def capture_lastwar_optimized(self):
        """Capture spéciale Last War avec méthode OBS moderne"""
        if not self.hwnd:
            return None
            
        try:
            rect = win32gui.GetWindowRect(self.hwnd)
            width, height = rect[2] - rect[0], rect[3] - rect[1]
            
            if width <= 0 or height <= 0:
                return None
                
            hwndDC = win32gui.GetWindowDC(self.hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            # Flag OBS moderne : 0x00000003
            result = windll.user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 0x00000003)
            
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
                
                return img
                
        except Exception as e:
            print(f"Erreur capture Last War: {e}")
            
        return None
    
    def capture(self):
        """Point d'entrée principal pour la capture"""
        start_time = time.time()
        self.stats['total_attempts'] += 1
        
        if not self.hwnd and not self.find_window():
            return None
            
        # Méthode spéciale pour Last War
        if "last war" in self.window_title.lower():
            img = self.capture_lastwar_optimized()
        else:
            img = self.capture_standard()
            
        if img is not None:
            self.stats['successful_captures'] += 1
            duration = (time.time() - start_time) * 1000
            self.stats['avg_time_ms'] = (
                (self.stats['avg_time_ms'] * (self.stats['successful_captures'] - 1) + duration) 
                / self.stats['successful_captures']
            )
            
        return img
    
    def capture_standard(self):
        """Capture standard pour autres fenêtres"""
        # Implementation simplifiée du capture standard
        try:
            rect = win32gui.GetWindowRect(self.hwnd)
            width, height = rect[2] - rect[0], rect[3] - rect[1]
            
            hwndDC = win32gui.GetWindowDC(self.hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            result = windll.user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 0)
            
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
                
                return img
                
        except Exception as e:
            print(f"Erreur capture standard: {e}")
            
        return None

class CaptureManager:
    """Gestionnaire de captures multiples"""
    
    def __init__(self):
        self.capturers = {}
        
    def add_source(self, source_name, window_title):
        """Ajoute une source de capture"""
        self.capturers[source_name] = WindowCapture(window_title)
        
    def capture_source(self, source_name):
        """Capture une source spécifique"""
        if source_name in self.capturers:
            return self.capturers[source_name].capture()
        return None
        
    def get_statistics(self):
        """Retourne les statistiques de toutes les captures"""
        stats = {}
        for source_name, capturer in self.capturers.items():
            stats[source_name] = capturer.stats
        return stats

# Instance globale
capture_manager = CaptureManager()
