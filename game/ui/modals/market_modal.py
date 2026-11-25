"""
Market Profile Modal (AGENT 2)
Displays landlord & household market stall management with beginner-friendly UX:
- Clear mode header (Lord Stall vs Household Stall) with one-click Unassign
- Unified single PRICE (Copper) control with +/- steppers & coin preview
- Household Stall transparent STALL / HOME stock, reserve protection, and SALE CAP %
- Auto-List Surplus (excluding Tools) + Quick Add Common Goods empty-state helpers
- Clickable pagination (< Prev / Next >) & scrollable item/family pickers
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
    DENOMINATION_CAP,
    MARKET_ALLOC_STEP,
    MARKET_PRICE_STEP,
    MARKET_UI_ITEMS_PER_PAGE,
    MARKET_LORD_COMMON_GOODS,
    MARKET_TRADEABLE_ITEMS,
    MARKET_QUANTITY_DEFAULT,
    MARKET_QUANTITY_MAX,
    MARKET_CURRENCY_DENOMINATIONS,
    MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT,
    MARKET_HOUSEHOLD_SALE_PERCENT_MIN,
    MARKET_HOUSEHOLD_SALE_PERCENT_MAX,
    TOOL_TYPES,
    TILE_SIZE,
)
from game.systems.economy.currency import (
    to_copper,
    from_copper,
    normalize_wallet,
)
from game.systems.economy.market_service import MarketService
from game.systems.economy.household_stall_system import HouseholdStallSystem
from game.systems.economy.wealth_system import VillageWealthSystem
from game.ui.item_icons import draw_item_icon
from game.ui.number_input import NumberInputState
from game.ui.ui_theme import ui_font, upx


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
        self.modal_w = upx(840)
        self.modal_h = upx(590)
        self.modal_top = 0

        # Tabs & Sub-views
        self.active_tab = "goods"
        self.tab_goods_rect = None

        # Dialog States
        self.show_assign_dialog = False
        self.show_coin_dialog = None  # None | "deposit" | "withdraw"
        self.show_item_picker = False
        self.item_picker_rects = {}
        self.picker_selected = set()
        self.picker_scroll = 0
        self.picker_items = []
        self.picker_dialog_rect = None
        self.picker_list_rect = None
        self.picker_done_rect = None
        self.picker_cancel_rect = None
        self.picker_select_all_rect = None
        self.assign_scroll = 0
        self.assign_list_rect = None

        # Main goods controls
        self.add_item_btn_rect = None
        self.auto_list_btn_rect = None
        self.quick_add_common_rect = None
        self.stock_quantity_rects = {}
        self.quantity_values = {}
        self.focused_quantity = None
        self.num_fields = {}          # key -> {"rect","kind","item","min","max"}
        self.status_message = None

        # Typable number fields
        self.num_input = NumberInputState(max_digits=7)

        # UI interaction rects
        self.close_btn_rect = None
        self.assign_stall_btn_rect = None
        self.quick_unassign_btn_rect = None
        self.unassign_stall_btn_rect = None
        self.close_assign_dlg_btn_rect = None
        self.family_assign_btn_rects = {}

        # Coin Treasury Rects
        self.deposit_coin_btn_rect = None
        self.withdraw_coin_btn_rect = None
        self.coin_action_btn_rects = {}
        self.coin_quantity_rects = {}
        self.close_coin_dlg_btn_rect = None

        # Stock & stepper rects
        self.stock_dep_btns = {}
        self.stock_with_btns = {}
        self.stock_remove_btns = {}
        self.price_step_btns = {}      # (item_name, delta) -> Rect
        self.price_auto_btns = {}      # item_name -> Rect
        self.alloc_step_btns = {}      # (item_name, delta) -> Rect

        # Lord BUY controls (assigned household stalls only): item -> rect
        self.buy_btns = {}
        self.buy_qty_rects = {}

        # Pagination for tradeable goods
        self.goods_page = 0
        self.goods_list_rect = None
        self.page_prev_rect = None
        self.page_next_rect = None
        self.tradeable_items = list(MARKET_TRADEABLE_ITEMS)

    def _ensure_fonts(self):
        if self.font_title is None:
            self.font_title = ui_font(16, bold=True)
            self.font_sub = ui_font(12, bold=True)
            self.font_body = ui_font(11)
            self.font_badge = ui_font(10, bold=True)
            self.font_btn = ui_font(11, bold=True)

    def open(self, market_building):
        """Opens market profile modal for the selected market building."""
        if market_building and getattr(market_building, "building_type", "") == "market":
            self.target_market = market_building
            self.is_open = True
            self.show_assign_dialog = False
            self.show_coin_dialog = None
            self.show_item_picker = False
            self.picker_selected.clear()
            self.picker_scroll = 0
            self.assign_scroll = 0
            self.goods_page = 0
            self.status_message = None

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
        self.picker_selected.clear()
        self.picker_scroll = 0
        self.assign_scroll = 0
        self.focused_quantity = None
        self.num_input.cancel()

    def _clear_interactive_rects(self):
        self.stock_dep_btns.clear()
        self.stock_with_btns.clear()
        self.stock_remove_btns.clear()
        self.stock_quantity_rects.clear()
        self.price_step_btns.clear()
        self.price_auto_btns.clear()
        self.alloc_step_btns.clear()
        self.buy_btns.clear()
        self.buy_qty_rects.clear()
        self.num_fields.clear()
        self.auto_list_btn_rect = None
        self.quick_add_common_rect = None
        self.page_prev_rect = None
        self.page_next_rect = None

    def _landlord_stockpile_qty(self, item_name, stockpile_manager, resources):
        storage_key = MARKET_TRADEABLE_ITEMS.get(item_name, item_name)
        if stockpile_manager is not None:
            return sum(
                max(0, int(getattr(stack, "available_amount", 0)))
                for stack in getattr(stockpile_manager, "stacks", [])
                if getattr(stack, "owner_type", "landlord") == "landlord"
                and getattr(stack, "resource_type", None) == storage_key
            )
        if isinstance(resources, dict):
            return max(0, int(resources.get(storage_key, 0)))
        return 0

    @staticmethod
    def _format_copper(copper_amount):
        parts = from_copper(max(0, int(copper_amount)))
        return f"{parts['Gold']}g {parts['Silver']}s {parts['Copper']}c"

    def _run_auto_list_surplus(self, mkt, furniture_manager, villager_manager, stockpile_manager):
        added = HouseholdStallSystem.auto_list_surplus_items(
            mkt, furniture_manager, villager_manager, stockpile_manager
        )
        if added:
            self.status_message = f"Auto-listed {len(added)} surplus item(s) (tools excluded)."
            return "market_auto_listed"
        self.status_message = "No new non-tool surplus items available in household storage."
        return "market_auto_list_none"

    def _run_quick_add_common(self, mkt):
        if not isinstance(getattr(mkt, "sale_items", None), list):
            mkt.sale_items = []
        if not isinstance(getattr(mkt, "prices", None), dict):
            mkt.prices = {}
        added = 0
        for item_name in MARKET_LORD_COMMON_GOODS:
            if item_name in MARKET_TRADEABLE_ITEMS and item_name not in mkt.sale_items:
                mkt.sale_items.append(item_name)
                mkt.prices.setdefault(item_name, DEFAULT_ITEM_PRICES.get(item_name, 1))
                added += 1
        if added:
            self.status_message = f"Added {added} common village item(s) for sale."
            return "market_quick_added_common"
        self.status_message = "Common village items are already listed."
        return "market_quick_add_noop"

    def handle_event(self, event, resources=None, stockpile_manager=None, servant_manager=None, villager_manager=None, furniture_manager=None, permit_manager=None):
        """Handles keyboard and mouse events for Market Profile Modal."""
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
                    self.picker_selected.clear()
                    self.picker_scroll = 0
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
                return self._handle_picker_click(
                    mouse_pos, mkt, furniture_manager, villager_manager, stockpile_manager
                )

            if self.show_assign_dialog:
                return self._handle_assign_dialog_click(
                    mouse_pos, mkt, furniture_manager, villager_manager, stockpile_manager
                )

            if self.show_coin_dialog:
                return self._handle_coin_dialog_click(
                    mouse_pos, mkt, resources, stockpile_manager, servant_manager, permit_manager
                )

            # Header mode actions
            if self.assign_stall_btn_rect and self.assign_stall_btn_rect.collidepoint(mouse_pos):
                self.show_assign_dialog = True
                return "open_assign_dialog"

            if (getattr(mkt, "assigned_family_id", None)
                    and self.quick_unassign_btn_rect
                    and self.quick_unassign_btn_rect.collidepoint(mouse_pos)):
                HouseholdStallSystem.unassign_stall(mkt)
                self.status_message = "Stall reverted to Lord Stall control."
                VillageWealthSystem.mark_dirty()
                return "stall_unassigned"

            # Treasury dialog openers (Lord Stall only)
            if (not getattr(mkt, "assigned_family_id", None)
                    and self.deposit_coin_btn_rect and self.deposit_coin_btn_rect.collidepoint(mouse_pos)):
                self.show_coin_dialog = "deposit"
                return "open_deposit_dialog"

            if (not getattr(mkt, "assigned_family_id", None)
                    and self.withdraw_coin_btn_rect and self.withdraw_coin_btn_rect.collidepoint(mouse_pos)):
                self.show_coin_dialog = "withdraw"
                return "open_withdraw_dialog"

            # Goods header & empty-state quick buttons
            if self.add_item_btn_rect and self.add_item_btn_rect.collidepoint(mouse_pos):
                self.show_item_picker = True
                self.focused_quantity = None
                return "open_item_picker"

            if (getattr(mkt, "assigned_family_id", None)
                    and self.auto_list_btn_rect
                    and self.auto_list_btn_rect.collidepoint(mouse_pos)):
                return self._run_auto_list_surplus(mkt, furniture_manager, villager_manager, stockpile_manager)

            if (not getattr(mkt, "assigned_family_id", None)
                    and self.quick_add_common_rect
                    and self.quick_add_common_rect.collidepoint(mouse_pos)):
                return self._run_quick_add_common(mkt)

            # Pagination buttons
            tradeable_count = sum(1 for it in getattr(mkt, "sale_items", []) if it in MARKET_TRADEABLE_ITEMS)
            total_pages = max(1, math.ceil(tradeable_count / MARKET_UI_ITEMS_PER_PAGE))
            if self.page_prev_rect and self.page_prev_rect.collidepoint(mouse_pos) and self.goods_page > 0:
                self.goods_page -= 1
                return "market_page_prev"
            if self.page_next_rect and self.page_next_rect.collidepoint(mouse_pos) and self.goods_page < total_pages - 1:
                self.goods_page += 1
                return "market_page_next"

            # Price steppers & Base reset (Lord Stall)
            if not getattr(mkt, "assigned_family_id", None):
                for (item_name, delta), rect in self.price_step_btns.items():
                    if rect.collidepoint(mouse_pos):
                        cur = int(mkt.prices.get(item_name, DEFAULT_ITEM_PRICES.get(item_name, 1)))
                        mkt.auto_pricing = False
                        mkt.prices[item_name] = max(1, cur + delta)
                        self.focused_quantity = None
                        return f"price_step_{item_name}"
                for item_name, rect in self.price_auto_btns.items():
                    if rect.collidepoint(mouse_pos):
                        base_p = max(1, int(DEFAULT_ITEM_PRICES.get(item_name, 1)))
                        mkt.auto_pricing = False
                        mkt.prices[item_name] = base_p
                        self.status_message = f"Reset {item_name.replace('_', ' ')} price to base ({base_p}c)."
                        return f"price_reset_{item_name}"

            # Allocation % steppers (Household Stall)
            if getattr(mkt, "assigned_family_id", None):
                for (item_name, delta), rect in self.alloc_step_btns.items():
                    if rect.collidepoint(mouse_pos):
                        cur = HouseholdStallSystem.get_item_allocation(mkt, item_name)
                        HouseholdStallSystem.set_item_allocation(mkt, item_name, cur + delta)
                        self.focused_quantity = None
                        return f"alloc_step_{item_name}"

            # Remove item
            for item_name, rect in self.stock_remove_btns.items():
                if rect.collidepoint(mouse_pos):
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

            # Focus QTY fields
            for item_name, rect in self.stock_quantity_rects.items():
                if rect.collidepoint(mouse_pos):
                    self.focused_quantity = item_name
                    self.quantity_values.setdefault(item_name, str(MARKET_QUANTITY_DEFAULT))
                    return None

            for item_name, rect in self.buy_qty_rects.items():
                if rect.collidepoint(mouse_pos):
                    self.focused_quantity = item_name
                    self.quantity_values.setdefault(item_name, str(MARKET_QUANTITY_DEFAULT))
                    return None

            # Restock & Withdraw & Lord Buy
            res = self._handle_row_actions_click(
                mouse_pos, mkt, resources, stockpile_manager, servant_manager,
                villager_manager, furniture_manager, permit_manager
            )
            if res is not None:
                return res

        elif event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()
            if (self.show_item_picker and self.picker_list_rect
                    and self.picker_list_rect.collidepoint(mouse_pos)):
                self.picker_scroll = max(0, self.picker_scroll - event.y * upx(38))
                return "market_picker_scrolled"
            if (self.show_assign_dialog and self.assign_list_rect
                    and self.assign_list_rect.collidepoint(mouse_pos)):
                self.assign_scroll = max(0, self.assign_scroll - event.y * upx(38))
                return "market_assign_scrolled"
            if self.goods_list_rect and self.goods_list_rect.collidepoint(mouse_pos):
                tradeable_count = sum(
                    1 for item in getattr(mkt, "sale_items", [])
                    if item in MARKET_TRADEABLE_ITEMS
                )
                total_pages = max(1, math.ceil(tradeable_count / MARKET_UI_ITEMS_PER_PAGE))
                self.goods_page = max(0, min(total_pages - 1, self.goods_page - event.y))
                return "market_goods_scrolled"

        return None

    def _handle_picker_click(self, mouse_pos, mkt, furniture_manager, villager_manager, stockpile_manager):
        if self.picker_select_all_rect and self.picker_select_all_rect.collidepoint(mouse_pos):
            if self.picker_items:
                if len(self.picker_selected) >= len(self.picker_items):
                    self.picker_selected.clear()
                else:
                    self.picker_selected.update(self.picker_items)
            return "picker_toggle_all"
        if self.picker_done_rect and self.picker_done_rect.collidepoint(mouse_pos):
            added, skipped = self._apply_picker_selection(
                mkt, furniture_manager, villager_manager, stockpile_manager)
            self.show_item_picker = False
            self.picker_selected.clear()
            self.picker_scroll = 0
            if skipped:
                self.status_message = f"Added {added} item(s); {skipped} not owned by this household."
            elif added:
                self.status_message = f"Added {added} item(s) to stall."
            return "market_items_added"
        if self.picker_cancel_rect and self.picker_cancel_rect.collidepoint(mouse_pos):
            self.show_item_picker = False
            self.picker_selected.clear()
            self.picker_scroll = 0
            return "close_item_picker"
        for item_name, rect in self.item_picker_rects.items():
            if rect.collidepoint(mouse_pos):
                if item_name in self.picker_selected:
                    self.picker_selected.discard(item_name)
                else:
                    self.picker_selected.add(item_name)
                return None
        if self.picker_dialog_rect and not self.picker_dialog_rect.collidepoint(mouse_pos):
            self.show_item_picker = False
            self.picker_selected.clear()
            self.picker_scroll = 0
            return "close_item_picker"
        return None

    def _handle_assign_dialog_click(self, mouse_pos, mkt, furniture_manager, villager_manager, stockpile_manager):
        if self.close_assign_dlg_btn_rect and self.close_assign_dlg_btn_rect.collidepoint(mouse_pos):
            self.show_assign_dialog = False
            return "close_assign_dialog"

        if self.unassign_stall_btn_rect and self.unassign_stall_btn_rect.collidepoint(mouse_pos):
            HouseholdStallSystem.unassign_stall(mkt)
            self.show_assign_dialog = False
            self.status_message = "Stall reverted to Lord Stall control."
            VillageWealthSystem.mark_dirty()
            return "stall_unassigned"

        for fam_id, btn_rect in self.family_assign_btn_rects.items():
            if btn_rect.collidepoint(mouse_pos):
                HouseholdStallSystem.assign_stall(mkt, fam_id)
                HouseholdStallSystem.retain_household_owned_sale_items(
                    mkt, furniture_manager, villager_manager, stockpile_manager
                )
                for item_name in mkt.sale_items:
                    mkt.item_allocations.setdefault(item_name, MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT)
                auto_added = HouseholdStallSystem.auto_list_surplus_items(
                    mkt, furniture_manager, villager_manager, stockpile_manager
                )
                self.goods_page = 0
                self.show_assign_dialog = False
                if auto_added:
                    self.status_message = f"Assigned stall & auto-listed {len(auto_added)} surplus item(s)."
                else:
                    self.status_message = "Assigned stall to family."
                VillageWealthSystem.mark_dirty()
                return f"stall_assigned_{fam_id}"
        return None

    def _handle_coin_dialog_click(self, mouse_pos, mkt, resources, stockpile_manager, servant_manager, permit_manager):
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

        action = self.show_coin_dialog
        for (denom, coin_action), btn_rect in self.coin_action_btn_rects.items():
            if btn_rect.collidepoint(mouse_pos):
                amount = self._get_quantity(f"coin:{denom}")
                if amount <= 0:
                    self.status_message = "Enter a quantity greater than zero."
                    return "coin_invalid_quantity"
                if action == "deposit" and servant_manager:
                    order = servant_manager.add_restock_order(
                        mkt, denom, amount, stockpile_manager=stockpile_manager,
                        resources=resources, permit_manager=permit_manager
                    )
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
                        if servant_manager is not None:
                            servant_manager.restock_orders[:] = [
                                o for o in getattr(servant_manager, "restock_orders", [])
                                if not (o.get("market_building") is mkt and o.get("item_type") == denom)
                            ]
                        VillageWealthSystem.mark_dirty()
                        self.status_message = f"Dropped {actual} {denom} near the market for servant hauling."
                        return f"coin_withdrawn_{actual}_{denom}"
                    self.status_message = f"Only {market_wallet.get(denom, 0)} {denom} available in market."
                elif action == "deposit":
                    self.status_message = "No servant available to carry the deposit."
        return None

    def _handle_row_actions_click(self, mouse_pos, mkt, resources, stockpile_manager,
                                  servant_manager, villager_manager, furniture_manager, permit_manager):
        for it_name, rect in self.stock_dep_btns.items():
            if rect.collidepoint(mouse_pos):
                amount = self._get_quantity(it_name)
                if amount <= 0:
                    self.status_message = "Enter a quantity greater than zero."
                    return "restock_invalid_quantity"
                if getattr(mkt, "assigned_family_id", None):
                    queued = HouseholdStallSystem.request_goods_restock(
                        mkt, it_name, amount, furniture_manager,
                        stockpile_manager=stockpile_manager,
                        villager_manager=villager_manager,
                    )
                    if queued:
                        self.status_message = f"Household restock queued for {queued} {it_name}."
                        return f"household_restock_order_{it_name}"
                    self.status_message = "No Goods available from household storage."
                    return f"restock_no_stock_{it_name}"
                if servant_manager:
                    order = servant_manager.add_restock_order(
                        mkt, it_name, amount,
                        stockpile_manager=stockpile_manager,
                        resources=resources,
                        permit_manager=permit_manager
                    )
                    if order:
                        self.status_message = f"Servant order created for {order['amount']} {it_name}."
                        return f"restock_order_created_{it_name}"
                    self.status_message = "No Goods in landlord storage."
                    return f"restock_no_stock_{it_name}"
                self.status_message = "No servant available to carry the goods."
                return None

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

        if not getattr(mkt, "assigned_family_id", None):
            for it_name, rect in self.stock_with_btns.items():
                if rect.collidepoint(mouse_pos):
                    in_market = mkt.inventory.get(it_name, 0)
                    withdraw_amt = min(self._get_quantity(it_name), in_market)
                    if withdraw_amt > 0:
                        mkt.inventory[it_name] -= withdraw_amt
                        if mkt.inventory[it_name] <= 0:
                            del mkt.inventory[it_name]
                            from game.systems.economy.market_pricing import MarketPricingSystem
                            MarketPricingSystem.update_market_prices(mkt)
                        if stockpile_manager and getattr(mkt, "tiles", None):
                            target_res = MARKET_TRADEABLE_ITEMS.get(it_name, it_name)
                            market_center = mkt.get_center_world(TILE_SIZE)
                            approach = mkt.get_approach_point(market_center, TILE_SIZE, bm=None)
                            drop_tile = (int(math.floor(approach[0] / TILE_SIZE)), int(math.floor(approach[1] / TILE_SIZE)))
                            stockpile_manager.drop_resource(target_res, withdraw_amt, drop_tile[0], drop_tile[1], owner_type="landlord")
                            stockpile_manager.refresh_stacks(resources, None)
                            if servant_manager is not None:
                                servant_manager.restock_orders[:] = [
                                    o for o in getattr(servant_manager, "restock_orders", [])
                                    if not (o.get("market_building") is mkt and o.get("item_type") == it_name)
                                ]
                        else:
                            self.status_message = "No stockpile available for physical withdrawal."
                            mkt.inventory[it_name] = mkt.inventory.get(it_name, 0) + withdraw_amt
                            return f"stock_withdraw_failed_{it_name}"
                        self.status_message = f"Dropped {withdraw_amt} {it_name} near the market for servant hauling."
                        return f"stock_withdrawn_{it_name}"
                    self.status_message = f"Only {in_market} {it_name} available in market."
                    return None
        return None

    def draw(self, surface, resources=None, stockpile_manager=None, servant_manager=None, villager_manager=None, furniture_manager=None, day_number=1):
        if not self.is_open or not self.target_market:
            return

        self._ensure_fonts()
        mkt = self.target_market
        sw, sh = surface.get_width(), surface.get_height()
        self.modal_w = min(upx(840), sw - upx(40))
        self.modal_h = min(upx(590), sh - upx(40))
        m_pos = pygame.mouse.get_pos()

        # Backdrop
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        mx = (sw - self.modal_w) // 2
        my = (sh - self.modal_h) // 2
        self.modal_top = my
        modal_rect = pygame.Rect(mx, my, self.modal_w, self.modal_h)
        pygame.draw.rect(surface, COLOR_MODAL_BG, modal_rect, border_radius=upx(10))
        pygame.draw.rect(surface, (245, 158, 11), modal_rect, width=2, border_radius=upx(10))

        # Header & Mode Banner
        mode_bottom = self._draw_header_and_mode(surface, mx, my, mkt, villager_manager, m_pos)

        # Treasury Bar
        stats_bottom = self._draw_treasury_bar(surface, mx, mode_bottom + upx(8), mkt, m_pos)

        # Main Goods Table
        self._draw_goods_tab(
            surface, mx, stats_bottom + upx(12), mkt, servant_manager, resources,
            stockpile_manager, furniture_manager, villager_manager, m_pos, day_number
        )

        # Overlays
        if self.show_assign_dialog:
            self._draw_assign_dialog(surface, mx, my, mkt, villager_manager, m_pos)
        if self.show_coin_dialog:
            self._draw_coin_dialog(surface, mx, my, mkt, resources, m_pos, stockpile_manager, servant_manager)
        self._draw_item_picker(surface, mx, mkt, furniture_manager, villager_manager, stockpile_manager, m_pos)

    def _draw_header_and_mode(self, surface, mx, my, mkt, villager_manager, m_pos):
        header_y = my + upx(14)
        title_txt = f"{getattr(mkt, 'name', 'Village Market')} — Market Stall"
        surface.blit(self.font_title.render(title_txt, True, (250, 204, 21)), (mx + upx(20), header_y))

        # Close [X]
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - upx(38), my + upx(12), upx(26), upx(26))
        c_hover = self.close_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (220, 38, 38) if c_hover else (51, 65, 85), self.close_btn_rect, border_radius=upx(5))
        x_lbl = self.font_sub.render("X", True, (255, 255, 255))
        surface.blit(x_lbl, (self.close_btn_rect.centerx - x_lbl.get_width() // 2,
                             self.close_btn_rect.centery - x_lbl.get_height() // 2))

        fam_id = getattr(mkt, "assigned_family_id", None)
        assigned_fam = None
        if fam_id and villager_manager:
            assigned_fam = next((f for f in getattr(villager_manager, "families", []) if f.id == fam_id), None)

        banner_y = header_y + upx(28)
        banner_rect = pygame.Rect(mx + upx(20), banner_y, self.modal_w - upx(40), upx(38))
        pygame.draw.rect(surface, (17, 24, 39), banner_rect, border_radius=upx(6))
        border_col = (34, 197, 94) if fam_id else (245, 158, 11)
        pygame.draw.rect(surface, border_col, banner_rect, width=1, border_radius=upx(6))

        if fam_id:
            fam_label = f"The {assigned_fam.surname} Family" if assigned_fam else f"Family {fam_id}"
            pill_text = f"HOUSEHOLD STALL: {fam_label}"
            pill_bg = (20, 83, 45)
            hint_text = "Hauls surplus goods & keeps earnings during Leisure."
        else:
            pill_text = "LORD STALL (Crown Managed)"
            pill_bg = (120, 53, 15)
            hint_text = "Set prices & restock via servants. Withdraw coins below."

        pill_surf = self.font_badge.render(pill_text, True, (255, 255, 255))
        pill_rect = pygame.Rect(banner_rect.x + upx(8), banner_rect.y + upx(7), pill_surf.get_width() + upx(16), upx(24))
        pygame.draw.rect(surface, pill_bg, pill_rect, border_radius=upx(4))
        surface.blit(pill_surf, (pill_rect.x + upx(8), pill_rect.y + upx(5)))

        hint_surf = self.font_badge.render(hint_text, True, COLOR_TEXT_MUTED)
        surface.blit(hint_surf, (pill_rect.right + upx(10), banner_rect.y + upx(12)))

        # Quick Unassign + Switch/Assign Family buttons on right
        right_x = banner_rect.right - upx(8)
        self.quick_unassign_btn_rect = None
        if fam_id:
            un_w = upx(74)
            self.quick_unassign_btn_rect = pygame.Rect(right_x - un_w, banner_rect.y + upx(6), un_w, upx(26))
            u_hov = self.quick_unassign_btn_rect.collidepoint(m_pos)
            pygame.draw.rect(surface, (153, 27, 27) if u_hov else (127, 29, 29),
                             self.quick_unassign_btn_rect, border_radius=upx(4))
            u_lbl = self.font_badge.render("Unassign", True, (255, 255, 255))
            surface.blit(u_lbl, (self.quick_unassign_btn_rect.centerx - u_lbl.get_width() // 2,
                                 self.quick_unassign_btn_rect.centery - u_lbl.get_height() // 2))
            right_x = self.quick_unassign_btn_rect.left - upx(6)

        btn_w = upx(118) if fam_id else upx(132)
        self.assign_stall_btn_rect = pygame.Rect(right_x - btn_w, banner_rect.y + upx(6), btn_w, upx(26))
        as_hov = self.assign_stall_btn_rect.collidepoint(m_pos)
        pygame.draw.rect(surface, (14, 116, 144) if as_hov else (15, 23, 42),
                         self.assign_stall_btn_rect, border_radius=upx(4))
        pygame.draw.rect(surface, (56, 189, 248), self.assign_stall_btn_rect, width=1, border_radius=upx(4))
        as_txt = "Switch Family" if fam_id else "Assign to Family"
        as_lbl = self.font_badge.render(as_txt, True, (255, 255, 255))
        surface.blit(as_lbl, (self.assign_stall_btn_rect.centerx - as_lbl.get_width() // 2,
                              self.assign_stall_btn_rect.centery - as_lbl.get_height() // 2))

        self.tab_goods_rect = None
        return banner_rect.bottom

    def _draw_treasury_bar(self, surface, mx, stats_y, mkt, m_pos):
        stats_rect = pygame.Rect(mx + upx(20), stats_y, self.modal_w - upx(40), upx(48))
        pygame.draw.rect(surface, (24, 34, 52), stats_rect, border_radius=upx(6))
        pygame.draw.rect(surface, (71, 85, 105), stats_rect, width=1, border_radius=upx(6))

        fam_assigned_id = getattr(mkt, "assigned_family_id", None)
        curr = normalize_wallet(getattr(mkt, "currency", {}))
        total_mkt_c = to_copper(curr)

        t_x = stats_rect.x + upx(14)
        title_txt = "STALL CASHBOX (Pending Family Pickup):" if fam_assigned_id else "MARKET TREASURY:"
        surface.blit(self.font_badge.render(title_txt, True, COLOR_TEXT_MUTED), (t_x, stats_rect.y + upx(7)))

        bal_y = stats_rect.y + upx(23)
        surface.blit(self.font_sub.render(f"{curr['Gold']} Gold", True, (250, 204, 21)), (t_x, bal_y))
        surface.blit(self.font_sub.render(f"{curr['Silver']} Silver", True, (203, 213, 225)), (t_x + upx(84), bal_y))
        surface.blit(self.font_sub.render(f"{curr['Copper']} Copper", True, (184, 115, 51)), (t_x + upx(172), bal_y))
        surface.blit(self.font_body.render(f"({total_mkt_c}c)  •  Storage: ∞", True, COLOR_TEXT_MUTED),
                     (t_x + upx(266), bal_y + 1))

        landlord_owned = not fam_assigned_id
        self.deposit_coin_btn_rect = pygame.Rect(stats_rect.right - upx(184), stats_rect.y + upx(10), upx(84), upx(28)) if landlord_owned else None
        self.withdraw_coin_btn_rect = pygame.Rect(stats_rect.right - upx(94), stats_rect.y + upx(10), upx(84), upx(28)) if landlord_owned else None
        if landlord_owned:
            dep_hov = self.deposit_coin_btn_rect.collidepoint(m_pos)
            pygame.draw.rect(surface, (22, 101, 52) if dep_hov else (20, 83, 45), self.deposit_coin_btn_rect, border_radius=upx(4))
            pygame.draw.rect(surface, (74, 222, 128), self.deposit_coin_btn_rect, width=1, border_radius=upx(4))
            d_lbl = self.font_badge.render("Deposit", True, (255, 255, 255))
            surface.blit(d_lbl, (self.deposit_coin_btn_rect.centerx - d_lbl.get_width() // 2,
                                 self.deposit_coin_btn_rect.centery - d_lbl.get_height() // 2))

            with_hov = self.withdraw_coin_btn_rect.collidepoint(m_pos)
            pygame.draw.rect(surface, (153, 27, 27) if with_hov else (127, 29, 29), self.withdraw_coin_btn_rect, border_radius=upx(4))
            pygame.draw.rect(surface, (248, 113, 113), self.withdraw_coin_btn_rect, width=1, border_radius=upx(4))
            w_lbl = self.font_badge.render("Withdraw", True, (255, 255, 255))
            surface.blit(w_lbl, (self.withdraw_coin_btn_rect.centerx - w_lbl.get_width() // 2,
                                 self.withdraw_coin_btn_rect.centery - w_lbl.get_height() // 2))
        else:
            note = self.font_badge.render("Family collects coins automatically", True, (134, 239, 172))
            surface.blit(note, (stats_rect.right - note.get_width() - upx(14), stats_rect.y + upx(17)))

        return stats_rect.bottom

    def _get_quantity(self, item_name):
        raw = self.quantity_values.get(item_name, str(MARKET_QUANTITY_DEFAULT))
        try:
            return max(0, min(MARKET_QUANTITY_MAX, int(raw)))
        except (TypeError, ValueError):
            return 0

    def _num_field_value(self, fld):
        mkt = self.target_market
        if fld["kind"] == "alloc":
            val = int(mkt.item_allocations.get(
                fld["item"], MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT))
            return max(MARKET_HOUSEHOLD_SALE_PERCENT_MIN, min(MARKET_HOUSEHOLD_SALE_PERCENT_MAX, val))
        return int(mkt.prices.get(fld["item"], DEFAULT_ITEM_PRICES.get(fld["item"], 1)))

    def _commit_num_field(self):
        key = self.num_input.active_key
        fld = self.num_fields.get(key)
        text = self.num_input.text.strip()
        self.num_input.cancel()
        if fld is None or not text.isdigit():
            return
        mkt = self.target_market
        min_val = int(fld.get("min", MARKET_HOUSEHOLD_SALE_PERCENT_MIN if fld.get("kind") == "alloc" else 0))
        max_val = int(fld.get("max", MARKET_HOUSEHOLD_SALE_PERCENT_MAX if fld.get("kind") == "alloc" else 9999999))
        val = max(min_val, min(max_val, int(text)))
        if fld["kind"] == "alloc":
            HouseholdStallSystem.set_item_allocation(mkt, fld["item"], val)
        elif fld["kind"] == "price":
            mkt.auto_pricing = False
            mkt.prices[fld["item"]] = val

    def _draw_num_input(self, surface, key, rect, display_value, is_percent=False):
        active = (self.num_input.active_key == key)
        bg = (15, 23, 42) if not active else (30, 58, 138)
        border = (250, 204, 21) if active else (71, 85, 105)
        pygame.draw.rect(surface, bg, rect, border_radius=upx(4))
        pygame.draw.rect(surface, border, rect, width=2 if active else 1, border_radius=upx(4))
        if active:
            txt = (self.num_input.text + "_") + ("%" if is_percent else "")
        else:
            txt = f"{display_value}%" if is_percent else str(display_value)
        t = self.font_badge.render(txt, True, (250, 204, 21) if is_percent else (255, 255, 255))
        surface.blit(t, (rect.centerx - t.get_width() // 2,
                         rect.centery - t.get_height() // 2))

    @staticmethod
    def _draw_small_btn(surface, rect, label, bg, hover_bg, m_pos, font, border_col=None):
        hov = rect.collidepoint(m_pos)
        pygame.draw.rect(surface, hover_bg if hov else bg, rect, border_radius=upx(4))
        if border_col:
            pygame.draw.rect(surface, border_col, rect, width=1, border_radius=upx(4))
        lbl = font.render(label, True, (255, 255, 255))
        surface.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.centery - lbl.get_height() // 2))

    def _draw_goods_tab(self, surface, mx, list_y, mkt, servant_manager, resources,
                        stockpile_manager, furniture_manager, villager_manager, m_pos,
                        day_number=1):
        """Draw explicitly listed market goods with beginner-friendly controls."""
        assigned = bool(getattr(mkt, "assigned_family_id", None))
        self._clear_interactive_rects()

        row_x = mx + upx(20)
        row_w = self.modal_w - upx(40)
        tradeable_items = [it for it in getattr(mkt, "sale_items", []) if it in MARKET_TRADEABLE_ITEMS]

        # Section Header + Action Buttons
        surface.blit(
            self.font_sub.render(f"GOODS FOR SALE ({len(tradeable_items)})", True, COLOR_TEXT_TITLE),
            (row_x, list_y + upx(4))
        )

        btn_right = row_x + row_w
        self.add_item_btn_rect = pygame.Rect(btn_right - upx(138), list_y - 2, upx(138), upx(26))
        self._draw_small_btn(surface, self.add_item_btn_rect, "+ Add Item",
                             (20, 83, 45), (22, 101, 52), m_pos, self.font_badge, (74, 222, 128))

        if assigned:
            self.auto_list_btn_rect = pygame.Rect(self.add_item_btn_rect.left - upx(150), list_y - 2, upx(142), upx(26))
            self._draw_small_btn(surface, self.auto_list_btn_rect, "Auto-List Surplus",
                                 (30, 58, 138), (37, 99, 235), m_pos, self.font_badge, (96, 165, 250))

        # Column Header
        row_top = list_y + upx(30)
        table = pygame.Rect(row_x, row_top, row_w, upx(24))
        pygame.draw.rect(surface, (30, 41, 59), table, border_radius=upx(4))
        if assigned:
            labels = (
                (row_x + upx(12), "ITEM"),
                (row_x + upx(184), "STALL / HOME"),
                (row_x + upx(324), "AUTO PRICE"),
                (row_x + upx(420), "SALE CAP %"),
                (row_x + upx(568), "LORD BUY"),
                (table.right - upx(34), "DEL"),
            )
        else:
            labels = (
                (row_x + upx(12), "ITEM"),
                (row_x + upx(204), "STALL STOCK"),
                (row_x + upx(308), "PRICE (Copper)"),
                (row_x + upx(468), "BATCH QTY"),
                (row_x + upx(550), "ACTIONS"),
            )
        for lx, label in labels:
            surface.blit(self.font_badge.render(label, True, COLOR_TEXT_MUTED), (lx, row_top + upx(5)))

        # Paginated Rows
        items_per_page = MARKET_UI_ITEMS_PER_PAGE
        total_pages = max(1, math.ceil(len(tradeable_items) / items_per_page))
        self.goods_page = max(0, min(getattr(self, "goods_page", 0), total_pages - 1))
        page_items = tradeable_items[self.goods_page * items_per_page:(self.goods_page + 1) * items_per_page]
        row_y = row_top + upx(28)
        row_h = upx(62) if assigned else upx(52)

        for item_name in page_items:
            card = pygame.Rect(row_x, row_y, row_w, row_h)
            pygame.draw.rect(surface, (15, 23, 42), card, border_radius=upx(5))
            pygame.draw.rect(surface, (30, 41, 59), card, width=1, border_radius=upx(5))
            if assigned:
                self._draw_household_row(
                    surface, card, mkt, item_name, furniture_manager,
                    stockpile_manager, villager_manager, m_pos
                )
            else:
                self._draw_lord_row(
                    surface, card, mkt, item_name, servant_manager,
                    stockpile_manager, resources, m_pos
                )
            row_y += row_h + upx(4)

        if not page_items:
            self._draw_empty_goods_state(surface, row_x, row_y, row_w, assigned, m_pos)

        list_bottom = row_top + upx(28) + items_per_page * (row_h + upx(4))
        self.goods_list_rect = pygame.Rect(row_x, row_top + upx(28), row_w, max(1, list_bottom - (row_top + upx(28))))

        # Status & Pagination Footer Bar
        footer_y = list_bottom + upx(4)
        self._draw_list_footer(surface, row_x, row_w, footer_y, total_pages, m_pos)

        # Sales Report Box
        self._draw_sales_report(surface, row_x, row_w, footer_y + upx(30), mkt, day_number)

    def _draw_lord_row(self, surface, card, mkt, item_name, servant_manager,
                       stockpile_manager, resources, m_pos):
        rx, ry, rh = card.x, card.y, card.height
        draw_item_icon(surface, item_name, rx + upx(20), ry + rh // 2, size=upx(10))
        surface.blit(self.font_sub.render(item_name.replace("_", " "), True, (241, 245, 249)), (rx + upx(38), ry + upx(8)))
        pile_qty = self._landlord_stockpile_qty(item_name, stockpile_manager, resources)
        surface.blit(self.font_badge.render(f"Stockpile: {pile_qty}", True, COLOR_TEXT_MUTED), (rx + upx(38), ry + upx(29)))

        # Stall Stock + optional in-transit
        stock = max(0, int(mkt.inventory.get(item_name, 0)))
        stock_col = (34, 197, 94) if stock else (239, 68, 68)
        surface.blit(self.font_sub.render(str(stock), True, stock_col), (rx + upx(212), ry + upx(9)))
        in_transit = (
            servant_manager.get_in_transit_for_market(mkt, item_name)
            if servant_manager and hasattr(servant_manager, "get_in_transit_for_market") else 0
        )
        if in_transit > 0:
            surface.blit(self.font_badge.render(f"+{in_transit} hauling", True, (96, 165, 250)), (rx + upx(212), ry + upx(29)))

        # Unified PRICE (Copper) with - / + steppers & denomination preview
        price = max(1, int(MarketService.get_item_price(item_name, mkt)))
        p_x = rx + upx(306)
        dec_r = pygame.Rect(p_x, ry + upx(6), upx(22), upx(24))
        box_r = pygame.Rect(dec_r.right + upx(3), ry + upx(6), upx(52), upx(24))
        inc_r = pygame.Rect(box_r.right + upx(3), ry + upx(6), upx(22), upx(24))
        self.price_step_btns[(item_name, -MARKET_PRICE_STEP)] = dec_r
        self.price_step_btns[(item_name, MARKET_PRICE_STEP)] = inc_r
        self._draw_small_btn(surface, dec_r, "-", (30, 41, 59), (51, 65, 85), m_pos, self.font_badge)
        price_key = ("num", "price", item_name)
        self.num_fields[price_key] = {"rect": box_r, "kind": "price", "item": item_name, "min": 1, "max": 9999999}
        self._draw_num_input(surface, price_key, box_r, price)
        self._draw_small_btn(surface, inc_r, "+", (30, 41, 59), (51, 65, 85), m_pos, self.font_badge)

        surface.blit(self.font_badge.render(self._format_copper(price), True, (250, 204, 21)), (p_x, ry + upx(33)))
        base_p = max(1, int(DEFAULT_ITEM_PRICES.get(item_name, 1)))
        if price != base_p:
            auto_r = pygame.Rect(inc_r.right + upx(6), ry + upx(8), upx(36), upx(20))
            self.price_auto_btns[item_name] = auto_r
            self._draw_small_btn(surface, auto_r, "Base", (51, 65, 85), (71, 85, 105), m_pos, self.font_badge)

        # Batch QTY input
        qty_x = rx + upx(470)
        qty_rect = pygame.Rect(qty_x, ry + upx(7), upx(54), upx(24))
        self.stock_quantity_rects[item_name] = qty_rect
        qty_text = self.quantity_values.setdefault(item_name, str(MARKET_QUANTITY_DEFAULT))
        pygame.draw.rect(surface, (15, 23, 42), qty_rect, border_radius=3)
        q_col = (250, 204, 21) if self.focused_quantity == item_name else (71, 85, 105)
        pygame.draw.rect(surface, q_col, qty_rect, width=1, border_radius=3)
        qty_surf = self.font_badge.render(qty_text or "0", True, (255, 255, 255))
        surface.blit(qty_surf, (qty_rect.centerx - qty_surf.get_width() // 2, qty_rect.centery - qty_surf.get_height() // 2))
        surface.blit(self.font_badge.render("click qty", True, COLOR_TEXT_MUTED), (qty_x + upx(2), ry + upx(34)))

        # Action buttons anchored cleanly from card.right
        remove = pygame.Rect(card.right - upx(34), ry + upx(13), upx(24), upx(24))
        withdraw = pygame.Rect(remove.left - upx(84), ry + upx(13), upx(78), upx(24))
        restock = pygame.Rect(withdraw.left - upx(80), ry + upx(13), upx(74), upx(24))
        self.stock_remove_btns[item_name] = remove
        self.stock_with_btns[item_name] = withdraw
        self.stock_dep_btns[item_name] = restock

        self._draw_small_btn(surface, restock, "Restock", (30, 58, 138), (37, 99, 235), m_pos, self.font_badge)
        self._draw_small_btn(surface, withdraw, "Withdraw", (120, 53, 15), (146, 64, 14), m_pos, self.font_badge)
        self._draw_small_btn(surface, remove, "X", (127, 29, 29), (185, 28, 28), m_pos, self.font_badge)

    def _draw_household_row(self, surface, card, mkt, item_name, furniture_manager,
                            stockpile_manager, villager_manager, m_pos):
        rx, ry, rh = card.x, card.y, card.height
        fam_id = getattr(mkt, "assigned_family_id", None)
        summary = HouseholdStallSystem.get_household_stock_summary(
            mkt, fam_id, item_name, furniture_manager,
            stockpile_manager=stockpile_manager, villager_manager=villager_manager
        )

        draw_item_icon(surface, item_name, rx + upx(20), ry + rh // 2, size=upx(10))
        surface.blit(self.font_sub.render(item_name.replace("_", " "), True, (241, 245, 249)), (rx + upx(38), ry + upx(12)))
        if item_name in TOOL_TYPES:
            surface.blit(self.font_badge.render("[Tool — manual]", True, (251, 191, 36)), (rx + upx(38), ry + upx(34)))
        else:
            cat = MARKET_TRADEABLE_ITEMS.get(item_name, "")
            surface.blit(self.font_badge.render(cat, True, COLOR_TEXT_MUTED), (rx + upx(38), ry + upx(34)))

        # STALL / HOME column
        sh_x = rx + upx(184)
        stall_stock = summary["stall_stock"]
        stall_col = (34, 197, 94) if stall_stock else (239, 68, 68)
        stall_txt = f"{stall_stock} at stall"
        if summary["in_transit"] > 0:
            stall_txt += f" (+{summary['in_transit']})"
        surface.blit(self.font_badge.render(stall_txt, True, stall_col), (sh_x, ry + upx(12)))

        home_txt = f"{summary['home_stock']} home"
        if summary["reserve"] > 0:
            home_txt += f" (keep {summary['reserve']})"
        surface.blit(self.font_badge.render(home_txt, True, (148, 163, 184)), (sh_x, ry + upx(34)))

        # AUTO PRICE column
        price = MarketService.get_item_price(item_name, mkt)
        surface.blit(self.font_badge.render(self._format_copper(price), True, (250, 204, 21)), (rx + upx(324), ry + upx(14)))
        surface.blit(self.font_badge.render("Scarcity Auto", True, COLOR_TEXT_MUTED), (rx + upx(324), ry + upx(34)))

        # SALE CAP % stepper + live sellable cap
        cap_x = rx + upx(418)
        pct = HouseholdStallSystem.get_item_allocation(mkt, item_name)
        dec_r = pygame.Rect(cap_x, ry + upx(9), upx(22), upx(24))
        pct_rect = pygame.Rect(dec_r.right + upx(3), ry + upx(9), upx(48), upx(24))
        inc_r = pygame.Rect(pct_rect.right + upx(3), ry + upx(9), upx(22), upx(24))
        self.alloc_step_btns[(item_name, -MARKET_ALLOC_STEP)] = dec_r
        self.alloc_step_btns[(item_name, MARKET_ALLOC_STEP)] = inc_r
        self._draw_small_btn(surface, dec_r, "-", (30, 41, 59), (51, 65, 85), m_pos, self.font_badge)
        pct_key = ("num", "alloc", item_name)
        self.num_fields[pct_key] = {
            "rect": pct_rect, "kind": "alloc", "item": item_name,
            "min": MARKET_HOUSEHOLD_SALE_PERCENT_MIN, "max": MARKET_HOUSEHOLD_SALE_PERCENT_MAX,
        }
        self._draw_num_input(surface, pct_key, pct_rect, pct, is_percent=True)
        self._draw_small_btn(surface, inc_r, "+", (30, 41, 59), (51, 65, 85), m_pos, self.font_badge)

        cap_info = f"Sell up to {summary['max_alloc']} (surplus {summary['surplus']})"
        cap_col = (134, 239, 172) if summary["max_alloc"] > 0 else COLOR_TEXT_MUTED
        surface.blit(self.font_badge.render(cap_info, True, cap_col), (cap_x, ry + upx(38)))

        # LORD BUY column
        lb_x = rx + upx(568)
        qty_rect = pygame.Rect(lb_x, ry + upx(9), upx(44), upx(24))
        self.buy_qty_rects[item_name] = qty_rect
        qty_text = self.quantity_values.setdefault(item_name, str(MARKET_QUANTITY_DEFAULT))
        pygame.draw.rect(surface, (15, 23, 42), qty_rect, border_radius=3)
        q_border = (250, 204, 21) if self.focused_quantity == item_name else (71, 85, 105)
        pygame.draw.rect(surface, q_border, qty_rect, width=1, border_radius=3)
        qty_surf = self.font_badge.render(qty_text or "0", True, (255, 255, 255))
        surface.blit(qty_surf, (qty_rect.centerx - qty_surf.get_width() // 2, qty_rect.centery - qty_surf.get_height() // 2))

        buy_rect = pygame.Rect(qty_rect.right + upx(6), ry + upx(9), upx(54), upx(24))
        self.buy_btns[item_name] = buy_rect
        self._draw_small_btn(surface, buy_rect, "BUY", (20, 83, 45), (22, 101, 52), m_pos, self.font_badge, (74, 222, 128))

        try:
            est_qty = max(0, min(MARKET_QUANTITY_MAX, int(qty_text or 0)))
        except (TypeError, ValueError):
            est_qty = 0
        surface.blit(self.font_badge.render(f"~{price * est_qty}c", True, (250, 204, 21)),
                     (buy_rect.right + upx(6), ry + upx(14)))
        surface.blit(self.font_badge.render("Buy -> Lord Stockpile", True, COLOR_TEXT_MUTED),
                     (lb_x, ry + upx(38)))

        # Remove [X]
        remove = pygame.Rect(card.right - upx(34), ry + upx(18), upx(24), upx(24))
        self.stock_remove_btns[item_name] = remove
        self._draw_small_btn(surface, remove, "X", (127, 29, 29), (185, 28, 28), m_pos, self.font_badge)

    def _draw_empty_goods_state(self, surface, row_x, row_y, row_w, assigned, m_pos):
        empty = pygame.Rect(row_x, row_y, row_w, upx(104))
        pygame.draw.rect(surface, (15, 23, 42), empty, border_radius=upx(6))
        pygame.draw.rect(surface, (51, 65, 85), empty, width=1, border_radius=upx(6))
        msg = (
            "No goods listed yet. Family only sells surplus goods you list (tools are protected)."
            if assigned else
            "Stall is empty. Add items to sell or quick-add common village goods."
        )
        txt = self.font_body.render(msg, True, COLOR_TEXT_MUTED)
        surface.blit(txt, (empty.centerx - txt.get_width() // 2, empty.y + upx(20)))

        if assigned:
            btn = pygame.Rect(empty.centerx - upx(96), empty.y + upx(52), upx(192), upx(30))
            self.auto_list_btn_rect = btn
            self._draw_small_btn(surface, btn, "Auto-List Household Surplus",
                                 (30, 58, 138), (37, 99, 235), m_pos, self.font_badge, (96, 165, 250))
        else:
            btn = pygame.Rect(empty.centerx - upx(96), empty.y + upx(52), upx(192), upx(30))
            self.quick_add_common_rect = btn
            self._draw_small_btn(surface, btn, "+ Quick Add Common Goods",
                                 (20, 83, 45), (22, 101, 52), m_pos, self.font_badge, (74, 222, 128))

    def _draw_list_footer(self, surface, row_x, row_w, footer_y, total_pages, m_pos):
        if self.status_message:
            is_err = any(w in self.status_message for w in ("No Goods", "Cannot", "Only ", "Enter "))
            col = (248, 113, 113) if is_err else (134, 239, 172)
            surface.blit(self.font_badge.render(self.status_message, True, col), (row_x + upx(4), footer_y + upx(6)))

        right = row_x + row_w
        self.page_next_rect = pygame.Rect(right - upx(56), footer_y, upx(56), upx(24))
        pg_lbl = self.font_badge.render(f"Page {self.goods_page + 1}/{total_pages}", True, COLOR_TEXT_MUTED)
        pg_x = self.page_next_rect.left - pg_lbl.get_width() - upx(10)
        self.page_prev_rect = pygame.Rect(pg_x - upx(64), footer_y, upx(56), upx(24))

        can_prev = self.goods_page > 0
        can_next = self.goods_page < total_pages - 1
        self._draw_small_btn(
            surface, self.page_prev_rect, "< Prev",
            (30, 41, 59) if can_prev else (17, 24, 39),
            (51, 65, 85) if can_prev else (17, 24, 39),
            m_pos, self.font_badge, (71, 85, 105) if can_prev else (30, 41, 59)
        )
        surface.blit(pg_lbl, (pg_x, footer_y + upx(5)))
        self._draw_small_btn(
            surface, self.page_next_rect, "Next >",
            (30, 41, 59) if can_next else (17, 24, 39),
            (51, 65, 85) if can_next else (17, 24, 39),
            m_pos, self.font_badge, (71, 85, 105) if can_next else (30, 41, 59)
        )

    def _draw_sales_report(self, surface, row_x, row_w, report_top, mkt, day_number):
        from game.systems.economy.market_sales_report import MarketSalesReportSystem
        report = MarketSalesReportSystem.get_report(mkt, day_number)
        report_bottom = self.modal_top + self.modal_h - upx(12)
        report_rect = pygame.Rect(row_x, report_top, row_w, max(upx(46), report_bottom - report_top))
        pygame.draw.rect(surface, (15, 23, 42), report_rect, border_radius=upx(5))
        pygame.draw.rect(surface, (51, 65, 85), report_rect, width=1, border_radius=upx(5))
        report_title = self.font_badge.render(
            f"TOTAL SALES - DAYS {report['start_day']} to {report['end_day']} (THROUGH DAY {min(day_number, report['end_day'])})",
            True, COLOR_TEXT_TITLE,
        )
        surface.blit(report_title, (report_rect.x + upx(10), report_rect.y + upx(6)))
        sold_items = sorted(report["items"].items(), key=lambda pair: pair[0].casefold())
        if not sold_items:
            surface.blit(self.font_body.render("No sales recorded in this 10-day period.", True, COLOR_TEXT_MUTED),
                         (report_rect.x + upx(10), report_rect.y + upx(24)))
            return

        row_height = upx(16)
        rows_per_column = max(1, (report_rect.height - upx(26)) // row_height)
        visible_count = min(len(sold_items), rows_per_column * 2)
        column_width = (report_rect.width - upx(20)) // 2
        for idx, (item_name, sale) in enumerate(sold_items[:visible_count]):
            col, row = divmod(idx, rows_per_column)
            item_x = report_rect.x + upx(10) + col * column_width
            item_y = report_rect.y + upx(24) + row * row_height
            qty = max(0, int(sale.get("quantity", 0)))
            earnings = self._format_copper(sale.get("revenue_copper", 0))
            label = self.font_badge.render(f"{item_name}: {qty} sold, {earnings} earned", True, COLOR_TEXT_MAIN)
            surface.blit(label, (item_x, item_y))
        if visible_count < len(sold_items):
            more = self.font_badge.render(f"+ {len(sold_items) - visible_count} more items", True, COLOR_TEXT_MUTED)
            surface.blit(more, (report_rect.right - more.get_width() - upx(10), report_rect.bottom - more.get_height() - upx(5)))

    def _draw_item_picker(self, surface, mx, mkt, furniture_manager, villager_manager, stockpile_manager, m_pos):
        self.item_picker_rects.clear()
        self.picker_dialog_rect = None
        self.picker_list_rect = None
        self.picker_done_rect = None
        self.picker_cancel_rect = None
        self.picker_select_all_rect = None
        if not self.show_item_picker:
            return

        selectable = self._get_picker_selectable(
            mkt, furniture_manager, villager_manager, stockpile_manager
        )
        self.picker_items = selectable
        assigned = bool(getattr(mkt, "assigned_family_id", None))

        dlg_w = upx(500)
        dlg_h = min(upx(470), self.modal_h - upx(70))
        dlg_x = mx + (self.modal_w - dlg_w) // 2
        dlg_y = self.modal_top + (self.modal_h - dlg_h) // 2
        self.picker_dialog_rect = pygame.Rect(dlg_x, dlg_y, dlg_w, dlg_h)
        pygame.draw.rect(surface, (15, 23, 42), self.picker_dialog_rect, border_radius=upx(10))
        pygame.draw.rect(surface, (96, 165, 250), self.picker_dialog_rect, width=2, border_radius=upx(10))

        surface.blit(self.font_sub.render("Add items to sell", True, COLOR_TEXT_TITLE),
                     (dlg_x + upx(16), dlg_y + upx(12)))

        if selectable:
            self.picker_select_all_rect = pygame.Rect(self.picker_dialog_rect.right - upx(172), dlg_y + upx(10), upx(82), upx(22))
            all_sel = len(self.picker_selected) >= len(selectable)
            self._draw_small_btn(surface, self.picker_select_all_rect, "Clear All" if all_sel else "Select All",
                                 (30, 41, 59), (51, 65, 85), m_pos, self.font_badge, (71, 85, 105))

        sel_count = len(self.picker_selected)
        count_txt = self.font_badge.render(f"{sel_count} selected", True, COLOR_TEXT_MUTED)
        surface.blit(count_txt, (self.picker_dialog_rect.right - upx(16) - count_txt.get_width(), dlg_y + upx(15)))

        row_h = upx(42)
        list_x = dlg_x + upx(16)
        list_y = dlg_y + upx(44)
        list_w = dlg_w - upx(32)
        btn_zone = upx(52)
        visible_rows = max(1, (dlg_h - (list_y - dlg_y) - btn_zone) // row_h)
        list_h = visible_rows * row_h
        self.picker_list_rect = pygame.Rect(list_x, list_y, list_w, list_h)
        max_scroll = max(0, len(selectable) * row_h - list_h)
        self.picker_scroll = max(0, min(self.picker_scroll, max_scroll))

        clip = self.picker_list_rect.clip(self.picker_dialog_rect)
        surface.set_clip(clip)
        for idx, item_name in enumerate(selectable):
            ry = list_y + idx * row_h - self.picker_scroll
            if ry + row_h - 4 < list_y or ry > list_y + list_h:
                continue
            item_rect = pygame.Rect(list_x + upx(6), ry, list_w - upx(12), row_h - upx(5))
            self.item_picker_rects[item_name] = item_rect
            checked = item_name in self.picker_selected
            bg = (30, 58, 138) if checked else (30, 41, 59)
            border = (96, 165, 250) if checked else (51, 65, 85)
            pygame.draw.rect(surface, bg, item_rect, border_radius=upx(6))
            pygame.draw.rect(surface, border, item_rect, width=1, border_radius=upx(6))

            cb = pygame.Rect(item_rect.right - upx(30), item_rect.centery - upx(8), upx(16), upx(16))
            pygame.draw.rect(surface, (15, 23, 42), cb, border_radius=3)
            if checked:
                pygame.draw.rect(surface, (59, 130, 246), cb, border_radius=3)
                chk = self.font_badge.render("✓", True, (255, 255, 255))
                surface.blit(chk, (cb.centerx - chk.get_width() // 2, cb.centery - chk.get_height() // 2))
            else:
                pygame.draw.rect(surface, (96, 165, 250), cb, width=1, border_radius=3)

            draw_item_icon(surface, item_name, item_rect.x + upx(26), item_rect.centery, size=upx(13))
            name_txt = self.font_sub.render(item_name.replace("_", " "), True, (241, 245, 249))
            surface.blit(name_txt, (item_rect.x + upx(48), item_rect.y + upx(6)))

            is_tool = item_name in TOOL_TYPES
            cat_str = "Tool (worker job tools protected)" if (is_tool and assigned) else ("Tool" if is_tool else MARKET_TRADEABLE_ITEMS.get(item_name, "Good"))
            cat_col = (251, 191, 36) if is_tool else COLOR_TEXT_MUTED
            surface.blit(self.font_badge.render(cat_str, True, cat_col), (item_rect.x + upx(48), item_rect.y + upx(21)))
        surface.set_clip(None)

        if not selectable:
            empty_label = ("No eligible household goods are available in storage."
                           if assigned
                           else "All supported goods are already listed at this stall.")
            surface.blit(self.font_body.render(empty_label, True, COLOR_TEXT_MUTED),
                         (list_x + upx(8), list_y + upx(10)))
        elif max_scroll > 0:
            track = pygame.Rect(list_x + list_w - upx(8), list_y + upx(4), upx(4), list_h - upx(8))
            pygame.draw.rect(surface, (30, 41, 59), track, border_radius=2)
            thumb_h = max(upx(16), int(list_h * list_h / (len(selectable) * row_h)))
            thumb_y = list_y + 4 + int((list_h - upx(8) - thumb_h) * (self.picker_scroll / max_scroll))
            pygame.draw.rect(surface, (96, 165, 250), (track.x, thumb_y, upx(4), thumb_h), border_radius=2)

        btn_y = dlg_y + dlg_h - upx(42)
        self.picker_cancel_rect = pygame.Rect(dlg_x + upx(16), btn_y, upx(110), upx(30))
        self.picker_done_rect = pygame.Rect(dlg_x + dlg_w - upx(16) - upx(150), btn_y, upx(150), upx(30))
        self._draw_small_btn(surface, self.picker_cancel_rect, "Cancel", (51, 65, 85), (71, 85, 105), m_pos, self.font_btn)
        done_bg = (22, 101, 52) if sel_count else (30, 58, 138)
        done_hov = (20, 83, 45) if sel_count else (37, 99, 235)
        self._draw_small_btn(surface, self.picker_done_rect, f"Done ({sel_count})", done_bg, done_hov, m_pos, self.font_btn)

    def _get_picker_selectable(self, mkt, furniture_manager, villager_manager, stockpile_manager):
        if getattr(mkt, "assigned_family_id", None):
            owned_items = HouseholdStallSystem.get_household_owned_sale_items(
                mkt.assigned_family_id, furniture_manager,
                villager_manager, stockpile_manager
            )
            return [it for it in MARKET_TRADEABLE_ITEMS
                    if it in owned_items and it not in getattr(mkt, "sale_items", [])]
        return [it for it in MARKET_TRADEABLE_ITEMS
                if it not in getattr(mkt, "sale_items", [])]

    def _apply_picker_selection(self, mkt, furniture_manager, villager_manager, stockpile_manager):
        owned = None
        if getattr(mkt, "assigned_family_id", None):
            owned = HouseholdStallSystem.get_household_owned_sale_items(
                mkt.assigned_family_id, furniture_manager,
                villager_manager, stockpile_manager
            )
        added = skipped = 0
        for item_name in self.picker_items:
            if item_name not in self.picker_selected:
                continue
            if item_name in getattr(mkt, "sale_items", []):
                continue
            if owned is not None and item_name not in owned:
                skipped += 1
                continue
            mkt.sale_items.append(item_name)
            mkt.prices.setdefault(item_name, DEFAULT_ITEM_PRICES.get(item_name, 1))
            if getattr(mkt, "assigned_family_id", None):
                mkt.item_allocations.setdefault(item_name, MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT)
            added += 1
        return added, skipped

    def _draw_assign_dialog(self, surface, mx, my, mkt, villager_manager, m_pos):
        """Displays modal dialog for assigning stall to a peasant household."""
        dlg_w = upx(460)
        dlg_h = upx(340)
        dlg_x = mx + (self.modal_w - dlg_w) // 2
        dlg_y = my + (self.modal_h - dlg_h) // 2

        pygame.draw.rect(surface, (15, 23, 42), (dlg_x, dlg_y, dlg_w, dlg_h), border_radius=upx(10))
        pygame.draw.rect(surface, (56, 189, 248), (dlg_x, dlg_y, dlg_w, dlg_h), width=2, border_radius=upx(10))

        surface.blit(self.font_title.render("Assign Stall To Household", True, (250, 204, 21)), (dlg_x + upx(20), dlg_y + upx(14)))
        surface.blit(self.font_body.render("Select a family to haul & sell their surplus goods here:", True, COLOR_TEXT_MUTED),
                     (dlg_x + upx(20), dlg_y + upx(40)))

        self.close_assign_dlg_btn_rect = pygame.Rect(dlg_x + dlg_w - upx(34), dlg_y + upx(12), upx(22), upx(22))
        self._draw_small_btn(surface, self.close_assign_dlg_btn_rect, "X", (51, 65, 85), (220, 38, 38), m_pos, self.font_badge)

        self.family_assign_btn_rects.clear()
        fam_list = getattr(villager_manager, "families", []) if villager_manager else []

        row_h = upx(44)
        list_rect = pygame.Rect(dlg_x + upx(20), dlg_y + upx(66), dlg_w - upx(40), dlg_h - upx(124))
        self.assign_list_rect = list_rect
        max_scroll = max(0, len(fam_list) * row_h - list_rect.height)
        self.assign_scroll = max(0, min(self.assign_scroll, max_scroll))

        surface.set_clip(list_rect)
        for idx, fam in enumerate(fam_list):
            f_y = list_rect.y + idx * row_h - self.assign_scroll
            if f_y + row_h < list_rect.y or f_y > list_rect.bottom:
                continue
            f_rect = pygame.Rect(list_rect.x, f_y, list_rect.width - (upx(8) if max_scroll > 0 else 0), upx(38))
            is_cur = (getattr(mkt, "assigned_family_id", None) == fam.id)
            pygame.draw.rect(surface, (30, 58, 138) if is_cur else (30, 41, 59), f_rect, border_radius=upx(6))
            pygame.draw.rect(surface, (56, 189, 248) if is_cur else (51, 65, 85), f_rect, width=1, border_radius=upx(6))

            surface.blit(self.font_sub.render(f"The {fam.surname} Family", True, (255, 255, 255)), (f_rect.x + upx(12), f_rect.y + upx(10)))
            surface.blit(self.font_badge.render(f"({len(fam.members)} members)", True, (148, 163, 184)), (f_rect.x + upx(180), f_rect.y + upx(12)))

            btn_a = pygame.Rect(f_rect.right - upx(88), f_rect.y + upx(7), upx(80), upx(24))
            self.family_assign_btn_rects[fam.id] = btn_a
            a_lbl = "Assigned" if is_cur else "Assign"
            self._draw_small_btn(surface, btn_a, a_lbl, (20, 83, 45), (22, 101, 52), m_pos, self.font_badge)
        surface.set_clip(None)

        if not fam_list:
            surface.blit(self.font_body.render("No settled families available yet.", True, COLOR_TEXT_MUTED),
                         (list_rect.x + upx(8), list_rect.y + upx(12)))

        self.unassign_stall_btn_rect = pygame.Rect(dlg_x + upx(20), dlg_y + dlg_h - upx(44), upx(210), upx(30))
        self._draw_small_btn(surface, self.unassign_stall_btn_rect, "Unassign (Revert to Crown)",
                             (153, 27, 27), (127, 29, 29), m_pos, self.font_badge)

    def _draw_coin_dialog(self, surface, mx, my, mkt, resources, m_pos, stockpile_manager=None, servant_manager=None):
        """Quantity-based physical coin deposit or withdrawal controls."""
        action = self.show_coin_dialog
        dlg_w, dlg_h = upx(420), upx(240)
        dlg_x = mx + (self.modal_w - dlg_w) // 2
        dlg_y = my + (self.modal_h - dlg_h) // 2
        pygame.draw.rect(surface, (15, 23, 42), (dlg_x, dlg_y, dlg_w, dlg_h), border_radius=upx(10))
        pygame.draw.rect(surface, (245, 158, 11), (dlg_x, dlg_y, dlg_w, dlg_h), width=2, border_radius=upx(10))
        title = "Deposit Coins to Market" if action == "deposit" else "Withdraw Coins from Market"
        surface.blit(self.font_title.render(title, True, (250, 204, 21)), (dlg_x + upx(20), dlg_y + upx(14)))
        self.close_coin_dlg_btn_rect = pygame.Rect(dlg_x + dlg_w - upx(32), dlg_y + upx(12), upx(22), upx(22))
        self._draw_small_btn(surface, self.close_coin_dlg_btn_rect, "X", (51, 65, 85), (220, 38, 38), m_pos, self.font_badge)

        wallet = normalize_wallet(getattr(mkt, "currency", {}))
        self.coin_action_btn_rects.clear()
        self.coin_quantity_rects.clear()
        for idx, denom in enumerate(MARKET_CURRENCY_DENOMINATIONS):
            row_y = dlg_y + upx(48) + idx * upx(42)
            surface.blit(self.font_sub.render(denom, True, (241, 245, 249)), (dlg_x + upx(20), row_y + upx(7)))
            field = pygame.Rect(dlg_x + upx(100), row_y + 2, upx(72), upx(28))
            self.coin_quantity_rects[denom] = field
            key = f"coin:{denom}"
            raw = self.quantity_values.setdefault(key, str(MARKET_QUANTITY_DEFAULT))
            pygame.draw.rect(surface, (15, 23, 42), field, border_radius=3)
            pygame.draw.rect(surface, (96, 165, 250) if self.focused_quantity == key else (71, 85, 105), field, width=1, border_radius=3)
            qty_surf = self.font_badge.render(raw or "0", True, (255, 255, 255))
            surface.blit(qty_surf, (field.centerx - qty_surf.get_width() // 2, field.centery - qty_surf.get_height() // 2))

            button = pygame.Rect(dlg_x + upx(184), row_y + 2, upx(94), upx(28))
            self.coin_action_btn_rects[(denom, action)] = button
            bg = (20, 83, 45) if action == "deposit" else (127, 29, 29)
            hov = (22, 101, 52) if action == "deposit" else (153, 27, 27)
            self._draw_small_btn(surface, button, action.title(), bg, hov, m_pos, self.font_badge)

            if action == "deposit":
                available = sum(
                    stack.available_amount for stack in getattr(stockpile_manager, "stacks", [])
                    if getattr(stack, "owner_type", "landlord") == "landlord" and stack.resource_type == denom
                ) if stockpile_manager else 0
            else:
                available = wallet.get(denom, 0)
            surface.blit(self.font_badge.render(f"Available: {available}", True, COLOR_TEXT_MUTED), (dlg_x + upx(286), row_y + upx(9)))

        if self.status_message:
            status = self.font_badge.render(self.status_message, True, (248, 113, 113) if "No Goods" in self.status_message else (134, 239, 172))
            surface.blit(status, (dlg_x + upx(20), dlg_y + dlg_h - upx(22)))
