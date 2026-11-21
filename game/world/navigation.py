"""Small obstacle-aware navigation helpers for game actors."""

import math

from game.config import PATH_TARGET_FALLBACK_OFFSETS, TILE_SIZE


def distance_to_object(target, x, y, tile_size=TILE_SIZE):
    """Return the distance from a world point to an object's footprint."""
    tiles = getattr(target, "tiles", None)
    if tiles:
        return min(
            math.hypot(
                max(gx * tile_size - x, 0.0, x - (gx + 1) * tile_size),
                max(gy * tile_size - y, 0.0, y - (gy + 1) * tile_size),
            )
            for gx, gy in tiles
        )

    grid_x = getattr(target, "grid_x", None)
    grid_y = getattr(target, "grid_y", None)
    if grid_x is not None and grid_y is not None:
        dimensions = getattr(target, "footprint_dimensions", None)
        if dimensions is None:
            config = getattr(target, "type_cfg", {})
            if not isinstance(config, dict):
                config = {}
            dimensions = (
                max(1, int(config.get("width_tiles", 1))),
                max(1, int(config.get("height_tiles", 1))),
            )
        width, height = dimensions
        return math.hypot(
            max(grid_x * tile_size - x, 0.0, x - (grid_x + width) * tile_size),
            max(grid_y * tile_size - y, 0.0, y - (grid_y + height) * tile_size),
        )

    position = None
    for getter_name in ("get_world_pos", "get_center_world"):
        getter = getattr(target, getter_name, None)
        if callable(getter):
            position = getter(tile_size)
            break
    if position is None and hasattr(target, "x") and hasattr(target, "y"):
        position = (target.x, target.y)
    if position is None:
        return None

    center_distance = math.hypot(position[0] - x, position[1] - y)
    return max(0.0, center_distance - max(0.0, float(getattr(target, "radius", 0.0))))


def interaction_arrival_distance(target, target_x, target_y, arrival_dist, tile_size=TILE_SIZE):
    """Cap arrival so the actor cannot stop more than one tile from an object."""
    object_distance = distance_to_object(target, target_x, target_y, tile_size)
    if object_distance is None:
        return arrival_dist
    return min(float(arrival_dist), max(0.0, tile_size - object_distance))


def find_navigation_path(start, target, building_manager=None, furniture_manager=None,
                         tile_size=TILE_SIZE, avoid_tiles=None):
    """Find a walkable route, approaching blocked building targets from any open side."""
    if not building_manager:
        return [target]

    avoided = set(avoid_tiles or ())
    target_tile = (int(math.floor(target[0] / tile_size)), int(math.floor(target[1] / tile_size)))
    if avoided:
        route = building_manager.find_path(start, target, tile_size, avoid_tiles=avoided)
    else:
        route = building_manager.find_path(start, target, tile_size)
    if route:
        return route

    start_tile = (int(math.floor(start[0] / tile_size)), int(math.floor(start[1] / tile_size)))
    target_building = building_manager.get_building_at(*target_tile)
    footprint = getattr(target_building, "tiles", ()) if target_building else (target_tile,)
    fallback_tiles = {
        (gx + dx, gy + dy)
        for gx, gy in footprint
        for dx, dy in PATH_TARGET_FALLBACK_OFFSETS
        if building_manager.get_building_at(gx + dx, gy + dy) is None
        and (gx + dx, gy + dy) not in avoided
    }
    fallback_tiles = sorted(
        fallback_tiles,
        key=lambda tile: (
            abs((tile[0] + 0.5) * tile_size - start[0])
            + abs((tile[1] + 0.5) * tile_size - start[1]),
            tile,
        ),
    )
    best_route = None
    best_route_length = float("inf")
    for gx, gy in fallback_tiles:
        fallback_target = ((gx + 0.5) * tile_size, (gy + 0.5) * tile_size)
        # The Manhattan distance is a lower bound on every walkable route.
        # Once it cannot beat the best route already found, later A* searches
        # are unnecessary while the nearest reachable interaction point stays exact.
        lower_bound = abs(fallback_target[0] - start[0]) + abs(fallback_target[1] - start[1])
        if lower_bound >= best_route_length:
            break
        if avoided:
            route = building_manager.find_path(
                start, fallback_target, tile_size, avoid_tiles=avoided,
            )
        else:
            route = building_manager.find_path(start, fallback_target, tile_size)
        if not route:
            continue
        route_length = math.dist(start, route[0]) + sum(
            math.dist(route[index - 1], route[index]) for index in range(1, len(route))
        )
        if route_length < best_route_length:
            best_route = route
            best_route_length = route_length
    return best_route or []


def find_nearest_target(start, candidates, get_position, building_manager=None,
                        furniture_manager=None, tile_size=TILE_SIZE):
    """Choose the closest target point; movement uses the normal obstacle-aware route."""
    best = None
    best_position = None
    best_distance = float("inf")
    for candidate in candidates:
        try:
            position = get_position(candidate)
        except (AttributeError, TypeError, ValueError):
            continue
        if not position or len(position) < 2:
            continue
        distance = math.hypot(position[0] - start[0], position[1] - start[1])
        if distance < best_distance:
            best = candidate
            best_position = position
            best_distance = distance
    return best, best_position, best_distance
