"""Words for trainer stops in the guide: who trains a rank, where, and what is nearby.

Everything here returns None (or "") when the player's faction or the trainer data is missing, so
the guide then says what it said before trainers were named.
"""
import dataclasses
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from yap_forever import gamedata, trainer_notes, trainers
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
    notes: trainer_notes.Notes | None = None  # facts from play; None: say none


def _usable(info: TrainerInfo | None, cap: int) -> bool:
    return bool(info and info.data and info.faction in CAPITALS and cap in RANK_BY_CAP)


def _no_trainer(rank: str, profession: int) -> str:
    return f"the planner has no {rank} {PERSON.get(profession, PROFESSIONS.get(profession, ''))} trainer " \
           "for your faction in its data."


NEUTRAL_AH = "neutral AH (its own prices and a higher deposit)"  # the planner prices the faction AH


def services_text(s: Services, closest: trainers.Closest | None = None) -> str:
    """'Nearby: bank, mailbox; no auction house.' With nothing near, the closest service in the zone
    (`closest`), when there is one: 'Nearby: nothing within a short walk; the closest is the mailbox.'"""
    auction = NEUTRAL_AH if s.neutral_auction else "auction house"
    parts = (("bank", s.bank), (auction, s.auction), ("mailbox", s.mail))
    have = [w for w, ok in parts if ok]
    lack = [w for w, ok in (("bank", s.bank), ("auction house", s.auction), ("mailbox", s.mail)) if not ok]
    if not have:
        if closest is not None:
            what = {"mailbox": "mailbox", "bank": "bank", "auction": NEUTRAL_AH if closest.neutral else "auction house"}
            return f"Nearby: nothing within a short walk; the closest is the {what[closest.kind]}."
        return "Nearby: none (no bank, auction house or mailbox)."
    if not lack:
        return f"Nearby: {', '.join(have)}."
    return f"Nearby: {', '.join(have)}; no {' or '.join(lack)}."


def _confirmed_first(found: list[Trainer]) -> list[tuple[Trainer, str]]:
    """Trainers with a confirmed title; when there are none, the others, each flagged."""
    sure = [(t, "") for t in found if t.title_confirmed]
    return sure or [(t, UNCONFIRMED) for t in found]


def notes_text(note: trainer_notes.TrainerNote | None, level: int | None) -> str:
    """What the owner learned from play about a trainer, as sentences ("" when there is nothing):
    from what level the trip is easy, a flight path, a tip. `level` is the character's."""
    if note is None:
        return ""
    out = []
    if note.group_level is not None:  # an instance: a group's level and a solo level
        text = f"Go with a group from about level {note.group_level}, solo from about level {note.solo_level}"
        if level is not None and level < note.group_level:
            text += f" (you're level {level})"
        out.append(text + ".")
    elif note.reach_level is not None or note.flight_path:
        text = f"Easy to reach from about level {note.reach_level}" if note.reach_level is not None else "With"
        if note.flight_path:
            text += (", with" if note.reach_level is not None else "") + " a flight path for repeat visits"
        if note.reach_level is not None and level is not None and level < note.reach_level:
            text += f" (you're level {level}: the first trip is harder)"
        out.append(text + ".")
    if note.note:
        out.append(note.note)
    return " ".join(out)


def _place(t: Trainer, flag: str, info: TrainerInfo, level: int | None = None) -> tuple[str, bool]:
    """The trainer's place (then what is known from play), and whether it says what services are there."""
    text, known = _where(t, flag, info)
    said = notes_text(info.notes.trainers.get(t.npc_id) if info.notes else None, level)
    return (f"{text} {said}" if said else text), known


def _where(t: Trainer, flag: str, info: TrainerInfo) -> tuple[str, bool]:
    data = info.data
    zone = data.zone_name(t.zone)
    if t.coords is None:
        parent = data.parent_zone(t.zone)
        return f"{t.name}{flag}, inside {zone}" + (f" ({data.zone_name(parent)})" if parent else "") + ".", False
    place = f"{t.name}{flag}, {zone} ({t.coords[0]:.1f}, {t.coords[1]:.1f})."
    if t.zone in CAPITALS[info.faction]:  # a capital has a bank, an auction house and a mailbox
        return place, True
    near = trainers.nearby(t, data.npc_rows, data.mailboxes, trainers.NEARBY_RADIUS)
    listed = info.notes.trainers[t.npc_id].nearby if info.notes and t.npc_id in info.notes.trainers else ()
    if listed:  # facts from play beat the radius
        near = dataclasses.replace(near, bank=near.bank or "bank" in listed,
                                   auction=near.auction or "auction" in listed, mail=near.mail or "mail" in listed)
    closest = None if near.bank or near.auction or near.mail else \
        trainers.closest_service(t, data.npc_rows, data.mailboxes)
    return f"{place} {services_text(near, closest)}", True


