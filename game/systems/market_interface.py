"""
Market Purchasing Interface (Forwarder for backward compatibility & Agent 1 integration)
"""
from game.systems.market_service import MarketService

MarketInterface = MarketService

def request_market_food_purchase(family_id, villager=None, food_item="Potato", quantity=1, market_service=None, building_manager=None, furniture_manager=None, villager_manager=None):
    """
    Called by AGENT 1 when a villager reaches critical hunger and has no food at home.
    Returns: (bought: bool, food_name: str, amount: int)
    """
    bm = building_manager or getattr(villager, "building_manager", None) or getattr(market_service, "building_manager", None) or getattr(MarketService, "default_building_manager", None)
    fm = furniture_manager or getattr(villager, "furniture_manager", None) or getattr(MarketService, "default_furniture_manager", None)
    vm = villager_manager or getattr(villager, "villager_manager", None) or getattr(MarketService, "default_villager_manager", None)

    service = market_service if market_service is not None else MarketService
    target = villager if villager is not None else family_id

    if hasattr(service, "purchase_food"):
        return service.purchase_food(family_id=family_id, villager=villager, food_type=food_item, amount=quantity)
    elif hasattr(service, "buy_food"):
        return service.buy_food(family_id=family_id, villager=villager, item_name=food_item, amount=quantity)
    elif hasattr(service, "execute_purchase"):
        ok, msg, receipt = service.execute_purchase(
            target, food_item, quantity,
            building_manager=bm,
            furniture_manager=fm,
            villager_manager=vm
        )
        if ok:
            return True, food_item, quantity
    return False, food_item, 0

