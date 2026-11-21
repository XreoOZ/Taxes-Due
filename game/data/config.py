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
PATH_ARROW_HEAD_LENGTH = 8
PATH_ARROW_HEAD_WIDTH = 6
PATH_ROUTE_WAYPOINT_RADIUS = 3
COLOR_PATH_ROUTE = COLOR_PATH_TARGET_RING
COLOR_PATH_ROUTE_FAILED = (239, 68, 68)
PATH_WAYPOINT_TOLERANCE = 14.0           # Waypoint arrival threshold
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
WATERING_DURATION_SECONDS = 2.0
DOORWAY_WAYPOINT_DISTANCE = 24.0
DEFAULT_PLOT_MAX_WORKERS = 2

# Farming Task Durations & Dispersion Settings (Config-Driven, Zero Hardcode)
WATERING_DURATION_INGAME_HOURS = 20.0 / 60.0  # 20 in-game minutes per tile
TILLING_DURATION_INGAME_HOURS = 1.0           # 1 in-game hour per tile
FARM_TILE_PROXIMITY_PENALTY_ADJACENT = 3000.0  # Heavy penalty for tiles adjacent to other active workers (< 1.5 grid units)
FARM_TILE_PROXIMITY_PENALTY_NEAR = 1500.0      # Penalty for tiles within 2.5 grid units
FARM_TILE_ARRIVAL_DIST = 20.0                  # Arrival radius inside target work tile
INTERACTION_CONTACT_RADIUS = 58.0              # Contact pickup distance (allowing adjacent tile pickup without clipping)
TOOL_STOW_ARRIVAL_DIST = 36.0                  # Arrival distance to household chest when returning unused tools
LOOSE_ITEM_ARRIVAL_DIST = 24.0                 # Arrival distance for gathering loose items
CHEST_INTERACTION_RADIUS = 36.0                # Interaction distance with household chest
CARPENTER_BUILD_DURATION_INGAME_HOURS = 1.0
CARPENTER_DEFAULT_LIVING_HOUSEHOLD_SIZE = 1
FURNITURE_DAILY_BREAK_CHANCE = 0.05
CARPENTER_REPAIR_FOOD_DAYS = 3
CARPENTER_REPAIR_MATERIALS = {"Wood": 2}
CARPENTER_TOOL_SWING_SPEED = 7.0
CARPENTER_TOOL_SWING_ANGLE = 0.55
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
    "Unassigned": {
        "id": "Unassigned",
        "name": "Unassigned",
        "title": "Unassigned",
        "color": (148, 163, 184),
        "wip": False,
        "workplace_permit": None,
        "desc": "Individual with no assigned job. Available for assignment.",
        "required_tools": []
    },
    "Farmer": {
        "id": "Farmer",
        "name": "Farmer",
        "title": "Farmer",
        "color": (34, 197, 94),
        "wip": False,
        "workplace_permit": "farm",
        "desc": "Tends crops and agricultural plots; waters and harvests food.",
        "required_tools": ["Hoe", "Watering_Can", "Sickle"]
    },
    "Builder": {
        "id": "Builder",
        "name": "Builder",
        "title": "Builder",
        "color": (245, 158, 11),
        "wip": False,
        "workplace_permit": "construction",
        "desc": "Constructs buildings, infrastructure, and structural works.",
        "required_tools": ["Hammer"]
    },
    "Blacksmith": {
        "id": "Blacksmith",
        "name": "Blacksmith",
        "title": "Blacksmith (WIP)",
        "color": (239, 68, 68),
        "wip": True,
        "workplace_permit": "smithy",
        "desc": "Forges iron tools, nails, and armor for the settlement.",
        "required_tools": ["Hammer", "Tongs"]
    },
    "Carpenter": {
        "id": "Carpenter",
        "name": "Carpenter",
        "title": "Carpenter",
        "color": (234, 179, 8),
        "wip": False,
        "workplace_permit": "construction",
        "workplace_furniture_type": "carpenter_workbench",
        "desc": "Crafts furniture, structural beams, and wooden barrels.",
        "required_tools": ["Saw", "Adze"],
        "material_stock_target": {"Wood": 10, "Stone": 10}
    },
    "Tax Collector": {
        "id": "Tax Collector",
        "name": "Tax Collector",
        "title": "Tax Collector",
        "color": (180, 83, 9),
        "wip": False,
        "workplace_building_type": "tax_house",
        "desc": "Collects the scheduled household socage tax and returns it to the Crown Treasury.",
        "required_tools": []
    },
    "Baker": {
        "id": "Baker",
        "name": "Baker",
        "title": "Baker (WIP)",
        "color": (249, 115, 22),
        "wip": True,
        "workplace_permit": "bakery",
        "desc": "Mills grain and bakes daily bread loaves for villagers.",
        "required_tools": ["Rolling_Pin", "Peel"]
    },
    "Fisherman": {
        "id": "Fisherman",
        "name": "Fisherman",
        "title": "Fisherman (WIP)",
        "color": (56, 189, 248),
        "wip": True,
        "workplace_permit": "fishery",
        "desc": "Catches fish and gathers seafood at village docks and shores.",
        "required_tools": ["Fishing_Rod"]
    },
    "Priest": {
        "id": "Priest",
        "name": "Priest",
        "title": "Priest",
        "color": (168, 85, 247),
        "wip": False,
        "workplace_permit": "church",
        "desc": "Conducts daily prayer and collects church taxes at the village church.",
        "required_tools": []
    },
    "Gravedigger": {
        "id": "Gravedigger",
        "name": "Gravedigger",
        "title": "Gravedigger",
        "color": (48, 50, 56),
        "wip": False,
        "workplace_permit": "cemetery",
        "desc": "Prepares graves and buries deceased villagers in the cemetery.",
        "required_tools": ["Hoe"],
        "material_stock_target": {"Wood": 5, "Stone": 5},
        "materials_per_grave": {"Wood": 1, "Stone": 1}
    }
}

