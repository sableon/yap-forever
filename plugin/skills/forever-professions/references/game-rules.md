# WoW: Forever rules for profession planning

Learned in play. Where the planner's data (much of it from Classic) disagrees, go with these and
say so.

## Trainers and ranks

- Expert trainers train up to 150, Artisan to 225, Master to 300. Artisan and Master trainers
  sit in specific towns.
- **A trainer teaches every recipe from 1 up to its rank's cap**: Journeyman to 75, Expert to 150,
  Artisan to 225, Master to 300. The rule is confirmed in game (2026-11-21). Expert trainers stop at 150: the
  Stormwind Expert Blacksmith doesn't teach Truesilver Rod (175), and an Artisan does. A higher
  rank also teaches every recipe of the lower ranks, so a guide never needs a second trainer for a
  lower recipe. A recipe's rank is the lowest whose cap is at or above its required skill (the safe
  one, below).
- Level requirements (Classic data, not yet contradicted): 150 needs level 10, 225 level 20,
  300 level 35. The pinned trainer data gives Tailoring's Master rank level 0 (and a few other
  ranks too); a rank with level 0 takes the level the other professions give the same cap, when
  they agree, so Tailoring to 300 waits for level 35 like every other profession.
- Fees: base 5s / 50s / 5g per rank; players report that only reputation changes them. The
  client data shows small per-profession differences that nobody has confirmed in game.
- **Recipe skill requirements at trainers are often inferred** from Classic and moved down. Some
  hold (a recipe learnable about 25 points earlier than in Classic), some don't (a recipe missing
  from the trainer 30 points past its inferred level). Skill points come only from crafting (and
  one legacy talent), so the planner plans the **safe route**: a trainer recipe whose inferred skill
  is above the Forever listing is learned and crafted from the inferred skill, so the route works
  wherever the trainer sets the bar. Recipes from vendors, Favor, patterns and quests are not
  changed. The learn row says where the Forever data lists the recipe, and each route's header
  and report notes say how much cheaper it could be if trainers offer recipes at the listing.
  A recipe seen learnable in play below its inferred skill keeps the Forever requirement
  (`yap_forever/data_static/seen_requirements.toml`): Truesilver Rod was learned at Blacksmithing
  184, so it needs 175, not the inferred 200. Each row is a single observation and an upper bound only.
- Trainer places are not listed here: the guide's trainer rows come from the Questie Forever NPC
  data, for the character's faction. Facts the data lacks: Booty Bay is a neutral town, and the
  Alliance Master Enchanting trainer is inside Uldaman (Badlands), which has no map coordinates.
  Booty Bay, Gadgetzan and Everlook have a neutral auction house with its own prices and a higher
  deposit; the planner's prices are the faction auction house's, so the guide calls it out.
- From what character level each Artisan and Master trip is comfortable, which trainers have a
  flight path for repeat visits, small tips, and which capital trainers are close together
  (Stormwind City: Tailoring, Alchemy and Enchanting; Blacksmithing and Engineering; Leatherworking
  alone) were noted in play (2026-11-19) and live in `yap_forever/data_static/trainer_notes.toml`; the guide's
  trainer rows say them. They are tips only and never change the route.

## Bags, bank and mail

- Buying is never the limit: auction house purchases wait in the mail for 30 days.
- The limit is crafting and selling space: each crafted gear piece takes a slot.
- Bag slots: the backpack (16) plus 4 normal bags and **1 reagent bag**. A reagent bag holds any
  crafting materials, so materials can sit there while normal slots hold the crafts. The planner
  counts them apart: `bag_slots` are free normal slots, `reagent_slots` the slots of the reagent bag.
  Any item a loaded recipe uses as a reagent, and any trade good (item class 7: crafted
  intermediates and disenchant materials too), goes in the reagent bag first; gear (weapons,
  armor), patterns and tools never do. Packed essences count as reagents.
- A pattern item (`Plans:`, `Pattern:`) in a character's own stock teaches its recipe at no cost, on
  every character: it is used up when learned (no longer owned, sellable or bought, and
  not on the shopping list), and the recipe's skill requirement still applies. Only recipes taught
  by a pattern item count; trainer, Favor and quest recipes are unchanged.
- A mail a player sends holds at most 12 attachments; auction house mail can hold more.
- Items move in stacks. Usually 20; potions often 5; armor kits 10. The client's `Stackable`
  field has matched every in-game check so far; when an item has none, or two item IDs exist,
  ask the player.
- Tailoring makes bags, including reagent bags: a tailoring character can grow its own bag space
  as it levels and later supply bags to other characters.

## Disenchanting

- **Forever has no item-level gate on disenchanting:** at low Enchanting skill a player
  disenchanted greens up to item level 44 (the Classic rule would have needed 125). Disenchant
  everything at once.
