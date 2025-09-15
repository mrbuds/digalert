# -*- coding: utf-8 -*-
"""
Script de démarrage pour Last War Alerts
Valide la configuration et démarre l'application
"""

import os
import sys
import time
from pathlib import Path

def check_python_version():
    """Vérifie que Python 3.8+ est utilisé"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 ou supérieur requis")
        print(f"Version actuelle: {sys.version}")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    return True

def check_dependencies():
    """Vérifie que toutes les dépendances sont installées"""
    required_packages = [
        ('cv2', 'opencv-python'),
        ('numpy', 'numpy'),
        ('obswebsocket', 'obs-websocket-py'),
        ('win10toast', 'win10toast'),
        ('pytesseract', 'pytesseract'),
        ('flask', 'flask'),
        ('pygetwindow', 'pygetwindow'),
        ('win32gui', 'pywin32')
    ]
    
    missing_packages = []
    
    for package, pip_name in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} (manquant)")
            missing_packages.append(pip_name)
    
    if missing_packages:
        print(f"\n🔧 Pour installer les dépendances manquantes:")
        print(f"pip install {' '.join(missing_packages)}")
        return False
    
    return True

def check_tesseract():
    """Vérifie que Tesseract OCR est installé"""
    tesseract_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        'tesseract'  # Dans le PATH
    ]
    
    for path in tesseract_paths:
        if os.path.exists(path) or path == 'tesseract':
            try:
                import pytesseract
                if path != 'tesseract':
                    pytesseract.pytesseract.tesseract_cmd = path
                
                # Test basique
                pytesseract.get_tesseract_version()
                print(f"✅ Tesseract OCR trouvé: {path}")
                return True
            except:
                continue
    
    print("❌ Tesseract OCR non trouvé")
    print("📥 Téléchargez depuis: https://github.com/UB-Mannheim/tesseract/wiki")
    return False

def create_directory_structure():
    """Crée la structure de dossiers nécessaire"""
    directories = [
        'templates',
        'static',
        'static/screenshots', 
        'logs',
        'debug_screenshots',
        'statistics'
    ]
    
    created = []
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            if not os.path.exists(directory):
                created.append(directory)
            print(f"📁 {directory}")
        except Exception as e:
            print(f"❌ Erreur création {directory}: {e}")
            return False
    
    if created:
        print(f"✅ Dossiers créés: {', '.join(created)}")
    
    return True

def check_template_file():
    """Vérifie que le template HTML existe"""
    template_path = 'templates/index.html'
    
    if os.path.exists(template_path):
        print("✅ Template HTML trouvé")
        return True
    
    print(f"⚠️ Template HTML manquant: {template_path}")
    print("🔧 Le fichier index.html doit être placé dans le dossier templates/")
    return False

def check_alert_images():
    """Vérifie que les images d'alerte existent"""
    try:
        from config import ALERTS
    except ImportError:
        print("❌ Impossible d'importer config.py")
        return False
    
    missing_images = []
    
    for alert in ALERTS:
        if 'img' in alert:
            img_path = alert['img']
            if os.path.exists(img_path):
                print(f"✅ {img_path}")
            else:
                print(f"❌ {img_path} (manquant)")
                missing_images.append(img_path)
    
    if missing_images:
        print(f"\n🖼️ Images manquantes: {', '.join(missing_images)}")
        print("Placez vos images de référence dans le dossier racine")
        return False
    
    return True

def validate_configuration():
    """Valide la configuration complète"""
    try:
        from config import validate_configuration
        valid, errors, warnings = validate_configuration()
        
        if errors:
            print("❌ Erreurs de configuration:")
            for error in errors:
                print(f"   - {error}")
        
        if warnings:
            print("⚠️ Avertissements:")
            for warning in warnings:
                print(f"   - {warning}")
        
        if valid:
            print("✅ Configuration validée")
        
        return valid
    except Exception as e:
        print(f"❌ Erreur validation config: {e}")
        return False

def check_obs_connection():
    """Teste la connexion OBS (optionnel)"""
    try:
        from obswebsocket import obsws
        from config import OBS_WS_HOST, OBS_WS_PORT, OBS_WS_PASSWORD
        
        print("🔗 Test connexion OBS...")
        ws = obsws(OBS_WS_HOST, OBS_WS_PORT, OBS_WS_PASSWORD)
        ws.connect()
        ws.disconnect()
        print("✅ Connexion OBS réussie")
        return True
    except Exception as e:
        print(f"⚠️ Connexion OBS échouée: {e}")
        print("   Assurez-vous qu'OBS est ouvert avec WebSocket activé")
        return False

def show_startup_info():
    """Affiche les informations de démarrage"""
    print("=" * 60)
    print("🎮 LAST WAR ALERTS - VALIDATION DU SYSTÈME")
    print("=" * 60)

def show_summary(all_checks_passed):
    """Affiche le résumé final"""
    print("\n" + "=" * 60)
    
    if all_checks_passed:
        print("✅ SYSTÈME PRÊT")
        print("\n🚀 Pour démarrer l'application:")
        print("   python main.py")
        print("\n🌐 Interface web sera disponible sur:")
        print("   http://localhost:5000")
    else:
        print("❌ SYSTÈME NON PRÊT")
        print("\n🔧 Corrigez les erreurs ci-dessus avant de continuer")
        print("\n📚 Consultez le README.md pour l'aide")
    
    print("=" * 60)

def main():
    """Fonction principale de validation"""
    show_startup_info()
    
    checks = [
        ("Version Python", check_python_version),
        ("Dépendances", check_dependencies),
        ("Tesseract OCR", check_tesseract),
        ("Structure dossiers", create_directory_structure),
        ("Template HTML", check_template_file),
        ("Images d'alerte", check_alert_images),
        ("Configuration", validate_configuration),
    ]
    
    results = []
    
    for check_name, check_func in checks:
        print(f"\n📋 Vérification: {check_name}")
        try:
            result = check_func()
            results.append(result)
        except Exception as e:
            print(f"❌ Erreur lors de {check_name}: {e}")
            results.append(False)
    
    # Test OBS optionnel (n'affecte pas le résultat final)
    print(f"\n📋 Vérification optionnelle: Connexion OBS")
    check_obs_connection()
    
    all_checks_passed = all(results)
    show_summary(all_checks_passed)
    
    if all_checks_passed:
        response = input("\n🚀 Démarrer l'application maintenant? (o/n): ")
        if response.lower() in ['o', 'oui', 'y', 'yes']:
            print("\n🎯 Démarrage de Last War Alerts...")
            time.sleep(1)
            
            try:
                # Import et démarrage de l'application
                from main import main as start_app
                start_app()
            except KeyboardInterrupt:
                print("\n👋 Application arrêtée par l'utilisateur")
            except Exception as e:
                print(f"\n❌ Erreur démarrage: {e}")
    else:
        input("\nAppuyez sur Entrée pour quitter...")

if __name__ == "__main__":
    main()