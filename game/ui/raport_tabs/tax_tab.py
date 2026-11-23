"""RaportUI tab view — extracted from ui_raport.py (mixin)."""

import pygame
import math
from game.config import COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, COLOR_TEXT_TITLE
from game.data.config import CHURCH_TAX_HAPPINESS_TIERS_COPPER
from game.systems.economy.production_distribution import ProductionDistributionSystem
from game.systems.economy.wealth_system import VillageWealthSystem


class TaxMixin:
    def _draw_tax_tab(self, surface, mx, cy, villager_manager, permit_manager, furniture_manager=None, production_system=None, resources=None, building_manager=None, stockpile_manager=None, day_cycle=None):
        """Tax System UI, Church Tithes & Village Wealth Distribution (AGENT 2)"""
        ps = production_system or ProductionDistributionSystem.get_instance()
        mouse_pos = pygame.mouse.get_pos()

        # Title
        title = self.font_title.render("VILLAGE TAXATION & ROYAL TITHES", True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + 24, cy - 4))

        # 1. Configurable Church Tax (Daily Tithe per Household)
        church_card = pygame.Rect(mx + 24, cy + 22, self.modal_w - 48, 102)
        pygame.draw.rect(surface, (30, 27, 46), church_card, border_radius=6)
        pygame.draw.rect(surface, (168, 85, 247), church_card, width=1, border_radius=6)

        surface.blit(self.font_sub.render("⛪ Church Tax (Daily Tithe per Household):", True, (216, 180, 254)), (church_card.x + 14, church_card.y + 8))
        surface.blit(self.font_body.render("Daily household tithe during prayer; OFF gives everyone +10 Happiness.", True, COLOR_TEXT_MUTED), (church_card.x + 14, church_card.y + 30))

        from game.systems.village_life.church_system import ChurchSystem
        if not hasattr(self, "church_tax") or not isinstance(self.church_tax, dict):
            self.church_tax = ChurchSystem.get_tax_settings()

        self.church_tax_enabled_rect = pygame.Rect(church_card.right - 76, church_card.y + 7, 62, 22)
        church_enabled = ChurchSystem.is_tax_enabled()
        pygame.draw.rect(surface, (5, 150, 105) if church_enabled else (71, 85, 105), self.church_tax_enabled_rect, border_radius=4)
        surface.blit(self.font_badge.render("ON" if church_enabled else "OFF", True, (255, 255, 255)),
                     (self.church_tax_enabled_rect.centerx - 10, self.church_tax_enabled_rect.y + 5))

        # Denomination controls: Gold, Silver, Copper (typable inputs)
        tx_ctrl_x = church_card.x + 14
        btn_ty = church_card.y + 58
        denom_specs = (
            ("Gold", (250, 204, 21), tx_ctrl_x, 0),
            ("Silver", (203, 213, 225), tx_ctrl_x + 96, 0),
            ("Copper", (217, 119, 6), tx_ctrl_x + 196, 1),
        )
        for denom, col, dx, default_val in denom_specs:
            surface.blit(self.font_badge.render(f"{denom}:", True, col), (dx, btn_ty + 3))
            d_key = ("num", "church_tax", denom)
            d_rect = pygame.Rect(dx + 44, btn_ty - 2, 40, 26)
            self.num_fields[d_key] = {"rect": d_rect, "kind": "church_tax",
                                      "payload": denom, "min": 0, "max": 9999}
            self._draw_num_input(surface, d_key, d_rect,
                                 self.church_tax.get(denom, default_val))
        church_tier_text = "Church happiness: " + " | ".join(
            f"{lower}–{upper if upper is not None else '∞'}c −{abs(penalty)}"
            for lower, upper, penalty in CHURCH_TAX_HAPPINESS_TIERS_COPPER
        ) + " | OFF +10"
        surface.blit(self.font_badge.render(church_tier_text, True, (196, 181, 253)),
                     (church_card.x + 14, church_card.y + 84))

        # 2. Village Wealth Section (AGENT 2)
        wealth_data = VillageWealthSystem.calculate_village_wealth(
            resources=resources,
            villager_manager=villager_manager,
            furniture_manager=furniture_manager,
            building_manager=building_manager,
            stockpile_manager=stockpile_manager
        )
        self.cached_wealth_data = wealth_data

        from game.systems.economy.taxation_system import TaxationSystem
        from game.systems.economy.currency import from_copper
        from game.data.config import SOCAGE_TAX_INTERVAL_DAYS, SOCAGE_TAX_HAPPINESS_TIERS
        current_day = int(getattr(day_cycle, "day_number", 1)) if day_cycle else 1
        next_day = TaxationSystem.next_collection_day(current_day, villager_manager)
        tax_report = TaxationSystem.get_socage_tax_report(current_day)
        collected = from_copper(tax_report["collected_copper"])
        socage_card = pygame.Rect(mx + 24, cy + 130, self.modal_w - 48, 90)
        pygame.draw.rect(surface, (24, 34, 52), socage_card, border_radius=6)
        pygame.draw.rect(surface, (217, 119, 6), socage_card, width=1, border_radius=6)
        surface.blit(self.font_sub.render("Socage Tax — household coin tax", True, (251, 191, 36)),
                     (socage_card.x + 14, socage_card.y + 8))
        if not TaxationSystem.is_socage_enabled():
            next_label = "Collection paused while Socage Tax is OFF"
        else:
            next_label = (f"Next collection: Day {next_day} (today)" if next_day == current_day
                          else f"Next collection: Day {next_day}")
        surface.blit(self.font_body.render(
            f"{next_label} · every {SOCAGE_TAX_INTERVAL_DAYS} days · based on household chest coins.",
            True, COLOR_TEXT_MUTED), (socage_card.x + 14, socage_card.y + 30))
        self.socage_tax_enabled_rect = pygame.Rect(socage_card.right - 76, socage_card.y + 7, 62, 22)
        socage_enabled = TaxationSystem.is_socage_enabled()
        pygame.draw.rect(surface, (5, 150, 105) if socage_enabled else (71, 85, 105), self.socage_tax_enabled_rect, border_radius=4)
        socage_toggle = self.font_badge.render("ON" if socage_enabled else "OFF", True, (255, 255, 255))
        surface.blit(socage_toggle, (self.socage_tax_enabled_rect.centerx - socage_toggle.get_width() // 2,
                                     self.socage_tax_enabled_rect.centery - socage_toggle.get_height() // 2))
        rate_x = socage_card.right - 306
        self.socage_tax_input_rect = pygame.Rect(rate_x + 48, socage_card.y + 48, 140, 22)
        pygame.draw.rect(surface, (15, 23, 42), self.socage_tax_input_rect, border_radius=3)
        input_border = (56, 189, 248) if self.socage_tax_input_active else (71, 85, 105)
        pygame.draw.rect(surface, input_border, self.socage_tax_input_rect, width=1, border_radius=3)
        rate_value = (self.socage_tax_input_text if self.socage_tax_input_active
                      else str(TaxationSystem.get_socage_percent()))
        rate_text = self.font_sub.render(f"{rate_value}%", True, (250, 204, 21))
        surface.blit(rate_text, (self.socage_tax_input_rect.centerx - rate_text.get_width() // 2,
                                 self.socage_tax_input_rect.centery - rate_text.get_height() // 2))
        surface.blit(self.font_badge.render("Rate", True, COLOR_TEXT_MUTED), (rate_x, socage_card.y + 53))
        collected_amount = (
            f"{collected['Gold']}g {collected['Silver']}s {collected['Copper']}c"
        )
        collected_label = (
            f"Collected (Days {tax_report['start_day']}–{tax_report['end_day']}, "
            f"through {tax_report['through_day']}): {collected_amount}"
        )
        available_label_width = rate_x - socage_card.x - 24
        collected_text = self.font_badge.render(collected_label, True, COLOR_TEXT_MAIN)
        if collected_text.get_width() > available_label_width:
            collected_text = self.font_badge.render(
                f"Collected this period: {collected_amount}", True, COLOR_TEXT_MAIN,
            )
        surface.blit(collected_text, (socage_card.x + 14, socage_card.y + 53))
        socage_tier_text = "Happiness: " + " | ".join(
            f"{lower}–{upper if upper is not None else '∞'}% −{abs(penalty)}"
            for lower, upper, penalty in SOCAGE_TAX_HAPPINESS_TIERS
        )
        surface.blit(self.font_badge.render(socage_tier_text, True, (253, 186, 116)),
                     (socage_card.x + 14, socage_card.y + 73))
        wealth_card = pygame.Rect(mx + 24, cy + 228, self.modal_w - 48, 52)
        pygame.draw.rect(surface, (24, 34, 52), wealth_card, border_radius=6)
        pygame.draw.rect(surface, (234, 179, 8), wealth_card, width=1, border_radius=6)

        tw = wealth_data["total_wallet"]
        tot_c = wealth_data["total_wealth_copper"]

        surface.blit(self.font_sub.render("💰 Village Wealth & Coin Distribution:", True, (250, 204, 21)), (wealth_card.x + 14, wealth_card.y + 8))
        wealth_sub = f"Total Village Wealth: {tw['Gold']} Gold, {tw['Silver']} Silver, {tw['Copper']} Copper  (Total: {tot_c}c)"
        surface.blit(self.font_body.render(wealth_sub, True, (241, 245, 249)), (wealth_card.x + 14, wealth_card.y + 28))

        # 'Check Wealth Detail' Button
        self.check_wealth_detail_btn_rect = pygame.Rect(wealth_card.right - 170, wealth_card.y + 11, 156, 30)
        wd_hov = self.check_wealth_detail_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (217, 119, 6) if wd_hov else (180, 83, 9), self.check_wealth_detail_btn_rect, border_radius=5)
        pygame.draw.rect(surface, (251, 191, 36), self.check_wealth_detail_btn_rect, width=1, border_radius=5)
        wd_txt = self.font_badge.render("Check Wealth Detail", True, (255, 255, 255))
        surface.blit(wd_txt, (self.check_wealth_detail_btn_rect.centerx - wd_txt.get_width() // 2, self.check_wealth_detail_btn_rect.centery - wd_txt.get_height() // 2))

        # Active tax settings replace the old inactive WIP policy placeholders.

        # 5. Wealth Detail & Pie Chart Dialog Modal (if active)
        if self.show_wealth_detail_dialog:
            self._draw_wealth_pie_chart_dialog(surface, mx, cy, wealth_data, mouse_pos)

    def _draw_wealth_pie_chart_dialog(self, surface, mx, cy, wealth_data, mouse_pos):
        """Displays procedural Pie Chart & Breakdown Dialog for Village Wealth (AGENT 2)"""
        sw, sh = surface.get_size()

        # Modal backdrop
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        dlg_w = 640
        dlg_h = 360
        dlg_x = (sw - dlg_w) // 2
        dlg_y = (sh - dlg_h) // 2

        pygame.draw.rect(surface, (15, 23, 42), (dlg_x, dlg_y, dlg_w, dlg_h), border_radius=10)
        pygame.draw.rect(surface, (234, 179, 8), (dlg_x, dlg_y, dlg_w, dlg_h), width=2, border_radius=10)

        # Header
        surface.blit(self.font_title.render("Village Wealth Distribution", True, (250, 204, 21)), (dlg_x + 24, dlg_y + 16))
        surface.blit(self.font_body.render("Proportional pie chart of circulating coin wealth across Landlord and Households:", True, COLOR_TEXT_MUTED), (dlg_x + 24, dlg_y + 42))

        # Close [X]
        self.close_wealth_dlg_btn_rect = pygame.Rect(dlg_x + dlg_w - 36, dlg_y + 14, 22, 22)
        pygame.draw.rect(surface, (51, 65, 85), self.close_wealth_dlg_btn_rect, border_radius=4)
        surface.blit(self.font_badge.render("X", True, (255, 255, 255)), (self.close_wealth_dlg_btn_rect.x + 6, self.close_wealth_dlg_btn_rect.y + 3))

        # -------------------------------------------------------------
        # LEFT: PROCEDURAL PIE CHART (Pure trigonometry, KaTeX / math safe)
        # -------------------------------------------------------------
        chart_cx = dlg_x + 130
        chart_cy = dlg_y + 185
        chart_radius = 80

        # Collect entities: Landlord + all households
        entities = [wealth_data["landlord"]] + wealth_data["households"]
        total_copper = wealth_data["total_wealth_copper"]

        if total_copper <= 0:
            pygame.draw.circle(surface, (51, 65, 85), (chart_cx, chart_cy), chart_radius)
            pygame.draw.circle(surface, (100, 116, 139), (chart_cx, chart_cy), chart_radius, 2)
            n_txt = self.font_badge.render("No Coins", True, (148, 163, 184))
            surface.blit(n_txt, (chart_cx - n_txt.get_width() // 2, chart_cy - n_txt.get_height() // 2))
        else:
            current_angle = -math.pi / 2.0  # Start from top (12 o'clock)
            for ent in entities:
                pct = ent["percentage"]
                if pct <= 0.0:
                    continue
                slice_angle = (pct / 100.0) * (2.0 * math.pi)
                end_angle = current_angle + slice_angle

                # Draw polygon slice
                num_steps = max(6, int(math.ceil(slice_angle * 16)))
                points = [(chart_cx, chart_cy)]
                for st in range(num_steps + 1):
                    a = current_angle + (slice_angle * (st / num_steps))
                    px = chart_cx + chart_radius * math.cos(a)
                    py = chart_cy + chart_radius * math.sin(a)
                    points.append((px, py))

                if len(points) >= 3:
                    pygame.draw.polygon(surface, ent["color"], points)
                    pygame.draw.polygon(surface, (15, 23, 42), points, 1)

                current_angle = end_angle

            # Outer border ring
            pygame.draw.circle(surface, (71, 85, 105), (chart_cx, chart_cy), chart_radius, 2)

        # -------------------------------------------------------------
        # RIGHT: DETAILED BREAKDOWN & LEGEND
        # -------------------------------------------------------------
        leg_x = dlg_x + 250
        leg_y = dlg_y + 75

        for ent in entities[:6]:
            w_box = pygame.Rect(leg_x, leg_y, dlg_w - 275, 40)
            pygame.draw.rect(surface, (24, 34, 52), w_box, border_radius=5)
            pygame.draw.rect(surface, (51, 65, 85), w_box, width=1, border_radius=5)

            # Color Swatch
            swatch_r = pygame.Rect(w_box.x + 10, w_box.y + 12, 16, 16)
            pygame.draw.rect(surface, ent["color"], swatch_r, border_radius=3)

            # Name & Percentage
            surface.blit(self.font_sub.render(ent["name"], True, (241, 245, 249)), (w_box.x + 34, w_box.y + 6))
            pct_badge = f"{ent['percentage']}%"
            surface.blit(self.font_sub.render(pct_badge, True, (250, 204, 21)), (w_box.right - 55, w_box.y + 6))

            # Absolute Wealth
            w = ent["wallet"]
            c_val = ent["wealth_copper"]
            bal_str = f"{w['Gold']}g  {w['Silver']}s  {w['Copper']}c   ({c_val}c)"
            surface.blit(self.font_body.render(bal_str, True, COLOR_TEXT_MUTED), (w_box.x + 34, w_box.y + 22))

            leg_y += 44

        # Footer Summary
        tw = wealth_data["total_wallet"]
        f_txt = f"Total Village Coin Pool: {tw['Gold']} Gold, {tw['Silver']} Silver, {tw['Copper']} Copper ({total_copper}c)"
        surface.blit(self.font_badge.render(f_txt, True, (250, 204, 21)), (dlg_x + 24, dlg_y + dlg_h - 26))