# Calendar labels shown in the HUD only; schedules are shared across every day.
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAYS_OF_WEEK = WEEKDAY_NAMES  # Legacy import compatibility; never used by schedules.

# 24-Hour Schedule System (RimWorld-Style Activity Management)
SCHEDULE_WORK = "WORK"
SCHEDULE_LEISURE = "LEISURE"
SCHEDULE_SLEEP = "SLEEP"
SCHEDULE_ANY = "ANY"
SCHEDULE_PRAYER = "PRAYER"
DEFAULT_PRAYER_START_HOUR = 3
DEFAULT_PRAYER_END_HOUR = 4

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
        "desc": "Finish active work, meet needs (including sleep), then choose leisure or available work."
    },
    "PRAYER": {
        "id": "PRAYER",
        "name": "Prayer",
        "color": (234, 179, 8),        # Radiant gold
        "desc": "Mandatory church prayer time decreed by the Priest."
    }
}

# Task states are paused outside these schedule slots and resumed when the slot
# returns. Prefixes are kept separate so task families stay data-driven.
SCHEDULE_ACTIVITY_TASKS = {
    "WORK": frozenset({
        "BUYING_JOB_TOOLS_RETRIEVE_COINS", "BUYING_JOB_TOOLS_TRAVEL_TO_MARKET",
        "BUYING_JOB_TOOLS_RETURN_HOME", "MISSING_TOOL", "RETURNING_TOOLS",
        "EQUIPPING_JOB_TOOLS", "TILLING", "FETCHING_WATER", "WATERING",
        "HARVESTING", "HAULING_HOME", "PREACHING", "RETURNING_TITHES_HOME",
        "CARRYING_CORPSE", "DIGGING_GRAVE", "BURYING_GRAVE", "FETCHING_CORPSE",
        "GRAVEDIGGER_BURIAL_PAYMENT_RETRIEVE", "WAITING_FOR_BURIAL_PAYMENT",
        "GOING_TO_TAX_OFFICE", "STATIONED_AT_TAX_OFFICE",
        "VISITING_HOUSEHOLD_FOR_TAX", "WAITING_FOR_HOUSEHOLD_TAX",
        "RETURNING_TAX_TO_TREASURY", "PAYING_SOCAGE_TAX",
        "WAITING_FOR_CARPENTER_COMMISSION", "CARPENTER_CONSTRUCTING",
        "CARPENTER_COLLECTING_MATERIALS", "CARPENTER_DELIVERING_MATERIALS",
        "CARPENTER_REPAIRING",
    }),
    "LEISURE": frozenset({
        "SEEKING_FOOD", "SEEKING_WATER", "SEEKING_TOILET",
        "RECOVER_DEATH_ITEMS", "BUYING_FOOD_RETRIEVE_COINS",
        "BUYING_FOOD_RETRIEVE_GROUND_COINS", "BUYING_FOOD_TRAVEL_TO_MARKET",
        "BUYING_FOOD_HAULING_HOME", "FETCHING_FURNITURE",
        "FETCHING_DROPPED_FURNITURE", "HAULING_FURNITURE",
        "HAULING_DROPPED_FURNITURE", "FETCHING_POSSESSION",
        "HAULING_POSSESSION_HOME", "HAULING_HOUSEHOLD_WATER",
        "COLLECTING_HOUSEHOLD_WATER", "BURIAL_PAYMENT_RETRIEVE",
        "BURIAL_PAYMENT_TRAVEL", "CONFESSION_QUEUED",
        "WAITING_FOR_CONFESSION", "CONFESSION_RETRIEVE_COINS",
        "CONFESSION_TRAVEL_TO_PRIEST", "GOING_TO_CONFESSOR",
        "GOING_TO_CONFESSION_BOX", "CONFESSING", "HEARING_CONFESSION",
        "DEPOSITING_UNUSED_ITEMS",
    }),
    "SLEEP": frozenset({"SLEEPING", "DEPOSITING_UNUSED_ITEMS"}),
    "PRAYER": frozenset({"LEADING_PRAYER", "ATTENDING_PRAYER", "PRAYING"}),
}
SCHEDULE_ACTIVITY_TASK_PREFIXES = (
    ("CARPENTER_FEE_", "LEISURE"),
    ("CARPENTER_RESTOCK_", "WORK"),
    ("CARPENTER_", "WORK"),
    ("GRAVEDIGGER_RESTOCK_", "WORK"),
    ("HAULING_STALL_", "LEISURE"),
)
ARTISAN_JOB_IDS = ("Carpenter", "Blacksmith", "Baker")
SCHEDULE_ACTIVITY_STRICT_TASK_PREFIXES = tuple(
    f"{job.upper()}_" for job in ARTISAN_JOB_IDS
)
SCHEDULE_ACTIVITY_STRICT_TASK_PREFIX_EXEMPTIONS = ("CARPENTER_FEE_",)
SCHEDULE_ACTIVITY_NEUTRAL_TASKS = frozenset({
    "IDLE", "DECEASED", "LEISURE", "STROLLING", "ZONKED_SLEEP",
})
SCHEDULE_ACTIVITY_CANCEL_ON_BOUNDARY = frozenset({
    "SLEEPING", "LEADING_PRAYER", "ATTENDING_PRAYER", "PRAYING",
    "CONFESSION_QUEUED", "WAITING_FOR_CONFESSION",
    "CONFESSION_RETRIEVE_COINS", "CONFESSION_TRAVEL_TO_PRIEST",
    "GOING_TO_CONFESSOR", "GOING_TO_CONFESSION_BOX", "CONFESSING",
    "HEARING_CONFESSION",
})
SCHEDULE_ACTIVITY_STRICT_TASKS = frozenset({
    "GOING_TO_TAX_OFFICE", "STATIONED_AT_TAX_OFFICE",
    "VISITING_HOUSEHOLD_FOR_TAX", "WAITING_FOR_HOUSEHOLD_TAX",
    "RETURNING_TAX_TO_TREASURY",
    "WAITING_FOR_CARPENTER_COMMISSION",
})
SCHEDULE_ACTIVITY_TASK_STATE_FIELDS = (
    "current_work_tile", "tilling_timer", "watering_timer", "well_draw_timer",
    "has_water", "water_day", "water_charges", "carrying_crop",
    "carrying_res", "carrying_amount", "water_collect_amount",
)

