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
import pygame
from game.config import (
    WINDOW_TITLE,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    FPS,
    TILE_SIZE,
    DEFAULT_RESOURCES,
    DEFAULT_STARTER_TOOLS,
    BUILDING_TYPES,
    PERMIT_TYPES,
    FURNITURE_TYPES,
    COST_PER_BLOCK_WOOD,
    COST_PER_BLOCK_STONE,
    PATH_TOGGLE_BTN_WIDTH,
    PATH_TOGGLE_BTN_HEIGHT,
    COLOR_PATH_TOGGLE_ON,
    COLOR_PATH_TOGGLE_OFF,
    COLOR_PATH_TOGGLE_BORDER
)
from game.camera import Camera
from game.player import Player
from game.world import World
from game.world.pathfinding import draw_ai_paths
from game.menu import MainMenu
from game.hud import ResourceHUD
from game.buildings import BuildingManager
from game.permits import PermitManager, get_exterior_edges_for_tile
from game.stockpile import StockpileManager
from game.servants import ServantManager
from game.villagers import VillagerManager
from game.furniture import FurnitureManager
from game.ui_raport import RaportUI
from game.speed_control import SpeedController
from game.day_cycle import DayCycleSystem
from game.settings import SettingsModal
from game.schedule import ScheduleManager
from game.save_modal import SaveLoadModal
from game.save_system import save_to_slot, load_from_slot

STATE_MENU = "menu"
STATE_PLAYING = "playing"

def get_rect_tiles(start_pt, cur_pt):
    """Mengembalikan set koordinat tile (gx, gy) di dalam bounding box dua titik"""
    gx = min(start_pt[0], cur_pt[0])
    gy = min(start_pt[1], cur_pt[1])
    tw = abs(cur_pt[0] - start_pt[0]) + 1
    th = abs(cur_pt[1] - start_pt[1]) + 1
    return {(gx + c, gy + r) for c in range(tw) for r in range(th)}

