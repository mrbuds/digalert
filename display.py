# -*- coding: utf-8 -*-
import os
import time
import shutil
from datetime import datetime, timedelta
from utils import (format_duration, format_percentage, create_progress_bar, 
                  colorize_text, get_memory_usage, safe_divide, truncate_string)
from config import CONSOLE_WIDTH, COLORS, SHOW_PERFORMANCE_STATS, SHOW_CONFIDENCE_HISTORY

def clear_console():
    """Fonction compatible Windows et Linux/Mac"""
    os.system('cls' if os.name == 'nt' else 'clear')


def get_display_length(text):
    """Calcule la longueur d'affichage réelle d'un texte avec codes couleur et emojis"""
    import re
    
    # Vérifier si le texte est None ou vide
    if text is None:
        return 0
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    
    # Supprimer les codes couleur ANSI
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)
    
    # Compter la largeur réelle en tenant compte des emojis
    display_width = 0
    for char in clean_text:
        char_code = ord(char)
        # Détection des emojis et caractères large
        if (char_code >= 0x1F300 and char_code <= 0x1F9FF) or \
           (char_code >= 0x2600 and char_code <= 0x26FF) or \
           (char_code >= 0x2700 and char_code <= 0x27BF) or \
           char in ['✅', '🚨', '⚠️', '🎯', '📊', '⏱️', '🔄', '🔌', '💾']:
            display_width += 2  # Les emojis prennent 2 positions
        else:
            display_width += 1  # Caractère normal
    
    return display_width


def simple_pad_text(text, width, align='left'):
    """Version simplifiée du padding plus fiable"""
    if text is None:
        text = ""
    if not isinstance(text, str):
        text = str(text)
    
    # Pour les textes avec couleurs, on utilise une approche plus conservative
    display_len = get_display_length(text)
    
    # Si le texte est trop long, le tronquer
    if display_len > width:
        # Tronquer en gardant les codes couleur à la fin
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_text = ansi_escape.sub('', text)
        if len(clean_text) > width:
            # Trouver la position de coupure
            truncated = clean_text[:width-1]
            return truncated + "…"
        return text
    
    padding_needed = width - display_len
    if padding_needed <= 0:
        return text
    
    if align == 'left':
        return text + ' ' * padding_needed
    elif align == 'right':
        return ' ' * padding_needed + text
    else:  # center
        left_pad = padding_needed // 2
        right_pad = padding_needed - left_pad
        return ' ' * left_pad + text + ' ' * right_pad


def pad_text_to_width(text, width, align='left'):
    """Fonction de compatibilité - utilise simple_pad_text"""
    return simple_pad_text(text, width, align)
    """Calcule la longueur d'affichage réelle d'un texte avec codes couleur et emojis"""
    import re
    
    # Vérifier si le texte est None ou vide
    if text is None:
        return 0
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    
    # Supprimer les codes couleur ANSI
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)
    
    # Compter les caractères en tenant compte des emojis
    # Les emojis comptent souvent pour 2 caractères d'affichage
    emoji_count = 0
    try:
        for char in clean_text:
            # Détection basique des emojis (code Unicode > 1F000)
            if ord(char) > 0x1F000:
                emoji_count += 1
    except (TypeError, ValueError):
        # En cas d'erreur Unicode, ignorer les emojis
        emoji_count = 0
    
    # Longueur d'affichage = longueur du texte nettoyé + largeur extra des emojis
    display_length = len(clean_text) + emoji_count
    return display_length


def get_display_length(text):
    """Calcule la longueur d'affichage réelle d'un texte avec codes couleur et emojis"""
    import re
    
    # Vérifier si le texte est None ou vide
    if text is None:
        return 0
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    
    # Supprimer les codes couleur ANSI
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean_text = ansi_escape.sub('', text)
    
    # Compter la largeur réelle en tenant compte des emojis
    display_width = 0
    for char in clean_text:
        char_code = ord(char)
        # Détection des emojis et caractères large
        if (char_code >= 0x1F300 and char_code <= 0x1F9FF) or \
           (char_code >= 0x2600 and char_code <= 0x26FF) or \
           (char_code >= 0x2700 and char_code <= 0x27BF) or \
           char in ['✅', '🚨', '⚠️', '🎯', '📊', '⏱️', '🔄', '🔌', '💾']:
            display_width += 2  # Les emojis prennent 2 positions
        else:
            display_width += 1  # Caractère normal
    
    return display_width


