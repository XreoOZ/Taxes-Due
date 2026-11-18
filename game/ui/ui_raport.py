"""
Raport UI (Town Ledger, Free-form Area Permit Deeds, RimWorld Work Priorities & Building Management Modal)
"""

import math
import pygame
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
    WORK_TYPES,
    PRIORITY_COLORS,
    DEDICATED_JOBS,
    FURNITURE_TYPES,
    COST_PER_BLOCK_WOOD,
    COST_PER_BLOCK_STONE,
    TILE_SIZE,
    RAPORT_MODAL_WIDTH,
    RAPORT_MODAL_HEIGHT,
    DEMOLITION_REFUND_RATIO,
    SCHEDULE_TYPES,
    DEFAULT_JOB_SCHEDULE,
    DAYS_OF_WEEK,
    is_food_item
)
from game.data.planning import (
    PLANNING_FEATURES,
    get_all_planning_features,
    get_features_by_status,
    STATUS_IMPLEMENTED,
    STATUS_PARTIAL,
    STATUS_PLANNED
)
from game.systems.production_distribution import ProductionDistributionSystem
from game.systems.household_inventory import (
    get_household_possessions,
    sort_possession_items,
    canonical_item_name
)
from game.systems.wealth_system import VillageWealthSystem
from game.ui.item_icons import draw_item_icon

GRANTABLE_ITEMS = [
    {"type": "Hoe", "name": "Hoe"},
    {"type": "Sickle", "name": "Sickle"},
    {"type": "Watering_Can", "name": "Watering Can"},
    {"type": "Potato", "name": "Potato"},
    {"type": "Water", "name": "Water"},
    {"type": "Wood", "name": "Wood"},
    {"type": "Stone", "name": "Stone"},
    {"type": "Copper", "name": "Copper Coin"},
    {"type": "Silver", "name": "Silver Coin"},
    {"type": "Gold", "name": "Gold Coin"},
]

