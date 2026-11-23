"""Furniture catalogue and live commission quotes for Carpenter workbenches."""

import pygame

from game.data.config import BUILDING_TYPES, FURNITURE_TYPES, COLOR_MODAL_BG, COLOR_MODAL_BORDER, COLOR_TEXT_TITLE, COLOR_TEXT_MAIN, COLOR_TEXT_MUTED
from game.systems.work.carpenter_system import CarpenterSystem
from game.systems.economy.currency import from_copper
from game.config import TILE_SIZE


class CarpenterCatalogModal:
    def __init__(self):
        self.is_open = False
        self.workbench = None
        self.modal_rect = None
        self.close_rect = None
        self.viewport_rect = None
        self.order_rects = {}
        self.scroll_y = 0
        self.max_scroll = 0
        self.font_title = None
        self.font_sub = None
        self.font_body = None
        self.font_badge = None
        self.font_btn = None

    def open(self, workbench):
        self.workbench = workbench
        self.is_open = True
        self.scroll_y = 0

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
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
            return "close"
        if event.type == pygame.MOUSEWHEEL and self.viewport_rect:
            if self.viewport_rect.collidepoint(pygame.mouse.get_pos()):
                self.scroll_y = max(0, min(self.scroll_y - event.y * 38, self.max_scroll))
                return "scroll"
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.close_rect and self.close_rect.collidepoint(event.pos):
                self.close()
                return "close"
            if self.viewport_rect and self.viewport_rect.collidepoint(event.pos):
                for order_key, rect in self.order_rects.items():
                    if rect.collidepoint(event.pos):
                        self.close()
                        kind, item_type = order_key.split(":", 1)
                        return f"commission_{kind}_{item_type}"
            return "blocked"
        return None

    @staticmethod
    def _format_price(amount):
        coins = from_copper(max(0, int(amount)))
        return f"{coins['Gold']}g  {coins['Silver']}s  {coins['Copper']}c"

    def draw(self, surface, building_manager=None, villager_manager=None):
        if not self.is_open or not self.workbench:
            return
        self._ensure_fonts()
        screen_w, screen_h = surface.get_size()
        modal_w = min(780, screen_w - 32)
        modal_h = min(620, screen_h - 32)
        modal_x = (screen_w - modal_w) // 2
        modal_y = (screen_h - modal_h) // 2
        self.modal_rect = pygame.Rect(modal_x, modal_y, modal_w, modal_h)

        shade = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, COLOR_MODAL_BG, self.modal_rect, border_radius=12)
        pygame.draw.rect(surface, COLOR_MODAL_BORDER, self.modal_rect, width=2, border_radius=12)

        title = self.font_title.render("CARPENTER WORKBENCH", True, COLOR_TEXT_TITLE)
        surface.blit(title, (modal_x + 24, modal_y + 18))
        subtitle = self.font_sub.render("Furniture and public build quotes use market material costs and living wages.", True, COLOR_TEXT_MUTED)
        surface.blit(subtitle, (modal_x + 26, modal_y + 48))

        self.close_rect = pygame.Rect(modal_x + modal_w - 42, modal_y + 16, 26, 26)
        pygame.draw.rect(surface, (30, 41, 59), self.close_rect, border_radius=5)
        close_label = self.font_badge.render("X", True, COLOR_TEXT_MAIN)
        surface.blit(close_label, (self.close_rect.centerx - close_label.get_width() // 2,
                                   self.close_rect.centery - close_label.get_height() // 2))

        footer_h = 42
        viewport_top = modal_y + 82
        viewport_bottom = modal_y + modal_h - footer_h - 12
        self.viewport_rect = pygame.Rect(modal_x + 20, viewport_top, modal_w - 40,
                                         max(0, viewport_bottom - viewport_top))
        item_types = [(key, cfg, "furniture") for key, cfg in FURNITURE_TYPES.items()]
        item_types.extend((key, cfg, "building") for key, cfg in BUILDING_TYPES.items()
                          if cfg.get("carpenter_commissionable"))
        row_h = 90
        row_step = row_h + 8
        content_h = len(item_types) * row_step
        self.max_scroll = max(0, content_h - self.viewport_rect.height)
        self.scroll_y = max(0, min(self.scroll_y, self.max_scroll))
        self.order_rects = {}
        old_clip = surface.get_clip()
        surface.set_clip(self.viewport_rect)

        reference_position = self.workbench.get_world_pos(TILE_SIZE)
        for index, (item_type, cfg, item_kind) in enumerate(item_types):
            order_key = f"{item_kind}:{item_type}"
            row = pygame.Rect(self.viewport_rect.x,
                              self.viewport_rect.y + index * row_step - self.scroll_y,
                              self.viewport_rect.width, row_h)
            pygame.draw.rect(surface, (15, 23, 42), row, border_radius=7)
            pygame.draw.rect(surface, (51, 65, 85), row, width=1, border_radius=7)
            name = self.font_body.render(cfg.get("name", item_type.replace("_", " ").title()), True, COLOR_TEXT_MAIN)
            surface.blit(name, (row.x + 14, row.y + 10))
            desc = self.font_sub.render(cfg.get("desc", ""), True, COLOR_TEXT_MUTED)
            surface.blit(desc, (row.x + 14, row.y + 31))
            materials = cfg.get("materials", {})
            if item_kind == "building":
                quote = CarpenterSystem.quote_building_order(item_type, building_manager, villager_manager)
                materials = quote.get("materials", {})
            material_text = ", ".join(f"{amount}x {item}" for item, amount in materials.items() if amount)
            if not material_text:
                material_text = "No material cost"
            material_label = self.font_sub.render(f"Materials: {material_text}", True, COLOR_TEXT_MUTED)
            surface.blit(material_label, (row.x + 14, row.y + 56))

            if item_kind == "furniture":
                quote = CarpenterSystem.quote_order(
                    item_type, building_manager, villager_manager,
                    reference_position=reference_position,
                )
            price = self._format_price(quote["price_copper"])
            price_label = self.font_badge.render(f"{price}  (material + living wage)", True, (250, 204, 21))
            surface.blit(price_label, (row.right - 218, row.y + 14))
            order_rect = pygame.Rect(row.right - 128, row.y + 49, 112, 28)
            self.order_rects[order_key] = order_rect
            hovered = order_rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (16, 185, 129) if hovered else (5, 150, 105), order_rect, border_radius=5)
            pygame.draw.rect(surface, (52, 211, 153), order_rect, width=1, border_radius=5)
            order_label = self.font_badge.render("Commission" if item_kind == "furniture" else "Plan", True, (255, 255, 255))
            surface.blit(order_label, (order_rect.centerx - order_label.get_width() // 2,
                                       order_rect.centery - order_label.get_height() // 2))

        surface.set_clip(old_clip)
        if self.max_scroll:
            track = pygame.Rect(self.viewport_rect.right - 4, self.viewport_rect.y, 3, self.viewport_rect.height)
            pygame.draw.rect(surface, (51, 65, 85), track, border_radius=2)
            thumb_h = max(24, int(track.height * self.viewport_rect.height / content_h))
            thumb_y = track.y + int((track.height - thumb_h) * self.scroll_y / self.max_scroll)
            pygame.draw.rect(surface, (96, 165, 250), (track.x, thumb_y, track.width, thumb_h), border_radius=2)
