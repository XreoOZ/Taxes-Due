"""
Configuration and Global Constants
"""

import sys
from game.data.catalog import (
    ARTISAN_JOB_IDS, BUILDER_DEFAULT_LIVING_HOUSEHOLD_SIZE, BUILDER_TOOL_SWING_ANGLE, BUILDER_TOOL_SWING_SPEED, COLOR_CROP_WITHERED, COLOR_SOIL_DRY,
    COLOR_SOIL_WET, COLOR_WATER_SHEEN, COMMISSION_CLAIM_RETRY_SECONDS, CROP_TYPES, DAYS_OF_WEEK, DEDICATED_JOBS,
    DEFAULT_COMMISSION_ARTISAN_JOB, DEFAULT_JOB_SCHEDULE, DEFAULT_PLOT_MAX_WORKERS, DEFAULT_PRAYER_END_HOUR, DEFAULT_PRAYER_START_HOUR, DEFAULT_PRIORITIES,
    DEFAULT_STARTER_TOOLS, FARMING_BATCH_GROWTH_DAYS, FARMING_BATCH_WINDOW_DAYS, FARM_TILE_ARRIVAL_DIST, FARM_TILE_DISPERSION_ENABLED, FARM_TILE_PROXIMITY_PENALTY_ADJACENT,
    FARM_TILE_PROXIMITY_PENALTY_NEAR, FREE_TIME_SCHEDULE_ACTIVITIES, FURNITURE_CLAIM_BED_SEARCH_RADIUS, ITEM_CATEGORIES, PRIORITY_COLORS, RESOURCE_COLORS,
    SCHEDULE_ACTIVITY_CANCEL_ON_BOUNDARY, SCHEDULE_ACTIVITY_NEUTRAL_TASKS, SCHEDULE_ACTIVITY_STRICT_TASKS, SCHEDULE_ACTIVITY_STRICT_TASK_PREFIXES, SCHEDULE_ACTIVITY_STRICT_TASK_PREFIX_EXEMPTIONS, SCHEDULE_ACTIVITY_TASKS,
    SCHEDULE_ACTIVITY_TASK_PREFIXES, SCHEDULE_ACTIVITY_TASK_STATE_FIELDS, SCHEDULE_ANY, SCHEDULE_LEISURE, SCHEDULE_NON_WORK_TASKS, SCHEDULE_PRAYER,
    SCHEDULE_SLEEP, SCHEDULE_TYPES, SCHEDULE_WORK, STARTER_FAMILY_SIZE, STARTER_PRESETS, TILLING_DURATION_INGAME_HOURS,
    TOOLMAKER_BAR_DAILY_CAP, TOOLMAKER_BAR_RECIPE, TOOLMAKER_BAR_SMELT_INGAME_MINUTES, TOOLMAKER_BAR_STOCK_TARGET, TOOLMAKER_TOOL_MAX_INGAME_HOURS, TOOLMAKER_TOOL_MIN_INGAME_HOURS,
    TOOLMAKER_TOOL_RECIPE, TOOL_CONDITION_CHECK_EVERY_DAYS, TOOL_CONDITION_DEGRADE_CHANCE, TOOL_CONDITION_STAGES, TOOL_TYPES, TREE_WOOD_YIELD_MAX,
    TREE_WOOD_YIELD_MIN, VILLAGER_FEMALE_NAMES, VILLAGER_MALE_NAMES, VILLAGER_SURNAMES, WATERING_DURATION_INGAME_HOURS, WATERING_DURATION_SECONDS,
    WEEKDAY_NAMES, WOODSMAN_CUT_INGAME_HOURS, WOODSMAN_PLANT_INGAME_HOURS, WOODSMAN_WORKSTATION_TILES, WORKSTATION_DEFAULT_QUOTA_DAILY, WORKSTATION_MAX_WORKERS,
    WORKSTATION_QUOTA_STEP, WORK_TYPES,
)
from game.data.structures import (
    BUILDER_BUILD_DURATION_INGAME_HOURS, BUILDER_REPAIR_FOOD_DAYS, BUILDER_REPAIR_MATERIALS, BUILDING_TYPES, BUILDING_WALL_THICKNESS, BUILD_DURATION_SECONDS,
    BURIAL_FEE_MAX_SILVER, COLOR_BUILDING_DOOR, COLOR_BUILDING_FLOOR, COLOR_BUILDING_FLOOR_ALT, COLOR_BUILDING_WALL, COLOR_BUILDING_WALL_OUTLINE,
    COLOR_STONE_DOOR, COLOR_STONE_FLOOR, COLOR_STONE_FLOOR_ALT, COLOR_STONE_WALL, COLOR_STONE_WALL_OUTLINE, COST_PER_BLOCK_STONE,
    COST_PER_BLOCK_WOOD, DEMOLISH_DURATION_SECONDS, DEMOLITION_REFUND_RATIO, FURNITURE_DAILY_BREAK_CHANCE, FURNITURE_TYPES, GRAVEDIGGER_TARGET_STONE,
    GRAVEDIGGER_TARGET_WOOD, GRAVE_BURY_HOURS, GRAVE_COST_STONE, GRAVE_COST_WOOD, GRAVE_DIG_HOURS, GRAVE_REUSE_DAYS,
    LORD_TREASURY_PLACEMENT_SEARCH_RADIUS, LORD_TREASURY_START_TILE, PERMIT_TYPES, PUBLIC_STRUCTURE_DAILY_BREAK_CHANCE, ROAD_PLACEMENT_BLOCKED, ROAD_TYPES,
    TOMBSTONE_MODELS_COUNT,
)
from game.data.economy import (
    BUILDER_INSUFFICIENT_LANDLORD_COIN_MESSAGES, CHURCH_TAX_HAPPINESS_TIERS_COPPER, CURRENCY_DENOMINATIONS, DEFAULT_CHURCH_TAX, DEFAULT_ITEM_PRICES, DEFAULT_RESOURCES,
    DEFAULT_SOCAGE_TAX_ENABLED, DEFAULT_SOCAGE_TAX_PERCENT, DENOMINATION_CAP, EXCHANGE_RATES, HAPPINESS_WEALTH_DENOMINATION, HOUSEHOLD_STALL_HAUL_CAPACITY,
    MARKET_CURRENCY_DENOMINATIONS, MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT, MARKET_PERCENT_STEP, MARKET_QUANTITY_DEFAULT, MARKET_QUANTITY_MAX, MARKET_RESTOCK_ORDER_TIMEOUT_SECONDS, MARKET_SALES_REPORT_PERIOD_DAYS,
    MARKET_TRADEABLE_ITEMS, MARKET_WEALTH_CONTEXT_REFRESH_SECONDS, MARKET_WEALTH_PRICE_ELASTICITY, MARKET_WEALTH_PRICE_FACTOR_MAX, MARKET_WEALTH_PRICE_FACTOR_MIN, MARKET_WEALTH_REFERENCE_DAYS,
    MAX_STACK_SIZE, MAX_TILE_CAPACITY, NO_CHURCH_TAX_HAPPINESS_BONUS, SOCAGE_TAX_GREETING_LINES, SOCAGE_TAX_HAPPINESS_REPLIES, SOCAGE_TAX_HAPPINESS_TIERS,
    SOCAGE_TAX_INTERVAL_DAYS, SOCAGE_TAX_QUICK_STEP, TAX_COLLECTOR_STATION_ARRIVAL_DISTANCE, TAX_UNHAPPINESS_DURATION_DAYS, VILLAGER_HUD_COUNT_REFRESH_SECONDS, VILLAGER_INVENTORY_CAPACITY,
)


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
# Free-fly pan speed (world px/sec) while picking a starter village location
STARTER_PLACEMENT_PAN_SPEED = 700.0

