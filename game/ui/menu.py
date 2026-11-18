"""
Main Menu System (Dynamic & Responsive)
"""

import pygame
from game.config import (
    DAY_LENGTH_OPTIONS,
    DEFAULT_DAY_LENGTH_INDEX,
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED
)

class MainMenu:
    def __init__(self):
        # Struktur menu yang dinamis (bisa ditambah/diubah dengan mudah)
        self.items = [
            {"id": "play", "label": "Start a New", "enabled": True},
            {"id": "load", "label": "Load Game", "enabled": True},
            {"id": "setting", "label": "Settings", "enabled": True},
            {"id": "exit", "label": "Exit Game", "enabled": True},
        ]
        
        # Dimensi dinamis tombol
        self.btn_width = 300
        self.btn_height = 54
        self.btn_spacing = 18

        # Cache rect untuk deteksi mouse hover/click
        self.btn_rects = []

        # New Game Day Duration Modal State
        self.show_day_modal = False
        self.selected_day_index = DEFAULT_DAY_LENGTH_INDEX
        self.modal_day_rects = []
        self.modal_start_btn_rect = None
        self.modal_cancel_btn_rect = None

        # Font lazily initialized
        self.title_font = None
        self.btn_font = None
        self.sub_font = None
        self.body_font = None

    def _init_fonts(self):
        if self.title_font is None:
            self.title_font = pygame.font.SysFont("Segoe UI", 48, bold=True)
            self.btn_font = pygame.font.SysFont("Segoe UI", 20, bold=True)
            self.sub_font = pygame.font.SysFont("Segoe UI", 16, bold=True)
            self.body_font = pygame.font.SysFont("Segoe UI", 13)

    def _compute_layout(self, screen_w, screen_h):
        """Menghitung posisi tombol secara dinamis di tengah layar"""
        total_menu_height = len(self.items) * self.btn_height + (len(self.items) - 1) * self.btn_spacing
        start_y = (screen_h - total_menu_height) // 2 + 40
        center_x = screen_w // 2

        rects = []
        for i in range(len(self.items)):
            x = center_x - self.btn_width // 2
            y = start_y + i * (self.btn_height + self.btn_spacing)
            rects.append(pygame.Rect(x, y, self.btn_width, self.btn_height))
        
        self.btn_rects = rects

    def handle_event(self, event):
        """Mengembalikan action id ('play', 'exit', dll) jika tombol diklik"""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos

            # Jika New Game Day Length modal sedang aktif
            if self.show_day_modal:
                # Opsi Day Length (10, 20, 30 menit)
                for i, rect in enumerate(self.modal_day_rects):
                    if rect.collidepoint(mouse_pos):
                        self.selected_day_index = i
                        return None

                # Tombol Begin Settlement
                if self.modal_start_btn_rect and self.modal_start_btn_rect.collidepoint(mouse_pos):
                    self.show_day_modal = False
                    return f"start_game_{self.selected_day_index}"

                # Tombol Cancel
                if self.modal_cancel_btn_rect and self.modal_cancel_btn_rect.collidepoint(mouse_pos):
                    self.show_day_modal = False
                    return None

                return None

            # Menu Utama
            for i, rect in enumerate(self.btn_rects):
                if rect.collidepoint(mouse_pos):
                    item = self.items[i]
                    if item["enabled"]:
                        if item["id"] == "play":
                            self.show_day_modal = True
                            return None
                        return item["id"]
        return None

    def draw(self, surface):
        self._init_fonts()
        screen_w, screen_h = surface.get_size()
        self._compute_layout(screen_w, screen_h)

        # Background Menu
        surface.fill((15, 23, 42))

        # Title
        title_surf = self.title_font.render("VILLAGE BUILDER", True, (56, 189, 248))
        title_rect = title_surf.get_rect(center=(screen_w // 2, self.btn_rects[0].top - 80))
        surface.blit(title_surf, title_rect)

        mouse_pos = pygame.mouse.get_pos()

        # Render setiap tombol secara dinamis
        for i, item in enumerate(self.items):
            rect = self.btn_rects[i]
            is_enabled = item["enabled"]
            is_hovered = rect.collidepoint(mouse_pos) and is_enabled and not self.show_day_modal

            # Warna tombol
            if not is_enabled:
                bg_color = (30, 41, 59, 120)
                border_color = (51, 65, 85)
                text_color = (100, 116, 139)
            elif is_hovered:
                bg_color = (37, 99, 235)
                border_color = (96, 165, 250)
                text_color = (255, 255, 255)
            else:
                bg_color = (30, 41, 59)
                border_color = (71, 85, 105)
                text_color = (226, 232, 240)

            # Gambar background tombol
            pygame.draw.rect(surface, bg_color, rect, border_radius=8)
            pygame.draw.rect(surface, border_color, rect, width=2, border_radius=8)

            # Render teks tombol tepat di tengah
            text_surf = self.btn_font.render(item["label"], True, text_color)
            text_rect = text_surf.get_rect(center=rect.center)
            surface.blit(text_surf, text_rect)

        # -----------------------------------------------------------------
        # MODAL: Pilih Durasi Hari untuk Game Baru (10 / 20 / 30 Menit)
        # -----------------------------------------------------------------
        if self.show_day_modal:
            dim_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
            dim_surf.fill((0, 0, 0, 180))
            surface.blit(dim_surf, (0, 0))

            mw = 560
            mh = 380
            mx = (screen_w - mw) // 2
            my = (screen_h - mh) // 2

            modal_surf = pygame.Surface((mw, mh), pygame.SRCALPHA)
            pygame.draw.rect(modal_surf, COLOR_MODAL_BG, (0, 0, mw, mh), border_radius=14)
            pygame.draw.rect(modal_surf, (56, 189, 248), (0, 0, mw, mh), width=2, border_radius=14)
            surface.blit(modal_surf, (mx, my))

            # Header
            t_surf = self.sub_font.render("☀️ START A NEW SETTLEMENT", True, COLOR_TEXT_TITLE)
            surface.blit(t_surf, (mx + 28, my + 24))

            sub_desc = self.body_font.render("Select real-world duration for each 24-hour in-game day:", True, COLOR_TEXT_MUTED)
            surface.blit(sub_desc, (mx + 28, my + 54))

            pygame.draw.line(surface, COLOR_MODAL_BORDER, (mx + 24, my + 82), (mx + mw - 24, my + 82))

            # Option Cards (10 Min, 20 Min, 30 Min)
            self.modal_day_rects = []
            opt_descriptions = [
                ("10 Minutes / Day", "Fast Pace — Quick day/night shifts, brisk village simulation."),
                ("20 Minutes / Day", "Normal Pace (Recommended) — Balanced daily workflow for farmers."),
                ("30 Minutes / Day", "Slow Pace — Relaxed, deep management with prolonged daylight.")
            ]

            card_y = my + 98
            for i, opt in enumerate(DAY_LENGTH_OPTIONS):
                c_rect = pygame.Rect(mx + 28, card_y, mw - 56, 58)
                self.modal_day_rects.append(c_rect)

                is_sel = (i == self.selected_day_index)
                c_hover = c_rect.collidepoint(mouse_pos)

                if is_sel:
                    c_bg = (16, 185, 129, 60)
                    c_border = (16, 185, 129)
                    dot_c = (52, 211, 153)
                elif c_hover:
                    c_bg = (30, 41, 59)
                    c_border = (96, 165, 250)
                    dot_c = (148, 163, 184)
                else:
                    c_bg = (20, 29, 45)
                    c_border = (51, 65, 85)
                    dot_c = (71, 85, 105)

                pygame.draw.rect(surface, c_bg, c_rect, border_radius=8)
                pygame.draw.rect(surface, c_border, c_rect, width=2 if is_sel else 1, border_radius=8)

                # Radio circle
                r_cx = c_rect.x + 22
                r_cy = c_rect.y + c_rect.h // 2
                pygame.draw.circle(surface, dot_c, (r_cx, r_cy), 8, width=0 if is_sel else 2)
                if is_sel:
                    pygame.draw.circle(surface, (255, 255, 255), (r_cx, r_cy), 3)

                # Option title & description
                o_title, o_desc = opt_descriptions[i]
                t_color = (255, 255, 255) if is_sel else (226, 232, 240)
                surface.blit(self.sub_font.render(o_title, True, t_color), (c_rect.x + 42, c_rect.y + 10))
                surface.blit(self.body_font.render(o_desc, True, (148, 163, 184)), (c_rect.x + 42, c_rect.y + 32))

                card_y += 68

            # Action Buttons: [Begin Settlement] and [Cancel]
            btn_w = 190
            btn_h = 42
            by = my + mh - 58

            self.modal_start_btn_rect = pygame.Rect(mx + mw - btn_w - 28, by, btn_w, btn_h)
            b_hover = self.modal_start_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (16, 185, 129) if b_hover else (5, 150, 105), self.modal_start_btn_rect, border_radius=8)
            st_txt = self.sub_font.render("▶ Begin Settlement", True, (255, 255, 255))
            surface.blit(st_txt, (self.modal_start_btn_rect.centerx - st_txt.get_width() // 2, self.modal_start_btn_rect.centery - st_txt.get_height() // 2))

            cancel_w = 110
            self.modal_cancel_btn_rect = pygame.Rect(mx + 28, by, cancel_w, btn_h)
            c_hover = self.modal_cancel_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (51, 65, 85) if c_hover else (30, 41, 59), self.modal_cancel_btn_rect, border_radius=8)
            pygame.draw.rect(surface, (71, 85, 105), self.modal_cancel_btn_rect, width=1, border_radius=8)
            cn_txt = self.sub_font.render("✕ Cancel", True, (203, 213, 225))
            surface.blit(cn_txt, (self.modal_cancel_btn_rect.centerx - cn_txt.get_width() // 2, self.modal_cancel_btn_rect.centery - cn_txt.get_height() // 2))
