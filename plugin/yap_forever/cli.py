"""One command line for players: init, check, probe, prices, plan.

Every next-step message names the exact command for the player's system (see command_hint).
"""
import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

from yap_forever import auctionator, bnet, prices, probe, profile, remote, settings
from yap_forever.settings import Paths, command_hint

__all__ = ["command_hint", "main"]

PROFILE_TEMPLATE = """# yap-forever profile: edit to match your account.
region = "eu"        # eu, us, kr or tw
ruleset = 2          # 2 = Normal
faction = "alliance" # alliance or horde

# One section per character you plan for, by its full two-word Forever name, in quotes.
# Favor standing: Neutral, Friendly, Honored, Revered, Exalted.
[characters."Firstname Lastname"]
favor_standing = "Neutral"
"""

API_CLIENTS = "https://develop.battle.net/access/clients"


def _create(path: Path, text: str, private: bool = False) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if private and os.name != "nt":
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        path.write_text(text, encoding="utf-8")
    return True


def cmd_init(paths: Paths) -> int:
    for d in (paths.root, paths.root / "characters", paths.cache, paths.reports):
        d.mkdir(parents=True, exist_ok=True)
    creds = json.dumps({"client_id": "", "client_secret": "", "region": "eu"}, indent=1) + "\n"
    for path, text, private in ((paths.profile, PROFILE_TEMPLATE, False),
                                (paths.credentials, creds, True)):
        print(f"{'created' if _create(path, text, private) else 'kept   '} {path}")
    print(f"Next: edit {paths.profile}, put your API client into {paths.credentials} "
          f"(never paste it into a chat), then run: {command_hint('check')}")
    return 0


def _client(paths: Paths, prof: profile.Profile) -> bnet.Client:
    return bnet.Client(settings.load_credentials(paths.credentials), token_cache=paths.token,
                       region=prof.region)


def cmd_check(paths: Paths, offline: bool) -> int:
    lines, missing = [], False
    try:
        imported = prices.Market.load(paths.prices).source == "auctionator" if paths.prices.exists() else False
    except ValueError:  # the prices line reports it below
        imported = False

    def line(name: str, ok: bool, text: str, needed: bool = True):
        nonlocal missing
        if not ok and not needed:  # imported prices need no API client and no house
            lines.append(f"{name:<12} not needed with imported prices")
            return
        missing |= not ok
        lines.append(f"{name:<12} {'OK' if ok else 'MISSING:'} {text}")

    v = sys.version_info
    line("Python", True, f"{v.major}.{v.minor}")
    prof = None
    try:
        prof = profile.load_profile(paths.profile)
        line("profile", True, f"{prof.region}, ruleset {prof.ruleset}, {prof.faction}, "
                              f"characters: {', '.join(prof.characters) or 'none'}")
    except (FileNotFoundError, ValueError) as e:
        line("profile", False, str(e))
    creds_ok = False
    try:
        settings.load_credentials(paths.credentials)
        creds_ok = True
        line("credentials", True, str(paths.credentials))
    except FileNotFoundError:
        line("credentials", False, f"no {paths.credentials}: run {command_hint('init')}", needed=not imported)
    except ValueError:
        line("credentials", False, f"put your API client ID and secret into {paths.credentials} "
                                   f"(create a client at {API_CLIENTS})", needed=not imported)
    except PermissionError as e:
        line("credentials", False, f"{e} ({paths.credentials})", needed=not imported)
    if offline:
        lines.append(f"{'API token':<12} skipped (--offline)")
    elif creds_ok and prof:
        try:
            _client(paths, prof).token()
            line("API token", True, "Battle.net accepted the client")
        except (bnet.AuthError, bnet.ApiError) as e:
            line("API token", False, str(e))
    try:
        line("house", True, str(profile.load_house(paths.house)))
    except (FileNotFoundError, ValueError) as e:
        line("house", False, str(e), needed=not imported)
    if paths.prices.exists():
        try:
            line("prices", True, prices.Market.load(paths.prices).snapshot_time or "saved")
        except ValueError as e:
            line("prices", False, str(e))
    else:
        line("prices", False, f"run {command_hint('prices')}")
    print("\n".join(lines))
    return 1 if missing else 0


def cmd_probe(paths: Paths, item: int, buyout: int) -> int:
    try:
        prof = profile.load_profile(paths.profile)
        client = _client(paths, prof)
    except (FileNotFoundError, ValueError, PermissionError) as e:
        print(e)
        return 1
    return probe.run(client, prof.region, prof.ruleset, item, buyout, paths.house)


