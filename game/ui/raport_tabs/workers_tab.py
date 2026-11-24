"""RaportUI tab view — extracted from ui_raport.py (mixin)."""

import pygame
from game.config import COLOR_BADGE_WIP, COLOR_TEXT_MUTED, COLOR_TEXT_TITLE, DEDICATED_JOBS
from game.systems.economy.production_distribution import ProductionDistributionSystem
from game.systems.work.schedule import UNIVERSAL_SCHEDULE_ID
from game.ui.ui_theme import ui_font, upx


class WorkersMixin:
    @staticmethod
    def _workplace_key(workplace):
        kind, obj = workplace
        object_id = getattr(obj, "id", None)
        if object_id is None:
            object_id = f"{getattr(obj, 'building_type', kind)}:{getattr(obj, 'grid_x', 0)}:{getattr(obj, 'grid_y', 0)}"
        return f"{kind}:{object_id}"

    def _draw_workplaces_view(self, surface, mx, cy, villager_manager, permit_manager, furniture_manager, building_manager=None):
        from game.systems.work.workplace_system import get_job_workplaces, workplace_workers, workplace_job_workers, workplace_capacity
        # This sub-view draws no sort buttons — clear stale rects so clicks
        # here can't trigger the directory-level handlers.
        self.auto_sort_all_btn_rect = None
        self.unassign_all_btn_rect = None
        job_id = self.selected_workstation_job_id
        job_cfg = DEDICATED_JOBS.get(job_id, {})
        mouse_pos = pygame.mouse.get_pos()
        self.back_to_jobs_btn_rect = pygame.Rect(mx + upx(24), cy - upx(4), upx(140), upx(28))
        pygame.draw.rect(surface, (30, 41, 59), self.back_to_jobs_btn_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (96, 165, 250), self.back_to_jobs_btn_rect, width=1, border_radius=upx(6))
        label = self.font_badge.render("< Back to Jobs", True, (255, 255, 255))
        surface.blit(label, (self.back_to_jobs_btn_rect.centerx - label.get_width() // 2, self.back_to_jobs_btn_rect.centery - label.get_height() // 2))
        title = self.font_title.render(f"{job_cfg.get('name', job_id)} Workstations", True, (241, 245, 249))
        surface.blit(title, (mx + upx(178), cy - upx(4)))
        workplaces = get_job_workplaces(job_id, permit_manager, furniture_manager, building_manager)
        y = cy + upx(40)
        bottom = (surface.get_height() + self.modal_h) // 2 - upx(14)
        self.workplace_crop_btn_rects = {}
        self.workplace_plant_btn_rects = {}
        self.jobs_viewport_rect = pygame.Rect(mx + upx(16), y, self.modal_w - upx(32), max(0, bottom - y))
        old_clip = surface.get_clip()
        surface.set_clip(self.jobs_viewport_rect)
        if not workplaces:
            msg = self.font_body.render("No workplaces are available yet. Place or create one first.", True, COLOR_TEXT_MUTED)
            surface.blit(msg, (mx + upx(32), y + upx(12)))
        for kind, obj in workplaces:
            is_permit = kind == "permit"
            obj_cfg = getattr(obj, "type_cfg", {}) if not is_permit else {}
            is_station = (kind == "furniture"
                          and (obj_cfg.get("station_inventory_items")
                               or obj_cfg.get("station_inventory_mine_bound")))
            is_farm_permit = is_permit and getattr(obj, "permit_type", "") == "farm"
            card_h = (upx(104) if is_farm_permit else upx(84)) if is_permit else (upx(118) if is_station else upx(54))
            card = pygame.Rect(mx + upx(24), y, self.modal_w - upx(48), card_h)
            pygame.draw.rect(surface, (24, 34, 52), card, border_radius=upx(7))
            pygame.draw.rect(surface, (51, 65, 85), card, width=1, border_radius=upx(7))
            station_key = self._workplace_key((kind, obj))
            if getattr(self, "highlight_workplace_key", None) == station_key:
                pygame.draw.rect(surface, (56, 189, 248), card, width=2, border_radius=upx(7))
            station_name = getattr(obj, "name", None) or getattr(obj, "type_cfg", {}).get("name", getattr(obj, "permit_type", "Workplace").replace("_", " ").title())
            station_workers = workplace_job_workers((kind, obj), job_id, villager_manager)
            label = self.font_sub.render(station_name, True, (241, 245, 249))
            surface.blit(label, (card.x + upx(14), card.y + upx(8)))
            station_cap = workplace_capacity((kind, obj))
            detail_txt = f"{len(station_workers)} workers" if station_cap is None else f"{len(station_workers)} / {station_cap} workers"
            detail = self.font_body.render(detail_txt, True, COLOR_TEXT_MUTED)
            surface.blit(detail, (card.x + upx(14), card.y + upx(29)))
            wk_key = ("num", "workplace_workers", (job_id, station_key))
            # Worker-count input sits right next to its "N / cap workers" label
            # instead of floating in the top-right corner.
            wk_rect = pygame.Rect(card.x + upx(14) + detail.get_width() + upx(10), card.y + upx(22), upx(38), upx(26))
            self.num_fields[wk_key] = {"rect": wk_rect, "kind": "workplace_workers",
                                       "payload": (job_id, station_key),
                                       "min": 0, "max": station_cap if station_cap is not None else 99}
            self._draw_num_input(surface, wk_key, wk_rect, len(station_workers))

            if is_permit:
                # Row 2: typable worker cap + crop selector (farms)
                row2_y = card.y + upx(50)
                max_lbl = self.font_badge.render("Max:", True, COLOR_TEXT_MUTED)
                surface.blit(max_lbl, (card.x + upx(14), row2_y + upx(4)))
                cur_max = int(getattr(obj, "max_workers", 2))
                max_key = ("num", "workplace_max", (job_id, station_key))
                max_rect = pygame.Rect(card.x + upx(52), row2_y - 2, upx(36), upx(26))
                self.num_fields[max_key] = {"rect": max_rect, "kind": "workplace_max",
                                            "payload": (job_id, station_key), "min": 0, "max": 99}
                self._draw_num_input(surface, max_key, max_rect, cur_max)

                if getattr(obj, "permit_type", "") == "farm":
                    crop_name = getattr(obj, "crop", None) or "No crop"
                    crop_lbl = self.font_badge.render(f"Crop: {crop_name}", True, COLOR_TEXT_MUTED)
                    surface.blit(crop_lbl, (card.x + upx(160), row2_y + upx(4)))
                    # Select button hugs the Crop label instead of the far
                    # right edge of the card.
                    crop_btn = pygame.Rect(card.x + upx(160) + crop_lbl.get_width() + upx(10), row2_y - 2, upx(76), upx(28))
                    self.workplace_crop_btn_rects[(job_id, self._workplace_key((kind, obj)))] = crop_btn
                    cb_hov = crop_btn.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (22, 101, 52) if cb_hov else (20, 83, 45), crop_btn, border_radius=upx(5))
                    pygame.draw.rect(surface, (74, 222, 128), crop_btn, width=1, border_radius=upx(5))
                    cb_txt = self.font_badge.render("Select", True, (255, 255, 255))
                    surface.blit(cb_txt, (crop_btn.centerx - cb_txt.get_width() // 2, crop_btn.centery - cb_txt.get_height() // 2))

                    # Row 3: household output shares for this specific lot
                    # (moved here from the old Production tab).
                    row3_y = card.y + upx(76)
                    from game.systems.economy.production_distribution import ProductionDistributionSystem
                    ps = ProductionDistributionSystem.get_instance()
                    assigned_w = list(getattr(obj, "assigned_workers", []) or [])
                    counts, total_w = ps.get_participating_household_counts(assigned_w, villager_manager)
                    shares = ps.calculate_shares(assigned_w, villager_manager)
                    if total_w > 0 and shares:
                        parts = []
                        for h_id, ratio in shares.items():
                            fam = villager_manager.get_family_by_id(h_id) if villager_manager else None
                            fam_name = f"The {fam.surname} Family" if fam else h_id
                            parts.append(f"{fam_name}: {counts.get(h_id, 0)}w ({ratio * 100:.0f}%)")
                        share_txt = self.font_badge.render("Shares: " + " | ".join(parts), True, (34, 197, 94))
                    else:
                        share_txt = self.font_badge.render("Shares: no workers assigned", True, COLOR_TEXT_MUTED)
                    surface.blit(share_txt, (card.x + upx(14), row3_y + 2))

            if is_station:
                from game.world.natural_resources import (
                    NaturalResourceManager, get_natural_resources,
                )
                station_key = self._workplace_key((kind, obj))
                # Row 2: typable daily quota (0 = unlimited)
                row2_y = card.y + upx(50)
                quota_lbl = self.font_badge.render("Quota/day (0=∞):", True, COLOR_TEXT_MUTED)
                surface.blit(quota_lbl, (card.x + upx(14), row2_y + upx(4)))
                quota_val = int(getattr(obj, "station_quota_daily", 0) or 0)
                quota_key = ("num", "workplace_quota", (job_id, station_key))
                quota_rect = pygame.Rect(card.x + upx(140), row2_y - 2, upx(40), upx(26))
                self.num_fields[quota_key] = {"rect": quota_rect, "kind": "workplace_quota",
                                              "payload": (job_id, station_key), "min": 0, "max": 99999}
                self._draw_num_input(surface, quota_key, quota_rect,
                                     quota_val if quota_val > 0 else "∞")

                # Row 3: Plant-a-Tree toggle (woodsman) or mine info (miner)
                row3_y = card.y + upx(78)
                if obj.furniture_type == "woodsman_lodge":
                    plant_on = bool(getattr(obj, "plant_tree_enabled", False))
                    plant_lbl = self.font_badge.render("Plant a Tree:", True, COLOR_TEXT_MUTED)
                    surface.blit(plant_lbl, (card.x + upx(14), row3_y + upx(4)))
                    plant_btn = pygame.Rect(card.x + upx(118), row3_y - 2, upx(76), upx(24))
                    self.workplace_plant_btn_rects[(job_id, station_key)] = plant_btn
                    ph = plant_btn.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (22, 101, 52) if (plant_on or ph) else (51, 65, 85), plant_btn, border_radius=upx(5))
                    pygame.draw.rect(surface, (74, 222, 128) if plant_on else (100, 116, 139), plant_btn, width=1, border_radius=upx(5))
                    pt = self.font_badge.render("ON" if plant_on else "OFF", True, (255, 255, 255))
                    surface.blit(pt, (plant_btn.centerx - pt.get_width() // 2, plant_btn.centery - pt.get_height() // 2))
                elif obj.furniture_type == "miner_workstation":
                    nr = get_natural_resources()
                    mine = next((m for m in nr.mines if m.get("id") == getattr(obj, "bound_mine_id", None)), None)
                    if mine is not None:
                        tier_name = NaturalResourceManager.mine_tier_name(mine)
                        lo, hi = NaturalResourceManager.mine_yield_range(mine)
                        rate_str = f"{lo}/hr" if lo == hi else f"{lo}-{hi}/hr"
                        info = self.font_badge.render(
                            f"{mine['kind']} · {tier_name} ({rate_str})", True, COLOR_TEXT_MUTED)
                        surface.blit(info, (card.x + upx(14), row3_y + upx(4)))

                # Row 4: workstation stock (unlimited, filtered)
                row4_y = card.y + upx(102)
                stock_parts = [f"{amt}x {item}" for item, amt in sorted(obj.inventory.items()) if amt > 0]
                stock_txt = "Stock: " + (", ".join(stock_parts) if stock_parts else "empty")
                stock_lbl = self.font_badge.render(stock_txt, True, (251, 191, 36))
                surface.blit(stock_lbl, (card.x + upx(14), row4_y + 2))
            y += card_h + upx(8)
        surface.set_clip(old_clip)
        self._draw_crop_picker_popup(surface, mx, cy, permit_manager)

    def _draw_workers_tab(self, surface, mx, cy, villager_manager, permit_manager, furniture_manager=None, schedule_manager=None, building_manager=None):
        mouse_pos = pygame.mouse.get_pos()
        self.universal_schedule_btn_rect = None
        self.job_search_rect = None

        # =============================================================
        # VIEW 1: Dedicated Jobs Directory
        # =============================================================
        if self.selected_workstation_job_id is not None:
            self._draw_workplaces_view(surface, mx, cy, villager_manager, permit_manager, furniture_manager, building_manager)
        elif self.selected_job_id is None:
            # Title
            w_title = self.font_title.render("VILLAGE WORKFORCE & JOBS DIRECTORY", True, COLOR_TEXT_TITLE)
            surface.blit(w_title, (mx + upx(24), cy - upx(4)))

            # Unassign All + Auto Sort All Buttons (Top Right)
            self.unassign_all_btn_rect = pygame.Rect(mx + self.modal_w - upx(352), cy - upx(6), upx(140), upx(28))
            ua_hover = self.unassign_all_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (122, 72, 48) if ua_hover else (96, 56, 38), self.unassign_all_btn_rect, border_radius=upx(6))
            pygame.draw.rect(surface, (214, 120, 90), self.unassign_all_btn_rect, width=1, border_radius=upx(6))
            ua_lbl = self.font_badge.render("Unassign All", True, (255, 255, 255))
            surface.blit(ua_lbl, (self.unassign_all_btn_rect.centerx - ua_lbl.get_width() // 2, self.unassign_all_btn_rect.centery - ua_lbl.get_height() // 2))

            self.auto_sort_all_btn_rect = pygame.Rect(mx + self.modal_w - upx(200), cy - upx(6), upx(176), upx(28))
            as_hover = self.auto_sort_all_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (16, 185, 129) if as_hover else (5, 150, 105), self.auto_sort_all_btn_rect, border_radius=upx(6))
            pygame.draw.rect(surface, (52, 211, 153), self.auto_sort_all_btn_rect, width=1, border_radius=upx(6))
            as_lbl = self.font_badge.render("Auto Sort All Workers", True, (255, 255, 255))
            surface.blit(as_lbl, (self.auto_sort_all_btn_rect.centerx - as_lbl.get_width() // 2, self.auto_sort_all_btn_rect.centery - as_lbl.get_height() // 2))

            sub_txt = self.font_body.render("Job roles dictate villager daily routines. Workers prioritize nearest designated lots.", True, COLOR_TEXT_MUTED)
            surface.blit(sub_txt, (mx + upx(24), cy + upx(22)))

            universal_y = cy + upx(42)
            self.universal_schedule_btn_rect = pygame.Rect(mx + upx(24), universal_y, self.modal_w - upx(48), upx(36))
            universal_hover = self.universal_schedule_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (30, 58, 88) if universal_hover else (24, 34, 52), self.universal_schedule_btn_rect, border_radius=upx(7))
            pygame.draw.rect(surface, (56, 189, 248), self.universal_schedule_btn_rect, width=1, border_radius=upx(7))
            universal_label = self.font_badge.render("Universal Schedule — Edit all jobs together", True, (241, 245, 249))
            surface.blit(universal_label, (self.universal_schedule_btn_rect.x + upx(12),
                                           self.universal_schedule_btn_rect.centery - universal_label.get_height() // 2))
            if schedule_manager:
                preview = schedule_manager.get_schedule_view(UNIVERSAL_SCHEDULE_ID)
                work_count = sum(1 for activity in preview if activity == "WORK")
                sleep_count = sum(1 for activity in preview if activity == "SLEEP")
                summary = self.font_badge.render(
                    f"{work_count}h Work  |  {sleep_count}h Sleep  |  Applies to every job, including Unassigned",
                    True, COLOR_TEXT_MUTED,
                )
                if summary.get_width() < self.universal_schedule_btn_rect.width - universal_label.get_width() - upx(40):
                    surface.blit(summary, (self.universal_schedule_btn_rect.right - summary.get_width() - upx(12),
                                           self.universal_schedule_btn_rect.centery - summary.get_height() // 2))

            # Job search box — type to filter the directory instead of scrolling
            search_y = cy + upx(84)
            self.job_search_rect = pygame.Rect(mx + upx(24), search_y, upx(320), upx(30))
            s_hover = self.job_search_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (24, 34, 52) if not self.job_search_active else (15, 23, 42), self.job_search_rect, border_radius=6)
            pygame.draw.rect(surface, (56, 189, 248) if (self.job_search_active or s_hover) else (71, 85, 105), self.job_search_rect, width=1, border_radius=upx(6))
            search_label = self.job_search_text if self.job_search_text else "Search jobs..."
            label_col = (241, 245, 249) if self.job_search_text else COLOR_TEXT_MUTED
            search_surface = self.font_body.render(search_label + ("_" if self.job_search_active else ""), True, label_col)
            surface.blit(search_surface, (self.job_search_rect.x + upx(10), self.job_search_rect.centery - search_surface.get_height() // 2))
            if self.job_search_text:
                clear_lbl = self.font_badge.render("ESC clear", True, COLOR_TEXT_MUTED)
                surface.blit(clear_lbl, (self.job_search_rect.right - clear_lbl.get_width() - upx(10), self.job_search_rect.centery - clear_lbl.get_height() // 2))

            query = self.job_search_text.strip().lower()
            visible_jobs = [
                (job_id, job_cfg) for job_id, job_cfg in DEDICATED_JOBS.items()
                if not query or query in (job_cfg.get("name", "") + " " + job_cfg.get("desc", "") + " " + job_id).lower()
            ]
            if query:
                match_lbl = self.font_badge.render(f"{len(visible_jobs)} match(es)", True, COLOR_TEXT_MUTED)
                surface.blit(match_lbl, (self.job_search_rect.right + upx(12), self.job_search_rect.centery - match_lbl.get_height() // 2))

            y_cur = cy + upx(124)
            screen_h = surface.get_height()
            content_bottom = (screen_h + self.modal_h) // 2 - upx(14)
            self.jobs_viewport_rect = pygame.Rect(mx + upx(16), y_cur, self.modal_w - upx(32), max(0, content_bottom - y_cur))
            jobs_content_h = len(visible_jobs) * (upx(58) + upx(8))
            self.jobs_max_scroll = max(0, jobs_content_h - self.jobs_viewport_rect.height)
            self.jobs_scroll_y = max(0, min(self.jobs_scroll_y, self.jobs_max_scroll))
            y_cur -= self.jobs_scroll_y
            self.job_select_btn_rects = {}
            self.job_workstation_btn_rects = {}
            self.job_schedule_btn_rects = {}

            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            idle_vils = sum(
                1 for v in all_vils
                if getattr(v, "is_alive", True)
                and getattr(v, "job", "") in ("Unassigned", "Unemployed", "Peasant", None, "")
            )

            old_clip = surface.get_clip()
            surface.set_clip(self.jobs_viewport_rect)
            for job_id, job_cfg in visible_jobs:
                card_h = upx(58)
                card_rect = pygame.Rect(mx + upx(24), y_cur, self.modal_w - upx(48), card_h)
                is_wip = job_cfg.get("wip", False)

                pygame.draw.rect(surface, (24, 34, 52), card_rect, border_radius=upx(8))
                pygame.draw.rect(surface, (51, 65, 85), card_rect, width=1, border_radius=upx(8))

                # Icon circle
                icon_col = (71, 85, 105) if is_wip else (34, 197, 94)
                pygame.draw.circle(surface, icon_col, (card_rect.x + upx(24), card_rect.y + card_h // 2), upx(12))
                pygame.draw.circle(surface, (15, 23, 42), (card_rect.x + upx(24), card_rect.y + card_h // 2), upx(12), 2)

                # Title
                j_title = self.font_sub.render(job_cfg["name"], True, (241, 245, 249) if not is_wip else COLOR_TEXT_MUTED)
                surface.blit(j_title, (card_rect.x + upx(46), card_rect.y + upx(8)))

                if is_wip:
                    # WIP Badge
                    wip_b = pygame.Rect(card_rect.x + upx(46) + j_title.get_width() + upx(12), card_rect.y + upx(10), upx(48), upx(16))
                    pygame.draw.rect(surface, COLOR_BADGE_WIP, wip_b, border_radius=3)
                    surface.blit(self.font_badge.render("WIP", True, (0, 0, 0)), (wip_b.x + upx(13), wip_b.y + 1))

                    desc = self.font_body.render(job_cfg.get("desc", "Guild profession in development."), True, COLOR_TEXT_MUTED)
                    surface.blit(desc, (card_rect.x + upx(46), card_rect.y + upx(30)))
                else:
                    # Mirror the Workstations view: staffed/capacity aggregated
                    # across this job's actual workplaces (permits, furniture,
                    # buildings) instead of raw job-title headcount.
                    from game.systems.work.workplace_system import (
                        get_job_workplaces, workplace_capacity,
                        workplace_job_workers,
                    )
                    workplaces = get_job_workplaces(job_id, permit_manager, furniture_manager, building_manager)
                    total_cap = 0
                    filled = 0
                    for wp in workplaces:
                        cap = workplace_capacity(wp)
                        if cap is not None:
                            total_cap += cap
                        filled += len(workplace_job_workers(wp, job_id, villager_manager))

                    job_desc = job_cfg.get("desc", "Guild duties")
                    if workplaces:
                        stat_str = f"Workers: {filled}/{total_cap} slots ({idle_vils} idle) — {job_desc}"
                        stat_col = (34, 197, 94) if total_cap > 0 and filled >= total_cap else (245, 158, 11)
                    else:
                        stat_str = f"No workplaces yet — {job_desc}"
                        stat_col = COLOR_TEXT_MUTED
                    if len(stat_str) > 75:
                        stat_str = stat_str[:72] + "..."
                    surface.blit(self.font_body.render(stat_str, True, stat_col), (card_rect.x + upx(46), card_rect.y + upx(30)))

                    # Action Buttons: Workstations & roster (per-job schedules removed —
                    # the Universal Schedule button above edits every job at once)
                    btn_w = upx(104)
                    btn_h = upx(30)
                    btn_y = card_rect.y + upx(14)
                    action_gap = upx(6)
                    ws_rect = pygame.Rect(card_rect.right - upx(14) - btn_w, btn_y, btn_w, btn_h)
                    vw_rect = pygame.Rect(ws_rect.x - action_gap - btn_w, btn_y, btn_w, btn_h)
                    self.job_workstation_btn_rects[job_id] = ws_rect
                    ws_hover = ws_rect.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (14, 116, 144) if ws_hover else (15, 23, 42), ws_rect, border_radius=upx(6))
                    pygame.draw.rect(surface, (56, 189, 248), ws_rect, width=1, border_radius=upx(6))
                    ws_lbl = self.font_badge.render("Workstations", True, (255, 255, 255))
                    surface.blit(ws_lbl, (ws_rect.centerx - ws_lbl.get_width() // 2, ws_rect.centery - ws_lbl.get_height() // 2))

                    # View Workers Button
                    self.job_select_btn_rects[job_id] = vw_rect
                    vw_hover = vw_rect.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (37, 99, 235) if vw_hover else (30, 58, 138), vw_rect, border_radius=upx(6))
                    pygame.draw.rect(surface, (96, 165, 250), vw_rect, width=1, border_radius=upx(6))
                    vw_lbl = self.font_badge.render("View Workers", True, (255, 255, 255))
                    surface.blit(vw_lbl, (vw_rect.centerx - vw_lbl.get_width() // 2, vw_rect.centery - vw_lbl.get_height() // 2))

                y_cur += card_h + upx(8)
            if not visible_jobs:
                none_lbl = self.font_body.render("No jobs match your search.", True, COLOR_TEXT_MUTED)
                surface.blit(none_lbl, (mx + upx(40), y_cur + upx(8)))
            surface.set_clip(old_clip)
            if self.jobs_max_scroll > 0:
                track = pygame.Rect(self.jobs_viewport_rect.right - upx(5), self.jobs_viewport_rect.y, 3, self.jobs_viewport_rect.height)
                pygame.draw.rect(surface, (51, 65, 85), track, border_radius=2)
                thumb_h = max(upx(24), int(track.height * self.jobs_viewport_rect.height / jobs_content_h))
                thumb_y = track.y + int((track.height - thumb_h) * self.jobs_scroll_y / self.jobs_max_scroll)
                pygame.draw.rect(surface, (96, 165, 250), (track.x, thumb_y, track.width, thumb_h), border_radius=2)

        # =============================================================
        # VIEW 2: Individual Workers Roster for Selected Job
        # =============================================================
        else:
            job_cfg = DEDICATED_JOBS.get(self.selected_job_id, {})
            job_name = job_cfg.get("name", self.selected_job_id)

            # Header & Back Button
            back_w = upx(140)
            self.back_to_jobs_btn_rect = pygame.Rect(mx + upx(24), cy - upx(4), back_w, upx(28))
            b_hover = self.back_to_jobs_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (51, 65, 85) if b_hover else (30, 41, 59), self.back_to_jobs_btn_rect, border_radius=upx(6))
            pygame.draw.rect(surface, (96, 165, 250), self.back_to_jobs_btn_rect, width=1, border_radius=upx(6))

            back_lbl = self.font_badge.render("< Back to Jobs", True, (255, 255, 255))
            surface.blit(back_lbl, (self.back_to_jobs_btn_rect.centerx - back_lbl.get_width() // 2, self.back_to_jobs_btn_rect.centery - back_lbl.get_height() // 2))

            j_title = self.font_title.render(f"{job_name} Workforce", True, (241, 245, 249))
            surface.blit(j_title, (mx + upx(24) + back_w + upx(14), cy - upx(4)))

            # Auto Sort Button for this Job
            self.auto_sort_all_btn_rect = pygame.Rect(mx + self.modal_w - upx(180), cy - upx(4), upx(156), upx(28))
            as_hover = self.auto_sort_all_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (16, 185, 129) if as_hover else (5, 150, 105), self.auto_sort_all_btn_rect, border_radius=upx(6))
            pygame.draw.rect(surface, (52, 211, 153), self.auto_sort_all_btn_rect, width=1, border_radius=upx(6))
            as_lbl = self.font_badge.render("Auto Sort Closest", True, (255, 255, 255))
            surface.blit(as_lbl, (self.auto_sort_all_btn_rect.centerx - as_lbl.get_width() // 2, self.auto_sort_all_btn_rect.centery - as_lbl.get_height() // 2))

            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            job_vils = [v for v in all_vils if getattr(v, "is_alive", True) and v.job == self.selected_job_id]
            job_vils.sort(key=lambda v: ((getattr(villager_manager.get_family_by_id(v.family_id), "surname", "") if villager_manager else ""), str(v.full_name)))

            # Summary banner
            from game.systems.work.workplace_system import assigned_ids
            workforce_assigned = assigned_ids(permit_manager, furniture_manager, building_manager)
            assigned_vils = [v for v in job_vils if str(v.id) in workforce_assigned]
            unassigned_count = len(job_vils) - len(assigned_vils)

            banner_y = cy + upx(32)
            banner_rect = pygame.Rect(mx + upx(24), banner_y, self.modal_w - upx(48), upx(32))
            pygame.draw.rect(surface, (24, 34, 52), banner_rect, border_radius=upx(6))
            pygame.draw.rect(surface, (71, 85, 105), banner_rect, width=1, border_radius=upx(6))

            stat_txt = f"Total: {len(job_vils)} Workers   |   Assigned: {len(assigned_vils)}   |   Unassigned / Idle: {unassigned_count}"
            surface.blit(self.font_sub.render(stat_txt, True, (56, 189, 248)), (banner_rect.x + upx(14), banner_rect.y + upx(8)))

            y_cur = banner_y + upx(40)
            self.worker_assign_btn_rects = {}
            self.worker_unassign_btn_rects = {}

            if not job_vils:
                none_txt = self.font_body.render("- No villagers registered for this job yet. Add families in the Villagers tab!", True, COLOR_TEXT_MUTED)
                surface.blit(none_txt, (mx + upx(36), y_cur + upx(10)))
            else:
                last_household = None
                for v in job_vils:
                    fam = villager_manager.get_family_by_id(v.family_id) if villager_manager else None
                    household = f"The {fam.surname} Family" if fam else "No Household"
                    if household != last_household:
                        household_label = self.font_sub.render(household, True, (56, 189, 248))
                        surface.blit(household_label, (mx + upx(28), y_cur + 2))
                        y_cur += upx(22)
                        last_household = household
                    card = pygame.Rect(mx + upx(24), y_cur, self.modal_w - upx(48), upx(32))
                    pygame.draw.rect(surface, (15, 23, 42, 180), card, border_radius=upx(5))
                    pygame.draw.rect(surface, (51, 65, 85), card, width=1, border_radius=upx(5))

                    # Info
                    info_str = f"{v.full_name} ({v.role})"
                    surface.blit(self.font_body.render(info_str, True, (241, 245, 249)), (card.x + upx(12), card.y + upx(7)))

                    # Find this worker's assigned workplace for the selected job.
                    from game.systems.work.workplace_system import get_job_workplaces, workplace_job_workers
                    assigned_ws = next((ws for ws in get_job_workplaces(self.selected_job_id, permit_manager, furniture_manager, building_manager)
                                        if str(v.id) in {str(wid) for wid in workplace_job_workers(ws, self.selected_job_id, villager_manager)}), None)
                    assigned_station = assigned_ws[1] if assigned_ws else None
                    if assigned_station:
                        station_name = getattr(assigned_station, "name", None) or getattr(assigned_station, "type_cfg", {}).get("name", "Workplace")
                        status_str = f"Assigned:  {station_name}"
                        surface.blit(self.font_body.render(status_str, True, (34, 197, 94)), (card.x + upx(310), card.y + upx(7)))

                        # Unassign Button
                        un_btn = pygame.Rect(card.right - upx(94), card.y + upx(4), upx(84), upx(24))
                        station_kind = assigned_ws[0]
                        self.worker_unassign_btn_rects[(station_kind, self._workplace_key(assigned_ws), v.id)] = un_btn
                        u_hover = un_btn.collidepoint(mouse_pos)
                        pygame.draw.rect(surface, (220, 38, 38) if u_hover else (153, 27, 27), un_btn, border_radius=upx(4))
                        u_lbl = self.font_badge.render("Unassign", True, (255, 255, 255))
                        surface.blit(u_lbl, (un_btn.centerx - u_lbl.get_width() // 2, un_btn.centery - u_lbl.get_height() // 2))
                    else:
                        status_str = "Idle (Unassigned)"
                        surface.blit(self.font_body.render(status_str, True, (245, 158, 11)), (card.x + upx(310), card.y + upx(7)))

                        # Assign Nearest Button
                        as_btn = pygame.Rect(card.right - upx(110), card.y + upx(4), upx(100), upx(24))
                        self.worker_assign_btn_rects[v.id] = as_btn
                        a_hover = as_btn.collidepoint(mouse_pos)
                        pygame.draw.rect(surface, (37, 99, 235) if a_hover else (30, 58, 138), as_btn, border_radius=upx(4))
                        a_lbl = self.font_badge.render("+ Assign Slot", True, (255, 255, 255))
                        surface.blit(a_lbl, (as_btn.centerx - a_lbl.get_width() // 2, as_btn.centery - a_lbl.get_height() // 2))

                    y_cur += upx(36)

