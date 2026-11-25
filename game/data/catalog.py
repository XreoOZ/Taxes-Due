"""Game data — catalog domain constants.

Auto-extracted from config.py; imported back by game.data.config
so `from game.data.config import X` keeps working everywhere.
"""

# -----------------------------------------------------------------------------
# CATALOG — items, tools, jobs, crops, schedules, starter content
# -----------------------------------------------------------------------------
WATERING_DURATION_SECONDS = 2.0

DEFAULT_PLOT_MAX_WORKERS = 2

# Farm plots use a manually configurable worker cap (set via Jobs > Workstations > Farmer).

# Farming Task Durations & Dispersion Settings (Config-Driven, Zero Hardcode)
# Farm task durations per tile, in in-game hours.
# *** ESTABLISHED — user-requested 30 in-game minutes each ***
WATERING_DURATION_INGAME_HOURS = 0.25  # 15 in-game minutes per tile

TILLING_DURATION_INGAME_HOURS = 0.25   # 15 in-game minutes per tile

FARM_TILE_DISPERSION_ENABLED = False           # False = farmers sweep tiles nearest-first in order; True = spread workers apart

FARM_TILE_PROXIMITY_PENALTY_ADJACENT = 3000.0  # Heavy penalty for tiles adjacent to other active workers (< 1.5 grid units)

FARM_TILE_PROXIMITY_PENALTY_NEAR = 1500.0      # Penalty for tiles within 2.5 grid units

FARM_TILE_ARRIVAL_DIST = 20.0                  # Arrival radius inside target work tile

WOODSMAN_CUT_INGAME_HOURS = 0.25         # 15 in-game minutes per tree

WOODSMAN_PLANT_INGAME_HOURS = 0.25       # 15 in-game minutes per replant

MINER_WORK_INGAME_HOURS = 20.0 / 60.0    # 20 in-game minutes per mining cycle

TREE_WOOD_YIELD_MIN = 1

TREE_WOOD_YIELD_MAX = 2

TREE_WOOD_YIELD_DISTRIBUTION = [
    {"amount": 1, "weight": 0.80},
    {"amount": 2, "weight": 0.20},
]

WOODSMAN_WORKSTATION_TILES = 4           # Woodsman Lodge footprint (square)

WORKSTATION_MAX_WORKERS = 5

WORKSTATION_DEFAULT_QUOTA_DAILY = 0      # 0 = unlimited daily output quota

WORKSTATION_QUOTA_STEP = 10

BUILDER_DEFAULT_LIVING_HOUSEHOLD_SIZE = 1

# Commission queue: seconds before a failed payment claim may be retried.
COMMISSION_CLAIM_RETRY_SECONDS = 20.0


# -----------------------------------------------------------------------------
# Toolmaker System (Iron chain: Iron Mine -> Iron Ore -> Iron Bar -> Tools)
# -----------------------------------------------------------------------------
# Smelting: 1 Iron Ore + 1 Wood -> 1 Iron Bar at the Toolmaker Workbench.
TOOLMAKER_BAR_RECIPE = {"Iron Ore": 1, "Wood": 1}

TOOLMAKER_BAR_SMELT_INGAME_MINUTES = 10.0

# Automatic bar production: keep up to this many bars in the toolmaker's
# household chest; never exceed this many smelts per in-game day.
TOOLMAKER_BAR_STOCK_TARGET = 10

TOOLMAKER_BAR_DAILY_CAP = 10

# Tool forging: every craftable tool costs this per unit, build time is
# 20 in-game minutes (1/3 in-game hour) per tool.
TOOLMAKER_TOOL_RECIPE = {"Wood": 2, "Iron Bar": 3}

TOOLMAKER_TOOL_MIN_INGAME_HOURS = 20.0 / 60.0

TOOLMAKER_TOOL_MAX_INGAME_HOURS = 20.0 / 60.0

# Spare set kept in the toolmaker's household chest for quick replacement
TOOLMAKER_SPARE_TOOLS_TARGET = 1

# Craftable catalogue = every item whose ITEM_CATEGORIES value is "TOOL".
# -----------------------------------------------------------------------------
# Tool Condition Lifecycle (per-unit wear on every TOOL item)
# -----------------------------------------------------------------------------
TOOL_CONDITION_STAGES = ["PRISTINE", "GOOD", "WORN", "DAMAGED", "BROKEN"]

