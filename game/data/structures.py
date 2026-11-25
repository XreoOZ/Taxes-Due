"""Game data — structures domain constants.

Auto-extracted from config.py; imported back by game.data.config
so `from game.data.config import X` keeps working everywhere.
"""

# -----------------------------------------------------------------------------
# STRUCTURES — buildings, furniture, permits, roads, cemetery, construction
# -----------------------------------------------------------------------------
BUILD_DURATION_SECONDS = 5.0

# Collision thickness of building perimeter walls. Kept slim so 1-tile-wide
# interior corridors (concave footprints like U-shapes) remain passable for
# the player (radius 24 needs ~48px of free width inside a 64px tile).
# *** ESTABLISHED — DO NOT REGRESS *** Raising this above ~8 re-blocks
# 1-tile corridors for the player; lowering it lets entities clip wall edges.
BUILDING_WALL_THICKNESS = 6

DEMOLISH_DURATION_SECONDS = 5.0

DEMOLITION_REFUND_RATIO = 0.5  # 50% resource refund when demolishing buildings

BUILDER_BUILD_DURATION_INGAME_HOURS = 20.0 / 60.0  # 20 in-game minutes

FURNITURE_DAILY_BREAK_CHANCE = 0.05

BUILDER_REPAIR_FOOD_DAYS = 3

BUILDER_REPAIR_MATERIALS = {"Wood": 1, "Stone": 1}


# Building Visuals (RimWorld Cutaway Style)
COLOR_BUILDING_WALL = (120, 80, 50)

COLOR_BUILDING_WALL_OUTLINE = (60, 35, 15)

COLOR_BUILDING_FLOOR = (195, 150, 105)

COLOR_BUILDING_FLOOR_ALT = (185, 140, 95)

COLOR_BUILDING_DOOR = (140, 90, 55)


# Stone Building Visuals
COLOR_STONE_WALL = (95, 100, 110)

COLOR_STONE_WALL_OUTLINE = (40, 45, 55)

COLOR_STONE_FLOOR = (160, 165, 175)

COLOR_STONE_FLOOR_ALT = (145, 150, 160)

COLOR_STONE_DOOR = (110, 75, 45)


# Free-Form Building Types (Zero Templates, Material-Driven Structures)
COST_PER_BLOCK_WOOD = 5

COST_PER_BLOCK_STONE = 5


