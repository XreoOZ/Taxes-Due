"""
Market Purchasing Interface (Forwarder for backward compatibility & Agent 1 integration)
"""
from game.systems.market_service import MarketService
from game.data.config import is_food_item

MarketInterface = MarketService

def request_market_food_purchase(family_id, villager=None, food_item="Potato", quantity=1, market_service=None, building_manager=None, furniture_manager=None, villager_manager=None, stockpile_manager=None):
    """
    Called by AGENT 1 when a villager needs food.
    Agent 2 rule: IF HOUSEHOLD HAS FOOD -> DO NOT BUY FOOD FROM MARKET.
    Returns: (bought: bool, food_name: str, amount: int)
    """
    bm = building_manager or getattr(villager, "building_manager", None) or getattr(market_service, "building_manager", None) or getattr(MarketService, "default_building_manager", None)
    fm = furniture_manager or getattr(villager, "furniture_manager", None) or getattr(MarketService, "default_furniture_manager", None)
    vm = villager_manager or getattr(villager, "villager_manager", None) or getattr(MarketService, "default_villager_manager", None)
    sm = stockpile_manager or getattr(villager, "stockpile_manager", None)

    service = market_service if market_service is not None else MarketService
    target = villager if villager is not None else family_id

    # Agent 2: Enforce household food purchasing restriction before attempting market purchase
    get_stock_fn = getattr(service, "get_household_available_food_stock", getattr(MarketService, "get_household_available_food_stock", None))
    if is_food_item(food_item) and callable(get_stock_fn):
        avail_food = get_stock_fn(
            target,
            furniture_manager=fm,
            villager_manager=vm,
            stockpile_manager=sm
        )
        if avail_food > 0:
            return False, food_item, 0

    if hasattr(service, "purchase_food"):
        try:
            return service.purchase_food(
                family_id=family_id,
                villager=villager,
                food_type=food_item,
                amount=quantity,
                building_manager=bm,
                furniture_manager=fm,
                villager_manager=vm,
                stockpile_manager=sm
            )
        except TypeError:
            return service.purchase_food(
                family_id=family_id,
                villager=villager,
                food_type=food_item,
                amount=quantity
            )
    elif hasattr(service, "buy_food"):
        return service.buy_food(
            family_id=family_id,
            villager=villager,
            item_name=food_item,
            amount=quantity,
            building_manager=bm,
            furniture_manager=fm,
            villager_manager=vm,
            stockpile_manager=sm
        )
    elif hasattr(service, "execute_purchase"):
        ok, msg, receipt = service.execute_purchase(
            target, food_item, quantity,
            building_manager=bm,
            furniture_manager=fm,
            villager_manager=vm,
            stockpile_manager=sm,
            enforce_food_restriction=True
        )
        if ok:
            return True, food_item, quantity
    return False, food_item, 0

