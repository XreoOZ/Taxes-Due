"""
Configuration and Global Constants
"""

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

# Window Settings
WINDOW_TITLE = "Taxes-Due | Village Building Prototype"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60

# Grid & World Settings
TILE_SIZE = 64

# Camera & Zoom Settings
CAMERA_LERP_SPEED = 0.12
CAMERA_ZOOM_DEFAULT = 1.0
CAMERA_ZOOM_MIN = 0.5
CAMERA_ZOOM_MAX = 2.0
CAMERA_ZOOM_STEP = 0.1

# Colors (RGB)
COLOR_BG = (30, 41, 59)
COLOR_GRASS_A = (76, 138, 66)
COLOR_GRASS_B = (69, 128, 60)
COLOR_GRID = (255, 255, 255, 12)

# Player Settings
PLAYER_RADIUS = 24
PLAYER_SPEED = 280.0
COLOR_PLAYER_BODY = (56, 189, 248)       # Sky blue
COLOR_PLAYER_OUTLINE = (8, 47, 73)      # Dark navy
COLOR_PLAYER_EYE = (255, 255, 255)       # White pointer
COLOR_SHADOW = (0, 0, 0, 70)             # Semi-transparent black

# Minimum personal space separation between AI entities (px)
MIN_ENTITY_SEPARATION = 14.0
DOORWAY_CLEARANCE_RADIUS = 36.0

# Servant AI Settings
SERVANT_COUNT = 2
SERVANT_RADIUS = 20
SERVANT_SPEED = 220.0
SERVANT_CARRY_CAPACITY = 5
BUILD_DURATION_SECONDS = 5.0
DEMOLISH_DURATION_SECONDS = 5.0
DEMOLITION_REFUND_RATIO = 0.5  # 50% resource refund when demolishing buildings
ENTITY_AVOIDANCE_RADIUS = 56.0
SERVANT_YIELD_FORCE = 60.0
COLOR_SERVANT_BODY = (245, 158, 11)     # Amber orange
COLOR_SERVANT_OUTLINE = (120, 53, 15)   # Deep brown/amber outline

# Pathfinding Visualization & Predetermined Route Settings (Config-Driven, Zero Hardcode)
COLOR_PATH_VILLAGER = (34, 197, 94)      # Emerald green for villager path lines
COLOR_PATH_SERVANT = (245, 158, 11)      # Amber orange for servant path lines
COLOR_PATH_TARGET_RING = (56, 189, 248)  # Cyan for target destination reticle
PATH_LINE_WIDTH = 2
PATH_ARROW_SPACING = 36.0                # Distance in screen pixels between directional arrows
PATH_WAYPOINT_TOLERANCE = 14.0           # Waypoint arrival threshold
PATH_TOGGLE_BTN_WIDTH = 180
PATH_TOGGLE_BTN_HEIGHT = 32
COLOR_PATH_TOGGLE_ON = (16, 185, 129)        # Emerald green when active
COLOR_PATH_TOGGLE_OFF = (51, 65, 85)         # Slate gray when inactive
COLOR_PATH_TOGGLE_BORDER = (100, 116, 139)   # Border outline

# Obstacle-Aware Pathfinding & Stuck Recovery Settings
STUCK_THRESHOLD_SECONDS = 0.5           # Time with no progress before triggering stuck recovery
STUCK_MIN_PROGRESS_DISTANCE = 2.0       # Minimum distance moved in step to count as progress
STUCK_AVOIDANCE_DURATION = 3.0          # Time to remember a blocked node to prevent route oscillation
EMERGENCY_STUCK_TIMEOUT = 3.0           # Continuous seconds before triggering emergency recovery
EMERGENCY_COLLISION_BYPASS_DURATION = 0.8 # Duration (seconds) of collision bypass to unblock deadlock
PATH_SEGMENT_COLLISION_RADIUS = 12.0    # Radius margin for line-of-sight sweep validation
PATH_MAX_ASTAR_ITERATIONS = 1500        # Max A* iterations for extensive map searches
PATH_RESERVATION_CLEARANCE = 28.0      # Minimum clearance distance between two distinct path reservations
PATH_WAIT_RECHECK_INTERVAL = 0.25      # Interval in seconds to recheck path availability when waiting
PATH_RESERVATION_TIMEOUT = 12.0        # Stale reservation safety expiration timeout (seconds)

