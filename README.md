# Xeffy Bot

Auditable Python version of the Xeffy Telegram Mini App runner. The public HanaPromax repo ships the real runner as a compiled `main.exe`; this repo keeps the workflow readable and editable.

## Files

| File/folder | What goes here |
| --- | --- |
| `.env.example` | Demo Telegram `API_ID` and `API_HASH`. `setup.bat` copies it to `.env` if missing. |
| `sessions/` | Put real Pyrogram `.session` files here. |
| `sessions.txt` | `sessions` folder path, exact `.session` paths, or Pyrogram session strings. |
| `data.txt` | Telegram WebApp `query` / `tgWebAppData` / decoded `initData`. |
| `ref.txt` | Optional Telegram referral link or start parameter. |
| `proxy.txt` | Proxies. Upstream format: `ip:port:user:pass`. |
| `xtoken.txt` | Optional X/Twitter token lines. Upstream format: `auth token|ct0`. |
| `useragents.txt` | Optional browser user-agent rotation. |
| `channel.txt` | Optional Telegram channel/group links for Full mode. |
| `answers.txt` | Optional fallback quiz answer index. |
| `config.json` | Threads and feature toggles. |
| `exports/` | CSV result files. |
| `xeffy_bot.py` | CLI bot. |
| `web_gui.py` / `gui.bat` | Local browser control panel. |

The root text files already contain demo placeholders, so you can see the exact format directly in each file.

## Setup

Install Python 3.11 or newer, then run:

```bat
setup.bat
```

If setup cannot create `.venv`, install Python from `https://www.python.org/downloads/` and tick `Add python.exe to PATH` during install.

Open `.env` and replace the demo values:

```env
API_ID=123456
API_HASH=your_api_hash_here
```

Get these from `https://my.telegram.org`.

## Account Input

Use at least one account source.

Session files:

```text
sessions/account_01.session
sessions/account_02.session
```

Keep this active line in `sessions.txt`:

```text
sessions
```

WebApp query data:

```text
tgWebAppData=query_id%3D...%26auth_date%3D...%26hash%3D...
```

`data.txt` accounts can check in and submit tasks, but cannot join channels.

## Referral Link

Put your referral link in `ref.txt`:

```text
https://t.me/Xeffy_Bot?start=ref_5005957731
```

For session accounts, the bot sends `/start ref_...` and passes the same value as Mini App `start_param`. For `data.txt` accounts, capture the WebApp query/initData using the referral link first.

## X Connect

Set this in `config.json`:

```json
"auto_connect_x": true
```

Then put one token per line in `xtoken.txt`:

```text
auth_token_value|ct0_value
```

Connected tokens are moved to `x_connected.txt`. Invalid/dead tokens are removed from `xtoken.txt`.

If Xeffy changes the endpoint, set `connect_x_endpoint` in `config.json`.

## Run

CLI:

```bat
run.bat
```

Local web GUI:

```bat
gui.bat
```

Then open:

```text
http://127.0.0.1:8787
```

The GUI can edit root files, save config, start/stop the bot, and show live logs.

## Modes

| Mode | Work |
| --- | --- |
| Full | Join channels, check-in, tasks |
| Daily | Check-in and tasks |
| Check-in | Check-in only |

## Config

Important settings:

```json
{
  "threads": 1,
  "task_enabled": true,
  "join_enabled": true,
  "checkin_enabled": true,
  "proxy_enabled": false,
  "auto_connect_x": false,
  "auto_quiz_answer": true,
  "export_csv": true,
  "export_points": true
}
```

Keep `threads` at `1` until your sessions/proxies are stable.

## Safety

Do not commit real `.session` files, `.env`, real `initData`, proxies, or X tokens. Treat them like passwords.

## Session Error

`no such column: number` means the `.session` file is not a Pyrogram v2 session database. It may be from Telethon, another bot, an older Pyrogram version, or a corrupt file.

Use one of these instead:

- a fresh Pyrogram v2 `.session` file
- a Pyrogram session string in `sessions.txt`
- a valid Xeffy WebApp query/initData line in `data.txt`
