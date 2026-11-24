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
        self.current_tab = "JOB_SETS"  # "JOB_SETS" or "SINGLE_TOOLS"
        self.tab_rects = {}
        self.order_rects = {}
        self.qty_rects = {}
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
        self.is_open = True
        self.scroll_y = 0
        self.status_message = None
        self.current_tab = "JOB_SETS"
        self._focused_qty = None

    def close(self):
        self.is_open = False
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
        subtitle = self.font_sub.render("Commission forge work: Pick up completed tools at the workbench output rack.", True, COLOR_TEXT_MUTED)
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
            "JOB_SETS": pygame.Rect(modal_x + upx(24), tab_y, upx(130), tab_h),
            "SINGLE_TOOLS": pygame.Rect(modal_x + upx(162), tab_y, upx(140), tab_h),
        }
        for tab_name, tab_rect in self.tab_rects.items():
            is_active = (self.current_tab == tab_name)
            bg_col = (37, 99, 235) if is_active else (30, 41, 59)
            border_col = (147, 197, 253) if is_active else (71, 85, 105)
            pygame.draw.rect(surface, bg_col, tab_rect, border_radius=upx(6))
            pygame.draw.rect(surface, border_col, tab_rect, width=1 if not is_active else 2, border_radius=upx(6))
            lbl_txt = "JOB SETS" if tab_name == "JOB_SETS" else "SINGLE TOOLS"
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

        else:
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

        surface.set_clip(old_clip)
        if self.status_message:
            status = self.font_badge.render(self.status_message, True, (134, 239, 172))
            surface.blit(status, (modal_x + upx(24), modal_y + modal_h - upx(14)))
