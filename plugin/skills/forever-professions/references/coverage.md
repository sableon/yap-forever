# What the planner covers

What `plan` does today. The rules behind each line are in the section named; this page only
says what is there.

- Any crafting profession, one or two at once, each to its own target (a skill up to 300 or one
  recipe crafted once), from the character's `stock.toml`; two routes side by side (least gold and
  least total value).
- The route in trainer stages, with trips away from home marked (Artisan and Master trainers,
  vendor patterns, the Favor vendor) and the cost of skipping a recipe trip. Trainers are named for
  the character's faction, with zone, map coordinates and what is nearby
  ([list-layout.md](list-layout.md), "Trainer stages and trips").
- The safe route for trainer recipes whose skill requirement is only inferred from Classic, with a
  header line on what the route could save ([game-rules.md](game-rules.md), "Trainers and ranks";
  [list-layout.md](list-layout.md), "Trainer stages and trips").
- Merchant's Favor recipes for the character's standing (Alliance, Blacksmithing and Enchanting),
  as far as their vendor, standing and price are known: up to the Honored Wristguards and Brilliant
  Wand. Other Favor-era recipes (the Blacksmithing plans at 300 among them) are not listed yet.
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

Not yet: gathering while levelling, keep-or-sell advice, budget targets, gear. Say so when asked,
rather than guessing.
