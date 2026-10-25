"""Bilateral console state introspection and reactive UI interaction engine."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Union

from gemini_app.config import GEMINI_HOME, THEMES, DEFAULT_PALETTE, MOBILE_BREAKPOINT

ANIMATION_EFFECTS: set[str] = {"sparkle", "pulse", "wave", "synapse", "glow"}

ANIMATION_FRAMES: dict[str, list[str]] = {
    "sparkle": ["✨ ∙ ∙ ✨", "∙ ✨ ∙ ∙", "∙ ∙ ✨ ∙", "✨ ∙ ✨ ∙", "★ ✧ ✦ ✧"],
    "pulse": ["● ∙ ∙ ∙", "∙ ● ∙ ∙", "∙ ∙ ● ∙", "∙ ∙ ∙ ●", "∙ ∙ ● ∙", "∙ ● ∙ ∙"],
    "wave": ["∿ ∿ ∿ ∿", "〜 〜 〜 〜", "≈ ≈ ≈ ≈", "〜 〜 〜 〜"],
    "synapse": ["⚡ ∙ ∙ ⚡", "∙ ⚡ ∙ ∙", "∙ ∙ ⚡ ∙", "⚡ ⚡ ⚡ ⚡", "⟡ ⟢ ⟣ ⟡"],
    "glow": ["◐ ◓ ◑ ◒", "✦ ✧ ✦ ✧", "✶ ✷ ✸ ✹"],
}


def compute_user_location(app: Any) -> Dict[str, Any]:
    """Determines exact human-readable location of the user across screens, modals, and widgets."""
    screen_obj = getattr(app, "screen", None)
    screen_name = type(screen_obj).__name__ if screen_obj else "Unknown"

    screen_stack = getattr(app, "screen_stack", [])
    stack_names = [type(s).__name__ for s in screen_stack] if screen_stack else [screen_name]

    focused = getattr(app, "focused", None)
    focused_id = getattr(focused, "id", None)
    focused_type = type(focused).__name__ if focused else None

    notes_open = bool(getattr(app, "notes_open", False))
    notes_mgr = getattr(app, "notes_manager", None)
    active_topic = getattr(notes_mgr, "active_topic", "general") if notes_mgr else "general"

    turn_idx = getattr(app, "current_focused_turn_index", None)
    turn_id = getattr(app, "current_focused_turn_id", None)

    modal_labels = {
        "MindMapScreen": "Cognitive Mind Map (Viewing visual relation tree & anchors)",
        "BootScreen": "Boot Splash Screen",
        "ForkModal": "Fork & Branch Navigation Modal",
        "CommandsModal": "Commands & Shortcuts Palette",
        "VaultDashboardModal": "Vault Dashboard (Encrypted secrets & passkeys)",
        "VaultAuthModal": "Vault Authentication Prompt",
        "VaultChangePasskeyModal": "Vault Passkey Setup",
        "VaultPasswordEntryModal": "Vault Password Entry Modal",
        "VaultSecretEntryModal": "Vault Secret Entry Modal",
        "VaultFileEntryModal": "Vault File Entry Modal",
        "GitTreeModal": "Git Tree Inspector (Browsing files)",
        "WriteSnippetModal": "Snippet Composer Modal",
        "InsertFileModal": "File Ingestion Modal",
        "FrameSelectModal": "Frame Select Modal",
        "GitSetupModal": "Git Setup Modal",
        "ApiKeyModal": "API Key Modal",
        "ConfirmModal": "Confirmation Dialog",
        "TitlePromptModal": "Title Prompt Dialog",
        "WingmanAuthModal": "Wingman Security Authorization Modal",
    }

    if screen_name in modal_labels:
        loc = modal_labels[screen_name]
        if focused_id:
            loc += f" [Focus: {focused_id}]"
        active_view = screen_name
    elif screen_name not in ("Screen", "ChatApp", "Unknown"):
        loc = f"Modal: {screen_name}" + (f" [Focus: {focused_id}]" if focused_id else "")
        active_view = screen_name
    else:
        active_view = "MainChat"
        if focused_id == "input":
            loc = "Main Chat Input (Typing prompt / command)"
        elif focused_id in ("notes_editor", "notes_input"):
            loc = f"Notes Panel Editor (Active Topic: '{active_topic}')"
        elif focused_type == "TopicChip" or (focused_id and "chip" in str(focused_id)):
            loc = f"Notes Panel (Browsing topic chips: active '{active_topic}')"
        elif focused_id == "snippet_preview":
            loc = "Snippet Preview (Inspecting staged code snippet)"
        elif focused_id == "feed" or focused_type == "TurnCard" or (focused_id and "turn" in str(focused_id)):
            turn_str = f"Turn #{turn_idx + 1}" if turn_idx is not None and turn_idx >= 0 else "Feed"
            if turn_id:
                turn_str += f" [{turn_id[:8]}]"
            loc = f"Chat Feed (Viewing {turn_str})"
        elif notes_open and ("notes" in str(focused_id).lower() or "notes" in str(focused_type).lower()):
            loc = f"Notes Panel (Active topic: '{active_topic}')"
        else:
            loc = f"Main Chat (Focus: {focused_id or focused_type or 'Feed'})"

    return {
        "user_location": loc,
        "active_view": active_view,
        "screen_name": screen_name,
        "modal_stack": stack_names,
        "focused_widget_id": focused_id,
        "focused_widget_type": focused_type,
        "notes_open": notes_open,
        "active_topic": active_topic,
        "turn_index": turn_idx,
        "turn_id": turn_id,
    }


def get_tier_1_visual(app: Any) -> Dict[str, Any]:
    """Tier 1: Visual & Layout Awareness (Presentation Layer)."""
    theme_name = getattr(app, "active_palette_name", DEFAULT_PALETTE)
    theme_cfg = THEMES.get(theme_name, THEMES[DEFAULT_PALETTE])

    w = 80
    h = 24
    if hasattr(app, "size") and app.size:
        w = app.size.width
        h = app.size.height

    loc_info = compute_user_location(app)
    screen_name = loc_info["screen_name"]
    is_mobile = w <= MOBILE_BREAKPOINT

    return {
        "tier": 1,
        "name": "visual_layout",
        "user_location": loc_info["user_location"],
        "active_view": loc_info["active_view"],
        "active_theme": theme_name,
        "accent_color": theme_cfg.get("accent", "#ff3333"),
        "accent_bright": theme_cfg.get("accent_bright", "#ff6666"),
        "accent_dim": theme_cfg.get("accent_dim", "#aa1111"),
        "banner_bg": theme_cfg.get("banner_bg", "#8b0000"),
        "card_active_bg": theme_cfg.get("card_active_bg", "#2a0808"),
        "available_themes": sorted(list(THEMES.keys())),
        "viewport": {
            "width": w,
            "height": h,
            "is_mobile": is_mobile,
            "mobile_breakpoint": MOBILE_BREAKPOINT,
        },
        "views": {
            "active_screen": screen_name,
            "active_view": loc_info["active_view"],
            "screen_stack": loc_info["modal_stack"],
            "is_mind_screen_open": screen_name == "MindMapScreen",
            "notes_panel_open": loc_info["notes_open"],
            "focused_widget_id": loc_info["focused_widget_id"],
            "focused_widget_type": loc_info["focused_widget_type"],
            "nav_indicator_action": getattr(app, "_nav_indicator_action", None),
            "nav_indicator_palette": getattr(app, "_nav_indicator_palette", None),
        },
    }


def get_tier_2_runtime(app: Any) -> Dict[str, Any]:
    """Tier 2: Runtime & Operational Environment (Runtime Layer)."""
    working_dir = (
        app.get_effective_working_dir()
        if hasattr(app, "get_effective_working_dir")
        else getattr(app, "working_dir", "")
    )

    history = getattr(app, "history", [])
    turns_count = len(history)

    chat_id = getattr(app, "current_chat_id", "")
    parent_id = getattr(app, "current_chat_parent_id", None)

    phase = getattr(app, "_request_phase", "idle")
    details = getattr(app, "_request_details", "")

    focused_turn = getattr(app, "current_focused_turn_id", "")
    marker = getattr(app, "current_chat_center_marker", "")

    emergency_runs = 0
    last_emergency = None
    try:
        emg_file = GEMINI_HOME / "emergency_state.json"
        if emg_file.exists():
            emg_data = json.loads(emg_file.read_text(encoding="utf-8"))
            emergency_runs = int(emg_data.get("total_runs", 0))
            last_emergency = emg_data.get("last_session")
    except Exception:
        pass

    return {
        "tier": 2,
        "name": "runtime_operational",
        "working_dir": str(working_dir),
        "chat_id": chat_id,
        "parent_id": parent_id,
        "turns_count": turns_count,
        "request_phase": phase,
        "request_details": details,
        "focused_turn_id": focused_turn,
        "center_marker": marker,
        "emergency_runs": emergency_runs,
        "last_emergency_session": last_emergency,
    }


def get_tier_3_workflow(app: Any) -> Dict[str, Any]:
    """Tier 3: Ergonomic & Workflow Anchors (Cognitive Layer)."""
    task_title = getattr(app, "active_task_title", "")
    gemini_state = getattr(app, "current_gemini_state", "")
    user_state = getattr(app, "current_user_state", "")
    tree_state = getattr(app, "current_tree_state", [])
    tree_content = getattr(app, "current_tree_content", "")
    working_notes = getattr(app, "gemini_notes", "")

    notes_mgr = getattr(app, "notes_manager", None)
    active_topic = getattr(notes_mgr, "active_topic", "general") if notes_mgr else "general"
    topics_list = notes_mgr.get_all_topics() if notes_mgr else ["general"]
    notes_count = len(getattr(notes_mgr, "notes", [])) if notes_mgr else 0

    held_snapshots_count = 0
    try:
        from gemini_app.tools.snapshots import list_held_snapshots
        held_snapshots_count = len(list_held_snapshots(only_held=True))
    except Exception:
        pass

    return {
        "tier": 3,
        "name": "workflow_cognitive",
        "active_task_title": task_title,
        "gemini_mind_state": gemini_state,
        "user_mind_state": user_state,
        "tree_state": tree_state,
        "tree_content": tree_content,
        "active_topic": active_topic,
        "all_topics": topics_list,
        "notes_count": notes_count,
        "working_notes": working_notes,
        "held_snapshots_count": held_snapshots_count,
    }


def get_console_state(app: Any, tier: str = "all") -> Dict[str, Any]:
    """Aggregates requested introspection tiers into a unified dictionary."""
    t_clean = (tier or "all").lower().strip()

    if t_clean in ("1", "visual", "presentation"):
        return {"status": "success", "tier_1": get_tier_1_visual(app)}
    elif t_clean in ("2", "runtime", "operational"):
        return {"status": "success", "tier_2": get_tier_2_runtime(app)}
    elif t_clean in ("3", "workflow", "cognitive", "mind"):
        return {"status": "success", "tier_3": get_tier_3_workflow(app)}
    else:
        return {
            "status": "success",
            "tier_1_visual": get_tier_1_visual(app),
            "tier_2_runtime": get_tier_2_runtime(app),
            "tier_3_workflow": get_tier_3_workflow(app),
        }


def format_introspection_summary(app: Any) -> str:
    """Formats a dense multi-tier summary string for the system prompt."""
    t1 = get_tier_1_visual(app)
    t2 = get_tier_2_runtime(app)
    t3 = get_tier_3_workflow(app)

    geom = t1["viewport"]
    views = t1["views"]

    summary_lines = [
        "### BILATERAL CONSOLE INTROSPECTION (LIVE APPLICATION STATE)",
        f"• Visual Layer (Tier 1): Location: {t1['user_location']} | "
        f"Theme: '{t1['active_theme']}' (Accent: {t1['accent_color']}) | "
        f"Screen: {views['active_screen']} (Focus: {views['focused_widget_id'] or 'None'}) | "
        f"Viewport: {geom['width']}x{geom['height']} (Mobile: {geom['is_mobile']}) | "
        f"Notes: {'Open' if views['notes_panel_open'] else 'Closed'}",
        f"• Runtime Layer (Tier 2): CWD: {t2['working_dir']} | Lineage: {t2['chat_id']} (Turns: {t2['turns_count']}) | "
        f"Phase: {t2['request_phase']}",
        f"• Cognitive Layer (Tier 3): Task: '{t3['active_task_title']}' | Topic: '{t3['active_topic']}' ({t3['notes_count']} notes) | "
        f"Snapshots Held: {t3['held_snapshots_count']}",
    ]

    if t2.get("emergency_runs", 0) > 0:
        last_emg = t2.get("last_emergency_session") or {}
        r_num = last_emg.get("run_number", t2["emergency_runs"])
        status = last_emg.get("status", "completed")
        summary_lines.append(f"• Emergency Bridge: {t2['emergency_runs']} run(s) logged (Last: Session #{r_num} - {status})")

    return "\n".join(summary_lines)


def apply_accent_talk(
    app: Any,
    target: str = "all",
    palette: str = "",
    duration: float = 3.0,
    message: str = "",
) -> Dict[str, Any]:
    """Alters accent colors on the fly for specific areas or pulses them with dynamic effects."""
    pal_clean = (palette or "").strip().lower()
    if not pal_clean:
        pal_clean = getattr(app, "active_palette_name", DEFAULT_PALETTE)
    if pal_clean not in THEMES:
        valid = ", ".join(THEMES.keys())
        return {
            "status": "error",
            "message": f"Invalid palette '{palette}'. Choose from: {valid}",
        }

    target_clean = (target or "all").strip().lower()
    theme_cfg = THEMES[pal_clean]
    accent = theme_cfg["accent"]

    # Comma-separated multi-targets (e.g. "input,navbar" or "feed,input")
    if "," in target:
        sub_targets = [t.strip() for t in target.split(",") if t.strip()]
        for st in sub_targets:
            apply_accent_talk(app, target=st, palette=palette, duration=duration, message="")
        if message and hasattr(app, "notify") and not getattr(app, "_suppress_ambient_toasts", False):
            app.notify(f"[{accent}]{message}[/]", timeout=max(2.0, duration))
        return {
            "status": "success",
            "action": "multi_accent_talk",
            "targets": sub_targets,
            "palette": pal_clean,
            "duration": duration,
            "message": f"Accent applied across {len(sub_targets)} targets ({', '.join(sub_targets)}).",
        }

    # Preset collections
    if target_clean in ("widgets", "workspace"):
        return apply_accent_talk(app, target="input,navbar,feed", palette=palette, duration=duration, message=message)

    # Ambient status or mood
    if target_clean in ("mood", "status") and message:
        if hasattr(app, "set_status_text"):
            app.set_status_text(f"[{accent}]{message}[/]")
            if duration > 0 and hasattr(app, "set_timer"):
                app.set_timer(duration, getattr(app, "hide_status", lambda: None))
        return {
            "status": "success",
            "target": target_clean,
            "palette": pal_clean,
            "duration": duration,
            "message": message,
        }

    # If target is "all" or "theme", permanently or temporarily switch theme
    if target_clean in ("all", "theme", "app"):
        if duration <= 0:
            if hasattr(app, "set_theme"):
                app.set_theme(pal_clean, notify_user=bool(message))
            if message and hasattr(app, "notify"):
                app.notify(message, timeout=3.5)
            return {
                "status": "success",
                "target": "app",
                "action": "theme_switch",
                "palette": pal_clean,
                "message": f"Global theme permanently switched to '{pal_clean}'.",
            }
        else:
            prev_theme = getattr(app, "active_palette_name", DEFAULT_PALETTE)
            if hasattr(app, "pulse_theme"):
                app.pulse_theme(pal_clean, duration=duration)
            elif hasattr(app, "set_theme"):
                app.set_theme(pal_clean, notify_user=False, save_state=False)
                if hasattr(app, "set_timer"):
                    app.set_timer(duration, lambda: app.set_theme(prev_theme, notify_user=False, save_state=False))

            if message and hasattr(app, "notify") and not getattr(app, "_suppress_ambient_toasts", False):
                app.notify(f"[{accent}]{message}[/]", timeout=duration)

            return {
                "status": "success",
                "target": "app",
                "action": "theme_pulse",
                "palette": pal_clean,
                "duration": duration,
                "message": f"Global theme pulsed to '{pal_clean}' for {duration:.1f}s.",
            }

    # Navbar navigation item triggers (e.g. edge, cards, snippets, mind, fork, navbar, nav, flash)
    nav_targets = (
        "edge",
        "edge_home",
        "edge_end",
        "cards",
        "snippets",
        "mind",
        "fork",
        "scroll",
        "viewport",
        "navbar",
        "nav",
        "flash",
        "banner",
    )
    if target_clean in nav_targets:
        nav_action = target_clean
        if nav_action == "scroll":
            nav_action = "scroll_down"
        elif nav_action == "viewport":
            nav_action = "page_down"
        elif nav_action in ("nav", "flash", "banner"):
            nav_action = "navbar"

        if hasattr(app, "trigger_nav_indicator"):
            app.trigger_nav_indicator(
                nav_action, toast_message=message if not getattr(app, "_suppress_ambient_toasts", False) else "", palette=pal_clean, duration=duration
            )

        return {
            "status": "success",
            "target": target_clean,
            "palette": pal_clean,
            "accent": accent,
            "duration": duration,
            "message": f"Navbar indicator '{target_clean}' pulsed with '{pal_clean}' ({accent})"
            + (f" for {duration:.1f}s" if duration > 0 else "")
            + (f": {message}" if message else "."),
        }

    # Targeted accent shifts
    widget_selector_map = {
        "feed": "#feed",
        "notes": "#notes_panel",
        "input": "#input",
        "footer": "#custom_footer",
        "preview": "#snippet_preview",
        "status": "#feed_status",
        "runner": "#runner_status",
        "navbar": "#feed_nav_banner",
        "nav": "#feed_nav_banner",
    }

    selector = widget_selector_map.get(target_clean)
    if not selector:
        valid_targets = ", ".join(
            list(widget_selector_map.keys()) + list(nav_targets) + ["all", "theme", "mind"]
        )
        return {
            "status": "error",
            "message": f"Unknown target '{target}'. Available targets: {valid_targets}",
        }

    applied = False
    try:
        widgets = list(app.query(selector)) if hasattr(app, "query") else []
        for w in widgets:
            if getattr(w, "id", None) == "feed_nav_banner":
                if hasattr(app, "trigger_nav_indicator"):
                    app.trigger_nav_indicator(
                        "navbar", toast_message=message if not getattr(app, "_suppress_ambient_toasts", False) else "", palette=pal_clean, duration=duration
                    )
                applied = True
            elif getattr(w, "id", None) == "custom_footer":
                orig_bg = getattr(w.styles, "background", None)
                w.styles.background = accent
                applied = True
                if hasattr(w, "refresh"):
                    w.refresh()
                if duration > 0 and hasattr(app, "set_timer"):
                    def _reset_footer(target_widget=w, prev_bg=orig_bg):
                        try:
                            target_widget.styles.background = prev_bg
                            if hasattr(target_widget, "refresh"):
                                target_widget.refresh()
                        except Exception:
                            pass
                    app.set_timer(duration, _reset_footer)
            else:
                orig_b = getattr(w.styles, "border", None)
                w.styles.border = ("round", accent)
                if hasattr(w, "add_class"):
                    w.add_class(f"border-{pal_clean}")
                applied = True
                if hasattr(w, "refresh"):
                    w.refresh()

                if duration > 0 and hasattr(app, "set_timer"):
                    def _reset_border(target_widget=w, prev_border=orig_b, pal=pal_clean):
                        try:
                            if hasattr(target_widget, "remove_class"):
                                target_widget.remove_class(f"border-{pal}")
                            if prev_border is not None:
                                target_widget.styles.border = prev_border
                            else:
                                target_widget.styles.border = None
                            if hasattr(target_widget, "refresh"):
                                target_widget.refresh()
                        except Exception:
                            pass
                    app.set_timer(duration, _reset_border)

        if message and hasattr(app, "notify") and not getattr(app, "_suppress_ambient_toasts", False):
            app.notify(f"[{accent}]{message}[/]", timeout=max(2.0, duration))

    except Exception as e:
        return {"status": "error", "message": f"Failed to apply accent to '{target}': {e}"}

    return {
        "status": "success" if applied else "target_not_mounted",
        "target": target_clean,
        "palette": pal_clean,
        "accent": accent,
        "duration": duration,
        "message": f"Accent for '{target_clean}' set to '{pal_clean}' ({accent})"
        + (f" for {duration:.1f}s" if duration > 0 else " permanently")
        + ".",
    }


def start_mind_animation(
    app: Any,
    effect: str = "sparkle",
    palette: str = "",
    duration: float = 4.0,
    message: str = "",
) -> Dict[str, Any]:
    """Triggers a playful reactive animation in the Mind Map view."""
    eff_clean = (effect or "sparkle").strip().lower()
    if eff_clean not in ANIMATION_EFFECTS:
        eff_clean = "sparkle"

    pal_clean = palette.strip().lower() if palette else getattr(app, "active_palette_name", DEFAULT_PALETTE)
    if pal_clean not in THEMES:
        pal_clean = getattr(app, "active_palette_name", DEFAULT_PALETTE)

    dur = max(1.0, float(duration))
    now = time.monotonic()

    anim_state = {
        "effect": eff_clean,
        "palette": pal_clean,
        "duration": dur,
        "end_time": now + dur,
        "message": message or f"AI Cognitive Resonance ({eff_clean.title()})",
    }

    setattr(app, "_active_mind_animation", anim_state)

    # If user is currently on MindMapScreen, refresh display immediately
    screen = getattr(app, "screen", None)
    if screen and type(screen).__name__ == "MindMapScreen" and hasattr(screen, "_on_live_watch_tick"):
        screen._on_live_watch_tick()

    if message and hasattr(app, "notify") and not getattr(app, "_suppress_ambient_toasts", False):
        acc = THEMES[pal_clean]["accent"]
        app.notify(f"[{acc}]{message}[/]", title=f"Mind Animation: {eff_clean.title()}", timeout=dur)

    return {
        "status": "success",
        "effect": eff_clean,
        "palette": pal_clean,
        "duration": dur,
        "message": f"Mind animation '{eff_clean}' activated with '{pal_clean}' palette for {dur:.1f}s.",
    }