# World Type Selection (New Game)
WORLD_TYPE_INFINITE = "infinite"
WORLD_TYPE_ISLAND = "island"
WORLD_TYPE_OPTIONS = [
    {"id": WORLD_TYPE_INFINITE, "label": "Infinite", "desc": "Endless procedural grassland. No edges, no borders."},
    {"id": WORLD_TYPE_ISLAND, "label": "Island", "desc": "A single landmass surrounded by water. Build within the shores."},
]
DEFAULT_WORLD_TYPE_INDEX = 0

# Island Terrain Settings
ISLAND_SEED_MIN = 1
ISLAND_SEED_MAX = 999999
ISLAND_RADIUS_X_TILES = 600
ISLAND_RADIUS_Y_TILES = 244
ISLAND_EDGE_NOISE_AMP = 0.16
ISLAND_BEACH_WIDTH = 0.07
COLOR_WATER_DEEP = (37, 99, 235)
COLOR_WATER_SHALLOW = (56, 130, 246)
COLOR_SAND = (221, 184, 112)

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
VILLAGER_MICRO_SEPARATION_DISTANCE = 1.2
VILLAGER_MICRO_SEPARATION_PUSH_DISTANCE = 1.5
VILLAGER_SLEEPING_SEPARATION_DISTANCE = 8.0
VILLAGER_SEPARATION_PASSES = 2
VILLAGER_SEPARATION_CELL_SIZE = 8.0
DOORWAY_CLEARANCE_RADIUS = 36.0

# AI decision updates are time-sliced independently from physics/rendering.
# The interval grows with population to keep per-simulated-second decision work scalable.
AI_DECISION_TICK_INTERVAL_SECONDS = 0.05
AI_DECISION_REFERENCE_POPULATION = 50
AI_DECISION_MAX_INTERVAL_SECONDS = 0.5
SERVANT_AI_DECISION_TICK_INTERVAL_SECONDS = AI_DECISION_TICK_INTERVAL_SECONDS
SIMULATION_PROFILE_REPORT_SECONDS = 5.0

# Servant AI Settings
SERVANT_COUNT = 2
SERVANT_RADIUS = 20
SERVANT_SPEED = 220.0
SERVANT_CARRY_CAPACITY = 50
# ESTABLISHED: the Landlord cannot act without servants, so a servant that
# keeps failing to reach its target must never soft-lock forever. After this
# many consecutive stuck recoveries the servant teleports to the nearest
# walkable tile around its destination (see servants.py stuck recovery).
SERVANT_STUCK_TELEPORT_THRESHOLD = 3
SERVANT_TELEPORT_SEARCH_RADIUS_TILES = 10
# Max anti-softlock teleports allowed per destination tile. Beyond this the
# servant abandons the task instead of bouncing between tiles forever.
SERVANT_MAX_TELEPORTS_PER_TARGET = 2
ENTITY_AVOIDANCE_RADIUS = 56.0
SERVANT_YIELD_FORCE = 60.0
# AI servants phase through walls/furniture/narrow passages: they still compute
# and follow normal A* paths, but skip building collision resolution so a 1-tile
# gap or wall edge can't permanently stall them. Player & villagers unaffected.
SERVANT_PHASE_THROUGH_OBSTACLES = True
# Radius (tiles) searched around an intended ground-drop/delivery point for
# the nearest villager-reachable tile, so dropped goods never land on water,
# inside solid structures, or on furniture footprints members cannot path to.
SERVANT_SAFE_DROP_SEARCH_RADIUS_TILES = 10
COLOR_SERVANT_BODY = (245, 158, 11)     # Amber orange
COLOR_SERVANT_OUTLINE = (120, 53, 15)   # Deep brown/amber outline