TOOL_CONDITION_DEGRADE_CHANCE = 0.30   # per unit, per check

TOOL_CONDITION_CHECK_EVERY_DAYS = 2     # degradation sweep cadence

# Orders carry "artisan_job"; missing value falls back to this job id.
DEFAULT_COMMISSION_ARTISAN_JOB = "Builder"

BUILDER_TOOL_SWING_SPEED = 7.0

BUILDER_TOOL_SWING_ANGLE = 0.55

FURNITURE_CLAIM_BED_SEARCH_RADIUS = 8.5        # Max tile distance to infer chest household ownership from beds

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

# Fresh-game starter household size (randomized composition each new game).
STARTER_FAMILY_SIZE = 5


# New-game starter presets ("difficulty" select after map choice).
# enabled=False entries render as WIP and cannot be picked.
STARTER_PRESETS = [
    {
        "id": "nepo_baby",
        "label": "Nepo Baby : Easy Start",
        "desc": "A supplied household, stocked landlord storage, a ready timber hall, and a market.",
        "enabled": True,
        "wip": False,
        "family_size": 5,
        "permit_padding": 0,
        "house": {"building_type": "wooden_structure", "width": 6, "height": 3},
        "market": {"building_type": "market", "width": 3, "height": 2},
        # Player-picked placement: tile offsets from the HOUSE TOP-LEFT.
        # House occupies (0,0)-(5,2); market sits left with a 1-tile gap,
        # storage yard below leaving the door front yard (rows 3-4) clear.
        "farm": {"width": 6, "height": 4},
        "cluster": {
            "house": {"dx": 0, "dy": 0},
            "market": {"dx": -4, "dy": 0},
            "storage": {"dx": 0, "dy": 5},
            "farm": {"dx": 7, "dy": 0},
            "props": [
                {"building": "toilet", "dx": 6, "dy": 0},
                # Well & Toilet are public structures — no permit needed,
                # they sit on open ground beside the farm tiles.
                {"building": "well", "dx": 13, "dy": 1},
            ],
        },
        "landlord_storage": True,
        "storage_permit_width": 6,
        "storage_permit_height": 6,
        "storage_chest_inside_house": True,
        "builder_workbench": True,
        # Lord Treasury belongs to the landlord — parked on open ground
        # beside the storage yard, never inside the household home.
        "treasury_chest_spot": "beside_storage",
        "treasury_items": {"Gold": 10},
        "storage_items": {
            "Potato": 100,
            "Wood": 500,
            "Stone": 500,
            "Iron Ore": 50,
            "Iron Bar": 50,
            "Hoe": 3,
            "Sickle": 3,
            "Watering_Can": 3,
            "Hammer": 1,
            "Tongs": 1,
            "Saw": 1,
            "Adze": 1,
            "Felling_Axe": 1,
            "Spade": 1,
            "Pickaxe": 1,
            "Sledgehammer": 1,
        },
    },
    {
        "id": "trailblazer",
        "label": "Trailblazer : Hard Start",
        "desc": "Work in progress — a harsher founding scenario.",
        "enabled": False,
        "wip": True,
        "family_size": None,
        "permit_padding": 2,
        "house": None,
        "market": None,
        "landlord_storage": False,
        "builder_workbench": False,
        "storage_items": {},
    },
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
    "Builder": {
        "id": "Builder",
        "name": "Builder",
        "title": "Builder",
        "color": (234, 179, 8),
        "wip": False,
        "workplace_permit": "construction",
        "workplace_furniture_type": "builder_workbench",
        "desc": "Crafts furniture, structural beams, and wooden barrels.",
        "required_tools": ["Saw", "Adze"],
        "material_stock_target": {"Wood": 5, "Stone": 5}
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
        # "Rolling_Pin"/"Peel"/"Fishing_Rod" disabled — reserved for WIP
        # Baker/Fisherman jobs; uncomment when those mechanics ship.
        "required_tools": []
    },
    "Fisherman": {
        "id": "Fisherman",
        "name": "Fisherman",
        "title": "Fisherman (WIP)",
        "color": (56, 189, 248),
        "wip": True,
        "workplace_permit": "fishery",
        "desc": "Catches fish and gathers seafood at village docks and shores.",
        "required_tools": []
    },
    "Priest": {
        "id": "Priest",
        "name": "Priest",
        "title": "Priest",
        "color": (168, 85, 247),
        "wip": False,
        "auto_sortable": False,
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
    },
    "Woodsman": {
        "id": "Woodsman",
        "name": "Woodsman",
        "title": "Woodsman",
        "color": (22, 101, 52),
        "wip": False,
        "workplace_furniture_type": "woodsman_lodge",
        "desc": "Fells the nearest mature trees in the forest and replants them when the lodge is set to Plant a Tree.",
        "required_tools": ["Felling_Axe", "Spade"]
    },
    "Miner": {
        "id": "Miner",
        "name": "Miner",
        "title": "Miner",
        "color": (71, 85, 105),
        "wip": False,
        "workplace_furniture_type": "miner_workstation",
        "desc": "Extracts ore at the mine a Miner Workstation is built upon (Stone, Copper, Gold, ...).",
        "required_tools": ["Pickaxe", "Sledgehammer"]
    },
    "Toolmaker": {
        "id": "Toolmaker",
        "name": "Toolmaker",
        "title": "Toolmaker",
        "color": (180, 83, 9),
        "wip": False,
        "workplace_furniture_type": "toolmaker_workbench",
        "desc": "Smelts iron ore into bars and forges tools at the Toolmaker Workbench (hammer, tongs, and moulds).",
        "required_tools": ["Hammer", "Tongs"],
        "material_stock_target": {"Wood": 10, "Iron Ore": 10}
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
        "WAITING_FOR_BUILDER_COMMISSION", "BUILDER_CONSTRUCTING",
        "BUILDER_COLLECTING_MATERIALS", "BUILDER_DELIVERING_MATERIALS",
        "BUILDER_REPAIRING",
        "BUILDER_FEE_RETRIEVE", "BUILDER_FEE_TRAVEL",
        "BUILDER_FEE_LANDLORD_RETRIEVE",
        "STATION_LEFTOVER_FETCH", "STATION_LEFTOVER_DELIVER",
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
        "STATION_LEFTOVER_FETCH", "STATION_LEFTOVER_DELIVER",
    }),
    "SLEEP": frozenset({"SLEEPING", "DEPOSITING_UNUSED_ITEMS"}),
    "PRAYER": frozenset({"LEADING_PRAYER", "ATTENDING_PRAYER", "PRAYING"}),
}

