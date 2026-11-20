"""Find which auction house is the player's, from one marker listing they posted in game.

The API does not label houses by realm or faction, and listings carry no seller name, so the
player lists one item at an odd, unique buyout and the probe looks for it in every house of
the ruleset's index.
"""
from pathlib import Path

from yap_forever import bnet, profile


def find_marker_houses(client, ruleset: int, item_id: int, buyout: int) -> list[int]:
    idx = client.get(bnet.index_path(ruleset)).body or {}
    houses = {}
    for h in bnet.index_houses(idx):
        regular = client.get(bnet.house_path(h, ruleset)).body or {}
        comm = client.get(bnet.house_path(h, ruleset, commodities=True)).body or {}
        houses[h] = (regular, comm)
        print(f"house {h}: {len(regular.get('auctions', []))} listings, "
              f"{len(comm.get('auctions', []))} commodity listings")
    return bnet.find_marker(houses, item_id, buyout)


def run(client, region: str, ruleset: int, item_id: int, buyout: int, house_file: Path) -> int:
    """Save the one house holding the marker; leave house_file alone otherwise. Returns an exit code."""
    try:
        matches = find_marker_houses(client, ruleset, item_id, buyout)
    except bnet.AuthError:
        print(bnet.AUTH_MESSAGE)
        return 2
    except bnet.ApiError as e:
        print(e if e.status == 0 else f"{e} — the Forever API route may have changed.")
        return 1
    if len(matches) != 1:
        print(f"marker found in {len(matches)} houses ({matches}); the snapshot may not include it yet. "
              "Try again in an hour, or pick a more unusual buyout.")
        return 1
    profile.save_house(house_file, matches[0], region, ruleset)
    print(f"Your auction house is {matches[0]} (saved to {house_file}).")
    return 0
