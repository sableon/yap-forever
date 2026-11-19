# Setup

Go one step at a time and run `check --offline` after each.

## 1. Python 3.11 or newer

- **Windows:** install from python.org and tick "Add python.exe to PATH". Check with
  `py -3 --version`.
- **macOS:** `python3 --version`; if it is older than 3.11, install from python.org or with
  Homebrew (`brew install python`).
- **Linux:** the distribution's `python3` package, 3.11 or newer.

## 2. Home folder

`<python> -m yap_forever init` creates `~/.yap-forever/` with `profile.toml`,
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
  default `0`) and `dedicated_study` (`true` if the character has taken Dedicated Study,
  default `false`).
- Optional, once at the top of the file: `working_overtime_reading = "relative"` (default) or
  `"points"`, how the player reads the Working Overtime bonus: `relative` adds 4% of the base
  chance per rank, `points` adds 4 percentage points per rank. `plan` uses the rank for every
  skill-up (disenchanting too) and names the rank and reading in the guide header; a character with
  `dedicated_study` gets one guide line about the free daily point.

```toml
working_overtime_reading = "relative"
[characters."Aldra Stoneward"]
favor_standing = "Honored"
working_overtime = 2
dedicated_study = true
```

Each character planned gets `characters/<Name>/stock.toml`:

```toml
level = 40
favor = 300          # Merchant's Favor points
cash_gold = 25       # soft budget
mining = 0           # Mining skill, if the character mines
short_farm_ore = 0
bag_slots = 40       # free normal bag slots while crafting; gives mailbox trips (leave out to skip them)
reagent_slots = 0    # slots in a reagent bag (materials only, filled first); 0 = none
keep_greens = false  # without Enchanting: keep green crafts to disenchant on another character
[goals]              # one or two professions: a skill up to 300, or a recipe to craft once
blacksmithing = 225
enchanting = "Enchant Bracer - Minor Health"
[skills]             # current profession skills; the plan starts here (absent = 1)
blacksmithing = 120
enchanting = 95
[items]              # what the character already has: item ID = count
2840 = 40            # Copper Bar
```

`plan --prof NAME:TARGET` overrides `[goals]` for one run.

Optional `remote.toml` in the home folder, for a player whose own network cannot reach the API
and who has another machine that can fetch prices:

```toml
host = "me@my-vps"                  # required: an ssh host
key = "~/.ssh/id_example"           # optional: ssh key file; ~ is expanded
command = "cd yap-forever && git pull -q && python3 -m yap_forever prices"  # default, run there
remote_file = ".yap-forever/cache/prices.json"  # default: where that machine leaves its prices
```

Without the file nothing changes. An empty `host` is refused.

## 3. Blizzard API client

The player creates it themselves; you never see the secret.

1. Sign in at https://develop.battle.net/access/clients and choose "Create Client".
2. Any name. No redirect URL needed. "Service URL" can be left empty.
3. The player opens `~/.yap-forever/credentials.json` in a text editor and pastes the Client ID
   and Client Secret between the quotes. Set `"region"` to the same region as the profile.
4. `<python> -m yap_forever check` (without `--offline`) should now say `API token OK`.

If the API can't be reached at all (timeouts), the player's network may block it. Two fallbacks
for prices are in step 5: another machine over ssh, or Auctionator's saved data.

## 4. Find the auction house

The API does not say which auction house belongs to which realm and faction, so the player marks
theirs:

1. In game, list one cheap item on the auction house at an odd buyout no one else would use,
   e.g. 7g 13s 13c (= 71313 copper). Note the item ID (Wowhead or an addon shows it).
2. Wait for the next API snapshot, up to about an hour.
3. `<python> -m yap_forever probe --item <ID> --buyout <copper>`.
4. If it finds the marker in no house or several, wait an hour or pick a stranger buyout and
   try again. The saved house is only replaced when exactly one house matches.

## 5. Prices

`<python> -m yap_forever prices`. Then `check` should show every line `OK`.

If the API can't be reached from the player's machine, there are two fallbacks. Both save the
same prices file the normal command does, so `plan` works unchanged.

**From another machine (`--remote`).** Needs OpenSSH (`ssh` and `scp` on the PATH: included with
Windows 10 and later (an optional feature on some builds), macOS and Linux) and a machine that can
reach the API and has this tool set up. Write `remote.toml` in the home folder (the keys are in step
2), then run `<python> -m yap_forever prices --remote`. It runs the remote command over ssh, copies
the prices file back and replaces the saved prices only when the copy is a valid prices file with
listings. The ssh login must work without a prompt (ssh-agent or an unencrypted key), because the
command asks for no passphrase or password and fails at once if one is needed. `--host NAME`
replaces the host from `remote.toml` for one run (the other keys stay; without a `remote.toml` the
defaults apply). Keep the host and key path to the player's own machine; never paste them anywhere
public.

**From Auctionator (`--auctionator`).** For a player with the Auctionator addon who has scanned the
auction house in game. Log out or `/reload` first so the game writes its saved data, then run
`<python> -m yap_forever prices --auctionator PATH`, where PATH is the addon's file:
`WTF/Account/<account>/SavedVariables/Auctionator.lua` inside the game folder, for example
`.../World of Warcraft/<game version folder>/WTF/Account/MYACCOUNT/SavedVariables/Auctionator.lua`.
The game version folder depends on the install, and `<account>` is the player's account folder. If
the file holds several realms, the command lists their keys and asks for `--realm KEY`. If it holds
none, scan the auction house with Auctionator first.

What an Auctionator import can't give: one price and one count per item, no listing depth. The
planner buys the whole quantity at that one price, so costs are a lower bound, and sale limits
that depend on listing counts use the day's quantity, so they are approximate. Items whose latest
count is more than 3 days older than the newest scan, or zero, are left out, and the guide and
report say how many. The guide and report header names the scan day and warns when it is more
than 3 days old: tell the player to scan again before relying on the numbers.
