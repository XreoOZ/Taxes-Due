"""
Speed & Time Control System (Pause, Very Slow, Slow, Normal, Fast, Very Fast)
Shortcut keys: Space (Pause), 1 (Very Slow), 2 (Slow), 3 (Normal), 4 (Fast), 5 (Very Fast)
"""

import pygame
from game.config import SPEED_LEVELS, DEFAULT_SPEED_INDEX, COLOR_HUD_BG, COLOR_HUD_BORDER

class SpeedController:
    def __init__(self):
        self.levels = SPEED_LEVELS
        self.active_index = DEFAULT_SPEED_INDEX  # Index 2: Normal (1.0x)
        self.is_paused = False

        self.font_btn = None
        self.font_sub = None
        self.font_paused = None

        # Cache button rects for click detection
        self.pause_btn_rect = pygame.Rect(0, 0, 0, 0)
        self.speed_btn_rects = []

    def _init_fonts(self):
        if self.font_btn is None:
            self.font_btn = pygame.font.SysFont("Segoe UI", 12, bold=True)
            self.font_sub = pygame.font.SysFont("Segoe UI", 9, bold=True)
            self.font_paused = pygame.font.SysFont("Segoe UI", 14, bold=True)

    def get_multiplier(self):
        """Mengembalikan pengali kecepatan game aktual (0.0 jika pause)"""
        if self.is_paused:
            return 0.0
        return self.levels[self.active_index]["speed"]

    def get_game_dt(self, real_dt):
        """Mengembalikan delta time yang telah diskalakan dengan kecepatan game"""
        return real_dt * self.get_multiplier()

    def toggle_pause(self):
        self.is_paused = not self.is_paused

    def set_speed_by_index(self, index):
        if 0 <= index < len(self.levels):
            self.active_index = index
            self.is_paused = False

    def handle_event(self, event):
        """Menangani shortcut keyboard (Space, 1, 2, 3, 4, 5) dan klik tombol mouse"""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                self.toggle_pause()
                return "toggle_pause"
            elif event.key == pygame.K_1:
                self.set_speed_by_index(0)  # Very Slow
                return "speed_very_slow"
            elif event.key == pygame.K_2:
                self.set_speed_by_index(1)  # Slow
                return "speed_slow"
            elif event.key == pygame.K_3:
                self.set_speed_by_index(2)  # Normal
                return "speed_normal"
            elif event.key == pygame.K_4:
                self.set_speed_by_index(3)  # Fast
                return "speed_fast"
            elif event.key == pygame.K_5:
                self.set_speed_by_index(4)  # Very Fast
                return "speed_very_fast"

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            m_pos = event.pos
            if self.pause_btn_rect.collidepoint(m_pos):
                self.toggle_pause()
                return "toggle_pause"

            for i, rect in enumerate(self.speed_btn_rects):
                if rect.collidepoint(m_pos):
                    self.set_speed_by_index(i)
                    return f"speed_{self.levels[i]['id']}"

        return None

    def draw(self, surface):
        """Render floating speed control HUD di pojok kanan bawah"""
        self._init_fonts()
        screen_w, screen_h = surface.get_size()

        # Ukuran dan posisi panel speed (Dihitung dinamis relatif terhadap resolusi layar)
        panel_w = 320
        panel_h = 46
        panel_x = screen_w - panel_w - 16
        panel_y = screen_h - panel_h - 14

        # Background panel
        bg_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(bg_surf, COLOR_HUD_BG, (0, 0, panel_w, panel_h), border_radius=8)
        pygame.draw.rect(bg_surf, COLOR_HUD_BORDER, (0, 0, panel_w, panel_h), width=1, border_radius=8)
        surface.blit(bg_surf, (panel_x, panel_y))

        mouse_pos = pygame.mouse.get_pos()
        btn_y = panel_y + 7
        btn_h = 32

        # 1. Tombol Pause (Space)
        pause_w = 58
        self.pause_btn_rect = pygame.Rect(panel_x + 8, btn_y, pause_w, btn_h)

        if self.is_paused:
            p_bg = (220, 38, 38)
            p_border = (239, 68, 68)
            p_txt_col = (255, 255, 255)
        else:
            is_hover = self.pause_btn_rect.collidepoint(mouse_pos)
            p_bg = (40, 56, 80) if is_hover else (30, 41, 59)
            p_border = (71, 85, 105)
            p_txt_col = (203, 213, 225)

        pygame.draw.rect(surface, p_bg, self.pause_btn_rect, border_radius=6)
        pygame.draw.rect(surface, p_border, self.pause_btn_rect, width=1, border_radius=6)

        p_lbl = self.font_btn.render("⏸ Spc", True, p_txt_col)
        surface.blit(p_lbl, (self.pause_btn_rect.x + (pause_w - p_lbl.get_width()) // 2, self.pause_btn_rect.y + 7))

        # 2. Tombol-tombol Kecepatan (1 s/d 5)
        self.speed_btn_rects = []
        cur_x = self.pause_btn_rect.right + 6
        speed_btn_w = 46

        for i, lvl in enumerate(self.levels):
            rect = pygame.Rect(cur_x, btn_y, speed_btn_w, btn_h)
            self.speed_btn_rects.append(rect)

            is_active = (not self.is_paused) and (i == self.active_index)
            is_hover = rect.collidepoint(mouse_pos)

            if is_active:
                btn_bg = (16, 185, 129)
                btn_border = (52, 211, 153)
                txt_col = (255, 255, 255)
            elif is_hover:
                btn_bg = (51, 65, 85)
                btn_border = (96, 165, 250)
                txt_col = (255, 255, 255)
            else:
                btn_bg = (30, 41, 59)
                btn_border = (71, 85, 105)
                txt_col = (148, 163, 184)

            pygame.draw.rect(surface, btn_bg, rect, border_radius=6)
            pygame.draw.rect(surface, btn_border, rect, width=1, border_radius=6)

            # Key label & Speed multiplier
            main_txt = self.font_btn.render(f"{lvl['key_label']}:{lvl['short_label']}", True, txt_col)
            surface.blit(main_txt, (rect.x + (speed_btn_w - main_txt.get_width()) // 2, rect.y + 7))

            cur_x += speed_btn_w + 4

        # 3. Indikator Visual Jika Sedang Pause
        if self.is_paused:
            pause_tag_surf = pygame.Surface((140, 28), pygame.SRCALPHA)
            pygame.draw.rect(pause_tag_surf, (220, 38, 38, 220), (0, 0, 140, 28), border_radius=6)
            pause_txt = self.font_paused.render("PAUSED (Space)", True, (255, 255, 255))
            pause_tag_surf.blit(pause_txt, (10, 4))
            surface.blit(pause_tag_surf, (screen_w // 2 - 70, 16))
