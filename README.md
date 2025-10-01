# 🎮 Last War Alerts - Système de Détection v2.1

Un système avancé de détection d'alertes pour le jeu Last War, avec capture directe (sans OBS), interface web complète et gestion de configuration intégrée.

## ✨ Nouveautés v2.1

### 🌐 Interface Web Complète
- **Configuration complète depuis l'interface** : Créez, modifiez et supprimez alertes, templates et sources directement
- **Gestion des alertes** : Nom, seuil, cooldown, activation/désactivation
- **Gestion des templates** : Import multiple, édition des seuils, statistiques de performance
- **Gestion des sources** : Ajout, modification, suppression des fenêtres à surveiller
- **Import/Export** : Sauvegardez et partagez vos configurations

### 🎯 Améliorations de Détection
- Capture directe sans OBS (méthode OBS moderne pour Last War)
- Support multi-fenêtres avec capture même minimisées
- Templates multiples par alerte pour meilleure détection
- Statistiques détaillées par template

### 📊 Interface Améliorée
- Dashboard temps réel avec screenshots
- Historique des alertes avec captures
- Statistiques de performance
- Mode pause/reprise

## 📋 Prérequis

### Logiciels Requis
1. **Python 3.8+**
2. **Tesseract OCR** ([Télécharger ici](https://github.com/UB-Mannheim/tesseract/wiki))

### Pas besoin d'OBS !
Le système utilise maintenant la capture directe des fenêtres.

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
### 3. Lancer l'application
```bash
python main.py
```