# 🎮 Last War Alerts - Système de Détection v2.0

Un système avancé de détection d'alertes pour le jeu Last War, capable de surveiller plusieurs fenêtres simultanément via OBS WebSocket et d'envoyer des notifications Windows.

## ✨ Fonctionnalités

### 🎯 Détection Multi-Méthode
- **Template Matching**: Détection par image avec échelle adaptative
- **OCR**: Reconnaissance de texte avec Tesseract
- **Multi-échelle**: Support automatique des différentes tailles d'interface

### 📢 Notifications Intelligentes
- **Queue de notifications**: Évite le spam et respecte les limitations Windows
- **Cooldown adaptatif**: Délais personnalisables par source
- **Retry automatique**: Gestion des échecs d'envoi

### 📊 Interface Web Moderne
- **Dashboard temps réel**: Interface web avec Bootstrap 5
- **Screenshots automatiques**: Capture et affichage des zones détectées
- **Statistiques détaillées**: Performance, taux de succès, historique

### 🛠️ Récupération d'Erreurs
- **Reconnexion OBS**: Automatique en cas de déconnexion
- **Retry intelligent**: Tentatives multiples avec backoff exponentiel
- **Logs détaillés**: Système de logging avec rotation de fichiers

## 📋 Prérequis

### Logiciels Requis
1. **Python 3.8+**
2. **OBS Studio** avec WebSocket activé (port 4455)
3. **Tesseract OCR** ([Télécharger ici](https://github.com/UB-Mannheim/tesseract/wiki))

### Configuration OBS
1. Ouvrir OBS Studio
2. Aller dans `Outils > obs-websocket Settings`
3. Activer le serveur sur le port `4455`
4. Définir un mot de passe (optionnel)

## 🚀 Installation Rapide

### 1. Télécharger le projet
```bash
git clone https://github.com/votre-repo/last-war-alerts.git
cd last-war-alerts
```

### 2. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 3. Validation automatique
```bash
python startup.py
```
Ce script vérifiera automatiquement :
- ✅ Version de Python
- ✅ Dépendances installées
- ✅ Tesseract OCR
- ✅ Structure des dossiers
- ✅ Configuration

### 4. Placer vos images de référence
Copiez vos images PNG dans le dossier racine :
- `DIG.png`
- `egg.png`

### 5. Lancer l'application
```bash
python main.py
```

## 🌐 Interface Web

Une fois démarré, l'interface web est accessible sur :
**http://localhost:5000**

### Fonctionnalités Web
- 📊 Statistiques temps réel
- 📸 Screenshots avec zones de détection
- 🔔 Historique des alertes
- ⚙️ Réinitialisation des stats
- 📱 Interface responsive

## ⚙️ Configuration

### Fichier `config.py`

#### Configuration des Fenêtres
```python
SOURCE_WINDOWS = [
    {
        "source_name": "last war!",           # Nom de la source OBS
        "window_title": "Last War-Survival Game",  # Titre de la fenêtre
        "notification_cooldown": 30,          # Délai entre notifications (secondes)
        "priority": 1                         # Priorité (1=haute, 2=normale)
    }
]
```

#### Configuration des Alertes
```python
ALERTS = [
    {
        "img": "DIG.png",                     # Image de référence
        "name": "Dig!",                       # Nom de l'alerte
        "threshold": 0.7,                     # Seuil de confiance (0.0-1.0)
        "debug": False,                       # Mode debug
        "priority": "high",                   # Priorité
        "enabled": True                       # Activer/désactiver
    }
]
```

## 🔧 Dépannage

### Problèmes Fréquents

#### 1. "Impossible de capturer la fenêtre"
**Solutions:**
- Vérifier qu'OBS est ouvert
- Contrôler le nom de la source dans OBS
- S'assurer que la fenêtre n'est pas minimisée

#### 2. "Tesseract non trouvé"
**Solutions:**
```bash
# Installer Tesseract depuis le site officiel
# Puis ajouter au PATH ou modifier config.py :
pytesseract.pytesseract.tesseract_cmd = r'C:\Chemin\vers\tesseract.exe'
```

#### 3. "Template non trouvé"
**Solutions:**
- Vérifier que les fichiers PNG sont dans le dossier racine
- Contrôler les noms de fichiers dans `config.py`
- Utiliser des images haute qualité

#### 4. Interface web inaccessible
**Solutions:**
- Vérifier que le port 5000 n'est pas utilisé
- Contrôler les logs pour les erreurs Flask
- Essayer un autre port dans `webapp.py`

### Mode Debug

#### Activation du Debug
```python
# Dans config.py
DEBUG_SAVE_SCREENSHOTS = True      # Sauvegarde des captures
DEBUG_SCREENSHOT_PATH = "debug/"   # Dossier de debug
DEBUG_SHOW_DETECTION_AREAS = True  # Affichage des zones détectées
```

#### Logs Détaillés
```python
# Dans config.py
LOG_LEVEL = "DEBUG"  # Plus de détails dans les logs
```

## 📊 Optimisation

### Amélioration des Performances

#### 1. Ajustement des Intervalles
```python
# Pour plus de réactivité (consomme plus de CPU)
CHECK_INTERVAL = 1

# Pour économiser les ressources
CHECK_INTERVAL = 3
```

#### 2. Optimisation des Seuils
```python
# Seuils recommandés par type d'image
"threshold": 0.8  # Images très distinctives
"threshold": 0.6  # Images avec variations
"threshold": 0.4  # Images difficiles à détecter
```

#### 3. Configuration Multi-Sources
```python
# Pour 3+ fenêtres simultanées
CHECK_INTERVAL = 3  # Plus long pour éviter surcharge
COOLDOWN_PERIOD = 45  # Éviter spam notifications
```

## 📁 Structure du Projet

```
last-war-alerts/
├── main.py              # Point d'entrée principal
├── config.py            # Configuration centrale
├── capture.py           # Gestion des captures d'écran
├── detection.py         # Algorithmes de détection
├── webapp.py            # Interface web Flask
├── utils.py             # Utilitaires et logging
├── startup.py           # Script de validation
├── requirements.txt     # Dépendances Python
├── README.md           # Documentation
├── DIG.png             # Images de référence
├── egg.png             
├── templates/           # Templates HTML
│   └── index.html
├── static/             # Fichiers statiques web
│   └── screenshots/    # Screenshots automatiques
├── logs/               # Fichiers de logs
├── debug_screenshots/  # Captures de debug
└── statistics/         # Statistiques sauvegardées
```

## 🚨 Détection d'Écran Noir

Le système détecte automatiquement les écrans noirs et envoie des notifications :
- 🔍 Analyse de la luminosité moyenne
- ⏰ Cooldown de 60 secondes entre notifications
- 📸 Screenshots automatiques pour debug

## 📈 Statistiques et Monitoring

### Métriques Suivies
- ✅ Taux de succès des captures
- ⚡ Temps de réponse moyen
- 🎯 Confiance des détections
- 📊 Historique des alertes
- 🔄 Reconnexions OBS

### Sauvegarde Automatique
- 💾 Statistiques sauvées toutes les 5 minutes
- 📄 Format JSON pour analyse
- 🔄 Historique sur 24h

## 🔄 Mise à Jour

### Validation après modification
```bash
python startup.py  # Valide la configuration
python config.py   # Test direct de config
```

### Réinitialisation
```bash
# Via interface web : bouton "Réinitialiser"
# Ou redémarrer l'application
```

## 🛡️ Sécurité

### Bonnes Pratiques
- 🔒 Pas de mots de passe en dur
- 📁 Permissions limitées sur les dossiers
- 🌐 Interface web accessible uniquement en local
- 📝 Logs rotatifs pour éviter l'accumulation

## ⚠️ Limitations

- Windows uniquement (dépendances win32)
- Nécessite OBS Studio en fonctionnement
- Performance dépendante de la qualité des images de référence
- Interface web non sécurisée (usage local uniquement)

## 🤝 Contribution

### Signaler un Bug
1. Activer le mode debug
2. Reproduire le problème
3. Collecter les logs et captures debug
4. Créer une issue avec les détails

### Développement
```bash
# Tests de validation
python startup.py

# Tests de performance
python -c "from detection import benchmark_detection_methods; print('Tests OK')"
```

## 📄 Licence

MIT License - Voir le fichier LICENSE pour les détails.

## 🆘 Support

### Logs Utiles
```bash
# Logs principaux
./logs/last_war_alerts.log

# Statistiques temps réel  
./alert_statistics.json

# Captures de debug
./debug_screenshots/
```

### Validation Système
```bash
python startup.py  # Diagnostic complet
```

### Contact
- 📧 Issues GitHub pour les bugs
- 📚 Consultez ce README pour la documentation
- 🔧 Mode debug pour les problèmes techniques

---

**Développé avec ❤️ pour la communauté Last War**

## 🚀 Démarrage Rapide (Résumé)

1. `pip install -r requirements.txt`
2. Installer Tesseract OCR
3. `python startup.py` (validation)
4. Placer images DIG.png et egg.png
5. Configurer OBS WebSocket (port 4455)
6. `python main.py`
7. Ouvrir http://localhost:5000

✨ **Prêt à détecter !**