SCHEDULE_ACTIVITY_TASK_PREFIXES = (
    ("BUILDER_FEE_", "LEISURE"),
    ("BUILDER_RESTOCK_", "WORK"),
    ("BUILDER_", "WORK"),
    ("GRAVEDIGGER_RESTOCK_", "WORK"),
    ("HAULING_STALL_", "LEISURE"),
)

ARTISAN_JOB_IDS = ("Builder", "Blacksmith", "Baker", "Toolmaker")

SCHEDULE_ACTIVITY_STRICT_TASK_PREFIXES = tuple(
    f"{job.upper()}_" for job in ARTISAN_JOB_IDS
)

SCHEDULE_ACTIVITY_STRICT_TASK_PREFIX_EXEMPTIONS = ("BUILDER_FEE_",)

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
    "WAITING_FOR_BUILDER_COMMISSION",
})

SCHEDULE_ACTIVITY_TASK_STATE_FIELDS = (
    "current_work_tile", "tilling_timer", "watering_timer", "well_draw_timer",
    "has_water", "water_day", "water_charges", "carrying_crop",
    "carrying_res", "carrying_amount", "water_collect_amount",
    "station_work_timer", "station_target_tile", "station_phase", "station_carry",
)


# Kept for older callers; scheduling now uses SCHEDULE_ACTIVITY_TASKS.
SCHEDULE_NON_WORK_TASKS = frozenset(
    task
    for group, tasks in SCHEDULE_ACTIVITY_TASKS.items()
    if group != "WORK"
    for task in tasks
) | SCHEDULE_ACTIVITY_NEUTRAL_TASKS