# AI Collision Sliding & Route Recovery (Agent 1)
COLLISION_SLIDE_TANGENT_FACTOR = 1.0     # Strength of tangential deflection when encountering colliding AI
COLLISION_MIN_SEPARATION = 6.0          # Separation buffer between AI collision radii
COLLISION_SLIDE_SMOOTHING = 0.65        # Smoothing factor for directional slide transitions
ROUTE_REQUEST_TIMEOUT = 2.0             # Automatic timeout (sim seconds) to recover pending route requests
ROUTE_MAX_RETRIES = 3                   # Max route retry attempts before fallback
ROUTE_RETRY_BACKOFF = 0.25              # Initial backoff delay for retrying route requests
ROUTE_FALLBACK_COOLDOWN = 1.5           # Cooldown before re-attempting an unreachable destination

# Route Request Lifecycle States
ROUTE_STATE_NONE = "NONE"
ROUTE_STATE_REQUESTED = "REQUESTED"
ROUTE_STATE_PROCESSING = "PROCESSING"
ROUTE_STATE_ASSIGNED = "ASSIGNED"
ROUTE_STATE_ACTIVE = "ACTIVE"
ROUTE_STATE_COMPLETED = "COMPLETED"
ROUTE_STATE_FAILED = "FAILED"

# Tile Occupancy, Narrow Doorways & Passage Management (Agent 1)
DOORWAY_IDLE_MIN_DISTANCE = 48.0          # Minimum distance (px) AI must keep from any doorway when idling/wandering
DOORWAY_QUEUE_LATERAL_OFFSET = 36.0       # Lateral offset (px) for doorway queueing to clear passage line
TILE_OCCUPANCY_TIMEOUT = 5.0              # Timeout (seconds) for physical tile occupancy tracking
TILE_STEP_RESERVATION_TIMEOUT = 1.5       # Timeout (seconds) for step reservation ahead
NARROW_PASSAGE_WAIT_DISTANCE = 32.0       # Distance to halt outside narrow passage when opposing AI is traversing

# Villager & Family Settings
VILLAGER_RADIUS = 20
VILLAGER_SPEED = 180.0
VILLAGER_CARRY_CAPACITY = 5
WATERING_DURATION_SECONDS = 2.0
DOORWAY_WAYPOINT_DISTANCE = 24.0
DEFAULT_PLOT_MAX_WORKERS = 2

