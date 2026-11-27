"""Toolmaker Workbench catalogue: forge tool commissions with qty per order (Job Sets & Single Tools)."""

import pygame

from game.data.config import COLOR_MODAL_BG, COLOR_MODAL_BORDER, COLOR_TEXT_TITLE, COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, TOOLMAKER_TOOL_RECIPE
from game.systems.work.toolmaker_system import ToolmakerSystem
from game.systems.work.builder_system import BuilderSystem
from game.systems.economy.currency import from_copper
from game.ui.ui_theme import ui_font, upx

JOB_TOOL_SETS = {
    "Farmer": {
        "title": "Farmer Set",
        "desc": "Tills, waters, and harvests crops",
        "tools": ["Hoe", "Watering_Can", "Sickle"],
    },
    "Woodsman": {
        "title": "Woodsman Set",
        "desc": "Fells trees and plants saplings",
        "tools": ["Felling_Axe", "Spade"],
    },
    "Miner": {
        "title": "Miner Set",
        "desc": "Excavates ore and breaks stone",
        "tools": ["Pickaxe", "Sledgehammer"],
    },
    "Builder": {
        "title": "Builder Set",
        "desc": "Saws timber, shapes wood, and constructs",
        "tools": ["Saw", "Adze", "Hammer"],
    },
    "Gravedigger": {
        "title": "Gravedigger Set",
        "desc": "Prepares graves and cemetery plots",
        "tools": ["Hoe"],
    },
    "Toolmaker": {
        "title": "Toolmaker Set",
        "desc": "Forges iron tools and metalwork",
        "tools": ["Hammer", "Tongs"],
    },
}


