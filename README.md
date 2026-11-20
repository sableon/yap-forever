# yap-forever

> **Work in progress.** Phase 2 of 5: the planner works for any one or two crafting professions,
> with trainer stops, legacy talents, bag space and price fallbacks. Setup covers every region
> and both factions, but only EU has been tried.

**Yet another planner** for WoW: Forever. A Claude Code plugin that finds the cheapest way to
level your professions from **your own auction house prices**, and writes the route the way you
follow it in game: craft by craft, with a shopping list, mailbox trips and a buffer for unlucky
skill-ups.

## What you need

- [Claude Code](https://claude.com/claude-code)
- Python 3.11 or newer (Windows: from python.org, then `py -3 --version`; macOS and Linux:
  `python3 --version`)
- A free Blizzard API client from [develop.battle.net](https://develop.battle.net/access/clients)

## Install

In Claude Code:

```
/plugin marketplace add sableon/yap-forever
/plugin install yap-forever@yap-forever
```

Then ask Claude something like "plan my Forever Blacksmithing to 150". The first time, it walks
you through setup: your profile, your API client, and finding your auction house with one marker
listing.

## Update

Each tag is a new version. Updates are off by default for this marketplace; either turn them on
(`/plugin`, **Marketplaces**, select yap-forever, turn on auto-update) or update by hand in a
terminal:

```
claude plugin marketplace update yap-forever
claude plugin update yap-forever@yap-forever
```

The new version loads in your next session, or after `/reload-plugins`. Game data follows the
version: the first plan after an update downloads what changed.

## Privacy

Your API client, characters, stock and prices stay in `~/.yap-forever/` on your machine. Claude
never reads your credentials file; you paste the client ID and secret into it yourself. Never
share that file.

## Command line

The skill runs these for you, but they work on their own too (`py -3` instead of `python3` on
Windows). From a clone of this repository, run them in the `plugin` folder (`cd plugin` first):

```
python3 -m yap_forever init       # create ~/.yap-forever with a profile and credentials file
python3 -m yap_forever check      # what is set up and what is missing
python3 -m yap_forever probe --item ITEM_ID --buyout COPPER   # find your auction house
python3 -m yap_forever prices     # download your auction house's prices
python3 -m yap_forever plan --character NAME
```

## Contributing

Bug reports, game-data corrections from play, and pull requests are welcome: see
[CONTRIBUTING.md](CONTRIBUTING.md). Never post your API client ID or secret; see
[SECURITY.md](SECURITY.md).

## Licence and credits

GPL-3.0-or-later. Game data comes from other projects and Blizzard; see [plugin/CREDITS.md](plugin/CREDITS.md).
Not affiliated with Blizzard Entertainment.