- Disenchanting gives Enchanting skill-ups, with thresholds near 1 / 20 / 40 / 60: roughly 19
  disenchants to reach 20, 46 to 40, 73 to 50, 190 to 60.
- Disenchanting levels Enchanting only up to 60 (the last threshold). Enchanting from 1 to 60 costs
  about 41s by recipes (measured 2026-11-20 on a fresh character, at that day's auction house
  prices), so using a crafting profession's greens for those skill-ups would save under 1g, and
  only for a character starting both professions from scratch. The planner never reorders
  professions for it: both level side by side, and the greens are disenchanted for materials in
  any order, since Forever has no disenchant gate.
- Enchanting wands can't be disenchanted.
- Disenchanting "compresses" green crafts into stackable dust, essences and shards, which saves
  bag space on long routes.
- Essences pack 3 lesser into 1 greater of the same kind and back (Magic, Astral, Mystic, Nether,
  Eternal), so carried essences take fewer bag slots.

## Merchant's Favor

- Merchant's Favor recipes are personal-use rewards: the planner never uses them to level, as
  needed or in one go, and plans no trip to the Favor vendor for them. A Favor recipe set as a
  recipe target is still planned: learned with Favor and crafted once, with its trip to the Favor
  vendor (in one go, its pattern on the remote trainer's bring list); a target's trip has no skip.
- The guide and the report suggest Favor recipes to craft once for yourself instead
  ([list-layout.md](list-layout.md), "You could also make"), for the character's standing, when
  the crafted item's required level is within 5 levels of the character's level (within 3 from
  character level 46): gear far below the character is outgrown, gear far above can't be worn yet.
  An item whose required level the game data doesn't give is not suggested; an item with required
  level 0 (no requirement) has no level test, nor has an enchant, which crafts no item (a level
  taken from the same skill's items would hide the necklace enchants from a character who made
  one). The character's current skill must reach the
  recipe's Favor skill, and its Favor the price. The materials come from the bank first, then by
  mail from the group's other characters, and the rest is bought at today's AH or vendor price;
  that gold must fit the group's gold, before the route. A reagent with no price that nobody holds
  rules the recipe out. A craft-once target is not suggested: the route plans it. Without `level` in
  `stock.toml` only the items with no level requirement and the enchants are suggested, and the guide
  and the report say to set it.

## Legacy talents

- **Milestones:** the first time a profession on the account reaches 150, 225 and 300 gives one
  legacy talent point each. They make good targets to suggest; the planner doesn't count them.
- **Working Overtime** (up to 5 ranks, 4% each) raises the chance of a skill-up from every
  tradeskill. Guides disagree whether 20% at 5/5 means 20 percentage points or 20% more of the
  base chance. The planner takes the rank from the profile (`working_overtime`) and the reading
  from `working_overtime_reading`: `relative` is p x (1 + 0.04 x rank), `points` is p + 0.04 x
  rank, both capped at 1; a craft that can't skill up stays at 0. It applies to disenchanting too,
  because those are Enchanting skill-ups. Which reading is right is unconfirmed in game; the guide
  header and the report's data notes say the rank and the reading used (nothing when the rank is 0).
- **Dedicated Study** gives one free point a day to the lowest profession. It changes no route:
  when the character has it, the guide header and the report's data notes add one line, "N days
  would cover the last N points" of the lower-skill planned profession (on a tie the first of the
  route), N being that profession's points from its start to its target on the route.
  On that profession's route, a row (one recipe over a skill range) that costs at least
  `study_hint_gold_per_point` gold a point (default 100, set in `profile.toml`; an example
  threshold, not a rule) gets a hint: how many days of the free point would cover its points, and
  "(a legacy talent you haven't taken)" when the character hasn't taken it. The cost is the row's
  own, in the route's measure (gold out of pocket for the least-gold route, net cost for the
  least-total-value route): its crafting cost as the report's Route table shows it, before resale
  or leftover credit. Other professions and cheaper rows get no hint.

## Loot

- Dungeon and raid item stats are hidden until the item first drops, and there is no Dungeon
  Journal. The client's item table doesn't carry that loot, so its stats are unknown until
  someone reveals them.

## Enchanting from the profession window

Forever's client uses the modern profession API (`DoCraft` and `DoTradeSkill` don't work). This
macro enchants the selected recipe onto an equipped item (slot 9 = wrist; chest 5, cloak 15,
two-hand 16, boots 8):

```
/run local r=ProfessionsFrame.CraftingPage.SchematicForm:GetRecipeInfo() C_TradeSkillUI.CraftEnchant(r.recipeID,1,{},ItemLocation:CreateFromEquipmentSlot(9))
/click StaticPopup1Button1
```
