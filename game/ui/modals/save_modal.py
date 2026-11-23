"""
Save & Load Game Modal Dialog
Displays 3 configurable save slots with timestamp, population, day number, interactive save/load actions,
and atomic overwrite confirmation dialog.
"""

import pygame
from game.config import (
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED
)
from game.save_system import get_all_slots_meta

class SaveLoadModal:
    def __init__(self):
        self.is_open = False
        self.mode = "LOAD"  # "SAVE" or "LOAD"
        self.modal_w = 660
        self.modal_h = 470
        self.font_title = None
        self.font_sub = None
        self.font_body = None
        self.font_badge = None
        self.font_btn = None

        self.slot_action_btn_rects = {}  # slot_id -> Rect
        self.close_btn_rect = None
        self.status_message = None
        self.status_timer = 0.0
        self.cached_slots_meta = None

        # Overwrite Confirmation Dialog State
        self.confirming_overwrite_slot = None
        self.overwrite_confirm_btn_rect = None
        self.overwrite_cancel_btn_rect = None

    def _ensure_fonts(self):
        if self.font_title is None:
            self.font_title = pygame.font.SysFont("Segoe UI", 20, bold=True)
            self.font_sub = pygame.font.SysFont("Segoe UI", 14, bold=True)
            self.font_body = pygame.font.SysFont("Segoe UI", 12)
            self.font_badge = pygame.font.SysFont("Segoe UI", 11, bold=True)
            self.font_btn = pygame.font.SysFont("Segoe UI", 13, bold=True)

    def refresh_slots(self, message="Progress saved successfully!"):
        self.status_message = message
        self.status_timer = 3.5
        self.confirming_overwrite_slot = None
        self.cached_slots_meta = get_all_slots_meta()

    def open(self, mode="LOAD"):
        self.mode = mode
        self.is_open = True
        self.status_message = None
        self.confirming_overwrite_slot = None
        self.cached_slots_meta = get_all_slots_meta()

    def close(self):
        self.is_open = False
        self.confirming_overwrite_slot = None

    def handle_event(self, event):
        if not self.is_open:
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos

            # Priority 1: Overwrite confirmation dialog clicks
            if self.confirming_overwrite_slot is not None:
                if self.overwrite_confirm_btn_rect and self.overwrite_confirm_btn_rect.collidepoint(mouse_pos):
                    slot_id = self.confirming_overwrite_slot
                    self.confirming_overwrite_slot = None
                    return f"save_slot_{slot_id}"
                if self.overwrite_cancel_btn_rect and self.overwrite_cancel_btn_rect.collidepoint(mouse_pos):
                    self.confirming_overwrite_slot = None
                    return "cancel_overwrite"
                return "overwrite_dialog_blocked"

            # Close button (X)
            if self.close_btn_rect and self.close_btn_rect.collidepoint(mouse_pos):
                self.close()
                return "close_save_modal"

            # Slot buttons
            if self.cached_slots_meta is None:
                self.cached_slots_meta = get_all_slots_meta()
            slots_meta = {m["slot_id"]: m for m in self.cached_slots_meta}
            for slot_id, rect in list(self.slot_action_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    if self.mode == "SAVE":
                        meta = slots_meta.get(slot_id, {})
                        if not meta.get("is_empty", True):
                            # Slot is already occupied -> prompt confirmation before overwriting
                            self.confirming_overwrite_slot = slot_id
                            return f"prompt_overwrite_{slot_id}"
                        else:
                            return f"save_slot_{slot_id}"
                    else:
                        return f"load_slot_{slot_id}"

        return None

    def draw(self, surface):
        if not self.is_open:
            return

        self._ensure_fonts()
        screen_w, screen_h = surface.get_size()
        mouse_pos = pygame.mouse.get_pos()

        # Dim overlay
        dim_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        dim_surf.fill((0, 0, 0, 160))
        surface.blit(dim_surf, (0, 0))

        mx = (screen_w - self.modal_w) // 2
        my = (screen_h - self.modal_h) // 2

        # Card
        modal_surf = pygame.Surface((self.modal_w, self.modal_h), pygame.SRCALPHA)
        pygame.draw.rect(modal_surf, COLOR_MODAL_BG, (0, 0, self.modal_w, self.modal_h), border_radius=12)
        pygame.draw.rect(modal_surf, COLOR_MODAL_BORDER, (0, 0, self.modal_w, self.modal_h), width=2, border_radius=12)
        surface.blit(modal_surf, (mx, my))

        # Title
        title_str = "SAVE GAME (SELECT SLOT)" if self.mode == "SAVE" else "LOAD GAME (SELECT SLOT)"
        title_surf = self.font_title.render(title_str, True, COLOR_TEXT_TITLE)
        surface.blit(title_surf, (mx + 24, my + 18))

        sub_desc = "Select a slot to record your village progress:" if self.mode == "SAVE" else "Select a previous game record to load:"
        surface.blit(self.font_body.render(sub_desc, True, COLOR_TEXT_MUTED), (mx + 24, my + 44))

        # Close button (X)
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - 36, my + 16, 22, 22)
        close_hover = self.close_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (239, 68, 68) if close_hover else (30, 41, 59), self.close_btn_rect, border_radius=4)
        c_lbl = self.font_btn.render("X", True, (255, 255, 255))
        surface.blit(c_lbl, (self.close_btn_rect.centerx - c_lbl.get_width() // 2, self.close_btn_rect.centery - c_lbl.get_height() // 2))

        pygame.draw.line(surface, COLOR_MODAL_BORDER, (mx + 20, my + 68), (mx + self.modal_w - 20, my + 68))

        # Slots Rendering using cached metadata
        if self.cached_slots_meta is None:
            self.cached_slots_meta = get_all_slots_meta()
        slots_meta = self.cached_slots_meta
        self.slot_action_btn_rects.clear()

        y_cur = my + 82
        for meta in slots_meta:
            slot_id = meta["slot_id"]
            is_empty = meta["is_empty"]

            slot_card = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 86)
            pygame.draw.rect(surface, (24, 34, 52), slot_card, border_radius=8)
            pygame.draw.rect(surface, (51, 65, 85), slot_card, width=1, border_radius=8)

            # Slot Number Badge
            badge_rect = pygame.Rect(slot_card.x + 14, slot_card.y + 14, 60, 24)
            pygame.draw.rect(surface, (37, 99, 235), badge_rect, border_radius=4)
            b_txt = self.font_badge.render(f"SLOT {slot_id}", True, (255, 255, 255))
            surface.blit(b_txt, (badge_rect.centerx - b_txt.get_width() // 2, badge_rect.centery - b_txt.get_height() // 2))

            if is_empty:
                # Empty slot info
                surface.blit(self.font_sub.render("— [ Empty Save Slot ] —", True, COLOR_TEXT_MUTED), (slot_card.x + 88, slot_card.y + 16))
                surface.blit(self.font_body.render("No village history recorded in this slot yet.", True, (100, 116, 139)), (slot_card.x + 88, slot_card.y + 44))

                # Button
                btn_w = 140
                btn_rect = pygame.Rect(slot_card.right - btn_w - 14, slot_card.y + 26, btn_w, 34)
                if self.mode == "SAVE":
                    self.slot_action_btn_rects[slot_id] = btn_rect
                    b_hover = btn_rect.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (16, 185, 129) if b_hover else (5, 150, 105), btn_rect, border_radius=6)
                    pygame.draw.rect(surface, (52, 211, 153), btn_rect, width=1, border_radius=6)
                    act_txt = self.font_btn.render("Save Here", True, (255, 255, 255))
                    surface.blit(act_txt, (btn_rect.centerx - act_txt.get_width() // 2, btn_rect.centery - act_txt.get_height() // 2))
                else:
                    # Disabled load button
                    pygame.draw.rect(surface, (30, 41, 59), btn_rect, border_radius=6)
                    pygame.draw.rect(surface, (51, 65, 85), btn_rect, width=1, border_radius=6)
                    dis_txt = self.font_badge.render("— Empty —", True, (100, 116, 139))
                    surface.blit(dis_txt, (btn_rect.centerx - dis_txt.get_width() // 2, btn_rect.centery - dis_txt.get_height() // 2))
            else:
                # Occupied slot info
                t_str = f"Day {meta.get('day_number', 1)} ({meta.get('time_str', '08:00')})   •   Saved: {meta.get('timestamp', 'Unknown')}"
                surface.blit(self.font_sub.render(t_str, True, (241, 245, 249)), (slot_card.x + 88, slot_card.y + 16))

                details = f"Settlers: {meta.get('population', 0)} People   |   Food: {meta.get('food', 0)}   |   Wood: {meta.get('wood', 0)}"
                surface.blit(self.font_body.render(details, True, (56, 189, 248)), (slot_card.x + 88, slot_card.y + 44))

                # Button
                btn_w = 140
                btn_rect = pygame.Rect(slot_card.right - btn_w - 14, slot_card.y + 26, btn_w, 34)
                self.slot_action_btn_rects[slot_id] = btn_rect
                b_hover = btn_rect.collidepoint(mouse_pos)

                if self.mode == "SAVE":
                    pygame.draw.rect(surface, (234, 179, 8) if b_hover else (180, 83, 9), btn_rect, border_radius=6)
                    pygame.draw.rect(surface, (250, 204, 21), btn_rect, width=1, border_radius=6)
                    act_txt = self.font_btn.render("Overwrite", True, (255, 255, 255))
                else:
                    pygame.draw.rect(surface, (37, 99, 235) if b_hover else (30, 58, 138), btn_rect, border_radius=6)
                    pygame.draw.rect(surface, (96, 165, 250), btn_rect, width=1, border_radius=6)
                    act_txt = self.font_btn.render("Load Game", True, (255, 255, 255))
                surface.blit(act_txt, (btn_rect.centerx - act_txt.get_width() // 2, btn_rect.centery - act_txt.get_height() // 2))

            y_cur += 98

        # Status notification banner if any
        if self.status_message:
            sb_rect = pygame.Rect(mx + 24, my + self.modal_h - 44, self.modal_w - 48, 28)
            banner_col = (220, 38, 38) if ("failed" in self.status_message.lower() or "error" in self.status_message.lower()) else (16, 185, 129)
            pygame.draw.rect(surface, banner_col, sb_rect, border_radius=5)
            st_txt = self.font_badge.render(self.status_message, True, (255, 255, 255))
            surface.blit(st_txt, (sb_rect.centerx - st_txt.get_width() // 2, sb_rect.centery - st_txt.get_height() // 2))

        # -------------------------------------------------------------
        # OVERWRITE CONFIRMATION MODAL OVERLAY
        # -------------------------------------------------------------
        if self.confirming_overwrite_slot is not None:
            ov_dim = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
            ov_dim.fill((0, 0, 0, 180))
            surface.blit(ov_dim, (0, 0))

            dialog_w = 440
            dialog_h = 190
            dx = (screen_w - dialog_w) // 2
            dy = (screen_h - dialog_h) // 2

            d_rect = pygame.Rect(dx, dy, dialog_w, dialog_h)
            pygame.draw.rect(surface, (15, 23, 42), d_rect, border_radius=10)
            pygame.draw.rect(surface, (234, 179, 8), d_rect, width=2, border_radius=10)

            warn_title = self.font_sub.render(f"Overwrite Save Slot {self.confirming_overwrite_slot}?", True, (250, 204, 21))
            surface.blit(warn_title, (dx + 20, dy + 18))

            line1 = self.font_body.render("The old save data in this slot will be completely replaced", True, (241, 245, 249))
            line2 = self.font_body.render("with your current village progress. This action cannot be undone.", True, (148, 163, 184))
            surface.blit(line1, (dx + 20, dy + 52))
            surface.blit(line2, (dx + 20, dy + 72))

            # Buttons
            btn_w = 150
            btn_h = 36
            btn_y = dy + dialog_h - btn_h - 20

            # 1. Yes, Overwrite Button
            self.overwrite_confirm_btn_rect = pygame.Rect(dx + 20, btn_y, btn_w + 20, btn_h)
            c_hov = self.overwrite_confirm_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (220, 38, 38) if c_hov else (185, 28, 28), self.overwrite_confirm_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (248, 113, 113), self.overwrite_confirm_btn_rect, width=1, border_radius=6)
            c_txt = self.font_btn.render("Yes, Overwrite", True, (255, 255, 255))
            surface.blit(c_txt, (self.overwrite_confirm_btn_rect.centerx - c_txt.get_width() // 2, self.overwrite_confirm_btn_rect.centery - c_txt.get_height() // 2))

            # 2. Cancel Button
            self.overwrite_cancel_btn_rect = pygame.Rect(dx + dialog_w - btn_w - 20, btn_y, btn_w, btn_h)
            canc_hov = self.overwrite_cancel_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (51, 65, 85) if canc_hov else (30, 41, 59), self.overwrite_cancel_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (100, 116, 139), self.overwrite_cancel_btn_rect, width=1, border_radius=6)
            canc_txt = self.font_btn.render("Cancel", True, (255, 255, 255))
            surface.blit(canc_txt, (self.overwrite_cancel_btn_rect.centerx - canc_txt.get_width() // 2, self.overwrite_cancel_btn_rect.centery - canc_txt.get_height() // 2))
