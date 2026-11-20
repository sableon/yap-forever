# Handoff

State on 2026-11-18, end of phase 1 work (first public planner, tag `v0.1.0-planner`). Phases 2–5 are planned by the owner.

## What works

- The planner from the owner's personal project, moved into `plugin/yap_forever/` unchanged in
  behaviour: the owner's main route and an alt shopping list reproduce line for line.
- Per-player home folder `~/.yap-forever/` (`YAP_FOREVER_HOME` overrides), one command line,
  setup checks with next steps, any region and ruleset in principle (only EU tried).
- Claude Code plugin with the `forever-professions` skill; loads with `--plugin-dir plugin`.
- An independent review (2026-11-18) found ten issues; all are fixed (PRs 15–22): bank metal and
  current skills are used, a 15% buffer on yellow and green steps, prices tied to their house,
  Forever disenchanting, quest levels, realistic sales, damaged files, `migrate` flags.

## Not done yet

- Any crafting profession, one or two at once, each to its own target, plans through
  `plan --prof` (phase 2, #29); the old alt scripts are gone.
- No trainer stops on route rows, no legacy talents, Alliance trainer locations only, no gear.
- No price import for players whose network can't reach the Blizzard API.
- Only EU has been seen to serve Forever auction data.

## How to work on it

Read [AGENTS.md](AGENTS.md) and [docs/project-setup.md](docs/project-setup.md) first: task
branches, pull requests, CI green before merge, tags `vX.Y.Z-<slice>`. Run the tests with
`python3 -m unittest discover -s tests -t .` (`py -3` on Windows). Keep a `.private-denylist`
(untracked) with anything personal; `tests/test_publishable.py` checks every tracked file.
