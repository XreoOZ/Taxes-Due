"""RaportUI tab view — extracted from ui_raport.py (mixin)."""

import pygame
from game.config import COLOR_TEXT_MUTED, COLOR_TEXT_TITLE, DEDICATED_JOBS
from game.systems.economy.household_inventory import canonical_item_name, get_household_possessions, sort_possession_items
from game.systems.economy.production_distribution import ProductionDistributionSystem
from game.ui.item_icons import draw_item_icon
from game.ui.raport_tabs.common import GRANTABLE_ITEMS
from game.ui.ui_theme import ui_font, upx


class VillagersMixin:
    def _draw_villagers_tab(self, surface, mx, cy, villager_manager, permit_manager, building_manager, furniture_manager=None, stockpile_manager=None, resources=None, servant_manager=None, production_system=None, day_cycle=None):
        if villager_manager:
            villager_manager.ensure_unique_family_ids()
        mouse_pos = pygame.mouse.get_pos()
        families = villager_manager.families if villager_manager else []
        total_villagers = len(villager_manager.get_all_villagers()) if villager_manager else 0

        # =============================================================
        # VIEW 1: Family Clan Directory (List of All Families)
        # =============================================================
        if self.selected_family_id is None:
            title = self.font_sub.render(f" Town Census & Family Directory ({total_villagers} Settlers | {len(families)} Families)", True, COLOR_TEXT_TITLE)
            surface.blit(title, (mx + upx(24), cy))

            # Button: [+ Add Family (Cheat)] — only visible when cheats unlocked via ESC menu
            if self.cheats_active:
                btn_w = upx(175)
                btn_h = upx(30)
                self.add_family_cheat_btn_rect = pygame.Rect(mx + self.modal_w - btn_w - upx(24), cy - upx(4), btn_w, btn_h)
                btn_hover = self.add_family_cheat_btn_rect.collidepoint(mouse_pos)
                btn_col = (126, 34, 206) if btn_hover else (107, 33, 168)

                pygame.draw.rect(surface, btn_col, self.add_family_cheat_btn_rect, border_radius=upx(6))
                pygame.draw.rect(surface, (192, 132, 252), self.add_family_cheat_btn_rect, width=1, border_radius=upx(6))
                b_txt = self.font_badge.render("+ Add Family (Cheat)", True, (255, 255, 255))
                surface.blit(b_txt, (self.add_family_cheat_btn_rect.centerx - b_txt.get_width() // 2, self.add_family_cheat_btn_rect.centery - b_txt.get_height() // 2))
            else:
                self.add_family_cheat_btn_rect = None

            sub = self.font_body.render("Settlers migrate in family clans (1–3 generations). Landlord grants Housing Deeds to each family:", True, COLOR_TEXT_MUTED)
            surface.blit(sub, (mx + upx(24), cy + upx(22)))

            y_cur = cy + upx(48)
            self.view_family_btn_rects = []
            self.family_possession_btn_rects = []
            self.family_deed_btn_rects = []

            if not families:
                empty_card = pygame.Rect(mx + upx(24), y_cur, self.modal_w - upx(48), upx(80))
                pygame.draw.rect(surface, (24, 34, 52), empty_card, border_radius=upx(8))
                pygame.draw.rect(surface, (51, 65, 85), empty_card, width=1, border_radius=upx(8))

                msg1 = self.font_body.render("• No settler families residing on your estate yet.", True, COLOR_TEXT_MUTED)
                if self.cheats_active:
                    msg2 = self.font_body.render("Click [+ Add Family (Cheat)] above to welcome a new immigrant family to your land!", True, (56, 189, 248))
                else:
                    msg2 = self.font_body.render("Families arrive via the Notice Board Immigrant tab, or unlock cheats via ESC menu.", True, COLOR_TEXT_MUTED)
                surface.blit(msg1, (empty_card.x + upx(20), empty_card.y + upx(18)))
                surface.blit(msg2, (empty_card.x + upx(20), empty_card.y + upx(42)))

            else:
                card_h = upx(78)
                for fam in families:
                    card_rect = pygame.Rect(mx + upx(24), y_cur, self.modal_w - upx(48), card_h)
                    pygame.draw.rect(surface, (24, 34, 52), card_rect, border_radius=upx(8))
                    pygame.draw.rect(surface, (51, 65, 85), card_rect, width=1, border_radius=upx(8))

                    # Family Coat of Arms / Emblem Circle
                    emblem_col = (34, 197, 94) if fam.assigned_permit_id else (245, 158, 11)
                    pygame.draw.circle(surface, emblem_col, (card_rect.x + upx(24), card_rect.y + card_h // 2), upx(12))
                    pygame.draw.circle(surface, (15, 23, 42), (card_rect.x + upx(24), card_rect.y + card_h // 2), upx(12), 2)

                    # Family Title & Living Population
                    deceased_count = fam.member_count - fam.living_member_count
                    pop_label = f"{fam.living_member_count} Living" if deceased_count == 0 else f"{fam.living_member_count} Living, {deceased_count} Deceased"
                    fam_name = self.font_sub.render(f"The {fam.surname} Family  ({pop_label})", True, (241, 245, 249))
                    surface.blit(fam_name, (card_rect.x + upx(46), card_rect.y + upx(8)))

                    # Generation badge
                    gen_txt = self.font_badge.render(f"Generations: {fam.get_generation_label()}", True, (56, 189, 248))
                    surface.blit(gen_txt, (card_rect.x + upx(46) + fam_name.get_width() + upx(12), card_rect.y + upx(10)))

                    # Primary Needs Indicator (Agent 1: Food & Water Stocks + Daily Fulfillment)
                    food_stk = fam.get_food_stock(furniture_manager, stockpile_manager)
                    water_stk = fam.get_water_stock(furniture_manager, stockpile_manager)
                    food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
                    needs_x = card_rect.right - upx(350)
                    needs_y = card_rect.y + upx(18)

                    # Food Badge: Displays actual storage stock + daily fulfillment count
                    food_col = (34, 197, 94) if (food_ok >= living_tot and living_tot > 0) else ((245, 158, 11) if (food_ok > 0 or food_stk > 0) else (239, 68, 68))
                    food_badge = pygame.Rect(needs_x, needs_y, upx(105), upx(22))
                    pygame.draw.rect(surface, (15, 23, 42), food_badge, border_radius=upx(4))
                    pygame.draw.rect(surface, food_col, food_badge, width=1, border_radius=upx(4))
                    f_txt = self.font_badge.render(f"Food: {food_stk} ({food_ok}/{living_tot})", True, food_col)
                    surface.blit(f_txt, (food_badge.centerx - f_txt.get_width() // 2, food_badge.centery - f_txt.get_height() // 2))

                    # Water Badge: Displays actual storage stock + daily fulfillment count
                    water_col = (56, 189, 248) if (water_ok >= living_tot and living_tot > 0) else ((245, 158, 11) if (water_ok > 0 or water_stk > 0) else (239, 68, 68))
                    water_badge = pygame.Rect(needs_x + upx(112), needs_y, upx(105), upx(22))
                    pygame.draw.rect(surface, (15, 23, 42), water_badge, border_radius=upx(4))
                    pygame.draw.rect(surface, water_col, water_badge, width=1, border_radius=upx(4))
                    w_txt = self.font_badge.render(f"Water: {water_stk} ({water_ok}/{living_tot})", True, water_col)
                    surface.blit(w_txt, (water_badge.centerx - w_txt.get_width() // 2, water_badge.centery - w_txt.get_height() // 2))

                    # Assigned Deed Status
                    if fam.assigned_permit_id:
                        p_deed = next((p for p in permit_manager.permits if p.id == fam.assigned_permit_id), None)
                        deed_label = f"Assigned Deed: {p_deed.name}" if p_deed else "Assigned Deed: Active Lot"
                        deed_col = (34, 197, 94)
                    else:
                        deed_label = "Deed: Unassigned (Homeless Immigrants at Town Center)"
                        deed_col = (245, 158, 11)

                    surface.blit(self.font_body.render(deed_label, True, deed_col), (card_rect.x + upx(46), card_rect.y + upx(30)))


                    # Action Button: [👥 View Family]
                    action_y = card_rect.y + upx(50)
                    deed_btn = pygame.Rect(card_rect.right - upx(12) - upx(112), action_y, upx(112), upx(22))
                    self.family_deed_btn_rects.append((fam.id, deed_btn))
                    deed_hover = deed_btn.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (16, 185, 129) if deed_hover else (5, 150, 105), deed_btn, border_radius=upx(5))
                    pygame.draw.rect(surface, (74, 222, 128), deed_btn, width=1, border_radius=upx(5))
                    deed_action = "Change Deed" if fam.assigned_permit_id else "Assign Deed"
                    deed_lbl = self.font_badge.render(deed_action, True, (255, 255, 255))
                    surface.blit(deed_lbl, (deed_btn.centerx - deed_lbl.get_width() // 2, deed_btn.centery - deed_lbl.get_height() // 2))

                    possession_btn = pygame.Rect(deed_btn.x - upx(8) - upx(150), action_y, upx(150), upx(22))
                    self.family_possession_btn_rects.append((fam.id, possession_btn))
                    possession_hover = possession_btn.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (202, 138, 4) if possession_hover else (161, 98, 7), possession_btn, border_radius=upx(5))
                    pygame.draw.rect(surface, (250, 204, 21), possession_btn, width=1, border_radius=upx(5))
                    possession_lbl = self.font_badge.render("Household Possession", True, (255, 255, 255))
                    surface.blit(possession_lbl, (possession_btn.centerx - possession_lbl.get_width() // 2, possession_btn.centery - possession_lbl.get_height() // 2))

                    view_btn = pygame.Rect(possession_btn.x - upx(8) - upx(108), action_y, upx(108), upx(22))
                    self.view_family_btn_rects.append((fam.id, view_btn))
                    v_hover = view_btn.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (37, 99, 235) if v_hover else (30, 58, 138), view_btn, border_radius=upx(6))
                    pygame.draw.rect(surface, (96, 165, 250), view_btn, width=1, border_radius=upx(6))

                    lbl = self.font_badge.render("View Family", True, (255, 255, 255))
                    surface.blit(lbl, (view_btn.centerx - lbl.get_width() // 2, view_btn.centery - lbl.get_height() // 2))

                    y_cur += card_h + upx(8)

        # =============================================================
        # VIEW 2: Detailed Family Roster & Deed Management
        # =============================================================
        else:
            fam = villager_manager.get_family_by_id(self.selected_family_id) if villager_manager else None
            if not fam:
                self.selected_family_id = None
                return

            if self.show_household_possession:
                # ---------------------------------------------------------
                # VIEW 2B: Household Possessions Grid (3x3 with sekat)
                # ---------------------------------------------------------
                self.close_possession_btn_rect = pygame.Rect(mx + upx(24), cy - upx(4), upx(150), upx(28))
                b_hover = self.close_possession_btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (51, 65, 85) if b_hover else (30, 41, 59), self.close_possession_btn_rect, border_radius=upx(6))
                pygame.draw.rect(surface, (96, 165, 250), self.close_possession_btn_rect, width=1, border_radius=upx(6))
                back_lbl = self.font_badge.render("< Back to Roster", True, (255, 255, 255))
                surface.blit(back_lbl, (self.close_possession_btn_rect.centerx - back_lbl.get_width() // 2, self.close_possession_btn_rect.centery - back_lbl.get_height() // 2))

                f_title = self.font_title.render(f"Household Possessions: The {fam.surname} Family", True, (241, 245, 249))
                surface.blit(f_title, (mx + upx(24) + upx(150) + upx(14), cy - upx(4)))

                # Button: [🎁 Grant Item]
                grant_btn_w = upx(140)
                self.open_grant_dialog_btn_rect = pygame.Rect(mx + self.modal_w - upx(24) - grant_btn_w, cy - upx(4), grant_btn_w, upx(28))
                g_hov = self.open_grant_dialog_btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (22, 101, 52) if g_hov else (21, 128, 61), self.open_grant_dialog_btn_rect, border_radius=upx(6))
                pygame.draw.rect(surface, (74, 222, 128), self.open_grant_dialog_btn_rect, width=1, border_radius=upx(6))
                grant_lbl = self.font_badge.render("Grant Item", True, (255, 255, 255))
                surface.blit(grant_lbl, (self.open_grant_dialog_btn_rect.centerx - grant_lbl.get_width() // 2, self.open_grant_dialog_btn_rect.centery - grant_lbl.get_height() // 2))

                # Dynamically retrieve and sort actual household possessions (Single Source of Truth)
                possessions = get_household_possessions(fam, furniture_manager, stockpile_manager, servant_manager)
                items = sort_possession_items(possessions)

                # Pagination parameters
                per_page = 9
                total_items = len(items)
                max_page = max(0, (total_items - 1) // per_page)
                self.possession_page = max(0, min(getattr(self, "possession_page", 0), max_page))
                page_items = items[self.possession_page * per_page : (self.possession_page + 1) * per_page]

                # 3x3 Grid Layout
                grid_x = mx + upx(24)
                grid_y = cy + upx(34)
                grid_w = self.modal_w - upx(48)
                grid_h = upx(240)
                col_w = grid_w / 3.0
                row_h = grid_h / 3.0

                # Grid Background & Outer Border
                grid_rect = pygame.Rect(grid_x, grid_y, grid_w, grid_h)
                pygame.draw.rect(surface, (15, 23, 42), grid_rect, border_radius=upx(8))
                pygame.draw.rect(surface, (51, 65, 85), grid_rect, width=2, border_radius=upx(8))

                if total_items == 0:
                    # Empty state display: No WIP, no placeholders, no fake zero items
                    empty_lbl = self.font_body.render("— Household storage and inventory are currently empty —", True, (148, 163, 184))
                    surface.blit(empty_lbl, (grid_rect.centerx - empty_lbl.get_width() // 2, grid_rect.centery - upx(12)))
                    sub_lbl = self.font_badge.render("Items produced, harvested, granted, or purchased will appear here.", True, (100, 116, 139))
                    surface.blit(sub_lbl, (grid_rect.centerx - sub_lbl.get_width() // 2, grid_rect.centery + upx(12)))
                else:
                    # Draw Cells for possessed items
                    for idx, item in enumerate(page_items):
                        c_col = idx % 3
                        c_row = idx // 3
                        cx_start = int(grid_x + c_col * col_w)
                        cy_start = int(grid_y + c_row * row_h)
                        cell_rect = pygame.Rect(cx_start, cy_start, int(col_w), int(row_h))

                        # Cell hover highlight
                        if cell_rect.collidepoint(mouse_pos):
                            pygame.draw.rect(surface, (30, 41, 59, 120), cell_rect)

                        # [Icon]  [Jumlah]  [Nama item]
                        draw_item_icon(surface, item["name"], cx_start + upx(24), cy_start + int(row_h // 2), size=upx(11))

                        cnt_color = (34, 197, 94)  # Vibrant green for actual possessed items
                        cnt_str = f"x {item['count']}"
                        cnt_surf = self.font_sub.render(cnt_str, True, cnt_color)
                        surface.blit(cnt_surf, (cx_start + upx(44), cy_start + int(row_h // 2) - upx(9)))

                        name_color = (241, 245, 249)
                        name_surf = self.font_body.render(item["name"], True, name_color)
                        surface.blit(name_surf, (cx_start + upx(98), cy_start + int(row_h // 2) - upx(8)))

                    # Divider Lines (Sekat) matching actual content rows
                    num_rows = (len(page_items) + 2) // 3
                    if num_rows >= 2:
                        pygame.draw.line(surface, (51, 65, 85), (grid_x, grid_y + int(row_h)), (grid_x + grid_w, grid_y + int(row_h)), 2)
                    if num_rows >= 3:
                        pygame.draw.line(surface, (51, 65, 85), (grid_x, grid_y + int(2 * row_h)), (grid_x + grid_w, grid_y + int(2 * row_h)), 2)

                    active_h = int(num_rows * row_h)
                    pygame.draw.line(surface, (51, 65, 85), (grid_x + int(col_w), grid_y), (grid_x + int(col_w), grid_y + active_h), 2)
                    pygame.draw.line(surface, (51, 65, 85), (grid_x + int(2 * col_w), grid_y), (grid_x + int(2 * col_w), grid_y + active_h), 2)

                # Subtitle & Notes below grid
                note_y = grid_y + grid_h + upx(16)
                surface.blit(self.font_sub.render("Private Household Property Rules:", True, (245, 158, 11)), (mx + upx(24), note_y))
                surface.blit(self.font_body.render("• Villagers store their private crop harvest in storage furniture (chests) placed inside their assigned Housing Lot.", True, (226, 232, 240)), (mx + upx(24), note_y + upx(20)))
                surface.blit(self.font_body.render("• Lord's servants cannot touch, haul, or seize peasant household possessions. Only landlord private stockpiles belong to the Lord.", True, COLOR_TEXT_MUTED), (mx + upx(24), note_y + upx(38)))

                # Pagination controls if total items exceed 1 page
                if max_page > 0:
                    pag_w = upx(70)
                    pag_h = upx(24)
                    pag_x = mx + grid_w - upx(180)
                    pag_y = note_y

                    # Page Indicator
                    page_str = f"Page {self.possession_page + 1}/{max_page + 1}"
                    page_surf = self.font_badge.render(page_str, True, (148, 163, 184))
                    surface.blit(page_surf, (pag_x - page_surf.get_width() - upx(10), pag_y + upx(4)))

                    # Prev Button
                    self.possession_prev_btn_rect = pygame.Rect(pag_x, pag_y, pag_w, pag_h)
                    p_hov = self.possession_prev_btn_rect.collidepoint(mouse_pos)
                    can_prev = (self.possession_page > 0)
                    pygame.draw.rect(surface, (51, 65, 85) if (p_hov and can_prev) else (30, 41, 59), self.possession_prev_btn_rect, border_radius=upx(4))
                    pygame.draw.rect(surface, (96, 165, 250) if can_prev else (71, 85, 105), self.possession_prev_btn_rect, width=1, border_radius=upx(4))
                    prev_txt = self.font_badge.render("< Prev", True, (255, 255, 255) if can_prev else (100, 116, 139))
                    surface.blit(prev_txt, (self.possession_prev_btn_rect.centerx - prev_txt.get_width() // 2, self.possession_prev_btn_rect.centery - prev_txt.get_height() // 2))

                    # Next Button
                    self.possession_next_btn_rect = pygame.Rect(pag_x + pag_w + upx(8), pag_y, pag_w, pag_h)
                    n_hov = self.possession_next_btn_rect.collidepoint(mouse_pos)
                    can_next = (self.possession_page < max_page)
                    pygame.draw.rect(surface, (51, 65, 85) if (n_hov and can_next) else (30, 41, 59), self.possession_next_btn_rect, border_radius=upx(4))
                    pygame.draw.rect(surface, (96, 165, 250) if can_next else (71, 85, 105), self.possession_next_btn_rect, width=1, border_radius=upx(4))
                    next_txt = self.font_badge.render("Next >", True, (255, 255, 255) if can_next else (100, 116, 139))
                    surface.blit(next_txt, (self.possession_next_btn_rect.centerx - next_txt.get_width() // 2, self.possession_next_btn_rect.centery - next_txt.get_height() // 2))
                else:
                    self.possession_prev_btn_rect = None
                    self.possession_next_btn_rect = None

                # Draw Grant Item modal overlays if active
                if self.show_grant_dialog:
                    self._draw_grant_dialog(surface, fam, stockpile_manager, resources, mouse_pos)
                if self.show_grant_confirm:
                    self._draw_grant_confirm(surface, fam, mouse_pos)
                return

            # Header & Back Button
            back_w = upx(150)
            self.back_to_families_btn_rect = pygame.Rect(mx + upx(24), cy - upx(4), back_w, upx(28))
            b_hover = self.back_to_families_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (51, 65, 85) if b_hover else (30, 41, 59), self.back_to_families_btn_rect, border_radius=upx(6))
            pygame.draw.rect(surface, (96, 165, 250), self.back_to_families_btn_rect, width=1, border_radius=upx(6))

            back_lbl = self.font_badge.render("< Back to Families", True, (255, 255, 255))
            surface.blit(back_lbl, (self.back_to_families_btn_rect.centerx - back_lbl.get_width() // 2, self.back_to_families_btn_rect.centery - back_lbl.get_height() // 2))

            f_title = self.font_title.render(f"Household: The {fam.surname} Family", True, (241, 245, 249))
            surface.blit(f_title, (mx + upx(24) + back_w + upx(14), cy - upx(4)))

            # Button: [📦 Household Possession]
            self.household_possession_btn_rect = None

            # Land Deed & Household Status Banner
            banner_y = cy + upx(30)
            banner_rect = pygame.Rect(mx + upx(24), banner_y, self.modal_w - upx(48), upx(70))
            pygame.draw.rect(surface, (24, 34, 52), banner_rect, border_radius=upx(8))
            pygame.draw.rect(surface, (71, 85, 105), banner_rect, width=1, border_radius=upx(8))

            p_assigned = next((p for p in permit_manager.permits if p.id == fam.assigned_permit_id), None)
            if p_assigned:
                d_txt = f"Land Deed: Assigned to {p_assigned.name} ({len(p_assigned.tiles)} tiles)"
                d_col = (34, 197, 94)
                self.household_view_permit_btn_rect = pygame.Rect(banner_rect.right - upx(108), banner_rect.y + upx(4), upx(96), upx(22))
                vp_hov = self.household_view_permit_btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (37, 99, 235) if vp_hov else (30, 41, 59), self.household_view_permit_btn_rect, border_radius=upx(4))
                pygame.draw.rect(surface, (96, 165, 250), self.household_view_permit_btn_rect, width=1, border_radius=upx(4))
                vp_lbl = self.font_badge.render("View Permit", True, (255, 255, 255))
                surface.blit(vp_lbl, (self.household_view_permit_btn_rect.centerx - vp_lbl.get_width() // 2, self.household_view_permit_btn_rect.centery - vp_lbl.get_height() // 2))
            else:
                self.household_view_permit_btn_rect = None
                d_txt = "Land Deed: Unassigned — Living at Town Center"
                d_col = (245, 158, 11)

            # Row 1: Deed & Population
            pop_summary = f"{d_txt}   |   Living Population: {fam.living_member_count} Members"
            surface.blit(self.font_sub.render(pop_summary, True, d_col), (banner_rect.x + upx(14), banner_rect.y + upx(5)))

            # Row 2: Food & Water Stocks and Daily Requirements (Agent 1)
            food_stk = fam.get_food_stock(furniture_manager, stockpile_manager)
            water_stk = fam.get_water_stock(furniture_manager, stockpile_manager)
            food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
            needs_summary = f"Primary Needs: Food: {food_stk} ({food_ok}/{living_tot} fulfilled)   |   Water: {water_stk} ({water_ok}/{living_tot} fulfilled)   |   Daily Requirement: {fam.daily_food_required} Food, {fam.daily_water_required} Water"
            surface.blit(self.font_badge.render(needs_summary, True, (241, 245, 249)), (banner_rect.x + upx(14), banner_rect.y + upx(22)))

            # Row 3: Currency (Agent 2) & Production (Agent 3)
            ps = production_system or ProductionDistributionSystem.get_instance()
            p_sum = ps.get_household_production_summary(fam.id)
            potatoes_earned = p_sum["total_produced"].get("Potato", 0)
            farm_permits = [p for p in permit_manager.permits if p.permit_type == "farm"] if permit_manager else []
            assigned_work_count = sum(1 for m in fam.members if any(m.id in getattr(p, "assigned_workers", []) for p in farm_permits))
            curr_balance = getattr(fam, "currency_balance", getattr(fam, "coins", 0))
            econ_text = f"Treasury: {curr_balance} Copper Coins   |   Production: x{potatoes_earned} Potatoes Harvested ({assigned_work_count} Farmers in Fields)"
            surface.blit(self.font_badge.render(econ_text, True, (56, 189, 248)), (banner_rect.x + upx(14), banner_rect.y + upx(37)))

            from game.systems.economy.market_sales_report import MarketSalesReportSystem
            from game.systems.economy.currency import from_copper
            income_report = MarketSalesReportSystem.get_household_report(
                building_manager, fam.id, getattr(day_cycle, "day_number", 1),
                villager_manager=villager_manager,
            )
            income_wallet = from_copper(income_report["revenue_copper"])
            income_text = (
                f"Household Income (Days {income_report['start_day']}–{income_report['end_day']}): "
                f"{income_wallet['Gold']}g {income_wallet['Silver']}s {income_wallet['Copper']}c"
            )
            surface.blit(self.font_badge.render(income_text, True, (250, 204, 21)),
                         (banner_rect.x + upx(14), banner_rect.y + upx(52)))

            # Button: [Assign / Change Deed]
            self.assign_permit_btn_rects = {}
            self.revoke_deed_btn_rect = None
            self.open_assign_lot_btn_rect = None

            if p_assigned:
                self.revoke_deed_btn_rect = pygame.Rect(banner_rect.right - upx(92), banner_rect.y + upx(12), upx(84), upx(28))
                r_hover = self.revoke_deed_btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (220, 38, 38) if r_hover else (153, 27, 27), self.revoke_deed_btn_rect, border_radius=upx(5))
                r_lbl = self.font_badge.render("Revoke", True, (255, 255, 255))
                surface.blit(r_lbl, (self.revoke_deed_btn_rect.centerx - r_lbl.get_width() // 2, self.revoke_deed_btn_rect.centery - r_lbl.get_height() // 2))

            # Member Roster Grouped by Generation
            self.member_inventory_btn_rects.clear()
            y_cur = banner_y + upx(80)
            m_header = self.font_sub.render(f"Household Members Roster ({fam.member_count} Members across {fam.get_generation_label()}):", True, COLOR_TEXT_TITLE)
            surface.blit(m_header, (mx + upx(24), y_cur))


            y_cur += upx(22)
            gen_names = {1: "Generation 1 (Elders / Grandparents)", 2: "Generation 2 (Core Couple / Parents)", 3: "Generation 3 (Adult Offspring)"}

            for gen_idx in sorted(list({m.generation for m in fam.members})):
                gen_title = self.font_badge.render(gen_names.get(gen_idx, f"Generation {gen_idx}"), True, (245, 158, 11))
                surface.blit(gen_title, (mx + upx(28), y_cur))
                y_cur += upx(16)

                for m in [mem for mem in fam.members if mem.generation == gen_idx]:
                    m_card = pygame.Rect(mx + upx(24), y_cur, self.modal_w - upx(48), upx(30))
                    pygame.draw.rect(surface, (15, 23, 42, 180), m_card, border_radius=upx(5))
                    pygame.draw.rect(surface, (51, 65, 85), m_card, width=1, border_radius=upx(5))

                    # Icon & Name
                    m_info = f"{m.full_name}  ({m.role}, Age {m.age}, {m.gender})"
                    name_col = (241, 245, 249) if getattr(m, "is_alive", True) else (148, 163, 184)
                    surface.blit(self.font_body.render(m_info, True, name_col), (m_card.x + upx(12), m_card.y + upx(6)))

                    # Needs & Living Status Indicator
                    if not getattr(m, "is_alive", True):
                        d_lbl = self.font_badge.render(f"[DECEASED: {getattr(m, 'death_reason', 'Starvation')}]", True, (239, 68, 68))
                        surface.blit(d_lbl, (m_card.right - upx(370), m_card.y + upx(7)))
                    else:
                        h_val = int(getattr(m, "hunger", 100.0))
                        t_val = int(getattr(m, "thirst", 100.0))
                        need_col = (239, 68, 68) if min(h_val, t_val) <= 20 else ((245, 158, 11) if min(h_val, t_val) <= 50 else (148, 163, 184))
                        n_lbl = self.font_badge.render(f"H: {h_val}% | T: {t_val}%", True, need_col)
                        surface.blit(n_lbl, (m_card.right - upx(340), m_card.y + upx(7)))


                    # Dedicated Job Badge
                    job_cfg = DEDICATED_JOBS.get(getattr(m, "job", "Farmer"), {})
                    job_title = job_cfg.get("title", getattr(m, "job", "Worker"))
                    job_badge = pygame.Rect(m_card.right - upx(230), m_card.y + upx(4), upx(110), upx(22))
                    pygame.draw.rect(surface, (20, 83, 45), job_badge, border_radius=upx(4))
                    pygame.draw.rect(surface, (34, 197, 94), job_badge, width=1, border_radius=upx(4))
                    j_txt = self.font_badge.render(job_title, True, (240, 253, 244))
                    surface.blit(j_txt, (job_badge.centerx - j_txt.get_width() // 2, job_badge.centery - j_txt.get_height() // 2))

                    # [🎒 Inventory] Button
                    inv_btn = pygame.Rect(m_card.right - upx(114), m_card.y + upx(4), upx(106), upx(22))
                    self.member_inventory_btn_rects[m.id] = inv_btn
                    i_hov = inv_btn.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (37, 99, 235) if i_hov else (30, 58, 138), inv_btn, border_radius=upx(4))
                    pygame.draw.rect(surface, (96, 165, 250), inv_btn, width=1, border_radius=upx(4))
                    i_txt = self.font_badge.render("Inventory", True, (255, 255, 255))
                    surface.blit(i_txt, (inv_btn.centerx - i_txt.get_width() // 2, inv_btn.centery - i_txt.get_height() // 2))

                    y_cur += upx(34)
                y_cur += upx(6)

            # Housing Lot Deed Picker Dropdown/Modal (Drawn as an Overlay on Top of the Roster)
            self.assign_permit_btn_rects = {}
            if self.show_assign_permit_picker:
                picker_w = upx(420)
                housing_permits = [p for p in permit_manager.permits if p.permit_type in ["housing", "landlord_private"]]
                picker_h = max(upx(70), min(upx(240), len(housing_permits) * upx(36) + upx(46)))
                picker_x = banner_rect.right - picker_w
                picker_y = banner_rect.bottom + upx(4)
                self.deed_picker_bg_rect = pygame.Rect(picker_x, picker_y, picker_w, picker_h)

                # Shadow
                shadow_surf = pygame.Surface((picker_w, picker_h), pygame.SRCALPHA)
                pygame.draw.rect(shadow_surf, (0, 0, 0, 180), (0, 0, picker_w, picker_h), border_radius=upx(8))
                surface.blit(shadow_surf, (picker_x + upx(4), picker_y + upx(4)))

                # Background & Border
                pygame.draw.rect(surface, (15, 23, 42), self.deed_picker_bg_rect, border_radius=upx(8))
                pygame.draw.rect(surface, (59, 130, 246), self.deed_picker_bg_rect, width=2, border_radius=upx(8))

                p_header = self.font_badge.render("SELECT HOUSING PERMIT DEED FOR THIS FAMILY:", True, (56, 189, 248))
                surface.blit(p_header, (picker_x + upx(14), picker_y + upx(12)))

                # Close [✕] button
                self.close_deed_picker_btn_rect = pygame.Rect(picker_x + picker_w - upx(28), picker_y + upx(10), upx(18), upx(18))
                pygame.draw.rect(surface, (220, 38, 38), self.close_deed_picker_btn_rect, border_radius=3)
                x_lbl = self.font_badge.render("X", True, (255, 255, 255))
                surface.blit(x_lbl, (self.close_deed_picker_btn_rect.x + upx(4), self.close_deed_picker_btn_rect.y + 2))

                row_y = picker_y + upx(36)
                if not housing_permits:
                    none_txt = self.font_body.render("- No Housing Permits issued. Issue one first in Area Permits tab!", True, (239, 68, 68))
                    surface.blit(none_txt, (picker_x + upx(14), row_y + upx(4)))
                else:
                    for p in housing_permits:
                        occupant = next((f for f in villager_manager.families if f.assigned_permit_id == p.id and f.id != fam.id), None) if villager_manager else None
                        p_btn = pygame.Rect(picker_x + upx(10), row_y, picker_w - upx(20), upx(28))

                        if occupant:
                            # Occupied by another family! Cannot be assigned unless revoked first!
                            pygame.draw.rect(surface, (30, 20, 25), p_btn, border_radius=upx(4))
                            pygame.draw.rect(surface, (127, 29, 29), p_btn, width=1, border_radius=upx(4))
                            occ_txt = self.font_badge.render(f"[Occupied] {p.name} - Occupied by The {occupant.surname}s (Revoke first)", True, (248, 113, 113))
                            surface.blit(occ_txt, (p_btn.x + upx(12), p_btn.y + upx(7)))
                        elif p.id == fam.assigned_permit_id:
                            # Already this family's current permit
                            pygame.draw.rect(surface, (20, 83, 45), p_btn, border_radius=upx(4))
                            pygame.draw.rect(surface, (34, 197, 94), p_btn, width=1, border_radius=upx(4))
                            curr_txt = self.font_badge.render(f"Current Deed: {p.name} ({len(p.tiles)} tiles)", True, (240, 253, 244))
                            surface.blit(curr_txt, (p_btn.x + upx(12), p_btn.y + upx(7)))
                        else:
                            # Vacant - can be assigned!
                            self.assign_permit_btn_rects[p.id] = p_btn
                            p_hov = p_btn.collidepoint(mouse_pos)
                            pygame.draw.rect(surface, (37, 99, 235) if p_hov else (30, 41, 59), p_btn, border_radius=upx(4))
                            pygame.draw.rect(surface, (96, 165, 250), p_btn, width=1, border_radius=upx(4))
                            p_txt = self.font_badge.render(f"Grant {p.name} ({len(p.tiles)} tiles)", True, (255, 255, 255))
                            surface.blit(p_txt, (p_btn.x + upx(12), p_btn.y + upx(7)))

                        row_y += upx(34)

            # Member Individual Inventory Modal Overlay
            if self.selected_member_inventory_id is not None:
                mem_obj = next((m for m in fam.members if m.id == self.selected_member_inventory_id), None)
                if mem_obj:
                    self._draw_member_inventory_dialog(surface, mem_obj, fam, furniture_manager, stockpile_manager, mouse_pos)

    def _draw_member_inventory_dialog(self, surface, member, fam, furniture_manager, stockpile_manager, mouse_pos):
        from game.systems.village_life.happiness_system import HappinessSystem
        screen_w, screen_h = surface.get_size()
        dim_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        dim_surf.fill((0, 0, 0, 160))
        surface.blit(dim_surf, (0, 0))

        inv = member.inventory
        carrying = getattr(member, "carrying_crop", 0)
        items = list(inv.items())
        if carrying > 0:
            items.insert(0, ("Potato (Harvest)", carrying))
        happiness_factors = HappinessSystem.get_breakdown(member)
        factor_panel_h = max(upx(48), upx(24) + len(happiness_factors) * upx(16))

        dlg_w = min(upx(540), screen_w - upx(40))
        items_cnt = len(items) if items else 1
        needed_h = upx(150) + factor_panel_h + items_cnt * upx(44) + upx(36)
        dlg_h = min(max(upx(320), needed_h), int(screen_h * 0.85))
        dx = (screen_w - dlg_w) // 2
        dy = (screen_h - dlg_h) // 2
        self.member_inv_bg_rect = pygame.Rect(dx, dy, dlg_w, dlg_h)

        pygame.draw.rect(surface, (15, 23, 42), self.member_inv_bg_rect, border_radius=upx(10))
        pygame.draw.rect(surface, (59, 130, 246), self.member_inv_bg_rect, width=2, border_radius=upx(10))

        # Title
        title_surf = self.font_sub.render(f"Personal Profile & Inventory: {member.full_name}", True, (241, 245, 249))
        surface.blit(title_surf, (dx + upx(20), dy + upx(14)))

        # Living / Deceased Status Badge
        is_alive = getattr(member, "is_alive", True)
        h_timer = getattr(member, "hunger_death_timer", None)
        t_timer = getattr(member, "thirst_death_timer", None)
        if is_alive:
            if h_timer is not None and t_timer is not None:
                st_badge = self.font_badge.render("[CRITICAL: Starving & Dehydrated]", True, (239, 68, 68))
            elif h_timer is not None:
                st_badge = self.font_badge.render(f"[CRITICAL: Starving in {h_timer:.1f}h]", True, (239, 68, 68))
            elif t_timer is not None:
                st_badge = self.font_badge.render(f"[CRITICAL: Dehydrated in {t_timer:.1f}h]", True, (239, 68, 68))
            else:
                st_badge = self.font_badge.render("[ALIVE]", True, (34, 197, 94))
        else:
            reason = getattr(member, "death_reason", "Starvation")
            st_badge = self.font_badge.render(f"[DECEASED: {reason}]", True, (239, 68, 68))
        surface.blit(st_badge, (dx + dlg_w - upx(38) - st_badge.get_width(), dy + upx(16)))

        # Close [✕] button
        self.close_member_inv_btn_rect = pygame.Rect(dx + dlg_w - upx(32), dy + upx(14), upx(20), upx(20))
        c_hov = self.close_member_inv_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (239, 68, 68) if c_hov else (30, 41, 59), self.close_member_inv_btn_rect, border_radius=upx(4))
        c_txt = self.font_badge.render("X", True, (255, 255, 255))
        surface.blit(c_txt, (self.close_member_inv_btn_rect.centerx - c_txt.get_width() // 2, self.close_member_inv_btn_rect.centery - c_txt.get_height() // 2))

        # Member details banner
        info_str = f"Role: {member.role}  |  Age: {member.age}  |  Household: The {fam.surname} Family  |  Job: {getattr(member, 'job', 'Farmer')}"
        surface.blit(self.font_body.render(info_str, True, (56, 189, 248)), (dx + upx(20), dy + upx(38)))

        # Needs Status Bars (Hunger & Thirst)
        h_val = max(0.0, min(100.0, getattr(member, "hunger", 100.0)))
        t_val = max(0.0, min(100.0, getattr(member, "thirst", 100.0)))

        # Hunger Bar
        surface.blit(self.font_badge.render("Hunger:", True, (241, 245, 249)), (dx + upx(20), dy + upx(58)))
        h_bar_bg = pygame.Rect(dx + upx(74), dy + upx(58), upx(120), upx(14))
        pygame.draw.rect(surface, (30, 41, 59), h_bar_bg, border_radius=upx(4))
        h_fill_w = max(0, int(120 * (h_val / 100.0)))
        if h_fill_w > 0:
            h_col = (34, 197, 94) if h_val > 50 else ((234, 179, 8) if h_val > 20 else (239, 68, 68))
            pygame.draw.rect(surface, h_col, (dx + upx(74), dy + upx(58), h_fill_w, upx(14)), border_radius=upx(4))
        pygame.draw.rect(surface, (71, 85, 105), h_bar_bg, width=1, border_radius=upx(4))
        h_txt_str = f"{int(h_val)}%" if h_timer is None else f"{int(h_val)}% ({h_timer:.1f}h)"
        h_pct = self.font_badge.render(h_txt_str, True, (255, 255, 255) if h_timer is None else (239, 68, 68))
        surface.blit(h_pct, (dx + upx(200), dy + upx(58)))

        # Thirst Bar
        surface.blit(self.font_badge.render("Thirst:", True, (241, 245, 249)), (dx + upx(276), dy + upx(58)))
        t_bar_bg = pygame.Rect(dx + upx(322), dy + upx(58), upx(120), upx(14))
        pygame.draw.rect(surface, (30, 41, 59), t_bar_bg, border_radius=upx(4))
        t_fill_w = max(0, int(120 * (t_val / 100.0)))
        if t_fill_w > 0:
            t_col = (56, 189, 248) if t_val > 50 else ((59, 130, 246) if t_val > 20 else (239, 68, 68))
            pygame.draw.rect(surface, t_col, (dx + upx(322), dy + upx(58), t_fill_w, upx(14)), border_radius=upx(4))
        pygame.draw.rect(surface, (71, 85, 105), t_bar_bg, width=1, border_radius=upx(4))
        t_txt_str = f"{int(t_val)}%" if t_timer is None else f"{int(t_val)}% ({t_timer:.1f}h)"
        t_pct = self.font_badge.render(t_txt_str, True, (255, 255, 255) if t_timer is None else (239, 68, 68))
        surface.blit(t_pct, (dx + upx(448), dy + upx(58)))

        # Bed Status & Active tool
        bed_status = f"Assigned Bed:  {member.assigned_bed_id}" if getattr(member, 'assigned_bed_id', None) else " Bed: None (Sleeping on Floor)"
        tool_status = f"Active Tool:  {member.active_tool or 'None'}"
        water_status = "Water: Full" if member.has_water else "Water: Empty"
        status_line = f"{bed_status}  •  {tool_status}  •  {water_status}"
        surface.blit(self.font_badge.render(status_line, True, (148, 163, 184)), (dx + upx(20), dy + upx(78)))

        factor_y = dy + upx(102)
        factor_rect = pygame.Rect(dx + upx(20), factor_y, dlg_w - upx(40), factor_panel_h)
        pygame.draw.rect(surface, (24, 34, 52), factor_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (51, 65, 85), factor_rect, width=1, border_radius=upx(6))
        title = self.font_badge.render("Happiness factors", True, (56, 189, 248))
        surface.blit(title, (factor_rect.x + upx(10), factor_rect.y + upx(6)))
        factors_y = factor_rect.y + upx(21)
        if not happiness_factors:
            surface.blit(self.font_badge.render("No active happiness modifiers", True, (148, 163, 184)), (factor_rect.x + upx(10), factors_y))
        else:
            for factor in happiness_factors:
                amount = float(factor.get("amount", 0.0))
                label = str(factor.get("label", "Happiness factor"))
                duration = str(factor.get("duration", ""))
                color = (74, 222, 128) if amount >= 0 else (248, 113, 113)
                amount_text = f"{amount:+g}"
                row_text = self.font_badge.render(label, True, (226, 232, 240))
                value_text = self.font_badge.render(amount_text, True, color)
                surface.blit(row_text, (factor_rect.x + upx(10), factors_y))
                if duration and duration != "Base":
                    duration_surface = self.font_badge.render(duration, True, (148, 163, 184))
                    surface.blit(duration_surface, (factor_rect.right - upx(50) - value_text.get_width() - duration_surface.get_width(), factors_y))
                surface.blit(value_text, (factor_rect.right - upx(10) - value_text.get_width(), factors_y))
                factors_y += upx(16)

        divider_y = factor_rect.bottom + upx(6)
        pygame.draw.line(surface, (51, 65, 85), (dx + upx(20), divider_y), (dx + dlg_w - upx(20), divider_y), 1)

        self.member_deposit_btn_rects.clear()
        self.member_drop_btn_rects.clear()

        has_chest = (furniture_manager.get_storage_for_family(fam.id) is not None) if furniture_manager else False

        y_item = divider_y + upx(8)

        if not items:
            empty_lbl = self.font_body.render("— Personal inventory is currently empty (Hands/Bag free) —", True, (100, 116, 139))
            surface.blit(empty_lbl, (dx + upx(20), y_item + upx(20)))
        else:
            for item_name, count in items:
                row_rect = pygame.Rect(dx + upx(20), y_item, dlg_w - upx(40), upx(36))
                pygame.draw.rect(surface, (30, 41, 59), row_rect, border_radius=upx(6))
                pygame.draw.rect(surface, (51, 65, 85), row_rect, width=1, border_radius=upx(6))

                draw_item_icon(surface, item_name, row_rect.x + upx(24), row_rect.y + upx(18), size=upx(10))
                item_lbl = self.font_body.render(f"{item_name}  × {count}", True, (241, 245, 249))
                surface.blit(item_lbl, (row_rect.x + upx(42), row_rect.y + upx(9)))

                # Buttons: [Deposit to Chest] & [Drop to Ground]
                if item_name in inv and inv[item_name] > 0:
                    btn_x = row_rect.right - upx(10)
                    # Drop button
                    drop_btn = pygame.Rect(btn_x - upx(70), row_rect.y + upx(6), upx(70), upx(24))
                    self.member_drop_btn_rects[item_name] = drop_btn
                    d_hov = drop_btn.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (185, 28, 28) if d_hov else (127, 29, 29), drop_btn, border_radius=upx(4))
                    d_txt = self.font_badge.render("Drop", True, (255, 255, 255))
                    surface.blit(d_txt, (drop_btn.centerx - d_txt.get_width() // 2, drop_btn.centery - d_txt.get_height() // 2))

                    # Deposit button
                    if has_chest:
                        dep_btn = pygame.Rect(drop_btn.x - upx(110), row_rect.y + upx(6), upx(102), upx(24))
                        self.member_deposit_btn_rects[item_name] = dep_btn
                        dp_hov = dep_btn.collidepoint(mouse_pos)
                        pygame.draw.rect(surface, (16, 185, 129) if dp_hov else (5, 150, 105), dep_btn, border_radius=upx(4))
                        dp_txt = self.font_badge.render("To Chest", True, (255, 255, 255))
                        surface.blit(dp_txt, (dep_btn.centerx - dp_txt.get_width() // 2, dep_btn.centery - dp_txt.get_height() // 2))

                y_item += upx(42)

        # Footer explanation
        foot_y = dy + dlg_h - upx(36)
        note = self.font_badge.render("Items in personal inventory are immediately available for this member to work with.", True, (148, 163, 184))
        surface.blit(note, (dx + upx(20), foot_y))

    def _draw_grant_dialog(self, surface, fam, stockpile_manager, resources, mouse_pos):
        self._init_fonts()
        sm = stockpile_manager or self.cached_stockpile_manager
        stock = self.get_landlord_stock(sm, resources)

        screen_w, screen_h = surface.get_size()

        # Dark overlay backdrop
        overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        # Responsive Dimensions:
        dlg_w = min(upx(600), max(upx(460), screen_w - upx(40)))

        # Dynamically build grantable items list (Standard items + any extra items currently in landlord stock)
        grantable = list(GRANTABLE_ITEMS)
        existing_types = {it["type"] for it in grantable}
        for st_type, st_qty in stock.items():
            if st_type not in existing_types and st_qty > 0:
                grantable.append({"type": st_type, "name": canonical_item_name(st_type)})

        # Layout metrics
        header_h = upx(76)
        footer_h = upx(66)
        row_h = upx(44)
        row_gap = upx(8)
        row_step = row_h + row_gap
        num_items = len(grantable)
        total_items_h = num_items * row_step

        # Max modal height allowed relative to viewport
        max_dlg_h = min(int(screen_h * 0.88), upx(680))

        # Dynamic height calculation
        needed_dlg_h = header_h + total_items_h + footer_h + upx(8)
        if needed_dlg_h <= max_dlg_h:
            dlg_h = needed_dlg_h
            viewport_h = total_items_h + upx(8)
        else:
            dlg_h = max_dlg_h
            viewport_h = dlg_h - header_h - footer_h

        dlg_x = (screen_w - dlg_w) // 2
        dlg_y = (screen_h - dlg_h) // 2
        dlg_rect = pygame.Rect(dlg_x, dlg_y, dlg_w, dlg_h)
        self.grant_dlg_rect = dlg_rect

        # Draw Modal Container Box
        pygame.draw.rect(surface, (15, 23, 42), dlg_rect, border_radius=upx(10))
        pygame.draw.rect(surface, (59, 130, 246), dlg_rect, width=2, border_radius=upx(10))

        # -------------------------------------------------------------
        # 1. HEADER (Title, Subtitle & Header Close [X] Button)
        # -------------------------------------------------------------
        t_surf = self.font_title.render(f"Grant Supplies:  The {fam.surname} Family", True, (241, 245, 249))
        surface.blit(t_surf, (dlg_x + upx(24), dlg_y + upx(18)))
        sub_surf = self.font_body.render("Select supplies from Landlord Storage for AI Servants to haul & deliver.", True, (148, 163, 184))
        surface.blit(sub_surf, (dlg_x + upx(24), dlg_y + upx(46)))

        # Header Close [X] Button
        self.grant_header_close_btn_rect = pygame.Rect(dlg_x + dlg_w - upx(36), dlg_y + upx(16), upx(22), upx(22))
        x_hov = self.grant_header_close_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (239, 68, 68) if x_hov else (30, 41, 59), self.grant_header_close_btn_rect, border_radius=upx(4))
        x_lbl = self.font_badge.render("X", True, (255, 255, 255))
        surface.blit(x_lbl, (self.grant_header_close_btn_rect.centerx - x_lbl.get_width() // 2, self.grant_header_close_btn_rect.centery - x_lbl.get_height() // 2))

        # Header Separator
        pygame.draw.line(surface, (51, 65, 85), (dlg_x + upx(20), dlg_y + header_h - upx(4)), (dlg_x + dlg_w - upx(20), dlg_y + header_h - upx(4)), 1)

        # -------------------------------------------------------------
        # 2. SCROLLABLE CONTENT VIEWPORT
        # -------------------------------------------------------------
        viewport_y = dlg_y + header_h
        viewport_rect = pygame.Rect(dlg_x + upx(16), viewport_y, dlg_w - upx(32), viewport_h)
        self.grant_viewport_rect = viewport_rect

        # Max scroll calculation
        max_scroll = max(0, total_items_h - viewport_h + 8)
        self.grant_max_scroll = max_scroll
        self.grant_scroll_y = max(0, min(self.grant_scroll_y, max_scroll))

        has_scrollbar = (max_scroll > 0)
        content_margin_right = upx(16) if has_scrollbar else upx(4)
        item_row_w = viewport_rect.w - upx(8) - content_margin_right

        self.grant_max_btn_rects.clear()
        self.grant_item_qty_rects.clear()

        # Scissor clipping to parent container: no item row can render outside viewport!
        old_clip = surface.get_clip()
        surface.set_clip(viewport_rect)

        start_row_y = viewport_y + upx(4) - self.grant_scroll_y

        for idx, item_data in enumerate(grantable):
            it_type = item_data["type"]
            it_name = item_data["name"]
            avail = stock.get(it_type, 0)
            qty = self.grant_amounts.get(it_type, 0)

            cur_row_y = start_row_y + idx * row_step

            # Culling optimization: skip rows completely outside the visible viewport
            if cur_row_y + row_h < viewport_y or cur_row_y > viewport_y + viewport_h:
                continue

            row_rect = pygame.Rect(viewport_rect.x + upx(4), cur_row_y, item_row_w, row_h)
            pygame.draw.rect(surface, (30, 41, 59), row_rect, border_radius=upx(6))
            pygame.draw.rect(surface, (51, 65, 85), row_rect, width=1, border_radius=upx(6))

            # Icon & Name
            draw_item_icon(surface, it_name, row_rect.x + upx(20), cur_row_y + upx(22), size=upx(11))
            name_s = self.font_sub.render(it_name, True, (241, 245, 249))
            surface.blit(name_s, (row_rect.x + upx(44), cur_row_y + upx(11)))

            # Available in Stockpile
            stk_color = (34, 197, 94) if avail > 0 else (148, 163, 184)
            stk_s = self.font_body.render(f"In Storage: {avail}", True, stk_color)
            surface.blit(stk_s, (row_rect.x + upx(180), cur_row_y + upx(13)))

            # Controls: [ QTY ] [Max]  (quantity is typed directly)
            ctrl_rx = row_rect.right - upx(240)

            # Quantity Display / Input box
            qty_r = pygame.Rect(ctrl_rx, cur_row_y + upx(8), upx(126), upx(28))
            if viewport_rect.collidepoint(qty_r.center):
                self.grant_item_qty_rects[it_type] = qty_r
            is_active_input = (self.active_grant_input_item == it_type)
            box_bg = (15, 23, 42) if not is_active_input else (30, 58, 138)
            border_c = (250, 204, 21) if is_active_input else (71, 85, 105)
            pygame.draw.rect(surface, box_bg, qty_r, border_radius=upx(4))
            pygame.draw.rect(surface, border_c, qty_r, width=2 if is_active_input else 1, border_radius=upx(4))
            
            disp_txt = str(qty) if not is_active_input else (self.grant_input_text or "0")
            q_color = (250, 204, 21) if qty > 0 else (148, 163, 184)
            q_txt = self.font_sub.render(disp_txt, True, q_color)
            surface.blit(q_txt, (qty_r.centerx - q_txt.get_width() // 2, qty_r.centery - q_txt.get_height() // 2))

            # Max button
            max_r = pygame.Rect(ctrl_rx + upx(138), cur_row_y + upx(8), upx(52), upx(28))
            if viewport_rect.collidepoint(max_r.center):
                self.grant_max_btn_rects[it_type] = max_r
            max_hov = max_r.collidepoint(mouse_pos) if viewport_rect.collidepoint(mouse_pos) else False
            pygame.draw.rect(surface, (71, 85, 105) if max_hov else (51, 65, 85), max_r, border_radius=upx(4))
            pygame.draw.rect(surface, (148, 163, 184), max_r, width=1, border_radius=upx(4))
            max_txt = self.font_badge.render("Max", True, (241, 245, 249))
            surface.blit(max_txt, (max_r.centerx - max_txt.get_width() // 2, max_r.centery - max_txt.get_height() // 2))

        # Restore normal clipping
        surface.set_clip(old_clip)

        # -------------------------------------------------------------
        # 3. SCROLLBAR (if content exceeds viewport)
        # -------------------------------------------------------------
        if has_scrollbar:
            sb_x = dlg_x + dlg_w - upx(24)
            sb_y = viewport_y + upx(4)
            sb_w = upx(6)
            sb_h = viewport_h - upx(8)
            self.grant_scrollbar_rect = pygame.Rect(sb_x - 3, sb_y, sb_w + upx(6), sb_h)
            pygame.draw.rect(surface, (30, 41, 59), (sb_x, sb_y, sb_w, sb_h), border_radius=3)
            
            thumb_h = max(upx(24), int(sb_h * (viewport_h / total_items_h)))
            thumb_ratio = self.grant_scroll_y / max_scroll if max_scroll > 0 else 0
            thumb_y = sb_y + int((sb_h - thumb_h) * thumb_ratio)
            self.grant_thumb_rect = pygame.Rect(sb_x, thumb_y, sb_w, thumb_h)
            
            sb_hov = self.grant_scrollbar_rect.collidepoint(mouse_pos) or self.grant_is_dragging_scrollbar
            pygame.draw.rect(surface, (96, 165, 250) if sb_hov else (71, 85, 105), (sb_x, thumb_y, sb_w, thumb_h), border_radius=3)
        else:
            self.grant_scrollbar_rect = None
            self.grant_thumb_rect = None

        # -------------------------------------------------------------
        # 4. STICKY FOOTER (Solid backdrop, Grant & Cancel buttons)
        # -------------------------------------------------------------
        footer_y = dlg_y + dlg_h - footer_h
        footer_bg = pygame.Rect(dlg_x + 2, footer_y, dlg_w - upx(4), footer_h - 2)
        pygame.draw.rect(surface, (15, 23, 42), footer_bg, border_bottom_left_radius=upx(10), border_bottom_right_radius=upx(10))
        pygame.draw.line(surface, (51, 65, 85), (dlg_x + upx(20), footer_y), (dlg_x + dlg_w - upx(20), footer_y), 1)

        total_grant = sum(self.grant_amounts.values())
        btn_y = footer_y + upx(15)

        # Grant Button
        self.grant_submit_btn_rect = pygame.Rect(dlg_x + upx(20), btn_y, upx(240), upx(36))
        s_hov = self.grant_submit_btn_rect.collidepoint(mouse_pos)
        can_grant = total_grant > 0
        s_bg = (22, 101, 52) if (can_grant and not s_hov) else ((21, 128, 61) if can_grant else (51, 65, 85))
        pygame.draw.rect(surface, s_bg, self.grant_submit_btn_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (74, 222, 128) if can_grant else (71, 85, 105), self.grant_submit_btn_rect, width=1, border_radius=upx(6))
        sub_lbl = self.font_sub.render(f"Grant ({total_grant} items)", True, (255, 255, 255) if can_grant else (148, 163, 184))
        surface.blit(sub_lbl, (self.grant_submit_btn_rect.centerx - sub_lbl.get_width() // 2, self.grant_submit_btn_rect.centery - sub_lbl.get_height() // 2))

        # Cancel Button
        self.grant_close_btn_rect = pygame.Rect(dlg_x + dlg_w - upx(20) - upx(130), btn_y, upx(130), upx(36))
        c_hov = self.grant_close_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (71, 85, 105) if c_hov else (30, 41, 59), self.grant_close_btn_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (148, 163, 184), self.grant_close_btn_rect, width=1, border_radius=upx(6))
        c_lbl = self.font_sub.render("Cancel", True, (241, 245, 249))
        surface.blit(c_lbl, (self.grant_close_btn_rect.centerx - c_lbl.get_width() // 2, self.grant_close_btn_rect.centery - c_lbl.get_height() // 2))

    def _draw_grant_confirm(self, surface, fam, mouse_pos):
        self._init_fonts()
        screen_w, screen_h = surface.get_size()
        overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        cf_w = min(upx(520), max(upx(440), screen_w - upx(40)))

        # Summary of items with multi-line wrapping
        items_summary = []
        for it_type, qty in self.grant_amounts.items():
            if qty > 0:
                name = it_type.replace("_", " ")
                items_summary.append(f"{qty}x {name}")

        summary_lines = []
        cur_line = "Items: "
        for idx, itm_txt in enumerate(items_summary):
            sep = ", " if idx > 0 else ""
            if len(cur_line + sep + itm_txt) > 48:
                summary_lines.append(cur_line)
                cur_line = "       " + itm_txt
            else:
                cur_line += sep + itm_txt
        if cur_line:
            summary_lines.append(cur_line)
        if not summary_lines:
            summary_lines = ["Items: None"]

        cf_h = 190 + len(summary_lines) * 22
        cf_x = (screen_w - cf_w) // 2
        cf_y = (screen_h - cf_h) // 2
        cf_rect = pygame.Rect(cf_x, cf_y, cf_w, cf_h)

        pygame.draw.rect(surface, (15, 23, 42), cf_rect, border_radius=upx(10))
        pygame.draw.rect(surface, (245, 158, 11), cf_rect, width=2, border_radius=upx(10))

        # Title
        t_s = self.font_title.render("Confirm Royal Grant Decree", True, (250, 204, 21))
        surface.blit(t_s, (cf_x + upx(24), cf_y + upx(18)))

        # Question
        q_s = self.font_sub.render(f"Are you sure you want to grant these items to The {fam.surname} Family?", True, (241, 245, 249))
        surface.blit(q_s, (cf_x + upx(24), cf_y + upx(48)))

        # Summary lines
        line_y = cf_y + upx(78)
        for s_line in summary_lines:
            sum_s = self.font_body.render(s_line, True, (34, 197, 94))
            surface.blit(sum_s, (cf_x + upx(24), line_y))
            line_y += upx(20)

        # Hauling notice
        notice_s = self.font_body.render("• AI Servants will fetch items from Landlord storage and haul them to the household.", True, (148, 163, 184))
        surface.blit(notice_s, (cf_x + upx(24), line_y + upx(6)))

        # Action Buttons: [✓ Yes, Grant] and [✕ Cancel]
        btn_y = cf_y + cf_h - upx(52)

        self.grant_confirm_btn_rect = pygame.Rect(cf_x + upx(24), btn_y, upx(180), upx(36))
        yes_hov = self.grant_confirm_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (22, 101, 52) if yes_hov else (21, 128, 61), self.grant_confirm_btn_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (74, 222, 128), self.grant_confirm_btn_rect, width=1, border_radius=upx(6))
        yes_s = self.font_sub.render("Yes, Grant", True, (255, 255, 255))
        surface.blit(yes_s, (self.grant_confirm_btn_rect.centerx - yes_s.get_width() // 2, self.grant_confirm_btn_rect.centery - yes_s.get_height() // 2))

        self.grant_cancel_btn_rect = pygame.Rect(cf_x + cf_w - upx(24) - upx(130), btn_y, upx(130), upx(36))
        no_hov = self.grant_cancel_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (71, 85, 105) if no_hov else (30, 41, 59), self.grant_cancel_btn_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (148, 163, 184), self.grant_cancel_btn_rect, width=1, border_radius=upx(6))
        no_s = self.font_sub.render("Cancel", True, (241, 245, 249))
        surface.blit(no_s, (self.grant_cancel_btn_rect.centerx - no_s.get_width() // 2, self.grant_cancel_btn_rect.centery - no_s.get_height() // 2))

