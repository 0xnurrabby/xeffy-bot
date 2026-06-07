import argparse
import asyncio
import csv
import json
import os
import random
import sqlite3
from datetime import datetime
from pathlib import Path
import urllib.parse

import requests as req
from dotenv import load_dotenv


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
    "tool_name": "Xeffy",
    "threads": 1,
    "task_enabled": True,
    "join_enabled": True,
    "checkin_enabled": True,
    "delay_between_accounts": 10,
    "repeat_enabled": False,
    "repeat_interval": 300,
    "proxy_enabled": False,
    "auto_connect_x": False,
    "connect_x_endpoint": "",
    "auto_quiz_answer": True,
    "quiz_answer_index": None,
    "export_csv": True,
    "export_excel": True,
    "export_points": True,
    "request_timeout": 30,
}

DEMO_VALUES = {
    "",
    "query",
    "initdata",
    "init_data",
    "tgwebappdata=query_id%3ddemo%26auth_date%3d1700000000%26hash%3ddemo_hash",
    "auth token|ct0",
    "auth_token|ct0",
    "ip:port",
    "ip:port:user:pass",
    "api_id=123456",
    "api_hash=your_api_hash_here",
}

X_CONNECT_ENDPOINT_CANDIDATES = [
    "/social-accounts/twitter/connect",
    "/social-accounts/x/connect",
    "/auth/twitter/connect",
    "/twitter/connect",
    "/x/connect",
    "/connect-x",
]

POINT_KEYS = {
    "point",
    "points",
    "score",
    "scores",
    "totalpoint",
    "totalpoints",
    "totalpointsamount",
    "rewardpoint",
    "rewardpoints",
    "balance",
    "xef",
}

Client = None
RequestWebView = None
PYROGRAM_IMPORT_ERROR = None


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


def as_optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_config(config):
    config["tool_name"] = str(config.get("tool_name") or "Xeffy")
    config["threads"] = as_int(config.get("threads"), 1, minimum=1, maximum=20)
    config["delay_between_accounts"] = as_int(
        config.get("delay_between_accounts"), 10, minimum=0
    )
    config["repeat_interval"] = as_int(config.get("repeat_interval"), 300, minimum=1)
    config["request_timeout"] = as_int(config.get("request_timeout"), 30, minimum=5)
    config["quiz_answer_index"] = as_optional_int(config.get("quiz_answer_index"))
    config["connect_x_endpoint"] = str(config.get("connect_x_endpoint") or "").strip()

    for key in [
        "task_enabled",
        "join_enabled",
        "checkin_enabled",
        "repeat_enabled",
        "proxy_enabled",
        "auto_connect_x",
        "auto_quiz_answer",
        "export_csv",
        "export_excel",
        "export_points",
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
        if "export_csv" not in user_config and "export_excel" in user_config:
            user_config["export_csv"] = user_config["export_excel"]
        config.update(user_config)

    return normalize_config(config)


def is_demo_value(value):
    normalized = value.strip().lower()
    return (
        normalized in DEMO_VALUES
        or "your_" in normalized
        or normalized.startswith("demo_")
    )


def load_file(path):
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]


def load_quiz_answer(config=None):
    if config:
        config_answer = as_optional_int(config.get("quiz_answer_index"))
        if config_answer is not None:
            return config_answer

    for val in load_file("answers.txt"):
        return int(val) if val.isdigit() else None

    return None


def load_session_sources(path="sessions.txt"):
    sources = []
    seen = set()
    items = load_file(path)

    if not items and Path("sessions").is_dir():
        items = ["sessions"]

    for item in items:
        if is_demo_value(item):
            continue

        item_path = Path(item).expanduser()

        if item_path.is_dir():
            candidates = sorted(item_path.glob("*.session"))
            if not candidates:
                continue
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

    if not text or is_demo_value(text):
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
            if not is_demo_value(item):
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


def extract_ref_start_param(value):
    text = value.strip()
    if not text or is_demo_value(text):
        return None

    if text.lower().startswith("/start"):
        parts = text.split(maxsplit=1)
        return parts[1].strip() if len(parts) == 2 else None

    if text.lower().startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(text)
        params = urllib.parse.parse_qs(parsed.query)
        for key in ["start", "startapp"]:
            if params.get(key):
                return params[key][0].strip() or None
        return None

    if "start=" in text or "startapp=" in text:
        params = urllib.parse.parse_qs(text.lstrip("?"))
        for key in ["start", "startapp"]:
            if params.get(key):
                return params[key][0].strip() or None

    return text