def cmd_prices_auctionator(paths: Paths, file: Path, realm: str | None) -> int:
    try:
        m = auctionator.load_auctionator(file, realm)
    except OSError as e:
        print(f"can't read {file}: {e.strerror or e}")
        return 1
    except ValueError as e:
        print(e)
        return 1
    m.save(paths.prices)
    print(f"Saved {len(m.listings)} items from Auctionator, scan day {m.scan_day or 'unknown'} "
          f"({m.dropped} left out: {prices.dropped_reason()}).")
    return 0


def _remote_accept(paths: Paths):
    """The check for a copied prices file: its region and ruleset are the profile's, and its house is the
    saved house when there is one. Returns the reason to refuse it, or None. Nothing is compared when the
    profile can't be read (the plan checks the house later)."""
    try:
        prof = profile.load_profile(paths.profile)
    except (FileNotFoundError, ValueError):
        return lambda m: None
    try:
        house = profile.load_house(paths.house)
    except (FileNotFoundError, ValueError):
        house = None

    def accept(m: prices.Market) -> str | None:
        for field, theirs, ours in (("region", m.region, prof.region), ("ruleset", m.ruleset, prof.ruleset),
                                    ("house", m.house, house)):
            if ours is not None and theirs != ours:
                return (f"the copied prices are for {field} {theirs if theirs not in (None, '') else 'unknown'}, "
                        f"but yours is {ours}")
        return None
    return accept


def cmd_prices_remote(paths: Paths, host: str | None) -> int:
    try:
        saved = settings.load_remote(paths.remote)
    except ValueError as e:
        print(e)
        return 1
    if host is not None:
        host = host.strip()
        if not host:
            print("--host is empty: give the machine to use, e.g. --host user@machine")
            return 1
        saved = dataclasses.replace(saved, host=host) if saved else settings.Remote(host)
    if saved is None:
        print(f"no remote machine set: write host = \"...\" in {paths.remote} "
              "(see references/setup.md), or pass --host HOST")
        return 1
    return remote.fetch_remote(saved, paths.prices, accept=_remote_accept(paths))


def cmd_prices(paths: Paths) -> int:
    try:
        prof = profile.load_profile(paths.profile)
        house = profile.load_house(paths.house)
        client = _client(paths, prof)
    except (FileNotFoundError, ValueError, PermissionError) as e:
        print(e)
        return 1
    paths.cache.mkdir(parents=True, exist_ok=True)
    return prices.fetch(client, house, prof.ruleset, paths.prices, paths.cache / "snapshots.log",
                        region=prof.region)


def cmd_plan(paths: Paths, character: str, profs: list[str] | None = None) -> int:
    try:
        prof = profile.load_profile(paths.profile)
    except (FileNotFoundError, ValueError) as e:
        print(e)
        return 1
    if character not in prof.characters:
        print(f"no character {character!r} in {paths.profile}; known: {', '.join(prof.characters) or 'none'}")
        return 1
    group = prof.group_of(character)
    if group != (prof.ruleset, prof.faction):
        print(f"{character} plays on ruleset {group[0]}, {group[1]}, but your saved prices are for ruleset "
              f"{prof.ruleset}, {prof.faction}: there are no prices yet for that ruleset and faction, "
              "and planning it isn't supported yet")
        return 1
    if not paths.prices.exists():
        print(f"no prices yet: run {command_hint('prices')}")
        return 1
    try:
        saved_for = prices.Market.load(paths.prices).house
        house = profile.load_house(paths.house)
    except FileNotFoundError:
        house = None
    except ValueError as e:
        print(e)
        return 1
    if saved_for is not None and house is not None and saved_for != house:
        print(f"your prices are for house {saved_for}, but your auction house is {house}: "
              f"run {command_hint('prices')}")
        return 1
    stock = paths.character(character) / "stock.toml"
    bags = paths.character(character) / "bags.toml"
    if not stock.exists() and bags.exists():  # a home from before every character got a stock file
        from yap_forever import migrate
        try:
            migrate.bags_to_stock(bags, stock)
        except ValueError as e:
            print(e)
            return 1
        print(f"made {stock} from {bags}: fill in {migrate.FILL_IN}")
    if not stock.exists():
        print(f"no stock file for {character}: create {stock} (see the skill's setup guide)")
        return 1
    from yap_forever import config
    try:
        flags = [config.parse_prof_arg(x) for x in profs or []]
        if len(flags) > 2 or len({p for p, _ in flags}) < len(flags):
            print("plan one or two different professions at a time (one --prof each)")
            return 1
        goals = dict(flags) or config.load_stock(stock).goals
        if len(goals) > 2:
            print(f"{stock} has goals for {len(goals)} professions: plan one or two at a time (one --prof each)")
            return 1
    except ValueError as e:
        print(e)
        return 1
    if not goals:
        print("name the professions to plan: "
              + command_hint(f"plan --character {character!r} --prof blacksmithing:225 [--prof enchanting:225]")
              + " (a skill 1-300 or a recipe name per profession), or save them under [goals] in " + str(stock))
        return 1
    import urllib.error

    from yap_forever import plan, shared  # heavy imports only when planning
    try:
        me = prof.characters[character]
        table, files = plan.write_reports(paths, stock, me.favor_standing, goals, me, prof.overtime_reading,
                                          faction=prof.faction, profile_names=list(prof.characters),
                                          study_hint_gold_per_point=prof.study_hint_gold_per_point,
                                          group=shared.load_group(paths, prof, character))
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"could not download game data ({getattr(e, 'reason', e)}): check your network or VPN, "
              f"then run {command_hint('plan --character ' + character)} again")
        return 1
    except ValueError as e:  # a recipe goal the data doesn't know or can't learn
        print(e)
        return 1
    print(table)
    print()
    for key, path in files.items():
        print(f"{key}: {path}")
    return 0


