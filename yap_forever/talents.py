"""What the guide and the report say about the character's legacy talents."""
from yap_forever.costmodel import OVERTIME_STEP
from yap_forever.gamedata import PROFESSIONS

MAX_RANK = 5


def talent_lines(character, reading, plan, caps, stock) -> list[str]:
    """Plain sentences for the guide header and the report notes; none for a talent not taken."""
    out: list[str] = []
    rank = character.working_overtime if character else 0
    if rank > 0:
        pct = round(OVERTIME_STEP * rank * 100)
        if reading == "points":
            how = f"+{pct} percentage points (unconfirmed in game)"
        else:
            how = (f"+{pct}% of the base chance (unconfirmed in game; "
                   f'set working_overtime_reading = "points" for +{pct} percentage points)')
        out.append(f"Working Overtime {rank}/{MAX_RANK}, read as {how}.")
    if character and character.dedicated_study and caps:
        out.append(_dedicated_study(plan, caps, stock))
    return out


def _dedicated_study(plan, caps, stock) -> str:
    """The free daily point goes to the lowest profession (the lower skill when the route starts;
    on a tie the first of the route): say how many days cover its points on the route."""
    start = {p: max(1, stock.skills.get(p, 1)) for p in caps}
    prof = min(caps, key=lambda p: start[p])  # min keeps the first of equals
    name = PROFESSIONS.get(prof, str(prof))
    n = max(0, plan.final_skill.get(prof, start[prof]) - start[prof])
    head = "Dedicated Study: one free point a day goes to your lowest profession; "
    if n == 0:
        return head + f"{name} needs no points on this route."
    if n == 1:
        return head + f"1 day would cover the last 1 point of {name}."
    return head + f"{n} days would cover the last {n} points of {name}."