# Kept for older callers; scheduling now uses SCHEDULE_ACTIVITY_TASKS.
SCHEDULE_NON_WORK_TASKS = frozenset(
    task
    for group, tasks in SCHEDULE_ACTIVITY_TASKS.items()
    if group != "WORK"
    for task in tasks
) | SCHEDULE_ACTIVITY_NEUTRAL_TASKS
FREE_TIME_SCHEDULE_ACTIVITIES = frozenset({"LEISURE", "ANY"})
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
    "CARPENTER_RESTOCK_RETRIEVE_COINS": (
        "Travel to the market", "Buy materials", "Carry materials to storage",
        "Resume Carpenter work",
    ),
    "CARPENTER_RESTOCK_TRAVEL_TO_MARKET": (
        "Buy materials", "Carry materials to storage", "Resume Carpenter work",
    ),
    "CARPENTER_RESTOCK_HAULING_HOME": (
        "Store materials", "Resume Carpenter work",
    ),
    "CARPENTER_COLLECTING_MATERIALS": ("Deliver materials", "Continue construction or repair"),
    "CARPENTER_DELIVERING_MATERIALS": ("Continue construction or repair",),
    "CARPENTER_CONSTRUCTING": ("Continue construction",),
    "CARPENTER_REPAIRING": ("Continue repair",),
    "CONFESSION_QUEUED": ("Wait for the Priest", "Approach the Priest", "Confess"),
    "WAITING_FOR_CONFESSION": ("Approach the Priest when called", "Confess"),
    "CONFESSION_RETRIEVE_COINS": ("Travel to the Priest", "Confess"),
    "CONFESSION_TRAVEL_TO_PRIEST": ("Meet the Priest", "Confess"),
    "GOING_TO_CONFESSOR": ("Meet the Priest", "Confess"),
    "GOING_TO_CONFESSION_BOX": ("Confess with the Priest",),
    "CONFESSING": ("Complete confession",),
}
MARKET_SALES_REPORT_PERIOD_DAYS = 10
CARPENTER_INSUFFICIENT_LANDLORD_COIN_MESSAGES = (
    "The treasury does not hold enough coin for this commission, my Lord.",
    "I cannot pay the Carpenter yet; the treasury is short on coin.",
    "The available coin falls short of the Carpenter's price, Sire.",
    "We need more treasury coin before this work can be commissioned.",
    "The Carpenter's fee exceeds our current coin reserve, my Lord.",
)

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
    "Wood": 0,
    "Food": 0,
    "Stone": 0,
    "Water": 0,
    "Copper": 0,
    "Silver": 0,
    "Gold": 0,
}
MAX_STACK_SIZE = 100
MAX_TILE_CAPACITY = 1000  # Up to 10 stacks of 100 per tile (kotak)
VILLAGER_INVENTORY_CAPACITY = 50

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
    "Water": 2,
    "Hoe": 8,
    "Sickle": 6,
    "Watering_Can": 8,
    "Saw": 12,
    "Adze": 10,
}

