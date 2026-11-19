---
name: forever-professions
description: Plan WoW: Forever profession levelling from the player's own auction house prices - cheapest craft route, shopping list, mailbox trips, Merchant's Favor recipes. Use when a player asks how to level a crafting profession on WoW: Forever (Blacksmithing, Enchanting, Leatherworking, Tailoring, Alchemy, Engineering), what to buy for it, what it will cost, or wants their yap-forever prices or setup checked.
---

# Forever professions

You plan WoW: Forever professions with the yap-forever planner. **The planner computes every
number; you never work out routes, counts or costs yourself.** Your job is setup, asking the
player what changed, running the planner, and walking them through the result.

## Running the planner

- The code lives at the plugin root: two folders above this skill's base directory (the
  directory you were given when this skill loaded). `cd` there before every command.
- Find the Python command once per session: on Windows try `py -3`, otherwise `python3`, then
  `python`; keep the first whose `--version` says 3.11 or newer. Below it is written `<python>`.
- Run `<python> -m yap_forever <command>`. Commands: `init`, `check [--offline]`,
  `probe --item ID --buyout COPPER`, `prices`, `plan --character "FIRST LAST" --prof NAME:TARGET [--prof NAME:TARGET]` (Forever
  character names are two words; quote them; `TARGET` is a skill 1-300 or a recipe name).
- The player's files are in `~/.yap-forever/` (or `$YAP_FOREVER_HOME`).
- **Never open, print or ask for `credentials.json`.** The player pastes their API client ID and
  secret into it themselves. If they paste them into the chat, tell them to create a new secret
  at develop.battle.net.

## Workflow

1. **Setup, if needed.** Run `check --offline`. For every `MISSING` line, follow
   [references/setup.md](references/setup.md) with the player, one step at a time. A player who
   uses a price fallback from setup step 5 skips the probe: `check` keeps showing credentials and
   house as missing, and `plan` doesn't need them.
2. **Ask what changed** since the last plan: level, profession skills, gold, Favor standing,
   free bag slots, and what has piled up (greens to disenchant, leftover materials). Update their
   character's `stock.toml` with what they confirm, including the `[skills]` table: the plan
   starts from those skills.
   **Ask the goal before every plan:** one profession or two, and for each a target: a milestone
   (150, 225 or 300: the first time a profession reaches each on the account gives a legacy talent
   point), another skill, or one recipe to reach and craft once (often a Merchant's Favor craft).
   Save the answer under `[goals]` in `stock.toml` if the player wants it kept.
   If Enchanting isn't in the plan, ask whether green crafts should be **kept to disenchant on
   another character** or sold, and set `keep_greens = true` or `false` in `stock.toml`. A
   character with only a `bags.toml` gets a `stock.toml` made from it the first time `plan` runs
   (`bag_slots`, `reagent_slots` and `[items]` carry over; the file is never overwritten or
   deleted): help the player fill in level, gold (`cash_gold`), `[skills]` and `[goals]`.
3. **Refresh prices** with `prices`. Prices update about once an hour. If the API can't be
   reached, use a fallback from [references/setup.md](references/setup.md) step 5:
   `prices --remote` (another machine over ssh) or `prices --auctionator PATH` (Auctionator's
   saved data). An import has one price per item and no listing depth: say so, and if the guide
   header warns the scan is old, ask the player to scan again.
4. **Run the planner** for what they asked: `plan --character NAME --prof NAME:TARGET` (once per
   profession). Show the comparison table it prints and explain the two routes in a sentence each:
   **least gold** counts what the player owns as free; **least total value** counts owned
   materials at what they'd sell for, so it may leave valuable ones to sell, which takes time on
   the AH. When both are the same route, say so. Ask which guide they want to follow. The reports are named for the character
   (`reports/<date>-<name>-plan-gold.md` and so on), so planning another character doesn't
   overwrite them.
5. **Walk through the result** top-down, craft by craft, as laid out in
   [references/list-layout.md](references/list-layout.md). When game data and play experience
   disagree, quote [references/game-rules.md](references/game-rules.md) and go with the rules.
6. **Save what they confirm** (new skills, stock) so the next plan starts from it.

## What the planner covers today

- Any crafting profession, one or two at once, each to its own target (a skill up to 300 or one
  recipe crafted once), from the character's `stock.toml`; two routes side by side.
- The route in trainer stages. Trips away from home (Artisan and Master trainers, vendor
  patterns, the Favor vendor) are marked, with the cost of skipping a recipe trip. The guide
  names the trainer for the character's faction (from the profile) with the zone and map
  coordinates, and says what is nearby (bank, auction house, mailbox). The Expert rank names
  capital trainers. A trainer recipe whose skill requirement is only inferred from Classic gets a
  fallback note on its learn row.
- Merchant's Favor recipes for the character's standing (Alliance, Blacksmithing and
  Enchanting).
- A shopping list in every guide; mailbox trips when `stock.toml` gives `bag_slots`, and a reagent
  bag when it gives `reagent_slots` (materials fill it first).
- Owned patterns: a pattern in the character's stock teaches its recipe at no cost, and is left
  off the shopping list and the "Sell now" list.
- Legacy talents from the profile: Working Overtime (a higher skill-up chance) and Dedicated Study
  (the guide says how many days of the free daily point would cover the last points).
- Two price fallbacks when the API can't be reached: `prices --remote` (another machine over
  ssh) and `prices --auctionator PATH` (Auctionator's saved data).
- Not yet: gathering while levelling, keep-or-sell advice, budget targets, gear. Say so when
  asked, rather than guessing.