# Pathfinding Visualization & Predetermined Route Settings (Config-Driven, Zero Hardcode)
COLOR_PATH_VILLAGER = (34, 197, 94)      # Emerald green for villager path lines
COLOR_PATH_SERVANT = (245, 158, 11)      # Amber orange for servant path lines
COLOR_PATH_TARGET_RING = (56, 189, 248)  # Cyan for target destination reticle
PATH_LINE_WIDTH = 2
PATH_ARROW_SPACING = 36.0                # Distance in screen pixels between directional arrows
PATH_ARROW_HEAD_LENGTH = 8
PATH_ARROW_HEAD_WIDTH = 6
PATH_ROUTE_WAYPOINT_RADIUS = 3
COLOR_PATH_ROUTE = COLOR_PATH_TARGET_RING
COLOR_PATH_ROUTE_FAILED = (239, 68, 68)
PATH_WAYPOINT_TOLERANCE = 14.0           # Waypoint arrival threshold
PATH_STEER_LOOKAHEAD = 4                 # Waypoints ahead scanned for a clear straight-line shortcut
PATH_STEER_RESCAN_INTERVAL = 0.08        # Seconds between steering rescans per actor
PATH_DIAGONAL_STEP_COST = 1.4142135623730951
PATH_NEIGHBOR_OFFSETS = (
    (1, 0), (-1, 0), (0, 1), (0, -1),
    (1, 1), (1, -1), (-1, 1), (-1, -1),
)
NAVIGATION_RETRY_INTERVAL = 0.5          # Seconds before retrying an unreachable destination
NAVIGATION_BLOCKED_TILE_TIMEOUT = 8.0    # Seconds to avoid a tile that stopped an actor
NAVIGATION_BLOCKED_PROBE_DISTANCE = 48.0 # Distance ahead used to identify a blocked tile
PATH_TARGET_FALLBACK_OFFSETS = (
    (0, 1), (1, 0), (0, -1), (-1, 0),
    (1, 1), (-1, -1), (1, -1), (-1, 1),
)
PATH_TOGGLE_BTN_WIDTH = 180
PATH_TOGGLE_BTN_HEIGHT = 32
PATH_TOGGLE_BTN_MARGIN = 8
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
PATH_ROUTE_CACHE_MAX_ENTRIES = 4096
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
PLACEMENT_ORIENTATION_MARKER_LENGTH_RATIO = 0.34
PLACEMENT_ORIENTATION_MARKER_HEAD_RATIO = 0.42
PLACEMENT_ORIENTATION_MARKER_COLOR = (255, 255, 255)
PLACEMENT_ORIENTATION_MARKER_OUTLINE = (15, 23, 42)
DOORWAY_QUEUE_LATERAL_OFFSET = 36.0       # Lateral offset (px) for doorway queueing to clear passage line
TILE_OCCUPANCY_TIMEOUT = 5.0              # Timeout (seconds) for physical tile occupancy tracking
TILE_STEP_RESERVATION_TIMEOUT = 1.5       # Timeout (seconds) for step reservation ahead
NARROW_PASSAGE_WAIT_DISTANCE = 32.0       # Distance to halt outside narrow passage when opposing AI is traversing

# Villager & Family Settings
VILLAGER_RADIUS = 20
VILLAGER_SPEED = 180.0
DOORWAY_WAYPOINT_DISTANCE = 24.0
INTERACTION_CONTACT_RADIUS = 58.0              # Contact pickup distance (allowing adjacent tile pickup without clipping)
TOOL_STOW_ARRIVAL_DIST = 36.0                  # Arrival distance to household chest when returning unused tools
LOOSE_ITEM_ARRIVAL_DIST = 24.0                 # Arrival distance for gathering loose items
CHEST_INTERACTION_RADIUS = 36.0                # Interaction distance with household chest

# =====================================================================
# Natural Resources: Forest & Mines (Island world only)
# =====================================================================
# Values = trees per 10x10 forest-tile region (i.e. percent occupancy).
# *** ESTABLISHED — DO NOT REGRESS *** the old 3-40 range made forests look
# empty (measured 6-18% occupancy); ~10-95 gives visible woodland. The biome
# MASK coverage is controlled separately by FOREST_BIOME_* noise settings.
FOREST_DENSITY_TIERS = {
    1: {"name": "Scarce", "min": 10, "max": 16},
    2: {"name": "Sparse", "min": 20, "max": 32},
    3: {"name": "Moderate", "min": 38, "max": 55},
    4: {"name": "Dense", "min": 60, "max": 78},
    5: {"name": "Abundant", "min": 80, "max": 95},
}
FOREST_DENSITY_SAMPLE_AREA = 10          # density measured per NxN tile area
# Forest biome: seeded value-noise coverage across the whole island landmass
# (organic shapes like the coastline, not round blobs). Threshold is lowered
# per island forest tier to grow/shrink total coverage.
FOREST_BIOME_NOISE_FREQ = 0.018          # noise spatial frequency (lower = larger forests)
FOREST_BIOME_OCTAVE2_FREQ_MULT = 2.3     # second octave adds organic edges
FOREST_BIOME_OCTAVE2_WEIGHT = 0.35       # blend weight of the detail octave
FOREST_BIOME_THRESHOLD_BASE = 0.62       # Scarce coverage cutoff on [0,1] noise
FOREST_BIOME_THRESHOLD_STEP = 0.055      # threshold drop per tier (-> more forest)
FOREST_BIOME_MINE_CLEARING_TILES = 2     # no-forest margin around each mine footprint
FOREST_MAP_COLOR = (21, 128, 61)         # biome tint on the world map overlay
FOREST_TREE_CHUNK_TILES = 16             # spatial bucket size for tree rendering
FOREST_MOVE_SPEED_FACTOR = 0.7           # -30% movement speed on forest tiles
TREE_GROWTH_DAYS = 10.0                  # in-game days for a planted tree to mature