class ToolmakerCatalogModal:
    def __init__(self):
        self.is_open = False
        self.workbench = None
        self.modal_rect = None
        self.close_rect = None
        self.viewport_rect = None
        self.current_tab = "JOB_SETS"  # "JOB_SETS", "SINGLE_TOOLS", or "OUTPUT_RACK"
        self.tab_rects = {}
        self.order_rects = {}
        self.qty_rects = {}
        self.rack_action_rects = {}
        self.quantity_values = {}
        self.scroll_y = 0
        self.max_scroll = 0
        self.status_message = None
        self.font_title = None
        self.font_sub = None
        self.font_body = None
        self.font_badge = None
        self.font_btn = None

    def open(self, workbench):
        self.workbench = workbench
        self.last_workbench = workbench
        if workbench:
            ToolmakerSystem.clean_completed_orders(workbench)
        self.is_open = True
        self.scroll_y = 0
        self.status_message = None
        self.current_tab = "JOB_SETS"
        self._focused_qty = None

    def close(self):
        self.is_open = False
        if self.workbench:
            self.last_workbench = self.workbench
        self.workbench = None
        self._focused_qty = None

    def _ensure_fonts(self):
        if self.font_title is None:
            self.font_title = ui_font(19, bold=True)
            self.font_sub = ui_font(12)
            self.font_body = ui_font(13)
            self.font_badge = ui_font(11, bold=True)
            self.font_btn = ui_font(12, bold=True)

    def handle_event(self, event):
        if not self.is_open:
            return None
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
                return "close"
            if self._focused_qty is not None:
                cur = self.quantity_values.get(self._focused_qty, "1")
                if event.key == pygame.K_BACKSPACE:
                    self.quantity_values[self._focused_qty] = cur[:-1]
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._focused_qty = None
                elif event.unicode.isdigit() and len(cur) < 3:
                    self.quantity_values[self._focused_qty] = cur + event.unicode
                return None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.close_rect and self.close_rect.collidepoint(event.pos):
                self.close()
                return "close"
            for tab_name, rect in self.tab_rects.items():
                if rect.collidepoint(event.pos):
                    if self.current_tab != tab_name:
                        self.current_tab = tab_name
                        self.scroll_y = 0
                        self._focused_qty = None
                    return "tab_change"
            for item_name, rect in self.qty_rects.items():
                if rect.collidepoint(event.pos):
                    self._focused_qty = item_name
                    self.quantity_values.setdefault(item_name, "1")
                    return None
            if self.viewport_rect and self.viewport_rect.collidepoint(event.pos):
                if self.current_tab == "OUTPUT_RACK":
                    for act_key, rect in self.rack_action_rects.items():
                        if rect.collidepoint(event.pos):
                            if act_key.startswith("TAKE|"):
                                _, tool_name = act_key.split("|", 1)
                                return f"tool_take_{tool_name}"
                            elif act_key.startswith("HAUL|"):
                                _, tool_name = act_key.split("|", 1)
                                return f"tool_haul_{tool_name}"
                for order_key, rect in self.order_rects.items():
                    if rect.collidepoint(event.pos):
                        if order_key.startswith("SET|"):
                            _, job_id, qty = order_key.split("|")
                            try:
                                qty_i = max(1, min(100, int(qty)))
                            except (TypeError, ValueError):
                                qty_i = 1
                            self.close()
                            return f"tool_order_set_{job_id}_{qty_i}"
                        elif order_key.startswith("SINGLE|"):
                            _, tool_name, qty = order_key.split("|")
                            try:
                                qty_i = max(1, min(100, int(qty)))
                            except (TypeError, ValueError):
                                qty_i = 1
                            self.close()
                            return f"tool_order_{tool_name}_{qty_i}"
            return "blocked"
        if event.type == pygame.MOUSEWHEEL and self.viewport_rect:
            if self.viewport_rect.collidepoint(pygame.mouse.get_pos()):
                self.scroll_y = max(0, min(self.scroll_y - event.y * upx(38), self.max_scroll))
                return "scroll"
        return None

    _focused_qty = None

    @staticmethod
    def _format_price(amount):
        coins = from_copper(max(0, int(amount)))
        return f"{coins['Gold']}g  {coins['Silver']}s  {coins['Copper']}c"

    def _qty_for(self, item_name):
        try:
            return max(1, min(100, int(self.quantity_values.get(item_name, "1") or 1)))
        except (TypeError, ValueError):
            return 1

    def draw(self, surface, building_manager=None, villager_manager=None):
        if not self.is_open or not self.workbench:
            return
        self._ensure_fonts()
        screen_w, screen_h = surface.get_size()
        modal_w = min(upx(760), screen_w - upx(32))
        modal_h = min(upx(620), screen_h - upx(32))
        modal_x = (screen_w - modal_w) // 2
        modal_y = (screen_h - modal_h) // 2
        self.modal_rect = pygame.Rect(modal_x, modal_y, modal_w, modal_h)

        shade = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, COLOR_MODAL_BG, self.modal_rect, border_radius=upx(12))
        pygame.draw.rect(surface, COLOR_MODAL_BORDER, self.modal_rect, width=2, border_radius=upx(12))

        title = self.font_title.render("TOOLMAKER WORKBENCH", True, COLOR_TEXT_TITLE)
        surface.blit(title, (modal_x + upx(24), modal_y + upx(18)))
        rack = dict(getattr(self.workbench, "output_inventory", {}) or {})
        for sk, sv in (getattr(self.workbench, "inventory", {}) or {}).items():
            if int(sv or 0) > 0:
                rack[sk] = rack.get(sk, 0) + int(sv)
        rack_str = ", ".join(f"{v}x {k.replace('_', ' ')}" for k, v in rack.items() if v > 0) or "Empty"
        subtitle = self.font_sub.render(f"Output Rack: {rack_str} | Pick up completed tools at this workbench.", True, (134, 239, 172) if rack_str != "Empty" else COLOR_TEXT_MUTED)
        surface.blit(subtitle, (modal_x + upx(26), modal_y + upx(46)))

        self.close_rect = pygame.Rect(modal_x + modal_w - upx(42), modal_y + upx(16), upx(26), upx(26))
        pygame.draw.rect(surface, (30, 41, 59), self.close_rect, border_radius=upx(5))
        close_label = self.font_badge.render("X", True, COLOR_TEXT_MAIN)
        surface.blit(close_label, (self.close_rect.centerx - close_label.get_width() // 2,
                                   self.close_rect.centery - close_label.get_height() // 2))

        # --- Tabs ---
        tab_y = modal_y + upx(72)
        tab_h = upx(32)
        self.tab_rects = {
            "JOB_SETS": pygame.Rect(modal_x + upx(24), tab_y, upx(120), tab_h),
            "SINGLE_TOOLS": pygame.Rect(modal_x + upx(152), tab_y, upx(130), tab_h),
            "OUTPUT_RACK": pygame.Rect(modal_x + upx(290), tab_y, upx(180), tab_h),
        }
        tot_rack = sum(v for v in rack.values() if v > 0)
        for tab_name, tab_rect in self.tab_rects.items():
            is_active = (self.current_tab == tab_name)
            bg_col = (37, 99, 235) if is_active else (30, 41, 59)
            border_col = (147, 197, 253) if is_active else (71, 85, 105)
            pygame.draw.rect(surface, bg_col, tab_rect, border_radius=upx(6))
            pygame.draw.rect(surface, border_col, tab_rect, width=1 if not is_active else 2, border_radius=upx(6))
            if tab_name == "JOB_SETS":
                lbl_txt = "JOB SETS"
            elif tab_name == "SINGLE_TOOLS":
                lbl_txt = "SINGLE TOOLS"
            else:
                lbl_txt = f"WORKBENCH RACK ({tot_rack})"
            lbl = self.font_badge.render(lbl_txt, True, (255, 255, 255) if is_active else COLOR_TEXT_MUTED)
            surface.blit(lbl, (tab_rect.centerx - lbl.get_width() // 2, tab_rect.centery - lbl.get_height() // 2))

        # --- Viewport ---
        viewport_top = modal_y + upx(114)
        viewport_bottom = modal_y + modal_h - upx(16)
        self.viewport_rect = pygame.Rect(modal_x + upx(20), viewport_top, modal_w - upx(40),
                                         max(0, viewport_bottom - viewport_top))

        self.order_rects = {}
        self.qty_rects = {}
        old_clip = surface.get_clip()
        surface.set_clip(self.viewport_rect)

        if self.current_tab == "JOB_SETS":
            row_h = upx(76)
            row_step = row_h + 8
            content_h = len(JOB_TOOL_SETS) * row_step
            self.max_scroll = max(0, content_h - self.viewport_rect.height)
            self.scroll_y = max(0, min(self.scroll_y, self.max_scroll))

            for index, (job_id, set_info) in enumerate(JOB_TOOL_SETS.items()):
                row = pygame.Rect(self.viewport_rect.x,
                                  self.viewport_rect.y + index * row_step - self.scroll_y,
                                  self.viewport_rect.width, row_h)
                pygame.draw.rect(surface, (15, 23, 42), row, border_radius=upx(7))
                pygame.draw.rect(surface, (51, 65, 85), row, width=1, border_radius=upx(7))

                # Title & description
                name = self.font_body.render(set_info["title"], True, (253, 224, 71))
                surface.blit(name, (row.x + upx(14), row.y + upx(8)))

                tools_str = ", ".join(t.replace("_", " ") for t in set_info["tools"])
                tools_lbl = self.font_sub.render(f"Includes: {tools_str}", True, COLOR_TEXT_MAIN)
                surface.blit(tools_lbl, (row.x + upx(14), row.y + upx(30)))

                qty = self._qty_for(f"set_{job_id}")

                # Calculate total materials and price
                tot_wood = sum(int(TOOLMAKER_TOOL_RECIPE.get("Wood", 2)) for _ in set_info["tools"]) * qty
                tot_iron = sum(int(TOOLMAKER_TOOL_RECIPE.get("Iron Bar", 3)) for _ in set_info["tools"]) * qty
                tot_price = sum(
                    ToolmakerSystem.quote_tool_order(t, qty, building_manager, villager_manager)["price_copper"]
                    for t in set_info["tools"]
                )

                mat_label = self.font_sub.render(f"Materials: {tot_wood}x Wood, {tot_iron}x Iron Bar", True, COLOR_TEXT_MUTED)
                surface.blit(mat_label, (row.x + upx(14), row.y + upx(48)))

                price_str = self._format_price(tot_price)
                price_label = self.font_badge.render(f"{price_str} total", True, (250, 204, 21))
                surface.blit(price_label, (row.x + upx(260), row.y + upx(48)))

                # Qty input
                q_key = f"set_{job_id}"
                qty_rect = pygame.Rect(row.right - upx(270), row.y + upx(20), upx(46), upx(26))
                self.qty_rects[q_key] = qty_rect
                focused = (self._focused_qty == q_key)
                pygame.draw.rect(surface, (15, 23, 42) if not focused else (30, 58, 138), qty_rect, border_radius=4)
                pygame.draw.rect(surface, (250, 204, 21) if focused else (71, 85, 105), qty_rect, width=2 if focused else 1, border_radius=upx(4))
                q_txt = self.font_badge.render(self.quantity_values.get(q_key, "1"), True, (255, 255, 255))
                surface.blit(q_txt, (qty_rect.centerx - q_txt.get_width() // 2, qty_rect.centery - q_txt.get_height() // 2))
                q_lbl = self.font_badge.render("SET QTY", True, COLOR_TEXT_MUTED)
                surface.blit(q_lbl, (qty_rect.centerx - q_lbl.get_width() // 2, qty_rect.bottom + 2))

                # Order button
                order_rect = pygame.Rect(row.right - upx(190), row.y + upx(22), upx(120), upx(32))
                self.order_rects[f"SET|{job_id}|{qty}"] = order_rect
                hovered = order_rect.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (16, 185, 129) if hovered else (5, 150, 105), order_rect, border_radius=upx(5))
                pygame.draw.rect(surface, (52, 211, 153), order_rect, width=1, border_radius=upx(5))
                order_label = self.font_badge.render("Order Set", True, (255, 255, 255))
                surface.blit(order_label, (order_rect.centerx - order_label.get_width() // 2,
                                           order_rect.centery - order_label.get_height() // 2))

        elif self.current_tab == "SINGLE_TOOLS":
            # SINGLE_TOOLS tab
            tools = ToolmakerSystem.craftable_tools()
            row_h = upx(64)
            row_step = row_h + 8
            content_h = len(tools) * row_step
            self.max_scroll = max(0, content_h - self.viewport_rect.height)
            self.scroll_y = max(0, min(self.scroll_y, self.max_scroll))

            for index, tool_name in enumerate(tools):
                row = pygame.Rect(self.viewport_rect.x,
                                  self.viewport_rect.y + index * row_step - self.scroll_y,
                                  self.viewport_rect.width, row_h)
                pygame.draw.rect(surface, (15, 23, 42), row, border_radius=upx(7))
                pygame.draw.rect(surface, (51, 65, 85), row, width=1, border_radius=upx(7))
                name = self.font_body.render(tool_name.replace("_", " "), True, COLOR_TEXT_MAIN)
                surface.blit(name, (row.x + upx(14), row.y + upx(10)))
                mats = ", ".join(f"{a}x {i}" for i, a in TOOLMAKER_TOOL_RECIPE.items())
                mat_label = self.font_sub.render(f"Materials/tool: {mats}", True, COLOR_TEXT_MUTED)
                surface.blit(mat_label, (row.x + upx(14), row.y + upx(32)))

                qty = self._qty_for(tool_name)
                quote = ToolmakerSystem.quote_tool_order(tool_name, qty, building_manager, villager_manager)
                price = self._format_price(quote["price_copper"])
                price_label = self.font_badge.render(f"{price} total", True, (250, 204, 21))
                surface.blit(price_label, (row.x + upx(14), row.y + upx(48)))

                # Qty input
                q_key = tool_name
                qty_rect = pygame.Rect(row.right - upx(270), row.y + upx(14), upx(46), upx(26))
                self.qty_rects[tool_name] = qty_rect
                focused = (self._focused_qty == tool_name)
                pygame.draw.rect(surface, (15, 23, 42) if not focused else (30, 58, 138), qty_rect, border_radius=4)
                pygame.draw.rect(surface, (250, 204, 21) if focused else (71, 85, 105), qty_rect, width=2 if focused else 1, border_radius=upx(4))
                q_txt = self.font_badge.render(self.quantity_values.get(tool_name, "1"), True, (255, 255, 255))
                surface.blit(q_txt, (qty_rect.centerx - q_txt.get_width() // 2, qty_rect.centery - q_txt.get_height() // 2))
                q_lbl = self.font_badge.render("QTY", True, COLOR_TEXT_MUTED)
                surface.blit(q_lbl, (qty_rect.centerx - q_lbl.get_width() // 2, qty_rect.bottom + 2))

                order_rect = pygame.Rect(row.right - upx(190), row.y + upx(22), upx(120), upx(30))
                self.order_rects[f"SINGLE|{tool_name}|{qty}"] = order_rect
                hovered = order_rect.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (16, 185, 129) if hovered else (5, 150, 105), order_rect, border_radius=upx(5))
                pygame.draw.rect(surface, (52, 211, 153), order_rect, width=1, border_radius=upx(5))
                order_label = self.font_badge.render("Forge Tool", True, (255, 255, 255))
                surface.blit(order_label, (order_rect.centerx - order_label.get_width() // 2,
                                           order_rect.centery - order_label.get_height() // 2))

        elif self.current_tab == "OUTPUT_RACK":
            self.rack_action_rects = {}
            rack_items = [(k, v) for k, v in rack.items() if v > 0]
            orders = [s for s in getattr(self.workbench, "tool_order_subjects", [])
                      if getattr(s, "construction_order", None)
                      and s.construction_order.get("status") not in (None, "COMPLETE")]

            content_h = upx(30) + (len(rack_items) * upx(60) if rack_items else upx(40)) + upx(36) + (len(orders) * upx(60) if orders else upx(40)) + upx(20)
            self.max_scroll = max(0, content_h - self.viewport_rect.height)
            self.scroll_y = max(0, min(self.scroll_y, self.max_scroll))

            cur_y = self.viewport_rect.y - self.scroll_y

            # Section 1: Output Rack
            lbl_rack = self.font_badge.render("FINISHED TOOLS ON WORKBENCH OUTPUT RACK (READY FOR PICKUP)", True, (253, 224, 71))
            surface.blit(lbl_rack, (self.viewport_rect.x + upx(4), cur_y))
            cur_y += upx(24)

            if not rack_items:
                empty_row = pygame.Rect(self.viewport_rect.x, cur_y, self.viewport_rect.width, upx(38))
                pygame.draw.rect(surface, (15, 23, 42), empty_row, border_radius=upx(6))
                pygame.draw.rect(surface, (51, 65, 85), empty_row, width=1, border_radius=upx(6))
                txt = self.font_sub.render("Output rack is empty. Completed tools will appear here when forged.", True, COLOR_TEXT_MUTED)
                surface.blit(txt, (empty_row.x + upx(14), empty_row.y + upx(10)))
                cur_y += upx(46)
            else:
                for tool_name, qty in rack_items:
                    row = pygame.Rect(self.viewport_rect.x, cur_y, self.viewport_rect.width, upx(52))
                    pygame.draw.rect(surface, (15, 23, 42), row, border_radius=upx(7))
                    pygame.draw.rect(surface, (52, 211, 153), row, width=1, border_radius=upx(7))

                    t_name = self.font_body.render(f"{qty}x {tool_name.replace('_', ' ')}", True, (255, 255, 255))
                    surface.blit(t_name, (row.x + upx(14), row.y + upx(8)))
                    t_desc = self.font_sub.render("Available on workbench rack — villagers pick up here, or take/haul manually.", True, (134, 239, 172))
                    surface.blit(t_desc, (row.x + upx(14), row.y + upx(28)))

                    # Take 1 button
                    btn_take = pygame.Rect(row.right - upx(260), row.y + upx(10), upx(100), upx(32))
                    self.rack_action_rects[f"TAKE|{tool_name}"] = btn_take
                    t_hov = btn_take.collidepoint(pygame.mouse.get_pos())
                    pygame.draw.rect(surface, (37, 99, 235) if not t_hov else (59, 130, 246), btn_take, border_radius=upx(5))
                    pygame.draw.rect(surface, (147, 197, 253), btn_take, width=1, border_radius=upx(5))
                    take_lbl = self.font_badge.render("Take 1", True, (255, 255, 255))
                    surface.blit(take_lbl, (btn_take.centerx - take_lbl.get_width() // 2, btn_take.centery - take_lbl.get_height() // 2))

                    # Haul to Stockpile button
                    btn_haul = pygame.Rect(row.right - upx(150), row.y + upx(10), upx(140), upx(32))
                    self.rack_action_rects[f"HAUL|{tool_name}"] = btn_haul
                    h_hov = btn_haul.collidepoint(pygame.mouse.get_pos())
                    pygame.draw.rect(surface, (202, 138, 4) if not h_hov else (234, 179, 8), btn_haul, border_radius=upx(5))
                    pygame.draw.rect(surface, (253, 224, 71), btn_haul, width=1, border_radius=upx(5))
                    haul_lbl = self.font_badge.render("Haul to Yard", True, (15, 23, 42))
                    surface.blit(haul_lbl, (btn_haul.centerx - haul_lbl.get_width() // 2, btn_haul.centery - haul_lbl.get_height() // 2))

                    cur_y += upx(60)

            cur_y += upx(10)
            # Section 2: Active Commissions
            lbl_orders = self.font_badge.render("COMMISSIONS ON THIS WORKBENCH", True, (253, 224, 71))
            surface.blit(lbl_orders, (self.viewport_rect.x + upx(4), cur_y))
            cur_y += upx(24)

            if not orders:
                empty_row = pygame.Rect(self.viewport_rect.x, cur_y, self.viewport_rect.width, upx(38))
                pygame.draw.rect(surface, (15, 23, 42), empty_row, border_radius=upx(6))
                pygame.draw.rect(surface, (51, 65, 85), empty_row, width=1, border_radius=upx(6))
                txt = self.font_sub.render("No commissions currently queued on this workbench.", True, COLOR_TEXT_MUTED)
                surface.blit(txt, (empty_row.x + upx(14), empty_row.y + upx(10)))
            else:
                for sub in orders:
                    o = sub.construction_order
                    o_row = pygame.Rect(self.viewport_rect.x, cur_y, self.viewport_rect.width, upx(52))
                    pygame.draw.rect(surface, (15, 23, 42), o_row, border_radius=upx(7))
                    pygame.draw.rect(surface, (51, 65, 85), o_row, width=1, border_radius=upx(7))

                    t_name = o.get("tool_name", "Tool").replace("_", " ")
                    q_done = int(o.get("qty_done", 0))
                    q_tot = int(o.get("qty_total", 1))
                    t_txt = self.font_body.render(f"{t_name} (Qty: {q_done}/{q_tot})", True, (255, 255, 255))
                    surface.blit(t_txt, (o_row.x + upx(14), o_row.y + upx(8)))

                    p_type = o.get("payer_type")
                    p_fam = o.get("payer_family_id")
                    fam_name = "Landlord"
                    if p_type != "landlord" and p_fam and villager_manager:
                        fam = villager_manager.get_family_by_id(str(p_fam))
                        if fam:
                            fam_name = f"The {fam.surname} Family"
                        else:
                            fam_name = f"Household {p_fam}"

                    p_txt = self.font_sub.render(f"Payer: {fam_name}", True, COLOR_TEXT_MUTED)
                    surface.blit(p_txt, (o_row.x + upx(14), o_row.y + upx(28)))

                    # Status badge
                    st = o.get("status", "UNKNOWN")
                    if st == "READY_FOR_PICKUP":
                        st_txt = "Ready for Pickup"
                        st_col = (34, 197, 94)
                    elif st == "CRAFTING":
                        prog = int(float(o.get("craft_progress", 0.0)) * 100)
                        st_txt = f"Forging ({prog}%)"
                        st_col = (56, 189, 248)
                    elif st == "PAID":
                        st_txt = "Paid — In Queue"
                        st_col = (147, 197, 253)
                    elif st == "AWAITING_PAYMENT":
                        st_txt = "Awaiting Household Payment"
                        st_col = (250, 204, 21)
                    elif st == "LANDLORD_PAYMENT_PENDING":
                        st_txt = "Awaiting Treasury Courier"
                        st_col = (251, 146, 60)
                    elif st == "COMPLETE":
                        st_txt = "Completed"
                        st_col = (148, 163, 184)
                    else:
                        st_txt = st
                        st_col = (203, 213, 225)

                    badge = self.font_badge.render(st_txt, True, st_col)
                    surface.blit(badge, (o_row.right - badge.get_width() - upx(16), o_row.y + upx(16)))
                    cur_y += upx(60)

        surface.set_clip(old_clip)
        if self.status_message:
            status = self.font_badge.render(self.status_message, True, (134, 239, 172))
            surface.blit(status, (modal_x + upx(24), modal_y + modal_h - upx(14)))
