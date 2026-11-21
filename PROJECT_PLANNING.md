# Taxes-Due: Project Planning & Roadmap Documentation

> **Multi-Agent Coordination Charter**
> This repository is actively developed by 3 AI agents in parallel:
> - **AGENT 1**: Household Survival, Hunger, Thirst & AI Needs.
> - **AGENT 2**: Market, Currency, Economy & Purchasing.
> - **AGENT 3**: Production Distribution, Farming Adjustments & WIP Planning.

---

## 1. Development Boundaries & Domain Ownership

| System Domain | Responsible Agent | Integration Interfaces / Shared Boundaries |
| :--- | :--- | :--- |
| **Household Survival, Hunger, Thirst** | **AGENT 1** | Owns Villager daily consumption records, thirst/water needs, starvation/death checks, Family List primary need indicators. |
| **Market, Currency, Economy** | **AGENT 2** | Owns Market stall construction, Market Profile, Currency/Coin transactions, Purchasing algorithms, Stall pricing. |
| **Production, Farming, Distribution & Planning** | **AGENT 3** | Owns proportional production distribution, participating worker math, indivisible item apportionment, weighted potato farming yields, production reports, and persistent roadmap planning. |

---

## 2. Core Implemented Systems (Active & Functional)

1. **Household Production Distribution System**
   - **Formula**: `Household share = Household participating worker count / Total participating worker count`.
   - **Apportionment Engine**: Largest Remainder (Hamilton-Hare) method with persistent credit tracking across production cycles.
   - **Integrity Guarantee**: Strictly zero item loss and zero item duplication ($\sum \text{Allocated} = \text{Yield}$ in every cycle).
   - **Delivery**: Output is deposited directly into each household's private storage (chests), never redirected to the market without player/household decree.
   - **Generic Support**: Agnostic of profession (Farmers, Builders, Blacksmiths, Bakers).

2. **Potato Farming Yield Distribution**
   - **Yield**: 2 Potatoes with 80% probability, 4 with 15%, and 5 with 5% per harvested tile every 10 days.
   - **Cycle**: Standard 10-day growth cycle preserved (Sprout: Day 2, Leaf: Day 4, Harvest: Day 10).
   - **Configuration**: Weighted outcomes are read from `CROP_TYPES["potato"]["yield_distribution"]`.

3. **Household Socage Tax Collection**
   - The Tax Collector works only during scheduled work hours and visits living households through a dynamic queue.
   - A household representative must arrive and transfer the configured share of chest currency directly to the collector.
   - After the round handles every household, the collector deposits the collected currency in the landlord's Treasury.

4. **RimWorld-Style Work Priorities Grid**
   - Dynamic 1–4 priority matrix and activity schedule.

5. **RimWorld-Style 24-Hour Schedule Matrix**
   - Hourly activity brush painter for routines (Work, Sleep, Recreation, Any).

6. **Universal Parallel AI Work Execution**
   - Obstacle-aware path reservation, dynamic yielding, and parallel tile operations.

---

## 3. Future Tax Modes (WIP)

Household socage coin collection through the Tax Collector is active. Agricultural
tithes and production-based deductions remain future work; household production
distribution is not taxed.

---

## 4. Tracked Roadmap Items

Planned features and implemented milestones remain recorded below and mirrored in the in-game UI (`Reports -> Roadmap / WIP`):

### 1. Corpse Burial & Removal
- **Status**: IMPLEMENTED
- **Category**: Sanitation & AI Needs
- **Lead Agent**: Agent 1
- **Description**: Gravediggers transport corpses, prepare and bury graves, hold bodies safely when the cemetery is full, resume burial when space opens, and reuse graves after 30 days.

### 2. Household-Owned Market Management
- **Category**: Market & Commerce
- **Lead Agent**: Agent 2
- **Description**: Allow settler households to purchase, own, and independently operate market stalls to retail their surplus goods.

### 3. Market Assignment
- **Category**: Market & Commerce
- **Lead Agent**: Agent 2
- **Description**: Administrative assignment system for designating merchant households or stall managers to commercial market stalls.

### 4. Household Production-Based Market Inventory
- **Category**: Economy & Logistics
- **Lead Agent**: Agents 2 & 3
- **Description**: Logistics pipeline allowing household surplus inventory to supply market stalls for domestic sale.

### 5. Different Household Production Types
- **Category**: Guilds & Production
- **Lead Agent**: Agent 3
- **Description**: Support diverse household specializations (Blacksmithing tools, Carpentry furniture, Bakeries, Weaving) supplying unique trade commodities.

### 6. Dynamic Market Pricing
- **Category**: Market & Economy
- **Lead Agent**: Agent 2
- **Description**: Supply-and-demand price oscillation engine based on local commodity scarcity, abundance, and seasonal harvest yields.

### 7. Household Taxation
- **Category**: Taxation & Governance
- **Lead Agent**: Agent 3
- **Description**: Household socage coin collection is active; agricultural tithes (such as a percentage of potato harvest) remain future work.

### 8. Additional Food Categories & Types
- **Category**: Agriculture & Nutrition
- **Lead Agent**: Agents 1 & 3
- **Description**: Expand food variety beyond potatoes to include Wheat, Bread, Carrots, and Corn with varying nutrition and spoilage rates.

### 9. Water Market / Water Purchasing
- **Category**: Survival & Trade (Future Consideration)
- **Lead Agent**: Agent 2
- **Description**: Long-term conceptual framework for commercial water utilities. Currently excluded from implementation to prevent economic distortion.

---

## 5. Persistence & Update Rules

- WIP items must never be silently removed or truncated.
- When an agent implements a planned feature, its status in `game/data/planning.py` and this document must be updated to `IMPLEMENTED`.
- The in-game UI (`Reports -> Roadmap / WIP`) dynamically queries `game/data/planning.py`, ensuring player visibility matches technical documentation at all times.