# Only goods with implemented storage and market behavior are listed here.
# Other ITEM_CATEGORIES entries may be used by WIP systems, but are not sellable.
MARKET_TRADEABLE_ITEMS = {
    "Potato": "Food",
    "Wood": "Wood",
    "Stone": "Stone",
    "Water": "Water",
    "Hoe": "Hoe",
    "Sickle": "Sickle",
    "Watering_Can": "Watering_Can",
    "Saw": "Saw",
    "Adze": "Adze",
}
MARKET_CURRENCY_DENOMINATIONS = ("Gold", "Silver", "Copper")
MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT = 20
HOUSEHOLD_STALL_HAUL_CAPACITY = 20
MARKET_QUANTITY_DEFAULT = 10
MARKET_QUANTITY_MAX = 1000
MARKET_PERCENT_STEP = 5
MARKET_WEALTH_REFERENCE_DAYS = 7.0
MARKET_WEALTH_PRICE_ELASTICITY = 0.12
MARKET_WEALTH_PRICE_FACTOR_MIN = 0.75
MARKET_WEALTH_PRICE_FACTOR_MAX = 1.5
VILLAGER_HUD_COUNT_REFRESH_SECONDS = 0.5
MARKET_WEALTH_CONTEXT_REFRESH_SECONDS = 0.5

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
    "Hoe": 0,
    "Sickle": 0,
    "Watering_Can": 0,
    "Hammer": 0
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
STARTING_HOUR = 8.0
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
        "carpenter_commissionable": True,
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
        "carpenter_commissionable": True,
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
        "carpenter_commissionable": True,
    },
    "tax_house": {
        "id": "tax_house",
        "name": "Tax Office",
        "category": "Tax Office",
        "category_id": "public_structure",
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
        "carpenter_commissionable": True,
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
    return list(categories.values())

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
        "desc": "Hearty staple tuber crop. Each tile yields 2 potatoes 80% of the time, 4 potatoes 15% of the time, and 5 potatoes 5% of the time every 10 days.",
        "growth_days": 10.0,
        "sprout_day": 2.0,
        "leaf_day": 4.0,
        "harvest_day": 10.0,
        "yield_distribution": [
            {"amount": 2, "weight": 0.80},
            {"amount": 4, "weight": 0.15},
            {"amount": 5, "weight": 0.05},
        ],
        "yield_per_tile": 2,
        "yield": 2
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
    "carpenter_workbench": {
        "id": "carpenter_workbench",
        "name": "Carpenter Workbench",
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
        "carpenter_commissionable": True,
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
    }
}

