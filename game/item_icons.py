"""
Centralized Global Item Icons System (AGENT 2)
Provides consistent, recognizable procedural vector icons for all items across the entire game
(Resource HUD, Storage Chests, Stockpiles, Market, Household Possessions, Member Inventories, and Grants).
Zero reliance on emoji fonts; 100% vector-rendered across all platforms and display resolutions.
"""

import math
import pygame

# --- Medieval tool icon helpers -------------------------------------------
# Consistent material palette: dark wood outline, warm wood core,
# forged steel (dark base / mid / bright edge), iron collar bands.

_HAFT_DARK = (74, 45, 18)
_HAFT_WOOD = (139, 90, 43)
_HAFT_WOOD_LT = (176, 122, 62)
_STEEL_DARK = (51, 65, 85)
_STEEL_MID = (100, 116, 139)
_STEEL_LT = (203, 213, 225)
_STEEL_HI = (241, 245, 249)
_IRON_BAND = (71, 85, 105)


def _haft(surface, x1, y1, x2, y2, width=3, wrap=True):
    """Draws a wooden tool haft: dark outline, warm core, pale top edge,
    and a dark grip-wrap band near the lower (held) end."""
    pygame.draw.line(surface, _HAFT_DARK, (x1, y1), (x2, y2), width + 1)
    pygame.draw.line(surface, _HAFT_WOOD, (x1, y1), (x2, y2), width)
    # Subtle lit edge along the haft
    pygame.draw.line(surface, _HAFT_WOOD_LT, (x1 - 1, y1 - 1), (x2 - 1, y2 - 1), 1)
    if wrap:
        # Grip wrap: two dark bands a third of the way up from the grip end
        dx, dy = x2 - x1, y2 - y1
        length = max(1.0, math.hypot(dx, dy))
        for frac in (0.22, 0.34):
            t = frac
            wx, wy = x1 + dx * t, y1 + dy * t
            nx, ny = -dy / length, dx / length
            pygame.draw.line(surface, _STEEL_DARK,
                             (wx - nx, wy - ny), (wx + nx, wy + ny), width + 1)


def _steel_line(surface, x1, y1, x2, y2, width=3):
    """Forged steel stroke: dark edge, mid body, bright edge highlight."""
    pygame.draw.line(surface, _STEEL_DARK, (x1, y1), (x2, y2), width + 1)
    pygame.draw.line(surface, _STEEL_MID, (x1, y1), (x2, y2), width)
    pygame.draw.line(surface, _STEEL_LT, (x1 - 1, y1 - 1), (x2 - 1, y2 - 1), max(1, width - 2))


def _collar(surface, cx, cy, radius=3):
    """Iron collar band where a steel head meets the wooden haft."""
    pygame.draw.circle(surface, _IRON_BAND, (cx, cy), radius)
    pygame.draw.circle(surface, _STEEL_DARK, (cx, cy), radius, 1)


