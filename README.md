# Xeffy Bot

Xeffy Bot is a readable Python runner for the Xeffy Telegram Mini App workflow. It can log in with Telegram session files or captured WebApp initData, run daily check-in, join configured Telegram channels, submit available tasks, connect an X account when a token is provided, and export results after each run.

This repository is meant to be easy to audit and edit. The upstream public runner ships as a compiled executable, while this version keeps the logic in Python files so you can see how accounts, X tokens, quiz answers, and exports are handled.

## Quick Start

Install Python 3.11 or newer first. On Windows, run `setup.bat` from this folder. The setup script creates `.venv`, installs the packages from `requirements.txt`, and copies `.env.example` to `.env` if `.env` does not exist yet.

Open `.env` and put your Telegram API credentials:

```env
API_ID=123456
API_HASH=your_api_hash_here
```

You can get `API_ID` and `API_HASH` from `https://my.telegram.org`. Without these values, session-file login cannot work.

After setup, run the CLI with:

```bat
run.bat
```

You can also use the local web control panel:

```bat
gui.bat
```

Then open:

```text
http://127.0.0.1:8787
```

## Main Files

`xeffy_bot.py` is the main CLI bot. It loads accounts, logs in to Xeffy, connects X when enabled, runs check-in, submits tasks, answers quizzes, exports results, and updates token files.

`web_gui.py` starts the local browser control panel. The GUI can edit the root text files, save config, start or stop the bot, and show live logs.

The GUI dashboard shows quick stats from the latest export, including total accounts, total points, submitted tasks, skipped tasks, failed tasks, finished accounts, and X connected count. If no export exists yet, account stats fall back to the configured session files.

`xeffy_x_tools.py` is a helper for X connection troubleshooting. It can check whether a Telegram/Xeffy account currently has X connected and can call the unlink endpoint for that same account.

The root `.txt` files are simple input files. Each non-empty line is used as one item, and lines starting with `#` are ignored.

## Telegram Accounts

Use either session files or WebApp query/initData. Session files are better for full mode because they can open the Telegram Mini App and join Telegram channels. `data.txt` query accounts can check in and submit tasks, but they cannot join channels.

Put `.session` files inside `sessions/`. Pyrogram v2 session files run directly. Telethon session files are auto-converted into `.converted_sessions/` at runtime, and the original files in `sessions/` are not modified.

The safest account layout is explicit numbering. Rename your Telegram session files like this:

```text
sessions/1.session
sessions/2.session
sessions/3.session
sessions/4.session
sessions/5.session
```

Then write the same order in `sessions.txt`:

```text
sessions/1.session
sessions/2.session
sessions/3.session
sessions/4.session
sessions/5.session
```

This removes sorting confusion. If `sessions.txt` only contains `sessions`, the bot loads all `.session` files in sorted filename order. That can be confusing when names like `1.session`, `2.session`, and `10.session` are mixed.

## X Token Mapping

When `auto_connect_x` is enabled, the bot maps the session filename number to the same X token line number. For example, `sessions/1.session` uses line 1 from `xtoken.txt`, `sessions/2.session` uses line 2, and `sessions/11.session` uses line 11. If a session file is not named with a number, the bot falls back to the account's run number.

Example:

```text
sessions/1.session  -> xtoken.txt line 1
sessions/2.session  -> xtoken.txt line 2
sessions/11.session -> xtoken.txt line 11
```

Write `xtoken.txt` in the same order:

```text
auth_token_for_1|ct0_for_1
auth_token_for_2|ct0_for_2
auth_token_for_3|ct0_for_3
...
auth_token_for_11|ct0_for_11
```

Keep a private note if you manage many accounts:

```text
1 | sessions/1.session | TG: @telegram1 | X: @xuser1 | xtoken line 1
2 | sessions/2.session | TG: @telegram2 | X: @xuser2 | xtoken line 2
3 | sessions/3.session | TG: @telegram3 | X: @xuser3 | xtoken line 3
```

By default, `xtoken.txt` line mapping is preserved. The bot does not rewrite `xtoken.txt` after a run, because removing connected or dead tokens shifts the line numbers and breaks the Telegram-to-X mapping. Keep every account's token on its matching line.

If Xeffy says an X account is already linked to another Xeffy user, the current Telegram account cannot disconnect it because the current account has no linked X identity. You must either run unlink from the old Telegram/Xeffy account that owns that X link, or replace the token with a fresh X account that was not linked before.

After every run, the bot writes a local `tg_x_mapping.csv` file. This file shows account number, Telegram username, Telegram ID, session/data source, X token line, X connect status, whether the token was actually used, and the assigned X token. It is useful for checking exactly which Telegram account was paired with which X token. Because it contains private tokens, it is ignored by Git and should stay local.

