# -*- coding: utf-8 -*-
"""
Permits UI Module (Stage A)

Provides the interface for viewing and interacting with Area Permits (Church, Cemetery, etc.).
Implemented as a simple modal overlay similar to other UI modals.

All parameters are driven by `game.config.config` where possible.
"""

import pygame
from game.config import (
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    TILE_SIZE,
)
from game.world.permits import PERMIT_TYPES  # Assume a dict mapping permit ids to metadata
from game.ui.ui_theme import ui_font, upx


class PermitsModal:
    """Modal UI for displaying permits list and details."""

    def __init__(self):
        self.show = False
        self.selected_permit_id = None
        self.modal_rect = None
        self.permit_rects = []  # List of (permit_id, pygame.Rect)
        self.font_title = None
        self.font_body = None

    def _init_fonts(self):
        if self.font_title is None:
            self.font_title = ui_font(28, bold=True)
            self.font_body = ui_font(18)

    def open(self, permit_id=None):
        self.show = True
        self.selected_permit_id = permit_id

    def close(self):
        self.show = False
        self.selected_permit_id = None

    def handle_event(self, event):
        if not self.show:
            return None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos
            # Click on a permit in the list
            for pid, rect in self.permit_rects:
                if rect.collidepoint(mouse_pos):
                    self.selected_permit_id = pid
                    return "permit_selected"
            # Click outside modal to close
            if self.modal_rect and not self.modal_rect.collidepoint(mouse_pos):
                self.close()
                return "permit_modal_closed"
        return None

    def draw(self, surface):
        if not self.show:
            return
        self._init_fonts()
        screen_w, screen_h = surface.get_size()
        # Modal dimensions (relative to screen size)
        mw = int(screen_w * 0.6)
        mh = int(screen_h * 0.7)
        mx = (screen_w - mw) // 2
        my = (screen_h - mh) // 2
        self.modal_rect = pygame.Rect(mx, my, mw, mh)

        # Dim background
        dim = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 120))
        surface.blit(dim, (0, 0))

        # Modal background
        pygame.draw.rect(surface, COLOR_MODAL_BG, self.modal_rect, border_radius=12)
        pygame.draw.rect(surface, COLOR_MODAL_BORDER, self.modal_rect, width=2, border_radius=12)

        # Header
        header_surf = self.font_title.render("Permits Overview", True, COLOR_TEXT_TITLE)
        surface.blit(header_surf, (mx + 20, my + 20))

        # List of permits on the left side (30% width)
        list_w = int(mw * 0.35)
        list_h = mh - 80
        list_x = mx + 20
        list_y = my + 60
        item_h = upx(40)
        self.permit_rects.clear()
        for idx, (pid, pinfo) in enumerate(PERMIT_TYPES.items()):
            rect = pygame.Rect(list_x, list_y + idx * (item_h + 8), list_w, item_h)
            self.permit_rects.append((pid, rect))
            bg = (30, 41, 59) if pid != self.selected_permit_id else (45, 55, 72)
            pygame.draw.rect(surface, bg, rect, border_radius=6)
            label = pinfo.get("name", pid).title()
            txt = self.font_body.render(label, True, COLOR_TEXT_MAIN)
            surface.blit(txt, (rect.x + 10, rect.centery - txt.get_height() // 2))

        # Detail pane on the right side
        detail_x = list_x + list_w + 20
        detail_w = mw - (list_w + 60)
        if self.selected_permit_id:
            pinfo = PERMIT_TYPES.get(self.selected_permit_id, {})
            # Title
            title = self.font_title.render(pinfo.get("name", ""), True, COLOR_TEXT_TITLE)
            surface.blit(title, (detail_x, my + 60))
            # Description
            desc_lines = pinfo.get("description", "").split("\n")
            for i, line in enumerate(desc_lines):
                line_surf = self.font_body.render(line, True, COLOR_TEXT_MAIN)
                surface.blit(line_surf, (detail_x, my + 100 + i * (line_surf.get_height() + 4)))
            # Stats (e.g., max workers, cost)
            stats = []
            if "max_workers" in pinfo:
                stats.append(f"Max Workers: {pinfo['max_workers']}")
            if "cost" in pinfo:
                stats.append(f"Cost: {pinfo['cost']} Wood, {pinfo.get('cost_stone', 0)} Stone")
            for i, s in enumerate(stats):
                s_surf = self.font_body.render(s, True, COLOR_TEXT_MAIN)
                surface.blit(s_surf, (detail_x, my + 180 + i * (s_surf.get_height() + 4)))

        # Close button (top‑right corner)
        btn_w, btn_h = 80, 30
        btn_rect = pygame.Rect(mx + mw - btn_w - 10, my + 10, btn_w, btn_h)
        pygame.draw.rect(surface, (200, 50, 50), btn_rect, border_radius=4)
        btn_txt = self.font_body.render("Close", True, (255, 255, 255))
        surface.blit(btn_txt, (btn_rect.centerx - btn_txt.get_width() // 2, btn_rect.centery - btn_txt.get_height() // 2))
        # Register close button for click handling
        self.permit_rects.append(("__close__", btn_rect))