BUILDING_TYPES = {
    "wooden_structure": {
        "id": "wooden_structure",
        "name": "Wooden Structure",
        "category": "Structure",
        "category_id": "structure",
        "desc": "Timber-framed building constructed from logs and wooden planks.",
        "cost_wood": 5,
        "cost_stone": 1,
        "color": (180, 120, 70),
        "border_color": (217, 119, 6),
        "required_permit": "housing",
        "allowed_permits": ["housing", "storage", "landlord_private", "church"],
    },
    "stone_structure": {
        "id": "stone_structure",
        "name": "Stone Structure",
        "category": "Structure",
        "category_id": "structure",
        "desc": "Heavy masonry structure built from carved stones and mortar.",
        "cost_wood": 1,
        "cost_stone": 5,
        "color": (148, 163, 184),
        "border_color": (203, 213, 225),
        "required_permit": "housing",
        "allowed_permits": ["housing", "storage", "landlord_private", "church"],
    },
    "well": {
        "id": "well",
        "name": "Well",
        "category": "Well",
        "category_id": "public_structure",
        "public_structure": True,
        "maintainable": True,
        "desc": "Fresh water well built of masonry and timber. Impenetrable 4-tile solid structure.",
        "cost_wood": 5,
        "cost_stone": 20,
        "fixed_cost": True,
        "fixed_tiles_count": 4,
        "width_tiles": 2,
        "height_tiles": 2,
        "is_solid": True,
        "has_door": False,
        "color": (56, 189, 248),
        "border_color": (96, 165, 250),
        "required_permit": "any",
        "allowed_permits": ["housing", "storage", "landlord_private", "church"],
        "builder_commissionable": True,
    },
    "market": {
        "id": "market",
        "name": "Market",
        "title": "Market Stall",
        "category": "Market Stall",
        "category_id": "public_structure",
        "public_structure": True,
        "maintainable": True,
        "desc": "Medieval marketplace stall for trading food, goods, and currency. Footprint: 3x2 tiles.",
        "cost_wood": 15,
        "cost_stone": 5,
        "fixed_cost": True,
        "fixed_tiles_count": 6,
        "width_tiles": 3,
        "height_tiles": 2,
        "is_solid": False,
        "has_door": False,
        "color": (245, 158, 11),
        "border_color": (251, 191, 36),
        "required_permit": "any",
        "allowed_permits": ["market", "storage", "landlord_private", "housing"],
        "builder_commissionable": True,
    },
    "toilet": {
        "id": "toilet",
        "name": "Toilet",
        "category": "Toilet",
        "category_id": "public_structure",
        "public_structure": True,
        "maintainable": True,
        "desc": "Medieval wooden outhouse latrine. Footprint: 1x1 tile. Does not require a Permit.",
        "cost_wood": 5,
        "cost_stone": 0,
        "fixed_cost": True,
        "fixed_tiles_count": 1,
        "width_tiles": 1,
        "height_tiles": 1,
        "is_solid": False,
        "has_door": False,
        "color": (120, 80, 40),
        "border_color": (160, 110, 60),
        "required_permit": None,
        "allowed_permits": None,
        "builder_commissionable": True,
    },
    "tax_house": {
        "id": "tax_house",
        "name": "Tax Office",
        "category": "Tax Office",
        "category_id": "workplace",
        "public_structure": True,
        "maintainable": True,
        "desc": "An open medieval tax-collection work station with a clerk's counter, ledgers, and royal banner.",
        "cost_wood": 20,
        "cost_stone": 15,
        "fixed_cost": True,
        "fixed_tiles_count": 4,
        "width_tiles": 2,
        "height_tiles": 2,
        "max_workers": 1,
        "is_solid": False,
        "has_door": False,
        "color": (177, 132, 82),
        "border_color": (217, 119, 6),
        "required_permit": None,
        "allowed_permits": None,
        "builder_commissionable": True,
        "visual_style": {
            "platform": (95, 75, 53),
            "platform_light": (105, 83, 59),
            "platform_dark": (88, 69, 49),
            "tile_seam": (72, 56, 40),
            "wood": (121, 78, 42),
            "wood_light": (166, 112, 61),
            "wood_dark": (62, 39, 26),
            "royal_cloth": (126, 32, 35),
            "gold": (226, 174, 73),
            "parchment": (221, 202, 158),
            "metal": (105, 112, 119),
        },
    }
}


# Roads: instant-paint public tile layer. cost = resources per tile,
# speed_multiplier applies to every mover standing on the tile.
ROAD_TYPES = {
    "dirt_road": {
        "id": "dirt_road",
        "name": "Dirt Road",
        "desc": "Packed earth path. +5% walk speed.",
        "color": (146, 104, 58),
        "rut_color": (120, 84, 44),
        "speed_multiplier": 1.05,
        "cost": {"Wood": 1},
    },
    "stone_road": {
        "id": "stone_road",
        "name": "Stone Road",
        "desc": "Paved flagstones. +10% walk speed.",
        "color": (120, 130, 145),
        "rut_color": (96, 105, 120),
        "speed_multiplier": 1.10,
        "cost": {"Stone": 1},
    },
    "luxury_road": {
        "id": "luxury_road",
        "name": "Luxury Road",
        "desc": "Fine paved boulevard. +15% walk speed.",
        "color": (203, 213, 225),
        "rut_color": (160, 170, 185),
        "speed_multiplier": 1.15,
        "cost": {"Stone": 5},
    },
}

ROAD_PLACEMENT_BLOCKED = True   # roads cannot overlap buildings/furniture/stockpiles


