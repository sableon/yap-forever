---
name: forever-professions
description: Plan WoW: Forever profession levelling from the player's own auction house prices - cheapest craft route, shopping list, mailbox trips, Merchant's Favor recipes. Use when a player asks how to level a crafting profession on WoW: Forever (Blacksmithing, Enchanting, Leatherworking, Tailoring, Alchemy, Engineering), what to buy for it, what it will cost, or wants their yap-forever prices or setup checked.
allowed-tools:
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/yap-forever.py" *)
  - Bash(python "${CLAUDE_PLUGIN_ROOT}/yap-forever.py" *)
  - Bash(py -3 "${CLAUDE_PLUGIN_ROOT}/yap-forever.py" *)
---

# Forever professions

You plan WoW: Forever professions with the yap-forever planner. **The planner computes every
number; you never work out routes, counts or costs yourself.** Your job is setup, asking the
player what changed, running the planner, and walking them through the result.

## Running the planner

- Run every command in exactly this form, from any folder, with no `cd` before it:
  `<python> "${CLAUDE_PLUGIN_ROOT}/yap-forever.py" <command>`. This skill and its references
  write it `<planner> <command>`. The skill's `allowed-tools` approve this form, and only it, in
  the turn that loads the skill; any other form (a `cd` first, `-m yap_forever`) always asks.
- `<python>`: on Windows try `py -3`, otherwise `python3`, then `python`. Keep the first with
  which `<planner> check --offline` runs and doesn't say it needs a newer Python.
- When the planner's output says to run `python3 -m yap_forever X` (or `py -3 -m ...`), run
  `<planner> X`.
- Commands: `init`, `check [--offline]`, `probe --item ID --buyout COPPER`, `prices`,
  `plan --character "FIRST LAST" --prof NAME:TARGET [--prof NAME:TARGET] [--budget GOLD]
  [--order even|NAME,NAME]` (Forever character names are two words; quote them; `TARGET` is a
  skill 1-300 or a recipe name).
- The player's files are in `~/.yap-forever/` (or `$YAP_FOREVER_HOME`).
- **Never open, print or ask for `credentials.json`.** The player pastes their API client ID and
  secret into it themselves. If they paste them into the chat, tell them to create a new secret
  at develop.battle.net.

## Workflow

The rules behind each question are in the references, each in one place. Read the section named
when a question or answer needs it.

1. **Setup, if needed.** Run `<planner> check --offline`. For every `MISSING` line, follow
   [references/setup.md](references/setup.md) with the player, one step at a time.
2. **Ask what changed** since the last plan, and save what the player confirms:
   - Level, profession skills, free bag slots, and what has piled up (greens to disenchant,
     leftover materials): into the character's `stock.toml`. Favor standing: `favor_standing` in
     `profile.toml` ([setup.md](references/setup.md), step 2).
   - Gold: once per ruleset and faction, not per character, into `[gold]` in `profile.toml`
     ([setup.md](references/setup.md), "Ruleset and faction groups").
   - Other characters on the same ruleset and faction: ask the player to keep each one's
     `stock.toml` up to date, and tell them what that means for this plan
     ([setup.md](references/setup.md), "Items shared by mail").
   - A character with only a `bags.toml`: run `plan` once, then fill in the new `stock.toml` with
     the player ([setup.md](references/setup.md), "A bags file").
3. **Ask the goal before every plan:** one profession or two, and for each a target: a milestone
   ([game-rules.md](references/game-rules.md), "Legacy talents"), another skill, or one recipe to
   reach and craft once (often a Merchant's Favor craft). Or a budget: "how far does this gold get
   me?", suggesting the `[gold]` amount of the character's ruleset and faction (`--budget GOLD`).
   With a budget and two crafting professions, ask: **raise both evenly or one at a time?** and, for
   one at a time, which first (`--order NAME,NAME`)
   ([setup.md](references/setup.md), "A budget as a goal"). Save it under `[goals]` in `stock.toml`
   if the player wants it kept. If Enchanting isn't in the plan, ask whether green crafts should be
   kept to disenchant on another character or sold, and set `keep_greens`
   ([setup.md](references/setup.md), step 2, "Green crafts").
   When the goal takes two professions into Artisan stages whose trainers stand in two capitals
   ([game-rules.md](references/game-rules.md), "Trainers and ranks"; the guide also says so under its
   intro) and the character has no `capital` yet, ask **Start in <City A>
   (<Profession A>'s <Rank>) or <City B> (<Profession B>'s <Rank>)?** (for example: **Start in
   Ironforge (Engineering's Artisan) or Darnassus (Alchemy's Artisan)?**) with each capital's tip
   ([game-rules.md](references/game-rules.md), "Trainers and ranks"), then, for the other one, **level that
   stage there in one go, or go as needed?** When the character already has `trainer_trips`, don't ask
   that again: say what it is set to, since changing it changes the trips to the remote trainers too. Save
   the answers as `capital` and `trainer_trips` under
   `[characters."Name"]` in `profile.toml` ([setup.md](references/setup.md), step 2). One
   `trainer_trips` answer covers both kinds of trip: the other capital and the remote trainers (every
   Master, the Artisan Enchanters); tell the player so when you ask, and step 5 doesn't ask again. With
   one capital, say where the guide starts and ask nothing.
4. **Refresh prices** with `<planner> prices`. If the API can't be reached, use a fallback and
   tell the player what it can't give ([setup.md](references/setup.md), step 5):
   `<planner> prices --remote` or `<planner> prices --auctionator PATH`.
5. **Run the planner** for what they asked: `<planner> plan --character "NAME" --prof NAME:TARGET`
   (once per profession). Show the comparison table it prints and explain the two routes in a
   sentence each: **least gold** counts what the player owns as free; **least total value** counts
   owned materials at what they'd sell for, so it may leave valuable ones to sell, which takes time
   on the AH. When both are the same route, say so. Ask which guide they want to follow (the report
   files: [setup.md](references/setup.md), "Report names").
   When the route has a remote trainer (a `**Trip:**` row for a rank to 225 or 300) and the character has
   no `trainer_trips` yet (step 3's answer counts), ask once per character: **level there in one go, or come back as needed?**
   (one go: bring everything to the next rank or the target and learn the recipes at the trainer; as
   needed: come back for each later recipe). Save the answer as `trainer_trips` under
   `[characters."Name"]` in `profile.toml` (`"one_go"` or `"as_needed"`,
   [setup.md](references/setup.md), step 2) and, for one go, run `plan` again.
6. **Walk through the result** top-down, craft by craft, as laid out in
   [references/list-layout.md](references/list-layout.md). When game data and play experience
   disagree, quote [references/game-rules.md](references/game-rules.md) and go with the rules.
7. **Save what they confirm** (new skills, stock) so the next plan starts from it.

## What the planner covers

What it does today and what it doesn't do yet: [references/coverage.md](references/coverage.md).
Read it when the player asks whether the planner can do something. When it isn't covered, say so,
rather than guessing.