# Stone/ore mines: 5x5 pre-generated deposits scattered on the island.
MINE_SIZE_TILES = 5
MINE_SPAWN_COUNT_MIN = 10
MINE_SPAWN_COUNT_MAX = 14
MINE_SPAWN_GUARANTEE_TYPES = ("Stone Mine", "Iron Mine")  # one of each near spawn
MINE_SPAWN_GUARANTEE_DIST_MIN_TILES = 50  # nearest guaranteed mine distance band
MINE_SPAWN_GUARANTEE_DIST_MAX_TILES = 100
MINE_SPAWN_KIND_RATIO = {"Stone Mine": 3, "Iron Mine": 1}  # exact island-wide ratio
# Yield per in-game hour by tier (unlimited deposits; tier = speed only).
MINE_YIELD_PER_INGAME_HOUR = {
    1: {"name": "Scarce", "min": 1, "max": 1},
    2: {"name": "Low", "min": 1, "max": 2},
    3: {"name": "Normal", "min": 2, "max": 2},
    4: {"name": "Rich", "min": 3, "max": 4},
    5: {"name": "Abundant", "min": 4, "max": 4},
}
MINE_TYPE_TABLE = {
    "Stone Mine": {"output_item": "Stone", "color": (203, 213, 225)},
    "Iron Mine": {"output_item": "Iron Ore", "color": (249, 115, 22)},
}
COLOR_VILLAGER_BODY = (34, 197, 94)     # Forest/Emerald green (Peasant tunic)
COLOR_VILLAGER_OUTLINE = (20, 83, 45)   # Deep forest green
AI_ACTIVITY_PREVIEW_MAX_NEXT = 5
AI_PROFILE_HAPPINESS_VISIBLE_ROWS = 5
AI_PROFILE_ACTIVITY_ROW_HEIGHT = 14
AI_PROFILE_NEED_ROW_HEIGHT = 17
AI_PROFILE_CARD_WIDTH = 380
AI_PROFILE_ACTIVITY_OFFSET = 54
AI_PROFILE_DECEASED_ACTIVITY_OFFSET = 68
AI_PROFILE_ACTIVITY_HEADER_OFFSET = 30
AI_PROFILE_NEED_SECTION_GAP = 5
AI_PROFILE_INFO_SECTION_GAP = 2
AI_PROFILE_FACTOR_SECTION_GAP = 18
AI_PROFILE_FACTOR_PANEL_HEADER_HEIGHT = 22
AI_PROFILE_PANEL_BOTTOM_PADDING = 10
AI_ACTIVITY_NEXT_STEPS = {
    "SEEKING_FOOD": ("Eat available food or arrange a market purchase",),
    "BUYING_FOOD_RETRIEVE_COINS": (
        "Travel to the market", "Purchase food", "Return home and eat",
    ),
    "BUYING_FOOD_RETRIEVE_GROUND_COINS": (
        "Collect household coins", "Travel to the market", "Purchase food",
        "Return home and eat",
    ),
    "BUYING_FOOD_TRAVEL_TO_MARKET": (
        "Purchase food", "Return home and eat",
    ),
    "BUYING_FOOD_HAULING_HOME": ("Store food and eat",),
    "SEEKING_WATER": ("Collect or drink water",),
    "FETCHING_WATER": ("Drink collected water",),
    "SEEKING_TOILET": ("Use the toilet", "Release the toilet reservation"),
    "FETCHING_POSSESSION": ("Carry items home", "Store household items"),
    "HAULING_POSSESSION_HOME": ("Store household items",),
    "COLLECTING_HOUSEHOLD_WATER": ("Carry water home", "Store household water"),
    "HAULING_HOUSEHOLD_WATER": ("Store household water",),
    "FETCHING_FURNITURE": ("Carry furniture home", "Install furniture"),
    "FETCHING_DROPPED_FURNITURE": ("Carry furniture home", "Install furniture"),
    "HAULING_FURNITURE": ("Install furniture",),
    "HAULING_DROPPED_FURNITURE": ("Install furniture",),
    "RECOVER_DEATH_ITEMS": ("Return recovered items to household storage",),
    "SLEEPING": ("Continue sleeping until rested",),
    "ZONKED_SLEEP": ("Continue sleeping until the wake threshold",),
    "EQUIPPING_JOB_TOOLS": ("Travel to the workplace", "Perform the assigned job"),
    "TILLING": ("Water or harvest eligible crops",),
    "WATERING": ("Continue farming or return to other work",),
    "HARVESTING": ("Carry the harvest home", "Store the harvest"),
    "HAULING_HOME": ("Store the harvest",),
    "BUILDER_RESTOCK_RETRIEVE_COINS": (
        "Travel to the market", "Buy materials", "Carry materials to storage",
        "Resume Builder work",
    ),
    "BUILDER_RESTOCK_TRAVEL_TO_MARKET": (
        "Buy materials", "Carry materials to storage", "Resume Builder work",
    ),
    "BUILDER_RESTOCK_HAULING_HOME": (
        "Store materials", "Resume Builder work",
    ),
    "BUILDER_COLLECTING_MATERIALS": ("Deliver materials", "Continue construction or repair"),
    "BUILDER_DELIVERING_MATERIALS": ("Continue construction or repair",),
    "BUILDER_CONSTRUCTING": ("Continue construction",),
    "BUILDER_REPAIRING": ("Continue repair",),
    "CONFESSION_QUEUED": ("Wait for the Priest", "Approach the Priest", "Confess"),
    "WAITING_FOR_CONFESSION": ("Approach the Priest when called", "Confess"),
    "CONFESSION_RETRIEVE_COINS": ("Travel to the Priest", "Confess"),
    "CONFESSION_TRAVEL_TO_PRIEST": ("Meet the Priest", "Confess"),
    "GOING_TO_CONFESSOR": ("Meet the Priest", "Confess"),
    "GOING_TO_CONFESSION_BOX": ("Confess with the Priest",),
    "CONFESSING": ("Complete confession",),
    "COMMISSION_REFUND_COLLECT": ("Collect the refund", "Deliver it to the household"),
}

