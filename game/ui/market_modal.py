"""
Market Profile Modal (AGENT 2)
Displays landlord & household market stall management:
- Household Stall Assignment ('Assign Stall To')
- One household sales cap applied to goods in household storage
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
    MARKET_TRADEABLE_ITEMS,
    MARKET_QUANTITY_DEFAULT,
    MARKET_QUANTITY_MAX,
    MARKET_CURRENCY_DENOMINATIONS,
    MARKET_PERCENT_STEP,
    MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT,
    TILE_SIZE,
)
from game.systems.currency import (
    to_copper,
    from_copper,
    normalize_wallet,
    canonical_denomination
)
from game.systems.market_service import MarketService
from game.systems.household_stall_system import HouseholdStallSystem
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
        self.active_tab = "goods"
        self.tab_goods_rect = None

        # Dialog States
        self.show_assign_dialog = False
        self.show_coin_dialog = None  # None | "deposit" | "withdraw"
        self.show_item_picker = False
        self.item_picker_rects = {}
        self.add_item_btn_rect = None
        self.stock_quantity_rects = {}
        self.quantity_values = {}
        self.focused_quantity = None
        self.household_percent_dec_rect = None
        self.household_percent_inc_rect = None
        self.status_message = None

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
        self.coin_quantity_rects = {}
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
            self.status_message = None

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
            if not isinstance(getattr(market_building, "sale_items", None), list):
                market_building.sale_items = [item for item in market_building.inventory if item in MARKET_TRADEABLE_ITEMS]
            if not hasattr(market_building, "household_sale_percent"):
                market_building.household_sale_percent = MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT
            if not hasattr(market_building, "household_sale_limits"):
                market_building.household_sale_limits = {}

    def close(self):
        self.is_open = False
        self.target_market = None
        self.show_assign_dialog = False
        self.show_coin_dialog = None
        self.show_item_picker = False
        self.focused_quantity = None

    def handle_event(self, event, resources=None, stockpile_manager=None, servant_manager=None, villager_manager=None, furniture_manager=None):
        """Handles keyboard and mouse events for Market Profile Modal"""
        if not self.is_open or not self.target_market:
            return None

        mkt = self.target_market

        if event.type == pygame.KEYDOWN:
            if self.focused_quantity is not None:
                current = self.quantity_values.get(self.focused_quantity, "")
                if event.key == pygame.K_BACKSPACE:
                    self.quantity_values[self.focused_quantity] = current[:-1]
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                    self.focused_quantity = None
                elif event.unicode.isdigit() and len(current) < len(str(MARKET_QUANTITY_MAX)):
                    self.quantity_values[self.focused_quantity] = current + event.unicode
                return None
            if event.key == pygame.K_ESCAPE:
                if self.show_item_picker:
                    self.show_item_picker = False
                    return "close_item_picker"
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

            if self.show_item_picker:
                for item_name, rect in self.item_picker_rects.items():
                    if rect.collidepoint(mouse_pos):
                        if item_name not in mkt.sale_items:
                            mkt.sale_items.append(item_name)
                            mkt.prices.setdefault(item_name, DEFAULT_ITEM_PRICES.get(item_name, 1))
                        self.show_item_picker = False
                        return f"market_item_added_{item_name}"
                self.show_item_picker = False
                return None

            if not self.show_assign_dialog and not self.show_coin_dialog and self.add_item_btn_rect and self.add_item_btn_rect.collidepoint(mouse_pos):
                self.show_item_picker = True
                self.focused_quantity = None
                return "open_item_picker"

            if not self.show_assign_dialog and not self.show_coin_dialog and self.household_percent_dec_rect and self.household_percent_dec_rect.collidepoint(mouse_pos):
                mkt.household_sale_percent = max(0, mkt.household_sale_percent - MARKET_PERCENT_STEP)
                mkt.household_sale_limits = {}
                return "household_sale_percent_decreased"
            if not self.show_assign_dialog and not self.show_coin_dialog and self.household_percent_inc_rect and self.household_percent_inc_rect.collidepoint(mouse_pos):
                mkt.household_sale_percent = min(100, mkt.household_sale_percent + MARKET_PERCENT_STEP)
                mkt.household_sale_limits = {}
                return "household_sale_percent_increased"
            # 2. Assign Stall Dialog Handling
            if self.show_assign_dialog:
                if self.close_assign_dlg_btn_rect and self.close_assign_dlg_btn_rect.collidepoint(mouse_pos):
                    self.show_assign_dialog = False
                    return "close_assign_dialog"

                if self.unassign_stall_btn_rect and self.unassign_stall_btn_rect.collidepoint(mouse_pos):
                    mkt.assigned_family_id = None
                    mkt.assigned_household_id = None
                    mkt.owner = "landlord"
                    mkt.household_sale_limits = {}
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
                        mkt.household_sale_limits = {}
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

                for denom, rect in self.coin_quantity_rects.items():
                    if rect.collidepoint(mouse_pos):
                        self.focused_quantity = f"coin:{denom}"
                        self.quantity_values.setdefault(self.focused_quantity, str(MARKET_QUANTITY_DEFAULT))
                        return None

                action = self.show_coin_dialog  # "deposit" or "withdraw"
                for (denom, coin_action), btn_rect in self.coin_action_btn_rects.items():
                    if btn_rect.collidepoint(mouse_pos):
                        amount = self._get_quantity(f"coin:{denom}")
                        if amount <= 0:
                            self.status_message = "Enter a quantity greater than zero."
                            return "coin_invalid_quantity"
                        if action == "deposit" and servant_manager:
                            order = servant_manager.add_restock_order(mkt, denom, amount, stockpile_manager=stockpile_manager, resources=resources)
                            if order:
                                self.status_message = f"Servant order created for {order['amount']} {denom}."
                                return f"coin_deposit_order_{denom}_{order['amount']}"
                            self.status_message = "No Goods in landlord storage."
                            return f"coin_no_stock_{denom}"
                        if action == "withdraw" and stockpile_manager:
                            market_wallet = normalize_wallet(mkt.currency)
                            actual = min(amount, market_wallet.get(denom, 0))
                            if actual > 0:
                                market_wallet[denom] -= actual
                                mkt.currency = market_wallet
                                market_center = mkt.get_center_world(TILE_SIZE)
                                approach = mkt.get_approach_point(market_center, TILE_SIZE, bm=None)
                                drop_tile = (int(math.floor(approach[0] / TILE_SIZE)), int(math.floor(approach[1] / TILE_SIZE)))
                                stockpile_manager.drop_resource(denom, actual, drop_tile[0], drop_tile[1], owner_type="landlord")
                                stockpile_manager.refresh_stacks(resources, None)
                                self.status_message = f"Dropped {actual} {denom} near the market for servant hauling."
                                return f"coin_withdrawn_{actual}_{denom}"
                            self.status_message = f"Only {market_wallet.get(denom, 0)} {denom} available in market."
                        elif action == "deposit":
                            self.status_message = "No servant available to carry the deposit."
                return None

            for item_name, rect in self.stock_quantity_rects.items():
                if rect.collidepoint(mouse_pos):
                    self.focused_quantity = item_name
                    self.quantity_values.setdefault(item_name, str(MARKET_QUANTITY_DEFAULT))
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

            # Goods rows are the only market management view.
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
                    amount = self._get_quantity(it_name)
                    if amount <= 0:
                        self.status_message = "Enter a quantity greater than zero."
                        return "restock_invalid_quantity"
                    if getattr(mkt, "assigned_family_id", None):
                        queued = HouseholdStallSystem.request_goods_restock(mkt, it_name, amount, furniture_manager)
                        if queued:
                            self.status_message = f"Household restock queued for {queued} {it_name}."
                            return f"household_restock_order_{it_name}"
                        self.status_message = "No Goods available from household storage."
                        return f"restock_no_stock_{it_name}"
                    if servant_manager:
                        order = servant_manager.add_restock_order(
                            mkt, it_name, amount,
                            stockpile_manager=stockpile_manager,
                            resources=resources
                        )
                        if order:
                            self.status_message = f"Servant order created for {order['amount']} {it_name}."
                            return f"restock_order_created_{it_name}"
                        self.status_message = "No Goods in landlord storage."
                        return f"restock_no_stock_{it_name}"
                    else:
                        self.status_message = "No servant available to carry the goods."

            # Stock Withdrawal
            for it_name, rect in self.stock_with_btns.items():
                if rect.collidepoint(mouse_pos):
                    in_market = mkt.inventory.get(it_name, 0)
                    withdraw_amt = min(self._get_quantity(it_name), in_market)
                    if withdraw_amt > 0:
                        mkt.inventory[it_name] -= withdraw_amt
                        if mkt.inventory[it_name] <= 0:
                            del mkt.inventory[it_name]
                            from game.systems.market_pricing import MarketPricingSystem
                            MarketPricingSystem.update_market_prices(mkt)
                        if stockpile_manager and getattr(mkt, "tiles", None):
                            target_res = MARKET_TRADEABLE_ITEMS.get(it_name, it_name)
                            market_center = mkt.get_center_world(TILE_SIZE)
                            approach = mkt.get_approach_point(market_center, TILE_SIZE, bm=None)
                            drop_tile = (int(math.floor(approach[0] / TILE_SIZE)), int(math.floor(approach[1] / TILE_SIZE)))
                            assigned_family_id = getattr(mkt, "assigned_family_id", None)
                            owner_id = str(assigned_family_id) if assigned_family_id else None
                            owner_type = "villager" if assigned_family_id else "landlord"
                            stockpile_manager.drop_resource(target_res, withdraw_amt, drop_tile[0], drop_tile[1], owner_type=owner_type, owner_id=owner_id)
                            stockpile_manager.refresh_stacks(resources, None)
                        else:
                            self.status_message = "No stockpile available for physical withdrawal."
                            mkt.inventory[it_name] = mkt.inventory.get(it_name, 0) + withdraw_amt
                            return f"stock_withdraw_failed_{it_name}"
                        self.status_message = f"Dropped {withdraw_amt} {it_name} near the market for servant hauling."
                        return f"stock_withdrawn_{it_name}"
                    self.status_message = f"Only {in_market} {it_name} available in market."

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

        # Goods and household sale limits share this single market view.
        tab_y = status_y + 4
        self.tab_goods_rect = None


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
        landlord_owned = not fam_assigned_id
        self.deposit_coin_btn_rect = pygame.Rect(stats_rect.right - 180, stats_rect.y + 14, 82, 28) if landlord_owned else None
        if landlord_owned:
            dep_hov = self.deposit_coin_btn_rect.collidepoint(m_pos)
            pygame.draw.rect(surface, (22, 101, 52) if dep_hov else (20, 83, 45), self.deposit_coin_btn_rect, border_radius=4)
            pygame.draw.rect(surface, (74, 222, 128), self.deposit_coin_btn_rect, width=1, border_radius=4)
            surface.blit(self.font_badge.render("Deposit", True, (255, 255, 255)), (self.deposit_coin_btn_rect.x + 18, self.deposit_coin_btn_rect.y + 8))

        self.withdraw_coin_btn_rect = pygame.Rect(stats_rect.right - 92, stats_rect.y + 14, 82, 28) if landlord_owned else None
        if landlord_owned:
            with_hov = self.withdraw_coin_btn_rect.collidepoint(m_pos)
            pygame.draw.rect(surface, (153, 27, 27) if with_hov else (127, 29, 29), self.withdraw_coin_btn_rect, border_radius=4)
            pygame.draw.rect(surface, (248, 113, 113), self.withdraw_coin_btn_rect, width=1, border_radius=4)
            surface.blit(self.font_badge.render("Withdraw", True, (255, 255, 255)), (self.withdraw_coin_btn_rect.x + 12, self.withdraw_coin_btn_rect.y + 8))

        # -------------------------------------------------------------
        # TAB CONTENT
        # -------------------------------------------------------------
        content_y = stats_rect.bottom + 14

        self._draw_goods_tab(surface, mx, content_y, mkt, servant_manager, resources, stockpile_manager, m_pos)

        # 7. ASSIGN STALL DIALOG OVERLAY (if active)
        if self.show_assign_dialog:
            self._draw_assign_dialog(surface, mx, my, mkt, villager_manager, m_pos)

        # 8. COIN DEPOSIT / WITHDRAW DIALOG OVERLAY (if active)
        if self.show_coin_dialog:
            self._draw_coin_dialog(surface, mx, my, mkt, resources, m_pos, stockpile_manager, servant_manager)

    def _get_quantity(self, item_name):
        raw = self.quantity_values.get(item_name, str(MARKET_QUANTITY_DEFAULT))
        try:
            return max(0, min(MARKET_QUANTITY_MAX, int(raw)))
        except (TypeError, ValueError):
            return 0

    def _draw_goods_tab(self, surface, mx, list_y, mkt, servant_manager, resources, stockpile_manager, m_pos):
        """Draw only explicitly enabled market goods and their physical stock controls."""
        assigned = bool(getattr(mkt, "assigned_family_id", None))
        self.price_g_dec_btns.clear()
        self.price_g_inc_btns.clear()
        self.price_s_dec_btns.clear()
        self.price_s_inc_btns.clear()
        self.price_c_dec_btns.clear()
        self.price_c_inc_btns.clear()
        self.stock_dep_btns.clear()
        self.stock_with_btns.clear()
        self.stock_quantity_rects.clear()

        self.add_item_btn_rect = pygame.Rect(mx + self.modal_w - 188, list_y - 2, 164, 26)
        pygame.draw.rect(surface, (22, 101, 52) if self.add_item_btn_rect.collidepoint(m_pos) else (20, 83, 45), self.add_item_btn_rect, border_radius=4)
        surface.blit(self.font_badge.render("+ Add item to sell", True, (255, 255, 255)), (self.add_item_btn_rect.x + 12, self.add_item_btn_rect.y + 7))

        title = "MARKET ITEMS FOR SALE"
        surface.blit(self.font_sub.render(title, True, COLOR_TEXT_TITLE), (mx + 24, list_y + 4))
        row_top = list_y + 30

        if assigned:
            pct = max(0, min(100, int(getattr(mkt, "household_sale_percent", MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT))))
            surface.blit(self.font_badge.render("Household goods limit:", True, COLOR_TEXT_MUTED), (mx + 24, row_top + 5))
            self.household_percent_dec_rect = pygame.Rect(mx + 172, row_top, 26, 24)
            self.household_percent_inc_rect = pygame.Rect(mx + 252, row_top, 26, 24)
            for rect, text in ((self.household_percent_dec_rect, "-"), (self.household_percent_inc_rect, "+")):
                pygame.draw.rect(surface, (51, 65, 85), rect, border_radius=3)
                surface.blit(self.font_sub.render(text, True, (255, 255, 255)), (rect.centerx - 4, rect.centery - 8))
            pct_rect = pygame.Rect(mx + 202, row_top, 46, 24)
            pygame.draw.rect(surface, (15, 23, 42), pct_rect, border_radius=3)
            surface.blit(self.font_sub.render(f"{pct}%", True, (250, 204, 21)), (pct_rect.centerx - 12, pct_rect.centery - 8))
            surface.blit(self.font_badge.render("of household stock may be sold; price is market controlled", True, COLOR_TEXT_MUTED), (mx + 292, row_top + 6))
            row_top += 30
        else:
            self.household_percent_dec_rect = None
            self.household_percent_inc_rect = None

        table = pygame.Rect(mx + 24, row_top, self.modal_w - 48, 24)
        pygame.draw.rect(surface, (30, 41, 59), table, border_radius=4)
        labels = ((mx + 36, "ITEM"), (mx + 174, "STOCK"), (mx + 250, "SELL PRICE"), (mx + 330, "PRICE"), (mx + 394, "QTY"), (mx + 468, "RESTOCK"), (mx + 570, "WITHDRAW"))
        for x, label in labels:
            surface.blit(self.font_badge.render(label, True, COLOR_TEXT_MUTED), (x, row_top + 5))

        tradeable_items = [it for it in getattr(mkt, "sale_items", []) if it in MARKET_TRADEABLE_ITEMS]
        items_per_page = 4
        total_pages = max(1, math.ceil(len(tradeable_items) / items_per_page))
        self.goods_page = max(0, min(getattr(self, "goods_page", 0), total_pages - 1))
        page_items = tradeable_items[self.goods_page * items_per_page:(self.goods_page + 1) * items_per_page]
        row_y = row_top + 28
        row_h = 38
        for item_name in page_items:
            card = pygame.Rect(mx + 24, row_y, self.modal_w - 48, row_h)
            pygame.draw.rect(surface, (15, 23, 42), card, border_radius=5)
            draw_item_icon(surface, item_name, mx + 44, row_y + row_h // 2, size=9)
            surface.blit(self.font_sub.render(item_name.replace("_", " "), True, (241, 245, 249)), (mx + 60, row_y + 11))
            stock = max(0, int(mkt.inventory.get(item_name, 0)))
            surface.blit(self.font_badge.render(str(stock), True, (34, 197, 94) if stock else (239, 68, 68)), (mx + 180, row_y + 13))
            price = MarketService.get_item_price(item_name, mkt)
            price_display = from_copper(max(1, int(price)))
            surface.blit(self.font_badge.render(f"{price_display['Gold']}g {price_display['Silver']}s {price_display['Copper']}c", True, (250, 204, 21)), (mx + 250, row_y + 13))

            if not assigned:
                price_minus = pygame.Rect(mx + 326, row_y + 7, 22, 24)
                price_plus = pygame.Rect(mx + 350, row_y + 7, 22, 24)
                self.price_c_dec_btns[item_name] = price_minus
                self.price_c_inc_btns[item_name] = price_plus
                for rect, label in ((price_minus, "-"), (price_plus, "+")):
                    pygame.draw.rect(surface, (51, 65, 85), rect, border_radius=3)
                    text = self.font_sub.render(label, True, (255, 255, 255))
                    surface.blit(text, (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2))

            qty_rect = pygame.Rect(mx + 390, row_y + 7, 54, 24)
            self.stock_quantity_rects[item_name] = qty_rect
            qty_text = self.quantity_values.setdefault(item_name, str(MARKET_QUANTITY_DEFAULT))
            pygame.draw.rect(surface, (15, 23, 42), qty_rect, border_radius=3)
            pygame.draw.rect(surface, (96, 165, 250) if self.focused_quantity == item_name else (71, 85, 105), qty_rect, width=1, border_radius=3)
            shown_qty = qty_text if qty_text else "0"
            qty_surf = self.font_badge.render(shown_qty, True, (255, 255, 255))
            surface.blit(qty_surf, (qty_rect.centerx - qty_surf.get_width() // 2, qty_rect.centery - qty_surf.get_height() // 2))

            restock = pygame.Rect(mx + 456, row_y + 7, 76, 24)
            self.stock_dep_btns[item_name] = restock
            pygame.draw.rect(surface, (30, 58, 138), restock, border_radius=3)
            surface.blit(self.font_badge.render("Restock", True, (255, 255, 255)), (restock.x + 12, restock.y + 6))
            withdraw = pygame.Rect(mx + 558, row_y + 7, 84, 24)
            self.stock_with_btns[item_name] = withdraw
            pygame.draw.rect(surface, (127, 29, 29), withdraw, border_radius=3)
            surface.blit(self.font_badge.render("Withdraw", True, (255, 255, 255)), (withdraw.x + 10, withdraw.y + 6))
            row_y += row_h + 3

        if not page_items:
            empty = pygame.Rect(mx + 24, row_y, self.modal_w - 48, 82)
            pygame.draw.rect(surface, (15, 23, 42), empty, border_radius=5)
            empty_text = self.font_body.render("No goods listed. Choose Add item to sell to begin.", True, COLOR_TEXT_MUTED)
            surface.blit(empty_text, (empty.centerx - empty_text.get_width() // 2, empty.centery - empty_text.get_height() // 2))

        page_y = max(row_y + 4, row_top + 28 + items_per_page * (row_h + 3))
        self.prev_page_btn_rect = pygame.Rect(mx + 24, page_y, 90, 22)
        self.next_page_btn_rect = pygame.Rect(mx + self.modal_w - 114, page_y, 90, 22)
        has_prev = self.goods_page > 0
        has_next = self.goods_page < total_pages - 1
        for rect, label, enabled in ((self.prev_page_btn_rect, "< Prev", has_prev), (self.next_page_btn_rect, "Next >", has_next)):
            pygame.draw.rect(surface, (30, 58, 138) if enabled else (51, 65, 85), rect, border_radius=3)
            text = self.font_badge.render(label, True, (255, 255, 255) if enabled else COLOR_TEXT_MUTED)
            surface.blit(text, (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2))

        if self.status_message:
            status = self.font_badge.render(self.status_message, True, (248, 113, 113) if "No Goods" in self.status_message else (134, 239, 172))
            surface.blit(status, (mx + 130, page_y + 5))

        self.item_picker_rects.clear()
        if self.show_item_picker:
            picker = pygame.Rect(mx + 170, row_top + 18, self.modal_w - 340, min(300, len(MARKET_TRADEABLE_ITEMS) * 38 + 48))
            pygame.draw.rect(surface, (15, 23, 42), picker, border_radius=8)
            pygame.draw.rect(surface, (96, 165, 250), picker, width=2, border_radius=8)
            surface.blit(self.font_sub.render("Choose a market item", True, COLOR_TEXT_TITLE), (picker.x + 14, picker.y + 12))
            selectable = [it for it in MARKET_TRADEABLE_ITEMS if it not in getattr(mkt, "sale_items", [])]
            if not selectable:
                surface.blit(self.font_body.render("All supported goods are already listed.", True, COLOR_TEXT_MUTED), (picker.x + 14, picker.y + 42))
            for idx, item_name in enumerate(selectable):
                item_rect = pygame.Rect(picker.x + 12, picker.y + 38 + idx * 34, picker.width - 24, 30)
                self.item_picker_rects[item_name] = item_rect
                pygame.draw.rect(surface, (30, 41, 59), item_rect, border_radius=4)
                surface.blit(self.font_body.render(item_name.replace("_", " "), True, (241, 245, 249)), (item_rect.x + 10, item_rect.y + 8))

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

    def _draw_coin_dialog(self, surface, mx, my, mkt, resources, m_pos, stockpile_manager=None, servant_manager=None):
        """Quantity based physical coin deposit or withdrawal controls."""
        action = self.show_coin_dialog
        dlg_w, dlg_h = 420, 240
        dlg_x = mx + (self.modal_w - dlg_w) // 2
        dlg_y = my + (self.modal_h - dlg_h) // 2
        pygame.draw.rect(surface, (15, 23, 42), (dlg_x, dlg_y, dlg_w, dlg_h), border_radius=10)
        pygame.draw.rect(surface, (245, 158, 11), (dlg_x, dlg_y, dlg_w, dlg_h), width=2, border_radius=10)
        title = "Deposit Coins to Market" if action == "deposit" else "Withdraw Coins from Market"
        surface.blit(self.font_title.render(title, True, (250, 204, 21)), (dlg_x + 20, dlg_y + 14))
        self.close_coin_dlg_btn_rect = pygame.Rect(dlg_x + dlg_w - 32, dlg_y + 12, 22, 22)
        pygame.draw.rect(surface, (51, 65, 85), self.close_coin_dlg_btn_rect, border_radius=4)
        surface.blit(self.font_badge.render("X", True, (255, 255, 255)), (self.close_coin_dlg_btn_rect.x + 6, self.close_coin_dlg_btn_rect.y + 4))

        wallet = normalize_wallet(getattr(mkt, "currency", {}))
        self.coin_action_btn_rects.clear()
        self.coin_quantity_rects.clear()
        for idx, denom in enumerate(MARKET_CURRENCY_DENOMINATIONS):
            row_y = dlg_y + 48 + idx * 42
            surface.blit(self.font_sub.render(denom, True, (241, 245, 249)), (dlg_x + 20, row_y + 7))
            field = pygame.Rect(dlg_x + 100, row_y + 2, 72, 28)
            self.coin_quantity_rects[denom] = field
            key = f"coin:{denom}"
            raw = self.quantity_values.setdefault(key, str(MARKET_QUANTITY_DEFAULT))
            pygame.draw.rect(surface, (15, 23, 42), field, border_radius=3)
            pygame.draw.rect(surface, (96, 165, 250) if self.focused_quantity == key else (71, 85, 105), field, width=1, border_radius=3)
            qty_surf = self.font_badge.render(raw or "0", True, (255, 255, 255))
            surface.blit(qty_surf, (field.centerx - qty_surf.get_width() // 2, field.centery - qty_surf.get_height() // 2))

            button = pygame.Rect(dlg_x + 184, row_y + 2, 94, 28)
            self.coin_action_btn_rects[(denom, action)] = button
            pygame.draw.rect(surface, (20, 83, 45) if action == "deposit" else (127, 29, 29), button, border_radius=4)
            btn_surf = self.font_badge.render(action.title(), True, (255, 255, 255))
            surface.blit(btn_surf, (button.centerx - btn_surf.get_width() // 2, button.centery - btn_surf.get_height() // 2))

            if action == "deposit":
                available = sum(
                    stack.available_amount for stack in getattr(stockpile_manager, "stacks", [])
                    if getattr(stack, "owner_type", "landlord") == "landlord" and stack.resource_type == denom
                ) if stockpile_manager else 0
            else:
                available = wallet.get(denom, 0)
            surface.blit(self.font_badge.render(f"Available: {available}", True, COLOR_TEXT_MUTED), (dlg_x + 286, row_y + 9))

        if self.status_message:
            status = self.font_badge.render(self.status_message, True, (248, 113, 113) if "No Goods" in self.status_message else (134, 239, 172))
            surface.blit(status, (dlg_x + 20, dlg_y + dlg_h - 22))
