# Xeffy Bot

Clean Python runner for Xeffy Telegram Mini App accounts.

## What This Bot Does

- Loads Pyrogram `.session` files from the `sessions/` folder.
- Also supports Pyrogram session strings through `sessions.txt`.
- Also supports Telegram WebApp `initData` through `data.txt`.
- Can join Telegram channels/groups in Full mode.
- Can run check-in and task submission.
- Can submit quiz tasks with an answer index from `answers.txt`.
- Supports optional proxy and user-agent rotation.
- Exports each run to CSV in `exports/`.

## Folder Map

| Path | Purpose |
| --- | --- |
| `xeffy_bot.py` | Main bot script |
| `setup.bat` | Installs dependencies and creates missing runtime files |
| `run.bat` | Starts the bot |
| `config.json` | Bot settings |
| `examples/` | Safe demo/template files |
| `sessions/` | Put real `.session` files here |
| `exports/` | CSV run results are saved here |

## Runtime Files

`setup.bat` creates these files in the repo root if they are missing. Real account data goes in these root files, not in `examples/`.

| File | Required? | What to add |
| --- | --- | --- |
| `.env` | Required for `.session` accounts | Telegram `API_ID` and `API_HASH` |
| `sessions.txt` | Required if using sessions | `sessions`, exact `.session` file paths, or session strings |
| `data.txt` | Optional account source | Xeffy WebApp `initData` lines |
| `channel.txt` | Optional | Telegram channel/group links for Full mode |
| `answers.txt` | Optional | Quiz answer index, for example `0` |
| `proxy.txt` | Optional | One proxy per line |
| `useragents.txt` | Optional | One browser user-agent per line |

The repo ignores real runtime files, `.session` files, proxies, exports, and `.env` so secrets are not committed.

## Quick Setup

1. Install Python 3.11.
2. Open this repo folder in CMD or PowerShell.
3. Run:

```bat
setup.bat
```

4. Open `.env` and add your Telegram API credentials:

```env
API_ID=123456
API_HASH=your_api_hash_here
```

5. Put your Pyrogram session files here:

```text
sessions/account_01.session
sessions/account_02.session
```

The default `sessions.txt` already contains:

```text
sessions
```

So the bot automatically loads every `.session` file from the `sessions/` folder.

## Account Source Options

Use at least one of these options.

### Option 1: Session Files

Recommended. Put `.session` files in:

```text
sessions/
```

Keep this line in `sessions.txt`:

```text
sessions
```

### Option 2: Exact Session File Paths

Add one exact file path per line in `sessions.txt`:

```text
sessions\account_01.session
C:\Users\YourName\Desktop\sessions\account_02.session
```

### Option 3: Pyrogram Session Strings

Add one session string per line in `sessions.txt`:

```text
1AABCD_your_pyrogram_session_string_here
```

### Option 4: WebApp initData

Add one Xeffy Telegram WebApp `initData` line per account in `data.txt`:

```text
tgWebAppData=query_id%3D...%26auth_date%3D...%26hash%3D...
```

`data.txt` accounts can check in and submit tasks, but they cannot join channels because they do not open Telegram.

## Channel Links

For Full mode, add one channel/group link per line in `channel.txt`:

```text
https://t.me/example_channel
https://t.me/example_group
```

## Quiz Answers

If Xeffy has a quiz task, add the selected answer index in `answers.txt`.

Example:

```text
0
```

Index starts from `0`, so the first answer is `0`, second answer is `1`, and so on.

## Proxy Format

Set `proxy_enabled` to `true` in `config.json`, then add proxies in `proxy.txt`.

Supported formats:

```text
ip:port
ip:port:user:pass
http://user:pass@ip:port
```

## Config

Default `config.json`:

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

Keep `threads` at `1` until your sessions and proxies are stable.

## Run

```bat
run.bat
```

Manual run:

```powershell
.\.venv\Scripts\python.exe .\xeffy_bot.py
```

Menu choices:

| Choice | Meaning |
| --- | --- |
| `1` | Run all accounts |
| `2` | Run one account |
| `3` | Start from account number |

Mode choices:

| Mode | Meaning |
| --- | --- |
| `A` | Full: join channels, check-in, tasks |
| `B` | Daily: check-in and tasks |
| `C` | Check-in only |

## Output

If `export_csv` is enabled, results are saved in:

```text
exports/
```

## Troubleshooting

### `API_ID/API_HASH missing`

Open `.env` and fill in your Telegram API credentials from `https://my.telegram.org`.

### `No accounts found`

Put `.session` files in `sessions/`, or add valid WebApp `initData` lines in `data.txt`.

### `tgcrypto` install fails on Python 3.12

Use Python 3.11. `tgcrypto==1.2.5` has a Windows wheel for Python 3.11.

### `Channel join skipped for data.txt query accounts`

This is expected. `data.txt` accounts cannot join channels because they do not open Telegram.

## Safety

Do not commit real `.session` files, session strings, `initData`, proxies, or API credentials. Treat them like passwords.