# UI HUD Colors
COLOR_HUD_BG = (15, 23, 42, 220)
COLOR_HUD_BORDER = (51, 65, 85)
COLOR_TEXT_TITLE = (56, 189, 248)
COLOR_TEXT_MAIN = (241, 245, 249)
COLOR_TEXT_MUTED = (148, 163, 184)
COLOR_KBD_BG = (51, 65, 85)

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

# Cheat Mode (ESC → Active Cheat → password)
CHEAT_PASSWORD = "bahlilkontol123"
CHEAT_MODAL_WIDTH = 560
CHEAT_MODAL_HEIGHT = 320

# Game Speed & Simulation Settings
SPEED_LEVELS = [
    {"id": "very_slow", "name": "Very Slow", "short_label": "¼×", "speed": 0.25, "key_label": "1"},
    {"id": "slow", "name": "Slow", "short_label": "½×", "speed": 0.5, "key_label": "2"},
    {"id": "normal", "name": "Normal", "short_label": "1×", "speed": 1.0, "key_label": "3"},
    {"id": "fast", "name": "Fast", "short_label": "2×", "speed": 2.0, "key_label": "4"},
    {"id": "very_fast", "name": "Very Fast", "short_label": "4×", "speed": 4.0, "key_label": "5"},
]
DEFAULT_SPEED_INDEX = 2  # Normal (1.0x)
# Cap on simulated game-time consumed per rendered frame. Prevents a
# hitched frame at high speed multipliers from queueing dozens of physics
# substeps and spiralling the FPS further down.
MAX_FRAME_GAME_DT = 0.15
SPEED_CONTROL_UI = {
    "font_button": 12,
    "font_sub": 9,
    "font_paused": 14,
    "panel_min_width": 320,
    "panel_height": 46,
    "panel_margin_x": 16,
    "panel_margin_y": 14,
    "panel_padding_x": 8,
    "panel_padding_y": 7,
    "panel_border_radius": 8,
    "button_height": 32,
    "button_border_radius": 6,
    "pause_button_width": 58,
    "pause_speed_gap": 6,
    "speed_button_width": 46,
    "speed_button_gap": 4,
    "right_padding": 2,
    "button_text_y": 7,
    "pause_tag_width": 140,
    "pause_tag_height": 28,
    "pause_tag_x_padding": 10,
    "pause_tag_y": 16,
    "pause_tag_text_y": 4,
    "colors": {
        "paused_bg": (220, 38, 38),
        "paused_border": (239, 68, 68),
        "paused_tag": (220, 38, 38, 220),
        "active_bg": (16, 185, 129),
        "active_border": (52, 211, 153),
        "pause_hover_bg": (40, 56, 80),
        "hover_bg": (51, 65, 85),
        "hover_border": (96, 165, 250),
        "idle_bg": (30, 41, 59),
        "idle_border": (71, 85, 105),
        "paused_text": (255, 255, 255),
        "hover_text": (255, 255, 255),
        "idle_text": (148, 163, 184),
        "pause_text": (203, 213, 225),
    },
}

# Day Length Settings (Configurable In-Game Day Duration)
DAY_LENGTH_OPTIONS = [
    {"id": "10_min", "label": "10 minutes per day", "short_label": "10 Min", "seconds": 600.0},
    {"id": "20_min", "label": "20 minutes per day", "short_label": "20 Min (Normal)", "seconds": 1200.0},
    {"id": "30_min", "label": "30 minutes per day", "short_label": "30 Min", "seconds": 1800.0},
]
DEFAULT_DAY_LENGTH_INDEX = 1  # 20 minutes default (1200.0 seconds)
DEFAULT_DAY_LENGTH_SECONDS = DAY_LENGTH_OPTIONS[DEFAULT_DAY_LENGTH_INDEX]["seconds"]
HOURS_PER_DAY = 24.0
MINUTES_PER_HOUR = 60
# Day 1 starts at 05:00 (dawn). *** ESTABLISHED — user-requested *** only
# affects NEW games; existing saves keep their stored clock.
STARTING_HOUR = 5.0
NIGHT_START_HOUR = 20
NIGHT_END_HOUR = 5
DAY_CYCLE_LIGHTING = {
    "daylight_start_hour": 6.0,
    "sunset_start_hour": 18.0,
    "sunrise_start_hour": 4.5,
    "sunset_start_color": (245, 140, 60),
    "sunset_end_color": (45, 40, 110),
    "sunset_alpha": (30, 100),
    "night_color": (15, 23, 42, 110),
    "sunrise_color": (251, 191, 36),
    "sunrise_alpha": 110,
}
# Placeable structures and furniture share quarter-turn rotation behavior.
for _building_config in BUILDING_TYPES.values():
    _building_config.setdefault("rotatable", True)