# Farming Task Durations & Dispersion Settings (Config-Driven, Zero Hardcode)
WATERING_DURATION_INGAME_HOURS = 0.5   # 30 in-game minutes per tile
TILLING_DURATION_INGAME_HOURS = 1.0    # 1 in-game hour per tile
FARM_TILE_PROXIMITY_PENALTY_ADJACENT = 3000.0  # Heavy penalty for tiles adjacent to other active workers (< 1.5 grid units)
FARM_TILE_PROXIMITY_PENALTY_NEAR = 1500.0      # Penalty for tiles within 2.5 grid units
FARM_TILE_ARRIVAL_DIST = 20.0                  # Arrival radius inside target work tile
INTERACTION_CONTACT_RADIUS = 58.0              # Contact pickup distance (allowing adjacent tile pickup without clipping)
TOOL_STOW_ARRIVAL_DIST = 36.0                  # Arrival distance to household chest when returning unused tools
LOOSE_ITEM_ARRIVAL_DIST = 24.0                 # Arrival distance for gathering loose items
CHEST_INTERACTION_RADIUS = 36.0                # Interaction distance with household chest
FURNITURE_CLAIM_BED_SEARCH_RADIUS = 8.5        # Max tile distance to infer chest household ownership from beds
COLOR_VILLAGER_BODY = (34, 197, 94)     # Forest/Emerald green (Peasant tunic)
COLOR_VILLAGER_OUTLINE = (20, 83, 45)   # Deep forest green
VILLAGER_SURNAMES = [
    "Miller", "Fletcher", "Smith", "Cooper", "Baker",
    "Tanner", "Ward", "Carter", "Mason", "Thatcher",
    "Weaver", "Shepherd", "Potter", "Fisher", "Brewer"
]
VILLAGER_MALE_NAMES = [
    "Arthur", "John", "Thomas", "William", "Robert",
    "Edward", "Henry", "Walter", "Hugh", "Geoffrey"
]
VILLAGER_FEMALE_NAMES = [
    "Mary", "Alice", "Agnes", "Joan", "Margaret",
    "Emma", "Matilda", "Eleanor", "Beatrice", "Cecily"
]
DEDICATED_JOBS = {
    "Farmer": {
        "id": "Farmer",
        "name": "Farmer",
        "title": "Peasant Farmer",
        "color": (34, 197, 94),
        "wip": False,
        "workplace_permit": "farm",
        "desc": "Tends crops and agricultural plots; waters and harvests food.",
        "required_tools": ["Hoe", "Watering_Can", "Sickle"]
    },
    "Builder": {
        "id": "Builder",
        "name": "Builder",
        "title": "Village Builder",
        "color": (245, 158, 11),
        "wip": False,
        "workplace_permit": "construction",
        "desc": "Constructs buildings, infrastructure, and structural works.",
        "required_tools": ["Hammer"]
    },
    "Blacksmith": {
        "id": "Blacksmith",
        "name": "Blacksmith",
        "title": "Village Blacksmith (WIP)",
        "color": (239, 68, 68),
        "wip": True,
        "workplace_permit": "smithy",
        "desc": "Forges iron tools, nails, and armor for the settlement.",
        "required_tools": ["Hammer", "Tongs"]
    },
    "Carpenter": {
        "id": "Carpenter",
        "name": "Carpenter",
        "title": "Wood Carpenter (WIP)",
        "color": (234, 179, 8),
        "wip": True,
        "workplace_permit": "workshop",
        "desc": "Crafts furniture, structural beams, and wooden barrels.",
        "required_tools": ["Saw", "Adze"]
    },
    "Baker": {
        "id": "Baker",
        "name": "Baker",
        "title": "Village Baker (WIP)",
        "color": (249, 115, 22),
        "wip": True,
        "workplace_permit": "bakery",
        "desc": "Mills grain and bakes daily bread loaves for villagers.",
        "required_tools": ["Rolling_Pin", "Peel"]
    },
    "Fisherman": {
        "id": "Fisherman",
        "name": "Fisherman",
        "title": "Coastal Fisherman (WIP)",
        "color": (56, 189, 248),
        "wip": True,
        "workplace_permit": "fishery",
        "desc": "Catches fish and gathers seafood at village docks and shores.",
        "required_tools": ["Fishing_Rod"]
    },
    "Priest": {
        "id": "Priest",
        "name": "Priest",
        "title": "Village Priest",
        "color": (168, 85, 247),
        "wip": False,
        "workplace_permit": "church",
        "desc": "Conducts daily prayer and collects church taxes at the village church.",
        "required_tools": []
    },
    "Gravedigger": {
        "id": "Gravedigger",
        "name": "Gravedigger",
        "title": "Cemetery Gravedigger",
        "color": (100, 116, 139),
        "wip": False,
        "workplace_permit": "cemetery",
        "desc": "Prepares graves and buries deceased villagers in the cemetery.",
        "required_tools": ["Hoe"]
    }
}

# Days of the Week Schedule
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# 24-Hour Schedule System (RimWorld-Style Activity Management)
SCHEDULE_WORK = "WORK"
SCHEDULE_LEISURE = "LEISURE"
SCHEDULE_SLEEP = "SLEEP"
SCHEDULE_ANY = "ANY"
SCHEDULE_PRAYER = "PRAYER"

SCHEDULE_TYPES = {
    "WORK": {
        "id": "WORK",
        "name": "Work",
        "color": (59, 130, 246),       # Bright blue
        "desc": "Mandatory labor: tending farm crops, harvesting, or crafting at workplace."
    },
    "LEISURE": {
        "id": "LEISURE",
        "name": "Leisure",
        "color": (34, 197, 94),        # Emerald green
        "desc": "Rest, stroll around town, chat with villagers, and recreate."
    },
    "SLEEP": {
        "id": "SLEEP",
        "name": "Sleep",
        "color": (147, 51, 234),       # Royal purple
        "desc": "Sleep inside family home to restore energy."
    },
    "ANY": {
        "id": "ANY",
        "name": "Anything",
        "color": (100, 116, 139),      # Slate gray
        "desc": "Work if unfinished tasks remain; otherwise relax and rest."
    },
    "PRAYER": {
        "id": "PRAYER",
        "name": "Prayer",
        "color": (234, 179, 8),        # Radiant gold
        "desc": "Mandatory church prayer time decreed by the Priest."
    }
}

