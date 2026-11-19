"""Disenchanting uncommon armor and weapons: Forever gates and skill-ups, Classic material odds."""
import tomllib

from yap_forever.config import STATIC_DIR

WEAPON, ARMOR = 2, 4
UNCOMMON = 2
NOT_DISENCHANTABLE = 999

with open(STATIC_DIR / "disenchant.toml", "rb") as _f:
    _DATA = tomllib.load(_f)
BANDS = _DATA["band"]
DE_THRESHOLDS: tuple[int, int, int, int] = tuple(_DATA["skill_ups"])
ESSENCE_PAIRS: dict[int, int] = {int(k): v for k, v in _DATA["essence_pairs"].items()}  # lesser -> greater


def _band(item_level: int):
    for b in BANDS:
        if item_level <= b["max_ilvl"]:
            return b
    return None


def de_skill_needed(item_level: int) -> int:
    b = _band(item_level)
    return b["skill"] if b else NOT_DISENCHANTABLE


def de_yield(item) -> dict[int, float]:
    """Expected count of each material from disenchanting one item."""
    if item.no_disenchant or item.quality != UNCOMMON or item.class_id not in (WEAPON, ARMOR):
        return {}
    b = _band(item.item_level)
    if not b:
        return {}
    dust, ess = b["dust"], b["essence"]
    dust_chance, ess_chance = dust[3], ess[3]
    if item.class_id == WEAPON:
        dust_chance, ess_chance = ess_chance, dust_chance
    out = {dust[0]: dust[2] * dust_chance, ess[0]: ess[2] * ess_chance}
    if "shard" in b:
        out[b["shard"][0]] = out.get(b["shard"][0], 0) + b["shard"][2] * b["shard"][3]
    return out


def de_value(item, market, items) -> int:
    """Expected copper from one disenchant: each material at AH net sell or vendor price."""
    total = 0.0
    for mat, count in de_yield(item).items():
        info = items.get(mat)
        total += count * max(market.net_sell(mat) or 0, info.sell_price if info else 0)
    return int(total)
