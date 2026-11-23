"""RaportUI tab view — extracted from ui_raport.py (mixin)."""

import pygame
from game.config import COLOR_BADGE_WIP, COLOR_MODAL_BORDER, COLOR_TEXT_MUTED, COLOR_TEXT_TITLE, PRIORITY_COLORS, WORK_TYPES


class PriorityMixin:
    def _draw_priority_tab(self, surface, mx, cy, servant_manager):
        """RimWorld-Style Work Priorities Grid (1=High, 4=Low, -=Off)"""
        title = self.font_sub.render(" Servant Work Priorities (RimWorld Priority Matrix)", True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + 24, cy))

        sub_desc = self.font_body.render("Left-click each cell to cycle priority: 1 (High) → 2 → 3 → 4 (Low) → - (Off)", True, COLOR_TEXT_MUTED)
        surface.blit(sub_desc, (mx + 24, cy + 20))

        if not servant_manager or not servant_manager.servants:
            none_s = self.font_body.render("- No servants currently assigned to manor.", True, COLOR_TEXT_MUTED)
            surface.blit(none_s, (mx + 36, cy + 50))
            return

        table_x = mx + 24
        table_y = cy + 48
        name_col_w = 150
        cell_w = 110
        row_h = 36

        self.priority_cell_rects = {}

        # 1. Header Row
        header_rect = pygame.Rect(table_x, table_y, name_col_w + len(WORK_TYPES) * cell_w, 28)
        pygame.draw.rect(surface, (30, 41, 59), header_rect, border_radius=4)

        h_name = self.font_badge.render("WORKER", True, COLOR_TEXT_TITLE)
        surface.blit(h_name, (table_x + 10, table_y + 7))

        for j, wt in enumerate(WORK_TYPES):
            col_x = table_x + name_col_w + (j * cell_w)
            w_col = COLOR_BADGE_WIP if wt["wip"] else (241, 245, 249)
            h_lbl = self.font_badge.render(wt["name"], True, w_col)
            surface.blit(h_lbl, (col_x + 8, table_y + 7))

        # 2. Worker Rows
        cur_y = table_y + 32
        for s in servant_manager.servants:
            row_rect = pygame.Rect(table_x, cur_y, name_col_w + len(WORK_TYPES) * cell_w, row_h)
            pygame.draw.rect(surface, (15, 23, 42, 180), row_rect, border_radius=4)
            pygame.draw.rect(surface, (51, 65, 85), row_rect, width=1, border_radius=4)

            # Servant Avatar Dot & Name
            pygame.draw.circle(surface, (245, 158, 11), (table_x + 18, cur_y + row_h // 2), 7)
            pygame.draw.circle(surface, (120, 53, 15), (table_x + 18, cur_y + row_h // 2), 7, 1)
            s_name = self.font_sub.render(s.name, True, (241, 245, 249))
            surface.blit(s_name, (table_x + 32, cur_y + 9))

            # Work Type Cells
            for j, wt in enumerate(WORK_TYPES):
                w_id = wt["id"]
                col_x = table_x + name_col_w + (j * cell_w)
                cell_rect = pygame.Rect(col_x + 6, cur_y + 4, cell_w - 12, row_h - 8)

                if wt["wip"]:
                    # Disabled WIP cell
                    pygame.draw.rect(surface, (30, 41, 59, 140), cell_rect, border_radius=4)
                    pygame.draw.rect(surface, (51, 65, 85), cell_rect, width=1, border_radius=4)
                    txt = self.font_badge.render("- (WIP)", True, (100, 116, 139))
                    surface.blit(txt, (cell_rect.centerx - txt.get_width() // 2, cell_rect.centery - txt.get_height() // 2))
                else:
                    self.priority_cell_rects[(s.id, w_id)] = cell_rect
                    p_val = s.work_priorities.get(w_id, 1)
                    p_col = PRIORITY_COLORS.get(p_val, (71, 85, 105))

                    cell_hover = cell_rect.collidepoint(pygame.mouse.get_pos())
                    bg_col = (45, 60, 80) if cell_hover else (24, 34, 52)

                    pygame.draw.rect(surface, bg_col, cell_rect, border_radius=4)
                    pygame.draw.rect(surface, p_col, cell_rect, width=2 if p_val > 0 else 1, border_radius=4)

                    val_str = str(p_val) if p_val > 0 else "—"
                    p_surf = self.font_priority.render(val_str, True, p_col if p_val > 0 else (100, 116, 139))
                    surface.blit(p_surf, (cell_rect.centerx - p_surf.get_width() // 2, cell_rect.centery - p_surf.get_height() // 2))

            cur_y += row_h + 6

        # 3. Legend & Instructions Footer
        leg_y = cur_y + 14
        pygame.draw.line(surface, COLOR_MODAL_BORDER, (table_x, leg_y), (table_x + name_col_w + len(WORK_TYPES) * cell_w, leg_y))

        leg_txt = self.font_body.render("Priority Levels: [ 1 ] Highest Priority  |  [ 2 ] Normal  |  [ 3 ] Low  |  [ 4 ] Lowest  |  [ — ] Disabled", True, (226, 232, 240))
        surface.blit(leg_txt, (table_x, leg_y + 10))

        rule_txt = self.font_badge.render("Servants automatically choose the lowest number task available. If tied, closest work is preferred.", True, COLOR_TEXT_MUTED)
        surface.blit(rule_txt, (table_x, leg_y + 32))

