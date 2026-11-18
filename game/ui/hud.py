"""
Resource HUD (Dynamic & Responsive)
"""

import pygame
from game.config import (
    COLOR_HUD_BG,
    COLOR_HUD_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    RESOURCE_COLORS,
    RES_HUD_WIDTH,
    RES_HUD_MARGIN
)

class ResourceHUD:
    def __init__(self):
        self.card_width = RES_HUD_WIDTH
        self.margin = RES_HUD_MARGIN
        self.row_height = 28
        self.header_height = 36
        self.padding = 12

        self.font_title = None
        self.font_item = None
        self.font_val = None

    def _init_fonts(self):
        if self.font_title is None:
            self.font_title = pygame.font.SysFont("Segoe UI", 12, bold=True)
            self.font_item = pygame.font.SysFont("Segoe UI", 13)
            self.font_val = pygame.font.SysFont("Consolas", 13, bold=True)

    def draw(self, surface, resources):
        self._init_fonts()
        screen_w, _ = surface.get_size()

        # Hitung tinggi kartu berdasarkan jumlah resource
        num_items = len(resources)
        card_h = self.header_height + (num_items * self.row_height) + self.padding

        # Posisi di pojok kanan atas
        card_x = screen_w - self.card_width - self.margin
        card_y = self.margin

        # 1. Background Card Panel
        card_surf = pygame.Surface((self.card_width, card_h), pygame.SRCALPHA)
        pygame.draw.rect(card_surf, COLOR_HUD_BG, (0, 0, self.card_width, card_h), border_radius=8)
        pygame.draw.rect(card_surf, COLOR_HUD_BORDER, (0, 0, self.card_width, card_h), width=1, border_radius=8)
        surface.blit(card_surf, (card_x, card_y))

        # 2. Header Title
        title_surf = self.font_title.render("RESOURCES", True, COLOR_TEXT_TITLE)
        surface.blit(title_surf, (card_x + self.padding, card_y + 10))

        # Garis pemisah tipis di bawah header
        pygame.draw.line(
            surface,
            COLOR_HUD_BORDER,
            (card_x + self.padding, card_y + 28),
            (card_x + self.card_width - self.padding, card_y + 28)
        )

        # 3. List Resource Items
        start_y = card_y + 36
        for i, (name, amount) in enumerate(resources.items()):
            row_y = start_y + (i * self.row_height)

            # Titik warna indikator resource
            dot_color = RESOURCE_COLORS.get(name, (200, 200, 200))
            dot_x = card_x + self.padding + 5
            dot_y = row_y + 8
            pygame.draw.circle(surface, dot_color, (dot_x, dot_y), 4)

            # Label nama resource
            lbl_surf = self.font_item.render(name, True, COLOR_TEXT_MAIN)
            surface.blit(lbl_surf, (card_x + self.padding + 16, row_y))

            # Jumlah resource (rata kanan)
            val_surf = self.font_val.render(str(amount), True, COLOR_TEXT_MAIN)
            val_x = card_x + self.card_width - self.padding - val_surf.get_width()
            surface.blit(val_surf, (val_x, row_y))
