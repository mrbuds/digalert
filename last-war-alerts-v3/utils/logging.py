# -*- coding: utf-8 -*-
"""
Système de logging unifié
Extrait et simplifié de utils.py
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logging(level="INFO", log_to_file=True, log_file="data/logs/app.log"):
    """Configure le système de logging"""
    
    # Créer le dossier de logs
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger('LastWarAlerts')
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    if log_to_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=3
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    return logger

def get_logger(name=None):
    """Retourne un logger configuré"""
    return logging.getLogger(name or 'LastWarAlerts')
