# Skill checks before a tag

CI checks the manifests and the skill's frontmatter on every push (`claude plugin validate
--strict`, the `plugin` job). It can't check what Claude does with the skill. These four cases
do; they make real model calls, so they are run by hand before a tag, not in CI.

## Before the tag: bump the version

The pull request before a tag sets the new `X.Y.Z` in both `plugin/.claude-plugin/plugin.json`
(`version`) and `plugin/yap_forever/__init__.py` (`__version__`). Without it, players who installed
an earlier version never get the new one, and a `v*` tag can't be moved or deleted afterwards.
`tests/test_publishable.py` checks that the two match and are not behind the newest tag.

## Before the tag: the first run after an update

Players update from the previous tag, so check that a home folder it used still works with the new
`main`. Use a scratch home, so your own stays as it is:

```
export YAP_FOREVER_HOME="$HOME/.yap-update-check"
rm -rf "$YAP_FOREVER_HOME" && mkdir -p "$YAP_FOREVER_HOME" && cp -R ~/.yap-forever/. "$YAP_FOREVER_HOME"/
git worktree add ../yap-prev <previous tag>
```

- Run one `plan` for a character with the previous tag, in its package folder (`../yap-prev` for
  `v0.1.0-*`, `../yap-prev/plugin` after), then the same `plan` with the new `main` from `plugin/`.
- **Must happen:** the new `plan` runs with no step by hand, downloads the new game data once and
  removes the old copy, and ends with no traceback. Its guide and report match the previous tag's,
  unless a pull request since then says what changes.
- Every "Outside the repo" section in the pull requests since the previous tag is checked here too:
  for the price command on a server, the folder it runs in still holds the package.
- Afterwards: `git worktree remove ../yap-prev` and `rm -rf "$YAP_FOREVER_HOME"`.

## Set up a clean install

Use a separate Claude Code folder and a separate player home, so your own setup and files stay as
they are. In a terminal (macOS or Linux; on Windows use `$env:NAME = "..."` in PowerShell):

```
export CLAUDE_CONFIG_DIR="$HOME/.claude-skill-check"   # a Claude Code with no other plugins
export YAP_FOREVER_HOME="$HOME/.yap-skill-check"       # the player home the planner uses
claude plugin marketplace add sableon/yap-forever#BRANCH   # before the merge; after it: sableon/yap-forever
claude plugin install yap-forever@yap-forever
find "$CLAUDE_CONFIG_DIR/plugins" -name yap-forever.py
```

The installed folder (the one `find` prints) must hold only `.claude-plugin/`, `CREDITS.md`,
`LICENSE`, `skills/`, `yap-forever.py` and `yap_forever/`: no `tests/` or `docs/`.

Then start a session in an empty folder: `mkdir -p ~/yap-check && cd ~/yap-check && claude`. Log
in if it asks. Start a new session (`/clear` is not enough) for each case, and set up the player
home as the case says before you start it.

Afterwards: `rm -rf "$HOME/.claude-skill-check" "$HOME/.yap-skill-check" ~/yap-check`.

## What every case must show

- The skill loads (Claude names it or follows its steps).
- Every planner command has the form `<python> "<installed folder>/yap-forever.py" <command>`,
  with the installed folder as an absolute path. No `cd` before it, no `-m yap_forever`, and no
  search for the plugin folder (`find`, `ls`, guessing "two folders above").
- No permission prompt for a planner command in the turn that loads the skill. A prompt in a later
  turn is expected: the skill's `allowed-tools` last only for the turn that invokes it. Prompts to
  edit files in the player home are expected too.
- Claude never opens, prints or asks for `credentials.json` or the API secret.
- Claude never works out a route, count or cost itself: the numbers come from `plan`.

## 1. First setup

- **Starting state:** the player home doesn't exist (`rm -rf "$YAP_FOREVER_HOME"`).
- **Prompt:** "Plan my WoW Forever Blacksmithing to 150."
- **Must happen:**
  - Claude runs `check --offline`, sees the `MISSING` lines and runs `init`.
  - It asks for the region, ruleset, faction, the character's two-word name and Favor standing,
    one step at a time (setup step 2), and fills in `profile.toml` with the answers.
  - It explains how to create the Blizzard API client and has the player paste the ID and secret
    into `credentials.json` themselves (setup step 3).
  - It explains the marker listing for finding the auction house (setup step 4) and doesn't run
    `plan` before `check` says the setup is done or a price fallback is in use.

## 2. A plan for one profession

- **Starting state:** a working home, copied from your own (the copy stays on your machine):
  `mkdir -p "$YAP_FOREVER_HOME" && cp -R ~/.yap-forever/. "$YAP_FOREVER_HOME"/`, with prices less
  than an hour old.
- **Prompt:** "Plan Blacksmithing to 150 for <a character in the profile>."
- **Must happen:**
  - Claude asks what changed: level, skills, Favor standing, free bag slots, what has piled up,
    and gold once for the character's ruleset and faction (not per character). It saves the
    answers in `stock.toml` and `[gold]` in `profile.toml`.
  - It asks the goal (150 is given, so it confirms it) and, with no Enchanting in the plan,
    whether green crafts are kept to disenchant on another character or sold (`keep_greens`).
  - It runs `prices`, then `plan --character "<name>" --prof blacksmithing:150`.
  - It shows the comparison table, explains least gold and least total value in a sentence each
    (or says they are the same route), and asks which guide to follow.

## 3. Prices that can't be downloaded

- **Starting state:** the home from case 2, with `client_id` and `client_secret` in
  `credentials.json` left empty and no `cache/prices.json`. Your `Auctionator.lua` from a recent
  scan is on this machine.
- **Prompt:** "The Blizzard API times out on my network, so prices won't download. I use
  Auctionator. Plan my Blacksmithing to 150."
- **Must happen:**
  - Claude offers the two fallbacks (setup step 5) and doesn't ask for the marker listing or the
    API client (setup step 4 says to skip them).
  - It asks for the path to `Auctionator.lua` (or the game folder) instead of searching the disk
    or guessing the account folder, and runs `prices --auctionator "<PATH>"`.
  - It tells the player what an import can't give (one price per item, no listing depth), and
    asks for a new scan if the guide header says the scan is old.
  - `plan` runs on the imported prices.

## 4. A second character of the same group

- **Starting state:** the home from case 2, with two characters on the same ruleset and faction
  in the profile, both with a `stock.toml`, and a `[gold]` entry for the group.
- **Prompt:** "Now plan Tailoring to 75 for <the other character>."
- **Must happen:**
  - Claude doesn't ask for gold per character: it confirms the group's `[gold]` figure once.
  - It asks the player to keep the first character's `stock.toml` up to date, and says that two
    plans may count the same mailed items.
  - The plan runs, the reports are named for this character, and the first character's reports
    are still there.
