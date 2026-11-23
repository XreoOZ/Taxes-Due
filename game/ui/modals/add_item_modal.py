"""
Add Item Interactive Modal Dialog (AGENT 2)
Bulk grant utility: every item row has its own quantity field — type the
amounts you want, then press ADD ALL once. Items with qty > 0 are physically
deposited into storage (Chest or Storage Permit Stockpile) and overflow drops
on the ground near storage when full.
Zero hardcoding, config-driven.
"""
from game.ui.ui_theme import ui_font, upx

import pygame
from game.config import (
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED
)
from game.data.config import ITEM_CATEGORIES
from game.ui.item_icons import draw_item_icon
from game.systems.core.cheat_system import (
    get_registered_item_types,
    spawn_item_physically
)

MAX_QTY_PER_ITEM = 5000
MAX_QTY_DIGITS = 4


class AddItemModal:
    def __init__(self):
        self.is_open = False
        self.target_storage = None
        self.modal_w = upx(720)
        self.modal_h = upx(600)

        self.font_title = None
        self.font_sub = None
        self.font_body = None
        self.font_badge = None
        self.font_btn = None
        self.font_qty = None

        self.items = []
        self.category_filter = "ALL"

        # Bulk-entry state: item_name -> int quantity
        self.qty_inputs = {}
        self.editing_item = None      # item_name currently being typed into
        self.editing_text = ""        # raw text buffer while editing

        # Search filter
        self.search_text = ""
        self.search_active = False

        self.close_btn_rect = None
        self.add_btn_rect = None
        self.cancel_btn_rect = None
        self.search_rect = None
        self.category_btn_rects = {}
        self.row_rects = {}           # item_name -> (row_rect, qty_rect)

        self.scroll_offset = 0
        self.status_message = None
        self.status_timer = 0.0

    def _ensure_fonts(self):
        if self.font_title is None:
            self.font_title = ui_font(18, bold=True)
            self.font_sub = ui_font(13, bold=True)
            self.font_body = ui_font(11)
            self.font_badge = ui_font(10, bold=True)
            self.font_btn = ui_font(13, bold=True)
            self.font_qty = ui_font(16, bold=True)

    def open(self, target_storage=None):
        """Opens the modal and initializes items and entry state"""
        self.is_open = True
        self.target_storage = target_storage
        self.items = get_registered_item_types()
        self.qty_inputs = {}
        self.editing_item = None
        self.editing_text = ""
        self.search_text = ""
        self.search_active = False
        self.category_filter = "ALL"
        self.scroll_offset = 0
        self.status_message = None
        self.status_timer = 0.0

    def close(self):
        self.is_open = False
        self.target_storage = None
        self.editing_item = None
        self.editing_text = ""
        self.search_active = False

    def _get_item_category(self, item_name):
        cat = ITEM_CATEGORIES.get(item_name)
        if cat:
            return cat
        name_clean = item_name.strip().title()
        cat = ITEM_CATEGORIES.get(name_clean)
        if cat:
            return cat
        for k, v in ITEM_CATEGORIES.items():
            if k.lower() == item_name.lower():
                return v
        return "RESOURCE"

    def _filtered_items(self):
        query = self.search_text.strip().lower()
        result = []
        for it in self.items:
            cat = self._get_item_category(it)
            if self.category_filter != "ALL" and cat.upper() != self.category_filter:
                continue
            if query and query not in it.lower().replace("_", " "):
                continue
            result.append(it)
        return result

    def _pending_entries(self):
        return [(name, qty) for name, qty in self.qty_inputs.items() if qty > 0]

    def handle_event(self, event, resources=None, stockpile_manager=None, permit_manager=None, building_manager=None, furniture_manager=None):
        """
        Processes modal interactions: qty typing, search, filters, bulk add.
        Returns (success: bool, message: str) on action, or None.
        """
        if not self.is_open:
            return None

        if event.type == pygame.KEYDOWN:
            if self.editing_item is not None:
                if event.key == pygame.K_BACKSPACE:
                    self.editing_text = self.editing_text[:-1]
                    return None
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._commit_editing()
                    self._focus_next_item(1)
                    return None
                if event.key == pygame.K_TAB:
                    self._commit_editing()
                    self._focus_next_item(1 if not pygame.key.get_pressed()[pygame.K_LSHIFT] else -1)
                    return None
                if event.key == pygame.K_ESCAPE:
                    self.editing_item = None
                    self.editing_text = ""
                    return None
                if event.unicode.isdigit() and len(self.editing_text) < MAX_QTY_DIGITS:
                    self.editing_text += event.unicode
                return None

            if self.search_active:
                if event.key == pygame.K_BACKSPACE:
                    self.search_text = self.search_text[:-1]
                    self.scroll_offset = 0
                    return None
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                    self.search_active = False
                    return None
                if event.unicode and len(self.search_text) < 32:
                    self.search_text += event.unicode
                    self.scroll_offset = 0
                return None

            if event.key == pygame.K_ESCAPE:
                self.close()
                return (False, "Cancelled item addition.")
            elif event.key == pygame.K_RETURN:
                return self._trigger_add_all(resources, stockpile_manager, permit_manager, building_manager, furniture_manager)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            m_pos = event.pos

            # Clicking outside the focused qty box commits it
            clicked_qty = False
            for item_name, (_, qty_rect) in self.row_rects.items():
                if qty_rect.collidepoint(m_pos):
                    clicked_qty = True
                    break
            if self.editing_item is not None and not clicked_qty:
                self._commit_editing()

            # 1. Close Button [X] or Cancel Button
            if (self.close_btn_rect and self.close_btn_rect.collidepoint(m_pos)) or \
               (self.cancel_btn_rect and self.cancel_btn_rect.collidepoint(m_pos)):
                self.close()
                return (False, "Cancelled item addition.")

            # 2. Search box focus
            if self.search_rect and self.search_rect.collidepoint(m_pos):
                self.search_active = True
                self.editing_item = None
                self.editing_text = ""
                return None
            if self.search_active:
                self.search_active = False

            # 3. Category Filter Tabs
            for cat_id, rect in self.category_btn_rects.items():
                if rect.collidepoint(m_pos):
                    self.category_filter = cat_id
                    self.scroll_offset = 0
                    return None

            # 4. Row quantity fields — click to type an amount
            for item_name, (row_rect, qty_rect) in self.row_rects.items():
                if qty_rect.collidepoint(m_pos):
                    self.editing_item = item_name
                    self.editing_text = str(self.qty_inputs.get(item_name, 0)) if self.qty_inputs.get(item_name, 0) > 0 else ""
                    self.search_active = False
                    return None
                if row_rect.collidepoint(m_pos):
                    # Clicking the row body focuses its qty field too
                    self.editing_item = item_name
                    self.editing_text = str(self.qty_inputs.get(item_name, 0)) if self.qty_inputs.get(item_name, 0) > 0 else ""
                    self.search_active = False
                    return None

            # 5. Add All Button
            if self.add_btn_rect and self.add_btn_rect.collidepoint(m_pos):
                return self._trigger_add_all(resources, stockpile_manager, permit_manager, building_manager, furniture_manager)

        elif event.type == pygame.MOUSEWHEEL:
            if self.modal_w:
                self.scroll_offset = max(0, self.scroll_offset - event.y)

        return None

    def _commit_editing(self):
        if self.editing_item is None:
            return
        text = self.editing_text.strip()
        qty = int(text) if text.isdigit() else 0
        qty = min(MAX_QTY_PER_ITEM, max(0, qty))
        if qty > 0:
            self.qty_inputs[self.editing_item] = qty
        else:
            self.qty_inputs.pop(self.editing_item, None)

    def _focus_next_item(self, direction):
        visible = self._filtered_items()
        if not visible:
            self.editing_item = None
            self.editing_text = ""
            return
        try:
            idx = visible.index(self.editing_item)
        except ValueError:
            idx = 0 if direction > 0 else len(visible) - 1
        nxt = visible[(idx + direction) % len(visible)]
        self.editing_item = nxt
        qty = self.qty_inputs.get(nxt, 0)
        self.editing_text = str(qty) if qty > 0 else ""

    def _trigger_add_all(self, resources, stockpile_manager, permit_manager, building_manager, furniture_manager=None):
        pending = self._pending_entries()
        if not pending:
            return (False, "Type quantities next to the items you want first.")

        added = 0
        failed = 0
        messages = []
        for item_name, qty in pending:
            success, msg = spawn_item_physically(
                item_name=item_name,
                amount=qty,
                target_storage=self.target_storage,
                stockpile_manager=stockpile_manager,
                permit_manager=permit_manager,
                resources=resources,
                building_manager=building_manager,
                furniture_manager=furniture_manager
            )
            if success:
                added += 1
            else:
                failed += 1
                if len(messages) < 3:
                    messages.append(msg)

        self.qty_inputs = {}
        self.close()

        total_qty = sum(qty for _, qty in pending)
        if failed == 0:
            return (True, f"Added {total_qty} items across {added} types to storage.")
        detail = f" ({'; '.join(messages)})" if messages else ""
        return (added > 0, f"Added {total_qty} items across {added} types; {failed} failed{detail}.")

    def draw(self, surface, permit_manager=None, stockpile_manager=None):
        if not self.is_open:
            return

        self._ensure_fonts()
        screen_w, screen_h = surface.get_size()
        self.modal_w = min(upx(720), screen_w - upx(48))
        self.modal_h = min(upx(600), screen_h - upx(48))
        m_pos = pygame.mouse.get_pos()

        # 1. Dimmed Backdrop
        backdrop = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        backdrop.fill((0, 0, 0, 160))
        surface.blit(backdrop, (0, 0))

        # 2. Main Modal Box
        mx = (screen_w - self.modal_w) // 2
        my = (screen_h - self.modal_h) // 2
        modal_rect = pygame.Rect(mx, my, self.modal_w, self.modal_h)

        pygame.draw.rect(surface, (15, 23, 42), modal_rect, border_radius=upx(10))
        pygame.draw.rect(surface, (245, 158, 11), modal_rect, width=2, border_radius=upx(10))

        # 3. Header Bar
        header_rect = pygame.Rect(mx, my, self.modal_w, upx(48))
        pygame.draw.rect(surface, (30, 41, 59), header_rect, border_top_left_radius=upx(10), border_top_right_radius=upx(10))
        pygame.draw.line(surface, (51, 65, 85), (mx, my + upx(48)), (mx + self.modal_w, my + upx(48)), 1)

        title_surf = self.font_title.render("ADD ITEMS (BULK GRANT)", True, (251, 191, 36))
        surface.blit(title_surf, (mx + upx(20), my + upx(13)))

        # Close [X] Button
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - upx(38), my + upx(10), upx(28), upx(28))
        c_hov = self.close_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (239, 68, 68) if c_hov else (51, 65, 85), self.close_btn_rect, border_radius=upx(6))
        x_lbl = self.font_btn.render("X", True, (255, 255, 255))
        surface.blit(x_lbl, (self.close_btn_rect.centerx - x_lbl.get_width() // 2, self.close_btn_rect.centery - x_lbl.get_height() // 2))

        # 4. Storage Destination Banner
        dest_y = my + upx(56)
        dest_rect = pygame.Rect(mx + upx(20), dest_y, self.modal_w - upx(40), upx(32))
        pygame.draw.rect(surface, (30, 41, 59), dest_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (71, 85, 105), dest_rect, width=1, border_radius=upx(6))

        if self.target_storage:
            cap = getattr(self.target_storage, "type_cfg", {}).get("capacity", 500)
            curr = getattr(self.target_storage, "total_stored", sum(getattr(self.target_storage, "inventory", {}).values()))
            name = getattr(self.target_storage, "name", "Storage Chest")
            dest_text = f"Destination: {name} (Selected) — Capacity: {curr}/{cap} items"
            dest_col = (56, 189, 248)
        else:
            storage_tiles_count = 0
            if permit_manager and hasattr(permit_manager, "permits"):
                for p in permit_manager.permits:
                    if getattr(p, "permit_type", "") == "storage":
                        storage_tiles_count += len(getattr(p, "tiles", []))
            dest_text = f"Destination: Village Storage Stockpile ({storage_tiles_count} tiles) — Overflow drops near storage!"
            dest_col = (250, 204, 21)

        d_surf = self.font_sub.render(dest_text, True, dest_col)
        surface.blit(d_surf, (dest_rect.x + upx(12), dest_rect.centery - d_surf.get_height() // 2))

        # 5. Search + Category Filter Row
        filter_y = dest_y + upx(40)
        self.search_rect = pygame.Rect(mx + upx(20), filter_y, upx(220), upx(26))
        s_hov = self.search_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (15, 23, 42) if not self.search_active else (10, 15, 29), self.search_rect, border_radius=5)
        pygame.draw.rect(surface, (56, 189, 248) if (self.search_active or s_hov) else (71, 85, 105), self.search_rect, width=1, border_radius=upx(5))
        search_label = self.search_text if self.search_text else "Search items..."
        search_col = (241, 245, 249) if self.search_text else COLOR_TEXT_MUTED
        search_surf = self.font_body.render(search_label + ("_" if self.search_active else ""), True, search_col)
        surface.blit(search_surf, (self.search_rect.x + upx(10), self.search_rect.centery - search_surf.get_height() // 2))

        cat_x = self.search_rect.right + upx(12)
        categories = ["ALL"] + list(dict.fromkeys(
            self._get_item_category(item).upper() for item in self.items
        ))
        self.category_btn_rects.clear()

        for cat in categories:
            btn_w = upx(64)
            cat_rect = pygame.Rect(cat_x, filter_y, btn_w, upx(26))
            self.category_btn_rects[cat] = cat_rect
            is_active = (self.category_filter == cat)
            is_hov = cat_rect.collidepoint(m_pos)

            bg = (59, 130, 246) if is_active else ((51, 65, 85) if is_hov else (30, 41, 59))
            border = (147, 197, 253) if is_active else (71, 85, 105)
            pygame.draw.rect(surface, bg, cat_rect, border_radius=upx(4))
            pygame.draw.rect(surface, border, cat_rect, width=1, border_radius=upx(4))

            lbl = self.font_badge.render(cat.capitalize(), True, (255, 255, 255) if is_active else (203, 213, 225))
            surface.blit(lbl, (cat_rect.centerx - lbl.get_width() // 2, cat_rect.centery - lbl.get_height() // 2))
            cat_x += btn_w + upx(5)

        # 6. Item List (bulk quantity rows)
        list_y = filter_y + upx(36)
        list_h = self.modal_h - (list_y - my) - upx(96)
        list_rect = pygame.Rect(mx + upx(20), list_y, self.modal_w - upx(40), list_h)
        pygame.draw.rect(surface, (10, 15, 29), list_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (51, 65, 85), list_rect, width=1, border_radius=upx(6))

        filtered_items = self._filtered_items()
        row_h = upx(30)
        rows_visible = max(1, list_rect.height // row_h)
        max_scroll = max(0, len(filtered_items) - rows_visible)
        self.scroll_offset = min(self.scroll_offset, max_scroll)

        self.row_rects.clear()
        clip = surface.get_clip()
        surface.set_clip(list_rect)
        for row_idx in range(self.scroll_offset, min(len(filtered_items), self.scroll_offset + rows_visible + 1)):
            item_name = filtered_items[row_idx]
            ry = list_rect.y + upx(6) + (row_idx - self.scroll_offset) * row_h
            row_rect = pygame.Rect(list_rect.x + upx(6), ry, list_rect.width - upx(90), row_h - upx(4))
            qty_rect = pygame.Rect(list_rect.right - upx(76), ry, upx(70), row_h - upx(4))
            self.row_rects[item_name] = (row_rect, qty_rect)

            is_editing = (self.editing_item == item_name)
            has_qty = self.qty_inputs.get(item_name, 0) > 0
            row_hov = row_rect.collidepoint(m_pos) or qty_rect.collidepoint(m_pos)

            row_bg = (30, 58, 138) if is_editing else ((30, 41, 59) if row_hov else (15, 23, 42))
            row_border = (250, 204, 21) if is_editing else ((56, 189, 248) if row_hov else (51, 65, 85))
            pygame.draw.rect(surface, row_bg, row_rect, border_radius=upx(5))
            pygame.draw.rect(surface, row_border, row_rect, width=2 if is_editing else 1, border_radius=upx(5))

            draw_item_icon(surface, item_name, row_rect.x + upx(16), row_rect.centery, size=upx(11))
            display_name = item_name.replace("_", " ")
            if len(display_name) > 30:
                display_name = display_name[:28] + ".."
            name_col = (254, 240, 138) if has_qty else ((255, 255, 255) if row_hov else (226, 232, 240))
            name_surf = self.font_body.render(display_name, True, name_col)
            surface.blit(name_surf, (row_rect.x + upx(30), row_rect.centery - name_surf.get_height() // 2))

            cat_tag = self._get_item_category(item_name)
            if cat_tag and cat_tag != "RESOURCE":
                cat_surf = self.font_badge.render(cat_tag[:12], True, COLOR_TEXT_MUTED)
                surface.blit(cat_surf, (row_rect.right - cat_surf.get_width() - upx(8), row_rect.centery - cat_surf.get_height() // 2))

            # Quantity box
            q_bg = (15, 23, 42) if not is_editing else (30, 41, 59)
            q_border = (250, 204, 21) if is_editing else ((56, 189, 248) if has_qty else (71, 85, 105))
            pygame.draw.rect(surface, q_bg, qty_rect, border_radius=upx(4))
            pygame.draw.rect(surface, q_border, qty_rect, width=1, border_radius=upx(4))

            if is_editing:
                q_text = self.editing_text + "_"
                q_col = (251, 191, 36)
            elif has_qty:
                q_text = str(self.qty_inputs[item_name])
                q_col = (254, 240, 138)
            else:
                q_text = "0"
                q_col = COLOR_TEXT_MUTED
            q_surf = self.font_qty.render(q_text, True, q_col)
            surface.blit(q_surf, (qty_rect.centerx - q_surf.get_width() // 2, qty_rect.centery - q_surf.get_height() // 2))

        if not filtered_items:
            none_surf = self.font_body.render("No items match the current filter.", True, COLOR_TEXT_MUTED)
            surface.blit(none_surf, (list_rect.centerx - none_surf.get_width() // 2, list_rect.centery))
        surface.set_clip(clip)

        # Scrollbar
        if max_scroll > 0:
            track = pygame.Rect(list_rect.right - upx(5), list_rect.y, 3, list_rect.height)
            pygame.draw.rect(surface, (51, 65, 85), track, border_radius=2)
            thumb_h = max(upx(20), int(track.height * rows_visible / max(len(filtered_items), rows_visible)))
            thumb_y = track.y + int((track.height - thumb_h) * self.scroll_offset / max_scroll)
            pygame.draw.rect(surface, (96, 165, 250), (track.x, thumb_y, track.width, thumb_h), border_radius=2)

        # 7. Bottom Action Row
        pending = self._pending_entries()
        total_pending_qty = sum(q for _, q in pending)
        act_y = list_rect.bottom + upx(10)

        summary_surf = self.font_badge.render(
            f"{len(pending)} item type(s), {total_pending_qty} total — Enter/Tab to move between rows",
            True, (56, 189, 248) if pending else COLOR_TEXT_MUTED,
        )
        surface.blit(summary_surf, (mx + upx(24), act_y + upx(8)))

        # Cancel Button
        self.cancel_btn_rect = pygame.Rect(mx + self.modal_w - upx(240), act_y, upx(110), upx(38))
        c_hov = self.cancel_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (71, 85, 105) if c_hov else (51, 65, 85), self.cancel_btn_rect, border_radius=upx(6))
        canc_txt = self.font_btn.render("Cancel", True, (241, 245, 249))
        surface.blit(canc_txt, (self.cancel_btn_rect.centerx - canc_txt.get_width() // 2, self.cancel_btn_rect.centery - canc_txt.get_height() // 2))

        # Add All Button
        self.add_btn_rect = pygame.Rect(mx + self.modal_w - upx(120), act_y, upx(100), upx(38))
        a_hov = self.add_btn_rect.collidepoint(m_pos)
        a_bg = (16, 185, 129) if (a_hov and pending) else (5, 150, 105)
        pygame.draw.rect(surface, a_bg, self.add_btn_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (110, 231, 183) if a_hov else (52, 211, 153), self.add_btn_rect, width=2, border_radius=upx(6))

        add_label = f"ADD {len(pending)}" if pending else "ADD"
        add_txt = self.font_btn.render(add_label, True, (255, 255, 255))
        surface.blit(add_txt, (self.add_btn_rect.centerx - add_txt.get_width() // 2, self.add_btn_rect.centery - add_txt.get_height() // 2))
