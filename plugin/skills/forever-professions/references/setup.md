# Setup

Go one step at a time and run `check --offline` after each. `<planner>` is the command form
in SKILL.md, "Running the planner".

## 1. Python 3.11 or newer

- **Windows:** install from python.org and tick "Add python.exe to PATH". Check with
  `py -3 --version`.
- **macOS:** `python3 --version`; if it is older than 3.11, install from python.org or with
  Homebrew (`brew install python`).
- **Linux:** the distribution's `python3` package, 3.11 or newer.

## 2. Home folder

`<planner> init` creates `~/.yap-forever/` with `profile.toml`,
`credentials.json` (readable only by the player), `characters/`, `cache/` and `reports/`. It
never overwrites existing files.

Fill in `profile.toml` with the player:
- `region`: `eu`, `us`, `kr` or `tw`. Only `eu` has been tried so far: if another region fails,
  say so plainly.
- `ruleset`: `2` is Normal.
- `faction`: `alliance` or `horde`.
- One section per character, under its full name in quotes (Forever names are two words):
  `[characters."Aldra Stoneward"]`, with `favor_standing` (`Neutral`, `Friendly`, `Honored`,
  `Revered` or `Exalted`). Pass the same name to `plan --character "Aldra Stoneward"`.
  Optional per character: `working_overtime` (rank of the Working Overtime talent, `0` to `5`,
  default `0`), `dedicated_study` (`true` if the character has taken Dedicated Study,
  default `false`), and `ruleset` and `faction` (see "Ruleset and faction groups" below; they
  default to the top-level values).
- Optional per character: `trainer_trips`: `"as_needed"` (default) or `"one_go"`, how the character
  levels when a rank is trained at a remote trainer (Artisan and Master trainers sit in set towns).
  `as_needed`: train the rank, level anywhere, and go back to the trainer for each later recipe only
  that trainer teaches (each such trip says what skipping it costs; one that costs nothing to skip is
  left out of the route). `one_go`: level at the trainer up
  to the next rank or the target, learning those recipes there as the skill reaches them; the bring
  list covers the whole stretch ([list-layout.md](list-layout.md), "Trainer stages and trips"). The
  skill asks once per character (SKILL.md, step 5, or step 3 with the `capital` question); the one
  answer also decides the stage in the other capital (`capital`, below).
- Optional per character: `capital`, the capital the guide starts in (every capital has an AH,
  mailbox and bank): `"stormwind"`, `"ironforge"` or `"darnassus"` for Alliance, `"orgrimmar"`,
  `"thunder_bluff"` or `"undercity"` for Horde; another faction's capital, or any other value, is
  refused. A stage of the route needs a capital when all its rank's trainers stand there (the
  Artisan Engineer in Ironforge, say). Left out (default), the guide starts in the only capital the
  route's stages need, or, when two professions point to two capitals, in the one whose stage the
  route reaches first, and it says how to start in the other. In that capital the guide levels the
  stage: the stage starts with a line naming its trainer, and the rank training and the visits back
  for recipes are capital stops, not trips, with no bring list, whatever `trainer_trips`. The other
  capital follows `trainer_trips`; its trips have no bring list either (buy there). Remote trainers
  (every Master, the Artisan Enchanters) stay trips. "Trips away" counts the trips outside the
  capital the guide starts in. Without the trainer data or a faction, or with no stage in a capital,
  the guide names no capital, as before. The skill asks for it with `trainer_trips` when the route's
  stages are in two capitals (SKILL.md, step 3).
- Optional, once at the top of the file: `working_overtime_reading = "relative"` (default) or
  `"points"`, how the player reads the Working Overtime bonus: `relative` adds 4% of the base
  chance per rank, `points` adds 4 percentage points per rank. `plan` uses the rank for every
  skill-up (disenchanting too) and names the rank and reading in the guide header; a character with
  `dedicated_study` gets one guide line about the free daily point.
- Optional, once at the top of the file: `study_hint_gold_per_point = 100` (default; a number of gold
  above 0). It is an example threshold you can change: on the lowest profession's route, a row that
  costs this much gold a point or more gets a note that Dedicated Study (one free point a day) would
  cover its points, with "(a legacy talent you haven't taken)" if the character lacks it. A lower
  number shows more hints.

```toml
working_overtime_reading = "relative"
[characters."Aldra Stoneward"]
favor_standing = "Honored"
working_overtime = 2
dedicated_study = true
trainer_trips = "one_go"
[gold]                      # see "Ruleset and faction groups" below
"2/alliance" = 45
```

Every character gets the same file, `characters/<Name>/stock.toml`, and its own reports: the
planner treats all characters alike, whatever the player calls them.