class RaportUI:
    def __init__(self):
        self.is_open = False
        self.active_tab = 0  # 0: Buildings, 1: Area Permits, 2: Priority, 3: Schedule, 4: Villagers, 5: Workers
        self.show_build_menu = False
        self.show_structures_menu = False
        self.show_furniture_menu = False
        self.selected_building_type = None
        self.selected_furniture_type = None
        self.placing_permit_type = None

        # Inspection & Focused entity tracking
        self.selected_permit_inspect_id = None
        self.selected_building_inspect = None
        self.market_profile_btn_rects = {}
        self.selected_market_building = None

        # Left HUD Button (Town Ledger)
        self.btn_left_rect = pygame.Rect(16, 200, 116, 42)

        # Tabs
        self.tabs = [
            {"id": "building", "title": "Buildings", "wip": False},
            {"id": "permit", "title": "Permits", "wip": False},
            {"id": "priority", "title": "Priority", "wip": False},
            {"id": "schedule", "title": "Schedule", "wip": False, "hidden": True},
            {"id": "villagers", "title": "Household", "wip": False},
            {"id": "workers", "title": "Jobs", "wip": False},
            {"id": "production", "title": "Production", "wip": False},
            {"id": "tax", "title": "Taxes", "wip": True},
            {"id": "planning", "title": "Roadmap", "wip": True},
        ]

        # Building Category Navigation State
        self.selected_building_category = None  # None = Root Category View; cat_id = Category Filtered View
        self.building_category_btn_rects = {}
        self.building_category_back_btn_rect = None
        self.quick_build_btn_rects = {}
        self.furniture_move_btn_rects = {}
        self.furniture_destroy_btn_rects = {}
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
        self.selected_schedule_day = "Monday"
        self.schedule_day_btn_rects = {}
        self.prayer_start_dec_rect = None
        self.prayer_start_inc_rect = None
        self.prayer_end_dec_rect = None
        self.prayer_end_inc_rect = None
        self.schedule_job_select_btn_rects = {}
        self.schedule_brush_btn_rects = {}
        self.schedule_hour_cell_rects = {}
        self.schedule_preset_btn_rects = {}
        self.schedule_back_btn_rect = None

        # Member Job Assignment State
        self.member_job_btn_rects = {}

        # Church Tax State
        self.church_tax = {"Gold": 0, "Silver": 0, "Copper": 1}
        self.church_tax_g_dec_rect = None
        self.church_tax_g_inc_rect = None
        self.church_tax_s_dec_rect = None
        self.church_tax_s_inc_rect = None
        self.church_tax_c_dec_rect = None
        self.church_tax_c_inc_rect = None

        # Village Wealth State
        self.show_wealth_detail_dialog = False
        self.check_wealth_detail_btn_rect = None
        self.close_wealth_dlg_btn_rect = None

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
        self.grant_dec_btn_rects = {}
        self.grant_inc_btn_rects = {}
        self.grant_max_btn_rects = {}
        self.grant_item_qty_rects = {}
        self.active_grant_input_item = None
        self.grant_input_text = ""
        self.grant_header_close_btn_rect = None
        self.grant_dlg_rect = None
        self.grant_viewport_rect = None
        self.grant_scrollbar_rect = None
        self.grant_thumb_rect = None
        self.grant_scroll_y = 0
        self.grant_max_scroll = 0
        self.grant_is_dragging_scrollbar = False
        self.cached_stockpile_manager = None

        # Contextual View Navigation Rects (Agent 2)
        self.permit_household_btn_rects = {}
        self.building_household_btn_rects = {}
        self.household_view_permit_btn_rect = None
        self.cancel_construction_btn_rects = {}
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
        self.back_to_families_btn_rect = None
        self.view_family_btn_rects = []
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
        self.worker_dec_btn_rects = {}
        self.worker_inc_btn_rects = {}
        self.worker_auto_btn_rects = {}

        # Workers / Jobs Tab Controls
        self.selected_job_id = None
        self.back_to_jobs_btn_rect = None
        self.auto_sort_all_btn_rect = None
        self.job_select_btn_rects = {}
        self.job_schedule_btn_rects = {}
        self.worker_assign_btn_rects = {}
        self.worker_unassign_btn_rects = {}

        self.fonts_loaded = False

    def _init_fonts(self):
        if not self.fonts_loaded:
            self.font_btn = pygame.font.SysFont("Segoe UI", 12, bold=True)
            self.font_title = pygame.font.SysFont("Segoe UI", 16, bold=True)
            self.font_tab = pygame.font.SysFont("Segoe UI", 12, bold=True)
            self.font_body = pygame.font.SysFont("Segoe UI", 12)
            self.font_badge = pygame.font.SysFont("Segoe UI", 10, bold=True)
            self.font_sub = pygame.font.SysFont("Segoe UI", 12, bold=True)
            self.font_priority = pygame.font.SysFont("Segoe UI", 14, bold=True)
            self.fonts_loaded = True

    def open(self):
        self.is_open = True

    def close(self):
        """Tutup modal Raport UI dan reset seluruh status dialog internalnya"""
        self.is_open = False
        self.selected_building_category = None
        self.selected_permit_category = None
        self.show_build_menu = False
        self.show_structures_menu = False
        self.show_furniture_menu = False
        self.show_household_possession = False
        self.show_wealth_detail_dialog = False
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

    def open_household_directly(self, family_id):
        """Contextual View: Opens Town Ledger directly to the specified family's View Family screen"""
        self.is_open = True
        self.active_tab = 4  # Tab Household
        self.selected_family_id = family_id
        self.show_household_possession = False
        self.show_wealth_detail_dialog = False
        self.show_grant_dialog = False
        self.show_grant_confirm = False
        self.show_assign_permit_picker = False

    def open_possession_directly(self, family_id):
        """Contextual View: Opens Town Ledger directly to the specified household's Possession screen"""
        self.is_open = True
        self.active_tab = 4  # Tab Household
        self.selected_family_id = family_id
        self.show_household_possession = True
        self.show_grant_dialog = False
        self.show_grant_confirm = False
        self.show_assign_permit_picker = False

    def open_permit_directly(self, permit_id, permit_manager):
        """Contextual View: Opens Town Ledger directly to the specified permit within its category view"""
        target_p = next((p for p in getattr(permit_manager, "permits", []) if p.id == permit_id), None)
        self.is_open = True
        self.active_tab = 1  # Tab Area Permits
        self.selected_permit_inspect_id = permit_id
        if target_p:
            categories = get_permit_categories()
            cat = next((c for c in categories if target_p.permit_type in c.get("permit_types", [])), None)
            self.selected_permit_category = cat["id"] if cat else None
        else:
            self.selected_permit_category = None

    def open_building_directly(self, building):
        """Contextual View: Opens Town Ledger directly to the specified building in its category view"""
        if building:
            b_cfg = BUILDING_TYPES.get(getattr(building, "building_type", ""), {})
            cat_id = b_cfg.get("category_id", getattr(building, "building_type", "wooden_structure"))
            self.is_open = True
            self.active_tab = 0  # Tab Buildings
            self.selected_building_category = cat_id
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
        return stock

    def is_text_input_active(self):
        """Mengembalikan True jika player sedang mengetik di input/text field dalam UI Raport"""
        return bool(self.is_open and self.show_grant_dialog and self.active_grant_input_item is not None)

    def toggle(self):
        if self.is_open:
            self.close()
        else:
            self.open()

    def handle_event(self, event, building_manager, permit_manager, resources, servant_manager=None, villager_manager=None, schedule_manager=None, day_cycle=None, stockpile_manager=None, furniture_manager=None, production_system=None):
        if stockpile_manager is not None:
            self.cached_stockpile_manager = stockpile_manager
        sm = stockpile_manager or self.cached_stockpile_manager

        if event.type == pygame.KEYDOWN:
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
            if self.show_grant_dialog and getattr(self, "grant_max_scroll", 0) > 0:
                self.grant_scroll_y = max(0, min(self.grant_scroll_y - event.y * 36, self.grant_max_scroll))
                return "grant_scroll"
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
                scroll_step = -36 if event.button == 4 else 36
                self.grant_scroll_y = max(0, min(self.grant_scroll_y + scroll_step, self.grant_max_scroll))
                return "grant_scroll"
            if event.button != 1:
                return None
        else:
            return None

        mouse_pos = event.pos

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
                for it_type, rect in list(self.grant_dec_btn_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        self.grant_amounts[it_type] = max(0, self.grant_amounts.get(it_type, 0) - 1)
                        return f"grant_dec_{it_type}"

                for it_type, rect in list(self.grant_inc_btn_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        avail = stock.get(it_type, 0)
                        self.grant_amounts[it_type] = min(avail, self.grant_amounts.get(it_type, 0) + 1)
                        return f"grant_inc_{it_type}"

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

        # 2. Close Button (X)
        if self.close_btn_rect and self.close_btn_rect.collidepoint(mouse_pos):
            self.is_open = False
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
                self.grant_amounts = {}
                self.active_grant_input_item = None
                self.show_assign_permit_picker = False
                self.selected_job_id = None
                self.selected_schedule_job_id = None
                return f"switch_tab_{i}"

        # 4. Tab 0: Building Management
        if self.active_tab == 0:
            # Check Back button when viewing a specific building category
            if self.building_category_back_btn_rect and self.building_category_back_btn_rect.collidepoint(mouse_pos):
                self.selected_building_category = None
                return "building_category_back"

            # Check Category Selection buttons on Root Categories Screen
            if self.selected_building_category is None:
                for cat_id, rect in list(self.building_category_btn_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        if cat_id == "furniture_quick":
                            self.selected_building_category = "furniture"
                            return "select_building_category_furniture"
                        self.selected_building_category = cat_id
                        return f"select_building_category_{cat_id}"

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

            # Check Cancel Construction buttons
            for s, rect in list(self.cancel_construction_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    servants = servant_manager.servants if servant_manager else None
                    building_manager.cancel_construction(s, resources=resources, stockpile_manager=stockpile_manager, all_servants=servants)
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

            # Check Furniture Placement buttons
            for f_type, rect in list(self.furniture_select_rects.items()):
                if rect.collidepoint(mouse_pos):
                    f_cfg = FURNITURE_TYPES.get(f_type, {})
                    can_afford = (resources.get("Wood", 0) >= f_cfg.get("cost_wood", 0))
                    if can_afford:
                        self.selected_furniture_type = f_type
                        self.selected_building_type = None
                        self.placing_permit_type = None
                        self.show_furniture_menu = False
                        self.is_open = False
                        return f"start_place_furniture_{f_type}"
                    else:
                        return f"low_wood_{f_type}"

            # Check Furniture Move buttons
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

            # Worker count +/- and Auto buttons
            for pid, rect in list(self.worker_dec_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    permit_manager.change_max_workers(pid, -1, villager_manager)
                    return f"dec_worker_{pid}"

            for pid, rect in list(self.worker_inc_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    permit_manager.change_max_workers(pid, 1, villager_manager)
                    return f"inc_worker_{pid}"

            for pid, rect in list(self.worker_auto_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    if villager_manager:
                        permit_manager.auto_sort_workers(villager_manager)
                    return f"auto_worker_{pid}"

            # Check crop picker dialog first if open
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

            # Check Plant Crop buttons
            for pid, rect in list(self.open_plant_btn_rects.items()):
                if rect.collidepoint(mouse_pos):
                    self.crop_picker_permit_id = pid if self.crop_picker_permit_id != pid else None
                    return f"toggle_plant_{pid}"

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

                    for day_name, rect in self.schedule_day_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            self.selected_schedule_day = day_name
                            return f"select_schedule_day_{day_name}"

                    if self.prayer_start_dec_rect and self.prayer_start_dec_rect.collidepoint(mouse_pos):
                        s, e = schedule_manager.get_prayer_hours()
                        schedule_manager.set_prayer_time(max(0, s - 1), e)
                        return "prayer_start_dec"
                    if self.prayer_start_inc_rect and self.prayer_start_inc_rect.collidepoint(mouse_pos):
                        s, e = schedule_manager.get_prayer_hours()
                        if s + 1 < e:
                            schedule_manager.set_prayer_time(s + 1, e)
                        return "prayer_start_inc"
                    if self.prayer_end_dec_rect and self.prayer_end_dec_rect.collidepoint(mouse_pos):
                        s, e = schedule_manager.get_prayer_hours()
                        if e - 1 > s:
                            schedule_manager.set_prayer_time(s, e - 1)
                        return "prayer_end_dec"
                    if self.prayer_end_inc_rect and self.prayer_end_inc_rect.collidepoint(mouse_pos):
                        s, e = schedule_manager.get_prayer_hours()
                        schedule_manager.set_prayer_time(s, min(24, e + 1))
                        return "prayer_end_inc"

                    for brush_type, rect in self.schedule_brush_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            self.selected_schedule_brush = brush_type
                            return f"select_brush_{brush_type}"

                    for hour_idx, rect in self.schedule_hour_cell_rects.items():
                        if rect.collidepoint(mouse_pos):
                            schedule_manager.set_hour_activity(self.selected_schedule_job_id, hour_idx, self.selected_schedule_brush, day=self.selected_schedule_day)
                            return f"paint_hour_{hour_idx}_{self.selected_schedule_brush}"

                    for preset_name, rect in self.schedule_preset_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            if preset_name == "standard":
                                schedule_manager.reset_to_default(self.selected_schedule_job_id, day=self.selected_schedule_day)
                            elif preset_name == "hardwork":
                                sched = ["SLEEP"]*5 + ["LEISURE"] + ["WORK"]*15 + ["LEISURE"] + ["SLEEP"]*2
                                for h in range(24):
                                    schedule_manager.set_hour_activity(self.selected_schedule_job_id, h, sched[h], day=self.selected_schedule_day)
                            elif preset_name == "relaxed":
                                sched = ["SLEEP"]*7 + ["LEISURE"]*2 + ["WORK"]*7 + ["LEISURE"]*6 + ["SLEEP"]*2
                                for h in range(24):
                                    schedule_manager.set_hour_activity(self.selected_schedule_job_id, h, sched[h], day=self.selected_schedule_day)
                            return f"apply_schedule_preset_{preset_name}"

        # 7. Tab 4: Villagers & Family Clans Management
        elif self.active_tab == 4:
            if villager_manager:
                # View 1: Family Directory
                if self.selected_family_id is None:
                    if self.add_family_cheat_btn_rect and self.add_family_cheat_btn_rect.collidepoint(mouse_pos):
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

                    if self.household_possession_btn_rect and self.household_possession_btn_rect.collidepoint(mouse_pos):
                        self.show_household_possession = True
                        self.possession_page = 0
                        return "open_household_possession"

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
            # Sub-view A: 24-Hour Schedule Matrix for Selected Job
            if self.selected_schedule_job_id is not None:
                if self.schedule_back_btn_rect and self.schedule_back_btn_rect.collidepoint(mouse_pos):
                    self.selected_schedule_job_id = None
                    return "back_to_jobs"

                if schedule_manager:
                    for day_name, rect in self.schedule_day_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            self.selected_schedule_day = day_name
                            return f"select_schedule_day_{day_name}"

                    if self.prayer_start_dec_rect and self.prayer_start_dec_rect.collidepoint(mouse_pos):
                        s, e = schedule_manager.get_prayer_hours()
                        schedule_manager.set_prayer_time(max(0, s - 1), e)
                        return "prayer_start_dec"
                    if self.prayer_start_inc_rect and self.prayer_start_inc_rect.collidepoint(mouse_pos):
                        s, e = schedule_manager.get_prayer_hours()
                        if s + 1 < e:
                            schedule_manager.set_prayer_time(s + 1, e)
                        return "prayer_start_inc"
                    if self.prayer_end_dec_rect and self.prayer_end_dec_rect.collidepoint(mouse_pos):
                        s, e = schedule_manager.get_prayer_hours()
                        if e - 1 > s:
                            schedule_manager.set_prayer_time(s, e - 1)
                        return "prayer_end_dec"
                    if self.prayer_end_inc_rect and self.prayer_end_inc_rect.collidepoint(mouse_pos):
                        s, e = schedule_manager.get_prayer_hours()
                        schedule_manager.set_prayer_time(s, min(24, e + 1))
                        return "prayer_end_inc"

                    for brush_type, rect in self.schedule_brush_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            self.selected_schedule_brush = brush_type
                            return f"select_brush_{brush_type}"

                    for hour_idx, rect in self.schedule_hour_cell_rects.items():
                        if rect.collidepoint(mouse_pos):
                            schedule_manager.set_hour_activity(self.selected_schedule_job_id, hour_idx, self.selected_schedule_brush, day=self.selected_schedule_day)
                            return f"paint_hour_{hour_idx}_{self.selected_schedule_brush}"

                    for preset_name, rect in self.schedule_preset_btn_rects.items():
                        if rect.collidepoint(mouse_pos):
                            if preset_name == "standard":
                                schedule_manager.reset_to_default(self.selected_schedule_job_id, day=self.selected_schedule_day)
                            elif preset_name == "hardwork":
                                sched = ["SLEEP"]*5 + ["LEISURE"] + ["WORK"]*15 + ["LEISURE"] + ["SLEEP"]*2
                                for h in range(24):
                                    schedule_manager.set_hour_activity(self.selected_schedule_job_id, h, sched[h], day=self.selected_schedule_day)
                            elif preset_name == "relaxed":
                                sched = ["SLEEP"]*7 + ["LEISURE"]*2 + ["WORK"]*7 + ["LEISURE"]*6 + ["SLEEP"]*2
                                for h in range(24):
                                    schedule_manager.set_hour_activity(self.selected_schedule_job_id, h, sched[h], day=self.selected_schedule_day)
                            return f"apply_schedule_preset_{preset_name}"

            # Sub-view B: Worker Roster for Selected Job
            elif self.selected_job_id is not None:
                if self.back_to_jobs_btn_rect and self.back_to_jobs_btn_rect.collidepoint(mouse_pos):
                    self.selected_job_id = None
                    return "back_to_jobs"

                if self.auto_sort_all_btn_rect and self.auto_sort_all_btn_rect.collidepoint(mouse_pos):
                    if villager_manager:
                        permit_manager.auto_sort_workers(villager_manager)
                    return "auto_sort_job"

                # Unassign worker
                for (pid, v_id), rect in list(self.worker_unassign_btn_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        permit_manager.unassign_worker_from_permit(pid, v_id)
                        return f"unassign_worker_{v_id}"

                # Assign worker to nearest available farm permit
                for v_id, rect in list(self.worker_assign_btn_rects.items()):
                    if rect.collidepoint(mouse_pos):
                        if villager_manager:
                            worker = next((v for v in villager_manager.get_all_villagers() if v.id == v_id), None)
                            if worker:
                                avail_permits = [p for p in permit_manager.permits if p.permit_type == "farm"]
                                if avail_permits:
                                    avail_permits.sort(key=lambda p: (
                                        0 if len(p.assigned_workers) < p.max_workers else 1,
                                        math.hypot((p.grid_x + p.tiles_w / 2.0) * TILE_SIZE - worker.x, (p.grid_y + p.tiles_h / 2.0) * TILE_SIZE - worker.y)
                                    ))
                                    permit_manager.assign_worker_to_permit(avail_permits[0].id, worker.id)
                        return f"assign_worker_{v_id}"

            # View 1: Root Jobs Directory
            else:
                if self.auto_sort_all_btn_rect and self.auto_sort_all_btn_rect.collidepoint(mouse_pos):
                    if villager_manager:
                        permit_manager.auto_sort_workers(villager_manager)
                    return "auto_sort_all"

                for job_id, rect in self.job_select_btn_rects.items():
                    if rect.collidepoint(mouse_pos):
                        self.selected_job_id = job_id
                        return f"select_job_{job_id}"

                for job_id, rect in self.job_schedule_btn_rects.items():
                    if rect.collidepoint(mouse_pos):
                        self.selected_schedule_job_id = job_id
                        return f"edit_schedule_{job_id}"

        # 8.5. Tab 7: Taxation & Tithes
        elif self.active_tab == 7:
            if self.show_wealth_detail_dialog:
                if self.close_wealth_dlg_btn_rect and self.close_wealth_dlg_btn_rect.collidepoint(mouse_pos):
                    self.show_wealth_detail_dialog = False
                    return "close_wealth_dialog"
                return None

            if self.check_wealth_detail_btn_rect and self.check_wealth_detail_btn_rect.collidepoint(mouse_pos):
                self.show_wealth_detail_dialog = True
                return "open_wealth_dialog"

            if not hasattr(self, "church_tax") or not isinstance(self.church_tax, dict):
                self.church_tax = {"Gold": 0, "Silver": 0, "Copper": 1}
            if self.church_tax_g_dec_rect and self.church_tax_g_dec_rect.collidepoint(mouse_pos):
                self.church_tax["Gold"] = max(0, self.church_tax.get("Gold", 0) - 1)
                return "church_tax_gold_dec"
            if self.church_tax_g_inc_rect and self.church_tax_g_inc_rect.collidepoint(mouse_pos):
                self.church_tax["Gold"] = self.church_tax.get("Gold", 0) + 1
                return "church_tax_gold_inc"
            if self.church_tax_s_dec_rect and self.church_tax_s_dec_rect.collidepoint(mouse_pos):
                self.church_tax["Silver"] = max(0, self.church_tax.get("Silver", 0) - 1)
                return "church_tax_silver_dec"
            if self.church_tax_s_inc_rect and self.church_tax_s_inc_rect.collidepoint(mouse_pos):
                self.church_tax["Silver"] = self.church_tax.get("Silver", 0) + 1
                return "church_tax_silver_inc"
            if self.church_tax_c_dec_rect and self.church_tax_c_dec_rect.collidepoint(mouse_pos):
                self.church_tax["Copper"] = max(0, self.church_tax.get("Copper", 0) - 1)
                return "church_tax_copper_dec"
            if self.church_tax_c_inc_rect and self.church_tax_c_inc_rect.collidepoint(mouse_pos):
                self.church_tax["Copper"] = self.church_tax.get("Copper", 0) + 1
                return "church_tax_copper_inc"

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

        self.btn_left_rect.x = 16
        self.btn_left_rect.y = (screen_h // 2) - 21

        # Left HUD Button "Raport"
        mouse_pos = pygame.mouse.get_pos()
        btn_hover = self.btn_left_rect.collidepoint(mouse_pos)
        btn_bg = (40, 56, 80) if btn_hover else COLOR_RAPORT_BTN_BG
        pygame.draw.rect(surface, btn_bg, self.btn_left_rect, border_radius=6)
        pygame.draw.rect(surface, COLOR_RAPORT_BTN_BORDER, self.btn_left_rect, width=2, border_radius=6)

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
        pygame.draw.rect(modal_surf, COLOR_MODAL_BG, (0, 0, self.modal_w, self.modal_h), border_radius=12)
        pygame.draw.rect(modal_surf, COLOR_MODAL_BORDER, (0, 0, self.modal_w, self.modal_h), width=2, border_radius=12)
        surface.blit(modal_surf, (mx, my))

        # Title
        title_surf = self.font_title.render("TOWN LEDGER", True, COLOR_TEXT_TITLE)
        surface.blit(title_surf, (mx + 20, my + 16))

        # Close (X)
        self.close_btn_rect = pygame.Rect(mx + self.modal_w - 36, my + 14, 22, 22)
        close_hover = self.close_btn_rect.collidepoint(mouse_pos)
        close_col = (239, 68, 68) if close_hover else COLOR_TEXT_MUTED
        close_surf = self.font_btn.render("X", True, close_col)
        surface.blit(close_surf, (self.close_btn_rect.x + 5, self.close_btn_rect.y + 1))

        # Tabs
        self.tab_rects = []
        tab_x = mx + 20
        tab_y = my + 50
        tab_spacing = 8
        visible_tabs = [t for t in self.tabs if not t.get("hidden", False)]
        avail_w = self.modal_w - 40 - ((len(visible_tabs) - 1) * tab_spacing)
        tab_w = avail_w // len(visible_tabs)
        tab_h = 32

        for i, tab in enumerate(self.tabs):
            if tab.get("hidden", False):
                self.tab_rects.append(pygame.Rect(-9999, -9999, 0, 0))
                continue

            t_rect = pygame.Rect(tab_x, tab_y, tab_w, tab_h)
            self.tab_rects.append(t_rect)
            is_active = (i == self.active_tab)

            t_bg = COLOR_TAB_ACTIVE if is_active else COLOR_TAB_INACTIVE
            pygame.draw.rect(surface, t_bg, t_rect, border_radius=6)
            if is_active:
                pygame.draw.rect(surface, (96, 165, 250), t_rect, width=1, border_radius=6)

            txt_c = (255, 255, 255) if is_active else COLOR_TEXT_MUTED
            t_surf = self.font_tab.render(tab["title"], True, txt_c)

            if tab["wip"]:
                wip_w = 26
                wip_h = 14
                wip_rect = pygame.Rect(tab_x + tab_w - wip_w - 4, tab_y + (tab_h - wip_h) // 2, wip_w, wip_h)
                pygame.draw.rect(surface, COLOR_BADGE_WIP, wip_rect, border_radius=3)
                w_txt = self.font_badge.render("WIP", True, (0, 0, 0))
                surface.blit(w_txt, (wip_rect.centerx - w_txt.get_width() // 2, wip_rect.centery - w_txt.get_height() // 2))
                surface.blit(t_surf, (tab_x + 5, tab_y + (tab_h - t_surf.get_height()) // 2))
            else:
                surface.blit(t_surf, (tab_x + (tab_w - t_surf.get_width()) // 2, tab_y + (tab_h - t_surf.get_height()) // 2))

            tab_x += tab_w + tab_spacing

        pygame.draw.line(surface, COLOR_MODAL_BORDER, (mx + 20, tab_y + tab_h + 8), (mx + self.modal_w - 20, tab_y + tab_h + 8))

        content_y = tab_y + tab_h + 16
        if self.active_tab == 0:
            self._draw_building_tab(surface, mx, content_y, building_manager, permit_manager, resources, furniture_manager=furniture_manager, villager_manager=villager_manager)
        elif self.active_tab == 1:
            self._draw_permit_tab(surface, mx, content_y, permit_manager, building_manager)
        elif self.active_tab == 2:
            self._draw_priority_tab(surface, mx, content_y, servant_manager)
        elif self.active_tab == 3:
            self._draw_schedule_tab(surface, mx, content_y, schedule_manager=schedule_manager, day_cycle=day_cycle)
        elif self.active_tab == 4:
            self._draw_villagers_tab(surface, mx, content_y, villager_manager, permit_manager, building_manager, furniture_manager=furniture_manager, stockpile_manager=stockpile_manager, resources=resources, servant_manager=servant_manager, production_system=production_system)
        elif self.active_tab == 5:
            if self.selected_schedule_job_id is not None:
                self._draw_schedule_tab(surface, mx, content_y, schedule_manager=schedule_manager, day_cycle=day_cycle)
            else:
                self._draw_workers_tab(surface, mx, content_y, villager_manager, permit_manager)
        elif self.active_tab == 6:
            self._draw_production_tab(surface, mx, content_y, villager_manager, permit_manager, furniture_manager=furniture_manager, stockpile_manager=stockpile_manager, production_system=production_system)
        elif self.active_tab == 7:
            self._draw_tax_tab(surface, mx, content_y, villager_manager, permit_manager, furniture_manager=furniture_manager, production_system=production_system, resources=resources, building_manager=building_manager, stockpile_manager=stockpile_manager)
        elif self.active_tab == 8:
            self._draw_planning_tab(surface, mx, content_y)

    def _draw_building_tab(self, surface, mx, cy, building_manager, permit_manager, resources, furniture_manager=None, villager_manager=None):
        """
        Category-based Building Organization UI (Town Ledger)
        Screen 1: Lists dynamically discovered building categories with built count badges & quick construction deeds.
        Screen 2: When category is selected, displays only buildings/furniture belonging to that category with Back button & empty state.
        Zero hardcoded categories or building lists.
        """
        categories = get_building_categories()
        m_pos = pygame.mouse.get_pos()

        self.building_category_back_btn_rect = None
        self.building_category_btn_rects = {}
        self.building_household_btn_rects.clear()
        self.destroy_building_btn_rects = {}
        self.market_profile_btn_rects.clear()
        self.building_select_rects = {}
        self.furniture_select_rects = {}
        self.furniture_move_btn_rects = {}
        self.furniture_destroy_btn_rects = {}

        if self.selected_building_category is None:
            # -----------------------------------------------------------------
            # SCREEN 1: Building & Structure Categories Selection Screen
            # -----------------------------------------------------------------
            demos = getattr(building_manager, "demolition_sites", [])
            total_structures = len(building_manager.buildings) + len(building_manager.construction_sites) + len(demos)
            if furniture_manager and hasattr(furniture_manager, "furniture"):
                total_structures += len(furniture_manager.furniture)

            b_title = self.font_sub.render(f" Buildings & Structure Categories ({len(categories)} categories, {total_structures} total structures):", True, COLOR_TEXT_TITLE)
            surface.blit(b_title, (mx + 24, cy))

            sub_txt = self.font_body.render("Select a category below to inspect structures, manage demolition, or quick-construct deeds:", True, COLOR_TEXT_MUTED)
            surface.blit(sub_txt, (mx + 28, cy + 22))

            card_y = cy + 44
            for cat in categories:
                cat_id = cat["id"]
                cat_name = cat["name"]
                cat_desc = cat["desc"]
                cat_col = cat.get("color", (59, 130, 246))

                if cat.get("kind") == "furniture":
                    cat_items = [f for f in getattr(furniture_manager, "furniture", []) if f.furniture_type in cat["building_types"]] if furniture_manager else []
                else:
                    b_types = cat["building_types"]
                    b_built = [b for b in building_manager.buildings if getattr(b, "building_type", "") in b_types]
                    b_sites = [s for s in building_manager.construction_sites if getattr(s, "building_type", "") in b_types]
                    b_demos = [d for d in demos if getattr(d, "building_type", "") in b_types or getattr(getattr(d, "building", None), "building_type", "") in b_types]
                    cat_items = b_built + b_sites + b_demos

                item_count = len(cat_items)

                card_rect = pygame.Rect(mx + 24, card_y, self.modal_w - 48, 36)
                self.building_category_btn_rects[cat_id] = card_rect

                is_hov = card_rect.collidepoint(m_pos)
                bg_col = (30, 41, 59) if is_hov else (15, 23, 42)
                border_col = (56, 189, 248) if is_hov else (51, 65, 85)

                pygame.draw.rect(surface, bg_col, card_rect, border_radius=6)
                pygame.draw.rect(surface, border_col, card_rect, width=1, border_radius=6)

                # Left color accent bar
                accent_rect = pygame.Rect(card_rect.x, card_rect.y, 5, card_rect.height)
                pygame.draw.rect(surface, cat_col, accent_rect, border_top_left_radius=6, border_bottom_left_radius=6)

                # Category title & description
                t_surf = self.font_sub.render(cat_name, True, (241, 245, 249) if is_hov else (226, 232, 240))
                surface.blit(t_surf, (card_rect.x + 16, card_rect.y + 9))

                desc_surf = self.font_body.render(f"— {cat_desc}", True, COLOR_TEXT_MUTED)
                surface.blit(desc_surf, (card_rect.x + 22 + t_surf.get_width(), card_rect.y + 10))

                # Right badges: item count and "View Structures →"
                badge_w = 80
                badge_rect = pygame.Rect(card_rect.right - badge_w - 12, card_rect.y + 7, badge_w, 22)
                badge_bg = (22, 101, 52) if item_count > 0 else (51, 65, 85)
                badge_border = (74, 222, 128) if item_count > 0 else (100, 116, 139)
                pygame.draw.rect(surface, badge_bg, badge_rect, border_radius=4)
                pygame.draw.rect(surface, badge_border, badge_rect, width=1, border_radius=4)

                lbl_text = f"{item_count} Built" if item_count != 1 else "1 Built"
                cnt_txt = self.font_badge.render(lbl_text, True, (255, 255, 255))
                surface.blit(cnt_txt, (badge_rect.centerx - cnt_txt.get_width() // 2, badge_rect.centery - cnt_txt.get_height() // 2))

                arrow_lbl = self.font_badge.render("View →", True, (56, 189, 248) if is_hov else (148, 163, 184))
                surface.blit(arrow_lbl, (badge_rect.x - arrow_lbl.get_width() - 10, card_rect.y + 11))

                card_y += 42

            # Bottom: Quick Construction Deeds Bar
            btn_y = cy + 270
            inst_txt = self.font_sub.render("Construct New Structures (Select to Place on Map):", True, (56, 189, 248))
            surface.blit(inst_txt, (mx + 24, btn_y))

            total_avail_w = self.modal_w - 48
            btn_gap = 8
            btn_w = (total_avail_w - (4 * btn_gap)) // 5

            wood_btn = pygame.Rect(mx + 24 + 0 * (btn_w + btn_gap), btn_y + 26, btn_w, 36)
            stone_btn = pygame.Rect(mx + 24 + 1 * (btn_w + btn_gap), btn_y + 26, btn_w, 36)
            well_btn = pygame.Rect(mx + 24 + 2 * (btn_w + btn_gap), btn_y + 26, btn_w, 36)
            market_btn = pygame.Rect(mx + 24 + 3 * (btn_w + btn_gap), btn_y + 26, btn_w, 36)
            toilet_btn = pygame.Rect(mx + 24 + 4 * (btn_w + btn_gap), btn_y + 26, btn_w, 36)

            self.building_select_rects["wooden_structure"] = wood_btn
            self.building_select_rects["stone_structure"] = stone_btn
            self.building_select_rects["well"] = well_btn
            self.building_select_rects["market"] = market_btn
            self.building_select_rects["toilet"] = toilet_btn

            # 1. Wooden Structure
            w_has = permit_manager.has_permit_type("wooden_structure")
            w_hov = wood_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (180, 83, 9) if w_has else (71, 85, 105), wood_btn, border_radius=6)
            pygame.draw.rect(surface, (251, 191, 36) if (w_hov and w_has) else (217, 119, 6), wood_btn, width=1, border_radius=6)
            w_lbl = self.font_btn.render("+ Wooden House", True, (255, 255, 255))
            surface.blit(w_lbl, (wood_btn.centerx - w_lbl.get_width() // 2, wood_btn.centery - w_lbl.get_height() // 2))

            # 2. Stone Structure
            s_has = permit_manager.has_permit_type("stone_structure")
            s_hov = stone_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (71, 85, 105) if s_has else (51, 65, 85), stone_btn, border_radius=6)
            pygame.draw.rect(surface, (203, 213, 225) if (s_hov and s_has) else (148, 163, 184), stone_btn, width=1, border_radius=6)
            s_lbl = self.font_btn.render("+ Stone House", True, (255, 255, 255))
            surface.blit(s_lbl, (stone_btn.centerx - s_lbl.get_width() // 2, stone_btn.centery - s_lbl.get_height() // 2))

            # 3. Water Well
            wl_has = permit_manager.has_permit_type("well")
            wl_hov = well_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (14, 116, 144) if wl_has else (71, 85, 105), well_btn, border_radius=6)
            pygame.draw.rect(surface, (56, 189, 248) if (wl_hov and wl_has) else (6, 182, 212), well_btn, width=1, border_radius=6)
            wl_lbl = self.font_btn.render("+ Water Well", True, (255, 255, 255))
            surface.blit(wl_lbl, (well_btn.centerx - wl_lbl.get_width() // 2, well_btn.centery - wl_lbl.get_height() // 2))

            # 4. Market
            m_has = permit_manager.has_permit_type("market")
            m_hov = market_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (217, 119, 6) if m_has else (71, 85, 105), market_btn, border_radius=6)
            pygame.draw.rect(surface, (253, 230, 138) if (m_hov and m_has) else (245, 158, 11), market_btn, width=1, border_radius=6)
            m_lbl = self.font_btn.render("+ Market Stall", True, (255, 255, 255))
            surface.blit(m_lbl, (market_btn.centerx - m_lbl.get_width() // 2, market_btn.centery - m_lbl.get_height() // 2))

            # 5. Toilet
            tl_has = permit_manager.has_permit_type("toilet")
            tl_hov = toilet_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (139, 90, 43) if tl_has else (71, 85, 105), toilet_btn, border_radius=6)
            pygame.draw.rect(surface, (202, 138, 4) if (tl_hov and tl_has) else (101, 67, 33), toilet_btn, width=1, border_radius=6)
            tl_lbl = self.font_btn.render("+ Toilet", True, (255, 255, 255))
            surface.blit(tl_lbl, (toilet_btn.centerx - tl_lbl.get_width() // 2, toilet_btn.centery - tl_lbl.get_height() // 2))

        else:
            # -----------------------------------------------------------------
            # SCREEN 2: Category Details & Filtered Structures View
            # -----------------------------------------------------------------
            current_cat = next((c for c in categories if c["id"] == self.selected_building_category), None)
            if not current_cat:
                self.selected_building_category = None
                return

            cat_name = current_cat["name"]
            cat_desc = current_cat["desc"]
            cat_types = current_cat["building_types"]
            demos = getattr(building_manager, "demolition_sites", [])

            if current_cat.get("kind") == "furniture":
                cat_items = [f for f in getattr(furniture_manager, "furniture", []) if f.furniture_type in cat_types] if furniture_manager else []
                b_built, b_sites, b_demos = [], [], []
            else:
                b_built = [b for b in building_manager.buildings if getattr(b, "building_type", "") in cat_types]
                b_sites = [s for s in building_manager.construction_sites if getattr(s, "building_type", "") in cat_types]
                b_demos = [d for d in demos if getattr(d, "building_type", "") in cat_types or getattr(getattr(d, "building", None), "building_type", "") in cat_types]
                cat_items = b_built + b_sites + b_demos

            # 1. Back button to return to categories view
            back_btn = pygame.Rect(mx + 24, cy, 160, 26)
            self.building_category_back_btn_rect = back_btn
            b_hov = back_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (30, 58, 138) if b_hov else (30, 41, 59), back_btn, border_radius=4)
            pygame.draw.rect(surface, (96, 165, 250) if b_hov else (71, 85, 105), back_btn, width=1, border_radius=4)
            b_lbl = self.font_badge.render("← Back to Categories", True, (255, 255, 255))
            surface.blit(b_lbl, (back_btn.centerx - b_lbl.get_width() // 2, back_btn.centery - b_lbl.get_height() // 2))

            # 2. Section Title
            b_title = self.font_sub.render(f"Category: {cat_name} ({len(cat_items)} structures)", True, COLOR_TEXT_TITLE)
            surface.blit(b_title, (back_btn.right + 14, cy + 3))

            # 3. Subtitle / Description
            sub_txt = self.font_body.render(f"• {cat_desc}", True, COLOR_TEXT_MUTED)
            surface.blit(sub_txt, (mx + 28, cy + 32))

            y_cur = cy + 54

            # 4. Filtered List or Empty State
            if not cat_items:
                empty_box = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 54)
                pygame.draw.rect(surface, (15, 23, 42, 200), empty_box, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), empty_box, width=1, border_radius=6)
                msg1 = f"• No structures built under '{cat_name}' yet."
                msg2 = "Click the button below to construct or place a new structure for this category on the estate map."
                surface.blit(self.font_body.render(msg1, True, (203, 213, 225)), (empty_box.x + 16, empty_box.y + 10))
                surface.blit(self.font_body.render(msg2, True, COLOR_TEXT_MUTED), (empty_box.x + 16, empty_box.y + 30))
                y_cur = empty_box.bottom + 16
            else:
                if current_cat.get("kind") == "furniture":
                    for f in cat_items:
                        owner_fam = villager_manager.get_family_by_id(f.family_id) if (villager_manager and f.family_id) else None
                        fam_str = f"The {owner_fam.surname} Family" if owner_fam else "Town / Unassigned"

                        row_rect = pygame.Rect(mx + 30, y_cur - 2, self.modal_w - 60, 24)
                        txt = f"• {f.name} at ({f.grid_x}, {f.grid_y}) — Owner: {fam_str} | Status: [{f.status}]"
                        surface.blit(self.font_body.render(txt, True, COLOR_TEXT_MAIN), (mx + 36, y_cur + 2))

                        # Move button
                        mv_btn = pygame.Rect(row_rect.right - 180, y_cur - 1, 84, 22)
                        self.furniture_move_btn_rects[f] = mv_btn
                        mv_hov = mv_btn.collidepoint(m_pos)
                        pygame.draw.rect(surface, (37, 99, 235) if mv_hov else (29, 78, 216), mv_btn, border_radius=4)
                        m_lbl = self.font_badge.render("Move", True, (255, 255, 255))
                        surface.blit(m_lbl, (mv_btn.centerx - m_lbl.get_width() // 2, mv_btn.centery - m_lbl.get_height() // 2))

                        # Destroy button
                        dest_btn = pygame.Rect(row_rect.right - 90, y_cur - 1, 86, 22)
                        self.furniture_destroy_btn_rects[f] = dest_btn
                        dest_hov = dest_btn.collidepoint(m_pos)
                        pygame.draw.rect(surface, (220, 38, 38) if dest_hov else (153, 27, 27), dest_btn, border_radius=4)
                        d_lbl = self.font_badge.render("Destroy", True, (255, 255, 255))
                        surface.blit(d_lbl, (dest_btn.x + (dest_btn.w - d_lbl.get_width()) // 2, dest_btn.y + 4))

                        y_cur += 26
                else:
                    # Demolition Sites
                    for d in b_demos:
                        pct = int((d.progress / d.duration) * 100)
                        txt = f"[Demolishing] {d.name} ({pct}% | Salvaging +{d.refund_wood}W, +{d.refund_stone}S)"
                        surface.blit(self.font_body.render(txt, True, (239, 68, 68)), (mx + 36, y_cur + 2))

                        c_btn = pygame.Rect(mx + self.modal_w - 120, y_cur - 1, 80, 22)
                        self.cancel_demolition_btn_rects[d] = c_btn
                        c_hov = c_btn.collidepoint(m_pos)
                        pygame.draw.rect(surface, (220, 38, 38) if c_hov else (153, 27, 27), c_btn, border_radius=4)
                        c_lbl = self.font_badge.render("Cancel", True, (255, 255, 255))
                        surface.blit(c_lbl, (c_btn.centerx - c_lbl.get_width() // 2, c_btn.centery - c_lbl.get_height() // 2))

                        y_cur += 26

                    # Construction Sites
                    for s in b_sites:
                        txt = f"[Building] {s.name} ({s.total_delivered()}/{s.total_required()} Materials)"
                        surface.blit(self.font_body.render(txt, True, (245, 158, 11)), (mx + 36, y_cur + 2))

                        c_btn = pygame.Rect(mx + self.modal_w - 120, y_cur - 1, 80, 22)
                        self.cancel_construction_btn_rects[s] = c_btn
                        c_hov = c_btn.collidepoint(m_pos)
                        pygame.draw.rect(surface, (217, 119, 6) if c_hov else (180, 83, 9), c_btn, border_radius=4)
                        c_lbl = self.font_badge.render("Cancel", True, (255, 255, 255))
                        surface.blit(c_lbl, (c_btn.centerx - c_lbl.get_width() // 2, c_btn.centery - c_lbl.get_height() // 2))

                        y_cur += 26

                    # Completed Buildings
                    for b in b_built:
                        is_focused = (self.selected_building_inspect == b)
                        door_side_str = b.door_side.capitalize() if hasattr(b, "door_side") and b.door_side else "Standard"
                        b_cfg = BUILDING_TYPES.get(b.building_type, BUILDING_TYPES["wooden_structure"])
                        cost_w = b_cfg.get("cost_wood", COST_PER_BLOCK_WOOD)
                        cost_s = b_cfg.get("cost_stone", COST_PER_BLOCK_STONE)
                        ref_w = int(len(b.tiles) * cost_w * DEMOLITION_REFUND_RATIO)
                        ref_s = int(len(b.tiles) * cost_s * DEMOLITION_REFUND_RATIO)

                        row_rect = pygame.Rect(mx + 30, y_cur - 2, self.modal_w - 60, 24)
                        if is_focused:
                            pygame.draw.rect(surface, (30, 58, 138, 120), row_rect, border_radius=4)
                            pygame.draw.rect(surface, (59, 130, 246), row_rect, width=1, border_radius=4)

                        txt = f"{b.name} ({len(b.tiles)} tiles | Door: {door_side_str}) — Refund: +{ref_w}W, +{ref_s}S"
                        surface.blit(self.font_body.render(txt, True, (255, 255, 255) if is_focused else COLOR_TEXT_MAIN), (mx + 36, y_cur + 2))

                        # Contextual Button: Jump to Household if building is occupied by a family
                        tenant_fam = None
                        if villager_manager:
                            for fam in getattr(villager_manager, "families", []):
                                p_fam = next((p for p in getattr(permit_manager, "permits", []) if p.id == fam.assigned_permit_id), None) if (fam.assigned_permit_id and permit_manager) else None
                                if p_fam and any(tile in p_fam.tiles for tile in b.tiles):
                                    tenant_fam = fam
                                    break
                        if tenant_fam:
                            fam_b_btn = pygame.Rect(row_rect.right - 276, y_cur - 1, 84, 22)
                            self.building_household_btn_rects[b] = (fam_b_btn, tenant_fam.id)
                            fh_hov = fam_b_btn.collidepoint(m_pos)
                            pygame.draw.rect(surface, (14, 116, 144) if fh_hov else (15, 23, 42), fam_b_btn, border_radius=4)
                            pygame.draw.rect(surface, (56, 189, 248), fam_b_btn, width=1, border_radius=4)
                            fh_lbl = self.font_badge.render("Household", True, (255, 255, 255))
                            surface.blit(fh_lbl, (fam_b_btn.x + (fam_b_btn.w - fh_lbl.get_width()) // 2, fam_b_btn.y + 4))

                        # Market Profile Button
                        if getattr(b, "building_type", "") == "market":
                            prof_btn = pygame.Rect(row_rect.right - 180, y_cur - 1, 84, 22)
                            self.market_profile_btn_rects[b] = prof_btn
                            prof_hover = prof_btn.collidepoint(m_pos)
                            pygame.draw.rect(surface, (245, 158, 11) if prof_hover else (180, 83, 9), prof_btn, border_radius=4)
                            p_lbl = self.font_badge.render("Profile", True, (255, 255, 255))
                            surface.blit(p_lbl, (prof_btn.x + (prof_btn.w - p_lbl.get_width()) // 2, prof_btn.y + 4))

                        # Destroy Button
                        dest_btn = pygame.Rect(row_rect.right - 90, y_cur - 1, 86, 22)
                        self.destroy_building_btn_rects[b] = dest_btn
                        dest_hover = dest_btn.collidepoint(m_pos)
                        pygame.draw.rect(surface, (220, 38, 38) if dest_hover else (153, 27, 27), dest_btn, border_radius=4)
                        d_lbl = self.font_badge.render("Destroy", True, (255, 255, 255))
                        surface.blit(d_lbl, (dest_btn.x + (dest_btn.w - d_lbl.get_width()) // 2, dest_btn.y + 4))

                        y_cur += 26

            # 5. Bottom Action: Construct Button(s) for this specific category
            btn_y = max(y_cur + 20, cy + 220)
            inst_txt = self.font_sub.render(f"Construct / Place {cat_name} (Select to Place on Map):", True, (56, 189, 248))
            surface.blit(inst_txt, (mx + 24, btn_y))

            if current_cat.get("kind") == "furniture":
                avail_w = self.modal_w - 48
                f_keys = list(FURNITURE_TYPES.keys())
                f_btn_w = (avail_w - ((len(f_keys) - 1) * 8)) // max(1, len(f_keys))
                for idx, f_id in enumerate(f_keys):
                    f_cfg = FURNITURE_TYPES[f_id]
                    can_afford = (resources.get("Wood", 0) >= f_cfg.get("cost_wood", 0))
                    f_btn = pygame.Rect(mx + 24 + idx * (f_btn_w + 8), btn_y + 26, f_btn_w, 36)
                    self.furniture_select_rects[f_id] = f_btn
                    hov = f_btn.collidepoint(m_pos)
                    b_col = (16, 185, 129) if can_afford else (71, 85, 105)
                    pygame.draw.rect(surface, (34, 197, 94) if (hov and can_afford) else b_col, f_btn, border_radius=6)
                    lbl_txt = f"+ Place {f_cfg['name']} ({f_cfg['cost_wood']} Wood)"
                    lbl = self.font_btn.render(lbl_txt, True, (255, 255, 255))
                    surface.blit(lbl, (f_btn.centerx - lbl.get_width() // 2, f_btn.centery - lbl.get_height() // 2))
            else:
                avail_w = self.modal_w - 48
                b_keys = [b for b in cat_types if b in ("wooden_structure", "stone_structure", "well", "market", "toilet")]
                if not b_keys:
                    b_keys = list(cat_types)
                b_btn_w = (avail_w - ((len(b_keys) - 1) * 8)) // max(1, len(b_keys))
                for idx, b_id in enumerate(b_keys):
                    b_cfg = BUILDING_TYPES.get(b_id, {})
                    has_permit = permit_manager.has_permit_type(b_id)
                    b_btn = pygame.Rect(mx + 24 + idx * (b_btn_w + 8), btn_y + 26, b_btn_w, 36)
                    self.building_select_rects[b_id] = b_btn
                    hov = b_btn.collidepoint(m_pos)
                    b_col = (16, 185, 129) if has_permit else (71, 85, 105)
                    pygame.draw.rect(surface, (34, 197, 94) if (hov and has_permit) else b_col, b_btn, border_radius=6)
                    lbl_txt = f"+ {b_cfg.get('name', b_id.replace('_', ' ').title())}"
                    lbl = self.font_btn.render(lbl_txt, True, (255, 255, 255))
                    surface.blit(lbl, (b_btn.centerx - lbl.get_width() // 2, b_btn.centery - lbl.get_height() // 2))

    def _draw_permit_row(self, surface, p, mx, y_cur, empty_areas):
        """Helper to render a single permit row with all interactive controls (Agent 2)"""
        is_empty = p in empty_areas
        is_focused = (self.selected_permit_inspect_id == p.id)

        row_rect = pygame.Rect(mx + 30, y_cur - 2, self.modal_w - 60, 24)
        if is_focused:
            pygame.draw.rect(surface, (30, 58, 138, 140), row_rect, border_radius=4)
            pygame.draw.rect(surface, (59, 130, 246), row_rect, width=1, border_radius=4)

        status_str = "Empty" if is_empty else "Occupied"
        col = (245, 158, 11) if is_empty else (16, 185, 129)
        prefix = "[Private] " if p.permit_type == "landlord_private" else ""

        if p.permit_type == "farm":
            if getattr(p, "crop", None):
                w_tag = "Watered" if getattr(p, "watered_today", False) else "Dry"
                crop_str = f"{p.crop} (Day {getattr(p, 'growth_days', 0.0):.0f}/10 | {w_tag})"
            else:
                crop_str = "Unplanted"
            col = (34, 197, 94)
            txt = f"• {p.name} [{len(p.tiles)}t Farm] — {crop_str}"
            surface.blit(self.font_body.render(txt, True, col), (mx + 36, y_cur + 2))

            # Right side buttons
            right_cursor = row_rect.right

            # Delete button if empty
            if is_empty:
                del_btn = pygame.Rect(right_cursor - 84, y_cur - 1, 82, 22)
                self.delete_permit_btn_rects[p.id] = del_btn
                del_hover = del_btn.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (220, 38, 38) if del_hover else (153, 27, 27), del_btn, border_radius=4)
                del_lbl = self.font_badge.render("Delete", True, (255, 255, 255))
                surface.blit(del_lbl, (del_btn.x + (del_btn.w - del_lbl.get_width()) // 2, del_btn.y + 4))
                right_cursor -= 88

            # Edit Lot button
            edit_btn = pygame.Rect(right_cursor - 64, y_cur - 1, 60, 22)
            self.edit_permit_btn_rects[p.id] = edit_btn
            edit_hov = edit_btn.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (202, 138, 4) if edit_hov else (161, 98, 7), edit_btn, border_radius=4)
            pygame.draw.rect(surface, (250, 204, 21), edit_btn, width=1, border_radius=4)
            edit_lbl = self.font_badge.render("Edit", True, (255, 255, 255))
            surface.blit(edit_lbl, (edit_btn.x + (edit_btn.w - edit_lbl.get_width()) // 2, edit_btn.y + 4))

            # Contextual Navigation: Household button if lot is assigned to a family
            if getattr(p, "assigned_family_id", None):
                fam_btn = pygame.Rect(edit_btn.left - 88, y_cur - 1, 82, 22)
                self.permit_household_btn_rects[p.id] = (fam_btn, p.assigned_family_id)
                f_hov = fam_btn.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (14, 116, 144) if f_hov else (15, 23, 42), fam_btn, border_radius=4)
                pygame.draw.rect(surface, (56, 189, 248), fam_btn, width=1, border_radius=4)
                f_lbl = self.font_badge.render("Household", True, (255, 255, 255))
                surface.blit(f_lbl, (fam_btn.x + (fam_btn.w - f_lbl.get_width()) // 2, fam_btn.y + 4))
            right_cursor -= 68

            # Plant button for Farm permit
            plant_btn = pygame.Rect(right_cursor - 82, y_cur - 1, 78, 22)
            self.open_plant_btn_rects[p.id] = plant_btn
            plant_hover = plant_btn.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (22, 101, 52) if plant_hover else (20, 83, 45), plant_btn, border_radius=4)
            pygame.draw.rect(surface, (74, 222, 128), plant_btn, width=1, border_radius=4)
            p_label = f"{p.crop}" if getattr(p, "crop", None) else "Plant"
            p_surf = self.font_badge.render(p_label, True, (255, 255, 255))
            surface.blit(p_surf, (plant_btn.x + (plant_btn.w - p_surf.get_width()) // 2, plant_btn.y + 4))
            right_cursor -= 86

            # Worker Controls: [⚡ Auto] [+] {count/max} [-]
            auto_btn = pygame.Rect(right_cursor - 28, y_cur - 1, 26, 22)
            self.worker_auto_btn_rects[p.id] = auto_btn
            a_hov = auto_btn.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (16, 185, 129) if a_hov else (5, 150, 105), auto_btn, border_radius=3)
            a_txt = self.font_badge.render("Auto", True, (255, 255, 255))
            surface.blit(a_txt, (auto_btn.x + 6, auto_btn.y + 4))
            right_cursor -= 32

            inc_btn = pygame.Rect(right_cursor - 20, y_cur - 1, 18, 22)
            self.worker_inc_btn_rects[p.id] = inc_btn
            inc_hov = inc_btn.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (37, 99, 235) if inc_hov else (30, 58, 138), inc_btn, border_radius=3)
            surface.blit(self.font_badge.render("+", True, (255, 255, 255)), (inc_btn.x + 5, inc_btn.y + 3))
            right_cursor -= 24

            w_count = len(getattr(p, 'assigned_workers', set()))
            w_max = getattr(p, 'max_workers', 2)
            cnt_str = f"{w_count}/{w_max} Workers"
            cnt_surf = self.font_badge.render(cnt_str, True, (241, 245, 249))
            surface.blit(cnt_surf, (right_cursor - cnt_surf.get_width() - 4, y_cur + 3))
            right_cursor -= (cnt_surf.get_width() + 8)

            dec_btn = pygame.Rect(right_cursor - 20, y_cur - 1, 18, 22)
            self.worker_dec_btn_rects[p.id] = dec_btn
            dec_hov = dec_btn.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (71, 85, 105) if dec_hov else (51, 65, 85), dec_btn, border_radius=3)
            surface.blit(self.font_badge.render("-", True, (255, 255, 255)), (dec_btn.x + 6, dec_btn.y + 3))

        else:
            txt = f"• {prefix}{p.name} [{len(p.tiles)} tiles {p.permit_type.capitalize()}] — {status_str}"
            surface.blit(self.font_body.render(txt, True, col), (mx + 36, y_cur + 2))

            right_cursor = row_rect.right
            # Delete button for empty permits
            if is_empty:
                del_btn = pygame.Rect(right_cursor - 84, y_cur - 1, 82, 22)
                self.delete_permit_btn_rects[p.id] = del_btn
                del_hover = del_btn.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (220, 38, 38) if del_hover else (153, 27, 27), del_btn, border_radius=4)
                del_lbl = self.font_badge.render("Delete", True, (255, 255, 255))
                surface.blit(del_lbl, (del_btn.x + (del_btn.w - del_lbl.get_width()) // 2, del_btn.y + 4))
                right_cursor -= 88

            # Edit Lot button
            edit_btn = pygame.Rect(right_cursor - 64, y_cur - 1, 60, 22)
            self.edit_permit_btn_rects[p.id] = edit_btn
            edit_hov = edit_btn.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, (202, 138, 4) if edit_hov else (161, 98, 7), edit_btn, border_radius=4)
            pygame.draw.rect(surface, (250, 204, 21), edit_btn, width=1, border_radius=4)
            edit_lbl = self.font_badge.render("Edit", True, (255, 255, 255))
            surface.blit(edit_lbl, (edit_btn.x + (edit_btn.w - edit_lbl.get_width()) // 2, edit_btn.y + 4))

            # Contextual Navigation: Household button if lot is assigned to a family
            if getattr(p, "assigned_family_id", None):
                fam_btn = pygame.Rect(edit_btn.left - 88, y_cur - 1, 82, 22)
                self.permit_household_btn_rects[p.id] = (fam_btn, p.assigned_family_id)
                f_hov = fam_btn.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, (14, 116, 144) if f_hov else (15, 23, 42), fam_btn, border_radius=4)
                pygame.draw.rect(surface, (56, 189, 248), fam_btn, width=1, border_radius=4)
                f_lbl = self.font_badge.render("Household", True, (255, 255, 255))
                surface.blit(f_lbl, (fam_btn.x + (fam_btn.w - f_lbl.get_width()) // 2, fam_btn.y + 4))

    def _draw_permit_tab(self, surface, mx, cy, permit_manager, building_manager):
        """
        Category-based Permit Organization UI (Agent 2)
        Screen 1: Lists dynamically discovered permit categories with lot count badges.
        Screen 2: When category is selected, displays only permits belonging to that category with Back button & empty state.
        Zero hardcoded categories or permit lists.
        """
        categories = get_permit_categories()
        empty_areas, occupied_areas = permit_manager.get_permits_status(building_manager)
        m_pos = pygame.mouse.get_pos()

        self.permit_category_back_btn_rect = None
        self.permit_category_btn_rects = {}
        self.permit_household_btn_rects.clear()
        self.delete_permit_btn_rects = {}
        self.edit_permit_btn_rects = {}
        self.open_plant_btn_rects = {}
        self.worker_dec_btn_rects = {}
        self.worker_inc_btn_rects = {}
        self.worker_auto_btn_rects = {}
        self.permit_btn_rects = {}

        if self.selected_permit_category is None:
            # -----------------------------------------------------------------
            # SCREEN 1: Permit Categories Selection Screen
            # -----------------------------------------------------------------
            p_title = self.font_sub.render(f" Landlord Permit Categories ({len(categories)} categories, {len(permit_manager.permits)} total lots):", True, COLOR_TEXT_TITLE)
            surface.blit(p_title, (mx + 24, cy))

            sub_txt = self.font_body.render("Select a category below to inspect and manage designated lots, or quick-issue a permit:", True, COLOR_TEXT_MUTED)
            surface.blit(sub_txt, (mx + 28, cy + 22))

            card_y = cy + 44
            for cat in categories:
                cat_id = cat["id"]
                cat_name = cat["name"]
                cat_desc = cat["desc"]
                cat_col = cat.get("color", (59, 130, 246))
                cat_permits = [p for p in permit_manager.permits if p.permit_type in cat["permit_types"]]
                lot_count = len(cat_permits)

                card_rect = pygame.Rect(mx + 24, card_y, self.modal_w - 48, 32)
                self.permit_category_btn_rects[cat_id] = card_rect

                is_hov = card_rect.collidepoint(m_pos)
                bg_col = (30, 41, 59) if is_hov else (15, 23, 42)
                border_col = (56, 189, 248) if is_hov else (51, 65, 85)

                pygame.draw.rect(surface, bg_col, card_rect, border_radius=6)
                pygame.draw.rect(surface, border_col, card_rect, width=1, border_radius=6)

                # Left color accent bar
                accent_rect = pygame.Rect(card_rect.x, card_rect.y, 5, card_rect.height)
                pygame.draw.rect(surface, cat_col, accent_rect, border_top_left_radius=6, border_bottom_left_radius=6)

                # Category title & description
                t_surf = self.font_sub.render(cat_name, True, (241, 245, 249) if is_hov else (226, 232, 240))
                surface.blit(t_surf, (card_rect.x + 16, card_rect.y + 7))

                desc_surf = self.font_body.render(f"— {cat_desc}", True, COLOR_TEXT_MUTED)
                surface.blit(desc_surf, (card_rect.x + 22 + t_surf.get_width(), card_rect.y + 8))

                # Right badges: Lot count and "View Lots →"
                badge_w = 80
                badge_rect = pygame.Rect(card_rect.right - badge_w - 12, card_rect.y + 5, badge_w, 22)
                badge_bg = (22, 101, 52) if lot_count > 0 else (51, 65, 85)
                badge_border = (74, 222, 128) if lot_count > 0 else (100, 116, 139)
                pygame.draw.rect(surface, badge_bg, badge_rect, border_radius=4)
                pygame.draw.rect(surface, badge_border, badge_rect, width=1, border_radius=4)

                lbl_text = f"{lot_count} Lots" if lot_count != 1 else "1 Lot"
                cnt_txt = self.font_badge.render(lbl_text, True, (255, 255, 255))
                surface.blit(cnt_txt, (badge_rect.centerx - cnt_txt.get_width() // 2, badge_rect.centery - cnt_txt.get_height() // 2))

                arrow_lbl = self.font_badge.render("View →", True, (56, 189, 248) if is_hov else (148, 163, 184))
                surface.blit(arrow_lbl, (badge_rect.x - arrow_lbl.get_width() - 10, card_rect.y + 9))

                card_y += 36

            # Bottom: Quick Issue New Landlord Permits
            btn_y = max(cy + 250, card_y + 4)
            inst_txt = self.font_sub.render("Issue New Landlord Permits (Select, then Click & Drag on Map to Size):", True, (56, 189, 248))
            surface.blit(inst_txt, (mx + 24, btn_y))

            total_avail_w = self.modal_w - 48
            btn_gap = 8

            # Row 1 (4 buttons: Housing, Storage, Market, Farm)
            w4 = (total_avail_w - (3 * btn_gap)) // 4
            housing_btn = pygame.Rect(mx + 24 + 0 * (w4 + btn_gap), btn_y + 24, w4, 30)
            storage_btn = pygame.Rect(mx + 24 + 1 * (w4 + btn_gap), btn_y + 24, w4, 30)
            market_btn = pygame.Rect(mx + 24 + 2 * (w4 + btn_gap), btn_y + 24, w4, 30)
            farm_btn = pygame.Rect(mx + 24 + 3 * (w4 + btn_gap), btn_y + 24, w4, 30)

            # Row 2 (3 buttons: Church, Cemetery, Private Area)
            w3 = (total_avail_w - (2 * btn_gap)) // 3
            church_btn = pygame.Rect(mx + 24 + 0 * (w3 + btn_gap), btn_y + 58, w3, 30)
            cemetery_btn = pygame.Rect(mx + 24 + 1 * (w3 + btn_gap), btn_y + 58, w3, 30)
            private_btn = pygame.Rect(mx + 24 + 2 * (w3 + btn_gap), btn_y + 58, w3, 30)

            self.permit_btn_rects["housing"] = housing_btn
            self.permit_btn_rects["storage"] = storage_btn
            self.permit_btn_rects["market"] = market_btn
            self.permit_btn_rects["farm"] = farm_btn
            self.permit_btn_rects["church"] = church_btn
            self.permit_btn_rects["cemetery"] = cemetery_btn
            self.permit_btn_rects["landlord_private"] = private_btn

            # 1. Housing Permit Button
            h_hov = housing_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (59, 130, 246) if h_hov else (37, 99, 235), housing_btn, border_radius=6)
            pygame.draw.rect(surface, (147, 197, 253) if h_hov else (96, 165, 250), housing_btn, width=1, border_radius=6)
            h_lbl = self.font_btn.render("+ Housing Permit", True, (255, 255, 255))
            surface.blit(h_lbl, (housing_btn.centerx - h_lbl.get_width() // 2, housing_btn.centery - h_lbl.get_height() // 2))

            # 2. Storage Permit Button
            s_hov = storage_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (234, 179, 8) if s_hov else (202, 138, 4), storage_btn, border_radius=6)
            pygame.draw.rect(surface, (253, 224, 71) if s_hov else (250, 204, 21), storage_btn, width=1, border_radius=6)
            s_lbl = self.font_btn.render("+ Storage Permit", True, (255, 255, 255))
            surface.blit(s_lbl, (storage_btn.centerx - s_lbl.get_width() // 2, storage_btn.centery - s_lbl.get_height() // 2))

            # 3. Market Permit Button
            m_hov = market_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (245, 158, 11) if m_hov else (217, 119, 6), market_btn, border_radius=6)
            pygame.draw.rect(surface, (253, 230, 138) if m_hov else (251, 191, 36), market_btn, width=1, border_radius=6)
            m_lbl = self.font_btn.render("+ Market Permit", True, (255, 255, 255))
            surface.blit(m_lbl, (market_btn.centerx - m_lbl.get_width() // 2, market_btn.centery - m_lbl.get_height() // 2))

            # 4. Farm Permit Button
            f_hov = farm_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (34, 197, 94) if f_hov else (22, 101, 52), farm_btn, border_radius=6)
            pygame.draw.rect(surface, (134, 239, 172) if f_hov else (74, 222, 128), farm_btn, width=1, border_radius=6)
            f_lbl = self.font_btn.render("+ Farm Permit", True, (255, 255, 255))
            surface.blit(f_lbl, (farm_btn.centerx - f_lbl.get_width() // 2, farm_btn.centery - f_lbl.get_height() // 2))

            # 5. Church Permit Button
            ch_hov = church_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (168, 85, 247) if ch_hov else (147, 51, 234), church_btn, border_radius=6)
            pygame.draw.rect(surface, (216, 180, 254) if ch_hov else (192, 132, 252), church_btn, width=1, border_radius=6)
            ch_lbl = self.font_btn.render("+ Church Permit", True, (255, 255, 255))
            surface.blit(ch_lbl, (church_btn.centerx - ch_lbl.get_width() // 2, church_btn.centery - ch_lbl.get_height() // 2))

            # 6. Cemetery Permit Button
            cm_hov = cemetery_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (100, 116, 139) if cm_hov else (71, 85, 105), cemetery_btn, border_radius=6)
            pygame.draw.rect(surface, (203, 213, 225) if cm_hov else (148, 163, 184), cemetery_btn, width=1, border_radius=6)
            cm_lbl = self.font_btn.render("+ Cemetery Permit", True, (255, 255, 255))
            surface.blit(cm_lbl, (cemetery_btn.centerx - cm_lbl.get_width() // 2, cemetery_btn.centery - cm_lbl.get_height() // 2))

            # 7. Landlord Private Area Button
            p_hov = private_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (126, 34, 206) if p_hov else (88, 28, 135), private_btn, border_radius=6)
            pygame.draw.rect(surface, (250, 204, 21) if p_hov else (234, 179, 8), private_btn, width=1, border_radius=6)
            p_lbl = self.font_btn.render("+ Private Area", True, (255, 255, 255))
            surface.blit(p_lbl, (private_btn.centerx - p_lbl.get_width() // 2, private_btn.centery - p_lbl.get_height() // 2))

        else:
            # -----------------------------------------------------------------
            # SCREEN 2: Category Details & Filtered Permits View
            # -----------------------------------------------------------------
            current_cat = next((c for c in categories if c["id"] == self.selected_permit_category), None)
            if not current_cat:
                self.selected_permit_category = None
                return

            cat_name = current_cat["name"]
            cat_desc = current_cat["desc"]
            cat_types = current_cat["permit_types"]
            category_permits = [p for p in permit_manager.permits if p.permit_type in cat_types]

            # 1. Back button to return to category selection screen
            back_btn = pygame.Rect(mx + 24, cy, 160, 26)
            self.permit_category_back_btn_rect = back_btn
            b_hov = back_btn.collidepoint(m_pos)
            pygame.draw.rect(surface, (30, 58, 138) if b_hov else (30, 41, 59), back_btn, border_radius=4)
            pygame.draw.rect(surface, (96, 165, 250) if b_hov else (71, 85, 105), back_btn, width=1, border_radius=4)
            b_lbl = self.font_badge.render("← Back to Categories", True, (255, 255, 255))
            surface.blit(b_lbl, (back_btn.centerx - b_lbl.get_width() // 2, back_btn.centery - b_lbl.get_height() // 2))

            # 2. Section Title (Displays Category Name as required)
            p_title = self.font_sub.render(f"Category: {cat_name} ({len(category_permits)} lots)", True, COLOR_TEXT_TITLE)
            surface.blit(p_title, (back_btn.right + 14, cy + 3))

            # 3. Subtitle / Description
            sub_txt = self.font_body.render(f"• {cat_desc}", True, COLOR_TEXT_MUTED)
            surface.blit(sub_txt, (mx + 28, cy + 32))

            y_cur = cy + 54

            # 4. Filtered Permits List or Empty State
            if not category_permits:
                empty_box = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 54)
                pygame.draw.rect(surface, (15, 23, 42, 200), empty_box, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), empty_box, width=1, border_radius=6)
                msg1 = f"• No active permits issued under '{cat_name}' yet."
                msg2 = "Click the button below to issue and drag a new lot for this category on the estate map."
                surface.blit(self.font_body.render(msg1, True, (203, 213, 225)), (empty_box.x + 16, empty_box.y + 10))
                surface.blit(self.font_body.render(msg2, True, COLOR_TEXT_MUTED), (empty_box.x + 16, empty_box.y + 30))
                y_cur = empty_box.bottom + 16
            else:
                for p in category_permits:
                    self._draw_permit_row(surface, p, mx, y_cur, empty_areas)
                    y_cur += 26

            # 5. Bottom Action: Issue New Permit for this specific category
            btn_y = max(y_cur + 20, cy + 220)
            inst_txt = self.font_sub.render(f"Issue New {cat_name} (Select, then Click & Drag on Map to Size):", True, (56, 189, 248))
            surface.blit(inst_txt, (mx + 24, btn_y))

            avail_w = self.modal_w - 48
            k = len(cat_types)
            c_btn_w = min(180, (avail_w - ((k - 1) * 8)) // max(1, k))
            for idx, p_type in enumerate(cat_types):
                p_cfg = PERMIT_TYPES.get(p_type, {})
                p_btn = pygame.Rect(mx + 24 + idx * (c_btn_w + 8), btn_y + 26, c_btn_w, 36)
                self.permit_btn_rects[p_type] = p_btn
                hov = p_btn.collidepoint(m_pos)
                raw_col = p_cfg.get("color", (59, 130, 246, 60))
                rgb_col = (raw_col[0], raw_col[1], raw_col[2])
                brd_col = p_cfg.get("border_color", (96, 165, 250))
                pygame.draw.rect(surface, brd_col if hov else rgb_col, p_btn, border_radius=6)
                pygame.draw.rect(surface, (255, 255, 255) if hov else brd_col, p_btn, width=1, border_radius=6)
                b_text = f"+ {p_cfg.get('name', p_type.capitalize())}"
                lbl = self.font_btn.render(b_text, True, (255, 255, 255))
                surface.blit(lbl, (p_btn.centerx - lbl.get_width() // 2, p_btn.centery - lbl.get_height() // 2))

        # Crop Selection Popup Dialog
        self.crop_select_btn_rects = {}
        if self.crop_picker_permit_id:
            target_p = next((p for p in permit_manager.permits if p.id == self.crop_picker_permit_id), None)
            pop_w = 480
            pop_h = 240
            pop_x = mx + (self.modal_w - pop_w) // 2
            pop_y = cy + 10
            self.crop_picker_bg_rect = pygame.Rect(pop_x, pop_y, pop_w, pop_h)

            # Dim backdrop around popup inside modal
            dim_pop = pygame.Surface((pop_w, pop_h), pygame.SRCALPHA)
            pygame.draw.rect(dim_pop, (15, 23, 42, 250), (0, 0, pop_w, pop_h), border_radius=10)
            pygame.draw.rect(dim_pop, (74, 222, 128), (0, 0, pop_w, pop_h), width=2, border_radius=10)
            surface.blit(dim_pop, (pop_x, pop_y))

            p_title_str = target_p.name if target_p else "Farm Lot"
            head_txt = self.font_sub.render(f"Select Crop for {p_title_str}:", True, (74, 222, 128))
            surface.blit(head_txt, (pop_x + 16, pop_y + 14))

            # Close button
            self.close_crop_picker_btn_rect = pygame.Rect(pop_x + pop_w - 30, pop_y + 12, 18, 18)
            pygame.draw.rect(surface, (220, 38, 38), self.close_crop_picker_btn_rect, border_radius=3)
            x_txt = self.font_badge.render("X", True, (255, 255, 255))
            surface.blit(x_txt, (self.close_crop_picker_btn_rect.x + 4, self.close_crop_picker_btn_rect.y + 2))

            crop_y = pop_y + 44
            for c_id, c_cfg in CROP_TYPES.items():
                is_wip = c_cfg.get("wip", False)
                row_r = pygame.Rect(pop_x + 16, crop_y, pop_w - 32, 40)
                pygame.draw.rect(surface, (30, 41, 59), row_r, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), row_r, width=1, border_radius=6)

                # Icon & Name
                c_title = self.font_sub.render(f"{c_cfg['icon']} {c_cfg['name']}", True, (255, 255, 255) if not is_wip else COLOR_TEXT_MUTED)
                surface.blit(c_title, (row_r.x + 10, row_r.y + 4))

                # Desc
                c_desc = self.font_badge.render(c_cfg['desc'], True, (148, 163, 184) if not is_wip else (100, 116, 139))
                surface.blit(c_desc, (row_r.x + 10, row_r.y + 22))

                # Button
                btn_r = pygame.Rect(row_r.right - 100, row_r.y + 8, 90, 24)
                self.crop_select_btn_rects[c_id] = btn_r

                if is_wip:
                    pygame.draw.rect(surface, (51, 65, 85), btn_r, border_radius=4)
                    b_txt = self.font_badge.render("WIP", True, (148, 163, 184))
                else:
                    is_active = (target_p and getattr(target_p, "crop", None) == c_cfg["name"])
                    btn_col = (16, 185, 129) if not is_active else (37, 99, 235)
                    pygame.draw.rect(surface, btn_col, btn_r, border_radius=4)
                    b_txt = self.font_badge.render("PLANTED" if is_active else "PLANT", True, (255, 255, 255))

                surface.blit(b_txt, (btn_r.x + (btn_r.w - b_txt.get_width()) // 2, btn_r.y + 5))

                crop_y += 46

    def _draw_priority_tab(self, surface, mx, cy, servant_manager):
        """RimWorld-Style Work Priorities Grid (1=High, 4=Low, -=Off)"""
        title = self.font_sub.render(" Servant Work Priorities (RimWorld Priority Matrix)", True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + 24, cy))

        sub_desc = self.font_body.render("Left-click each cell to cycle priority: 1 (High) → 2 → 3 → 4 (Low) → - (Off)", True, COLOR_TEXT_MUTED)
        surface.blit(sub_desc, (mx + 24, cy + 20))

        if not servant_manager or not servant_manager.servants:
            none_s = self.font_body.render("- No servants currently assigned to manor.", True, COLOR_TEXT_MUTED)
            surface.blit(none_s, (mx + 36, cy + 50))
            return

        table_x = mx + 24
        table_y = cy + 48
        name_col_w = 150
        cell_w = 110
        row_h = 36

        self.priority_cell_rects = {}

        # 1. Header Row
        header_rect = pygame.Rect(table_x, table_y, name_col_w + len(WORK_TYPES) * cell_w, 28)
        pygame.draw.rect(surface, (30, 41, 59), header_rect, border_radius=4)

        h_name = self.font_badge.render("WORKER", True, COLOR_TEXT_TITLE)
        surface.blit(h_name, (table_x + 10, table_y + 7))

        for j, wt in enumerate(WORK_TYPES):
            col_x = table_x + name_col_w + (j * cell_w)
            w_col = COLOR_BADGE_WIP if wt["wip"] else (241, 245, 249)
            h_lbl = self.font_badge.render(wt["name"], True, w_col)
            surface.blit(h_lbl, (col_x + 8, table_y + 7))

        # 2. Worker Rows
        cur_y = table_y + 32
        for s in servant_manager.servants:
            row_rect = pygame.Rect(table_x, cur_y, name_col_w + len(WORK_TYPES) * cell_w, row_h)
            pygame.draw.rect(surface, (15, 23, 42, 180), row_rect, border_radius=4)
            pygame.draw.rect(surface, (51, 65, 85), row_rect, width=1, border_radius=4)

            # Servant Avatar Dot & Name
            pygame.draw.circle(surface, (245, 158, 11), (table_x + 18, cur_y + row_h // 2), 7)
            pygame.draw.circle(surface, (120, 53, 15), (table_x + 18, cur_y + row_h // 2), 7, 1)
            s_name = self.font_sub.render(s.name, True, (241, 245, 249))
            surface.blit(s_name, (table_x + 32, cur_y + 9))

            # Work Type Cells
            for j, wt in enumerate(WORK_TYPES):
                w_id = wt["id"]
                col_x = table_x + name_col_w + (j * cell_w)
                cell_rect = pygame.Rect(col_x + 6, cur_y + 4, cell_w - 12, row_h - 8)

                if wt["wip"]:
                    # Disabled WIP cell
                    pygame.draw.rect(surface, (30, 41, 59, 140), cell_rect, border_radius=4)
                    pygame.draw.rect(surface, (51, 65, 85), cell_rect, width=1, border_radius=4)
                    txt = self.font_badge.render("- (WIP)", True, (100, 116, 139))
                    surface.blit(txt, (cell_rect.centerx - txt.get_width() // 2, cell_rect.centery - txt.get_height() // 2))
                else:
                    self.priority_cell_rects[(s.id, w_id)] = cell_rect
                    p_val = s.work_priorities.get(w_id, 1)
                    p_col = PRIORITY_COLORS.get(p_val, (71, 85, 105))

                    cell_hover = cell_rect.collidepoint(pygame.mouse.get_pos())
                    bg_col = (45, 60, 80) if cell_hover else (24, 34, 52)

                    pygame.draw.rect(surface, bg_col, cell_rect, border_radius=4)
                    pygame.draw.rect(surface, p_col, cell_rect, width=2 if p_val > 0 else 1, border_radius=4)

                    val_str = str(p_val) if p_val > 0 else "—"
                    p_surf = self.font_priority.render(val_str, True, p_col if p_val > 0 else (100, 116, 139))
                    surface.blit(p_surf, (cell_rect.centerx - p_surf.get_width() // 2, cell_rect.centery - p_surf.get_height() // 2))

            cur_y += row_h + 6

        # 3. Legend & Instructions Footer
        leg_y = cur_y + 14
        pygame.draw.line(surface, COLOR_MODAL_BORDER, (table_x, leg_y), (table_x + name_col_w + len(WORK_TYPES) * cell_w, leg_y))

        leg_txt = self.font_body.render("Priority Levels: [ 1 ] Highest Priority  |  [ 2 ] Normal  |  [ 3 ] Low  |  [ 4 ] Lowest  |  [ — ] Disabled", True, (226, 232, 240))
        surface.blit(leg_txt, (table_x, leg_y + 10))

        rule_txt = self.font_badge.render("Servants automatically choose the lowest number task available. If tied, closest work is preferred.", True, COLOR_TEXT_MUTED)
        surface.blit(rule_txt, (table_x, leg_y + 32))

    def _draw_schedule_tab(self, surface, mx, cy, schedule_manager=None, day_cycle=None):
        """RimWorld-Style 24-Hour Activity Schedule Tab"""
        mouse_pos = pygame.mouse.get_pos()
        cur_hour = getattr(day_cycle, "current_hour", 8.0) if day_cycle else 8.0

        # =============================================================
        # VIEW 1: Job Selection Directory
        # =============================================================
        if self.selected_schedule_job_id is None:
            title = self.font_title.render("VILLAGE LABOR & SHIFT SCHEDULE", True, COLOR_TEXT_TITLE)
            surface.blit(title, (mx + 24, cy - 4))

            sub = self.font_body.render("Set daily 24-hour work shifts, recreation, and sleep hours for each guild profession:", True, COLOR_TEXT_MUTED)
            surface.blit(sub, (mx + 24, cy + 22))

            y_cur = cy + 46
            self.schedule_job_select_btn_rects = {}

            for job_id, job_cfg in DEDICATED_JOBS.items():
                card_h = 58
                card_rect = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, card_h)

                pygame.draw.rect(surface, (24, 34, 52), card_rect, border_radius=8)
                pygame.draw.rect(surface, (51, 65, 85), card_rect, width=1, border_radius=8)

                # Icon
                icon_col = job_cfg.get("color", (34, 197, 94))
                pygame.draw.circle(surface, icon_col, (card_rect.x + 24, card_rect.y + card_h // 2), 12)
                pygame.draw.circle(surface, (15, 23, 42), (card_rect.x + 24, card_rect.y + card_h // 2), 12, 2)

                # Title
                j_title = self.font_sub.render(job_cfg["name"], True, (241, 245, 249))
                surface.blit(j_title, (card_rect.x + 46, card_rect.y + 8))

                # Mini schedule preview bar
                if schedule_manager:
                    sched = schedule_manager.get_schedule(job_id)
                    bar_x = card_rect.x + 46
                    bar_y = card_rect.y + 32
                    bar_w = 260
                    seg_w = bar_w / 24.0
                    for h_idx in range(24):
                        act = sched[h_idx]
                        col = SCHEDULE_TYPES.get(act, {}).get("color", (100, 116, 139))
                        pygame.draw.rect(surface, col, (bar_x + int(h_idx * seg_w), bar_y, int(seg_w) + 1, 14))

                    # Count work hours
                    work_hours = sum(1 for a in sched if a == "WORK")
                    sleep_hours = sum(1 for a in sched if a == "SLEEP")
                    summary_txt = f"{work_hours}h Work, {sleep_hours}h Sleep"
                    surface.blit(self.font_badge.render(summary_txt, True, COLOR_TEXT_MUTED), (bar_x + bar_w + 14, bar_y + 1))

                # Action Button: [Edit Schedule ➔]
                btn_rect = pygame.Rect(card_rect.right - 140, card_rect.y + 13, 126, 32)
                self.schedule_job_select_btn_rects[job_id] = btn_rect
                b_hover = btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (37, 99, 235) if b_hover else (30, 58, 138), btn_rect, border_radius=6)
                pygame.draw.rect(surface, (96, 165, 250), btn_rect, width=1, border_radius=6)
                btn_lbl = self.font_badge.render("Edit Schedule ->", True, (255, 255, 255))
                surface.blit(btn_lbl, (btn_rect.centerx - btn_lbl.get_width() // 2, btn_rect.centery - btn_lbl.get_height() // 2))

                y_cur += card_h + 8

        # =============================================================
        # VIEW 2: Detailed 24-Hour Matrix for Selected Job
        # =============================================================
        else:
            job_cfg = DEDICATED_JOBS.get(self.selected_schedule_job_id, {})
            job_name = job_cfg.get("name", self.selected_schedule_job_id)

            # Header & Back Button
            back_w = 140
            self.schedule_back_btn_rect = pygame.Rect(mx + 24, cy - 4, back_w, 28)
            b_hover = self.schedule_back_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (51, 65, 85) if b_hover else (30, 41, 59), self.schedule_back_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (96, 165, 250), self.schedule_back_btn_rect, width=1, border_radius=6)
            b_lbl = self.font_badge.render("< Back to Jobs", True, (255, 255, 255))
            surface.blit(b_lbl, (self.schedule_back_btn_rect.centerx - b_lbl.get_width() // 2, self.schedule_back_btn_rect.centery - b_lbl.get_height() // 2))

            surface.blit(self.font_title.render(f"{job_name} 24-Hour Schedule", True, (241, 245, 249)), (mx + 24 + back_w + 14, cy - 4))

            # Current Hour indicator
            curr_str = f"Time: {int(cur_hour):02d}:00"
            surface.blit(self.font_sub.render(curr_str, True, (250, 204, 21)), (mx + self.modal_w - 180, cy - 2))

            # 1. Day of the Week Selector Bar (Monday - Sunday)
            cur_d_y = cy + 28
            avail_w = self.modal_w - 48
            day_w = (avail_w - (6 * 6)) // 7
            self.schedule_day_btn_rects = {}
            for idx, d_name in enumerate(DAYS_OF_WEEK):
                day_btn = pygame.Rect(mx + 24 + idx * (day_w + 6), cur_d_y, day_w, 24)
                self.schedule_day_btn_rects[d_name] = day_btn
                is_cur_day = (self.selected_schedule_day == d_name)
                d_hov = day_btn.collidepoint(mouse_pos)
                d_bg = (37, 99, 235) if is_cur_day else ((45, 60, 80) if d_hov else (24, 34, 52))
                pygame.draw.rect(surface, d_bg, day_btn, border_radius=4)
                pygame.draw.rect(surface, (96, 165, 250) if is_cur_day else (51, 65, 85), day_btn, width=1, border_radius=4)
                d_lbl = self.font_badge.render(d_name[:3], True, (255, 255, 255) if is_cur_day else (148, 163, 184))
                surface.blit(d_lbl, (day_btn.centerx - d_lbl.get_width() // 2, day_btn.centery - d_lbl.get_height() // 2))

            # 2. Paintbrush tools banner
            tool_y = cur_d_y + 30
            tool_rect = pygame.Rect(mx + 24, tool_y, self.modal_w - 48, 38)
            pygame.draw.rect(surface, (24, 34, 52), tool_rect, border_radius=6)
            pygame.draw.rect(surface, (71, 85, 105), tool_rect, width=1, border_radius=6)

            surface.blit(self.font_badge.render("PAINT TOOL:", True, COLOR_TEXT_MUTED), (tool_rect.x + 12, tool_rect.y + 11))

            self.schedule_brush_btn_rects = {}
            bx = tool_rect.x + 100
            for b_id, b_info in SCHEDULE_TYPES.items():
                b_btn = pygame.Rect(bx, tool_rect.y + 5, 96, 28)
                self.schedule_brush_btn_rects[b_id] = b_btn
                is_sel = (self.selected_schedule_brush == b_id)
                col = b_info["color"]
                if is_sel:
                    pygame.draw.rect(surface, col, b_btn, border_radius=5)
                    pygame.draw.rect(surface, (255, 255, 255), b_btn, width=2, border_radius=5)
                    lbl_col = (255, 255, 255)
                else:
                    pygame.draw.rect(surface, (30, 41, 59), b_btn, border_radius=5)
                    pygame.draw.rect(surface, col, b_btn, width=1, border_radius=5)
                    lbl_col = col

                t_lbl = self.font_badge.render(f"{b_info['name']}", True, lbl_col)
                surface.blit(t_lbl, (b_btn.centerx - t_lbl.get_width() // 2, b_btn.centery - t_lbl.get_height() // 2))
                bx += 104

            # 3. Priest Prayer Time Contiguous Block Adjustment Banner (If Priest selected)
            self.prayer_start_dec_rect = None
            self.prayer_start_inc_rect = None
            self.prayer_end_dec_rect = None
            self.prayer_end_inc_rect = None
            if self.selected_schedule_job_id == "Priest" and schedule_manager:
                p_s, p_e = schedule_manager.get_prayer_hours()
                pr_banner = pygame.Rect(mx + 24, tool_y + 44, self.modal_w - 48, 36)
                pygame.draw.rect(surface, (30, 27, 46), pr_banner, border_radius=6)
                pygame.draw.rect(surface, (168, 85, 247), pr_banner, width=1, border_radius=6)

                pr_head = self.font_badge.render("⛪ DECREED PRAYER TIME BLOCK (ALL GUILDS ATTEND):", True, (216, 180, 254))
                surface.blit(pr_head, (pr_banner.x + 12, pr_banner.y + 10))

                # Start Hour [-] {p_s}:00 [+]
                ctrl_x = pr_banner.right - 280
                surface.blit(self.font_badge.render("Start:", True, COLOR_TEXT_MUTED), (ctrl_x, pr_banner.y + 10))
                self.prayer_start_dec_rect = pygame.Rect(ctrl_x + 40, pr_banner.y + 6, 22, 24)
                pygame.draw.rect(surface, (51, 65, 85), self.prayer_start_dec_rect, border_radius=3)
                surface.blit(self.font_badge.render("-", True, (255, 255, 255)), (self.prayer_start_dec_rect.x + 7, self.prayer_start_dec_rect.y + 4))

                surface.blit(self.font_sub.render(f"{p_s:02d}:00", True, (250, 204, 21)), (ctrl_x + 68, pr_banner.y + 8))

                self.prayer_start_inc_rect = pygame.Rect(ctrl_x + 115, pr_banner.y + 6, 22, 24)
                pygame.draw.rect(surface, (51, 65, 85), self.prayer_start_inc_rect, border_radius=3)
                surface.blit(self.font_badge.render("+", True, (255, 255, 255)), (self.prayer_start_inc_rect.x + 6, self.prayer_start_inc_rect.y + 4))

                # End Hour [-] {p_e}:00 [+]
                end_ctrl_x = ctrl_x + 150
                surface.blit(self.font_badge.render("End:", True, COLOR_TEXT_MUTED), (end_ctrl_x, pr_banner.y + 10))
                self.prayer_end_dec_rect = pygame.Rect(end_ctrl_x + 35, pr_banner.y + 6, 22, 24)
                pygame.draw.rect(surface, (51, 65, 85), self.prayer_end_dec_rect, border_radius=3)
                surface.blit(self.font_badge.render("-", True, (255, 255, 255)), (self.prayer_end_dec_rect.x + 7, self.prayer_end_dec_rect.y + 4))

                surface.blit(self.font_sub.render(f"{p_e:02d}:00", True, (250, 204, 21)), (end_ctrl_x + 63, pr_banner.y + 8))

                self.prayer_end_inc_rect = pygame.Rect(end_ctrl_x + 110, pr_banner.y + 6, 22, 24)
                pygame.draw.rect(surface, (51, 65, 85), self.prayer_end_inc_rect, border_radius=3)
                surface.blit(self.font_badge.render("+", True, (255, 255, 255)), (self.prayer_end_inc_rect.x + 6, self.prayer_end_inc_rect.y + 4))

                grid_y = pr_banner.bottom + 12
            else:
                grid_y = tool_y + 46

            # 4. Timetable Grid (24 boxes)
            day_sched_title = f"{self.selected_schedule_day} 24-Hour Timeline (Click hour slot to apply paint tool):"
            surface.blit(self.font_sub.render(day_sched_title, True, (241, 245, 249)), (mx + 24, grid_y))

            sched = schedule_manager.get_schedule(self.selected_schedule_job_id, day=self.selected_schedule_day) if schedule_manager else list(DEFAULT_JOB_SCHEDULE)
            grid_bar_y = grid_y + 24
            avail_grid_w = self.modal_w - 48
            cell_w = avail_grid_w // 24
            cell_h = 54

            self.schedule_hour_cell_rects = {}
            for h in range(24):
                cx = mx + 24 + h * cell_w
                cell_rect = pygame.Rect(cx, grid_bar_y, cell_w - 2, cell_h)
                self.schedule_hour_cell_rects[h] = cell_rect

                act = sched[h]
                act_col = SCHEDULE_TYPES.get(act, {}).get("color", (100, 116, 139))
                is_current = (int(cur_hour) == h)

                pygame.draw.rect(surface, act_col, cell_rect, border_radius=4)
                if is_current:
                    pygame.draw.rect(surface, (250, 204, 21), cell_rect, width=2, border_radius=4)
                else:
                    pygame.draw.rect(surface, (15, 23, 42), cell_rect, width=1, border_radius=4)

                # Hour text
                h_txt = self.font_badge.render(f"{h:02d}", True, (255, 255, 255))
                surface.blit(h_txt, (cell_rect.centerx - h_txt.get_width() // 2, cell_rect.y + 5))

                # Activity abbreviation
                abbrev = act[:1]  # 'W', 'L', 'S', 'A', 'P'
                a_txt = self.font_sub.render(abbrev, True, (255, 255, 255))
                surface.blit(a_txt, (cell_rect.centerx - a_txt.get_width() // 2, cell_rect.y + 22))

                if is_current:
                    pygame.draw.polygon(surface, (250, 204, 21), [
                        (cell_rect.centerx, grid_bar_y - 2),
                        (cell_rect.centerx - 4, grid_bar_y - 7),
                        (cell_rect.centerx + 4, grid_bar_y - 7)
                    ])

            # Presets & Quick Fill Section
            preset_y = grid_bar_y + cell_h + 14
            surface.blit(self.font_sub.render("Quick Schedule Presets:", True, COLOR_TEXT_MUTED), (mx + 24, preset_y + 4))

            self.schedule_preset_btn_rects = {}
            presets = [
                ("standard", "Standard (10h Work, 8h Sleep)", (59, 130, 246)),
                ("hardwork", "Hardworking (15h Work, 6h Sleep)", (245, 158, 11)),
                ("relaxed", "Relaxed (7h Work, 9h Sleep)", (34, 197, 94))
            ]
            px = mx + 200
            for p_id, p_title, p_col in presets:
                p_rect = pygame.Rect(px, preset_y, 160, 28)
                self.schedule_preset_btn_rects[p_id] = p_rect
                p_hover = p_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, p_col if p_hover else (30, 41, 59), p_rect, border_radius=5)
                pygame.draw.rect(surface, p_col, p_rect, width=1, border_radius=5)
                p_lbl = self.font_badge.render(p_title.split(' ')[0], True, (255, 255, 255))
                surface.blit(p_lbl, (p_rect.centerx - p_lbl.get_width() // 2, p_rect.centery - p_lbl.get_height() // 2))
                px += 170

            # Explanation notes
            note_y = preset_y + 38
            note = self.font_body.render("• Workers follow their active hourly schedule. During WORK, farmers water unwatered tiles and harvest ripe crops.", True, COLOR_TEXT_MUTED)
            surface.blit(note, (mx + 24, note_y))
            note2 = self.font_body.render("• During SLEEP, villagers return to their family household. During LEISURE, they relax near Town Center.", True, COLOR_TEXT_MUTED)
            surface.blit(note2, (mx + 24, note_y + 18))

    def _draw_villagers_tab(self, surface, mx, cy, villager_manager, permit_manager, building_manager, furniture_manager=None, stockpile_manager=None, resources=None, servant_manager=None, production_system=None):
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
            surface.blit(title, (mx + 24, cy))

            # Button: [+ Add Family (Cheat)]
            btn_w = 175
            btn_h = 30
            self.add_family_cheat_btn_rect = pygame.Rect(mx + self.modal_w - btn_w - 24, cy - 4, btn_w, btn_h)
            btn_hover = self.add_family_cheat_btn_rect.collidepoint(mouse_pos)
            btn_col = (126, 34, 206) if btn_hover else (107, 33, 168)

            pygame.draw.rect(surface, btn_col, self.add_family_cheat_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (192, 132, 252), self.add_family_cheat_btn_rect, width=1, border_radius=6)
            b_txt = self.font_badge.render("+ Add Family (Cheat)", True, (255, 255, 255))
            surface.blit(b_txt, (self.add_family_cheat_btn_rect.centerx - b_txt.get_width() // 2, self.add_family_cheat_btn_rect.centery - b_txt.get_height() // 2))

            sub = self.font_body.render("Settlers migrate in family clans (1–3 generations). Landlord grants Housing Deeds to each family:", True, COLOR_TEXT_MUTED)
            surface.blit(sub, (mx + 24, cy + 22))

            y_cur = cy + 48
            self.view_family_btn_rects = []

            if not families:
                empty_card = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 80)
                pygame.draw.rect(surface, (24, 34, 52), empty_card, border_radius=8)
                pygame.draw.rect(surface, (51, 65, 85), empty_card, width=1, border_radius=8)

                msg1 = self.font_body.render("• No settler families residing on your estate yet.", True, COLOR_TEXT_MUTED)
                msg2 = self.font_body.render("Click [+ Add Family (Cheat)] above to welcome a new immigrant family to your land!", True, (56, 189, 248))
                surface.blit(msg1, (empty_card.x + 20, empty_card.y + 18))
                surface.blit(msg2, (empty_card.x + 20, empty_card.y + 42))

            else:
                card_h = 58
                for fam in families:
                    card_rect = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, card_h)
                    pygame.draw.rect(surface, (24, 34, 52), card_rect, border_radius=8)
                    pygame.draw.rect(surface, (51, 65, 85), card_rect, width=1, border_radius=8)

                    # Family Coat of Arms / Emblem Circle
                    emblem_col = (34, 197, 94) if fam.assigned_permit_id else (245, 158, 11)
                    pygame.draw.circle(surface, emblem_col, (card_rect.x + 24, card_rect.y + card_h // 2), 12)
                    pygame.draw.circle(surface, (15, 23, 42), (card_rect.x + 24, card_rect.y + card_h // 2), 12, 2)

                    # Family Title & Living Population
                    deceased_count = fam.member_count - fam.living_member_count
                    pop_label = f"{fam.living_member_count} Living" if deceased_count == 0 else f"{fam.living_member_count} Living, {deceased_count} Deceased"
                    fam_name = self.font_sub.render(f"The {fam.surname} Family  ({pop_label})", True, (241, 245, 249))
                    surface.blit(fam_name, (card_rect.x + 46, card_rect.y + 8))

                    # Generation badge
                    gen_txt = self.font_badge.render(f"Generations: {fam.get_generation_label()}", True, (56, 189, 248))
                    surface.blit(gen_txt, (card_rect.x + 46 + fam_name.get_width() + 12, card_rect.y + 10))

                    # Primary Needs Indicator (Agent 1: Food & Water Stocks + Daily Fulfillment)
                    food_stk = fam.get_food_stock(furniture_manager, stockpile_manager)
                    water_stk = fam.get_water_stock(furniture_manager, stockpile_manager)
                    food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
                    needs_x = card_rect.right - 350
                    needs_y = card_rect.y + 18

                    # Food Badge: Displays actual storage stock + daily fulfillment count
                    food_col = (34, 197, 94) if (food_ok >= living_tot and living_tot > 0) else ((245, 158, 11) if (food_ok > 0 or food_stk > 0) else (239, 68, 68))
                    food_badge = pygame.Rect(needs_x, needs_y, 105, 22)
                    pygame.draw.rect(surface, (15, 23, 42), food_badge, border_radius=4)
                    pygame.draw.rect(surface, food_col, food_badge, width=1, border_radius=4)
                    f_txt = self.font_badge.render(f"Food: {food_stk} ({food_ok}/{living_tot})", True, food_col)
                    surface.blit(f_txt, (food_badge.centerx - f_txt.get_width() // 2, food_badge.centery - f_txt.get_height() // 2))

                    # Water Badge: Displays actual storage stock + daily fulfillment count
                    water_col = (56, 189, 248) if (water_ok >= living_tot and living_tot > 0) else ((245, 158, 11) if (water_ok > 0 or water_stk > 0) else (239, 68, 68))
                    water_badge = pygame.Rect(needs_x + 112, needs_y, 105, 22)
                    pygame.draw.rect(surface, (15, 23, 42), water_badge, border_radius=4)
                    pygame.draw.rect(surface, water_col, water_badge, width=1, border_radius=4)
                    w_txt = self.font_badge.render(f"Water: {water_stk} ({water_ok}/{living_tot})", True, water_col)
                    surface.blit(w_txt, (water_badge.centerx - w_txt.get_width() // 2, water_badge.centery - w_txt.get_height() // 2))

                    # Dedicated Job & Assigned Deed Status
                    if fam.assigned_permit_id:
                        p_deed = next((p for p in permit_manager.permits if p.id == fam.assigned_permit_id), None)
                        deed_label = f"Assigned Deed: {p_deed.name}" if p_deed else "Assigned Deed: Active Lot"
                        deed_col = (34, 197, 94)
                    else:
                        deed_label = "Deed: Unassigned (Homeless Immigrants at Town Center)"
                        deed_col = (245, 158, 11)

                    sub_line = f"Dedicated Profession: Peasant Farmer   |   {deed_label}"
                    surface.blit(self.font_body.render(sub_line, True, deed_col), (card_rect.x + 46, card_rect.y + 30))


                    # Action Button: [👥 View Family]
                    view_btn = pygame.Rect(card_rect.right - 120, card_rect.y + 13, 108, 32)
                    self.view_family_btn_rects.append((fam.id, view_btn))
                    v_hover = view_btn.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (37, 99, 235) if v_hover else (30, 58, 138), view_btn, border_radius=6)
                    pygame.draw.rect(surface, (96, 165, 250), view_btn, width=1, border_radius=6)

                    lbl = self.font_badge.render("View Family", True, (255, 255, 255))
                    surface.blit(lbl, (view_btn.centerx - lbl.get_width() // 2, view_btn.centery - lbl.get_height() // 2))

                    y_cur += card_h + 8

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
                self.close_possession_btn_rect = pygame.Rect(mx + 24, cy - 4, 150, 28)
                b_hover = self.close_possession_btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (51, 65, 85) if b_hover else (30, 41, 59), self.close_possession_btn_rect, border_radius=6)
                pygame.draw.rect(surface, (96, 165, 250), self.close_possession_btn_rect, width=1, border_radius=6)
                back_lbl = self.font_badge.render("< Back to Roster", True, (255, 255, 255))
                surface.blit(back_lbl, (self.close_possession_btn_rect.centerx - back_lbl.get_width() // 2, self.close_possession_btn_rect.centery - back_lbl.get_height() // 2))

                f_title = self.font_title.render(f"Household Possessions: The {fam.surname} Family", True, (241, 245, 249))
                surface.blit(f_title, (mx + 24 + 150 + 14, cy - 4))

                # Button: [🎁 Grant Item]
                grant_btn_w = 140
                self.open_grant_dialog_btn_rect = pygame.Rect(mx + self.modal_w - 24 - grant_btn_w, cy - 4, grant_btn_w, 28)
                g_hov = self.open_grant_dialog_btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (22, 101, 52) if g_hov else (21, 128, 61), self.open_grant_dialog_btn_rect, border_radius=6)
                pygame.draw.rect(surface, (74, 222, 128), self.open_grant_dialog_btn_rect, width=1, border_radius=6)
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
                grid_x = mx + 24
                grid_y = cy + 34
                grid_w = self.modal_w - 48
                grid_h = 240
                col_w = grid_w / 3.0
                row_h = grid_h / 3.0

                # Grid Background & Outer Border
                grid_rect = pygame.Rect(grid_x, grid_y, grid_w, grid_h)
                pygame.draw.rect(surface, (15, 23, 42), grid_rect, border_radius=8)
                pygame.draw.rect(surface, (51, 65, 85), grid_rect, width=2, border_radius=8)

                if total_items == 0:
                    # Empty state display: No WIP, no placeholders, no fake zero items
                    empty_lbl = self.font_body.render("— Household storage and inventory are currently empty —", True, (148, 163, 184))
                    surface.blit(empty_lbl, (grid_rect.centerx - empty_lbl.get_width() // 2, grid_rect.centery - 12))
                    sub_lbl = self.font_badge.render("Items produced, harvested, granted, or purchased will appear here.", True, (100, 116, 139))
                    surface.blit(sub_lbl, (grid_rect.centerx - sub_lbl.get_width() // 2, grid_rect.centery + 12))
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
                        draw_item_icon(surface, item["name"], cx_start + 24, cy_start + int(row_h // 2), size=11)

                        cnt_color = (34, 197, 94)  # Vibrant green for actual possessed items
                        cnt_str = f"x {item['count']}"
                        cnt_surf = self.font_sub.render(cnt_str, True, cnt_color)
                        surface.blit(cnt_surf, (cx_start + 44, cy_start + int(row_h // 2) - 9))

                        name_color = (241, 245, 249)
                        name_surf = self.font_body.render(item["name"], True, name_color)
                        surface.blit(name_surf, (cx_start + 98, cy_start + int(row_h // 2) - 8))

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
                note_y = grid_y + grid_h + 16
                surface.blit(self.font_sub.render("Private Household Property Rules:", True, (245, 158, 11)), (mx + 24, note_y))
                surface.blit(self.font_body.render("• Villagers store their private crop harvest in storage furniture (chests) placed inside their assigned Housing Lot.", True, (226, 232, 240)), (mx + 24, note_y + 20))
                surface.blit(self.font_body.render("• Lord's servants cannot touch, haul, or seize peasant household possessions. Only landlord private stockpiles belong to the Lord.", True, COLOR_TEXT_MUTED), (mx + 24, note_y + 38))

                # Pagination controls if total items exceed 1 page
                if max_page > 0:
                    pag_w = 70
                    pag_h = 24
                    pag_x = mx + grid_w - 180
                    pag_y = note_y

                    # Page Indicator
                    page_str = f"Page {self.possession_page + 1}/{max_page + 1}"
                    page_surf = self.font_badge.render(page_str, True, (148, 163, 184))
                    surface.blit(page_surf, (pag_x - page_surf.get_width() - 10, pag_y + 4))

                    # Prev Button
                    self.possession_prev_btn_rect = pygame.Rect(pag_x, pag_y, pag_w, pag_h)
                    p_hov = self.possession_prev_btn_rect.collidepoint(mouse_pos)
                    can_prev = (self.possession_page > 0)
                    pygame.draw.rect(surface, (51, 65, 85) if (p_hov and can_prev) else (30, 41, 59), self.possession_prev_btn_rect, border_radius=4)
                    pygame.draw.rect(surface, (96, 165, 250) if can_prev else (71, 85, 105), self.possession_prev_btn_rect, width=1, border_radius=4)
                    prev_txt = self.font_badge.render("< Prev", True, (255, 255, 255) if can_prev else (100, 116, 139))
                    surface.blit(prev_txt, (self.possession_prev_btn_rect.centerx - prev_txt.get_width() // 2, self.possession_prev_btn_rect.centery - prev_txt.get_height() // 2))

                    # Next Button
                    self.possession_next_btn_rect = pygame.Rect(pag_x + pag_w + 8, pag_y, pag_w, pag_h)
                    n_hov = self.possession_next_btn_rect.collidepoint(mouse_pos)
                    can_next = (self.possession_page < max_page)
                    pygame.draw.rect(surface, (51, 65, 85) if (n_hov and can_next) else (30, 41, 59), self.possession_next_btn_rect, border_radius=4)
                    pygame.draw.rect(surface, (96, 165, 250) if can_next else (71, 85, 105), self.possession_next_btn_rect, width=1, border_radius=4)
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
            back_w = 150
            self.back_to_families_btn_rect = pygame.Rect(mx + 24, cy - 4, back_w, 28)
            b_hover = self.back_to_families_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (51, 65, 85) if b_hover else (30, 41, 59), self.back_to_families_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (96, 165, 250), self.back_to_families_btn_rect, width=1, border_radius=6)

            back_lbl = self.font_badge.render("< Back to Families", True, (255, 255, 255))
            surface.blit(back_lbl, (self.back_to_families_btn_rect.centerx - back_lbl.get_width() // 2, self.back_to_families_btn_rect.centery - back_lbl.get_height() // 2))

            f_title = self.font_title.render(f"Household: The {fam.surname} Family", True, (241, 245, 249))
            surface.blit(f_title, (mx + 24 + back_w + 14, cy - 4))

            # Button: [📦 Household Possession]
            self.household_possession_btn_rect = pygame.Rect(mx + self.modal_w - 24 - 180, cy - 4, 180, 28)
            hp_hover = self.household_possession_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (202, 138, 4) if hp_hover else (161, 98, 7), self.household_possession_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (250, 204, 21), self.household_possession_btn_rect, width=1, border_radius=6)
            hp_lbl = self.font_badge.render("Household Possession", True, (255, 255, 255))
            surface.blit(hp_lbl, (self.household_possession_btn_rect.centerx - hp_lbl.get_width() // 2, self.household_possession_btn_rect.centery - hp_lbl.get_height() // 2))

            # Land Deed & Household Status Banner
            banner_y = cy + 30
            banner_rect = pygame.Rect(mx + 24, banner_y, self.modal_w - 48, 54)
            pygame.draw.rect(surface, (24, 34, 52), banner_rect, border_radius=8)
            pygame.draw.rect(surface, (71, 85, 105), banner_rect, width=1, border_radius=8)

            p_assigned = next((p for p in permit_manager.permits if p.id == fam.assigned_permit_id), None)
            if p_assigned:
                d_txt = f"Land Deed: Assigned to {p_assigned.name} ({len(p_assigned.tiles)} tiles)"
                d_col = (34, 197, 94)
                self.household_view_permit_btn_rect = pygame.Rect(banner_rect.right - 108, banner_rect.y + 4, 96, 22)
                vp_hov = self.household_view_permit_btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (37, 99, 235) if vp_hov else (30, 41, 59), self.household_view_permit_btn_rect, border_radius=4)
                pygame.draw.rect(surface, (96, 165, 250), self.household_view_permit_btn_rect, width=1, border_radius=4)
                vp_lbl = self.font_badge.render("View Permit", True, (255, 255, 255))
                surface.blit(vp_lbl, (self.household_view_permit_btn_rect.centerx - vp_lbl.get_width() // 2, self.household_view_permit_btn_rect.centery - vp_lbl.get_height() // 2))
            else:
                self.household_view_permit_btn_rect = None
                d_txt = "Land Deed: Unassigned — Living at Town Center"
                d_col = (245, 158, 11)

            # Row 1: Deed & Population
            pop_summary = f"{d_txt}   |   Living Population: {fam.living_member_count} Members"
            surface.blit(self.font_sub.render(pop_summary, True, d_col), (banner_rect.x + 14, banner_rect.y + 5))

            # Row 2: Food & Water Stocks and Daily Requirements (Agent 1)
            food_stk = fam.get_food_stock(furniture_manager, stockpile_manager)
            water_stk = fam.get_water_stock(furniture_manager, stockpile_manager)
            food_ok, water_ok, living_tot = fam.get_primary_needs_progress()
            needs_summary = f"Primary Needs: Food: {food_stk} ({food_ok}/{living_tot} fulfilled)   |   Water: {water_stk} ({water_ok}/{living_tot} fulfilled)   |   Daily Requirement: {fam.daily_food_required} Food, {fam.daily_water_required} Water"
            surface.blit(self.font_badge.render(needs_summary, True, (241, 245, 249)), (banner_rect.x + 14, banner_rect.y + 22))

            # Row 3: Currency (Agent 2) & Production (Agent 3)
            ps = production_system or ProductionDistributionSystem.get_instance()
            p_sum = ps.get_household_production_summary(fam.id)
            potatoes_earned = p_sum["total_produced"].get("Potato", 0)
            farm_permits = [p for p in permit_manager.permits if p.permit_type == "farm"] if permit_manager else []
            assigned_work_count = sum(1 for m in fam.members if any(m.id in getattr(p, "assigned_workers", []) for p in farm_permits))
            curr_balance = getattr(fam, "currency_balance", getattr(fam, "coins", 0))
            econ_text = f"Treasury: {curr_balance} Copper Coins   |   Production: x{potatoes_earned} Potatoes Harvested ({assigned_work_count} Farmers in Fields)"
            surface.blit(self.font_badge.render(econ_text, True, (56, 189, 248)), (banner_rect.x + 14, banner_rect.y + 37))

            # Button: [Assign / Change Deed]
            self.assign_permit_btn_rects = {}
            self.revoke_deed_btn_rect = None
            self.open_assign_lot_btn_rect = pygame.Rect(banner_rect.right - 230, banner_rect.y + 12, 130, 28)
            a_hover = self.open_assign_lot_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (16, 185, 129) if a_hover else (5, 150, 105), self.open_assign_lot_btn_rect, border_radius=5)
            a_lbl = self.font_badge.render("Assign Deed" if not p_assigned else "Change Deed", True, (255, 255, 255))
            surface.blit(a_lbl, (self.open_assign_lot_btn_rect.centerx - a_lbl.get_width() // 2, self.open_assign_lot_btn_rect.centery - a_lbl.get_height() // 2))

            if p_assigned:
                self.revoke_deed_btn_rect = pygame.Rect(banner_rect.right - 92, banner_rect.y + 12, 84, 28)
                r_hover = self.revoke_deed_btn_rect.collidepoint(mouse_pos)
                pygame.draw.rect(surface, (220, 38, 38) if r_hover else (153, 27, 27), self.revoke_deed_btn_rect, border_radius=5)
                r_lbl = self.font_badge.render("Revoke", True, (255, 255, 255))
                surface.blit(r_lbl, (self.revoke_deed_btn_rect.centerx - r_lbl.get_width() // 2, self.revoke_deed_btn_rect.centery - r_lbl.get_height() // 2))

            # Member Roster Grouped by Generation
            self.member_inventory_btn_rects.clear()
            y_cur = banner_y + 64
            m_header = self.font_sub.render(f"Household Members Roster ({fam.member_count} Members across {fam.get_generation_label()}):", True, COLOR_TEXT_TITLE)
            surface.blit(m_header, (mx + 24, y_cur))


            y_cur += 22
            gen_names = {1: "Generation 1 (Elders / Grandparents)", 2: "Generation 2 (Core Couple / Parents)", 3: "Generation 3 (Adult Offspring)"}

            for gen_idx in sorted(list({m.generation for m in fam.members})):
                gen_title = self.font_badge.render(gen_names.get(gen_idx, f"Generation {gen_idx}"), True, (245, 158, 11))
                surface.blit(gen_title, (mx + 28, y_cur))
                y_cur += 16

                for m in [mem for mem in fam.members if mem.generation == gen_idx]:
                    m_card = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 30)
                    pygame.draw.rect(surface, (15, 23, 42, 180), m_card, border_radius=5)
                    pygame.draw.rect(surface, (51, 65, 85), m_card, width=1, border_radius=5)

                    # Icon & Name
                    m_info = f"{m.full_name}  ({m.role}, Age {m.age}, {m.gender})"
                    name_col = (241, 245, 249) if getattr(m, "is_alive", True) else (148, 163, 184)
                    surface.blit(self.font_body.render(m_info, True, name_col), (m_card.x + 12, m_card.y + 6))

                    # Needs & Living Status Indicator
                    if not getattr(m, "is_alive", True):
                        d_lbl = self.font_badge.render(f"[DECEASED: {getattr(m, 'death_reason', 'Starvation')}]", True, (239, 68, 68))
                        surface.blit(d_lbl, (m_card.right - 370, m_card.y + 7))
                    else:
                        h_val = int(getattr(m, "hunger", 100.0))
                        t_val = int(getattr(m, "thirst", 100.0))
                        need_col = (239, 68, 68) if min(h_val, t_val) <= 20 else ((245, 158, 11) if min(h_val, t_val) <= 50 else (148, 163, 184))
                        n_lbl = self.font_badge.render(f"H: {h_val}% | T: {t_val}%", True, need_col)
                        surface.blit(n_lbl, (m_card.right - 340, m_card.y + 7))


                    # Dedicated Job Badge
                    job_cfg = DEDICATED_JOBS.get(getattr(m, "job", "Farmer"), {})
                    job_title = job_cfg.get("title", getattr(m, "job", "Worker"))
                    job_badge = pygame.Rect(m_card.right - 230, m_card.y + 4, 110, 22)
                    pygame.draw.rect(surface, (20, 83, 45), job_badge, border_radius=4)
                    pygame.draw.rect(surface, (34, 197, 94), job_badge, width=1, border_radius=4)
                    j_txt = self.font_badge.render(job_title, True, (240, 253, 244))
                    surface.blit(j_txt, (job_badge.centerx - j_txt.get_width() // 2, job_badge.centery - j_txt.get_height() // 2))

                    # [🎒 Inventory] Button
                    inv_btn = pygame.Rect(m_card.right - 114, m_card.y + 4, 106, 22)
                    self.member_inventory_btn_rects[m.id] = inv_btn
                    i_hov = inv_btn.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (37, 99, 235) if i_hov else (30, 58, 138), inv_btn, border_radius=4)
                    pygame.draw.rect(surface, (96, 165, 250), inv_btn, width=1, border_radius=4)
                    i_txt = self.font_badge.render("Inventory", True, (255, 255, 255))
                    surface.blit(i_txt, (inv_btn.centerx - i_txt.get_width() // 2, inv_btn.centery - i_txt.get_height() // 2))

                    y_cur += 34
                y_cur += 6

            # Housing Lot Deed Picker Dropdown/Modal (Drawn as an Overlay on Top of the Roster)
            self.assign_permit_btn_rects = {}
            if self.show_assign_permit_picker:
                picker_w = 420
                housing_permits = [p for p in permit_manager.permits if p.permit_type in ["housing", "landlord_private"]]
                picker_h = max(70, min(240, len(housing_permits) * 36 + 46))
                picker_x = banner_rect.right - picker_w
                picker_y = banner_rect.bottom + 4
                self.deed_picker_bg_rect = pygame.Rect(picker_x, picker_y, picker_w, picker_h)

                # Shadow
                shadow_surf = pygame.Surface((picker_w, picker_h), pygame.SRCALPHA)
                pygame.draw.rect(shadow_surf, (0, 0, 0, 180), (0, 0, picker_w, picker_h), border_radius=8)
                surface.blit(shadow_surf, (picker_x + 4, picker_y + 4))

                # Background & Border
                pygame.draw.rect(surface, (15, 23, 42), self.deed_picker_bg_rect, border_radius=8)
                pygame.draw.rect(surface, (59, 130, 246), self.deed_picker_bg_rect, width=2, border_radius=8)

                p_header = self.font_badge.render("SELECT HOUSING PERMIT DEED FOR THIS FAMILY:", True, (56, 189, 248))
                surface.blit(p_header, (picker_x + 14, picker_y + 12))

                # Close [✕] button
                self.close_deed_picker_btn_rect = pygame.Rect(picker_x + picker_w - 28, picker_y + 10, 18, 18)
                pygame.draw.rect(surface, (220, 38, 38), self.close_deed_picker_btn_rect, border_radius=3)
                x_lbl = self.font_badge.render("X", True, (255, 255, 255))
                surface.blit(x_lbl, (self.close_deed_picker_btn_rect.x + 4, self.close_deed_picker_btn_rect.y + 2))

                row_y = picker_y + 36
                if not housing_permits:
                    none_txt = self.font_body.render("- No Housing Permits issued. Issue one first in Area Permits tab!", True, (239, 68, 68))
                    surface.blit(none_txt, (picker_x + 14, row_y + 4))
                else:
                    for p in housing_permits:
                        occupant = next((f for f in villager_manager.families if f.assigned_permit_id == p.id and f.id != fam.id), None) if villager_manager else None
                        p_btn = pygame.Rect(picker_x + 10, row_y, picker_w - 20, 28)

                        if occupant:
                            # Occupied by another family! Cannot be assigned unless revoked first!
                            pygame.draw.rect(surface, (30, 20, 25), p_btn, border_radius=4)
                            pygame.draw.rect(surface, (127, 29, 29), p_btn, width=1, border_radius=4)
                            occ_txt = self.font_badge.render(f"[Occupied] {p.name} - Occupied by The {occupant.surname}s (Revoke first)", True, (248, 113, 113))
                            surface.blit(occ_txt, (p_btn.x + 12, p_btn.y + 7))
                        elif p.id == fam.assigned_permit_id:
                            # Already this family's current permit
                            pygame.draw.rect(surface, (20, 83, 45), p_btn, border_radius=4)
                            pygame.draw.rect(surface, (34, 197, 94), p_btn, width=1, border_radius=4)
                            curr_txt = self.font_badge.render(f"Current Deed: {p.name} ({len(p.tiles)} tiles)", True, (240, 253, 244))
                            surface.blit(curr_txt, (p_btn.x + 12, p_btn.y + 7))
                        else:
                            # Vacant - can be assigned!
                            self.assign_permit_btn_rects[p.id] = p_btn
                            p_hov = p_btn.collidepoint(mouse_pos)
                            pygame.draw.rect(surface, (37, 99, 235) if p_hov else (30, 41, 59), p_btn, border_radius=4)
                            pygame.draw.rect(surface, (96, 165, 250), p_btn, width=1, border_radius=4)
                            p_txt = self.font_badge.render(f"Grant {p.name} ({len(p.tiles)} tiles)", True, (255, 255, 255))
                            surface.blit(p_txt, (p_btn.x + 12, p_btn.y + 7))

                        row_y += 34

            # Member Individual Inventory Modal Overlay
            if self.selected_member_inventory_id is not None:
                mem_obj = next((m for m in fam.members if m.id == self.selected_member_inventory_id), None)
                if mem_obj:
                    self._draw_member_inventory_dialog(surface, mem_obj, fam, furniture_manager, stockpile_manager, mouse_pos)

    def _draw_member_inventory_dialog(self, surface, member, fam, furniture_manager, stockpile_manager, mouse_pos):
        screen_w, screen_h = surface.get_size()
        dim_surf = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        dim_surf.fill((0, 0, 0, 160))
        surface.blit(dim_surf, (0, 0))

        inv = member.inventory
        carrying = getattr(member, "carrying_crop", 0)
        items = list(inv.items())
        if carrying > 0:
            items.insert(0, ("Potato (Harvest)", carrying))

        dlg_w = min(540, screen_w - 40)
        items_cnt = len(items) if items else 1
        needed_h = 150 + items_cnt * 44 + 36
        dlg_h = min(max(320, needed_h), int(screen_h * 0.85))
        dx = (screen_w - dlg_w) // 2
        dy = (screen_h - dlg_h) // 2
        self.member_inv_bg_rect = pygame.Rect(dx, dy, dlg_w, dlg_h)

        pygame.draw.rect(surface, (15, 23, 42), self.member_inv_bg_rect, border_radius=10)
        pygame.draw.rect(surface, (59, 130, 246), self.member_inv_bg_rect, width=2, border_radius=10)

        # Title
        title_surf = self.font_sub.render(f"Personal Profile & Inventory: {member.full_name}", True, (241, 245, 249))
        surface.blit(title_surf, (dx + 20, dy + 14))

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
        surface.blit(st_badge, (dx + dlg_w - 38 - st_badge.get_width(), dy + 16))

        # Close [✕] button
        self.close_member_inv_btn_rect = pygame.Rect(dx + dlg_w - 32, dy + 14, 20, 20)
        c_hov = self.close_member_inv_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (239, 68, 68) if c_hov else (30, 41, 59), self.close_member_inv_btn_rect, border_radius=4)
        c_txt = self.font_badge.render("X", True, (255, 255, 255))
        surface.blit(c_txt, (self.close_member_inv_btn_rect.centerx - c_txt.get_width() // 2, self.close_member_inv_btn_rect.centery - c_txt.get_height() // 2))

        # Member details banner
        info_str = f"Role: {member.role}  |  Age: {member.age}  |  Household: The {fam.surname} Family  |  Job: {getattr(member, 'job', 'Farmer')}"
        surface.blit(self.font_body.render(info_str, True, (56, 189, 248)), (dx + 20, dy + 38))

        # Needs Status Bars (Hunger & Thirst)
        h_val = max(0.0, min(100.0, getattr(member, "hunger", 100.0)))
        t_val = max(0.0, min(100.0, getattr(member, "thirst", 100.0)))

        # Hunger Bar
        surface.blit(self.font_badge.render("Hunger:", True, (241, 245, 249)), (dx + 20, dy + 58))
        h_bar_bg = pygame.Rect(dx + 74, dy + 58, 120, 14)
        pygame.draw.rect(surface, (30, 41, 59), h_bar_bg, border_radius=4)
        h_fill_w = max(0, int(120 * (h_val / 100.0)))
        if h_fill_w > 0:
            h_col = (34, 197, 94) if h_val > 50 else ((234, 179, 8) if h_val > 20 else (239, 68, 68))
            pygame.draw.rect(surface, h_col, (dx + 74, dy + 58, h_fill_w, 14), border_radius=4)
        pygame.draw.rect(surface, (71, 85, 105), h_bar_bg, width=1, border_radius=4)
        h_txt_str = f"{int(h_val)}%" if h_timer is None else f"{int(h_val)}% ({h_timer:.1f}h)"
        h_pct = self.font_badge.render(h_txt_str, True, (255, 255, 255) if h_timer is None else (239, 68, 68))
        surface.blit(h_pct, (dx + 200, dy + 58))

        # Thirst Bar
        surface.blit(self.font_badge.render("Thirst:", True, (241, 245, 249)), (dx + 276, dy + 58))
        t_bar_bg = pygame.Rect(dx + 322, dy + 58, 120, 14)
        pygame.draw.rect(surface, (30, 41, 59), t_bar_bg, border_radius=4)
        t_fill_w = max(0, int(120 * (t_val / 100.0)))
        if t_fill_w > 0:
            t_col = (56, 189, 248) if t_val > 50 else ((59, 130, 246) if t_val > 20 else (239, 68, 68))
            pygame.draw.rect(surface, t_col, (dx + 322, dy + 58, t_fill_w, 14), border_radius=4)
        pygame.draw.rect(surface, (71, 85, 105), t_bar_bg, width=1, border_radius=4)
        t_txt_str = f"{int(t_val)}%" if t_timer is None else f"{int(t_val)}% ({t_timer:.1f}h)"
        t_pct = self.font_badge.render(t_txt_str, True, (255, 255, 255) if t_timer is None else (239, 68, 68))
        surface.blit(t_pct, (dx + 448, dy + 58))

        # Bed Status & Active tool
        bed_status = f"Assigned Bed:  {member.assigned_bed_id}" if getattr(member, 'assigned_bed_id', None) else " Bed: None (Sleeping on Floor)"
        tool_status = f"Active Tool:  {member.active_tool or 'None'}"
        water_status = "Water: Full" if member.has_water else "Water: Empty"
        status_line = f"{bed_status}  •  {tool_status}  •  {water_status}"
        surface.blit(self.font_badge.render(status_line, True, (148, 163, 184)), (dx + 20, dy + 78))

        pygame.draw.line(surface, (51, 65, 85), (dx + 20, dy + 98), (dx + dlg_w - 20, dy + 98), 1)

        self.member_deposit_btn_rects.clear()
        self.member_drop_btn_rects.clear()

        has_chest = (furniture_manager.get_storage_for_family(fam.id) is not None) if furniture_manager else False

        y_item = dy + 108

        if not items:
            empty_lbl = self.font_body.render("— Personal inventory is currently empty (Hands/Bag free) —", True, (100, 116, 139))
            surface.blit(empty_lbl, (dx + 20, y_item + 20))
        else:
            for item_name, count in items:
                row_rect = pygame.Rect(dx + 20, y_item, dlg_w - 40, 36)
                pygame.draw.rect(surface, (30, 41, 59), row_rect, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), row_rect, width=1, border_radius=6)

                draw_item_icon(surface, item_name, row_rect.x + 24, row_rect.y + 18, size=10)
                item_lbl = self.font_body.render(f"{item_name}  × {count}", True, (241, 245, 249))
                surface.blit(item_lbl, (row_rect.x + 42, row_rect.y + 9))

                # Buttons: [Deposit to Chest] & [Drop to Ground]
                if item_name in inv and inv[item_name] > 0:
                    btn_x = row_rect.right - 10
                    # Drop button
                    drop_btn = pygame.Rect(btn_x - 70, row_rect.y + 6, 70, 24)
                    self.member_drop_btn_rects[item_name] = drop_btn
                    d_hov = drop_btn.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (185, 28, 28) if d_hov else (127, 29, 29), drop_btn, border_radius=4)
                    d_txt = self.font_badge.render("Drop", True, (255, 255, 255))
                    surface.blit(d_txt, (drop_btn.centerx - d_txt.get_width() // 2, drop_btn.centery - d_txt.get_height() // 2))

                    # Deposit button
                    if has_chest:
                        dep_btn = pygame.Rect(drop_btn.x - 110, row_rect.y + 6, 102, 24)
                        self.member_deposit_btn_rects[item_name] = dep_btn
                        dp_hov = dep_btn.collidepoint(mouse_pos)
                        pygame.draw.rect(surface, (16, 185, 129) if dp_hov else (5, 150, 105), dep_btn, border_radius=4)
                        dp_txt = self.font_badge.render("To Chest", True, (255, 255, 255))
                        surface.blit(dp_txt, (dep_btn.centerx - dp_txt.get_width() // 2, dep_btn.centery - dp_txt.get_height() // 2))

                y_item += 42

        # Footer explanation
        foot_y = dy + dlg_h - 36
        note = self.font_badge.render("Items in personal inventory are immediately available for this member to work with.", True, (148, 163, 184))
        surface.blit(note, (dx + 20, foot_y))

    def _draw_workers_tab(self, surface, mx, cy, villager_manager, permit_manager):
        mouse_pos = pygame.mouse.get_pos()

        # =============================================================
        # VIEW 1: Dedicated Jobs Directory
        # =============================================================
        if self.selected_job_id is None:
            # Title
            w_title = self.font_title.render("VILLAGE WORKFORCE & JOBS DIRECTORY", True, COLOR_TEXT_TITLE)
            surface.blit(w_title, (mx + 24, cy - 4))

            # Auto Sort All Button (Top Right)
            self.auto_sort_all_btn_rect = pygame.Rect(mx + self.modal_w - 200, cy - 6, 176, 28)
            as_hover = self.auto_sort_all_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (16, 185, 129) if as_hover else (5, 150, 105), self.auto_sort_all_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (52, 211, 153), self.auto_sort_all_btn_rect, width=1, border_radius=6)
            as_lbl = self.font_badge.render("Auto Sort All Workers", True, (255, 255, 255))
            surface.blit(as_lbl, (self.auto_sort_all_btn_rect.centerx - as_lbl.get_width() // 2, self.auto_sort_all_btn_rect.centery - as_lbl.get_height() // 2))

            sub_txt = self.font_body.render("Job roles dictate villager daily routines. Workers prioritize nearest designated lots.", True, COLOR_TEXT_MUTED)
            surface.blit(sub_txt, (mx + 24, cy + 22))

            y_cur = cy + 46
            self.job_select_btn_rects = {}
            self.job_schedule_btn_rects = {}

            all_vils = villager_manager.get_all_villagers() if villager_manager else []

            for job_id, job_cfg in DEDICATED_JOBS.items():
                card_h = 58
                card_rect = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, card_h)
                is_wip = job_cfg.get("wip", False)

                pygame.draw.rect(surface, (24, 34, 52), card_rect, border_radius=8)
                pygame.draw.rect(surface, (51, 65, 85), card_rect, width=1, border_radius=8)

                # Icon circle
                icon_col = (71, 85, 105) if is_wip else (34, 197, 94)
                pygame.draw.circle(surface, icon_col, (card_rect.x + 24, card_rect.y + card_h // 2), 12)
                pygame.draw.circle(surface, (15, 23, 42), (card_rect.x + 24, card_rect.y + card_h // 2), 12, 2)

                # Title
                j_title = self.font_sub.render(job_cfg["name"], True, (241, 245, 249) if not is_wip else COLOR_TEXT_MUTED)
                surface.blit(j_title, (card_rect.x + 46, card_rect.y + 8))

                if is_wip:
                    # WIP Badge
                    wip_b = pygame.Rect(card_rect.x + 46 + j_title.get_width() + 12, card_rect.y + 10, 48, 16)
                    pygame.draw.rect(surface, COLOR_BADGE_WIP, wip_b, border_radius=3)
                    surface.blit(self.font_badge.render("WIP", True, (0, 0, 0)), (wip_b.x + 13, wip_b.y + 1))

                    desc = self.font_body.render(job_cfg.get("desc", "Guild profession in development."), True, COLOR_TEXT_MUTED)
                    surface.blit(desc, (card_rect.x + 46, card_rect.y + 30))
                else:
                    # Calculate active workers
                    job_vils = [v for v in all_vils if v.job == job_id]
                    assigned_vils = [v for v in job_vils if any(v.id in getattr(p, "assigned_workers", set()) for p in permit_manager.permits)]
                    unassigned_count = len(job_vils) - len(assigned_vils)

                    job_desc = job_cfg.get("desc", "Guild duties")
                    stat_str = f"Workforce: {len(assigned_vils)}/{len(job_vils)} Assigned ({unassigned_count} Idle) — {job_desc}"
                    if len(stat_str) > 75:
                        stat_str = stat_str[:72] + "..."
                    surface.blit(self.font_body.render(stat_str, True, (34, 197, 94) if unassigned_count == 0 else (245, 158, 11)), (card_rect.x + 46, card_rect.y + 30))

                    # Action Buttons: [View Workers] and [Edit Schedule]
                    btn_w = 110
                    btn_h = 30
                    btn_y = card_rect.y + 14

                    # 1. View Workers Button
                    vw_rect = pygame.Rect(card_rect.right - 14 - (btn_w * 2 + 10), btn_y, btn_w, btn_h)
                    self.job_select_btn_rects[job_id] = vw_rect
                    vw_hover = vw_rect.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (37, 99, 235) if vw_hover else (30, 58, 138), vw_rect, border_radius=6)
                    pygame.draw.rect(surface, (96, 165, 250), vw_rect, width=1, border_radius=6)
                    vw_lbl = self.font_badge.render("View Workers", True, (255, 255, 255))
                    surface.blit(vw_lbl, (vw_rect.centerx - vw_lbl.get_width() // 2, vw_rect.centery - vw_lbl.get_height() // 2))

                    # 2. Edit Schedule Button
                    es_rect = pygame.Rect(card_rect.right - 14 - btn_w, btn_y, btn_w, btn_h)
                    self.job_schedule_btn_rects[job_id] = es_rect
                    es_hover = es_rect.collidepoint(mouse_pos)
                    pygame.draw.rect(surface, (14, 116, 144) if es_hover else (15, 23, 42), es_rect, border_radius=6)
                    pygame.draw.rect(surface, (56, 189, 248), es_rect, width=1, border_radius=6)
                    es_lbl = self.font_badge.render("Edit Schedule", True, (255, 255, 255))
                    surface.blit(es_lbl, (es_rect.centerx - es_lbl.get_width() // 2, es_rect.centery - es_lbl.get_height() // 2))

                y_cur += card_h + 8

        # =============================================================
        # VIEW 2: Individual Workers Roster for Selected Job
        # =============================================================
        else:
            job_cfg = DEDICATED_JOBS.get(self.selected_job_id, {})
            job_name = job_cfg.get("name", self.selected_job_id)

            # Header & Back Button
            back_w = 140
            self.back_to_jobs_btn_rect = pygame.Rect(mx + 24, cy - 4, back_w, 28)
            b_hover = self.back_to_jobs_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (51, 65, 85) if b_hover else (30, 41, 59), self.back_to_jobs_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (96, 165, 250), self.back_to_jobs_btn_rect, width=1, border_radius=6)

            back_lbl = self.font_badge.render("< Back to Jobs", True, (255, 255, 255))
            surface.blit(back_lbl, (self.back_to_jobs_btn_rect.centerx - back_lbl.get_width() // 2, self.back_to_jobs_btn_rect.centery - back_lbl.get_height() // 2))

            j_title = self.font_title.render(f"{job_name} Workforce", True, (241, 245, 249))
            surface.blit(j_title, (mx + 24 + back_w + 14, cy - 4))

            # Auto Sort Button for this Job
            self.auto_sort_all_btn_rect = pygame.Rect(mx + self.modal_w - 180, cy - 4, 156, 28)
            as_hover = self.auto_sort_all_btn_rect.collidepoint(mouse_pos)
            pygame.draw.rect(surface, (16, 185, 129) if as_hover else (5, 150, 105), self.auto_sort_all_btn_rect, border_radius=6)
            pygame.draw.rect(surface, (52, 211, 153), self.auto_sort_all_btn_rect, width=1, border_radius=6)
            as_lbl = self.font_badge.render("Auto Sort Closest", True, (255, 255, 255))
            surface.blit(as_lbl, (self.auto_sort_all_btn_rect.centerx - as_lbl.get_width() // 2, self.auto_sort_all_btn_rect.centery - as_lbl.get_height() // 2))

            all_vils = villager_manager.get_all_villagers() if villager_manager else []
            job_vils = [v for v in all_vils if v.job == self.selected_job_id]

            # Summary banner
            assigned_vils = [v for v in job_vils if any(v.id in getattr(p, "assigned_workers", set()) for p in permit_manager.permits)]
            unassigned_count = len(job_vils) - len(assigned_vils)

            banner_y = cy + 32
            banner_rect = pygame.Rect(mx + 24, banner_y, self.modal_w - 48, 32)
            pygame.draw.rect(surface, (24, 34, 52), banner_rect, border_radius=6)
            pygame.draw.rect(surface, (71, 85, 105), banner_rect, width=1, border_radius=6)

            stat_txt = f"Total: {len(job_vils)} Workers   |   Assigned: {len(assigned_vils)}   |   Unassigned / Idle: {unassigned_count}"
            surface.blit(self.font_sub.render(stat_txt, True, (56, 189, 248)), (banner_rect.x + 14, banner_rect.y + 8))

            y_cur = banner_y + 40
            self.worker_assign_btn_rects = {}
            self.worker_unassign_btn_rects = {}

            if not job_vils:
                none_txt = self.font_body.render("- No villagers registered for this job yet. Add families in the Villagers tab!", True, COLOR_TEXT_MUTED)
                surface.blit(none_txt, (mx + 36, y_cur + 10))
            else:
                for v in job_vils:
                    card = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 32)
                    pygame.draw.rect(surface, (15, 23, 42, 180), card, border_radius=5)
                    pygame.draw.rect(surface, (51, 65, 85), card, width=1, border_radius=5)

                    # Info
                    fam = villager_manager.get_family_by_id(v.family_id) if villager_manager else None
                    fam_name = f"The {fam.surname} Family" if fam else "No Family"
                    info_str = f"{v.full_name} ({v.role}, {fam_name})"
                    surface.blit(self.font_body.render(info_str, True, (241, 245, 249)), (card.x + 12, card.y + 7))

                    # Find assigned permit
                    p_assigned = next((p for p in permit_manager.permits if v.id in getattr(p, "assigned_workers", set())), None)
                    if p_assigned:
                        status_str = f"Assigned:  {p_assigned.name}"
                        surface.blit(self.font_body.render(status_str, True, (34, 197, 94)), (card.x + 310, card.y + 7))

                        # Unassign Button
                        un_btn = pygame.Rect(card.right - 94, card.y + 4, 84, 24)
                        self.worker_unassign_btn_rects[(p_assigned.id, v.id)] = un_btn
                        u_hover = un_btn.collidepoint(mouse_pos)
                        pygame.draw.rect(surface, (220, 38, 38) if u_hover else (153, 27, 27), un_btn, border_radius=4)
                        u_lbl = self.font_badge.render("Unassign", True, (255, 255, 255))
                        surface.blit(u_lbl, (un_btn.centerx - u_lbl.get_width() // 2, un_btn.centery - u_lbl.get_height() // 2))
                    else:
                        status_str = "Idle (Unassigned)"
                        surface.blit(self.font_body.render(status_str, True, (245, 158, 11)), (card.x + 310, card.y + 7))

                        # Assign Nearest Button
                        as_btn = pygame.Rect(card.right - 110, card.y + 4, 100, 24)
                        self.worker_assign_btn_rects[v.id] = as_btn
                        a_hover = as_btn.collidepoint(mouse_pos)
                        pygame.draw.rect(surface, (37, 99, 235) if a_hover else (30, 58, 138), as_btn, border_radius=4)
                        a_lbl = self.font_badge.render("+ Assign Slot", True, (255, 255, 255))
                        surface.blit(a_lbl, (as_btn.centerx - a_lbl.get_width() // 2, as_btn.centery - a_lbl.get_height() // 2))

                    y_cur += 36

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
        dlg_w = min(600, max(460, screen_w - 40))

        # Dynamically build grantable items list (Standard items + any extra items currently in landlord stock)
        grantable = list(GRANTABLE_ITEMS)
        existing_types = {it["type"] for it in grantable}
        for st_type, st_qty in stock.items():
            if st_type not in existing_types and st_qty > 0:
                grantable.append({"type": st_type, "name": canonical_item_name(st_type)})

        # Layout metrics
        header_h = 76
        footer_h = 66
        row_h = 44
        row_gap = 8
        row_step = row_h + row_gap
        num_items = len(grantable)
        total_items_h = num_items * row_step

        # Max modal height allowed relative to viewport
        max_dlg_h = min(int(screen_h * 0.88), 680)

        # Dynamic height calculation
        needed_dlg_h = header_h + total_items_h + footer_h + 8
        if needed_dlg_h <= max_dlg_h:
            dlg_h = needed_dlg_h
            viewport_h = total_items_h + 8
        else:
            dlg_h = max_dlg_h
            viewport_h = dlg_h - header_h - footer_h

        dlg_x = (screen_w - dlg_w) // 2
        dlg_y = (screen_h - dlg_h) // 2
        dlg_rect = pygame.Rect(dlg_x, dlg_y, dlg_w, dlg_h)
        self.grant_dlg_rect = dlg_rect

        # Draw Modal Container Box
        pygame.draw.rect(surface, (15, 23, 42), dlg_rect, border_radius=10)
        pygame.draw.rect(surface, (59, 130, 246), dlg_rect, width=2, border_radius=10)

        # -------------------------------------------------------------
        # 1. HEADER (Title, Subtitle & Header Close [X] Button)
        # -------------------------------------------------------------
        t_surf = self.font_title.render(f"Grant Supplies:  The {fam.surname} Family", True, (241, 245, 249))
        surface.blit(t_surf, (dlg_x + 24, dlg_y + 18))
        sub_surf = self.font_body.render("Select supplies from Landlord Storage for AI Servants to haul & deliver.", True, (148, 163, 184))
        surface.blit(sub_surf, (dlg_x + 24, dlg_y + 46))

        # Header Close [X] Button
        self.grant_header_close_btn_rect = pygame.Rect(dlg_x + dlg_w - 36, dlg_y + 16, 22, 22)
        x_hov = self.grant_header_close_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (239, 68, 68) if x_hov else (30, 41, 59), self.grant_header_close_btn_rect, border_radius=4)
        x_lbl = self.font_badge.render("X", True, (255, 255, 255))
        surface.blit(x_lbl, (self.grant_header_close_btn_rect.centerx - x_lbl.get_width() // 2, self.grant_header_close_btn_rect.centery - x_lbl.get_height() // 2))

        # Header Separator
        pygame.draw.line(surface, (51, 65, 85), (dlg_x + 20, dlg_y + header_h - 4), (dlg_x + dlg_w - 20, dlg_y + header_h - 4), 1)

        # -------------------------------------------------------------
        # 2. SCROLLABLE CONTENT VIEWPORT
        # -------------------------------------------------------------
        viewport_y = dlg_y + header_h
        viewport_rect = pygame.Rect(dlg_x + 16, viewport_y, dlg_w - 32, viewport_h)
        self.grant_viewport_rect = viewport_rect

        # Max scroll calculation
        max_scroll = max(0, total_items_h - viewport_h + 8)
        self.grant_max_scroll = max_scroll
        self.grant_scroll_y = max(0, min(self.grant_scroll_y, max_scroll))

        has_scrollbar = (max_scroll > 0)
        content_margin_right = 16 if has_scrollbar else 4
        item_row_w = viewport_rect.w - 8 - content_margin_right

        self.grant_dec_btn_rects.clear()
        self.grant_inc_btn_rects.clear()
        self.grant_max_btn_rects.clear()
        self.grant_item_qty_rects.clear()

        # Scissor clipping to parent container: no item row can render outside viewport!
        old_clip = surface.get_clip()
        surface.set_clip(viewport_rect)

        start_row_y = viewport_y + 4 - self.grant_scroll_y

        for idx, item_data in enumerate(grantable):
            it_type = item_data["type"]
            it_name = item_data["name"]
            avail = stock.get(it_type, 0)
            qty = self.grant_amounts.get(it_type, 0)

            cur_row_y = start_row_y + idx * row_step

            # Culling optimization: skip rows completely outside the visible viewport
            if cur_row_y + row_h < viewport_y or cur_row_y > viewport_y + viewport_h:
                continue

            row_rect = pygame.Rect(viewport_rect.x + 4, cur_row_y, item_row_w, row_h)
            pygame.draw.rect(surface, (30, 41, 59), row_rect, border_radius=6)
            pygame.draw.rect(surface, (51, 65, 85), row_rect, width=1, border_radius=6)

            # Icon & Name
            draw_item_icon(surface, it_name, row_rect.x + 20, cur_row_y + 22, size=11)
            name_s = self.font_sub.render(it_name, True, (241, 245, 249))
            surface.blit(name_s, (row_rect.x + 44, cur_row_y + 11))

            # Available in Stockpile
            stk_color = (34, 197, 94) if avail > 0 else (148, 163, 184)
            stk_s = self.font_body.render(f"In Storage: {avail}", True, stk_color)
            surface.blit(stk_s, (row_rect.x + 180, cur_row_y + 13))

            # Controls: [-] [ QTY ] [+] [Max]
            ctrl_rx = row_rect.right - 240
            
            # Minus button
            minus_r = pygame.Rect(ctrl_rx, cur_row_y + 8, 30, 28)
            if viewport_rect.collidepoint(minus_r.center):
                self.grant_dec_btn_rects[it_type] = minus_r
            m_hov = minus_r.collidepoint(mouse_pos) if viewport_rect.collidepoint(mouse_pos) else False
            pygame.draw.rect(surface, (51, 65, 85) if m_hov else (30, 41, 59), minus_r, border_radius=4)
            pygame.draw.rect(surface, (96, 165, 250), minus_r, width=1, border_radius=4)
            m_txt = self.font_sub.render("-", True, (255, 255, 255))
            surface.blit(m_txt, (minus_r.centerx - m_txt.get_width() // 2, minus_r.centery - m_txt.get_height() // 2))

            # Quantity Display / Input box
            qty_r = pygame.Rect(ctrl_rx + 36, cur_row_y + 8, 60, 28)
            if viewport_rect.collidepoint(qty_r.center):
                self.grant_item_qty_rects[it_type] = qty_r
            is_active_input = (self.active_grant_input_item == it_type)
            box_bg = (15, 23, 42) if not is_active_input else (30, 58, 138)
            border_c = (250, 204, 21) if is_active_input else (71, 85, 105)
            pygame.draw.rect(surface, box_bg, qty_r, border_radius=4)
            pygame.draw.rect(surface, border_c, qty_r, width=2 if is_active_input else 1, border_radius=4)
            
            disp_txt = str(qty) if not is_active_input else (self.grant_input_text or "0")
            q_color = (250, 204, 21) if qty > 0 else (148, 163, 184)
            q_txt = self.font_sub.render(disp_txt, True, q_color)
            surface.blit(q_txt, (qty_r.centerx - q_txt.get_width() // 2, qty_r.centery - q_txt.get_height() // 2))

            # Plus button
            plus_r = pygame.Rect(ctrl_rx + 102, cur_row_y + 8, 30, 28)
            if viewport_rect.collidepoint(plus_r.center):
                self.grant_inc_btn_rects[it_type] = plus_r
            p_hov = plus_r.collidepoint(mouse_pos) if viewport_rect.collidepoint(mouse_pos) else False
            pygame.draw.rect(surface, (51, 65, 85) if p_hov else (30, 41, 59), plus_r, border_radius=4)
            pygame.draw.rect(surface, (96, 165, 250), plus_r, width=1, border_radius=4)
            p_txt = self.font_sub.render("+", True, (255, 255, 255))
            surface.blit(p_txt, (plus_r.centerx - p_txt.get_width() // 2, plus_r.centery - p_txt.get_height() // 2))

            # Max button
            max_r = pygame.Rect(ctrl_rx + 138, cur_row_y + 8, 52, 28)
            if viewport_rect.collidepoint(max_r.center):
                self.grant_max_btn_rects[it_type] = max_r
            max_hov = max_r.collidepoint(mouse_pos) if viewport_rect.collidepoint(mouse_pos) else False
            pygame.draw.rect(surface, (71, 85, 105) if max_hov else (51, 65, 85), max_r, border_radius=4)
            pygame.draw.rect(surface, (148, 163, 184), max_r, width=1, border_radius=4)
            max_txt = self.font_badge.render("Max", True, (241, 245, 249))
            surface.blit(max_txt, (max_r.centerx - max_txt.get_width() // 2, max_r.centery - max_txt.get_height() // 2))

        # Restore normal clipping
        surface.set_clip(old_clip)

        # -------------------------------------------------------------
        # 3. SCROLLBAR (if content exceeds viewport)
        # -------------------------------------------------------------
        if has_scrollbar:
            sb_x = dlg_x + dlg_w - 24
            sb_y = viewport_y + 4
            sb_w = 6
            sb_h = viewport_h - 8
            self.grant_scrollbar_rect = pygame.Rect(sb_x - 3, sb_y, sb_w + 6, sb_h)
            pygame.draw.rect(surface, (30, 41, 59), (sb_x, sb_y, sb_w, sb_h), border_radius=3)
            
            thumb_h = max(24, int(sb_h * (viewport_h / total_items_h)))
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
        footer_bg = pygame.Rect(dlg_x + 2, footer_y, dlg_w - 4, footer_h - 2)
        pygame.draw.rect(surface, (15, 23, 42), footer_bg, border_bottom_left_radius=10, border_bottom_right_radius=10)
        pygame.draw.line(surface, (51, 65, 85), (dlg_x + 20, footer_y), (dlg_x + dlg_w - 20, footer_y), 1)

        total_grant = sum(self.grant_amounts.values())
        btn_y = footer_y + 15

        # Grant Button
        self.grant_submit_btn_rect = pygame.Rect(dlg_x + 20, btn_y, 240, 36)
        s_hov = self.grant_submit_btn_rect.collidepoint(mouse_pos)
        can_grant = total_grant > 0
        s_bg = (22, 101, 52) if (can_grant and not s_hov) else ((21, 128, 61) if can_grant else (51, 65, 85))
        pygame.draw.rect(surface, s_bg, self.grant_submit_btn_rect, border_radius=6)
        pygame.draw.rect(surface, (74, 222, 128) if can_grant else (71, 85, 105), self.grant_submit_btn_rect, width=1, border_radius=6)
        sub_lbl = self.font_sub.render(f"Grant ({total_grant} items)", True, (255, 255, 255) if can_grant else (148, 163, 184))
        surface.blit(sub_lbl, (self.grant_submit_btn_rect.centerx - sub_lbl.get_width() // 2, self.grant_submit_btn_rect.centery - sub_lbl.get_height() // 2))

        # Cancel Button
        self.grant_close_btn_rect = pygame.Rect(dlg_x + dlg_w - 20 - 130, btn_y, 130, 36)
        c_hov = self.grant_close_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (71, 85, 105) if c_hov else (30, 41, 59), self.grant_close_btn_rect, border_radius=6)
        pygame.draw.rect(surface, (148, 163, 184), self.grant_close_btn_rect, width=1, border_radius=6)
        c_lbl = self.font_sub.render("Cancel", True, (241, 245, 249))
        surface.blit(c_lbl, (self.grant_close_btn_rect.centerx - c_lbl.get_width() // 2, self.grant_close_btn_rect.centery - c_lbl.get_height() // 2))

    def _draw_grant_confirm(self, surface, fam, mouse_pos):
        self._init_fonts()
        screen_w, screen_h = surface.get_size()
        overlay = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        cf_w = min(520, max(440, screen_w - 40))

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

        pygame.draw.rect(surface, (15, 23, 42), cf_rect, border_radius=10)
        pygame.draw.rect(surface, (245, 158, 11), cf_rect, width=2, border_radius=10)

        # Title
        t_s = self.font_title.render("Confirm Royal Grant Decree", True, (250, 204, 21))
        surface.blit(t_s, (cf_x + 24, cf_y + 18))

        # Question
        q_s = self.font_sub.render(f"Are you sure you want to grant these items to The {fam.surname} Family?", True, (241, 245, 249))
        surface.blit(q_s, (cf_x + 24, cf_y + 48))

        # Summary lines
        line_y = cf_y + 78
        for s_line in summary_lines:
            sum_s = self.font_body.render(s_line, True, (34, 197, 94))
            surface.blit(sum_s, (cf_x + 24, line_y))
            line_y += 20

        # Hauling notice
        notice_s = self.font_body.render("• AI Servants will fetch items from Landlord storage and haul them to the household.", True, (148, 163, 184))
        surface.blit(notice_s, (cf_x + 24, line_y + 6))

        # Action Buttons: [✓ Yes, Grant] and [✕ Cancel]
        btn_y = cf_y + cf_h - 52

        self.grant_confirm_btn_rect = pygame.Rect(cf_x + 24, btn_y, 180, 36)
        yes_hov = self.grant_confirm_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (22, 101, 52) if yes_hov else (21, 128, 61), self.grant_confirm_btn_rect, border_radius=6)
        pygame.draw.rect(surface, (74, 222, 128), self.grant_confirm_btn_rect, width=1, border_radius=6)
        yes_s = self.font_sub.render("Yes, Grant", True, (255, 255, 255))
        surface.blit(yes_s, (self.grant_confirm_btn_rect.centerx - yes_s.get_width() // 2, self.grant_confirm_btn_rect.centery - yes_s.get_height() // 2))

        self.grant_cancel_btn_rect = pygame.Rect(cf_x + cf_w - 24 - 130, btn_y, 130, 36)
        no_hov = self.grant_cancel_btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(surface, (71, 85, 105) if no_hov else (30, 41, 59), self.grant_cancel_btn_rect, border_radius=6)
        pygame.draw.rect(surface, (148, 163, 184), self.grant_cancel_btn_rect, width=1, border_radius=6)
        no_s = self.font_sub.render("Cancel", True, (241, 245, 249))
        surface.blit(no_s, (self.grant_cancel_btn_rect.centerx - no_s.get_width() // 2, self.grant_cancel_btn_rect.centery - no_s.get_height() // 2))

    def _draw_production_tab(self, surface, mx, cy, villager_manager, permit_manager, furniture_manager=None, stockpile_manager=None, production_system=None):
        """Household Production & Harvest Distribution Overview"""
        ps = production_system or ProductionDistributionSystem.get_instance()
        mouse_pos = pygame.mouse.get_pos()

        # Title & Subtitle
        title = self.font_title.render("HOUSEHOLD PRODUCTION & HARVEST DISTRIBUTION", True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + 24, cy - 4))

        formula_txt = "Distribution Formula: Household Share = Participating Household Workers / Total Participating Workers"
        surface.blit(self.font_body.render(formula_txt, True, (56, 189, 248)), (mx + 24, cy + 22))

        # Top 3 KPI Cards
        card_w = (self.modal_w - 48 - 16) // 3
        card_h = 52

        farm_permits = [p for p in permit_manager.permits if p.permit_type == "farm"] if permit_manager else []
        total_farm_workers = sum(len(getattr(p, "assigned_workers", [])) for p in farm_permits)

        all_families = villager_manager.families if villager_manager else []
        total_potatoes_distributed = 0
        for f in all_families:
            p_sum = ps.get_household_production_summary(f.id)
            total_potatoes_distributed += p_sum["total_produced"].get("Potato", 0)

        kpis = [
            ("Cultivated Farm Lots", f"{len(farm_permits)} Active Farms", (34, 197, 94)),
            ("Participating Farmers", f"{total_farm_workers} Settlers Assigned", (56, 189, 248)),
            ("Total Crop Output Distributed", f"{total_potatoes_distributed} Potatoes", (245, 158, 11))
        ]

        for k_idx, (k_label, k_val, k_col) in enumerate(kpis):
            kx = mx + 24 + k_idx * (card_w + 8)
            kr = pygame.Rect(kx, cy + 44, card_w, card_h)
            pygame.draw.rect(surface, (24, 34, 52), kr, border_radius=6)
            pygame.draw.rect(surface, (51, 65, 85), kr, width=1, border_radius=6)
            surface.blit(self.font_badge.render(k_label, True, COLOR_TEXT_MUTED), (kr.x + 12, kr.y + 8))
            surface.blit(self.font_sub.render(k_val, True, k_col), (kr.x + 12, kr.y + 24))

        # Section 1: Active Production Sites & Household Shares
        y_cur = cy + 104
        surface.blit(self.font_sub.render("Active Production Sites & Participating Household Shares:", True, (241, 245, 249)), (mx + 24, y_cur))
        y_cur += 22

        if not farm_permits:
            empty_r = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 54)
            pygame.draw.rect(surface, (24, 34, 52), empty_r, border_radius=6)
            surface.blit(self.font_body.render("• No farm lots issued yet. Issue Farm Permits in Permits tab to assign workers.", True, COLOR_TEXT_MUTED), (empty_r.x + 16, empty_r.y + 18))
            y_cur += 64
        else:
            for p in farm_permits[:3]:
                lot_r = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 48)
                pygame.draw.rect(surface, (24, 34, 52), lot_r, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), lot_r, width=1, border_radius=6)

                assigned_w = getattr(p, "assigned_workers", [])
                counts, total_w = ps.get_participating_household_counts(assigned_w, villager_manager)
                shares = ps.calculate_shares(assigned_w, villager_manager)

                crop_type = getattr(p, "crop", "Potato") or "Potato"
                yield_txt = "2 Potatoes / tile every 10 days" if crop_type == "Potato" else "Standard Yield"
                surface.blit(self.font_sub.render(f"🌾 {p.name} ({len(p.tiles)} tiles) — Crop: {crop_type} ({yield_txt})", True, (241, 245, 249)), (lot_r.x + 12, lot_r.y + 6))

                if total_w > 0:
                    shares_str_parts = []
                    for h_id, share_ratio in shares.items():
                        fam_name = h_id
                        if villager_manager:
                            f = villager_manager.get_family_by_id(h_id)
                            if f:
                                fam_name = f"The {f.surname} Family"
                        shares_str_parts.append(f"{fam_name}: {counts[h_id]} worker(s) ({share_ratio * 100:.1f}%)")
                    share_desc = "Shares: " + " | ".join(shares_str_parts)
                    share_col = (34, 197, 94)
                else:
                    share_desc = "No workers currently assigned to this lot."
                    share_col = (245, 158, 11)

                surface.blit(self.font_body.render(share_desc, True, share_col), (lot_r.x + 12, lot_r.y + 26))
                y_cur += 54

        # Section 2: Household Income & Storage Deposits Roster
        surface.blit(self.font_sub.render("Household Income & Storage Balance (Private Household Property):", True, (241, 245, 249)), (mx + 24, y_cur))
        y_cur += 22

        if not all_families:
            none_r = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 44)
            pygame.draw.rect(surface, (24, 34, 52), none_r, border_radius=6)
            surface.blit(self.font_body.render("• No households registered in census.", True, COLOR_TEXT_MUTED), (none_r.x + 16, none_r.y + 14))
        else:
            for f in all_families[:4]:
                fam_r = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 36)
                pygame.draw.rect(surface, (15, 23, 42), fam_r, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), fam_r, width=1, border_radius=6)

                surface.blit(self.font_sub.render(f"The {f.surname} Family", True, (241, 245, 249)), (fam_r.x + 12, fam_r.y + 8))

                f_workers = [m for m in f.members if any(m.id in getattr(p, "assigned_workers", []) for p in farm_permits)]
                w_str = f"Active Farmers: {len(f_workers)}"
                surface.blit(self.font_body.render(w_str, True, (56, 189, 248)), (fam_r.x + 200, fam_r.y + 9))

                p_sum = ps.get_household_production_summary(f.id)
                pot_harvested = p_sum["total_produced"].get("Potato", 0)
                harvest_str = f"Gross Harvest Income: x{pot_harvested} Potatoes"
                surface.blit(self.font_body.render(harvest_str, True, (34, 197, 94)), (fam_r.x + 360, fam_r.y + 9))

                chest_stock = 0
                if furniture_manager:
                    c = furniture_manager.get_storage_for_family(f.id)
                    if c:
                        chest_stock = c.inventory.get("Potato", 0)
                chest_str = f"In Household Chest: x{chest_stock}"
                surface.blit(self.font_body.render(chest_str, True, (245, 158, 11)), (fam_r.x + 620, fam_r.y + 9))

                y_cur += 40

    def _draw_tax_tab(self, surface, mx, cy, villager_manager, permit_manager, furniture_manager=None, production_system=None, resources=None, building_manager=None, stockpile_manager=None):
        """Tax System UI, Church Tithes & Village Wealth Distribution (AGENT 2)"""
        ps = production_system or ProductionDistributionSystem.get_instance()
        mouse_pos = pygame.mouse.get_pos()

        # Title
        title = self.font_title.render("VILLAGE TAXATION & ROYAL TITHES", True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + 24, cy - 4))

        # 1. Configurable Church Tax (Daily Tithe per Household)
        church_card = pygame.Rect(mx + 24, cy + 22, self.modal_w - 48, 56)
        pygame.draw.rect(surface, (30, 27, 46), church_card, border_radius=6)
        pygame.draw.rect(surface, (168, 85, 247), church_card, width=1, border_radius=6)

        surface.blit(self.font_sub.render("⛪ Church Tax (Daily Tithe per Household):", True, (216, 180, 254)), (church_card.x + 14, church_card.y + 8))
        surface.blit(self.font_body.render("Ecclesiastical tithe collected daily by the Priest for village church operations & salvation rites.", True, COLOR_TEXT_MUTED), (church_card.x + 14, church_card.y + 30))

        if not hasattr(self, "church_tax") or not isinstance(self.church_tax, dict):
            self.church_tax = {"Gold": 0, "Silver": 0, "Copper": 1}

        # Denomination controls: Gold, Silver, Copper
        tx_ctrl_x = church_card.right - 330
        btn_ty = church_card.y + 15

        # Gold
        surface.blit(self.font_badge.render("Gold:", True, (250, 204, 21)), (tx_ctrl_x, btn_ty + 3))
        self.church_tax_g_dec_rect = pygame.Rect(tx_ctrl_x + 36, btn_ty, 20, 22)
        self.church_tax_g_inc_rect = pygame.Rect(tx_ctrl_x + 76, btn_ty, 20, 22)
        pygame.draw.rect(surface, (51, 65, 85), self.church_tax_g_dec_rect, border_radius=3)
        surface.blit(self.font_badge.render("-", True, (255, 255, 255)), (self.church_tax_g_dec_rect.x + 7, self.church_tax_g_dec_rect.y + 3))
        g_val_s = self.font_sub.render(str(self.church_tax.get("Gold", 0)), True, (250, 204, 21))
        surface.blit(g_val_s, (tx_ctrl_x + 60, btn_ty + 2))
        pygame.draw.rect(surface, (51, 65, 85), self.church_tax_g_inc_rect, border_radius=3)
        surface.blit(self.font_badge.render("+", True, (255, 255, 255)), (self.church_tax_g_inc_rect.x + 6, self.church_tax_g_inc_rect.y + 3))

        # Silver
        s_ctrl_x = tx_ctrl_x + 106
        surface.blit(self.font_badge.render("Silver:", True, (203, 213, 225)), (s_ctrl_x, btn_ty + 3))
        self.church_tax_s_dec_rect = pygame.Rect(s_ctrl_x + 38, btn_ty, 20, 22)
        self.church_tax_s_inc_rect = pygame.Rect(s_ctrl_x + 78, btn_ty, 20, 22)
        pygame.draw.rect(surface, (51, 65, 85), self.church_tax_s_dec_rect, border_radius=3)
        surface.blit(self.font_badge.render("-", True, (255, 255, 255)), (self.church_tax_s_dec_rect.x + 7, self.church_tax_s_dec_rect.y + 3))
        s_val_s = self.font_sub.render(str(self.church_tax.get("Silver", 0)), True, (203, 213, 225))
        surface.blit(s_val_s, (s_ctrl_x + 62, btn_ty + 2))
        pygame.draw.rect(surface, (51, 65, 85), self.church_tax_s_inc_rect, border_radius=3)
        surface.blit(self.font_badge.render("+", True, (255, 255, 255)), (self.church_tax_s_inc_rect.x + 6, self.church_tax_s_inc_rect.y + 3))

        # Copper
        c_ctrl_x = s_ctrl_x + 110
        surface.blit(self.font_badge.render("Copper:", True, (217, 119, 6)), (c_ctrl_x, btn_ty + 3))
        self.church_tax_c_dec_rect = pygame.Rect(c_ctrl_x + 48, btn_ty, 20, 22)
        self.church_tax_c_inc_rect = pygame.Rect(c_ctrl_x + 88, btn_ty, 20, 22)
        pygame.draw.rect(surface, (51, 65, 85), self.church_tax_c_dec_rect, border_radius=3)
        surface.blit(self.font_badge.render("-", True, (255, 255, 255)), (self.church_tax_c_dec_rect.x + 7, self.church_tax_c_dec_rect.y + 3))
        c_val_s = self.font_sub.render(str(self.church_tax.get("Copper", 1)), True, (217, 119, 6))
        surface.blit(c_val_s, (c_ctrl_x + 72, btn_ty + 2))
        pygame.draw.rect(surface, (51, 65, 85), self.church_tax_c_inc_rect, border_radius=3)
        surface.blit(self.font_badge.render("+", True, (255, 255, 255)), (self.church_tax_c_inc_rect.x + 6, self.church_tax_c_inc_rect.y + 3))

        # 2. Village Wealth Section (AGENT 2)
        wealth_data = VillageWealthSystem.calculate_village_wealth(
            resources=resources,
            villager_manager=villager_manager,
            furniture_manager=furniture_manager,
            building_manager=building_manager,
            stockpile_manager=stockpile_manager
        )
        self.cached_wealth_data = wealth_data

        wealth_card = pygame.Rect(mx + 24, cy + 84, self.modal_w - 48, 52)
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

        # 3. Proposed Taxation Policies Structure (3 cards)
        y_cur = cy + 144
        surface.blit(self.font_sub.render("Proposed Village Tax Policies (Future Implementation Framework):", True, (241, 245, 249)), (mx + 24, y_cur))
        y_cur += 20

        policy_w = (self.modal_w - 48 - 16) // 3
        policy_h = 68
        policies = [
            ("🌾 Agricultural Crop Tithe", "Tithe on peasant potato harvest.", "10% of Harvest", "INACTIVE (WIP)", (34, 197, 94)),
            ("⚒️ Craft & Artisan Duty", "Tithe on produced tools & wares.", "5% of Craft Output", "INACTIVE (WIP)", (56, 189, 248)),
            ("🪙 Market Trade Tariff", "Commercial stall transaction tariff.", "2 Coins / Stall", "INACTIVE (WIP)", (245, 158, 11))
        ]

        for p_idx, (p_title, p_desc, p_rate, p_stat, p_col) in enumerate(policies):
            px = mx + 24 + p_idx * (policy_w + 8)
            pr = pygame.Rect(px, y_cur, policy_w, policy_h)
            pygame.draw.rect(surface, (24, 34, 52), pr, border_radius=6)
            pygame.draw.rect(surface, (51, 65, 85), pr, width=1, border_radius=6)

            surface.blit(self.font_sub.render(p_title, True, p_col), (pr.x + 10, pr.y + 6))
            surface.blit(self.font_body.render(p_desc, True, COLOR_TEXT_MUTED), (pr.x + 10, pr.y + 24))
            surface.blit(self.font_badge.render(f"Rate: {p_rate}", True, (241, 245, 249)), (pr.x + 10, pr.y + 44))

            stat_badge = pygame.Rect(pr.right - 96, pr.y + 44, 88, 18)
            pygame.draw.rect(surface, (71, 85, 105), stat_badge, border_radius=3)
            b_txt = self.font_badge.render(p_stat, True, (203, 213, 225))
            surface.blit(b_txt, (stat_badge.centerx - b_txt.get_width() // 2, stat_badge.centery - b_txt.get_height() // 2))

        y_cur += policy_h + 12

        # 4. Projected Household Assessment Table
        surface.blit(self.font_sub.render("Projected Household Tax Assessment Table (Zero Active Deductions):", True, (241, 245, 249)), (mx + 24, y_cur))
        y_cur += 20

        all_families = villager_manager.families if villager_manager else []
        if not all_families:
            none_r = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 38)
            pygame.draw.rect(surface, (24, 34, 52), none_r, border_radius=6)
            surface.blit(self.font_body.render("• No households registered in census.", True, COLOR_TEXT_MUTED), (none_r.x + 16, none_r.y + 11))
        else:
            for f in all_families[:4]:
                row_r = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 32)
                pygame.draw.rect(surface, (15, 23, 42), row_r, border_radius=6)
                pygame.draw.rect(surface, (51, 65, 85), row_r, width=1, border_radius=6)

                surface.blit(self.font_sub.render(f"The {f.surname} Family", True, (241, 245, 249)), (row_r.x + 12, row_r.y + 6))

                f_workers = len(f.members)
                surface.blit(self.font_body.render(f"{f_workers} Members", True, COLOR_TEXT_MUTED), (row_r.x + 200, row_r.y + 8))

                p_sum = ps.get_household_production_summary(f.id)
                potatoes = p_sum["total_produced"].get("Potato", 0)
                surface.blit(self.font_body.render(f"Est. Production: {potatoes} Potatoes", True, (56, 189, 248)), (row_r.x + 310, row_r.y + 8))

                surface.blit(self.font_body.render(f"Projected Due: {int(potatoes * 0.10)} Pot.", True, (245, 158, 11)), (row_r.x + 510, row_r.y + 8))

                st_b = pygame.Rect(row_r.right - 180, row_r.y + 5, 168, 22)
                pygame.draw.rect(surface, (20, 83, 45), st_b, border_radius=4)
                pygame.draw.rect(surface, (34, 197, 94), st_b, width=1, border_radius=4)
                st_txt = self.font_badge.render("EXEMPT (WIP - No Deductions)", True, (240, 253, 244))
                surface.blit(st_txt, (st_b.centerx - st_txt.get_width() // 2, st_b.centery - st_txt.get_height() // 2))

                y_cur += 36

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

    def _draw_planning_tab(self, surface, mx, cy):
        """In-game WIP Planning Overview and Roadmap"""
        mouse_pos = pygame.mouse.get_pos()

        # Title & Subtitle
        title = self.font_title.render("PROJECT PLANNING & WIP ROADMAP", True, COLOR_TEXT_TITLE)
        surface.blit(title, (mx + 24, cy - 4))

        sub = self.font_body.render("Public roadmap of implemented, partial, and planned WIP features. Informational overview.", True, COLOR_TEXT_MUTED)
        surface.blit(sub, (mx + 24, cy + 22))

        # Filter Chips
        filter_chips = [
            ("ALL", "All Features", len(PLANNING_FEATURES)),
            (STATUS_PLANNED, "Planned WIP", len(get_features_by_status(STATUS_PLANNED))),
            (STATUS_PARTIAL, "Partial WIP", len(get_features_by_status(STATUS_PARTIAL))),
            (STATUS_IMPLEMENTED, "Implemented", len(get_features_by_status(STATUS_IMPLEMENTED)))
        ]

        chip_x = mx + 24
        chip_y = cy + 44
        self.planning_filter_rects = {}

        for key, label, count in filter_chips:
            is_sel = (self.planning_filter_status == key)
            c_text = f"{label} ({count})"
            c_surf = self.font_badge.render(c_text, True, (255, 255, 255) if is_sel else COLOR_TEXT_MUTED)
            c_w = c_surf.get_width() + 18
            c_h = 24
            cr = pygame.Rect(chip_x, chip_y, c_w, c_h)
            self.planning_filter_rects[key] = cr

            bg = (37, 99, 235) if is_sel else (30, 41, 59)
            border_c = (96, 165, 250) if is_sel else (71, 85, 105)
            pygame.draw.rect(surface, bg, cr, border_radius=12)
            pygame.draw.rect(surface, border_c, cr, width=1, border_radius=12)
            surface.blit(c_surf, (cr.centerx - c_surf.get_width() // 2, cr.centery - c_surf.get_height() // 2))

            chip_x += c_w + 8

        # Active items
        if self.planning_filter_status == "ALL":
            active_list = PLANNING_FEATURES
        else:
            active_list = get_features_by_status(self.planning_filter_status)

        total_items = len(active_list)
        per_page = self.planning_items_per_page
        max_page = max(0, (total_items - 1) // per_page)
        self.planning_page = min(self.planning_page, max_page)
        start_idx = self.planning_page * per_page
        page_items = active_list[start_idx:start_idx + per_page]

        # Feature Cards
        y_cur = cy + 74
        for f in page_items:
            f_rect = pygame.Rect(mx + 24, y_cur, self.modal_w - 48, 64)
            status = f.get("status")

            if status == STATUS_IMPLEMENTED:
                card_bg = (15, 30, 20)
                border_col = (34, 197, 94)
                badge_bg = (20, 83, 45)
                badge_txt_col = (240, 253, 244)
                badge_label = "IMPLEMENTED"
            elif status == STATUS_PARTIAL:
                card_bg = (35, 28, 12)
                border_col = COLOR_BADGE_PARTIAL
                badge_bg = (113, 63, 18)
                badge_txt_col = (254, 240, 138)
                badge_label = "PARTIAL (WIP)"
            else:
                card_bg = (24, 34, 52)
                border_col = (71, 85, 105)
                badge_bg = (51, 65, 85)
                badge_txt_col = (203, 213, 225)
                badge_label = "PLANNED WIP"

            pygame.draw.rect(surface, card_bg, f_rect, border_radius=6)
            pygame.draw.rect(surface, border_col, f_rect, width=1, border_radius=6)

            # Name & Category
            title_text = f"{f['name']}  ·  [{f.get('category', 'System')}]"
            surface.blit(self.font_sub.render(title_text, True, (241, 245, 249)), (f_rect.x + 12, f_rect.y + 6))

            # Status Badge
            b_surf = self.font_badge.render(badge_label, True, badge_txt_col)
            b_w = b_surf.get_width() + 16
            b_rect = pygame.Rect(f_rect.right - b_w - 12, f_rect.y + 7, b_w, 20)
            pygame.draw.rect(surface, badge_bg, b_rect, border_radius=4)
            pygame.draw.rect(surface, border_col, b_rect, width=1, border_radius=4)
            surface.blit(b_surf, (b_rect.centerx - b_surf.get_width() // 2, b_rect.centery - b_surf.get_height() // 2))

            # Summary and description
            desc_text = f"{f.get('summary', '')} — {f.get('description', '')}"
            if len(desc_text) > 130:
                desc_text = desc_text[:127] + "..."
            surface.blit(self.font_body.render(desc_text, True, (203, 213, 225)), (f_rect.x + 12, f_rect.y + 26))

            # Lead Agent tag
            agent_tag = f"Lead Agent: {f.get('owner_agent', 'Settlement Engine')}"
            surface.blit(self.font_badge.render(agent_tag, True, (148, 163, 184)), (f_rect.x + 12, f_rect.y + 45))

            y_cur += 70

        # Pagination Controls
        pag_y = cy + self.modal_h - 100
        page_info = f"Showing page {self.planning_page + 1} of {max_page + 1}  ({total_items} features)"
        surface.blit(self.font_body.render(page_info, True, COLOR_TEXT_MUTED), (mx + 24, pag_y + 4))

        self.planning_prev_btn_rect = pygame.Rect(mx + self.modal_w - 190, pag_y, 76, 26)
        prev_hov = self.planning_prev_btn_rect.collidepoint(mouse_pos)
        prev_enabled = (self.planning_page > 0)
        pygame.draw.rect(surface, (51, 65, 85) if (prev_hov and prev_enabled) else (30, 41, 59), self.planning_prev_btn_rect, border_radius=4)
        pygame.draw.rect(surface, (96, 165, 250) if prev_enabled else (71, 85, 105), self.planning_prev_btn_rect, width=1, border_radius=4)
        p_txt = self.font_badge.render("< Prev", True, (255, 255, 255) if prev_enabled else COLOR_TEXT_MUTED)
        surface.blit(p_txt, (self.planning_prev_btn_rect.centerx - p_txt.get_width() // 2, self.planning_prev_btn_rect.centery - p_txt.get_height() // 2))

        self.planning_next_btn_rect = pygame.Rect(mx + self.modal_w - 104, pag_y, 76, 26)
        next_hov = self.planning_next_btn_rect.collidepoint(mouse_pos)
        next_enabled = (self.planning_page < max_page)
        pygame.draw.rect(surface, (51, 65, 85) if (next_hov and next_enabled) else (30, 41, 59), self.planning_next_btn_rect, border_radius=4)
        pygame.draw.rect(surface, (96, 165, 250) if next_enabled else (71, 85, 105), self.planning_next_btn_rect, width=1, border_radius=4)
        n_txt = self.font_badge.render("Next >", True, (255, 255, 255) if next_enabled else COLOR_TEXT_MUTED)
        surface.blit(n_txt, (self.planning_next_btn_rect.centerx - n_txt.get_width() // 2, self.planning_next_btn_rect.centery - n_txt.get_height() // 2))
