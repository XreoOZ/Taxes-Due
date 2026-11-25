"""
Right-Side In-Game Notice Board HUD (Village Alerts & Needs Indicators).
Displays real-time warnings when households run out of coins, lack a house,
miss tools, lack food/water, or when immigrants wait at the Notice Board.
Every alert is clickable to jump directly to the fix.
"""

import pygame
from game.systems.village_life.village_alerts import collect_village_alerts, group_village_alerts
from game.ui.ui_theme import ui_font, upx


_SEVERITY_COLORS = {
    "critical": (239, 68, 68),
    "warning": (245, 158, 11),
    "info": (56, 189, 248),
}


class VillageAlertsHUD:
    def __init__(self, width=230, max_visible=5):
        self.base_width = width
        self.max_visible = max_visible
        self.collapsed = False
        self.alerts = []
        self.grouped_alerts = []
        self.toggle_btn_rect = pygame.Rect(0, 0, 0, 0)
        self.more_btn_rect = pygame.Rect(0, 0, 0, 0)
        self.alert_row_rects = []  # [(rect, alert_dict), ...]
        self.panel_rect = pygame.Rect(0, 0, 0, 0)

    def refresh(
        self,
        villager_manager=None,
        permit_manager=None,
        building_manager=None,
        furniture_manager=None,
        stockpile_manager=None,
        servant_manager=None,
    ):
        self.alerts = collect_village_alerts(
            villager_manager=villager_manager,
            permit_manager=permit_manager,
            building_manager=building_manager,
            furniture_manager=furniture_manager,
            stockpile_manager=stockpile_manager,
            servant_manager=servant_manager,
        )
        self.grouped_alerts = group_village_alerts(self.alerts)
        return self.alerts

    def handle_event(self, event):
        """Handle mouse clicks on the Notice Board HUD. Returns an action dict or None."""
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None
        m_pos = event.pos

        if self.toggle_btn_rect.collidepoint(m_pos):
            self.collapsed = not self.collapsed
            return {"action": "TOGGLE_COLLAPSE"}

        if not self.collapsed:
            for rect, alert in self.alert_row_rects:
                if rect.collidepoint(m_pos):
                    return {
                        "action": alert["action_type"],
                        "target_id": alert.get("target_id"),
                        "alert": alert,
                    }
            if self.more_btn_rect.width > 0 and self.more_btn_rect.collidepoint(m_pos):
                return {"action": "OPEN_TOWN_HALL", "target_id": None}

        # Consume click inside panel body so it doesn't click through to map
        if self.panel_rect.collidepoint(m_pos):
            return {"action": "HANDLED"}
        return None

    def draw(self, surface, right_x, top_y):
        """Render the collapsible Notice Board panel right-aligned at (right_x, top_y)."""
        panel_w = upx(self.base_width)
        header_h = upx(26)
        row_h = upx(22)
        pad = upx(6)
        m_pos = pygame.mouse.get_pos()

        total_count = len(self.alerts)
        grouped = self.grouped_alerts or group_village_alerts(self.alerts)
        visible_alerts = grouped[:self.max_visible]
        overflow = max(0, len(grouped) - len(visible_alerts))

        if self.collapsed:
            panel_h = header_h
        elif total_count == 0:
            panel_h = header_h + row_h + pad
        else:
            footer_h = upx(20) if overflow > 0 else 0
            panel_h = header_h + pad + len(visible_alerts) * (row_h + upx(2)) + footer_h + pad // 2

        panel_x = right_x - panel_w
        panel_y = top_y
        self.panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)

        # Panel background
        bg_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        pygame.draw.rect(bg_surf, (15, 23, 42, 225), (0, 0, panel_w, panel_h), border_radius=upx(8))
        has_critical = any(a["severity"] == "critical" for a in self.alerts)
        border_col = (239, 68, 68) if has_critical else ((245, 158, 11) if total_count > 0 else (51, 65, 85))
        pygame.draw.rect(bg_surf, border_col, (0, 0, panel_w, panel_h), width=1, border_radius=upx(8))
        surface.blit(bg_surf, (panel_x, panel_y))

        # Header bar
        hdr_rect = pygame.Rect(panel_x, panel_y, panel_w, header_h)
        hdr_title = f"Notice Board ({total_count})" if total_count > 0 else "Notice Board (OK)"
        hdr_col = (248, 113, 113) if has_critical else ((250, 204, 21) if total_count > 0 else (74, 222, 128))
        title_surf = ui_font(11, bold=True).render(hdr_title, True, hdr_col)
        surface.blit(title_surf, (hdr_rect.x + upx(10), hdr_rect.centery - title_surf.get_height() // 2))

        # Collapse toggle button [- / +]
        btn_sz = upx(18)
        self.toggle_btn_rect = pygame.Rect(hdr_rect.right - btn_sz - upx(6), hdr_rect.centery - btn_sz // 2, btn_sz, btn_sz)
        t_hov = self.toggle_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (51, 65, 85) if t_hov else (30, 41, 59), self.toggle_btn_rect, border_radius=upx(4))
        t_sym = ui_font(10, bold=True).render("+" if self.collapsed else "-", True, (226, 232, 240))
        surface.blit(t_sym, t_sym.get_rect(center=self.toggle_btn_rect.center))

        self.alert_row_rects = []
        self.more_btn_rect = pygame.Rect(0, 0, 0, 0)
        if self.collapsed:
            return

        cur_y = panel_y + header_h + upx(2)
        if total_count == 0:
            ok_surf = ui_font(10).render("All settlers & village OK", True, (148, 163, 184))
            surface.blit(ok_surf, (panel_x + upx(10), cur_y + upx(3)))
            return

        hovered_alert = None
        hovered_rect = None
        for alert in visible_alerts:
            row_rect = pygame.Rect(panel_x + upx(5), cur_y, panel_w - upx(10), row_h)
            self.alert_row_rects.append((row_rect, alert))
            is_hov = row_rect.collidepoint(m_pos)
            if is_hov:
                hovered_alert = alert
                hovered_rect = row_rect

            row_bg = (30, 41, 59) if is_hov else (20, 29, 48)
            pygame.draw.rect(surface, row_bg, row_rect, border_radius=upx(4))
            dot_col = _SEVERITY_COLORS.get(alert["severity"], (148, 163, 184))
            pygame.draw.circle(surface, dot_col, (row_rect.x + upx(8), row_rect.centery), upx(3))

            title_txt = alert["title"]
            max_chars = 28
            if len(title_txt) > max_chars:
                title_txt = title_txt[:max_chars - 2] + ".."
            txt_surf = ui_font(10, bold=is_hov).render(title_txt, True, (255, 255, 255) if is_hov else (226, 232, 240))
            surface.blit(txt_surf, (row_rect.x + upx(16), row_rect.centery - txt_surf.get_height() // 2))
            arrow_s = ui_font(10, bold=True).render(">", True, (96, 165, 250) if is_hov else (100, 116, 139))
            surface.blit(arrow_s, (row_rect.right - arrow_s.get_width() - upx(6), row_rect.centery - arrow_s.get_height() // 2))
            cur_y += row_h + upx(2)

        if overflow > 0:
            self.more_btn_rect = pygame.Rect(panel_x + upx(5), cur_y, panel_w - upx(10), upx(18))
            m_hov = self.more_btn_rect.collidepoint(m_pos)
            more_surf = ui_font(9, bold=True).render(f"+ {overflow} more — Open Town Hall", True, (96, 165, 250) if m_hov else (148, 163, 184))
            surface.blit(more_surf, more_surf.get_rect(center=self.more_btn_rect.center))

        # Floating hint tooltip to the left of the hovered row
        if hovered_alert and hovered_rect:
            hint_txt = f"{hovered_alert['hint']} (Click: {hovered_alert['action_label']})"
            tip_surf = ui_font(10).render(hint_txt, True, (255, 255, 255))
            tip_w = tip_surf.get_width() + upx(14)
            tip_h = tip_surf.get_height() + upx(8)
            tip_x = max(upx(8), panel_x - tip_w - upx(8))
            tip_y = max(upx(8), hovered_rect.centery - tip_h // 2)
            tip_bg = pygame.Surface((tip_w, tip_h), pygame.SRCALPHA)
            pygame.draw.rect(tip_bg, (15, 23, 42, 245), (0, 0, tip_w, tip_h), border_radius=upx(5))
            pygame.draw.rect(tip_bg, _SEVERITY_COLORS.get(hovered_alert["severity"], (96, 165, 250)), (0, 0, tip_w, tip_h), width=1, border_radius=upx(5))
            surface.blit(tip_bg, (tip_x, tip_y))
            surface.blit(tip_surf, (tip_x + upx(7), tip_y + upx(4)))
