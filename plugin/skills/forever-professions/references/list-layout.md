# How to lay out routes and shopping lists

Players read a route top-down, one craft after another, standing at the trainer or the mailbox.
Write it for that.

## Counts

- **Every count the player acts on includes the 15% buffer** on yellow and green steps: route
  rows (`×N`), the shopping list and the mailbox take-lists alike. Saying "×26" when 29 crafts
  were needed sends the player back to the auction house.
- **Round to the safe side.** A row asking for one or two more than the shopping list is fine.
  Buying short costs an extra trip. Totals are at least the sum of the rounded rows.
- On WoW: Forever materials can be bought in any quantity, not only whole stacks. Don't round
  purchases up to a stack.

## Reagent crafts

- Crafting a reagent (bolts, cured hides, Light Leather from scraps) gives skill-ups while it is
  not grey. Count those as route steps.
- Name a reagent craft **on the row that needs it** ("first craft 7 Handful of Copper Bolts,
  then…"), not in a separate list.
- Craft each intermediate **in one go at its first row**, with the buffer, rather than split
  across rows.

## Craft or buy

- Craft an intermediate only when it is cheaper than buying it by more than a margin: about 10%
  early on (materials cost tens of silver, small savings aren't worth a craft), falling to about
  5% at 300. Recipe cost included.
- When a useful item can be crafted or bought (a tool, a bag), show both with the cost
  difference and let the player choose.
- Judge a bag craft (or any useful craft) against the **route craft it replaces** at the same
  skill-up, not against its full material cost.

## Mailbox trips

- Bought materials wait in the mail. Split the route into trips that fit the player's free bag
  slots, keeping about 10 slots for crafted items. With a reagent bag (`reagent_slots`), materials
  fill it first and only what does not fit takes normal slots; the 10 crafting slots stay on
  normal slots. Without `reagent_slots` the trips are the same as before.
- Each trip lists what to take from the mail **including patterns bought on the auction house**,
  what to buy from the vendor (thread, salt, dyes, vials), and what is already in the bags.
- What the player's other characters (same ruleset and faction) mail over is named by source in the
  trip: "10 Iron Bar (mail from <Name>)", one entry per character, in name order. It costs no gold
  and is not on the shopping list.
- Mark mailbox pickups on the route rows. The mailbox can be far from the trainer.
- Carried lesser essences are packed 3 to 1 into greater ones when that saves slots (all of them
  on a tie), and unpacked as they are used. Trips and bring lists count slots packed and say
  what to pack; the shopping list still buys the lesser ones the route uses.

## Crafted items

- Green crafts are not sold when the player (or another of their characters) can disenchant:
  mark them for disenchanting and leave their value out of "leftovers sell for".
- Whites are vendored or parked in the mail (send and return) until there's time to sell.

## Trainer stages and trips

- A route is laid out in stages that end where each rank is trained. A rank can be trained
  anywhere from its required skill to the cap (50–75, 125–150, 200–225, 275–300): train it on the
  trip that learns a trainer recipe, as written guides do.
- Trips away from home are rank training to 225 and 300 (Artisan and Master trainers sit in set
  towns), trips back to them for recipes, vendor-sold patterns and the Merchant's Favor vendor. Say
  a trip is needed, how to avoid a second one (buy every vendor pattern on one visit; patterns can be
  bought before they can be learned), and what to bring to keep levelling at a remote trainer, with
  the bag slots it takes.
- A trainer teaches recipes up to its rank's cap ([game-rules.md](game-rules.md), "Trainers and
  ranks"), so every trainer visit learns ahead: a rank row ends with `While there, learn: <recipe>
  (<fee>), ...` for the trainer recipes the route needs later whose required skill is reached and
  whose rank the trainer teaches; nothing to learn, no sentence. The stock doesn't say which recipes
  a character knows, so recipes already reachable at the start skill never make a visit of their
  own: they are listed once, at the first visit that teaches them, as `If you don't have them yet:
  <recipe>, ...` (`it` for one). When the route uses one before any such visit, the route starts with
  `- **Before you start**, make sure you know: <recipes> (any <Rank> <Person> teaches them).`
- A recipe below the visit trainer's rank says where else to learn it, since the lower ranks are
  unconfirmed: `(if <trainer> doesn't list it: <who>)` after the recipes it is for (`them` for
  several), where `<trainer>` is the one trainer the row names or `the <Rank> <Person>`, and `<who>`
  names the Artisan or Master trainers of the recipe's rank (`<name> (<Rank>, <zone>)`) or reads
  `any <Rank> <Person>` below them.
- A trainer recipe that no earlier visit of its rank can teach gets a visit of its own at the skill
  the route needs it, and later recipes of that rank with a required skill at or below that skill
  join it (two needs at 240 and 245 make two rows). An Artisan or Master recipe is a trip:
  `- **Trip:** back to <trainer>, <place>, at <skill> for <recipes>`, then `; or skip it: +<gold>
  for the route without it` (the route planned again without those recipes) or `; there is no other
  way to reach the target without it`, and a full stop. Below Artisan it is a stop in a capital:
  `Learn <recipes> at any <Rank> <Person> in a capital (for example <name>, <capital>).` Without
  the faction or the trainer in the data the row says so (`back to the Master Enchanter in a set
  town (the planner doesn't say where yet)`) and still lists the recipes.
- Name the trainer from the data, for the character's faction (the profile's `faction`; without it
  the row says "a set town"). A remote rank row reads `**Trip:** Blacksmithing rank to 300: <name>,
  <zone> (x, y). Nearby: bank, mailbox; no auction house.` (map coordinates; "Nearby" is a bank, an
  auction house and a mailbox within a few map units of the trainer, same zone, and says plainly
  when there is none). A trainer inside an instance reads `<name>, inside <instance>` and gets no
  coordinates, never `(-1, -1)`. A trainer in a capital of the character's own faction gets no
  "Nearby" line (capitals have all three); a trainer in the other faction's capital still does.
  When the auction house found is run by auctioneers friendly to both factions (Booty Bay,
  Gadgetzan, Everlook), "Nearby" says `neutral AH (its own prices and a higher deposit)` instead of
  `auction house`: the planner's prices are the faction auction house's. When nothing is within a
  short walk but the zone has a bank, an auction house or a mailbox, it says `Nearby: nothing within
  a short walk; the closest is the <mailbox|bank|auction house>.` (no distances; the same neutral
  wording for an auction house); with none in the zone it keeps `Nearby: none (no bank, auction
  house or mailbox).`
- Trainer notes from play (`yap_forever/data_static/trainer_notes.toml`, keyed by NPC ID) follow a
  remote row's place and Nearby line: `Easy to reach from about level N, with a flight path for
  repeat visits.` (each part only when the file has it; below that level, ` (you're level L: the
  first trip is harder)` before the full stop), then the trainer's one-sentence tip. An instance
  trainer reads `Go with a group from about level G, solo from about level S.` (` (you're level L)`
  below G), then the tip. A trainer without notes reads as before. A city row (`Train ... in a
  capital (for example ...)`) adds the tip of each capital it names, once per row. A capital's notes may also
  group the professions whose trainers are close together (Stormwind: Tailoring, Alchemy and
  Enchanting; Blacksmithing and Engineering; Leatherworking alone). When the guide plans two
  professions that the notes put in different groups of a capital a city row names, the first
  such row says once per city `In <city>, the <A> and <B> trainers are in different parts of the
  city.` (after the tip, with the planned professions' names in the guide's order); the same group,
  one planned profession or a profession in no group say nothing. A trainer's notes
  may also list services known from play to be near (`nearby`: bank, auction, mail); they count as
  near in the "Nearby" line even when the data's radius finds none, so "nothing within a short walk"
  is not said for them. Tips never change the route.
  Name only trainers whose title names the rank; if there is none, name the odd-titled one with
  "(title unconfirmed in the data)". When the data has no trainer of that rank for the faction, say so
  in a sentence; never leave a name or a place empty.
- Expert and Journeyman ranks are not trips: `Train Blacksmithing to 150 at any Expert Blacksmith
  in a capital (for example <name>, <capital>).` names up to two trainers in the faction's capitals.
  When none of the rank's trainers is in a capital, the row names up to two of them with their zones
  and says `(no Expert Blacksmith in a capital in the data)`, never "in a capital".
- The route uses the safe requirement for trainer recipes: the higher of the Forever listing and the
  skill inferred from Classic (`TrainerInferred`). A trainer recipe learned above its Forever listing
  gets a note inside the fee's parenthesis: `(trainer <fee>; listed from <skill> in the Forever data:
  if the trainer offers it then, you can start it earlier)`.
- One header line, after the intro, the trainer note and the talent lines, when the route could be
  cheaper if trainers offer recipes at the Forever listing (the route planned again with the listed
  requirements, compared in the route's own measure): `A route planned at the Forever listing
  (trainers offering recipes from their listed skill) could cost about <gold> less.` The report's data notes carry the same line. No line when listing the recipes
  would not make the route cheaper.
- On the lowest profession's route, a row that costs `study_hint_gold_per_point` gold a point or more
  ends with ` — about <gold> a point here: Dedicated Study (one free point a day) would cover these N
  points in N days`, and ` (a legacy talent you haven't taken)` when the profile's character lacks
  the talent.
- If the trainer data can't be downloaded or read, the guide renders without names and says why
  once, near the top.

## Budget

With a budget goal ([setup.md](setup.md), "A budget as a goal"), the guide says under the comparison,
and the report in its verdict, what the gold reaches, in one paragraph:

- `<budget> takes <Profession> to <stop> (<gold>).`, the professions that advance joined with "and";
  `<gold>` is the cut route's "Gold to bring". When no profession advances but one would with more
  gold: `<budget> doesn't reach the first stop: nothing is planned yet.` Then the route section
  (guide and report) says `Nothing to craft within this budget.`, and the report's verdict gives only
  the budget paragraph, with no "Ready to level". When nothing advances because every target is
  reached or every profession is stalled, neither line is said: the "already at" and stall lines
  explain it.
- A profession that can't advance: `<Profession> gets none of it: <why>.` (the stall reason).
- Each profession with a stop above the cut: `The next stop, <Profession> <stop>, costs about <gold> more.`
  (the route planned to that stop, its "Gold to bring" minus the cut route's). When that stop is where
  the route stalls, below the target, the line ends `; the route stops there: <why>.` instead of the
  full stop. No line when the budget reaches the target.
- `<budget>` is the gold as given (`30g`, `12.5g`). The report's budget line ends with
  `; planned to your <budget> budget`.
- Two professions one at a time: the intro says `Level one profession at a time: <first> first, then <second>.`
  instead of "Level both professions side by side".
