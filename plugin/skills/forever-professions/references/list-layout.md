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
  trip that learns a trainer recipe, as written guides do. A run that crosses a rank training is
  two rows, one in each stage.
- Trips away from home are rank training to 225 and 300 (Artisan and Master trainers sit in set
  towns), trips back to them for recipes, vendor-sold patterns and the Merchant's Favor vendor. Say
  a trip is needed, how to avoid a second one (buy every vendor pattern on one visit; patterns can be
  bought before they can be learned), and what to bring to keep levelling at a remote trainer, with
  the bag slots it takes. The bring list ends at the next rank trip, trip back for recipes or
  capital stop for recipes: level at home after that and come back then. With bag slots in the
  stock it is cut to what fits in them.
- With `trainer_trips = "one_go"` ([setup.md](setup.md), step 2) the player levels at a remote rank
  trainer to the profession's next rank training or the end of its route, whichever comes first.
  The trips back for recipes and capital stops inside that stretch are left out: their recipes end
  the rank row as `Learn at the trainer as you reach them: <recipe> at <skill>, ...` (in skill order,
  `<skill>` where the route learns it), and each keeps its `*At <skill>: Learn <recipe> (trainer <fee>)*` row. The bring list
  covers the whole stretch, whatever the bags hold. What the stretch uses of your own crafts and
  disenchants made before the trip (in route order, either profession) is listed as `<count> <item>
  (yours)`. What your other profession makes later on the route is listed apart, after the bring list:
  `Made later by your <Profession> on this route: <count> <item>, ...: craft those rows before you go, or
  buy them on the AH (about <gold>).`; the dust, essences and shards that disenchanting such crafts
  gives are listed in a sentence of their own, `From disenchanting what your <Profession> makes later
  on this route: <count> <item>, ...: craft those rows and disenchant the greens before you go, or buy
  them on the AH (about <gold>).`, with `<gold>` at today's AH prices and no `(about ...)` when one
  of the items has no AH price. These items count in the bag slots too. The other profession's rows stay
  where they are. A recipe trip with no remote rank training before it on the route stays a trip.
  The patterns the stretch learns are on the bring list too: from the trip's skill up to where its bring
  list ends, a goal pattern learned at the end of the route included, and one learned at the next rank
  training left to that trip's list. One slot each, named by where they come from as on the shopping
  list: `1 <pattern> (from the AH)`, `(from a pattern vendor)` (the data doesn't name the vendor), `(from
  the Merchant's Favor vendor)`, `(from the bank)` for one you own, `(mail from <Name>)` for one another character mails. A vendor or
  Merchant's Favor pattern on that list gets no `**Trip:**` row of its own: it is bought before you go. A
  pattern trip outside every stretch stays a trip. As needed, the bring list has no patterns: the shopping
  list carries them.
- With bag slots in the stock (`bag_slots`, and `reagent_slots` for reagents), a trip's bring list that
  doesn't fit them (10 slots kept free for crafting, as for mailbox trips) ends with `This needs <N>
  free slots and you have <M>: get bigger bags, bank what this stretch doesn't need, or set a lower goal
  (for example <skill>) so it fits.` `<N>` is the list's bag slots plus the 10, `<M>` is `bag_slots`,
  and `<skill>` is the highest skill whose bring list fits; when not even the first row's list fits, it
  ends `or set a lower goal so it fits.` Without `bag_slots`, no warning.
- A trainer teaches recipes up to its rank's cap ([game-rules.md](game-rules.md), "Trainers and
  ranks"), so every trainer visit learns ahead: a rank row ends with `While there, learn: <recipe>
  (<fee>), ...` for the trainer recipes the route needs later whose required skill is reached and
  whose rank the trainer teaches; nothing to learn, no sentence. The stock doesn't say which recipes
  a character knows, so recipes already reachable at the start skill never make a visit of their
  own: they are listed once, at the first visit that teaches them, as `If you don't have them yet:
  <recipe>, ...` (`it` for one). When the route uses one before any such visit, the route starts with
  `- **Before you start**, make sure you know: <recipes> (any <Rank> <Person> teaches them).`
  A recipe learned at a visit or before the start is not learned again where the route first uses it:
  that row reads `*At <skill>: start crafting <recipe> (learned at <trainer>)*` or `(learned before you
  start)`, with no second fee, and comes after the visit's row at the same skill. A recipe listed as `If
  you don't have them yet` may already be known, so its row reads `(learn it at <trainer> if you don't
  have it)` and keeps the `; listed from ...` note when there is one.
- The recipes of a row keep route order (the order the route learns them), whatever their rank:
  a trainer teaches every recipe up to its rank's cap, so no row names a second trainer for a lower
  recipe.
- A trainer recipe that no earlier visit of its rank can teach gets a visit of its own at the skill
  the route needs it, and later recipes of that rank with a required skill at or below that skill
  join it: a recipe needed at 240 and used then, and one at 245, make two rows; when the first isn't
  used before 245, one visit teaches both. The recipes of a trip or a capital stop are listed with
  their fees (`<recipe> (<fee>)`, to the copper as on the route's `Learn` rows: `(4s 50c)`, `(10s 0c)`).
  An Artisan or Master recipe is a trip:
  `- **Trip:** back to <trainer>, <place>, at <skill> for <recipes>`, then `; or skip it: +<gold>
  for the route without it` (the route planned again without those recipes) or `; there is no other
  way to reach the target without it`, and a full stop. As with vendor and Favor trips, which keep
  their own three, only the costliest three recipe trips (by trainer fees) get the skip clause; a trip
  for the goal recipe always says there is no other way. A trip whose route-without costs at most 0.5c
  more (or less), reaches the same skills and makes fewer trainer visits and pattern trips is left out
  of the route (trainer visits: rank trainings, trips back and capital stops; pattern trips: vendor and
  Favor trips). The route is planned again without it, at most three rounds, the recipes left out
  adding up, never the goal recipe, and under a budget only when its "Gold to bring" still fits; the
  trips left out cost at most 0.5c more together, against the route as first planned, each skip is also
  within 0.5c of the route it starts from, and a route both guides share is planned without a trip only
  when it is free in both measures. The guide header (after the listing line) and the report's data
  notes say so, one line a trip: `Planned without the trip back to <trainer> at <skill> for <recipes>:
  the route without it costs the same.` (`<trainer>` is the trainer's name when the data names one,
  else `the <Rank> <Person>`), or `Planned without the trip to buy the pattern for <recipe>: the route
  without it costs the same.` for a vendor trip (a Favor trip is a
  target's, never left out). A trip left on the route whose skip costs at
  most 0.5c more gets no skip clause. Below Artisan it is a stop in a capital:
  `- At <skill>, learn <recipes> at any <Rank> <Person> in a capital (for example <name>, <capital>).`
  After the first row of a rank and profession has named the capital trainers (and the city's tip),
  later stops of that rank read `- At <skill>, learn <recipes> at any <Rank> <Person> in a capital.` Without
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
  skill inferred from Classic (`TrainerInferred`), unless the recipe was seen learnable lower in play
  ([game-rules.md](game-rules.md), "Trainers and ranks"). A trainer recipe learned above its Forever
  listing gets a note inside the parenthesis of its row: `*At <skill>: start crafting <recipe> (learned
  at <trainer>; listed from <skill> in the Forever data: if the trainer offers it then, you can start it
  earlier)*` (or `(learned before you start; listed from ...)`).
- One header line, after the intro, the trainer note and the talent lines, when the route could be
  cheaper if trainers offer recipes at the Forever listing (the route planned again with the listed
  requirements, compared in the route's own measure): `A route planned at the Forever listing
  (trainers offering recipes from their listed skill) could cost about <gold> less.` The report's data notes carry the same line. No line when listing the recipes
  would not make the route cheaper. The lines of the trips the route was planned without follow it
  ("Trainer stages and trips").
- On the lowest profession's route, a row that costs `study_hint_gold_per_point` gold a point or more
  ends with ` — about <gold> a point here: Dedicated Study (one free point a day) would cover these N
  points in N days`, and ` (a legacy talent you haven't taken)` when the profile's character lacks
  the talent.
- If the trainer data can't be downloaded or read, the guide renders without names and says why
  once, near the top.

## You could also make

Merchant's Favor recipes the character could craft once for itself ([game-rules.md](game-rules.md),
"Merchant's Favor"). The guide has the section after the route, before the shopping list; the report
has it inside "Merchant's Favor", after the Favor spent, under `**You could also make**`. Neither has
it when nothing fits, or for Horde (no Favor recipes yet):