# Backward compatibility aliases
BUILDING_TYPES["house"] = BUILDING_TYPES["wooden_structure"]
BUILDING_TYPES["storage"] = BUILDING_TYPES["wooden_structure"]
BUILDING_TYPES["manor"] = BUILDING_TYPES["stone_structure"]

def get_building_categories():
    """
    Returns the top-level Building menu categories from asset configuration.
    """
    structure_types = [
        building_id for building_id, config in BUILDING_TYPES.items()
        if config.get("category_id", "structure") == "structure"
        and building_id not in ("house", "storage", "manor")
    ]
    public_building_types = [
        building_id for building_id, config in BUILDING_TYPES.items()
        if config.get("category_id") == "public_structure"
        and building_id not in ("house", "storage", "manor")
    ]
    public_furniture_types = [
        furniture_id for furniture_id, config in FURNITURE_TYPES.items()
        if config.get("category_id") == "public_structure"
    ]
    household_furniture_types = [
        furniture_id for furniture_id, config in FURNITURE_TYPES.items()
        if config.get("category_id", "furniture") == "furniture"
    ]
    workplace_building_types = [
        building_id for building_id, config in BUILDING_TYPES.items()
        if config.get("category_id") == "workplace"
    ]
    workplace_furniture_types = [
        furniture_id for furniture_id, config in FURNITURE_TYPES.items()
        if config.get("category_id") == "workplace"
    ]
    categories = {
        "structure": {
            "id": "structure",
            "name": "Structure",
            "desc": "Wooden and stone buildings.",
            "color": (59, 130, 246),
            "kind": "structure",
            "building_types": structure_types,
        },
        "public_structure": {
            "id": "public_structure",
            "name": "Public Structure",
            "desc": "Shared public buildings and fixtures maintained by the Lord.",
            "color": (34, 197, 94),
            "kind": "public",
            "building_types": public_building_types,
            "furniture_types": public_furniture_types,
            "road_types": list(ROAD_TYPES.keys()),
        },
    }
    categories["furniture"] = {
        "id": "furniture",
        "name": "Furniture",
        "desc": "Household storage chests, beds, and interior living fixtures.",
        "color": (250, 204, 21),
        "kind": "furniture",
        "building_types": household_furniture_types
    }
    categories["workplace"] = {
        "id": "workplace",
        "name": "Workplace",
        "desc": "Work stations and tools where villagers perform their jobs.",
        "color": (249, 115, 22),
        "kind": "public",
        "building_types": workplace_building_types,
        "furniture_types": workplace_furniture_types,
    }
    return list(categories.values())

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

# =====================================================================
# Immigration / Notice Board System
# =====================================================================
# Each day with an active posting there is a flat chance that immigrant
# households arrive; on success 1..MAX households spawn at random times.
IMMIGRATION_DAILY_SPAWN_CHANCE = 0.3
IMMIGRATION_MIN_HOUSEHOLDS_PER_DAY = 1
IMMIGRATION_MAX_HOUSEHOLDS_PER_DAY = 3
IMMIGRATION_MIN_HOUSEHOLD_SIZE = 2
IMMIGRATION_MAX_HOUSEHOLD_SIZE = 6
# Households waiting at the board leave on their own after this many
# full in-game days unattended (rejected, or player never opened the menu).
IMMIGRATION_PATIENCE_DAYS = 1.0
IMMIGRATION_SPAWN_DISTANCE_TILES = 45
IMMIGRATION_DESPAWN_DISTANCE_TILES = 60
IMMIGRATION_QUEUE_SLOTS_PER_ROW = 4
IMMIGRATION_QUEUE_SLOT_SPACING = 34   # px between queue slots
IMMIGRATION_QUEUE_ROW_SPACING = 1.2   # tiles between queue rows
IMMIGRATION_MEMBER_JITTER = 10        # px scatter around a member's slot point
IMMIGRATION_DEFAULT_REWARD_GOLD = 1   # gold coins per household, paid on Accept

# Furniture is represented by the same movable world-item entity after removal.
for _furniture_config in FURNITURE_TYPES.values():
    _furniture_config.setdefault("can_be_dropped", True)
    _furniture_config.setdefault("rotatable", True)

