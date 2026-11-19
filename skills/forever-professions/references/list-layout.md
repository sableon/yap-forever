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
- Trainer recipes are the same at every trainer. Trips away from home are rank training to 225
  and 300 (Artisan and Master trainers sit in set towns), vendor-sold patterns and the Merchant's
  Favor vendor. Say a trip is needed, how to avoid a second one (buy every vendor pattern on one
  visit; patterns can be bought before they can be learned), and what to bring to keep levelling
  at a remote trainer, with the bag slots it takes.
- Name the trainer from the data, for the character's faction (the profile's `faction`; without it
  the row says "a set town"). A remote rank row reads `**Trip:** Blacksmithing rank to 300: <name>,
  <zone> (x, y). Nearby: bank, mailbox; no auction house.` (map coordinates; "Nearby" is a bank, an
  auction house and a mailbox within a few map units of the trainer, same zone, and says plainly
  when there is none). A trainer inside an instance reads `<name>, inside <instance>` and gets no
  coordinates, never `(-1, -1)`. A trainer in a capital of the character's own faction gets no
  "Nearby" line (capitals have all three); a trainer in the other faction's capital still does.
  Name only trainers whose title names the rank; if there is none, name the odd-titled one with
  "(title unconfirmed in the data)". When the data has no trainer of that rank for the faction, say so
  in a sentence; never leave a name or a place empty.
- Expert and Journeyman ranks are not trips: `Train Blacksmithing to 150 at any Expert Blacksmith
  in a capital (for example <name>, <capital>).` names up to two trainers in the faction's capitals.
  When none of the rank's trainers is in a capital, the row names up to two of them with their zones
  and says `(no Expert Blacksmith in a capital in the data)`, never "in a capital".
- A trainer recipe whose requirement is only inferred from Classic (`TrainerInferred`) and is above
  the skill the route learns it at gets a note inside the fee's parenthesis: `(trainer <fee>; inferred: the trainer may ask up to
  <skill>; if it isn't offered, craft <recipe> instead)`. The recipe is the first later row of the
  profession that the player can craft at that skill (its requirement is met and it is not itself a
  trainer recipe inferred higher); when there is none the note says `come back at <skill>`.
- If the trainer data can't be downloaded or read, the guide renders without names and says why
  once, near the top.
