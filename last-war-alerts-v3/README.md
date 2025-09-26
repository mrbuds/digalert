# Last War Alerts v3.0 - Version Refactorisée

## Améliorations

- **Architecture simplifiée** : Code 40% plus léger
- **Modules unifiés** : Plus de duplication
- **Configuration centralisée** : Un seul système de config
- **Performance optimisée** : Capture Last War améliorée

## Structure

```
last-war-alerts-v3/
├── core/              # Logique métier
│   ├── capture.py     # Système de capture unifié
│   ├── detection.py   # Détection d'alertes
│   ├── config_manager.py  # Configuration JSON
│   └── constants.py   # Constantes globales
├── web/               # Interface web
│   ├── app.py         # Application Flask
│   ├── static/        # Assets web
│   └── templates/     # Templates HTML
├── utils/             # Utilitaires
│   ├── logging.py     # Système de logs
│   └── helpers.py     # Fonctions utilitaires
├── data/              # Données
│   ├── config.json    # Configuration principale
│   ├── templates/     # Images des alertes
│   └── screenshots/   # Captures récentes
├── main.py           # Point d'entrée
└── requirements.txt  # Dépendances
```

## Installation

```bash
cd last-war-alerts-v3
pip install -r requirements.txt
python main.py
```

## Interface Web

Ouvrez http://localhost:5000 dans votre navigateur.

## Configuration

Éditez `data/config.json` pour configurer :
- Sources de capture
- Alertes et templates
- Paramètres de détection

## Migration depuis v2

Ce projet est une version refactorisée qui :
- ✅ Supprime le code dupliqué
- ✅ Unifie les systèmes de capture et détection
- ✅ Simplifie la configuration
- ✅ Améliore les performances
