"""Words for trainer stops in the guide: who trains a rank, where, and what is nearby.

Everything here returns None (or "") when the player's faction or the trainer data is missing, so
the guide then says what it said before trainers were named.
"""
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from yap_forever import gamedata, trainers
from yap_forever.gamedata import PROFESSIONS
from yap_forever.trainers import CAPITALS, RANK_BY_CAP, Services, Trainer, TrainerData

PERSON = {171: "Alchemist", 164: "Blacksmith", 333: "Enchanter", 202: "Engineer",
          165: "Leatherworker", 197: "Tailor"}  # how a trainer's title names the profession
MAX_REMOTE = 3  # trainers named for a remote rank
MAX_EXAMPLES = 2  # trainers named as examples for a capital rank


UNCONFIRMED = " (title unconfirmed in the data)"


@dataclass(frozen=True)
class RemoteStop:
    text: str
    found: bool  # False: the sentence says the data has no such trainer
    services_known: bool = False  # every trainer named is in the character's capital or has a Nearby line


@dataclass(frozen=True)
class TrainerInfo:
    faction: str  # "alliance" or "horde"
    data: TrainerData | None


def _usable(info: TrainerInfo | None, cap: int) -> bool:
    return bool(info and info.data and info.faction in CAPITALS and cap in RANK_BY_CAP)


def _no_trainer(rank: str, profession: int) -> str:
    return f"the planner has no {rank} {PERSON.get(profession, PROFESSIONS.get(profession, ''))} trainer " \
           "for your faction in its data."


def services_text(s: Services) -> str:
    """'Nearby: bank, mailbox; no auction house.'"""
    have = [w for w, ok in (("bank", s.bank), ("auction house", s.auction), ("mailbox", s.mail)) if ok]
    lack = [w for w, ok in (("bank", s.bank), ("auction house", s.auction), ("mailbox", s.mail)) if not ok]
    if not have:
        return "Nearby: none (no bank, auction house or mailbox)."
    if not lack:
        return f"Nearby: {', '.join(have)}."
    return f"Nearby: {', '.join(have)}; no {' or '.join(lack)}."


def _confirmed_first(found: list[Trainer]) -> list[tuple[Trainer, str]]:
    """Trainers with a confirmed title; when there are none, the others, each flagged."""
    sure = [(t, "") for t in found if t.title_confirmed]
    return sure or [(t, UNCONFIRMED) for t in found]


def _place(t: Trainer, flag: str, info: TrainerInfo) -> tuple[str, bool]:
    """The trainer's place, and whether it says what services are there."""
    data = info.data
    zone = data.zone_name(t.zone)
    if t.coords is None:
        parent = data.parent_zone(t.zone)
        return f"{t.name}{flag}, inside {zone}" + (f" ({data.zone_name(parent)})" if parent else "") + ".", False
    place = f"{t.name}{flag}, {zone} ({t.coords[0]:.1f}, {t.coords[1]:.1f})."
    if t.zone in CAPITALS[info.faction]:  # a capital has a bank, an auction house and a mailbox
        return place, True
    near = trainers.nearby(t, data.npc_rows, data.mailboxes, trainers.NEARBY_RADIUS)
    return f"{place} {services_text(near)}", True


def remote_stop(info: TrainerInfo | None, profession: int, cap: int) -> RemoteStop | None:
    """Where to train to `cap` in a set town (Artisan and Master): the text that follows
    '**Trip:** <what>: ', or None when the guide should not name trainers.
    A trainer in the character's own capital gets no "Nearby" line; others outside it do."""
    if not _usable(info, cap):
        return None
    rank = RANK_BY_CAP[cap]
    found = trainers.trainers_for(info.data.trainers, profession, rank, info.faction)
    if not found:
        return RemoteStop(_no_trainer(rank, profession), False)
    named = _confirmed_first(found)[:MAX_REMOTE]
    places = [_place(t, flag, info) for t, flag in named]
    return RemoteStop(" ".join(("Or " if i else "") + text for i, (text, _known) in enumerate(places)),
                      True, all(known for _text, known in places))


def city_row(info: TrainerInfo | None, profession: int, cap: int) -> str | None:
    """The row (without its dash) for a rank trained at any trainer of that rank in a capital."""
    if not _usable(info, cap):
        return None
    rank, name = RANK_BY_CAP[cap], PROFESSIONS.get(profession, str(profession))
    found = trainers.trainers_for(info.data.trainers, profession, rank, info.faction)
    if not found:
        return f"Train {name} to {cap}: {_no_trainer(rank, profession)}"
    capital = [t for t in found if t.zone in CAPITALS[info.faction]]
    examples = _confirmed_first(capital)[:MAX_EXAMPLES]
    if not examples:  # no trainer of the rank in a capital: say where they are, never "in a capital"
        where = " or ".join(f"{t.name}{flag}, {info.data.zone_name(t.zone)}"
                            for t, flag in _confirmed_first(found)[:MAX_EXAMPLES])
        return f"Train {name} to {cap} at {where} (no {rank} {PERSON.get(profession, name)} in a capital in the data)."
    text = f"Train {name} to {cap} at any {rank} {PERSON.get(profession, name)} in a capital"
    text += " (for example " + " or ".join(f"{t.name}{flag}, {info.data.zone_name(t.zone)}" for t, flag in examples) + ")"
    return text + "."


def add_note(text: str, note: str) -> str:
    """Put a " (...)" note inside the row's closing parenthesis ("(trainer 45s; inferred: ...)"),
    or after the text when it has none."""
    if note and text.endswith(")") and note.startswith(" ("):
        return f"{text[:-1]}; {note[2:]}"
    return text + note


def inferred_note(classic_skill: int, next_recipe: str | None) -> str:
    """Appended to a trainer recipe's learn row when its skill requirement is inferred."""
    fallback = f"craft {next_recipe} instead" if next_recipe else f"come back at {classic_skill}"
    return f" (inferred: the trainer may ask up to {classic_skill}; if it isn't offered, {fallback})"


def load_info(dest: Path, faction: str) -> tuple[TrainerInfo | None, str]:
    """Download (if missing) and load the trainer data: (info, "") or (None, why trainers are left out).
    No faction means no trainers are named, and nothing is downloaded."""
    if faction not in CAPITALS:
        return None, ""
    try:
        gamedata.fetch_all(dest=dest, only=gamedata.TRAINER_FILES)
        return TrainerInfo(faction, trainers.load_trainer_data(dest)), ""
    except ValueError as e:  # damaged, with what to do about it
        why = str(e)
    except urllib.error.URLError as e:
        why = f"the trainer data could not be downloaded ({e.reason}); run the plan again with a network connection"
    except FileNotFoundError:
        why = "the trainer data files are missing; run the plan again with a network connection"
    except OSError as e:
        why = f"the trainer data could not be read ({e})"
    return None, f"Trainer names are left out of this guide: {why}."
