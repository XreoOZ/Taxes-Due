"""RaportUI tab view — extracted from ui_raport.py (mixin)."""

import pygame
from game.config import COLOR_TEXT_MUTED, DEFAULT_JOB_SCHEDULE, SCHEDULE_TYPES
from game.systems.work.schedule import UNIVERSAL_SCHEDULE_ID
from game.ui.ui_theme import ui_font, upx


class ScheduleMixin:
    def _draw_schedule_tab(self, surface, mx, cy, schedule_manager=None, day_cycle=None):
        """RimWorld-Style 24-Hour Activity Schedule Tab"""
        mouse_pos = pygame.mouse.get_pos()
        cur_hour = getattr(day_cycle, "current_hour", 8.0) if day_cycle else 8.0

        # =============================================================
        # Universal 24-Hour Schedule (per-job schedules removed —
        # every job, including Unassigned, follows this one schedule)
        # =============================================================
        self.selected_schedule_job_id = UNIVERSAL_SCHEDULE_ID
        self.schedule_job_select_btn_rects = {}
        self.schedule_back_btn_rect = None
        self.job_search_rect = None
        self.job_search_active = False
        if schedule_manager and not getattr(schedule_manager, "universal_schedule_enabled", False):
            # One-time migration: per-job schedules are gone, so seed the
            # universal schedule and sync every job to it.
            schedule_manager.activate_universal_schedule()

        job_name = "Universal Schedule (All Jobs)"

        # Header & Back Button (Back only exists when embedded in the Workers tab)
        back_w = 140 if self.active_tab == 5 else 0
        title_x = mx + upx(24) + (back_w + upx(14) if back_w else 0)
        if back_w:
            self.schedule_back_btn_rect = pygame.Rect(mx + upx(24), cy - upx(4), back_w, upx(28))
            b_hover = self.schedule_back_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (51, 65, 85) if b_hover else (30, 41, 59), self.schedule_back_btn_rect, border_radius=upx(6))
            pygame.draw.rect(surface, (96, 165, 250), self.schedule_back_btn_rect, width=1, border_radius=upx(6))
            b_lbl = self.font_badge.render("< Back to Jobs", True, (255, 255, 255))
            surface.blit(b_lbl, (self.schedule_back_btn_rect.centerx - b_lbl.get_width() // 2, self.schedule_back_btn_rect.centery - b_lbl.get_height() // 2))

        surface.blit(self.font_title.render(f"{job_name} 24-Hour Schedule", True, (241, 245, 249)), (title_x, cy - upx(4)))

        # Current Hour indicator
        curr_str = f"Time: {int(cur_hour):02d}:00"
        surface.blit(self.font_sub.render(curr_str, True, (250, 204, 21)), (mx + self.modal_w - upx(180), cy - 2))

        # 1. Paintbrush tools banner
        tool_y = cy + upx(28)
        tool_rect = pygame.Rect(mx + upx(24), tool_y, self.modal_w - upx(48), upx(38))
        pygame.draw.rect(surface, (24, 34, 52), tool_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (71, 85, 105), tool_rect, width=1, border_radius=upx(6))

        surface.blit(self.font_badge.render("PAINT TOOL:", True, COLOR_TEXT_MUTED), (tool_rect.x + upx(12), tool_rect.y + upx(11)))

        self.schedule_brush_btn_rects = {}
        bx = tool_rect.x + upx(100)
        for b_id, b_info in SCHEDULE_TYPES.items():
            if b_id == "PRAYER":
                continue
            b_btn = pygame.Rect(bx, tool_rect.y + upx(5), upx(96), upx(28))
            self.schedule_brush_btn_rects[b_id] = b_btn
            is_sel = (self.selected_schedule_brush == b_id)
            col = b_info["color"]
            if is_sel:
                pygame.draw.rect(surface, col, b_btn, border_radius=upx(5))
                pygame.draw.rect(surface, (255, 255, 255), b_btn, width=2, border_radius=upx(5))
                lbl_col = (255, 255, 255)
            else:
                pygame.draw.rect(surface, (30, 41, 59), b_btn, border_radius=upx(5))
                pygame.draw.rect(surface, col, b_btn, width=1, border_radius=upx(5))
                lbl_col = col

            t_lbl = self.font_badge.render(f"{b_info['name']}", True, lbl_col)
            surface.blit(t_lbl, (b_btn.centerx - t_lbl.get_width() // 2, b_btn.centery - t_lbl.get_height() // 2))
            bx += upx(104)

        # 3. Prayer Time Contiguous Block Adjustment Banner (universal schedule)
        if schedule_manager:
            p_s, p_e = schedule_manager.get_prayer_hours()
            pr_banner = pygame.Rect(mx + upx(24), tool_y + upx(44), self.modal_w - upx(48), upx(36))
            pygame.draw.rect(surface, (30, 27, 46), pr_banner, border_radius=upx(6))
            pygame.draw.rect(surface, (168, 85, 247), pr_banner, width=1, border_radius=upx(6))

            pr_head = self.font_badge.render("⛪ DECREED PRAYER TIME BLOCK (ALL GUILDS ATTEND):", True, (216, 180, 254))
            surface.blit(pr_head, (pr_banner.x + upx(12), pr_banner.y + upx(10)))

            # Start Hour typable input
            ctrl_x = pr_banner.right - upx(280)
            surface.blit(self.font_badge.render("Start:", True, COLOR_TEXT_MUTED), (ctrl_x, pr_banner.y + upx(10)))
            s_key = ("num", "prayer_start", 0)
            s_rect = pygame.Rect(ctrl_x + upx(42), pr_banner.y + upx(6), upx(34), upx(24))
            self.num_fields[s_key] = {"rect": s_rect, "kind": "prayer_start",
                                      "min": 0, "max": 23}
            self._draw_num_input(surface, s_key, s_rect, f"{p_s:02d}")
            surface.blit(self.font_badge.render(":00", True, COLOR_TEXT_MUTED),
                         (s_rect.right + upx(4), pr_banner.y + upx(8)))

            # End Hour typable input
            end_ctrl_x = ctrl_x + upx(110)
            surface.blit(self.font_badge.render("End:", True, COLOR_TEXT_MUTED), (end_ctrl_x, pr_banner.y + upx(10)))
            e_key = ("num", "prayer_end", 0)
            e_rect = pygame.Rect(end_ctrl_x + upx(37), pr_banner.y + upx(6), upx(34), upx(24))
            self.num_fields[e_key] = {"rect": e_rect, "kind": "prayer_end",
                                      "min": 1, "max": 24}
            self._draw_num_input(surface, e_key, e_rect, f"{p_e:02d}")
            surface.blit(self.font_badge.render(":00", True, COLOR_TEXT_MUTED),
                         (e_rect.right + upx(4), pr_banner.y + upx(8)))

            grid_y = pr_banner.bottom + upx(12)
        else:
            grid_y = tool_y + upx(46)

        # 3. Timetable Grid (24 boxes)
        day_sched_title = f"{job_name} 24-Hour Timeline (Click hour slot to apply paint tool):"
        surface.blit(self.font_sub.render(day_sched_title, True, (241, 245, 249)), (mx + upx(24), grid_y))

        sched = schedule_manager.get_schedule_view(self.selected_schedule_job_id) if schedule_manager else list(DEFAULT_JOB_SCHEDULE)
        grid_bar_y = grid_y + upx(24)
        avail_grid_w = self.modal_w - upx(48)
        cell_w = avail_grid_w // upx(24)
        cell_h = upx(54)

        self.schedule_hour_cell_rects = {}
        for h in range(24):
            cx = mx + upx(24) + h * cell_w
            cell_rect = pygame.Rect(cx, grid_bar_y, cell_w - 2, cell_h)
            self.schedule_hour_cell_rects[h] = cell_rect

            act = sched[h]
            act_col = SCHEDULE_TYPES.get(act, {}).get("color", (100, 116, 139))
            is_current = (int(cur_hour) == h)

            pygame.draw.rect(surface, act_col, cell_rect, border_radius=upx(4))
            if is_current:
                pygame.draw.rect(surface, (250, 204, 21), cell_rect, width=2, border_radius=upx(4))
            else:
                pygame.draw.rect(surface, (15, 23, 42), cell_rect, width=1, border_radius=upx(4))

            # Hour text
            h_txt = self.font_badge.render(f"{h:02d}", True, (255, 255, 255))
            surface.blit(h_txt, (cell_rect.centerx - h_txt.get_width() // 2, cell_rect.y + upx(5)))

            # Activity abbreviation
            abbrev = act[:1]  # 'W', 'L', 'S', 'A', 'P'
            a_txt = self.font_sub.render(abbrev, True, (255, 255, 255))
            surface.blit(a_txt, (cell_rect.centerx - a_txt.get_width() // 2, cell_rect.y + upx(22)))

            if is_current:
                pygame.draw.polygon(surface, (250, 204, 21), [
                    (cell_rect.centerx, grid_bar_y - 2),
                    (cell_rect.centerx - upx(4), grid_bar_y - upx(7)),
                    (cell_rect.centerx + upx(4), grid_bar_y - upx(7))
                ])

        # Presets & Quick Fill Section
        preset_y = grid_bar_y + cell_h + upx(14)
        surface.blit(self.font_sub.render("Quick Schedule Presets:", True, COLOR_TEXT_MUTED), (mx + upx(24), preset_y + upx(4)))

        self.schedule_preset_btn_rects = {}
        presets = [
            ("standard", "Standard (10h Work, 8h Sleep)", (59, 130, 246)),
            ("hardwork", "Hardworking (15h Work, 6h Sleep)", (245, 158, 11)),
            ("relaxed", "Relaxed (7h Work, 9h Sleep)", (34, 197, 94))
        ]
        px = mx + upx(200)
        for p_id, p_title, p_col in presets:
            p_rect = pygame.Rect(px, preset_y, upx(160), upx(28))
            self.schedule_preset_btn_rects[p_id] = p_rect
            p_hover = p_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, p_col if p_hover else (30, 41, 59), p_rect, border_radius=upx(5))
            pygame.draw.rect(surface, p_col, p_rect, width=1, border_radius=upx(5))
            p_lbl = self.font_badge.render(p_title.split(' ')[0], True, (255, 255, 255))
            surface.blit(p_lbl, (p_rect.centerx - p_lbl.get_width() // 2, p_rect.centery - p_lbl.get_height() // 2))
            px += upx(170)

        # Explanation notes
        note_y = preset_y + upx(38)
        note = self.font_body.render("• Workers follow their active hourly schedule. During WORK, farmers water unwatered tiles and harvest ripe crops.", True, COLOR_TEXT_MUTED)
        surface.blit(note, (mx + upx(24), note_y))
        note2 = self.font_body.render("• During SLEEP, villagers return to their family household. During LEISURE, they relax near Town Center.", True, COLOR_TEXT_MUTED)
        surface.blit(note2, (mx + upx(24), note_y + upx(18)))