DEFAULT_JOB_SCHEDULE = [
    # 00:00 - 05:00: Night Sleep
    "SLEEP", "SLEEP", "SLEEP", "SLEEP", "SLEEP", "SLEEP",
    # 06:00 - 07:00: Morning Preparation / Leisure
    "LEISURE", "LEISURE",
    # 08:00 - 17:00: Prime Daytime Labor (10 hours)
    "WORK", "WORK", "WORK", "WORK", "WORK", "WORK", "WORK", "WORK", "WORK", "WORK",
    # 18:00 - 21:00: Evening Dinner & Leisure
    "LEISURE", "LEISURE", "LEISURE", "LEISURE",
    # 22:00 - 23:00: Bedtime Sleep
    "SLEEP", "SLEEP"
]

# Soil & Crop Visuals
COLOR_SOIL_DRY = (115, 80, 50, 130)
COLOR_SOIL_WET = (50, 32, 16, 230)
COLOR_WATER_SHEEN = (125, 211, 252, 160)
COLOR_CROP_WITHERED = (140, 120, 85)

# UI HUD Colors
COLOR_HUD_BG = (15, 23, 42, 220)
COLOR_HUD_BORDER = (51, 65, 85)
COLOR_TEXT_TITLE = (56, 189, 248)
COLOR_TEXT_MAIN = (241, 245, 249)
COLOR_TEXT_MUTED = (148, 163, 184)
COLOR_KBD_BG = (51, 65, 85)

# Resource System & HUD Settings
DEFAULT_RESOURCES = {
    "Wood": 1000,
    "Food": 1000,
    "Stone": 1000,
    "Water": 1000,
    "Copper": 1000,
    "Silver": 1000,
    "Gold": 1000,
}
MAX_STACK_SIZE = 100
MAX_TILE_CAPACITY = 1000  # Up to 10 stacks of 100 per tile (kotak)

# Currency & Economy System Settings (Config-Driven, Zero Hardcode)
DENOMINATION_CAP = 1000
CURRENCY_DENOMINATIONS = ["Copper", "Silver", "Gold"]
EXCHANGE_RATES = {
    "Copper": 1,       # 1 Copper = 1 Copper (base monetary unit)
    "Silver": 10,      # 1 Silver = 10 Copper
    "Gold": 100,       # 1 Gold = 100 Copper = 10 Silver
}
DEFAULT_ITEM_PRICES = {
    "Potato": 3,       # 1 Potato = 3 Copper (Configurable default price)
    "Wood": 2,         # 1 Wood = 2 Copper
    "Stone": 3,        # 1 Stone = 3 Copper
}

# -----------------------------------------------------------------------------
# GENERIC ITEM CATEGORY DEFINITIONS (Single Source of Truth - No Hardcoding)
# -----------------------------------------------------------------------------
ITEM_CATEGORIES = {
    # FOOD
    "Potato": "FOOD",
    "potato": "FOOD",
    "Food": "FOOD",
    "food": "FOOD",
    "Bread": "FOOD",
    "bread": "FOOD",
    "Carrot": "FOOD",
    "carrot": "FOOD",
    "Cabbage": "FOOD",
    "cabbage": "FOOD",
    "Wheat": "FOOD",
    "wheat": "FOOD",
    "Fish": "FOOD",
    "fish": "FOOD",
    "Meat": "FOOD",
    "meat": "FOOD",
    "Apple": "FOOD",
    "apple": "FOOD",

    # WATER
    "Water": "WATER",
    "water": "WATER",

    # TOOLS
    "Hoe": "TOOL",
    "Sickle": "TOOL",
    "Watering_Can": "TOOL",
    "Watering Can": "TOOL",
    "Hammer": "TOOL",
    "Tongs": "TOOL",
    "Saw": "TOOL",
    "Adze": "TOOL",
    "Rolling_Pin": "TOOL",
    "Peel": "TOOL",
    "Fishing_Rod": "TOOL",

    # RESOURCES
    "Wood": "RESOURCE",
    "Stone": "RESOURCE",
    "Timber": "RESOURCE",
    "Carved Stone": "RESOURCE",
    "Linen Cloth": "RESOURCE",

    # CURRENCY
    "Copper": "CURRENCY",
    "Silver": "CURRENCY",
    "Gold": "CURRENCY",
    "Copper Coin": "CURRENCY",
    "Silver Coin": "CURRENCY",
    "Gold Coin": "CURRENCY",
}