# Furniture is represented by the same movable world-item entity after removal.
for _furniture_config in FURNITURE_TYPES.values():
    _furniture_config.setdefault("can_be_dropped", True)
    _furniture_config.setdefault("rotatable", True)

PUBLIC_STRUCTURE_DAILY_BREAK_CHANCE = FURNITURE_DAILY_BREAK_CHANCE
LORD_TREASURY_START_TILE = (1, 0)
LORD_TREASURY_PLACEMENT_SEARCH_RADIUS = 8

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
AI_NEED_SEEK_COOLDOWN_SECONDS = 4.0
AI_NEED_PURCHASE_WAIT_COOLDOWN_SECONDS = 3.0
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
HAPPINESS_WEALTH_DENOMINATION = "Gold"
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
    "ate_varied_food": {"label": "Ate varied food", "amount": 5.0, "duration_days": 1, "food_variety_required": 2},
    "needs_comfortable": {"label": "Hunger, thirst and toilet satisfied", "amount": 5.0, "duration_days": 1, "threshold": 50.0},
    "usable_bed": {"label": "Usable bed", "amount": 5.0, "persistent": True},
    "leisure_per_hour": {"label": "Leisure time", "amount": 3.0, "duration_days": 1},
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
    "bereavement": {"label": "Family member died", "amount": -50.0, "duration_days": 5},
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

# =====================================================================
# Church, Priest, Cemetery, Gravedigger & Toilet Systems (Agent 3)
# =====================================================================
DEFAULT_CHURCH_TAX = {"Gold": 0, "Silver": 0, "Copper": 1}  # 1 Copper per household per day default
DEFAULT_SOCAGE_TAX_ENABLED = True
DEFAULT_SOCAGE_TAX_PERCENT = 10
SOCAGE_TAX_QUICK_STEP = 10
SOCAGE_TAX_INTERVAL_DAYS = 10
SOCAGE_TAX_HAPPINESS_TIERS = ((1, 10, -5), (11, 20, -20), (21, 30, -30),
                               (31, 60, -50), (61, 100, -100))
CHURCH_TAX_HAPPINESS_TIERS_COPPER = ((1, 1, -5), (2, 19, -10),
                                     (20, 99, -20), (100, None, -50))
NO_CHURCH_TAX_HAPPINESS_BONUS = 10
TAX_COLLECTOR_STATION_ARRIVAL_DISTANCE = 20.0
SOCAGE_TAX_GREETING_LINES = ("Pay your taxes, please.", "The Crown's due is collected today.",
                             "I am here for the household socage.")
SOCAGE_TAX_HAPPINESS_REPLIES = {
    "miserable": ("This levy leaves us with too little.", "Must we pay even now?"),
    "unhappy": ("We will pay, though it is a burden.", "Here is the household's due."),
    "happy": ("Here is the household tax. Thank you.", "Our due is ready."),
    "very_happy": ("Gladly; may the village prosper.", "The Crown's due, collected in good faith."),
}

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
    "ai": "AI",
    "resources": "Resources",
}
MAP_OVERLAY_ZOOM_MIN = 0.25
MAP_OVERLAY_ZOOM_MAX = 4.0
MAP_OVERLAY_ZOOM_STEP = 0.15
