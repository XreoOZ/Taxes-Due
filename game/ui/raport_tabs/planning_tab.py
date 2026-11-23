"""RaportUI tab view — extracted from ui_raport.py (mixin)."""

import pygame
from game.config import COLOR_BADGE_PARTIAL, COLOR_TEXT_MUTED, COLOR_TEXT_TITLE
from game.data.planning import PLANNING_FEATURES, STATUS_IMPLEMENTED, STATUS_PARTIAL, STATUS_PLANNED, get_features_by_status


class PlanningMixin:
    def _draw_planning_tab(self, surface, mx, cy):
        """In-game WIP Planning Overview and Roadmap"""
        mouse_pos = pygame.mouse.get_pos()

        # Title & Subtitle
        title = self.font_title.render("PROJECT PLANNING & WIP ROADMAP", True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + 24, cy - 4))

        sub = self.font_body.render("Public roadmap of implemented, partial, and planned WIP features. Informational overview.", True, COLOR_TEXT_MUTED)
        surface.blit(sub, (mx + 24, cy + 22))

        # Filter Chips
        filter_chips = [
            ("ALL", "All Features", len(PLANNING_FEATURES)),
            (STATUS_PLANNED, "Planned WIP", len(get_features_by_status(STATUS_PLANNED))),
            (STATUS_PARTIAL, "Partial WIP", len(get_features_by_status(STATUS_PARTIAL))),
            (STATUS_IMPLEMENTED, "Implemented", len(get_features_by_status(STATUS_IMPLEMENTED)))
        ]

        chip_x = mx + 24
        chip_y = cy + 44
        self.planning_filter_rects = {}

        for key, label, count in filter_chips:
            is_sel = (self.planning_filter_status == key)
            c_text = f"{label} ({count})"
            c_surf = self.font_badge.render(c_text, True, (255, 255, 255) if is_sel else COLOR_TEXT_MUTED)
            c_w = c_surf.get_width() + 18
            c_h = 24
            cr = pygame.Rect(chip_x, chip_y, c_w, c_h)
            self.planning_filter_rects[key] = cr

            bg = (37, 99, 235) if is_sel else (30, 41, 59)
            border_c = (96, 165, 250) if is_sel else (71, 85, 105)
            pygame.draw.rect(surface, bg, cr, border_radius=12)
            pygame.draw.rect(surface, border_c, cr, width=1, border_radius=12)
            surface.blit(c_surf, (cr.centerx - c_surf.get_width() // 2, cr.centery - c_surf.get_height() // 2))

            chip_x += c_w + 8

        # Active items
        if self.planning_filter_status == "ALL":
            active_list = PLANNING_FEATURES
        else:
            active_list = get_features_by_status(self.planning_filter_status)

        total_items = len(active_list)
        per_page = self.planning_items_per_page
        max_page = max(0, (total_items - 1) // per_page)
        self.planning_page = min(self.planning_page, max_page)
        start_idx = self.planning_page * per_page
        page_items = active_list[start_idx:start_idx + per_page]

        # Feature Cards
        y_cur = cy + 74
        for f in page_items:
            f_rect = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 64)
            status = f.get("status")

            if status == STATUS_IMPLEMENTED:
                card_bg = (15, 30, 20)
                border_col = (34, 197, 94)
                badge_bg = (20, 83, 45)
                badge_txt_col = (240, 253, 244)
                badge_label = "IMPLEMENTED"
            elif status == STATUS_PARTIAL:
                card_bg = (35, 28, 12)
                border_col = COLOR_BADGE_PARTIAL
                badge_bg = (113, 63, 18)
                badge_txt_col = (254, 240, 138)
                badge_label = "PARTIAL (WIP)"
            else:
                card_bg = (24, 34, 52)
                border_col = (71, 85, 105)
                badge_bg = (51, 65, 85)
                badge_txt_col = (203, 213, 225)
                badge_label = "PLANNED WIP"

            pygame.draw.rect(surface, card_bg, f_rect, border_radius=6)
            pygame.draw.rect(surface, border_col, f_rect, width=1, border_radius=6)

            # Name & Category
            title_text = f"{f['name']}  ·  [{f.get('category', 'System')}]"
            surface.blit(self.font_sub.render(title_text, True, (241, 245, 249)), (f_rect.x + 12, f_rect.y + 6))

            # Status Badge
            b_surf = self.font_badge.render(badge_label, True, badge_txt_col)
            b_w = b_surf.get_width() + 16
            b_rect = pygame.Rect(f_rect.right - b_w - 12, f_rect.y + 7, b_w, 20)
            pygame.draw.rect(surface, badge_bg, b_rect, border_radius=4)
            pygame.draw.rect(surface, border_col, b_rect, width=1, border_radius=4)
            surface.blit(b_surf, (b_rect.centerx - b_surf.get_width() // 2, b_rect.centery - b_surf.get_height() // 2))

            # Summary and description
            desc_text = f"{f.get('summary', '')} — {f.get('description', '')}"
            if len(desc_text) > 130:
                desc_text = desc_text[:127] + "..."
            surface.blit(self.font_body.render(desc_text, True, (203, 213, 225)), (f_rect.x + 12, f_rect.y + 26))

            # Lead Agent tag
            agent_tag = f"Lead Agent: {f.get('owner_agent', 'Settlement Engine')}"
            surface.blit(self.font_badge.render(agent_tag, True, (148, 163, 184)), (f_rect.x + 12, f_rect.y + 45))

            y_cur += 70

        # Pagination Controls
        pag_y = cy + self.modal_h - 100
        page_info = f"Showing page {self.planning_page + 1} of {max_page + 1}  ({total_items} features)"
        surface.blit(self.font_body.render(page_info, True, COLOR_TEXT_MUTED), (mx + 24, pag_y + 4))

        self.planning_prev_btn_rect = pygame.Rect(mx + self.modal_w - 190, pag_y, 76, 26)
        prev_hov = self.planning_prev_btn_rect.collidepoint(mouse_pos)
        prev_enabled = (self.planning_page > 0)
        pygame.draw.rect(surface, (51, 65, 85) if (prev_hov and prev_enabled) else (30, 41, 59), self.planning_prev_btn_rect, border_radius=4)
        pygame.draw.rect(surface, (96, 165, 250) if prev_enabled else (71, 85, 105), self.planning_prev_btn_rect, width=1, border_radius=4)
        p_txt = self.font_badge.render("< Prev", True, (255, 255, 255) if prev_enabled else COLOR_TEXT_MUTED)
        surface.blit(p_txt, (self.planning_prev_btn_rect.centerx - p_txt.get_width() // 2, self.planning_prev_btn_rect.centery - p_txt.get_height() // 2))

        self.planning_next_btn_rect = pygame.Rect(mx + self.modal_w - 104, pag_y, 76, 26)
        next_hov = self.planning_next_btn_rect.collidepoint(mouse_pos)
        next_enabled = (self.planning_page < max_page)
        pygame.draw.rect(surface, (51, 65, 85) if (next_hov and next_enabled) else (30, 41, 59), self.planning_next_btn_rect, border_radius=4)
        pygame.draw.rect(surface, (96, 165, 250) if next_enabled else (71, 85, 105), self.planning_next_btn_rect, width=1, border_radius=4)
        n_txt = self.font_badge.render("Next >", True, (255, 255, 255) if next_enabled else COLOR_TEXT_MUTED)
        surface.blit(n_txt, (self.planning_next_btn_rect.centerx - n_txt.get_width() // 2, self.planning_next_btn_rect.centery - n_txt.get_height() // 2))