def render_window_row_simple(source_name, state, col_widths):
    """Version simplifiée de l'affichage des lignes avec gestion emoji correcte"""
    
    # Sécurité
    if source_name is None:
        source_name = "Inconnu"
    if state is None:
        state = {}
    
    # Préparation des données SANS couleurs d'abord
    last_capture = state.get("last_capture_time", "Jamais")
    if last_capture and last_capture != "Jamais":
        try:
            capture_time = datetime.strptime(last_capture, "%Y-%m-%d %H:%M:%S")
            time_ago = datetime.now() - capture_time
            if time_ago.total_seconds() < 60:
                last_capture = f"{int(time_ago.total_seconds())}s"
            elif time_ago.total_seconds() < 3600:
                last_capture = f"{int(time_ago.total_seconds() // 60)}min"
            else:
                last_capture = f"{int(time_ago.total_seconds() // 3600)}h"
        except:
            last_capture = "Erreur"
    elif not last_capture:
        last_capture = "Jamais"
    
    # Statut - SANS emoji d'abord, puis ajout de couleur
    alert_state = state.get("last_alert_state", False)
    consecutive_failures = state.get("consecutive_failures", 0)
    
    if consecutive_failures >= 5:
        status_text = "ERREUR"
        status_emoji = "⚠️ "
    elif alert_state:
        status_text = "ALERTE"
        status_emoji = "🚨 "
    elif consecutive_failures > 0:
        status_text = "Instable"
        status_emoji = "⚠️ "
    else:
        status_text = "OK"
        status_emoji = "✅ "
    
    # Calcul précis pour la colonne statut
    status_display_text = status_emoji + status_text
    status_width_needed = get_display_length(status_display_text)
    
    # Dernière alerte
    last_alert = state.get("last_alert_name")
    if not last_alert or last_alert == "Aucune":
        last_alert = "─"
    else:
        last_alert = str(last_alert)[:col_widths[3]-1]
    
    # Confiance
    confidence = state.get("last_confidence", 0.0)
    confidence_text = f"{confidence:.1%}"
    
    # Statistiques
    total_detections = state.get("total_detections", 0)
    total_captures = state.get("total_captures", 0)
    successful_captures = state.get("successful_captures", 0)
    error_count = state.get("error_count", 0)
    
    success_rate = safe_divide(successful_captures, total_captures, 0) * 100
    success_text = f"{success_rate:.0f}%"
    
    # Construction de la ligne avec padding manuel précis
    parts = []
    
    # Colonne 1: Source (simple)
    source_trunc = str(source_name)[:col_widths[0]]
    parts.append(source_trunc.ljust(col_widths[0]))
    
    # Colonne 2: Statut (avec emoji - CRITIQUE)
    # Calculer le padding nécessaire en tenant compte de la largeur réelle
    padding_needed = col_widths[1] - status_width_needed
    if padding_needed > 0:
        status_padded = status_display_text + (' ' * padding_needed)
    else:
        # Si trop long, tronquer sans casser l'emoji
        status_padded = status_text[:col_widths[1]]
    
    # Ajouter les couleurs APRÈS le padding
    if consecutive_failures >= 5 or alert_state:
        status_final = colorize_text(status_padded, 'RED')
    elif consecutive_failures > 0:
        status_final = colorize_text(status_padded, 'YELLOW')
    else:
        status_final = colorize_text(status_padded, 'GREEN')
    
    parts.append(status_final)
    
    # Colonne 3: Dernière capture
    capture_trunc = str(last_capture)[:col_widths[2]]
    parts.append(capture_trunc.ljust(col_widths[2]))
    
    # Colonne 4: Alerte
    alert_padded = str(last_alert).ljust(col_widths[3])
    if last_alert != "─":
        alert_final = colorize_text(alert_padded, 'YELLOW')
    else:
        alert_final = colorize_text(alert_padded, 'CYAN')
    parts.append(alert_final)
    
    # Colonne 5: Confiance (alignée à droite)
    conf_padded = confidence_text.rjust(col_widths[4])
    if confidence >= 0.8:
        conf_final = colorize_text(conf_padded, 'GREEN')
    elif confidence >= 0.5:
        conf_final = colorize_text(conf_padded, 'YELLOW')
    else:
        conf_final = colorize_text(conf_padded, 'RED')
    parts.append(conf_final)
    
    # Colonne 6: Détections (alignée à droite)
    parts.append(str(total_detections).rjust(col_widths[5]))
    
    # Colonne 7: Succès (alignée à droite)
    success_padded = success_text.rjust(col_widths[6])
    if success_rate >= 90:
        success_final = colorize_text(success_padded, 'GREEN')
    elif success_rate >= 70:
        success_final = colorize_text(success_padded, 'YELLOW')
    else:
        success_final = colorize_text(success_padded, 'RED')
    parts.append(success_final)
    
    # Colonne 8: Erreurs (alignée à droite)
    error_padded = str(error_count).rjust(col_widths[7])
    if error_count > 0:
        error_final = colorize_text(error_padded, 'RED')
    else:
        error_final = error_padded
    parts.append(error_final)
    
    # Assemblage final
    try:
        row = " │ ".join(parts)
        print(row)
    except Exception as e:
        # Fallback ultra-simple
        print(f"{source_name} | {status_text} | {last_capture} | {last_alert} | {confidence_text}")
    """Récupère la taille du terminal"""
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except:
        return CONSOLE_WIDTH, 50  # Valeurs par défaut


