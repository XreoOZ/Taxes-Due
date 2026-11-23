"""
Settings Modal System (Configurable Day Length & Mockup Feature Settings)
"""
from game.ui.ui_theme import ui_font, upx

import pygame
from game.config import (
    DAY_LENGTH_OPTIONS,
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_BADGE_WIP,
    SETTINGS_MODAL_WIDTH,
    SETTINGS_MODAL_HEIGHT
)

class SettingsModal:
    def __init__(self):
        self.is_open = False
        self.modal_w = SETTINGS_MODAL_WIDTH
        self.modal_h = SETTINGS_MODAL_HEIGHT + 30

        # Day length button rects
        self.day_btn_rects = []
        self.close_btn_rect = pygame.Rect(0, 0, 24, 24)

        # In-game Action Buttons
        self.btn_unpause_rect = None
        self.btn_save_rect = None
        self.btn_load_rect = None
        self.btn_main_menu_rect = None

        # In-game HUD Settings Button
        self.hud_btn_rect = pygame.Rect(16, 58, 110, 32)

        # Mockup Settings List (Format: "nama fitur WIP")
        self.wip_features = [
            {"name": "Audio & Sound Effects WIP", "desc": "Adjust master sound effects volume."},
            {"name": "Background Music WIP", "desc": "Atmospheric village music and ambient audio."},
            {"name": "Display & Fullscreen WIP", "desc": "Toggle fullscreen mode and render resolution."},
            {"name": "Auto-Save Interval WIP", "desc": "Frequency of automatic game state saves."},
            {"name": "Custom Keybindings WIP", "desc": "Remap keyboard shortcuts and controls."},
        ]

        self.font_title = None
        self.font_sub = None
        self.font_body = None
        self.font_badge = None
        self.font_btn = None

    def _init_fonts(self):
        if self.font_title is None:
            self.font_title = ui_font(16, bold=True)
            self.font_sub = ui_font(13, bold=True)
            self.font_body = ui_font(11)
            self.font_badge = ui_font(10, bold=True)
            self.font_btn = ui_font(12, bold=True)

    def open(self, is_ingame=False):
        self.is_open = True

    def close(self):
        self.is_open = False

    def toggle(self):
        self.is_open = not self.is_open

    def handle_event(self, event, day_cycle, is_ingame=False):
        """Menangani klik mouse pada tombol HUD setting, modal close, dan pilihan day length"""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.is_open:
            self.is_open = False
            return "close_settings"

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos

            # 1. In-game HUD Button "⚙ Settings"
            if not self.is_open and self.hud_btn_rect.collidepoint(mouse_pos):
                self.is_open = True
                return "open_settings"

            if not self.is_open:
                return None

            # 2. Close Button (X)
            if self.close_btn_rect.collidepoint(mouse_pos):
                self.is_open = False
                return "close_settings"

            # 3. In-Game Action Buttons
            if is_ingame:
                if self.btn_unpause_rect and self.btn_unpause_rect.collidepoint(mouse_pos):
                    self.is_open = False
                    return "unpause_game"
                if self.btn_save_rect and self.btn_save_rect.collidepoint(mouse_pos):
                    return "open_save_modal"
                if self.btn_load_rect and self.btn_load_rect.collidepoint(mouse_pos):
                    return "open_load_modal"
                if self.btn_main_menu_rect and self.btn_main_menu_rect.collidepoint(mouse_pos):
                    self.is_open = False
                    return "return_to_main_menu"

        return None

    def draw_hud_button(self, surface):
        """Gambar tombol ⚙ Settings di HUD samping kiri (di bawah clock)"""
        self._init_fonts()
        mouse_pos = pygame.mouse.get_pos()
        hover = self.hud_btn_rect.collidepoint(mouse_pos)

        btn_bg = (40, 56, 80) if hover else (30, 41, 59, 230)
        pygame.draw.rect(surface, btn_bg, self.hud_btn_rect, border_radius=6)
        pygame.draw.rect(surface, (71, 85, 105), self.hud_btn_rect, width=1, border_radius=6)

        lbl = self.font_btn.render("Settings", True, (241, 245, 249))
        surface.blit(lbl, (self.hud_btn_rect.x + (self.hud_btn_rect.w - lbl.get_width()) // 2, self.hud_btn_rect.y + 6))

    def draw(self, surface, day_cycle, is_ingame=False):
        """Render Modal Settings Dialog"""
        if not self.is_open:
            return

        self._init_fonts()
        screen_w, screen_h = surface.get_size()

        # Modal Overlay Dimming
        dim_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        dim_surf.fill((0, 0, 0, 140))
        surface.blit(dim_surf, (0, 0))

        # Modal Card
        mx = (screen_w - self.modal_w) // 2
        my = (screen_h - self.modal_h) // 2

        modal_surf = pygame.Surface((self.modal_w, self.modal_h), pygame.SRCALPHA)
        pygame.draw.rect(modal_surf, COLOR_MODAL_BG, (0, 0, self.modal_w, self.modal_h), border_radius=12)
        pygame.draw.rect(modal_surf, COLOR_MODAL_BORDER, (0, 0, self.modal_w, self.modal_h), width=2, border_radius=12)
        surface.blit(modal_surf, (mx, my))

        # Title
        title_str = "GAME PAUSED & SETTINGS" if is_ingame else "GAME SETTINGS"
        title_surf = self.font_title.render(title_str, True, COLOR_TEXT_TITLE)
        surface.blit(title_surf, (mx + 20, my + 16))

        # Close Button (X)
        mouse_pos = pygame.mouse.get_pos()
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - 36, my + 14, 22, 22)
        c_hover = self.close_btn_rect.collidepoint(mouse_pos)
        c_col = (239, 68, 68) if c_hover else COLOR_TEXT_MUTED
        c_surf = self.font_btn.render("X", True, c_col)
        surface.blit(c_surf, (self.close_btn_rect.x + 5, self.close_btn_rect.y + 1))

        pygame.draw.line(surface, COLOR_MODAL_BORDER, (mx + 20, my + 48), (mx + self.modal_w - 20, my + 48))

        # -------------------------------------------------------------
        # 1. In-Game Session Controls Bar (Resume, Save, Load, Menu)
        # -------------------------------------------------------------
        act_y = my + 58
        if is_ingame:
            surface.blit(self.font_sub.render("Session Actions:", True, COLOR_TEXT_TITLE), (mx + 24, act_y))

            bx = mx + 24
            by = act_y + 26
            bw = 135
            bh = 34

            # 1. Unpause
            self.btn_unpause_rect = pygame.Rect(bx, by, bw, bh)
            u_hover = self.btn_unpause_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (16, 185, 129) if u_hover else (5, 150, 105), self.btn_unpause_rect, border_radius=6)
            u_txt = self.font_btn.render("Resume", True, (255, 255, 255))
            surface.blit(u_txt, (self.btn_unpause_rect.centerx - u_txt.get_width() // 2, self.btn_unpause_rect.centery - u_txt.get_height() // 2))

            # 2. Save
            bx += bw + 12
            self.btn_save_rect = pygame.Rect(bx, by, bw, bh)
            s_hover = self.btn_save_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (37, 99, 235) if s_hover else (30, 58, 138), self.btn_save_rect, border_radius=6)
            s_txt = self.font_btn.render("Save Game", True, (255, 255, 255))
            surface.blit(s_txt, (self.btn_save_rect.centerx - s_txt.get_width() // 2, self.btn_save_rect.centery - s_txt.get_height() // 2))

            # 3. Load
            bx += bw + 12
            self.btn_load_rect = pygame.Rect(bx, by, bw, bh)
            l_hover = self.btn_load_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (234, 179, 8) if l_hover else (180, 83, 9), self.btn_load_rect, border_radius=6)
            l_txt = self.font_btn.render("Load Game", True, (255, 255, 255))
            surface.blit(l_txt, (self.btn_load_rect.centerx - l_txt.get_width() // 2, self.btn_load_rect.centery - l_txt.get_height() // 2))

            # 4. Main Menu
            bx += bw + 12
            self.btn_main_menu_rect = pygame.Rect(bx, by, bw, bh)
            m_hover = self.btn_main_menu_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (239, 68, 68) if m_hover else (185, 28, 28), self.btn_main_menu_rect, border_radius=6)
            m_txt = self.font_btn.render("Main Menu", True, (255, 255, 255))
            surface.blit(m_txt, (self.btn_main_menu_rect.centerx - m_txt.get_width() // 2, self.btn_main_menu_rect.centery - m_txt.get_height() // 2))

            wip_y = by + bh + 14
        else:
            self.btn_unpause_rect = None
            self.btn_save_rect = None
            self.btn_load_rect = None
            self.btn_main_menu_rect = None
            wip_y = my + 58

        # -------------------------------------------------------------
        # 2. SECTION: Mockup Settings ("nama fitur WIP")
        # -------------------------------------------------------------
        pygame.draw.line(surface, (51, 65, 85), (mx + 24, wip_y), (mx + self.modal_w - 24, wip_y))

        wip_title = self.font_sub.render("Additional Settings (Future Features):", True, COLOR_TEXT_TITLE)
        surface.blit(wip_title, (mx + 24, wip_y + 10))

        row_y = wip_y + 34
        for item in self.wip_features:
            # Row Background
            row_rect = pygame.Rect(mx + 24, row_y, self.modal_w - 48, 32)
            pygame.draw.rect(surface, (20, 29, 45), row_rect, border_radius=6)
            pygame.draw.rect(surface, (40, 53, 75), row_rect, width=1, border_radius=6)

            # Feature Name
            name_surf = self.font_body.render(item["name"], True, COLOR_TEXT_MAIN)
            surface.blit(name_surf, (row_rect.x + 12, row_rect.y + 7))

            # WIP Badge
            wip_badge_rect = pygame.Rect(row_rect.right - 54, row_rect.y + 6, 42, 18)
            pygame.draw.rect(surface, COLOR_BADGE_WIP, wip_badge_rect, border_radius=4)
            w_txt = self.font_badge.render("WIP", True, (0, 0, 0))
            surface.blit(w_txt, (wip_badge_rect.x + (wip_badge_rect.w - w_txt.get_width()) // 2, wip_badge_rect.y + 2))

            row_y += 38
