"""
Add Item Interactive Modal Dialog (AGENT 2)
Allows the developer/player to:
1. Select an item to add from all registered items (with procedural vector icons).
2. Configure the exact quantity to add with stepper controls and presets.
3. Physically deposit the items into storage (Chest or Storage Permit Stockpile).
4. Automatically drops items physically on the ground near storage when full.
Zero hardcoding, config-driven.
"""

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
from game.systems.cheat_system import (
    get_registered_item_types,
    spawn_item_physically
)

class AddItemModal:
    def __init__(self):
        self.is_open = False
        self.target_storage = None
        self.modal_w = 640
        self.modal_h = 520

        self.font_title = None
        self.font_sub = None
        self.font_body = None
        self.font_badge = None
        self.font_btn = None
        self.font_qty = None

        self.items = []
        self.selected_item = "Potato"
        self.quantity = 50
        self.category_filter = "ALL"

        self.close_btn_rect = None
        self.add_btn_rect = None
        self.cancel_btn_rect = None
        self.category_btn_rects = {}
        self.item_btn_rects = {}
        self.qty_btn_rects = {}

        self.scroll_offset = 0
        self.status_message = None
        self.status_timer = 0.0

    def _ensure_fonts(self):
        if self.font_title is None:
            self.font_title = pygame.font.SysFont("Segoe UI", 18, bold=True)
            self.font_sub = pygame.font.SysFont("Segoe UI", 13, bold=True)
            self.font_body = pygame.font.SysFont("Segoe UI", 11)
            self.font_badge = pygame.font.SysFont("Segoe UI", 10, bold=True)
            self.font_btn = pygame.font.SysFont("Segoe UI", 13, bold=True)
            self.font_qty = pygame.font.SysFont("Segoe UI", 22, bold=True)

    def open(self, target_storage=None):
        """Opens the modal and initializes items and selected state"""
        self.is_open = True
        self.target_storage = target_storage
        self.items = get_registered_item_types()
        if not self.selected_item or self.selected_item not in self.items:
            self.selected_item = self.items[0] if self.items else "Potato"
        self.quantity = 50
        self.category_filter = "ALL"
        self.scroll_offset = 0
        self.status_message = None
        self.status_timer = 0.0

    def close(self):
        self.is_open = False
        self.target_storage = None

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

    def handle_event(self, event, resources=None, stockpile_manager=None, permit_manager=None, building_manager=None):
        """
        Processes modal interactions: item selection, quantity adjustment, and physical addition.
        Returns (success: bool, message: str) on action, or None.
        """
        if not self.is_open:
            return None

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
                return (False, "Cancelled item addition.")
            elif event.key == pygame.K_RETURN:
                return self._trigger_add(resources, stockpile_manager, permit_manager, building_manager)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            m_pos = event.pos

            # 1. Close Button [X] or Cancel Button
            if (self.close_btn_rect and self.close_btn_rect.collidepoint(m_pos)) or \
               (self.cancel_btn_rect and self.cancel_btn_rect.collidepoint(m_pos)):
                self.close()
                return (False, "Cancelled item addition.")

            # 2. Category Filter Tabs
            for cat_id, rect in self.category_btn_rects.items():
                if rect.collidepoint(m_pos):
                    self.category_filter = cat_id
                    self.scroll_offset = 0
                    return None

            # 3. Item Selection Cards
            for item_name, rect in self.item_btn_rects.items():
                if rect.collidepoint(m_pos):
                    self.selected_item = item_name
                    return None

            # 4. Quantity Adjustments
            for action_key, rect in self.qty_btn_rects.items():
                if rect.collidepoint(m_pos):
                    if action_key == "dec_10":
                        self.quantity = max(1, self.quantity - 10)
                    elif action_key == "dec_1":
                        self.quantity = max(1, self.quantity - 1)
                    elif action_key == "inc_1":
                        self.quantity = min(5000, self.quantity + 1)
                    elif action_key == "inc_10":
                        self.quantity = min(5000, self.quantity + 10)
                    elif action_key == "inc_50":
                        self.quantity = min(5000, self.quantity + 50)
                    elif action_key == "inc_100":
                        self.quantity = min(5000, self.quantity + 100)
                    elif action_key.startswith("set_"):
                        val = int(action_key.split("_")[1])
                        self.quantity = val
                    return None

            # 5. Add Button
            if self.add_btn_rect and self.add_btn_rect.collidepoint(m_pos):
                return self._trigger_add(resources, stockpile_manager, permit_manager, building_manager)

        elif event.type == pygame.MOUSEWHEEL:
            if event.y > 0:
                self.scroll_offset = max(0, self.scroll_offset - 1)
            elif event.y < 0:
                self.scroll_offset += 1

        return None

    def _trigger_add(self, resources, stockpile_manager, permit_manager, building_manager):
        if not self.selected_item:
            return (False, "Please select an item first.")
        if self.quantity <= 0:
            return (False, "Quantity must be greater than zero.")

        success, msg = spawn_item_physically(
            item_name=self.selected_item,
            amount=self.quantity,
            target_storage=self.target_storage,
            stockpile_manager=stockpile_manager,
            permit_manager=permit_manager,
            resources=resources,
            building_manager=building_manager
        )
        self.close()
        return (success, msg)

    def draw(self, surface, permit_manager=None, stockpile_manager=None):
        if not self.is_open:
            return

        self._ensure_fonts()
        screen_w, screen_h = surface.get_size()
        m_pos = pygame.mouse.get_pos()

        # 1. Dimmed Backdrop
        backdrop = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        backdrop.fill((0, 0, 0, 160))
        surface.blit(backdrop, (0, 0))

        # 2. Main Modal Box
        mx = (screen_w - self.modal_w) // 2
        my = (screen_h - self.modal_h) // 2
        modal_rect = pygame.Rect(mx, my, self.modal_w, self.modal_h)

        pygame.draw.rect(surface, (15, 23, 42), modal_rect, border_radius=10)
        pygame.draw.rect(surface, (245, 158, 11), modal_rect, width=2, border_radius=10)

        # 3. Header Bar
        header_rect = pygame.Rect(mx, my, self.modal_w, 48)
        pygame.draw.rect(surface, (30, 41, 59), header_rect, border_top_left_radius=10, border_top_right_radius=10)
        pygame.draw.line(surface, (51, 65, 85), (mx, my + 48), (mx + self.modal_w, my + 48), 1)

        title_surf = self.font_title.render("ADD ITEM CHEAT (DEVELOPER UTILITY)", True, (251, 191, 36))
        surface.blit(title_surf, (mx + 20, my + 13))

        # Close [X] Button
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - 38, my + 10, 28, 28)
        c_hov = self.close_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (239, 68, 68) if c_hov else (51, 65, 85), self.close_btn_rect, border_radius=6)
        x_lbl = self.font_btn.render("X", True, (255, 255, 255))
        surface.blit(x_lbl, (self.close_btn_rect.centerx - x_lbl.get_width() // 2, self.close_btn_rect.centery - x_lbl.get_height() // 2))

        # 4. Storage Destination Banner
        dest_y = my + 56
        dest_rect = pygame.Rect(mx + 20, dest_y, self.modal_w - 40, 32)
        pygame.draw.rect(surface, (30, 41, 59), dest_rect, border_radius=6)
        pygame.draw.rect(surface, (71, 85, 105), dest_rect, width=1, border_radius=6)

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
        surface.blit(d_surf, (dest_rect.x + 12, dest_rect.centery - d_surf.get_height() // 2))

        # 5. Category Filter Row
        cat_y = dest_y + 40
        categories = ["ALL"] + list(dict.fromkeys(
            self._get_item_category(item).upper() for item in self.items
        ))
        cat_x = mx + 20
        self.category_btn_rects.clear()

        cat_lbl = self.font_body.render("Filter:", True, (148, 163, 184))
        surface.blit(cat_lbl, (cat_x, cat_y + 4))
        cat_x += 42

        for cat in categories:
            btn_w = 68
            cat_rect = pygame.Rect(cat_x, cat_y, btn_w, 24)
            self.category_btn_rects[cat] = cat_rect
            is_active = (self.category_filter == cat)
            is_hov = cat_rect.collidepoint(m_pos)

            bg = (59, 130, 246) if is_active else ((51, 65, 85) if is_hov else (30, 41, 59))
            border = (147, 197, 253) if is_active else (71, 85, 105)
            pygame.draw.rect(surface, bg, cat_rect, border_radius=4)
            pygame.draw.rect(surface, border, cat_rect, width=1, border_radius=4)

            lbl = self.font_badge.render(cat.capitalize(), True, (255, 255, 255) if is_active else (203, 213, 225))
            surface.blit(lbl, (cat_rect.centerx - lbl.get_width() // 2, cat_rect.centery - lbl.get_height() // 2))
            cat_x += btn_w + 6

        # 6. Item Grid (Select Item)
        grid_y = cat_y + 32
        grid_h = 190
        grid_rect = pygame.Rect(mx + 20, grid_y, self.modal_w - 40, grid_h)
        pygame.draw.rect(surface, (10, 15, 29), grid_rect, border_radius=6)
        pygame.draw.rect(surface, (51, 65, 85), grid_rect, width=1, border_radius=6)

        # Filter items
        filtered_items = []
        for it in self.items:
            cat = self._get_item_category(it)
            if self.category_filter == "ALL" or cat.upper() == self.category_filter:
                filtered_items.append(it)

        # Render items in 4 columns
        cols = 4
        card_w = (grid_rect.width - 20) // cols
        card_h = 36
        self.item_btn_rects.clear()

        # Handle max visible
        visible_rows = 4
        max_scroll = max(0, ((len(filtered_items) + cols - 1) // cols) - visible_rows)
        self.scroll_offset = min(self.scroll_offset, max_scroll)

        start_idx = self.scroll_offset * cols
        end_idx = min(len(filtered_items), start_idx + (visible_rows * cols))

        for idx in range(start_idx, end_idx):
            item_name = filtered_items[idx]
            rel_idx = idx - start_idx
            row = rel_idx // cols
            col = rel_idx % cols

            ix = grid_rect.x + 8 + (col * (card_w + 3))
            iy = grid_rect.y + 8 + (row * (card_h + 8))
            card_r = pygame.Rect(ix, iy, card_w, card_h)
            self.item_btn_rects[item_name] = card_r

            is_sel = (self.selected_item == item_name)
            is_hov = card_r.collidepoint(m_pos)

            bg = (30, 58, 138) if is_sel else ((30, 41, 59) if is_hov else (15, 23, 42))
            border = (250, 204, 21) if is_sel else ((56, 189, 248) if is_hov else (51, 65, 85))
            bw = 2 if is_sel else 1

            pygame.draw.rect(surface, bg, card_r, border_radius=6)
            pygame.draw.rect(surface, border, card_r, width=bw, border_radius=6)

            # Draw procedural vector item icon
            icon_cx = card_r.x + 18
            icon_cy = card_r.centery
            draw_item_icon(surface, item_name, icon_cx, icon_cy, size=11)

            # Draw Item Name
            display_name = item_name.replace("_", " ")
            if len(display_name) > 13:
                display_name = display_name[:11] + ".."
            name_col = (254, 240, 138) if is_sel else ((255, 255, 255) if is_hov else (226, 232, 240))
            name_surf = self.font_body.render(display_name, True, name_col)
            surface.blit(name_surf, (icon_cx + 14, card_r.centery - name_surf.get_height() // 2))

        # 7. Quantity Selector Section (JUMLAHNYA)
        qty_y = grid_y + grid_h + 12
        qty_box = pygame.Rect(mx + 20, qty_y, self.modal_w - 40, 80)
        pygame.draw.rect(surface, (20, 29, 47), qty_box, border_radius=8)
        pygame.draw.rect(surface, (51, 65, 85), qty_box, width=1, border_radius=8)

        # Quantity Label
        qlbl = self.font_sub.render("Quantity to Add:", True, (241, 245, 249))
        surface.blit(qlbl, (qty_box.x + 16, qty_box.y + 12))

        # Stepper Buttons: [-10] [-1] [  QTY  ] [+1] [+10]
        step_x = qty_box.x + 16
        step_y = qty_box.y + 36
        self.qty_btn_rects.clear()

        # Dec 10
        d10 = pygame.Rect(step_x, step_y, 42, 32)
        self.qty_btn_rects["dec_10"] = d10
        pygame.draw.rect(surface, (71, 85, 105) if d10.collidepoint(m_pos) else (51, 65, 85), d10, border_radius=4)
        t_d10 = self.font_btn.render("-10", True, (255, 255, 255))
        surface.blit(t_d10, (d10.centerx - t_d10.get_width() // 2, d10.centery - t_d10.get_height() // 2))
        step_x += 46

        # Dec 1
        d1 = pygame.Rect(step_x, step_y, 36, 32)
        self.qty_btn_rects["dec_1"] = d1
        pygame.draw.rect(surface, (71, 85, 105) if d1.collidepoint(m_pos) else (51, 65, 85), d1, border_radius=4)
        t_d1 = self.font_btn.render("-1", True, (255, 255, 255))
        surface.blit(t_d1, (d1.centerx - t_d1.get_width() // 2, d1.centery - t_d1.get_height() // 2))
        step_x += 40

        # Number Display Box
        num_box = pygame.Rect(step_x, step_y, 90, 32)
        pygame.draw.rect(surface, (15, 23, 42), num_box, border_radius=4)
        pygame.draw.rect(surface, (245, 158, 11), num_box, width=1, border_radius=4)
        q_val_surf = self.font_qty.render(str(self.quantity), True, (251, 191, 36))
        surface.blit(q_val_surf, (num_box.centerx - q_val_surf.get_width() // 2, num_box.centery - q_val_surf.get_height() // 2))
        step_x += 94

        # Inc 1
        i1 = pygame.Rect(step_x, step_y, 36, 32)
        self.qty_btn_rects["inc_1"] = i1
        pygame.draw.rect(surface, (71, 85, 105) if i1.collidepoint(m_pos) else (51, 65, 85), i1, border_radius=4)
        t_i1 = self.font_btn.render("+1", True, (255, 255, 255))
        surface.blit(t_i1, (i1.centerx - t_i1.get_width() // 2, i1.centery - t_i1.get_height() // 2))
        step_x += 40

        # Inc 10
        i10 = pygame.Rect(step_x, step_y, 42, 32)
        self.qty_btn_rects["inc_10"] = i10
        pygame.draw.rect(surface, (71, 85, 105) if i10.collidepoint(m_pos) else (51, 65, 85), i10, border_radius=4)
        t_i10 = self.font_btn.render("+10", True, (255, 255, 255))
        surface.blit(t_i10, (i10.centerx - t_i10.get_width() // 2, i10.centery - t_i10.get_height() // 2))
        step_x += 52

        # Separator line
        pygame.draw.line(surface, (51, 65, 85), (step_x, qty_box.y + 10), (step_x, qty_box.bottom - 10), 1)
        step_x += 14

        # Quick Preset Chips: [10] [50] [100] [500]
        p_lbl = self.font_badge.render("Presets:", True, (148, 163, 184))
        surface.blit(p_lbl, (step_x, qty_box.y + 12))

        preset_x = step_x
        preset_y = qty_box.y + 36
        for p_val in [10, 50, 100, 500]:
            p_rect = pygame.Rect(preset_x, preset_y, 50, 32)
            self.qty_btn_rects[f"set_{p_val}"] = p_rect
            p_hov = p_rect.collidepoint(m_pos)
            p_active = (self.quantity == p_val)

            p_bg = (59, 130, 246) if p_active else ((51, 65, 85) if p_hov else (30, 41, 59))
            pygame.draw.rect(surface, p_bg, p_rect, border_radius=4)
            pygame.draw.rect(surface, (147, 197, 253) if p_active else (71, 85, 105), p_rect, width=1, border_radius=4)

            p_surf = self.font_btn.render(str(p_val), True, (255, 255, 255))
            surface.blit(p_surf, (p_rect.centerx - p_surf.get_width() // 2, p_rect.centery - p_surf.get_height() // 2))
            preset_x += 54

        # 8. Bottom Action Row: [Cancel] and [+ ADD {qty}x {item} TO STORAGE]
        act_y = qty_y + 92

        # Cancel Button
        self.cancel_btn_rect = pygame.Rect(mx + 20, act_y, 110, 40)
        c_hov = self.cancel_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (71, 85, 105) if c_hov else (51, 65, 85), self.cancel_btn_rect, border_radius=6)
        canc_txt = self.font_btn.render("Cancel", True, (241, 245, 249))
        surface.blit(canc_txt, (self.cancel_btn_rect.centerx - canc_txt.get_width() // 2, self.cancel_btn_rect.centery - canc_txt.get_height() // 2))

        # Add Button
        add_w = self.modal_w - 40 - 120
        self.add_btn_rect = pygame.Rect(mx + 140, act_y, add_w, 40)
        a_hov = self.add_btn_rect.collidepoint(m_pos)
        a_bg = (16, 185, 129) if a_hov else (5, 150, 105)
        pygame.draw.rect(surface, a_bg, self.add_btn_rect, border_radius=6)
        pygame.draw.rect(surface, (110, 231, 183) if a_hov else (52, 211, 153), self.add_btn_rect, width=2, border_radius=6)

        item_display = self.selected_item.replace("_", " ") if self.selected_item else "Item"
        add_btn_label = f"+ ADD {self.quantity}x {item_display.upper()} TO STORAGE"
        add_txt = self.font_btn.render(add_btn_label, True, (255, 255, 255))
        surface.blit(add_txt, (self.add_btn_rect.centerx - add_txt.get_width() // 2, self.add_btn_rect.centery - add_txt.get_height() // 2))
