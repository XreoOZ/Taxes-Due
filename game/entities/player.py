"""
Player Entity (Dummy Character)
"""

import math
import pygame
from game.render_cache import ellipse_surface
from game.config import (
    TILE_SIZE,
    PLAYER_RADIUS,
    PLAYER_SPEED,
    COLOR_PLAYER_BODY,
    COLOR_PLAYER_OUTLINE,
    COLOR_PLAYER_EYE,
    COLOR_SHADOW
)

class Player:
    def __init__(self, x=0.0, y=0.0):
        self.x = float(x)
        self.y = float(y)
        self.radius = PLAYER_RADIUS
        self.speed = PLAYER_SPEED  # pixel per detik
        self.facing_angle = 0.0  # radian
        self.walk_cycle = 0.0
        self.is_moving = False

    def handle_input(self, keys, dt, building_manager=None, tile_size=TILE_SIZE):
        dx = 0.0
        dy = 0.0

        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy -= 1.0
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy += 1.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx -= 1.0
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx += 1.0

        self.is_moving = (dx != 0.0 or dy != 0.0)

        if self.is_moving:
            # Normalisasi kecepatan diagonal agar tidak lebih cepat
            if dx != 0.0 and dy != 0.0:
                inv_mag = 1.0 / math.sqrt(2.0)
                dx *= inv_mag
                dy *= inv_mag

            # Terrain factors: forest floor slows, roads speed up.
            from game.world.natural_resources import get_natural_resources
            from game.world.roads import get_roads
            terrain_mult = (get_natural_resources().speed_factor_at(self.x, self.y, tile_size)
                            * get_roads().speed_factor_at(self.x, self.y, tile_size))

            # Continuous collision micro-stepping: cegah tunneling menembus tembok saat dt besar / speed tinggi
            total_dist = self.speed * terrain_mult * dt
            max_step_dist = 6.0
            num_steps = max(1, math.ceil(total_dist / max_step_dist))
            sub_dt = dt / num_steps

            from game.world.island import is_land_world
            for _ in range(num_steps):
                old_step_x, old_step_y = self.x, self.y
                self.x += dx * self.speed * terrain_mult * sub_dt
                self.y += dy * self.speed * terrain_mult * sub_dt

                # Island worlds: don't let the player walk onto water.
                if not is_land_world(self.x, self.y, tile_size):
                    if is_land_world(self.x, old_step_y, tile_size):
                        self.y = old_step_y
                    elif is_land_world(old_step_x, self.y, tile_size):
                        self.x = old_step_x
                    else:
                        self.x, self.y = old_step_x, old_step_y

                # Selesaikan tabrakan fisik dengan dinding bangunan (Wall Collision)
                if building_manager:
                    self.x, self.y = building_manager.resolve_collision(self.x, self.y, self.radius, tile_size, old_x=old_step_x, old_y=old_step_y)

            # Update arah hadap karakter
            self.facing_angle = math.atan2(dy, dx)

            # Update walk cycle untuk animasi bobbing
            self.walk_cycle += dt * 14.0
        else:
            self.walk_cycle = 0.0

    def draw(self, surface, camera):
        sx, sy = camera.world_to_screen(self.x, self.y)

        # Skala dimensi berdasarkan zoom kamera
        r = max(4, int(self.radius * camera.zoom))
        bob = math.sin(self.walk_cycle) * (2.5 * camera.zoom) if self.is_moving else 0.0
        char_y = sy + int(bob)

        # 1. Bayangan di tanah (Drop Shadow transparan)
        shadow_w = int(r * 1.8)
        shadow_h = max(2, int(r * 0.9))
        shadow_surf = ellipse_surface(shadow_w, shadow_h, COLOR_SHADOW)
        surface.blit(shadow_surf, (sx - shadow_w // 2, sy + int(r * 0.4)))

        # 2. Badan Karakter (Lingkaran Dummy)
        pygame.draw.circle(surface, COLOR_PLAYER_BODY, (sx, char_y), r)
        outline_w = max(1, int(3 * camera.zoom))
        pygame.draw.circle(surface, COLOR_PLAYER_OUTLINE, (sx, char_y), r, outline_w)

        # 3. Mata / Pointer Arah Hadap
        eye_dist = r * 0.55
        eye_x = sx + int(math.cos(self.facing_angle) * eye_dist)
        eye_y = char_y + int(math.sin(self.facing_angle) * eye_dist)
        eye_r = max(2, int(5 * camera.zoom))
        eye_outline_w = max(1, int(2 * camera.zoom))

        pygame.draw.circle(surface, COLOR_PLAYER_EYE, (eye_x, eye_y), eye_r)
        pygame.draw.circle(surface, COLOR_PLAYER_OUTLINE, (eye_x, eye_y), eye_r, eye_outline_w)