def remote_stop(info: TrainerInfo | None, profession: int, cap: int, level: int | None = None) -> RemoteStop | None:
    """Where to train to `cap` in a set town (Artisan and Master): the text that follows
    '**Trip:** <what>: ', or None when the guide should not name trainers.
    A trainer in the character's own capital gets no "Nearby" line; others outside it do.
    level: the character's level, for what the notes say about a first trip below it."""
    if not _usable(info, cap):
        return None
    rank = RANK_BY_CAP[cap]
    found = trainers.trainers_for(info.data.trainers, profession, rank, info.faction)
    if not found:
        return RemoteStop(_no_trainer(rank, profession), False)
    named = _confirmed_first(found)[:MAX_REMOTE]
    places = [_place(t, flag, info, level) for t, flag in named]
    return RemoteStop(" ".join(("Or " if i else "") + text for i, (text, _known) in enumerate(places)),
                      True, all(known for _text, known in places))


def _apart(info: TrainerInfo, zone: int, planned: tuple[int, ...]) -> str:
    """'In <city>, the <A> and <B> trainers are in different parts of the city.' for each two planned
    professions the city's notes put in different groups; "" for a city without groups, a profession
    in none of them, or fewer than two planned professions."""
    groups = info.notes.city_groups.get(zone, ()) if info.notes else ()
    where = {p: i for i, g in enumerate(groups) for p in g}
    city = info.data.zone_name(zone)
    return " ".join(f"In {city}, the {PROFESSIONS.get(a, a)} and {PROFESSIONS.get(b, b)} trainers are in "
                    "different parts of the city."
                    for i, a in enumerate(planned) for b in planned[i + 1:]
                    if a in where and b in where and where[a] != where[b])


def city_row(info: TrainerInfo | None, profession: int, cap: int, planned: tuple[int, ...] = (),
             said: set[int] | None = None) -> str | None:
    """The row (without its dash) for a rank trained at any trainer of that rank in a capital.
    planned: the professions the guide plans, in order; a capital whose notes put two of them in
    different groups says so. said: the zones that already said it (a set the caller keeps, so a
    city says it once in the guide); a zone is added when its row says it."""
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
    text += " (for example " + " or ".join(f"{t.name}{flag}, {info.data.zone_name(t.zone)}" for t, flag in examples) + ")."
    notes = info.notes
    said = set() if said is None else said
    parts = [text]
    for z in dict.fromkeys(t.zone for t, _flag in examples):
        if notes and z in notes.cities:
            parts.append(notes.cities[z])
        apart = _apart(info, z, planned) if z not in said else ""
        if apart:
            parts.append(apart)
            said.add(z)
    return " ".join(parts)


def add_note(text: str, note: str) -> str:
    """Put a " (...)" note inside the row's closing parenthesis ("(trainer 45s; inferred: ...)"),
    or after the text when it has none."""
    if note and text.endswith(")") and note.startswith(" ("):
        return f"{text[:-1]}; {note[2:]}"
    return text + note


def listed_note(listed_skill: int) -> str:
    """Appended to a trainer recipe's learn row when the route learns it above the skill the Forever data lists."""
    return (f" (listed from {listed_skill} in the Forever data: "
            "if the trainer offers it then, you can start it earlier)")


def load_info(dest: Path, faction: str) -> tuple[TrainerInfo | None, str]:
    """Download (if missing) and load the trainer data: (info, "") or (None, why trainers are left out).
    No faction means no trainers are named, and nothing is downloaded."""
    if faction not in CAPITALS:
        return None, ""
    try:
        gamedata.fetch_all(dest=dest, only=gamedata.TRAINER_FILES)
        data = trainers.load_trainer_data(dest)
        try:
            return TrainerInfo(faction, data, trainer_notes.load_notes()), ""
        except ValueError as e:  # the shipped notes are unusable: name the trainers without them
            return TrainerInfo(faction, data), f"Trainer notes are left out of this guide: {e}."
    except ValueError as e:  # damaged, with what to do about it
        why = str(e)
    except urllib.error.URLError as e:
        why = f"the trainer data could not be downloaded ({e.reason}); run the plan again with a network connection"
    except FileNotFoundError:
        why = "the trainer data files are missing; run the plan again with a network connection"
    except OSError as e:
        why = f"the trainer data could not be read ({e})"
    return None, f"Trainer names are left out of this guide: {why}."
