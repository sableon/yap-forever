# Security

yap-forever runs on each player's own computer. It stores the player's Battle.net API client in
`~/.yap-forever/credentials.json` (mode 600 on macOS and Linux) and a short-lived access token in
`~/.yap-forever/cache/token.json`. Nothing is sent anywhere except Blizzard's API and the pinned
game-data downloads listed in [plugin/CREDITS.md](plugin/CREDITS.md).

## Reporting a problem

If you find a way the planner or the skill could leak a player's credentials or other private
data, report it privately through **Security → Report a vulnerability** on the GitHub repository
page. Please don't open a public issue for it.

## If you posted your own credentials

If your client ID and secret ended up in an issue, a pull request or a chat, delete that client on
<https://develop.battle.net/access/clients> and create a new one, then put the new values into
`credentials.json`.
