"""Game data — economy domain constants.

Auto-extracted from config.py; imported back by game.data.config
so `from game.data.config import X` keeps working everywhere.
"""

# -----------------------------------------------------------------------------
# ECONOMY — currency, market, prices, taxes, wealth
# -----------------------------------------------------------------------------
MARKET_SALES_REPORT_PERIOD_DAYS = 10

BUILDER_INSUFFICIENT_LANDLORD_COIN_MESSAGES = (
    "The treasury does not hold enough coin for this commission, my Lord.",
    "I cannot pay the Builder yet; the treasury is short on coin.",
    "The available coin falls short of the Builder's price, Sire.",
    "We need more treasury coin before this work can be commissioned.",
    "The Builder's fee exceeds our current coin reserve, my Lord.",
)


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
DEFAULT_MATERIAL_RESTOCK_BATCH = 10
MAX_MATERIAL_RESTOCK_BATCH = 50


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
    "Hoe": 10,
    "Sickle": 10,
    "Watering_Can": 10,
    "Saw": 10,
    "Adze": 10,
    "Felling_Axe": 10,
    "Spade": 10,
    "Pickaxe": 10,
    "Sledgehammer": 10,
    "Hammer": 10,
    "Tongs": 10,
    "Iron Ore": 4,      # Raw ore; base for smelting cost
    "Iron Bar": 10,     # Smelted bar: ore + wood + labor priced in
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
    "Felling_Axe": "Felling_Axe",
    "Spade": "Spade",
    "Pickaxe": "Pickaxe",
    "Sledgehammer": "Sledgehammer",
    "Hammer": "Hammer",
    "Tongs": "Tongs",
    "Iron Ore": "Iron Ore",
    "Iron Bar": "Iron Bar",
}

MARKET_CURRENCY_DENOMINATIONS = ("Gold", "Silver", "Copper")

MARKET_DEFAULT_HOUSEHOLD_SALE_PERCENT = 20
MARKET_HOUSEHOLD_SALE_PERCENT_MIN = 10
MARKET_HOUSEHOLD_SALE_PERCENT_MAX = 100
MARKET_ALLOC_STEP = 10
MARKET_PRICE_STEP = 1

HOUSEHOLD_STALL_HAUL_CAPACITY = 20
HOUSEHOLD_STALL_FOOD_RESERVE_DAYS = 2
HOUSEHOLD_STALL_WATER_RESERVE_DAYS = 2
MARKET_UI_ITEMS_PER_PAGE = 4
MARKET_LORD_COMMON_GOODS = ("Potato", "Wood", "Stone", "Water")

MARKET_QUANTITY_DEFAULT = 10

MARKET_QUANTITY_MAX = 1000

MARKET_PERCENT_STEP = 5
MARKET_RESTOCK_ORDER_TIMEOUT_SECONDS = 900.0  # Restock orders expire instead of zombie-pulling storage forever

MARKET_WEALTH_REFERENCE_DAYS = 7.0

MARKET_WEALTH_PRICE_ELASTICITY = 0.12

MARKET_WEALTH_PRICE_FACTOR_MIN = 0.75

MARKET_WEALTH_PRICE_FACTOR_MAX = 1.5

VILLAGER_HUD_COUNT_REFRESH_SECONDS = 0.5

MARKET_WEALTH_CONTEXT_REFRESH_SECONDS = 0.5

HAPPINESS_WEALTH_DENOMINATION = "Gold"

TAX_UNHAPPINESS_DURATION_DAYS = 10


# =====================================================================
# Church, Priest, Cemetery, Gravedigger & Toilet Systems (Agent 3)
# =====================================================================
DEFAULT_CHURCH_TAX = {"Gold": 0, "Silver": 0, "Copper": 1}  # 1 Copper per household per day default

DEFAULT_SOCAGE_TAX_ENABLED = False

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

