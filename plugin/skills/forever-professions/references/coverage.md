# What the planner covers

What `plan` does today. The rules behind each line are in the section named; this page only
says what is there.

- Any crafting profession, one or two at once, each to its own target (a skill up to 300 or one
  recipe crafted once), from the character's `stock.toml`; two routes side by side (least gold and
  least total value).
- The route in trainer stages, with trips away from home marked (Artisan and Master trainers, trips
  back to them for recipes, vendor patterns, the Favor vendor) and the cost of skipping a recipe
  trip (a trip that costs nothing to skip is left out of the route, and said); or, per character,
  levelling at the remote trainer in one go with everything brought along, and a warning when the
  bring list doesn't fit the bags. Each trainer visit lists the trainer recipes to learn there, as
  far as the trainer's rank teaches them. Trainers are named for the character's faction, with zone,
  map coordinates and what is nearby ([list-layout.md](list-layout.md), "Trainer stages and trips").
- The safe route for trainer recipes whose skill requirement is only inferred from Classic, with a
  header line on what the route could save, and recipes seen learnable earlier in play kept at the
  Forever requirement ([game-rules.md](game-rules.md), "Trainers and ranks";
  [list-layout.md](list-layout.md), "Trainer stages and trips").
- Merchant's Favor recipes for the character's standing (Alliance, Blacksmithing and Enchanting),
  as far as their vendor, standing and price are known: up to the Honored Wristguards and Brilliant
  Wand. They are never used to level: one can be a craft-once target, and the guide and report list
  the ones the character could make now under "You could also make" ([game-rules.md](game-rules.md),
  "Merchant's Favor"). Other Favor-era recipes (the Blacksmithing plans at 300 among them) are not
  listed yet.
  Horde characters get no Favor recipes or crate turn-ins yet: the guide and report say so.
- A shopping list in every guide; mailbox trips when `stock.toml` gives `bag_slots`, and a reagent
  bag when it gives `reagent_slots` ([list-layout.md](list-layout.md), "Mailbox trips").
- Owned patterns: a pattern in the character's stock teaches its recipe at no cost, and is left
  off the shopping list and the "Sell now" list.
- Shared gold and items between characters on one ruleset and faction
  ([setup.md](setup.md), "Ruleset and faction groups" and "Items shared by mail"). A character on
  another ruleset or faction can't be planned yet (no prices for it).
- Legacy talents from the profile: Working Overtime and Dedicated Study
  ([game-rules.md](game-rules.md), "Legacy talents").
- Two price fallbacks when the API can't be reached: `prices --remote` and
  `prices --auctionator PATH` ([setup.md](setup.md), step 5).
- A budget as a goal: the route ends at the last stop (rank cap or target) the gold reaches, two
  professions shared evenly or one at a time, with what the next stop costs on top
  ([setup.md](setup.md), "A budget as a goal"; [list-layout.md](list-layout.md), "Budget").

Not yet: gathering while levelling, keep-or-sell advice, gear. Say so when asked,
rather than guessing.