def register_item_category(item_name: str, category: str):
    """
    Dynamically register or update an item's category.
    Allows new items (e.g. newly modded or planted crops/foods) to be registered at runtime.
    """
    if item_name and category:
        ITEM_CATEGORIES[str(item_name).strip()] = str(category).strip().upper()

def get_item_category(item_name: str) -> str:
    """
    Returns the generic category of an item ('FOOD', 'WATER', 'TOOL', 'RESOURCE', 'CURRENCY', or 'MISC').
    Case-insensitive fallback is applied.
    """
    if not item_name:
        return "MISC"
    cat = ITEM_CATEGORIES.get(item_name)
    if cat:
        return cat
    low = str(item_name).strip().lower()
    for k, v in ITEM_CATEGORIES.items():
        if k.lower() == low:
            return v
    return "MISC"

def is_food_item(item_name: str) -> bool:
    """
    Generic verification if an item belongs to the FOOD category.
    Zero hardcoded item names!
    """
    return get_item_category(item_name) == "FOOD"

def is_water_item(item_name: str) -> bool:
    """
    Generic verification if an item belongs to the WATER category.
    """
    return get_item_category(item_name) == "WATER"


RESOURCE_COLORS = {
    "Wood": (180, 120, 70),     # Wood brown
    "Food": (234, 179, 8),      # Golden food grain
    "Stone": (148, 163, 184),   # Slate stone
    "Water": (56, 189, 248),    # Fresh water blue
    "Potato": (194, 120, 60),   # Russet brown potato
    "Hoe": (202, 138, 4),       # Iron & wood hoe
    "Sickle": (168, 85, 247),   # Curved steel sickle
    "Watering_Can": (180, 105, 55), # Medieval copper/clay sprinkler pot
    "Copper": (184, 115, 51),   # Copper coin bronze
    "Silver": (203, 213, 225),  # Silver coin shine
    "Gold": (250, 204, 21),     # Gold coin luster
    "Copper Coin": (184, 115, 51),
    "Silver Coin": (203, 213, 225),
    "Gold Coin": (250, 204, 21),
}

TOOL_TYPES = {
    "Hoe": {
        "id": "Hoe",
        "name": "Hoe",
        "icon": "⛏",
        "color": (202, 138, 4),
        "desc": "Forged iron farming hoe for tilling soil and sowing crop seeds."
    },
    "Sickle": {
        "id": "Sickle",
        "name": "Sickle",
        "icon": "🌾",
        "color": (168, 85, 247),
        "desc": "Curved steel harvesting sickle for reaping ripe agricultural crops."
    },
    "Watering_Can": {
        "id": "Watering_Can",
        "name": "Watering Can",
        "icon": "🏺",
        "color": (180, 105, 55),
        "desc": "Medieval copper sprinkler pot (chantepleure) for irrigating crops."
    },
    "Hammer": {
        "id": "Hammer",
        "name": "Hammer",
        "icon": "🔨",
        "color": (148, 163, 184),
        "desc": "Heavy iron construction hammer for raising structures and masonry."
    },
    "Tongs": {
        "id": "Tongs",
        "name": "Tongs",
        "icon": "🛠",
        "color": (100, 116, 139),
        "desc": "Forged iron tongs for holding red-hot iron on the smithy anvil."
    },
    "Saw": {
        "id": "Saw",
        "name": "Saw",
        "icon": "🪚",
        "color": (217, 119, 6),
        "desc": "Steel carpenter saw for cutting structural timber and planks."
    },
    "Adze": {
        "id": "Adze",
        "name": "Adze",
        "icon": "🪓",
        "color": (180, 83, 9),
        "desc": "Curved woodworking adze for dressing beams and shaping wood."
    },
    "Rolling_Pin": {
        "id": "Rolling_Pin",
        "name": "Rolling Pin",
        "icon": "🥖",
        "color": (245, 158, 11),
        "desc": "Hardwood rolling pin for flattening dough in the bakery."
    },
    "Peel": {
        "id": "Peel",
        "name": "Baker's Peel",
        "icon": "🍞",
        "color": (217, 119, 6),
        "desc": "Broad wooden paddle for loading and removing loaves from the stone oven."
    },
    "Fishing_Rod": {
        "id": "Fishing_Rod",
        "name": "Fishing Rod",
        "icon": "🎣",
        "color": (14, 165, 233),
        "desc": "Flexible ash-wood rod with line and hook for catching fish."
    }
}

