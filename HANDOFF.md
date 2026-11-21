# Handoff

State on 2026-11-21. Phase 1 is done and tagged (`v0.1.0-planner`). The phase 2 planner work is
in (`docs/progress.md`, 2.1 to 2.23), and so are the fixes from the engineering review of
2026-11-19 (parts A to E, 2.24 to 2.28); phase 2 is tagged `v0.2.0-general-planner` (to 2.30). The
0.2.1 batch is tagged `v0.2.1-options` (2.31 to 2.37). Phases 3 to 5 are planned by the owner; the
plans are private.

## What works

- Phase 1: the planner from the owner's personal project, as a package, with a per-player home
  folder `~/.yap-forever/` (`YAP_FOREVER_HOME` overrides), one command line, setup checks with
  next steps, and any region and ruleset in principle (only EU tried). An independent review
  (2026-11-18) found ten issues; all are fixed (PRs 15 to 22).
- Phase 2:
  - Any crafting profession, one or two at once, each to its own target (a skill up to 300 or a
    recipe crafted once), through `plan --prof` or saved `[goals]`. Two routes, least gold and
    least total value, with a comparison table.
  - Shopping list, mailbox trips and bring lists in whole crafts; essences packed to save slots.
  - Trainer stops on the route rows for the character's faction, with notes from play and the
    trainer groups of a capital. The route is the safe one where a trainer requirement is only
    inferred from Classic.
  - Legacy talents: Working Overtime and Dedicated Study.
  - Bags: `bag_slots`, a reagent bag (`reagent_slots`), and owned patterns.
  - Price fallbacks for players who can't reach the Blizzard API: `prices --auctionator` and
    `prices --remote`.
  - Gold and mailable items shared by the characters of one ruleset and faction; each character
    gets its own report files.
- Engineering review fixes: game data cached per pinned version, the plugin version bumped with
  every tag, stock-file mistakes named by file and key, a `lint` job, the planner split into small
  steps, the plugin moved into `plugin/` and checked by `claude plugin validate`, these entry
  documents brought up to date, and tests named after the module they test.

## Not done yet

- Not covered by the planner: gathering while levelling, keep-or-sell advice, gear. The list is in
  [coverage.md](plugin/skills/forever-professions/references/coverage.md); the open issues
  labelled `phase-2` (#48, #49) and `phase-3` hold the planned work.
- Covered since 0.2.0: budget targets, the trainer-rank rule with the recipes learned at each visit
  and the trips back for them, levelling at a remote trainer in one go, and the bag warning on bring
  lists. Open from the 0.2.1 review: #87, #90, #91 and #92; #88 (patterns on the one-go bring list)
  is closed by the 2.36 fixes.
- Merchant's Favor recipes are the Alliance ones, Blacksmithing and Enchanting only.
- Only EU has been seen to serve Forever auction data.

## Where things live

- `plugin/`: what players install (the marketplace source): the skill
  (`plugin/skills/forever-professions/`), the planner package (`plugin/yap_forever/`), the
  launcher `plugin/yap-forever.py`, the licence and [CREDITS.md](plugin/CREDITS.md).
- Repository root: the tests (`tests/`), project documents (`docs/`), the marketplace file
  (`.claude-plugin/marketplace.json`), CI (`.github/`) and the agent rules.
- A player's data: `~/.yap-forever/` on their own machine.

## How to work on it

- Read [AGENTS.md](AGENTS.md) and [docs/project-setup.md](docs/project-setup.md) first: task
  branches, pull requests, CI green before merge, tags `vX.Y.Z-<slice>`.
- Run the tests from the root: `python3 -m unittest discover -s tests -t .` (`py -3` on Windows).
  Run the command line in `plugin/` (`cd plugin`, then `python3 -m yap_forever check`).
- CI (`.github/workflows/tests.yml`) has six test jobs (Windows, macOS and Linux with Python 3.11
  and 3.13), `lint` (ruff) and `plugin` (`claude plugin validate --strict` on the marketplace and
  the plugin). The six test jobs are the checks `main` requires.
- Releases: every tag bumps the version players get (`version` in
  `plugin/.claude-plugin/plugin.json` and `__version__` in `plugin/yap_forever/__init__.py`). Run
  the skill cases in [docs/skill-checks.md](docs/skill-checks.md) before a tag.
- Keep a `.private-denylist` (untracked) with anything personal; `tests/test_publishable.py`
  checks every tracked file.
