"""
Bottom Dock UI — Primary In-Game Action Bar & Quick Palette.
Provides an intuitive, zero-friction building and planning workflow:
- 5 Compact primary tabs (Building, Zones, Roads, Demolish, Ledger).
- Hierarchical Sub-Tray for Building with instant sub-category pills:
  [Structures] [Civic/Public] [Workstations] [Furniture].
- Procedural vector icons (100% resolution independent, no emoji glyph bugs).
- Quick palette above the dock to pick items without opening full-screen modals.
- Interactive planning pill with clear keyboard hints and one-click confirm/cancel.
"""

import pygame
from game.config import (
    BUILDING_TYPES,
    FURNITURE_TYPES,
    PERMIT_TYPES,
    ROAD_TYPES,
    COLOR_HUD_BG,
    COLOR_HUD_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
)
from game.ui.ui_theme import ui_font, upx
from game.ui.item_icons import draw_item_icon


class BottomDockUI:
    def __init__(self):
        self.active_category = None  # None | "building" | "zones" | "roads"
        self.active_building_subcat = "structures"  # "structures" | "public" | "workstations" | "furniture"
        self.hovered_item = None
        self.tooltip_text = None

        # Rect caches for mouse collision
        self.category_btn_rects = {}
        self.subcat_pill_rects = {}
        self.item_card_rects = {}
        self.pill_confirm_rect = pygame.Rect(0, 0, 0, 0)
        self.pill_cancel_rect = pygame.Rect(0, 0, 0, 0)
        self.pill_clear_rect = pygame.Rect(0, 0, 0, 0)

        # 5 Primary Tab definitions (compact, zero overlap)
        self.tabs = [
            {"id": "building", "label": "Building", "hotkey": "B"},
            {"id": "zones", "label": "Zones", "hotkey": "Z"},
            {"id": "roads", "label": "Roads", "hotkey": "P"},
            {"id": "demolish", "label": "Demolish", "hotkey": "X"},
            {"id": "ledger", "label": "Ledger", "hotkey": "R"},
        ]

        # 4 Sub-categories under Building
        self.building_subcats = [
            {"id": "structures", "label": "Structures", "hotkey": "B"},
            {"id": "public", "label": "Civic/Public", "hotkey": "C"},
            {"id": "workstations", "label": "Workstations", "hotkey": "T"},
            {"id": "furniture", "label": "Furniture", "hotkey": "F"},
        ]

    def close_palette(self):
        """Close active sub-tray palette."""
        self.active_category = None

    def get_items_for_category(self, cat_id):
        """Returns ordered list of items for the selected category."""
        # If building is requested, resolve to the current active subcategory
        target_cat = self.active_building_subcat if cat_id == "building" else cat_id

        items = []
        if target_cat == "structures":
            order = ["wooden_structure", "stone_structure"]
            for k in order:
                if k in BUILDING_TYPES:
                    cfg = BUILDING_TYPES[k]
                    name = cfg.get("name", k)
                    w_cost = cfg.get("cost_wood", 0)
                    s_cost = cfg.get("cost_stone", 0)
                    cost_str = f"{w_cost}W {s_cost}S" if (w_cost or s_cost) else "Free"
                    fixed = cfg.get("fixed_tiles_count")
                    size_str = "2x2" if fixed == 4 else ("1x1" if fixed == 1 else ("3x2" if fixed == 6 else "Drag"))
                    items.append({
                        "id": k,
                        "kind": "BUILDING",
                        "name": name,
                        "desc": cfg.get("desc", ""),
                        "cost_str": cost_str,
                        "size_str": size_str,
                        "rotatable": cfg.get("rotatable", True),
                    })
        elif target_cat == "public":
            # 1. Public Buildings (Civic amenities maintained by Lord)
            b_order = ["well", "market", "tax_house"]
            for k in b_order:
                if k in BUILDING_TYPES:
                    cfg = BUILDING_TYPES[k]
                    name = cfg.get("name", k)
                    w_cost = cfg.get("cost_wood", 0)
                    s_cost = cfg.get("cost_stone", 0)
                    cost_str = f"{w_cost}W {s_cost}S" if (w_cost or s_cost) else "Free"
                    fixed = cfg.get("fixed_tiles_count")
                    size_str = "2x2" if fixed == 4 else ("1x1" if fixed == 1 else ("3x2" if fixed == 6 else "Drag"))
                    items.append({
                        "id": k,
                        "kind": "BUILDING",
                        "name": name,
                        "desc": cfg.get("desc", ""),
                        "cost_str": cost_str,
                        "size_str": size_str,
                        "rotatable": cfg.get("rotatable", True),
                    })
            # 2. Public Fixtures (movable furniture)
            f_order = ["toilet", "notice_board", "confession_box"]
            for k in f_order:
                if k in FURNITURE_TYPES:
                    cfg = FURNITURE_TYPES[k]
                    name = cfg.get("name", k)
                    mat = cfg.get("materials", {})
                    w = mat.get("Wood", 0)
                    s = mat.get("Stone", 0)
                    cost_str = f"{w}W {s}S" if (w or s) else "Free"
                    fw = cfg.get("width_tiles", 1)
                    fh = cfg.get("height_tiles", 1)
                    items.append({
                        "id": k,
                        "kind": "FURNITURE",
                        "name": name,
                        "desc": cfg.get("desc", ""),
                        "cost_str": cost_str,
                        "size_str": f"{fw}x{fh}",
                        "rotatable": cfg.get("rotatable", True),
                    })
        elif target_cat == "workstations":
            order = ["builder_workbench", "toolmaker_workbench", "woodsman_lodge", "miner_workstation"]
            for k in order:
                if k in FURNITURE_TYPES:
                    cfg = FURNITURE_TYPES[k]
                    name = cfg.get("name", k)
                    mat = cfg.get("materials", {})
                    w = mat.get("Wood", 0)
                    s = mat.get("Stone", 0)
                    cost_str = f"{w}W {s}S" if (w or s) else "Free"
                    fw = cfg.get("width_tiles", 1)
                    fh = cfg.get("height_tiles", 1)
                    items.append({
                        "id": k,
                        "kind": "FURNITURE",
                        "name": name,
                        "desc": cfg.get("desc", ""),
                        "cost_str": cost_str,
                        "size_str": f"{fw}x{fh}",
                        "rotatable": cfg.get("rotatable", True),
                    })
        elif target_cat == "furniture":
            order = ["bed", "household_storage", "lord_treasury_chest"]
            for k in order:
                if k in FURNITURE_TYPES:
                    cfg = FURNITURE_TYPES[k]
                    name = cfg.get("name", k)
                    mat = cfg.get("materials", {})
                    w = mat.get("Wood", 0)
                    s = mat.get("Stone", 0)
                    cost_str = f"{w}W {s}S" if (w or s) else "Free"
                    fw = cfg.get("width_tiles", 1)
                    fh = cfg.get("height_tiles", 1)
                    items.append({
                        "id": k,
                        "kind": "FURNITURE",
                        "name": name,
                        "desc": cfg.get("desc", ""),
                        "cost_str": cost_str,
                        "size_str": f"{fw}x{fh}",
                        "rotatable": cfg.get("rotatable", True),
                    })
        elif target_cat == "zones":
            order = ["farm", "housing", "storage", "market", "church", "cemetery", "landlord_private"]
            for k in order:
                if k in PERMIT_TYPES:
                    cfg = PERMIT_TYPES[k]
                    name = cfg.get("name", k)
                    items.append({
                        "id": k,
                        "kind": "PERMIT",
                        "name": name,
                        "desc": cfg.get("desc", ""),
                        "cost_str": "Deed",
                        "size_str": "Area",
                        "rotatable": False,
                    })
        elif target_cat == "roads":
            order = ["dirt_road", "stone_road", "luxury_road"]
            for k in order:
                if k in ROAD_TYPES:
                    cfg = ROAD_TYPES[k]
                    name = cfg.get("name", k)
                    cost = cfg.get("cost", {})
                    w = cost.get("Wood", 0)
                    s = cost.get("Stone", 0)
                    cost_str = f"{w}W/t" if w else (f"{s}S/t" if s else "Free")
                    items.append({
                        "id": k,
                        "kind": "ROAD",
                        "name": name,
                        "desc": cfg.get("desc", ""),
                        "cost_str": cost_str,
                        "size_str": "Tile",
                        "rotatable": False,
                    })
        return items

    def handle_event(self, event, planning_mode="NONE"):
        """
        Processes mouse clicks and hotkeys.
        Returns an action dict if a build action is triggered, e.g.:
        {"action": "START_PLANNING", "kind": "BUILDING", "id": "toilet"}
        {"action": "TOGGLE_RAPORT"}
        {"action": "TOGGLE_DEMOLISH"}
        {"action": "PILL_CONFIRM"}
        {"action": "PILL_CANCEL"}
        {"action": "PILL_CLEAR"}
        """
        if event.type == pygame.KEYDOWN:
            # Hotkey handlers (only when text input in other modals is NOT active)
            if planning_mode == "NONE":
                if event.key == pygame.K_b:
                    if self.active_category == "building" and self.active_building_subcat == "structures":
                        self.close_palette()
                    else:
                        self.active_category = "building"
                        self.active_building_subcat = "structures"
                    return {"action": "HANDLED"}
                elif event.key == pygame.K_c:
                    if self.active_category == "building" and self.active_building_subcat == "public":
                        self.close_palette()
                    else:
                        self.active_category = "building"
                        self.active_building_subcat = "public"
                    return {"action": "HANDLED"}
                elif event.key in (pygame.K_t, pygame.K_k):
                    if self.active_category == "building" and self.active_building_subcat == "workstations":
                        self.close_palette()
                    else:
                        self.active_category = "building"
                        self.active_building_subcat = "workstations"
                    return {"action": "HANDLED"}
                elif event.key == pygame.K_f:
                    if self.active_category == "building" and self.active_building_subcat == "furniture":
                        self.close_palette()
                    else:
                        self.active_category = "building"
                        self.active_building_subcat = "furniture"
                    return {"action": "HANDLED"}
                elif event.key == pygame.K_z:
                    self.active_category = None if self.active_category == "zones" else "zones"
                    return {"action": "HANDLED"}
                elif event.key == pygame.K_p:
                    self.active_category = None if self.active_category == "roads" else "roads"
                    return {"action": "HANDLED"}
                elif event.key == pygame.K_x:
                    self.close_palette()
                    return {"action": "TOGGLE_DEMOLISH"}
            if event.key == pygame.K_ESCAPE:
                if self.active_category is not None:
                    self.close_palette()
                    return {"action": "HANDLED"}

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            m_pos = event.pos

            # 1. Check Planning Pill Buttons if planning
            if planning_mode != "NONE":
                if self.pill_confirm_rect.collidepoint(m_pos):
                    return {"action": "PILL_CONFIRM"}
                if self.pill_cancel_rect.collidepoint(m_pos):
                    return {"action": "PILL_CANCEL"}
                if self.pill_clear_rect.collidepoint(m_pos):
                    return {"action": "PILL_CLEAR"}
                return None

            # 2. Check Palette Sub-Category Pills (when building category is active)
            if self.active_category == "building":
                for sub_id, rect in self.subcat_pill_rects.items():
                    if rect.collidepoint(m_pos):
                        self.active_building_subcat = sub_id
                        return {"action": "HANDLED"}

            # 3. Check Palette Item Cards if category open
            if self.active_category is not None:
                for item_id, rect in self.item_card_rects.items():
                    if rect.collidepoint(m_pos):
                        items = self.get_items_for_category(self.active_category)
                        chosen = next((it for it in items if it["id"] == item_id), None)
                        self.close_palette()
                        if chosen:
                            return {
                                "action": "START_PLANNING",
                                "kind": chosen["kind"],
                                "id": chosen["id"]
                            }

            # 4. Check Dock Category Buttons
            for tab_id, rect in self.category_btn_rects.items():
                if rect.collidepoint(m_pos):
                    if tab_id == "ledger":
                        self.close_palette()
                        return {"action": "TOGGLE_RAPORT"}
                    elif tab_id == "demolish":
                        self.close_palette()
                        return {"action": "TOGGLE_DEMOLISH"}
                    elif tab_id == "building":
                        self.active_category = None if self.active_category == "building" else "building"
                        return {"action": "HANDLED"}
                    else:
                        self.active_category = None if self.active_category == tab_id else tab_id
                        return {"action": "HANDLED"}

            # 5. Clicking anywhere outside palette and dock closes palette
            if self.active_category is not None:
                self.close_palette()

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            # Right-click cancels palette
            if self.active_category is not None:
                self.close_palette()
                return {"action": "HANDLED"}

        return None

    def _draw_tab_icon(self, surface, tab_id, cx, cy, is_active):
        """Renders crisp procedural vector mini-icons (zero emoji glyph dependency)."""
        col = (255, 255, 255) if is_active else (203, 213, 225)
        if tab_id == "building":
            # House shape
            pygame.draw.polygon(surface, col, [(cx, cy - upx(5)), (cx - upx(6), cy), (cx + upx(6), cy)])
            pygame.draw.rect(surface, col, (cx - upx(4), cy, upx(8), upx(5)))
        elif tab_id == "zones":
            # Dashed perimeter zone shape
            pygame.draw.rect(surface, col, (cx - upx(5), cy - upx(5), upx(10), upx(10)), width=1)
            pygame.draw.rect(surface, col, (cx - upx(2), cy - upx(2), upx(4), upx(4)))
        elif tab_id == "roads":
            # Path road lanes
            pygame.draw.line(surface, col, (cx - upx(4), cy - upx(5)), (cx - upx(4), cy + upx(5)), 2)
            pygame.draw.line(surface, col, (cx + upx(4), cy - upx(5)), (cx + upx(4), cy + upx(5)), 2)
            pygame.draw.line(surface, col, (cx, cy - upx(2)), (cx, cy + upx(2)), 1)
        elif tab_id == "demolish":
            # Red/white cross
            dcol = (239, 68, 68) if not is_active else (255, 255, 255)
            pygame.draw.line(surface, dcol, (cx - upx(5), cy - upx(5)), (cx + upx(5), cy + upx(5)), 2)
            pygame.draw.line(surface, dcol, (cx - upx(5), cy + upx(5)), (cx + upx(5), cy - upx(5)), 2)
        elif tab_id == "ledger":
            # Document sheet
            pygame.draw.rect(surface, col, (cx - upx(4), cy - upx(5), upx(8), upx(10)), border_radius=1)
            bg = (15, 23, 42) if not is_active else (37, 99, 235)
            pygame.draw.line(surface, bg, (cx - upx(2), cy - upx(3)), (cx + upx(2), cy - upx(3)), 1)
            pygame.draw.line(surface, bg, (cx - upx(2), cy), (cx + upx(2), cy), 1)
            pygame.draw.line(surface, bg, (cx - upx(2), cy + upx(3)), (cx, cy + upx(3)), 1)

    def draw(self, surface, planning_mode="NONE", planning_info=None):
        """Renders the Bottom Dock or Planning Pill."""
        screen_w, screen_h = surface.get_size()

        if planning_mode != "NONE":
            self._draw_planning_pill(surface, screen_w, screen_h, planning_mode, planning_info)
            return

        # 1. Draw Sub-Tray Palette if active
        if self.active_category is not None:
            self._draw_sub_tray(surface, screen_w, screen_h)

        # 2. Draw Bottom Dock Bar (5 Compact Tabs)
        tab_count = len(self.tabs)
        btn_w = upx(96)
        btn_h = upx(38)
        gap = upx(6)
        bar_w = (btn_w * tab_count) + (gap * (tab_count - 1)) + upx(16)
        bar_h = btn_h + upx(12)
        bar_x = (screen_w - bar_w) // 2
        bar_y = screen_h - bar_h - upx(8)

        # Background surface with rounded border
        dock_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        pygame.draw.rect(dock_surf, (15, 23, 42, 235), (0, 0, bar_w, bar_h), border_radius=upx(10))
        pygame.draw.rect(dock_surf, (51, 65, 85, 255), (0, 0, bar_w, bar_h), width=1, border_radius=upx(10))
        surface.blit(dock_surf, (bar_x, bar_y))

        m_pos = pygame.mouse.get_pos()
        self.category_btn_rects.clear()

        cur_x = bar_x + upx(8)
        cur_y = bar_y + upx(6)

        for tab in self.tabs:
            tab_id = tab["id"]
            rect = pygame.Rect(cur_x, cur_y, btn_w, btn_h)
            self.category_btn_rects[tab_id] = rect

            is_active = (self.active_category == tab_id)
            is_hover = rect.collidepoint(m_pos)

            # Colors
            if is_active:
                bg_col = (37, 99, 235)
                border_col = (96, 165, 250)
                text_col = (255, 255, 255)
            elif is_hover:
                bg_col = (30, 41, 59)
                border_col = (100, 116, 139)
                text_col = (241, 245, 249)
            else:
                bg_col = (15, 23, 42, 180)
                border_col = (51, 65, 85)
                text_col = (203, 213, 225)

            pygame.draw.rect(surface, bg_col, rect, border_radius=upx(6))
            pygame.draw.rect(surface, border_col, rect, width=1, border_radius=upx(6))

            # Procedural Vector Icon
            icon_cx = rect.left + upx(18)
            icon_cy = rect.centery - upx(5)
            self._draw_tab_icon(surface, tab_id, icon_cx, icon_cy, is_active)

            # Label (Clean Typography)
            txt_surf = ui_font(10, bold=True).render(tab["label"], True, text_col)
            surface.blit(txt_surf, txt_surf.get_rect(midleft=(rect.left + upx(30), rect.centery - upx(5))))

            # Hotkey badge (subtle)
            hk_surf = ui_font(8).render(f"[{tab['hotkey']}]", True, (148, 163, 184) if not is_active else (191, 219, 254))
            surface.blit(hk_surf, hk_surf.get_rect(center=(rect.centerx, rect.bottom - upx(7))))

            cur_x += btn_w + gap

    def _draw_sub_tray(self, surface, screen_w, screen_h):
        """Draws the palette grid of items belonging to the active category."""
        items = self.get_items_for_category(self.active_category)
        if not items:
            return

        m_pos = pygame.mouse.get_pos()
        item_count = len(items)
        card_w = upx(104)
        card_h = upx(64)
        gap = upx(8)
        padding = upx(10)

        row2_w = (card_w * item_count) + (gap * (item_count - 1))

        # Check if building category has sub-pills row
        has_subcats = (self.active_category == "building")
        row1_h = upx(28) if has_subcats else 0
        row1_gap = upx(8) if has_subcats else 0

        subcat_w = upx(105)
        subcat_gap = upx(6)
        row1_w = (subcat_w * len(self.building_subcats)) + (subcat_gap * (len(self.building_subcats) - 1)) if has_subcats else 0

        tray_w = max(row1_w, row2_w) + (padding * 2)
        tray_h = row1_h + row1_gap + card_h + (padding * 2)

        tray_x = (screen_w - tray_w) // 2
        dock_h = upx(38) + upx(12)
        tray_y = screen_h - dock_h - upx(8) - tray_h - upx(6)

        # Background container
        tray_surf = pygame.Surface((tray_w, tray_h), pygame.SRCALPHA)
        pygame.draw.rect(tray_surf, (15, 23, 42, 240), (0, 0, tray_w, tray_h), border_radius=upx(10))
        pygame.draw.rect(tray_surf, (51, 65, 85, 255), (0, 0, tray_w, tray_h), width=1, border_radius=upx(10))
        surface.blit(tray_surf, (tray_x, tray_y))

        # Clear rect caches for new frame
        self.subcat_pill_rects.clear()
        self.item_card_rects.clear()

        # Row 1: Sub-category Pills (only when building is active)
        if has_subcats:
            subcat_start_x = tray_x + (tray_w - row1_w) // 2
            subcat_y = tray_y + padding
            cur_sub_x = subcat_start_x

            for subcat in self.building_subcats:
                sub_id = subcat["id"]
                sub_rect = pygame.Rect(cur_sub_x, subcat_y, subcat_w, row1_h)
                self.subcat_pill_rects[sub_id] = sub_rect

                is_active = (self.active_building_subcat == sub_id)
                is_hover = sub_rect.collidepoint(m_pos)

                bg_col = (37, 99, 235) if is_active else ((30, 41, 59) if is_hover else (15, 23, 42, 200))
                border_col = (96, 165, 250) if is_active else ((100, 116, 139) if is_hover else (51, 65, 85))
                text_col = (255, 255, 255) if is_active else ((241, 245, 249) if is_hover else (203, 213, 225))

                pygame.draw.rect(surface, bg_col, sub_rect, border_radius=upx(6))
                pygame.draw.rect(surface, border_col, sub_rect, width=1, border_radius=upx(6))

                lbl_txt = f"{subcat['label']} [{subcat['hotkey']}]"
                lbl_surf = ui_font(9, bold=True).render(lbl_txt, True, text_col)
                surface.blit(lbl_surf, lbl_surf.get_rect(center=sub_rect.center))

                cur_sub_x += subcat_w + subcat_gap

        # Row 2: Item Cards
        cards_start_x = tray_x + (tray_w - row2_w) // 2
        cards_y = tray_y + padding + row1_h + row1_gap
        cur_card_x = cards_start_x
        hovered_item_info = None

        for item in items:
            rect = pygame.Rect(cur_card_x, cards_y, card_w, card_h)
            self.item_card_rects[item["id"]] = rect
            is_hover = rect.collidepoint(m_pos)
            if is_hover:
                hovered_item_info = item

            # Card background
            bg_col = (30, 41, 59) if is_hover else (15, 23, 42, 200)
            border_col = (56, 189, 248) if is_hover else (51, 65, 85)
            pygame.draw.rect(surface, bg_col, rect, border_radius=upx(6))
            pygame.draw.rect(surface, border_col, rect, width=1, border_radius=upx(6))

            # Icon
            icon_y = rect.top + upx(16)
            icon_x = rect.centerx
            draw_item_icon(surface, item["id"], icon_x, icon_y, size=upx(10))

            # Name (compact)
            name_txt = item["name"]
            if len(name_txt) > 13:
                name_txt = name_txt[:11] + ".."
            name_surf = ui_font(10, bold=True).render(name_txt, True, (241, 245, 249) if is_hover else (203, 213, 225))
            surface.blit(name_surf, name_surf.get_rect(center=(rect.centerx, rect.top + upx(36))))

            # Cost Tag
            cost_surf = ui_font(9).render(item["cost_str"], True, (250, 204, 21))
            surface.blit(cost_surf, cost_surf.get_rect(center=(rect.centerx, rect.top + upx(50))))

            cur_card_x += card_w + gap

        # Tooltip for hovered item
        if hovered_item_info:
            tip_text = f"{hovered_item_info['name']} — {hovered_item_info.get('desc', '')} ({hovered_item_info['cost_str']})"
            tip_surf = ui_font(10).render(tip_text, True, (255, 255, 255))
            tip_w = tip_surf.get_width() + upx(16)
            tip_h = tip_surf.get_height() + upx(8)
            tip_x = min(screen_w - tip_w - upx(8), max(upx(8), m_pos[0] - tip_w // 2))
            tip_y = tray_y - tip_h - upx(6)

            tip_bg = pygame.Surface((tip_w, tip_h), pygame.SRCALPHA)
            pygame.draw.rect(tip_bg, (15, 23, 42, 240), (0, 0, tip_w, tip_h), border_radius=upx(4))
            pygame.draw.rect(tip_bg, (56, 189, 248), (0, 0, tip_w, tip_h), width=1, border_radius=upx(4))
            surface.blit(tip_bg, (tip_x, tip_y))
            surface.blit(tip_surf, (tip_x + upx(8), tip_y + upx(4)))

    def _draw_planning_pill(self, surface, screen_w, screen_h, planning_mode, planning_info):
        """Draws a sleek, unified action pill at the bottom when in any planning/build mode."""
        pill_w = min(upx(660), max(upx(420), screen_w - upx(20)))
        pill_h = upx(46)
        pill_x = (screen_w - pill_w) // 2
        pill_y = screen_h - pill_h - upx(10)

        # Background
        pill_surf = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pygame.draw.rect(pill_surf, (15, 23, 42, 245), (0, 0, pill_w, pill_h), border_radius=upx(10))
        border_col = (239, 68, 68) if planning_mode == "DESTROY" else (56, 189, 248)
        pygame.draw.rect(pill_surf, border_col, (0, 0, pill_w, pill_h), width=1, border_radius=upx(10))
        surface.blit(pill_surf, (pill_x, pill_y))

        m_pos = pygame.mouse.get_pos()

        # Precompute right-side button positions so left texts never overlap them
        btn_h = upx(30)
        btn_y = pill_y + upx(8)
        btn_w_confirm = upx(90)
        btn_w_cancel = upx(80)
        confirm_x = pill_x + pill_w - upx(200)
        max_text_right = confirm_x - upx(10)

        # Format title based on mode
        info = planning_info or {}
        mode_title = f"{planning_mode.replace('_', ' ').title()}"
        item_name = info.get("name", "")
        cost_info = info.get("cost_str", "")
        tiles_info = info.get("tiles_str", "")
        status_msg = info.get("status_msg", "")
        is_valid = info.get("is_valid", True)

        title_str = f"Placing: {item_name}" if item_name else mode_title
        if planning_mode == "DESTROY":
            title_str = "Demolish Mode — Click object/road to mark for removal"

        title_x = pill_x + upx(16)
        title_surf = ui_font(12, bold=True).render(title_str, True, (255, 255, 255))
        surface.blit(title_surf, (title_x, pill_y + upx(8)))

        # Total tiles badge beside the title when available
        if tiles_info:
            badge_font = ui_font(10, bold=True)
            badge_txt = badge_font.render(tiles_info, True, (125, 211, 252))
            badge_pad_x = upx(8)
            badge_pad_y = upx(2)
            badge_w = badge_txt.get_width() + badge_pad_x * 2
            badge_h = badge_txt.get_height() + badge_pad_y * 2
            badge_x = title_x + title_surf.get_width() + upx(10)
            if badge_x + badge_w <= max_text_right:
                badge_rect = pygame.Rect(badge_x, pill_y + upx(7), badge_w, badge_h)
                pygame.draw.rect(surface, (30, 58, 138), badge_rect, border_radius=upx(5))
                pygame.draw.rect(surface, (56, 189, 248), badge_rect, width=1, border_radius=upx(5))
                surface.blit(badge_txt, (badge_x + badge_pad_x, badge_rect.y + badge_pad_y))

        # Subtitle / Hints
        if planning_mode == "DESTROY":
            hint_str = "[Left Click: Mark] [Enter: Confirm] [Esc: Cancel]"
        elif info.get("rotatable"):
            hint_str = f"[L-Click: Place] [R: Rotate] [Enter: Done] [Esc: Cancel] | {cost_info}"
        else:
            hint_str = f"[L-Click: Place/Drag] [Enter: Done] [Esc: Cancel] | {cost_info}"

        hint_x = pill_x + upx(16)
        hint_surf = ui_font(9).render(hint_str, True, (148, 163, 184))
        surface.blit(hint_surf, (hint_x, pill_y + upx(26)))

        # Status / Warning text positioned dynamically right after hint_surf
        if status_msg:
            stat_col = (34, 197, 94) if is_valid else (239, 68, 68)
            stat_x = hint_x + hint_surf.get_width() + upx(12)
            avail_w = max_text_right - stat_x
            if avail_w > upx(24):
                stat_font = ui_font(9, bold=True)
                disp_stat = status_msg
                while len(disp_stat) > 4 and stat_font.size(disp_stat)[0] > avail_w:
                    disp_stat = disp_stat[:-4] + "..."
                stat_surf = stat_font.render(disp_stat, True, stat_col)
                surface.blit(stat_surf, (stat_x, pill_y + upx(26)))

        # Interactive Buttons on Pill (Confirm, Cancel)
        # 1. Confirm / Done button
        self.pill_confirm_rect = pygame.Rect(confirm_x, btn_y, btn_w_confirm, btn_h)
        c_hover = self.pill_confirm_rect.collidepoint(m_pos)
        c_bg = (34, 197, 94) if is_valid else (71, 85, 105)
        if c_hover and is_valid:
            c_bg = (22, 163, 74)
        pygame.draw.rect(surface, c_bg, self.pill_confirm_rect, border_radius=upx(6))
        c_lbl = "CONFIRM" if planning_mode in ("BUILDING", "PERMIT", "DESTROY") else "DONE"
        c_surf = ui_font(11, bold=True).render(f"✔ {c_lbl}", True, (255, 255, 255))
        surface.blit(c_surf, c_surf.get_rect(center=self.pill_confirm_rect.center))

        # 2. Cancel button
        self.pill_cancel_rect = pygame.Rect(pill_x + pill_w - upx(95), btn_y, btn_w_cancel, btn_h)
        x_hover = self.pill_cancel_rect.collidepoint(m_pos)
        x_bg = (220, 38, 38) if x_hover else (185, 28, 28)
        pygame.draw.rect(surface, x_bg, self.pill_cancel_rect, border_radius=upx(6))
        x_surf = ui_font(11, bold=True).render("✖ CANCEL", True, (255, 255, 255))
        surface.blit(x_surf, x_surf.get_rect(center=self.pill_cancel_rect.center))