FREE_TIME_SCHEDULE_ACTIVITIES = frozenset({"LEISURE", "ANY"})


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
    # "Rolling_Pin": "TOOL",   # disabled — WIP Baker job
    # "Peel": "TOOL",          # disabled — WIP Baker job
    # "Fishing_Rod": "TOOL",   # disabled — WIP Fisherman job
    "Felling_Axe": "TOOL",
    "Spade": "TOOL",
    "Pickaxe": "TOOL",
    "Sledgehammer": "TOOL",

    # RESOURCES
    "Wood": "RESOURCE",
    "Stone": "RESOURCE",
    "Timber": "RESOURCE",
    "Carved Stone": "RESOURCE",
    "Linen Cloth": "RESOURCE",
    "Copper Ore": "RESOURCE",
    "Gold Ore": "RESOURCE",
    "Iron Ore": "RESOURCE",
    "iron ore": "RESOURCE",
    "Iron Bar": "RESOURCE",
    "iron bar": "RESOURCE",

    # CURRENCY
    "Copper": "CURRENCY",
    "Silver": "CURRENCY",
    "Gold": "CURRENCY",
    "Copper Coin": "CURRENCY",
    "Silver Coin": "CURRENCY",
    "Gold Coin": "CURRENCY",
}



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
    "Felling_Axe": (101, 67, 33),
    "Spade": (146, 64, 14),
    "Pickaxe": (100, 116, 139),
    "Sledgehammer": (71, 85, 105),
    "Copper Ore": (194, 96, 40),
    "Gold Ore": (234, 179, 8),
    "Iron Ore": (120, 72, 40),
    "Iron Bar": (148, 163, 184),
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
        "desc": "Steel builder saw for cutting structural timber and planks."
    },
    "Adze": {
        "id": "Adze",
        "name": "Adze",
        "icon": "🪓",
        "color": (180, 83, 9),
        "desc": "Curved woodworking adze for dressing beams and shaping wood."
    },
    # Disabled until Baker/Fisherman jobs ship — uncomment to re-enable.
    # "Rolling_Pin": {
    #     "id": "Rolling_Pin",
    #     "name": "Rolling Pin",
    #     "icon": "🥖",
    #     "color": (245, 158, 11),
    #     "desc": "Hardwood rolling pin for flattening dough in the bakery."
    # },
    # "Peel": {
    #     "id": "Peel",
    #     "name": "Baker's Peel",
    #     "icon": "🍞",
    #     "color": (217, 119, 6),
    #     "desc": "Broad wooden paddle for loading and removing loaves from the stone oven."
    # },
    # "Fishing_Rod": {
    #     "id": "Fishing_Rod",
    #     "name": "Fishing Rod",
    #     "icon": "🎣",
    #     "color": (14, 165, 233),
    #     "desc": "Flexible ash-wood rod with line and hook for catching fish."
    # },
    "Felling_Axe": {
        "id": "Felling_Axe",
        "name": "Felling Axe",
        "icon": "🪓",
        "color": (101, 67, 33),
        "desc": "Heavy two-handed axe for felling mature forest trees."
    },
    "Spade": {
        "id": "Spade",
        "name": "Spade",
        "icon": "⛏",
        "color": (146, 64, 14),
        "desc": "Flat-bladed spade for replanting saplings on forest tiles."
    },
    "Pickaxe": {
        "id": "Pickaxe",
        "name": "Pickaxe",
        "icon": "⛏",
        "color": (100, 116, 139),
        "desc": "Iron-headed pick for breaking ore out of mine walls."
    },
    "Sledgehammer": {
        "id": "Sledgehammer",
        "name": "Sledgehammer",
        "icon": "🔨",
        "color": (71, 85, 105),
        "desc": "Two-handed sledge carried by miners as part of the trade kit."
    }
}


DEFAULT_STARTER_TOOLS = {
    "Hoe": 0,
    "Sickle": 0,
    "Watering_Can": 0,
    "Hammer": 0
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


# Agricultural Crops System (Cultivated on Farm Permits)
FARMING_BATCH_GROWTH_DAYS = 10.0

FARMING_BATCH_WINDOW_DAYS = 1.0  # 1 in-game day default planting window


CROP_TYPES = {
    "potato": {
        "id": "potato",
        "name": "Potato",
        "icon": "🥔",
        "wip": False,
        "desc": "Hearty staple tuber crop. Each tile yields 5 potatoes 80% of the time, 6 potatoes 15% of the time, and 8 potatoes 5% of the time every 10 days.",
        "growth_days": 10.0,
        "sprout_day": 2.0,
        "leaf_day": 4.0,
        "harvest_day": 10.0,
        "yield_distribution": [
            {"amount": 5, "weight": 0.80},
            {"amount": 6, "weight": 0.15},
            {"amount": 8, "weight": 0.05},
        ],
        "yield_per_tile": 5,
        "yield": 5
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