- `## You could also make`, then
  `Merchant's Favor recipes to craft once for yourself, if you don't have the item yet. They are not part of the route, its shopping list or its gold.`
- A row per recipe: `- **<name>** (<Profession> <skill>, for level <level>): <favor> of your <Favor> Favor; materials about <gold> on the AH, <n> <item> from your bank, <n> <item> (mail from <Name>).`
  `<skill>` is the recipe's Favor skill, `<level>` the crafted item's required level, `<gold>` what the
  materials not held cost at today's prices. An enchant crafts no item: `(<Profession> <skill>)`. What
  is bought is `on the AH`, `from a vendor` or `on the AH and from a vendor`; the bank part lists each
  item (`2 Dream Dust and 1 Star Wood from your bank`), the mail part names each sender as on the
  shopping list. When nothing needs buying: `materials: <n> <item> from your bank`, then the mail.
- Items first, the nearest to the character's level first, then by Favor price; then the enchants,
  by Favor price. At most 6 rows, then `and <n> more.` in a paragraph of its own.
- The report's data notes say `Merchant's Favor recipes are not used to level (see You could also make).`
  (without the parenthesis when there is no section), and, when the game data gives no item a required
  level, `Item required levels are not in the game data: Merchant's Favor items are not suggested, only enchants.`

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
- A recipe target wins over the budget ([setup.md](setup.md)): with a budget set and a recipe target, the
  guide (under the comparison) and the report (in its verdict) say only `The <budget> budget is not applied:
  a recipe target is planned in full.`, and the plan command prints the same line.
- Two professions one at a time: the intro says `Level one profession at a time: <first> first, then <second>.`
  instead of "Level both professions side by side".