def get_terminal_size():
    """Récupère la taille du terminal"""
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except:
        return CONSOLE_WIDTH, 50  # Valeurs par défaut


def render_enhanced_table(windows_state, global_stats):
    """
    Affichage amélioré avec statistiques détaillées et couleurs
    """
    clear_console()
    
    # Récupération de la taille du terminal
    terminal_width, terminal_height = get_terminal_size()
    width = min(terminal_width - 2, CONSOLE_WIDTH)
    
    # En-tête avec informations globales
    render_header(global_stats, width)
    
    # Tableau principal des fenêtres avec alignement corrigé
    render_windows_table_aligned(windows_state, width)
    
    # Statistiques de performance si activées
    if SHOW_PERFORMANCE_STATS:
        render_performance_stats(windows_state, width)
    
    # Historique de confiance si activé
    if SHOW_CONFIDENCE_HISTORY:
        render_confidence_history(windows_state, width)
    
    # Pied de page avec contrôles
    render_footer(width)


def render_windows_table_aligned(windows_state, width):
    """Affiche le tableau principal avec alignement parfait - version simplifiée"""
    
    if not windows_state:
        print("Aucune fenêtre configurée".center(width))
        return
    
    # En-têtes du tableau
    headers = [
        "Source", "Statut", "Dernière capture", "Alerte", 
        "Confiance", "Détections", "Succès", "Erreurs"
    ]
    
    # Largeurs fixes testées et ajustées
    col_widths = [12, 10, 16, 15, 11, 11, 8, 8]
    
    # Vérifier que la largeur totale ne dépasse pas l'écran
    total_needed = sum(col_widths) + (len(headers) - 1) * 3  # 3 pour " │ "
    if total_needed > width:
        # Réduction proportionnelle simple
        factor = (width - (len(headers) - 1) * 3) / sum(col_widths) * 0.95  # 5% de marge
        col_widths = [max(6, int(w * factor)) for w in col_widths]
    
    # En-tête avec alignement simple
    header_parts = []
    for i, header in enumerate(headers):
        # Pas de couleur dans les en-têtes pour éviter les problèmes
        padded = header.ljust(col_widths[i])[:col_widths[i]]
        header_parts.append(padded)
    
    print("─" * width)
    print(" │ ".join(header_parts))
    print("─" * width)
    
    # Lignes de données
    for source_name, state in windows_state.items():
        render_window_row_simple(source_name, state, col_widths)
    
    print("─" * width)
    """Affiche le tableau principal avec alignement parfait"""
    
    if not windows_state:
        print("Aucune fenêtre configurée".center(width))
        return
    
    # En-têtes du tableau
    headers = [
        "Source", "Statut", "Dernière capture", "Alerte", 
        "Confiance", "Détections", "Succès", "Erreurs"
    ]
    
    # Calcul des largeurs de colonnes
    col_widths = [15, 12, 16, 18, 10, 11, 8, 8]  # Largeurs fixes optimisées
    
    # Ajustement si la largeur totale dépasse l'écran
    total_width_needed = sum(col_widths) + (len(headers) - 1) * 3  # 3 pour " │ "
    if total_width_needed > width:
        # Réduction proportionnelle
        reduction_factor = (width - (len(headers) - 1) * 3) / sum(col_widths)
        col_widths = [max(8, int(w * reduction_factor)) for w in col_widths]
    
    # Ligne d'en-tête avec padding correct
    header_parts = []
    for i, header in enumerate(headers):
        padded_header = pad_text_to_width(colorize_text(header, 'BOLD'), col_widths[i])
        header_parts.append(padded_header)
    
    header_line = " │ ".join(header_parts)
    print(header_line)
    
    # Ligne de séparation avec largeurs correctes
    sep_parts = []
    for w in col_widths:
        sep_parts.append("─" * w)
    sep_line = "─┼─".join(sep_parts)
    print(sep_line)
    
    # Lignes de données avec alignement parfait
    for source_name, state in windows_state.items():
        render_window_row_aligned(source_name, state, col_widths)


