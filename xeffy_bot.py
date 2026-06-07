import asyncio
import csv
import json
import os
import random
from datetime import datetime
from pathlib import Path
import urllib.parse

import requests as req
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.raw.functions.messages import RequestWebView


load_dotenv()

BOT_USERNAME = "Xeffy_Bot"
ORG_SLUG = "xeffy"
CAMPAIGN_ID = "447eb124-e731-4853-be60-39aae9bb0127"
BASE_URL = "https://api.go.xeffy.io/api/mini"

API_ID = int(os.getenv("API_ID", "0") or "0")
API_HASH = os.getenv("API_HASH", "")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

DEFAULT_CONFIG = {
    "threads": 1,
    "task_enabled": True,
    "join_enabled": True,
    "checkin_enabled": True,
    "delay_between_accounts": 10,
    "repeat_enabled": False,
    "repeat_interval": 300,
    "proxy_enabled": False,
    "export_csv": True,
    "request_timeout": 30,
}


def as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def as_int(value, default, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default

    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)

    return number


def normalize_config(config):
    config["threads"] = as_int(config.get("threads"), 1, minimum=1, maximum=20)
    config["delay_between_accounts"] = as_int(
        config.get("delay_between_accounts"), 10, minimum=0
    )
    config["repeat_interval"] = as_int(config.get("repeat_interval"), 300, minimum=1)
    config["request_timeout"] = as_int(config.get("request_timeout"), 30, minimum=5)

    for key in [
        "task_enabled",
        "join_enabled",
        "checkin_enabled",
        "repeat_enabled",
        "proxy_enabled",
        "export_csv",
    ]:
        config[key] = as_bool(config.get(key), DEFAULT_CONFIG[key])

    return config


