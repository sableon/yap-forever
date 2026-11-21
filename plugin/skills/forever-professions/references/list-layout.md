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
  then…"), not in a separate list. One made with a profession the route doesn't plan (a budget with a
  recipe goal) names it: `first craft <n> <item> (your <Profession>)`.
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
- A route row whose crafts go to a vendor ends `→ sell to a vendor: about <gold> back`, or
  `→ sell up to <n> on the AH (about <price> each), the rest to a vendor: about <gold> back`:
  the vendor price × the crafts the planner expects for the row, in whole crafts (without the buffer
  the row's `×N` includes) × the output, less the crafts sold on the AH, which go to the item's first
  rows. A row the AH takes whole, one whose craft a vendor pays nothing for and the AH-only quest
  form (`→ sell on the AH (quest item, about <price> each)`) get no amount. For a craft the route
  only sells, its rows add up to what vendors pay back for it within about a craft each.
- The goal recipe crafted once is the player's: it is no leftover, and neither its row nor `Back from a
  vendor`, the guide's Money, the report's Totals or the least-gold measure count it as sold.
- The comparison table gives `Gold out of pocket`, `Back from a vendor`, `Total value` (vendor sales
  only) and `AH sales on top` (`—` when there are none), and ends with `Least gold is the gold out of
  pocket less what vendors pay back for the crafts. AH sales of crafts are not counted in choosing a
  route.`
- The guide's Money says `- **Back from selling crafts:** about <total>: <vendor> from vendors
  (counted in choosing the route) and about <ah> more if the AH sales go through.`, or, with no AH
  sales, `- **Back from selling crafts:** about <vendor> from vendors (counted in choosing the
  route).`; its Net counts vendor sales only. The report's Totals say `Back from vendors: <gold>
  (counted in choosing the route).` and `AH sales on top: <gold> (not counted).`
  On a budget's route planned without the vendor credit ([setup.md](setup.md), "A budget as a
  goal"), both say `(left out in choosing this route, to fit the budget)` instead of `(counted in
  choosing the route)`.
- The shopping list's `**Gold to bring: <gold>**` is everything bought before you start. When selling
  crafts to a vendor as you go needs less, the next line says `If you sell crafts to a vendor as you
  go and buy each row's reagents when you reach it, about <gold> is enough up front (<gold> less).`:
  the most you are short at any route row (what is bought up to the end of that row, with the
  patterns and trainer fees met by then, less what vendors paid for the earlier rows' crafts, the
  amounts the rows say, which round each row up to whole crafts: their sum is capped at what vendors
  pay back for the route). AH sales and disenchant materials never count. The figure assumes each
  row's reagents are bought when you reach it. A remote trip's bring list buys its stretch before the
  trip, so shopping by the bring list can need more up front. The line is left out when the two
  figures print the same.

## Trainer stages and trips

- A route is laid out in stages that end where each rank is trained. A rank can be trained
  anywhere from its required skill to the cap (50–75, 125–150, 200–225, 275–300): train it on the
  trip that learns a trainer recipe, as written guides do. A run that crosses a rank training is
  two rows, one in each stage.
- Trips away from home are rank training to 225 and 300 (Artisan and Master trainers sit in set
  towns; an Artisan in a capital is a trip only to the capital the guide doesn't start in, see "The
  home capital" below), trips back to them for recipes, vendor-sold patterns and the Merchant's Favor vendor. Say
  a trip is needed, how to avoid a second one (buy every vendor pattern on one visit; patterns can be
  bought before they can be learned), and what to bring to keep levelling at a remote trainer, with
  the bag slots it takes. The bring list ends at the next rank trip, trip back for recipes or
  capital stop for recipes: level at home after that and come back then. With bag slots in the
  stock it is cut to what fits in them.
- With `trainer_trips = "one_go"` ([setup.md](setup.md), step 2) the player levels at a remote rank
  trainer to the profession's next rank training or the end of its route, whichever comes first.
  The trips back for recipes and capital stops inside that stretch are left out (never the home
  capital's stops, below): their recipes end
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
  way to reach the target without it`, and a full stop. As with vendor trips, which keep their own
  three, only the costliest three recipe trips (by trainer fees) get the skip clause; a trip for the
  goal recipe always says there is no other way, and a Favor trip, always a target's, gets no clause.
  A trip whose route-without costs at most 0.5c more (or less), reaches the same skills, still crafts
  the goal recipe (a trip for the recipe of a tool or reagent the goal needs stays) and makes fewer
  trainer visits and pattern trips is left out of the route (trainer visits: rank
  trainings, trips back and capital stops; pattern trips: vendor and Favor trips). The route is
  planned again without it, at most three rounds, the recipes left out adding up, never the goal
  recipe, and under a budget only when its gold ("Budget") still fits; the trips left out cost
  at most 0.5c more together, against the route as first planned, each skip is also within 0.5c
  of the route it starts from, and a route both guides share is planned without a trip only when
  it is free in both measures. The guide header (after the listing line) and the report's data
  notes say so, one line a trip: `Planned without the trip back to <trainer> at <skill> for
  <recipes>: the route without it costs the same.` (`<trainer>` is the trainer's name when the
  data names one, else `the <Rank> <Person>`), or `Planned without the trip to buy the pattern
  for <recipe>: the route without it costs the same.` for a vendor trip (a Favor trip is a
  target's, never left out). A trip left on the route whose skip costs at most 0.5c more gets no
  skip clause. Below Artisan it is a stop in a capital:
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
- **The home capital** ([setup.md](setup.md), `capital`). A rank whose trainers all stand in one capital
  (the Artisans of Alchemy, Blacksmithing, Engineering, Leatherworking and Tailoring:
  [game-rules.md](game-rules.md), "Trainers and ranks") is levelled in that capital: every capital has
  an AH, mailbox and bank, so the player starts there. The guide starts in the character's `capital`,
  else in the only capital the route's stages need, else in the one whose stage the route reaches first.
  - That stage opens, under its `**<Profession> <from>–<to>**` header, with `Level <Profession>
    <from>–<to> in <City>: the <Rank> <Person> <name> (x, y) is there, with the AH, mailbox and bank.`
    and the city's tip.
  - In that capital the rank training and every visit back for recipes are stops, not trips, with no
    bring list, as needed and in one go (one go never folds them): `- At <skill>, in <City>: train
    <Profession> to <cap> at <name>.` (then `While there, learn: ...`) and `- At <skill>, in <City>:
    learn <recipes> at <name>`, then the skip clause and a full stop. A stop the route is planned
    without reads `Planned without the stop at <skill> in <City> for <recipes>: the route without it
    costs the same.`
  - Journeyman and Expert stops name the city when it has that trainer: `- At <skill>, learn <recipes>
    at any <Rank> <Person> in <City>.` and `- Train <Profession> to <cap> at any <Rank> <Person> in
    <City>.`; when it hasn't (Darnassus has no Blacksmithing or Engineering trainer, Thunder Bluff no
    Engineering one), the row says "in a capital (for example ...)" as below.
  - The other capital follows `trainer_trips`: as needed, its rank training and visits back stay trips;
    in one go the player levels that stage there (one trip, its recipes learned as the skill reaches
    them). Its trip rows have no bring list and end `<City> has an AH, mailbox and bank: buy as you go
    there.` and the city's tip. The stage line is the home capital's only. A vendor or Merchant's Favor
    pattern inside a capital's stage stays a trip of its own: there is no bring list to carry it.
  - With two capitals and no `capital` set, a line under the intro says `This route's <Rank> trainers
    are in <City A> (<Profession A>) and <City B> (<Profession B>). This guide starts in <City A>; to
    start in <City B>, set capital = "<key>" for this character in profile.toml.` (without `<Rank>`
    when the two stages' ranks differ). With `capital` set, no line.
  - Remote trainers (every Master, the Artisan Enchanters) stay trips with their bring lists. "Trips
    away" counts only the trips outside the home capital. Without the trainer data or a faction, or
    with no stage in a capital, none of this shows: the trips and "in a capital" rows as before.
- **Joined capital stops.** Capital stops (Journeyman and Expert stops, and the home capital's) of the two
  professions that come close together on the route are one row. In route order, a later stop joins an
  earlier one of the other profession (in the home capital; with no home capital, in any capital) when that
  city has the trainers of both, where the earlier stop is made, the later stop's profession is
  no more than 10 skill points short of the later stop's skill, and every recipe of the later stop can be
  learned at that skill. A stop joins whole or not at all; a rank training never moves, but others can join
  it. Fees, the route, "Trips away" and the free skips don't change (a stop of one profession already
  teaches every recipe of it the skill allows, so joins are few). The row sits in the earlier stop's block,
  at its skill: `- **Capital stop** at <Profession A> <skill> (in <City>): learn <recipes A> at <a|an> <Rank>
  <Person A>, and <recipes B> at <a|an> <Rank> <Person B> (you use <it|them> from <Profession B> <skill>).`,
  with `(any capital, for example <City>)` when there is no home capital (the first capital with both) and
  `train <Profession A> to <cap> at ...` for a rank training. When no trainer of a rank there has a
  confirmed title, its part says so: `<a|an> <Rank> <Person> (title unconfirmed in the data)`, or `(title
  unconfirmed in the data; you use ...)` for a joined part. The earlier stop's skip clause follows its
  trainer, and the city's "different parts" sentence comes once, as on the other rows. The joined recipes'
  rows read `*At <skill>: start crafting <recipe> (learned at the capital stop at <Profession A> <skill>)*`.
  When the route rows of the stop's professions, from the stop to each one's next trainer visit as the guide
  shows it (a visit joined to a later stop is made there, so no row is in two sentences), buy reagents from a
  vendor, the row adds `The trade supplies vendor near the trainers sells the <count>
  <item>, ... these rows need.`, counted as the mailbox trips count them (whole crafts with the buffer,
  after the bank and the mail; the row the stop's skill falls in counts, a run that crosses the next visit
  doesn't). A stop alone keeps its row.
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
  materials not held cost at today's prices. An enchant crafts no item: `(<Profession> <skill>)`;
  an item with no level requirement reads `(<Profession> <skill>, any level)`. What is bought is
  `on the AH`, `from a vendor` or `on the AH and from a vendor`; the bank part lists each item
  (`2 Dream Dust and 1 Star Wood from your bank`), the mail part names each sender as on the
  shopping list. When nothing needs buying: `materials: <n> <item> from your bank`, then the mail;
  a recipe with no reagents ends after `Favor`.
- Items first, the nearest to the character's level first, then by Favor price, then the items with
  no level requirement, by Favor price; then the enchants, by Favor price, as a list of their own.
  The guide lists at most 6 items, then at most 6 enchants, each kind followed by `and <n> more.` in
  a paragraph of its own when it is cut; the report lists them all.
- The report's data notes say `Merchant's Favor recipes are not used to level (see You could also make).`
  (without the parenthesis when there is no section), and, when the game data gives no item a required
  level, `Item required levels are not in the game data: Merchant's Favor items are not suggested, only enchants.`
  When `stock.toml` gives no `level`, the guide's notes and the report's data notes say
  `Set level in stock.toml to get Merchant's Favor item suggestions.`

## Budget

With a budget goal ([setup.md](setup.md), "A budget as a goal"), the guide says under the comparison,
and the report in its verdict, what the gold reaches, in one paragraph:

- `<budget> takes <Profession> to <stop> (<gold>).`, the professions that advance joined with "and";
  `<gold>` is the cut route's "Gold to bring". With `pay = "as_you_go"` it is the gold enough up front
  selling crafts as you go ([setup.md](setup.md)), and the line reads `<budget> takes <Profession> to
  <stop> (<gold>, selling crafts to a vendor as you go).` When the route has a trip with a bring list
  (a remote trainer's), that line ends `; a trip's bring list is bought before the trip and can need
  more.` instead of the full stop (after `; the route stops there: <why>` when both are said). When no
  profession advances but one would
  with more gold: `<budget> doesn't reach the first stop: nothing is planned yet.` Then the route section
  (guide and report) says `Nothing to craft within this budget.`, and the report's verdict gives only
  the budget paragraph, with no "Ready to level". When nothing advances because every target is
  reached or every profession is stalled, neither line is said: the "already at" and stall lines
  explain it.
- A profession that can't advance: `<Profession> gets none of it: <why>.` (the stall reason).
- Each profession with a stop above the cut: `The next stop, <Profession> <stop>, costs about <gold> more.`
  (the route planned to that stop, its gold counted the same way minus the cut route's). When that
  stop is where the route stalls, below the target, the line ends `; the route stops there: <why>.`
  instead of the full stop. No line when the budget reaches the target.
- `<budget>` is the gold as given (`30g`, `12.5g`). The report's budget line ends with
  `; planned to your <budget> budget`, and with `pay = "as_you_go"` `; planned to your <budget> budget,
  selling crafts to a vendor as you go` (its cash before any sales can then be over the budget).
- A recipe target under a budget ([setup.md](setup.md)): its last stop is the goal, the recipe's skill with
  the recipe crafted once. When the route covers it: `<budget> covers <Profession> to <skill> and one <recipe>
  (<gold>).` (with `as_you_go`, `(<gold>, selling crafts to a vendor as you go).`; two recipe goals joined with
  ", and "). When the cut stops below it, after the "takes" line: `The goal, <Profession> <skill> and one
  <recipe>, costs about <gold> more.`, which replaces the next stop's line when that stop is the goal. When the
  character already has the recipe's skill: `<budget> covers one <recipe> (<gold>); your <Profession> <skill>
  already meets its <recipe skill>.` (in a line with two goals, that goal's part reads `one <recipe>` and the
  `; your ... already meets its ...` clause comes after the gold). When the goal's route can't craft it for a
  reason gold doesn't change (too little Favor, a tool, materials), the goal stop's line ends `; the route stops
  there: <why>.`: the next stop's line when the goal is the next stop, the `takes` line when the cut takes the
  goal stop. When the character already has the recipe's skill: `<budget> doesn't cover one <recipe>; your
  <Profession> <skill> already meets its <recipe skill>; the route stops there: <why>.` When the goal is two or
  more stops above the cut, after the next stop's line: `The route stops at <Profession> <skill>: <why>.`
  A skill target next to it: `<Profession> is not planned with this budget: it goes to the <Profession>
  goal.` Another of your characters who can make an item the route buys on the AH for less, by the craft
  margin: `Your <Person> <Name> can make the <n> <item> for about <gold> less than the AH and mail them; the
  gold to bring doesn't count that.` (after the budget lines).
- The plan command prints the budget lines after the comparison too, for every budget (once, or after
  `Least gold:` and `Least total value:` when the routes differ), so a budget below the first stop says so
  there and not only in the files.
- Two professions one at a time: the intro says `Level one profession at a time: <first> first, then <second>.`
  instead of "Level both professions side by side".