# Area Permit Types (Landlord Zoning)
PERMIT_TYPES = {
    "housing": {
        "id": "housing",
        "name": "Housing Permit",
        "category": "Housing & Residential",
        "category_id": "housing",
        "desc": "Official landlord deed for residential settlements.",
        "color": (59, 130, 246, 60),
        "border_color": (96, 165, 250),
    },
    "storage": {
        "id": "storage",
        "name": "Storage Permit",
        "category": "Logistics & Storage",
        "category_id": "storage",
        "desc": "Official landlord deed for resource storage & stockpiles.",
        "color": (234, 179, 8, 60),
        "border_color": (250, 204, 21),
    },
    "market": {
        "id": "market",
        "name": "Market Permit",
        "category": "Commercial & Trade",
        "category_id": "market",
        "desc": "Official landlord deed for commercial trade and market stalls.",
        "color": (245, 158, 11, 60),
        "border_color": (251, 191, 36),
    },
    "farm": {
        "id": "farm",
        "name": "Farm Permit",
        "category": "Agriculture & Farming",
        "category_id": "farm",
        "desc": "Official landlord agricultural deed for cultivating crops.",
        "color": (34, 197, 94, 50),
        "border_color": (74, 222, 128),
    },
    "landlord_private": {
        "id": "landlord_private",
        "name": "Landlord Private Area",
        "category": "Estate & Private Grounds",
        "category_id": "landlord_private",
        "desc": "Restricted estate grounds. Only Landlord and Servants may enter.",
        "color": (147, 51, 234, 60),
        "border_color": (234, 179, 8),
    },
    "church": {
        "id": "church",
        "name": "Church Permit",
        "category": "Religious & Community",
        "category_id": "church",
        "desc": "Official landlord deed for church grounds. Uses Wooden or Stone Structure construction.",
        "color": (168, 85, 247, 60),
        "border_color": (192, 132, 252),
    },
    "cemetery": {
        "id": "cemetery",
        "name": "Cemetery Permit",
        "category": "Burial & Memorial Grounds",
        "category_id": "cemetery",
        "desc": "Consecrated ground for burial plots and tombstones. Editable plot area.",
        "color": (100, 116, 139, 60),
        "border_color": (148, 163, 184),
    }
}