# =====================================================================
# Needs, Survival & Household Consumption System (Agent 1)
# =====================================================================
AI_NEED_MAX = 100.0
AI_NEED_HUNGER_DECAY_PER_DAY = 100.0   # Decays by 100% per 1 full in-game day (1200 seconds)
AI_NEED_THIRST_DECAY_PER_DAY = 100.0   # Decays by 100% per 1 full in-game day
AI_CRITICAL_NEED_THRESHOLD = 20.0      # Critical threshold (<= 20%) triggering task interruption
AI_DEATH_COUNTDOWN_HOURS = 24.0        # 24 in-game hours before death occurs when a need reaches 0%
# Survival override: a need that will turn lethal within this many in-game
# hours overrides every schedule slot and errand (except sleep itself).
AI_LETHAL_NEED_OVERRIDE_INGAME_HOURS = 2.0
DAILY_FOOD_REQUIREMENT = 1             # 1 food per day per living individual
DAILY_WATER_REQUIREMENT = 1            # 1 water per day per living individual
AI_NEED_FOOD_RESTORE = 100.0           # Need restored when consuming food
AI_NEED_WATER_RESTORE = 100.0          # Need restored when drinking water
AI_NEED_SEEK_COOLDOWN_SECONDS = 4.0
AI_NEED_PURCHASE_WAIT_COOLDOWN_SECONDS = 3.0
# Max real seconds a villager may spend on the physical market food-purchase
# errand (coin retrieval -> travel -> hauling home) before it is aborted so
# the household "already purchasing" flag can never stay stuck forever.
AI_FOOD_PURCHASE_ERRAND_TIMEOUT_SECONDS = 180.0
HOUSEHOLD_WATER_MAX_COLLECTORS = 2     # Maximum concurrent household members hauling water
AI_NEED_FAITH_MAX = 100.0
AI_NEED_FAITH_DAILY_DECAY_MIN = 10.0
AI_NEED_FAITH_DAILY_DECAY_MAX = 35.0
AI_NEED_FAITH_CONFESSION_THRESHOLD = 20.0
AI_NEED_FAITH_CONFESSION_RESTORE_MIN = 85.0
AI_NEED_FAITH_CONFESSION_RESTORE_MAX = 100.0
AI_NEED_FAITH_PRAYER_RESTORE_MIN = 10.0
AI_NEED_FAITH_PRAYER_RESTORE_MAX = 20.0
CONFESSION_DURATION_SECONDS = 5.0
CONFESSION_BUBBLE_DURATION_SECONDS = 5.0

# Individual happiness modifiers and their performance effects.
# Conditions are evaluated by HappinessSystem; this data owns all tuning values.
HAPPINESS_INITIAL_VALUE = 70.0
HAPPINESS_MIN_VALUE = 0.0
HAPPINESS_MAX_VALUE = 100.0
# Full happiness recompute (permit/building scans, wallet normalize) is a
# slow stat — throttle it to this many game-seconds per villager.
HAPPINESS_REFRESH_INTERVAL_SECONDS = 5.0
HAPPINESS_STATUS_BANDS = (
    {"id": "miserable", "label": "Miserable", "min": 0.0, "max": 24.0},
    {"id": "unhappy", "label": "Unhappy", "min": 25.0, "max": 49.0},
    {"id": "happy", "label": "Happy", "min": 50.0, "max": 74.0},
    {"id": "very_happy", "label": "Very Happy", "min": 75.0, "max": 100.0},
)
HAPPINESS_STATUS_COLORS = {
    "miserable": (239, 68, 68),
    "unhappy": (245, 158, 11),
    "happy": (34, 197, 94),
    "very_happy": (56, 189, 248),
}
HAPPINESS_ACTIVITY_MULTIPLIERS = {
    "miserable": 0.80,
    "unhappy": 0.90,
    "happy": 1.0,
    "very_happy": 1.0,
}
HAPPINESS_MODIFIERS = {
    "tax_church": {"label": "Church tax", "amount": 0.0, "duration_days": TAX_UNHAPPINESS_DURATION_DAYS},
    "tax_socage": {"label": "Socage tax", "amount": 0.0, "duration_days": TAX_UNHAPPINESS_DURATION_DAYS},
    "ate_varied_food": {"label": "Ate varied food", "amount": 5.0, "duration_days": 1, "food_variety_required": 2},
    "needs_comfortable": {"label": "Hunger, thirst and toilet satisfied", "amount": 5.0, "duration_days": 1, "threshold": 50.0},
    "usable_bed": {"label": "Usable bed", "amount": 5.0, "persistent": True},
    # Leisure happiness: +3 per in-game hour, hard cap +20, lasts 1 day.
# *** ESTABLISHED — DO NOT REGRESS *** removing max_amount lets leisure
# happiness stack unbounded (user-requested cap).
"leisure_per_hour": {"label": "Leisure time", "amount": 3.0, "duration_days": 1, "max_amount": 20.0},
    "prayer_completed": {"label": "Prayer completed", "amount": 5.0, "duration_days": 1},
    "confession_completed": {"label": "Confession completed", "amount": 5.0, "duration_days": 1},
    "gold_coin": {"label": "Personal gold coins", "amount_per_coin": 1.0},
    "small_home": {"label": "Small home", "amount": -10.0, "max_tiles": 10},
    "need_low": {"label": "Need below 20%", "amount": -10.0, "threshold": 20.0, "duration_days": 1},
    "need_empty": {"label": "Need reached 0%", "amount": -20.0, "threshold": 0.0, "duration_days": 1},
    "no_home": {"label": "No usable home", "amount": -20.0, "persistent": True},
    "no_bed": {"label": "No usable bed", "amount": -5.0, "persistent": True},
    "purchase_unaffordable": {"label": "Could not afford a needed purchase", "amount": -10.0, "duration_days": 1},
    "unemployed": {"label": "Unassigned / unemployed", "amount": -20.0, "persistent": True},
    # Faith consequences: <=20% faith -> -20 unhappiness; at 0% -> -30 total.
    "faith_low": {"label": "Faith below 20%", "amount": -20.0, "threshold": 20.0},
    "faith_empty": {"label": "Faith at 0%", "amount": -30.0, "threshold": 0.0},
    "bereavement": {"label": "Family member died", "amount": -50.0, "duration_days": 5},
    "no_church_building": {"label": "No church building", "amount": -30.0, "duration_days": 3},
    "sleep_fatigue": {"label": "Sleep deprivation", "duration_days": 1},
}
HAPPINESS_NEED_LABELS = {"hunger": "Hunger", "thirst": "Thirst", "toilet": "Toilet"}

