"""
Raport UI (Town Ledger, Free-form Area Permit Deeds, RimWorld Work Priorities & Building Management Modal)
"""

import math
import pygame
from game.ui.modals.permits_ui import PermitsModal
from game.config import (
    COLOR_RAPORT_BTN_BG,
    COLOR_RAPORT_BTN_BORDER,
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TAB_ACTIVE,
    COLOR_TAB_INACTIVE,
    COLOR_BADGE_WIP,
    COLOR_BADGE_PARTIAL,
    COLOR_BADGE_IMPLEMENTED,
    COLOR_TEXT_TITLE,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    BUILDING_TYPES,
    get_building_categories,
    PERMIT_TYPES,
    get_permit_categories,
    CROP_TYPES,
    FARMING_BATCH_GROWTH_DAYS,
    WORK_TYPES,
    PRIORITY_COLORS,
    DEDICATED_JOBS,
    FURNITURE_TYPES,
    COST_PER_BLOCK_WOOD,
    COST_PER_BLOCK_STONE,
    TILE_SIZE,
    ROAD_TYPES,
    RAPORT_MODAL_WIDTH,
    RAPORT_MODAL_HEIGHT,
    DEMOLITION_REFUND_RATIO,
    SCHEDULE_TYPES,
    DEFAULT_JOB_SCHEDULE,
    is_food_item
)
from game.data.config import CHURCH_TAX_HAPPINESS_TIERS_COPPER
from game.data.planning import (
    PLANNING_FEATURES,
    get_all_planning_features,
    get_features_by_status,
    STATUS_IMPLEMENTED,
    STATUS_PARTIAL,
    STATUS_PLANNED
)
from game.systems.economy.production_distribution import ProductionDistributionSystem
from game.systems.economy.household_inventory import (
    get_household_possessions,
    sort_possession_items,
    canonical_item_name
)
from game.systems.economy.wealth_system import VillageWealthSystem
from game.systems.work.schedule import UNIVERSAL_SCHEDULE_ID
from game.ui.item_icons import draw_item_icon
from game.ui.number_input import NumberInputState

from game.ui.raport_tabs.building_tab import BuildingMixin
from game.ui.raport_tabs.permit_tab import PermitMixin
from game.ui.raport_tabs.priority_tab import PriorityMixin
from game.ui.raport_tabs.schedule_tab import ScheduleMixin
from game.ui.raport_tabs.villagers_tab import VillagersMixin
from game.ui.raport_tabs.workers_tab import WorkersMixin
from game.ui.raport_tabs.immigrant_tab import ImmigrantMixin
from game.ui.raport_tabs.tax_tab import TaxMixin
from game.ui.raport_tabs.planning_tab import PlanningMixin

from game.ui.raport_tabs.common import GRANTABLE_ITEMS
from game.ui.ui_theme import ui_font, upx

