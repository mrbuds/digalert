# -*- coding: utf-8 -*-
"""
Fonctions utilitaires générales
Extraites et simplifiées de utils.py
"""

import time
from datetime import datetime, timedelta

def format_duration(seconds):
    """Formate une durée en format lisible"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{int(minutes)}m {seconds:.0f}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{int(hours)}h {int(minutes)}m"

def safe_divide(a, b, default=0):
    """Division sécurisée"""
    return a / b if b != 0 else default

def get_relative_time(timestamp_str):
    """Convertit un timestamp en temps relatif"""
    if not timestamp_str:
        return 'Jamais'
        
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.now(timestamp.tzinfo)
        diff = now - timestamp
        
        if diff.total_seconds() < 60:
            return f"{int(diff.total_seconds())}s"
        elif diff.total_seconds() < 3600:
            return f"{int(diff.total_seconds() // 60)}min"
        else:
            return f"{int(diff.total_seconds() // 3600)}h"
    except:
        return timestamp_str