DEFAULT_STARTER_TOOLS = {
    "Hoe": 10,
    "Sickle": 10,
    "Watering_Can": 10,
    "Hammer": 5
}

def get_job_required_tools(job_id):
    """Mendapatkan daftar alat yang dibutuhkan oleh profesi/pekerjaan secara data-driven"""
    job_cfg = DEDICATED_JOBS.get(job_id)
    if job_cfg and "required_tools" in job_cfg:
        return list(job_cfg["required_tools"])
    return []

def is_tool_item(item_name):
    """Mengecek apakah suatu nama item merupakan alat kerja terdaftar"""
    return item_name in TOOL_TYPES

RES_HUD_WIDTH = 180
RES_HUD_MARGIN = 16

# Raport & Building Colors
COLOR_RAPORT_BTN_BG = (30, 41, 59, 230)
COLOR_RAPORT_BTN_BORDER = (56, 189, 248)
COLOR_MODAL_BG = (15, 23, 42, 245)
COLOR_MODAL_BORDER = (71, 85, 105)
COLOR_TAB_ACTIVE = (37, 99, 235)
COLOR_TAB_INACTIVE = (30, 41, 59)
COLOR_BADGE_WIP = (245, 158, 11)
COLOR_BADGE_PARTIAL = (234, 179, 8)
COLOR_BADGE_IMPLEMENTED = (34, 197, 94)

# Modal Dimensions
RAPORT_MODAL_WIDTH = 860
RAPORT_MODAL_HEIGHT = 500
SETTINGS_MODAL_WIDTH = 640
SETTINGS_MODAL_HEIGHT = 440

# Game Speed & Simulation Settings
SPEED_LEVELS = [
    {"id": "very_slow", "name": "Very Slow", "short_label": "¼×", "speed": 0.25, "key_label": "1"},
    {"id": "slow", "name": "Slow", "short_label": "½×", "speed": 0.5, "key_label": "2"},
    {"id": "normal", "name": "Normal", "short_label": "1×", "speed": 1.0, "key_label": "3"},
    {"id": "fast", "name": "Fast", "short_label": "2×", "speed": 2.0, "key_label": "4"},
    {"id": "very_fast", "name": "Very Fast", "short_label": "4×", "speed": 4.0, "key_label": "5"},
]
DEFAULT_SPEED_INDEX = 2  # Normal (1.0x)

# Day Length Settings (Configurable In-Game Day Duration)
DAY_LENGTH_OPTIONS = [
    {"id": "10_min", "label": "10 minutes per day", "short_label": "10 Min", "seconds": 600.0},
    {"id": "20_min", "label": "20 minutes per day", "short_label": "20 Min (Normal)", "seconds": 1200.0},
    {"id": "30_min", "label": "30 minutes per day", "short_label": "30 Min", "seconds": 1800.0},
]
DEFAULT_DAY_LENGTH_INDEX = 1  # 20 minutes default (1200.0 seconds)
STARTING_HOUR = 8.0
NIGHT_START_HOUR = 20
NIGHT_END_HOUR = 5

