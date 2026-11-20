## Project setup
*Recorded 2026-11-18. Answers can be changed by running `/project-setup` again; that should be rare.*

| Setting | Value | Source | Ask again when |
|---|---|---|---|
| Requirements document (BT) | The owner's private design spec `public-skill-design.md` and plan `yap-forever-phase1-plan.md` (2026-11-18), kept outside this public repo; only the file names are recorded here | asked | a phase gets its own plan or the spec is revised |
| Remote and CI | GitHub `sableon/yap-forever` (public, `origin`). GitHub Actions runs the tests on Windows, macOS and Linux with Python 3.11 and 3.13 (since PR #8) | asked | |
| Branch rules | Work on a task branch and reach `main` only by pull request; no direct commits or pushes to `main`. Once CI exists, merge only with CI green. Enforced by GitHub rulesets since 2026-11-18 (PR, six CI jobs, code-owner review; `v*` tags immutable) | asked; "CI green" derived from the spec | |
| Who merges | An agent may merge every pull request within a plan section the owner approved; outside contributors' pull requests only with the owner's OK | asked | |
| Stack | Inherited from the owner's personal planner: Python 3.11+ standard library only, `unittest` | derived | |
| Scale and deployment | Each player's own machine (Windows, macOS, Linux), installed as a Claude Code plugin; no server | derived | a hosted service is planned |
| Production authentication | None of ours: each player's own Blizzard API key in `~/.yap-forever/credentials.json` (mode 600), never read into a conversation | derived | a hosted service is planned |
| Tags | `vX.Y.Z-<slice>`, annotated with what was verified; these are the versions players see. X grows per production release, Y per major functionality change, Z per fix. First: `v0.1.0-planner` (renamed by the owner from `v0.1.0-skeleton`, 2026-11-18). Every tag bumps the version players get: the pull request before the tag sets `version` in `plugin/.claude-plugin/plugin.json` and `__version__` in `plugin/yap_forever/__init__.py` to X.Y.Z (a fixed version pins players until it changes; `tests/test_publishable.py` checks the two match and are not behind the newest tag) | default; bump rule by the owner, 2026-11-20 | |
| Verified build | After the last change of a slice: `python3 -m unittest discover -s tests -t .` passes; plus the route reproduction and the plugin install check in a fresh session once they exist; once CI exists, all its jobs green. Then a tag | default, adapted | |
| Tests without code changes | Always run the full suite, documents included: it takes under a second, and `test_no_private_details` scans every tracked file | default, adapted | the suite gets slow |
| Manual tests | Suggested after each slice, with test cases and data prepared as part of the slice, including the owner's in-game checks | default | |
| Commit identity | Repo-local `user.email` is the owner's GitHub noreply address (since 2026-11-18; earlier history keeps the personal address, owner's choice). GitHub's "keep email private" and "block pushes that expose my email" are the owner's to turn on. A test fails on a non-noreply commit after the baseline | asked | |
| Agent merge permission | Agents may merge (row above); the owner confirms in chat until a matching Claude Code permission rule exists | derived | a permission rule is added |
| Commit conventions | Conventional prefixes (`feat:`, `fix:`, `chore:`), enforced by a hook or message template, not by choosing a model | default | |
| Progress tracking | Ledger `docs/progress.md`, one line per finished task | default | another tracker is adopted |
| Lessons | A lessons pass at the end of each phase with `/recording-lessons-learned`, kept outside this repo, saved on the owner's OK | derived | |
| Diagrams | Text | default | team work or production |
| Load tests | None (local CLI) | default | a hosted service is planned |
| Customer input files | Nice to have before designing imports (for example a sample of addon saved data before the phase-2 price import); otherwise a minimal assumption | default | |
| Model and review depth | By the risk of the task, as named tiers (fast, regular, strong); each agent tool maps the tiers to its own models | default | |
| Independent review | Before each tag, one review of the whole project by a different model family or a person, given the skill's reference documents as the spec (lesson 9, 2026-11-18) | default, adapted | |
| Agent decisions | Access, personal data and money always go to the owner; here that includes credentials, the repo's settings and visibility, force-pushes, and anything owner-specific entering the repo. The agent decides the rest and lists it for veto; an agent that did not write the list filters it before the owner sees it | default, adapted | |
| Owner attention | Decisions reach the owner in batches, within the number per week set for the phase. The owner can declare a low-attention mode: agents then take only work that needs no decision | default | |
| Document size | Guide size for a slice spec and for its plan: 40 KB each. Replaced text is deleted; history stays in git | default | |
| Phase measures | Set before each phase and checked after it. Phase 1: at most 10 owner decisions per week, documents under 40 KB, cost per task measured but not capped | default | phase 2 starts |
| Entry documents | `AGENTS.md` (rules agents follow), `llms.txt` (document index), `HANDOFF.md` (for people) | fixed rule | |
| Language | English everywhere; the owner's global rule for `~/Projects/pets/` overrides the skill's fixed Russian | asked | |