# Individual sleep need and pacing. A full awake cycle drains the meter over
# the configured waking hours; sleep restores it over the configured duration.
SLEEP_INITIAL_VALUE = 100.0
SLEEP_MIN_VALUE = 0.0
SLEEP_MAX_VALUE = 100.0
SLEEP_FULL_RECOVERY_INGAME_HOURS = 8.0
SLEEP_WAKE_DRAIN_INGAME_HOURS = 20.0
SLEEP_NO_BED_RECOVERY_DURATION_MULTIPLIER = 1.5
SLEEP_BED_ARRIVAL_DISTANCE = 12.0
SLEEP_FORCED_WAKE_THRESHOLD = 10.0
SLEEP_ANY_REST_THRESHOLD = 30.0
SLEEP_ANY_WAKE_THRESHOLD = 70.0
SLEEP_STATUS_BANDS = (
    {"id": "rested", "label": "Rested", "min": 50.0},
    {"id": "sluggish", "label": "Sluggish", "min": 31.0},
    {"id": "drowsy", "label": "Drowsy", "min": 21.0},
    {"id": "half_asleep", "label": "Half Asleep", "min": 0.001},
    {"id": "zonked", "label": "Zonked", "min": 0.0},
)
SLEEP_STATUS_COLORS = {
    "rested": (34, 197, 94),
    "sluggish": (234, 179, 8),
    "drowsy": (249, 115, 22),
    "half_asleep": (239, 68, 68),
    "zonked": (190, 24, 93),
}
SLEEP_HAPPINESS_PENALTIES = {
    "sluggish": -2.0,
    "drowsy": -5.0,
    "half_asleep": -7.0,
    "zonked": -20.0,
}

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
CORPSE_CARRY_SPEED_RATIO = 0.5  # 50% speed while carrying corpse

AI_NEED_TOILET_DECAY_PER_DAY = 150.0   # Decays over time to trigger urgent need ~1-2 times daily
AI_NEED_TOILET_URGENT_THRESHOLD = 20.0 # <= 20% triggers toilet seeking
AI_NEED_TOILET_RESTORE = 100.0         # Restored when using toilet
TOILET_USE_DURATION_HOURS = 0.25       # 15 in-game minutes
TOILET_USE_DURATION_SECONDS = 5.0      # Real-time seconds for toilet usage



# =====================================================================
# World Map Overlay (M key) - fullscreen player-centered view
# =====================================================================
MAP_OVERLAY_BG = (8, 12, 20, 245)
MAP_OVERLAY_MAP_BG = (15, 23, 42, 220)
MAP_OVERLAY_GRID_COLOR = (51, 65, 85, 80)
MAP_OVERLAY_BORDER = (71, 85, 105)
MAP_OVERLAY_TEXT = (226, 232, 240)
MAP_OVERLAY_TEXT_DIM = (148, 163, 184)
MAP_OVERLAY_TITLE_COLOR = (56, 189, 248)
MAP_OVERLAY_LAYER_ON_BG = (30, 58, 95, 220)
MAP_OVERLAY_LAYER_OFF_BG = (30, 41, 59, 180)
MAP_OVERLAY_LAYER_ON_BORDER = (56, 189, 248)
MAP_OVERLAY_LAYER_OFF_BORDER = (71, 85, 105)
MAP_OVERLAY_PLAYER_COLOR = (255, 255, 255)
MAP_OVERLAY_SERVANT_COLOR = (250, 204, 21)
MAP_OVERLAY_VILLAGER_FALLBACK = (148, 163, 184)
MAP_OVERLAY_CONSTRUCTION_COLOR = (251, 191, 36)
MAP_OVERLAY_RESOURCE_COLORS = {
    "Wood": (180, 83, 9),
    "Stone": (100, 116, 139),
    "Food": (34, 197, 94),
    "Water": (56, 189, 248),
    "Copper": (217, 119, 6),
    "Silver": (203, 213, 225),
    "Gold": (250, 204, 21),
}
MAP_OVERLAY_VIEW_RADIUS_TILES = 60
MAP_OVERLAY_MARGIN = 16
MAP_OVERLAY_TOP_BAR_HEIGHT = 40
MAP_OVERLAY_BTN_HEIGHT = 26
MAP_OVERLAY_BTN_GAP = 8
MAP_OVERLAY_BTN_PADDING_X = 12
MAP_OVERLAY_FONT_SIZE_TITLE = 18
MAP_OVERLAY_FONT_SIZE_BTN = 12
MAP_OVERLAY_FONT_SIZE_HINT = 10
MAP_OVERLAY_DOT_RADIUS_VILLAGER = 4
MAP_OVERLAY_DOT_RADIUS_SERVANT = 4
MAP_OVERLAY_DOT_RADIUS_RESOURCE = 2
MAP_OVERLAY_DOT_RADIUS_PLAYER = 6
MAP_OVERLAY_ICON_MIN_PX = 4
MAP_OVERLAY_GRID_STEP_TILES = 10
MAP_OVERLAY_LAYERS = {
    "permits": "Permits",
    "structures": "Structures",
    "furniture": "Furniture",
    "forest": "Forest",
    "mines": "Mines",
    "ai": "AI",
    "resources": "Resources",
}
MAP_OVERLAY_ZOOM_MIN = 0.25
MAP_OVERLAY_ZOOM_MAX = 4.0
MAP_OVERLAY_ZOOM_STEP = 0.15

# Autosave: writes saves/autosave-dayNN.json every interval (real seconds).
AUTOSAVE_INTERVAL_SECONDS = 300.0
AUTOSAVE_KEEP_COUNT = 3

# Global UI scale: multiplies every UI font/pixel metric. 1.35 = ~35%
# larger text than the original compact sizes; resolution ratio on top.
UI_FONT_BOOST = 1.0