def render_window_row_aligned(source_name, state, col_widths):
    """Affiche une ligne du tableau avec alignement parfait"""
    
    # Vérifications de sécurité pour éviter les erreurs None
    if source_name is None:
        source_name = "Inconnu"
    if state is None:
        state = {}
    
    # Préparation des données (même logique qu'avant)
    last_capture = state.get("last_capture_time", "Jamais")
    if last_capture and last_capture != "Jamais":
        try:
            capture_time = datetime.strptime(last_capture, "%Y-%m-%d %H:%M:%S")
            time_ago = datetime.now() - capture_time
            if time_ago.total_seconds() < 60:
                last_capture = f"{int(time_ago.total_seconds())}s"
            elif time_ago.total_seconds() < 3600:
                last_capture = f"{int(time_ago.total_seconds() // 60)}min"
            else:
                last_capture = f"{int(time_ago.total_seconds() // 3600)}h"
        except (ValueError, TypeError):
            last_capture = "Erreur"
    elif not last_capture:
        last_capture = "Jamais"
    
    # Statut avec couleur
    alert_state = state.get("last_alert_state", False)
    consecutive_failures = state.get("consecutive_failures", 0)
    
    try:
        if consecutive_failures >= 5:
            status = colorize_text("⚠️ ERREUR", 'RED')
        elif alert_state:
            status = colorize_text("🚨 ALERTE", 'RED')
        elif consecutive_failures > 0:
            status = colorize_text("⚠️ Instable", 'YELLOW')
        else:
            status = colorize_text("✅ OK", 'GREEN')
    except Exception:
        status = "ERREUR"
    
    # Dernière alerte
    last_alert = state.get("last_alert_name")
    if not last_alert or last_alert == "Aucune":
        last_alert = colorize_text("─", 'CYAN')
    else:
        try:
            last_alert = colorize_text(truncate_string(str(last_alert), col_widths[3]-2), 'YELLOW')
        except Exception:
            last_alert = str(last_alert)[:col_widths[3]-2] if last_alert else "─"
    
    # Confiance avec couleur selon le niveau
    confidence = state.get("last_confidence", 0.0)
    try:
        confidence_text = f"{confidence:.1%}"
        if confidence >= 0.8:
            confidence_text = colorize_text(confidence_text, 'GREEN')
        elif confidence >= 0.5:
            confidence_text = colorize_text(confidence_text, 'YELLOW')
        else:
            confidence_text = colorize_text(confidence_text, 'RED')
    except (ValueError, TypeError):
        confidence_text = "0.0%"
    
    # Statistiques
    total_detections = state.get("total_detections", 0)
    total_captures = state.get("total_captures", 0)
    successful_captures = state.get("successful_captures", 0)
    error_count = state.get("error_count", 0)
    
    try:
        success_rate = safe_divide(successful_captures, total_captures, 0) * 100
        success_text = f"{success_rate:.0f}%"
        if success_rate >= 90:
            success_text = colorize_text(success_text, 'GREEN')
        elif success_rate >= 70:
            success_text = colorize_text(success_text, 'YELLOW')
        else:
            success_text = colorize_text(success_text, 'RED')
    except Exception:
        success_text = "0%"
    
    try:
        error_text = colorize_text(str(error_count), 'RED') if error_count > 0 else '0'
    except Exception:
        error_text = '0'
    
    # Construction de la ligne avec padding exact
    row_data = [
        truncate_string(str(source_name), col_widths[0]-1) if source_name else "Inconnu",
        status,
        str(last_capture) if last_capture else "Jamais",
        last_alert,
        confidence_text,
        str(total_detections),
        success_text,
        error_text
    ]
    
    # Application du padding pour chaque colonne avec gestion d'erreur
    row_parts = []
    for i, data in enumerate(row_data):
        try:
            align = 'right' if i in [4, 5, 6, 7] else 'left'  # Colonnes numériques à droite
            padded_data = pad_text_to_width(data, col_widths[i], align)
            row_parts.append(padded_data)
        except Exception as e:
            # En cas d'erreur, utiliser un padding simple
            if data is None:
                data = ""
            row_parts.append(str(data)[:col_widths[i]].ljust(col_widths[i]))
    
    try:
        row_line = " │ ".join(row_parts)
        print(row_line)
    except Exception as e:
        # Fallback en cas d'erreur d'affichage
        fallback_line = f"{source_name} | Erreur d'affichage: {str(e)[:50]}"
        print(fallback_line[:80])  # Limité à 80 caractères