Twitter/X tasks are only submitted after the bot verifies that the Mini App itself reports an X identity for that Telegram account. If the Mini App says X is not connected and a matching token exists, the bot tries to connect X before the first X task. If no matching token exists, the log shows the exact `xtoken.txt` line that must contain `auth_token|ct0`. The bot also performs best-effort X actions for supported tasks before submitting them: follow, like, retweet, and reply.

## X Check And Unlink Helper

Use this command to check whether a Telegram/Xeffy account has X connected:

```bat
.venv\Scripts\python.exe xeffy_x_tools.py check --account-number 1
```

Use this command to unlink X from that same Telegram/Xeffy account:

```bat
.venv\Scripts\python.exe xeffy_x_tools.py unlink --account-number 1
```

Unlink only works when the selected Telegram account is the account that currently owns the X link. If the account is not connected, Xeffy returns `ACCOUNT_NOT_FOUND`.

## Quiz Answers

For quiz tasks the bot reads `answers.txt`. The recommended and most reliable way to answer is to put the **option number** exactly as it is shown in the app. The number is 1-based: `1` is the first option, `2` is the second option, and so on.

Example: the quiz shows

```text
1. Meko | Xeffy
2. Charlie | Xeffy
3. Eric | Xeffy
```

If the correct answer is `Charlie | Xeffy` (the second option), put:

```text
2
```

The bot converts that to the 0-based value the API expects and submits `quizSelectedIndex: 1`. The number method works even when the option text is not included in the task response, which is why it is preferred. When the run starts you will see a line such as `[QUIZ] Xeffy Daily Quiz -> option #2: Charlie | Xeffy` so you can confirm the right option was picked.

You can still put the exact option text instead of a number (case and extra spaces are ignored, but there is no fuzzy guessing):

```text
Charlie | Xeffy
```

Answer resolution order: the option number in `answers.txt` (or `quiz_answer_index` in `config.json`, also 1-based) is used first, then an exact text match, then any correct-answer hint the task response happens to expose (`auto_quiz_answer`).

## Referral

Put a referral link or start parameter in `ref.txt`:

```text
https://t.me/Xeffy_Bot?start=ref_5005957731
```

For session-file accounts, the bot sends `/start ref_...` and passes the same value as the Mini App start parameter. For `data.txt` accounts, capture the WebApp query/initData using the referral link first.

## Modes

Full mode joins Telegram channel/group links from `channel.txt`, runs check-in, and submits tasks.

Daily mode runs check-in and submits tasks, but it does not join channels.

Check-in mode only runs daily check-in. It is useful when you want to test account login without submitting tasks.

## Config

Important settings live in `config.json`:

```json
{
  "threads": 1,
  "task_enabled": true,
  "join_enabled": true,
  "checkin_enabled": true,
  "proxy_enabled": false,
  "auto_connect_x": true,
  "auto_quiz_answer": true,
  "export_csv": true,
  "export_points": true
}
```

Keep `threads` at `1` until your sessions, proxies, and X token order are confirmed. After everything is stable, you can increase it carefully.

## Proxies And User Agents

Put proxies in `proxy.txt` if `proxy_enabled` is true. Supported formats are:

```text
ip:port
ip:port:user:pass
http://user:pass@ip:port
```

Put browser user agents in `useragents.txt` if you want rotation. If the file is empty or only contains placeholders, the bot uses a default Android Chrome user agent.

## Exports

Run results are written to `exports/` when export is enabled. The export includes account number, source, Telegram user, login status, X connect status, check-in status, task counts, points, final status, and error message.

## Session Errors

`missing version.number column` or `no such column: number` usually means the `.session` file is not a Pyrogram v2 session database. Telethon sessions are supported and converted automatically when possible. If conversion fails, the session is probably expired, logged out, corrupt, or made by another library.

If a session is already Pyrogram-compatible, the bot uses it directly and no converted copy is needed. If a session is Telethon, the bot creates a Pyrogram-compatible copy inside `.converted_sessions/` and leaves the original file untouched. You can delete `.converted_sessions/`; the bot will recreate what it needs on the next run.

Use one of these instead:

```text
a fresh Pyrogram v2 session file
a fresh Telethon session file
a Pyrogram session string in sessions.txt
a valid Xeffy WebApp query/initData line in data.txt
```

## Safety

Do not commit real `.session` files, `.env`, real initData, proxies, or X tokens. Treat them like passwords. Anyone with these values may be able to access your accounts.

The repository ignores session files, converted sessions, virtualenv files, exports, connected-token files, and common binary archives. Keep your private runtime files local.