# RimWorld-Style Work Priorities Configuration
WORK_TYPES = [
    {"id": "Building", "name": "Building", "wip": False, "desc": "Construct & demolish buildings."},
    {"id": "Hauling", "name": "Hauling", "wip": False, "desc": "Haul loose items to storage & materials to sites."},
    {"id": "Cleaning", "name": "Cleaning (WIP)", "wip": True, "desc": "Sweep debris and dirt."},
    {"id": "Crafting", "name": "Crafting (WIP)", "wip": True, "desc": "Produce tools and goods."},
    {"id": "Cooking", "name": "Cooking (WIP)", "wip": True, "desc": "Prepare meals and rations."},
]
DEFAULT_PRIORITIES = {"Building": 1, "Hauling": 1, "Cleaning": 0, "Crafting": 0, "Cooking": 0}
PRIORITY_COLORS = {
    1: (34, 197, 94),     # High Priority (Green)
    2: (59, 130, 246),    # Normal Priority (Blue)
    3: (234, 179, 8),     # Low Priority (Yellow)
    4: (148, 163, 184),   # Lowest Priority (Gray)
    0: (71, 85, 105)      # Disabled / Off (Dark Slate)
}

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
        "category": "Structure",
        "category_id": "structure",
        "desc": "Fresh water well built of masonry and timber. Impenetrable 4-tile solid structure.",
        "cost_wood": 5,
        "cost_stone": 20,
        "fixed_cost": True,
        "fixed_tiles_count": 4,
        "is_solid": True,
        "has_door": False,
        "color": (56, 189, 248),
        "border_color": (96, 165, 250),
        "required_permit": "any",
        "allowed_permits": ["housing", "storage", "landlord_private", "church"],
    },
    "market": {
        "id": "market",
        "name": "Market",
        "category": "Structure",
        "category_id": "structure",
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
    },
    "toilet": {
        "id": "toilet",
        "name": "Toilet",
        "category": "Structure",
        "category_id": "structure",
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
    }
}
# Backward compatibility aliases
BUILDING_TYPES["house"] = BUILDING_TYPES["wooden_structure"]
BUILDING_TYPES["storage"] = BUILDING_TYPES["wooden_structure"]
BUILDING_TYPES["manor"] = BUILDING_TYPES["stone_structure"]

def get_building_categories():
    """
    Returns the two primary building and furnishings categories: Structure and Furniture.
    Preserves config-driven architecture: zero hardcoding in UI.
    Automatically incorporates newly registered building and structure types into Structure.
    """
    structure_types = [b_id for b_id in BUILDING_TYPES if b_id not in ("house", "storage", "manor")]
    return [
        {
            "id": "structure",
            "name": "Structure",
            "desc": "All building blueprints including Wooden, Stone, Water Well, Market, Toilet, and civic structures.",
            "color": (59, 130, 246),
            "kind": "structure",
            "building_types": structure_types
        },
        {
            "id": "furniture",
            "name": "Furniture",
            "desc": "All furniture blueprints including storage chests, beds, and interior living fixtures.",
            "color": (250, 204, 21),
            "kind": "furniture",
            "building_types": list(FURNITURE_TYPES.keys())
        }
    ]

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

def get_permit_categories():
    """
    Returns dynamically discovered categories from PERMIT_TYPES.
    Preserves config-driven architecture: zero hardcoding in UI.
    Automatically incorporates newly registered permit types.
    """
    categories = {}
    for p_id, p_cfg in PERMIT_TYPES.items():
        cat_id = p_cfg.get("category_id", p_id)
        if cat_id not in categories:
            categories[cat_id] = {
                "id": cat_id,
                "name": p_cfg.get("category", p_cfg.get("name", cat_id.capitalize())),
                "desc": p_cfg.get("desc", ""),
                "color": p_cfg.get("border_color", (59, 130, 246)),
                "permit_types": []
            }
        if p_id not in categories[cat_id]["permit_types"]:
            categories[cat_id]["permit_types"].append(p_id)
    return list(categories.values())

# Agricultural Crops System (Cultivated on Farm Permits)
FARMING_BATCH_GROWTH_DAYS = 10.0
FARMING_BATCH_WINDOW_DAYS = 1.0  # 1 in-game day default planting window

CROP_TYPES = {
    "potato": {
        "id": "potato",
        "name": "Potato",
        "icon": "🥔",
        "wip": False,
        "desc": "Hearty staple tuber crop. Produces exactly 2 potatoes per tile every 10 days.",
        "growth_days": 10.0,
        "sprout_day": 2.0,
        "leaf_day": 4.0,
        "harvest_day": 10.0,
        "yield_per_tile": 2,
        "yield": 2,
        "yield_chance_2": 0.0
    },
    "wheat": {
        "id": "wheat",
        "name": "Wheat (WIP)",
        "icon": "🌾",
        "wip": True,
        "desc": "Golden cereal grain for milling flour and bread."
    },
    "carrot": {
        "id": "carrot",
        "name": "Carrot (WIP)",
        "icon": "🥕",
        "wip": True,
        "desc": "Sweet orange root vegetable."
    },
    "corn": {
        "id": "corn",
        "name": "Corn (WIP)",
        "icon": "🌽",
        "wip": True,
        "desc": "Tall sweet maize stalks."
    }
}

