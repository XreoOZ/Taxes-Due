"""Toolmaker Workbench catalogue: forge tool commissions with qty per order."""

import pygame

from game.data.config import COLOR_MODAL_BG, COLOR_MODAL_BORDER, COLOR_TEXT_TITLE, COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, TOOLMAKER_TOOL_RECIPE
from game.systems.work.toolmaker_system import ToolmakerSystem
from game.systems.work.builder_system import BuilderSystem
from game.systems.economy.currency import from_copper


class ToolmakerCatalogModal:
    def __init__(self):
        self.is_open = False
        self.workbench = None
        self.modal_rect = None
        self.close_rect = None
        self.viewport_rect = None
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

    def close(self):
        self.is_open = False
        self.workbench = None

    def _ensure_fonts(self):
        if self.font_title is None:
            self.font_title = pygame.font.SysFont("Segoe UI", 19, bold=True)
            self.font_sub = pygame.font.SysFont("Segoe UI", 12)
            self.font_body = pygame.font.SysFont("Segoe UI", 13)
            self.font_badge = pygame.font.SysFont("Segoe UI", 11, bold=True)
            self.font_btn = pygame.font.SysFont("Segoe UI", 12, bold=True)

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
            for item_name, rect in self.qty_rects.items():
                if rect.collidepoint(event.pos):
                    self._focused_qty = item_name
                    self.quantity_values.setdefault(item_name, "1")
                    return None
            if self.viewport_rect and self.viewport_rect.collidepoint(event.pos):
                for order_key, rect in self.order_rects.items():
                    if rect.collidepoint(event.pos):
                        tool_name, qty = order_key.rsplit("|", 1)
                        try:
                            qty_i = max(1, min(100, int(qty)))
                        except (TypeError, ValueError):
                            qty_i = 1
                        self.close()
                        return f"tool_order_{tool_name}_{qty_i}"
            return "blocked"
        if event.type == pygame.MOUSEWHEEL and self.viewport_rect:
            if self.viewport_rect.collidepoint(pygame.mouse.get_pos()):
                self.scroll_y = max(0, min(self.scroll_y - event.y * 38, self.max_scroll))
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
        modal_w = min(720, screen_w - 32)
        modal_h = min(600, screen_h - 32)
        modal_x = (screen_w - modal_w) // 2
        modal_y = (screen_h - modal_h) // 2
        self.modal_rect = pygame.Rect(modal_x, modal_y, modal_w, modal_h)

        shade = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, COLOR_MODAL_BG, self.modal_rect, border_radius=12)
        pygame.draw.rect(surface, COLOR_MODAL_BORDER, self.modal_rect, width=2, border_radius=12)

        title = self.font_title.render("TOOLMAKER WORKBENCH", True, COLOR_TEXT_TITLE)
        surface.blit(title, (modal_x + 24, modal_y + 18))
        subtitle = self.font_sub.render("Forge tools to order: 2 Wood + 3 Iron Bar each, 1-2 hours per tool.", True, COLOR_TEXT_MUTED)
        surface.blit(subtitle, (modal_x + 26, modal_y + 46))

        self.close_rect = pygame.Rect(modal_x + modal_w - 42, modal_y + 16, 26, 26)
        pygame.draw.rect(surface, (30, 41, 59), self.close_rect, border_radius=5)
        close_label = self.font_badge.render("X", True, COLOR_TEXT_MAIN)
        surface.blit(close_label, (self.close_rect.centerx - close_label.get_width() // 2,
                                   self.close_rect.centery - close_label.get_height() // 2))

        viewport_top = modal_y + 76
        viewport_bottom = modal_y + modal_h - 16
        self.viewport_rect = pygame.Rect(modal_x + 20, viewport_top, modal_w - 40,
                                         max(0, viewport_bottom - viewport_top))
        tools = ToolmakerSystem.craftable_tools()
        row_h = 64
        row_step = row_h + 8
        content_h = len(tools) * row_step
        self.max_scroll = max(0, content_h - self.viewport_rect.height)
        self.scroll_y = max(0, min(self.scroll_y, self.max_scroll))
        self.order_rects = {}
        self.qty_rects = {}
        old_clip = surface.get_clip()
        surface.set_clip(self.viewport_rect)

        for index, tool_name in enumerate(tools):
            row = pygame.Rect(self.viewport_rect.x,
                              self.viewport_rect.y + index * row_step - self.scroll_y,
                              self.viewport_rect.width, row_h)
            pygame.draw.rect(surface, (15, 23, 42), row, border_radius=7)
            pygame.draw.rect(surface, (51, 65, 85), row, width=1, border_radius=7)
            name = self.font_body.render(tool_name.replace("_", " "), True, COLOR_TEXT_MAIN)
            surface.blit(name, (row.x + 14, row.y + 10))
            mats = ", ".join(f"{a}x {i}" for i, a in TOOLMAKER_TOOL_RECIPE.items())
            mat_label = self.font_sub.render(f"Materials/tool: {mats}", True, COLOR_TEXT_MUTED)
            surface.blit(mat_label, (row.x + 14, row.y + 32))

            qty = self._qty_for(tool_name)
            quote = ToolmakerSystem.quote_tool_order(tool_name, qty, building_manager, villager_manager)
            price = self._format_price(quote["price_copper"])
            price_label = self.font_badge.render(f"{price} total", True, (250, 204, 21))
            surface.blit(price_label, (row.x + 14, row.y + 48))

            # Qty input
            q_key = tool_name
            qty_rect = pygame.Rect(row.right - 260, row.y + 14, 46, 26)
            self.qty_rects[tool_name] = qty_rect
            focused = (self._focused_qty == tool_name)
            pygame.draw.rect(surface, (15, 23, 42) if not focused else (30, 58, 138), qty_rect, border_radius=4)
            pygame.draw.rect(surface, (250, 204, 21) if focused else (71, 85, 105), qty_rect, width=2 if focused else 1, border_radius=4)
            q_txt = self.font_badge.render(self.quantity_values.get(tool_name, "1"), True, (255, 255, 255))
            surface.blit(q_txt, (qty_rect.centerx - q_txt.get_width() // 2, qty_rect.centery - q_txt.get_height() // 2))
            q_lbl = self.font_badge.render("QTY", True, COLOR_TEXT_MUTED)
            surface.blit(q_lbl, (qty_rect.centerx - q_lbl.get_width() // 2, qty_rect.bottom + 2))

            order_rect = pygame.Rect(row.right - 190, row.y + 22, 110, 30)
            self.order_rects[f"{tool_name}|{qty}"] = order_rect
            hovered = order_rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (16, 185, 129) if hovered else (5, 150, 105), order_rect, border_radius=5)
            pygame.draw.rect(surface, (52, 211, 153), order_rect, width=1, border_radius=5)
            order_label = self.font_badge.render("Forge", True, (255, 255, 255))
            surface.blit(order_label, (order_rect.centerx - order_label.get_width() // 2,
                                       order_rect.centery - order_label.get_height() // 2))

        surface.set_clip(old_clip)
        if self.status_message:
            status = self.font_badge.render(self.status_message, True, (134, 239, 172))
            surface.blit(status, (modal_x + 24, modal_y + modal_h - 14))
