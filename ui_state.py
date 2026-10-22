"""Shared transient state for classic panels and Custom UI capture."""
from dataclasses import dataclass


@dataclass
class DrawState:
    drawing_section: object = None
    detached_target: object = None
    detached_layout: object = None
    group_discovery: object = None
    search_probing: bool = False
    search_filter_groups: object = None
    search_filter_terms: tuple = ()
    custom_capturing: bool = False
    custom_header_only: bool = False
    section_panel_classes: tuple = ()


state = DrawState()
