"""
Market Profile Modal (AGENT 2)
Displays landlord & household market stall management:
- Household Stall Assignment ('Assign Stall To')
- Independent Item Allocation Settings (% per item with actual chest ownership)
- Market Treasury with Deposit Coin & Withdraw Coin
- Scarcity-Aware Dynamic Selling Price Display
- Physical Restock & Withdraw Goods
- Consistent Global Procedural Vector Item Icons
"""

import math
import pygame
from game.data.config import (
    DEFAULT_ITEM_PRICES,
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    RESOURCE_COLORS,
    DENOMINATION_CAP,
    ITEM_CATEGORIES
)
from game.systems.currency import (
    to_copper,
    from_copper,
    normalize_wallet,
    canonical_denomination
)
from game.systems.household_inventory import get_household_possessions
from game.systems.market_service import MarketService
from game.ui.item_icons import draw_item_icon

class MarketProfileModal:
    def __init__(self):
        self.is_open = False
        self.target_market = None
        self.font_title = None
        self.font_sub = None
        self.font_body = None
        self.font_badge = None
        self.font_btn = None

        # Modal bounds
        self.modal_w = 780
        self.modal_h = 560

        # Tabs & Sub-views
        self.active_tab = "goods"  # "goods" (Market Goods & Pricing) | "allocation" (Household Goods Allocation)
        self.tab_goods_rect = None
        self.tab_alloc_rect = None

        # Dialog States
        self.show_assign_dialog = False
        self.show_coin_dialog = None  # None | "deposit" | "withdraw"

        # UI interaction rects
        self.close_btn_rect = None
        self.assign_stall_btn_rect = None
        self.unassign_stall_btn_rect = None
        self.close_assign_dlg_btn_rect = None
        self.family_assign_btn_rects = {}

        # Coin Treasury Rects
        self.deposit_coin_btn_rect = None
        self.withdraw_coin_btn_rect = None
        self.coin_action_btn_rects = {}
        self.close_coin_dlg_btn_rect = None

        # Price adjustment rects
        self.price_g_dec_btns = {}
        self.price_g_inc_btns = {}
        self.price_s_dec_btns = {}
        self.price_s_inc_btns = {}
        self.price_c_dec_btns = {}
        self.price_c_inc_btns = {}
        self.price_dec_btns = self.price_c_dec_btns
        self.price_inc_btns = self.price_c_inc_btns
        self.price_dec5_btns = {}
        self.price_inc5_btns = {}

        # Stock management rects
        self.stock_dep_btns = {}
        self.stock_with_btns = {}

        # Allocation controls rects (item_name -> rect)
        self.alloc_dec_btns = {}
        self.alloc_inc_btns = {}
        self.alloc_min_btns = {}
        self.alloc_max_btns = {}

        # Pagination for tradeable goods
        self.goods_page = 0
        self.prev_page_btn_rect = None
        self.next_page_btn_rect = None

    def _ensure_fonts(self):
        if self.font_title is None:
            self.font_title = pygame.font.SysFont("Segoe UI", 16, bold=True)
            self.font_sub = pygame.font.SysFont("Segoe UI", 12, bold=True)
            self.font_body = pygame.font.SysFont("Segoe UI", 11)
            self.font_badge = pygame.font.SysFont("Segoe UI", 10, bold=True)
            self.font_btn = pygame.font.SysFont("Segoe UI", 11, bold=True)

    def open(self, market_building):
        """Opens market profile modal for the selected market building"""
        if market_building and getattr(market_building, "building_type", "") == "market":
            self.target_market = market_building
            self.is_open = True
            self.show_assign_dialog = False
            self.show_coin_dialog = None

            # Ensure data integrity & contracts
            if not hasattr(market_building, "prices") or not market_building.prices:
                market_building.prices = dict(DEFAULT_ITEM_PRICES)
            if not hasattr(market_building, "inventory") or market_building.inventory is None:
                market_building.inventory = {}
            if not hasattr(market_building, "currency") or not market_building.currency:
                market_building.currency = {"Copper": 0, "Silver": 0, "Gold": 0}
            if not hasattr(market_building, "assigned_family_id"):
                market_building.assigned_family_id = None
            if not hasattr(market_building, "item_allocations") or not isinstance(market_building.item_allocations, dict):
                market_building.item_allocations = {}
            if not hasattr(market_building, "auto_pricing"):
                market_building.auto_pricing = True

    def close(self):
        self.is_open = False
        self.target_market = None
        self.show_assign_dialog = False
        self.show_coin_dialog = None

    def handle_event(self, event, resources=None, stockpile_manager=None, servant_manager=None, villager_manager=None, furniture_manager=None):
        """Handles keyboard and mouse events for Market Profile Modal"""
        if not self.is_open or not self.target_market:
            return None

        mkt = self.target_market

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.show_assign_dialog:
                    self.show_assign_dialog = False
                    return "close_assign_dialog"
                if self.show_coin_dialog:
                    self.show_coin_dialog = None
                    return "close_coin_dialog"
                self.close()
                return "close"

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = event.pos

            # 1. Close Button [X]
            if self.close_btn_rect and self.close_btn_rect.collidepoint(mouse_pos):
                self.close()
                return "close"

            # 2. Assign Stall Dialog Handling
            if self.show_assign_dialog:
                if self.close_assign_dlg_btn_rect and self.close_assign_dlg_btn_rect.collidepoint(mouse_pos):
                    self.show_assign_dialog = False
                    return "close_assign_dialog"

                if self.unassign_stall_btn_rect and self.unassign_stall_btn_rect.collidepoint(mouse_pos):
                    mkt.assigned_family_id = None
                    mkt.assigned_household_id = None
                    mkt.owner = "landlord"
                    self.show_assign_dialog = False
                    try:
                        from game.systems.wealth_system import VillageWealthSystem
                        VillageWealthSystem.mark_dirty()
                    except ImportError:
                        pass
                    return "stall_unassigned"

                for fam_id, btn_rect in self.family_assign_btn_rects.items():
                    if btn_rect.collidepoint(mouse_pos):
                        mkt.assigned_family_id = fam_id
                        mkt.assigned_household_id = fam_id
                        mkt.owner = fam_id
                        self.show_assign_dialog = False
                        try:
                            from game.systems.wealth_system import VillageWealthSystem
                            VillageWealthSystem.mark_dirty()
                        except ImportError:
                            pass
                        return f"stall_assigned_{fam_id}"
                return None

            # 3. Coin Deposit / Withdraw Dialog Handling
            if self.show_coin_dialog:
                if self.close_coin_dlg_btn_rect and self.close_coin_dlg_btn_rect.collidepoint(mouse_pos):
                    self.show_coin_dialog = None
                    return "close_coin_dialog"

                action = self.show_coin_dialog  # "deposit" or "withdraw"
                for (denom, amt), btn_rect in self.coin_action_btn_rects.items():
                    if btn_rect.collidepoint(mouse_pos):
                        if action == "deposit":
                            # Transfer from Landlord resources to Market currency
                            ll_avail = 0
                            if resources:
                                ll_avail = resources.get(denom, 0)
                            dep_amt = min(amt, ll_avail)
                            if dep_amt > 0:
                                if resources:
                                    resources[denom] = max(0, resources.get(denom, 0) - dep_amt)
                                mkt_curr = normalize_wallet(mkt.currency)
                                mkt_curr[denom] += dep_amt
                                mkt.currency = mkt_curr
                                if stockpile_manager:
                                    stockpile_manager.refresh_stacks(resources, None)
                                return f"coin_deposited_{dep_amt}_{denom}"
                        elif action == "withdraw":
                            # Transfer from Market currency to Landlord resources
                            mkt_curr = normalize_wallet(mkt.currency)
                            mkt_avail = mkt_curr.get(denom, 0)
                            with_amt = min(amt, mkt_avail)
                            if with_amt > 0:
                                mkt_curr[denom] -= with_amt
                                mkt.currency = mkt_curr
                                if resources is not None:
                                    resources[denom] = resources.get(denom, 0) + with_amt
                                if stockpile_manager:
                                    stockpile_manager.refresh_stacks(resources, None)
                                return f"coin_withdrawn_{with_amt}_{denom}"
                return None

            # 4. Open Assign Stall Dialog
            if self.assign_stall_btn_rect and self.assign_stall_btn_rect.collidepoint(mouse_pos):
                self.show_assign_dialog = True
                return "open_assign_dialog"

            # 5. Open Deposit / Withdraw Dialogs
            if self.deposit_coin_btn_rect and self.deposit_coin_btn_rect.collidepoint(mouse_pos):
                self.show_coin_dialog = "deposit"
                return "open_deposit_dialog"

            if self.withdraw_coin_btn_rect and self.withdraw_coin_btn_rect.collidepoint(mouse_pos):
                self.show_coin_dialog = "withdraw"
                return "open_withdraw_dialog"

            # 6. Tab Navigation
            if self.tab_goods_rect and self.tab_goods_rect.collidepoint(mouse_pos):
                self.active_tab = "goods"
                return "tab_goods"

            if self.tab_alloc_rect and self.tab_alloc_rect.collidepoint(mouse_pos):
                self.active_tab = "allocation"
                return "tab_allocation"

            # 7. Item Allocation Controls (Tab 2)
            if self.active_tab == "allocation":
                allocs = mkt.item_allocations
                for it_name, rect in self.alloc_dec_btns.items():
                    if rect.collidepoint(mouse_pos):
                        allocs[it_name] = max(0, allocs.get(it_name, 50) - 10)
                        return f"alloc_dec_{it_name}"

                for it_name, rect in self.alloc_inc_btns.items():
                    if rect.collidepoint(mouse_pos):
                        allocs[it_name] = min(100, allocs.get(it_name, 50) + 10)
                        return f"alloc_inc_{it_name}"

                for it_name, rect in self.alloc_min_btns.items():
                    if rect.collidepoint(mouse_pos):
                        allocs[it_name] = 0
                        return f"alloc_min_{it_name}"

                for it_name, rect in self.alloc_max_btns.items():
                    if rect.collidepoint(mouse_pos):
                        allocs[it_name] = 100
                        return f"alloc_max_{it_name}"

            # 8. Goods & Pricing Controls (Tab 1)
            elif self.active_tab == "goods":
                # Manual Price Tuning (Gold, Silver, Copper)
                for it_name, rect in self.price_g_dec_btns.items():
                    if rect.collidepoint(mouse_pos):
                        cur_p = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 1))
                        mkt.prices[it_name] = max(1, cur_p - 100)
                        return f"price_decreased_gold_{it_name}"

                for it_name, rect in self.price_g_inc_btns.items():
                    if rect.collidepoint(mouse_pos):
                        cur_p = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 1))
                        mkt.prices[it_name] = cur_p + 100
                        return f"price_increased_gold_{it_name}"

                for it_name, rect in self.price_s_dec_btns.items():
                    if rect.collidepoint(mouse_pos):
                        cur_p = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 1))
                        mkt.prices[it_name] = max(1, cur_p - 10)
                        return f"price_decreased_silver_{it_name}"

                for it_name, rect in self.price_s_inc_btns.items():
                    if rect.collidepoint(mouse_pos):
                        cur_p = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 1))
                        mkt.prices[it_name] = cur_p + 10
                        return f"price_increased_silver_{it_name}"

                for it_name, rect in self.price_c_dec_btns.items():
                    if rect.collidepoint(mouse_pos):
                        cur_p = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 1))
                        mkt.prices[it_name] = max(1, cur_p - 1)
                        return f"price_decreased_{it_name}"

                for it_name, rect in self.price_c_inc_btns.items():
                    if rect.collidepoint(mouse_pos):
                        cur_p = mkt.prices.get(it_name, DEFAULT_ITEM_PRICES.get(it_name, 1))
                        mkt.prices[it_name] = cur_p + 1
                        return f"price_increased_{it_name}"

                # Physical Stock Restocking
                for it_name, rect in self.stock_dep_btns.items():
                    if rect.collidepoint(mouse_pos):
                        if servant_manager:
                            order = servant_manager.add_restock_order(
                                mkt, it_name, 10,
                                stockpile_manager=stockpile_manager,
                                resources=resources
                            )
                            if order:
                                return f"restock_order_created_{it_name}"
                            return f"restock_no_stock_{it_name}"
                        else:
                            # Standalone test fallback
                            target_res = "Food" if it_name in ("Potato", "potato") else it_name
                            avail_stock = resources.get(target_res, resources.get(it_name, 0)) if resources else 0
                            transfer_amt = min(10, avail_stock)
                            if transfer_amt > 0 and resources:
                                k = target_res if target_res in resources else it_name
                                resources[k] = max(0, resources[k] - transfer_amt)
                                mkt.inventory[it_name] = mkt.inventory.get(it_name, 0) + transfer_amt
                                return f"stock_deposited_{it_name}"

                # Stock Withdrawal
                for it_name, rect in self.stock_with_btns.items():
                    if rect.collidepoint(mouse_pos):
                        in_market = mkt.inventory.get(it_name, 0)
                        withdraw_amt = min(10, in_market)
                        if withdraw_amt > 0:
                            mkt.inventory[it_name] -= withdraw_amt
                            if mkt.inventory[it_name] <= 0:
                                del mkt.inventory[it_name]
                            target_res = "Food" if it_name in ("Potato", "potato") else it_name
                            if resources is not None:
                                k = target_res if target_res in resources else it_name
                                resources[k] = resources.get(k, 0) + withdraw_amt
                            if stockpile_manager and getattr(mkt, "tiles", None):
                                t0 = next(iter(mkt.tiles))
                                stockpile_manager.drop_resource(target_res, withdraw_amt, t0[0], t0[1], owner_type="landlord")
                                stockpile_manager.refresh_stacks(resources, None)
                            return f"stock_withdrawn_{it_name}"

                # Pagination controls for tradeable items
                if self.prev_page_btn_rect and self.prev_page_btn_rect.collidepoint(mouse_pos):
                    self.goods_page = max(0, getattr(self, "goods_page", 0) - 1)
                    return "market_prev_page"

                if self.next_page_btn_rect and self.next_page_btn_rect.collidepoint(mouse_pos):
                    self.goods_page = getattr(self, "goods_page", 0) + 1
                    return "market_next_page"

        return None

    def draw(self, surface, resources=None, stockpile_manager=None, servant_manager=None, villager_manager=None, furniture_manager=None):
        if not self.is_open or not self.target_market:
            return

        self._ensure_fonts()
        mkt = self.target_market
        sw = surface.get_width()
        sh = surface.get_height()
        m_pos = pygame.mouse.get_pos()

        # 1. Dark Backdrop Overlay
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        # 2. Main Modal Box
        mx = (sw - self.modal_w) // 2
        my = (sh - self.modal_h) // 2
        modal_rect = pygame.Rect(mx, my, self.modal_w, self.modal_h)

        pygame.draw.rect(surface, COLOR_MODAL_BG, modal_rect, border_radius=10)
        pygame.draw.rect(surface, (245, 158, 11), modal_rect, width=2, border_radius=10)

        # 3. Header: Title & Close Button
        header_y = my + 16
        title_txt = f"{getattr(mkt, 'name', 'Village Market')} — Market Management"
        surface.blit(self.font_title.render(title_txt, True, (250, 204, 21)), (mx + 24, header_y))

        # Close [X] Button
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - 38, my + 14, 26, 26)
        c_hover = self.close_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (220, 38, 38) if c_hover else (51, 65, 85), self.close_btn_rect, border_radius=5)
        x_lbl = self.font_sub.render("X", True, (255, 255, 255))
        surface.blit(x_lbl, (self.close_btn_rect.centerx - x_lbl.get_width() // 2, self.close_btn_rect.centery - x_lbl.get_height() // 2))

        # 4. Household Assignment Status & 'Assign Stall To' Button
        fam_assigned_id = getattr(mkt, "assigned_family_id", None)
        assigned_fam = None
        if fam_assigned_id and villager_manager:
            assigned_fam = next((f for f in getattr(villager_manager, "families", []) if f.id == fam_assigned_id), None)

        status_y = header_y + 26
        if assigned_fam:
            assign_txt = f"Stall Assigned To: The {assigned_fam.surname} Family"
            status_col = (34, 197, 94)
        else:
            assign_txt = "Stall Assigned To: Unassigned (Controlled by Landlord)"
            status_col = (148, 163, 184)

        surface.blit(self.font_body.render(assign_txt, True, status_col), (mx + 24, status_y + 4))

        # 'Assign Stall To' Button
        self.assign_stall_btn_rect = pygame.Rect(mx + self.modal_w - 180, status_y, 142, 26)
        as_hov = self.assign_stall_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (14, 116, 144) if as_hov else (15, 23, 42), self.assign_stall_btn_rect, border_radius=4)
        pygame.draw.rect(surface, (56, 189, 248), self.assign_stall_btn_rect, width=1, border_radius=4)
        as_lbl = self.font_badge.render("Assign Stall To", True, (255, 255, 255))
        surface.blit(as_lbl, (self.assign_stall_btn_rect.centerx - as_lbl.get_width() // 2, self.assign_stall_btn_rect.centery - as_lbl.get_height() // 2))

        # 5. Tab Buttons: [Market Goods & Pricing] and [Household Allocation Settings]
        tab_y = status_y + 32
        self.tab_goods_rect = pygame.Rect(mx + 24, tab_y, 220, 28)
        self.tab_alloc_rect = pygame.Rect(mx + 252, tab_y, 240, 28)

        # Tab 1: Goods & Pricing
        tg_active = (self.active_tab == "goods")
        pygame.draw.rect(surface, (59, 130, 246) if tg_active else (30, 41, 59), self.tab_goods_rect, border_radius=5)
        pygame.draw.rect(surface, (96, 165, 250) if tg_active else (51, 65, 85), self.tab_goods_rect, width=1, border_radius=5)
        tg_txt = self.font_sub.render("Stall Goods & Pricing", True, (255, 255, 255) if tg_active else (148, 163, 184))
        surface.blit(tg_txt, (self.tab_goods_rect.centerx - tg_txt.get_width() // 2, self.tab_goods_rect.centery - tg_txt.get_height() // 2))

        # Tab 2: Allocation Settings
        ta_active = (self.active_tab == "allocation")
        pygame.draw.rect(surface, (59, 130, 246) if ta_active else (30, 41, 59), self.tab_alloc_rect, border_radius=5)
        pygame.draw.rect(surface, (96, 165, 250) if ta_active else (51, 65, 85), self.tab_alloc_rect, width=1, border_radius=5)
        ta_txt = self.font_sub.render("Item Allocation Settings", True, (255, 255, 255) if ta_active else (148, 163, 184))
        surface.blit(ta_txt, (self.tab_alloc_rect.centerx - ta_txt.get_width() // 2, self.tab_alloc_rect.centery - ta_txt.get_height() // 2))

        # 6. STATS & TREASURY BAR: Capacity, Coin Balances, Deposit Coin & Withdraw Coin
        stats_y = tab_y + 34
        stats_rect = pygame.Rect(mx + 24, stats_y, self.modal_w - 48, 56)
        pygame.draw.rect(surface, (24, 34, 52), stats_rect, border_radius=6)
        pygame.draw.rect(surface, (71, 85, 105), stats_rect, width=1, border_radius=6)

        # Capacity Badge (UNLIMITED)
        cap_badge_rect = pygame.Rect(stats_rect.x + 12, stats_rect.y + 12, 140, 32)
        pygame.draw.rect(surface, (16, 185, 129), cap_badge_rect, border_radius=5)
        cap_lbl = self.font_sub.render("Storage: ∞ UNLIMITED", True, (255, 255, 255))
        surface.blit(cap_lbl, (cap_badge_rect.centerx - cap_lbl.get_width() // 2, cap_badge_rect.centery - cap_lbl.get_height() // 2))

        # Market Currency Treasury (Gold, Silver, Copper)
        curr = normalize_wallet(getattr(mkt, "currency", {}))
        total_mkt_c = to_copper(curr)

        t_x = cap_badge_rect.right + 16
        t_y = stats_rect.y + 9
        surface.blit(self.font_badge.render("MARKET TREASURY:", True, COLOR_TEXT_MUTED), (t_x, t_y))

        bal_y = t_y + 15
        surface.blit(self.font_sub.render(f"{curr['Gold']} Gold", True, (250, 204, 21)), (t_x, bal_y))
        surface.blit(self.font_sub.render(f"{curr['Silver']} Silver", True, (203, 213, 225)), (t_x + 85, bal_y))
        surface.blit(self.font_sub.render(f"{curr['Copper']} Copper", True, (184, 115, 51)), (t_x + 175, bal_y))
        surface.blit(self.font_body.render(f"({total_mkt_c}c)", True, COLOR_TEXT_MUTED), (t_x + 265, bal_y + 1))

        # Deposit Coin & Withdraw Coin Buttons
        self.deposit_coin_btn_rect = pygame.Rect(stats_rect.right - 180, stats_rect.y + 14, 82, 28)
        dep_hov = self.deposit_coin_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (22, 101, 52) if dep_hov else (20, 83, 45), self.deposit_coin_btn_rect, border_radius=4)
        pygame.draw.rect(surface, (74, 222, 128), self.deposit_coin_btn_rect, width=1, border_radius=4)
        surface.blit(self.font_badge.render("+Deposit", True, (255, 255, 255)), (self.deposit_coin_btn_rect.x + 14, self.deposit_coin_btn_rect.y + 8))

        self.withdraw_coin_btn_rect = pygame.Rect(stats_rect.right - 92, stats_rect.y + 14, 82, 28)
        with_hov = self.withdraw_coin_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (153, 27, 27) if with_hov else (127, 29, 29), self.withdraw_coin_btn_rect, border_radius=4)
        pygame.draw.rect(surface, (248, 113, 113), self.withdraw_coin_btn_rect, width=1, border_radius=4)
        surface.blit(self.font_badge.render("-Withdraw", True, (255, 255, 255)), (self.withdraw_coin_btn_rect.x + 12, self.withdraw_coin_btn_rect.y + 8))

        # -------------------------------------------------------------
        # TAB CONTENT
        # -------------------------------------------------------------
        content_y = stats_rect.bottom + 14

        if self.active_tab == "allocation":
            # ---------------------------------------------------------
            # TAB 2: HOUSEHOLD ITEM ALLOCATION SETTINGS
            # ---------------------------------------------------------
            self._draw_allocation_tab(surface, mx, content_y, mkt, assigned_fam, furniture_manager, villager_manager, m_pos)
        else:
            # ---------------------------------------------------------
            # TAB 1: GOODS, SELLING PRICES & PHYSICAL STOCK
            # ---------------------------------------------------------
            self._draw_goods_tab(surface, mx, content_y, mkt, servant_manager, resources, stockpile_manager, m_pos)

        # 7. ASSIGN STALL DIALOG OVERLAY (if active)
        if self.show_assign_dialog:
            self._draw_assign_dialog(surface, mx, my, mkt, villager_manager, m_pos)

        # 8. COIN DEPOSIT / WITHDRAW DIALOG OVERLAY (if active)
        if self.show_coin_dialog:
            self._draw_coin_dialog(surface, mx, my, mkt, resources, m_pos)

    def _draw_goods_tab(self, surface, mx, list_y, mkt, servant_manager, resources, stockpile_manager, m_pos):
        """Renders Market Goods list with Selling Prices and Restock controls"""
        sec_title = "MARKET GOODS, SELLING PRICES & PHYSICAL RESTOCKING:"
        surface.blit(self.font_sub.render(sec_title, True, COLOR_TEXT_TITLE), (mx + 24, list_y))

        th_y = list_y + 22
        pygame.draw.rect(surface, (30, 41, 59), (mx + 24, th_y, self.modal_w - 48, 24), border_radius=4)
        surface.blit(self.font_badge.render("ITEM", True, COLOR_TEXT_MUTED), (mx + 36, th_y + 4))
        surface.blit(self.font_badge.render("MARKET STOCK", True, COLOR_TEXT_MUTED), (mx + 160, th_y + 4))
        surface.blit(self.font_badge.render("SELLING PRICE", True, COLOR_TEXT_MUTED), (mx + 280, th_y + 4))
        surface.blit(self.font_badge.render("PRICE ADJUSTMENT (G / S / C)", True, COLOR_TEXT_MUTED), (mx + 420, th_y + 4))
        surface.blit(self.font_badge.render("MANAGE STOCK", True, COLOR_TEXT_MUTED), (mx + 610, th_y + 4))

        self.price_g_dec_btns.clear()
        self.price_g_inc_btns.clear()
        self.price_s_dec_btns.clear()
        self.price_s_inc_btns.clear()
        self.price_c_dec_btns.clear()
        self.price_c_inc_btns.clear()
        self.stock_dep_btns.clear()
        self.stock_with_btns.clear()

        self.tradeable_items = []
        for it, cat in ITEM_CATEGORIES.items():
            if cat != "CURRENCY" and it[0].isupper() and it not in self.tradeable_items:
                self.tradeable_items.append(it)
        for it in getattr(mkt, "inventory", {}):
            if it not in self.tradeable_items:
                self.tradeable_items.append(it)
        tradeable_items = self.tradeable_items

        items_per_page = 5
        total_pages = max(1, math.ceil(len(tradeable_items) / items_per_page))
        self.goods_page = max(0, min(getattr(self, "goods_page", 0), total_pages - 1))
        page_items = tradeable_items[self.goods_page * items_per_page : (self.goods_page + 1) * items_per_page]

        row_y = th_y + 28
        row_h = 42

        for it_name in page_items:
            stock_qty = mkt.inventory.get(it_name, 0)

            # Selling Price & Buying Price (AGENT 1 & 2)
            active_price = MarketService.get_item_price(it_name, mkt)
            active_price = max(1, int(active_price))
            d_price = from_copper(active_price)

            buy_price = MarketService.get_buying_price(it_name, mkt)
            d_buy = from_copper(buy_price)

            card_rect = pygame.Rect(mx + 24, row_y, self.modal_w - 48, row_h)
            pygame.draw.rect(surface, (15, 23, 42, 220), card_rect, border_radius=6)
            pygame.draw.rect(surface, (51, 65, 85), card_rect, width=1, border_radius=6)

            # Unified Procedural Vector Icon & Name
            draw_item_icon(surface, it_name, mx + 44, row_y + row_h // 2, size=10)
            surface.blit(self.font_sub.render(it_name, True, (241, 245, 249)), (mx + 60, row_y + 11))

            # Stock with transit indicator
            in_transit = 0
            if servant_manager and hasattr(servant_manager, "get_in_transit_for_market"):
                in_transit = servant_manager.get_in_transit_for_market(mkt, it_name)

            stock_str = f"{stock_qty} in stock" if stock_qty > 0 else "OUT OF STOCK"
            if in_transit > 0:
                stock_str += f" (+{in_transit})"
            stock_col = (34, 197, 94) if stock_qty > 0 else ((56, 189, 248) if in_transit > 0 else (239, 68, 68))
            surface.blit(self.font_badge.render(stock_str, True, stock_col), (mx + 160, row_y + 13))

            # Active Selling & Buying Price Displays (Separate values)
            pr_x = mx + 276
            pr_y = row_y + 5
            surface.blit(self.font_badge.render(f"Sell: {d_price['Gold']}g {d_price['Silver']}s {d_price['Copper']}c", True, (250, 204, 21)), (pr_x, pr_y))
            surface.blit(self.font_badge.render(f"Buy:  {d_buy['Gold']}g {d_buy['Silver']}s {d_buy['Copper']}c", True, (148, 163, 184)), (pr_x, pr_y + 15))

            # Price Adjustment Buttons (G / S / C)
            btn_y = row_y + 9
            # Gold
            gm_rect = pygame.Rect(mx + 410, btn_y, 20, 24)
            gp_rect = pygame.Rect(mx + 432, btn_y, 20, 24)
            self.price_g_dec_btns[it_name] = gm_rect
            self.price_g_inc_btns[it_name] = gp_rect
            pygame.draw.rect(surface, (71, 85, 105) if gm_rect.collidepoint(m_pos) else (30, 41, 59), gm_rect, border_radius=3)
            pygame.draw.rect(surface, (250, 204, 21), gm_rect, width=1, border_radius=3)
            surface.blit(self.font_badge.render("-", True, (250, 204, 21)), (gm_rect.x + 6, gm_rect.y + 4))
            pygame.draw.rect(surface, (71, 85, 105) if gp_rect.collidepoint(m_pos) else (30, 41, 59), gp_rect, border_radius=3)
            pygame.draw.rect(surface, (250, 204, 21), gp_rect, width=1, border_radius=3)
            surface.blit(self.font_badge.render("+", True, (250, 204, 21)), (gp_rect.x + 5, gp_rect.y + 4))

            # Silver
            sm_rect = pygame.Rect(mx + 460, btn_y, 20, 24)
            sp_rect = pygame.Rect(mx + 482, btn_y, 20, 24)
            self.price_s_dec_btns[it_name] = sm_rect
            self.price_s_inc_btns[it_name] = sp_rect
            pygame.draw.rect(surface, (71, 85, 105) if sm_rect.collidepoint(m_pos) else (30, 41, 59), sm_rect, border_radius=3)
            pygame.draw.rect(surface, (203, 213, 225), sm_rect, width=1, border_radius=3)
            surface.blit(self.font_badge.render("-", True, (203, 213, 225)), (sm_rect.x + 6, sm_rect.y + 4))
            pygame.draw.rect(surface, (71, 85, 105) if sp_rect.collidepoint(m_pos) else (30, 41, 59), sp_rect, border_radius=3)
            pygame.draw.rect(surface, (203, 213, 225), sp_rect, width=1, border_radius=3)
            surface.blit(self.font_badge.render("+", True, (203, 213, 225)), (sp_rect.x + 5, sp_rect.y + 4))

            # Copper
            cm_rect = pygame.Rect(mx + 510, btn_y, 20, 24)
            cp_rect = pygame.Rect(mx + 532, btn_y, 20, 24)
            self.price_c_dec_btns[it_name] = cm_rect
            self.price_c_inc_btns[it_name] = cp_rect
            pygame.draw.rect(surface, (71, 85, 105) if cm_rect.collidepoint(m_pos) else (30, 41, 59), cm_rect, border_radius=3)
            pygame.draw.rect(surface, (217, 119, 6), cm_rect, width=1, border_radius=3)
            surface.blit(self.font_badge.render("-", True, (217, 119, 6)), (cm_rect.x + 6, cm_rect.y + 4))
            pygame.draw.rect(surface, (71, 85, 105) if cp_rect.collidepoint(m_pos) else (30, 41, 59), cp_rect, border_radius=3)
            pygame.draw.rect(surface, (217, 119, 6), cp_rect, width=1, border_radius=3)
            surface.blit(self.font_badge.render("+", True, (217, 119, 6)), (cp_rect.x + 5, cp_rect.y + 4))

            # Stock Management Buttons: [+ Restock 10] and [- Withdraw 10]
            btn_dep = pygame.Rect(mx + 580, btn_y, 68, 24)
            self.stock_dep_btns[it_name] = btn_dep
            h_dep = btn_dep.collidepoint(m_pos)
            pygame.draw.rect(surface, (37, 99, 235) if h_dep else (30, 58, 138), btn_dep, border_radius=4)
            surface.blit(self.font_badge.render("+Restock", True, (255, 255, 255)), (btn_dep.x + 8, btn_dep.y + 5))

            btn_with = pygame.Rect(mx + 654, btn_y, 68, 24)
            self.stock_with_btns[it_name] = btn_with
            h_with = btn_with.collidepoint(m_pos)
            pygame.draw.rect(surface, (71, 85, 105) if h_with else (51, 65, 85), btn_with, border_radius=4)
            surface.blit(self.font_badge.render("-Withdraw", True, (255, 255, 255)), (btn_with.x + 6, btn_with.y + 5))

            row_y += row_h + 4

        # Bottom Pagination Bar
        page_y = max(row_y + 6, th_y + 28 + (5 * (row_h + 4)))
        self.prev_page_btn_rect = pygame.Rect(mx + 24, page_y, 90, 24)
        self.next_page_btn_rect = pygame.Rect(mx + self.modal_w - 114, page_y, 90, 24)

        prev_hov = self.prev_page_btn_rect.collidepoint(m_pos)
        next_hov = self.next_page_btn_rect.collidepoint(m_pos)

        has_prev = self.goods_page > 0
        has_next = self.goods_page < total_pages - 1

        pygame.draw.rect(surface, (37, 99, 235) if (prev_hov and has_prev) else ((30, 58, 138) if has_prev else (51, 65, 85)), self.prev_page_btn_rect, border_radius=4)
        surface.blit(self.font_badge.render("< Prev", True, (255, 255, 255) if has_prev else (148, 163, 184)), (self.prev_page_btn_rect.centerx - 16, self.prev_page_btn_rect.centery - 6))

        pygame.draw.rect(surface, (37, 99, 235) if (next_hov and has_next) else ((30, 58, 138) if has_next else (51, 65, 85)), self.next_page_btn_rect, border_radius=4)
        surface.blit(self.font_badge.render("Next >", True, (255, 255, 255) if has_next else (148, 163, 184)), (self.next_page_btn_rect.centerx - 16, self.next_page_btn_rect.centery - 6))

        page_str = f"Page {self.goods_page + 1} / {total_pages} ({len(tradeable_items)} Tradeable Items Registered)"
        p_surf = self.font_badge.render(page_str, True, (203, 213, 225))
        surface.blit(p_surf, (mx + (self.modal_w - p_surf.get_width()) // 2, page_y + 4))

    def _draw_allocation_tab(self, surface, mx, list_y, mkt, assigned_fam, furniture_manager, villager_manager, m_pos):
        """Renders Household Item Allocation Settings (% per item with actual chest ownership)"""
        self.alloc_dec_btns.clear()
        self.alloc_inc_btns.clear()
        self.alloc_min_btns.clear()
        self.alloc_max_btns.clear()

        if not assigned_fam:
            # Unassigned state
            info_box = pygame.Rect(mx + 24, list_y + 10, self.modal_w - 48, 140)
            pygame.draw.rect(surface, (24, 34, 52), info_box, border_radius=8)
            pygame.draw.rect(surface, (71, 85, 105), info_box, width=1, border_radius=8)

            surface.blit(self.font_title.render("Stall Not Assigned to a Household", True, (250, 204, 21)), (info_box.x + 20, info_box.y + 20))
            surface.blit(self.font_body.render("This Market stall is currently operated by the Crown (Landlord).", True, (241, 245, 249)), (info_box.x + 20, info_box.y + 50))
            surface.blit(self.font_body.render("Click 'Assign Stall To' above to lease this stall to a peasant household.", True, COLOR_TEXT_MUTED), (info_box.x + 20, info_box.y + 70))
            surface.blit(self.font_body.render("Once assigned, the household can configure sales allocation percentages for their stored items.", True, (148, 163, 184)), (info_box.x + 20, info_box.y + 90))
            return

        # Assigned state: fetch actual household possessions
        possessions = get_household_possessions(assigned_fam.id, furniture_manager, villager_manager)
        allocs = getattr(mkt, "item_allocations", {})

        sec_title = f"SALE ALLOCATION SETTINGS — The {assigned_fam.surname} Family"
        surface.blit(self.font_sub.render(sec_title, True, COLOR_TEXT_TITLE), (mx + 24, list_y))

        sub_desc = "Configure the maximum percentage of each stored item available for sale in this stall:"
        surface.blit(self.font_body.render(sub_desc, True, COLOR_TEXT_MUTED), (mx + 24, list_y + 20))

        th_y = list_y + 40
        pygame.draw.rect(surface, (30, 41, 59), (mx + 24, th_y, self.modal_w - 48, 24), border_radius=4)
        surface.blit(self.font_badge.render("ITEM", True, COLOR_TEXT_MUTED), (mx + 36, th_y + 4))
        surface.blit(self.font_badge.render("OWNED IN CHESTS", True, COLOR_TEXT_MUTED), (mx + 170, th_y + 4))
        surface.blit(self.font_badge.render("SALE ALLOCATION %", True, COLOR_TEXT_MUTED), (mx + 310, th_y + 4))
        surface.blit(self.font_badge.render("MAX ALLOCATED / KEPT", True, COLOR_TEXT_MUTED), (mx + 530, th_y + 4))

        if not possessions:
            empty_box = pygame.Rect(mx + 24, th_y + 30, self.modal_w - 48, 60)
            pygame.draw.rect(surface, (15, 23, 42), empty_box, border_radius=6)
            surface.blit(self.font_body.render(f"— The {assigned_fam.surname} Family currently has 0 goods stored in household chests —", True, (148, 163, 184)), (empty_box.centerx - 200, empty_box.centery - 8))
            return

        row_y = th_y + 28
        row_h = 40

        for it_data in possessions[:5]:
            it_name = it_data["name"]
            owned_cnt = it_data["count"]
            pct = allocs.get(it_name, 50)
            max_for_sale = min(owned_cnt, int(math.floor(owned_cnt * (pct / 100.0))))
            kept_in_chest = owned_cnt - max_for_sale

            card_rect = pygame.Rect(mx + 24, row_y, self.modal_w - 48, row_h)
            pygame.draw.rect(surface, (15, 23, 42, 220), card_rect, border_radius=6)
            pygame.draw.rect(surface, (51, 65, 85), card_rect, width=1, border_radius=6)

            # Icon & Name
            draw_item_icon(surface, it_name, mx + 44, row_y + row_h // 2, size=10)
            surface.blit(self.font_sub.render(it_name, True, (241, 245, 249)), (mx + 60, row_y + 11))

            # Owned Quantity
            surface.blit(self.font_badge.render(f"{owned_cnt} Owned", True, (34, 197, 94)), (mx + 170, row_y + 13))

            # Percentage Controls: [0%] [-10%] [ 50% ] [+10%] [100%]
            btn_cy = row_y + 8

            # [0%]
            min_r = pygame.Rect(mx + 300, btn_cy, 28, 24)
            self.alloc_min_btns[it_name] = min_r
            pygame.draw.rect(surface, (51, 65, 85) if min_r.collidepoint(m_pos) else (30, 41, 59), min_r, border_radius=3)
            surface.blit(self.font_badge.render("0%", True, (148, 163, 184)), (min_r.x + 4, min_r.y + 4))

            # [-10%]
            dec_r = pygame.Rect(mx + 332, btn_cy, 28, 24)
            self.alloc_dec_btns[it_name] = dec_r
            pygame.draw.rect(surface, (71, 85, 105) if dec_r.collidepoint(m_pos) else (30, 41, 59), dec_r, border_radius=3)
            surface.blit(self.font_sub.render("-", True, (255, 255, 255)), (dec_r.x + 9, dec_r.y + 3))

            # Value Display
            val_r = pygame.Rect(mx + 364, btn_cy, 52, 24)
            pygame.draw.rect(surface, (15, 23, 42), val_r, border_radius=3)
            pygame.draw.rect(surface, (96, 165, 250), val_r, width=1, border_radius=3)
            pct_txt = self.font_sub.render(f"{pct}%", True, (250, 204, 21))
            surface.blit(pct_txt, (val_r.centerx - pct_txt.get_width() // 2, val_r.centery - pct_txt.get_height() // 2))

            # [+10%]
            inc_r = pygame.Rect(mx + 420, btn_cy, 28, 24)
            self.alloc_inc_btns[it_name] = inc_r
            pygame.draw.rect(surface, (71, 85, 105) if inc_r.collidepoint(m_pos) else (30, 41, 59), inc_r, border_radius=3)
            surface.blit(self.font_sub.render("+", True, (255, 255, 255)), (inc_r.x + 8, inc_r.y + 3))

            # [100%]
            max_r = pygame.Rect(mx + 452, btn_cy, 38, 24)
            self.alloc_max_btns[it_name] = max_r
            pygame.draw.rect(surface, (51, 65, 85) if max_r.collidepoint(m_pos) else (30, 41, 59), max_r, border_radius=3)
            surface.blit(self.font_badge.render("Max", True, (148, 163, 184)), (max_r.x + 6, max_r.y + 4))

            # Resulting Allocation Summary
            res_txt = f"{max_for_sale} for sale  ({kept_in_chest} kept)"
            surface.blit(self.font_sub.render(res_txt, True, (250, 204, 21) if max_for_sale > 0 else (148, 163, 184)), (mx + 530, row_y + 11))

            row_y += row_h + 4

    def _draw_assign_dialog(self, surface, mx, my, mkt, villager_manager, m_pos):
        """Displays modal dialog for assigning stall to a peasant household"""
        dlg_w = 460
        dlg_h = 320
        dlg_x = mx + (self.modal_w - dlg_w) // 2
        dlg_y = my + (self.modal_h - dlg_h) // 2

        pygame.draw.rect(surface, (15, 23, 42), (dlg_x, dlg_y, dlg_w, dlg_h), border_radius=10)
        pygame.draw.rect(surface, (56, 189, 248), (dlg_x, dlg_y, dlg_w, dlg_h), width=2, border_radius=10)

        # Title
        surface.blit(self.font_title.render("Assign Stall To Household", True, (250, 204, 21)), (dlg_x + 20, dlg_y + 16))
        surface.blit(self.font_body.render("Select a peasant family to operate this market stall:", True, COLOR_TEXT_MUTED), (dlg_x + 20, dlg_y + 42))

        # Close X
        self.close_assign_dlg_btn_rect = pygame.Rect(dlg_x + dlg_w - 32, dlg_y + 14, 22, 22)
        pygame.draw.rect(surface, (51, 65, 85), self.close_assign_dlg_btn_rect, border_radius=4)
        surface.blit(self.font_badge.render("X", True, (255, 255, 255)), (self.close_assign_dlg_btn_rect.x + 6, self.close_assign_dlg_btn_rect.y + 3))

        self.family_assign_btn_rects.clear()
        fam_list = getattr(villager_manager, "families", []) if villager_manager else []

        f_y = dlg_y + 70
        for fam in fam_list[:4]:
            f_rect = pygame.Rect(dlg_x + 20, f_y, dlg_w - 40, 38)
            is_cur = (getattr(mkt, "assigned_family_id", None) == fam.id)
            pygame.draw.rect(surface, (30, 58, 138) if is_cur else (30, 41, 59), f_rect, border_radius=6)
            pygame.draw.rect(surface, (56, 189, 248) if is_cur else (51, 65, 85), f_rect, width=1, border_radius=6)

            surface.blit(self.font_sub.render(f"The {fam.surname} Family", True, (255, 255, 255)), (f_rect.x + 12, f_rect.y + 10))
            surface.blit(self.font_badge.render(f"({len(fam.members)} members)", True, (148, 163, 184)), (f_rect.x + 180, f_rect.y + 12))

            btn_a = pygame.Rect(f_rect.right - 90, f_rect.y + 7, 80, 24)
            self.family_assign_btn_rects[fam.id] = btn_a
            hov = btn_a.collidepoint(m_pos)
            pygame.draw.rect(surface, (22, 101, 52) if hov else (20, 83, 45), btn_a, border_radius=4)
            a_lbl = "Assigned" if is_cur else "Assign"
            surface.blit(self.font_badge.render(a_lbl, True, (255, 255, 255)), (btn_a.x + 16, btn_a.y + 5))

            f_y += 44

        # Bottom: Unassign button
        self.unassign_stall_btn_rect = pygame.Rect(dlg_x + 20, dlg_y + dlg_h - 44, 200, 30)
        u_hov = self.unassign_stall_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (127, 29, 29) if u_hov else (153, 27, 27), self.unassign_stall_btn_rect, border_radius=5)
        surface.blit(self.font_badge.render("Unassign (Revert to Crown)", True, (255, 255, 255)), (self.unassign_stall_btn_rect.x + 14, self.unassign_stall_btn_rect.y + 7))

    def _draw_coin_dialog(self, surface, mx, my, mkt, resources, m_pos):
        """Displays modal dialog for depositing or withdrawing actual coins"""
        action = self.show_coin_dialog  # "deposit" or "withdraw"
        dlg_w = 420
        dlg_h = 240
        dlg_x = mx + (self.modal_w - dlg_w) // 2
        dlg_y = my + (self.modal_h - dlg_h) // 2

        pygame.draw.rect(surface, (15, 23, 42), (dlg_x, dlg_y, dlg_w, dlg_h), border_radius=10)
        pygame.draw.rect(surface, (245, 158, 11), (dlg_x, dlg_y, dlg_w, dlg_h), width=2, border_radius=10)

        # Title
        t_str = "Deposit Coins to Market" if action == "deposit" else "Withdraw Coins from Market"
        surface.blit(self.font_title.render(t_str, True, (250, 204, 21)), (dlg_x + 20, dlg_y + 16))

        # Close X
        self.close_coin_dlg_btn_rect = pygame.Rect(dlg_x + dlg_w - 32, dlg_y + 14, 22, 22)
        pygame.draw.rect(surface, (51, 65, 85), self.close_coin_dlg_btn_rect, border_radius=4)
        surface.blit(self.font_badge.render("X", True, (255, 255, 255)), (self.close_coin_dlg_btn_rect.x + 6, self.close_coin_dlg_btn_rect.y + 3))

        # Current balances
        mkt_curr = normalize_wallet(mkt.currency)
        ll_curr = {"Copper": resources.get("Copper", 0) if resources else 0,
                   "Silver": resources.get("Silver", 0) if resources else 0,
                   "Gold": resources.get("Gold", 0) if resources else 0}

        if action == "deposit":
            src_str = f"Available in Crown Treasury: {ll_curr['Gold']}g, {ll_curr['Silver']}s, {ll_curr['Copper']}c"
        else:
            src_str = f"Available in Market Treasury: {mkt_curr['Gold']}g, {mkt_curr['Silver']}s, {mkt_curr['Copper']}c"
        surface.blit(self.font_body.render(src_str, True, (148, 163, 184)), (dlg_x + 20, dlg_y + 44))

        self.coin_action_btn_rects.clear()

        # Quick action buttons
        denoms = [("Copper", 10), ("Copper", 50), ("Silver", 1), ("Silver", 5), ("Gold", 1), ("Gold", 5)]
        btn_y = dlg_y + 75
        col_w = 114
        row_h = 32

        for idx, (denom, amt) in enumerate(denoms):
            c_idx = idx % 3
            r_idx = idx // 3
            bx = dlg_x + 20 + c_idx * (col_w + 14)
            by = btn_y + r_idx * (row_h + 12)

            btn_rect = pygame.Rect(bx, by, col_w, row_h)
            self.coin_action_btn_rects[(denom, amt)] = btn_rect

            # Check availability
            avail = ll_curr.get(denom, 0) if action == "deposit" else mkt_curr.get(denom, 0)
            can_act = avail >= amt

            b_hov = btn_rect.collidepoint(m_pos) and can_act
            bg_col = (22, 101, 52) if (b_hov and action == "deposit") else ((127, 29, 29) if b_hov else (30, 41, 59))
            if not can_act:
                bg_col = (20, 25, 35)

            pygame.draw.rect(surface, bg_col, btn_rect, border_radius=4)
            pygame.draw.rect(surface, (96, 165, 250) if can_act else (51, 65, 85), btn_rect, width=1, border_radius=4)

            draw_item_icon(surface, f"{denom} Coin", bx + 16, by + 16, size=7)
            prefix = "+" if action == "deposit" else "-"
            txt = f"{prefix}{amt} {denom[:4]}"
            t_col = (255, 255, 255) if can_act else (100, 116, 139)
            surface.blit(self.font_badge.render(txt, True, t_col), (bx + 32, by + 8))

        # Bottom note
        surface.blit(self.font_badge.render("Coins are physically transferred between treasuries without value loss.", True, COLOR_TEXT_MUTED), (dlg_x + 20, dlg_y + dlg_h - 26))
