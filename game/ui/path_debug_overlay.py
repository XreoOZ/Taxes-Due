"""Optional, viewport-culled visualization of active AI navigation routes."""

import math

import pygame

from game.data.config import (
    COLOR_PATH_ROUTE,
    COLOR_PATH_ROUTE_FAILED,
    COLOR_PATH_TOGGLE_BORDER,
    COLOR_PATH_TOGGLE_OFF,
    COLOR_PATH_TOGGLE_ON,
    PATH_ARROW_HEAD_LENGTH,
    PATH_ARROW_HEAD_WIDTH,
    PATH_ARROW_SPACING,
    PATH_LINE_WIDTH,
    PATH_ROUTE_WAYPOINT_RADIUS,
    PATH_TOGGLE_BTN_MARGIN,
    PATH_TOGGLE_BTN_HEIGHT,
    PATH_TOGGLE_BTN_WIDTH,
    ROUTE_STATE_FAILED,
)


class PathDebugOverlay:
    def __init__(self, enabled=True):
        self.enabled = bool(enabled)
        self.button_rect = pygame.Rect(0, 0, PATH_TOGGLE_BTN_WIDTH, PATH_TOGGLE_BTN_HEIGHT)

    def handle_event(self, event):
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.button_rect.collidepoint(event.pos)):
            self.enabled = not self.enabled
            return True
        return False

    def draw_toggle(self, surface, anchor_rect, font):
        """Place the switch beside the existing Add Item control, screen-relative."""
        x = max(0, min(anchor_rect.x, surface.get_width() - self.button_rect.width))
        y = min(anchor_rect.bottom + PATH_TOGGLE_BTN_MARGIN,
                surface.get_height() - self.button_rect.height - PATH_TOGGLE_BTN_MARGIN)
        self.button_rect.topleft = (x, max(PATH_TOGGLE_BTN_MARGIN, y))
        color = COLOR_PATH_TOGGLE_ON if self.enabled else COLOR_PATH_TOGGLE_OFF
        pygame.draw.rect(surface, color, self.button_rect, border_radius=6)
        pygame.draw.rect(surface, COLOR_PATH_TOGGLE_BORDER, self.button_rect, width=1, border_radius=6)
        label = font.render(f"AI Routes: {'ON' if self.enabled else 'OFF'}", True, (255, 255, 255))
        surface.blit(label, label.get_rect(center=self.button_rect.center))

    @staticmethod
    def _draw_arrow(surface, point, direction):
        half_length = PATH_ARROW_HEAD_LENGTH / 2.0
        half_width = PATH_ARROW_HEAD_WIDTH / 2.0
        px, py = -direction[1], direction[0]
        tip = (round(point[0] + direction[0] * half_length),
               round(point[1] + direction[1] * half_length))
        base_x = point[0] - direction[0] * half_length
        base_y = point[1] - direction[1] * half_length
        left = (round(base_x + px * half_width), round(base_y + py * half_width))
        right = (round(base_x - px * half_width), round(base_y - py * half_width))
        pygame.draw.polygon(surface, COLOR_PATH_ROUTE, (tip, left, right))

    def draw_routes(self, surface, camera, actors):
        if not self.enabled:
            return
        for actor in actors:
            if not getattr(actor, "is_alive", True):
                continue
            path = getattr(actor, "current_path", None) or []
            path_index = max(0, int(getattr(actor, "path_index", 0)))
            remaining = path[path_index:]
            if not remaining:
                target = getattr(actor, "path_target", None)
                if target and getattr(actor, "route_state", None) == ROUTE_STATE_FAILED:
                    tx, ty = target
                    if camera.is_world_rect_visible(tx - PATH_ROUTE_WAYPOINT_RADIUS,
                                                    ty - PATH_ROUTE_WAYPOINT_RADIUS,
                                                    PATH_ROUTE_WAYPOINT_RADIUS * 2,
                                                    PATH_ROUTE_WAYPOINT_RADIUS * 2):
                        sx, sy = camera.world_to_screen(tx, ty)
                        pygame.draw.circle(surface, COLOR_PATH_ROUTE_FAILED, (sx, sy),
                                           max(2, round(PATH_ROUTE_WAYPOINT_RADIUS * camera.zoom)), 2)
                continue

            points = [(float(actor.x), float(actor.y))]
            points.extend((float(point[0]), float(point[1])) for point in remaining)
            for start, end in zip(points, points[1:]):
                left, right = sorted((start[0], end[0]))
                top, bottom = sorted((start[1], end[1]))
                if not camera.is_world_rect_visible(left, top, max(1.0, right - left),
                                                    max(1.0, bottom - top)):
                    continue
                screen_start = camera.world_to_screen(*start)
                screen_end = camera.world_to_screen(*end)
                pygame.draw.line(surface, COLOR_PATH_ROUTE, screen_start, screen_end,
                                 max(1, round(PATH_LINE_WIDTH * camera.zoom)))
                dx = screen_end[0] - screen_start[0]
                dy = screen_end[1] - screen_start[1]
                length = math.hypot(dx, dy)
                if length <= 0.0:
                    continue
                direction = (dx / length, dy / length)
                spacing = max(1.0, float(PATH_ARROW_SPACING))
                offset = min(spacing / 2.0, length / 2.0)
                while offset < length:
                    point = (screen_start[0] + direction[0] * offset,
                             screen_start[1] + direction[1] * offset)
                    self._draw_arrow(surface, point, direction)
                    offset += spacing

            for waypoint in remaining:
                wx, wy = waypoint
                radius = max(2, round(PATH_ROUTE_WAYPOINT_RADIUS * camera.zoom))
                if camera.is_world_rect_visible(wx - PATH_ROUTE_WAYPOINT_RADIUS,
                                                wy - PATH_ROUTE_WAYPOINT_RADIUS,
                                                PATH_ROUTE_WAYPOINT_RADIUS * 2,
                                                PATH_ROUTE_WAYPOINT_RADIUS * 2):
                    pygame.draw.circle(surface, COLOR_PATH_ROUTE, camera.world_to_screen(wx, wy), radius)
