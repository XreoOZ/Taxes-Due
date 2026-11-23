"""
Main Entry Point
Taxes-Due | Village Building Prototype
"""

import os
import sys

# High DPI Awareness for Windows
if sys.platform == "win32":
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import math
import random
from time import perf_counter
import pygame
from game.config import (
    WINDOW_TITLE,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    FPS,
    TILE_SIZE,
    DEFAULT_RESOURCES,
    BUILDING_TYPES,
    PERMIT_TYPES,
    FURNITURE_TYPES,
    DEDICATED_JOBS,
    COST_PER_BLOCK_WOOD,
    COST_PER_BLOCK_STONE,
    PATH_TOGGLE_BTN_WIDTH,
    PATH_TOGGLE_BTN_HEIGHT,
    MARKET_WEALTH_CONTEXT_REFRESH_SECONDS,
    SIMULATION_PROFILE_REPORT_SECONDS,
    MAX_FRAME_GAME_DT,
    PLACEMENT_ORIENTATION_MARKER_LENGTH_RATIO,
    PLACEMENT_ORIENTATION_MARKER_HEAD_RATIO,
    PLACEMENT_ORIENTATION_MARKER_COLOR,
    PLACEMENT_ORIENTATION_MARKER_OUTLINE,
    LORD_TREASURY_START_TILE,
    HAPPINESS_MIN_VALUE,
    HAPPINESS_MAX_VALUE,
    HAPPINESS_STATUS_BANDS,
    HAPPINESS_STATUS_COLORS,
    SLEEP_MAX_VALUE,
    SLEEP_MIN_VALUE,
    SLEEP_STATUS_COLORS,
    AI_ACTIVITY_PREVIEW_MAX_NEXT,
    AI_PROFILE_HAPPINESS_VISIBLE_ROWS,
    AI_PROFILE_ACTIVITY_ROW_HEIGHT,
    AI_PROFILE_NEED_ROW_HEIGHT,
    AI_PROFILE_CARD_WIDTH,
    AI_PROFILE_ACTIVITY_OFFSET,
    AI_PROFILE_DECEASED_ACTIVITY_OFFSET,
    AI_PROFILE_ACTIVITY_HEADER_OFFSET,
    AI_PROFILE_NEED_SECTION_GAP,
    AI_PROFILE_INFO_SECTION_GAP,
    AI_PROFILE_FACTOR_SECTION_GAP,
    AI_PROFILE_FACTOR_PANEL_HEADER_HEIGHT,
    AI_PROFILE_PANEL_BOTTOM_PADDING,
    WORLD_TYPE_OPTIONS,
    ISLAND_SEED_MIN,
    ISLAND_SEED_MAX,
    ROAD_TYPES,
    COLOR_MODAL_BG,
    COLOR_MODAL_BORDER,
    COLOR_TEXT_TITLE,
    STARTER_PLACEMENT_PAN_SPEED,
)
from game.world.island import set_world
from game.camera import Camera
from game.player import Player
from game.world import World
from game.menu import MainMenu
from game.hud import ResourceHUD
from game.buildings import BuildingManager
from game.permits import PermitManager, get_exterior_edges_for_tile
from game.stockpile import StockpileManager
from game.servants import ServantManager
from game.villagers import VillagerManager
from game.furniture import FurnitureManager
from game.ui_raport import RaportUI
from game.ui.modals.market_modal import MarketProfileModal
from game.ui.modals.add_item_modal import AddItemModal
from game.ui.modals.cheat_modal import CheatModal
from game.ui.modals.builder_catalog_modal import BuilderCatalogModal
from game.ui.path_debug_overlay import PathDebugOverlay
from game.ui.map_overlay import MapOverlay
from game.systems.economy.production_distribution import ProductionDistributionSystem
from game.speed_control import SpeedController
from game.day_cycle import DayCycleSystem
from game.settings import SettingsModal
from game.schedule import ScheduleManager
from game.save_modal import SaveLoadModal
from game.save_system import save_to_slot, load_from_slot
from game.systems.economy.currency import from_copper
from game.systems.economy.market_pricing import MarketPricingSystem
from game.systems.economy.market_service import MarketService
from game.systems.economy.wealth_system import VillageWealthSystem
from game.systems.core.cheat_system import apply_add_item_cheat, clean_resources_dictionary, spawn_item_physically
from game.systems.work.activity_preview import ActivityPreviewSystem
from game.systems.village_life.happiness_system import HappinessSystem

STATE_MENU = "menu"
STATE_PLAYING = "playing"

def get_rect_tiles(start_pt, cur_pt):
    """Mengembalikan set koordinat tile (gx, gy) di dalam bounding box dua titik"""
    gx = min(start_pt[0], cur_pt[0])
    gy = min(start_pt[1], cur_pt[1])
    tw = abs(cur_pt[0] - start_pt[0]) + 1
    th = abs(cur_pt[1] - start_pt[1]) + 1
    return {(gx + c, gy + r) for c in range(tw) for r in range(th)}