def load_config(path="config.json"):
    config = DEFAULT_CONFIG.copy()

    if not os.path.exists(path):
        return normalize_config(config)

    try:
        with open(path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[WARN] Could not read {path}: {e}")
        return normalize_config(config)

    if isinstance(user_config, dict):
        config.update(user_config)

    return normalize_config(config)


def load_file(path):
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def load_quiz_answer():
    for val in load_file("answers.txt"):
        return int(val) if val.isdigit() else None

    return None


def load_session_sources(path="sessions.txt"):
    sources = []
    seen = set()

    for item in load_file(path):
        item_path = Path(item).expanduser()

        if item_path.is_dir():
            candidates = sorted(item_path.glob("*.session"))
        elif item_path.is_file() and item_path.suffix == ".session":
            candidates = [item_path]
        else:
            candidates = []

        if candidates:
            for session_file in candidates:
                key = str(session_file.resolve()).lower()
                if key in seen:
                    continue

                seen.add(key)
                sources.append(
                    {
                        "type": "file",
                        "name": session_file.stem,
                        "workdir": str(session_file.parent),
                    }
                )
            continue

        if item not in seen:
            seen.add(item)
            sources.append(
                {
                    "type": "string",
                    "value": item,
                }
            )

    return sources


def extract_init_data(value):
    text = value.strip()

    if not text or text.lower() in {"query", "initdata", "init_data"}:
        return None

    if "#" in text:
        fragment = text.split("#", 1)[1]
    elif "?" in text and text.lower().startswith(("http://", "https://")):
        fragment = text.split("?", 1)[1]
    else:
        fragment = text

    if "tgWebAppData=" in fragment:
        params = urllib.parse.parse_qs(fragment)
        tg_web_app_data = params.get("tgWebAppData", [None])[0]
        if not tg_web_app_data:
            return None
        return urllib.parse.unquote(tg_web_app_data)

    decoded = urllib.parse.unquote(fragment)
    if "auth_date=" in decoded and "hash=" in decoded:
        return decoded

    return None


def load_query_sources(path="data.txt"):
    sources = []
    seen = set()

    for item in load_file(path):
        init_data = extract_init_data(item)
        if not init_data:
            print(f"[WARN] Skipping invalid data.txt line: {item[:60]}")
            continue

        if init_data in seen:
            continue

        seen.add(init_data)
        sources.append(
            {
                "type": "query",
                "name": f"data_{len(sources) + 1}",
                "init_data": init_data,
            }
        )

    return sources


def load_account_sources():
    return load_session_sources("sessions.txt") + load_query_sources("data.txt")


def parse_proxy(line):
    if "://" in line:
        proxy_url = line
    else:
        parts = line.split(":")
        if len(parts) == 4:
            host, port, username, password = parts
            proxy_url = f"http://{username}:{password}@{host}:{port}"
        elif len(parts) == 2:
            host, port = parts
            proxy_url = f"http://{host}:{port}"
        else:
            print(f"[WARN] Invalid proxy format skipped: {line}")
            return None

    return {"http": proxy_url, "https": proxy_url}


def load_proxies(path="proxy.txt"):
    proxies = []
    for line in load_file(path):
        proxy = parse_proxy(line)
        if proxy:
            proxies.append(proxy)

    return proxies


def load_user_agents(path="useragents.txt"):
    user_agents = load_file(path)
    return user_agents if user_agents else [DEFAULT_USER_AGENT]


def pick_proxy(proxies, account_index, config):
    if not config.get("proxy_enabled") or not proxies:
        return None

    return proxies[(account_index - 1) % len(proxies)]


def pick_user_agent(user_agents):
    return random.choice(user_agents) if user_agents else DEFAULT_USER_AGENT


def make_headers(session_token=None, user_agent=None):
    headers = {
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://tg.go.xeffy.io",
        "Referer": "https://tg.go.xeffy.io/",
    }

    if session_token:
        headers["Cookie"] = f"__Secure-xeffy_contrib.session_token={session_token}"

    return headers


def xeffy_login(init_data, user_agent, proxy, config):
    try:
        r = req.post(
            f"{BASE_URL}/be-auth/sign-in/telegram",
            json={"initData": init_data, "orgSlug": ORG_SLUG},
            headers=make_headers(user_agent=user_agent),
            proxies=proxy,
            timeout=config["request_timeout"],
        )
    except req.RequestException as e:
        print(f"  Login request failed: {e}")
        return None

    if r.status_code in [200, 201]:
        for cookie in r.cookies:
            if "session_token" in cookie.name:
                return cookie.value

    print(f"  Login failed: {r.status_code} | {r.text[:150]}")
    return None


def check_in(session_token, user_agent, proxy, config):
    try:
        r = req.post(
            f"{BASE_URL}/attendance",
            headers=make_headers(session_token, user_agent),
            proxies=proxy,
            timeout=config["request_timeout"],
        )
    except req.RequestException as e:
        print(f"  Check-in request failed: {e}")
        return False

    return r.status_code in [200, 201]


def get_tasks(session_token, user_agent, proxy, config):
    try:
        r = req.get(
            f"{BASE_URL}/campaigns/{CAMPAIGN_ID}/tasks",
            headers=make_headers(session_token, user_agent),
            proxies=proxy,
            timeout=config["request_timeout"],
        )
    except req.RequestException as e:
        print(f"  Task request failed: {e}")
        return []

    if r.status_code == 200:
        return r.json().get("items", [])

    print(f"  Task request failed: {r.status_code} | {r.text[:150]}")
    return []


def submit_task(session_token, task_id, proof, user_agent, proxy, config):
    try:
        r = req.post(
            f"{BASE_URL}/submissions",
            json={"taskId": task_id, "proof": proof or {}},
            headers=make_headers(session_token, user_agent),
            proxies=proxy,
            timeout=config["request_timeout"],
        )
    except req.RequestException as e:
        print(f"  Submit request failed: {e}")
        return False

    return r.status_code in [200, 201]


def describe_account_source(source):
    if source["type"] == "file":
        return f"{source['name']}.session"
    if source["type"] == "query":
        return source["name"]

    return "session_string"


def build_result(account_index, source):
    return {
        "account_number": account_index,
        "source": describe_account_source(source),
        "telegram_user": "",
        "telegram_id": "",
        "login": "no",
        "checkin": "skipped",
        "tasks_found": 0,
        "tasks_submitted": 0,
        "tasks_failed": 0,
        "status": "started",
        "error": "",
    }


async def get_init_data(app, account_index):
    bot_peer = await app.resolve_peer(BOT_USERNAME)
    web_view = await app.invoke(
        RequestWebView(
            peer=bot_peer,
            bot=bot_peer,
            platform="android",
            url="https://tg.go.xeffy.io/",
        )
    )

    url = web_view.url
    if "#" in url:
        fragment = url.split("#", 1)[1]
    elif "?" in url:
        fragment = url.split("?", 1)[1]
    else:
        print(f"[Account {account_index}] [FAIL] WebView URL has no query data")
        return None

    return extract_init_data(fragment)


async def run_account(source, index, tele_links, mode, config, proxy, user_agent):
    result = build_result(index, source)

    print(f"\n{'=' * 50}")
    print(f"[Account {index}] Starting...")

    init_data = None

    if source["type"] == "query":
        init_data = source["init_data"]
        result["telegram_user"] = source["name"]
        print(f"[Account {index}] WebApp query from data.txt")
        if mode == "full" and tele_links and config.get("join_enabled", True):
            print(f"[Account {index}] [WARN] Channel join skipped for data.txt query accounts")
    else:
        if API_ID == 0 or not API_HASH:
            result["status"] = "failed"
            result["error"] = "missing API_ID/API_HASH"
            print("[FAIL] API_ID/API_HASH missing. Create .env from .env.example.")
            return result

        client_kwargs = {
            "api_id": API_ID,
            "api_hash": API_HASH,
        }

        if source["type"] == "file":
            client_kwargs["name"] = source["name"]
            client_kwargs["workdir"] = source["workdir"]
            print(f"[Account {index}] Session file: {source['name']}.session")
        else:
            client_kwargs["name"] = f"acc_{index}"
            client_kwargs["session_string"] = source["value"]
            client_kwargs["in_memory"] = True
            print(f"[Account {index}] Session string")

        async with Client(**client_kwargs) as app:
            me = await app.get_me()
            username = f"@{me.username}" if me.username else "(no username)"
            result["telegram_user"] = username
            result["telegram_id"] = str(me.id)
            print(f"[Account {index}] {username} ({me.id})")

            if mode == "full" and tele_links and config.get("join_enabled", True):
                print(f"[Account {index}] Joining {len(tele_links)} channel/group link(s)...")
                for link in tele_links:
                    try:
                        chat_username = (
                            link.replace("https://t.me/", "")
                            .replace("http://t.me/", "")
                            .replace("t.me/", "")
                            .strip("/")
                        )
                        await app.join_chat(chat_username)
                        print(f"[Account {index}] [OK] Joined: {chat_username}")
                    except Exception as e:
                        print(f"[Account {index}] [WARN] Join failed for {link}: {e}")

                    await asyncio.sleep(2)

            init_data = await get_init_data(app, index)
            if not init_data:
                result["status"] = "failed"
                result["error"] = "missing initData"
                return result

            print(f"[Account {index}] [OK] initData received")

    if proxy:
        print(f"[Account {index}] HTTP proxy enabled")

    print(f"[Account {index}] Logging in to Xeffy...")
    session_token = await asyncio.to_thread(
        xeffy_login,
        init_data,
        user_agent,
        proxy,
        config,
    )
    if not session_token:
        print(f"[Account {index}] [FAIL] Xeffy login failed")
        result["status"] = "failed"
        result["error"] = "xeffy login failed"
        return result

    result["login"] = "yes"
    print(f"[Account {index}] [OK] Xeffy login successful")

    if config.get("checkin_enabled", True):
        ok = await asyncio.to_thread(
            check_in,
            session_token,
            user_agent,
            proxy,
            config,
        )
        if ok:
            result["checkin"] = "ok"
            print(f"[Account {index}] [OK] Check-in complete")
        else:
            result["checkin"] = "failed_or_done"
            print(f"[Account {index}] [WARN] Check-in failed or already completed")

    if mode == "checkin" or not config.get("task_enabled", True):
        result["status"] = "done"
        print(f"[Account {index}] Done")
        return result

    await asyncio.sleep(2)

    quiz_answer = load_quiz_answer()
    tasks = await asyncio.to_thread(
        get_tasks,
        session_token,
        user_agent,
        proxy,
        config,
    )
    result["tasks_found"] = len(tasks)
    print(f"[Account {index}] Found {len(tasks)} task(s)")

    for task in tasks:
        task_id = task.get("id")
        task_name = task.get("name", "unknown")
        task_kind = task.get("kind", "")
        can_submit = task.get("canSubmit", False)

        if not can_submit:
            continue

        if task_kind == "quiz":
            if quiz_answer is None:
                print(f"[Account {index}] [WARN] Skipping quiz; answers.txt is empty: {task_name}")
                continue
            proof = {"quizSelectedIndex": quiz_answer}
        else:
            proof = {}

        ok = await asyncio.to_thread(
            submit_task,
            session_token,
            task_id,
            proof,
            user_agent,
            proxy,
            config,
        )
        if ok:
            result["tasks_submitted"] += 1
            print(f"[Account {index}] [OK] {task_name}")
        else:
            result["tasks_failed"] += 1
            print(f"[Account {index}] [FAIL] {task_name}")

        await asyncio.sleep(1)

    result["status"] = "done"
    print(f"[Account {index}] Done")
    return result


async def run_account_safe(source, index, tele_links, mode, config, proxies, user_agents):
    proxy = pick_proxy(proxies, index, config)
    user_agent = pick_user_agent(user_agents)

    try:
        return await run_account(source, index, tele_links, mode, config, proxy, user_agent)
    except Exception as e:
        print(f"[Account {index}] [FAIL] Unexpected error: {e}")
        result = build_result(index, source)
        result["status"] = "failed"
        result["error"] = str(e)
        return result


def export_results(results, path):
    if not results:
        return

    export_path = Path(path)
    export_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(results[0].keys())
    with open(export_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n[OK] Exported CSV: {export_path}")


def build_export_path():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("exports") / f"xeffy_run_{stamp}.csv"


def safe_thread_count(config, selected_count):
    return min(config["threads"], selected_count, 20)


async def run_selected_accounts(accounts, indices, tele_links, mode, config, proxies, user_agents):
    if not indices:
        return []

    workers = safe_thread_count(config, len(indices))
    print(f"\nWorker count: {workers}")

    if workers == 1:
        results = []
        for pos, i in enumerate(indices):
            results.append(
                await run_account_safe(
                    accounts[i],
                    i + 1,
                    tele_links,
                    mode,
                    config,
                    proxies,
                    user_agents,
                )
            )
            if pos != len(indices) - 1:
                print(f"\nWaiting {config['delay_between_accounts']} second(s)...")
                await asyncio.sleep(config["delay_between_accounts"])

        return results

    semaphore = asyncio.Semaphore(workers)

    async def limited_run(i):
        async with semaphore:
            return await run_account_safe(
                accounts[i],
                i + 1,
                tele_links,
                mode,
                config,
                proxies,
                user_agents,
            )

    return await asyncio.gather(*(limited_run(i) for i in indices))


def print_menu(total, channel_count, query_count, proxy_count, config):
    print()
    print("=" * 42)
    print("XEFFY BOT")
    print("=" * 42)
    print(f"Detected accounts : {total}")
    print(f"data.txt queries  : {query_count}")
    print(f"Channel links     : {channel_count}")
    print(f"Proxy entries     : {proxy_count}")
    print(f"Worker threads    : {config['threads']}")
    print("-" * 42)
    print("Account selection")
    print("1. Run all accounts")
    print("2. Run one account")
    print("3. Start from account number")
    print("-" * 42)
    print("Mode")
    print("A. Full: join channels + check-in + tasks")
    print("B. Daily: check-in + tasks")
    print("C. Check-in only")
    print("=" * 42)


def choose_indices(total):
    choice = input("\nChoose accounts (1/2/3): ").strip()

    if choice == "1":
        return list(range(total))

    if choice == "2":
        idx = int(input(f"Choose account number (1-{total}): ")) - 1
        if idx < 0 or idx >= total:
            print("Invalid account number.")
            return []
        return [idx]

    if choice == "3":
        start = int(input(f"Start from account number (1-{total}): ")) - 1
        if start < 0 or start >= total:
            print("Invalid start account number.")
            return []
        return list(range(start, total))

    print("Invalid account choice.")
    return []


def choose_mode():
    mode_input = input("Choose mode (A/B/C): ").strip().upper()
    if mode_input == "A":
        return "full"
    if mode_input == "B":
        return "daily"
    if mode_input == "C":
        return "checkin"

    print("Invalid mode.")
    return None


async def main():
    config = load_config()
    accounts = load_account_sources()
    query_count = len([source for source in accounts if source["type"] == "query"])
    tele_links = load_file("channel.txt")
    proxies = load_proxies("proxy.txt")
    user_agents = load_user_agents("useragents.txt")
    total = len(accounts)

    print_menu(total, len(tele_links), query_count, len(proxies), config)

    if total == 0:
        print("No accounts found. Check sessions.txt or data.txt.")
        return

    indices = choose_indices(total)
    if not indices:
        return

    mode = choose_mode()
    if not mode:
        return

    while True:
        results = await run_selected_accounts(
            accounts,
            indices,
            tele_links,
            mode,
            config,
            proxies,
            user_agents,
        )

        if config.get("export_csv", True):
            export_results(results, build_export_path())

        print("\nAll selected accounts are finished.")

        if not config.get("repeat_enabled"):
            break

        print(f"Repeat mode enabled. Waiting {config['repeat_interval']} second(s)...")
        await asyncio.sleep(config["repeat_interval"])


if __name__ == "__main__":
    asyncio.run(main())
