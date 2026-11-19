# Credits and data sources

yap-forever is GPL-3.0-or-later. It downloads game data at pinned versions onto your own machine
when it first plans; none of that data is stored in this repository.

## Downloaded when you plan

| What | Source | Licence | Pinned version |
|---|---|---|---|
| Recipes, skill-up colours, trainer and vendor recipes | [cjber/skillup-forever](https://github.com/cjber/skillup-forever) (`Data/Recipes.lua`, `Thresholds.lua`, `Trainer.lua`, `Vendor.lua`), generated from WoW: Forever client tables | GPL-3.0 | commit `77337fa60453304ab0ae656466807037802435bc` |
| Quests (spec quests, quest-taught plans), profession trainers, banks, auction houses and mailboxes | [Questie/QuestieDB](https://github.com/Questie/QuestieDB) (`data/Forever/foreverQuestDB.lua`, `foreverNpcDB.lua`, `foreverObjectDB.lua`) | GPLv3 for new contributions; older content per the project's `LICENSE.md` (forks allowed under GPLv3 by the team's statement) | commit `ae4404b01a45163d3ef05909395b29aafc437bc2` |
| Items, item quality, stack sizes, tools, recipe skill lines, zone names | [wago.tools](https://wago.tools) DB2 exports of the WoW: Forever client (`ItemSparse`, `Item`, `SpellTotems`, `TotemCategory`, `SkillLineAbility`, `AreaTable`) | Blizzard Entertainment's game data | build `1.60.1.70862` |
| Auction house prices | Blizzard Battle.net API, with **your own** API client | Blizzard API terms; prices stay on your machine | live |

## Kept in this repository (`yap_forever/data_static/`)

| File | What | Source |
|---|---|---|
| `favor.toml` | Merchant's Favor recipes and crate turn-ins (Alliance, Blacksmithing and Enchanting) | method.gg Merchant's Favor guide, wowhandbook.com, foreverchanges.pro (read 2026-11-10) |
| `disenchant.toml` | Disenchanting results for green items | Classic disenchant tables, used as estimates |
| `ore.toml` | Ore, bars and the Mining skill for each | Classic data with Forever's mithril change (Mining 175) |
| `quest_plans.toml` | Blacksmithing plans learned from quests | wow-professions.com Forever Blacksmithing guide (2026-11) |
| `sources.toml` | Where gathered materials come from | maintained by hand |

Game rules in `skills/forever-professions/references/game-rules.md` come from playing WoW: Forever.

World of Warcraft and WoW: Forever are trademarks of Blizzard Entertainment. This project is not
affiliated with or endorsed by Blizzard.
