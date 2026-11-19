"""One command line for players: init, check, probe, prices, plan.

Every next-step message names the exact command for the player's system (see command_hint).
"""
import argparse
import json
import os
import sys
from pathlib import Path

from yap_forever import bnet, prices, probe, profile, settings
from yap_forever.settings import Paths, command_hint

__all__ = ["main", "command_hint"]

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

    def line(name: str, ok: bool, text: str):
        nonlocal missing
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
        line("credentials", False, f"no {paths.credentials}: run {command_hint('init')}")
    except ValueError:
        line("credentials", False, f"put your API client ID and secret into {paths.credentials} "
                                   f"(create a client at {API_CLIENTS})")
    except PermissionError as e:
        line("credentials", False, f"{e} ({paths.credentials})")
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
        line("house", False, str(e))
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

    from yap_forever import plan  # heavy imports only when planning
    try:
        table, files = plan.write_reports(paths, stock, prof.characters[character].favor_standing, goals,
                                         faction=prof.faction)
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
    alts = {}
    for a in args.alt:
        name, sep, bags = a.partition("=")
        if not sep:
            print(f"--alt needs NAME=BAGSFILE, got {a!r}")
            return 1
        alts[name] = Path(bags).expanduser()
    for line in migrate(args.from_user.expanduser(), args.from_data.expanduser(), paths, args.main, alts,
                        region=args.region, ruleset=args.ruleset, faction=args.faction):
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
    sub.add_parser("prices", help="download your auction house's prices")
    pl = sub.add_parser("plan", help="plan a character's professions")
    pl.add_argument("--character", required=True)
    pl.add_argument("--prof", action="append", default=[], metavar="NAME:TARGET",
                    help="a profession and its target: a skill 1-300 or a recipe (once or twice)")
    m = sub.add_parser("migrate", help="move a pre-yap-forever planner folder into your home folder")
    m.add_argument("--from-user", type=Path, required=True, help="folder with stock.toml and bags files")
    m.add_argument("--from-data", type=Path, required=True, help="old data folder (house, prices, game data)")
    m.add_argument("--main", required=True, help="name of the character stock.toml belongs to")
    m.add_argument("--region", choices=profile.REGIONS, default="eu", help="your region (default eu)")
    m.add_argument("--ruleset", type=int, default=2, help="your ruleset ID (default 2)")
    m.add_argument("--faction", choices=profile.FACTIONS, default="alliance", help="default alliance")
    m.add_argument("--alt", action="append", default=[], metavar="NAME=BAGSFILE")
    args = parser.parse_args(argv)
    paths = paths or settings.paths()
    if args.command == "init":
        return cmd_init(paths)
    if args.command == "check":
        return cmd_check(paths, args.offline)
    if args.command == "probe":
        return cmd_probe(paths, args.item, args.buyout)
    if args.command == "prices":
        return cmd_prices(paths)
    if args.command == "migrate":
        return cmd_migrate(paths, args)
    return cmd_plan(paths, args.character, args.prof)