def render_header(global_stats, width):
    """Affiche l'en-tête avec les statistiques globales"""
    
    # Ligne de titre
    title = "🎮 LAST WAR - SYSTÈME DE DÉTECTION D'ALERTES 🎮"
    title_colored = colorize_text(title, 'BOLD')
    print(title_colored.center(width))
    
    # Ligne de séparation
    print("═" * width)
    
    # Statistiques globales
    uptime = time.time() - global_stats.get('start_time', time.time())
    cycles = global_stats.get('total_cycles', 0)
    reconnections = global_stats.get('obs_reconnections', 0)
    
    # Informations système
    memory_info = get_memory_usage()
    memory_text = ""
    if memory_info:
        memory_mb = memory_info['rss'] / (1024 * 1024)
        memory_text = f"Mémoire: {memory_mb:.1f}MB ({memory_info['percent']:.1f}%)"
    
    # Ligne d'informations
    uptime_str = format_duration(uptime)
    info_line = f"⏱️  Uptime: {uptime_str} | 🔄 Cycles: {cycles} | 🔌 Reconnexions OBS: {reconnections}"
    if memory_text:
        info_line += f" | 💾 {memory_text}"
    
    print(info_line[:width])
    print("─" * width)


def render_windows_table(windows_state, width):
    """Ancienne fonction - désactivée pour éviter la duplication"""
    # Cette fonction ne fait plus rien pour éviter l'affichage en double
    # Tout est géré par render_windows_table_aligned()
    pass


def calculate_column_widths(headers, windows_state, total_width):
    """Calcule les largeurs de colonnes de manière adaptative"""
    
    # Largeurs minimales
    min_widths = [12, 8, 16, 15, 10, 10, 8, 8]  # Basé sur les en-têtes
    
    # Espace disponible après les séparateurs
    separator_space = len(headers) * 3 - 1  # " │ " entre colonnes
    available_width = total_width - separator_space
    
    # Distribution proportionnelle
    base_total = sum(min_widths)
    if base_total <= available_width:
        # On a de l'espace supplémentaire à distribuer
        extra_space = available_width - base_total
        
        # Distribution de l'espace extra (plus sur les colonnes importantes)
        distribution = [0.2, 0.1, 0.25, 0.2, 0.1, 0.05, 0.05, 0.05]
        
        final_widths = []
        for i, (min_w, dist) in enumerate(zip(min_widths, distribution)):
            extra = int(extra_space * dist)
            final_widths.append(min_w + extra)
    else:
        # Espace insuffisant, utiliser les minimums
        final_widths = min_widths
    
    return final_widths


