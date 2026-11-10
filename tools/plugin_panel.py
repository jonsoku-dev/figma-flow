"""Embed the offline stylesheet in a generated Figma plugin panel."""
from pathlib import Path

_STYLESHEET = Path(__file__).resolve().parents[1] / 'figma-bridge' / 'panel.css'


def render_panel(html):
    marker = '/* FIGMA_FLOW_PANEL_CSS */'
    if html.count(marker) != 1:
        raise ValueError('Figma panel requires exactly one shared stylesheet marker')
    return html.replace(marker, _STYLESHEET.read_text(encoding='utf-8'))
