"""Desktop presentation theme.

The scientific ``Config`` remains the persisted model configuration.  This
module provides a GUI-facing view of the legacy ``ui_*`` values so the
presentation layer does not need to know about model configuration fields.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from damage_gui.config import CONFIG, Config


@dataclass(frozen=True)
class Theme:
    """Neutral engineering-workbench colors and typography."""

    bg: str = "#F3F5F7"
    panel_bg: str = "#FFFFFF"
    soft_bg: str = "#E9EDF1"
    border: str = "#CDD4DC"
    primary: str = "#234A73"
    primary_dark: str = "#183753"
    accent: str = "#234A73"
    text: str = "#1F2933"
    muted: str = "#66727E"
    header_bg: str = "#263B4D"
    header_fg: str = "#FFFFFF"
    header_muted: str = "#C7D1DA"
    success: str = "#2D6A4F"
    danger: str = "#A33A32"
    busy: str = "#9A6700"
    ui_latin_font: str = "Segoe UI"
    ui_chinese_font: str = "Microsoft YaHei UI"
    mono_font: str = "Cascadia Mono"

    @property
    def ui_font(self) -> str:
        """Backward-compatible name for the Chinese-capable UI family."""
        return self.ui_chinese_font

    @classmethod
    def from_config(cls, config: Config | None = None) -> Theme:
        """Read legacy UI values without changing model serialization."""
        source = config or CONFIG
        return cls(
            bg=getattr(source, "ui_bg", cls.bg),
            panel_bg=getattr(source, "ui_panel_bg", cls.panel_bg),
            soft_bg=getattr(source, "ui_soft_bg", cls.soft_bg),
            border=getattr(source, "ui_border", cls.border),
            primary=getattr(source, "ui_primary", cls.primary),
            primary_dark=getattr(source, "ui_primary_dark", cls.primary_dark),
            accent=getattr(source, "ui_accent", cls.accent),
            text=getattr(source, "ui_text", cls.text),
            muted=getattr(source, "ui_muted", cls.muted),
            header_bg=getattr(source, "ui_header_bg", cls.header_bg),
            header_fg=getattr(source, "ui_header_fg", cls.header_fg),
            header_muted=getattr(source, "ui_header_muted", cls.header_muted),
            success=getattr(source, "ui_success", cls.success),
            danger=getattr(source, "ui_danger", cls.danger),
            busy=getattr(source, "ui_busy", cls.busy),
        )


THEME = Theme.from_config()


@dataclass(frozen=True)
class FontFamilies:
    """Resolved font families used by Tk widgets and menus."""

    latin: str
    chinese: str
    mono: str


def resolve_font_families(
    available: Iterable[str],
    theme: Theme = THEME,
) -> FontFamilies:
    """Choose the preferred Windows families with deterministic fallbacks."""
    installed = {str(name).casefold(): str(name) for name in available}

    def choose(preferred: str, fallbacks: tuple[str, ...]) -> str:
        for family in (preferred, *fallbacks):
            resolved = installed.get(family.casefold())
            if resolved:
                return resolved
        # Let Tk resolve a missing family on unusual hosts while keeping the
        # requested family stable instead of selecting a platform default here.
        return preferred

    latin = choose(theme.ui_latin_font, ("Arial", "Tahoma", theme.ui_chinese_font))
    chinese = choose(
        theme.ui_chinese_font,
        ("Microsoft YaHei", "SimSun", latin),
    )
    mono = choose(theme.mono_font, ("Consolas", "Courier New", "DejaVu Sans Mono"))
    return FontFamilies(latin=latin, chinese=chinese, mono=mono)