def render_window_row(source_name, state, col_widths):
    """Affiche une ligne du tableau pour une fenêtre"""
    
    # Préparation des données
    last_capture = state.get("last_capture_time", "Jamais")
    if last_capture != "Jamais":
        # Affichage relatif du temps
        try:
            capture_time = datetime.strptime(last_capture, "%Y-%m-%d %H:%M:%S")
            time_ago = datetime.now() - capture_time
            if time_ago.total_seconds() < 60:
                last_capture = f"{int(time_ago.total_seconds())}s"
            elif time_ago.total_seconds() < 3600:
                last_capture = f"{int(time_ago.total_seconds() // 60)}min"
            else:
                last_capture = f"{int(time_ago.total_seconds() // 3600)}h"
        except:
            last_capture = "Erreur"
    
    # Statut avec couleur
    alert_state = state.get("last_alert_state", False)
    consecutive_failures = state.get("consecutive_failures", 0)
    
    if consecutive_failures >= 5:
        status = colorize_text("⚠️ ERREUR", 'RED')
    elif alert_state:
        status = colorize_text("🚨 ALERTE", 'RED')
    elif consecutive_failures > 0:
        status = colorize_text("⚠️ Instable", 'YELLOW')
    else:
        status = colorize_text("✅ OK", 'GREEN')
    
    # Dernière alerte
    last_alert = state.get("last_alert_name", "Aucune")
    if last_alert == "Aucune":
        last_alert = colorize_text("─", 'CYAN')
    else:
        last_alert = colorize_text(last_alert, 'YELLOW')
    
    # Confiance avec couleur selon le niveau
    confidence = state.get("last_confidence", 0.0)
    confidence_text = f"{confidence:.2%}"
    if confidence >= 0.8:
        confidence_text = colorize_text(confidence_text, 'GREEN')
    elif confidence >= 0.5:
        confidence_text = colorize_text(confidence_text, 'YELLOW')
    else:
        confidence_text = colorize_text(confidence_text, 'RED')
    
    # Statistiques
    total_detections = state.get("total_detections", 0)
    total_captures = state.get("total_captures", 0)
    successful_captures = state.get("successful_captures", 0)
    error_count = state.get("error_count", 0)
    
    success_rate = safe_divide(successful_captures, total_captures, 0) * 100
    success_text = f"{success_rate:.0f}%"
    if success_rate >= 90:
        success_text = colorize_text(success_text, 'GREEN')
    elif success_rate >= 70:
        success_text = colorize_text(success_text, 'YELLOW')
    else:
        success_text = colorize_text(success_text, 'RED')
    
    # Construction de la ligne
    row_data = [
        truncate_string(source_name, col_widths[0]),
        status,
        last_capture,
        last_alert,
        confidence_text,
        str(total_detections),
        success_text,
        colorize_text(str(error_count), 'RED') if error_count > 0 else '0'
    ]
    
    # Affichage avec padding
    row_line = " │ ".join(
        data.ljust(col_widths[i]) if i not in [1, 3, 4, 6, 7] else data
        for i, data in enumerate(row_data)
    )
    
    print(row_line)


def render_performance_stats(windows_state, width):
    """Affiche les statistiques de performance détaillées"""
    
    print("\n" + "─" * width)
    print(colorize_text("📊 STATISTIQUES DE PERFORMANCE", 'BOLD'))
    print("─" * width)
    
    for source_name, state in windows_state.items():
        total_captures = state.get("total_captures", 0)
        successful_captures = state.get("successful_captures", 0)
        performance_ms = state.get("performance_ms", 0)
        notifications_sent = state.get("notifications_sent", 0)
        
        if total_captures == 0:
            continue
        
        # Calculs
        success_rate = (successful_captures / total_captures) * 100
        
        # Ligne de performance
        perf_line = f"🎯 {source_name}:"
        perf_line += f" Captures: {successful_captures}/{total_captures}"
        perf_line += f" ({success_rate:.1f}%)"
        perf_line += f" │ Temps: {performance_ms:.1f}ms"
        perf_line += f" │ Notifications: {notifications_sent}"
        
        # Barre de progression du taux de succès
        progress_bar = create_progress_bar(success_rate, width=20)
        perf_line += f" │ {progress_bar}"
        
        print(perf_line[:width])
        
        # Erreurs récentes si présentes
        last_error = state.get("last_error")
        if last_error:
            error_line = f"   ⚠️ Dernière erreur: {truncate_string(last_error, width - 20)}"
            print(colorize_text(error_line, 'RED'))


