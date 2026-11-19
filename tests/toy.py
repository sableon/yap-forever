"""Small hand-made game data for cost model and planner tests."""
from yap_forever.config import Stock
from yap_forever.favor import FavorData
from yap_forever.gamedata import GameData, ItemInfo, Rank, Recipe
from yap_forever.prices import Market

COPPER_BAR, IRON_BAR, IRON_ORE, DUST, ESSENCE, SHARD = 2840, 3575, 2772, 10940, 10998, 10978
BELT, VEST, STONE, ROD, ROD_TOOL, SCROLL, ODD = 2857, 2851, 2862, 6217, 6218, 5555, 1234
HAMMER = 5956
GREATER_ESSENCE = 11082


def item(i, name, quality=1, ilvl=10, cls=7, sell=10, buy=40, bonding=0):
    return ItemInfo(i, name, quality, ilvl, cls, sell, buy, bonding=bonding)


def recipe(spell, name, line, reagents, output=None, t=(1, 300, 300, 300), req=1,
           source="trainer", fee=0, scroll=None, tools=None):
    return Recipe(spell, name, line, reagents, output, t, req, source, fee, scroll, tools or [])


def gamedata(recipes, quest_items=()):
    items = {i.id: i for i in [
        item(COPPER_BAR, "Copper Bar", sell=15),
        item(IRON_BAR, "Iron Bar", sell=50),
        item(IRON_ORE, "Iron Ore", sell=20),
        item(DUST, "Strange Dust", sell=5),
        item(ESSENCE, "Lesser Astral Essence", sell=30),
        item(GREATER_ESSENCE, "Greater Astral Essence", sell=90),
        item(SHARD, "Small Glimmering Shard", sell=50),
        item(BELT, "Runed Copper Belt", quality=2, ilvl=22, cls=4, sell=100),
        item(VEST, "Copper Chain Vest", quality=1, ilvl=8, cls=4, sell=20),
        item(STONE, "Rough Sharpening Stone", sell=2),
        item(ROD, "Copper Rod", sell=20),
        item(ROD_TOOL, "Runed Copper Rod", sell=25),
        item(HAMMER, "Blacksmith Hammer", sell=4, buy=18),
        item(SCROLL, "Plans: Something", sell=100),
        item(ODD, "Odd Thing", sell=0),
    ]}
    ranks = {164: [Rank(150, 450, 50, 10), Rank(225, 4500, 125, 20)],
             333: [Rank(150, 500, 50, 10), Rank(225, 5000, 125, 20)]}
    return GameData(recipes={r.spell_id: r for r in recipes}, items=items, trainer_ranks=ranks,
                    vendor_prices={ROD: 124}, quest_items=set(quest_items),
                    tool_items={162: HAMMER, 373: ROD_TOOL}, tool_masks={162: 4, 373: 1},
                    item_tool_category={HAMMER: 162, ROD_TOOL: 373})


def stock(items=None, favor=0, mining=0, level=60, skills=None, shared=None):
    """shared: another character's mailable items, {name: {item: n}}."""
    return Stock(items=items or {}, favor=favor, cash=120000, level=level, mining=mining,
                 short_farm_ore=200, marker=None, skills=skills or {}, shared=shared or {})


def market(listings=None):
    return Market(listings or {})


NO_FAVOR = FavorData({}, {}, [])
