"""RaportUI tab view — extracted from ui_raport.py (mixin)."""

import pygame
from game.config import COLOR_TEXT_MUTED, COLOR_TEXT_TITLE, CROP_TYPES, FARMING_BATCH_GROWTH_DAYS, PERMIT_TYPES, get_permit_categories


class PermitMixin:
    def _draw_permit_row(self, surface, p, mx, y_cur, empty_areas):
        """Helper to render a single permit row with all interactive controls (Agent 2)"""
        is_empty = p in empty_areas
        is_focused = (self.selected_permit_inspect_id == p.id)

        row_rect = pygame.Rect(mx + 30, y_cur - 2, self.modal_w - 60, 24)
        if is_focused:
            pygame.draw.rect(surface, (30, 58, 138, 140), row_rect, border_radius=4)
            pygame.draw.rect(surface, (59, 130, 246), row_rect, width=1, border_radius=4)

        status_str = "Empty" if is_empty else "Occupied"
        col = (245, 158, 11) if is_empty else (16, 185, 129)
        prefix = "[Private] " if p.permit_type == "landlord_private" else ""

        if p.permit_type == "farm":
            if getattr(p, "crop", None):
                w_tag = "Watered" if getattr(p, "watered_today", False) else "Dry"
                crop_cfg = CROP_TYPES.get(str(p.crop).lower(), {})
                growth_target = float(crop_cfg.get("growth_days", FARMING_BATCH_GROWTH_DAYS))
                crop_str = f"{p.crop} (Day {getattr(p, 'growth_days', 0.0):.0f}/{growth_target:g} | {w_tag})"
            else:
                crop_str = "Unplanted"
            col = (34, 197, 94)
            txt = f"• {p.name} [{len(p.tiles)}t Farm] — {crop_str}"
            surface.blit(self.font_body.render(txt, True, col), (mx + 36, y_cur + 2))

            # Right side buttons
            right_cursor = row_rect.right

            # Delete button if empty
            if is_empty:
                del_btn = pygame.Rect(right_cursor - 84, y_cur - 1, 82, 22)
                self.delete_permit_btn_rects[p.id] = del_btn
                del_hover = del_btn.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (220, 38, 38) if del_hover else (153, 27, 27), del_btn, border_radius=4)
                del_lbl = self.font_badge.render("Delete", True, (255, 255, 255))
                surface.blit(del_lbl, (del_btn.x + (del_btn.w - del_lbl.get_width()) // 2, del_btn.y + 4))
                right_cursor -= 88

            # Edit Lot button
            edit_btn = pygame.Rect(right_cursor - 64, y_cur - 1, 60, 22)
            self.edit_permit_btn_rects[p.id] = edit_btn
            edit_hov = edit_btn.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (202, 138, 4) if edit_hov else (161, 98, 7), edit_btn, border_radius=4)
            pygame.draw.rect(surface, (250, 204, 21), edit_btn, width=1, border_radius=4)
            edit_lbl = self.font_badge.render("Edit", True, (255, 255, 255))
            surface.blit(edit_lbl, (edit_btn.x + (edit_btn.w - edit_lbl.get_width()) // 2, edit_btn.y + 4))

            # Contextual Navigation: Household button if lot is assigned to a family
            if getattr(p, "assigned_family_id", None):
                fam_btn = pygame.Rect(edit_btn.left - 88, y_cur - 1, 82, 22)
                self.permit_household_btn_rects[p.id] = (fam_btn, p.assigned_family_id)
                f_hov = fam_btn.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (14, 116, 144) if f_hov else (15, 23, 42), fam_btn, border_radius=4)
                pygame.draw.rect(surface, (56, 189, 248), fam_btn, width=1, border_radius=4)
                f_lbl = self.font_badge.render("Household", True, (255, 255, 255))
                surface.blit(f_lbl, (fam_btn.x + (fam_btn.w - f_lbl.get_width()) // 2, fam_btn.y + 4))
            right_cursor -= 68

            # Worker Controls: [⚡ Auto] [+] {count/max} [-]
            auto_btn = pygame.Rect(right_cursor - 28, y_cur - 1, 26, 22)
            self.worker_auto_btn_rects[p.id] = auto_btn
            a_hov = auto_btn.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (16, 185, 129) if a_hov else (5, 150, 105), auto_btn, border_radius=3)
            a_txt = self.font_badge.render("Auto", True, (255, 255, 255))
            surface.blit(a_txt, (auto_btn.x + 6, auto_btn.y + 4))
            right_cursor -= 32

            w_count = len(getattr(p, 'assigned_workers', set()))
            w_max = getattr(p, 'max_workers', 2)
            cnt_str = f"{w_count} Workers"
            cnt_surf = self.font_badge.render(cnt_str, True, (241, 245, 249))
            surface.blit(cnt_surf, (right_cursor - cnt_surf.get_width() - 4, y_cur + 3))
            right_cursor -= (cnt_surf.get_width() + 8)

            cap_key = ("num", "permit_max", p.id)
            cap_rect = pygame.Rect(right_cursor - 36, y_cur - 1, 36, 22)
            self.num_fields[cap_key] = {"rect": cap_rect, "kind": "permit_max",
                                        "payload": p.id, "min": 0, "max": 99}
            surface.blit(self.font_badge.render("Max:", True, COLOR_TEXT_MUTED),
                         (cap_rect.x - 32, y_cur + 3))
            self._draw_num_input(surface, cap_key, cap_rect, w_max)

        elif p.permit_type in ("church", "cemetery"):
            p_workers = getattr(p, "assigned_workers", [])
            w_count = len(p_workers)
            w_max = getattr(p, "max_workers", 1 if p.permit_type == "church" else 2)
            worker_label = "Priest" if p.permit_type == "church" else "Gravedigger"
            status_str = f"{w_count}/{w_max} {worker_label} Assigned" if w_count > 0 else f"No {worker_label} Assigned"
            col = (168, 85, 247) if p.permit_type == "church" else (148, 163, 184)
            p_title_str = "Church" if p.permit_type == "church" else "Cemetery"
            txt = f"• {p.name} [{len(p.tiles)} tiles {p_title_str}] — {status_str}"
            surface.blit(self.font_body.render(txt, True, col), (mx + 36, y_cur + 2))

            right_cursor = row_rect.right
            # Delete button for empty permits
            if is_empty:
                del_btn = pygame.Rect(right_cursor - 84, y_cur - 1, 82, 22)
                self.delete_permit_btn_rects[p.id] = del_btn
                del_hover = del_btn.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (220, 38, 38) if del_hover else (153, 27, 27), del_btn, border_radius=4)
                del_lbl = self.font_badge.render("Delete", True, (255, 255, 255))
                surface.blit(del_lbl, (del_btn.x + (del_btn.w - del_lbl.get_width()) // 2, del_btn.y + 4))
                right_cursor -= 88

            # Edit Lot button
            edit_btn = pygame.Rect(right_cursor - 64, y_cur - 1, 60, 22)
            self.edit_permit_btn_rects[p.id] = edit_btn
            edit_hov = edit_btn.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (202, 138, 4) if edit_hov else (161, 98, 7), edit_btn, border_radius=4)
            pygame.draw.rect(surface, (250, 204, 21), edit_btn, width=1, border_radius=4)
            edit_lbl = self.font_badge.render("Edit", True, (255, 255, 255))
            surface.blit(edit_lbl, (edit_btn.x + (edit_btn.w - edit_lbl.get_width()) // 2, edit_btn.y + 4))
            right_cursor -= 68

            # Worker cap input (typable)
            cnt_str = f"{w_count} Workers"
            cnt_surf = self.font_badge.render(cnt_str, True, (241, 245, 249))
            surface.blit(cnt_surf, (right_cursor - cnt_surf.get_width() - 4, y_cur + 3))
            right_cursor -= (cnt_surf.get_width() + 8)

            cap_key = ("num", "permit_max", p.id)
            cap_rect = pygame.Rect(right_cursor - 36, y_cur - 1, 36, 22)
            self.num_fields[cap_key] = {"rect": cap_rect, "kind": "permit_max",
                                        "payload": p.id, "min": 0, "max": 99}
            surface.blit(self.font_badge.render("Max:", True, COLOR_TEXT_MUTED),
                         (cap_rect.x - 32, y_cur + 3))
            self._draw_num_input(surface, cap_key, cap_rect, w_max)

        else:
            txt = f"• {prefix}{p.name} [{len(p.tiles)} tiles {p.permit_type.capitalize()}] — {status_str}"
            surface.blit(self.font_body.render(txt, True, col), (mx + 36, y_cur + 2))

            right_cursor = row_rect.right
            # Delete button for empty permits
            if is_empty:
                del_btn = pygame.Rect(right_cursor - 84, y_cur - 1, 82, 22)
                self.delete_permit_btn_rects[p.id] = del_btn
                del_hover = del_btn.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (220, 38, 38) if del_hover else (153, 27, 27), del_btn, border_radius=4)
                del_lbl = self.font_badge.render("Delete", True, (255, 255, 255))
                surface.blit(del_lbl, (del_btn.x + (del_btn.w - del_lbl.get_width()) // 2, del_btn.y + 4))
                right_cursor -= 88

            # Edit Lot button
            edit_btn = pygame.Rect(right_cursor - 64, y_cur - 1, 60, 22)
            self.edit_permit_btn_rects[p.id] = edit_btn
            edit_hov = edit_btn.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (202, 138, 4) if edit_hov else (161, 98, 7), edit_btn, border_radius=4)
            pygame.draw.rect(surface, (250, 204, 21), edit_btn, width=1, border_radius=4)
            edit_lbl = self.font_badge.render("Edit", True, (255, 255, 255))
            surface.blit(edit_lbl, (edit_btn.x + (edit_btn.w - edit_lbl.get_width()) // 2, edit_btn.y + 4))

            # Contextual Navigation: Household button if lot is assigned to a family
            if getattr(p, "assigned_family_id", None):
                fam_btn = pygame.Rect(edit_btn.left - 88, y_cur - 1, 82, 22)
                self.permit_household_btn_rects[p.id] = (fam_btn, p.assigned_family_id)
                f_hov = fam_btn.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (14, 116, 144) if f_hov else (15, 23, 42), fam_btn, border_radius=4)
                pygame.draw.rect(surface, (56, 189, 248), fam_btn, width=1, border_radius=4)
                f_lbl = self.font_badge.render("Household", True, (255, 255, 255))
                surface.blit(f_lbl, (fam_btn.x + (fam_btn.w - f_lbl.get_width()) // 2, fam_btn.y + 4))

    def _draw_permit_tab(self, surface, mx, cy, permit_manager, building_manager):
        """
        Category-based Permit Organization UI (Agent 2)
        Screen 1: Lists dynamically discovered permit categories with lot count badges.
        Screen 2: When category is selected, displays only permits belonging to that category with Back button & empty state.
        Zero hardcoded categories or permit lists.
        """
        categories = get_permit_categories()
        empty_areas, occupied_areas = permit_manager.get_permits_status(building_manager)
        m_pos = pygame.mouse.get_pos()

        self.permit_category_back_btn_rect = None
        self.permit_category_btn_rects = {}
        self.permit_household_btn_rects.clear()
        self.delete_permit_btn_rects = {}
        self.edit_permit_btn_rects = {}
        self.open_plant_btn_rects = {}
        self.worker_auto_btn_rects = {}
        self.permit_btn_rects = {}

        if self.selected_permit_category is None:
            # -----------------------------------------------------------------
            # SCREEN 1: Permit Categories Selection Screen
            # -----------------------------------------------------------------
            p_title = self.font_sub.render(f" Landlord Permit Categories ({len(categories)} categories, {len(permit_manager.permits)} total lots):", True, COLOR_TEXT_TITLE)
            surface.blit(p_title, (mx + 24, cy))

            sub_txt = self.font_body.render("Select a category below to inspect and manage designated lots, or quick-issue a permit:", True, COLOR_TEXT_MUTED)
            surface.blit(sub_txt, (mx + 28, cy + 22))

            card_y = cy + 44
            for cat in categories:
                cat_id = cat["id"]
                cat_name = cat["name"]
                cat_desc = cat["desc"]
                cat_col = cat.get("color", (59, 130, 246))
                cat_permits = [p for p in permit_manager.permits if p.permit_type in cat["permit_types"]]
                lot_count = len(cat_permits)

                card_rect = pygame.Rect(mx + 24, card_y, self.modal_w - 48, 32)
                self.permit_category_btn_rects[cat_id] = card_rect

                is_hov = card_rect.collidepoint(m_pos)
                bg_col = (30, 41, 59) if is_hov else (15, 23, 42)
                border_col = (56, 189, 248) if is_hov else (51, 65, 85)

                pygame.draw.rect(surface, bg_col, card_rect, border_radius=6)
                pygame.draw.rect(surface, border_col, card_rect, width=1, border_radius=6)

                # Left color accent bar
                accent_rect = pygame.Rect(card_rect.x, card_rect.y, 5, card_rect.height)
                pygame.draw.rect(surface, cat_col, accent_rect, border_top_left_radius=6, border_bottom_left_radius=6)

                # Category title & description
                t_surf = self.font_sub.render(cat_name, True, (241, 245, 249) if is_hov else (226, 232, 240))
                surface.blit(t_surf, (card_rect.x + 16, card_rect.y + 7))

                desc_surf = self.font_body.render(f"— {cat_desc}", True, COLOR_TEXT_MUTED)
                surface.blit(desc_surf, (card_rect.x + 22 + t_surf.get_width(), card_rect.y + 8))

                # Right badges: Lot count and "View Lots →"
                badge_w = 80
                badge_rect = pygame.Rect(card_rect.right - badge_w - 12, card_rect.y + 5, badge_w, 22)
                badge_bg = (22, 101, 52) if lot_count > 0 else (51, 65, 85)
                badge_border = (74, 222, 128) if lot_count > 0 else (100, 116, 139)
                pygame.draw.rect(surface, badge_bg, badge_rect, border_radius=4)
                pygame.draw.rect(surface, badge_border, badge_rect, width=1, border_radius=4)

                lbl_text = f"{lot_count} Lots" if lot_count != 1 else "1 Lot"
                cnt_txt = self.font_badge.render(lbl_text, True, (255, 255, 255))
                surface.blit(cnt_txt, (badge_rect.centerx - cnt_txt.get_width() // 2, badge_rect.centery - cnt_txt.get_height() // 2))

                arrow_lbl = self.font_badge.render("View →", True, (56, 189, 248) if is_hov else (148, 163, 184))
                surface.blit(arrow_lbl, (badge_rect.x - arrow_lbl.get_width() - 10, card_rect.y + 9))

                card_y += 36

            # Bottom: Quick Issue New Landlord Permits
            btn_y = max(cy + 250, card_y + 4)
            inst_txt = self.font_sub.render("Issue New Landlord Permits (Select, then Click & Drag on Map to Size):", True, (56, 189, 248))
            surface.blit(inst_txt, (mx + 24, btn_y))

            total_avail_w = self.modal_w - 48
            btn_gap = 8

            # Row 1 (4 buttons: Housing, Storage, Market, Farm)
            w4 = (total_avail_w - (3 * btn_gap)) // 4
            housing_btn = pygame.Rect(mx + 24 + 0 * (w4 + btn_gap), btn_y + 24, w4, 30)
            storage_btn = pygame.Rect(mx + 24 + 1 * (w4 + btn_gap), btn_y + 24, w4, 30)
            market_btn = pygame.Rect(mx + 24 + 2 * (w4 + btn_gap), btn_y + 24, w4, 30)
            farm_btn = pygame.Rect(mx + 24 + 3 * (w4 + btn_gap), btn_y + 24, w4, 30)

            # Row 2 (3 buttons: Church, Cemetery, Private Area)
            w3 = (total_avail_w - (2 * btn_gap)) // 3
            church_btn = pygame.Rect(mx + 24 + 0 * (w3 + btn_gap), btn_y + 58, w3, 30)
            cemetery_btn = pygame.Rect(mx + 24 + 1 * (w3 + btn_gap), btn_y + 58, w3, 30)
            private_btn = pygame.Rect(mx + 24 + 2 * (w3 + btn_gap), btn_y + 58, w3, 30)

            self.permit_btn_rects["housing"] = housing_btn
            self.permit_btn_rects["storage"] = storage_btn
            self.permit_btn_rects["market"] = market_btn
            self.permit_btn_rects["farm"] = farm_btn
            self.permit_btn_rects["church"] = church_btn
            self.permit_btn_rects["cemetery"] = cemetery_btn
            self.permit_btn_rects["landlord_private"] = private_btn

            # 1. Housing Permit Button
            h_hov = housing_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (59, 130, 246) if h_hov else (37, 99, 235), housing_btn, border_radius=6)
            pygame.draw.rect(surface, (147, 197, 253) if h_hov else (96, 165, 250), housing_btn, width=1, border_radius=6)
            h_lbl = self.font_btn.render("+ Housing Permit", True, (255, 255, 255))
            surface.blit(h_lbl, (housing_btn.centerx - h_lbl.get_width() // 2, housing_btn.centery - h_lbl.get_height() // 2))

            # 2. Storage Permit Button
            s_hov = storage_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (234, 179, 8) if s_hov else (202, 138, 4), storage_btn, border_radius=6)
            pygame.draw.rect(surface, (253, 224, 71) if s_hov else (250, 204, 21), storage_btn, width=1, border_radius=6)
            s_lbl = self.font_btn.render("+ Storage Permit", True, (255, 255, 255))
            surface.blit(s_lbl, (storage_btn.centerx - s_lbl.get_width() // 2, storage_btn.centery - s_lbl.get_height() // 2))

            # 3. Market Permit Button
            m_hov = market_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (245, 158, 11) if m_hov else (217, 119, 6), market_btn, border_radius=6)
            pygame.draw.rect(surface, (253, 230, 138) if m_hov else (251, 191, 36), market_btn, width=1, border_radius=6)
            m_lbl = self.font_btn.render("+ Market Permit", True, (255, 255, 255))
            surface.blit(m_lbl, (market_btn.centerx - m_lbl.get_width() // 2, market_btn.centery - m_lbl.get_height() // 2))

            # 4. Farm Permit Button
            f_hov = farm_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (34, 197, 94) if f_hov else (22, 101, 52), farm_btn, border_radius=6)
            pygame.draw.rect(surface, (134, 239, 172) if f_hov else (74, 222, 128), farm_btn, width=1, border_radius=6)
            f_lbl = self.font_btn.render("+ Farm Permit", True, (255, 255, 255))
            surface.blit(f_lbl, (farm_btn.centerx - f_lbl.get_width() // 2, farm_btn.centery - f_lbl.get_height() // 2))

            # 5. Church Permit Button
            ch_hov = church_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (168, 85, 247) if ch_hov else (147, 51, 234), church_btn, border_radius=6)
            pygame.draw.rect(surface, (216, 180, 254) if ch_hov else (192, 132, 252), church_btn, width=1, border_radius=6)
            ch_lbl = self.font_btn.render("+ Church Permit", True, (255, 255, 255))
            surface.blit(ch_lbl, (church_btn.centerx - ch_lbl.get_width() // 2, church_btn.centery - ch_lbl.get_height() // 2))

            # 6. Cemetery Permit Button
            cm_hov = cemetery_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (100, 116, 139) if cm_hov else (71, 85, 105), cemetery_btn, border_radius=6)
            pygame.draw.rect(surface, (203, 213, 225) if cm_hov else (148, 163, 184), cemetery_btn, width=1, border_radius=6)
            cm_lbl = self.font_btn.render("+ Cemetery Permit", True, (255, 255, 255))
            surface.blit(cm_lbl, (cemetery_btn.centerx - cm_lbl.get_width() // 2, cemetery_btn.centery - cm_lbl.get_height() // 2))

            # 7. Landlord Private Area Button
            p_hov = private_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (126, 34, 206) if p_hov else (88, 28, 135), private_btn, border_radius=6)
            pygame.draw.rect(surface, (250, 204, 21) if p_hov else (234, 179, 8), private_btn, width=1, border_radius=6)
            p_lbl = self.font_btn.render("+ Private Area", True, (255, 255, 255))
            surface.blit(p_lbl, (private_btn.centerx - p_lbl.get_width() // 2, private_btn.centery - p_lbl.get_height() // 2))

        else:
            # -----------------------------------------------------------------
            # SCREEN 2: Category Details & Filtered Permits View
            # -----------------------------------------------------------------
            current_cat = next((c for c in categories if c["id"] == self.selected_permit_category), None)
            if not current_cat:
                self.selected_permit_category = None
                return

            cat_name = current_cat["name"]
            cat_desc = current_cat["desc"]
            cat_types = current_cat["permit_types"]
            category_permits = [p for p in permit_manager.permits if p.permit_type in cat_types]

            # 1. Back button to return to category selection screen
            back_btn = pygame.Rect(mx + 24, cy, 160, 26)
            self.permit_category_back_btn_rect = back_btn
            b_hov = back_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (30, 58, 138) if b_hov else (30, 41, 59), back_btn, border_radius=4)
            pygame.draw.rect(surface, (96, 165, 250) if b_hov else (71, 85, 105), back_btn, width=1, border_radius=4)
            b_lbl = self.font_badge.render("← Back to Categories", True, (255, 255, 255))
            surface.blit(b_lbl, (back_btn.centerx - b_lbl.get_width() // 2, back_btn.centery - b_lbl.get_height() // 2))

            # 2. Section Title (Displays Category Name as required)
            p_title = self.font_sub.render(f"Category: {cat_name} ({len(category_permits)} lots)", True, COLOR_TEXT_TITLE)
            surface.blit(p_title, (back_btn.right + 14, cy + 3))

            # 3. Subtitle / Description
            sub_txt = self.font_body.render(f"• {cat_desc}", True, COLOR_TEXT_MUTED)
            surface.blit(sub_txt, (mx + 28, cy + 32))

            y_cur = cy + 54

            # 4. Filtered Permits List or Empty State
            if not category_permits:
                empty_box = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 54)
                pygame.draw.rect(surface, (15, 23, 42, 200), empty_box, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), empty_box, width=1, border_radius=6)
                msg1 = f"• No active permits issued under '{cat_name}' yet."
                msg2 = "Click the button below to issue and drag a new lot for this category on the estate map."
                surface.blit(self.font_body.render(msg1, True, (203, 213, 225)), (empty_box.x + 16, empty_box.y + 10))
                surface.blit(self.font_body.render(msg2, True, COLOR_TEXT_MUTED), (empty_box.x + 16, empty_box.y + 30))
                y_cur = empty_box.bottom + 16
            else:
                for p in category_permits:
                    self._draw_permit_row(surface, p, mx, y_cur, empty_areas)
                    y_cur += 26

            # 5. Bottom Action: Issue New Permit for this specific category
            btn_y = max(y_cur + 20, cy + 220)
            inst_txt = self.font_sub.render(f"Issue New {cat_name} (Select, then Click & Drag on Map to Size):", True, (56, 189, 248))
            surface.blit(inst_txt, (mx + 24, btn_y))

            avail_w = self.modal_w - 48
            k = len(cat_types)
            c_btn_w = min(180, (avail_w - ((k - 1) * 8)) // max(1, k))
            for idx, p_type in enumerate(cat_types):
                p_cfg = PERMIT_TYPES.get(p_type, {})
                p_btn = pygame.Rect(mx + 24 + idx * (c_btn_w + 8), btn_y + 26, c_btn_w, 36)
                self.permit_btn_rects[p_type] = p_btn
                hov = p_btn.collidepoint(m_pos)
                raw_col = p_cfg.get("color", (59, 130, 246, 60))
                rgb_col = (raw_col[0], raw_col[1], raw_col[2])
                brd_col = p_cfg.get("border_color", (96, 165, 250))
                pygame.draw.rect(surface, brd_col if hov else rgb_col, p_btn, border_radius=6)
                pygame.draw.rect(surface, (255, 255, 255) if hov else brd_col, p_btn, width=1, border_radius=6)
                b_text = f"+ {p_cfg.get('name', p_type.capitalize())}"
                lbl = self.font_btn.render(b_text, True, (255, 255, 255))
                surface.blit(lbl, (p_btn.centerx - lbl.get_width() // 2, p_btn.centery - lbl.get_height() // 2))

        self._draw_crop_picker_popup(surface, mx, cy, permit_manager)

    def _draw_crop_picker_popup(self, surface, mx, cy, permit_manager):
        # Crop Selection Popup Dialog
        self.crop_select_btn_rects = {}
        if self.crop_picker_permit_id:
            target_p = next((p for p in permit_manager.permits if p.id == self.crop_picker_permit_id), None)
            pop_w = 480
            pop_h = 240
            pop_x = mx + (self.modal_w - pop_w) // 2
            pop_y = cy + 10
            self.crop_picker_bg_rect = pygame.Rect(pop_x, pop_y, pop_w, pop_h)

            # Dim backdrop around popup inside modal
            dim_pop = pygame.Surface((pop_w, pop_h), pygame.SRCALPHA)
            pygame.draw.rect(dim_pop, (15, 23, 42, 250), (0, 0, pop_w, pop_h), border_radius=10)
            pygame.draw.rect(dim_pop, (74, 222, 128), (0, 0, pop_w, pop_h), width=2, border_radius=10)
            surface.blit(dim_pop, (pop_x, pop_y))

            p_title_str = target_p.name if target_p else "Farm Lot"
            head_txt = self.font_sub.render(f"Select Crop for {p_title_str}:", True, (74, 222, 128))
            surface.blit(head_txt, (pop_x + 16, pop_y + 14))

            # Close button
            self.close_crop_picker_btn_rect = pygame.Rect(pop_x + pop_w - 30, pop_y + 12, 18, 18)
            pygame.draw.rect(surface, (220, 38, 38), self.close_crop_picker_btn_rect, border_radius=3)
            x_txt = self.font_badge.render("X", True, (255, 255, 255))
            surface.blit(x_txt, (self.close_crop_picker_btn_rect.x + 4, self.close_crop_picker_btn_rect.y + 2))

            crop_y = pop_y + 44
            for c_id, c_cfg in CROP_TYPES.items():
                is_wip = c_cfg.get("wip", False)
                row_r = pygame.Rect(pop_x + 16, crop_y, pop_w - 32, 40)
                pygame.draw.rect(surface, (30, 41, 59), row_r, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), row_r, width=1, border_radius=6)

                # Icon & Name
                c_title = self.font_sub.render(f"{c_cfg['icon']} {c_cfg['name']}", True, (255, 255, 255) if not is_wip else COLOR_TEXT_MUTED)
                surface.blit(c_title, (row_r.x + 10, row_r.y + 4))

                # Desc
                c_desc = self.font_badge.render(c_cfg['desc'], True, (148, 163, 184) if not is_wip else (100, 116, 139))
                surface.blit(c_desc, (row_r.x + 10, row_r.y + 22))

                # Button
                btn_r = pygame.Rect(row_r.right - 100, row_r.y + 8, 90, 24)
                self.crop_select_btn_rects[c_id] = btn_r

                if is_wip:
                    pygame.draw.rect(surface, (51, 65, 85), btn_r, border_radius=4)
                    b_txt = self.font_badge.render("WIP", True, (148, 163, 184))
                else:
                    is_active = (target_p and getattr(target_p, "crop", None) == c_cfg["name"])
                    btn_col = (16, 185, 129) if not is_active else (37, 99, 235)
                    pygame.draw.rect(surface, btn_col, btn_r, border_radius=4)
                    b_txt = self.font_badge.render("PLANTED" if is_active else "PLANT", True, (255, 255, 255))

                surface.blit(b_txt, (btn_r.x + (btn_r.w - b_txt.get_width()) // 2, btn_r.y + 5))

                crop_y += 46

