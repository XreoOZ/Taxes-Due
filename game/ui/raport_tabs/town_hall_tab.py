"""RaportUI tab view — Town Hall Action Center & Overview (mixin)."""

import pygame
from game.config import COLOR_TEXT_MUTED, COLOR_TEXT_TITLE
from game.systems.village_life.village_alerts import collect_village_alerts
from game.ui.ui_theme import upx


_IDLE_JOBS = ("Unassigned", "Unemployed", "Peasant", None, "")
_SEVERITY_COLORS = {
    "critical": (239, 68, 68),
    "warning": (245, 158, 11),
    "info": (56, 189, 248),
}


class TownHallMixin:
    def _draw_town_hall_tab(
        self,
        surface,
        mx,
        cy,
        villager_manager,
        permit_manager,
        building_manager,
        furniture_manager=None,
        stockpile_manager=None,
        servant_manager=None,
    ):
        """Interactive Town Hall Overview & Action Center.
        Summarizes village health and gives 1-click fixes for homeless families,
        broke households, missing tools, waiting immigrants, and idle workers.
        """
        mouse_pos = pygame.mouse.get_pos()
        self.town_hall_action_btns = []

        title = self.font_title.render("TOWN HALL — VILLAGE ACTION CENTER", True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + upx(24), cy - upx(4)))

        # Lord's Rule / Quick Guide Banner (Explains why House, Grant & Job matter)
        guide_rect = pygame.Rect(mx + upx(24), cy + upx(22), self.modal_w - upx(48), upx(46))
        pygame.draw.rect(surface, (20, 32, 54), guide_rect, border_radius=upx(7))
        pygame.draw.rect(surface, (56, 189, 248), guide_rect, width=1, border_radius=upx(7))
        g1 = self.font_badge.render(
            "Lord's Guide: Settlers arrive with 0 coins and no shelter. Give them a Housing Deed + starter coins (Grant) so they can buy food & tools,",
            True, (191, 219, 254),
        )
        g2 = self.font_badge.render(
            "then assign Jobs (in Jobs tab) so they harvest crops, craft goods, pay Market fees, and return Taxes to your Treasury.",
            True, COLOR_TEXT_MUTED,
        )
        surface.blit(g1, (guide_rect.x + upx(12), guide_rect.y + upx(7)))
        surface.blit(g2, (guide_rect.x + upx(12), guide_rect.y + upx(25)))

        # Summary KPI Strip
        families = getattr(villager_manager, "families", []) if villager_manager else []
        all_vils = villager_manager.get_all_villagers() if villager_manager else []
        living_vils = [v for v in all_vils if getattr(v, "is_alive", True)]
        homeless_cnt = sum(1 for f in families if f.living_member_count > 0 and not getattr(f, "assigned_permit_id", None))
        idle_cnt = sum(1 for v in living_vils if getattr(v, "job", "") in _IDLE_JOBS)

        alerts = collect_village_alerts(
            villager_manager=villager_manager,
            permit_manager=permit_manager,
            building_manager=building_manager,
            furniture_manager=furniture_manager,
            stockpile_manager=stockpile_manager,
            servant_manager=servant_manager,
        )

        kpi_y = guide_rect.bottom + upx(10)
        kpi_h = upx(36)
        kpi_gap = upx(10)
        kpi_w = (self.modal_w - upx(48) - 3 * kpi_gap) // 4
        kpis = [
            ("Settlers", f"{len(living_vils)} ({len(families)} Families)", (56, 189, 248)),
            ("Homeless Lots", f"{homeless_cnt} Families", (245, 158, 11) if homeless_cnt > 0 else (34, 197, 94)),
            ("Idle Workers", f"{idle_cnt} Unassigned", (245, 158, 11) if idle_cnt > 0 else (34, 197, 94)),
            ("Open Alerts", f"{len(alerts)} Issue(s)", (239, 68, 68) if alerts else (34, 197, 94)),
        ]
        for idx, (k_lbl, k_val, k_col) in enumerate(kpis):
            kx = mx + upx(24) + idx * (kpi_w + kpi_gap)
            k_rect = pygame.Rect(kx, kpi_y, kpi_w, kpi_h)
            pygame.draw.rect(surface, (24, 34, 52), k_rect, border_radius=upx(6))
            pygame.draw.rect(surface, (51, 65, 85), k_rect, width=1, border_radius=upx(6))
            lbl_s = self.font_badge.render(k_lbl, True, COLOR_TEXT_MUTED)
            val_s = self.font_sub.render(k_val, True, k_col)
            surface.blit(lbl_s, (k_rect.x + upx(10), k_rect.y + upx(4)))
            surface.blit(val_s, (k_rect.x + upx(10), k_rect.y + upx(16)))

        # Urgent Action Checklist
        list_y = kpi_y + kpi_h + upx(12)
        sec_hdr = self.font_sub.render("Actionable Checklist (Click any button to resolve):", True, COLOR_TEXT_TITLE)
        surface.blit(sec_hdr, (mx + upx(24), list_y))

        vp_y = list_y + upx(24)
        bottom = (surface.get_height() + self.modal_h) // 2 - upx(14)
        self.town_hall_viewport_rect = pygame.Rect(mx + upx(16), vp_y, self.modal_w - upx(32), max(0, bottom - vp_y))

        card_h = upx(46)
        card_gap = upx(6)
        content_h = len(alerts) * (card_h + card_gap)
        self.town_hall_max_scroll = max(0, content_h - self.town_hall_viewport_rect.height)
        self.town_hall_scroll_y = max(0, min(getattr(self, "town_hall_scroll_y", 0), self.town_hall_max_scroll))

        old_clip = surface.get_clip()
        surface.set_clip(self.town_hall_viewport_rect)

        if not alerts:
            ok_card = pygame.Rect(mx + upx(24), vp_y + upx(4), self.modal_w - upx(48), upx(64))
            pygame.draw.rect(surface, (20, 48, 36), ok_card, border_radius=upx(8))
            pygame.draw.rect(surface, (34, 197, 94), ok_card, width=1, border_radius=upx(8))
            t1 = self.font_sub.render("All Clear — Village Running Smoothly!", True, (74, 222, 128))
            t2 = self.font_body.render(
                "Every household has shelter, funds, food, and tools. Use the Bottom Dock [B/Z/P] to expand your settlement.",
                True, (203, 213, 225),
            )
            surface.blit(t1, (ok_card.x + upx(16), ok_card.y + upx(12)))
            surface.blit(t2, (ok_card.x + upx(16), ok_card.y + upx(36)))
        else:
            y_cur = vp_y - self.town_hall_scroll_y
            for alert in alerts:
                card = pygame.Rect(mx + upx(24), y_cur, self.modal_w - upx(48), card_h)
                pygame.draw.rect(surface, (24, 34, 52), card, border_radius=upx(7))
                dot_col = _SEVERITY_COLORS.get(alert["severity"], (148, 163, 184))
                pygame.draw.rect(surface, (51, 65, 85), card, width=1, border_radius=upx(7))
                pygame.draw.circle(surface, dot_col, (card.x + upx(18), card.centery), upx(5))

                t_surf = self.font_sub.render(alert["title"], True, (241, 245, 249))
                h_surf = self.font_badge.render(alert["hint"], True, COLOR_TEXT_MUTED)
                surface.blit(t_surf, (card.x + upx(34), card.y + upx(6)))
                surface.blit(h_surf, (card.x + upx(34), card.y + upx(25)))

                btn_w = upx(118)
                btn_h = upx(28)
                btn_rect = pygame.Rect(card.right - btn_w - upx(12), card.centery - btn_h // 2, btn_w, btn_h)
                self.town_hall_action_btns.append((btn_rect, alert))
                b_hov = btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (37, 99, 235) if b_hov else (30, 58, 138), btn_rect, border_radius=upx(5))
                pygame.draw.rect(surface, (96, 165, 250), btn_rect, width=1, border_radius=upx(5))
                b_lbl = self.font_badge.render(alert["action_label"], True, (255, 255, 255))
                surface.blit(b_lbl, b_lbl.get_rect(center=btn_rect.center))

                y_cur += card_h + card_gap

        surface.set_clip(old_clip)

        if self.town_hall_max_scroll > 0:
            track = pygame.Rect(self.town_hall_viewport_rect.right - upx(5), self.town_hall_viewport_rect.y, 3, self.town_hall_viewport_rect.height)
            pygame.draw.rect(surface, (51, 65, 85), track, border_radius=2)
            thumb_h = max(upx(24), int(track.height * self.town_hall_viewport_rect.height / content_h))
            thumb_y = track.y + int((track.height - thumb_h) * self.town_hall_scroll_y / self.town_hall_max_scroll)
            pygame.draw.rect(surface, (96, 165, 250), (track.x, thumb_y, track.width, thumb_h), border_radius=2)