def render_confidence_history(windows_state, width):
    """Affiche l'historique de confiance sous forme de graphique ASCII"""
    
    print("\n" + "─" * width)
    print(colorize_text("📈 HISTORIQUE DE CONFIANCE (20 dernières détections)", 'BOLD'))
    print("─" * width)
    
    # Import des alertes pour récupérer l'historique
    from config import ALERTS
    
    for alert in ALERTS:
        if not alert.get('enabled', True):
            continue
            
        history = list(alert.get('history', []))
        if len(history) < 2:
            continue
        
        # Prendre les 20 dernières valeurs
        recent_history = history[-20:]
        
        # Création du mini-graphique
        graph_width = min(40, width - 30)
        graph = create_confidence_graph(recent_history, graph_width)
        
        avg_confidence = sum(recent_history) / len(recent_history)
        max_confidence = max(recent_history)
        
        graph_line = f"🎯 {alert['name']}: {graph}"
        graph_line += f" │ Moy: {avg_confidence:.2%} Max: {max_confidence:.2%}"
        
        print(graph_line[:width])


def create_confidence_graph(values, width):
    """Crée un graphique ASCII des valeurs de confiance"""
    if not values or width < 5:
        return "─" * width
    
    # Normalisation des valeurs
    if max(values) > 0:
        normalized = [int(v / max(values) * 4) for v in values]
    else:
        normalized = [0] * len(values)
    
    # Caractères pour différents niveaux
    chars = [' ', '░', '▒', '▓', '█']
    
    # Création du graphique
    graph_values = []
    for i in range(width):
        if i < len(normalized):
            level = min(normalized[i], 4)
            graph_values.append(chars[level])
        else:
            graph_values.append(' ')
    
    return ''.join(graph_values)


def render_footer(width):
    """Affiche le pied de page avec les contrôles"""
    
    print("\n" + "─" * width)
    
    # Informations de contrôle
    controls = [
        "Ctrl+C: Arrêter",
        "F5: Actualiser",
        "F1: Aide"
    ]
    
    footer_line = " │ ".join(controls)
    footer_centered = footer_line.center(width)
    
    print(colorize_text(footer_centered, 'CYAN'))
    
    # Timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp_line = f"Dernière mise à jour: {timestamp}"
    print(timestamp_line.center(width))
    
    print("═" * width)


def render_simple_status(windows_state):
    """Affichage simplifié pour les terminaux étroits"""
    
    clear_console()
    
    print("🎮 LAST WAR ALERTS - Statut simplifié")
    print("=" * 50)
    
    for source_name, state in windows_state.items():
        alert_state = state.get("last_alert_state", False)
        last_alert = state.get("last_alert_name", "Aucune")
        success_rate = safe_divide(
            state.get("successful_captures", 0),
            state.get("total_captures", 1),
            0
        ) * 100
        
        status_icon = "🚨" if alert_state else "✅"
        print(f"{status_icon} {source_name}: {last_alert} ({success_rate:.0f}%)")
    
    print("=" * 50)
    print("Ctrl+C pour arrêter")


def show_startup_banner():
    """Affiche la bannière de démarrage"""
    
    clear_console()
    
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                    🎮 LAST WAR ALERTS 🎮                    ║
║                  Système de détection v2.0                  ║
║                                                              ║
║  🎯 Détection multi-fenêtre avec OBS WebSocket              ║
║  🔔 Notifications Windows améliorées                        ║
║  📊 Statistiques temps réel                                 ║
║  🛠️ Récupération automatique d'erreurs                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """
    
    print(colorize_text(banner, 'CYAN'))
    print("\n⚙️ Initialisation en cours...\n")
    time.sleep(1)


def show_shutdown_message(stats=None):
    """Affiche le message d'arrêt avec statistiques finales"""
    
    clear_console()
    
    print(colorize_text("🛑 ARRÊT DU SYSTÈME", 'RED'))
    print("=" * 50)
    
    if stats:
        uptime = time.time() - stats.get('start_time', time.time())
        cycles = stats.get('total_cycles', 0)
        
        print(f"⏱️  Temps de fonctionnement: {format_duration(uptime)}")
        print(f"🔄 Cycles exécutés: {cycles}")
        print(f"🔌 Reconnexions OBS: {stats.get('obs_reconnections', 0)}")
    
    print("\n✅ Arrêt propre terminé")
    print("Merci d'avoir utilisé Last War Alerts!")