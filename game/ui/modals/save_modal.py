"""
Save & Load Game Modal Dialog
Lists every save file in the save directory (unlimited named saves), with a
custom-name "New Save" row, overwrite confirmation, and mouse-wheel scrolling.
"""

import pygame
from game.config import (
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED
)
from game.save_system import get_all_slots_meta, _sanitize_save_name
from game.ui.ui_theme import ui_font, upx

CARD_H = 86
CARD_GAP = 12

class SaveLoadModal:
    def __init__(self):
        self.is_open = False
        self.mode = "LOAD"  # "SAVE" or "LOAD"
        self.modal_w = 660
        self.modal_h = 500
        self.font_title = None
        self.font_sub = None
        self.font_body = None
        self.font_badge = None
        self.font_btn = None

        self.slot_action_btn_rects = {}  # save name -> Rect
        self.delete_btn_rects = {}       # save name -> Rect
        self.close_btn_rect = None
        self.status_message = None
        self.status_timer = 0.0
        self.cached_slots_meta = None
        self.list_scroll = 0.0

        # New-save name input (SAVE mode only)
        self.save_name_input = ""
        self.name_input_rect = None
        self.name_input_active = False
        self.new_save_btn_rect = None

        # Overwrite Confirmation Dialog State
        self.confirming_overwrite_slot = None
        self.overwrite_confirm_btn_rect = None
        self.overwrite_cancel_btn_rect = None

        # Delete Confirmation Dialog State
        self.confirming_delete_slot = None
        self.delete_confirm_btn_rect = None
        self.delete_cancel_btn_rect = None

    def _ensure_fonts(self):
        if self.font_title is None:
            self.font_title = ui_font(20, bold=True)
            self.font_sub = ui_font(14, bold=True)
            self.font_body = ui_font(12)
            self.font_badge = ui_font(11, bold=True)
            self.font_btn = ui_font(13, bold=True)

    def refresh_slots(self, message="Progress saved successfully!"):
        self.status_message = message
        self.status_timer = 3.5
        self.confirming_overwrite_slot = None
        self.confirming_delete_slot = None
        self.cached_slots_meta = get_all_slots_meta()

    def open(self, mode="LOAD"):
        self.mode = mode
        self.is_open = True
        self.status_message = None
        self.confirming_overwrite_slot = None
        self.confirming_delete_slot = None
        self.save_name_input = ""
        self.name_input_active = False
        self.list_scroll = 0.0
        self.cached_slots_meta = get_all_slots_meta()

    def close(self):
        self.is_open = False
        self.confirming_overwrite_slot = None
        self.confirming_delete_slot = None
        self.name_input_active = False

    def _list_area(self, mx, my):
        top = my + (128 if self.mode == "SAVE" else 84)
        return pygame.Rect(mx + 24, top, self.modal_w - 48, my + self.modal_h - 60 - top)

    def _new_save_action(self, name):
        """Route a typed save name: prompt overwrite if it already exists."""
        if self.cached_slots_meta is None:
            self.cached_slots_meta = get_all_slots_meta()
        existing = next((m for m in self.cached_slots_meta
                         if m["slot_id"] == name and not m.get("is_empty", True)), None)
        if existing:
            self.confirming_overwrite_slot = name
            return f"prompt_overwrite_{name}"
        return f"new_save_{name}"

    def handle_event(self, event):
        if not self.is_open:
            return None

        # Name typing for the New Save row
        if event.type == pygame.KEYDOWN and self.name_input_active:
            if event.key == pygame.K_ESCAPE:
                self.name_input_active = False
                return "name_input_cancelled"
            if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                name = _sanitize_save_name(self.save_name_input)
                self.name_input_active = False
                if name:
                    return self._new_save_action(name)
                return "new_save_empty"
            if event.key == pygame.K_BACKSPACE:
                self.save_name_input = self.save_name_input[:-1]
                return "name_typed"
            if event.unicode and event.unicode.isprintable():
                self.save_name_input += event.unicode
                return "name_typed"
            return "name_typed_blocked"

        if event.type == pygame.MOUSEWHEEL:
            area = getattr(self, "_last_list_area", None)
            if area and area.collidepoint(pygame.mouse.get_pos()):
                self.list_scroll = max(0.0, self.list_scroll - event.y * 60)
                return "save_list_scrolled"
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

            # Priority 2: Delete confirmation dialog clicks
            if self.confirming_delete_slot is not None:
                if self.delete_confirm_btn_rect and self.delete_confirm_btn_rect.collidepoint(mouse_pos):
                    slot_id = self.confirming_delete_slot
                    self.confirming_delete_slot = None
                    return f"delete_slot_{slot_id}"
                if self.delete_cancel_btn_rect and self.delete_cancel_btn_rect.collidepoint(mouse_pos):
                    self.confirming_delete_slot = None
                    return "cancel_delete"
                return "delete_dialog_blocked"

            # Close button (X)
            if self.close_btn_rect and self.close_btn_rect.collidepoint(mouse_pos):
                self.close()
                return "close_save_modal"

            # New-save row (SAVE mode only)
            if self.mode == "SAVE":
                if self.name_input_rect and self.name_input_rect.collidepoint(mouse_pos):
                    self.name_input_active = True
                    return "name_input_focus"
                if self.new_save_btn_rect and self.new_save_btn_rect.collidepoint(mouse_pos):
                    name = _sanitize_save_name(self.save_name_input)
                    if name:
                        self.name_input_active = False
                        return self._new_save_action(name)
                    self.name_input_active = True
                    return "name_input_focus_empty"
                # Clicking elsewhere defocuses the input
                if self.name_input_active:
                    self.name_input_active = False

            # Delete buttons (any non-empty save, both modes)
            for slot_id, rect in list(self.delete_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    self.confirming_delete_slot = slot_id
                    return f"prompt_delete_{slot_id}"

            # Slot buttons
            if self.cached_slots_meta is None:
                self.cached_slots_meta = get_all_slots_meta()
            slots_meta = {m["slot_id"]: m for m in self.cached_slots_meta}
            for slot_id, rect in list(self.slot_action_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    meta = slots_meta.get(slot_id, {})
                    if self.mode == "SAVE":
                        if not meta.get("is_empty", True):
                            # Save exists -> prompt confirmation before overwriting
                            self.confirming_overwrite_slot = slot_id
                            return f"prompt_overwrite_{slot_id}"
                        else:
                            return f"save_slot_{slot_id}"
                    else:
                        if not meta.get("is_empty", True):
                            return f"load_slot_{slot_id}"
                        return "load_empty_slot"

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
        title_str = "SAVE GAME" if self.mode == "SAVE" else "LOAD GAME"
        title_surf = self.font_title.render(title_str, True, COLOR_TEXT_TITLE)
        surface.blit(title_surf, (mx + 24, my + 18))

        sub_desc = "Name a new save below, or overwrite an existing one:" if self.mode == "SAVE" else "Select a previous game record to load:"
        surface.blit(self.font_body.render(sub_desc, True, COLOR_TEXT_MUTED), (mx + 24, my + 44))

        # Close button (X)
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - 36, my + 16, 22, 22)
        close_hover = self.close_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (239, 68, 68) if close_hover else (30, 41, 59), self.close_btn_rect, border_radius=4)
        c_lbl = self.font_btn.render("X", True, (255, 255, 255))
        surface.blit(c_lbl, (self.close_btn_rect.centerx - c_lbl.get_width() // 2, self.close_btn_rect.centery - c_lbl.get_height() // 2))

        pygame.draw.line(surface, COLOR_MODAL_BORDER, (mx + 20, my + 68), (mx + self.modal_w - 20, my + 68))

        # -------------------------------------------------------------
        # NEW SAVE ROW (SAVE mode only)
        # -------------------------------------------------------------
        if self.mode == "SAVE":
            row_y = my + 82
            input_w = self.modal_w - 48 - 110 - 12
            self.name_input_rect = pygame.Rect(mx + 24, row_y, input_w, 34)
            inp = self.name_input_rect
            border_col = (96, 165, 250) if self.name_input_active else COLOR_MODAL_BORDER
            pygame.draw.rect(surface, (15, 23, 42), inp, border_radius=6)
            pygame.draw.rect(surface, border_col, inp, width=2 if self.name_input_active else 1, border_radius=6)
            shown = self.save_name_input or ("save name..." if not self.name_input_active else "")
            txt_col = COLOR_TEXT_MUTED if (not self.save_name_input and not self.name_input_active) else (255, 255, 255)
            shown_surf = self.font_body.render(shown, True, txt_col)
            surface.blit(shown_surf, (inp.x + 10, inp.centery - shown_surf.get_height() // 2))
            if self.name_input_active and (pygame.time.get_ticks() // 500) % 2 == 0:
                caret_x = inp.x + 10 + shown_surf.get_width()
                pygame.draw.line(surface, (255, 255, 255), (caret_x, inp.y + 8), (caret_x, inp.bottom - 8), 2)

            self.new_save_btn_rect = pygame.Rect(inp.right + 12, row_y, 110, 34)
            nb = self.new_save_btn_rect
            nb_hov = nb.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (16, 185, 129) if nb_hov else (5, 150, 105), nb, border_radius=6)
            pygame.draw.rect(surface, (52, 211, 153), nb, width=1, border_radius=6)
            nb_txt = self.font_btn.render("Save New", True, (255, 255, 255))
            surface.blit(nb_txt, (nb.centerx - nb_txt.get_width() // 2, nb.centery - nb_txt.get_height() // 2))

        # -------------------------------------------------------------
        # SAVES LIST (scrollable)
        # -------------------------------------------------------------
        if self.cached_slots_meta is None:
            self.cached_slots_meta = get_all_slots_meta()
        slots_meta = self.cached_slots_meta
        self.slot_action_btn_rects.clear()

        area = self._list_area(mx, my)
        self._last_list_area = area
        max_scroll = max(0.0, len(slots_meta) * (CARD_H + CARD_GAP) - area.height)
        self.list_scroll = min(self.list_scroll, max_scroll)
        self.delete_btn_rects.clear()

        clip = surface.get_clip()
        surface.set_clip(area)
        y_cur = area.y - self.list_scroll
        for meta in slots_meta:
            slot_id = meta["slot_id"]
            is_empty = meta["is_empty"]

            slot_card = pygame.Rect(area.x, y_cur, area.width, CARD_H)
            y_cur += CARD_H + CARD_GAP
            if slot_card.bottom < area.y or slot_card.top > area.bottom:
                continue

            pygame.draw.rect(surface, (24, 34, 52), slot_card, border_radius=8)
            pygame.draw.rect(surface, (51, 65, 85), slot_card, width=1, border_radius=8)

            # Save name badge
            badge_rect = pygame.Rect(slot_card.x + 14, slot_card.y + 14, min(220, area.width - 200), 24)
            pygame.draw.rect(surface, (37, 99, 235), badge_rect, border_radius=4)
            name_str = str(slot_id)
            if len(name_str) > 26:
                name_str = name_str[:23] + "..."
            b_txt = self.font_badge.render(name_str, True, (255, 255, 255))
            surface.blit(b_txt, (badge_rect.x + 8, badge_rect.centery - b_txt.get_height() // 2))

            if is_empty:
                surface.blit(self.font_sub.render("— [ Empty Save ] —", True, COLOR_TEXT_MUTED), (slot_card.x + 88, slot_card.y + 16))
                surface.blit(self.font_body.render("This save file could not be read.", True, (100, 116, 139)), (slot_card.x + 88, slot_card.y + 44))
            else:
                t_str = f"Day {meta.get('day_number', 1)} ({meta.get('time_str', '08:00')})   •   Saved: {meta.get('timestamp', 'Unknown')}"
                surface.blit(self.font_sub.render(t_str, True, (241, 245, 249)), (slot_card.x + 88, slot_card.y + 16))

                details = f"Settlers: {meta.get('population', 0)} People   |   Food: {meta.get('food', 0)}   |   Wood: {meta.get('wood', 0)}"
                surface.blit(self.font_body.render(details, True, (56, 189, 248)), (slot_card.x + 88, slot_card.y + 44))

            # Buttons: Delete (small, left) + primary action (right)
            if not is_empty:
                del_rect = pygame.Rect(slot_card.right - 14 - 140 - 76, slot_card.y + 26, 70, 34)
                self.delete_btn_rects[slot_id] = del_rect
                d_hov = del_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (220, 38, 38) if d_hov else (127, 29, 29), del_rect, border_radius=6)
                pygame.draw.rect(surface, (248, 113, 113), del_rect, width=1, border_radius=6)
                d_txt = self.font_badge.render("Delete", True, (255, 255, 255))
                surface.blit(d_txt, (del_rect.centerx - d_txt.get_width() // 2, del_rect.centery - d_txt.get_height() // 2))

            btn_w = 140
            btn_rect = pygame.Rect(slot_card.right - btn_w - 14, slot_card.y + 26, btn_w, 34)
            self.slot_action_btn_rects[slot_id] = btn_rect
            b_hover = btn_rect.collidepoint(mouse_pos)

            if is_empty:
                pygame.draw.rect(surface, (30, 41, 59), btn_rect, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), btn_rect, width=1, border_radius=6)
                dis_txt = self.font_badge.render("— Empty —", True, (100, 116, 139))
                surface.blit(dis_txt, (btn_rect.centerx - dis_txt.get_width() // 2, btn_rect.centery - dis_txt.get_height() // 2))
            elif self.mode == "SAVE":
                pygame.draw.rect(surface, (234, 179, 8) if b_hover else (180, 83, 9), btn_rect, border_radius=6)
                pygame.draw.rect(surface, (250, 204, 21), btn_rect, width=1, border_radius=6)
                act_txt = self.font_btn.render("Overwrite", True, (255, 255, 255))
                surface.blit(act_txt, (btn_rect.centerx - act_txt.get_width() // 2, btn_rect.centery - act_txt.get_height() // 2))
            else:
                pygame.draw.rect(surface, (37, 99, 235) if b_hover else (30, 58, 138), btn_rect, border_radius=6)
                pygame.draw.rect(surface, (96, 165, 250), btn_rect, width=1, border_radius=6)
                act_txt = self.font_btn.render("Load Game", True, (255, 255, 255))
                surface.blit(act_txt, (btn_rect.centerx - act_txt.get_width() // 2, btn_rect.centery - act_txt.get_height() // 2))

        surface.set_clip(clip)

        if not slots_meta:
            empty_txt = self.font_body.render("No saves yet — type a name above and press Save New.", True, COLOR_TEXT_MUTED)
            surface.blit(empty_txt, (area.centerx - empty_txt.get_width() // 2, area.y + 30))

        # Scrollbar hint when list overflows
        if max_scroll > 0:
            sb_x = area.right - 6
            sb_h = max(30, int(area.height * area.height / (len(slots_meta) * (CARD_H + CARD_GAP))))
            sb_y = area.y + int((area.height - sb_h) * (self.list_scroll / max_scroll))
            pygame.draw.rect(surface, (51, 65, 85), (sb_x, sb_y, 4, sb_h), border_radius=2)

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

            dialog_w = 460
            dialog_h = 190
            dx = (screen_w - dialog_w) // 2
            dy = (screen_h - dialog_h) // 2

            d_rect = pygame.Rect(dx, dy, dialog_w, dialog_h)
            pygame.draw.rect(surface, (15, 23, 42), d_rect, border_radius=10)
            pygame.draw.rect(surface, (234, 179, 8), d_rect, width=2, border_radius=10)

            save_name = str(self.confirming_overwrite_slot)
            warn_title = self.font_sub.render(f"Overwrite \"{save_name}\"?", True, (250, 204, 21))
            surface.blit(warn_title, (dx + 20, dy + 18))

            line1 = self.font_body.render("The old save data will be completely replaced", True, (241, 245, 249))
            line2 = self.font_body.render("with your current village progress. This action cannot be undone.", True, (148, 163, 184))
            surface.blit(line1, (dx + 20, dy + 52))
            surface.blit(line2, (dx + 20, dy + 72))

            # Buttons
            btn_w = 150
            btn_h = upx(36)
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

        # -------------------------------------------------------------
        # DELETE CONFIRMATION MODAL OVERLAY
        # -------------------------------------------------------------
        if self.confirming_delete_slot is not None:
            ov_dim = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
            ov_dim.fill((0, 0, 0, 180))
            surface.blit(ov_dim, (0, 0))

            dialog_w = 460
            dialog_h = 190
            dx = (screen_w - dialog_w) // 2
            dy = (screen_h - dialog_h) // 2

            d_rect = pygame.Rect(dx, dy, dialog_w, dialog_h)
            pygame.draw.rect(surface, (15, 23, 42), d_rect, border_radius=10)
            pygame.draw.rect(surface, (220, 38, 38), d_rect, width=2, border_radius=10)

            save_name = str(self.confirming_delete_slot)
            warn_title = self.font_sub.render(f"Delete \"{save_name}\"?", True, (248, 113, 113))
            surface.blit(warn_title, (dx + 20, dy + 18))

            line1 = self.font_body.render("This save file will be permanently removed from disk.", True, (241, 245, 249))
            line2 = self.font_body.render("This action cannot be undone.", True, (148, 163, 184))
            surface.blit(line1, (dx + 20, dy + 52))
            surface.blit(line2, (dx + 20, dy + 72))

            btn_w = 150
            btn_h = upx(36)
            btn_y = dy + dialog_h - btn_h - 20

            # 1. Yes, Delete Button
            self.delete_confirm_btn_rect = pygame.Rect(dx + 20, btn_y, btn_w + 20, btn_h)
            c_hov = self.delete_confirm_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (220, 38, 38) if c_hov else (185, 28, 28), self.delete_confirm_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (248, 113, 113), self.delete_confirm_btn_rect, width=1, border_radius=6)
            c_txt = self.font_btn.render("Yes, Delete", True, (255, 255, 255))
            surface.blit(c_txt, (self.delete_confirm_btn_rect.centerx - c_txt.get_width() // 2, self.delete_confirm_btn_rect.centery - c_txt.get_height() // 2))

            # 2. Cancel Button
            self.delete_cancel_btn_rect = pygame.Rect(dx + dialog_w - btn_w - 20, btn_y, btn_w, btn_h)
            canc_hov = self.delete_cancel_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (51, 65, 85) if canc_hov else (30, 41, 59), self.delete_cancel_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (100, 116, 139), self.delete_cancel_btn_rect, width=1, border_radius=6)
            canc_txt = self.font_btn.render("Cancel", True, (255, 255, 255))
            surface.blit(canc_txt, (self.delete_cancel_btn_rect.centerx - canc_txt.get_width() // 2, self.delete_cancel_btn_rect.centery - canc_txt.get_height() // 2))
