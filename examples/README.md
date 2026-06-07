# Example Runtime Files

These files are safe templates. `setup.bat` copies them to the repo root only when the real runtime file is missing.

| Template | Runtime file | What to put there |
| --- | --- | --- |
| `.env.example` | `.env` | Telegram `API_ID` and `API_HASH` |
| `sessions.example.txt` | `sessions.txt` | `sessions` folder path, exact `.session` file paths, or Pyrogram session strings |
| `data.example.txt` | `data.txt` | Xeffy Telegram WebApp `initData` lines |
| `channel.example.txt` | `channel.txt` | Telegram channel/group links for Full mode |
| `answers.example.txt` | `answers.txt` | Quiz answer index, such as `0` |
| `proxy.example.txt` | `proxy.txt` | Optional proxies |
| `useragents.example.txt` | `useragents.txt` | Optional browser user agents |

Do not put real account data in this `examples` folder.