**Ruleset and faction groups.** Characters on the same ruleset and faction share their gold (there
is no character-bound gold), and mail each other bind-on-equip items and most patterns. The
auction house belongs to the ruleset and faction too. A character's group is its `ruleset` and
`faction` (set under `[characters."Name"]`; left out, they are the profile's top-level values).
Ask the player for gold once per group, not per character:

- `[gold]` in `profile.toml`, keyed `"<ruleset>/<faction>"`, for example `"2/alliance" = 45` (gold,
  a number, 0 or more). The report's budget line compares the plan's cash with it: "within the
  45g 0s 0c shared by your 2/alliance characters", or "over the ... by <amount>".
- A group with no `[gold]` entry and at least two characters with a `stock.toml` uses the sum of
  `cash_gold` in those files (older files keep working), and the report says so once in its notes.
  A character alone in its group, with no `[gold]` entry, has just its own `cash_gold` as before:
  "within / over your 12g 0s 0c budget", with no note. `[gold]` is preferred: `cash_gold` in a
  stock file is the old, per-character place for it.
- The profile may hold characters on two rulesets (for example Normal, `2`, and RP-Normal). Their
  gold is kept apart, per ruleset and faction.
- Only the profile's own ruleset and faction have prices (the saved prices and `house.json`). `plan
  --character X` for a character on another ruleset or faction stops with a message that there are
  no prices for it yet and that planning it isn't supported yet.

**Items shared by mail.** When planning a character, every other character of its group that has a
`stock.toml` adds its `[items]` that can be mailed: bonding none, on equip or on use
(ItemSparse `Bonding` 0, 2 or 3). Items bound on pickup (1) and quest items (4) stay with their
character, and so do items the game data doesn't know. The planner uses a character's own items
first, then these by mail, then buys. In the "least total value" route they cost what they would
sell for, like the character's own items. A mailable pattern held by another character teaches its
recipe like an owned pattern (free in cash, used up). A mailable tool another character holds counts
as held (no cash; the lists name it), and when Enchanting is planned its mailable greens are
disenchanted after the character's own ("disenchant 30 X (mail from Name)"). Another character's
ore is not smelted into bars. The shopping list, mailbox trips and bring
lists name the source: "20 Copper Bar (mail from Aldra Stoneward)", several sources each, in name
order; the counts are the whole crafts the shopping list asks for (the buffer included), the same in
the guide's notes. The other characters' stock is counted as it is now, with nothing reserved between plans, so
the report says once that two plans may count the same items. Characters outside the group, or
without a `stock.toml`, add nothing. A group mate's `stock.toml` that can't be read is left out
(items and gold), and the report and guide notes name the file; the plan goes on.

Each character planned gets `characters/<Name>/stock.toml`:

```toml
level = 40
favor = 300          # Merchant's Favor points
cash_gold = 25       # old place for gold: see "Ruleset and faction groups"
mining = 0           # Mining skill, if the character mines
skinning = 0         # Skinning skill, if the character skins (the guide then says to gather leather)
short_farm_ore = 0
bag_slots = 40       # free normal bag slots while crafting; gives mailbox trips (leave out to skip them)
reagent_slots = 0    # slots in a reagent bag (materials only, filled first); 0 = none
keep_greens = false  # see "Green crafts" below
# ah_premium = 2     # optional: see "Selling crafts" below
# quest_item_sales = 10  # optional: how many of each quest item the AH takes (left out: no limit)
[goals]              # one or two professions: a skill up to 300, or a recipe to craft once
blacksmithing = 225
enchanting = "Enchant Bracer - Minor Health"
# budget = 20        # optional: plan only as far as 20 gold reaches (see "A budget as a goal")
# budget_order = "even"  # with two professions: "even", or one at a time: ["blacksmithing", "enchanting"]
# pay = "upfront"   # with a budget: buy everything before you start, or "as_you_go" (see "A budget as a goal")
[skills]             # current profession skills; the plan starts here (absent = 1)
blacksmithing = 120
enchanting = 95
[items]              # what the character already has: item ID = count
2840 = 40            # Copper Bar
```

`plan --prof NAME:TARGET` overrides `[goals]` for one run.

**A budget as a goal.** "How far does 20g get me?": `budget = 20` under `[goals]` (gold, a number, 0
or more), or `plan --budget GOLD` for one run (the flag wins over the key). Each profession's target
still bounds the route; the route ends at the last stop the gold reaches. Stops are the rank caps
75, 150, 225 and 300 and the profession's own target. The gold a stop needs is set by `pay` under
`[goals]` (or `plan --pay upfront|as_you_go` for one run; the flag wins over the key; it goes with a
budget): `pay = "upfront"` (the default) takes the shopping list's "Gold to bring" (whole crafts with
the buffer, patterns and trainer fees, everything bought before you start), so the list fits the
budget; `"as_you_go"` takes the gold enough up front when you sell crafts to a vendor as you go and buy
each row's reagents when you reach it (the line under "Gold to bring"; AH sales never count). A
craft's vendor price makes a route cheaper in the end but can make it need more of that gold, so
each stop takes the route planned with what vendors pay back when its gold fits, else the route
planned without it when that one fits and gets each profession as far; the stop is reached when
either fits.
With two professions, `budget_order` (or `--order even|NAME,NAME`) says how to share it:

- `"even"` (the default): both rise side by side, the lower one first. When its next stop doesn't
  fit, the gold left goes to the other one's next stop if that fits.
- a list of names, for example `["blacksmithing", "enchanting"]` (`--order blacksmithing,enchanting`):
  one at a time. The first takes its stops while they fit; the second gets what is left. A name
  that isn't planned is refused; with one profession the order is ignored.

A profession that can't advance (rank cap, level gate, no recipe) gets none of the gold, and the
guide says why. The plan output, the guide and the report say what the budget reaches and what each
next stop costs on top ([list-layout.md](list-layout.md), "Budget"); the report's budget line adds
"planned to your 20g budget". Both routes (least gold, least total value) are cut by their own gold.

A budget with a recipe target (craft once) covers that profession's goal: its stops are the rank caps
below the recipe's skill, then the goal, that skill with the recipe crafted once (only the goal's
route crafts it); a recipe whose skill the character already has is one stop, the craft. The plan
output, the guide header and the report verdict say what it covers or how far it gets, and what the
goal costs on top (or why the route can't craft it, for example too little Favor, also when the skill
is already there). A second profession with a skill target is not planned with the budget: the gold
goes to the recipe goal. It stays at its skill in `[skills]`, and
its trainer recipes up to that skill (assumed known) may make one of the goal's reagents when that
costs less than buying by the craft margin ("Craft or buy" in [list-layout.md](list-layout.md)): the
route row says `first craft <n> <item> (your <Profession>)`. Two recipe targets are cut like two skill
targets (`budget_order`). Your other characters of the same ruleset and faction with `[skills]` in
their `stock.toml` are named when they can make an item the route buys on the AH for less: a
suggestion only, not counted in "Gold to bring".

**Green crafts.** `keep_greens` (default `false`) matters only when the plan has no Enchanting.
With `true`, green crafts that can be disenchanted are kept for another character's Enchanting
instead of sold, and the plan counts them at the value of their disenchanting materials. With
`false` they are sold.

**Selling crafts.** A leftover craft counts as sold on the AH only when the AH pays, after its cut,
at least `ah_premium` times its vendor price and 1s more; otherwise it goes to a vendor.
`ah_premium` is a number, 1 or more, default 2 when left out; anything else is refused, naming
the file and the key. At most 5 of each craft count as sold there
(quest items: `quest_item_sales`, no limit when left out), whatever is listed today. The rule and
the report's supplier note are in [game-rules.md](game-rules.md), "Selling crafts".

**Report names.** `plan` writes `reports/<date>-<name>-plan-gold.md`, `-plan-value.md`,
`-guide-gold.md` and `-guide-value.md`, so each character keeps its own set. `<name>` is the
full name in lower case, with spaces as `-`, characters Windows refuses in file names
(`< > : " / \ | ? *` and control characters) left out and accented letters kept:
`Aldra Stoneward` gives `aldra-stoneward`. Two-word names can share a first or a second name, so
the whole name is used. If nothing is left of a name, or two characters in the profile give the
same `<name>`, `-` and the first 8 hex digits of the SHA-1 of the full name are added. When a
character whose name gives the same `<name>` is added to the profile later, both characters' reports
switch to the hashed names, and files written earlier keep their old names.

**A bags file.** A home from before every character had a `stock.toml` may hold only
`characters/<Name>/bags.toml` (`profs`, `bag_slots`, `reagent_slots`, `[items]`). The first
`plan --character "<Name>"` makes a `stock.toml` from it: `bag_slots`, `reagent_slots` and `[items]`
carry over, the professions become commented lines under `[skills]` and `[goals]`, and a comment at
the top says what to fill in: `level`, `[skills]` and `[goals]`, and that gold goes under `[gold]` in
`profile.toml`. It prints one line naming
the new file, and never overwrites a `stock.toml` or deletes the `bags.toml`. Fill the values in
with the player, then plan.

**Moving an old planner folder.** `<planner> migrate --from-data DIR --character
"NAME=FILE" [--character "NAME=FILE" ...]` (at least one `--character`; `--region`, `--ruleset` and
`--faction` set the profile) copies the old data folder's house and prices (game data is downloaded by the next `plan`) and gives every
character `characters/<NAME>/stock.toml`. An existing `stock.toml` is kept, never overwritten. `FILE`
is a stock file (copied; one without `[goals]` gets Blacksmithing and Enchanting at its `target`) or a bags file (a file with a `profs` key; converted as
above). Every character is listed in the profile. Credentials are never copied: the player pastes
them in.

Optional `remote.toml` in the home folder, for a player whose own network cannot reach the API
and who has another machine that can fetch prices:

```toml
host = "me@my-vps"                  # required: an ssh host
key = "~/.ssh/id_example"           # optional: ssh key file, an absolute path or one starting with ~
command = "cd yap-forever && git pull -q && cd plugin && python3 -m yap_forever prices"  # default, run there
remote_file = ".yap-forever/cache/prices.json"  # default: where that machine leaves its prices
```

Without the file nothing changes. An empty `host` is refused.

## 3. Blizzard API client

The player creates it themselves; you never see the secret.

1. Sign in at https://develop.battle.net/access/clients and choose "Create Client".
2. Any name. No redirect URL needed. "Service URL" can be left empty.
3. The player opens `~/.yap-forever/credentials.json` in a text editor and pastes the Client ID
   and Client Secret between the quotes. Set `"region"` to the same region as the profile.
4. `<planner> check` (without `--offline`) should now say `API token OK`.

If the API can't be reached at all (timeouts), the player's network may block it. Two fallbacks
for prices are in step 5: another machine over ssh, or Auctionator's saved data.

## 4. Find the auction house

If you use a price fallback from step 5 (`--remote` or `--auctionator`), skip this step. `check`
will keep showing credentials and house as missing (once the prices are imported from Auctionator,
it says "not needed with imported prices" instead), and `plan` doesn't need them.

The API does not say which auction house belongs to which realm and faction, so the player marks
theirs:

1. In game, list one cheap item on the auction house at an odd buyout no one else would use,
   e.g. 7g 13s 13c (= 71313 copper). Note the item ID (Wowhead or an addon shows it).
2. Wait for the next API snapshot, up to about an hour.
3. `<planner> probe --item <ID> --buyout <copper>`.
4. If it finds the marker in no house or several, wait an hour or pick a stranger buyout and
   try again. The saved house is only replaced when exactly one house matches.

## 5. Prices

`<planner> prices`. Then `check` should show every line `OK`. Prices update about once an hour.

If the API can't be reached from the player's machine, there are two fallbacks. Both save the
same prices file the normal command does, so `plan` works unchanged.

**From another machine (`--remote`).** Needs OpenSSH (`ssh` and `scp` on the PATH: included with
Windows 10 and later (an optional feature on some builds), macOS and Linux) and a machine that can
reach the API and has this tool set up. Write `remote.toml` in the home folder (the keys are in step
2), then run `<planner> prices --remote`. It runs the remote command over ssh, copies
the prices file back and replaces the saved prices only when the copy is a valid prices file with
listings, for the profile's region and ruleset (and for the saved auction house, when `house.json`
exists). A copy for another region, ruleset or house is refused and the saved prices stay.
Run `ssh HOST` once by hand first, so the machine's host key is known: the command refuses an
unknown key instead of asking. The ssh login must work without a prompt (ssh-agent or an
unencrypted key), because the command asks for no passphrase or password and fails at once if one
is needed. `--host NAME`
replaces the host from `remote.toml` for one run (the other keys stay; without a `remote.toml` the
defaults apply). Keep the host and key path to the player's own machine; never paste them anywhere
public.

**From Auctionator (`--auctionator`).** For a player with the Auctionator addon who has scanned the
auction house in game. Log out or `/reload` first so the game writes its saved data, then run
`<planner> prices --auctionator PATH`, where PATH is the addon's file:
`WTF/Account/<account>/SavedVariables/Auctionator.lua` inside the game folder, for example
`.../World of Warcraft/<game version folder>/WTF/Account/MYACCOUNT/SavedVariables/Auctionator.lua`.
The game version folder depends on the install, and `<account>` is the player's account folder. If
the file holds several realms, the command lists their keys and asks for `--realm KEY`. If it holds
none, scan the auction house with Auctionator first.

What an Auctionator import can't give: one price and one count per item, no listing depth. The
planner buys the whole quantity at that one price, so costs are a lower bound. The day's count
doesn't limit how many crafts count as sold; the report's supplier note and buyout flag use it as
the listing count, so they are approximate. The scan day is the day
most items were last seen (the full scan), so a later partial scan doesn't hide it. Items whose latest
count is more than 3 days older than that day, or zero, are left out, and the guide and
report say how many. The guide and report header names the scan day and warns when it is more
than 3 days old: tell the player to scan again before relying on the numbers.
