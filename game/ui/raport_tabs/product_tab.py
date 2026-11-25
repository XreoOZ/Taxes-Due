"""RaportUI tab view — Artisan Product Stock Quotas."""

import pygame
from game.config import (
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_TITLE,
    PRODUCTION_QUOTA_MAX,
    PRODUCTION_QUOTA_STEP,
)
from game.systems.work.production_system import ProductionSystem
from game.ui.ui_theme import upx


class ProductMixin:
    def _draw_product_tab(self, surface, mx, cy, building_manager,
                          furniture_manager=None, stockpile_manager=None):
        """Render the Product tab for configuring artisan stock production quotas."""
        m_pos = pygame.mouse.get_pos()

        self.product_filter_rects = {}
        self.product_quota_dec_rects = {}
        self.product_quota_inc_rects = {}

        title_surf = self.font_sub.render("Artisan Production Quotas", True, COLOR_TEXT_TITLE)
        surface.blit(title_surf, (mx + upx(24), cy))

        sub_surf = self.font_body.render(
            "Set target ready stock for artisans to craft when not busy with commissions.",
            True, COLOR_TEXT_MUTED,
        )
        surface.blit(sub_surf, (mx + upx(24), cy + upx(22)))

        # Filter pills on top-right
        filters = [("all", "All"), ("Toolmaker", "Toolmaker"), ("Builder", "Builder")]
        fx = mx + self.modal_w - upx(24)
        fy = cy - upx(2)
        for fkey, flabel in reversed(filters):
            lbl_s = self.font_badge.render(flabel, True, (241, 245, 249))
            fw = max(upx(64), lbl_s.get_width() + upx(18))
            fx -= fw
            frect = pygame.Rect(fx, fy, fw, upx(24))
            self.product_filter_rects[fkey] = frect
            active = (self.product_filter == fkey)
            hov = frect.collidepoint(m_pos)
            bg = (37, 99, 235) if active else ((45, 58, 82) if hov else (30, 41, 59))
            border = (96, 165, 250) if active else (71, 85, 105)
            pygame.draw.rect(surface, bg, frect, border_radius=upx(5))
            pygame.draw.rect(surface, border, frect, width=1, border_radius=upx(5))
            surface.blit(lbl_s, (frect.centerx - lbl_s.get_width() // 2,
                                 frect.centery - lbl_s.get_height() // 2))
            fx -= upx(6)

        catalog = ProductionSystem.get_catalog()
        if self.product_filter in ("Toolmaker", "Builder"):
            catalog = [c for c in catalog if c["artisan"] == self.product_filter]

        modal_bottom = (surface.get_height() + self.modal_h) // 2 - upx(18)
        viewport_top = cy + upx(48)
        viewport_h = max(upx(80), modal_bottom - viewport_top)
        self.product_viewport_rect = pygame.Rect(mx + upx(20), viewport_top, self.modal_w - upx(40), viewport_h)

        row_h = upx(36)
        row_gap = upx(6)
        content_h = len(catalog) * (row_h + row_gap)
        self.product_max_scroll = max(0, content_h - viewport_h)
        self.product_scroll_y = max(0, min(self.product_scroll_y, self.product_max_scroll))

        old_clip = surface.get_clip()
        surface.set_clip(self.product_viewport_rect)

        y_cur = viewport_top - self.product_scroll_y
        for entry in catalog:
            item_id = entry["id"]
            row_rect = pygame.Rect(mx + upx(24), y_cur, self.modal_w - upx(48), row_h)
            if row_rect.bottom >= viewport_top and row_rect.top <= modal_bottom:
                stock = ProductionSystem.get_current_stock(
                    item_id,
                    furniture_manager=furniture_manager,
                    building_manager=building_manager,
                    stockpile_manager=stockpile_manager,
                )
                quota = ProductionSystem.get_quota(building_manager, item_id)

                pygame.draw.rect(surface, (15, 23, 42, 210), row_rect, border_radius=upx(6))
                border_col = (34, 197, 94) if (quota > 0 and stock >= quota) else (
                    (245, 158, 11) if quota > 0 else (51, 65, 85)
                )
                pygame.draw.rect(surface, border_col, row_rect, width=1, border_radius=upx(6))

                # Item name + category
                name_surf = self.font_body.render(entry["name"], True, COLOR_TEXT_MAIN)
                surface.blit(name_surf, (row_rect.x + upx(12), row_rect.centery - name_surf.get_height() // 2))

                badge_txt = f"{entry['artisan']} • {entry['category']}"
                badge_surf = self.font_badge.render(badge_txt, True, COLOR_TEXT_MUTED)
                surface.blit(badge_surf, (row_rect.x + upx(190), row_rect.centery - badge_surf.get_height() // 2))

                # Recipe summary
                recipe_parts = [f"{qty} {mat}" for mat, qty in entry.get("recipe", {}).items()]
                recipe_str = ", ".join(recipe_parts) if recipe_parts else "Free"
                rec_surf = self.font_badge.render(recipe_str, True, (148, 163, 184))
                surface.blit(rec_surf, (row_rect.x + upx(365), row_rect.centery - rec_surf.get_height() // 2))

                # Stock indicator
                stock_col = (74, 222, 128) if (quota > 0 and stock >= quota) else (
                    (251, 191, 36) if quota > 0 else (148, 163, 184)
                )
                stock_surf = self.font_body.render(f"Stock: {stock}", True, stock_col)
                surface.blit(stock_surf, (row_rect.right - upx(210), row_rect.centery - stock_surf.get_height() // 2))

                # Stepper controls [ - ] quota [ + ]
                btn_size = upx(24)
                inc_rect = pygame.Rect(row_rect.right - upx(12) - btn_size, row_rect.centery - btn_size // 2, btn_size, btn_size)
                val_w = upx(44)
                val_rect = pygame.Rect(inc_rect.x - upx(4) - val_w, row_rect.centery - btn_size // 2, val_w, btn_size)
                dec_rect = pygame.Rect(val_rect.x - upx(4) - btn_size, row_rect.centery - btn_size // 2, btn_size, btn_size)

                self.product_dec_hit = dec_rect
                self.product_quota_dec_rects[item_id] = dec_rect
                self.product_quota_inc_rects[item_id] = inc_rect

                can_dec = quota > 0
                can_inc = quota < PRODUCTION_QUOTA_MAX

                dec_bg = (51, 65, 85) if can_dec else (30, 41, 59)
                if can_dec and dec_rect.collidepoint(m_pos):
                    dec_bg = (71, 85, 105)
                pygame.draw.rect(surface, dec_bg, dec_rect, border_radius=upx(4))
                dec_lbl = self.font_body.render("-", True, (255, 255, 255) if can_dec else (100, 116, 139))
                surface.blit(dec_lbl, (dec_rect.centerx - dec_lbl.get_width() // 2, dec_rect.centery - dec_lbl.get_height() // 2))

                pygame.draw.rect(surface, (30, 41, 59), val_rect, border_radius=upx(4))
                pygame.draw.rect(surface, (71, 85, 105), val_rect, width=1, border_radius=upx(4))
                q_lbl = self.font_body.render(str(quota), True, (255, 255, 255) if quota > 0 else (148, 163, 184))
                surface.blit(q_lbl, (val_rect.centerx - q_lbl.get_width() // 2, val_rect.centery - q_lbl.get_height() // 2))

                inc_bg = (37, 99, 235) if can_inc else (30, 41, 59)
                if can_inc and inc_rect.collidepoint(m_pos):
                    inc_bg = (59, 130, 246)
                pygame.draw.rect(surface, inc_bg, inc_rect, border_radius=upx(4))
                inc_lbl = self.font_body.render("+", True, (255, 255, 255) if can_inc else (100, 116, 139))
                surface.blit(inc_lbl, (inc_rect.centerx - inc_lbl.get_width() // 2, inc_rect.centery - inc_lbl.get_height() // 2))

            y_cur += row_h + row_gap

        surface.set_clip(old_clip)

    def _handle_product_click(self, pos, building_manager):
        for fkey, frect in list(getattr(self, "product_filter_rects", {}).items()):
            if frect.collidepoint(pos):
                self.product_filter = fkey
                self.product_scroll_y = 0
                return f"product_filter_{fkey}"

        for item_id, rect in list(getattr(self, "product_quota_dec_rects", {}).items()):
            if rect.collidepoint(pos):
                ProductionSystem.adjust_quota(building_manager, item_id, -PRODUCTION_QUOTA_STEP)
                return f"product_dec_{item_id}"

        for item_id, rect in list(getattr(self, "product_quota_inc_rects", {}).items()):
            if rect.collidepoint(pos):
                ProductionSystem.adjust_quota(building_manager, item_id, PRODUCTION_QUOTA_STEP)
                return f"product_inc_{item_id}"

        return None
