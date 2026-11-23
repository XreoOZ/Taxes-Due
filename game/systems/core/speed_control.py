"""
Speed & Time Control System (Pause, Very Slow, Slow, Normal, Fast, Very Fast)
Shortcut keys: Space (Pause), 1 (Very Slow), 2 (Slow), 3 (Normal), 4 (Fast), 5 (Very Fast)
"""

import pygame
from game.config import (
    SPEED_LEVELS,
    DEFAULT_SPEED_INDEX,
    COLOR_HUD_BG,
    COLOR_HUD_BORDER,
    SPEED_CONTROL_UI,
)

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
            self.font_btn = pygame.font.SysFont("Segoe UI", SPEED_CONTROL_UI["font_button"], bold=True)
            self.font_sub = pygame.font.SysFont("Segoe UI", SPEED_CONTROL_UI["font_sub"], bold=True)
            self.font_paused = pygame.font.SysFont("Segoe UI", SPEED_CONTROL_UI["font_paused"], bold=True)

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
            for index, level in enumerate(self.levels):
                if event.key == pygame.key.key_code(level["key_label"]):
                    self.set_speed_by_index(index)
                    return f"speed_{level['id']}"

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
        ui = SPEED_CONTROL_UI
        colors = ui["colors"]
        speed_count = len(self.levels)
        required_width = (
            ui["panel_padding_x"] + ui["pause_button_width"] + ui["pause_speed_gap"]
            + speed_count * ui["speed_button_width"]
            + max(0, speed_count - 1) * ui["speed_button_gap"]
            + ui["right_padding"]
        )
        panel_w = max(ui["panel_min_width"], required_width)
        panel_h = ui["panel_height"]
        panel_x = max(0, screen_w - panel_w - ui["panel_margin_x"])
        panel_y = max(0, screen_h - panel_h - ui["panel_margin_y"])

        # Background panel
        bg_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(bg_surf, COLOR_HUD_BG, (0, 0, panel_w, panel_h), border_radius=ui["panel_border_radius"])
        pygame.draw.rect(bg_surf, COLOR_HUD_BORDER, (0, 0, panel_w, panel_h), width=1,
                         border_radius=ui["panel_border_radius"])
        surface.blit(bg_surf, (panel_x, panel_y))

        mouse_pos = pygame.mouse.get_pos()
        btn_y = panel_y + ui["panel_padding_y"]
        btn_h = ui["button_height"]

        # 1. Tombol Pause (Space)
        pause_w = ui["pause_button_width"]
        self.pause_btn_rect = pygame.Rect(panel_x + ui["panel_padding_x"], btn_y, pause_w, btn_h)

        if self.is_paused:
            p_bg = colors["paused_bg"]
            p_border = colors["paused_border"]
            p_txt_col = colors["paused_text"]
        else:
            is_hover = self.pause_btn_rect.collidepoint(mouse_pos)
            p_bg = colors["pause_hover_bg"] if is_hover else colors["idle_bg"]
            p_border = colors["idle_border"]
            p_txt_col = colors["pause_text"]

        pygame.draw.rect(surface, p_bg, self.pause_btn_rect, border_radius=ui["button_border_radius"])
        pygame.draw.rect(surface, p_border, self.pause_btn_rect, width=1,
                         border_radius=ui["button_border_radius"])

        p_lbl = self.font_btn.render("⏸ Spc", True, p_txt_col)
        surface.blit(p_lbl, (self.pause_btn_rect.x + (pause_w - p_lbl.get_width()) // 2,
                             self.pause_btn_rect.y + ui["button_text_y"]))

        # 2. Tombol-tombol Kecepatan (1 s/d 5)
        self.speed_btn_rects = []
        cur_x = self.pause_btn_rect.right + ui["pause_speed_gap"]
        speed_btn_w = ui["speed_button_width"]

        for i, lvl in enumerate(self.levels):
            rect = pygame.Rect(cur_x, btn_y, speed_btn_w, btn_h)
            self.speed_btn_rects.append(rect)

            is_active = (not self.is_paused) and (i == self.active_index)
            is_hover = rect.collidepoint(mouse_pos)

            if is_active:
                btn_bg = colors["active_bg"]
                btn_border = colors["active_border"]
                txt_col = colors["paused_text"]
            elif is_hover:
                btn_bg = colors["hover_bg"]
                btn_border = colors["hover_border"]
                txt_col = colors["hover_text"]
            else:
                btn_bg = colors["idle_bg"]
                btn_border = colors["idle_border"]
                txt_col = colors["idle_text"]

            pygame.draw.rect(surface, btn_bg, rect, border_radius=ui["button_border_radius"])
            pygame.draw.rect(surface, btn_border, rect, width=1,
                             border_radius=ui["button_border_radius"])

            # Key label & Speed multiplier
            main_txt = self.font_btn.render(f"{lvl['key_label']}:{lvl['short_label']}", True, txt_col)
            surface.blit(main_txt, (rect.x + (speed_btn_w - main_txt.get_width()) // 2,
                                    rect.y + ui["button_text_y"]))

            cur_x += speed_btn_w + ui["speed_button_gap"]

        # 3. Indikator Visual Jika Sedang Pause
        if self.is_paused:
            tag_w = ui["pause_tag_width"]
            tag_h = ui["pause_tag_height"]
            pause_tag_surf = pygame.Surface((tag_w, tag_h), pygame.SRCALPHA)
            pygame.draw.rect(pause_tag_surf, colors["paused_tag"], (0, 0, tag_w, tag_h),
                             border_radius=ui["button_border_radius"])
            pause_txt = self.font_paused.render("PAUSED (Space)", True, colors["paused_text"])
            pause_tag_surf.blit(pause_txt, (ui["pause_tag_x_padding"], ui["pause_tag_text_y"]))
            surface.blit(pause_tag_surf, (screen_w // 2 - tag_w // 2, ui["pause_tag_y"]))
