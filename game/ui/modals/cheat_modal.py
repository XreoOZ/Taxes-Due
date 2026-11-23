"""
Cheat Modal System (ESC menu → Active Cheat → password gate)

Unlocks cheat features (Add Item, Add Family) for the session.
Password lives in game.data.config.CHEAT_PASSWORD.
"""

import pygame
from game.config import (
    CHEAT_PASSWORD,
    CHEAT_MODAL_WIDTH,
    CHEAT_MODAL_HEIGHT,
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
)


class CheatModal:
    def __init__(self):
        self.is_open = False
        self.modal_w = CHEAT_MODAL_WIDTH
        self.modal_h = CHEAT_MODAL_HEIGHT
        self.mode = "menu"  # "menu" | "password"
        self.password_input = ""
        self.error_msg = ""
        self.active_btn_rect = None
        self.deactivate_btn_rect = None
        self.unlock_btn_rect = None
        self.session_btn_rects = {}
        self.close_btn_rect = pygame.Rect(0, 0, 24, 24)
        self.font_title = None
        self.font_sub = None
        self.font_body = None
        self.font_btn = None

    def _init_fonts(self):
        if self.font_title is None:
            self.font_title = pygame.font.SysFont("Segoe UI", 16, bold=True)
            self.font_sub = pygame.font.SysFont("Segoe UI", 13, bold=True)
            self.font_body = pygame.font.SysFont("Segoe UI", 11)
            self.font_btn = pygame.font.SysFont("Segoe UI", 12, bold=True)

    def open(self):
        self.is_open = True
        self.mode = "menu"
        self.password_input = ""
        self.error_msg = ""

    def close(self):
        self.is_open = False
        self.mode = "menu"
        self.password_input = ""
        self.error_msg = ""

    def _submit_password(self):
        if self.password_input == CHEAT_PASSWORD:
            self.close()
            return "activate_cheats"
        self.error_msg = "Wrong password."
        self.password_input = ""
        return None

    def handle_event(self, event, cheats_active=False):
        """Returns 'activate_cheats' / 'deactivate_cheats' / None."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.mode == "password":
                self.mode = "menu"
                self.password_input = ""
                self.error_msg = ""
            else:
                self.close()
            return None

        if self.mode == "password":
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return self._submit_password()
                if event.key == pygame.K_BACKSPACE:
                    self.password_input = self.password_input[:-1]
                elif event.unicode and event.unicode.isprintable() and len(self.password_input) < 64:
                    self.password_input += event.unicode
            return None

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        mouse_pos = event.pos
        if self.close_btn_rect.collidepoint(mouse_pos):
            self.close()
            return None
        for action, rect in self.session_btn_rects.items():
            if rect and rect.collidepoint(mouse_pos):
                self.close()
                return action
        if cheats_active and self.deactivate_btn_rect and self.deactivate_btn_rect.collidepoint(mouse_pos):
            self.close()
            return "deactivate_cheats"
        if not cheats_active and self.active_btn_rect and self.active_btn_rect.collidepoint(mouse_pos):
            self.mode = "password"
            self.password_input = ""
            self.error_msg = ""
        return None

    def draw(self, surface, cheats_active=False):
        if not self.is_open:
            return

        self._init_fonts()
        screen_w, screen_h = surface.get_size()

        dim_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        dim_surf.fill((0, 0, 0, 140))
        surface.blit(dim_surf, (0, 0))

        mx = (screen_w - self.modal_w) // 2
        my = (screen_h - self.modal_h) // 2

        modal_surf = pygame.Surface((self.modal_w, self.modal_h), pygame.SRCALPHA)
        pygame.draw.rect(modal_surf, COLOR_MODAL_BG, (0, 0, self.modal_w, self.modal_h), border_radius=12)
        pygame.draw.rect(modal_surf, COLOR_MODAL_BORDER, (0, 0, self.modal_w, self.modal_h), width=2, border_radius=12)
        surface.blit(modal_surf, (mx, my))

        mouse_pos = pygame.mouse.get_pos()
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - 36, my + 14, 22, 22)
        c_hover = self.close_btn_rect.collidepoint(mouse_pos)
        c_col = (239, 68, 68) if c_hover else COLOR_TEXT_MUTED
        c_surf = self.font_btn.render("X", True, c_col)
        surface.blit(c_surf, (self.close_btn_rect.x + 5, self.close_btn_rect.y + 1))

        title = self.font_title.render("ESC MENU", True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + 20, my + 16))
        pygame.draw.line(surface, COLOR_MODAL_BORDER, (mx + 20, my + 48), (mx + self.modal_w - 20, my + 48))

        cy = my + 62
        if self.mode == "password":
            lbl = self.font_sub.render("Enter Cheat Password", True, COLOR_TEXT_TITLE)
            surface.blit(lbl, (mx + 24, cy))

            box = pygame.Rect(mx + 24, cy + 26, self.modal_w - 48, 34)
            pygame.draw.rect(surface, (20, 29, 45), box, border_radius=6)
            pygame.draw.rect(surface, COLOR_MODAL_BORDER, box, width=1, border_radius=6)
            masked = "•" * len(self.password_input)
            txt = self.font_body.render(masked if masked else "type password...", True,
                                        COLOR_TEXT_MAIN if masked else COLOR_TEXT_MUTED)
            surface.blit(txt, (box.x + 10, box.centery - txt.get_height() // 2))

            if self.error_msg:
                err = self.font_body.render(self.error_msg, True, (239, 68, 68))
                surface.blit(err, (mx + 24, box.bottom + 8))

            self.unlock_btn_rect = pygame.Rect(mx + self.modal_w // 2 - 70, self.modal_h + my - 62, 140, 32)
            u_hover = self.unlock_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (16, 185, 129) if u_hover else (5, 150, 105),
                             self.unlock_btn_rect, border_radius=6)
            u_txt = self.font_btn.render("Unlock", True, (255, 255, 255))
            surface.blit(u_txt, (self.unlock_btn_rect.centerx - u_txt.get_width() // 2,
                                 self.unlock_btn_rect.centery - u_txt.get_height() // 2))
            hint = self.font_body.render("Press ENTER to submit, ESC to go back", True, COLOR_TEXT_MUTED)
            surface.blit(hint, (mx + 24, my + self.modal_h - 30))
        else:
            status_col = (34, 197, 94) if cheats_active else (148, 163, 184)
            status = "ACTIVE" if cheats_active else "LOCKED"
            st = self.font_sub.render(f"Cheats: {status}", True, status_col)
            surface.blit(st, (mx + 24, cy))

            note = self.font_body.render(
                "Unlocks Add Item & Add Family buttons." if not cheats_active
                else "Cheat features are enabled this session.",
                True, COLOR_TEXT_MUTED)
            surface.blit(note, (mx + 24, cy + 22))

            # Session action buttons (same set as the old ESC settings menu)
            surface.blit(self.font_sub.render("Session Actions:", True, COLOR_TEXT_TITLE), (mx + 24, cy + 48))
            bx = mx + 24
            by = cy + 74
            bw = 100
            bh = 32
            gap = 8
            session_defs = [
                ("unpause_game", "Resume", (16, 185, 129), (5, 150, 105)),
                ("open_save_modal", "Save", (37, 99, 235), (30, 58, 138)),
                ("open_load_modal", "Load", (234, 179, 8), (180, 83, 9)),
                ("open_help_modal", "Help", (14, 165, 233), (29, 78, 216)),
                ("return_to_main_menu", "Menu", (239, 68, 68), (185, 28, 28)),
            ]
            self.session_btn_rects = {}
            for action, label, hov_col, base_col in session_defs:
                rect = pygame.Rect(bx, by, bw, bh)
                self.session_btn_rects[action] = rect
                hover = rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, hov_col if hover else base_col, rect, border_radius=6)
                txt = self.font_btn.render(label, True, (255, 255, 255))
                surface.blit(txt, (rect.centerx - txt.get_width() // 2,
                                   rect.centery - txt.get_height() // 2))
                bx += bw + gap

            # Cheat unlock / deactivate button
            cby = by + bh + 22
            if cheats_active:
                self.deactivate_btn_rect = pygame.Rect(mx + self.modal_w // 2 - 90, cby, 180, 34)
                d_hover = self.deactivate_btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (239, 68, 68) if d_hover else (185, 28, 28),
                                 self.deactivate_btn_rect, border_radius=6)
                d_txt = self.font_btn.render("Deactivate Cheats", True, (255, 255, 255))
                surface.blit(d_txt, (self.deactivate_btn_rect.centerx - d_txt.get_width() // 2,
                                     self.deactivate_btn_rect.centery - d_txt.get_height() // 2))
            else:
                self.active_btn_rect = pygame.Rect(mx + self.modal_w // 2 - 90, cby, 180, 34)
                a_hover = self.active_btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (245, 158, 11) if a_hover else (180, 83, 9),
                                 self.active_btn_rect, border_radius=6)
                a_txt = self.font_btn.render("Active Cheat", True, (255, 255, 255))
                surface.blit(a_txt, (self.active_btn_rect.centerx - a_txt.get_width() // 2,
                                     self.active_btn_rect.centery - a_txt.get_height() // 2))
                hint = self.font_body.render("You'll be asked for a password.", True, COLOR_TEXT_MUTED)
                surface.blit(hint, (mx + 24, my + self.modal_h - 30))
