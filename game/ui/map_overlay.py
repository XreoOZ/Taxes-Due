"""Fullscreen world map overlay (toggle with M).

View-only: the player stays centered and WASD movement keeps working while
the map is open. Shows mirrored world positions for structures, permits,
furniture, villagers/servants, and stockpiles, each behind a toggleable layer.
"""
import pygame

from game.data.config import (
    BUILDING_TYPES,
    DEDICATED_JOBS,
    FURNITURE_TYPES,
    PERMIT_TYPES,
    TILE_SIZE,
    MAP_OVERLAY_BG,
    MAP_OVERLAY_MAP_BG,
    MAP_OVERLAY_GRID_COLOR,
    MAP_OVERLAY_BORDER,
    MAP_OVERLAY_TEXT,
    MAP_OVERLAY_TEXT_DIM,
    MAP_OVERLAY_TITLE_COLOR,
    MAP_OVERLAY_LAYER_ON_BG,
    MAP_OVERLAY_LAYER_OFF_BG,
    MAP_OVERLAY_LAYER_ON_BORDER,
    MAP_OVERLAY_LAYER_OFF_BORDER,
    MAP_OVERLAY_PLAYER_COLOR,
    MAP_OVERLAY_SERVANT_COLOR,
    MAP_OVERLAY_VILLAGER_FALLBACK,
    MAP_OVERLAY_CONSTRUCTION_COLOR,
    MAP_OVERLAY_RESOURCE_COLORS,
    MAP_OVERLAY_VIEW_RADIUS_TILES,
    MAP_OVERLAY_MARGIN,
    MAP_OVERLAY_TOP_BAR_HEIGHT,
    MAP_OVERLAY_BTN_HEIGHT,
    MAP_OVERLAY_BTN_GAP,
    MAP_OVERLAY_BTN_PADDING_X,
    MAP_OVERLAY_FONT_SIZE_TITLE,
    MAP_OVERLAY_FONT_SIZE_BTN,
    MAP_OVERLAY_FONT_SIZE_HINT,
    MAP_OVERLAY_DOT_RADIUS_VILLAGER,
    MAP_OVERLAY_DOT_RADIUS_SERVANT,
    MAP_OVERLAY_DOT_RADIUS_RESOURCE,
    MAP_OVERLAY_DOT_RADIUS_PLAYER,
    MAP_OVERLAY_ICON_MIN_PX,
    MAP_OVERLAY_GRID_STEP_TILES,
    MAP_OVERLAY_LAYERS,
    MAP_OVERLAY_ZOOM_MIN,
    MAP_OVERLAY_ZOOM_MAX,
    MAP_OVERLAY_ZOOM_STEP,
)


