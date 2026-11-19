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

Each character planned gets `characters/<Name>/stock.toml`:

```toml
level = 40
favor = 300          # Merchant's Favor points
cash_gold = 25       # soft budget
mining = 0           # Mining skill, if the character mines
short_farm_ore = 0
bag_slots = 40       # free bag slots while crafting; gives mailbox trips (leave out to skip them)
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

## 3. Blizzard API client

The player creates it themselves; you never see the secret.

1. Sign in at https://develop.battle.net/access/clients and choose "Create Client".
2. Any name. No redirect URL needed. "Service URL" can be left empty.
3. The player opens `~/.yap-forever/credentials.json` in a text editor and pastes the Client ID
   and Client Secret between the quotes. Set `"region"` to the same region as the profile.
4. `<python> -m yap_forever check` (without `--offline`) should now say `API token OK`.

If the API can't be reached at all (timeouts), the player's network may block it. A VPN or
another machine can fetch prices for now. Price import from an addon is planned.

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