class RaportUI(
    BuildingMixin,
    PermitMixin,
    PriorityMixin,
    ScheduleMixin,
    VillagersMixin,
    WorkersMixin,
    ImmigrantMixin,
    TaxMixin,
    PlanningMixin,
):
    def __init__(self):
        self.is_open = False
        self.active_tab = 0  # 0: Buildings, 1: Area Permits, 2: Priority, 3: Schedule, 4: Villagers, 5: Workers
        self.show_build_menu = False
        self.show_structures_menu = False
        self.show_furniture_menu = False
        self.selected_building_type = None
        self.selected_furniture_type = None
        self.selected_road_type = None
        self.placing_permit_type = None

        # Inspection & Focused entity tracking
        self.selected_permit_inspect_id = None
        self.selected_building_inspect = None
        self.market_profile_btn_rects = {}
        self.selected_market_building = None

        # Left HUD Button (Town Ledger)
        self.btn_left_rect = pygame.Rect(upx(16), upx(200), upx(116), upx(42))

        # Tabs
        self.tabs = [
            {"id": "building", "title": "Buildings", "wip": False},
            {"id": "permit", "title": "Permits", "wip": False},
            {"id": "priority", "title": "Priority", "wip": False},
            {"id": "schedule", "title": "Schedule", "wip": False, "hidden": True},
            {"id": "villagers", "title": "Household", "wip": False},
            {"id": "workers", "title": "Jobs", "wip": False},
            {"id": "immigrant", "title": "Immigrant", "wip": False},
            {"id": "tax", "title": "Taxes", "wip": False},
            {"id": "planning", "title": "Roadmap", "wip": True},
        ]

        # Building Category Navigation State
        self.selected_building_category = None  # None = Root Category View; cat_id = Category Filtered View
        self.selected_building_owner = None
        self.building_category_btn_rects = {}
        self.building_owner_btn_rects = {}
        self.building_category_back_btn_rect = None
        self.quick_build_btn_rects = {}
        self.furniture_move_btn_rects = {}
        self.furniture_uninstall_btn_rects = {}
        self.furniture_destroy_btn_rects = {}
        self.road_select_rects = {}
        self.destroy_mode_btn_rect = None
        self.moving_furniture = None
        self.destroying_furniture_id = None

        # Permit Category Navigation State (Agent 2)
        self.selected_permit_category = None  # None = Category View; string cat_id = Category Permit Details View
        self.permit_category_btn_rects = {}
        self.permit_category_back_btn_rect = None

        # Planning & Roadmap UI State
        self.planning_filter_status = "ALL"
        self.planning_page = 0
        self.planning_items_per_page = 4
        self.planning_filter_rects = {}
        self.planning_prev_btn_rect = None
        self.planning_next_btn_rect = None

        # Schedule State
        self.selected_schedule_job_id = None
        self.selected_schedule_brush = "WORK"
        self.schedule_job_select_btn_rects = {}
        self.schedule_brush_btn_rects = {}
        self.schedule_hour_cell_rects = {}
        self.schedule_preset_btn_rects = {}
        self.schedule_back_btn_rect = None
        self.universal_schedule_btn_rect = None

        # Member Job Assignment State
        self.member_job_btn_rects = {}

        # Church Tax State
        self.church_tax = {"Gold": 0, "Silver": 0, "Copper": 1}
        self.church_tax_enabled_rect = None
        self.socage_tax_enabled_rect = None
        self.socage_tax_input_rect = None
        self.socage_tax_input_active = False
        self.socage_tax_input_text = ""
        self.socage_tax_input_replace = False
        # Typable number fields (replaces +/- steppers)
        self.num_input = NumberInputState()
        self.num_fields = {}
        self.jobs_scroll_y = 0
        self.jobs_max_scroll = 0
        self.jobs_viewport_rect = None
        self.building_scroll_y = 0
        self.building_max_scroll = 0
        self.building_viewport_rect = None

        # Village Wealth State
        self.show_wealth_detail_dialog = False
        self.check_wealth_detail_btn_rect = None
        self.close_wealth_dlg_btn_rect = None

        # Item Distribution State (Taxes tab)
        self.show_item_dist_dialog = False
        self.item_dist_view = "production"      # "production" | "stock"
        self.item_dist_checked = set()          # item names with chart expanded
        self.item_dist_scroll_prod = 0
        self.item_dist_scroll_stock = 0
        self.item_dist_close_rect = None
        self.item_dist_view_btns = {}
        self.item_dist_check_rects = {}
        self.item_dist_viewport_rect = None
        self.check_item_dist_btn_rect = None

        # Household Possession State
        self.show_household_possession = False
        self.household_possession_btn_rect = None
        self.close_possession_btn_rect = None
        self.possession_page = 0
        self.possession_prev_btn_rect = None
        self.possession_next_btn_rect = None

        # Royal Grant Item to Household State
        self.show_grant_dialog = False
        self.show_grant_confirm = False
        self.grant_amounts = {}
        self.open_grant_dialog_btn_rect = None
        self.grant_close_btn_rect = None
        self.grant_submit_btn_rect = None
        self.grant_confirm_btn_rect = None
        self.grant_cancel_btn_rect = None
        self.grant_max_btn_rects = {}
        self.grant_item_qty_rects = {}
        self.active_grant_input_item = None
        self.grant_input_text = ""
        self.socage_tax_input_active = False
        self.socage_tax_input_text = ""
        self.grant_header_close_btn_rect = None
        self.grant_dlg_rect = None
        self.grant_viewport_rect = None
        self.grant_scrollbar_rect = None
        self.grant_thumb_rect = None
        self.grant_scroll_y = 0
        self.grant_max_scroll = 0
        self.grant_is_dragging_scrollbar = False
        self.cached_stockpile_manager = None
        self.cached_furniture_manager = None

        # Contextual View Navigation Rects (Agent 2)
        self.permit_household_btn_rects = {}
        self.building_household_btn_rects = {}
        self.household_view_permit_btn_rect = None
        self.cancel_construction_btn_rects = {}
        self.public_commission_btn_rects = {}
        self.selected_public_commission = None
        self.cancel_demolition_btn_rects = {}

        self.modal_w = RAPORT_MODAL_WIDTH
        self.modal_h = RAPORT_MODAL_HEIGHT

        # Crop Planting State
        self.crop_picker_permit_id = None
        self.crop_select_btn_rects = {}
        self.open_plant_btn_rects = {}
        self.close_crop_picker_btn_rect = None
        self.crop_picker_bg_rect = None

        # Villagers Tab Navigation & State
        self.selected_family_id = None
        self.show_assign_permit_picker = False
        self.add_family_cheat_btn_rect = None
        self.cheats_active = False
        self.back_to_families_btn_rect = None
        self.view_family_btn_rects = []
        self.family_possession_btn_rects = []
        self.family_deed_btn_rects = []
        self.open_assign_lot_btn_rect = None
        self.revoke_deed_btn_rect = None
        self.assign_permit_btn_rects = {}
        self.close_deed_picker_btn_rect = None
        self.deed_picker_bg_rect = None

        # Individual Member Inventory Dialog State
        self.selected_member_inventory_id = None
        self.member_inventory_btn_rects = {}
        self.close_member_inv_btn_rect = None
        self.member_deposit_btn_rects = {}
        self.member_drop_btn_rects = {}
        self.member_inv_bg_rect = None

        # Clickable rects cache
        self.tab_rects = []
        self.close_btn_rect = None
        self.build_btn_rect = None
        self.structures_btn_rect = None
        self.furniture_btn_rect = None
        self.building_select_rects = {}
        self.furniture_select_rects = {}
        self.permit_btn_rects = {}
        self.delete_permit_btn_rects = {}
        self.edit_permit_btn_rects = {}
        self.destroy_building_btn_rects = {}
        self.priority_cell_rects = {}  # (servant_id, work_id) -> Rect

        # Area Permits Worker Assignment Controls
        self.worker_auto_btn_rects = {}

        # Workers / Jobs Tab Controls
        self.selected_job_id = None
        self.selected_workstation_job_id = None
        self.highlight_workplace_key = None
        self.back_to_jobs_btn_rect = None
        self.auto_sort_all_btn_rect = None
        self.unassign_all_btn_rect = None
        self.job_select_btn_rects = {}
        self.job_workstation_btn_rects = {}
        self.workplace_crop_btn_rects = {}
        self.workplace_plant_btn_rects = {}
        self.job_schedule_btn_rects = {}
        self.worker_assign_btn_rects = {}
        self.worker_unassign_btn_rects = {}
        self.job_search_text = ""
        self.job_search_active = False
        self.job_search_rect = None

        self.fonts_loaded = False

    def _init_fonts(self):
        if not self.fonts_loaded:
            self.font_btn = ui_font(12, bold=True)
            self.font_title = ui_font(16, bold=True)
            self.font_tab = ui_font(12, bold=True)
            self.font_body = ui_font(12)
            self.font_badge = ui_font(10, bold=True)
            self.font_sub = ui_font(12, bold=True)
            self.font_priority = ui_font(14, bold=True)
            self.fonts_loaded = True

    def open(self):
        self.is_open = True

    def close(self):
        """Tutup modal Raport UI dan reset seluruh status dialog internalnya"""
        self.is_open = False
        self.selected_building_category = None
        self.selected_building_owner = None
        self.selected_permit_category = None
        self.show_build_menu = False
        self.show_structures_menu = False
        self.show_furniture_menu = False
        self.show_household_possession = False
        self.show_wealth_detail_dialog = False
        self.show_item_dist_dialog = False
        self.show_grant_dialog = False
        self.show_grant_confirm = False
        self.grant_amounts = {}
        self.grant_scroll_y = 0
        self.grant_is_dragging_scrollbar = False
        self.active_grant_input_item = None
        self.grant_input_text = ""
        self.selected_family_id = None
        self.selected_member_inventory_id = None
        self.show_assign_permit_picker = False
        self.crop_picker_permit_id = None
        self.selected_job_id = None
        self.selected_schedule_job_id = None
        self.job_search_text = ""
        self.job_search_active = False
        self.job_search_rect = None

    def open_household_directly(self, family_id):
        """Contextual View: Opens Town Ledger directly to the specified family's View Family screen"""
        self.is_open = True
        self.active_tab = 4  # Tab Household
        self.selected_family_id = family_id
        self.show_household_possession = False
        self.show_wealth_detail_dialog = False
        self.show_item_dist_dialog = False
        self.show_grant_dialog = False
        self.show_grant_confirm = False
        self.show_assign_permit_picker = False

    def open_possession_directly(self, family_id):
        """Contextual View: Opens Town Ledger directly to the specified household's Possession screen"""
        self.is_open = True
        self.active_tab = 4  # Tab Household
        self.selected_family_id = family_id
        self.show_household_possession = True
        self.show_wealth_detail_dialog = False
        self.show_item_dist_dialog = False
        self.show_grant_dialog = False
        self.show_grant_confirm = False
        self.show_assign_permit_picker = False

    def open_permit_directly(self, permit_id, permit_manager):
        """Contextual View: Opens Town Ledger directly to the specified permit within its category view"""
        target_p = next((p for p in getattr(permit_manager, "permits", []) if p.id == permit_id), None)
        self.is_open = True
        self.active_tab = 1  # Tab Area Permits
        self.show_wealth_detail_dialog = False
        self.show_item_dist_dialog = False
        self.selected_permit_inspect_id = permit_id
        if target_p:
            categories = get_permit_categories()
            cat = next((c for c in categories if target_p.permit_type in c.get("permit_types", [])), None)
            self.selected_permit_category = cat["id"] if cat else None
        else:
            self.selected_permit_category = None

    def open_workplace_workstations(self, job_id, workplace=None):
        """Contextual View: Opens Town Ledger Workers tab focused on a job's Workstations,
        optionally highlighting one specific workplace card."""
        self.is_open = True
        self.active_tab = 5  # Tab Workers
        self.show_wealth_detail_dialog = False
        self.show_item_dist_dialog = False
        self.selected_job_id = None
        self.selected_workstation_job_id = job_id
        self.highlight_workplace_key = self._workplace_key(workplace) if workplace else None
        self.jobs_scroll_y = 0
        self.job_search_text = ""
        self.job_search_active = False

    def open_immigrant_tab(self):
        """Contextual View: Opens Town Ledger directly to the Immigrant tab
        (used when the player clicks a Notice Board)."""
        self.is_open = True
        self.active_tab = 6  # Tab Immigrant
        self.show_wealth_detail_dialog = False
        self.show_item_dist_dialog = False
        self.selected_building_category = None
        self.selected_permit_category = None
        self.show_build_menu = False
        self.selected_family_id = None
        self.selected_job_id = None
        self.selected_workstation_job_id = None
        self.selected_schedule_job_id = None

    def open_building_directly(self, building):
        """Contextual View: Opens Town Ledger directly to the specified building in its category view"""
        if building:
            b_cfg = BUILDING_TYPES.get(getattr(building, "building_type", ""), {})
            cat_id = b_cfg.get("category_id", getattr(building, "building_type", "wooden_structure"))
            self.is_open = True
            self.active_tab = 0  # Tab Buildings
            self.show_wealth_detail_dialog = False
            self.show_item_dist_dialog = False
            self.selected_building_category = cat_id
            self.selected_building_owner = None
            self.building_scroll_y = 0
            self.selected_building_inspect = building

    def get_landlord_stock(self, stockpile_manager, resources):
        stock = {
            "Hoe": 0,
            "Sickle": 0,
            "Watering_Can": 0,
            "Potato": 0,
            "Wood": 0,
            "Stone": 0,
            "Copper": 0,
            "Silver": 0,
            "Gold": 0,
        }
        sm = stockpile_manager or self.cached_stockpile_manager
        if sm:
            for s in getattr(sm, "stacks", []):
                if getattr(s, "owner_type", "landlord") == "landlord" and getattr(s, "amount", 0) > 0:
                    rt = s.resource_type
                    if rt in stock:
                        stock[rt] += s.amount
                    elif is_food_item(rt):
                        stock["Potato"] += s.amount
                        if rt not in stock:
                            stock[rt] = s.amount
                    else:
                        c_name = canonical_item_name(rt)
                        if c_name in stock:
                            stock[c_name] += s.amount
                        else:
                            stock[rt] = stock.get(rt, 0) + s.amount
        if resources:
            for k in ("Wood", "Stone", "Food", "Copper", "Silver", "Gold"):
                target_k = "Potato" if k == "Food" else k
                if resources.get(k, 0) > stock.get(target_k, 0):
                    stock[target_k] = resources[k]
        # Coins held in the Lord Treasury Chest are grantable too
        fm = getattr(self, "cached_furniture_manager", None)
        if fm is not None:
            try:
                from game.systems.economy.lord_treasury import LordTreasurySystem
                for denom, amount in LordTreasurySystem.wallet(fm).items():
                    if amount > 0:
                        stock[denom] = stock.get(denom, 0) + amount
            except Exception:
                pass
        return stock

    def is_text_input_active(self):
        """Mengembalikan True jika player sedang mengetik di input/text field dalam UI Raport"""
        return bool(self.is_open and (
            self.num_input.active
            or (self.show_grant_dialog and self.active_grant_input_item is not None)
            or (self.active_tab == 7 and self.socage_tax_input_active)
            or (self.active_tab == 5 and self.job_search_active)
        ))

    @staticmethod
    def _commit_socage_tax_input(text):
        if text and text.isdigit():
            from game.systems.economy.taxation_system import TaxationSystem
            TaxationSystem.set_socage_percent(int(text))

    # ---------------------------------------------------------
    # Typable number fields (replaces +/- steppers)
    # ---------------------------------------------------------
    def _num_field_station(self, fld, permit_manager, furniture_manager, building_manager):
        """Resolve a workplace field's (kind, obj) station tuple."""
        from game.systems.work.workplace_system import get_job_workplaces
        job_id, skey = fld["payload"]
        workplaces = get_job_workplaces(job_id, permit_manager, furniture_manager, building_manager)
        return next((w for w in workplaces if self._workplace_key(w) == skey), None)

    def _num_field_value(self, fld, permit_manager, villager_manager,
                         schedule_manager, furniture_manager, building_manager):
        """Current committed value shown inside a number field."""
        kind = fld["kind"]
        pl = fld.get("payload")
        if kind == "permit_max":
            p = next((x for x in getattr(permit_manager, "permits", []) if x.id == pl), None)
            if p is None:
                return 0
            cur = getattr(p, "max_workers", None)
            if cur is None:
                cur = 1 if p.permit_type == "church" else 2
            return int(cur)
        if kind in ("prayer_start", "prayer_end"):
            if not schedule_manager:
                return 0
            s, e = schedule_manager.get_prayer_hours()
            return int(s if kind == "prayer_start" else e)
        if kind == "workplace_workers":
            ws = self._num_field_station(fld, permit_manager, furniture_manager, building_manager)
            if ws is None:
                return 0
            from game.systems.work.workplace_system import workplace_job_workers
            return len(workplace_job_workers(ws, pl[0], villager_manager))
        if kind == "workplace_max":
            ws = self._num_field_station(fld, permit_manager, furniture_manager, building_manager)
            if ws is not None and ws[0] == "permit":
                return int(getattr(ws[1], "max_workers", 0))
            return 0
        if kind == "workplace_quota":
            ws = self._num_field_station(fld, permit_manager, furniture_manager, building_manager)
            if ws is not None and ws[0] == "furniture":
                return int(getattr(ws[1], "station_quota_daily", 0) or 0)
            return 0
        if kind == "church_tax":
            return int(self.church_tax.get(pl, 0))
        if kind == "immigrant_reward":
            from game.systems.village_life.immigration_system import get_immigration_system
            return get_immigration_system().reward_for(pl)
        return 0

    def _apply_num_field(self, fld, val, building_manager, permit_manager,
                         villager_manager, schedule_manager, furniture_manager):
        """Write a committed number back to its underlying setting."""
        kind = fld["kind"]
        pl = fld.get("payload")
        if kind == "permit_max":
            p = next((x for x in getattr(permit_manager, "permits", []) if x.id == pl), None)
            if p is None:
                return
            cur = getattr(p, "max_workers", 1 if p.permit_type == "church" else 2)
            while cur > val:
                permit_manager.change_max_workers(pl, -1, villager_manager, furniture_manager=furniture_manager)
                cur -= 1
            while cur < val:
                permit_manager.change_max_workers(pl, 1, villager_manager, furniture_manager=furniture_manager)
                cur += 1
        elif kind == "prayer_start":
            if not schedule_manager:
                return
            s, e = schedule_manager.get_prayer_hours()
            schedule_manager.set_prayer_time(max(0, min(val, e - 1)), e)
        elif kind == "prayer_end":
            if not schedule_manager:
                return
            s, e = schedule_manager.get_prayer_hours()
            schedule_manager.set_prayer_time(s, min(24, max(val, s + 1)))
        elif kind == "workplace_workers":
            ws = self._num_field_station(fld, permit_manager, furniture_manager, building_manager)
            if ws is None or not villager_manager:
                return
            from game.systems.work.workplace_system import (
                change_workplace_workers, workplace_job_workers,
            )
            job_id = pl[0]
            cur = len(workplace_job_workers(ws, job_id, villager_manager))
            while cur < val:
                if not change_workplace_workers(job_id, ws, 1, permit_manager,
                                                furniture_manager, villager_manager, building_manager):
                    break
                cur += 1
            while cur > val:
                if not change_workplace_workers(job_id, ws, -1, permit_manager,
                                                furniture_manager, villager_manager, building_manager):
                    break
                cur -= 1
        elif kind == "workplace_max":
            ws = self._num_field_station(fld, permit_manager, furniture_manager, building_manager)
            if ws is not None and ws[0] == "permit":
                p = ws[1]
                cur = int(getattr(p, "max_workers", 0))
                permit_manager.change_max_workers(
                    p.id, val - cur, villager_manager,
                    furniture_manager=furniture_manager, auto_assign=False)
        elif kind == "workplace_quota":
            ws = self._num_field_station(fld, permit_manager, furniture_manager, building_manager)
            if ws is not None and ws[0] == "furniture":
                ws[1].station_quota_daily = val
        elif kind == "church_tax":
            if isinstance(self.church_tax, dict):
                self.church_tax[pl] = val
                from game.systems.village_life.church_system import ChurchSystem
                ChurchSystem.set_tax_settings(
                    self.church_tax.get("Gold", 0),
                    self.church_tax.get("Silver", 0),
                    self.church_tax.get("Copper", 0), permit_manager)
        elif kind == "immigrant_reward":
            from game.systems.village_life.immigration_system import get_immigration_system
            get_immigration_system().set_reward(pl, val)

    def _commit_num_field(self, building_manager, permit_manager,
                          villager_manager, schedule_manager, furniture_manager):
        key = self.num_input.active_key
        fld = self.num_fields.get(key)
        val = self.num_input.value()
        self.num_input.cancel()
        if fld is None or val is None:
            return
        val = max(int(fld.get("min", 0)), min(int(fld.get("max", 999999)), val))
        self._apply_num_field(fld, val, building_manager, permit_manager,
                              villager_manager, schedule_manager, furniture_manager)

    def _draw_num_input(self, surface, key, rect, display_value):
        """Draw a typable number box; registers nothing (done by caller)."""
        active = (self.num_input.active_key == key)
        bg = (15, 23, 42) if not active else (30, 58, 138)
        border = (250, 204, 21) if active else (71, 85, 105)
        pygame.draw.rect(surface, bg, rect, border_radius=upx(4))
        pygame.draw.rect(surface, border, rect, width=2 if active else 1, border_radius=upx(4))
        txt = (self.num_input.text + "_") if active else str(display_value)
        t = self.font_badge.render(txt, True, (255, 255, 255))
        surface.blit(t, (rect.centerx - t.get_width() // 2,
                         rect.centery - t.get_height() // 2))

    def toggle(self):
        if self.is_open:
            self.close()
        else:
            self.open()

    def handle_event(self, event, building_manager, permit_manager, resources, servant_manager=None, villager_manager=None, schedule_manager=None, day_cycle=None, stockpile_manager=None, furniture_manager=None, production_system=None):
        if stockpile_manager is not None:
            self.cached_stockpile_manager = stockpile_manager
        if furniture_manager is not None:
            self.cached_furniture_manager = furniture_manager
        sm = stockpile_manager or self.cached_stockpile_manager

        if event.type == pygame.KEYDOWN:
            if self.is_open and self.num_input.active:
                if self.num_input.active_key not in self.num_fields:
                    self.num_input.cancel()
                else:
                    res = self.num_input.handle_keydown(event)
                    if res == "commit":
                        self._commit_num_field(
                            building_manager, permit_manager, villager_manager,
                            schedule_manager, furniture_manager)
                    elif res == "cancel":
                        self.num_input.cancel()
                    return "num_input_edit"
            if self.is_open and self.active_tab == 7 and self.socage_tax_input_active:
                if event.key == pygame.K_BACKSPACE:
                    self.socage_tax_input_text = self.socage_tax_input_text[:-1]
                    self.socage_tax_input_replace = False
                    return "socage_tax_input_edit"
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._commit_socage_tax_input(self.socage_tax_input_text)
                    self.socage_tax_input_active = False
                    return "socage_tax_percent_set"
                if event.key == pygame.K_ESCAPE:
                    self.socage_tax_input_active = False
                    self.socage_tax_input_text = ""
                    return "socage_tax_input_cancelled"
                if event.unicode.isdigit():
                    draft = event.unicode if self.socage_tax_input_replace else self.socage_tax_input_text + event.unicode
                    if len(draft) <= 3 and int(draft) <= 100:
                        self.socage_tax_input_text = draft
                        self.socage_tax_input_replace = False
                    return "socage_tax_input_edit"
                return None
            if self.is_open and self.active_tab == 5 and self.job_search_active:
                if event.key == pygame.K_BACKSPACE:
                    self.job_search_text = self.job_search_text[:-1]
                    self.jobs_scroll_y = 0
                    return "job_search_edit"
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                    self.job_search_active = False
                    return "job_search_done"
                if event.unicode and len(self.job_search_text) < 32:
                    self.job_search_text += event.unicode
                    self.jobs_scroll_y = 0
                    return "job_search_edit"
                return None
            if self.is_text_input_active():
                if event.key == pygame.K_BACKSPACE:
                    self.grant_input_text = self.grant_input_text[:-1]
                    val = int(self.grant_input_text) if self.grant_input_text else 0
                    self.grant_amounts[self.active_grant_input_item] = val
                    return "grant_input_edit"
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                    self.active_grant_input_item = None
                    self.grant_input_text = ""
                    return "grant_input_done"
                elif event.unicode.isdigit():
                    new_text = self.grant_input_text + event.unicode
                    val = int(new_text)
                    stock = self.get_landlord_stock(sm, resources)
                    avail = stock.get(self.active_grant_input_item, 0)
                    val = min(avail, max(0, val))
                    self.grant_input_text = str(val)
                    self.grant_amounts[self.active_grant_input_item] = val
                    return "grant_input_edit"
                return None
            if event.key == pygame.K_r:
                self.toggle()
                return "toggle_raport"
            return None

        # Mousewheel Scrolling (e.g. Grant Supplies modal list)
        if event.type == pygame.MOUSEWHEEL:
            if (self.is_open and self.active_tab == 0
                    and self.building_viewport_rect and self.building_viewport_rect.collidepoint(pygame.mouse.get_pos())
                    and self.building_max_scroll > 0):
                self.building_scroll_y = max(0, min(self.building_scroll_y - event.y * upx(36), self.building_max_scroll))
                return "building_scroll"
            if self.show_grant_dialog and getattr(self, "grant_max_scroll", 0) > 0:
                self.grant_scroll_y = max(0, min(self.grant_scroll_y - event.y * upx(36), self.grant_max_scroll))
                return "grant_scroll"
            if (self.show_item_dist_dialog
                    and getattr(self, "item_dist_viewport_rect", None)
                    and self.item_dist_viewport_rect.collidepoint(pygame.mouse.get_pos())):
                step = event.y * upx(36)
                if self.item_dist_view == "production":
                    self.item_dist_scroll_prod = max(0, self.item_dist_scroll_prod - step)
                else:
                    self.item_dist_scroll_stock = max(0, self.item_dist_scroll_stock - step)
                return "item_dist_scroll"
            if (self.is_open and self.active_tab == 5 and self.selected_job_id is None
                    and self.jobs_viewport_rect and self.jobs_viewport_rect.collidepoint(pygame.mouse.get_pos())
                    and self.jobs_max_scroll > 0):
                self.jobs_scroll_y = max(0, min(self.jobs_scroll_y - event.y * upx(36), self.jobs_max_scroll))
                return "jobs_scroll"
            return None

        # Scrollbar Dragging with Mouse Motion
        if event.type == pygame.MOUSEMOTION:
            if self.show_grant_dialog and self.grant_is_dragging_scrollbar and self.grant_scrollbar_rect and getattr(self, "grant_max_scroll", 0) > 0:
                rel_y = event.pos[1] - self.grant_scrollbar_rect.y
                ratio = max(0.0, min(1.0, rel_y / max(1, self.grant_scrollbar_rect.h)))
                self.grant_scroll_y = max(0, min(int(ratio * self.grant_max_scroll), self.grant_max_scroll))
                return "grant_scroll"
            return None

        # End of Scrollbar Drag
        if event.type == pygame.MOUSEBUTTONUP:
            if self.grant_is_dragging_scrollbar:
                self.grant_is_dragging_scrollbar = False
                return "grant_drag_end"
            return None

        # Mouse Button Press
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Handle legacy button 4/5 mouse wheel
            if event.button in (4, 5) and self.show_grant_dialog and getattr(self, "grant_max_scroll", 0) > 0:
                scroll_step = -upx(36) if event.button == 4 else upx(36)
                self.grant_scroll_y = max(0, min(self.grant_scroll_y + scroll_step, self.grant_max_scroll))
                return "grant_scroll"
            if event.button != 1:
                return None
        else:
            return None

        mouse_pos = event.pos

        if self.socage_tax_input_active and not (
                self.socage_tax_input_rect and self.socage_tax_input_rect.collidepoint(mouse_pos)):
            self._commit_socage_tax_input(self.socage_tax_input_text)
            self.socage_tax_input_active = False
            self.socage_tax_input_text = ""

        # 1. Left "Raport" Button
        if self.btn_left_rect.collidepoint(mouse_pos):
            self.toggle()
            return "toggle_raport"

        if not self.is_open:
            return None

        # -------------------------------------------------------------
        # MODAL OVERLAYS (Priority 0: Topmost modal capture)
        # -------------------------------------------------------------
        if self.show_grant_confirm:
            if self.grant_confirm_btn_rect and self.grant_confirm_btn_rect.collidepoint(mouse_pos):
                if servant_manager and self.selected_family_id is not None:
                    for item_type, qty in list(self.grant_amounts.items()):
                        if qty > 0:
                            servant_manager.add_grant_order(self.selected_family_id, item_type, qty)
                self.show_grant_confirm = False
                self.show_grant_dialog = False
                self.grant_amounts = {}
                self.grant_scroll_y = 0
                self.grant_is_dragging_scrollbar = False
                self.active_grant_input_item = None
                return "grant_items_confirmed"

            if self.grant_cancel_btn_rect and self.grant_cancel_btn_rect.collidepoint(mouse_pos):
                self.show_grant_confirm = False
                return "grant_items_cancelled"
            return "modal_blocked"

        if self.show_grant_dialog:
            # 1. Close modal (either Header [X] button or Footer [Cancel] button)
            if (self.grant_header_close_btn_rect and self.grant_header_close_btn_rect.collidepoint(mouse_pos)) or \
               (self.grant_close_btn_rect and self.grant_close_btn_rect.collidepoint(mouse_pos)):
                self.show_grant_dialog = False
                self.grant_amounts = {}
                self.grant_scroll_y = 0
                self.grant_is_dragging_scrollbar = False
                self.active_grant_input_item = None
                return "close_grant_dialog"

            # 2. Grant Submit [Grant (X items)]
            if self.grant_submit_btn_rect and self.grant_submit_btn_rect.collidepoint(mouse_pos):
                if sum(self.grant_amounts.values()) > 0:
                    self.show_grant_confirm = True
                    self.active_grant_input_item = None
                    return "open_grant_confirm"

            # 3. Scrollbar Thumb click
            if self.grant_thumb_rect and self.grant_thumb_rect.collidepoint(mouse_pos):
                self.grant_is_dragging_scrollbar = True
                return "grant_scroll"

            # 4. Scrollbar Track click (jump scroll)
            if self.grant_scrollbar_rect and self.grant_scrollbar_rect.collidepoint(mouse_pos):
                rel_y = mouse_pos[1] - self.grant_scrollbar_rect.y
                ratio = max(0.0, min(1.0, rel_y / max(1, self.grant_scrollbar_rect.h)))
                self.grant_scroll_y = max(0, min(int(ratio * self.grant_max_scroll), self.grant_max_scroll))
                self.grant_is_dragging_scrollbar = True
                return "grant_scroll"

            # 5. Controls inside Viewport
            if self.grant_viewport_rect and self.grant_viewport_rect.collidepoint(mouse_pos):
                stock = self.get_landlord_stock(sm, resources)
                for it_type, rect in list(self.grant_max_btn_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        avail = stock.get(it_type, 0)
                        self.grant_amounts[it_type] = avail
                        return f"grant_max_{it_type}"

                for it_type, rect in list(self.grant_item_qty_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        self.active_grant_input_item = it_type
                        self.grant_input_text = str(self.grant_amounts.get(it_type, 0))
                        return f"grant_input_focus_{it_type}"

            # 6. Click inside dialog rect but outside buttons (unfocus text input)
            if self.grant_dlg_rect and self.grant_dlg_rect.collidepoint(mouse_pos):
                self.active_grant_input_item = None
                return "modal_blocked"

            return "modal_blocked"

        # Typable number fields: focus on click, commit on outside click
        if not (self.show_grant_dialog or self.show_grant_confirm
                or self.crop_picker_permit_id or self.show_wealth_detail_dialog
                or self.show_item_dist_dialog
                or self.show_household_possession or self.selected_member_inventory_id
                or self.show_assign_permit_picker):
            hit_key = None
            for fkey, fld in self.num_fields.items():
                if fld["rect"].collidepoint(mouse_pos):
                    hit_key = fkey
                    break
            if self.num_input.active and hit_key != self.num_input.active_key:
                self._commit_num_field(
                    building_manager, permit_manager, villager_manager,
                    schedule_manager, furniture_manager)
            if hit_key is not None:
                self.num_input.focus(
                    hit_key,
                    self._num_field_value(
                        self.num_fields[hit_key], permit_manager, villager_manager,
                        schedule_manager, furniture_manager, building_manager))
                return "num_input_focus"

        # 2. Close Button (X)
        if self.close_btn_rect and self.close_btn_rect.collidepoint(mouse_pos):
            self.is_open = False
            self.selected_building_category = None
            self.selected_building_owner = None
            self.building_scroll_y = 0
            return "close_raport"

        # 3. Tab Switching
        for i, tr in enumerate(self.tab_rects):
            if tr.collidepoint(mouse_pos):
                self.active_tab = i
                self.selected_building_category = None
                self.selected_permit_category = None
                self.show_build_menu = False
                self.selected_family_id = None
                self.show_household_possession = False
                self.show_grant_dialog = False
                self.show_grant_confirm = False
                self.show_wealth_detail_dialog = False
                self.show_item_dist_dialog = False
                self.grant_amounts = {}
                self.active_grant_input_item = None
                self.show_assign_permit_picker = False
                self.selected_job_id = None
                self.selected_schedule_job_id = None
                self.selected_building_owner = None
                self.building_scroll_y = 0
                return f"switch_tab_{i}"

        # Crop picker dialog is modal-ish: handle it before tab dispatch so it
        # works when opened from Jobs > Workstations as well as the Permit tab.
        if self.crop_picker_permit_id:
            if self.close_crop_picker_btn_rect and self.close_crop_picker_btn_rect.collidepoint(mouse_pos):
                self.crop_picker_permit_id = None
                return "close_crop_picker"

            for crop_id, rect in self.crop_select_btn_rects.items():
                if rect.collidepoint(mouse_pos):
                    c_cfg = CROP_TYPES[crop_id]
                    if not c_cfg.get("wip", False):
                        p = next((p for p in permit_manager.permits if p.id == self.crop_picker_permit_id), None)
                        if p:
                            p.set_crop(c_cfg["name"])
                        self.crop_picker_permit_id = None
                        return f"plant_crop_{crop_id}"

            if self.crop_picker_bg_rect and not self.crop_picker_bg_rect.collidepoint(mouse_pos):
                self.crop_picker_permit_id = None
                return "close_crop_picker"

        # 4. Tab 0: Building Management
        if self.active_tab == 0:
            # Check Back button when viewing a specific building category
            if self.building_category_back_btn_rect and self.building_category_back_btn_rect.collidepoint(mouse_pos):
                self.selected_building_category = None
                self.building_scroll_y = 0
                return "building_category_back"

            # Household rows open that household's combined asset list directly.
            if self.selected_building_category is None:
                if self.building_viewport_rect and self.building_viewport_rect.collidepoint(mouse_pos):
                    for owner_id, rect in list(self.building_owner_btn_rects.items()):
                        if rect.collidepoint(mouse_pos):
                            self.selected_building_owner = owner_id
                            self.selected_building_category = "household"
                            self.building_scroll_y = 0
                            return f"select_building_owner_{owner_id}"
                for cat_id, rect in list(self.building_category_btn_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        self.selected_building_owner = None
                        self.selected_building_category = cat_id
                        self.building_scroll_y = 0
                        return f"select_building_category_{cat_id}"
                if self.destroy_mode_btn_rect and self.destroy_mode_btn_rect.collidepoint(mouse_pos):
                    self.is_open = False
                    return "start_destroy_mode"

            # Check Market Profile buttons
            for b, rect in list(getattr(self, "market_profile_btn_rects", {}).items()):
                if rect.collidepoint(mouse_pos):
                    self.selected_market_building = b
                    self.is_open = False
                    return "open_market_profile"

            # Contextual Navigation: Jump to Household from Building
            for b, (btn_rect, fid) in list(self.building_household_btn_rects.items()):
                if btn_rect.collidepoint(mouse_pos):
                    self.open_household_directly(fid)
                    return f"open_household_{fid}"

            # Check Cancel Demolition buttons
            for d, rect in list(self.cancel_demolition_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    servants = servant_manager.servants if servant_manager else None
                    building_manager.cancel_demolition(d, all_servants=servants)
                    self.cancel_demolition_btn_rects.clear()
                    return "cancel_demolition"

            # Public builder commissions are dispatched automatically from the Lord's Treasury.
            # Check Cancel Construction buttons
            for s, rect in list(self.cancel_construction_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    servants = servant_manager.servants if servant_manager else None
                    building_manager.cancel_construction(s, resources=resources, stockpile_manager=stockpile_manager, all_servants=servants, furniture_manager=furniture_manager)
                    self.cancel_construction_btn_rects.clear()
                    return "cancel_construction"

            # Check Destroy Building buttons
            for b, rect in list(self.destroy_building_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    building_manager.start_demolition(b)
                    self.selected_building_inspect = None
                    self.is_open = False
                    return "destroy_building"

            # Check Building Construction buttons (from category view or quick build)
            for b_type, rect in list(self.building_select_rects.items()):
                if rect.collidepoint(mouse_pos):
                    b_cfg = BUILDING_TYPES.get(b_type, {})
                    has_permit = permit_manager.has_permit_type(b_type)
                    if has_permit:
                        self.selected_building_type = b_type
                        self.selected_furniture_type = None
                        self.placing_permit_type = None
                        self.show_structures_menu = False
                        self.is_open = False
                        return f"start_drag_building_{b_type}"
                    else:
                        return f"need_permit_{b_type}"

            # Check Road type buttons (Public Structure > Road)
            for r_id, rect in list(getattr(self, "road_select_rects", {}).items()):
                if rect.collidepoint(mouse_pos):
                    self.selected_road_type = r_id
                    self.selected_building_type = None
                    self.selected_furniture_type = None
                    self.placing_permit_type = None
                    self.show_structures_menu = False
                    self.is_open = False
                    return "start_place_road"

            # Check Furniture Placement buttons
            for f_type, rect in list(self.furniture_select_rects.items()):
                if rect.collidepoint(mouse_pos):
                    self.selected_furniture_type = f_type
                    self.selected_building_type = None
                    self.placing_permit_type = None
                    self.show_furniture_menu = False
                    self.is_open = False
                    return f"start_place_furniture_{f_type}"

            # Check Furniture Move buttons
            for f, rect in list(getattr(self, "furniture_uninstall_btn_rects", {}).items()):
                if rect.collidepoint(mouse_pos):
                    if furniture_manager:
                        furniture_manager.uninstall_furniture(f.id)
                    return "uninstall_furniture"

            for f, rect in list(getattr(self, "furniture_move_btn_rects", {}).items()):
                if rect.collidepoint(mouse_pos):
                    self.moving_furniture = f
                    self.is_open = False
                    return "move_furniture"

            # Check Furniture Destroy buttons
            for f, rect in list(getattr(self, "furniture_destroy_btn_rects", {}).items()):
                if rect.collidepoint(mouse_pos):
                    self.destroying_furniture_id = f.id
                    self.is_open = False
                    return "destroy_furniture"

        # 5. Tab 1: Area Permit Management
        elif self.active_tab == 1:
            # Check Back button when viewing a specific permit category (Agent 2)
            if self.permit_category_back_btn_rect and self.permit_category_back_btn_rect.collidepoint(mouse_pos):
                self.selected_permit_category = None
                return "permit_category_back"

            # Check Category Selection buttons on Root Categories Screen (Agent 2)
            if self.selected_permit_category is None:
                for cat_id, rect in list(self.permit_category_btn_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        self.selected_permit_category = cat_id
                        return f"select_permit_category_{cat_id}"

            # Contextual Navigation: Jump to Household from Permit
            for pid, (btn_rect, fid) in list(self.permit_household_btn_rects.items()):
                if btn_rect.collidepoint(mouse_pos):
                    self.open_household_directly(fid)
                    return f"open_household_{fid}"

            # Auto buttons (worker caps are typable number fields now)
            for pid, rect in list(self.worker_auto_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    if villager_manager:
                        from game.systems.work.workplace_system import auto_sort_all_workers
                        auto_sort_all_workers(permit_manager, furniture_manager, villager_manager,
                                              building_manager=building_manager)
                    return f"auto_worker_{pid}"

            # Check Edit Permit buttons
            for pid, rect in list(self.edit_permit_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    self.is_open = False
                    return f"edit_permit_{pid}"

            # Check Delete Permit buttons
            for pid, rect in list(self.delete_permit_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    permit_manager.delete_permit(pid, building_manager, furniture_manager=furniture_manager, stockpile_manager=sm)
                    if self.selected_permit_inspect_id == pid:
                        self.selected_permit_inspect_id = None
                    return "delete_permit"

            for p_type, btn_rect in self.permit_btn_rects.items():
                if btn_rect.collidepoint(mouse_pos):
                    self.placing_permit_type = p_type
                    self.selected_building_type = None
                    self.is_open = False
                    return f"start_placing_permit_{p_type}"

        # 6. Tab 2: RimWorld-Style Work Priorities Matrix
        elif self.active_tab == 2:
            if servant_manager:
                for (s_id, w_id), cell_rect in self.priority_cell_rects.items():
                    if cell_rect.collidepoint(mouse_pos):
                        # Find servant and cycle priority
                        for s in servant_manager.servants:
                            if s.id == s_id:
                                s.cycle_priority(w_id)
                                if s.carried_amount == 0:
                                    s._reset_task()
                                return f"cycle_priority_{s_id}_{w_id}"

        # 6.5. Tab 3: RimWorld-Style 24-Hour Schedule Matrix
        elif self.active_tab == 3:
            if schedule_manager:
                if self.selected_schedule_job_id is None:
                    for job_id, rect in self.schedule_job_select_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            self.selected_schedule_job_id = job_id
                            return f"select_schedule_job_{job_id}"
                else:
                    if self.schedule_back_btn_rect and self.schedule_back_btn_rect.collidepoint(mouse_pos):
                        self.selected_schedule_job_id = None
                        return "back_to_schedule_jobs"

                    for brush_type, rect in self.schedule_brush_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            self.selected_schedule_brush = brush_type
                            return f"select_brush_{brush_type}"

                    for hour_idx, rect in self.schedule_hour_cell_rects.items():
                        if rect.collidepoint(mouse_pos):
                            schedule_manager.set_hour_activity(self.selected_schedule_job_id, hour_idx, self.selected_schedule_brush)
                            return f"paint_hour_{hour_idx}_{self.selected_schedule_brush}"

                    for preset_name, rect in self.schedule_preset_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            if preset_name == "standard":
                                schedule_manager.reset_to_default(self.selected_schedule_job_id)
                            elif preset_name == "hardwork":
                                sched = ["SLEEP"]*5 + ["LEISURE"] + ["WORK"]*15 + ["LEISURE"] + ["SLEEP"]*2
                                for h in range(24):
                                    schedule_manager.set_hour_activity(self.selected_schedule_job_id, h, sched[h])
                            elif preset_name == "relaxed":
                                sched = ["SLEEP"]*7 + ["LEISURE"]*2 + ["WORK"]*7 + ["LEISURE"]*6 + ["SLEEP"]*2
                                for h in range(24):
                                    schedule_manager.set_hour_activity(self.selected_schedule_job_id, h, sched[h])
                            return f"apply_schedule_preset_{preset_name}"

        # 7. Tab 4: Villagers & Family Clans Management
        elif self.active_tab == 4:
            if villager_manager:
                # View 1: Family Directory
                if self.selected_family_id is None:
                    if self.cheats_active and self.add_family_cheat_btn_rect and self.add_family_cheat_btn_rect.collidepoint(mouse_pos):
                        villager_manager.generate_random_family()
                        return "add_family_cheat"

                    for fam_id, rect in self.view_family_btn_rects:
                        if rect.collidepoint(mouse_pos):
                            self.selected_family_id = fam_id
                            self.show_household_possession = False
                            self.show_grant_dialog = False
                            self.show_grant_confirm = False
                            self.grant_amounts = {}
                            self.active_grant_input_item = None
                            self.show_assign_permit_picker = False
                            return f"view_family_{fam_id}"

                    for fam_id, rect in self.family_possession_btn_rects:
                        if rect.collidepoint(mouse_pos):
                            self.open_possession_directly(fam_id)
                            return f"open_household_possession_{fam_id}"

                    for fam_id, rect in self.family_deed_btn_rects:
                        if rect.collidepoint(mouse_pos):
                            self.selected_family_id = fam_id
                            self.show_household_possession = False
                            self.show_grant_dialog = False
                            self.show_grant_confirm = False
                            self.show_assign_permit_picker = True
                            return f"toggle_assign_permit_picker_{fam_id}"

                # View 2: Family Roster & Deed Management
                else:
                    if self.show_household_possession:
                        if self.close_possession_btn_rect and self.close_possession_btn_rect.collidepoint(mouse_pos):
                            self.show_household_possession = False
                            self.possession_page = 0
                            return "close_household_possession"

                        if self.open_grant_dialog_btn_rect and self.open_grant_dialog_btn_rect.collidepoint(mouse_pos):
                            self.show_grant_dialog = True
                            self.grant_amounts = {}
                            self.grant_scroll_y = 0
                            self.grant_is_dragging_scrollbar = False
                            self.active_grant_input_item = None
                            return "open_grant_dialog"

                        if self.possession_prev_btn_rect and self.possession_prev_btn_rect.collidepoint(mouse_pos):
                            if getattr(self, "possession_page", 0) > 0:
                                self.possession_page -= 1
                                return "possession_page_prev"

                        if self.possession_next_btn_rect and self.possession_next_btn_rect.collidepoint(mouse_pos):
                            self.possession_page = getattr(self, "possession_page", 0) + 1
                            return "possession_page_next"

                        return None

                    # Priority 0.5: Member Inventory Dialog clicks
                    if self.selected_member_inventory_id is not None:
                        if self.close_member_inv_btn_rect and self.close_member_inv_btn_rect.collidepoint(mouse_pos):
                            self.selected_member_inventory_id = None
                            return "close_member_inventory"

                        mem_obj = None
                        fam = villager_manager.get_family_by_id(self.selected_family_id)
                        if fam:
                            mem_obj = next((m for m in fam.members if m.id == self.selected_member_inventory_id), None)

                        if mem_obj:
                            for it_name, d_rect in list(self.member_deposit_btn_rects.items()):
                                if d_rect.collidepoint(mouse_pos):
                                    mem_obj.deposit_item_to_chest(it_name, 1, furniture_manager)
                                    return f"deposit_{it_name}"

                            for it_name, dr_rect in list(self.member_drop_btn_rects.items()):
                                if dr_rect.collidepoint(mouse_pos):
                                    mem_obj.drop_inventory_item(it_name, 1, stockpile_manager)
                                    return f"drop_{it_name}"

                        if self.member_inv_bg_rect and not self.member_inv_bg_rect.collidepoint(mouse_pos):
                            self.selected_member_inventory_id = None
                            return "close_member_inventory"

                        return "member_inventory_blocked"

                    # Member inventory buttons on cards
                    for mem_id, btn_rect in list(self.member_inventory_btn_rects.items()):
                        if btn_rect.collidepoint(mouse_pos):
                            self.selected_member_inventory_id = mem_id
                            return f"open_member_inventory_{mem_id}"

                    # Interactive Member Job Assignment: Cycle job directly
                    for mem_id, btn_rect in list(self.member_job_btn_rects.items()):
                        if btn_rect.collidepoint(mouse_pos):
                            fam = villager_manager.get_family_by_id(self.selected_family_id)
                            if fam:
                                mem = next((m for m in fam.members if m.id == mem_id), None)
                                if mem:
                                    job_keys = list(DEDICATED_JOBS.keys())
                                    cur_idx = job_keys.index(mem.job) if mem.job in job_keys else 0
                                    next_job = job_keys[(cur_idx + 1) % len(job_keys)]
                                    mem.set_job(next_job)
                                    return f"cycle_job_{mem_id}_{next_job}"

                    # Contextual Navigation: Jump to Permit from Household
                    if self.household_view_permit_btn_rect and self.household_view_permit_btn_rect.collidepoint(mouse_pos):
                        fam = villager_manager.get_family_by_id(self.selected_family_id) if (villager_manager and self.selected_family_id) else None
                        if fam and fam.assigned_permit_id:
                            self.open_permit_directly(fam.assigned_permit_id, permit_manager)
                            return f"open_permit_{fam.assigned_permit_id}"

                    if self.back_to_families_btn_rect and self.back_to_families_btn_rect.collidepoint(mouse_pos):
                        self.selected_family_id = None
                        self.show_household_possession = False
                        self.show_assign_permit_picker = False
                        return "back_to_families"

                    if self.open_assign_lot_btn_rect and self.open_assign_lot_btn_rect.collidepoint(mouse_pos):
                        self.show_assign_permit_picker = not self.show_assign_permit_picker
                        return "toggle_assign_permit_picker"

                    if self.revoke_deed_btn_rect and self.revoke_deed_btn_rect.collidepoint(mouse_pos):
                        villager_manager.unassign_family(self.selected_family_id)
                        return "revoke_deed"

                    if self.show_assign_permit_picker:
                        # Close button for deed picker
                        if self.close_deed_picker_btn_rect and self.close_deed_picker_btn_rect.collidepoint(mouse_pos):
                            self.show_assign_permit_picker = False
                            return "close_assign_permit_picker"

                        for pid, btn_rect in self.assign_permit_btn_rects.items():
                            if btn_rect.collidepoint(mouse_pos):
                                villager_manager.assign_family_to_permit(self.selected_family_id, pid, permit_manager, building_manager)
                                self.show_assign_permit_picker = False
                                return f"assign_permit_{pid}"

                        # Click outside deed picker closes it
                        if self.deed_picker_bg_rect and not self.deed_picker_bg_rect.collidepoint(mouse_pos):
                            self.show_assign_permit_picker = False
                            return "close_assign_permit_picker"

        # 8. Tab 5: Dedicated Jobs & Schedule Management
        elif self.active_tab == 5:
            # Job search box: click to focus, click elsewhere to unfocus
            if self.job_search_rect and self.job_search_rect.collidepoint(mouse_pos):
                self.job_search_active = True
                return "job_search_focus"
            if self.job_search_active:
                self.job_search_active = False

            # Sub-view A: 24-Hour Schedule Matrix for Selected Job
            if self.selected_schedule_job_id is not None:
                if self.schedule_back_btn_rect and self.schedule_back_btn_rect.collidepoint(mouse_pos):
                    self.selected_schedule_job_id = None
                    return "back_to_jobs"

                if schedule_manager:
                    for brush_type, rect in self.schedule_brush_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            self.selected_schedule_brush = brush_type
                            return f"select_brush_{brush_type}"

                    for hour_idx, rect in self.schedule_hour_cell_rects.items():
                        if rect.collidepoint(mouse_pos):
                            schedule_manager.set_hour_activity(self.selected_schedule_job_id, hour_idx, self.selected_schedule_brush)
                            return f"paint_hour_{hour_idx}_{self.selected_schedule_brush}"

                    for preset_name, rect in self.schedule_preset_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            if preset_name == "standard":
                                schedule_manager.reset_to_default(self.selected_schedule_job_id)
                            elif preset_name == "hardwork":
                                sched = ["SLEEP"]*5 + ["LEISURE"] + ["WORK"]*15 + ["LEISURE"] + ["SLEEP"]*2
                                for h in range(24):
                                    schedule_manager.set_hour_activity(self.selected_schedule_job_id, h, sched[h])
                            elif preset_name == "relaxed":
                                sched = ["SLEEP"]*7 + ["LEISURE"]*2 + ["WORK"]*7 + ["LEISURE"]*6 + ["SLEEP"]*2
                                for h in range(24):
                                    schedule_manager.set_hour_activity(self.selected_schedule_job_id, h, sched[h])
                            return f"apply_schedule_preset_{preset_name}"

            # Sub-view B: Worker Roster for Selected Job
            elif self.selected_job_id is not None:
                if self.back_to_jobs_btn_rect and self.back_to_jobs_btn_rect.collidepoint(mouse_pos):
                    self.selected_job_id = None
                    return "back_to_jobs"

                if self.auto_sort_all_btn_rect and self.auto_sort_all_btn_rect.collidepoint(mouse_pos):
                    if villager_manager:
                        from game.systems.work.workplace_system import auto_sort_all_workers
                        auto_sort_all_workers(permit_manager, furniture_manager, villager_manager,
                                              building_manager=building_manager,
                                              job_filter=self.selected_job_id)
                    return "auto_sort_job"

                # Unassign worker from its configured station.
                for key, rect in list(self.worker_unassign_btn_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        if len(key) == 3:
                            kind, station_id, v_id = key
                            if kind == "permit":
                                permit_manager.unassign_worker_from_permit(station_id, v_id, villager_manager=villager_manager)
                            else:
                                from game.systems.work.workplace_system import unassign_workplace_worker
                                station = None
                                if kind == "furniture" and furniture_manager:
                                    station = furniture_manager.get_furniture_by_id(station_id)
                                elif kind == "building" and building_manager:
                                    station = next((building for building in building_manager.buildings
                                                    if self._workplace_key((kind, building)) == str(station_id)), None)
                                if station:
                                    unassign_workplace_worker(self.selected_job_id, (kind, station), v_id, villager_manager)
                        else:
                            pid, v_id = key
                            permit_manager.unassign_worker_from_permit(pid, v_id, villager_manager=villager_manager)
                        return f"unassign_worker_{v_id}"

                # Assign worker to the nearest available workplace for this job.
                for v_id, rect in list(self.worker_assign_btn_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        if villager_manager:
                            worker = next((v for v in villager_manager.get_all_villagers() if v.id == v_id), None)
                            if worker:
                                from game.systems.work.workplace_system import get_job_workplaces, workplace_workers, workplace_capacity, assigned_ids
                                from game.world.permits import get_villager_home_position
                                home_x, home_y = get_villager_home_position(worker, villager_manager, permit_manager, furniture_manager)
                                occupied = assigned_ids(permit_manager, furniture_manager, building_manager)
                                options = []
                                for kind, station in get_job_workplaces(self.selected_job_id, permit_manager, furniture_manager, building_manager):
                                    workers = workplace_workers((kind, station))
                                    station_cap = workplace_capacity((kind, station))
                                    if station_cap is not None and len(workers) >= station_cap:
                                        continue
                                    sx = (station.grid_x + getattr(station, "tiles_w", getattr(station, "type_cfg", {}).get("width_tiles", 1)) / 2) * TILE_SIZE
                                    sy = (station.grid_y + getattr(station, "tiles_h", getattr(station, "type_cfg", {}).get("height_tiles", 1)) / 2) * TILE_SIZE
                                    options.append((math.hypot(sx - home_x, sy - home_y), kind, station, workers))
                                if options:
                                    _, kind, station, workers = min(options, key=lambda entry: entry[0])
                                    worker.set_job(self.selected_job_id)
                                    workers.append(worker.id)
                                    if kind == "permit":
                                        station.max_workers = max(getattr(station, "max_workers", 1), len(workers))
                        return f"assign_worker_{v_id}"

            # View 1: Root Jobs Directory
            if self.selected_job_id is None:
                if self.selected_workstation_job_id is not None:
                    if self.back_to_jobs_btn_rect and self.back_to_jobs_btn_rect.collidepoint(mouse_pos):
                        self.selected_workstation_job_id = None
                        self.highlight_workplace_key = None
                        return "back_to_workstations"
                    for key, rect in list(self.workplace_crop_btn_rects.items()):
                        if rect.collidepoint(mouse_pos):
                            job_id, station_key = key
                            from game.systems.work.workplace_system import get_job_workplaces
                            workplaces = get_job_workplaces(job_id, permit_manager, furniture_manager, building_manager)
                            station = next((ws for ws in workplaces if self._workplace_key(ws) == station_key), None)
                            if station is not None and station[0] == "permit":
                                self.crop_picker_permit_id = station[1].id
                            return f"workplace_crop_{job_id}"
                    for key, rect in list(self.workplace_plant_btn_rects.items()):
                        if rect.collidepoint(mouse_pos):
                            job_id, station_key = key
                            from game.systems.work.workplace_system import get_job_workplaces
                            workplaces = get_job_workplaces(job_id, permit_manager, furniture_manager, building_manager)
                            station = next((ws for ws in workplaces if self._workplace_key(ws) == station_key), None)
                            if station is not None and station[0] == "furniture":
                                obj = station[1]
                                obj.plant_tree_enabled = not bool(getattr(obj, "plant_tree_enabled", False))
                            return f"workplace_plant_{job_id}"
                if self.universal_schedule_btn_rect and self.universal_schedule_btn_rect.collidepoint(mouse_pos):
                    if schedule_manager:
                        schedule_manager.activate_universal_schedule()
                    self.selected_schedule_job_id = UNIVERSAL_SCHEDULE_ID
                    return "edit_universal_schedule"

                if self.auto_sort_all_btn_rect and self.auto_sort_all_btn_rect.collidepoint(mouse_pos):
                    if villager_manager:
                        from game.systems.work.workplace_system import auto_sort_all_workers
                        auto_sort_all_workers(permit_manager, furniture_manager, villager_manager,
                                              building_manager=building_manager)
                    return "auto_sort_all"

                if self.unassign_all_btn_rect and self.unassign_all_btn_rect.collidepoint(mouse_pos):
                    if villager_manager:
                        from game.systems.work.workplace_system import unassign_all_workers
                        unassign_all_workers(permit_manager, furniture_manager, villager_manager,
                                             building_manager=building_manager)
                    return "unassign_all"

                for job_id, rect in self.job_select_btn_rects.items():
                    if rect.collidepoint(mouse_pos) and self.jobs_viewport_rect and self.jobs_viewport_rect.collidepoint(mouse_pos):
                        self.selected_job_id = job_id
                        return f"select_job_{job_id}"

                for job_id, rect in getattr(self, "job_workstation_btn_rects", {}).items():
                    if rect.collidepoint(mouse_pos) and self.jobs_viewport_rect and self.jobs_viewport_rect.collidepoint(mouse_pos):
                        self.selected_workstation_job_id = job_id
                        return f"select_workstations_{job_id}"

                for job_id, rect in self.job_schedule_btn_rects.items():
                    if rect.collidepoint(mouse_pos) and self.jobs_viewport_rect and self.jobs_viewport_rect.collidepoint(mouse_pos):
                        self.selected_schedule_job_id = job_id
                        return f"edit_schedule_{job_id}"

        # 8.4. Tab 6: Immigration (Notice Board)
        elif self.active_tab == 6:
            from game.systems.village_life.immigration_system import (
                get_immigration_system, STATE_TRAVELING, STATE_WAITING,
            )
            imm = get_immigration_system()
            boards = imm.notice_boards(furniture_manager)
            board_id = boards[0].id if boards else None

            if board_id and getattr(self, "immigrant_post_btn_rect", None) \
                    and self.immigrant_post_btn_rect.collidepoint(mouse_pos):
                imm.post(board_id)
                return "immigration_post"
            if board_id and getattr(self, "immigrant_cancel_btn_rect", None) \
                    and self.immigrant_cancel_btn_rect.collidepoint(mouse_pos):
                imm.cancel_post(board_id)
                return "immigration_cancel"
            for hh_id, (a_rect, r_rect) in getattr(self, "immigrant_action_btns", {}).items():
                hh = imm.find_household(hh_id)
                if hh is None or hh["state"] not in (STATE_TRAVELING, STATE_WAITING):
                    continue
                if a_rect and a_rect.collidepoint(mouse_pos):
                    imm.accept(hh_id, villager_manager, servant_manager)
                    return f"immigration_accept_{hh_id}"
                if r_rect and r_rect.collidepoint(mouse_pos):
                    imm.reject(hh_id)
                    return f"immigration_reject_{hh_id}"

        # 8.5. Tab 7: Taxation & Tithes
        elif self.active_tab == 7:
            # Single modal owner: the Wealth dialog always wins over Item
            # Distribution if both flags ever desync.
            if self.show_item_dist_dialog and self.show_wealth_detail_dialog:
                self.show_item_dist_dialog = False
            if self.show_item_dist_dialog:
                # The wealth card sits outside the dialog — let it switch
                # dialogs directly instead of being blocked by the overlay.
                if self.check_wealth_detail_btn_rect and self.check_wealth_detail_btn_rect.collidepoint(mouse_pos):
                    self.show_wealth_detail_dialog = True
                    self.show_item_dist_dialog = False
                    return "open_wealth_dialog"
                if self.item_dist_close_rect and self.item_dist_close_rect.collidepoint(mouse_pos):
                    self.show_item_dist_dialog = False
                    return "close_item_dist_dialog"
                for view_key, r in getattr(self, "item_dist_view_btns", {}).items():
                    if r and r.collidepoint(mouse_pos):
                        self.item_dist_view = view_key
                        return f"item_dist_view_{view_key}"
                for item_name, r in getattr(self, "item_dist_check_rects", {}).items():
                    if r and r.collidepoint(mouse_pos):
                        if item_name in self.item_dist_checked:
                            self.item_dist_checked.discard(item_name)
                        else:
                            self.item_dist_checked.add(item_name)
                        return f"item_dist_toggle_{item_name}"
                return None

            if self.check_item_dist_btn_rect and self.check_item_dist_btn_rect.collidepoint(mouse_pos):
                self.show_item_dist_dialog = True
                self.show_wealth_detail_dialog = False
                self.item_dist_view = "production"
                return "open_item_dist_dialog"

            if self.show_wealth_detail_dialog:
                if self.check_item_dist_btn_rect and self.check_item_dist_btn_rect.collidepoint(mouse_pos):
                    self.show_item_dist_dialog = True
                    self.show_wealth_detail_dialog = False
                    self.item_dist_view = "production"
                    return "open_item_dist_dialog"
                if self.close_wealth_dlg_btn_rect and self.close_wealth_dlg_btn_rect.collidepoint(mouse_pos):
                    self.show_wealth_detail_dialog = False
                    return "close_wealth_dialog"
                return None

            if self.check_wealth_detail_btn_rect and self.check_wealth_detail_btn_rect.collidepoint(mouse_pos):
                self.show_wealth_detail_dialog = True
                self.show_item_dist_dialog = False
                return "open_wealth_dialog"

            from game.systems.village_life.church_system import ChurchSystem
            from game.systems.economy.taxation_system import TaxationSystem
            if not hasattr(self, "church_tax") or not isinstance(self.church_tax, dict):
                self.church_tax = ChurchSystem.get_tax_settings()

            if self.church_tax_enabled_rect and self.church_tax_enabled_rect.collidepoint(mouse_pos):
                ChurchSystem.set_tax_enabled(not ChurchSystem.is_tax_enabled())
                return "toggle_church_tax"
            if self.socage_tax_enabled_rect and self.socage_tax_enabled_rect.collidepoint(mouse_pos):
                TaxationSystem.set_socage_enabled(not TaxationSystem.is_socage_enabled())
                return "toggle_socage_tax"
            if self.socage_tax_input_rect and self.socage_tax_input_rect.collidepoint(mouse_pos):
                self.socage_tax_input_active = True
                self.socage_tax_input_text = str(TaxationSystem.get_socage_percent())
                self.socage_tax_input_replace = True
                return "socage_tax_input_focus"

        # 9. Tab 8: Planning & Roadmap Tab
        elif self.active_tab == 8:
            for status_key, r in list(self.planning_filter_rects.items()):
                if r.collidepoint(mouse_pos):
                    self.planning_filter_status = status_key
                    self.planning_page = 0
                    return f"planning_filter_{status_key}"

            if self.planning_prev_btn_rect and self.planning_prev_btn_rect.collidepoint(mouse_pos):
                if self.planning_page > 0:
                    self.planning_page -= 1
                    return "planning_page_prev"

            if self.planning_next_btn_rect and self.planning_next_btn_rect.collidepoint(mouse_pos):
                self.planning_page += 1
                return "planning_page_next"

        return None

    def draw(self, surface, building_manager, permit_manager, resources, servant_manager=None, villager_manager=None, schedule_manager=None, day_cycle=None, furniture_manager=None, stockpile_manager=None, production_system=None):
        self._init_fonts()
        screen_w, screen_h = surface.get_size()
        self.modal_w = min(upx(RAPORT_MODAL_WIDTH), screen_w - upx(48))
        self.modal_h = min(upx(RAPORT_MODAL_HEIGHT), screen_h - upx(48))

        self.btn_left_rect.x = upx(16)
        self.btn_left_rect.y = (screen_h // 2) - upx(21)

        # Left HUD Button "Raport"
        mouse_pos = pygame.mouse.get_pos()
        btn_hover = self.btn_left_rect.collidepoint(mouse_pos)
        btn_bg = (40, 56, 80) if btn_hover else COLOR_RAPORT_BTN_BG
        pygame.draw.rect(surface, btn_bg, self.btn_left_rect, border_radius=upx(6))
        pygame.draw.rect(surface, COLOR_RAPORT_BTN_BORDER, self.btn_left_rect, width=2, border_radius=upx(6))

        btn_txt = self.font_btn.render("Town Ledger", True, COLOR_TEXT_MAIN)
        txt_rect = btn_txt.get_rect(center=self.btn_left_rect.center)
        surface.blit(btn_txt, txt_rect)

        if not self.is_open:
            return

        # Modal Overlay
        dim_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        dim_surf.fill((0, 0, 0, 140))
        surface.blit(dim_surf, (0, 0))

        mx = (screen_w - self.modal_w) // 2
        my = (screen_h - self.modal_h) // 2

        modal_surf = pygame.Surface((self.modal_w, self.modal_h), pygame.SRCALPHA)
        pygame.draw.rect(modal_surf, COLOR_MODAL_BG, (0, 0, self.modal_w, self.modal_h), border_radius=upx(12))
        pygame.draw.rect(modal_surf, COLOR_MODAL_BORDER, (0, 0, self.modal_w, self.modal_h), width=2, border_radius=upx(12))
        surface.blit(modal_surf, (mx, my))

        # Title
        title_surf = self.font_title.render("TOWN LEDGER", True, COLOR_TEXT_TITLE)
        surface.blit(title_surf, (mx + upx(20), my + upx(16)))

        # Close (X)
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - upx(36), my + upx(14), upx(22), upx(22))
        close_hover = self.close_btn_rect.collidepoint(mouse_pos)
        close_col = (239, 68, 68) if close_hover else COLOR_TEXT_MUTED
        close_surf = self.font_btn.render("X", True, close_col)
        surface.blit(close_surf, (self.close_btn_rect.x + upx(5), self.close_btn_rect.y + 1))

        # Tabs
        self.tab_rects = []
        tab_x = mx + upx(20)
        tab_y = my + upx(50)
        tab_spacing = upx(8)
        visible_tabs = [t for t in self.tabs if not t.get("hidden", False)]
        avail_w = self.modal_w - upx(40) - ((len(visible_tabs) - 1) * tab_spacing)
        tab_w = avail_w // len(visible_tabs)
        tab_h = upx(32)

        for i, tab in enumerate(self.tabs):
            if tab.get("hidden", False):
                self.tab_rects.append(pygame.Rect(-upx(9999), -upx(9999), 0, 0))
                continue

            t_rect = pygame.Rect(tab_x, tab_y, tab_w, tab_h)
            self.tab_rects.append(t_rect)
            is_active = (i == self.active_tab)

            t_bg = COLOR_TAB_ACTIVE if is_active else COLOR_TAB_INACTIVE
            pygame.draw.rect(surface, t_bg, t_rect, border_radius=upx(6))
            if is_active:
                pygame.draw.rect(surface, (96, 165, 250), t_rect, width=1, border_radius=upx(6))

            txt_c = (255, 255, 255) if is_active else COLOR_TEXT_MUTED
            t_surf = self.font_tab.render(tab["title"], True, txt_c)

            if tab["wip"]:
                wip_w = upx(26)
                wip_h = upx(14)
                wip_rect = pygame.Rect(tab_x + tab_w - wip_w - upx(4), tab_y + (tab_h - wip_h) // 2, wip_w, wip_h)
                pygame.draw.rect(surface, COLOR_BADGE_WIP, wip_rect, border_radius=3)
                w_txt = self.font_badge.render("WIP", True, (0, 0, 0))
                surface.blit(w_txt, (wip_rect.centerx - w_txt.get_width() // 2, wip_rect.centery - w_txt.get_height() // 2))
                surface.blit(t_surf, (tab_x + upx(5), tab_y + (tab_h - t_surf.get_height()) // 2))
            else:
                surface.blit(t_surf, (tab_x + (tab_w - t_surf.get_width()) // 2, tab_y + (tab_h - t_surf.get_height()) // 2))

            tab_x += tab_w + tab_spacing

        pygame.draw.line(surface, COLOR_MODAL_BORDER, (mx + upx(20), tab_y + tab_h + upx(8)), (mx + self.modal_w - upx(20), tab_y + tab_h + upx(8)))

        content_y = tab_y + tab_h + upx(16)
        self.num_fields = {}
        if self.active_tab == 0:
            self._draw_building_tab(surface, mx, content_y, building_manager, permit_manager, resources, furniture_manager=furniture_manager, villager_manager=villager_manager)
        elif self.active_tab == 1:
            self._draw_permit_tab(surface, mx, content_y, permit_manager, building_manager)
        elif self.active_tab == 2:
            self._draw_priority_tab(surface, mx, content_y, servant_manager)
        elif self.active_tab == 3:
            self._draw_schedule_tab(surface, mx, content_y, schedule_manager=schedule_manager, day_cycle=day_cycle)
        elif self.active_tab == 4:
            self._draw_villagers_tab(surface, mx, content_y, villager_manager, permit_manager, building_manager, furniture_manager=furniture_manager, stockpile_manager=stockpile_manager, resources=resources, servant_manager=servant_manager, production_system=production_system, day_cycle=day_cycle)
        elif self.active_tab == 5:
            if self.selected_schedule_job_id is not None:
                self._draw_schedule_tab(surface, mx, content_y, schedule_manager=schedule_manager, day_cycle=day_cycle)
            else:
                self._draw_workers_tab(surface, mx, content_y, villager_manager, permit_manager, furniture_manager, schedule_manager=schedule_manager, building_manager=building_manager)
        elif self.active_tab == 6:
            self._draw_immigrant_tab(surface, mx, content_y, villager_manager, permit_manager, furniture_manager=furniture_manager, day_cycle=day_cycle)
        elif self.active_tab == 7:
            self._draw_tax_tab(surface, mx, content_y, villager_manager, permit_manager, furniture_manager=furniture_manager, production_system=production_system, resources=resources, building_manager=building_manager, stockpile_manager=stockpile_manager, day_cycle=day_cycle, servant_manager=servant_manager)
        elif self.active_tab == 8:
            self._draw_planning_tab(surface, mx, content_y)

















