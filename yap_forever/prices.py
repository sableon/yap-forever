"""Auction house prices: download a house's snapshot and answer price questions."""
import datetime
import json
from pathlib import Path

from yap_forever import bnet
from yap_forever import settings

AH_CUT = 0.05
STALE_DAYS = 3  # an imported scan older than this many days before today gets a warning


class Market:
    def __init__(self, listings: dict[int, list[tuple[int, int]]], snapshot_time: str = ""):
        # item -> [(unit price, quantity)] sorted cheapest first
        self.listings = {i: sorted(v) for i, v in listings.items()}
        self.snapshot_time = snapshot_time
        # Which house these prices belong to, and the commodities snapshot time (set by fetch).
        self.house: int | None = None
        self.region = ""
        self.ruleset: int | None = None
        self.commodities_time = ""
        # Where the prices came from: "api" (full listings) or "auctionator" (one price and count per
        # item); for an import, the scan day and how many items were left out as not listed.
        self.source = "api"
        self.scan_day = ""
        self.dropped = 0

    @classmethod
    def from_snapshot(cls, regular: dict, commodities: dict, snapshot_time: str = "") -> "Market":
        out: dict[int, list[tuple[int, int]]] = {}
        for a in (regular or {}).get("auctions", []):
            if "buyout" not in a:
                continue  # bid-only listing
            # Forever regular listings are always quantity 1, so buyout is the unit price.
            out.setdefault(a["item"]["id"], []).append((a["buyout"], a.get("quantity", 1)))
        for a in (commodities or {}).get("auctions", []):
            out.setdefault(a["item"]["id"], []).append((a["unit_price"], a["quantity"]))
        return cls(out, snapshot_time)

    def buy_cost(self, item_id: int, qty: int) -> int | None:
        """Cost of buying qty units cheapest-first; None if not enough listed."""
        if qty <= 0:
            return 0
        total, need = 0, qty
        for price, n in self.listings.get(item_id, []):
            take = min(n, need)
            total += take * price
            need -= take
            if need == 0:
                return total
        return None

    def min_price(self, item_id: int) -> int | None:
        lst = self.listings.get(item_id)
        return lst[0][0] if lst else None

    def net_sell(self, item_id: int) -> int | None:
        p = self.min_price(item_id)
        return None if p is None else int(p * (1 - AH_CUT))

    def depth(self, item_id: int) -> int:
        return sum(n for _, n in self.listings.get(item_id, []))

    def save(self, path: Path | None = None) -> None:
        path = Path(path) if path is not None else settings.paths().prices
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"snapshot_time": self.snapshot_time, "commodities_time": self.commodities_time,
                "house": self.house, "region": self.region, "ruleset": self.ruleset,
                "source": self.source, "scan_day": self.scan_day, "dropped": self.dropped,
                "listings": {str(i): v for i, v in self.listings.items()}}
        path.write_text(json.dumps(data), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | None = None) -> "Market":
        path = Path(path) if path is not None else settings.paths().prices
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            m = cls({int(i): [tuple(x) for x in v] for i, v in d["listings"].items()},
                    d.get("snapshot_time", ""))
            m.house, m.region, m.ruleset = d.get("house"), d.get("region", ""), d.get("ruleset")
            m.commodities_time = d.get("commodities_time", "")
            m.source, m.scan_day, m.dropped = d.get("source", "api"), d.get("scan_day", ""), d.get("dropped", 0)
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise ValueError(f"{path} is damaged ({type(e).__name__}): "
                             f"run {settings.command_hint('prices')}") from None
        return m


def source_line(market: "Market", today: datetime.date | None = None) -> str:
    """The header line for guide and report: where the prices came from. Empty for API prices."""
    if market.source != "auctionator":
        return ""
    # a hand-edited prices file can hold anything in these fields
    scan_day = market.scan_day if isinstance(market.scan_day, str) else ""
    dropped = market.dropped if isinstance(market.dropped, int) and not isinstance(market.dropped, bool) else 0
    line = (f"Prices: Auctionator scan of {scan_day or 'unknown date'} (one price per item, no listing "
            "depth: costs are a lower bound and AH sale limits are approximate).")
    try:
        age = ((today or datetime.date.today()) - datetime.date.fromisoformat(scan_day)).days
    except ValueError:
        line += " Scan date unknown: scan again for current prices."
    else:
        if age > STALE_DAYS:
            line += f" This scan is {age} days old: scan again for current prices."
    if dropped > 0:
        line += f" {dropped} items older than the scan window left out."
    return line


def fetch(client, house: int, ruleset: int, prices_path: Path, log_path: Path, region: str = "") -> int:
    """Download the house's auctions and commodities unless both are unchanged. Returns an exit code.

    Saved snapshot times are only trusted for the same house, region and ruleset; a different house
    always downloads in full. Auctions and commodities are separate snapshots and are checked apart.
    """
    try:
        old = Market.load(prices_path) if prices_path.exists() else None
    except ValueError:  # damaged: download in full and replace it
        old = None
    same = old is not None and (old.house, old.region, old.ruleset) == (house, region, ruleset)
    since = (old.snapshot_time or None) if same else None
    comm_since = (old.commodities_time or None) if same else None
    regular_path = bnet.house_path(house, ruleset)
    comm_path = bnet.house_path(house, ruleset, commodities=True)
    try:
        r = client.get(regular_path, if_modified_since=since)
        if r.status == 304:
            c = client.get(comm_path, if_modified_since=comm_since)
            if c.status == 304:
                print(f"No new snapshot since {since}.")
                return 0
            r = client.get(regular_path)  # commodities moved: rebuild from both snapshots
        else:
            c = client.get(comm_path)
    except bnet.AuthError:
        print(bnet.AUTH_MESSAGE)
        return 2
    except bnet.ApiError as e:
        print(e if e.status == 0 else f"{e} — the Forever API route may have changed.")
        return 1
    m = Market.from_snapshot(r.body or {}, c.body or {}, r.last_modified or "")
    m.house, m.region, m.ruleset = house, region, ruleset
    m.commodities_time = c.last_modified or ""
    m.save(prices_path)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{r.last_modified}\n")
    print(f"Saved {len(m.listings)} items from house {house}, snapshot {r.last_modified}.")
    return 0
