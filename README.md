# Xeffy Bot

Clean Python runner for Xeffy Telegram Mini App accounts.

It supports:

- Pyrogram `.session` files
- Pyrogram session strings
- Hana-style `data.txt` WebApp query/initData lines
- optional channel join in Full mode
- check-in and task submission
- optional quiz answer index
- optional proxy and user-agent rotation
- CSV export after each run
- repeat mode

## Safety Notes

Do not commit real account data. The repo ignores `sessions.txt`, `data.txt`, `.env`, `.session` files, proxies, and exports by default.

Session files, session strings, WebApp query data, proxies, and API credentials are sensitive. Treat them like passwords.

The Hana GitHub package ships a compiled `main.exe`. This repo does not include it. Use the auditable Python script here.

## Requirements

- Windows
- Python 3.11 recommended
- Telegram API ID and API hash from `https://my.telegram.org`

## Install

Open PowerShell or CMD in the repo folder, then run:

```bat
setup.bat
```

Manual install:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Configure

Create `.env` from `.env.example`:

```env
API_ID=123456
API_HASH=your_api_hash_here
```

Create your runtime files from the examples:

```powershell
copy sessions.example.txt sessions.txt
copy data.example.txt data.txt
copy channel.example.txt channel.txt
copy answers.example.txt answers.txt
copy proxy.example.txt proxy.txt
copy useragents.example.txt useragents.txt
```

You only need one account source:

- use `sessions.txt` for `.session` files/folders/session strings
- use `data.txt` for WebApp query/initData lines

## sessions.txt

Folder path:

```txt
C:\path\to\sessions
```

Specific `.session` file:

```txt
C:\path\to\sessions\acc_123.session
```

Pyrogram session string:

```txt
1AABCD_your_account_session_string
```

One line equals one source. Folder paths auto-load every `.session` file in that folder.

## data.txt

`data.txt` accepts Hana-style Telegram WebApp data:

```txt
tgWebAppData=query_id%3D...%26auth_date%3D...%26hash%3D...
```

It also accepts decoded initData containing `auth_date=` and `hash=`.

Query-only accounts can check in and submit tasks, but cannot join channels because they do not open Telegram.

## channel.txt

Optional. Used only in Full mode:

```txt
https://t.me/example_channel
```

## answers.txt

Optional quiz answer index:

```txt
0
```

## config.json

```json
{
  "threads": 1,
  "task_enabled": true,
  "join_enabled": true,
  "checkin_enabled": true,
  "delay_between_accounts": 10,
  "repeat_enabled": false,
  "repeat_interval": 300,
  "proxy_enabled": false,
  "export_csv": true,
  "request_timeout": 30
}
```

Recommended: keep `threads` as `1` until you know your accounts and proxies are stable.

## Run

```bat
run.bat
```

Manual:

```powershell
.\.venv\Scripts\python.exe .\xeffy_bot.py
```

Menu:

- `1` run all accounts
- `2` run one account
- `3` start from account number

Modes:

- `A` Full: join channels, check-in, tasks
- `B` Daily: check-in and tasks
- `C` Check-in only

## Output

If `export_csv` is enabled, results are saved in:

```txt
exports/
```

## Troubleshooting

`API_ID/API_HASH missing`

Create `.env` from `.env.example` and fill your Telegram API credentials.

`No accounts found`

Create either `sessions.txt` or `data.txt` from the example files and add real account data.

`tgcrypto` install fails on Python 3.12`

Use Python 3.11. `tgcrypto==1.2.5` has a Windows wheel for Python 3.11.

`Channel join skipped for data.txt query accounts`

This is expected. `data.txt` query accounts do not open Telegram, so they cannot join channels.