# Furniture System (Household Storage & Furnishings)
FURNITURE_TYPES = {
    "household_storage": {
        "id": "household_storage",
        "name": "Household Storage",
        "desc": "Wooden storage chest for a family's crops and goods. Placed inside a house or lot.",
        "cost_wood": 10,
        "cost_stone": 0,
        "capacity": 500,
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
        "cost_wood": 5,
        "cost_stone": 0,
        "capacity": 0,
        "width_tiles": 1,
        "height_tiles": 1,
        "color_frame": (139, 90, 43),
        "color_blanket": (59, 130, 246),
        "color_pillow": (241, 245, 249)
    }
}

# =====================================================================
# Needs, Survival & Household Consumption System (Agent 1)
# =====================================================================
AI_NEED_MAX = 100.0
AI_NEED_HUNGER_DECAY_PER_DAY = 100.0   # Decays by 100% per 1 full in-game day (1200 seconds)
AI_NEED_THIRST_DECAY_PER_DAY = 100.0   # Decays by 100% per 1 full in-game day
AI_CRITICAL_NEED_THRESHOLD = 20.0      # Critical threshold (<= 20%) triggering task interruption
AI_DEATH_COUNTDOWN_HOURS = 24.0        # 24 in-game hours before death occurs when a need reaches 0%
DAILY_FOOD_REQUIREMENT = 1             # 1 food per day per living individual
DAILY_WATER_REQUIREMENT = 1            # 1 water per day per living individual
AI_NEED_FOOD_RESTORE = 100.0           # Need restored when consuming food
AI_NEED_WATER_RESTORE = 100.0          # Need restored when drinking water
HOUSEHOLD_WATER_MAX_COLLECTORS = 2     # Maximum concurrent household members hauling water

# Visual Colors for Needs & Corpse States
COLOR_NEED_HUNGER_HIGH = (34, 197, 94)    # Green (Fulfilling)
COLOR_NEED_HUNGER_MED = (234, 179, 8)     # Yellow (Moderate)
COLOR_NEED_HUNGER_LOW = (239, 68, 68)     # Red (Critical Starvation)
COLOR_NEED_THIRST_HIGH = (56, 189, 248)   # Cyan / Sky Blue (Hydrated)
COLOR_NEED_THIRST_MED = (59, 130, 246)    # Blue (Moderate)
COLOR_NEED_THIRST_LOW = (239, 68, 68)     # Red (Critical Dehydration)
COLOR_STATUS_ALIVE = (34, 197, 94)
COLOR_STATUS_DECEASED = (148, 163, 184)
COLOR_CORPSE_BODY = (100, 116, 139)       # Desaturated slate gray for deceased villagers
COLOR_CORPSE_OUTLINE = (51, 65, 85)

# =====================================================================
# Church, Priest, Cemetery, Gravedigger & Toilet Systems (Agent 3)
# =====================================================================
DEFAULT_CHURCH_TAX = {"Gold": 0, "Silver": 0, "Copper": 1}  # 1 Copper per household per day default

GRAVEDIGGER_TARGET_WOOD = 5
GRAVEDIGGER_TARGET_STONE = 5
GRAVE_COST_WOOD = 1
GRAVE_COST_STONE = 1
GRAVE_DIG_HOURS = 1.0           # Exactly 1 in-game hour digging
GRAVE_BURY_HOURS = 0.5          # Exactly 30 in-game minutes burial
GRAVE_REUSE_DAYS = 30.0         # Reusable after 30 in-game days
BURIAL_FEE_MAX_SILVER = 1       # Up to 1 Silver (10 Copper)
CORPSE_CARRY_SPEED_RATIO = 0.5  # 50% speed while carrying corpse
TOMBSTONE_MODELS_COUNT = 5      # At least 5 distinct tombstone variants

AI_NEED_TOILET_DECAY_PER_DAY = 150.0   # Decays over time to trigger urgent need ~1-2 times daily
AI_NEED_TOILET_URGENT_THRESHOLD = 20.0 # <= 20% triggers toilet seeking
AI_NEED_TOILET_RESTORE = 100.0         # Restored when using toilet
TOILET_USE_DURATION_HOURS = 0.25       # 15 in-game minutes