def draw_placement_orientation(surface, rect, rotation):
    """Draw a clear compass arrow for square one-tile placement previews."""
    if rect.width <= 0 or rect.height <= 0:
        return
    directions = ((0.0, -1.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0))
    direction = directions[(int(rotation) // 90) % len(directions)]
    center = pygame.Vector2(rect.center)
    length = min(rect.width, rect.height) * PLACEMENT_ORIENTATION_MARKER_LENGTH_RATIO
    tip = center + pygame.Vector2(direction) * length
    base = tip - pygame.Vector2(direction) * length * PLACEMENT_ORIENTATION_MARKER_HEAD_RATIO
    side = pygame.Vector2(-direction[1], direction[0]) * length * PLACEMENT_ORIENTATION_MARKER_HEAD_RATIO * 0.65
    head = (tip, base + side, base - side)
    line_width = max(2, int(min(rect.width, rect.height) * 0.055))
    pygame.draw.line(surface, PLACEMENT_ORIENTATION_MARKER_OUTLINE,
                     center, tip, line_width + 2)
    pygame.draw.line(surface, PLACEMENT_ORIENTATION_MARKER_COLOR,
                     center, tip, line_width)
    pygame.draw.polygon(surface, PLACEMENT_ORIENTATION_MARKER_OUTLINE, head)
    pygame.draw.polygon(surface, PLACEMENT_ORIENTATION_MARKER_COLOR, head, width=1)

def workplace_bases_for(kind, obj):
    """Workplace base kinds ('permit'/'structure') provided by a placed object."""
    bases = set()
    for job_cfg in DEDICATED_JOBS.values():
        if kind == "permit" and job_cfg.get("workplace_permit") == getattr(obj, "permit_type", None):
            bases.add("permit")
        elif kind == "building" and job_cfg.get("workplace_building_type") == getattr(obj, "building_type", None):
            bases.add("structure")
        elif kind == "furniture" and job_cfg.get("workplace_furniture_type") == getattr(obj, "furniture_type", None):
            bases.add("structure")
    return bases


def furniture_menu_actions(f):
    """Contextual action buttons shown inside the furniture context menu."""
    acts = []
    ftype = getattr(f, "furniture_type", "")
    if ftype == "builder_workbench":
        acts.append(("catalogue", "Catalogue"))
    if ftype == "notice_board":
        acts.append(("immigrants", "Immigrants"))
    if workplace_bases_for("furniture", f):
        acts.append(("workplace", "Workplace"))
    return acts


def structure_menu_actions(b):
    """Contextual action buttons shown inside the public-structure menu."""
    acts = []
    if getattr(b, "building_type", "") == "market":
        acts.append(("market", "Market"))
    if workplace_bases_for("building", b):
        acts.append(("workplace", "Workplace"))
    return acts


def workplace_job_for(kind, obj):
    """Job id whose workplace definition matches this placed object."""
    for job_id, job_cfg in DEDICATED_JOBS.items():
        if kind == "permit" and job_cfg.get("workplace_permit") == getattr(obj, "permit_type", None):
            return job_id
        if kind == "building" and job_cfg.get("workplace_building_type") == getattr(obj, "building_type", None):
            return job_id
        if kind == "furniture" and job_cfg.get("workplace_furniture_type") == getattr(obj, "furniture_type", None):
            return job_id
    return None


def main():
    pygame.init()

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption(WINDOW_TITLE)

    clock = pygame.time.Clock()
    font_hud = pygame.font.SysFont("Segoe UI", 12, bold=True)
    font_card = pygame.font.SysFont("Segoe UI", 13, bold=True)
    font_btn = pygame.font.SysFont("Segoe UI", 12, bold=True)
    font_badge = pygame.font.SysFont("Segoe UI", 10, bold=True)
    font_body = pygame.font.SysFont("Segoe UI", 11)

    # Inisialisasi Game Objects, Menu, Resources & Building System
    current_state = STATE_MENU
    menu = MainMenu()
    camera = Camera(WINDOW_WIDTH, WINDOW_HEIGHT)
    world = World(tile_size=TILE_SIZE)
    resource_hud = ResourceHUD()
    raport_ui = RaportUI()
    market_modal = MarketProfileModal()
    add_item_modal = AddItemModal()
    cheat_modal = CheatModal()
    builder_catalog_modal = BuilderCatalogModal()
    path_debug_overlay = PathDebugOverlay(enabled=False)
    map_overlay = MapOverlay()
    production_system = ProductionDistributionSystem.get_instance()
    speed_controller = SpeedController()
    settings_modal = SettingsModal()
    save_modal = SaveLoadModal()

    player = None
    resources = None
    building_manager = None
    permit_manager = None
    stockpile_manager = None
    servant_manager = None
    villager_manager = None
    furniture_manager = None
    day_cycle = None
    schedule_manager = None

    # Dynamic Planning States (Multi-drag, Expandable, Zero Hardcoded Rectangles)
    planning_mode = "NONE"  # "NONE" | "PERMIT" | "EDIT_PERMIT" | "BUILDING" | "FURNITURE"
    planning_permit_type = None
    planning_permit_tiles = set()
    editing_permit_id = None
    original_permit_tiles = set()
    permit_drag_start = None
    permit_erase_start = None
    planning_building_type = None
    planning_building_tiles = set()
    planning_building_rotation = 0
    planned_door_tile = None
    planned_door_side = "bottom"
    building_drag_start = None
    building_erase_start = None
    planning_furniture_type = None
    planning_furniture_rotation = 0
    session_planned_furniture = []
    selected_planned_furniture = None
    selected_furniture = None
    moving_furniture = None
    selected_entity = None
    selected_entity_happiness_scroll = 0

    # Road painting mode (Public Structure > Road): drag-paint tiles, confirm pays cost.
    planning_road_type = None
    planning_road_tiles = set()
    road_drag_start = None

    # Destroy mode: click objects to mark them, DONE -> confirm -> execute.
    destroy_marks = []          # [("building"|"site"|"road", obj_or_tile), ...]
    destroy_confirm = None      # pending confirmed-destroy payload while popup open

    furn_menu_rect = pygame.Rect(0, 0, 270, 140)
    btn_furn_move_rect = pygame.Rect(0, 0, 112, 28)
    btn_furn_destroy_rect = pygame.Rect(0, 0, 112, 28)
    btn_furn_close_rect = pygame.Rect(0, 0, 22, 22)
    btn_furn_house_rect = pygame.Rect(0, 0, 116, 26)
    btn_furn_poss_rect = pygame.Rect(0, 0, 116, 26)
    btn_furn_store_rect = pygame.Rect(0, 0, 252, 24)
    btn_furn_pay_builder_rect = pygame.Rect(0, 0, 252, 24)
    furn_action_btns = []     # [{"rect": Rect, "action": str}] contextual actions

    # Public-structure context menu (List / Destroy / special actions)
    selected_structure = None
    struct_menu_rect = pygame.Rect(0, 0, 0, 0)
    struct_action_btns = []   # [{"rect": Rect, "action": str}]
    btn_struct_list_rect = pygame.Rect(0, 0, 112, 28)
    btn_struct_destroy_rect = pygame.Rect(0, 0, 112, 28)
    btn_struct_close_rect = pygame.Rect(0, 0, 22, 22)

    # Workplace base popup (Permit vs Structure) shown when clicking a
    # placed job-workplace object on the map.
    workplace_popup = None  # {"kind": "permit"|"building"|"furniture", "obj": ..., "pos": (x, y)}
    wp_popup_rect = pygame.Rect(0, 0, 0, 0)
    wp_base_btn_rect = pygame.Rect(0, 0, 0, 0)
    wp_ws_btn_rect = pygame.Rect(0, 0, 0, 0)
    wp_close_btn_rect = pygame.Rect(0, 0, 0, 0)

    # Natural-resource mine info popup shown when clicking a generated mine.
    mine_popup = None  # {"mine": dict, "pos": (x, y)}
    mine_popup_rect = pygame.Rect(0, 0, 0, 0)

    entity_card_rect = pygame.Rect(0, 0, 310, 180)
    entity_happiness_rect = pygame.Rect(0, 0, 0, 0)
    btn_entity_close_rect = pygame.Rect(0, 0, 22, 22)
    btn_entity_household_rect = pygame.Rect(0, 0, 96, 22)

    btn_add_item_cheat_rect = pygame.Rect(0, 0, PATH_TOGGLE_BTN_WIDTH, PATH_TOGGLE_BTN_HEIGHT)
    cheat_notice = ""
    cheat_notice_timer = 0.0
    cheats_active = False
    pending_starter_id = None
    starter_confirm_tile = None
    starter_done_btn_rect = pygame.Rect(0, 0, 0, 0)
    starter_cancel_btn_rect = pygame.Rect(0, 0, 0, 0)

    def start_fresh_game(day_length_index=None, world_map_index=None, starter_index=None):
        nonlocal player, resources, building_manager, permit_manager, stockpile_manager
        nonlocal pending_starter_id, starter_confirm_tile
        nonlocal servant_manager, villager_manager, furniture_manager, day_cycle, schedule_manager
        nonlocal planning_mode, planning_permit_type, planning_building_type, planning_furniture_type
        nonlocal planning_building_rotation, planning_furniture_rotation
        nonlocal planning_road_type, planning_road_tiles, road_drag_start
        nonlocal destroy_marks, destroy_confirm
        nonlocal session_planned_furniture, selected_planned_furniture
        nonlocal editing_permit_id, original_permit_tiles, selected_furniture, moving_furniture, selected_entity, selected_structure

        # Activate the chosen world terrain before any entity/manager setup.
        map_option = WORLD_TYPE_OPTIONS[world_map_index] if world_map_index is not None else WORLD_TYPE_OPTIONS[0]
        world_seed = random.randint(ISLAND_SEED_MIN, ISLAND_SEED_MAX) if map_option["id"] == "island" else None
        set_world(map_option["id"], seed=world_seed)
        from game.world.natural_resources import get_natural_resources
        get_natural_resources().generate(world_seed)
        from game.world.roads import get_roads
        get_roads().reset()

        from game.systems.village_life.cemetery_system import CemeterySystem
        cemetery_system = CemeterySystem.get_instance()
        cemetery_system.pending_commissions.clear()
        cemetery_system.overflow_corpses.clear()
        from game.systems.village_life.confession_system import ConfessionSystem
        confession_system = ConfessionSystem.get_instance()
        confession_system.queues.clear()
        confession_system.active.clear()

        player = Player(0.0, 0.0)
        camera.x = 0.0
        camera.y = 0.0
        camera.target_x = 0.0
        camera.target_y = 0.0
        camera.zoom = 1.0
        resources = dict(DEFAULT_RESOURCES)
        clean_resources_dictionary(resources)
        building_manager = BuildingManager()
        permit_manager = PermitManager()
        stockpile_manager = StockpileManager()
        servant_manager = ServantManager()
        villager_manager = VillagerManager()
        furniture_manager = FurnitureManager()
        furniture_manager.set_managers(
            building_manager=building_manager, permit_manager=permit_manager,
            villager_manager=villager_manager,
        )
        furniture_manager.ensure_lord_treasury_chest(
            permit_manager, villager_manager, building_manager,
            preferred_tile=LORD_TREASURY_START_TILE,
        )
        # Starter preset (Nepo Baby etc.) is deferred: the player picks the
        # drop location in-game, then StarterPresetSystem.apply() materializes
        # family, permits, buildings, furniture, storage yard, and treasury.
        # Without a preset, the world starts empty with the default family.
        pending_starter_id = None
        starter_confirm_tile = None
        if starter_index is not None:
            from game.data.config import STARTER_PRESETS
            if 0 <= int(starter_index) < len(STARTER_PRESETS):
                pending_starter_id = STARTER_PRESETS[int(starter_index)]["id"]
        if pending_starter_id is None:
            villager_manager.generate_starter_family()
        day_cycle = DayCycleSystem()
        if day_length_index is not None:
            day_cycle.set_day_length_index(day_length_index)
        schedule_manager = ScheduleManager()
        raport_ui.close()
        market_modal.close()
        add_item_modal.close()
        cheat_modal.close()
        settings_modal.close()
        save_modal.close()
        planning_mode = "NONE"
        planning_permit_type = None
        planning_building_type = None
        planning_furniture_type = None
        planning_road_type = None
        planning_building_rotation = 0
        planning_furniture_rotation = 0
        session_planned_furniture.clear()
        selected_planned_furniture = None
        editing_permit_id = None
        selected_furniture = None
        selected_structure = None
        moving_furniture = None
        builder_catalog_modal.close()
        original_permit_tiles.clear()
        planning_road_tiles.clear()
        road_drag_start = None
        destroy_marks.clear()
        destroy_confirm = None

    start_fresh_game()

    # Floating Bottom Bar Action Buttons
    btn_confirm_rect = pygame.Rect(0, 0, 150, 36)
    btn_clear_rect = pygame.Rect(0, 0, 90, 36)
    btn_cancel_rect = pygame.Rect(0, 0, 110, 36)
    btn_done_rect = pygame.Rect(0, 0, 110, 36)
    destroy_yes_rect = pygame.Rect(0, 0, 110, 36)
    destroy_no_rect = pygame.Rect(0, 0, 110, 36)
    btn_door_mode_rect = pygame.Rect(0, 0, 130, 36)

    running = True
    wealth_context_timer = 0.0
    autosave_elapsed = 0.0
    profile_enabled = os.environ.get("TAXES_DUE_PROFILE", "").strip().lower() in ("1", "true", "yes")
    profile_elapsed = 0.0
    profile_frame_count = 0
    profile_frame_ms = 0.0
    profile_simulation_ms = 0.0
    while running:
        real_dt = min(clock.tick(FPS) / 1000.0, 0.1)
        profile_frame_start = perf_counter() if profile_enabled else 0.0
        game_dt = min(speed_controller.get_game_dt(real_dt), MAX_FRAME_GAME_DT)
        if current_state == STATE_PLAYING and (settings_modal.is_open or save_modal.is_open or cheat_modal.is_open):
            game_dt = 0.0

        # Refresh fisik item di stockpile setiap frame
        stockpile_manager.refresh_stacks(resources, permit_manager)

        m_pos = pygame.mouse.get_pos()
        m_wx, m_wy = camera.screen_to_world(m_pos[0], m_pos[1])
        m_gx = int(math.floor(m_wx / TILE_SIZE))
        m_gy = int(math.floor(m_wy / TILE_SIZE))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                camera.resize(event.w, event.h)

            if current_state == STATE_MENU:
                if save_modal.is_open:
                    save_action = save_modal.handle_event(event)
                    if save_action and save_action.startswith("load_slot_"):
                        save_name = save_action.split("load_slot_", 1)[1]
                        success, msg = load_from_slot(save_name, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager)
                        if success:
                            save_modal.close()
                            settings_modal.close()
                            raport_ui.close()
                            market_modal.close()
                            builder_catalog_modal.close()
                            planning_mode = "NONE"
                            session_planned_furniture.clear()
                            selected_planned_furniture = None
                            selected_furniture = None
                            moving_furniture = None
                            camera.target_x = player.x
                            camera.target_y = player.y
                            camera.x = player.x
                            camera.y = player.y
                            current_state = STATE_PLAYING
                        else:
                            save_modal.refresh_slots(f"Error: {msg}")
                    elif save_action and save_action.startswith("delete_slot_"):
                        from game.save_system import delete_save
                        save_name = save_action.split("delete_slot_", 1)[1]
                        success, msg = delete_save(save_name)
                        save_modal.refresh_slots(msg if success else f"Error: {msg}")
                    continue

                if settings_modal.is_open:
                    settings_modal.handle_event(event, day_cycle, is_ingame=False)
                    continue

                action = menu.handle_event(event)
                if action and action.startswith("start_game_"):
                    parts = action.split("_")
                    day_idx = int(parts[2])
                    map_idx = int(parts[3]) if len(parts) > 3 else 0
                    starter_idx = int(parts[4]) if len(parts) > 4 else None
                    start_fresh_game(day_length_index=day_idx, world_map_index=map_idx,
                                     starter_index=starter_idx)
                    current_state = STATE_PLAYING
                elif action == "play":
                    start_fresh_game()
                    current_state = STATE_PLAYING
                elif action == "load":
                    save_modal.open(mode="LOAD")
                elif action == "setting":
                    settings_modal.open(is_ingame=False)
                elif action == "exit":
                    running = False

            elif current_state == STATE_PLAYING:
                if save_modal.is_open:
                    save_action = save_modal.handle_event(event)
                    if save_action:
                        if save_action.startswith("save_slot_") or save_action.startswith("new_save_"):
                            save_name = (save_action.split("save_slot_", 1)[1] if save_action.startswith("save_slot_")
                                         else save_action.split("new_save_", 1)[1])
                            success, msg = save_to_slot(save_name, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager)
                            save_modal.refresh_slots(msg if success else f"Error: {msg}")
                        elif save_action.startswith("load_slot_"):
                            save_name = save_action.split("load_slot_", 1)[1]
                            success, msg = load_from_slot(save_name, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager)
                            if success:
                                save_modal.close()
                                settings_modal.close()
                                raport_ui.close()
                                market_modal.close()
                                add_item_modal.close()
                                cheat_modal.close()
                                clean_resources_dictionary(resources)
                                planning_mode = "NONE"
                                session_planned_furniture.clear()
                                selected_planned_furniture = None
                                selected_furniture = None
                                moving_furniture = None
                                camera.target_x = player.x
                                camera.target_y = player.y
                                camera.x = player.x
                                camera.y = player.y
                            else:
                                save_modal.refresh_slots(f"Error: {msg}")
                        elif save_action.startswith("delete_slot_"):
                            from game.save_system import delete_save
                            save_name = save_action.split("delete_slot_", 1)[1]
                            success, msg = delete_save(save_name)
                            save_modal.refresh_slots(msg if success else f"Error: {msg}")
                    continue

                s_action = settings_modal.handle_event(event, day_cycle, is_ingame=True)
                if s_action == "close_settings":
                    continue
                elif s_action == "unpause_game":
                    settings_modal.close()
                    continue
                elif s_action == "open_save_modal":
                    save_modal.open(mode="SAVE")
                    continue
                elif s_action == "open_load_modal":
                    save_modal.open(mode="LOAD")
                    continue
                elif s_action == "return_to_main_menu":
                    settings_modal.close()
                    current_state = STATE_MENU
                    continue
                elif settings_modal.is_open:
                    continue

                # Route all keyboard input to an open market modal before global shortcuts.
                if market_modal.is_open:
                    market_modal.handle_event(
                        event, resources, stockpile_manager,
                        servant_manager=servant_manager,
                        villager_manager=villager_manager,
                        furniture_manager=furniture_manager,
                    )
                    continue

                if builder_catalog_modal.is_open:
                    catalog_action = builder_catalog_modal.handle_event(event)
                    if catalog_action and catalog_action.startswith("commission_furniture_"):
                        planning_mode = "FURNITURE"
                        planning_furniture_type = catalog_action.removeprefix("commission_furniture_")
                        session_planned_furniture.clear()
                        selected_planned_furniture = None
                        selected_furniture = None
                    elif catalog_action and catalog_action.startswith("commission_building_"):
                        planning_mode = "BUILDING"
                        planning_building_type = catalog_action.removeprefix("commission_building_")
                        planning_building_rotation = 0
                        planning_building_tiles.clear()
                        planned_door_tile = None
                        planned_door_side = "bottom"
                    continue

                # World map overlay (M): fullscreen view-only map; WASD keeps working.
                if map_overlay.is_open:
                    map_overlay.handle_event(event)
                    continue
                if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
                    map_overlay.open()
                    continue

                any_modal_open = (
                    raport_ui.is_open or settings_modal.is_open or save_modal.is_open
                    or market_modal.is_open or add_item_modal.is_open or cheat_modal.is_open
                )
                if not any_modal_open:
                    speed_action = speed_controller.handle_event(event)
                    if speed_action is not None:
                        continue

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if not any_modal_open and path_debug_overlay.handle_event(event):
                        continue
                    if not any_modal_open and cheats_active and btn_add_item_cheat_rect.collidepoint(event.pos):
                        tgt = selected_furniture if (selected_furniture and getattr(selected_furniture, "furniture_type", "") == "household_storage") else None
                        add_item_modal.open(target_storage=tgt)
                        continue
                # -------------------------------------------------------------
                # 1. PERMIT PLANNING MODE
                # -------------------------------------------------------------
                if planning_mode == "PERMIT":
                    can_place, status_msg = permit_manager.can_place_permit_tiles(planning_permit_tiles)

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            planning_mode = "NONE"
                            planning_permit_tiles.clear()
                            permit_drag_start = None
                            permit_erase_start = None
                        elif event.key == pygame.K_BACKSPACE or event.key == pygame.K_DELETE:
                            planning_permit_tiles.clear()
                        elif event.key == pygame.K_RETURN:
                            if can_place and len(planning_permit_tiles) > 0:
                                p_title = planning_permit_type.replace('_', ' ').title()
                                p_name = f"{p_title} Lot #{permit_manager.permit_counter}"
                                permit_manager.add_permit(p_name, planning_permit_type, planning_permit_tiles)
                                planning_mode = "NONE"
                                planning_permit_tiles.clear()
                                permit_drag_start = None

                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        # Check click on UI buttons first
                        if btn_confirm_rect.collidepoint(event.pos):
                            if can_place and len(planning_permit_tiles) > 0:
                                p_title = planning_permit_type.replace('_', ' ').title()
                                p_name = f"{p_title} Lot #{permit_manager.permit_counter}"
                                permit_manager.add_permit(p_name, planning_permit_type, planning_permit_tiles)
                                planning_mode = "NONE"
                                planning_permit_tiles.clear()
                        elif btn_clear_rect.collidepoint(event.pos):
                            planning_permit_tiles.clear()
                        elif btn_cancel_rect.collidepoint(event.pos):
                            planning_mode = "NONE"
                            planning_permit_tiles.clear()
                        elif event.button == 1:
                            permit_drag_start = (m_gx, m_gy)
                        elif event.button == 3:
                            permit_erase_start = (m_gx, m_gy)

                    elif event.type == pygame.MOUSEBUTTONUP:
                        if event.button == 1 and permit_drag_start:
                            new_box = get_rect_tiles(permit_drag_start, (m_gx, m_gy))
                            planning_permit_tiles.update(new_box)
                            permit_drag_start = None
                        elif event.button == 3 and permit_erase_start:
                            erase_box = get_rect_tiles(permit_erase_start, (m_gx, m_gy))
                            planning_permit_tiles.difference_update(erase_box)
                            permit_erase_start = None

                # -------------------------------------------------------------
                # 1B. EDIT PERMIT PLANNING MODE
                # -------------------------------------------------------------
                elif planning_mode == "EDIT_PERMIT":
                    target_p = next((p for p in permit_manager.permits if p.id == editing_permit_id), None)
                    if not target_p:
                        planning_mode = "NONE"
                        planning_permit_tiles.clear()
                        continue

                    can_resize, status_msg = target_p.can_resize(
                        planning_permit_tiles,
                        other_permits=permit_manager.permits,
                        building_manager=building_manager,
                        furniture_manager=furniture_manager
                    )

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            planning_mode = "NONE"
                            planning_permit_tiles.clear()
                            permit_drag_start = None
                            permit_erase_start = None
                            editing_permit_id = None
                        elif event.key == pygame.K_BACKSPACE or event.key == pygame.K_DELETE:
                            planning_permit_tiles = set(original_permit_tiles)
                        elif event.key == pygame.K_RETURN:
                            if can_resize and len(planning_permit_tiles) > 0:
                                target_p.resize(planning_permit_tiles)
                                planning_mode = "NONE"
                                planning_permit_tiles.clear()
                                editing_permit_id = None

                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        if btn_confirm_rect.collidepoint(event.pos):
                            if can_resize and len(planning_permit_tiles) > 0:
                                target_p.resize(planning_permit_tiles)
                                planning_mode = "NONE"
                                planning_permit_tiles.clear()
                                editing_permit_id = None
                        elif btn_clear_rect.collidepoint(event.pos):
                            planning_permit_tiles = set(original_permit_tiles)
                        elif btn_cancel_rect.collidepoint(event.pos):
                            planning_mode = "NONE"
                            planning_permit_tiles.clear()
                            editing_permit_id = None
                        elif event.button == 1:
                            permit_drag_start = (m_gx, m_gy)
                        elif event.button == 3:
                            permit_erase_start = (m_gx, m_gy)

                    elif event.type == pygame.MOUSEBUTTONUP:
                        if event.button == 1 and permit_drag_start:
                            new_box = get_rect_tiles(permit_drag_start, (m_gx, m_gy))
                            planning_permit_tiles.update(new_box)
                            permit_drag_start = None
                        elif event.button == 3 and permit_erase_start:
                            erase_box = get_rect_tiles(permit_erase_start, (m_gx, m_gy))
                            planning_permit_tiles.difference_update(erase_box)
                            permit_erase_start = None

                # -------------------------------------------------------------
                # 2. BUILDING PLANNING MODE
                # -------------------------------------------------------------
                elif planning_mode == "BUILDING":
                    b_cfg = BUILDING_TYPES[planning_building_type]
                    matching_permit, status_msg = permit_manager.find_matching_permit_for_tiles(
                        planning_building_type, planning_building_tiles, building_manager, furniture_manager=furniture_manager
                    )
                    can_afford = building_manager.can_afford(planning_building_type, resources, len(planning_building_tiles))
                    is_valid_tile_count = (len(planning_building_tiles) == b_cfg["fixed_tiles_count"]) if b_cfg.get("fixed_tiles_count") else (len(planning_building_tiles) > 0)
                    if b_cfg.get("fixed_tiles_count") and len(planning_building_tiles) > 0 and len(planning_building_tiles) != b_cfg["fixed_tiles_count"]:
                        status_msg = f"Must be exactly {b_cfg['fixed_tiles_count']} tiles (2x2)"
                    is_valid_build = (matching_permit is not None) and can_afford and is_valid_tile_count

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            planning_mode = "NONE"
                            planning_building_tiles.clear()
                            building_drag_start = None
                            building_erase_start = None
                        elif event.key == pygame.K_BACKSPACE or event.key == pygame.K_DELETE:
                            planning_building_tiles.clear()
                            planned_door_tile = None
                        elif event.key == pygame.K_r and b_cfg.get("rotatable", True):
                            planning_building_rotation = (planning_building_rotation + 90) % 360
                            if planning_building_tiles:
                                min_x = min(tile[0] for tile in planning_building_tiles)
                                min_y = min(tile[1] for tile in planning_building_tiles)
                                max_x = max(tile[0] for tile in planning_building_tiles)
                                max_y = max(tile[1] for tile in planning_building_tiles)
                                old_door = planned_door_tile
                                planning_building_tiles = {
                                    (min_x + (tile[1] - min_y), min_y + (max_x - tile[0]))
                                    for tile in planning_building_tiles
                                }
                                if old_door:
                                    planned_door_tile = (min_x + (old_door[1] - min_y), min_y + (max_x - old_door[0]))
                                planned_door_side = {"top": "right", "right": "bottom", "bottom": "left", "left": "top"}.get(planned_door_side, planned_door_side)
                        elif event.key == pygame.K_RETURN:
                            if is_valid_build:
                                started = building_manager.start_construction(
                                    planning_building_type, planning_building_tiles,
                                    planned_door_tile, planned_door_side, permit_manager,
                                    rotation=planning_building_rotation
                                )
                                if started and b_cfg.get("builder_commissionable"):
                                    from game.systems.work.builder_system import BuilderSystem
                                    BuilderSystem.dispatch_pending_public_commissions(
                                        building_manager, servant_manager, villager_manager,
                                        furniture_manager, day_cycle=day_cycle,
                                        stockpile_manager=stockpile_manager,
                                    )
                                planning_mode = "NONE"
                                planning_building_tiles.clear()
                                planned_door_tile = None

                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        # UI button checks
                        if btn_confirm_rect.collidepoint(event.pos):
                            if is_valid_build:
                                started = building_manager.start_construction(
                                    planning_building_type, planning_building_tiles,
                                    planned_door_tile, planned_door_side, permit_manager,
                                    rotation=planning_building_rotation
                                )
                                if started and b_cfg.get("builder_commissionable"):
                                    from game.systems.work.builder_system import BuilderSystem
                                    BuilderSystem.dispatch_pending_public_commissions(
                                        building_manager, servant_manager, villager_manager,
                                        furniture_manager, day_cycle=day_cycle,
                                        stockpile_manager=stockpile_manager,
                                    )
                                planning_mode = "NONE"
                                planning_building_tiles.clear()
                                planned_door_tile = None
                        elif btn_clear_rect.collidepoint(event.pos):
                            planning_building_tiles.clear()
                            planned_door_tile = None
                        elif btn_cancel_rect.collidepoint(event.pos):
                            planning_mode = "NONE"
                            planning_building_tiles.clear()
                            planned_door_tile = None
                        elif event.button == 1:
                            # Cek apakah pemain mengklik dinding batas luar untuk menempatkan PINTU
                            if b_cfg.get("has_door", True) and (m_gx, m_gy) in planning_building_tiles:
                                edges = get_exterior_edges_for_tile((m_gx, m_gy), planning_building_tiles)
                                if edges:
                                    if planned_door_tile == (m_gx, m_gy):
                                        idx = (edges.index(planned_door_side) + 1) % len(edges) if planned_door_side in edges else 0
                                        planned_door_side = edges[idx]
                                    else:
                                        planned_door_tile = (m_gx, m_gy)
                                        planned_door_side = edges[0]
                                    building_drag_start = None
                                    continue
                            elif (b_cfg.get("fixed_tiles_count") and b_cfg.get("width_tiles")
                                  and b_cfg.get("height_tiles")):
                                # Place a configured fixed-footprint structure, rotated as needed.
                                w_w = int(b_cfg["width_tiles"])
                                w_h = int(b_cfg["height_tiles"])
                                if planning_building_rotation % 180:
                                    w_w, w_h = w_h, w_w
                                planning_building_tiles = {
                                    (m_gx + dx, m_gy + dy)
                                    for dx in range(w_w) for dy in range(w_h)
                                }
                                planned_door_tile = None
                                planned_door_side = None
                                building_drag_start = None
                                continue
                            building_drag_start = (m_gx, m_gy)
                        elif event.button == 3:
                            building_erase_start = (m_gx, m_gy)

                    elif event.type == pygame.MOUSEBUTTONUP:
                        if event.button == 1 and building_drag_start:
                            new_box = get_rect_tiles(building_drag_start, (m_gx, m_gy))
                            planning_building_tiles.update(new_box)

                            # Auto-fallback door jika belum ada pintu yang valid
                            if b_cfg.get("has_door", True):
                                if planned_door_tile is None or planned_door_tile not in planning_building_tiles or not get_exterior_edges_for_tile(planned_door_tile, planning_building_tiles):
                                    sorted_tiles = sorted(planning_building_tiles, key=lambda t: (-t[1], t[0]))
                                    for t in sorted_tiles:
                                        edges = get_exterior_edges_for_tile(t, planning_building_tiles)
                                        if "bottom" in edges:
                                            planned_door_tile = t
                                            planned_door_side = "bottom"
                                            break
                                        elif edges:
                                            planned_door_tile = t
                                            planned_door_side = edges[0]
                                            break
                            else:
                                planned_door_tile = None
                                planned_door_side = None
                            building_drag_start = None
                        elif event.button == 3 and building_erase_start:
                            erase_box = get_rect_tiles(building_erase_start, (m_gx, m_gy))
                            planning_building_tiles.difference_update(erase_box)
                            if planned_door_tile in erase_box:
                                planned_door_tile = None
                            building_erase_start = None

                # -------------------------------------------------------------
                # 3. FURNITURE PLANNING MODE (Continuous Placement Session)
                # -------------------------------------------------------------
                elif planning_mode == "FURNITURE":
                    f_cfg = FURNITURE_TYPES.get(planning_furniture_type, FURNITURE_TYPES["household_storage"])
                    fw, fh = max(1, int(f_cfg.get("width_tiles", 1))), max(1, int(f_cfg.get("height_tiles", 1)))
                    if planning_furniture_rotation % 180:
                        fw, fh = fh, fw
                    footprint = {(m_gx + dx, m_gy + dy) for dx in range(fw) for dy in range(fh)}
                    footprint_context = []
                    for tx, ty in footprint:
                        target_permit = permit_manager.get_permit_at(tx, ty)
                        b_at = building_manager.get_building_at(tx, ty)
                        inside = b_at is not None and not getattr(b_at, "is_solid", False) and getattr(b_at, "building_type", "") != "well" and (tx, ty) != getattr(b_at, "door_pos", None)
                        is_door_tile = b_at is not None and getattr(b_at, "door_pos", None) == (tx, ty)
                        allowed = f_cfg.get("allowed_permits")
                        permit_allowed = f_cfg.get("placement_anywhere") or not allowed or (target_permit is not None and target_permit.permit_type in allowed)
                        footprint_context.append(((f_cfg.get("placement_anywhere") or target_permit is not None or inside) and permit_allowed and not is_door_tile,
                                                 furniture_manager.get_furniture_at(tx, ty) is not None))
                    planned_tiles = set()
                    for pf in session_planned_furniture:
                        p_cfg = FURNITURE_TYPES.get(pf.get("type", planning_furniture_type), f_cfg)
                        p_w, p_h = max(1, int(p_cfg.get("width_tiles", 1))), max(1, int(p_cfg.get("height_tiles", 1)))
                        if int(pf.get("rotation", 0)) % 180:
                            p_w, p_h = p_h, p_w
                        planned_tiles.update((pf["gx"] + dx, pf["gy"] + dy) for dx in range(p_w) for dy in range(p_h))
                    is_valid_place = all(valid and not occupied for valid, occupied in footprint_context) and not (footprint & planned_tiles)
                    if planning_furniture_type == "miner_workstation" and is_valid_place:
                        from game.world.natural_resources import get_natural_resources
                        is_valid_place = get_natural_resources().mine_for_footprint(footprint) is not None

                    is_valid_build = bool(session_planned_furniture)

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            session_planned_furniture.clear()
                            selected_planned_furniture = None
                            planning_mode = "NONE"
                            planning_furniture_type = None
                        elif event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
                            if selected_planned_furniture is not None:
                                session_planned_furniture = [pf for pf in session_planned_furniture if (pf["gx"], pf["gy"]) != selected_planned_furniture]
                                selected_planned_furniture = None
                            else:
                                session_planned_furniture.clear()
                        elif event.key == pygame.K_r and f_cfg.get("rotatable", True):
                            if selected_planned_furniture is not None:
                                planned_item = next((item for item in session_planned_furniture
                                                     if (item["gx"], item["gy"]) == selected_planned_furniture), None)
                                if planned_item:
                                    planned_item["rotation"] = (int(planned_item.get("rotation", 0)) + 90) % 360
                                    planning_furniture_rotation = planned_item["rotation"]
                            else:
                                planning_furniture_rotation = (planning_furniture_rotation + 90) % 360
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            if is_valid_build:
                                for pf in session_planned_furniture:
                                    furniture_manager.add_furniture(
                                        pf["type"], pf["gx"], pf["gy"],
                                        permit_manager, villager_manager, resources,
                                        building_manager=building_manager,
                                        rotation=pf.get("rotation", 0)
                                    )
                                session_planned_furniture.clear()
                                selected_planned_furniture = None
                                planning_mode = "NONE"
                                planning_furniture_type = None

                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        if btn_confirm_rect.collidepoint(event.pos):
                            if is_valid_build:
                                for pf in session_planned_furniture:
                                    furniture_manager.add_furniture(
                                        pf["type"], pf["gx"], pf["gy"],
                                        permit_manager, villager_manager, resources,
                                        building_manager=building_manager,
                                        rotation=pf.get("rotation", 0)
                                    )
                                session_planned_furniture.clear()
                                selected_planned_furniture = None
                                planning_mode = "NONE"
                                planning_furniture_type = None
                        elif btn_clear_rect.collidepoint(event.pos):
                            session_planned_furniture.clear()
                            selected_planned_furniture = None
                        elif btn_cancel_rect.collidepoint(event.pos):
                            session_planned_furniture.clear()
                            selected_planned_furniture = None
                            planning_mode = "NONE"
                            planning_furniture_type = None
                        elif event.button == 3:
                            if is_occupied_planned:
                                session_planned_furniture = [pf for pf in session_planned_furniture if (pf["gx"], pf["gy"]) != (m_gx, m_gy)]
                                if selected_planned_furniture == (m_gx, m_gy):
                                    selected_planned_furniture = None
                            elif len(session_planned_furniture) == 0:
                                planning_mode = "NONE"
                                planning_furniture_type = None
                                selected_planned_furniture = None
                        elif event.button == 1:
                            if is_occupied_planned:
                                if selected_planned_furniture == (m_gx, m_gy):
                                    selected_planned_furniture = None
                                else:
                                    selected_planned_furniture = (m_gx, m_gy)
                            elif is_valid_place:
                                session_planned_furniture.append({
                                    "gx": m_gx,
                                    "gy": m_gy,
                                    "type": planning_furniture_type,
                                    "rotation": planning_furniture_rotation
                                })
                                selected_planned_furniture = None

                # -------------------------------------------------------------
                # 3.5. MOVE FURNITURE PLANNING MODE
                # -------------------------------------------------------------
                elif planning_mode == "MOVE_FURNITURE" and moving_furniture:
                    target_permit = permit_manager.get_permit_at(m_gx, m_gy)
                    b_at = building_manager.get_building_at(m_gx, m_gy)
                    move_w, move_h = moving_furniture.footprint_dimensions
                    move_tiles = {(m_gx + dx, m_gy + dy) for dx in range(move_w) for dy in range(move_h)}
                    is_blocked = False
                    for move_tx, move_ty in move_tiles:
                        tile_building = building_manager.get_building_at(move_tx, move_ty)
                        tile_permit = permit_manager.get_permit_at(move_tx, move_ty)
                        allowed = moving_furniture.type_cfg.get("allowed_permits")
                        allowed_here = not allowed or (tile_permit is not None and tile_permit.permit_type in allowed)
                        inside = (tile_building is not None
                                  and not getattr(tile_building, "is_solid", False)
                                  and getattr(tile_building, "building_type", "") != "well"
                                  and (move_tx, move_ty) != getattr(tile_building, "door_pos", None))
                        if (not allowed_here and not inside) or (tile_building is not None and not inside):
                            is_blocked = True
                            break
                    other_tiles = set()
                    for existing_furniture in furniture_manager.furnitures:
                        if existing_furniture.id != moving_furniture.id and not existing_furniture.is_dropped:
                            other_tiles.update(furniture_manager._furniture_tiles(existing_furniture))
                    is_valid_dest = not is_blocked and not bool(move_tiles & other_tiles)

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE or event.key == pygame.K_BACKSPACE:
                            planning_mode = "NONE"
                            moving_furniture = None
                        elif event.key == pygame.K_r and moving_furniture.type_cfg.get("rotatable", True):
                            moving_furniture.rotation = (moving_furniture.rotation + 90) % 360
                            furniture_manager.invalidate_cache()
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        if btn_cancel_rect.collidepoint(event.pos) or event.button == 3:
                            planning_mode = "NONE"
                            moving_furniture = None
                        elif event.button == 1:
                            if btn_confirm_rect.collidepoint(event.pos) or is_valid_dest:
                                pid = target_permit.id if target_permit else None
                                moving_furniture.designate_move(m_gx, m_gy, pid)
                                planning_mode = "NONE"
                                moving_furniture = None

                # -------------------------------------------------------------
                # 3.7. ROAD PAINTING MODE (instant tile layer, pay per tile)
                # -------------------------------------------------------------
                elif planning_mode == "ROAD":
                    from game.world.roads import get_roads
                    from game.world.island import is_land_tile
                    from game.world.natural_resources import get_natural_resources
                    roads = get_roads()
                    nr = get_natural_resources()
                    r_cfg = ROAD_TYPES.get(planning_road_type, ROAD_TYPES["dirt_road"])

                    def road_tile_valid(tx, ty):
                        if not is_land_tile(tx, ty):
                            return False
                        if (tx, ty) in planning_road_tiles or (tx, ty) in roads.tiles:
                            return False
                        if building_manager.get_building_at(tx, ty):
                            return False
                        if building_manager.get_site_at(tx, ty):
                            return False
                        if furniture_manager.get_furniture_at(tx, ty):
                            return False
                        if stockpile_manager.get_stack_at(tx, ty):
                            return False
                        if nr.get_mine_at(tx, ty):
                            return False
                        return True

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            planning_mode = "NONE"
                            planning_road_tiles.clear()
                            road_drag_start = None
                        elif event.key == pygame.K_RETURN:
                            new_tiles = {t for t in planning_road_tiles if road_tile_valid(*t)}
                            cost = {}
                            for _ in new_tiles:
                                for res, amt in r_cfg["cost"].items():
                                    cost[res] = cost.get(res, 0) + amt
                            if new_tiles and all(resources.get(r, 0) >= a for r, a in cost.items()):
                                for r, a in cost.items():
                                    resources[r] -= a
                                roads.set_tiles(new_tiles, planning_road_type)
                                planning_mode = "NONE"
                                planning_road_tiles.clear()
                    elif event.type == pygame.MOUSEMOTION:
                        if road_drag_start and event.buttons[0]:
                            planning_road_tiles.add((m_gx, m_gy))
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        if btn_confirm_rect.collidepoint(event.pos):
                            new_tiles = {t for t in planning_road_tiles if road_tile_valid(*t)}
                            cost = {}
                            for _ in new_tiles:
                                for res, amt in r_cfg["cost"].items():
                                    cost[res] = cost.get(res, 0) + amt
                            if new_tiles and all(resources.get(r, 0) >= a for r, a in cost.items()):
                                for r, a in cost.items():
                                    resources[r] -= a
                                roads.set_tiles(new_tiles, planning_road_type)
                                planning_mode = "NONE"
                                planning_road_tiles.clear()
                                road_drag_start = None
                        elif btn_clear_rect.collidepoint(event.pos):
                            planning_road_tiles.clear()
                        elif btn_cancel_rect.collidepoint(event.pos):
                            planning_mode = "NONE"
                            planning_road_tiles.clear()
                            road_drag_start = None
                        elif event.button == 1:
                            road_drag_start = (m_gx, m_gy)
                            planning_road_tiles.add((m_gx, m_gy))
                        elif event.button == 3:
                            planning_road_tiles.discard((m_gx, m_gy))
                            road_drag_start = None

                # -------------------------------------------------------------
                # 3.8. DESTROY MODE — mark objects, DONE -> confirm -> execute
                # -------------------------------------------------------------
                elif planning_mode == "DESTROY":
                    from game.world.roads import get_roads
                    roads = get_roads()

                    def destroy_hit(tx, ty):
                        """Topmost destroyable object at tile, or None."""
                        site = building_manager.get_site_at(tx, ty)
                        if site is not None:
                            return ("site", site)
                        if building_manager.get_demolition_at(tx, ty) is not None:
                            return None  # already being demolished
                        b = building_manager.get_building_at(tx, ty)
                        if b is not None:
                            return ("building", b)
                        if roads.road_type_at(tx, ty) is not None:
                            return ("road", (tx, ty))
                        return None

                    def destroy_same(mark, hit):
                        if mark[0] != hit[0]:
                            return False
                        if mark[0] == "road":
                            return mark[1] == hit[1]
                        return mark[1] is hit[1]

                    if destroy_confirm is not None:
                        # Confirm popup: YES executes all marks, NO keeps marking.
                        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            if destroy_yes_rect.collidepoint(event.pos):
                                for kind, obj in destroy_confirm["marks"]:
                                    if kind == "site":
                                        building_manager.cancel_construction(
                                            obj, resources=resources,
                                            stockpile_manager=stockpile_manager,
                                            all_servants=servant_manager.servants,
                                            furniture_manager=furniture_manager)
                                    elif kind == "building":
                                        building_manager.start_demolition(obj)
                                    elif kind == "road":
                                        roads.remove_tiles([obj])
                                destroy_confirm = None
                                destroy_marks.clear()
                                planning_mode = "NONE"
                            elif destroy_no_rect.collidepoint(event.pos):
                                destroy_confirm = None
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            planning_mode = "NONE"
                            destroy_marks.clear()
                        elif event.key == pygame.K_RETURN and destroy_marks:
                            destroy_confirm = {"marks": list(destroy_marks)}
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        if btn_done_rect.collidepoint(event.pos) and destroy_marks:
                            destroy_confirm = {"marks": list(destroy_marks)}
                        elif btn_cancel_rect.collidepoint(event.pos):
                            planning_mode = "NONE"
                            destroy_marks.clear()
                        elif event.button == 1:
                            hit = destroy_hit(m_gx, m_gy)
                            if hit is not None:
                                existing = next((m for m in destroy_marks if destroy_same(m, hit)), None)
                                if existing is not None:
                                    destroy_marks.remove(existing)
                                else:
                                    destroy_marks.append(hit)

                # -------------------------------------------------------------
                # 4. RAPORT MODAL OPEN
                # -------------------------------------------------------------
                elif raport_ui.is_open:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        if raport_ui.is_text_input_active():
                            raport_ui.handle_event(event, building_manager, permit_manager, resources, servant_manager, villager_manager, schedule_manager=schedule_manager, day_cycle=day_cycle, stockpile_manager=stockpile_manager, furniture_manager=furniture_manager, production_system=production_system)
                        else:
                            raport_ui.close()
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                        if not raport_ui.is_text_input_active():
                            raport_ui.close()
                        else:
                            raport_ui.handle_event(event, building_manager, permit_manager, resources, servant_manager, villager_manager, schedule_manager=schedule_manager, day_cycle=day_cycle, stockpile_manager=stockpile_manager, furniture_manager=furniture_manager, production_system=production_system)
                    else:
                        action = raport_ui.handle_event(event, building_manager, permit_manager, resources, servant_manager, villager_manager, schedule_manager=schedule_manager, day_cycle=day_cycle, stockpile_manager=stockpile_manager, furniture_manager=furniture_manager, production_system=production_system)
                        if action == "open_market_profile" and getattr(raport_ui, "selected_market_building", None):
                            market_modal.open(raport_ui.selected_market_building)
                            continue
                        elif raport_ui.selected_building_type is not None:
                            planning_mode = "BUILDING"
                            planning_building_type = raport_ui.selected_building_type
                            planning_building_rotation = 0
                            raport_ui.selected_building_type = None
                            planning_building_tiles.clear()
                            planned_door_tile = None
                            planned_door_side = "bottom"
                        elif raport_ui.selected_furniture_type is not None:
                            planning_mode = "FURNITURE"
                            planning_furniture_type = raport_ui.selected_furniture_type
                            planning_furniture_rotation = 0
                            raport_ui.selected_furniture_type = None
                            session_planned_furniture.clear()
                            selected_planned_furniture = None
                        elif raport_ui.selected_road_type is not None:
                            planning_mode = "ROAD"
                            planning_road_type = raport_ui.selected_road_type
                            raport_ui.selected_road_type = None
                            planning_road_tiles.clear()
                            road_drag_start = None
                        elif action == "start_destroy_mode":
                            planning_mode = "DESTROY"
                            destroy_marks.clear()
                            destroy_confirm = None
                        elif raport_ui.placing_permit_type is not None:
                            planning_mode = "PERMIT"
                            planning_permit_type = raport_ui.placing_permit_type
                            raport_ui.placing_permit_type = None
                            planning_permit_tiles.clear()
                        elif action == "move_furniture" and getattr(raport_ui, "moving_furniture", None):
                            planning_mode = "MOVE_FURNITURE"
                            moving_furniture = raport_ui.moving_furniture
                            raport_ui.moving_furniture = None
                        elif action == "destroy_furniture" and getattr(raport_ui, "destroying_furniture_id", None):
                            furniture_manager.destroy_furniture(
                                raport_ui.destroying_furniture_id,
                                stockpile_manager=stockpile_manager,
                                resources=resources,
                                villager_manager=villager_manager,
                                servant_manager=servant_manager
                            )
                            raport_ui.destroying_furniture_id = None
                        elif action and action.startswith("edit_permit_"):
                            pid = action.replace("edit_permit_", "")
                            target_p = next((p for p in permit_manager.permits if p.id == pid), None)
                            if target_p:
                                planning_mode = "EDIT_PERMIT"
                                editing_permit_id = pid
                                planning_permit_tiles = set(target_p.tiles)
                                original_permit_tiles = set(target_p.tiles)
                                permit_drag_start = None
                                permit_erase_start = None

                # -------------------------------------------------------------
                # 4.5. MARKET PROFILE MODAL OPEN
                # -------------------------------------------------------------
                elif market_modal.is_open:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        market_modal.close()
                    else:
                        market_modal.handle_event(event, resources, stockpile_manager, servant_manager=servant_manager, villager_manager=villager_manager, furniture_manager=furniture_manager)

                # -------------------------------------------------------------
                # 4.6. ADD ITEM CHEAT MODAL OPEN (AGENT 2)
                # -------------------------------------------------------------
                elif add_item_modal.is_open:
                    res = add_item_modal.handle_event(event, resources=resources, stockpile_manager=stockpile_manager, permit_manager=permit_manager, building_manager=building_manager, furniture_manager=furniture_manager)
                    if res is not None:
                        success, msg = res
                        cheat_notice = msg
                        cheat_notice_timer = 4.0

                # -------------------------------------------------------------
                # 4.7. CHEAT MODAL (ESC menu → Active Cheat → password)
                # -------------------------------------------------------------
                elif cheat_modal.is_open:
                    c_action = cheat_modal.handle_event(event, cheats_active=cheats_active)
                    if c_action == "activate_cheats":
                        cheats_active = True
                    elif c_action == "deactivate_cheats":
                        cheats_active = False
                    elif c_action == "unpause_game":
                        continue
                    elif c_action == "open_save_modal":
                        save_modal.open(mode="SAVE")
                        continue
                    elif c_action == "open_load_modal":
                        save_modal.open(mode="LOAD")
                        continue
                    elif c_action == "return_to_main_menu":
                        current_state = STATE_MENU
                        continue

                # -------------------------------------------------------------
                # 4.8. STARTER PLACEMENT MODE (pick drop location → confirm)
                # -------------------------------------------------------------
                elif pending_starter_id is not None:
                    from game.systems.core.starter_preset import StarterPresetSystem
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        if starter_confirm_tile is not None:
                            starter_confirm_tile = None
                        else:
                            pending_starter_id = None
                            starter_confirm_tile = None
                            villager_manager.generate_starter_family()
                            cheat_notice = "Starter placement cancelled — plain start."
                            cheat_notice_timer = 4.0
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                        if starter_confirm_tile is not None:
                            starter_confirm_tile = None
                        else:
                            pending_starter_id = None
                            starter_confirm_tile = None
                            villager_manager.generate_starter_family()
                            cheat_notice = "Starter placement cancelled — plain start."
                            cheat_notice_timer = 4.0
                    elif event.type == pygame.MOUSEWHEEL:
                        camera.handle_zoom(event.y)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if starter_confirm_tile is not None:
                            if starter_done_btn_rect.collidepoint(event.pos):
                                ok = StarterPresetSystem.apply(
                                    pending_starter_id, villager_manager,
                                    furniture_manager, building_manager,
                                    permit_manager,
                                    stockpile_manager=stockpile_manager,
                                    anchor_tile=starter_confirm_tile)
                                if ok:
                                    placed_id = pending_starter_id
                                    placed_anchor = starter_confirm_tile
                                    pending_starter_id = None
                                    starter_confirm_tile = None
                                    # Spawn player & servants at the house door
                                    _pcfg = StarterPresetSystem.get_preset(placed_id)
                                    _hc = (_pcfg or {}).get("house") or {}
                                    _hw = int(_hc.get("width", 0) or 0)
                                    _hh = int(_hc.get("height", 0) or 0)
                                    if _hw and _hh and placed_anchor:
                                        _hx = placed_anchor[0] - _hw // 2
                                        _hy = placed_anchor[1] - _hh // 2
                                        _door_tx = _hx + _hw // 2
                                        _door_ty = _hy + _hh - 1
                                    else:
                                        _door_tx, _door_ty = placed_anchor or (0, 0)
                                    _px = (_door_tx + 0.5) * TILE_SIZE
                                    _py = (_door_ty + 1.5) * TILE_SIZE
                                    player.x = _px
                                    player.y = _py
                                    for i, s in enumerate(servant_manager.servants):
                                        s.x = _px + (i - len(servant_manager.servants) / 2) * TILE_SIZE * 0.5
                                        s.y = _py + TILE_SIZE * 0.5
                                    camera.x = player.x
                                    camera.y = player.y
                                else:
                                    starter_confirm_tile = None
                                    cheat_notice = "Could not place starter there."
                                    cheat_notice_timer = 4.0
                            elif starter_cancel_btn_rect.collidepoint(event.pos):
                                starter_confirm_tile = None
                        else:
                            wx, wy = camera.screen_to_world(event.pos[0], event.pos[1])
                            gx = int(math.floor(wx / TILE_SIZE))
                            gy = int(math.floor(wy / TILE_SIZE))
                            _, valid = StarterPresetSystem.get_anchor_preview(
                                pending_starter_id, (gx, gy),
                                building_manager, permit_manager,
                                furniture_manager)
                            if valid:
                                starter_confirm_tile = (gx, gy)
                            else:
                                cheat_notice = "Invalid location for starter village."
                                cheat_notice_timer = 2.0

                # -------------------------------------------------------------
                # 5. NORMAL GAMEPLAY
                # -------------------------------------------------------------
                else:
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            cheat_modal.open()
                        elif event.key == pygame.K_r:
                            if not raport_ui.is_text_input_active():
                                raport_ui.open()
                    elif event.type == pygame.MOUSEWHEEL:
                        if entity_happiness_rect.collidepoint(pygame.mouse.get_pos()):
                            selected_entity_happiness_scroll = max(
                                0, selected_entity_happiness_scroll - event.y
                            )
                        else:
                            camera.handle_zoom(event.y)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        action = raport_ui.handle_event(event, building_manager, permit_manager, resources, servant_manager, villager_manager, schedule_manager=schedule_manager, day_cycle=day_cycle, stockpile_manager=stockpile_manager, furniture_manager=furniture_manager, production_system=production_system)
                        if action == "toggle_raport":
                            continue
                        if action == "open_market_profile" and getattr(raport_ui, "selected_market_building", None):
                            market_modal.open(raport_ui.selected_market_building)
                            continue

                        if raport_ui.selected_building_type is not None:
                            planning_mode = "BUILDING"
                            planning_building_type = raport_ui.selected_building_type
                            planning_building_rotation = 0
                            raport_ui.selected_building_type = None
                            planning_building_tiles.clear()
                            planned_door_tile = None
                            planned_door_side = "bottom"
                        elif raport_ui.selected_furniture_type is not None:
                            planning_mode = "FURNITURE"
                            planning_furniture_type = raport_ui.selected_furniture_type
                            planning_furniture_rotation = 0
                            raport_ui.selected_furniture_type = None
                            session_planned_furniture.clear()
                            selected_planned_furniture = None
                        elif raport_ui.selected_road_type is not None:
                            planning_mode = "ROAD"
                            planning_road_type = raport_ui.selected_road_type
                            raport_ui.selected_road_type = None
                            planning_road_tiles.clear()
                            road_drag_start = None
                        elif action == "start_destroy_mode":
                            planning_mode = "DESTROY"
                            destroy_marks.clear()
                            destroy_confirm = None
                        elif raport_ui.placing_permit_type is not None:
                            planning_mode = "PERMIT"
                            planning_permit_type = raport_ui.placing_permit_type
                            raport_ui.placing_permit_type = None
                            planning_permit_tiles.clear()
                        elif action == "move_furniture" and getattr(raport_ui, "moving_furniture", None):
                            planning_mode = "MOVE_FURNITURE"
                            moving_furniture = raport_ui.moving_furniture
                            raport_ui.moving_furniture = None
                        elif action == "destroy_furniture" and getattr(raport_ui, "destroying_furniture_id", None):
                            furniture_manager.destroy_furniture(
                                raport_ui.destroying_furniture_id,
                                stockpile_manager=stockpile_manager,
                                resources=resources,
                                villager_manager=villager_manager,
                                servant_manager=servant_manager
                            )
                            raport_ui.destroying_furniture_id = None
                        elif action and action.startswith("edit_permit_"):
                            pid = action.replace("edit_permit_", "")
                            target_p = next((p for p in permit_manager.permits if p.id == pid), None)
                            if target_p:
                                planning_mode = "EDIT_PERMIT"
                                editing_permit_id = pid
                                planning_permit_tiles = set(target_p.tiles)
                                original_permit_tiles = set(target_p.tiles)
                                permit_drag_start = None
                                permit_erase_start = None
                        elif not raport_ui.is_open:
                            # 0A-1. Mine info popup — klik di luar/close
                            if mine_popup is not None:
                                if not mine_popup_rect.collidepoint(event.pos):
                                    mine_popup = None

                            # 0A0. Workplace popup (Permit/Structure + Workstation) — klik di luar/close
                            if workplace_popup is not None:
                                kind = workplace_popup["kind"]
                                obj = workplace_popup["obj"]
                                bases = workplace_bases_for(kind, obj)
                                if wp_close_btn_rect.collidepoint(event.pos) or not wp_popup_rect.collidepoint(event.pos):
                                    workplace_popup = None
                                elif wp_base_btn_rect.collidepoint(event.pos):
                                    workplace_popup = None
                                    base = "permit" if "permit" in bases else "structure"
                                    if base == "permit" and kind == "permit":
                                        raport_ui.open_permit_directly(obj.id, permit_manager)
                                    elif base == "structure":
                                        if kind == "building":
                                            raport_ui.open_building_directly(obj)
                                        else:
                                            selected_furniture = obj
                                            selected_entity = None
                                elif wp_ws_btn_rect.collidepoint(event.pos):
                                    workplace_popup = None
                                    job_id = workplace_job_for(kind, obj)
                                    if job_id:
                                        raport_ui.open_workplace_workstations(job_id, (kind, obj))
                                continue

                            # 0A. Klik pada Tombol di Menu Konteks Furniture jika sedang terbuka
                            if selected_furniture is not None:
                                order = getattr(selected_furniture, "construction_order", None) or {}
                                furn_action_hit = False
                                for ab in furn_action_btns:
                                    if ab["rect"].collidepoint(event.pos):
                                        act = ab["action"]
                                        if act == "catalogue":
                                            builder_catalog_modal.open(selected_furniture)
                                        elif act == "immigrants":
                                            raport_ui.open_immigrant_tab()
                                        elif act == "workplace":
                                            jid = workplace_job_for("furniture", selected_furniture)
                                            if jid:
                                                raport_ui.open_workplace_workstations(jid, ("furniture", selected_furniture))
                                        selected_furniture = None
                                        furn_action_hit = True
                                        break
                                if furn_action_hit:
                                    continue
                                if btn_furn_move_rect and btn_furn_move_rect.collidepoint(event.pos):
                                    moving_furniture = selected_furniture
                                    planning_mode = "MOVE_FURNITURE"
                                    selected_furniture = None
                                    continue
                                elif btn_furn_destroy_rect and btn_furn_destroy_rect.collidepoint(event.pos):
                                    furniture_manager.destroy_furniture(
                                        selected_furniture.id,
                                        stockpile_manager=stockpile_manager,
                                        resources=resources,
                                        villager_manager=villager_manager,
                                        servant_manager=servant_manager
                                    )
                                    selected_furniture = None
                                    continue
                                elif btn_furn_store_rect and btn_furn_store_rect.collidepoint(event.pos):
                                    furniture_manager.store_uninstalled_furniture(selected_furniture.id)
                                    selected_furniture = None
                                    continue
                                elif btn_furn_house_rect and btn_furn_house_rect.collidepoint(event.pos):
                                    if selected_furniture.family_id:
                                        raport_ui.open_household_directly(selected_furniture.family_id)
                                    selected_furniture = None
                                    continue
                                elif btn_furn_poss_rect and btn_furn_poss_rect.collidepoint(event.pos):
                                    if selected_furniture.family_id:
                                        raport_ui.open_possession_directly(selected_furniture.family_id)
                                    selected_furniture = None
                                    continue
                                elif btn_furn_close_rect and btn_furn_close_rect.collidepoint(event.pos):
                                    selected_furniture = None
                                    continue

                            # 0A1b. Klik pada Tombol di Menu Konteks Public Structure
                            if selected_structure is not None:
                                s_b = selected_structure
                                struct_hit = False
                                for ab in struct_action_btns:
                                    if ab["rect"].collidepoint(event.pos):
                                        act = ab["action"]
                                        if act == "list":
                                            raport_ui.open_building_directly(s_b)
                                        elif act == "market":
                                            market_modal.open(s_b)
                                            raport_ui.close()
                                        elif act == "workplace":
                                            jid = workplace_job_for("building", s_b)
                                            if jid:
                                                raport_ui.open_workplace_workstations(jid, ("building", s_b))
                                        elif act == "destroy":
                                            building_manager.start_demolition(s_b)
                                        selected_structure = None
                                        struct_hit = True
                                        break
                                if not struct_hit and btn_struct_list_rect and btn_struct_list_rect.collidepoint(event.pos):
                                    raport_ui.open_building_directly(s_b)
                                    selected_structure = None
                                    struct_hit = True
                                if not struct_hit and btn_struct_destroy_rect and btn_struct_destroy_rect.collidepoint(event.pos):
                                    building_manager.start_demolition(s_b)
                                    selected_structure = None
                                    struct_hit = True
                                if not struct_hit and btn_struct_close_rect and btn_struct_close_rect.collidepoint(event.pos):
                                    selected_structure = None
                                    struct_hit = True
                                if not struct_hit and struct_menu_rect and not struct_menu_rect.collidepoint(event.pos):
                                    selected_structure = None

                            # 0A2. Cek apakah pemain mengklik tombol close / action pada kartu profil entitas
                            if selected_entity is not None:
                                if btn_entity_close_rect and btn_entity_close_rect.collidepoint(event.pos):
                                    selected_entity = None
                                    selected_entity_happiness_scroll = 0
                                    continue
                                elif btn_entity_household_rect and btn_entity_household_rect.collidepoint(event.pos):
                                    fam_id = getattr(selected_entity, "family_id", None)
                                    if fam_id:
                                        raport_ui.open_household_directly(fam_id)
                                        selected_entity = None
                                        continue

                            # Furniture with dedicated action UIs (workbench catalogue,
                            # notice board ledger, job workplaces) still gets the context
                            # menu first — those UIs are buttons inside the menu. They are
                            # checked before entities so a worker standing on the tile
                            # doesn't swallow the click.
                            clicked_f = furniture_manager.get_furniture_at(m_gx, m_gy)
                            if clicked_f and (clicked_f.furniture_type in ("builder_workbench", "notice_board")
                                              or workplace_bases_for("furniture", clicked_f)):
                                selected_furniture = clicked_f
                                selected_entity = None
                                selected_structure = None
                                workplace_popup = None
                                continue

                            # 0A3. Cek apakah pemain mengklik entitas AI di peta (Villager / Servant)
                            clicked_ai = None
                            if villager_manager:
                                for v in villager_manager.get_all_villagers():
                                    dist_v = math.hypot(v.x - m_wx, v.y - m_wy)
                                    if dist_v <= max(v.radius + 8, 28):
                                        clicked_ai = v
                                        break
                            if not clicked_ai and servant_manager:
                                for s in servant_manager.servants:
                                    dist_s = math.hypot(s.x - m_wx, s.y - m_wy)
                                    if dist_s <= max(s.radius + 8, 28):
                                        clicked_ai = s
                                        break

                            if clicked_ai:
                                selected_entity = clicked_ai
                                selected_entity_happiness_scroll = 0
                                selected_furniture = None
                                continue
                            else:
                                if selected_entity is not None and entity_card_rect and not entity_card_rect.collidepoint(event.pos):
                                    selected_entity = None
                                    selected_entity_happiness_scroll = 0

                            # 0B. Cek apakah pemain mengklik furniture fisik di peta (INSTALLED maupun UNINSTALLED)
                            clicked_f = furniture_manager.get_furniture_at(m_gx, m_gy)
                            if clicked_f:
                                selected_entity = None
                                selected_structure = None
                                workplace_popup = None
                                selected_furniture = clicked_f
                                continue
                            else:
                                if selected_furniture is not None and furn_menu_rect and not furn_menu_rect.collidepoint(event.pos):
                                    selected_furniture = None

                            # 0C. Cek apakah pemain mengklik tumpukan barang / alat di tanah (Dropped Item Stack)
                            clicked_stack = stockpile_manager.get_stack_at(m_gx, m_gy) if stockpile_manager else None
                            if clicked_stack:
                                selected_furniture = None
                                selected_entity = None

                                if clicked_stack.owner_type == "villager":
                                    owner_family = next((fam for fam in villager_manager.families if str(fam.id) == str(clicked_stack.owner_id)), None)
                                    assigned_worker = None
                                    if owner_family:
                                        for m in owner_family.members:
                                            if getattr(m, "task", "") in ("IDLE", "LEISURE", "FETCHING_POSSESSION"):
                                                assigned_worker = m
                                                break
                                        if not assigned_worker and owner_family.members:
                                            assigned_worker = owner_family.members[0]

                                    if assigned_worker:
                                        assigned_worker.task = "FETCHING_POSSESSION"
                                        assigned_worker.target_loose_stack = clicked_stack
                                        assigned_worker.say(f"I am on my way to retrieve our {clicked_stack.resource_type}!", duration=2.5)
                                else:
                                    # Barang milik Landlord: minta royal servant untuk haul
                                    if servant_manager:
                                        free_servant = next((s for s in servant_manager.servants if s.state == "IDLE"), None)
                                        if free_servant:
                                            free_servant.state = "HAULING_LOOSE_FETCH"
                                            free_servant.target_loose_stack = clicked_stack
                                            free_servant.say(f"Hauling {clicked_stack.resource_type} to storage, Sire!", duration=2.5)
                                continue

                            # 0D. Cek apakah pemain mengklik mine hasil generate (natural resources)
                            from game.world.natural_resources import get_natural_resources
                            clicked_mine = get_natural_resources().get_mine_at(m_gx, m_gy)
                            if clicked_mine is not None:
                                selected_furniture = None
                                selected_entity = None
                                workplace_popup = None
                                mine_popup = {"mine": clicked_mine, "pos": event.pos}
                                continue

                            # 1. Cek apakah pemain mengklik bangunan fisik di peta
                            clicked_b = building_manager.get_building_at(m_gx, m_gy)
                            if clicked_b:
                                selected_furniture = None
                                selected_entity = None
                                b_cfg = getattr(clicked_b, "type_cfg", None) or {}
                                if b_cfg.get("public_structure"):
                                    # Public structures (well, market, toilet, tax house)
                                    # get the same context-menu treatment: List /
                                    # Destroy plus their special action buttons.
                                    workplace_popup = None
                                    selected_structure = clicked_b
                                elif workplace_bases_for("building", clicked_b):
                                    workplace_popup = {"kind": "building", "obj": clicked_b, "pos": event.pos}
                                    selected_structure = None
                                else:
                                    workplace_popup = None
                                    selected_structure = None
                                    raport_ui.open_building_directly(clicked_b)
                                continue

                            # 1B. Cek apakah mengklik construction site atau demolition site
                            clicked_site = building_manager.get_site_at(m_gx, m_gy)
                            if clicked_site:
                                selected_furniture = None
                                selected_entity = None
                                raport_ui.open_building_directly(clicked_site)
                                continue

                            clicked_demo = building_manager.get_demolition_at(m_gx, m_gy)
                            if clicked_demo:
                                selected_furniture = None
                                selected_entity = None
                                raport_ui.open_building_directly(getattr(clicked_demo, "building", clicked_demo))
                                continue

                            # 2. Cek apakah pemain mengklik surat tanah / permit di peta (empty atau occupied)
                            clicked_p = permit_manager.get_permit_at(m_gx, m_gy)
                            if clicked_p:
                                selected_furniture = None
                                selected_entity = None
                                if workplace_bases_for("permit", clicked_p):
                                    workplace_popup = {"kind": "permit", "obj": clicked_p, "pos": event.pos}
                                else:
                                    workplace_popup = None
                                    raport_ui.open_permit_directly(clicked_p.id, permit_manager)
                                continue

        # Update Game Logic
        if current_state == STATE_MENU:
            menu.draw(screen)
            settings_modal.draw(screen, day_cycle, is_ingame=False)
            save_modal.draw(screen)
        elif current_state == STATE_PLAYING:
            days_passed = day_cycle.update(game_dt)
            for market_building in building_manager.buildings:
                if getattr(market_building, "building_type", "") == "market":
                    market_building.current_day_number = day_cycle.day_number
            if days_passed > 0:
                for p in permit_manager.permits:
                    p.reset_daily_watering()
                villager_manager.daily_midnight_update(day_cycle.day_number)
                furniture_manager.daily_wear_update(days_passed)
                building_manager.daily_public_maintenance_update(days_passed)
            furniture_manager.check_breaks_by_time(day_cycle.day_number, day_cycle.current_hour)
            day_dt = game_dt / max(1.0, day_cycle.day_length_seconds)
            cur_day_time = day_cycle.day_number + (day_cycle.current_hour / 24.0)
            wealth_context_timer -= real_dt
            # Periodic autosave: one file per in-game day (autosave-dayNN).
            from game.data.config import AUTOSAVE_INTERVAL_SECONDS
            from game.save_system import autosave_slot_name
            autosave_elapsed += real_dt
            if autosave_elapsed >= AUTOSAVE_INTERVAL_SECONDS:
                autosave_elapsed = 0.0
                try:
                    save_to_slot(
                        autosave_slot_name(day_cycle.day_number),
                        day_cycle, resources, player, permit_manager, building_manager,
                        stockpile_manager, furniture_manager, villager_manager,
                        servant_manager, schedule_manager,
                    )
                except Exception as e:
                    print(f"[Autosave] failed: {e}")
            if wealth_context_timer <= 0.0:
                wealth_data = VillageWealthSystem.calculate_village_wealth(
                    resources=resources,
                    villager_manager=villager_manager,
                    furniture_manager=furniture_manager,
                    building_manager=building_manager,
                    stockpile_manager=stockpile_manager,
                )
                living_population = sum(
                    1 for villager in villager_manager.get_all_villagers()
                    if getattr(villager, "is_alive", True)
                )
                wealth_factor = MarketPricingSystem.get_village_wealth_factor(
                    wealth_data["total_wealth_copper"], living_population
                )
                for market in MarketService.get_all_markets(building_manager):
                    market.village_wealth_factor = wealth_factor
                wealth_context_timer = MARKET_WEALTH_CONTEXT_REFRESH_SECONDS
            for p in permit_manager.permits:
                p.update_growth(day_dt, current_day=cur_day_time)

            # Substep physics/entities so high speed multiplier (Fast 2x, Very Fast 4x) never tunnels through walls
            MAX_PHYSICS_SUB_DT = 0.02  # Maximum 20ms per physics integration step
            sub_time = game_dt
            is_modal_open = raport_ui.is_open or settings_modal.is_open or save_modal.is_open or market_modal.is_open or add_item_modal.is_open or cheat_modal.is_open or pending_starter_id is not None
            raport_ui.cheats_active = cheats_active
            keys = pygame.key.get_pressed() if not is_modal_open else None

            profile_simulation_start = perf_counter() if profile_enabled else 0.0
            run_ai_scheduler = True
            while sub_time > 0.0:
                step_dt = min(sub_time, MAX_PHYSICS_SUB_DT)
                if not is_modal_open:
                    player.handle_input(keys, step_dt, building_manager, TILE_SIZE)
                building_manager.update(step_dt)
                servant_manager.update(
                    step_dt, building_manager, permit_manager, stockpile_manager,
                    resources, player, furniture_manager=furniture_manager,
                    villager_manager=villager_manager,
                    run_ai_scheduler=run_ai_scheduler, ai_dt=game_dt,
                    day_cycle=day_cycle,
                )
                villager_manager.update(
                    step_dt, permit_manager, building_manager, servant_manager.servants,
                    player, stockpile_manager=stockpile_manager,
                    furniture_manager=furniture_manager, day_cycle=day_cycle,
                    schedule_manager=schedule_manager, production_system=production_system,
                    run_ai_scheduler=run_ai_scheduler, ai_dt=game_dt,
                )
                run_ai_scheduler = False
                sub_time -= step_dt
            if profile_enabled:
                profile_simulation_ms += (perf_counter() - profile_simulation_start) * 1000.0

            # Dead/reassigned artisans: dissolve their commission queues and
            # spawn refund errands for PAID orders.
            if furniture_manager is not None and villager_manager is not None:
                from game.systems.work.builder_system import BuilderSystem
                BuilderSystem.sweep_dead_commission_orders(
                    building_manager, furniture_manager, villager_manager,
                    servant_manager=servant_manager, stockpile_manager=stockpile_manager,
                    day_cycle=day_cycle)

            # Immigration: pending households travel/wait/leave at the Notice Board.
            if furniture_manager is not None and villager_manager is not None:
                from game.systems.village_life.immigration_system import get_immigration_system
                _imm_ents = villager_manager.get_all_villagers() + servant_manager.servants
                get_immigration_system().update(
                    game_dt, day_cycle, furniture_manager, villager_manager,
                    servant_manager=servant_manager, building_manager=building_manager,
                    player=player, all_entities=_imm_ents)

            if pending_starter_id is not None:
                # Starter placement: free-fly camera (nobody spawned yet)
                fly_keys = pygame.key.get_pressed()
                pan = STARTER_PLACEMENT_PAN_SPEED * real_dt
                if fly_keys[pygame.K_w] or fly_keys[pygame.K_UP]:
                    camera.y -= pan
                if fly_keys[pygame.K_s] or fly_keys[pygame.K_DOWN]:
                    camera.y += pan
                if fly_keys[pygame.K_a] or fly_keys[pygame.K_LEFT]:
                    camera.x -= pan
                if fly_keys[pygame.K_d] or fly_keys[pygame.K_RIGHT]:
                    camera.x += pan
            else:
                camera.follow(player)

            # 1. World & Ground
            world.draw(screen, camera)
            from game.world.natural_resources import get_natural_resources
            get_natural_resources().draw(screen, camera, TILE_SIZE)
            from game.world.roads import get_roads
            get_roads().draw(screen, camera, TILE_SIZE)

            # 2. Area Permits (Fixed, Permanent Boundaries)
            permit_manager.draw(screen, camera, TILE_SIZE, building_manager)

            # 3. Buildings & Construction Sites
            building_manager.draw(screen, camera, TILE_SIZE)

            # 4. Household Furniture (Chests & Storages)
            furniture_manager.draw(screen, camera, TILE_SIZE)

            # 4.5. Ground items render above home floors and furniture.
            stockpile_manager.draw(screen, camera, TILE_SIZE, permit_manager)

            # 5. Characters (Villagers, Servants & Player) — none exist yet
            # while the player is still picking the starter village location.
            if pending_starter_id is None:
                villager_manager.draw(screen, camera)
                servant_manager.draw(screen, camera)
                from game.systems.village_life.immigration_system import get_immigration_system
                get_immigration_system().draw(screen, camera, TILE_SIZE)
                player.draw(screen, camera)

            # 6. Ambient Day & Night Lighting Overlay
            ambient_surf = day_cycle.get_ambient_overlay(screen.get_width(), screen.get_height())
            if ambient_surf:
                screen.blit(ambient_surf, (0, 0))

            route_actors = villager_manager.get_all_villagers() + servant_manager.servants
            path_debug_overlay.draw_routes(screen, camera, route_actors)

            # -------------------------------------------------------------
            # 6. OVERLAYS: PERMIT PLANNING MODE
            # -------------------------------------------------------------
            if planning_mode == "PERMIT":
                type_cfg = PERMIT_TYPES.get(planning_permit_type, PERMIT_TYPES["housing"])
                scaled_t = int(TILE_SIZE * camera.zoom)

                # A. Render All Already Placed Tiles
                for (gx, gy) in planning_permit_tiles:
                    sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                    t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                    t_surf.fill((56, 189, 248, 110))
                    screen.blit(t_surf, (sx, sy))
                    pygame.draw.rect(screen, (56, 189, 248), (sx, sy, scaled_t, scaled_t), width=1)

                # B. Render Active Drag Box Preview
                if permit_drag_start:
                    cur_box = get_rect_tiles(permit_drag_start, (m_gx, m_gy))
                    for (gx, gy) in cur_box:
                        sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                        t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                        t_surf.fill((34, 197, 94, 100))
                        screen.blit(t_surf, (sx, sy))
                        pygame.draw.rect(screen, (34, 197, 94), (sx, sy, scaled_t, scaled_t), width=1)

                # C. Render Active Erase Box Preview
                if permit_erase_start:
                    cur_box = get_rect_tiles(permit_erase_start, (m_gx, m_gy))
                    for (gx, gy) in cur_box:
                        sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                        t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                        t_surf.fill((239, 68, 68, 120))
                        screen.blit(t_surf, (sx, sy))
                        pygame.draw.rect(screen, (239, 68, 68), (sx, sy, scaled_t, scaled_t), width=1)

                # D. Floating Bottom Control Bar
                can_place, status_msg = permit_manager.can_place_permit_tiles(planning_permit_tiles)
                bar_w = 620
                bar_h = 86
                bar_x = (screen.get_width() - bar_w) // 2
                bar_y = screen.get_height() - bar_h - 14

                bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
                pygame.draw.rect(bar_surf, (15, 23, 42, 245), (0, 0, bar_w, bar_h), border_radius=10)
                pygame.draw.rect(bar_surf, (71, 85, 105), (0, 0, bar_w, bar_h), width=2, border_radius=10)
                screen.blit(bar_surf, (bar_x, bar_y))

                # Header & Info
                p_title = planning_permit_type.replace('_', ' ').title()
                info_txt = f"Issue {p_title} Deed | Planned: {len(planning_permit_tiles)} Tiles"
                screen.blit(font_card.render(info_txt, True, (56, 189, 248)), (bar_x + 16, bar_y + 10))

                stat_col = (34, 197, 94) if can_place and len(planning_permit_tiles) > 0 else (239, 68, 68)
                stat_txt = f"Status: {status_msg} (Drag to add, Right-Click to erase)"
                screen.blit(font_hud.render(stat_txt, True, stat_col), (bar_x + 16, bar_y + 30))

                # Buttons
                btn_y = bar_y + 46
                btn_confirm_rect.x = bar_x + 16
                btn_confirm_rect.y = btn_y
                btn_clear_rect.x = bar_x + 180
                btn_clear_rect.y = btn_y
                btn_cancel_rect.x = bar_x + 280
                btn_cancel_rect.y = btn_y

                # Confirm Button
                c_col = (16, 185, 129) if can_place and len(planning_permit_tiles) > 0 else (71, 85, 105)
                pygame.draw.rect(screen, c_col, btn_confirm_rect, border_radius=6)
                screen.blit(font_btn.render("ISSUE PERMIT", True, (255, 255, 255)), (btn_confirm_rect.x + 22, btn_confirm_rect.y + 8))

                # Clear Button
                pygame.draw.rect(screen, (71, 85, 105), btn_clear_rect, border_radius=6)
                screen.blit(font_btn.render("CLEAR", True, (255, 255, 255)), (btn_clear_rect.x + 22, btn_clear_rect.y + 8))

                # Cancel Button
                pygame.draw.rect(screen, (220, 38, 38), btn_cancel_rect, border_radius=6)
                screen.blit(font_btn.render("CANCEL", True, (255, 255, 255)), (btn_cancel_rect.x + 24, btn_cancel_rect.y + 8))

            # -------------------------------------------------------------
            # 6B. OVERLAYS: EDIT PERMIT PLANNING MODE
            # -------------------------------------------------------------
            elif planning_mode == "EDIT_PERMIT":
                target_p = next((p for p in permit_manager.permits if p.id == editing_permit_id), None)
                if target_p:
                    scaled_t = int(TILE_SIZE * camera.zoom)

                    # A. Render All Current Tiles
                    for (gx, gy) in planning_permit_tiles:
                        sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                        t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                        is_new = (gx, gy) not in original_permit_tiles
                        t_surf.fill((34, 197, 94, 110) if is_new else (56, 189, 248, 110))
                        screen.blit(t_surf, (sx, sy))
                        pygame.draw.rect(screen, (34, 197, 94) if is_new else (56, 189, 248), (sx, sy, scaled_t, scaled_t), width=1)

                    # B. Active Drag Add Box
                    if permit_drag_start:
                        cur_box = get_rect_tiles(permit_drag_start, (m_gx, m_gy))
                        for (gx, gy) in cur_box:
                            sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                            t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                            t_surf.fill((34, 197, 94, 120))
                            screen.blit(t_surf, (sx, sy))
                            pygame.draw.rect(screen, (34, 197, 94), (sx, sy, scaled_t, scaled_t), width=1)

                    # C. Active Drag Erase Box
                    if permit_erase_start:
                        cur_box = get_rect_tiles(permit_erase_start, (m_gx, m_gy))
                        for (gx, gy) in cur_box:
                            sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                            t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                            t_surf.fill((239, 68, 68, 130))
                            screen.blit(t_surf, (sx, sy))
                            pygame.draw.rect(screen, (239, 68, 68), (sx, sy, scaled_t, scaled_t), width=1)

                    # D. Floating Bottom Control Bar
                    can_resize, status_msg = target_p.can_resize(
                        planning_permit_tiles,
                        other_permits=permit_manager.permits,
                        building_manager=building_manager,
                        furniture_manager=furniture_manager
                    )
                    bar_w = 660
                    bar_h = 86
                    bar_x = (screen.get_width() - bar_w) // 2
                    bar_y = screen.get_height() - bar_h - 14

                    bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
                    pygame.draw.rect(bar_surf, (15, 23, 42, 245), (0, 0, bar_w, bar_h), border_radius=10)
                    pygame.draw.rect(bar_surf, (245, 158, 11), (0, 0, bar_w, bar_h), width=2, border_radius=10)
                    screen.blit(bar_surf, (bar_x, bar_y))

                    diff = len(planning_permit_tiles) - len(original_permit_tiles)
                    diff_str = f"({diff:+d} tiles)" if diff != 0 else "(no change)"
                    info_txt = f"Edit Lot: {target_p.name} | Size: {len(original_permit_tiles)} -> {len(planning_permit_tiles)} Tiles {diff_str}"
                    screen.blit(font_card.render(info_txt, True, (250, 204, 21)), (bar_x + 16, bar_y + 10))

                    stat_col = (34, 197, 94) if can_resize and len(planning_permit_tiles) > 0 else (239, 68, 68)
                    stat_txt = f"Status: {status_msg} (Drag L-Click to add, R-Click to erase)"
                    screen.blit(font_hud.render(stat_txt, True, stat_col), (bar_x + 16, bar_y + 30))

                    # Buttons
                    btn_y = bar_y + 46
                    btn_confirm_rect.x = bar_x + 16
                    btn_confirm_rect.y = btn_y
                    btn_clear_rect.x = bar_x + 190
                    btn_clear_rect.y = btn_y
                    btn_cancel_rect.x = bar_x + 290
                    btn_cancel_rect.y = btn_y

                    c_col = (16, 185, 129) if can_resize and len(planning_permit_tiles) > 0 else (71, 85, 105)
                    pygame.draw.rect(screen, c_col, btn_confirm_rect, border_radius=6)
                    screen.blit(font_btn.render("APPLY RESIZE", True, (255, 255, 255)), (btn_confirm_rect.x + 20, btn_confirm_rect.y + 8))

                    pygame.draw.rect(screen, (71, 85, 105), btn_clear_rect, border_radius=6)
                    screen.blit(font_btn.render("RESET", True, (255, 255, 255)), (btn_clear_rect.x + 20, btn_clear_rect.y + 8))

                    pygame.draw.rect(screen, (220, 38, 38), btn_cancel_rect, border_radius=6)
                    screen.blit(font_btn.render("CANCEL", True, (255, 255, 255)), (btn_cancel_rect.x + 24, btn_cancel_rect.y + 8))

            # -------------------------------------------------------------
            # 7. OVERLAYS: BUILDING PLANNING MODE
            # -------------------------------------------------------------
            elif planning_mode == "BUILDING":
                b_cfg = BUILDING_TYPES[planning_building_type]
                scaled_t = int(TILE_SIZE * camera.zoom)

                # A. Render All Planned Tiles
                for (gx, gy) in planning_building_tiles:
                    sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                    t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                    t_surf.fill((30, 58, 138, 110))
                    screen.blit(t_surf, (sx, sy))
                    pygame.draw.rect(screen, (59, 130, 246), (sx, sy, scaled_t, scaled_t), width=1)

                    # Exterior perimeter lines
                    if (gx, gy - 1) not in planning_building_tiles:
                        pygame.draw.line(screen, (96, 165, 250), (sx, sy), (sx + scaled_t, sy), 2)
                    if (gx, gy + 1) not in planning_building_tiles:
                        pygame.draw.line(screen, (96, 165, 250), (sx, sy + scaled_t), (sx + scaled_t, sy + scaled_t), 2)
                    if (gx - 1, gy) not in planning_building_tiles:
                        pygame.draw.line(screen, (96, 165, 250), (sx, sy), (sx, sy + scaled_t), 2)
                    if (gx + 1, gy) not in planning_building_tiles:
                        pygame.draw.line(screen, (96, 165, 250), (sx + scaled_t, sy), (sx + scaled_t, sy + scaled_t), 2)

                if (planning_building_type == "tax_house"
                        and len(planning_building_tiles) == int(b_cfg.get("fixed_tiles_count", 0))):
                    building_manager.draw_public_structure_preview(
                        screen, camera, TILE_SIZE, planning_building_type,
                        planning_building_tiles, planning_building_rotation,
                    )

                # B. Render Door Marker
                if planned_door_tile and planned_door_tile in planning_building_tiles:
                    dsx, dsy = camera.world_to_screen(planned_door_tile[0] * TILE_SIZE, planned_door_tile[1] * TILE_SIZE)
                    door_box = pygame.Rect(dsx + 4, dsy + 4, scaled_t - 8, scaled_t - 8)
                    pygame.draw.rect(screen, (234, 179, 8, 200), door_box, border_radius=4)
                    d_lbl = font_badge.render(f"DOOR ({planned_door_side.upper()})", True, (0, 0, 0))
                    screen.blit(d_lbl, (door_box.centerx - d_lbl.get_width() // 2, door_box.centery - d_lbl.get_height() // 2))

                # C. Configured fixed-footprint structure hover preview.
                if (b_cfg.get("fixed_tiles_count") and b_cfg.get("width_tiles")
                        and b_cfg.get("height_tiles") and not planning_building_tiles and not building_drag_start):
                    w_w = int(b_cfg["width_tiles"])
                    w_h = int(b_cfg["height_tiles"])
                    if planning_building_rotation % 180:
                        w_w, w_h = w_h, w_w
                    preview_box = {(m_gx + c, m_gy + r) for c in range(w_w) for r in range(w_h)}
                    can_fit, _ = permit_manager.find_matching_permit_for_tiles(planning_building_type, preview_box, building_manager, furniture_manager=furniture_manager)
                    fit_tint = (34, 197, 94, 100) if can_fit else (239, 68, 68, 100)
                    for (gx, gy) in preview_box:
                        sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                        t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                        t_surf.fill(fit_tint)
                        screen.blit(t_surf, (sx, sy))
                        pygame.draw.rect(screen, (34, 197, 94) if can_fit else (239, 68, 68), (sx, sy, scaled_t, scaled_t), width=1)
                    if planning_building_type == "tax_house":
                        building_manager.draw_public_structure_preview(
                            screen, camera, TILE_SIZE, planning_building_type,
                            preview_box, planning_building_rotation,
                        )
                    if w_w == 1 and w_h == 1 and b_cfg.get("rotatable", True):
                        draw_placement_orientation(
                            screen, pygame.Rect(sx, sy, scaled_t, scaled_t),
                            planning_building_rotation,
                        )

                # D. Render Active Drag Box Preview
                if building_drag_start:
                    cur_box = get_rect_tiles(building_drag_start, (m_gx, m_gy))
                    for (gx, gy) in cur_box:
                        sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                        t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                        t_surf.fill((34, 197, 94, 90))
                        screen.blit(t_surf, (sx, sy))
                        pygame.draw.rect(screen, (34, 197, 94), (sx, sy, scaled_t, scaled_t), width=1)

                # E. Render Active Erase Box Preview
                if building_erase_start:
                    cur_box = get_rect_tiles(building_erase_start, (m_gx, m_gy))
                    for (gx, gy) in cur_box:
                        sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                        t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                        t_surf.fill((239, 68, 68, 120))
                        screen.blit(t_surf, (sx, sy))
                        pygame.draw.rect(screen, (239, 68, 68), (sx, sy, scaled_t, scaled_t), width=1)

                # F. Floating Bottom Control Bar
                matching_permit, status_msg = permit_manager.find_matching_permit_for_tiles(
                    planning_building_type, planning_building_tiles, building_manager, furniture_manager=furniture_manager
                )
                if b_cfg.get("fixed_cost", False):
                    cost_w = b_cfg.get("cost_wood", 5)
                    cost_s = b_cfg.get("cost_stone", 20)
                else:
                    cost_w = len(planning_building_tiles) * b_cfg.get("cost_wood", COST_PER_BLOCK_WOOD)
                    cost_s = len(planning_building_tiles) * b_cfg.get("cost_stone", COST_PER_BLOCK_STONE)

                can_afford = building_manager.can_afford(planning_building_type, resources, len(planning_building_tiles))
                is_valid_tile_count = (len(planning_building_tiles) == b_cfg["fixed_tiles_count"]) if b_cfg.get("fixed_tiles_count") else (len(planning_building_tiles) > 0)
                dim_w, dim_h = b_cfg.get("width_tiles", 2), b_cfg.get("height_tiles", 2)
                if planning_building_rotation % 180:
                    dim_w, dim_h = dim_h, dim_w
                dim_str = f"({dim_w}x{dim_h})" if b_cfg.get("fixed_tiles_count") else ""
                if b_cfg.get("fixed_tiles_count") and len(planning_building_tiles) > 0 and len(planning_building_tiles) != b_cfg["fixed_tiles_count"]:
                    status_msg = f"Must be exactly {b_cfg['fixed_tiles_count']} tiles {dim_str}"
                is_valid = (matching_permit is not None) and can_afford and is_valid_tile_count

                bar_w = 700
                bar_h = 92
                bar_x = (screen.get_width() - bar_w) // 2
                bar_y = screen.get_height() - bar_h - 14

                bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
                pygame.draw.rect(bar_surf, (15, 23, 42, 245), (0, 0, bar_w, bar_h), border_radius=10)
                pygame.draw.rect(bar_surf, (71, 85, 105), (0, 0, bar_w, bar_h), width=2, border_radius=10)
                screen.blit(bar_surf, (bar_x, bar_y))

                # Header & Cost
                tiles_label = f"Fixed: {b_cfg['fixed_tiles_count']} Tiles {dim_str}" if b_cfg.get("fixed_tiles_count") else f"Tiles: {len(planning_building_tiles)}"
                if b_cfg.get("builder_commissionable"):
                    info_txt = f"Design {b_cfg['name']} | {tiles_label} | Lord pays Builder commission"
                else:
                    info_txt = f"Design {b_cfg['name']} | {tiles_label} | Cost: {cost_w} Wood, {cost_s} Stone"
                screen.blit(font_card.render(info_txt, True, (56, 189, 248)), (bar_x + 16, bar_y + 10))

                # Status & Door info
                if not b_cfg.get("has_door", True):
                    door_str = "Solid Structure (Impenetrable)" if b_cfg.get("is_solid", False) else "Open-air Market Stall"
                    help_str = f"(R: Rotate | Click to place {dim_str} {b_cfg['name']})" if b_cfg.get("fixed_tiles_count") else "(R: Rotate | Drag to place)"
                else:
                    door_str = f"Door: {planned_door_tile} [{planned_door_side}]" if planned_door_tile else "Click any exterior wall tile to place Door"
                    help_str = "(R: Rotate | Drag to expand, Right-Click to erase)"
                stat_col = (34, 197, 94) if is_valid else (239, 68, 68)
                stat_txt = f"Status: {status_msg} | {door_str} | {help_str}"
                screen.blit(font_hud.render(stat_txt, True, stat_col), (bar_x + 16, bar_y + 32))

                # Buttons
                btn_y = bar_y + 52
                btn_confirm_rect.x = bar_x + 16
                btn_confirm_rect.y = btn_y
                btn_clear_rect.x = bar_x + 180
                btn_clear_rect.y = btn_y
                btn_cancel_rect.x = bar_x + 280
                btn_cancel_rect.y = btn_y

                # Confirm Build Button
                c_col = (16, 185, 129) if is_valid else (71, 85, 105)
                pygame.draw.rect(screen, c_col, btn_confirm_rect, border_radius=6)
                screen.blit(font_btn.render("ORDER", True, (255, 255, 255)), (btn_confirm_rect.x + 46, btn_confirm_rect.y + 8))

                # Clear Button
                pygame.draw.rect(screen, (71, 85, 105), btn_clear_rect, border_radius=6)
                screen.blit(font_btn.render("CLEAR", True, (255, 255, 255)), (btn_clear_rect.x + 22, btn_clear_rect.y + 8))

                # Cancel Button
                pygame.draw.rect(screen, (220, 38, 38), btn_cancel_rect, border_radius=6)
                screen.blit(font_btn.render("CANCEL", True, (255, 255, 255)), (btn_cancel_rect.x + 24, btn_cancel_rect.y + 8))

            # -------------------------------------------------------------
            # 7.5. OVERLAYS: FURNITURE PLANNING MODE
            # -------------------------------------------------------------
            elif planning_mode == "FURNITURE":
                f_cfg = FURNITURE_TYPES.get(planning_furniture_type, FURNITURE_TYPES["household_storage"])
                scaled_t = int(TILE_SIZE * camera.zoom)
                fw, fh = max(1, int(f_cfg.get("width_tiles", 1))), max(1, int(f_cfg.get("height_tiles", 1)))
                if planning_furniture_rotation % 180:
                    fw, fh = fh, fw
                planned_coords = set()
                for pf in session_planned_furniture:
                    p_cfg = FURNITURE_TYPES.get(pf.get("type", planning_furniture_type), f_cfg)
                    p_w, p_h = max(1, int(p_cfg.get("width_tiles", 1))), max(1, int(p_cfg.get("height_tiles", 1)))
                    if int(pf.get("rotation", 0)) % 180:
                        p_w, p_h = p_h, p_w
                    planned_coords.update((pf["gx"] + dx, pf["gy"] + dy) for dx in range(p_w) for dy in range(p_h))

                # 1. Render all planned unbuilt furniture objects in the current session
                for pf in session_planned_furniture:
                    psx, psy = camera.world_to_screen(pf["gx"] * TILE_SIZE, pf["gy"] * TILE_SIZE)
                    if -scaled_t <= psx <= screen.get_width() and -scaled_t <= psy <= screen.get_height():
                        p_cfg = FURNITURE_TYPES.get(pf.get("type", planning_furniture_type), f_cfg)
                        p_fw, p_fh = max(1, int(p_cfg.get("width_tiles", 1))), max(1, int(p_cfg.get("height_tiles", 1)))
                        if int(pf.get("rotation", 0)) % 180:
                            p_fw, p_fh = p_fh, p_fw
                        p_w, p_h = scaled_t * p_fw, scaled_t * p_fh
                        p_surf = pygame.Surface((p_w, p_h), pygame.SRCALPHA)
                        is_sel = (selected_planned_furniture == (pf["gx"], pf["gy"]))
                        p_tint = (250, 204, 21, 140) if is_sel else (34, 197, 94, 120)
                        p_surf.fill(p_tint)
                        screen.blit(p_surf, (psx, psy))
                        p_border_c = (250, 204, 21) if is_sel else (34, 197, 94)
                        pygame.draw.rect(screen, p_border_c, (psx, psy, p_w, p_h), width=3 if is_sel else 2, border_radius=4)

                        if p_fw == 1 and p_fh == 1 and p_cfg.get("rotatable", True):
                            draw_placement_orientation(
                                screen, pygame.Rect(psx, psy, p_w, p_h), pf.get("rotation", 0),
                            )

                        lbl = font_badge.render("PLAN", True, (255, 255, 255))
                        screen.blit(lbl, (psx + 4, psy + 4))

                # 2. Ghost Preview at Mouse Tile (if not already planned)
                fsx, fsy = camera.world_to_screen(m_gx * TILE_SIZE, m_gy * TILE_SIZE)
                footprint = {(m_gx + dx, m_gy + dy) for dx in range(fw) for dy in range(fh)}
                target_permit = permit_manager.get_permit_at(m_gx, m_gy)
                valid_cells = []
                for tx, ty in footprint:
                    target_permit = permit_manager.get_permit_at(tx, ty)
                    b_at = building_manager.get_building_at(tx, ty)
                    inside = b_at is not None and not getattr(b_at, "is_solid", False) and getattr(b_at, "building_type", "") != "well" and (tx, ty) != getattr(b_at, "door_pos", None)
                    is_door_tile = b_at is not None and getattr(b_at, "door_pos", None) == (tx, ty)
                    allowed = f_cfg.get("allowed_permits")
                    permit_allowed = f_cfg.get("placement_anywhere") or not allowed or (target_permit is not None and target_permit.permit_type in allowed)
                    valid_cells.append(((f_cfg.get("placement_anywhere") or target_permit is not None or inside) and permit_allowed and not is_door_tile,
                                        furniture_manager.get_furniture_at(tx, ty) is not None))
                is_occupied_planned = bool(footprint & planned_coords)
                is_occupied_existing = any(occupied for _, occupied in valid_cells)
                is_valid_location = all(valid for valid, _ in valid_cells)
                is_valid_place = all(valid and not occupied for valid, occupied in valid_cells) and not is_occupied_planned
                mine_match = None
                if planning_furniture_type == "miner_workstation" and is_valid_place:
                    from game.world.natural_resources import get_natural_resources
                    mine_match = get_natural_resources().mine_for_footprint(footprint)
                    is_valid_place = mine_match is not None
                    is_valid_location = is_valid_location and mine_match is not None

                if not is_occupied_planned:
                    f_surf = pygame.Surface((scaled_t * fw, scaled_t * fh), pygame.SRCALPHA)
                    tile_tint = (34, 197, 94, 100) if is_valid_place else (239, 68, 68, 100)
                    f_surf.fill(tile_tint)
                    screen.blit(f_surf, (fsx, fsy))
                    pygame.draw.rect(screen, (34, 197, 94) if is_valid_place else (239, 68, 68), (fsx, fsy, scaled_t * fw, scaled_t * fh), width=2)
                    if fw == 1 and fh == 1 and f_cfg.get("rotatable", True):
                        draw_placement_orientation(
                            screen, pygame.Rect(fsx, fsy, scaled_t * fw, scaled_t * fh),
                            planning_furniture_rotation,
                        )
                else:
                    # Hovering an already planned tile: show distinct highlight
                    pygame.draw.rect(screen, (239, 68, 68), (fsx, fsy, scaled_t, scaled_t), width=2)

                # 3. Floating Bottom Bar
                bar_w = 640
                bar_h = 96
                bar_x = (screen.get_width() - bar_w) // 2
                bar_y = screen.get_height() - bar_h - 14

                bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
                pygame.draw.rect(bar_surf, (15, 23, 42, 245), (0, 0, bar_w, bar_h), border_radius=10)
                pygame.draw.rect(bar_surf, (71, 85, 105), (0, 0, bar_w, bar_h), width=2, border_radius=10)
                screen.blit(bar_surf, (bar_x, bar_y))

                planned_count = len(session_planned_furniture)
                is_valid_build = planned_count > 0

                if f_cfg.get("instant_place"):
                    info_txt = f"Place {f_cfg['name']} | Planned: {planned_count} | Free and ready immediately"
                else:
                    info_txt = f"Order {f_cfg['name']} | Planned: {planned_count} | Household pays commission; Builder supplies materials"
                screen.blit(font_card.render(info_txt, True, (250, 204, 21)), (bar_x + 16, bar_y + 10))

                if is_occupied_planned:
                    stat_msg = "Planned furniture selected! (Right-Click or Del to remove from session)"
                    stat_col = (250, 204, 21)
                elif planning_furniture_type == "miner_workstation" and mine_match is None:
                    stat_msg = "Cannot place: Miner workstation must be placed exactly on a generated mine (5x5)!"
                    stat_col = (239, 68, 68)
                elif not is_valid_location:
                    stat_msg = "Cannot place: Must be placed inside an issued Permit lot or tenant house!"
                    stat_col = (239, 68, 68)
                elif is_occupied_existing:
                    stat_msg = "Cannot place: Tile already has built furniture!"
                    stat_col = (239, 68, 68)
                else:
                    owner_family = None
                    if target_permit:
                        owner_family = next((fam for fam in villager_manager.families if fam.assigned_permit_id == target_permit.id), None)
                    fam_str = f"The {owner_family.surname} Family" if owner_family else "Tenant house / lot"
                    stat_msg = f"Ready to order! (R: rotate | Left-Click to place, Right-Click to erase. {fam_str})"
                    stat_col = (34, 197, 94)

                screen.blit(font_hud.render(stat_msg, True, stat_col), (bar_x + 16, bar_y + 32))

                # Buttons
                btn_y = bar_y + 52
                btn_confirm_rect.x = bar_x + 16
                btn_confirm_rect.y = btn_y
                btn_clear_rect.x = bar_x + 180
                btn_clear_rect.y = btn_y
                btn_cancel_rect.x = bar_x + 280
                btn_cancel_rect.y = btn_y

                # Confirm Build Button
                c_col = (16, 185, 129) if is_valid_build else (71, 85, 105)
                pygame.draw.rect(screen, c_col, btn_confirm_rect, border_radius=6)
                screen.blit(font_btn.render("BUILD", True, (255, 255, 255)), (btn_confirm_rect.x + 46, btn_confirm_rect.y + 8))

                # Clear Button
                pygame.draw.rect(screen, (71, 85, 105), btn_clear_rect, border_radius=6)
                screen.blit(font_btn.render("CLEAR", True, (255, 255, 255)), (btn_clear_rect.x + 22, btn_clear_rect.y + 8))

                # Cancel Button
                pygame.draw.rect(screen, (220, 38, 38), btn_cancel_rect, border_radius=6)
                screen.blit(font_btn.render("CANCEL", True, (255, 255, 255)), (btn_cancel_rect.x + 24, btn_cancel_rect.y + 8))

            # -------------------------------------------------------------
            # 7.6. OVERLAYS: MOVE FURNITURE PLANNING MODE
            # -------------------------------------------------------------
            elif planning_mode == "MOVE_FURNITURE" and moving_furniture:
                scaled_t = int(TILE_SIZE * camera.zoom)
                fsx, fsy = camera.world_to_screen(m_gx * TILE_SIZE, m_gy * TILE_SIZE)

                target_permit = permit_manager.get_permit_at(m_gx, m_gy)
                b_at = building_manager.get_building_at(m_gx, m_gy)
                other_f = furniture_manager.get_furniture_at(m_gx, m_gy)
                is_occupied = (other_f is not None and other_f.id != moving_furniture.id and not other_f.is_dropped)

                is_blocked = False
                blocked_reason = ""
                if b_at is not None:
                    if getattr(b_at, "is_solid", False) or getattr(b_at, "building_type", "") == "well" or not getattr(b_at, "door_pos", None):
                        is_blocked = True
                        blocked_reason = "Cannot move here: Tile blocked by solid structure (Well)!"
                    elif (m_gx, m_gy) == getattr(b_at, "door_pos", None):
                        is_blocked = True
                        blocked_reason = "Cannot move here: Tile blocked by doorway entrance!"

                is_valid_dest = not is_blocked and not is_occupied

                # Ghost Preview at Mouse Tile
                f_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                tile_tint = (34, 197, 94, 120) if is_valid_dest else (239, 68, 68, 120)
                f_surf.fill(tile_tint)
                screen.blit(f_surf, (fsx, fsy))
                pygame.draw.rect(screen, (34, 197, 94) if is_valid_dest else (239, 68, 68), (fsx, fsy, scaled_t, scaled_t), width=2)

                # Floating Bottom Bar
                bar_w = 640
                bar_h = 86
                bar_x = (screen.get_width() - bar_w) // 2
                bar_y = screen.get_height() - bar_h - 14

                bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
                pygame.draw.rect(bar_surf, (15, 23, 42, 245), (0, 0, bar_w, bar_h), border_radius=10)
                pygame.draw.rect(bar_surf, (56, 189, 248), (0, 0, bar_w, bar_h), width=2, border_radius=10)
                screen.blit(bar_surf, (bar_x, bar_y))

                info_txt = f"Move {moving_furniture.name} (Status: {moving_furniture.status}) -> Target: ({m_gx}, {m_gy})"
                screen.blit(font_card.render(info_txt, True, (56, 189, 248)), (bar_x + 16, bar_y + 10))

                if is_blocked:
                    stat_msg = blocked_reason
                elif is_occupied:
                    stat_msg = "Cannot move here: Tile already has furniture!"
                else:
                    owner_family = next((fam for fam in villager_manager.families if fam.id == moving_furniture.family_id), None)
                    fam_name = f"The {owner_family.surname} Family" if owner_family else "Royal Servants"
                    stat_msg = f"Valid destination! Left-Click to confirm task ({fam_name} will haul it)."

                stat_col = (34, 197, 94) if is_valid_dest else (239, 68, 68)
                screen.blit(font_hud.render(stat_msg, True, stat_col), (bar_x + 16, bar_y + 32))

                btn_cancel_rect.x = bar_x + bar_w - 126
                btn_cancel_rect.y = bar_y + 25
                pygame.draw.rect(screen, (220, 38, 38), btn_cancel_rect, border_radius=6)
                screen.blit(font_btn.render("CANCEL", True, (255, 255, 255)), (btn_cancel_rect.x + 28, btn_cancel_rect.y + 8))

            # -------------------------------------------------------------
            # 7.6b. OVERLAYS: ROAD PAINTING MODE
            # -------------------------------------------------------------
            elif planning_mode == "ROAD":
                from game.world.roads import get_roads
                from game.world.island import is_land_tile
                from game.world.natural_resources import get_natural_resources
                roads = get_roads()
                r_cfg = ROAD_TYPES.get(planning_road_type, ROAD_TYPES["dirt_road"])
                scaled_t = int(TILE_SIZE * camera.zoom)

                def road_tile_valid_draw(tx, ty):
                    if not is_land_tile(tx, ty):
                        return False
                    if (tx, ty) in planning_road_tiles or (tx, ty) in roads.tiles:
                        return False
                    if building_manager.get_building_at(tx, ty):
                        return False
                    if building_manager.get_site_at(tx, ty):
                        return False
                    if furniture_manager.get_furniture_at(tx, ty):
                        return False
                    if stockpile_manager.get_stack_at(tx, ty):
                        return False
                    if get_natural_resources().get_mine_at(tx, ty):
                        return False
                    return True

                # Painted tiles
                for (gx, ty) in planning_road_tiles:
                    sx, sy = camera.world_to_screen(gx * TILE_SIZE, ty * TILE_SIZE)
                    valid = road_tile_valid_draw(gx, ty)
                    t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                    t_surf.fill((r_cfg["color"] + (150,)) if valid else (239, 68, 68, 110))
                    screen.blit(t_surf, (sx, sy))
                    pygame.draw.rect(screen, (255, 255, 255) if valid else (239, 68, 68),
                                     (sx, sy, scaled_t, scaled_t), width=1)

                # Hover cursor tile
                sx, sy = camera.world_to_screen(m_gx * TILE_SIZE, m_gy * TILE_SIZE)
                hover_valid = road_tile_valid_draw(m_gx, m_gy)
                h_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                h_col = r_cfg["color"] if hover_valid else (239, 68, 68)
                h_surf.fill(h_col + (90,))
                screen.blit(h_surf, (sx, sy))
                pygame.draw.rect(screen, (255, 255, 255) if hover_valid else (239, 68, 68),
                                 (sx, sy, scaled_t, scaled_t), width=2)

                # Bottom bar: cost summary + confirm
                new_count = sum(1 for t in planning_road_tiles if road_tile_valid_draw(*t))
                cost = {}
                for _ in range(new_count):
                    for res, amt in r_cfg["cost"].items():
                        cost[res] = cost.get(res, 0) + amt
                cost_str = ", ".join(f"{a} {r}" for r, a in cost.items()) or "free"
                can_afford = all(resources.get(r, 0) >= a for r, a in cost.items())

                bar_w = 700
                bar_h = 92
                bar_x = (screen.get_width() - bar_w) // 2
                bar_y = screen.get_height() - bar_h - 14
                bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
                pygame.draw.rect(bar_surf, (15, 23, 42, 245), (0, 0, bar_w, bar_h), border_radius=10)
                pygame.draw.rect(bar_surf, (180, 83, 9), (0, 0, bar_w, bar_h), width=2, border_radius=10)
                screen.blit(bar_surf, (bar_x, bar_y))

                screen.blit(font_card.render(
                    f"Road: {r_cfg['name']} | {r_cfg['desc']} | Drag to paint ({new_count} new tiles)",
                    True, (250, 204, 21)), (bar_x + 16, bar_y + 10))
                stat_col = (34, 197, 94) if (new_count > 0 and can_afford) else (239, 68, 68)
                screen.blit(font_hud.render(
                    f"Cost: {cost_str} total | L-drag paint, R-click unpaint, Enter/Click confirm",
                    True, stat_col), (bar_x + 16, bar_y + 34))

                btn_y = bar_y + 56
                btn_confirm_rect.x = bar_x + 16
                btn_confirm_rect.y = btn_y
                btn_clear_rect.x = bar_x + 180
                btn_clear_rect.y = btn_y
                btn_cancel_rect.x = bar_x + 280
                btn_cancel_rect.y = btn_y
                c_col = (16, 185, 129) if (new_count > 0 and can_afford) else (71, 85, 105)
                pygame.draw.rect(screen, c_col, btn_confirm_rect, border_radius=6)
                screen.blit(font_btn.render("BUILD", True, (255, 255, 255)),
                            (btn_confirm_rect.x + 46, btn_confirm_rect.y + 8))
                pygame.draw.rect(screen, (71, 85, 105), btn_clear_rect, border_radius=6)
                screen.blit(font_btn.render("CLEAR", True, (255, 255, 255)),
                            (btn_clear_rect.x + 22, btn_clear_rect.y + 8))
                pygame.draw.rect(screen, (220, 38, 38), btn_cancel_rect, border_radius=6)
                screen.blit(font_btn.render("CANCEL", True, (255, 255, 255)),
                            (btn_cancel_rect.x + 24, btn_cancel_rect.y + 8))

            # -------------------------------------------------------------
            # 7.6c. OVERLAYS: DESTROY MODE (mark objects -> DONE -> confirm)
            # -------------------------------------------------------------
            elif planning_mode == "DESTROY":
                scaled_t = int(TILE_SIZE * camera.zoom)

                def mark_tiles(mark):
                    kind, obj = mark
                    if kind == "road":
                        return {obj}
                    return set(getattr(obj, "tiles", ()))

                # Red highlight on every marked object's tiles
                for mark in destroy_marks:
                    for (gx, ty) in mark_tiles(mark):
                        sx, sy = camera.world_to_screen(gx * TILE_SIZE, ty * TILE_SIZE)
                        t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                        t_surf.fill((220, 38, 38, 90))
                        screen.blit(t_surf, (sx, sy))
                        pygame.draw.rect(screen, (239, 68, 68),
                                         (sx, sy, scaled_t, scaled_t), width=1)

                # Hover highlight
                sx, sy = camera.world_to_screen(m_gx * TILE_SIZE, m_gy * TILE_SIZE)
                h_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                h_surf.fill((250, 204, 21, 70))
                screen.blit(h_surf, (sx, sy))
                pygame.draw.rect(screen, (250, 204, 21),
                                 (sx, sy, scaled_t, scaled_t), width=1)

                # Bottom bar
                bar_w = 640
                bar_h = 86
                bar_x = (screen.get_width() - bar_w) // 2
                bar_y = screen.get_height() - bar_h - 14
                bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
                pygame.draw.rect(bar_surf, (15, 23, 42, 245), (0, 0, bar_w, bar_h), border_radius=10)
                pygame.draw.rect(bar_surf, (220, 38, 38), (0, 0, bar_w, bar_h), width=2, border_radius=10)
                screen.blit(bar_surf, (bar_x, bar_y))

                screen.blit(font_card.render(
                    f"Destroy Mode — {len(destroy_marks)} marked | Click objects to mark/unmark",
                    True, (248, 113, 113)), (bar_x + 16, bar_y + 10))
                screen.blit(font_hud.render(
                    "Buildings -> demolition (50% refund) | Sites -> cancel (materials refunded) | Roads -> gone, no refund",
                    True, (148, 163, 184)),
                    (bar_x + 16, bar_y + 34))

                btn_y = bar_y + 46
                btn_done_rect.x = bar_x + 16
                btn_done_rect.y = btn_y
                btn_cancel_rect.x = bar_x + 140
                btn_cancel_rect.y = btn_y
                done_col = (220, 38, 38) if destroy_marks else (71, 85, 105)
                pygame.draw.rect(screen, done_col, btn_done_rect, border_radius=6)
                screen.blit(font_btn.render(f"DONE ({len(destroy_marks)})", True, (255, 255, 255)),
                            (btn_done_rect.x + 14, btn_done_rect.y + 8))
                pygame.draw.rect(screen, (71, 85, 105), btn_cancel_rect, border_radius=6)
                screen.blit(font_btn.render("CANCEL", True, (255, 255, 255)),
                            (btn_cancel_rect.x + 24, btn_cancel_rect.y + 8))

                # Confirm popup
                if destroy_confirm is not None:
                    n = len(destroy_confirm["marks"])
                    pw, ph = 380, 150
                    px = (screen.get_width() - pw) // 2
                    py = (screen.get_height() - ph) // 2
                    p_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
                    pygame.draw.rect(p_surf, (15, 23, 42, 250), (0, 0, pw, ph), border_radius=10)
                    pygame.draw.rect(p_surf, (220, 38, 38), (0, 0, pw, ph), width=2, border_radius=10)
                    screen.blit(p_surf, (px, py))
                    q_txt = font_card.render(f"Destroy {n} marked object(s)?", True, (255, 255, 255))
                    screen.blit(q_txt, (px + (pw - q_txt.get_width()) // 2, py + 22))
                    s_txt = font_hud.render("This cannot be undone.", True, (203, 213, 225))
                    screen.blit(s_txt, (px + (pw - s_txt.get_width()) // 2, py + 52))
                    destroy_yes_rect.x = px + pw // 2 - 125
                    destroy_yes_rect.y = py + ph - 52
                    destroy_no_rect.x = px + pw // 2 + 15
                    destroy_no_rect.y = py + ph - 52
                    pygame.draw.rect(screen, (220, 38, 38), destroy_yes_rect, border_radius=6)
                    screen.blit(font_btn.render("YES, DESTROY", True, (255, 255, 255)),
                                (destroy_yes_rect.x + 12, destroy_yes_rect.y + 8))
                    pygame.draw.rect(screen, (71, 85, 105), destroy_no_rect, border_radius=6)
                    screen.blit(font_btn.render("NO", True, (255, 255, 255)),
                                (destroy_no_rect.x + 32, destroy_no_rect.y + 8))

            # -------------------------------------------------------------
            # 7.7. OVERLAYS: SELECTED FURNITURE CONTEXT MENU / ACTION POPUP
            # -------------------------------------------------------------
            if selected_furniture is not None and planning_mode == "NONE" and not raport_ui.is_open:
                scaled_t = int(TILE_SIZE * camera.zoom)
                fsx, fsy = camera.world_to_screen(selected_furniture.grid_x * TILE_SIZE, selected_furniture.grid_y * TILE_SIZE)

                # Draw selection box on the furniture
                pygame.draw.rect(screen, (250, 204, 21), (fsx - 2, fsy - 2, scaled_t + 4, scaled_t + 4), width=2, border_radius=5)

                # Modal popup positioned conveniently above/below the tile
                has_owner = bool(selected_furniture.family_id)
                is_uninstalled = selected_furniture.status == "UNINSTALLED"
                furniture_cfg = getattr(selected_furniture, "type_cfg", {})
                public_order_pending = (
                    not has_owner
                    and not furniture_cfg.get("household_owned", True)
                    and (getattr(selected_furniture, "construction_order", None) or {}).get("status")
                    in ("AWAITING_PAYMENT", "LANDLORD_PAYMENT_PENDING")
                )
                cw, ch = 280, (152 if has_owner else 134)
                if is_uninstalled:
                    ch = 152
                if public_order_pending:
                    ch = max(ch, 112)
                furn_action_btns.clear()
                furn_acts = furniture_menu_actions(selected_furniture)
                act_row_h = 30 if furn_acts else 0
                if act_row_h:
                    ch += act_row_h
                cx = max(12, min(screen.get_width() - cw - 12, fsx + scaled_t // 2 - cw // 2))
                cy = fsy - ch - 12
                if cy < 50:
                    cy = fsy + scaled_t + 12
                cy = max(50, min(screen.get_height() - ch - 12, cy))

                furn_menu_rect.x = cx
                furn_menu_rect.y = cy
                furn_menu_rect.w = cw
                furn_menu_rect.h = ch

                # Popup surface
                popup_surf = pygame.Surface((cw, ch), pygame.SRCALPHA)
                pygame.draw.rect(popup_surf, (15, 23, 42, 245), (0, 0, cw, ch), border_radius=10)
                pygame.draw.rect(popup_surf, (234, 179, 8) if selected_furniture.status == "UNINSTALLED" else (56, 189, 248), (0, 0, cw, ch), width=2, border_radius=10)
                screen.blit(popup_surf, (cx, cy))

                # Header
                screen.blit(font_card.render(selected_furniture.name, True, (255, 255, 255)), (cx + 14, cy + 10))

                # Status badge
                st = selected_furniture.status
                st_col = (234, 179, 8) if st == "UNINSTALLED" else ((56, 189, 248) if st == "MOVING" else (34, 197, 94))
                screen.blit(font_badge.render(f"[{st}]", True, st_col), (cx + cw - 100, cy + 12))

                # Close (X) button
                btn_furn_close_rect.x = cx + cw - 26
                btn_furn_close_rect.y = cy + 10
                c_hov = btn_furn_close_rect.collidepoint(m_pos)
                pygame.draw.rect(screen, (220, 38, 38) if c_hov else (30, 41, 59), btn_furn_close_rect, border_radius=4)
                x_lbl = font_badge.render("X", True, (255, 255, 255))
                screen.blit(x_lbl, (btn_furn_close_rect.centerx - x_lbl.get_width() // 2, btn_furn_close_rect.centery - x_lbl.get_height() // 2))

                # Owner info
                owner_fam = next((fam for fam in villager_manager.families if fam.id == selected_furniture.family_id), None)
                owner_txt = f"Owner: The {owner_fam.surname} Family" if owner_fam else "Owner: Unassigned / Town"
                screen.blit(font_hud.render(owner_txt, True, (148, 163, 184)), (cx + 14, cy + 34))

                # Details info
                if selected_furniture.furniture_type == "household_storage":
                    det_txt = f"Inventory: {selected_furniture.total_stored} items stored"
                elif selected_furniture.construction_order and selected_furniture.construction_order.get("status") != "COMPLETE":
                    order = selected_furniture.construction_order
                    fee = from_copper(order.get("price_copper", 0))
                    fee_txt = f"{fee['Gold']}g {fee['Silver']}s {fee['Copper']}c"
                    order_status = order.get("status")
                    was_paid = order.get("commission_paid", order_status in ("PAID", "BUILDING"))
                    payment_txt = (
                        "Paid" if was_paid or order_status in ("PAID", "BUILDING", "COMPLETE")
                        else "Retrieving landlord coins" if order_status == "LANDLORD_RETRIEVING"
                        else "Payment traveling" if order_status == "PAYMENT_TRAVELING"
                        else "Awaiting payment"
                    )
                    det_txt = f"Commission: {fee_txt} | {payment_txt}"
                elif selected_furniture.furniture_type == "bed":
                    det_txt = f"Assigned: {selected_furniture.assigned_villager_id or 'Vacant Bed'}"
                else:
                    det_txt = f"Location: ({selected_furniture.grid_x}, {selected_furniture.grid_y})"
                screen.blit(font_hud.render(det_txt, True, (56, 189, 248)), (cx + 14, cy + 54))

                # Contextual action buttons (Catalogue / Immigrants / Workplace)
                if furn_acts:
                    aw = (cw - 28 - 8 * (len(furn_acts) - 1)) // len(furn_acts)
                    for i, (act, label) in enumerate(furn_acts):
                        r = pygame.Rect(cx + 14 + i * (aw + 8), cy + 72, aw, 28)
                        furn_action_btns.append({"rect": r, "action": act})
                        a_hov = r.collidepoint(m_pos)
                        pygame.draw.rect(screen, (30, 41, 59) if not a_hov else (45, 58, 82), r, border_radius=6)
                        pygame.draw.rect(screen, (56, 189, 248), r, width=1, border_radius=6)
                        a_txt = font_btn.render(label, True, (255, 255, 255))
                        screen.blit(a_txt, (r.centerx - a_txt.get_width() // 2, r.centery - a_txt.get_height() // 2))
                row2_y = cy + 76 + act_row_h

                # Contextual buttons — Household/Possessions hanya untuk
                # household chest; furniture lain cukup Move/Destroy.
                if (owner_fam and not is_uninstalled
                        and selected_furniture.furniture_type == "household_storage"):
                    btn_furn_house_rect.x = cx + 14
                    btn_furn_house_rect.y = row2_y
                    btn_furn_house_rect.w = 114
                    btn_furn_house_rect.h = 28
                    h_hov = btn_furn_house_rect.collidepoint(m_pos)
                    pygame.draw.rect(screen, (14, 116, 144) if h_hov else (15, 23, 42), btn_furn_house_rect, border_radius=6)
                    pygame.draw.rect(screen, (56, 189, 248), btn_furn_house_rect, width=1, border_radius=6)
                    h_txt = font_btn.render("Household", True, (255, 255, 255))
                    screen.blit(h_txt, (btn_furn_house_rect.centerx - h_txt.get_width() // 2, btn_furn_house_rect.centery - h_txt.get_height() // 2))

                    btn_furn_poss_rect.x = cx + cw - 14 - 114
                    btn_furn_poss_rect.y = row2_y
                    btn_furn_poss_rect.w = 114
                    btn_furn_poss_rect.h = 28
                    p_hov = btn_furn_poss_rect.collidepoint(m_pos)
                    pygame.draw.rect(screen, (202, 138, 4) if p_hov else (161, 98, 7), btn_furn_poss_rect, border_radius=6)
                    pygame.draw.rect(screen, (250, 204, 21), btn_furn_poss_rect, width=1, border_radius=6)
                    p_txt = font_btn.render("Possessions", True, (255, 255, 255))
                    screen.blit(p_txt, (btn_furn_poss_rect.centerx - p_txt.get_width() // 2, btn_furn_poss_rect.centery - p_txt.get_height() // 2))
                else:
                    btn_furn_house_rect.x = -9999
                    btn_furn_poss_rect.x = -9999

                if is_uninstalled:
                    btn_furn_store_rect.update(cx + 14, row2_y, cw - 28, 28)
                    store_hov = btn_furn_store_rect.collidepoint(m_pos)
                    pygame.draw.rect(screen, (16, 185, 129) if store_hov else (5, 150, 105), btn_furn_store_rect, border_radius=6)
                    pygame.draw.rect(screen, (52, 211, 153), btn_furn_store_rect, width=1, border_radius=6)
                    store_txt = font_btn.render("Store in Household", True, (255, 255, 255))
                    screen.blit(store_txt, (btn_furn_store_rect.centerx - store_txt.get_width() // 2, btn_furn_store_rect.centery - store_txt.get_height() // 2))
                else:
                    btn_furn_store_rect.x = -9999
                if public_order_pending:
                    order_status = (getattr(selected_furniture, "construction_order", None) or {}).get("status")
                    status_labels = {
                        "AWAITING_PAYMENT": "Awaiting landlord payment",
                        "LANDLORD_PAYMENT_PENDING": "Awaiting landlord funds",
                        "LANDLORD_RETRIEVING": "Servant collecting commission",
                        "PAYMENT_TRAVELING": "Servant delivering commission",
                        "PAID": "Commission paid — Builder assigned",
                        "BUILDING": "Builder building",
                        "AWAITING_MATERIAL": "Builder gathering materials",
                    }
                    order_text = font_badge.render(status_labels.get(order_status, "Builder order"), True, (56, 189, 248))
                    screen.blit(order_text, (cx + 14, row2_y + 6))
                else:
                    btn_furn_pay_builder_rect.x = -9999

                # Buttons: Move & Destroy
                btn_furn_move_rect.x = cx + 14
                btn_furn_move_rect.y = cy + ch - 42
                m_hov = btn_furn_move_rect.collidepoint(m_pos)
                pygame.draw.rect(screen, (37, 99, 235) if m_hov else (29, 78, 216), btn_furn_move_rect, border_radius=6)
                pygame.draw.rect(screen, (96, 165, 250), btn_furn_move_rect, width=1, border_radius=6)
                mv_txt = font_btn.render("Move", True, (255, 255, 255))
                screen.blit(mv_txt, (btn_furn_move_rect.centerx - mv_txt.get_width() // 2, btn_furn_move_rect.centery - mv_txt.get_height() // 2))

                btn_furn_destroy_rect.x = cx + cw - 14 - btn_furn_destroy_rect.w
                btn_furn_destroy_rect.y = cy + ch - 42
                d_hov = btn_furn_destroy_rect.collidepoint(m_pos)
                pygame.draw.rect(screen, (220, 38, 38) if d_hov else (185, 28, 28), btn_furn_destroy_rect, border_radius=6)
                pygame.draw.rect(screen, (248, 113, 113), btn_furn_destroy_rect, width=1, border_radius=6)
                des_txt = font_btn.render("Destroy", True, (255, 255, 255))
                screen.blit(des_txt, (btn_furn_destroy_rect.centerx - des_txt.get_width() // 2, btn_furn_destroy_rect.centery - des_txt.get_height() // 2))

            # -------------------------------------------------------------
            # 7.74. PUBLIC STRUCTURE CONTEXT MENU (List / Destroy / actions)
            # -------------------------------------------------------------
            if selected_structure is not None and planning_mode == "NONE" and not raport_ui.is_open:
                b = selected_structure
                bxs = [t[0] for t in getattr(b, "tiles", set())]
                bys = [t[1] for t in getattr(b, "tiles", set())]
                if bxs and bys:
                    bwx = ((min(bxs) + max(bxs) + 1) / 2) * TILE_SIZE
                    bwy = ((min(bys) + max(bys) + 1) / 2) * TILE_SIZE
                    bsx, bsy = camera.world_to_screen(bwx, bwy)
                    # Selection outline around the whole footprint
                    ox0, oy0 = camera.world_to_screen(min(bxs) * TILE_SIZE, min(bys) * TILE_SIZE)
                    ox1, oy1 = camera.world_to_screen((max(bxs) + 1) * TILE_SIZE, (max(bys) + 1) * TILE_SIZE)
                    pygame.draw.rect(screen, (250, 204, 21), (ox0, oy0, ox1 - ox0, oy1 - oy0), width=2, border_radius=5)

                    struct_acts = structure_menu_actions(b)
                    cw, ch = 260, 104 + (30 if struct_acts else 0)
                    cx = max(12, min(screen.get_width() - cw - 12, bsx - cw // 2))
                    cy = bsy - ch - 12
                    if cy < 50:
                        cy = bsy + int(TILE_SIZE * camera.zoom) + 12
                    cy = max(50, min(screen.get_height() - ch - 12, cy))

                    struct_menu_rect.update(cx, cy, cw, ch)
                    struct_action_btns.clear()

                    popup_surf = pygame.Surface((cw, ch), pygame.SRCALPHA)
                    pygame.draw.rect(popup_surf, (15, 23, 42, 245), (0, 0, cw, ch), border_radius=10)
                    pygame.draw.rect(popup_surf, (56, 189, 248), (0, 0, cw, ch), width=2, border_radius=10)
                    screen.blit(popup_surf, (cx, cy))

                    screen.blit(font_card.render(getattr(b, "name", "Structure"), True, (255, 255, 255)), (cx + 14, cy + 10))
                    st_cfg = getattr(b, "type_cfg", {}) or {}
                    sub_txt = f"{st_cfg.get('name', b.building_type)} • Public Structure • {len(b.tiles)} tiles"
                    screen.blit(font_hud.render(sub_txt, True, (148, 163, 184)), (cx + 14, cy + 32))

                    btn_struct_close_rect.x = cx + cw - 26
                    btn_struct_close_rect.y = cy + 10
                    c_hov = btn_struct_close_rect.collidepoint(m_pos)
                    pygame.draw.rect(screen, (220, 38, 38) if c_hov else (30, 41, 59), btn_struct_close_rect, border_radius=4)
                    x_lbl = font_badge.render("X", True, (255, 255, 255))
                    screen.blit(x_lbl, (btn_struct_close_rect.centerx - x_lbl.get_width() // 2, btn_struct_close_rect.centery - x_lbl.get_height() // 2))

                    # Contextual action row (Market / Workplace)
                    if struct_acts:
                        aw = (cw - 28 - 8 * (len(struct_acts) - 1)) // len(struct_acts)
                        for i, (act, label) in enumerate(struct_acts):
                            r = pygame.Rect(cx + 14 + i * (aw + 8), cy + 52, aw, 28)
                            struct_action_btns.append({"rect": r, "action": act})
                            a_hov = r.collidepoint(m_pos)
                            pygame.draw.rect(screen, (30, 41, 59) if not a_hov else (45, 58, 82), r, border_radius=6)
                            pygame.draw.rect(screen, (56, 189, 248), r, width=1, border_radius=6)
                            a_txt = font_btn.render(label, True, (255, 255, 255))
                            screen.blit(a_txt, (r.centerx - a_txt.get_width() // 2, r.centery - a_txt.get_height() // 2))

                    # Bottom row: List (info panel) & Destroy (demolition)
                    btn_struct_list_rect.x = cx + 14
                    btn_struct_list_rect.y = cy + ch - 42
                    l_hov = btn_struct_list_rect.collidepoint(m_pos)
                    pygame.draw.rect(screen, (37, 99, 235) if l_hov else (29, 78, 216), btn_struct_list_rect, border_radius=6)
                    pygame.draw.rect(screen, (96, 165, 250), btn_struct_list_rect, width=1, border_radius=6)
                    l_txt = font_btn.render("List", True, (255, 255, 255))
                    screen.blit(l_txt, (btn_struct_list_rect.centerx - l_txt.get_width() // 2, btn_struct_list_rect.centery - l_txt.get_height() // 2))

                    btn_struct_destroy_rect.x = cx + cw - 14 - btn_struct_destroy_rect.w
                    btn_struct_destroy_rect.y = cy + ch - 42
                    d_hov = btn_struct_destroy_rect.collidepoint(m_pos)
                    pygame.draw.rect(screen, (220, 38, 38) if d_hov else (185, 28, 28), btn_struct_destroy_rect, border_radius=6)
                    pygame.draw.rect(screen, (248, 113, 113), btn_struct_destroy_rect, width=1, border_radius=6)
                    d_txt = font_btn.render("Destroy", True, (255, 255, 255))
                    screen.blit(d_txt, (btn_struct_destroy_rect.centerx - d_txt.get_width() // 2, btn_struct_destroy_rect.centery - d_txt.get_height() // 2))

            # -------------------------------------------------------------
            # 7.75. WORKPLACE BASE POPUP (Permit vs Structure)
            # -------------------------------------------------------------
            if workplace_popup is not None and planning_mode == "NONE" and not raport_ui.is_open:
                kind = workplace_popup["kind"]
                obj = workplace_popup["obj"]
                bases = workplace_bases_for(kind, obj)
                ox, oy = workplace_popup.get("pos", m_pos)
                pw, ph = 260, 96
                px = min(max(8, ox - pw // 2), screen.get_width() - pw - 8)
                py = min(max(8, oy - ph - 14), screen.get_height() - ph - 8)
                wp_popup_rect.update(px, py, pw, ph)
                pygame.draw.rect(screen, (24, 24, 30), wp_popup_rect, border_radius=8)
                pygame.draw.rect(screen, (80, 80, 95), wp_popup_rect, width=1, border_radius=8)

                title = f"{getattr(obj, 'name', '') or getattr(obj, 'permit_type', '') or getattr(obj, 'furniture_type', '') or getattr(obj, 'building_type', '')}"
                title_s = font_badge.render(title[:26], True, (220, 220, 230))
                screen.blit(title_s, (px + 12, py + 8))

                wp_close_btn_rect.update(px + pw - 24, py + 6, 18, 18)
                ch_hov = wp_close_btn_rect.collidepoint(m_pos)
                pygame.draw.rect(screen, (200, 60, 60) if ch_hov else (140, 45, 45), wp_close_btn_rect, border_radius=4)
                ch_s = font_badge.render("x", True, (255, 255, 255))
                screen.blit(ch_s, (wp_close_btn_rect.centerx - ch_s.get_width() // 2, wp_close_btn_rect.centery - ch_s.get_height() // 2))

                btn_w = (pw - 12 * 3) // 2
                by = py + 34
                wp_base_btn_rect.update(px + 12, by, btn_w, 26)
                wp_ws_btn_rect.update(px + 12 + btn_w + 12, by, btn_w, 26)

                base_label = "PERMIT" if "permit" in bases else "STRUCTURE"
                for rect, label, enabled in (
                    (wp_base_btn_rect, base_label, bool(bases)),
                    (wp_ws_btn_rect, "WORKSTATION", True),
                ):
                    hov = enabled and rect.collidepoint(m_pos)
                    if enabled:
                        bg = (37, 99, 235) if hov else (29, 78, 216)
                        fg = (96, 165, 250) if hov else (30, 64, 175)
                        tc = (255, 255, 255)
                    else:
                        bg = (45, 45, 52)
                        fg = (60, 60, 68)
                        tc = (110, 110, 120)
                    pygame.draw.rect(screen, bg, rect, border_radius=6)
                    pygame.draw.rect(screen, fg, rect, width=1, border_radius=6)
                    t = font_badge.render(label, True, tc)
                    screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))
            else:
                wp_popup_rect.x = -9999
                wp_base_btn_rect.x = -9999
                wp_ws_btn_rect.x = -9999
                wp_close_btn_rect.x = -9999

            # -------------------------------------------------------------
            # 7.76. MINE INFO POPUP (natural resources)
            # -------------------------------------------------------------
            if mine_popup is not None and planning_mode == "NONE" and not raport_ui.is_open:
                from game.world.natural_resources import NaturalResourceManager
                mine = mine_popup["mine"]
                ox, oy = mine_popup.get("pos", m_pos)
                pw, ph = 240, 92
                px = min(max(8, ox - pw // 2), screen.get_width() - pw - 8)
                py = min(max(8, oy - ph - 14), screen.get_height() - ph - 8)
                mine_popup_rect.update(px, py, pw, ph)
                pygame.draw.rect(screen, (24, 24, 30), mine_popup_rect, border_radius=8)
                pygame.draw.rect(screen, (80, 80, 95), mine_popup_rect, width=1, border_radius=8)

                kind_label = str(mine.get("kind", "Mine")).replace("_", " ").title()
                screen.blit(font_badge.render(kind_label, True, (220, 220, 230)), (px + 12, py + 8))
                tier_name = NaturalResourceManager.mine_tier_name(mine)
                lo, hi = NaturalResourceManager.mine_yield_range(mine)
                screen.blit(font_badge.render(f"Tier: {tier_name}", True, (251, 191, 36)), (px + 12, py + 28))
                screen.blit(font_body.render(f"Yield: {lo}-{hi} per hour", True, (203, 213, 225)), (px + 12, py + 48))
                screen.blit(font_body.render("Unlimited deposit", True, (148, 163, 184)), (px + 12, py + 68))
            else:
                mine_popup_rect.x = -9999

            # -------------------------------------------------------------
            # 7.8. OVERLAYS: SELECTED INDIVIDUAL AI PROFILE POPUP (Agent 1)
            # -------------------------------------------------------------
            if selected_entity is not None and planning_mode == "NONE" and not raport_ui.is_open:
                esx, esy = camera.world_to_screen(selected_entity.x, selected_entity.y)
                er = max(6, int(getattr(selected_entity, "radius", 20) * camera.zoom))

                # Ring indicator around entity
                pygame.draw.circle(screen, (56, 189, 248), (esx, esy), er + 6, 2)

                is_alive = getattr(selected_entity, "is_alive", True)
                h_timer = getattr(selected_entity, "hunger_death_timer", None)
                t_timer = getattr(selected_entity, "thirst_death_timer", None)
                has_happiness = hasattr(selected_entity, "happiness")
                next_activities = ActivityPreviewSystem.get_next_activities(selected_entity)
                next_activities = next_activities[:AI_ACTIVITY_PREVIEW_MAX_NEXT]
                next_rows = next_activities or ["No queued activity"]
                happiness_factors = HappinessSystem.get_breakdown(selected_entity) if has_happiness else []
                visible_factor_rows = min(
                    max(1, len(happiness_factors)),
                    AI_PROFILE_HAPPINESS_VISIBLE_ROWS,
                )
                activity_row_height = AI_PROFILE_ACTIVITY_ROW_HEIGHT
                act_offset = (
                    AI_PROFILE_DECEASED_ACTIVITY_OFFSET
                    if not is_alive else AI_PROFILE_ACTIVITY_OFFSET
                )
                next_header_offset = act_offset + AI_PROFILE_ACTIVITY_HEADER_OFFSET
                next_start_offset = next_header_offset + activity_row_height
                bar_start_offset = (
                    next_start_offset + len(next_rows) * activity_row_height
                    + AI_PROFILE_NEED_SECTION_GAP
                )
                bar_count = 5 + int(hasattr(selected_entity, "faith"))
                info_y1_offset = (
                    bar_start_offset + bar_count * AI_PROFILE_NEED_ROW_HEIGHT
                    + AI_PROFILE_INFO_SECTION_GAP
                )
                info_y2_offset = info_y1_offset + AI_PROFILE_NEED_ROW_HEIGHT
                happiness_panel_offset = info_y2_offset + AI_PROFILE_FACTOR_SECTION_GAP
                happiness_panel_height = (
                    AI_PROFILE_FACTOR_PANEL_HEADER_HEIGHT
                    + visible_factor_rows * activity_row_height
                )
                ch = (
                    happiness_panel_offset + happiness_panel_height
                    + AI_PROFILE_PANEL_BOTTOM_PADDING
                    if has_happiness else info_y2_offset + 28
                )
                cw = min(AI_PROFILE_CARD_WIDTH, max(1, screen.get_width() - 24))
                cx = max(12, min(screen.get_width() - cw - 12, esx - cw // 2))
                cy = esy - ch - 16
                if cy < 50:
                    cy = esy + er + 16
                cy = max(50, min(screen.get_height() - ch - 12, cy))

                entity_card_rect.x = cx
                entity_card_rect.y = cy
                entity_card_rect.w = cw
                entity_card_rect.h = ch

                card_surf = pygame.Surface((cw, ch), pygame.SRCALPHA)
                pygame.draw.rect(card_surf, (15, 23, 42, 245), (0, 0, cw, ch), border_radius=10)
                pygame.draw.rect(card_surf, (56, 189, 248), (0, 0, cw, ch), width=2, border_radius=10)
                screen.blit(card_surf, (cx, cy))

                # Living / Deceased / Survival Countdown Status Badge
                if not is_alive:
                    reason = getattr(selected_entity, "death_reason", "Starvation")
                    st_txt = font_badge.render(f"[DECEASED: {reason}]", True, (239, 68, 68))
                elif h_timer is not None and t_timer is not None:
                    st_txt = font_badge.render("[CRITICAL: Starving & Dehydrated]", True, (239, 68, 68))
                elif h_timer is not None:
                    st_txt = font_badge.render(f"[CRITICAL: Starving in {h_timer:.1f}h]", True, (239, 68, 68))
                elif t_timer is not None:
                    st_txt = font_badge.render(f"[CRITICAL: Dehydrated in {t_timer:.1f}h]", True, (239, 68, 68))
                else:
                    st_txt = font_badge.render("[ALIVE]", True, (34, 197, 94))

                # Close (X) button
                btn_entity_close_rect.x = cx + cw - 26
                btn_entity_close_rect.y = cy + 10
                c_hov = btn_entity_close_rect.collidepoint(m_pos)
                pygame.draw.rect(screen, (220, 38, 38) if c_hov else (30, 41, 59), btn_entity_close_rect, border_radius=4)
                x_lbl = font_badge.render("X", True, (255, 255, 255))
                screen.blit(x_lbl, (btn_entity_close_rect.centerx - x_lbl.get_width() // 2, btn_entity_close_rect.centery - x_lbl.get_height() // 2))

                # Row 1: Identity Name & Role
                name_str = getattr(selected_entity, "full_name", getattr(selected_entity, "name", "Settler"))
                role_str = getattr(selected_entity, "role", "")
                title_lbl = f"{name_str} ({role_str})" if role_str else name_str
                
                avail_title_w = max(40, cw - 36 - (st_txt.get_width() + 14 if is_alive else 0))
                title_surf = font_card.render(title_lbl, True, (255, 255, 255))
                if title_surf.get_width() > avail_title_w:
                    for i in range(len(title_lbl), 0, -1):
                        trunc_s = font_card.render(title_lbl[:i] + "...", True, (255, 255, 255))
                        if trunc_s.get_width() <= avail_title_w:
                            title_surf = trunc_s
                            break
                screen.blit(title_surf, (cx + 14, cy + 10))
                if is_alive:
                    screen.blit(st_txt, (cx + cw - 32 - st_txt.get_width(), cy + 12))

                # Household Affiliation
                fam_id = getattr(selected_entity, "family_id", None)
                if fam_id and villager_manager:
                    fam_obj = villager_manager.get_family_by_id(fam_id)
                    household_name = f"The {fam_obj.surname} Family" if fam_obj else str(fam_id)
                    btn_entity_household_rect.x = cx + cw - 96
                    btn_entity_household_rect.y = cy + 32
                    btn_entity_household_rect.w = 82
                    btn_entity_household_rect.h = 20
                    hh_hov = btn_entity_household_rect.collidepoint(m_pos)
                    pygame.draw.rect(screen, (14, 116, 144) if hh_hov else (15, 23, 42), btn_entity_household_rect, border_radius=4)
                    pygame.draw.rect(screen, (56, 189, 248), btn_entity_household_rect, width=1, border_radius=4)
                    hh_lbl = font_badge.render("Household", True, (255, 255, 255))
                    screen.blit(hh_lbl, (btn_entity_household_rect.centerx - hh_lbl.get_width() // 2, btn_entity_household_rect.centery - hh_lbl.get_height() // 2))
                else:
                    household_name = getattr(selected_entity, "household_name", "Crown Estate Household")
                    btn_entity_household_rect.x = -9999

                # Row 2: Status (if deceased) or Household Name
                if not is_alive:
                    screen.blit(st_txt, (cx + 14, cy + 32))
                    screen.blit(font_hud.render(f"Household: {household_name}", True, (56, 189, 248)), (cx + 14, cy + 48))
                    act_y = cy + 68
                else:
                    screen.blit(font_hud.render(f"Household: {household_name}", True, (56, 189, 248)), (cx + 14, cy + 34))
                    act_y = cy + 54

                # Current and upcoming activity details
                job_name = getattr(selected_entity, "job", "Worker")
                if not is_alive:
                    task_name = "DECEASED"
                else:
                    raw_act = (
                        getattr(selected_entity, "current_activity", None)
                        or getattr(selected_entity, "activity", None)
                        or getattr(selected_entity, "task", None)
                        or getattr(selected_entity, "state", "IDLE")
                    )
                    task_name = str(raw_act).replace("_", " ").title() if raw_act == getattr(selected_entity, "task", None) else str(raw_act)
                screen.blit(font_body.render(f"Profession: {job_name}", True, (226, 232, 240)), (cx + 14, act_y))
                current_activity_y = act_y + 14
                current_activity_rect = pygame.Rect(cx + 14, current_activity_y, cw - 28, font_body.get_height())
                old_clip = screen.get_clip()
                screen.set_clip(current_activity_rect)
                screen.blit(
                    font_body.render(f"Current Activity: {task_name}", True, (226, 232, 240)),
                    (current_activity_rect.x, current_activity_rect.y),
                )
                screen.set_clip(old_clip)

                next_header_y = cy + next_header_offset
                screen.blit(
                    font_badge.render("Next Activities:", True, (56, 189, 248)),
                    (cx + 14, next_header_y),
                )
                next_row_rect = pygame.Rect(
                    cx + 14, cy + next_start_offset, cw - 28,
                    len(next_rows) * activity_row_height,
                )
                old_clip = screen.get_clip()
                screen.set_clip(next_row_rect)
                for index, activity in enumerate(next_rows):
                    screen.blit(
                        font_badge.render(f"- {activity}", True, (203, 213, 225)),
                        (next_row_rect.x, next_row_rect.y + index * activity_row_height),
                    )
                screen.set_clip(old_clip)

                # Happiness is the first need meter on the profile card.
                bar_y1 = cy + bar_start_offset
                if hasattr(selected_entity, "happiness"):
                    happiness_val = max(
                        HAPPINESS_MIN_VALUE,
                        min(HAPPINESS_MAX_VALUE, float(selected_entity.happiness)),
                    )
                    happiness_status = getattr(selected_entity, "happiness_status", "happy")
                    happiness_band = next(
                        (band for band in HAPPINESS_STATUS_BANDS if band["id"] == happiness_status),
                        HAPPINESS_STATUS_BANDS[0],
                    )
                    happiness_color = HAPPINESS_STATUS_COLORS.get(happiness_status, (148, 163, 184))
                    screen.blit(font_badge.render("Happiness:", True, (241, 245, 249)), (cx + 14, bar_y1))
                    happiness_bg = pygame.Rect(cx + 68, bar_y1, 150, 14)
                    pygame.draw.rect(screen, (30, 41, 59), happiness_bg, border_radius=4)
                    happiness_range = max(1.0, HAPPINESS_MAX_VALUE - HAPPINESS_MIN_VALUE)
                    happiness_fill = max(0, int(150 * ((happiness_val - HAPPINESS_MIN_VALUE) / happiness_range)))
                    if happiness_fill > 0:
                        pygame.draw.rect(screen, happiness_color, (cx + 68, bar_y1, happiness_fill, 14), border_radius=4)
                    pygame.draw.rect(screen, (71, 85, 105), happiness_bg, width=1, border_radius=4)
                    screen.blit(font_badge.render(happiness_band.get("label", "Happy"), True, happiness_color), (cx + 226, bar_y1))

                # Sleep follows happiness, then bodily needs and faith.
                bar_y2 = bar_y1 + AI_PROFILE_NEED_ROW_HEIGHT
                if hasattr(selected_entity, "sleep_need"):
                    sleep_val = max(SLEEP_MIN_VALUE, min(SLEEP_MAX_VALUE, float(selected_entity.sleep_need)))
                    sleep_status = getattr(selected_entity, "sleep_status", "rested")
                    sleep_color = SLEEP_STATUS_COLORS.get(sleep_status, (148, 163, 184))
                    screen.blit(font_badge.render("Sleep:", True, (241, 245, 249)), (cx + 14, bar_y2))
                    sleep_bg = pygame.Rect(cx + 68, bar_y2, 150, 14)
                    pygame.draw.rect(screen, (30, 41, 59), sleep_bg, border_radius=4)
                    sleep_range = max(1.0, SLEEP_MAX_VALUE - SLEEP_MIN_VALUE)
                    sleep_fill = max(0, int(150 * ((sleep_val - SLEEP_MIN_VALUE) / sleep_range)))
                    if sleep_fill > 0:
                        pygame.draw.rect(screen, sleep_color, (cx + 68, bar_y2, sleep_fill, 14), border_radius=4)
                    pygame.draw.rect(screen, (71, 85, 105), sleep_bg, width=1, border_radius=4)
                    screen.blit(font_badge.render(f"{int(sleep_val)}% {sleep_status.replace('_', ' ').title()}", True, sleep_color), (cx + 226, bar_y2))

                # Hunger, thirst, toilet, and faith follow the sleep bar.
                bar_y3 = bar_y2 + AI_PROFILE_NEED_ROW_HEIGHT
                h_val = max(0.0, min(100.0, getattr(selected_entity, "hunger", 100.0)))
                screen.blit(font_badge.render("Hunger:", True, (241, 245, 249)), (cx + 14, bar_y3))
                h_bg = pygame.Rect(cx + 68, bar_y3, 150, 14)
                pygame.draw.rect(screen, (30, 41, 59), h_bg, border_radius=4)
                h_fill = max(0, int(150 * (h_val / 100.0)))
                if h_fill > 0:
                    h_c = (34, 197, 94) if h_val > 50 else ((234, 179, 8) if h_val > 20 else (239, 68, 68))
                    pygame.draw.rect(screen, h_c, (cx + 68, bar_y3, h_fill, 14), border_radius=4)
                pygame.draw.rect(screen, (71, 85, 105), h_bg, width=1, border_radius=4)
                h_str = f"{int(h_val)}%" if h_timer is None else f"{int(h_val)}% ({h_timer:.1f}h)"
                h_color = (255, 255, 255) if h_timer is None else (239, 68, 68)
                screen.blit(font_badge.render(h_str, True, h_color), (cx + 226, bar_y3))

                # Row 5: Thirst Bar
                bar_y4 = bar_y3 + AI_PROFILE_NEED_ROW_HEIGHT
                t_val = max(0.0, min(100.0, getattr(selected_entity, "thirst", 100.0)))
                screen.blit(font_badge.render("Thirst:", True, (241, 245, 249)), (cx + 14, bar_y4))
                t_bg = pygame.Rect(cx + 68, bar_y4, 150, 14)
                pygame.draw.rect(screen, (30, 41, 59), t_bg, border_radius=4)
                t_fill = max(0, int(150 * (t_val / 100.0)))
                if t_fill > 0:
                    t_c = (56, 189, 248) if t_val > 50 else ((59, 130, 246) if t_val > 20 else (239, 68, 68))
                    pygame.draw.rect(screen, t_c, (cx + 68, bar_y4, t_fill, 14), border_radius=4)
                pygame.draw.rect(screen, (71, 85, 105), t_bg, width=1, border_radius=4)
                t_str = f"{int(t_val)}%" if t_timer is None else f"{int(t_val)}% ({t_timer:.1f}h)"
                t_color = (255, 255, 255) if t_timer is None else (239, 68, 68)
                screen.blit(font_badge.render(t_str, True, t_color), (cx + 226, bar_y4))

                # Row 6: Need Toilet Bar
                bar_y5 = bar_y4 + AI_PROFILE_NEED_ROW_HEIGHT
                tl_val = max(0.0, min(100.0, getattr(selected_entity, "toilet", getattr(selected_entity, "need_toilet", 100.0))))
                screen.blit(font_badge.render("Toilet:", True, (241, 245, 249)), (cx + 14, bar_y5))
                tl_bg = pygame.Rect(cx + 68, bar_y5, 150, 14)
                pygame.draw.rect(screen, (30, 41, 59), tl_bg, border_radius=4)
                tl_fill = max(0, int(150 * (tl_val / 100.0)))
                if tl_fill > 0:
                    tl_c = (16, 185, 129) if tl_val > 50 else ((245, 158, 11) if tl_val > 20 else (239, 68, 68))
                    pygame.draw.rect(screen, tl_c, (cx + 68, bar_y5, tl_fill, 14), border_radius=4)
                pygame.draw.rect(screen, (71, 85, 105), tl_bg, width=1, border_radius=4)
                screen.blit(font_badge.render(f"{int(tl_val)}%", True, (255, 255, 255)), (cx + 226, bar_y5))

                # Faith meter is individual and does not decay continuously like bodily needs.
                info_y1 = bar_y5 + AI_PROFILE_NEED_ROW_HEIGHT + AI_PROFILE_INFO_SECTION_GAP
                if hasattr(selected_entity, "faith"):
                    bar_y6 = bar_y5 + AI_PROFILE_NEED_ROW_HEIGHT
                    faith_val = max(0.0, min(100.0, selected_entity.faith))
                    screen.blit(font_badge.render("Faith:", True, (241, 245, 249)), (cx + 14, bar_y6))
                    faith_bg = pygame.Rect(cx + 68, bar_y6, 150, 14)
                    pygame.draw.rect(screen, (30, 41, 59), faith_bg, border_radius=4)
                    faith_fill = max(0, int(150 * (faith_val / 100.0)))
                    if faith_fill > 0:
                        faith_color = (34, 197, 94) if faith_val > 50 else ((234, 179, 8) if faith_val > 20 else (239, 68, 68))
                        pygame.draw.rect(screen, faith_color, (cx + 68, bar_y6, faith_fill, 14), border_radius=4)
                    pygame.draw.rect(screen, (71, 85, 105), faith_bg, width=1, border_radius=4)
                    screen.blit(font_badge.render(f"{int(faith_val)}%", True, (255, 255, 255)), (cx + 226, bar_y6))
                    info_y1 = bar_y6 + AI_PROFILE_NEED_ROW_HEIGHT + AI_PROFILE_INFO_SECTION_GAP
                inv_items = []
                for it, c in getattr(selected_entity, "inventory", {}).items():
                    if c > 0:
                        inv_items.append(f"{c}x {it}")
                carried_crop = getattr(selected_entity, "carrying_crop", 0)
                if carried_crop > 0:
                    inv_items.append(f"{carried_crop}x Harvest")
                carried_res = getattr(selected_entity, "carried_res", None)
                if carried_res and getattr(selected_entity, "carried_amount", 0) > 0:
                    inv_items.append(f"{selected_entity.carried_amount}x {carried_res}")

                inv_summary = ", ".join(inv_items) if inv_items else "Empty (Hands free)"
                screen.blit(font_badge.render(f"Inventory: {inv_summary[:40]}", True, (148, 163, 184)), (cx + 14, info_y1))

                # Row 8: Bed / Tool info
                info_y2 = info_y1 + AI_PROFILE_NEED_ROW_HEIGHT
                assigned_bed = getattr(selected_entity, "assigned_bed_id", None)
                bed_str = f"Bed: {assigned_bed}" if assigned_bed else "Bed: Floor"
                tool_str = f"Tool: {getattr(selected_entity, 'active_tool', None) or 'None'}"
                screen.blit(font_badge.render(f"{bed_str}  •  {tool_str}", True, (100, 116, 139)), (cx + 14, info_y2))

                if has_happiness:
                    happiness_panel = pygame.Rect(
                        cx + 14, cy + happiness_panel_offset, cw - 28,
                        happiness_panel_height,
                    )
                    entity_happiness_rect.update(happiness_panel)
                    pygame.draw.rect(screen, (24, 34, 52), happiness_panel, border_radius=6)
                    pygame.draw.rect(screen, (51, 65, 85), happiness_panel, width=1, border_radius=6)

                    max_scroll = max(0, len(happiness_factors) - visible_factor_rows)
                    selected_entity_happiness_scroll = min(
                        max(0, selected_entity_happiness_scroll), max_scroll
                    )
                    first_factor = selected_entity_happiness_scroll
                    last_factor = min(
                        len(happiness_factors),
                        first_factor + visible_factor_rows,
                    )
                    if happiness_factors:
                        panel_title = (
                            f"Happiness factors {first_factor + 1}-{last_factor} "
                            f"of {len(happiness_factors)} (scroll)"
                        )
                    else:
                        panel_title = "Happiness factors"
                    screen.blit(
                        font_badge.render(panel_title, True, (56, 189, 248)),
                        (happiness_panel.x + 8, happiness_panel.y + 5),
                    )

                    if not happiness_factors:
                        screen.blit(
                            font_badge.render("No active happiness modifiers", True, (148, 163, 184)),
                            (
                                happiness_panel.x + 8,
                                happiness_panel.y + AI_PROFILE_FACTOR_PANEL_HEADER_HEIGHT,
                            ),
                        )
                    else:
                        factor_clip = pygame.Rect(
                            happiness_panel.x + 8,
                            happiness_panel.y + AI_PROFILE_FACTOR_PANEL_HEADER_HEIGHT,
                            happiness_panel.width - 16,
                            happiness_panel.height - AI_PROFILE_FACTOR_PANEL_HEADER_HEIGHT,
                        )
                        old_clip = screen.get_clip()
                        screen.set_clip(factor_clip)
                        for row, factor in enumerate(happiness_factors[first_factor:last_factor]):
                            amount = float(factor.get("amount", 0.0))
                            label = str(factor.get("label", "Happiness factor"))
                            color = (74, 222, 128) if amount >= 0 else (248, 113, 113)
                            row_y = factor_clip.y + row * activity_row_height
                            label_surface = font_badge.render(label, True, (226, 232, 240))
                            value_surface = font_badge.render(f"{amount:+g}", True, color)
                            label_clip = pygame.Rect(
                                factor_clip.x, row_y,
                                factor_clip.width - value_surface.get_width() - 8,
                                activity_row_height,
                            )
                            screen.set_clip(label_clip)
                            screen.blit(label_surface, (factor_clip.x, row_y))
                            screen.set_clip(factor_clip)
                            screen.blit(
                                value_surface,
                                (factor_clip.right - value_surface.get_width(), row_y),
                            )
                        screen.set_clip(old_clip)
                else:
                    entity_happiness_rect.update(0, 0, 0, 0)

            # 8. Clock & Calendar HUD (Top Left)
            day_cycle.draw_hud(screen, villager_manager)

            # 9. In-Game Settings Button
            settings_modal.draw_hud_button(screen)

            # 10. Resources HUD
            resource_hud.draw(screen, resources, weekday=day_cycle.get_weekday_name(),
                              furniture_manager=furniture_manager)

            # 10.5. Add Item Cheat Button (below Resources HUD; requires ESC-menu cheat unlock)
            screen_w = screen.get_width()
            res_card_h = (resource_hud.header_height + 7 * resource_hud.row_height
                          + resource_hud.padding)
            btn_add_item_cheat_rect.x = screen_w - PATH_TOGGLE_BTN_WIDTH - resource_hud.margin
            btn_add_item_cheat_rect.y = resource_hud.margin + res_card_h + 10
            if cheats_active:
                m_pos = pygame.mouse.get_pos()
                cheat_hover = btn_add_item_cheat_rect.collidepoint(m_pos)
                cheat_bg = (180, 83, 9) if cheat_hover else (120, 53, 15)
                pygame.draw.rect(screen, cheat_bg, btn_add_item_cheat_rect, border_radius=6)
                pygame.draw.rect(screen, (245, 158, 11), btn_add_item_cheat_rect, width=1, border_radius=6)
                cheat_txt = font_btn.render("Add Item", True, (255, 255, 255))
                screen.blit(cheat_txt, cheat_txt.get_rect(center=btn_add_item_cheat_rect.center))
                path_debug_overlay.draw_toggle(screen, btn_add_item_cheat_rect, font_btn)

                if cheat_notice_timer > 0.0:
                    cheat_notice_timer = max(0.0, cheat_notice_timer - game_dt)
                    not_surf = font_badge.render(cheat_notice, True, (250, 204, 21))
                    not_rect = not_surf.get_rect(right=screen_w - resource_hud.margin, top=btn_add_item_cheat_rect.bottom + 6)
                    screen.blit(not_surf, not_rect)

            # 11. Left Raport Button & Modal
            raport_ui.draw(screen, building_manager, permit_manager, resources, servant_manager, villager_manager, schedule_manager=schedule_manager, day_cycle=day_cycle, furniture_manager=furniture_manager, stockpile_manager=stockpile_manager, production_system=production_system)

            # 11.5. Market Profile Modal Dialog (AGENT 2)
            market_modal.draw(screen, resources, stockpile_manager, servant_manager=servant_manager, villager_manager=villager_manager, furniture_manager=furniture_manager, day_number=day_cycle.day_number)

            # 11.6. Add Item Cheat Modal Dialog (AGENT 2)
            add_item_modal.draw(screen, permit_manager, stockpile_manager)

            # 11.7. ESC Cheat Menu Modal
            cheat_modal.draw(screen, cheats_active=cheats_active)

            # 11.8. Starter Placement Ghost + Confirm Dialog
            if pending_starter_id is not None:
                from game.systems.core.starter_preset import StarterPresetSystem
                anchor = starter_confirm_tile if starter_confirm_tile is not None else (m_gx, m_gy)
                zones, valid = StarterPresetSystem.get_anchor_preview(
                    pending_starter_id, anchor,
                    building_manager, permit_manager, furniture_manager)
                fill_col = (34, 197, 94, 70) if valid else (239, 68, 68, 70)
                edge_col = (34, 197, 94) if valid else (239, 68, 68)
                for zname, (zx, zy, zw, zh) in zones.items():
                    sx1, sy1 = camera.world_to_screen(zx * TILE_SIZE, zy * TILE_SIZE)
                    sx2, sy2 = camera.world_to_screen((zx + zw) * TILE_SIZE, (zy + zh) * TILE_SIZE)
                    wpx, hpx = sx2 - sx1, sy2 - sy1
                    ghost = pygame.Surface((max(1, wpx), max(1, hpx)), pygame.SRCALPHA)
                    ghost.fill(fill_col)
                    screen.blit(ghost, (sx1, sy1))
                    pygame.draw.rect(screen, edge_col, (sx1, sy1, wpx, hpx), 2)
                    zlabel = zname[5:].capitalize() if zname.startswith("prop_") else zname.capitalize()
                    zl = font_badge.render(zlabel, True, edge_col)
                    screen.blit(zl, (sx1 + 3, sy1 + 3))

                hint = font_body.render(
                    "Click a location for your starter village — LMB confirm, RMB/ESC cancel",
                    True, (226, 232, 240))
                screen.blit(hint, hint.get_rect(center=(screen_w // 2, 24)))

                if starter_confirm_tile is not None:
                    dlg_w, dlg_h = 340, 110
                    dlg = pygame.Rect(screen_w // 2 - dlg_w // 2, screen.get_height() // 2 - dlg_h // 2, dlg_w, dlg_h)
                    pygame.draw.rect(screen, COLOR_MODAL_BG, dlg, border_radius=10)
                    pygame.draw.rect(screen, COLOR_MODAL_BORDER, dlg, width=2, border_radius=10)
                    q = font_card.render("Place starter village here?", True, COLOR_TEXT_TITLE)
                    screen.blit(q, (dlg.centerx - q.get_width() // 2, dlg.y + 16))
                    bw, bh = 110, 34
                    starter_done_btn_rect = pygame.Rect(dlg.centerx - bw - 8, dlg.bottom - bh - 14, bw, bh)
                    starter_cancel_btn_rect = pygame.Rect(dlg.centerx + 8, dlg.bottom - bh - 14, bw, bh)
                    d_hov = starter_done_btn_rect.collidepoint(pygame.mouse.get_pos())
                    pygame.draw.rect(screen, (16, 185, 129) if d_hov else (5, 150, 105), starter_done_btn_rect, border_radius=6)
                    dt = font_btn.render("Done", True, (255, 255, 255))
                    screen.blit(dt, dt.get_rect(center=starter_done_btn_rect.center))
                    c_hov = starter_cancel_btn_rect.collidepoint(pygame.mouse.get_pos())
                    pygame.draw.rect(screen, (239, 68, 68) if c_hov else (185, 28, 28), starter_cancel_btn_rect, border_radius=6)
                    ct = font_btn.render("Cancel", True, (255, 255, 255))
                    screen.blit(ct, ct.get_rect(center=starter_cancel_btn_rect.center))

            # 12. Speed Control HUD (Bottom Right)
            speed_controller.draw(screen)

            # 13. Settings Modal Dialog (On top if open)
            settings_modal.draw(screen, day_cycle, is_ingame=True)

            # The workbench catalogue is the topmost modal when opened from the map.
            builder_catalog_modal.draw(screen, building_manager, villager_manager)

            # 14. Save / Load Modal Dialog (Topmost overlay)
            save_modal.draw(screen)

            # 15. World Map Overlay (M) - fullscreen, covers everything
            map_overlay.draw(
                screen, player, permit_manager, building_manager, furniture_manager,
                villager_manager, servant_manager, stockpile_manager,
            )

        pygame.display.flip()

        if profile_enabled:
            profile_elapsed += real_dt
            profile_frame_count += 1
            profile_frame_ms += (perf_counter() - profile_frame_start) * 1000.0
            report_interval = max(0.1, SIMULATION_PROFILE_REPORT_SECONDS)
            if profile_elapsed >= report_interval:
                frame_ms = profile_frame_ms / max(1, profile_frame_count)
                simulation_ms = profile_simulation_ms / max(1, profile_frame_count)
                path_stats = building_manager.pathfinder.get_performance_stats(reset=True)
                population = len(villager_manager.get_all_villagers())
                print(
                    f"[perf] pop={population} frame={frame_ms:.2f}ms "
                    f"simulation={simulation_ms:.2f}ms "
                    f"AI ticks={villager_manager.ai_updates_since_profile + servant_manager.ai_updates_since_profile} "
                    f"paths={path_stats['queries']} cache_hits={path_stats['cache_hits']} "
                    f"A*_nodes={path_stats['astar_nodes']}"
                )
                villager_manager.ai_updates_since_profile = 0
                servant_manager.ai_updates_since_profile = 0
                profile_elapsed = 0.0
                profile_frame_count = 0
                profile_frame_ms = 0.0
                profile_simulation_ms = 0.0

    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()
