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
from game.ui.number_input import NumberInputState

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
        self.modal_top = 0

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
        self.num_fields = {}          # key -> {"rect","kind","item","min","max"}
        self.status_message = None

        # Typable number fields (replaces +/- steppers)
        self.num_input = NumberInputState(max_digits=7)

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

        # Stock management rects
        self.stock_dep_btns = {}
        self.stock_with_btns = {}
        self.stock_remove_btns = {}

        # Lord BUY controls (assigned household stalls only): item -> rect
        self.buy_btns = {}
        self.buy_qty_rects = {}

        # Allocation controls rects (item_name -> rect)

        # Pagination for tradeable goods
        self.goods_page = 0
        self.goods_list_rect = None
        self.tradeable_items = list(MARKET_TRADEABLE_ITEMS)

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
            market_building.auto_pricing = bool(getattr(market_building, "assigned_family_id", None))
            if not isinstance(getattr(market_building, "sale_items", None), list):
                market_building.sale_items = [item for item in market_building.inventory if item in MARKET_TRADEABLE_ITEMS]
            else:
                # Keep each stall's listing independent, even if old save data reused a list.
                market_building.sale_items = list(dict.fromkeys(market_building.sale_items))
            if not hasattr(market_building, "household_sale_percent"):
                market_building.household_sale_percent = MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT
            if not hasattr(market_building, "household_sale_limits"):
                market_building.household_sale_limits = {}
            self.tradeable_items = list(dict.fromkeys(
                list(MARKET_TRADEABLE_ITEMS) + list(market_building.sale_items)
            ))

    def close(self):
        self.is_open = False
        self.target_market = None
        self.show_assign_dialog = False
        self.show_coin_dialog = None
        self.show_item_picker = False
        self.focused_quantity = None
        self.num_input.cancel()

    def handle_event(self, event, resources=None, stockpile_manager=None, servant_manager=None, villager_manager=None, furniture_manager=None):
        """Handles keyboard and mouse events for Market Profile Modal"""
        if not self.is_open or not self.target_market:
            return None

        mkt = self.target_market

        if event.type == pygame.KEYDOWN:
            if self.num_input.active:
                if self.num_input.active_key not in self.num_fields:
                    self.num_input.cancel()
                else:
                    res = self.num_input.handle_keydown(event)
                    if res == "commit":
                        self._commit_num_field()
                    elif res == "cancel":
                        self.num_input.cancel()
                return None
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

            # Typable number fields: focus on click, commit on outside click
            if not (self.show_assign_dialog or self.show_coin_dialog or self.show_item_picker):
                hit_key = None
                for fkey, fld in self.num_fields.items():
                    if fld["rect"].collidepoint(mouse_pos):
                        hit_key = fkey
                        break
                if self.num_input.active and hit_key != self.num_input.active_key:
                    self._commit_num_field()
                if hit_key is not None:
                    self.num_input.focus(hit_key, self._num_field_value(self.num_fields[hit_key]))
                    self.focused_quantity = None
                    return None

            if self.show_item_picker:
                for item_name, rect in self.item_picker_rects.items():
                    if rect.collidepoint(mouse_pos):
                        if getattr(mkt, "assigned_family_id", None):
                            owned_items = HouseholdStallSystem.get_household_owned_sale_items(
                                mkt.assigned_family_id, furniture_manager,
                                villager_manager, stockpile_manager
                            )
                            if item_name not in owned_items:
                                self.show_item_picker = False
                                self.status_message = "This household no longer has that item in storage."
                                return "market_item_not_owned"
                        if item_name not in mkt.sale_items:
                            mkt.sale_items.append(item_name)
                            mkt.prices.setdefault(item_name, DEFAULT_ITEM_PRICES.get(item_name, 1))
                            if getattr(mkt, "assigned_family_id", None):
                                mkt.item_allocations.setdefault(item_name, MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT)
                        self.show_item_picker = False
                        return f"market_item_added_{item_name}"
                self.show_item_picker = False
                return None

            if not self.show_assign_dialog and not self.show_coin_dialog and self.add_item_btn_rect and self.add_item_btn_rect.collidepoint(mouse_pos):
                self.show_item_picker = True
                self.focused_quantity = None
                return "open_item_picker"

            for item_name, rect in self.stock_remove_btns.items():
                if (not self.show_assign_dialog and not self.show_coin_dialog
                        and rect.collidepoint(mouse_pos)):
                    remaining_stock = max(0, int(getattr(mkt, "inventory", {}).get(item_name, 0)))
                    if HouseholdStallSystem.remove_sale_item(
                            mkt, item_name, furniture_manager, stockpile_manager):
                        if remaining_stock and getattr(mkt, "assigned_family_id", None):
                            self.status_message = f"Removed {item_name}; remaining stock dropped for the household to haul."
                        elif remaining_stock:
                            self.status_message = f"Removed {item_name}; remaining stock dropped near the stall."
                        else:
                            self.status_message = f"Removed {item_name} from sale."
                        return f"market_item_removed_{item_name}"

            # 2. Assign Stall Dialog Handling
            if self.show_assign_dialog:
                if self.close_assign_dlg_btn_rect and self.close_assign_dlg_btn_rect.collidepoint(mouse_pos):
                    self.show_assign_dialog = False
                    return "close_assign_dialog"

                if self.unassign_stall_btn_rect and self.unassign_stall_btn_rect.collidepoint(mouse_pos):
                    HouseholdStallSystem.unassign_stall(mkt)
                    self.show_assign_dialog = False
                    try:
                        from game.systems.wealth_system import VillageWealthSystem
                        VillageWealthSystem.mark_dirty()
                    except ImportError:
                        pass
                    return "stall_unassigned"

                for fam_id, btn_rect in self.family_assign_btn_rects.items():
                    if btn_rect.collidepoint(mouse_pos):
                        HouseholdStallSystem.assign_stall(mkt, fam_id)
                        HouseholdStallSystem.retain_household_owned_sale_items(
                            mkt, furniture_manager, villager_manager, stockpile_manager
                        )
                        for item_name in mkt.sale_items:
                            mkt.item_allocations.setdefault(item_name, MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT)
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
                if getattr(mkt, "assigned_family_id", None):
                    self.show_coin_dialog = None
                    return "household_stall_coin_controls_disabled"
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
                                from game.systems.wealth_system import VillageWealthSystem
                                VillageWealthSystem.mark_dirty()
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

            # Lord BUY qty fields (assigned household stalls only)
            for item_name, rect in self.buy_qty_rects.items():
                if rect.collidepoint(mouse_pos):
                    self.focused_quantity = item_name
                    self.quantity_values.setdefault(item_name, str(MARKET_QUANTITY_DEFAULT))
                    return None

            # 4. Open Assign Stall Dialog
            if self.assign_stall_btn_rect and self.assign_stall_btn_rect.collidepoint(mouse_pos):
                self.show_assign_dialog = True
                return "open_assign_dialog"

            # 5. Open Deposit / Withdraw Dialogs
            if (not getattr(mkt, "assigned_family_id", None)
                    and self.deposit_coin_btn_rect and self.deposit_coin_btn_rect.collidepoint(mouse_pos)):
                self.show_coin_dialog = "deposit"
                return "open_deposit_dialog"

            if (not getattr(mkt, "assigned_family_id", None)
                    and self.withdraw_coin_btn_rect and self.withdraw_coin_btn_rect.collidepoint(mouse_pos)):
                self.show_coin_dialog = "withdraw"
                return "open_withdraw_dialog"

            # Goods rows are the only market management view.
            # Manual prices are edited via the typable PRICE field per row.
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

            # Lord BUY: servant fetches coins from Lord Treasury, buys from this
            # household stall at its active selling price, hauls goods to
            # landlord storage, and returns the change to the treasury.
            if getattr(mkt, "assigned_family_id", None):
                for it_name, rect in self.buy_btns.items():
                    if rect.collidepoint(mouse_pos):
                        amount = self._get_quantity(it_name)
                        if amount <= 0:
                            self.status_message = "Enter a quantity greater than zero."
                            return "buy_invalid_quantity"
                        if servant_manager is None:
                            self.status_message = "No servant manager available."
                            return "buy_no_servant"
                        order = servant_manager.add_buy_order(mkt, it_name, amount)
                        if order:
                            self.status_message = f"Buy order created: {order['quantity']}x {it_name} from this stall."
                            return f"buy_order_created_{it_name}"
                        self.status_message = "Cannot buy: stall is out of stock, unassigned, or item not for sale."
                        return f"buy_order_failed_{it_name}"

            # Physical stock withdrawal belongs to landlord-managed stalls only.
            if not getattr(mkt, "assigned_family_id", None):
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
                                stockpile_manager.drop_resource(target_res, withdraw_amt, drop_tile[0], drop_tile[1], owner_type="landlord")
                                stockpile_manager.refresh_stacks(resources, None)
                            else:
                                self.status_message = "No stockpile available for physical withdrawal."
                                mkt.inventory[it_name] = mkt.inventory.get(it_name, 0) + withdraw_amt
                                return f"stock_withdraw_failed_{it_name}"
                            self.status_message = f"Dropped {withdraw_amt} {it_name} near the market for servant hauling."
                            return f"stock_withdrawn_{it_name}"
                        self.status_message = f"Only {in_market} {it_name} available in market."

        elif event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            if self.goods_list_rect and self.goods_list_rect.collidepoint(mouse_pos):
                tradeable_count = sum(
                    1 for item in getattr(mkt, "sale_items", [])
                    if item in MARKET_TRADEABLE_ITEMS
                )
                total_pages = max(1, math.ceil(tradeable_count / 4))
                self.goods_page = max(0, min(total_pages - 1, self.goods_page - event.y))
                return "market_goods_scrolled"

        return None

    def draw(self, surface, resources=None, stockpile_manager=None, servant_manager=None, villager_manager=None, furniture_manager=None, day_number=1):
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
        self.modal_top = my
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

        self._draw_goods_tab(surface, mx, content_y, mkt, servant_manager, resources,
                             stockpile_manager, furniture_manager, villager_manager, m_pos,
                             day_number)

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

    def _num_field_value(self, fld):
        mkt = self.target_market
        if fld["kind"] == "alloc":
            return int(mkt.item_allocations.get(
                fld["item"], MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT))
        return int(mkt.prices.get(fld["item"], DEFAULT_ITEM_PRICES.get(fld["item"], 1)))

    def _commit_num_field(self):
        key = self.num_input.active_key
        fld = self.num_fields.get(key)
        text = self.num_input.text.strip()
        self.num_input.cancel()
        if fld is None or not text.isdigit():
            return
        mkt = self.target_market
        val = max(int(fld.get("min", 0)), min(int(fld.get("max", 9999999)), int(text)))
        if fld["kind"] == "alloc":
            HouseholdStallSystem.set_item_allocation(mkt, fld["item"], val)
        elif fld["kind"] == "price":
            mkt.auto_pricing = False
            mkt.prices[fld["item"]] = val

    def _draw_num_input(self, surface, key, rect, display_value):
        active = (self.num_input.active_key == key)
        bg = (15, 23, 42) if not active else (30, 58, 138)
        border = (250, 204, 21) if active else (71, 85, 105)
        pygame.draw.rect(surface, bg, rect, border_radius=4)
        pygame.draw.rect(surface, border, rect, width=2 if active else 1, border_radius=4)
        txt = (self.num_input.text + "_") if active else str(display_value)
        t = self.font_badge.render(txt, True, (255, 255, 255))
        surface.blit(t, (rect.centerx - t.get_width() // 2,
                         rect.centery - t.get_height() // 2))

    def _draw_goods_tab(self, surface, mx, list_y, mkt, servant_manager, resources,
                        stockpile_manager, furniture_manager, villager_manager, m_pos,
                        day_number=1):
        """Draw only explicitly enabled market goods and their physical stock controls."""
        assigned = bool(getattr(mkt, "assigned_family_id", None))
        self.stock_dep_btns.clear()
        self.stock_with_btns.clear()
        self.stock_remove_btns.clear()
        self.stock_quantity_rects.clear()
        self.buy_btns.clear()
        self.buy_qty_rects.clear()
        self.num_fields.clear()

        self.add_item_btn_rect = pygame.Rect(mx + self.modal_w - 188, list_y - 2, 164, 26)
        pygame.draw.rect(surface, (22, 101, 52) if self.add_item_btn_rect.collidepoint(m_pos) else (20, 83, 45), self.add_item_btn_rect, border_radius=4)
        surface.blit(self.font_badge.render("+ Add item to sell", True, (255, 255, 255)), (self.add_item_btn_rect.x + 12, self.add_item_btn_rect.y + 7))

        title = "MARKET ITEMS FOR SALE"
        surface.blit(self.font_sub.render(title, True, COLOR_TEXT_TITLE), (mx + 24, list_y + 4))
        row_top = list_y + 30

        table = pygame.Rect(mx + 24, row_top, self.modal_w - 48, 24)
        pygame.draw.rect(surface, (30, 41, 59), table, border_radius=4)
        labels = ((mx + 36, "ITEM"), (mx + 174, "STOCK"), (mx + 250, "PRICE"), (mx + 326, "SALE %" if assigned else "PRICE"), (mx + (352 if assigned else 394), "QTY"), (mx + 468, "RESTOCK"))
        if not assigned:
            labels += ((mx + 570, "WITHDRAW"),)
        labels += ((mx + (558 if assigned else 660), "REMOVE"),)
        for x, label in labels:
            surface.blit(self.font_badge.render(label, True, COLOR_TEXT_MUTED), (x, row_top + 5))

        tradeable_items = [it for it in getattr(mkt, "sale_items", []) if it in MARKET_TRADEABLE_ITEMS]
        items_per_page = 4
        total_pages = max(1, math.ceil(len(tradeable_items) / items_per_page))
        self.goods_page = max(0, min(getattr(self, "goods_page", 0), total_pages - 1))
        page_items = tradeable_items[self.goods_page * items_per_page:(self.goods_page + 1) * items_per_page]
        row_y = row_top + 28
        row_h = 58 if assigned else 38
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

            if assigned:
                pct = max(0, min(100, int(getattr(mkt, "item_allocations", {}).get(item_name, MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT))))
                pct_key = ("num", "alloc", item_name)
                pct_rect = pygame.Rect(mx + 328, row_y + 5, 44, 28)
                self.num_fields[pct_key] = {"rect": pct_rect, "kind": "alloc",
                                            "item": item_name, "min": 0, "max": 100}
                self._draw_num_input(surface, pct_key, pct_rect, pct)
            else:
                price_key = ("num", "price", item_name)
                price_rect = pygame.Rect(mx + 328, row_y + 5, 48, 28)
                self.num_fields[price_key] = {"rect": price_rect, "kind": "price",
                                              "item": item_name, "min": 1, "max": 9999999}
                self._draw_num_input(surface, price_key, price_rect,
                                     max(1, int(price)))

            if not assigned:
                qty_rect = pygame.Rect(mx + 390, row_y + 7, 54, 24)
                self.stock_quantity_rects[item_name] = qty_rect
                qty_text = self.quantity_values.setdefault(item_name, str(MARKET_QUANTITY_DEFAULT))
                pygame.draw.rect(surface, (15, 23, 42), qty_rect, border_radius=3)
                pygame.draw.rect(surface, (96, 165, 250) if self.focused_quantity == item_name else (71, 85, 105), qty_rect, width=1, border_radius=3)
                shown_qty = qty_text if qty_text else "0"
                qty_surf = self.font_badge.render(shown_qty, True, (255, 255, 255))
                surface.blit(qty_surf, (qty_rect.centerx - qty_surf.get_width() // 2, qty_rect.centery - qty_surf.get_height() // 2))

            restock = pygame.Rect(mx + 456, row_y + 7, 76, 24)
            if not assigned:
                self.stock_dep_btns[item_name] = restock
                pygame.draw.rect(surface, (30, 58, 138), restock, border_radius=3)
                surface.blit(self.font_badge.render("Restock", True, (255, 255, 255)), (restock.x + 12, restock.y + 6))
            else:
                surface.blit(self.font_badge.render("Auto", True, COLOR_TEXT_MUTED), (restock.x + 22, restock.y + 7))
            if not assigned:
                withdraw = pygame.Rect(mx + 558, row_y + 7, 84, 24)
                self.stock_with_btns[item_name] = withdraw
                pygame.draw.rect(surface, (127, 29, 29), withdraw, border_radius=3)
                surface.blit(self.font_badge.render("Withdraw", True, (255, 255, 255)), (withdraw.x + 10, withdraw.y + 6))
            remove = pygame.Rect(mx + (558 if assigned else 660), row_y + 7, 60, 24)
            self.stock_remove_btns[item_name] = remove
            pygame.draw.rect(surface, (127, 29, 29), remove, border_radius=3)
            surface.blit(self.font_badge.render("Remove", True, (255, 255, 255)), (remove.x + 8, remove.y + 6))

            if assigned:
                # Lord BUY row: qty + BUY button. Coins come from the Lord
                # Treasury; a servant hauls the goods to landlord storage.
                y2 = row_y + 33
                qty_rect = pygame.Rect(mx + 330, y2, 46, 22)
                self.buy_qty_rects[item_name] = qty_rect
                qty_text = self.quantity_values.setdefault(item_name, str(MARKET_QUANTITY_DEFAULT))
                pygame.draw.rect(surface, (15, 23, 42), qty_rect, border_radius=3)
                q_border = (96, 165, 250) if self.focused_quantity == item_name else (71, 85, 105)
                pygame.draw.rect(surface, q_border, qty_rect, width=1, border_radius=3)
                qty_surf = self.font_badge.render(qty_text or "0", True, (255, 255, 255))
                surface.blit(qty_surf, (qty_rect.centerx - qty_surf.get_width() // 2,
                                        qty_rect.centery - qty_surf.get_height() // 2))
                buy_rect = pygame.Rect(mx + 384, y2, 92, 22)
                self.buy_btns[item_name] = buy_rect
                b_hov = buy_rect.collidepoint(m_pos)
                pygame.draw.rect(surface, (22, 101, 52) if b_hov else (20, 83, 45), buy_rect, border_radius=3)
                b_lbl = self.font_badge.render("BUY", True, (255, 255, 255))
                surface.blit(b_lbl, (buy_rect.centerx - b_lbl.get_width() // 2,
                                     buy_rect.centery - b_lbl.get_height() // 2))
                try:
                    est_qty = max(0, min(MARKET_QUANTITY_MAX, int(qty_text or 0)))
                except (TypeError, ValueError):
                    est_qty = 0
                est_txt = self.font_badge.render(f"~{price * est_qty}c", True, COLOR_TEXT_MUTED)
                surface.blit(est_txt, (buy_rect.right + 10, y2 + 5))
            row_y += row_h + 3

        if not page_items:
            empty = pygame.Rect(mx + 24, row_y, self.modal_w - 48, 82)
            pygame.draw.rect(surface, (15, 23, 42), empty, border_radius=5)
            empty_text = self.font_body.render("No goods listed. Choose Add item to sell to begin.", True, COLOR_TEXT_MUTED)
            surface.blit(empty_text, (empty.centerx - empty_text.get_width() // 2, empty.centery - empty_text.get_height() // 2))

        page_y = max(row_y + 4, row_top + 28 + items_per_page * (row_h + 3))
        self.goods_list_rect = pygame.Rect(
            mx + 24, row_top + 28, self.modal_w - 48,
            max(1, page_y - (row_top + 28)),
        )
        if total_pages > 1:
            scroll_hint = self.font_badge.render("Scroll list for more items", True, COLOR_TEXT_MUTED)
            surface.blit(scroll_hint, (mx + self.modal_w - 24 - scroll_hint.get_width(), list_y + 5))

        if self.status_message:
            status = self.font_badge.render(self.status_message, True, (248, 113, 113) if "No Goods" in self.status_message else (134, 239, 172))
            surface.blit(status, (mx + 130, page_y + 5))

        from game.systems.market_sales_report import MarketSalesReportSystem
        report = MarketSalesReportSystem.get_report(mkt, day_number)
        report_top = page_y + 30
        report_bottom = self.modal_top + self.modal_h - 14
        report_rect = pygame.Rect(mx + 24, report_top, self.modal_w - 48,
                                  max(42, report_bottom - report_top))
        pygame.draw.rect(surface, (15, 23, 42), report_rect, border_radius=5)
        pygame.draw.rect(surface, (51, 65, 85), report_rect, width=1, border_radius=5)
        report_title = self.font_badge.render(
            f"TOTAL SALES - DAYS {report['start_day']} to {report['end_day']} (THROUGH DAY {min(day_number, report['end_day'])})",
            True, COLOR_TEXT_TITLE,
        )
        surface.blit(report_title, (report_rect.x + 10, report_rect.y + 7))
        sold_items = sorted(report["items"].items(), key=lambda pair: pair[0].casefold())
        if not sold_items:
            surface.blit(self.font_body.render("No sales recorded in this 10-day period.", True, COLOR_TEXT_MUTED),
                         (report_rect.x + 10, report_rect.y + 27))
        else:
            row_height = 16
            rows_per_column = max(1, (report_rect.height - 28) // row_height)
            visible_count = min(len(sold_items), rows_per_column * 2)
            column_width = (report_rect.width - 20) // 2
            for idx, (item_name, sale) in enumerate(sold_items[:visible_count]):
                col, row = divmod(idx, rows_per_column)
                item_x = report_rect.x + 10 + col * column_width
                item_y = report_rect.y + 25 + row * row_height
                qty = max(0, int(sale.get("quantity", 0)))
                revenue = from_copper(max(0, int(sale.get("revenue_copper", 0))))
                earnings = f"{revenue['Gold']}g {revenue['Silver']}s {revenue['Copper']}c"
                label = self.font_badge.render(
                    f"{item_name}: {qty} sold, {earnings} earned", True, COLOR_TEXT_MAIN,
                )
                surface.blit(label, (item_x, item_y))
            if visible_count < len(sold_items):
                more = self.font_badge.render(f"+ {len(sold_items) - visible_count} more items", True, COLOR_TEXT_MUTED)
                surface.blit(more, (report_rect.right - more.get_width() - 10, report_rect.bottom - more.get_height() - 5))

        self.item_picker_rects.clear()
        if self.show_item_picker:
            picker = pygame.Rect(mx + 170, row_top + 18, self.modal_w - 340, min(300, len(MARKET_TRADEABLE_ITEMS) * 38 + 48))
            pygame.draw.rect(surface, (15, 23, 42), picker, border_radius=8)
            pygame.draw.rect(surface, (96, 165, 250), picker, width=2, border_radius=8)
            surface.blit(self.font_sub.render("Choose a market item", True, COLOR_TEXT_TITLE), (picker.x + 14, picker.y + 12))
            # Each household may list only goods it currently owns. Landlord stalls
            # can list any supported trade good from landlord storage.
            if getattr(mkt, "assigned_family_id", None):
                owned_items = HouseholdStallSystem.get_household_owned_sale_items(
                    mkt.assigned_family_id, furniture_manager,
                    villager_manager, stockpile_manager
                )
                selectable = [it for it in MARKET_TRADEABLE_ITEMS
                              if it in owned_items and it not in getattr(mkt, "sale_items", [])]
            else:
                selectable = [it for it in MARKET_TRADEABLE_ITEMS
                              if it not in getattr(mkt, "sale_items", [])]
            if not selectable:
                empty_label = ("No eligible household goods are available in storage."
                               if getattr(mkt, "assigned_family_id", None)
                               else "All supported goods are already listed at this stall.")
                surface.blit(self.font_body.render(empty_label, True, COLOR_TEXT_MUTED), (picker.x + 14, picker.y + 42))
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
