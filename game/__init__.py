"""
Game Package - Modular & Plug-and-Play Architecture
Subpackages:
  - game.data: Game configurations and static definitions
  - game.entities: Actors (Player, Villagers, Servants)
  - game.systems: Day cycle, scheduling, speed controls, save/load
  - game.buildings: Buildings, construction sites, furniture
  - game.world: World rendering, camera, area permits, stockpiles
  - game.ui: Raport ledger, HUD, main menu, settings, save modal
"""
import sys
import importlib
import importlib.util

_LEGACY_MODULE_MAP = {
    'game.config': 'game.data.config',
    'game.player': 'game.entities.player',
    'game.villagers': 'game.entities.villagers',
    'game.servants': 'game.entities.servants',
    'game.day_cycle': 'game.systems.core.day_cycle',
    'game.schedule': 'game.systems.work.schedule',
    'game.speed_control': 'game.systems.core.speed_control',
    'game.save_system': 'game.systems.core.save_system',
    'game.furniture': 'game.buildings.furniture',
    'game.camera': 'game.world.camera',
    'game.permits': 'game.world.permits',
    'game.stockpile': 'game.world.stockpile',
    'game.ui_raport': 'game.ui.ui_raport',
    'game.hud': 'game.ui.hud',
    'game.menu': 'game.ui.menu',
    'game.settings': 'game.ui.modals.settings',
    'game.save_modal': 'game.ui.modals.save_modal',
    'game.pathfinding': 'game.world.navigation.pathfinding',
    'game.job_tool_system': 'game.systems.work.job_tool_system',
    'game.currency': 'game.systems.economy.currency',
    'game.market_service': 'game.systems.economy.market_service',
    'game.market_modal': 'game.ui.modals.market_modal',
    'game.market_interface': 'game.systems.economy.market_service',
    'game.household_inventory': 'game.systems.economy.household_inventory',
}

class _LegacyImportFinder:
    def find_spec(self, fullname, path, target=None):
        if fullname in _LEGACY_MODULE_MAP:
            target_mod = _LEGACY_MODULE_MAP[fullname]
            spec = importlib.util.find_spec(target_mod)
            if spec:
                return spec
        return None

if not any(isinstance(finder, _LegacyImportFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _LegacyImportFinder())

# Pre-bind sys.modules for instant availability
import game.data.config as _cfg
sys.modules['game.config'] = _cfg
