"""ttk style definitions for the desktop workbench."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from damage_gui.gui.theme import THEME, Theme, resolve_font_families


def configure_styles(root: tk.Misc, theme: Theme = THEME) -> ttk.Style:
    """Configure restrained native-ish widgets and return the active style."""
    root.configure(bg=theme.bg)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    try:
        families = resolve_font_families(tkfont.families(root), theme)
    except tk.TclError:
        families = resolve_font_families((), theme)

    latin_font = (families.latin, 10)
    small_latin_font = (families.latin, 9)
    section_font = (families.latin, 9, "bold")
    title_font = (families.latin, 12, "bold")
    chinese_font = (families.chinese, 10)
    small_chinese_font = (families.chinese, 9)
    small_value_font = (families.mono, 9)
    disabled_foreground = "#9AA4AE"
    disabled_background = theme.soft_bg
    hover_background = "#E9EDF1"
    pressed_background = "#DDE4EA"

    # Explicit base ttk assignments prevent platform theme defaults from
    # reintroducing Segoe UI/YaHei family changes between widget classes.
    style.configure(".", font=chinese_font)
    style.configure("TLabel", font=chinese_font)
    style.configure("TButton", font=chinese_font)
    style.configure("TEntry", font=chinese_font)
    style.configure("TCombobox", font=chinese_font)
    style.configure("TSpinbox", font=chinese_font)
    style.configure("TCheckbutton", font=chinese_font)
    style.configure("TMenubutton", font=chinese_font)
    style.configure("Workbench.TFrame", background=theme.bg)
    style.configure("Pane.TFrame", background=theme.panel_bg)
    style.configure("Inspector.TFrame", background=theme.panel_bg)
    style.configure("Toolbar.TFrame", background=theme.bg)
    style.configure("Status.TFrame", background=theme.bg)
    style.configure("PanelTitle.TLabel", background=theme.panel_bg, foreground=theme.text,
                    font=title_font)
    style.configure("PanelSubTitle.TLabel", background=theme.panel_bg, foreground=theme.muted,
                    font=small_chinese_font)
    style.configure("Section.TLabel", background=theme.panel_bg, foreground=theme.muted,
                    font=section_font)
    style.configure("FieldLabel.TLabel", background=theme.panel_bg, foreground=theme.muted,
                    font=small_latin_font)
    style.configure("Body.TLabel", background=theme.panel_bg, foreground=theme.text,
                    font=latin_font)
    style.configure("Muted.TLabel", background=theme.panel_bg, foreground=theme.muted,
                    font=small_latin_font)
    style.configure("MutedChinese.TLabel", background=theme.panel_bg, foreground=theme.muted,
                    font=small_chinese_font)
    style.configure("Value.TLabel", background=theme.panel_bg, foreground=theme.text,
                    font=small_value_font)
    style.configure("Unit.TLabel", background=theme.panel_bg, foreground=theme.muted,
                    font=small_latin_font)
    style.configure("Status.TLabel", background=theme.bg, foreground=theme.text,
                    font=small_chinese_font)
    style.configure("StatusValue.TLabel", background=theme.bg, foreground=theme.text,
                    font=small_value_font)
    style.configure("Toolbar.TButton", padding=(8, 3), font=small_latin_font,
                    background=theme.bg, foreground=theme.text, bordercolor=theme.border)
    style.map("Toolbar.TButton", background=[("active", hover_background),
                                               ("pressed", pressed_background),
                                               ("disabled", disabled_background)],
              foreground=[("disabled", disabled_foreground)])
    style.configure("ToolbarChinese.TButton", padding=(8, 3), font=small_chinese_font,
                    background=theme.bg, foreground=theme.text, bordercolor=theme.border)
    style.map("ToolbarChinese.TButton", background=[("active", hover_background),
                                                      ("pressed", pressed_background),
                                                      ("disabled", disabled_background)],
              foreground=[("disabled", disabled_foreground)])
    try:
        tk_scaling = float(root.tk.call("tk", "scaling"))
    except (tk.TclError, TypeError, ValueError):
        tk_scaling = 1.333
    if tk_scaling < 1.85:
        toolbar_combo_padding_y = 4
    elif tk_scaling < 2.15:
        toolbar_combo_padding_y = 6
    else:
        toolbar_combo_padding_y = 8
    style.configure("Toolbar.TCombobox", padding=(4, toolbar_combo_padding_y),
                    font=small_chinese_font,
                    fieldbackground=theme.bg, foreground=theme.text, bordercolor=theme.border)
    style.map("Toolbar.TCombobox", fieldbackground=[("disabled", disabled_background)],
              foreground=[("disabled", disabled_foreground)])
    style.configure("Primary.TButton", padding=(8, 3), font=small_latin_font,
                    background=theme.primary, foreground="#FFFFFF")
    style.map("Primary.TButton", background=[("active", theme.primary_dark),
                                               ("pressed", theme.primary_dark),
                                               ("disabled", "#AEB8C1")],
              foreground=[("disabled", "#EEF1F3"), ("!disabled", "#FFFFFF")])
    style.configure("Secondary.TButton", padding=(8, 3), font=small_latin_font,
                    background=theme.bg, foreground=theme.text,
                    bordercolor=theme.border)
    style.map("Secondary.TButton", background=[("active", hover_background),
                                                 ("pressed", pressed_background),
                                                 ("disabled", disabled_background)],
              foreground=[("disabled", disabled_foreground)])
    style.configure("App.TEntry", padding=(5, 3), font=latin_font, fieldbackground="#FFFFFF",
                    foreground=theme.text, bordercolor=theme.border)
    style.map("App.TEntry", fieldbackground=[("disabled", disabled_background)],
              foreground=[("disabled", disabled_foreground)])
    style.configure("App.TCombobox", padding=(4, 2), font=latin_font, fieldbackground="#FFFFFF",
                    foreground=theme.text, bordercolor=theme.border)
    style.map("App.TCombobox", fieldbackground=[("disabled", disabled_background)],
              foreground=[("disabled", disabled_foreground)])
    style.configure("App.TSpinbox", padding=(4, 2), font=latin_font, fieldbackground="#FFFFFF",
                    foreground=theme.text, bordercolor=theme.border,
                    arrowcolor=theme.primary)
    style.map("App.TSpinbox", fieldbackground=[("disabled", disabled_background)],
              foreground=[("disabled", disabled_foreground)],
              arrowcolor=[("disabled", disabled_foreground)])
    style.configure("App.Horizontal.TProgressbar", troughcolor=theme.soft_bg,
                    background=theme.primary, bordercolor=theme.border,
                    lightcolor=theme.primary, darkcolor=theme.primary, thickness=7)
    style.configure(
        "Navigation.Treeview", background=theme.panel_bg, fieldbackground=theme.panel_bg,
        foreground=theme.text, borderwidth=0, rowheight=24, indent=12, font=small_latin_font,
    )
    style.map("Navigation.Treeview", background=[("selected", "#DCE6F0")],
              foreground=[("selected", theme.primary)])
    style.configure("Navigation.Treeview.Heading", background=theme.panel_bg,
                    foreground=theme.muted, font=section_font)
    style.configure("Treeview", borderwidth=0, font=small_latin_font)
    style.configure("Treeview.Heading", font=section_font)
    style.configure("TSeparator", background=theme.border)
    style.configure("TPanedwindow", background=theme.bg)
    return style