def cmd_migrate(paths: Paths, args) -> int:
    from yap_forever.migrate import migrate
    characters: dict[str, Path] = {}
    for c in args.character:
        name, sep, file = c.partition("=")
        if not (sep and name.strip() and file.strip()):
            print(f"--character needs NAME=FILE, got {c!r}")
            return 1
        if name in characters:
            print(f"--character {name!r} given twice")
            return 1
        characters[name] = Path(file).expanduser()
    try:
        actions = migrate(args.from_data.expanduser(), paths, characters,
                          region=args.region, ruleset=args.ruleset, faction=args.faction)
    except ValueError as e:
        print(e)
        return 1
    for line in actions:
        print(line)
    print(f"Copy your API client into {paths.credentials} yourself, then run {command_hint('check')}")
    return 0


def main(argv: list[str], paths: Paths | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yap_forever", description="WoW: Forever profession planner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create your home folder, profile and credentials file")
    c = sub.add_parser("check", help="show what is set up and what is missing")
    c.add_argument("--offline", action="store_true", help="don't contact Battle.net")
    p = sub.add_parser("probe", help="find your auction house from a marker listing")
    p.add_argument("--item", type=int, required=True, help="item ID of the marker listing")
    p.add_argument("--buyout", type=int, required=True, help="its buyout in copper")
    pr = sub.add_parser("prices", help="download your auction house's prices")
    how = pr.add_mutually_exclusive_group()
    how.add_argument("--auctionator", type=Path, metavar="PATH",
                     help="read prices from Auctionator's saved file (Auctionator.lua) instead of downloading")
    how.add_argument("--remote", action="store_true",
                     help="fetch the prices through another machine over ssh (settings: remote.toml)")
    pr.add_argument("--realm", help="realm key in Auctionator.lua, when it holds several")
    pr.add_argument("--host", help="with --remote: the machine to use instead of remote.toml's host")
    pl = sub.add_parser("plan", help="plan a character's professions")
    pl.add_argument("--character", required=True)
    pl.add_argument("--prof", action="append", default=[], metavar="NAME:TARGET",
                    help="a profession and its target: a skill 1-300 or a recipe (once or twice)")
    m = sub.add_parser("migrate", help="move a pre-yap-forever planner folder into your home folder")
    m.add_argument("--from-data", type=Path, required=True, help="old data folder (house and prices are copied)")
    m.add_argument("--character", action="append", required=True, metavar="NAME=FILE",
                   help="a character and its stock file or bags file (repeat for every character)")
    m.add_argument("--region", choices=profile.REGIONS, default="eu", help="your region (default eu)")
    m.add_argument("--ruleset", type=int, default=2, help="your ruleset ID (default 2)")
    m.add_argument("--faction", choices=profile.FACTIONS, default="alliance", help="default alliance")
    args = parser.parse_args(argv)
    paths = paths or settings.paths()
    if args.command == "init":
        return cmd_init(paths)
    if args.command == "check":
        return cmd_check(paths, args.offline)
    if args.command == "probe":
        return cmd_probe(paths, args.item, args.buyout)
    if args.command == "prices":
        if args.auctionator is not None:
            return cmd_prices_auctionator(paths, args.auctionator.expanduser(), args.realm)
        if args.realm is not None:
            print("--realm goes with --auctionator")
            return 1
        if args.host is not None and not args.remote:
            print("--host goes with --remote")
            return 1
        if args.remote:
            return cmd_prices_remote(paths, args.host)
        return cmd_prices(paths)
    if args.command == "migrate":
        return cmd_migrate(paths, args)
    return cmd_plan(paths, args.character, args.prof)