class MapOverlay:
    """Fullscreen map overlay centered on the player."""

    def __init__(self):
        self.is_open = False
        self.zoom = 1.0
        self.layers = {key: True for key in MAP_OVERLAY_LAYERS}
        self._button_rects = {}
        self._fonts_ready = False
        self._font_title = None
        self._font_btn = None
        self._font_hint = None

    def _ensure_fonts(self):
        if self._fonts_ready:
            return
        self._font_title = pygame.font.SysFont("Segoe UI", MAP_OVERLAY_FONT_SIZE_TITLE, bold=True)
        self._font_btn = pygame.font.SysFont("Segoe UI", MAP_OVERLAY_FONT_SIZE_BTN, bold=True)
        self._font_hint = pygame.font.SysFont("Segoe UI", MAP_OVERLAY_FONT_SIZE_HINT)
        self._fonts_ready = True

    def toggle(self):
        self.is_open = not self.is_open

    def open(self):
        self.is_open = True
        self.zoom = 1.0

    def close(self):
        self.is_open = False

    def handle_event(self, event):
        """Route pygame events while the map is open. Returns True if consumed."""
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_m, pygame.K_ESCAPE):
                self.close()
                return True
        elif event.type == pygame.MOUSEWHEEL:
            self.zoom = max(
                MAP_OVERLAY_ZOOM_MIN,
                min(MAP_OVERLAY_ZOOM_MAX, self.zoom - event.y * MAP_OVERLAY_ZOOM_STEP),
            )
            return True
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            for key, rect in self._button_rects.items():
                if rect.collidepoint(pos):
                    self.layers[key] = not self.layers[key]
                    return True
        return False

    # ------------------------------------------------------------------
    # Coordinate transform
    # ------------------------------------------------------------------
    def _map_area(self, screen_w, screen_h):
        """Return (area_rect, content_rect) for the map drawing region."""
        m = MAP_OVERLAY_MARGIN
        top = MAP_OVERLAY_TOP_BAR_HEIGHT + m
        area = pygame.Rect(m, top, screen_w - 2 * m, screen_h - top - m)
        return area, area

    def _world_to_map(self, wx, wy, player, content_rect, scale, origin_x, origin_y):
        return (
            int(origin_x + (wx - player.x) * scale),
            int(origin_y + (wy - player.y) * scale),
        )

    def _compute_transform(self, player, content_rect):
        """Compute scale + origin so the player is centered in content_rect."""
        radius_px = MAP_OVERLAY_VIEW_RADIUS_TILES * TILE_SIZE / self.zoom
        scale = min(
            content_rect.width / (2.0 * radius_px),
            content_rect.height / (2.0 * radius_px),
        )
        origin_x = content_rect.centerx
        origin_y = content_rect.centery
        return scale, origin_x, origin_y

    # ------------------------------------------------------------------
    # Layer drawing helpers
    # ------------------------------------------------------------------
    def _draw_permits(self, surface, permit_manager, player, cr, scale, ox, oy):
        for permit in permit_manager.permits:
            gx, gy = permit.grid_x, permit.grid_y
            tw, th = permit.tiles_w, permit.tiles_h
            if tw <= 0 or th <= 0:
                continue
            wx = gx * TILE_SIZE
            wy = gy * TILE_SIZE
            ww = tw * TILE_SIZE
            wh = th * TILE_SIZE
            x1, y1 = self._world_to_map(wx, wy, player, cr, scale, ox, oy)
            x2, y2 = self._world_to_map(wx + ww, wy + wh, player, cr, scale, ox, oy)
            rect = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
            if not cr.contains(rect):
                continue
            cfg = PERMIT_TYPES.get(permit.permit_type, {})
            fill = cfg.get("color", (100, 100, 100, 40))
            border = cfg.get("border_color", (150, 150, 150))
            pygame.draw.rect(surface, fill, rect)
            pygame.draw.rect(surface, border, rect, width=1)

    def _draw_structures(self, surface, building_manager, player, cr, scale, ox, oy):
        # Construction sites first (under finished buildings)
        for site in building_manager.construction_sites:
            gx, gy = site.grid_x, site.grid_y
            tw, th = site.tiles_w, site.tiles_h
            if tw <= 0 or th <= 0:
                continue
            wx = gx * TILE_SIZE
            wy = gy * TILE_SIZE
            ww = tw * TILE_SIZE
            wh = th * TILE_SIZE
            x1, y1 = self._world_to_map(wx, wy, player, cr, scale, ox, oy)
            x2, y2 = self._world_to_map(wx + ww, wy + wh, player, cr, scale, ox, oy)
            rect = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
            if not cr.contains(rect):
                continue
            pygame.draw.rect(surface, MAP_OVERLAY_CONSTRUCTION_COLOR, rect)
            pygame.draw.rect(surface, (251, 191, 36), rect, width=1)

        for b in building_manager.buildings:
            gx, gy = b.grid_x, b.grid_y
            tw, th = b.tiles_w, b.tiles_h
            if tw <= 0 or th <= 0:
                continue
            wx = gx * TILE_SIZE
            wy = gy * TILE_SIZE
            ww = tw * TILE_SIZE
            wh = th * TILE_SIZE
            x1, y1 = self._world_to_map(wx, wy, player, cr, scale, ox, oy)
            x2, y2 = self._world_to_map(wx + ww, wy + wh, player, cr, scale, ox, oy)
            rect = pygame.Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
            if not cr.contains(rect):
                continue
            cfg = BUILDING_TYPES.get(b.building_type, {})
            color = cfg.get("color", (100, 100, 100))
            # Ensure minimum visible size
            min_px = MAP_OVERLAY_ICON_MIN_PX
            if rect.width < min_px:
                rect.width = min_px
            if rect.height < min_px:
                rect.height = min_px
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, (30, 41, 59), rect, width=1)

    def _draw_furniture(self, surface, furniture_manager, player, cr, scale, ox, oy):
        for f in furniture_manager.furnitures:
            if getattr(f, "is_dropped", False):
                continue
            gx, gy = f.grid_x, f.grid_y
            wx = gx * TILE_SIZE
            wy = gy * TILE_SIZE
            x, y = self._world_to_map(wx, wy, player, cr, scale, ox, oy)
            if not cr.collidepoint(x, y):
                continue
            cfg = f.type_cfg if hasattr(f, "type_cfg") else FURNITURE_TYPES.get(f.furniture_type, {})
            color = cfg.get("color_body") or cfg.get("color_frame") or (160, 82, 45)
            size = max(MAP_OVERLAY_ICON_MIN_PX, int(TILE_SIZE * scale))
            rect = pygame.Rect(x, y, size, size)
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, (30, 41, 59), rect, width=1)

    def _draw_ai(self, surface, villager_manager, servant_manager, player, cr, scale, ox, oy):
        # Servants
        for s in servant_manager.servants:
            x, y = self._world_to_map(s.x, s.y, player, cr, scale, ox, oy)
            if not cr.collidepoint(x, y):
                continue
            r = MAP_OVERLAY_DOT_RADIUS_SERVANT
            pygame.draw.circle(surface, MAP_OVERLAY_SERVANT_COLOR, (x, y), r)
            pygame.draw.circle(surface, (30, 41, 59), (x, y), r, width=1)

        # Villagers
        for v in villager_manager.get_all_villagers():
            if not getattr(v, "is_alive", True):
                continue
            x, y = self._world_to_map(v.x, v.y, player, cr, scale, ox, oy)
            if not cr.collidepoint(x, y):
                continue
            job_cfg = DEDICATED_JOBS.get(v.job, {})
            color = job_cfg.get("color", MAP_OVERLAY_VILLAGER_FALLBACK)
            r = MAP_OVERLAY_DOT_RADIUS_VILLAGER
            pygame.draw.circle(surface, color, (x, y), r)
            pygame.draw.circle(surface, (30, 41, 59), (x, y), r, width=1)

    def _draw_resources(self, surface, stockpile_manager, player, cr, scale, ox, oy):
        for stack in stockpile_manager.stacks:
            gx, gy = stack.grid_x, stack.grid_y
            wx = gx * TILE_SIZE
            wy = gy * TILE_SIZE
            x, y = self._world_to_map(wx, wy, player, cr, scale, ox, oy)
            if not cr.collidepoint(x, y):
                continue
            color = MAP_OVERLAY_RESOURCE_COLORS.get(stack.resource_type, (148, 163, 184))
            r = MAP_OVERLAY_DOT_RADIUS_RESOURCE
            pygame.draw.circle(surface, color, (x, y), r)

    def _draw_player(self, surface, player, cr, scale, ox, oy):
        x, y = self._world_to_map(player.x, player.y, player, cr, scale, ox, oy)
        r = MAP_OVERLAY_DOT_RADIUS_PLAYER
        pygame.draw.circle(surface, MAP_OVERLAY_PLAYER_COLOR, (x, y), r)
        pygame.draw.circle(surface, (255, 255, 255), (x, y), r, width=2)

    # ------------------------------------------------------------------
    # Main draw
    # ------------------------------------------------------------------
    def draw(self, surface, player, permit_manager, building_manager, furniture_manager,
             villager_manager, servant_manager, stockpile_manager):
        if not self.is_open:
            return
        self._ensure_fonts()

        screen_w, screen_h = surface.get_size()
        self._button_rects.clear()

        # Background
        surface.fill(MAP_OVERLAY_BG)

        # Top bar
        bar_rect = pygame.Rect(MAP_OVERLAY_MARGIN, MAP_OVERLAY_MARGIN,
                               screen_w - 2 * MAP_OVERLAY_MARGIN,
                               MAP_OVERLAY_TOP_BAR_HEIGHT)
        pygame.draw.rect(surface, MAP_OVERLAY_MAP_BG, bar_rect, border_radius=8)
        pygame.draw.rect(surface, MAP_OVERLAY_BORDER, bar_rect, width=1, border_radius=8)

        # Title
        title = self._font_title.render("World Map", True, MAP_OVERLAY_TITLE_COLOR)
        surface.blit(title, (bar_rect.x + MAP_OVERLAY_BTN_PADDING_X, bar_rect.centery - title.get_height() // 2))

        # Layer toggle buttons
        btn_y = bar_rect.centery - MAP_OVERLAY_BTN_HEIGHT // 2
        btn_x = bar_rect.right - MAP_OVERLAY_BTN_PADDING_X
        for key in reversed(list(MAP_OVERLAY_LAYERS.keys())):
            label = MAP_OVERLAY_LAYERS[key]
            state = self.layers.get(key, True)
            btn_text = self._font_btn.render(label, True, MAP_OVERLAY_TEXT)
            btn_w = btn_text.get_width() + 2 * MAP_OVERLAY_BTN_PADDING_X
            btn_rect = pygame.Rect(btn_x - btn_w, btn_y, btn_w, MAP_OVERLAY_BTN_HEIGHT)
            self._button_rects[key] = btn_rect
            btn_x = btn_rect.x - MAP_OVERLAY_BTN_GAP

            if state:
                bg = MAP_OVERLAY_LAYER_ON_BG
                border = MAP_OVERLAY_LAYER_ON_BORDER
            else:
                bg = MAP_OVERLAY_LAYER_OFF_BG
                border = MAP_OVERLAY_LAYER_OFF_BORDER
            pygame.draw.rect(surface, bg, btn_rect, border_radius=6)
            pygame.draw.rect(surface, border, btn_rect, width=1, border_radius=6)
            surface.blit(btn_text, btn_text.get_rect(center=btn_rect.center))

        # Hint text
        hint = self._font_hint.render("M / ESC to close", True, MAP_OVERLAY_TEXT_DIM)
        surface.blit(hint, (bar_rect.right - hint.get_width() - MAP_OVERLAY_BTN_PADDING_X,
                            bar_rect.bottom + 4))

        # Map content area
        area, cr = self._map_area(screen_w, screen_h)
        pygame.draw.rect(surface, MAP_OVERLAY_MAP_BG, area, border_radius=8)
        pygame.draw.rect(surface, MAP_OVERLAY_BORDER, area, width=1, border_radius=8)

        # Clip to content rect
        old_clip = surface.get_clip()
        surface.set_clip(cr)

        # Grid
        scale, ox, oy = self._compute_transform(player, cr)
        self._draw_grid(surface, cr, player, scale, ox, oy)

        # Layers
        if self.layers.get("permits", True):
            self._draw_permits(surface, permit_manager, player, cr, scale, ox, oy)
        if self.layers.get("structures", True):
            self._draw_structures(surface, building_manager, player, cr, scale, ox, oy)
        if self.layers.get("furniture", True):
            self._draw_furniture(surface, furniture_manager, player, cr, scale, ox, oy)
        if self.layers.get("ai", True):
            self._draw_ai(surface, villager_manager, servant_manager, player, cr, scale, ox, oy)
        if self.layers.get("resources", True):
            self._draw_resources(surface, stockpile_manager, player, cr, scale, ox, oy)

        # Player always on top
        self._draw_player(surface, player, cr, scale, ox, oy)

        surface.set_clip(old_clip)

    def _draw_grid(self, surface, cr, player, scale, ox, oy):
        """Draw subtle grid lines at tile boundaries."""
        step = MAP_OVERLAY_GRID_STEP_TILES * TILE_SIZE
        if step <= 0:
            return
        # Compute world bounds visible in content rect
        left_wx = player.x - (cr.centerx - cr.left) / scale
        right_wx = player.x + (cr.right - cr.centerx) / scale
        top_wy = player.y - (cr.centery - cr.top) / scale
        bottom_wy = player.y + (cr.bottom - cr.centery) / scale

        # Align to grid
        start_gx = int(left_wx // step) * step
        start_gy = int(top_wy // step) * step

        # Vertical lines
        gx = start_gx
        while gx <= right_wx:
            x, _ = self._world_to_map(gx, 0, player, cr, scale, ox, oy)
            pygame.draw.line(surface, MAP_OVERLAY_GRID_COLOR, (x, cr.top), (x, cr.bottom), 1)
            gx += step

        # Horizontal lines
        gy = start_gy
        while gy <= bottom_wy:
            _, y = self._world_to_map(0, gy, player, cr, scale, ox, oy)
            pygame.draw.line(surface, MAP_OVERLAY_GRID_COLOR, (cr.left, y), (cr.right, y), 1)
            gy += step
