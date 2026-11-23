"""RaportUI tab view — extracted from ui_raport.py (mixin)."""

import pygame
from game.config import BUILDING_TYPES, COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, COLOR_TEXT_TITLE, COST_PER_BLOCK_STONE, COST_PER_BLOCK_WOOD, DEMOLITION_REFUND_RATIO, FURNITURE_TYPES, ROAD_TYPES, get_building_categories


class BuildingMixin:
    def _draw_building_tab(self, surface, mx, cy, building_manager, permit_manager, resources, furniture_manager=None, villager_manager=None):
        """
        Category-based Building Organization UI (Town Ledger)
        Screen 1: Lists dynamically discovered building categories with built count badges & quick construction deeds.
        Screen 2: When category is selected, displays only buildings/furniture belonging to that category with Back button & empty state.
        Zero hardcoded categories or building lists.
        """
        categories = get_building_categories()
        m_pos = pygame.mouse.get_pos()

        self.building_category_back_btn_rect = None
        self.building_category_btn_rects = {}
        self.building_owner_btn_rects = {}
        self.building_household_btn_rects.clear()
        self.destroy_building_btn_rects = {}
        self.market_profile_btn_rects.clear()
        self.building_select_rects = {}
        self.furniture_select_rects = {}
        self.road_select_rects = {}
        self.destroy_mode_btn_rect = None
        self.furniture_move_btn_rects = {}
        self.furniture_uninstall_btn_rects = {}
        self.furniture_destroy_btn_rects = {}

        if self.selected_building_category is None:
            b_title = self.font_sub.render("Buildings — Choose a Household", True, COLOR_TEXT_TITLE)
            surface.blit(b_title, (mx + 24, cy))
            sub_txt = self.font_body.render("View a household's assets directly, or open a separate Structure or Furniture list below.", True, COLOR_TEXT_MUTED)
            surface.blit(sub_txt, (mx + 28, cy + 22))

            # Destroy Mode entry: mark multiple objects on the map, then confirm once.
            self.destroy_mode_btn_rect = pygame.Rect(mx + self.modal_w - 190, cy + 16, 166, 30)
            d_hov = self.destroy_mode_btn_rect.collidepoint(m_pos)
            pygame.draw.rect(surface, (220, 38, 38) if d_hov else (153, 27, 27),
                             self.destroy_mode_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (248, 113, 113), self.destroy_mode_btn_rect, width=1, border_radius=6)
            d_lbl = self.font_badge.render("Destroy Mode", True, (255, 255, 255))
            surface.blit(d_lbl, (self.destroy_mode_btn_rect.centerx - d_lbl.get_width() // 2,
                                 self.destroy_mode_btn_rect.centery - d_lbl.get_height() // 2))

            families = getattr(villager_manager, "families", []) if villager_manager else []
            owner_rows = [(str(family.id), f"The {family.surname} Household") for family in families]
            owner_rows.append(("__public__", "Public / Unassigned"))
            row_top = cy + 48
            row_step = 52
            card_height = 82
            modal_bottom = (surface.get_height() + self.modal_h) // 2 - 18
            card_top = modal_bottom - card_height
            viewport_bottom = card_top - 14
            viewport_height = max(0, viewport_bottom - row_top)
            self.building_viewport_rect = pygame.Rect(mx + 20, row_top, self.modal_w - 40, viewport_height)
            content_height = len(owner_rows) * row_step
            self.building_max_scroll = max(0, content_height - viewport_height)
            self.building_scroll_y = max(0, min(self.building_scroll_y, self.building_max_scroll))
            old_clip = surface.get_clip()
            surface.set_clip(self.building_viewport_rect)
            for row_index, (owner_id, owner_name) in enumerate(owner_rows):
                row = pygame.Rect(mx + 30, row_top + row_index * row_step - self.building_scroll_y,
                                  self.modal_w - 60, 44)
                pygame.draw.rect(surface, (15, 23, 42), row, border_radius=5)
                pygame.draw.rect(surface, (51, 65, 85), row, width=1, border_radius=5)
                name = self.font_sub.render(owner_name, True, COLOR_TEXT_MAIN)
                surface.blit(name, (row.x + 14, row.centery - name.get_height() // 2))
                button = pygame.Rect(row.right - 126, row.y + 5, 112, row.height - 10)
                self.building_owner_btn_rects[owner_id] = button
                hovered = button.collidepoint(m_pos)
                pygame.draw.rect(surface, (30, 58, 138) if hovered else (30, 41, 59), button, border_radius=4)
                pygame.draw.rect(surface, (96, 165, 250) if hovered else (71, 85, 105), button, width=1, border_radius=4)
                action = self.font_badge.render("View Household", True, COLOR_TEXT_MAIN)
                surface.blit(action, (button.centerx - action.get_width() // 2,
                                      button.centery - action.get_height() // 2))
            surface.set_clip(old_clip)

            card_gap = 12
            card_x = mx + 24
            card_width = (self.modal_w - 48 - card_gap) // 2
            category_count = max(1, len(categories))
            card_width = (self.modal_w - 48 - card_gap * (category_count - 1)) // category_count
            for index, category in enumerate(categories):
                card = pygame.Rect(card_x + index * (card_width + card_gap), card_top, card_width, card_height)
                self.building_category_btn_rects[category["id"]] = card
                hovered = card.collidepoint(m_pos)
                color = category.get("color", (59, 130, 246))
                border = color
                pygame.draw.rect(surface, (30, 41, 59) if hovered else (15, 23, 42), card, border_radius=6)
                pygame.draw.rect(surface, border, card, width=1, border_radius=6)
                pygame.draw.rect(surface, border, (card.x, card.y, 5, card.height), border_top_left_radius=6, border_bottom_left_radius=6)
                surface.blit(self.font_sub.render(category["name"], True, COLOR_TEXT_MAIN), (card.x + 16, card.y + 11))
                surface.blit(self.font_body.render(category["desc"], True, COLOR_TEXT_MUTED), (card.x + 16, card.y + 38))
                action = self.font_badge.render("View ->", True, color)
                surface.blit(action, (card.right - action.get_width() - 12, card.bottom - action.get_height() - 8))
            return

        else:
            # -----------------------------------------------------------------
            # SCREEN 2: Category Details & Filtered Structures View
            # -----------------------------------------------------------------
            if self.selected_building_category == "household":
                current_cat = {
                    "id": "household",
                    "name": "Household Assets",
                    "desc": "Structures and furniture owned by this household.",
                    "kind": "all",
                    "building_types": list(BUILDING_TYPES.keys()),
                }
            else:
                current_cat = next((c for c in categories if c["id"] == self.selected_building_category), None)
            if not current_cat:
                self.selected_building_category = None
                return

            cat_name = current_cat["name"]
            cat_desc = current_cat["desc"]
            cat_types = current_cat["building_types"]
            demos = getattr(building_manager, "demolition_sites", [])

            if current_cat.get("kind") == "furniture":
                cat_items = [f for f in getattr(furniture_manager, "furniture", []) if f.furniture_type in cat_types] if furniture_manager else []
                b_built, b_sites, b_demos = [], [], []
            elif current_cat.get("kind") == "public":
                furniture_types = set(current_cat.get("furniture_types", ()))
                cat_items = [f for f in getattr(furniture_manager, "furniture", [])
                             if f.furniture_type in furniture_types] if furniture_manager else []
                b_built = [b for b in building_manager.buildings if getattr(b, "building_type", "") in cat_types]
                b_sites = [s for s in building_manager.construction_sites if getattr(s, "building_type", "") in cat_types]
                b_demos = [d for d in demos if getattr(d, "building_type", "") in cat_types
                           or getattr(getattr(d, "building", None), "building_type", "") in cat_types]
                cat_items.extend(b_built + b_sites + b_demos)
            elif current_cat.get("kind") == "all":
                furniture_items = list(getattr(furniture_manager, "furniture", [])) if furniture_manager else []
                b_built = list(getattr(building_manager, "buildings", []))
                b_sites = list(getattr(building_manager, "construction_sites", []))
                b_demos = list(getattr(building_manager, "demolition_sites", []))
                cat_items = furniture_items + b_built + b_sites + b_demos
            else:
                b_built = [b for b in building_manager.buildings if getattr(b, "building_type", "") in cat_types]
                b_sites = [s for s in building_manager.construction_sites if getattr(s, "building_type", "") in cat_types]
                b_demos = [d for d in demos if getattr(d, "building_type", "") in cat_types or getattr(getattr(d, "building", None), "building_type", "") in cat_types]
                cat_items = b_built + b_sites + b_demos

            owner_groups = {}
            household_families = getattr(villager_manager, "families", []) if villager_manager else []
            for family in household_families:
                owner_groups[str(family.id)] = {"name": f"The {family.surname} Household", "items": []}
            owner_groups["__public__"] = {"name": "Public / Unassigned", "items": []}
            for item in cat_items:
                is_furniture_item = hasattr(item, "furniture_type")
                owner_id = getattr(item, "family_id", None) if is_furniture_item else None
                if owner_id is None and not is_furniture_item and villager_manager and permit_manager:
                    item_tiles = getattr(item, "tiles", set())
                    for family in getattr(villager_manager, "families", []):
                        family_permit = next((permit for permit in permit_manager.permits if permit.id == family.assigned_permit_id), None)
                        if family_permit and any(tile in family_permit.tiles for tile in item_tiles):
                            owner_id = family.id
                            break
                key = str(owner_id) if owner_id is not None else "__public__"
                family = villager_manager.get_family_by_id(owner_id) if (owner_id is not None and villager_manager) else None
                group_name = f"The {family.surname} Household" if family else "Public / Unassigned"
                owner_groups.setdefault(key, {"name": group_name, "items": []})["items"].append(item)

            if self.selected_building_owner is not None:
                selected_group = owner_groups.get(str(self.selected_building_owner), {"items": []})
                selected_items = selected_group.get("items", [])
                if current_cat.get("kind") in ("furniture", "all", "public"):
                    cat_items = [item for item in selected_items
                                 if (hasattr(item, "furniture_type")
                                     if current_cat.get("kind") == "public" else True)]
                if current_cat.get("kind") in ("structure", "all"):
                    b_built = [item for item in b_built if item in selected_items]
                    b_sites = [item for item in b_sites if item in selected_items]
                    b_demos = [item for item in b_demos if item in selected_items]
                    if current_cat.get("kind") != "all":
                        cat_items = selected_items
                elif current_cat.get("kind") == "public":
                    b_built = [item for item in b_built if item in selected_items]
                    b_sites = [item for item in b_sites if item in selected_items]
                    b_demos = [item for item in b_demos if item in selected_items]
                    cat_items.extend(b_built + b_sites + b_demos)

            # 1. Back button to return to household and public locations
            back_btn = pygame.Rect(mx + 24, cy, 160, 26)
            self.building_category_back_btn_rect = back_btn
            b_hov = back_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (30, 58, 138) if b_hov else (30, 41, 59), back_btn, border_radius=4)
            pygame.draw.rect(surface, (96, 165, 250) if b_hov else (71, 85, 105), back_btn, width=1, border_radius=4)
            back_text = "← Back to Households"
            b_lbl = self.font_badge.render(back_text, True, (255, 255, 255))
            surface.blit(b_lbl, (back_btn.centerx - b_lbl.get_width() // 2, back_btn.centery - b_lbl.get_height() // 2))

            # 2. Section Title
            owner_title = owner_groups.get(str(self.selected_building_owner), {}).get("name", "Households / Public")
            title_text = f"{owner_title} — {cat_name} ({len(cat_items)} items)" if self.selected_building_owner is not None else f"Category: {cat_name} — Households / Public"
            b_title = self.font_sub.render(title_text, True, COLOR_TEXT_TITLE)
            surface.blit(b_title, (back_btn.right + 14, cy + 3))

            # 3. Subtitle / Description
            sub_txt = self.font_body.render(f"• {cat_desc}", True, COLOR_TEXT_MUTED)
            surface.blit(sub_txt, (mx + 28, cy + 32))

            y_cur = cy + 54

            modal_bottom = (surface.get_height() + self.modal_h) // 2 - 16
            action_top = modal_bottom - 78
            viewport_top = cy + 50
            viewport_height = max(0, action_top - viewport_top)
            self.building_viewport_rect = pygame.Rect(mx + 20, viewport_top, self.modal_w - 40, viewport_height)
            content_height = len(cat_items) * 26
            self.building_max_scroll = max(0, content_height - viewport_height)
            self.building_scroll_y = max(0, min(self.building_scroll_y, self.building_max_scroll))
            y_cur -= self.building_scroll_y
            old_clip = surface.get_clip()
            surface.set_clip(self.building_viewport_rect)

            # 4. Filtered List or Empty State
            if not cat_items:
                empty_box = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 54)
                pygame.draw.rect(surface, (15, 23, 42, 200), empty_box, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), empty_box, width=1, border_radius=6)
                msg1 = f"• No structures built under '{cat_name}' yet."
                msg2 = "Click the button below to construct or place a new structure for this category on the estate map."
                surface.blit(self.font_body.render(msg1, True, (203, 213, 225)), (empty_box.x + 16, empty_box.y + 10))
                surface.blit(self.font_body.render(msg2, True, COLOR_TEXT_MUTED), (empty_box.x + 16, empty_box.y + 30))
                y_cur = empty_box.bottom + 16
            else:
                if current_cat.get("kind") in ("furniture", "all", "public"):
                    for f in cat_items:
                        if not hasattr(f, "furniture_type"):
                            continue
                        owner_fam = villager_manager.get_family_by_id(f.family_id) if (villager_manager and f.family_id) else None
                        fam_str = f"The {owner_fam.surname} Family" if owner_fam else "Town / Unassigned"

                        row_rect = pygame.Rect(mx + 30, y_cur - 2, self.modal_w - 60, 24)
                        txt = f"• {f.name} at ({f.grid_x}, {f.grid_y}) — Owner: {fam_str} | Status: [{f.status}]"
                        surface.blit(self.font_body.render(txt, True, COLOR_TEXT_MAIN), (mx + 36, y_cur + 2))

                        # Move button
                        mv_btn = pygame.Rect(row_rect.right - 270, y_cur - 1, 84, 22)
                        self.furniture_move_btn_rects[f] = mv_btn
                        mv_hov = mv_btn.collidepoint(m_pos)
                        pygame.draw.rect(surface, (37, 99, 235) if mv_hov else (29, 78, 216), mv_btn, border_radius=4)
                        m_lbl = self.font_badge.render("Move", True, (255, 255, 255))
                        surface.blit(m_lbl, (mv_btn.centerx - m_lbl.get_width() // 2, mv_btn.centery - m_lbl.get_height() // 2))

                        if f.status == "INSTALLED" and f.can_be_dropped:
                            drop_btn = pygame.Rect(row_rect.right - 180, y_cur - 1, 84, 22)
                            self.furniture_uninstall_btn_rects[f] = drop_btn
                            drop_hov = drop_btn.collidepoint(m_pos)
                            pygame.draw.rect(surface, (217, 119, 6) if drop_hov else (180, 83, 9), drop_btn, border_radius=4)
                            drop_lbl = self.font_badge.render("Uninstall", True, (255, 255, 255))
                            surface.blit(drop_lbl, (drop_btn.centerx - drop_lbl.get_width() // 2, drop_btn.centery - drop_lbl.get_height() // 2))

                        # Destroy button
                        dest_btn = pygame.Rect(row_rect.right - 90, y_cur - 1, 86, 22)
                        self.furniture_destroy_btn_rects[f] = dest_btn
                        dest_hov = dest_btn.collidepoint(m_pos)
                        pygame.draw.rect(surface, (220, 38, 38) if dest_hov else (153, 27, 27), dest_btn, border_radius=4)
                        d_lbl = self.font_badge.render("Destroy", True, (255, 255, 255))
                        surface.blit(d_lbl, (dest_btn.x + (dest_btn.w - d_lbl.get_width()) // 2, dest_btn.y + 4))

                        y_cur += 26
                if current_cat.get("kind") == "all":
                    for d in b_demos:
                        pct = int((d.progress / d.duration) * 100)
                        surface.blit(self.font_body.render(f"[Demolishing] {d.name} ({pct}%)", True, (239, 68, 68)), (mx + 36, y_cur + 2))
                        y_cur += 26
                    for s in b_sites:
                        surface.blit(self.font_body.render(f"[Building] {s.name} ({s.total_delivered()}/{s.total_required()} materials)", True, (245, 158, 11)), (mx + 36, y_cur + 2))
                        y_cur += 26
                    for b in b_built:
                        surface.blit(self.font_body.render(f"{b.name} ({len(b.tiles)} tiles) | Status: Built", True, COLOR_TEXT_MAIN), (mx + 36, y_cur + 2))
                        y_cur += 26
                elif current_cat.get("kind") != "furniture":
                    # Demolition Sites
                    for d in b_demos:
                        pct = int((d.progress / d.duration) * 100)
                        txt = f"[Demolishing] {d.name} ({pct}% | Salvaging +{d.refund_wood}W, +{d.refund_stone}S)"
                        surface.blit(self.font_body.render(txt, True, (239, 68, 68)), (mx + 36, y_cur + 2))

                        c_btn = pygame.Rect(mx + self.modal_w - 120, y_cur - 1, 80, 22)
                        self.cancel_demolition_btn_rects[d] = c_btn
                        c_hov = c_btn.collidepoint(m_pos)
                        pygame.draw.rect(surface, (220, 38, 38) if c_hov else (153, 27, 27), c_btn, border_radius=4)
                        c_lbl = self.font_badge.render("Cancel", True, (255, 255, 255))
                        surface.blit(c_lbl, (c_btn.centerx - c_lbl.get_width() // 2, c_btn.centery - c_lbl.get_height() // 2))

                        y_cur += 26

                    # Construction Sites
                    for s in b_sites:
                        txt = f"[Building] {s.name} ({s.total_delivered()}/{s.total_required()} Materials)"
                        surface.blit(self.font_body.render(txt, True, (245, 158, 11)), (mx + 36, y_cur + 2))

                        cfg = BUILDING_TYPES.get(getattr(s, "building_type", ""), {})
                        order = getattr(s, "construction_order", None) or {}
                        if cfg.get("builder_commissionable"):
                            status_labels = {
                                "AWAITING_PAYMENT": "Awaiting landlord payment",
                                "LANDLORD_PAYMENT_PENDING": "Awaiting landlord payment",
                                "LANDLORD_RETRIEVING": "Servant collecting commission",
                                "PAID": "Commission paid — awaiting Builder",
                                "BUILDING": "Builder building",
                                "AWAITING_MATERIAL": "Builder gathering materials",
                                "COMPLETE": "Complete",
                            }
                            status = status_labels.get(order.get("status"), "Builder order")
                            status_text = self.font_badge.render(status, True, (56, 189, 248))
                            surface.blit(status_text, (mx + self.modal_w - status_text.get_width() - 136, y_cur + 4))

                        c_btn = pygame.Rect(mx + self.modal_w - 120, y_cur - 1, 80, 22)
                        self.cancel_construction_btn_rects[s] = c_btn
                        c_hov = c_btn.collidepoint(m_pos)
                        pygame.draw.rect(surface, (217, 119, 6) if c_hov else (180, 83, 9), c_btn, border_radius=4)
                        c_lbl = self.font_badge.render("Cancel", True, (255, 255, 255))
                        surface.blit(c_lbl, (c_btn.centerx - c_lbl.get_width() // 2, c_btn.centery - c_lbl.get_height() // 2))

                        y_cur += 26

                    # Completed Buildings
                    for b in b_built:
                        is_focused = (self.selected_building_inspect == b)
                        door_side_str = b.door_side.capitalize() if hasattr(b, "door_side") and b.door_side else "Standard"
                        b_cfg = BUILDING_TYPES.get(b.building_type, BUILDING_TYPES["wooden_structure"])
                        cost_w = b_cfg.get("cost_wood", COST_PER_BLOCK_WOOD)
                        cost_s = b_cfg.get("cost_stone", COST_PER_BLOCK_STONE)
                        ref_w = int(len(b.tiles) * cost_w * DEMOLITION_REFUND_RATIO)
                        ref_s = int(len(b.tiles) * cost_s * DEMOLITION_REFUND_RATIO)

                        row_rect = pygame.Rect(mx + 30, y_cur - 2, self.modal_w - 60, 24)
                        if is_focused:
                            pygame.draw.rect(surface, (30, 58, 138, 120), row_rect, border_radius=4)
                            pygame.draw.rect(surface, (59, 130, 246), row_rect, width=1, border_radius=4)

                        txt = f"{b.name} ({len(b.tiles)} tiles | Door: {door_side_str}) — Refund: +{ref_w}W, +{ref_s}S"
                        surface.blit(self.font_body.render(txt, True, (255, 255, 255) if is_focused else COLOR_TEXT_MAIN), (mx + 36, y_cur + 2))

                        # Contextual Button: Jump to Household if building is occupied by a family
                        tenant_fam = None
                        if villager_manager:
                            for fam in getattr(villager_manager, "families", []):
                                p_fam = next((p for p in getattr(permit_manager, "permits", []) if p.id == fam.assigned_permit_id), None) if (fam.assigned_permit_id and permit_manager) else None
                                if p_fam and any(tile in p_fam.tiles for tile in b.tiles):
                                    tenant_fam = fam
                                    break
                        if tenant_fam:
                            fam_b_btn = pygame.Rect(row_rect.right - 276, y_cur - 1, 84, 22)
                            self.building_household_btn_rects[b] = (fam_b_btn, tenant_fam.id)
                            fh_hov = fam_b_btn.collidepoint(m_pos)
                            pygame.draw.rect(surface, (14, 116, 144) if fh_hov else (15, 23, 42), fam_b_btn, border_radius=4)
                            pygame.draw.rect(surface, (56, 189, 248), fam_b_btn, width=1, border_radius=4)
                            fh_lbl = self.font_badge.render("Household", True, (255, 255, 255))
                            surface.blit(fh_lbl, (fam_b_btn.x + (fam_b_btn.w - fh_lbl.get_width()) // 2, fam_b_btn.y + 4))

                        # Market Profile Button
                        if getattr(b, "building_type", "") == "market":
                            prof_btn = pygame.Rect(row_rect.right - 180, y_cur - 1, 84, 22)
                            self.market_profile_btn_rects[b] = prof_btn
                            prof_hover = prof_btn.collidepoint(m_pos)
                            pygame.draw.rect(surface, (245, 158, 11) if prof_hover else (180, 83, 9), prof_btn, border_radius=4)
                            p_lbl = self.font_badge.render("Profile", True, (255, 255, 255))
                            surface.blit(p_lbl, (prof_btn.x + (prof_btn.w - p_lbl.get_width()) // 2, prof_btn.y + 4))

                        # Destroy Button
                        dest_btn = pygame.Rect(row_rect.right - 90, y_cur - 1, 86, 22)
                        self.destroy_building_btn_rects[b] = dest_btn
                        dest_hover = dest_btn.collidepoint(m_pos)
                        pygame.draw.rect(surface, (220, 38, 38) if dest_hover else (153, 27, 27), dest_btn, border_radius=4)
                        d_lbl = self.font_badge.render("Destroy", True, (255, 255, 255))
                        surface.blit(d_lbl, (dest_btn.x + (dest_btn.w - d_lbl.get_width()) // 2, dest_btn.y + 4))

                        y_cur += 26

            surface.set_clip(old_clip)

            if current_cat.get("kind") == "all":
                return

            # 5. Bottom Action: Construct Button(s) for this specific category
            btn_y = action_top + 8
            inst_txt = self.font_sub.render(f"Construct / Place {cat_name} (Select to Place on Map):", True, (56, 189, 248))
            surface.blit(inst_txt, (mx + 24, btn_y))

            # Furniture and building buttons share one grid — drawing them in
            # separate loops at the same row offsets made them overlap exactly
            # (e.g. Tax Office covered the Builder Workbench button).
            grid_items = []
            if current_cat.get("kind") in ("furniture", "public"):
                f_keys = (list(current_cat.get("furniture_types", ()))
                          if current_cat.get("kind") == "public"
                          else list(cat_types))
                grid_items.extend(("furniture", f_id) for f_id in f_keys)
            if current_cat.get("kind") != "furniture":
                grid_items.extend(("building", b_id) for b_id in cat_types)
            if current_cat.get("kind") == "public":
                grid_items.extend(("road", r_id) for r_id in current_cat.get("road_types", ()))

            if grid_items:
                avail_w = self.modal_w - 48
                columns = max(1, min(len(grid_items), avail_w // 180))
                item_btn_w = (avail_w - ((columns - 1) * 8)) // columns
                for idx, (item_kind, item_id) in enumerate(grid_items):
                    row, col = divmod(idx, columns)
                    item_btn = pygame.Rect(mx + 24 + col * (item_btn_w + 8), btn_y + 26 + row * 42, item_btn_w, 36)
                    hov = item_btn.collidepoint(m_pos)
                    if item_kind == "furniture":
                        f_cfg = FURNITURE_TYPES[item_id]
                        self.furniture_select_rects[item_id] = item_btn
                        b_col = (16, 185, 129) if hov else (5, 150, 105)
                        pygame.draw.rect(surface, b_col, item_btn, border_radius=6)
                        lbl_txt = (f"+ Place {f_cfg['name']}" if f_cfg.get("instant_place")
                                   else f"+ Order {f_cfg['name']}")
                    elif item_kind == "road":
                        r_cfg = ROAD_TYPES[item_id]
                        self.road_select_rects[item_id] = item_btn
                        b_col = (180, 83, 9) if hov else (120, 53, 15)
                        pygame.draw.rect(surface, b_col, item_btn, border_radius=6)
                        lbl_txt = f"+ {r_cfg['name']}"
                    else:
                        b_cfg = BUILDING_TYPES.get(item_id, {})
                        has_permit = (not b_cfg.get("allowed_permits")
                                      or any(permit_manager.has_permit_type(p_type)
                                             for p_type in b_cfg.get("allowed_permits", ())))
                        self.building_select_rects[item_id] = item_btn
                        b_col = (16, 185, 129) if has_permit else (71, 85, 105)
                        pygame.draw.rect(surface, (34, 197, 94) if (hov and has_permit) else b_col, item_btn, border_radius=6)
                        lbl_txt = f"+ {b_cfg.get('name', item_id.replace('_', ' ').title())}"
                    lbl = self.font_btn.render(lbl_txt, True, (255, 255, 255))
                    surface.blit(lbl, (item_btn.centerx - lbl.get_width() // 2, item_btn.centery - lbl.get_height() // 2))