def main():
    pygame.init()

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption(WINDOW_TITLE)

    clock = pygame.time.Clock()
    font_hud = pygame.font.SysFont("Segoe UI", 12, bold=True)
    font_card = pygame.font.SysFont("Segoe UI", 13, bold=True)
    font_btn = pygame.font.SysFont("Segoe UI", 12, bold=True)
    font_badge = pygame.font.SysFont("Segoe UI", 10, bold=True)

    # Inisialisasi Game Objects, Menu, Resources & Building System
    current_state = STATE_MENU
    menu = MainMenu()
    camera = Camera(WINDOW_WIDTH, WINDOW_HEIGHT)
    world = World(tile_size=TILE_SIZE)
    resource_hud = ResourceHUD()
    raport_ui = RaportUI()
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
    planned_door_tile = None
    planned_door_side = "bottom"
    building_drag_start = None
    building_erase_start = None
    planning_furniture_type = None
    selected_furniture = None
    moving_furniture = None

    furn_menu_rect = pygame.Rect(0, 0, 270, 140)
    btn_furn_move_rect = pygame.Rect(0, 0, 112, 30)
    btn_furn_destroy_rect = pygame.Rect(0, 0, 112, 30)
    btn_furn_close_rect = pygame.Rect(0, 0, 22, 22)

    show_debug_paths = True
    btn_path_toggle_rect = pygame.Rect(0, 0, PATH_TOGGLE_BTN_WIDTH, PATH_TOGGLE_BTN_HEIGHT)

    def start_fresh_game(day_length_index=None):
        nonlocal player, resources, building_manager, permit_manager, stockpile_manager
        nonlocal servant_manager, villager_manager, furniture_manager, day_cycle, schedule_manager
        nonlocal planning_mode, planning_permit_type, planning_building_type, planning_furniture_type
        nonlocal editing_permit_id, original_permit_tiles, selected_furniture, moving_furniture

        player = Player(0.0, 0.0)
        camera.x = 0.0
        camera.y = 0.0
        camera.target_x = 0.0
        camera.target_y = 0.0
        camera.zoom = 1.0
        resources = dict(DEFAULT_RESOURCES)
        building_manager = BuildingManager()
        permit_manager = PermitManager()
        stockpile_manager = StockpileManager()
        stockpile_manager.initialize_starter_stockpile(DEFAULT_RESOURCES, permit_manager, DEFAULT_STARTER_TOOLS)
        servant_manager = ServantManager()
        villager_manager = VillagerManager()
        furniture_manager = FurnitureManager()
        day_cycle = DayCycleSystem()
        if day_length_index is not None:
            day_cycle.set_day_length_index(day_length_index)
        schedule_manager = ScheduleManager()
        raport_ui.close()
        settings_modal.close()
        save_modal.close()
        planning_mode = "NONE"
        planning_permit_type = None
        planning_building_type = None
        planning_furniture_type = None
        editing_permit_id = None
        selected_furniture = None
        moving_furniture = None
        original_permit_tiles.clear()

    start_fresh_game()

    # Floating Bottom Bar Action Buttons
    btn_confirm_rect = pygame.Rect(0, 0, 150, 36)
    btn_clear_rect = pygame.Rect(0, 0, 90, 36)
    btn_cancel_rect = pygame.Rect(0, 0, 110, 36)
    btn_door_mode_rect = pygame.Rect(0, 0, 130, 36)

    running = True
    while running:
        real_dt = min(clock.tick(FPS) / 1000.0, 0.1)
        game_dt = speed_controller.get_game_dt(real_dt)
        if current_state == STATE_PLAYING and (settings_modal.is_open or save_modal.is_open):
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
                        slot_id = int(save_action.split("_")[-1])
                        success, msg = load_from_slot(slot_id, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager)
                        if success:
                            save_modal.close()
                            settings_modal.close()
                            raport_ui.close()
                            planning_mode = "NONE"
                            selected_furniture = None
                            moving_furniture = None
                            camera.target_x = player.x
                            camera.target_y = player.y
                            camera.x = player.x
                            camera.y = player.y
                            current_state = STATE_PLAYING
                        else:
                            save_modal.refresh_slots(f"Error: {msg}")
                    continue

                if settings_modal.is_open:
                    settings_modal.handle_event(event, day_cycle, is_ingame=False)
                    continue

                action = menu.handle_event(event)
                if action and action.startswith("start_game_"):
                    day_idx = int(action.split("_")[-1])
                    start_fresh_game(day_length_index=day_idx)
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
                        if save_action.startswith("save_slot_"):
                            slot_id = int(save_action.split("_")[-1])
                            success, msg = save_to_slot(slot_id, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager)
                            save_modal.refresh_slots(msg if success else f"Error: {msg}")
                        elif save_action.startswith("load_slot_"):
                            slot_id = int(save_action.split("_")[-1])
                            success, msg = load_from_slot(slot_id, day_cycle, resources, player, permit_manager, building_manager, stockpile_manager, furniture_manager, villager_manager, servant_manager, schedule_manager)
                            if success:
                                save_modal.close()
                                settings_modal.close()
                                raport_ui.close()
                                planning_mode = "NONE"
                                selected_furniture = None
                                moving_furniture = None
                                camera.target_x = player.x
                                camera.target_y = player.y
                                camera.x = player.x
                                camera.y = player.y
                            else:
                                save_modal.refresh_slots(f"Error: {msg}")
                    continue

                s_action = settings_modal.handle_event(event, day_cycle, is_ingame=True)
                if s_action == "unpause_game":
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

                speed_action = speed_controller.handle_event(event)
                if speed_action is not None:
                    continue

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if not raport_ui.is_open and btn_path_toggle_rect.collidepoint(event.pos):
                        show_debug_paths = not show_debug_paths
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
                        elif event.key == pygame.K_RETURN:
                            if is_valid_build:
                                building_manager.start_construction(
                                    planning_building_type, planning_building_tiles,
                                    planned_door_tile, planned_door_side, permit_manager
                                )
                                planning_mode = "NONE"
                                planning_building_tiles.clear()
                                planned_door_tile = None

                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        # UI button checks
                        if btn_confirm_rect.collidepoint(event.pos):
                            if is_valid_build:
                                building_manager.start_construction(
                                    planning_building_type, planning_building_tiles,
                                    planned_door_tile, planned_door_side, permit_manager
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
                            elif planning_building_type == "well":
                                # Tempatkan footprint 2x2 secara instan pada tile mouse
                                planning_building_tiles = {(m_gx, m_gy), (m_gx + 1, m_gy), (m_gx, m_gy + 1), (m_gx + 1, m_gy + 1)}
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
                # 3. FURNITURE PLANNING MODE
                # -------------------------------------------------------------
                elif planning_mode == "FURNITURE":
                    f_cfg = FURNITURE_TYPES.get(planning_furniture_type, FURNITURE_TYPES["household_storage"])
                    target_permit = permit_manager.get_permit_at(m_gx, m_gy)
                    b_at = building_manager.get_building_at(m_gx, m_gy)
                    can_afford = (resources.get("Wood", 0) >= f_cfg.get("cost_wood", 0))
                    is_occupied = (furniture_manager.get_furniture_at(m_gx, m_gy) is not None)
                    is_inside_house = (b_at is not None and not getattr(b_at, "is_solid", False) and getattr(b_at, "building_type", "") != "well" and (m_gx, m_gy) != getattr(b_at, "door_pos", None))
                    is_valid_place = (target_permit is not None or is_inside_house) and can_afford and not is_occupied

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE or event.key == pygame.K_BACKSPACE:
                            planning_mode = "NONE"
                            planning_furniture_type = None
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        if btn_cancel_rect.collidepoint(event.pos) or event.button == 3:
                            planning_mode = "NONE"
                            planning_furniture_type = None
                        elif event.button == 1:
                            if is_valid_place:
                                f_obj, msg = furniture_manager.add_furniture(
                                    planning_furniture_type, m_gx, m_gy,
                                    permit_manager, villager_manager, resources
                                )
                                planning_mode = "NONE"
                                planning_furniture_type = None

                # -------------------------------------------------------------
                # 3.5. MOVE FURNITURE PLANNING MODE
                # -------------------------------------------------------------
                elif planning_mode == "MOVE_FURNITURE" and moving_furniture:
                    target_permit = permit_manager.get_permit_at(m_gx, m_gy)
                    b_at = building_manager.get_building_at(m_gx, m_gy)
                    other_f = furniture_manager.get_furniture_at(m_gx, m_gy)
                    is_occupied = (other_f is not None and other_f.id != moving_furniture.id and not other_f.is_dropped)

                    is_blocked = False
                    if b_at is not None:
                        if getattr(b_at, "is_solid", False) or getattr(b_at, "building_type", "") == "well" or not getattr(b_at, "door_pos", None):
                            is_blocked = True
                        elif (m_gx, m_gy) == getattr(b_at, "door_pos", None):
                            is_blocked = True

                    is_valid_dest = not is_blocked and not is_occupied

                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE or event.key == pygame.K_BACKSPACE:
                            planning_mode = "NONE"
                            moving_furniture = None
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
                # 4. RAPORT MODAL OPEN
                # -------------------------------------------------------------
                elif raport_ui.is_open:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        raport_ui.is_open = False
                    else:
                        action = raport_ui.handle_event(event, building_manager, permit_manager, resources, servant_manager, villager_manager, schedule_manager=schedule_manager, day_cycle=day_cycle, stockpile_manager=stockpile_manager, furniture_manager=furniture_manager)
                        if raport_ui.selected_building_type is not None:
                            planning_mode = "BUILDING"
                            planning_building_type = raport_ui.selected_building_type
                            raport_ui.selected_building_type = None
                            planning_building_tiles.clear()
                            planned_door_tile = None
                            planned_door_side = "bottom"
                        elif raport_ui.selected_furniture_type is not None:
                            planning_mode = "FURNITURE"
                            planning_furniture_type = raport_ui.selected_furniture_type
                            raport_ui.selected_furniture_type = None
                        elif raport_ui.placing_permit_type is not None:
                            planning_mode = "PERMIT"
                            planning_permit_type = raport_ui.placing_permit_type
                            raport_ui.placing_permit_type = None
                            planning_permit_tiles.clear()
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
                # 5. NORMAL GAMEPLAY
                # -------------------------------------------------------------
                else:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        settings_modal.open(is_ingame=True)
                    elif event.type == pygame.MOUSEWHEEL:
                        camera.handle_zoom(event.y)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        action = raport_ui.handle_event(event, building_manager, permit_manager, resources, servant_manager, villager_manager, schedule_manager=schedule_manager, day_cycle=day_cycle, stockpile_manager=stockpile_manager, furniture_manager=furniture_manager)
                        if action == "toggle_raport":
                            continue

                        if raport_ui.selected_building_type is not None:
                            planning_mode = "BUILDING"
                            planning_building_type = raport_ui.selected_building_type
                            raport_ui.selected_building_type = None
                            planning_building_tiles.clear()
                            planned_door_tile = None
                            planned_door_side = "bottom"
                        elif raport_ui.selected_furniture_type is not None:
                            planning_mode = "FURNITURE"
                            planning_furniture_type = raport_ui.selected_furniture_type
                            raport_ui.selected_furniture_type = None
                        elif raport_ui.placing_permit_type is not None:
                            planning_mode = "PERMIT"
                            planning_permit_type = raport_ui.placing_permit_type
                            raport_ui.placing_permit_type = None
                            planning_permit_tiles.clear()
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
                            # 0A. Klik pada Tombol di Menu Konteks Furniture jika sedang terbuka
                            if selected_furniture is not None:
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
                                elif btn_furn_close_rect and btn_furn_close_rect.collidepoint(event.pos):
                                    selected_furniture = None
                                    continue

                            # 0B. Cek apakah pemain mengklik furniture fisik di peta (INSTALLED maupun UNINSTALLED)
                            clicked_f = furniture_manager.get_furniture_at(m_gx, m_gy)
                            if clicked_f:
                                selected_furniture = clicked_f
                                continue
                            else:
                                if selected_furniture is not None and furn_menu_rect and not furn_menu_rect.collidepoint(event.pos):
                                    selected_furniture = None

                            # 0C. Cek apakah pemain mengklik tumpukan barang / alat di tanah (Dropped Item Stack)
                            clicked_stack = stockpile_manager.get_stack_at(m_gx, m_gy) if stockpile_manager else None
                            if clicked_stack:
                                selected_furniture = None
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
                                            free_servant.state = "FETCH_RESOURCE"
                                            free_servant.target_stack = clicked_stack
                                            free_servant.say(f"Hauling {clicked_stack.resource_type} to storage, Sire!", duration=2.5)
                                continue

                            # 1. Cek apakah pemain mengklik bangunan fisik di peta
                            clicked_b = building_manager.get_building_at(m_gx, m_gy)
                            if clicked_b:
                                selected_furniture = None
                                raport_ui.is_open = True
                                raport_ui.active_tab = 0  # Tab Buildings
                                raport_ui.selected_building_inspect = clicked_b
                                continue

                            # 2. Cek apakah pemain mengklik surat tanah / permit di peta (empty atau occupied)
                            clicked_p = permit_manager.get_permit_at(m_gx, m_gy)
                            if clicked_p:
                                selected_furniture = None
                                raport_ui.is_open = True
                                raport_ui.active_tab = 1  # Tab Area Permits
                                raport_ui.selected_permit_inspect_id = clicked_p.id
                                continue

        # Update Game Logic
        if current_state == STATE_MENU:
            menu.draw(screen)
            settings_modal.draw(screen, day_cycle, is_ingame=False)
            save_modal.draw(screen)
        elif current_state == STATE_PLAYING:
            days_passed = day_cycle.update(game_dt)
            if days_passed > 0:
                for p in permit_manager.permits:
                    p.reset_daily_watering()

            day_dt = game_dt / max(1.0, day_cycle.day_length_seconds)
            for p in permit_manager.permits:
                p.update_growth(day_dt)

            # Substep physics/entities so high speed multiplier (Fast 2x, Very Fast 4x) never tunnels through walls
            MAX_PHYSICS_SUB_DT = 0.02  # Maximum 20ms per physics integration step
            sub_time = game_dt
            is_modal_open = raport_ui.is_open or settings_modal.is_open or save_modal.is_open
            keys = pygame.key.get_pressed() if not is_modal_open else None

            while sub_time > 0.0:
                step_dt = min(sub_time, MAX_PHYSICS_SUB_DT)
                if not is_modal_open:
                    player.handle_input(keys, step_dt, building_manager, TILE_SIZE)
                building_manager.update(step_dt)
                servant_manager.update(step_dt, building_manager, permit_manager, stockpile_manager, resources, player, furniture_manager=furniture_manager, villager_manager=villager_manager)
                villager_manager.update(step_dt, permit_manager, building_manager, servant_manager.servants, player, stockpile_manager=stockpile_manager, furniture_manager=furniture_manager, day_cycle=day_cycle, schedule_manager=schedule_manager)
                sub_time -= step_dt

            camera.follow(player)

            # 1. World & Ground
            world.draw(screen, camera)

            # 2. Area Permits (Fixed, Permanent Boundaries)
            permit_manager.draw(screen, camera, TILE_SIZE, building_manager)

            # 3. Stockpile Stacks
            stockpile_manager.draw(screen, camera, TILE_SIZE, permit_manager)

            # 4. Buildings & Construction Sites
            building_manager.draw(screen, camera, TILE_SIZE)

            # 4.5. Household Furniture (Chests & Storages)
            furniture_manager.draw(screen, camera, TILE_SIZE)

            # 5. Characters (Villagers, Servants & Player)
            villager_manager.draw(screen, camera)
            servant_manager.draw(screen, camera)
            player.draw(screen, camera)

            # 5.5. AI Predetermined Path Lines & Directional Arrow Trails
            draw_ai_paths(screen, camera, villagers=villager_manager.get_all_villagers(), servants=servant_manager.servants, show_lines=show_debug_paths)

            # 6. Ambient Day & Night Lighting Overlay
            ambient_surf = day_cycle.get_ambient_overlay(screen.get_width(), screen.get_height())
            if ambient_surf:
                screen.blit(ambient_surf, (0, 0))

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

                # B. Render Door Marker
                if planned_door_tile and planned_door_tile in planning_building_tiles:
                    dsx, dsy = camera.world_to_screen(planned_door_tile[0] * TILE_SIZE, planned_door_tile[1] * TILE_SIZE)
                    door_box = pygame.Rect(dsx + 4, dsy + 4, scaled_t - 8, scaled_t - 8)
                    pygame.draw.rect(screen, (234, 179, 8, 200), door_box, border_radius=4)
                    d_lbl = font_badge.render(f"DOOR ({planned_door_side.upper()})", True, (0, 0, 0))
                    screen.blit(d_lbl, (door_box.centerx - d_lbl.get_width() // 2, door_box.centery - d_lbl.get_height() // 2))

                # C. Well Hover Preview (when 0 tiles selected)
                if planning_building_type == "well" and not planning_building_tiles and not building_drag_start:
                    well_box = {(m_gx, m_gy), (m_gx + 1, m_gy), (m_gx, m_gy + 1), (m_gx + 1, m_gy + 1)}
                    can_fit, _ = permit_manager.find_matching_permit_for_tiles("well", well_box, building_manager, furniture_manager=furniture_manager)
                    fit_tint = (34, 197, 94, 100) if can_fit else (239, 68, 68, 100)
                    for (gx, gy) in well_box:
                        sx, sy = camera.world_to_screen(gx * TILE_SIZE, gy * TILE_SIZE)
                        t_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                        t_surf.fill(fit_tint)
                        screen.blit(t_surf, (sx, sy))
                        pygame.draw.rect(screen, (34, 197, 94) if can_fit else (239, 68, 68), (sx, sy, scaled_t, scaled_t), width=1)

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
                if b_cfg.get("fixed_tiles_count") and len(planning_building_tiles) > 0 and len(planning_building_tiles) != b_cfg["fixed_tiles_count"]:
                    status_msg = f"Must be exactly {b_cfg['fixed_tiles_count']} tiles (2x2)"
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
                tiles_label = f"Fixed: {b_cfg['fixed_tiles_count']} Tiles (2x2)" if b_cfg.get("fixed_tiles_count") else f"Tiles: {len(planning_building_tiles)}"
                info_txt = f"Design {b_cfg['name']} | {tiles_label} | Cost: {cost_w} Wood, {cost_s} Stone"
                screen.blit(font_card.render(info_txt, True, (56, 189, 248)), (bar_x + 16, bar_y + 10))

                # Status & Door info
                if not b_cfg.get("has_door", True):
                    door_str = "Solid Structure (Impenetrable)"
                    help_str = "(Click to place 2x2 Well)" if planning_building_type == "well" else "(Drag to place)"
                else:
                    door_str = f"Door: {planned_door_tile} [{planned_door_side}]" if planned_door_tile else "Click any exterior wall tile to place Door"
                    help_str = "(Drag to expand, Right-Click to erase)"
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
                screen.blit(font_btn.render("BUILD", True, (255, 255, 255)), (btn_confirm_rect.x + 46, btn_confirm_rect.y + 8))

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
                fsx, fsy = camera.world_to_screen(m_gx * TILE_SIZE, m_gy * TILE_SIZE)

                target_permit = permit_manager.get_permit_at(m_gx, m_gy)
                can_afford = (resources.get("Wood", 0) >= f_cfg.get("cost_wood", 0))
                is_occupied = (furniture_manager.get_furniture_at(m_gx, m_gy) is not None)
                is_valid_place = (target_permit is not None) and can_afford and not is_occupied

                # Ghost Preview at Mouse Tile
                f_surf = pygame.Surface((scaled_t, scaled_t), pygame.SRCALPHA)
                tile_tint = (34, 197, 94, 120) if is_valid_place else (239, 68, 68, 120)
                f_surf.fill(tile_tint)
                screen.blit(f_surf, (fsx, fsy))
                pygame.draw.rect(screen, (34, 197, 94) if is_valid_place else (239, 68, 68), (fsx, fsy, scaled_t, scaled_t), width=2)

                # Floating Bottom Bar
                bar_w = 640
                bar_h = 86
                bar_x = (screen.get_width() - bar_w) // 2
                bar_y = screen.get_height() - bar_h - 14

                bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
                pygame.draw.rect(bar_surf, (15, 23, 42, 245), (0, 0, bar_w, bar_h), border_radius=10)
                pygame.draw.rect(bar_surf, (71, 85, 105), (0, 0, bar_w, bar_h), width=2, border_radius=10)
                screen.blit(bar_surf, (bar_x, bar_y))

                info_txt = f"Place {f_cfg['name']} | Cost: {f_cfg['cost_wood']} Wood"
                screen.blit(font_card.render(info_txt, True, (250, 204, 21)), (bar_x + 16, bar_y + 10))

                if not target_permit:
                    stat_msg = "Cannot place: Must be placed inside an issued Permit lot or tenant house!"
                elif is_occupied:
                    stat_msg = "Cannot place: Tile already has furniture!"
                elif not can_afford:
                    stat_msg = f"Cannot place: Need {f_cfg['cost_wood']} Wood!"
                else:
                    owner_family = next((fam for fam in villager_manager.families if fam.assigned_permit_id == target_permit.id), None)
                    fam_str = f"Will belong to The {owner_family.surname} Family" if owner_family else "Unassigned lot"
                    stat_msg = f"Ready to place! (Left-Click to build, {fam_str})"

                stat_col = (34, 197, 94) if is_valid_place else (239, 68, 68)
                screen.blit(font_hud.render(stat_msg, True, stat_col), (bar_x + 16, bar_y + 32))

                btn_cancel_rect.x = bar_x + bar_w - 126
                btn_cancel_rect.y = bar_y + 25
                pygame.draw.rect(screen, (220, 38, 38), btn_cancel_rect, border_radius=6)
                screen.blit(font_btn.render("CANCEL", True, (255, 255, 255)), (btn_cancel_rect.x + 28, btn_cancel_rect.y + 8))

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
            # 7.7. OVERLAYS: SELECTED FURNITURE CONTEXT MENU / ACTION POPUP
            # -------------------------------------------------------------
            if selected_furniture is not None and planning_mode == "NONE" and not raport_ui.is_open:
                scaled_t = int(TILE_SIZE * camera.zoom)
                fsx, fsy = camera.world_to_screen(selected_furniture.grid_x * TILE_SIZE, selected_furniture.grid_y * TILE_SIZE)

                # Draw selection box on the furniture
                pygame.draw.rect(screen, (250, 204, 21), (fsx - 2, fsy - 2, scaled_t + 4, scaled_t + 4), width=2, border_radius=5)

                # Modal popup positioned conveniently above/below the tile
                cw, ch = 270, 140
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
                elif selected_furniture.furniture_type == "bed":
                    det_txt = f"Assigned: {selected_furniture.assigned_villager_id or 'Vacant Bed'}"
                else:
                    det_txt = f"Location: ({selected_furniture.grid_x}, {selected_furniture.grid_y})"
                screen.blit(font_hud.render(det_txt, True, (56, 189, 248)), (cx + 14, cy + 54))

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

            # 8. Clock & Calendar HUD (Top Left)
            day_cycle.draw_hud(screen)

            # 9. In-Game Settings Button
            settings_modal.draw_hud_button(screen)

            # 10. Resources HUD
            resource_hud.draw(screen, resources)

            # 10.5. AI Paths Toggle Button (Right Side, below Resources HUD)
            screen_w = screen.get_width()
            res_card_h = resource_hud.header_height + (len(resources) * resource_hud.row_height) + resource_hud.padding
            btn_path_toggle_rect.x = screen_w - PATH_TOGGLE_BTN_WIDTH - resource_hud.margin
            btn_path_toggle_rect.y = resource_hud.margin + res_card_h + 10

            m_pos = pygame.mouse.get_pos()
            btn_hover = btn_path_toggle_rect.collidepoint(m_pos)
            btn_bg = COLOR_PATH_TOGGLE_ON if show_debug_paths else COLOR_PATH_TOGGLE_OFF
            if btn_hover:
                btn_bg = tuple(min(255, c + 25) for c in btn_bg)
            pygame.draw.rect(screen, btn_bg, btn_path_toggle_rect, border_radius=6)
            pygame.draw.rect(screen, COLOR_PATH_TOGGLE_BORDER, btn_path_toggle_rect, width=1, border_radius=6)

            toggle_status = "ON" if show_debug_paths else "OFF"
            btn_text = f"AI Path Lines: [{toggle_status}]"
            btn_surf = font_btn.render(btn_text, True, (255, 255, 255))
            txt_rect = btn_surf.get_rect(center=btn_path_toggle_rect.center)
            screen.blit(btn_surf, txt_rect)

            # 11. Left Raport Button & Modal
            raport_ui.draw(screen, building_manager, permit_manager, resources, servant_manager, villager_manager, schedule_manager=schedule_manager, day_cycle=day_cycle, furniture_manager=furniture_manager, stockpile_manager=stockpile_manager)

            # 12. Speed Control HUD (Bottom Right)
            speed_controller.draw(screen)

            # 13. Settings Modal Dialog (On top if open)
            settings_modal.draw(screen, day_cycle, is_ingame=True)

            # 14. Save / Load Modal Dialog (Topmost overlay)
            save_modal.draw(screen)

        pygame.display.flip()

    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()
