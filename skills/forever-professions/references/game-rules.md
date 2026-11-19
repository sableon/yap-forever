# WoW: Forever rules for profession planning

Learned in play. Where the planner's data (much of it from Classic) disagrees, go with these and
say so.

## Trainers and ranks

- Expert trainers train up to 150, Artisan to 225, Master to 300. Artisan and Master trainers
  sit in specific towns.
- Level requirements (Classic data, not yet contradicted): 150 needs level 10, 225 level 20,
  300 level 35.
- Fees: base 5s / 50s / 5g per rank; players report that only reputation changes them. The
  client data shows small per-profession differences that nobody has confirmed in game.
- **Recipe skill requirements at trainers are often inferred** from Classic and moved down. Some
  hold (a recipe learnable about 25 points earlier than in Classic), some don't (a recipe missing
  from the trainer 30 points past its inferred level). When a route leans on such a recipe, flag
  it and give a fallback craft.
- Trainer places are not listed here: the guide's trainer rows come from the Questie Forever NPC
  data, for the character's faction. Facts the data lacks: Booty Bay is a neutral town, and the
  Alliance Master Enchanting trainer is inside Uldaman (Badlands), which has no map coordinates.

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
  the main as on the alts: it is used up when learned (no longer owned, sellable or bought, and
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
- Enchanting wands can't be disenchanted.
- Disenchanting "compresses" green crafts into stackable dust, essences and shards, which saves
  bag space on long routes.
- Essences pack 3 lesser into 1 greater of the same kind and back (Magic, Astral, Mystic, Nether,
  Eternal), so carried essences take fewer bag slots.

## Legacy talents

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
