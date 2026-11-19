"""Small obstacle-aware navigation helpers for game actors."""

import math

from game.config import PATH_TARGET_FALLBACK_OFFSETS, TILE_SIZE


def find_navigation_path(start, target, building_manager=None, furniture_manager=None, tile_size=TILE_SIZE):
    """Find a walkable route, approaching blocked building targets from any open side."""
    if not building_manager:
        return [target]

    target_tile = (int(math.floor(target[0] / tile_size)), int(math.floor(target[1] / tile_size)))
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
    }
    fallback_tiles = sorted(
        fallback_tiles,
        key=lambda tile: abs(tile[0] - start_tile[0]) + abs(tile[1] - start_tile[1]),
    )
    best_route = None
    best_route_length = float("inf")
    for gx, gy in fallback_tiles:
        fallback_target = ((gx + 0.5) * tile_size, (gy + 0.5) * tile_size)
        route = building_manager.find_path(start, fallback_target, tile_size)
        if not route:
            continue
        route_length = sum(
            math.dist(route[index - 1], route[index])
            for index in range(1, len(route))
        )
        if route_length < best_route_length:
            best_route = route
            best_route_length = route_length
    return best_route or []