def load_ref_start_param(path="ref.txt"):
    for item in load_file(path):
        ref_start_param = extract_ref_start_param(item)
        if ref_start_param:
            return ref_start_param

    return None


def load_account_sources():
    return load_session_sources("sessions.txt") + load_query_sources("data.txt")


def parse_proxy(line):
    if is_demo_value(line):
        return None

    if "://" in line:
        proxy_url = line
    else:
        parts = line.split(":")
        if len(parts) == 4:
            host, port, username, password = parts
            if not port.isdigit():
                print(f"[WARN] Invalid proxy port skipped: {line}")
                return None
            proxy_url = f"http://{username}:{password}@{host}:{port}"
        elif len(parts) == 2:
            host, port = parts
            if not port.isdigit():
                print(f"[WARN] Invalid proxy port skipped: {line}")
                return None
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
    user_agents = [ua for ua in load_file(path) if not is_demo_value(ua)]
    return user_agents if user_agents else [DEFAULT_USER_AGENT]


def parse_x_token(line):
    if is_demo_value(line):
        return None

    parts = [part.strip() for part in line.split("|", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        print(f"[WARN] Invalid xtoken format skipped: {line[:20]}...")
        return None

    if is_demo_value(parts[0]) or is_demo_value(parts[1]):
        return None

    return {
        "raw": line,
        "auth_token": parts[0],
        "ct0": parts[1],
    }


def load_x_tokens(path="xtoken.txt"):
    tokens = []
    seen = set()
    for line in load_file(path):
        token = parse_x_token(line)
        if not token or token["raw"] in seen:
            continue
        seen.add(token["raw"])
        tokens.append(token)
    return tokens


def write_x_tokens(tokens, path="xtoken.txt"):
    with open(path, "w", encoding="utf-8") as f:
        if tokens:
            f.write("\n".join(token["raw"] for token in tokens))
            f.write("\n")
        else:
            f.write("auth token|ct0\n")


def append_connected_x_tokens(tokens, path="x_connected.txt"):
    if not tokens:
        return

    with open(path, "a", encoding="utf-8") as f:
        for token in tokens:
            f.write(f"{token['raw']}\n")


def pick_proxy(proxies, account_index, config):
    if not config.get("proxy_enabled") or not proxies:
        return None

    return proxies[(account_index - 1) % len(proxies)]


def pick_x_token(x_tokens, account_index, config):
    if not config.get("auto_connect_x") or not x_tokens:
        return None

    token_index = account_index - 1
    if token_index >= len(x_tokens):
        return None

    return x_tokens[token_index]


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


def safe_json(response):
    try:
        return response.json()
    except ValueError:
        return None


def find_value_by_keys(data, keys):
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = key.replace("_", "").replace("-", "").lower()
            if normalized in keys and value not in (None, ""):
                return value
        for value in data.values():
            found = find_value_by_keys(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_value_by_keys(item, keys)
            if found not in (None, ""):
                return found

    return None


def ensure_pyrogram():
    global Client, RequestWebView, PYROGRAM_IMPORT_ERROR

    if Client is not None and RequestWebView is not None:
        return True

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    try:
        from pyrogram import Client as PyrogramClient
        from pyrogram.raw.functions.messages import RequestWebView as PyrogramRequestWebView
    except ImportError as e:
        PYROGRAM_IMPORT_ERROR = str(e)
        return False

    Client = PyrogramClient
    RequestWebView = PyrogramRequestWebView
    return True


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

    data = safe_json(r)
    session_token = None

    if r.status_code in [200, 201]:
        for cookie in r.cookies:
            if "session_token" in cookie.name:
                session_token = cookie.value
                break

        if not session_token:
            session_token = find_value_by_keys(
                data,
                {"sessiontoken", "session", "token", "accesstoken"},
            )

        if session_token:
            return {"session_token": session_token, "data": data}

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
        data = safe_json(r) or {}
        return data.get("items", []) if isinstance(data, dict) else []

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


def build_endpoint_url(endpoint):
    endpoint = endpoint.strip()
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    return f"{BASE_URL}{endpoint}"


def x_connect_payloads(x_token):
    auth_token = x_token["auth_token"]
    ct0 = x_token["ct0"]
    return [
        {"authToken": auth_token, "ct0": ct0},
        {"auth_token": auth_token, "ct0": ct0},
        {"token": auth_token, "ct0": ct0},
        {"twitterAuthToken": auth_token, "twitterCt0": ct0},
        {"cookies": {"auth_token": auth_token, "ct0": ct0}},
    ]


def is_dead_x_response(status_code, body):
    if status_code in {401, 403}:
        return True
    text = (body or "").lower()
    return status_code == 400 and any(
        marker in text
        for marker in ["invalid", "expired", "dead", "unauthorized", "auth_token", "ct0"]
    )


def connect_x_account(session_token, x_token, user_agent, proxy, config):
    endpoints = []
    if config.get("connect_x_endpoint"):
        endpoints.append(config["connect_x_endpoint"])
    endpoints.extend(X_CONNECT_ENDPOINT_CANDIDATES)

    last_error = ""
    saw_missing_endpoint = False

    for endpoint in dict.fromkeys(endpoints):
        url = build_endpoint_url(endpoint)
        for payload in x_connect_payloads(x_token):
            try:
                r = req.post(
                    url,
                    json=payload,
                    headers=make_headers(session_token, user_agent),
                    proxies=proxy,
                    timeout=config["request_timeout"],
                )
            except req.RequestException as e:
                last_error = str(e)
                continue

            if r.status_code in [200, 201]:
                return {"status": "connected", "message": endpoint}

            if r.status_code in {404, 405}:
                saw_missing_endpoint = True
                last_error = f"{endpoint}: {r.status_code}"
                break

            if is_dead_x_response(r.status_code, r.text):
                return {"status": "dead", "message": r.text[:120]}

            last_error = f"{endpoint}: {r.status_code} {r.text[:120]}"

    if saw_missing_endpoint and not last_error:
        return {"status": "endpoint_not_found", "message": "No X endpoint found"}

    if saw_missing_endpoint:
        return {"status": "endpoint_not_found", "message": last_error}

    return {"status": "failed", "message": last_error or "Unknown X connect failure"}


def get_account_stats(session_token, user_agent, proxy, config):
    endpoints = [
        "/me",
        "/users/me",
        "/members/me",
        "/profile",
        "/be-auth/me",
        f"/campaigns/{CAMPAIGN_ID}/me",
        f"/campaigns/{CAMPAIGN_ID}/profile",
        f"/campaigns/{CAMPAIGN_ID}/summary",
        f"/campaigns/{CAMPAIGN_ID}/leaderboard/me",
    ]

    for endpoint in endpoints:
        try:
            r = req.get(
                build_endpoint_url(endpoint),
                headers=make_headers(session_token, user_agent),
                proxies=proxy,
                timeout=config["request_timeout"],
            )
        except req.RequestException:
            continue

        if r.status_code == 200:
            data = safe_json(r)
            if data:
                return data

    return None


def extract_points(*objects):
    for data in objects:
        value = find_value_by_keys(data, POINT_KEYS)
        if value in (None, ""):
            continue
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            cleaned = value.replace(",", "").strip()
            try:
                return int(cleaned) if cleaned.isdigit() else float(cleaned)
            except ValueError:
                continue
    return ""


def describe_account_source(source):
    if source["type"] == "file":
        return f"{source['name']}.session"
    if source["type"] == "query":
        return source["name"]

    return "session_string"


def validate_pyrogram_session_file(source):
    if source["type"] != "file":
        return None

    session_path = Path(source["workdir"]) / f"{source['name']}.session"
    if not session_path.exists():
        return f"session file not found: {session_path}"

    try:
        conn = sqlite3.connect(f"file:{session_path}?mode=ro", uri=True)
    except sqlite3.Error as e:
        return f"cannot open session sqlite database: {e}"

    try:
        version_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(version)").fetchall()
        }
        session_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
    except sqlite3.Error as e:
        return f"cannot inspect session database: {e}"
    finally:
        conn.close()

    if "number" not in version_columns:
        return (
            "invalid Pyrogram session format: missing version.number column. "
            "This usually means the file was made by Telethon, an older Pyrogram, "
            "or another bot. Use a Pyrogram v2 .session file, Pyrogram session "
            "string, or data.txt query instead."
        )

    required_session_columns = {"dc_id", "api_id", "auth_key", "user_id"}
    missing = sorted(required_session_columns - session_columns)
    if missing:
        return (
            "invalid Pyrogram session format: missing sessions column(s): "
            f"{', '.join(missing)}"
        )

    return None


def build_result(account_index, source):
    return {
        "account_number": account_index,
        "source": describe_account_source(source),
        "telegram_user": "",
        "telegram_id": "",
        "login": "no",
        "x_connect": "skipped",
        "checkin": "skipped",
        "tasks_found": 0,
        "tasks_submitted": 0,
        "tasks_failed": 0,
        "points": "",
        "status": "started",
        "error": "",
        "_x_token_raw": "",
    }


async def apply_referral(app, account_index, ref_start_param):
    if not ref_start_param:
        return

    try:
        await app.send_message(BOT_USERNAME, f"/start {ref_start_param}")
        print(f"[Account {account_index}] [OK] Referral applied: {ref_start_param}")
        await asyncio.sleep(1)
    except Exception as e:
        print(f"[Account {account_index}] [WARN] Referral start failed: {e}")


async def get_init_data(app, account_index, ref_start_param=None):
    bot_peer = await app.resolve_peer(BOT_USERNAME)
    request_kwargs = {
        "peer": bot_peer,
        "bot": bot_peer,
        "platform": "android",
        "url": "https://tg.go.xeffy.io/",
    }

    if ref_start_param:
        request_kwargs["start_param"] = ref_start_param

    web_view = await app.invoke(
        RequestWebView(**request_kwargs)
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


def iter_nested(data):
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from iter_nested(value)
    elif isinstance(data, list):
        yield data
        for item in data:
            yield from iter_nested(item)


def infer_quiz_answer(task):
    index_keys = {
        "correctindex",
        "correctanswerindex",
        "answerindex",
        "quizanswerindex",
        "quizselectedindex",
    }
    correct_flags = {"correct", "iscorrect", "isright", "right"}

    for item in iter_nested(task):
        if isinstance(item, dict):
            for key, value in item.items():
                normalized = key.replace("_", "").replace("-", "").lower()
                if normalized in index_keys:
                    answer = as_optional_int(value)
                    if answer is not None:
                        return answer

    for item in iter_nested(task):
        if not isinstance(item, dict):
            continue

        for options_key in ["options", "answers", "choices"]:
            options = item.get(options_key)
            if not isinstance(options, list):
                continue

            for index, option in enumerate(options):
                if not isinstance(option, dict):
                    continue
                for key, value in option.items():
                    normalized = key.replace("_", "").replace("-", "").lower()
                    if normalized in correct_flags and as_bool(value, False):
                        return index

    return None


def build_quiz_proof(task, config):
    answer_index = None
    if config.get("auto_quiz_answer", True):
        answer_index = infer_quiz_answer(task)

    if answer_index is None:
        answer_index = load_quiz_answer(config)

    if answer_index is None:
        return None

    return {"quizSelectedIndex": answer_index}


def is_quiz_task(task):
    task_kind = str(task.get("kind", "")).lower()
    task_name = str(task.get("name", "")).lower()
    return "quiz" in task_kind or "quiz" in task_name


async def run_account(
    source,
    index,
    tele_links,
    mode,
    config,
    proxy,
    user_agent,
    x_token,
    ref_start_param,
):
    result = build_result(index, source)

    print(f"\n{'=' * 50}")
    print(f"[Account {index}] Starting...")

    init_data = None

    if source["type"] == "query":
        init_data = source["init_data"]
        result["telegram_user"] = source["name"]
        print(f"[Account {index}] WebApp query from data.txt")
        if ref_start_param:
            print(
                f"[Account {index}] [WARN] Referral cannot be applied to data.txt accounts; "
                "capture initData with the referral link instead."
            )
        if mode == "full" and tele_links and config.get("join_enabled", True):
            print(f"[Account {index}] [WARN] Channel join skipped for data.txt query accounts")
    else:
        if not ensure_pyrogram():
            result["status"] = "failed"
            result["error"] = f"pyrogram is not installed: {PYROGRAM_IMPORT_ERROR}"
            print("[FAIL] Pyrogram is not installed. Run setup.bat first.")
            return result

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
            session_error = validate_pyrogram_session_file(source)
            if session_error:
                result["status"] = "failed"
                result["error"] = session_error
                print(f"[Account {index}] [FAIL] {session_error}")
                return result

            client_kwargs["name"] = source["name"]
            client_kwargs["workdir"] = source["workdir"]
            print(f"[Account {index}] Session file: {source['name']}.session")
        else:
            client_kwargs["name"] = f"acc_{index}"
            client_kwargs["session_string"] = source["value"]
            client_kwargs["in_memory"] = True
            print(f"[Account {index}] Session string")

        try:
            async with Client(**client_kwargs) as app:
                me = await app.get_me()
                username = f"@{me.username}" if me.username else "(no username)"
                result["telegram_user"] = username
                result["telegram_id"] = str(me.id)
                print(f"[Account {index}] {username} ({me.id})")

                await apply_referral(app, index, ref_start_param)

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

                init_data = await get_init_data(app, index, ref_start_param)
                if not init_data:
                    result["status"] = "failed"
                    result["error"] = "missing initData"
                    return result

                print(f"[Account {index}] [OK] initData received")
        except sqlite3.Error as e:
            result["status"] = "failed"
            result["error"] = f"session sqlite error: {e}"
            print(f"[Account {index}] [FAIL] Session sqlite error: {e}")
            return result

    if proxy:
        print(f"[Account {index}] HTTP proxy enabled")

    print(f"[Account {index}] Logging in to Xeffy...")
    login = await asyncio.to_thread(
        xeffy_login,
        init_data,
        user_agent,
        proxy,
        config,
    )
    if not login:
        print(f"[Account {index}] [FAIL] Xeffy login failed")
        result["status"] = "failed"
        result["error"] = "xeffy login failed"
        return result

    session_token = login["session_token"]
    result["login"] = "yes"
    result["points"] = extract_points(login.get("data"))
    print(f"[Account {index}] [OK] Xeffy login successful")

    if config.get("auto_connect_x") and x_token:
        result["_x_token_raw"] = x_token["raw"]
        print(f"[Account {index}] Connecting X account...")
        x_result = await asyncio.to_thread(
            connect_x_account,
            session_token,
            x_token,
            user_agent,
            proxy,
            config,
        )
        result["x_connect"] = x_result["status"]
        if x_result["status"] == "connected":
            print(f"[Account {index}] [OK] X connected")
        elif x_result["status"] == "dead":
            print(f"[Account {index}] [WARN] X token is invalid/dead")
        else:
            print(f"[Account {index}] [WARN] X connect skipped: {x_result['message']}")
    elif config.get("auto_connect_x"):
        print(f"[Account {index}] [WARN] auto_connect_x enabled but no xtoken available")

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
        if config.get("export_points", True):
            stats = await asyncio.to_thread(
                get_account_stats,
                session_token,
                user_agent,
                proxy,
                config,
            )
            result["points"] = extract_points(stats, login.get("data"))
        print(f"[Account {index}] Done")
        return result

    await asyncio.sleep(2)

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
        can_submit = task.get("canSubmit", False)

        if not task_id or not can_submit:
            continue

        if is_quiz_task(task):
            proof = build_quiz_proof(task, config)
            if proof is None:
                print(f"[Account {index}] [WARN] Skipping quiz; no answer found: {task_name}")
                continue
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

    if config.get("export_points", True):
        stats = await asyncio.to_thread(
            get_account_stats,
            session_token,
            user_agent,
            proxy,
            config,
        )
        result["points"] = extract_points(stats, login.get("data"))

    result["status"] = "done"
    print(f"[Account {index}] Done")
    return result


async def run_account_safe(
    source,
    index,
    tele_links,
    mode,
    config,
    proxies,
    user_agents,
    x_tokens,
    ref_start_param,
):
    proxy = pick_proxy(proxies, index, config)
    user_agent = pick_user_agent(user_agents)
    x_token = pick_x_token(x_tokens, index, config)

    try:
        return await run_account(
            source,
            index,
            tele_links,
            mode,
            config,
            proxy,
            user_agent,
            x_token,
            ref_start_param,
        )
    except Exception as e:
        print(f"[Account {index}] [FAIL] Unexpected error: {e}")
        result = build_result(index, source)
        result["status"] = "failed"
        result["error"] = str(e)
        if x_token:
            result["_x_token_raw"] = x_token["raw"]
        return result


def export_results(results, path):
    if not results:
        return

    export_path = Path(path)
    export_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [key for key in results[0].keys() if not key.startswith("_")]
    with open(export_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    print(f"\n[OK] Exported CSV: {export_path}")


def update_xtoken_files(results, x_tokens):
    if not x_tokens:
        return

    connected_raw = {
        row.get("_x_token_raw")
        for row in results
        if row.get("_x_token_raw") and row.get("x_connect") == "connected"
    }
    dead_raw = {
        row.get("_x_token_raw")
        for row in results
        if row.get("_x_token_raw") and row.get("x_connect") == "dead"
    }
    remove_raw = connected_raw | dead_raw

    if not remove_raw:
        return

    connected_tokens = [token for token in x_tokens if token["raw"] in connected_raw]
    remaining_tokens = [token for token in x_tokens if token["raw"] not in remove_raw]

    append_connected_x_tokens(connected_tokens)
    write_x_tokens(remaining_tokens)
    print(f"[OK] Updated xtoken.txt. Removed {len(remove_raw)} used/dead token(s).")


def build_export_path():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("exports") / f"xeffy_run_{stamp}.csv"


def safe_thread_count(config, selected_count):
    return min(config["threads"], selected_count, 20)


async def run_selected_accounts(
    accounts,
    indices,
    tele_links,
    mode,
    config,
    proxies,
    user_agents,
    x_tokens,
    ref_start_param,
):
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
                    x_tokens,
                    ref_start_param,
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
                x_tokens,
                ref_start_param,
            )

    return await asyncio.gather(*(limited_run(i) for i in indices))


def print_menu(total, channel_count, query_count, proxy_count, x_token_count, ref_start_param, config):
    print()
    print("=" * 42)
    print(config.get("tool_name", "XEFFY BOT").upper())
    print("=" * 42)
    print(f"Detected accounts : {total}")
    print(f"data.txt queries  : {query_count}")
    print(f"Channel links     : {channel_count}")
    print(f"Proxy entries     : {proxy_count}")
    print(f"X token entries   : {x_token_count}")
    print(f"Referral          : {ref_start_param or 'none'}")
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

    try:
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
    except ValueError:
        print("Invalid number.")
        return []

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


def select_indices(total, selection=None, account_number=None):
    if not selection:
        return choose_indices(total)

    if selection == "all":
        return list(range(total))

    if selection == "one":
        idx = (account_number or 1) - 1
        if idx < 0 or idx >= total:
            print("Invalid account number.")
            return []
        return [idx]

    if selection == "start":
        start = (account_number or 1) - 1
        if start < 0 or start >= total:
            print("Invalid start account number.")
            return []
        return list(range(start, total))

    print("Invalid account selection.")
    return []


async def main(selection=None, mode=None, account_number=None):
    config = load_config()
    accounts = load_account_sources()
    query_count = len([source for source in accounts if source["type"] == "query"])
    tele_links = load_file("channel.txt")
    proxies = load_proxies("proxy.txt")
    user_agents = load_user_agents("useragents.txt")
    x_tokens = load_x_tokens("xtoken.txt")
    ref_start_param = load_ref_start_param("ref.txt")
    total = len(accounts)

    print_menu(
        total,
        len(tele_links),
        query_count,
        len(proxies),
        len(x_tokens),
        ref_start_param,
        config,
    )

    if total == 0:
        print("No accounts found. Check sessions.txt or data.txt.")
        return

    indices = select_indices(total, selection, account_number)
    if not indices:
        return

    if not mode:
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
            x_tokens,
            ref_start_param,
        )

        if config.get("export_csv", True):
            export_results(results, build_export_path())

        update_xtoken_files(results, x_tokens)
        print("\nAll selected accounts are finished.")

        if not config.get("repeat_enabled"):
            break

        print(f"Repeat mode enabled. Waiting {config['repeat_interval']} second(s)...")
        await asyncio.sleep(config["repeat_interval"])


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Run the Xeffy bot.")
    parser.add_argument(
        "--accounts",
        choices=["all", "one", "start"],
        help="Account selection. Omit this to use the interactive menu.",
    )
    parser.add_argument(
        "--account-number",
        type=int,
        default=1,
        help="Account number for --accounts one/start. Starts at 1.",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "daily", "checkin"],
        help="Run mode. Omit this to use the interactive menu.",
    )
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    asyncio.run(main(args.accounts, args.mode, args.account_number))