# Furniture System (Household Storage & Furnishings)
FURNITURE_TYPES = {
    "household_storage": {
        "id": "household_storage",
        "name": "Household Storage",
        "desc": "Wooden storage chest for a family's crops and goods. Placed inside a house or lot.",
        "capacity": 500,
        "materials": {"Wood": 10, "Stone": 0},
        "width_tiles": 1,
        "height_tiles": 1,
        "color_body": (139, 90, 43),
        "color_lid": (160, 105, 55),
        "color_clasp": (234, 179, 8)
    },
    "bed": {
        "id": "bed",
        "name": "Bed",
        "desc": "Single wooden bed for 1 villager. Placed inside a house or lot.",
        "capacity": 0,
        "materials": {"Wood": 5, "Stone": 0},
        "width_tiles": 1,
        "height_tiles": 1,
        "color_frame": (139, 90, 43),
        "color_blanket": (59, 130, 246),
        "color_pillow": (241, 245, 249)
    },
    "builder_workbench": {
        "id": "builder_workbench",
        "name": "Builder Workbench",
        "category_id": "workplace",
        "desc": "A sturdy medieval workbench for shaping and assembling furniture. Place inside a household or house.",
        "capacity": 0,
        "materials": {"Wood": 5, "Stone": 0},
        "width_tiles": 2,
        "height_tiles": 1,
        "max_workers": 2,
        "workplace_available_while_building": True,
        "color_frame": (112, 72, 38),
        "color_top": (170, 119, 70),
        "color_iron": (82, 91, 101)
    },
    "confession_box": {
        "id": "confession_box",
        "name": "Confession Box",
        "category_id": "public_structure",
        "public_structure": True,
        "maintainable": True,
        "desc": "A private medieval confessional for church visitors.",
        "capacity": 0,
        "materials": {"Wood": 5, "Stone": 0},
        "width_tiles": 1,
        "height_tiles": 1,
        "max_workers": 0,
        "allowed_permits": ["church"],
        "household_owned": False,
        "builder_commissionable": True,
        "color_frame": (92, 57, 34),
        "color_panel": (122, 75, 42),
        "color_cloth": (112, 35, 42),
        "color_trim": (190, 151, 83)
    },
    "lord_treasury_chest": {
        "id": "lord_treasury_chest",
        "name": "Lord Treasury Chest",
        "category_id": "furniture",
        "desc": "A reinforced royal coffer for landlord coin only. Free and ready to use immediately.",
        "capacity": 0,
        "materials": {},
        "width_tiles": 1,
        "height_tiles": 1,
        "household_owned": False,
        "instant_place": True,
        "placement_anywhere": True,
        "unique": True,
        "rotatable": False,
        "maintainable": False,
        "color_body": (70, 55, 38),
        "color_lid": (112, 85, 48),
        "color_clasp": (250, 204, 21),
        "color_trim": (203, 213, 225)
    },
    "woodsman_lodge": {
        "id": "woodsman_lodge",
        "name": "Woodsman Lodge",
        "category_id": "workplace",
        "desc": "Outdoor logging lodge where Woodsmen store felling tools and stockpile Wood. Place on open ground.",
        "capacity": 0,
        "materials": {"Wood": 20, "Stone": 10},
        "width_tiles": 4,
        "height_tiles": 4,
        "max_workers": 5,
        "household_owned": False,
        "placement_anywhere": True,
        "maintainable": False,
        "station_inventory_items": ["Wood"],
        "color_frame": (101, 67, 33),
        "color_roof": (22, 101, 52),
        "color_door": (146, 64, 14)
    },
    "miner_workstation": {
        "id": "miner_workstation",
        "name": "Miner Workstation",
        "category_id": "workplace",
        "desc": "5x5 mine-head workstation. Must be placed exactly on top of a generated mine deposit.",
        "capacity": 0,
        "materials": {"Stone": 20, "Wood": 10},
        "width_tiles": 5,
        "height_tiles": 5,
        "max_workers": 5,
        "household_owned": False,
        "placement_anywhere": True,
        "maintainable": False,
        "rotatable": False,
        "movable": False,
        "station_inventory_mine_bound": True,
        "color_frame": (71, 85, 105),
        "color_roof": (51, 65, 85),
        "color_rock": (100, 116, 139)
    },
    "toolmaker_workbench": {
        "id": "toolmaker_workbench",
        "name": "Toolmaker Workbench",
        "category_id": "workplace",
        "desc": "Smithy bench with anvil, tongs, and moulds. Place inside a household or house.",
        "capacity": 0,
        "materials": {"Wood": 15, "Stone": 10},
        "width_tiles": 2,
        "height_tiles": 1,
        "max_workers": 2,
        "maintainable": False,
        "color_frame": (70, 55, 38),
        "color_top": (112, 85, 48),
        "color_iron": (100, 116, 139),
        "color_anvil": (71, 85, 105)
    },
    # *** ESTABLISHED — DO NOT REGRESS ***
    # Notice Board attracts immigrant households. UNIQUE: max 1 per village
    # (enforced by add_furniture). public_structure + builder_commissionable
    # so only a builder can build it (1h). household_owned False — it belongs
    # to the village, not a family. Clicking it opens Town Ledger > Immigrant.
    "notice_board": {
        "id": "notice_board",
        "name": "Notice Board",
        "category_id": "public_structure",
        "public_structure": True,
        "maintainable": True,
        "desc": "A public bulletin board. Post immigration notices to attract settler households.",
        "capacity": 0,
        "materials": {"Wood": 10},
        "width_tiles": 2,
        "height_tiles": 1,
        "household_owned": False,
        "placement_anywhere": True,
        "unique": True,
        "rotatable": True,
        "builder_commissionable": True,
        "color_frame": (101, 67, 33),
        "color_panel": (146, 96, 48),
        "color_paper": (241, 245, 249),
        "color_pin": (220, 38, 38)
    },
    "toilet": {
        "id": "toilet",
        "name": "Toilet",
        "category_id": "public_structure",
        "public_structure": True,
        "maintainable": True,
        "movable": True,
        "can_be_dropped": True,
        "desc": "Medieval wooden outhouse latrine. Footprint: 1x1 tile. Movable and does not require a Permit.",
        "capacity": 0,
        "materials": {"Wood": 5, "Stone": 0},
        "width_tiles": 1,
        "height_tiles": 1,
        "max_workers": 0,
        "household_owned": False,
        "placement_anywhere": True,
        "rotatable": False,
        "builder_commissionable": True,
        "color": (120, 80, 40),
        "border_color": (160, 110, 60),
    }
}


PUBLIC_STRUCTURE_DAILY_BREAK_CHANCE = FURNITURE_DAILY_BREAK_CHANCE

LORD_TREASURY_START_TILE = (1, 0)

LORD_TREASURY_PLACEMENT_SEARCH_RADIUS = 8


GRAVEDIGGER_TARGET_WOOD = 5

GRAVEDIGGER_TARGET_STONE = 5

GRAVE_COST_WOOD = 1

GRAVE_COST_STONE = 1

GRAVE_DIG_HOURS = 20.0 / 60.0   # 20 in-game minutes digging

GRAVE_BURY_HOURS = 20.0 / 60.0  # 20 in-game minutes burial

GRAVE_REUSE_DAYS = 30.0         # Reusable after 30 in-game days

BURIAL_FEE_MAX_SILVER = 1       # Up to 1 Silver (10 Copper)

TOMBSTONE_MODELS_COUNT = 5      # At least 5 distinct tombstone variants

