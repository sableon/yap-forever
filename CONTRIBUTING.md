# Contributing to yap-forever

**Active development is paused since 2026-11-25:** issues and pull requests may wait a long time for an
answer. For profession levelling, use the [SkillUp Forever](https://github.com/cjber/skillup-forever)
addon instead.

Thanks for helping. yap-forever is a Claude Code skill plus a small local Python planner for
WoW: Forever professions. This page says what a good contribution looks like. The rules agents
follow are in [AGENTS.md](AGENTS.md); they apply to people too.

## Before you start

- **Bugs and wrong game data:** open an issue with the matching template. For game data (Favor
  recipes, disenchanting, trainers, talents), say what you saw in game: item or recipe IDs, your
  skill, and a screenshot if you have one.
- **Changes to how the skill works** (`plugin/skills/forever-professions/`), to the game rules it
  states, or to the data in `plugin/yap_forever/data_static/`: open an issue first and agree the change
  with the maintainer. These parts need the maintainer's review (see `.github/CODEOWNERS`).
- **Never paste your Battle.net client ID or secret**, your `credentials.json`, or anything from
  your `~/.yap-forever/` folder that you don't want public.

## How the project is built

- The skill (`SKILL.md` and its references) tells Claude what to ask and which command to run;
  the planner (`plugin/yap_forever/`) does the maths. Keep that split: game knowledge the planner uses
  lives in data files or code with tests, and the skill explains it in words.
- Python 3.11 or newer, standard library only, tests with `unittest`. No new dependencies.
- Windows, macOS and Linux: open text files with `encoding="utf-8"` (a test checks this), and use
  `pathlib` paths.
- English for code, documents, commits and pull requests.

## Making a change

1. Fork, then work on a branch. Pull requests go to `main`.
2. Write the test first, then the change. Run the whole suite:

   ```
   python3 -m unittest discover -s tests -t .
   ```

   (`py -3` instead of `python3` on Windows.) It takes a couple of seconds. CI also runs the linter;
   to run it yourself, install ruff (a developer tool, version 0.17.6 as in CI) and run
   `ruff check plugin tests`.
3. **Planner changes:** run `plan` before and after your change on a real character (in a copy of
   your home folder: set `YAP_FOREVER_HOME`) and say in the pull request what changed in the guide.
   If nothing changed on real data, say so.
4. **Test data uses made-up values:** invented character names, invented auction house IDs. Never
   your own characters, realm, house or email. `tests/test_publishable.py` scans every tracked
   file for private details.
5. **New data from another project:** add it to [plugin/CREDITS.md](plugin/CREDITS.md) with its source, version
   and licence. A test checks that every source is credited.
6. Commit messages start with `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `ci:` or `chore:`.
7. Don't edit `docs/progress.md`; the maintainer adds a line for your change when it is merged.

CI runs the suite on Windows, macOS and Linux with Python 3.11 and 3.13. A first pull request from
a new contributor waits for the maintainer to approve the CI run.

## Licence

yap-forever is GPL-3.0-or-later. By contributing you agree that your contribution is licensed
under the same terms.
