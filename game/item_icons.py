"""
Centralized Global Item Icons System (AGENT 2)
Provides consistent, recognizable procedural vector icons for all items across the entire game
(Resource HUD, Storage Chests, Stockpiles, Market, Household Possessions, Member Inventories, and Grants).
Zero reliance on emoji fonts; 100% vector-rendered across all platforms and display resolutions.
"""

import math
import pygame

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

    # 8. TOOL: Hoe
    elif "hoe" in name_low:
        # Wooden shaft
        pygame.draw.line(surface, (139, 90, 43), (cx - size + 2, cy + size - 2), (cx + 4, cy - 4), 2)
        # Iron hoe blade
        pygame.draw.line(surface, (170, 175, 185), (cx + 1, cy - 8), (cx + 8, cy - 2), 3)
        pygame.draw.line(surface, (220, 225, 235), (cx + 2, cy - 7), (cx + 7, cy - 3), 1)

    # 9. TOOL: Sickle
    elif "sickle" in name_low:
        # Wooden handle
        pygame.draw.line(surface, (139, 90, 43), (cx - 4, cy + 2), (cx - 7, cy + size - 2), 2)
        # Crescent steel blade
        arc_rect = pygame.Rect(cx - 6, cy - size + 2, size * 2 - 2, size * 2 - 2)
        pygame.draw.arc(surface, (200, 210, 225), arc_rect, 0.4, 3.2, 2)

    # 10. TOOL: Watering Can / Pot
    elif "can" in name_low or "watering" in name_low or "pot" in name_low:
        # Medieval terracotta chantepleure pot
        pot_r = max(3, int(size * 0.7))
        pygame.draw.circle(surface, (180, 105, 55), (cx, cy + 2), pot_r)
        pygame.draw.circle(surface, (120, 65, 30), (cx, cy + 2), pot_r, 1)
        # Spout neck and handle
        pygame.draw.rect(surface, (160, 90, 45), (cx - 2, cy - int(size * 0.7), 4, int(size * 0.5)))
        pygame.draw.arc(surface, (100, 50, 20), (cx - int(size * 0.8), cy - int(size * 0.7), int(size * 1.6), int(size * 1.3)), 0.3, 2.8, 2)
        # Sprinkler rose head
        pygame.draw.line(surface, (190, 120, 60), (cx + int(size * 0.4), cy), (cx + size, cy - int(size * 0.5)), 2)
        pygame.draw.circle(surface, (217, 149, 44), (cx + size, cy - int(size * 0.5)), 2)

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

    # 14. FOOD: Fish
    elif "fish" in name_low:
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

    # Carpenter's tools: recognizable medieval hand tools.
    elif "saw" in name_low:
        pygame.draw.line(surface, (125, 82, 44), (cx - size + 2, cy + size - 3), (cx + size - 2, cy - size + 3), max(2, size // 5))
        blade = [(cx - size + 1, cy + size - 4), (cx + size - 2, cy - size + 2), (cx + size, cy - size + 5)]
        pygame.draw.polygon(surface, (203, 213, 225), blade)
        pygame.draw.line(surface, (100, 116, 139), blade[0], blade[1], 1)
        for tooth in range(3):
            x = cx + size - 5 - tooth * 3
            y = cy - size + 7 + tooth * 3
            pygame.draw.line(surface, (71, 85, 105), (x, y), (x + 2, y + 3), 1)
    elif "adze" in name_low:
        pygame.draw.line(surface, (125, 82, 44), (cx - size + 1, cy + size - 2), (cx + 3, cy - 2), max(2, size // 5))
        blade = [(cx + 1, cy - 5), (cx + size, cy - size + 1), (cx + size - 1, cy + 1), (cx + 4, cy + 2)]
        pygame.draw.polygon(surface, (203, 213, 225), blade)
        pygame.draw.polygon(surface, (100, 116, 139), blade, 1)
        pygame.draw.line(surface, (241, 245, 249), (cx + 5, cy - 4), (cx + size - 2, cy - size + 2), 1)

    # Field & mining tools: haft + perpendicular steel head (axe/pick/sledge) or forward blade (spade).
    elif "felling axe" in name_low or name_low == "axe" or "hatchet" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        pygame.draw.line(surface, (139, 90, 43), (cx - size + 2, cy + size - 2), (hx, hy), 2)
        # Head bar across the haft + wedge blade on the forward end
        pygame.draw.line(surface, (100, 116, 139), (hx - 4, hy - 4), (hx + 4, hy + 4), 4)
        pygame.draw.polygon(surface, (203, 213, 225), [(hx + 2, hy + 2), (hx + 7, hy + 7), (hx + 4, hy + 5)])
        pygame.draw.line(surface, (226, 232, 240), (hx + 3, hy + 3), (hx + 6, hy + 6), 1)
    elif "pickaxe" in name_low or "pick axe" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        pygame.draw.line(surface, (139, 90, 43), (cx - size + 2, cy + size - 2), (hx, hy), 2)
        # Double-pointed head: straight bar across the haft with tapered tips
        pygame.draw.line(surface, (100, 116, 139), (hx - 5, hy - 5), (hx + 5, hy + 5), 4)
        pygame.draw.line(surface, (203, 213, 225), (hx - 4, hy - 4), (hx + 4, hy + 4), 2)
        pygame.draw.circle(surface, (139, 90, 43), (hx, hy), 2)
    elif "sledge" in name_low or "sledgehammer" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        pygame.draw.line(surface, (139, 90, 43), (cx - size + 2, cy + size - 2), (hx, hy), 2)
        # Wide double-face head
        pygame.draw.line(surface, (71, 85, 105), (hx - 5, hy - 5), (hx + 5, hy + 5), 5)
        pygame.draw.line(surface, (148, 163, 184), (hx - 4, hy - 4), (hx - 1, hy - 1), 1)
        pygame.draw.line(surface, (148, 163, 184), (hx + 4, hy + 4), (hx + 1, hy + 1), 1)
    elif "spade" in name_low:
        hx, hy = cx + size - 4, cy - size + 4
        pygame.draw.line(surface, (139, 90, 43), (cx - size + 2, cy + size - 2), (hx, hy), 2)
        # Flat steel blade pointing forward along the haft
        pygame.draw.polygon(surface, (203, 213, 225), [(hx - 2, hy + 2), (hx + 2, hy - 2), (hx + 6, hy - 5)])
        pygame.draw.line(surface, (100, 116, 139), (hx - 2, hy + 2), (hx + 6, hy - 5), 1)
        pygame.draw.line(surface, (226, 232, 240), (hx + 1, hy - 2), (hx + 4, hy - 4), 1)

    # 16. GENERIC / FALLBACK: Supplies Crate
    else:
        bx = max(5, int(size * 0.75))
        by = max(4, int(size * 0.6))
        b_rect = pygame.Rect(cx - bx, cy - by, bx * 2, by * 2)
        pygame.draw.rect(surface, (180, 120, 70), b_rect, border_radius=2)
        pygame.draw.rect(surface, (120, 70, 30), b_rect, 1, border_radius=2)
        pygame.draw.line(surface, (120, 70, 30), (b_rect.left, b_rect.top), (b_rect.right, b_rect.bottom), 1)
