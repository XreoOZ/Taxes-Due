"""
Persistent Project Planning & Roadmap Registry
Maintains tracked features across development cycles, distinguishing implemented,
partially implemented, and planned WIP features.
"""

# Feature status constants
STATUS_IMPLEMENTED = "IMPLEMENTED"
STATUS_PARTIAL = "PARTIAL"
STATUS_PLANNED = "PLANNED"

PLANNING_FEATURES = [
    # -------------------------------------------------------------
    # 1. Planned WIP Features
    # -------------------------------------------------------------
    {
        "id": "corpse_burial",
        "name": "Corpse Burial & Removal",
        "status": STATUS_IMPLEMENTED,
        "category": "Sanitation & AI Needs",
        "owner_agent": "Agent 1",
        "summary": "Gravediggers transport, bury, and recover corpses when cemetery space opens.",
        "description": "Includes burial commissions, corpse transport, grave materials, full cemetery overflow, and reuse of graves after 30 days."
    },
    {
        "id": "household_market_mgmt",
        "name": "Household-Owned Market Management",
        "status": STATUS_PLANNED,
        "category": "Market & Commerce",
        "owner_agent": "Agent 2",
        "summary": "Allow households to own and manage their own markets.",
        "description": "Enables settler households to acquire market stalls, stock them with goods, and operate commercial trading directly as proprietors."
    },
    {
        "id": "market_assignment",
        "name": "Market Assignment",
        "status": STATUS_PLANNED,
        "category": "Market & Commerce",
        "owner_agent": "Agent 2",
        "summary": "Add a system for assigning households or managers to markets.",
        "description": "Administrative system allowing the Landlord or Village Council to assign designated merchant families or stall managers to commercial market stalls."
    },
    {
        "id": "production_market_inventory",
        "name": "Household Production-Based Market Inventory",
        "status": STATUS_PLANNED,
        "category": "Economy & Logistics",
        "owner_agent": "Agent 2 & 3",
        "summary": "Allow household production to supply market inventory.",
        "description": "Logistics pipeline connecting private household storage and surplus production to market supply, replenishing stall inventories."
    },
    {
        "id": "different_production_types",
        "name": "Different Household Production Types",
        "status": STATUS_PLANNED,
        "category": "Guilds & Production",
        "owner_agent": "Agent 3",
        "summary": "Support different household production specializations supplying different market goods.",
        "description": "Expanded profession-specific output for artisans, carpenters, weavers, smiths, and bakers to produce varied trade commodities."
    },
    {
        "id": "dynamic_pricing",
        "name": "Dynamic Market Pricing",
        "status": STATUS_PLANNED,
        "category": "Market & Economy",
        "owner_agent": "Agent 2",
        "summary": "Automatically adjust prices based on goods abundance and scarcity.",
        "description": "Supply-and-demand price simulation adjusting buying/selling values based on local stockpiles, harvest seasons, and consumer demand."
    },
    {
        "id": "household_taxation",
        "name": "Household Taxation",
        "status": STATUS_IMPLEMENTED,
        "category": "Taxation & Governance",
        "owner_agent": "Agent 3",
        "summary": "Collect configured household socage tax during the tax collector's work schedule.",
        "description": "The collector visits living households in a dynamic queue; a household representative transfers the configured share of chest currency directly to the collector, who deposits it in the landlord's Treasury after the round. Production-based tithes remain future work."
    },
    {
        "id": "food_categories",
        "name": "Additional Food Categories & Types",
        "status": STATUS_PLANNED,
        "category": "Agriculture & Nutrition",
        "owner_agent": "Agent 1 & 3",
        "summary": "Expand the current FOOD category beyond potatoes.",
        "description": "Diversify agricultural crops to include Wheat, Carrots, Corn, Bread, and processed foodstuffs with distinct nutritional value."
    },
    {
        "id": "water_market",
        "name": "Water Market / Water Purchasing",
        "status": STATUS_PLANNED,
        "category": "Survival & Trade (Future)",
        "owner_agent": "Agent 2",
        "summary": "Future consideration only. Do not implement water sales or invent water prices.",
        "description": "Long-term theoretical framework for commercial water distribution. Currently excluded from implementation to prevent premature economic distortion."
    },

    # -------------------------------------------------------------
    # 2. Implemented & Functional Features (Active in Game)
    # -------------------------------------------------------------
    {
        "id": "production_distribution",
        "name": "Household Production Distribution",
        "status": STATUS_IMPLEMENTED,
        "category": "Production & Labor",
        "owner_agent": "Agent 3",
        "summary": "Fair proportional output distribution based on participating workers.",
        "description": "Production output is distributed dynamically into household storage according to actual participating worker counts. Handles fractional and indivisible quantities with zero loss."
    },
    {
        "id": "potato_farming_2x",
        "name": "Potato Farming Yield (2-5 / Tile)",
        "status": STATUS_IMPLEMENTED,
        "category": "Agriculture & Food",
        "owner_agent": "Agent 3",
        "summary": "Each harvested potato tile yields 2 Potatoes 80% of the time, 4 Potatoes 15%, or 5 Potatoes 5% every 10 days.",
        "description": "Potato yield is selected from configurable weighted outcomes per tile harvest."
    },
    {
        "id": "work_priorities",
        "name": "Work Priorities Matrix",
        "status": STATUS_IMPLEMENTED,
        "category": "Management",
        "owner_agent": "Core",
        "summary": "RimWorld-style numerical work priority assignment (1=High to 4=Low, -=Off).",
        "description": "Hierarchical servant and villager work dispatch system allowing fine-grained labor assignment across tasks."
    },
    {
        "id": "schedule_matrix",
        "name": "24-Hour Schedule Matrix",
        "status": STATUS_IMPLEMENTED,
        "category": "Management",
        "owner_agent": "Core",
        "summary": "24-Hour hourly activity timetable for villager routines (Work, Sleep, Recreation, Any).",
        "description": "Customizable hourly schedule presets for governing settler daily routines."
    },
    {
        "id": "parallel_ai_work",
        "name": "Universal Parallel Work Execution",
        "status": STATUS_IMPLEMENTED,
        "category": "AI Engine",
        "owner_agent": "Core",
        "summary": "Tile reservation and collision-aware multi-agent parallel labor.",
        "description": "Enables dozens of villagers to work simultaneously on the same farm or construction site without clumping or deadlocks."
    }
]

def get_all_planning_features():
    """Returns all tracked features"""
    return list(PLANNING_FEATURES)

def get_features_by_status(status):
    """Filter features by status: PLANNED, PARTIAL, or IMPLEMENTED"""
    return [f for f in PLANNING_FEATURES if f.get("status") == status]

def get_wip_features():
    """Returns all non-implemented features (PLANNED and PARTIAL)"""
    return [f for f in PLANNING_FEATURES if f.get("status") in (STATUS_PLANNED, STATUS_PARTIAL)]

def update_feature_status(feature_id, new_status, notes=None):
    """Updates a feature's planning status"""
    for f in PLANNING_FEATURES:
        if f.get("id") == feature_id:
            f["status"] = new_status
            if notes:
                f["notes"] = notes
            return True
    return False