def draw_item_icon(surface, item_name, cx, cy, size=12):
    """
    Renders a unified procedural vector icon for any item.
    - surface: target Pygame surface
    - item_name: string identifier (e.g. 'Potato', 'Wood', 'Gold Coin', 'Watering_Can')
    - cx, cy: center coordinates of the icon
    - size: half-width / scale radius of the icon (default 12)
    """
    name_low = str(item_name).strip().lower().replace("_", " ")

    # 1. CURRENCY: Gold Coin
    if "gold" in name_low:
        r = max(4, int(size * 0.75))
        pygame.draw.circle(surface, (250, 204, 21), (cx, cy), r)
        pygame.draw.circle(surface, (161, 98, 7), (cx, cy), r, 1)
        # Inner rim & shine highlight
        if r >= 5:
            pygame.draw.circle(surface, (254, 240, 138), (cx - 1, cy - 1), r - 3, 1)

    # 2. CURRENCY: Silver Coin
    elif "silver" in name_low:
        r = max(4, int(size * 0.75))
        pygame.draw.circle(surface, (203, 213, 225), (cx, cy), r)
        pygame.draw.circle(surface, (100, 116, 139), (cx, cy), r, 1)
        if r >= 5:
            pygame.draw.circle(surface, (241, 245, 249), (cx - 1, cy - 1), r - 3, 1)

    # 3. CURRENCY: Copper Coin
    elif "copper" in name_low or (name_low == "coin"):
        r = max(4, int(size * 0.75))
        pygame.draw.circle(surface, (184, 115, 51), (cx, cy), r)
        pygame.draw.circle(surface, (120, 53, 15), (cx, cy), r, 1)
        if r >= 5:
            pygame.draw.circle(surface, (217, 149, 44), (cx - 1, cy - 1), r - 3, 1)

    # 4. FOOD: Potato
    elif "potato" in name_low or "spud" in name_low or (name_low == "food"):
        rx = max(4, int(size * 0.95))
        ry = max(3, int(size * 0.65))
        rect = pygame.Rect(cx - rx, cy - ry, rx * 2, ry * 2)
        pygame.draw.ellipse(surface, (180, 115, 60), rect)
        pygame.draw.ellipse(surface, (120, 70, 30), rect, 1)
        # Stippled potato eyes
        if rx >= 6:
            pygame.draw.circle(surface, (100, 50, 20), (cx - rx // 2, cy - 1), 1)
            pygame.draw.circle(surface, (100, 50, 20), (cx + rx // 3, cy + 2), 1)
            pygame.draw.circle(surface, (100, 50, 20), (cx + 1, cy - ry // 2), 1)

    # 5. WATER
    elif "water" in name_low:
        r = max(4, int(size * 0.65))
        # Droplet body
        pygame.draw.circle(surface, (56, 189, 248), (cx, cy + 2), r)
        pts = [(cx, cy - r - 2), (cx - r, cy + 1), (cx + r, cy + 1)]
        pygame.draw.polygon(surface, (56, 189, 248), pts)
        # Specular shine
        pygame.draw.circle(surface, (186, 230, 253), (cx - 1, cy), max(1, r // 2))
        pygame.draw.circle(surface, (14, 116, 144), (cx, cy + 2), r, 1)

    # 6. RESOURCE: Wood / Timber
    elif "wood" in name_low or "timber" in name_low:
        w_rect = pygame.Rect(cx - size + 1, cy - 4, size * 2 - 2, 8)
        pygame.draw.rect(surface, (160, 105, 55), w_rect, border_radius=2)
        pygame.draw.rect(surface, (100, 60, 25), w_rect, 1, border_radius=2)
        # Concentric tree ring end cap
        pygame.draw.circle(surface, (200, 150, 90), (cx + size - 3, cy), 3)
        pygame.draw.circle(surface, (100, 60, 25), (cx + size - 3, cy), 1)

    # 7. RESOURCE: Stone / Carved Stone
    elif "stone" in name_low or "rock" in name_low:
        s_rect = pygame.Rect(cx - int(size * 0.8), cy - int(size * 0.6), int(size * 1.6), int(size * 1.2))
        pygame.draw.rect(surface, (148, 163, 184), s_rect, border_radius=2)
        pygame.draw.rect(surface, (100, 116, 139), s_rect, 1, border_radius=2)
        # Ashlar block chamfer lines
        pygame.draw.line(surface, (226, 232, 240), (s_rect.left + 1, s_rect.top + 1), (s_rect.right - 2, s_rect.top + 1), 1)

    # 7b. RESOURCE: Iron Ore — rusty rock chunk with molten flecks
    elif "ore" in name_low:
        ore_rect = pygame.Rect(cx - int(size * 0.85), cy - int(size * 0.6),
                               int(size * 1.7), int(size * 1.2))
        pygame.draw.rect(surface, (120, 72, 40), ore_rect, border_radius=3)
        pygame.draw.rect(surface, (80, 45, 20), ore_rect, 1, border_radius=3)
        # Ore veins
        pygame.draw.circle(surface, (249, 115, 22), (cx - int(size * 0.3), cy - 1), max(1, int(size * 0.18)))
        pygame.draw.circle(surface, (249, 115, 22), (cx + int(size * 0.25), cy + 2), max(1, int(size * 0.14)))
        pygame.draw.circle(surface, (217, 119, 6), (cx + 1, cy - int(size * 0.25)), max(1, int(size * 0.12)))
        pygame.draw.line(surface, (160, 90, 45), (ore_rect.left + 2, ore_rect.top + 2),
                         (ore_rect.right - 3, ore_rect.top + 1), 1)

    # 7c. RESOURCE: Iron Bar — cast trapezoid ingot
    elif "bar" in name_low:
        top_w = int(size * 0.85)
        bot_w = int(size * 0.55)
        bar_h = int(size * 0.9)
        top_y, bot_y = cy - bar_h // 2, cy + bar_h // 2
        pts = [(cx - top_w, top_y), (cx + top_w, top_y),
               (cx + bot_w, bot_y), (cx - bot_w, bot_y)]
        pygame.draw.polygon(surface, (148, 163, 184), pts)
        pygame.draw.polygon(surface, (100, 116, 139), pts, 1)
        # Top face highlight + rust streak
        pygame.draw.polygon(surface, (203, 213, 225),
                            [(cx - top_w + 2, top_y + 1), (cx + top_w - 2, top_y + 1),
                             (cx + bot_w - 1, top_y + bar_h // 3), (cx - bot_w + 1, top_y + bar_h // 3)])
        pygame.draw.line(surface, (180, 83, 9), (cx - bot_w // 2, bot_y - 1),
                         (cx + bot_w // 2, bot_y - 1), 1)

    # 8. TOOL: Hoe — haft with angled steel blade plate
    elif "hoe" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        _haft(surface, cx - size + 2, cy + size - 2, hx, hy)
        # Blade plate swept back from the haft head
        pygame.draw.polygon(surface, _STEEL_DARK,
                            [(hx - 1, hy - 6), (hx + 8, hy - 1), (hx + 6, hy + 5), (hx - 2, hy + 1)])
        pygame.draw.polygon(surface, _STEEL_MID,
                            [(hx, hy - 5), (hx + 7, hy - 1), (hx + 5, hy + 4), (hx - 1, hy)])
        pygame.draw.line(surface, _STEEL_HI, (hx + 1, hy - 4), (hx + 6, hy - 1), 1)
        _collar(surface, hx - 1, hy - 2, 2)

    # 9. TOOL: Sickle — haft with crescent blade
    elif "sickle" in name_low:
        hx, hy = cx - 2, cy + 2
        _haft(surface, hx, cy + size - 1, hx - 3, hy + 3, width=3)
        # Crescent blade: layered arcs for forged edge
        arc_rect = pygame.Rect(cx - 7, cy - size + 2, size * 2 - 2, size * 2 - 2)
        pygame.draw.arc(surface, _STEEL_DARK, arc_rect, 0.5, 3.0, 4)
        pygame.draw.arc(surface, _STEEL_MID, arc_rect, 0.5, 3.0, 3)
        pygame.draw.arc(surface, _STEEL_LT, arc_rect, 0.7, 2.8, 1)
        _collar(surface, hx - 2, hy + 2, 2)

    # 10. TOOL: Watering Can — medieval copper chantepleure pot
    elif "can" in name_low or "watering" in name_low or "pot" in name_low:
        pot_r = max(4, int(size * 0.62))
        body = pygame.Rect(cx - pot_r, cy - pot_r // 2, pot_r * 2, pot_r * 2)
        # Pot body with shaded base
        pygame.draw.ellipse(surface, (140, 80, 35), body)
        pygame.draw.ellipse(surface, (180, 105, 55), (body.left + 2, body.top - 2, body.width - 4, body.height - 4))
        pygame.draw.ellipse(surface, (217, 149, 44), (body.left + 4, body.top, body.width - 8, body.height // 2 - 2))
        pygame.draw.ellipse(surface, (120, 65, 30), body, 1)
        # Rim + arched handle
        pygame.draw.ellipse(surface, (160, 90, 45), (cx - 4, cy - pot_r - 3, 8, 6), 1)
        pygame.draw.arc(surface, (100, 50, 20),
                        (cx - int(size * 0.85), cy - int(size * 0.75), int(size * 1.7), int(size * 1.35)),
                        0.3, 2.8, 2)
        # Spout + sprinkler rose
        pygame.draw.line(surface, (160, 90, 45), (cx + pot_r - 1, cy - 2), (cx + size, cy - int(size * 0.5)), 2)
        pygame.draw.circle(surface, (190, 120, 60), (cx + size, cy - int(size * 0.5)), 2)
        pygame.draw.circle(surface, (120, 65, 30), (cx + size, cy - int(size * 0.5)), 2, 1)

    # 11. FOOD: Bread
    elif "bread" in name_low or "loaf" in name_low:
        b_rect = pygame.Rect(cx - size, cy - int(size * 0.6), size * 2, int(size * 1.2))
        pygame.draw.ellipse(surface, (217, 149, 44), b_rect)
        pygame.draw.ellipse(surface, (146, 64, 14), b_rect, 1)
        pygame.draw.line(surface, (254, 243, 199), (cx - 4, cy - 2), (cx - 1, cy + 2), 1)
        pygame.draw.line(surface, (254, 243, 199), (cx + 1, cy - 2), (cx + 4, cy + 2), 1)

    # 12. RESOURCE: Cloth / Linen
    elif "cloth" in name_low or "linen" in name_low:
        c_rect = pygame.Rect(cx - int(size * 0.8), cy - int(size * 0.6), int(size * 1.6), int(size * 1.2))
        pygame.draw.rect(surface, (226, 232, 240), c_rect, border_radius=2)
        pygame.draw.rect(surface, (148, 163, 184), c_rect, 1, border_radius=2)
        pygame.draw.line(surface, (203, 213, 225), (c_rect.left + 2, c_rect.centery), (c_rect.right - 2, c_rect.centery), 1)

    # 13. FOOD: Apple / Fruit
    elif "apple" in name_low or "fruit" in name_low:
        r = max(4, int(size * 0.7))
        pygame.draw.circle(surface, (239, 68, 68), (cx - 1, cy + 1), r)
        pygame.draw.circle(surface, (185, 28, 28), (cx - 1, cy + 1), r, 1)
        # Stem and leaf
        pygame.draw.line(surface, (120, 53, 15), (cx - 1, cy - r), (cx + 1, cy - r - 3), 1)
        pygame.draw.polygon(surface, (34, 197, 94), [(cx + 1, cy - r - 2), (cx + 4, cy - r - 4), (cx + 2, cy - r)])

    # 14. FOOD: Fish (exclude "fishing rod" — handled in tools below)
    elif "fish" in name_low and "rod" not in name_low and "fishing" not in name_low:
        f_rect = pygame.Rect(cx - size + 2, cy - int(size * 0.5), int(size * 1.5), int(size * 1.0))
        pygame.draw.ellipse(surface, (56, 189, 248), f_rect)
        pygame.draw.ellipse(surface, (14, 116, 144), f_rect, 1)
        # Tail fin
        tail = [(cx + int(size * 0.5), cy), (cx + size, cy - 4), (cx + size, cy + 4)]
        pygame.draw.polygon(surface, (56, 189, 248), tail)
        # Eye
        pygame.draw.circle(surface, (255, 255, 255), (cx - int(size * 0.4), cy - 1), 1)

    # 15. FOOD: Meat
    elif "meat" in name_low or "pork" in name_low or "beef" in name_low:
        m_rect = pygame.Rect(cx - int(size * 0.8), cy - int(size * 0.6), int(size * 1.6), int(size * 1.2))
        pygame.draw.ellipse(surface, (190, 24, 93), m_rect)
        pygame.draw.ellipse(surface, (131, 24, 67), m_rect, 1)
        # Bone marrow circle
        pygame.draw.circle(surface, (254, 242, 242), (cx + int(size * 0.3), cy), max(1, int(size * 0.3)))

    # Medieval frame saw: wooden bowed frame + tensioned toothed blade.
    elif "saw" in name_low:
        fx1, fy1 = cx - size + 2, cy - int(size * 0.9)   # top-left corner
        fx2, fy2 = cx + size - 2, cy + int(size * 0.9)   # bottom-right corner
        # Frame rails (wood)
        _haft(surface, fx1, fy1, fx2, fy1 + int(size * 0.5), width=2, wrap=False)
        _haft(surface, fx1 + int(size * 0.4), fy2, fx2, fy2 - int(size * 0.5), width=2, wrap=False)
        # Crossbars
        pygame.draw.line(surface, _HAFT_WOOD, (fx1 + int(size * 0.2), fy1 + int(size * 0.1)),
                         (fx1 + int(size * 0.2), fy1 + int(size * 0.8)), 2)
        pygame.draw.line(surface, _HAFT_WOOD, (fx2 - int(size * 0.2), fy2 - int(size * 0.8)),
                         (fx2 - int(size * 0.2), fy2 - int(size * 0.1)), 2)
        # Blade: thin steel line with saw teeth
        bx1, by1 = fx1 + int(size * 0.55), fy1 + int(size * 0.55)
        bx2, by2 = fx2 - int(size * 0.55), fy2 - int(size * 0.55)
        pygame.draw.line(surface, _STEEL_DARK, (bx1, by1), (bx2, by2), 2)
        pygame.draw.line(surface, _STEEL_LT, (bx1, by1), (bx2, by2), 1)
        length = math.hypot(bx2 - bx1, by2 - by1)
        for i in range(1, 5):
            t = i / 5.0
            tx, ty = bx1 + (bx2 - bx1) * t, by1 + (by2 - by1) * t
            nx, ny = -(by2 - by1) / length, (bx2 - bx1) / length
            pygame.draw.line(surface, _STEEL_MID,
                             (tx - nx, ty - ny), (tx + nx * 0.4, ty + ny * 0.4), 1)

    # Medieval adze: haft with curved blade head perpendicular at top.
    elif "adze" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        _haft(surface, cx - size + 2, cy + size - 2, hx, hy)
        # Curved adze blade sweeping forward-down from the head
        pygame.draw.polygon(surface, _STEEL_DARK,
                            [(hx - 2, hy - 5), (hx + size - 2, hy - size + 3),
                             (hx + size - 4, hy - size + 8), (hx - 1, hy + 1)])
        pygame.draw.polygon(surface, _STEEL_MID,
                            [(hx - 1, hy - 4), (hx + size - 4, hy - size + 4),
                             (hx + size - 5, hy - size + 7), (hx, hy)])
        pygame.draw.line(surface, _STEEL_HI, (hx + 1, hy - 3), (hx + size - 5, hy - size + 4), 1)
        _collar(surface, hx, hy - 1, 2)

    # Felling axe: haft + forged wedge head with poll and blade edge.
    elif "felling axe" in name_low or name_low == "axe" or "hatchet" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        _haft(surface, cx - size + 2, cy + size - 2, hx, hy)
        # Axe head: back poll + top bar + wedge blade
        pygame.draw.polygon(surface, _STEEL_DARK,
                            [(hx - 6, hy - 5), (hx + 6, hy - 6), (hx + 6, hy + 1),
                             (hx + 2, hy + 2), (hx - 6, hy + 1)])
        pygame.draw.polygon(surface, _STEEL_MID,
                            [(hx - 5, hy - 4), (hx + 5, hy - 5), (hx + 5, hy),
                             (hx + 2, hy + 1), (hx - 5, hy)])
        # Blade bevel + edge
        pygame.draw.line(surface, _STEEL_HI, (hx + 2, hy - 3), (hx + 5, hy - 4), 1)
        pygame.draw.line(surface, _STEEL_HI, (hx + 2, hy - 1), (hx + 5, hy), 1)
        _collar(surface, hx, hy, 2)

    # Pickaxe: haft + pick head — curved point one side, blunt face other.
    elif "pickaxe" in name_low or "pick axe" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        _haft(surface, cx - size + 2, cy + size - 2, hx, hy)
        # Head bar across the haft
        pygame.draw.line(surface, _STEEL_DARK, (hx - 6, hy - 6), (hx + 6, hy + 6), 6)
        pygame.draw.line(surface, _STEEL_MID, (hx - 6, hy - 6), (hx + 6, hy + 6), 4)
        # Curved pick point (upper-left tip)
        pygame.draw.arc(surface, _STEEL_LT,
                        pygame.Rect(hx - size + 2, hy - size + 2, size, size),
                        3.6, 5.6, 2)
        # Blunt hammer face (lower-right tip)
        pygame.draw.line(surface, _STEEL_HI, (hx + 3, hy + 3), (hx + 7, hy + 7), 3)
        _collar(surface, hx, hy, 2)

    # Sledgehammer: haft + heavy double-face maul head.
    elif "sledge" in name_low or "sledgehammer" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        _haft(surface, cx - size + 2, cy + size - 2, hx, hy)
        # Long perpendicular maul head with two flat striking faces
        pygame.draw.line(surface, _STEEL_DARK, (hx - 7, hy - 7), (hx + 7, hy + 7), 7)
        pygame.draw.line(surface, _STEEL_MID, (hx - 6, hy - 6), (hx + 6, hy + 6), 5)
        pygame.draw.line(surface, _STEEL_HI, (hx - 5, hy - 5), (hx - 2, hy - 2), 1)
        pygame.draw.line(surface, _STEEL_HI, (hx + 5, hy + 5), (hx + 2, hy + 2), 1)
        _collar(surface, hx, hy, 2)

    # Spade: haft + leaf-shaped digging blade.
    elif "spade" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        _haft(surface, cx - size + 2, cy + size - 2, hx, hy)
        # Leaf blade pointing forward along the haft
        pygame.draw.polygon(surface, _STEEL_DARK,
                            [(hx - 2, hy + 2), (hx + 2, hy - 2), (hx + 7, hy - 6),
                             (hx + 4, hy - 8), (hx - 1, hy - 3)])
        pygame.draw.polygon(surface, _STEEL_MID,
                            [(hx - 1, hy + 1), (hx + 1, hy - 1), (hx + 6, hy - 5),
                             (hx + 3, hy - 7), (hx, hy - 2)])
        pygame.draw.line(surface, _STEEL_HI, (hx + 2, hy - 2), (hx + 5, hy - 5), 1)
        _collar(surface, hx, hy, 2)

    # Smith's hammer: haft + peen-and-face head block.
    elif "hammer" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        _haft(surface, cx - size + 2, cy + size - 2, hx, hy)
        # Head: perpendicular bar with flat face (right) and peen taper (left)
        pygame.draw.polygon(surface, _STEEL_DARK,
                            [(hx - 7, hy - 4), (hx - 2, hy - 6), (hx + 6, hy - 5),
                             (hx + 7, hy - 2), (hx + 6, hy + 3), (hx - 2, hy + 5),
                             (hx - 7, hy + 3)])
        pygame.draw.polygon(surface, _STEEL_MID,
                            [(hx - 6, hy - 3), (hx - 2, hy - 5), (hx + 5, hy - 4),
                             (hx + 6, hy - 1), (hx + 5, hy + 2), (hx - 2, hy + 4),
                             (hx - 6, hy + 2)])
        pygame.draw.line(surface, _STEEL_HI, (hx + 1, hy - 3), (hx + 5, hy - 3), 1)
        pygame.draw.line(surface, _STEEL_HI, (hx + 1, hy + 1), (hx + 5, hy + 1), 1)
        _collar(surface, hx, hy, 2)

    # Smith's tongs: two riveted arms with scalloped grips.
    elif "tongs" in name_low:
        # Arms from grip ends up to the pivot rivet
        _steel_line(surface, cx - size + 1, cy + size - 2, cx - 1, cy - 1, 2)
        _steel_line(surface, cx + size - 3, cy + size - 3, cx + 2, cy - 2, 2)
        # Pivot rivet
        pygame.draw.circle(surface, _STEEL_DARK, (cx, cy), 3)
        pygame.draw.circle(surface, _STEEL_HI, (cx, cy), 1)
        # Wooden grip wraps on both handles
        pygame.draw.line(surface, _HAFT_DARK, (cx - size + 1, cy + size - 2), (cx - size + 4, cy + size - 5), 3)
        pygame.draw.line(surface, _HAFT_WOOD, (cx - size + 2, cy + size - 3), (cx - size + 3, cy + size - 6), 1)
        pygame.draw.line(surface, _HAFT_DARK, (cx + size - 3, cy + size - 3), (cx + size - 6, cy + size - 6), 3)
        pygame.draw.line(surface, _HAFT_WOOD, (cx + size - 4, cy + size - 4), (cx + size - 5, cy + size - 7), 1)
    elif "rolling" in name_low or "pin" in name_low:
        # Horizontal flour-dusted cylinder
        pin_rect = pygame.Rect(cx - size + 1, cy - int(size * 0.4), int(size * 2 - 2), int(size * 0.8))
        pygame.draw.rect(surface, (210, 180, 140), pin_rect, border_radius=int(size * 0.3))
        pygame.draw.rect(surface, (160, 120, 80), pin_rect, 1, border_radius=int(size * 0.3))
        pygame.draw.line(surface, (255, 255, 255), (pin_rect.left + 3, pin_rect.centery - 1),
                         (pin_rect.right - 3, pin_rect.centery - 1), 1)
        pygame.draw.line(surface, (139, 90, 43), (cx - int(size * 0.3), cy - int(size * 0.4)),
                         (cx - int(size * 0.3), cy - int(size * 0.7)), 2)
        pygame.draw.line(surface, (139, 90, 43), (cx + int(size * 0.3), cy - int(size * 0.4)),
                         (cx + int(size * 0.3), cy - int(size * 0.7)), 2)
    elif "peel" in name_low:
        # Small peeling knife: angled blade + grip
        pygame.draw.line(surface, (139, 90, 43), (cx - size + 1, cy + size - 2), (cx + 2, cy - 2), 2)
        pygame.draw.polygon(surface, (203, 213, 225),
                            [(cx - 1, cy - 4), (cx + 6, cy - 7), (cx + 8, cy - 3), (cx + 2, cy)])
        pygame.draw.line(surface, (100, 116, 139), (cx - 1, cy - 4), (cx + 8, cy - 3), 1)
    elif "fishing" in name_low or "rod" in name_low:
        # Angled rod, reel, and line with bobber
        pygame.draw.line(surface, (139, 90, 43), (cx - size + 2, cy + size - 2), (cx + size - 4, cy - size + 4), 2)
        pygame.draw.circle(surface, (203, 213, 225), (cx + 1, cy + 1), max(2, int(size * 0.22)), 1)
        pygame.draw.line(surface, (226, 232, 240), (cx + size - 4, cy - size + 4), (cx + size - 1, cy + size - 6), 1)
        pygame.draw.circle(surface, (239, 68, 68), (cx + size - 1, cy + size - 6), max(1, int(size * 0.18)))

    # 16. GENERIC / FALLBACK: Supplies Crate
    else:
        bx = max(5, int(size * 0.75))
        by = max(4, int(size * 0.6))
        b_rect = pygame.Rect(cx - bx, cy - by, bx * 2, by * 2)
        pygame.draw.rect(surface, (180, 120, 70), b_rect, border_radius=2)
        pygame.draw.rect(surface, (120, 70, 30), b_rect, 1, border_radius=2)
        pygame.draw.line(surface, (120, 70, 30), (b_rect.left, b_rect.top), (b_rect.right, b_rect.bottom), 1)
