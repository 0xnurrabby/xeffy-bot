import argparse
import asyncio
import csv
import hashlib
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
MINI_APP_SHORTNAME = "xeffy_app"
ORG_SLUG = "xeffy"
CAMPAIGN_ID = "447eb124-e731-4853-be60-39aae9bb0127"
BASE_URL = "https://api.go.xeffy.io/api/mini"
CONVERTED_SESSION_DIR = Path(".converted_sessions")
PYROGRAM_SESSION_VERSION = 3
X_OAUTH_AUTHORIZE_URL = "https://api.x.com/2/oauth2/authorize"
X_WEB_BEARER = (
    "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

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
    "preserve_x_token_lines": True,
    "connect_x_endpoint": "",
    "auto_quiz_answer": True,
    "quiz_answer_index": None,
    "x_task_actions": True,
    "x_reply_text": "Great update",
    "x_action_delay": 2,
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

POINT_KEYS = {
    "point",
    "points",
    "score",
    "scores",
    "totalpoint",
    "totalpoints",
    "totalpointamount",
    "totalpointsamount",
    "totalscore",
    "pointsamount",
    "pointamount",
    "rewardpoint",
    "rewardpoints",
    "balance",
    "xp",
    "totalxp",
    "xef",
    "totalxef",
    "xefpoints",
}

# Keys used to dig a numeric value out of a nested points object such as
# {"points": {"total": 1234}} or {"points": {"amount": 1234}}.
POINT_NESTED_KEYS = {
    "total",
    "amount",
    "value",
    "count",
    "current",
    "balance",
    "points",
    "point",
}

X_TASK_KINDS = {
    "twitter_post",
    "twitter_retweet",
    "twitter_reply",
    "twitter_quote",
    "twitter_follow",
    "twitter_like",
}

X_TASK_TEXT_MARKERS = {
    "twitter",
    "x.com",
    "retweet",
    "tweet",
    "quote tweet",
    "x account",
    "x post",
}

X_IDENTITY_KEYS = {
    "screenname",
    "provideruserid",
    "providerusername",
    "socialuserid",
    "twitterid",
    "twitterusername",
    "xid",
    "xusername",
}

X_IDENTITY_CONTAINER_KEYS = {
    "data",
    "identity",
    "xidentity",
    "twitteridentity",
    "account",
    "profile",
    "user",
    "social",
}

X_IDENTITY_PROVIDER_KEYS = {
    "provider",
    "providerid",
    "platform",
    "network",
    "socialplatform",
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
    config["x_action_delay"] = as_int(config.get("x_action_delay"), 2, minimum=0)
    config["quiz_answer_index"] = as_optional_int(config.get("quiz_answer_index"))
    config["connect_x_endpoint"] = str(config.get("connect_x_endpoint") or "").strip()
    config["x_reply_text"] = str(config.get("x_reply_text") or "Great update").strip()

    for key in [
        "task_enabled",
        "join_enabled",
        "checkin_enabled",
        "repeat_enabled",
        "proxy_enabled",
        "auto_connect_x",
        "preserve_x_token_lines",
        "auto_quiz_answer",
        "x_task_actions",
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


def numeric_stem(value):
    stem = Path(str(value)).stem
    return int(stem) if stem.isdigit() else None


def session_sort_key(path):
    number = numeric_stem(path)
    if number is not None:
        return (0, number, str(path).lower())
    return (1, str(path).lower())


def quiz_number_to_index(value):
    """Convert a manual answer number into a 0-based quiz option index.

    The number is the option position as it appears in the app (1 = first
    option, 2 = second option, ...). The API expects a 0-based index, so we
    subtract one. ``0`` is kept as the first option for backward compatibility.
    """
    number = as_optional_int(value)
    if number is None:
        return None
    return number - 1 if number >= 1 else 0


def load_quiz_answer(config=None):
    if config:
        config_index = quiz_number_to_index(config.get("quiz_answer_index"))
        if config_index is not None:
            return config_index

    for val in load_file("answers.txt"):
        index = quiz_number_to_index(val)
        if index is not None:
            return index

    return None


def load_quiz_answer_lines(path="answers.txt"):
    return load_file(path)


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
            candidates = sorted(item_path.glob("*.session"), key=session_sort_key)
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


def extract_telegram_from_init_data(init_data):
    params = urllib.parse.parse_qs(init_data or "")
    raw_user = params.get("user", [""])[0]
    if not raw_user:
        return "", ""

    try:
        user = json.loads(raw_user)
    except (TypeError, ValueError):
        return "", ""

    username = str(user.get("username") or "").strip()
    telegram_id = str(user.get("id") or "").strip()
    first_name = str(user.get("first_name") or "").strip()
    last_name = str(user.get("last_name") or "").strip()
    display_name = " ".join(part for part in [first_name, last_name] if part)

    if username:
        return f"@{username}", telegram_id
    return display_name, telegram_id


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
    if not os.path.exists(path):
        return tokens

    with open(path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            token = parse_x_token(line)
            if not token or token["raw"] in seen:
                if token and token["raw"] in seen:
                    print(f"[WARN] Duplicate X token skipped at xtoken.txt line {line_number}")
                continue
            token["line"] = line_number
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


def expected_x_token_line(source, account_index):
    if source and source.get("type") == "file":
        number = numeric_stem(source.get("name", ""))
        if number is not None:
            return number
    return account_index


def pick_x_token(x_tokens, account_index, config, source=None):
    if not x_tokens:
        return None

    if config.get("preserve_x_token_lines", True):
        expected_line = expected_x_token_line(source, account_index)
        for token in x_tokens:
            if token.get("line") == expected_line:
                return token
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


def normalize_key(key):
    return str(key).replace("_", "").replace("-", "").lower()


def find_value_by_keys(data, keys):
    normalized_keys = {normalize_key(key) for key in keys}
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = normalize_key(key)
            if normalized in normalized_keys and value not in (None, ""):
                return value
        for value in data.values():
            found = find_value_by_keys(value, normalized_keys)
            if found not in (None, ""):
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_value_by_keys(item, normalized_keys)
            if found not in (None, ""):
                return found

    return None


def response_error_summary(response):
    data = safe_json(response)
    message = find_value_by_keys(data, {"message", "code", "error"})
    if isinstance(message, dict):
        message = find_value_by_keys(message, {"message", "code"})
    if isinstance(message, list):
        message = ", ".join(str(item) for item in message if item)

    if message:
        return f"{response.status_code} {message}"

    text = (response.text or "").strip()
    return f"{response.status_code} {text[:120]}".strip()


def has_meaningful_value(value):
    if value in (None, "", False):
        return False
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


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
        return False, str(e)

    if r.status_code in [200, 201]:
        return True, ""

    return False, response_error_summary(r)


def build_endpoint_url(endpoint):
    endpoint = endpoint.strip()
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    return f"{BASE_URL}{endpoint}"


def is_dead_x_response(status_code, body):
    if status_code in {401, 403}:
        return True
    text = (body or "").lower()
    return status_code in {400, 422} and any(
        marker in text
        for marker in [
            "invalid",
            "expired",
            "dead",
            "unauthorized",
            "auth_token",
            "ct0",
            "could not authenticate",
        ]
    )


def xeffy_session_headers(session_token, user_agent, json_body=True):
    headers = make_headers(session_token, user_agent)
    if not json_body:
        headers.pop("Content-Type", None)
    return headers


def make_xeffy_web_session(session_token):
    session = req.Session()
    session.cookies.set(
        "__Secure-xeffy_contrib.session_token",
        session_token,
        domain="api.go.xeffy.io",
        path="/",
    )
    return session


def extract_x_identity(data):
    if not data:
        return None

    if isinstance(data, list):
        for item in data:
            identity = extract_x_identity(item)
            if identity:
                return identity
        return None

    if not isinstance(data, dict):
        return None

    provider = find_value_by_keys(data, X_IDENTITY_PROVIDER_KEYS)
    if provider and str(provider).strip().lower() in {"twitter", "x"}:
        return data

    for key, value in data.items():
        normalized = normalize_key(key)
        if normalized in X_IDENTITY_KEYS and has_meaningful_value(value):
            return data

    for key, value in data.items():
        normalized = normalize_key(key)
        if normalized in X_IDENTITY_CONTAINER_KEYS:
            identity = extract_x_identity(value)
            if identity:
                return identity

    return None


def get_x_identity(web_session, session_token, user_agent, proxy, config):
    try:
        r = web_session.get(
            f"{BASE_URL}/registrations/x-identity",
            headers=xeffy_session_headers(session_token, user_agent, json_body=False),
            proxies=proxy,
            timeout=config["request_timeout"],
        )
    except req.RequestException as e:
        return None, f"x-identity request failed: {e}"

    if r.status_code == 204:
        return None, None
    if r.status_code != 200:
        return None, f"x-identity: {response_error_summary(r)}"

    data = safe_json(r)
    return extract_x_identity(data), None


def x_identity_connected(web_session, session_token, user_agent, proxy, config):
    identity, _ = get_x_identity(web_session, session_token, user_agent, proxy, config)
    return bool(identity)


def check_x_identity(session_token, user_agent, proxy, config):
    web_session = make_xeffy_web_session(session_token)
    return get_x_identity(web_session, None, user_agent, proxy, config)


def format_x_identity(identity):
    if not identity:
        return ""

    handle = find_value_by_keys(
        identity,
        {
            "screenname",
            "screen_name",
            "username",
            "handle",
            "providerusername",
            "twitterusername",
            "xusername",
        },
    )
    user_id = find_value_by_keys(
        identity,
        {"userid", "provideruserid", "socialuserid", "twitterid", "xid", "id"},
    )

    if handle:
        handle = str(handle).strip()
        if handle and not handle.startswith("@"):
            handle = f"@{handle}"
        return f"{handle} ({user_id})" if user_id else handle

    return str(user_id or "")


def prepare_x_link(web_session, session_token, user_agent, proxy, config):
    r = web_session.post(
        f"{BASE_URL}/registrations/x-link-prepare",
        json={},
        headers=xeffy_session_headers(session_token, user_agent),
        proxies=proxy,
        timeout=config["request_timeout"],
    )
    if r.status_code not in [200, 201]:
        return None, f"x-link-prepare: {r.status_code} {r.text[:120]}"

    data = safe_json(r) or {}
    code = data.get("code")
    if not code:
        return None, "x-link-prepare: missing code"

    return code, None


def create_x_oauth_url(web_session, session_token, user_agent, proxy, config, link_code):
    mini_app_path = f"{BOT_USERNAME}/{MINI_APP_SHORTNAME}" if MINI_APP_SHORTNAME else BOT_USERNAME
    callback_url = f"https://t.me/{mini_app_path}?startapp=xlink_{link_code}"
    error_callback_url = f"https://t.me/{mini_app_path}?startapp=xerr_{link_code}"

    r = web_session.post(
        f"{BASE_URL}/be-auth/link-social",
        json={
            "provider": "twitter",
            "callbackURL": callback_url,
            "errorCallbackURL": error_callback_url,
            "disableRedirect": True,
        },
        headers=xeffy_session_headers(session_token, user_agent),
        proxies=proxy,
        timeout=config["request_timeout"],
    )
    if r.status_code not in [200, 201]:
        return None, f"link-social: {r.status_code} {r.text[:120]}"

    data = safe_json(r) or {}
    oauth_url = data.get("url")
    if not oauth_url:
        return None, "link-social: missing oauth url"

    return oauth_url, None


def make_x_session(x_token):
    session = req.Session()
    for domain in [".x.com", ".twitter.com", "x.com", "twitter.com"]:
        session.cookies.set("auth_token", x_token["auth_token"], domain=domain)
        session.cookies.set("ct0", x_token["ct0"], domain=domain)
    return session


def x_api_headers(x_token, user_agent, oauth_url):
    return {
        "authorization": X_WEB_BEARER,
        "x-csrf-token": x_token["ct0"],
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "x-twitter-active-user": "yes",
        "user-agent": user_agent or DEFAULT_USER_AGENT,
        "accept": "application/json, text/plain, */*",
        "origin": "https://x.com",
        "referer": oauth_url,
    }


def x_form_headers(x_token, user_agent, referer):
    headers = x_api_headers(x_token, user_agent, referer)
    headers["content-type"] = "application/x-www-form-urlencoded"
    return headers


def parse_x_target(url):
    if not url:
        return None, None

    parsed = urllib.parse.urlparse(str(url).strip())
    path_parts = [part for part in parsed.path.split("/") if part]
    handle = path_parts[0].lstrip("@") if path_parts else None
    tweet_id = None
    for index, part in enumerate(path_parts):
        if part.lower() in {"status", "statuses"} and index + 1 < len(path_parts):
            candidate = path_parts[index + 1]
            if candidate.isdigit():
                tweet_id = candidate
                break

    return handle, tweet_id


def x_action_ok(response):
    if response.status_code in {200, 201, 204}:
        return True

    text = (response.text or "").lower()
    return response.status_code in {400, 403, 409} and any(
        marker in text
        for marker in [
            "already",
            "duplicate",
            "you have already",
            "already favorited",
            "already retweeted",
            "already requested",
        ]
    )


def perform_x_task_action(task, x_token, user_agent, proxy, config):
    if not x_token:
        return False, "no X token assigned"

    task_kind = str(task.get("kind", "")).strip().lower()
    task_config = task.get("config") if isinstance(task.get("config"), dict) else {}
    target_url = (
        task_config.get("twitterTargetUrl")
        or task_config.get("targetUrl")
        or task.get("targetUrl")
        or task.get("url")
    )
    handle, tweet_id = parse_x_target(target_url)
    x_session = make_x_session(x_token)
    referer = target_url or "https://x.com/"

    try:
        if task_kind == "twitter_follow":
            if not handle:
                return False, "missing X handle"
            r = x_session.post(
                "https://x.com/i/api/1.1/friendships/create.json",
                data={
                    "screen_name": handle,
                    "skip_status": "true",
                    "include_profile_interstitial_type": "1",
                },
                headers=x_form_headers(x_token, user_agent, referer),
                proxies=proxy,
                timeout=config["request_timeout"],
            )
        elif task_kind == "twitter_like":
            if not tweet_id:
                return False, "missing X post id"
            r = x_session.post(
                "https://x.com/i/api/1.1/favorites/create.json",
                data={"id": tweet_id, "include_entities": "true"},
                headers=x_form_headers(x_token, user_agent, referer),
                proxies=proxy,
                timeout=config["request_timeout"],
            )
        elif task_kind == "twitter_retweet":
            if not tweet_id:
                return False, "missing X post id"
            r = x_session.post(
                f"https://x.com/i/api/1.1/statuses/retweet/{tweet_id}.json",
                data={"trim_user": "false"},
                headers=x_form_headers(x_token, user_agent, referer),
                proxies=proxy,
                timeout=config["request_timeout"],
            )
        elif task_kind == "twitter_reply":
            if not tweet_id:
                return False, "missing X post id"
            reply_text = config.get("x_reply_text") or "Great update"
            r = x_session.post(
                "https://x.com/i/api/1.1/statuses/update.json",
                data={
                    "status": reply_text,
                    "in_reply_to_status_id": tweet_id,
                    "auto_populate_reply_metadata": "true",
                    "batch_mode": "off",
                },
                headers=x_form_headers(x_token, user_agent, referer),
                proxies=proxy,
                timeout=config["request_timeout"],
            )
        else:
            return True, "no X action needed"
    except req.RequestException as e:
        return False, str(e)

    if x_action_ok(r):
        return True, ""

    return False, response_error_summary(r)


def fetch_x_auth_code(x_session, x_token, oauth_url, user_agent, proxy, config):
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(oauth_url).query))
    required = {
        "client_id",
        "code_challenge",
        "code_challenge_method",
        "redirect_uri",
        "response_type",
        "scope",
        "state",
    }
    missing = sorted(required - set(query))
    if missing:
        return None, f"oauth url missing parameter(s): {', '.join(missing)}"

    r = x_session.get(
        X_OAUTH_AUTHORIZE_URL,
        params=query,
        headers=x_api_headers(x_token, user_agent, oauth_url),
        proxies=proxy,
        timeout=config["request_timeout"],
    )

    if is_dead_x_response(r.status_code, r.text):
        return None, "dead"
    if r.status_code != 200:
        return None, f"x oauth metadata: {r.status_code} {r.text[:120]}"

    data = safe_json(r) or {}
    auth_code = data.get("auth_code")
    if not auth_code:
        return None, f"x oauth metadata: missing auth_code {r.text[:120]}"

    return auth_code, None


def approve_x_oauth(x_session, x_token, auth_code, oauth_url, user_agent, proxy, config):
    headers = x_api_headers(x_token, user_agent, oauth_url)
    headers["content-type"] = "application/x-www-form-urlencoded"

    r = x_session.post(
        X_OAUTH_AUTHORIZE_URL,
        data={"approval": "true", "code": auth_code},
        headers=headers,
        proxies=proxy,
        timeout=config["request_timeout"],
    )

    if is_dead_x_response(r.status_code, r.text):
        return None, "dead"
    if r.status_code not in [200, 201]:
        return None, f"x oauth approval: {r.status_code} {r.text[:120]}"

    data = safe_json(r) or {}
    redirect_uri = data.get("redirect_uri")
    if not redirect_uri:
        return None, f"x oauth approval: missing redirect_uri {r.text[:120]}"

    return redirect_uri, None


def extract_x_link_code(text):
    if not text:
        return None

    text = urllib.parse.unquote(str(text))
    parsed = urllib.parse.urlparse(text)
    params = urllib.parse.parse_qs(parsed.query)
    for key in ["startapp", "start", "tgWebAppStartParam"]:
        for value in params.get(key, []):
            if value.startswith("xlink_"):
                return value.removeprefix("xlink_")

    marker = "xlink_"
    if marker in text:
        tail = text.split(marker, 1)[1]
        return tail.split("&", 1)[0].split("#", 1)[0].split("/", 1)[0]

    return None


def extract_x_oauth_error(text):
    if not text:
        return None

    text = urllib.parse.unquote(str(text))
    parsed = urllib.parse.urlparse(text)
    params = urllib.parse.parse_qs(parsed.query)

    for key in ["startapp", "start", "tgWebAppStartParam"]:
        for value in params.get(key, []):
            if value.startswith("xerr_"):
                error = params.get("error", [""])[0]
                return error or "x oauth returned an error"

    marker = "xerr_"
    if marker in text:
        if "error=" in text:
            error = text.split("error=", 1)[1]
            return error.split("&", 1)[0].split('"', 1)[0].split("'", 1)[0]
        return "x oauth returned an error"

    return None


def follow_xeffy_oauth_redirect(
    web_session,
    session_token,
    redirect_uri,
    user_agent,
    proxy,
    config,
):
    current_url = redirect_uri
    last_error = ""

    for _ in range(6):
        link_code = extract_x_link_code(current_url)
        if link_code:
            return link_code, None
        oauth_error = extract_x_oauth_error(current_url)
        if oauth_error:
            return None, f"x oauth error: {oauth_error}"

        try:
            r = web_session.get(
                current_url,
                headers=xeffy_session_headers(
                    session_token,
                    user_agent,
                    json_body=False,
                ),
                proxies=proxy,
                timeout=config["request_timeout"],
                allow_redirects=False,
            )
        except req.RequestException as e:
            return None, f"xeffy oauth callback: {e}"

        location = r.headers.get("Location")
        link_code = extract_x_link_code(location) or extract_x_link_code(r.text)
        if link_code:
            return link_code, None
        oauth_error = extract_x_oauth_error(location) or extract_x_oauth_error(r.text)
        if oauth_error:
            return None, f"x oauth error: {oauth_error}"

        if location:
            current_url = urllib.parse.urljoin(current_url, location)
            continue

        last_error = f"xeffy oauth callback: {r.status_code} {r.text[:120]}"
        break

    return None, last_error or "xeffy oauth callback: missing xlink code"


def claim_x_link(web_session, session_token, user_agent, proxy, config, link_code):
    r = web_session.post(
        f"{BASE_URL}/registrations/x-claim",
        json={"code": link_code},
        headers=xeffy_session_headers(session_token, user_agent),
        proxies=proxy,
        timeout=config["request_timeout"],
    )
    if r.status_code in [200, 201]:
        return None

    return f"x-claim: {r.status_code} {r.text[:120]}"


def connect_x_account(session_token, x_token, user_agent, proxy, config):
    web_session = make_xeffy_web_session(session_token)
    session_cookie_header = None

    identity, error = get_x_identity(
        web_session,
        session_cookie_header,
        user_agent,
        proxy,
        config,
    )
    if identity:
        return {
            "status": "connected_existing",
            "message": "already connected",
            "identity": identity,
            "used_token": False,
        }
    if error:
        return {
            "status": "failed",
            "message": error,
            "identity": None,
            "used_token": False,
        }

    try:
        link_code, error = prepare_x_link(
            web_session,
            session_cookie_header,
            user_agent,
            proxy,
            config,
        )
        if error:
            if "account_already_linked" in error:
                return {
                    "status": "already_linked",
                    "message": error,
                    "identity": None,
                    "used_token": False,
                }
            return {
                "status": "failed",
                "message": error,
                "identity": None,
                "used_token": False,
            }

        oauth_url, error = create_x_oauth_url(
            web_session,
            session_cookie_header,
            user_agent,
            proxy,
            config,
            link_code,
        )
        if error:
            return {
                "status": "failed",
                "message": error,
                "identity": None,
                "used_token": False,
            }

        x_session = make_x_session(x_token)
        auth_code, error = fetch_x_auth_code(
            x_session,
            x_token,
            oauth_url,
            user_agent,
            proxy,
            config,
        )
        if error == "dead":
            return {
                "status": "dead",
                "message": "X token is invalid/dead",
                "identity": None,
                "used_token": True,
            }
        if error:
            return {
                "status": "failed",
                "message": error,
                "identity": None,
                "used_token": False,
            }

        redirect_uri, error = approve_x_oauth(
            x_session,
            x_token,
            auth_code,
            oauth_url,
            user_agent,
            proxy,
            config,
        )
        if error == "dead":
            return {
                "status": "dead",
                "message": "X token is invalid/dead",
                "identity": None,
                "used_token": True,
            }
        if error:
            return {
                "status": "failed",
                "message": error,
                "identity": None,
                "used_token": False,
            }

        returned_link_code, error = follow_xeffy_oauth_redirect(
            web_session,
            session_cookie_header,
            redirect_uri,
            user_agent,
            proxy,
            config,
        )
        if error:
            if "account_already_linked" in error:
                return {
                    "status": "already_linked",
                    "message": error,
                    "identity": None,
                    "used_token": True,
                }
            return {
                "status": "failed",
                "message": error,
                "identity": None,
                "used_token": False,
            }

        error = claim_x_link(
            web_session,
            session_cookie_header,
            user_agent,
            proxy,
            config,
            returned_link_code,
        )
        if error:
            if "account_already_linked" in error:
                return {
                    "status": "already_linked",
                    "message": error,
                    "identity": None,
                    "used_token": True,
                }
            return {
                "status": "failed",
                "message": error,
                "identity": None,
                "used_token": True,
            }

        identity, error = get_x_identity(
            web_session,
            session_cookie_header,
            user_agent,
            proxy,
            config,
        )
        if identity:
            return {
                "status": "connected",
                "message": "oauth linked",
                "identity": identity,
                "used_token": True,
            }

        message = error or "x-claim succeeded but identity missing"
        return {
            "status": "failed",
            "message": message,
            "identity": None,
            "used_token": True,
        }
    except req.RequestException as e:
        return {
            "status": "failed",
            "message": str(e),
            "identity": None,
            "used_token": False,
        }


def get_account_stats(session_token, user_agent, proxy, config):
    # Campaign-scoped endpoints carry the contributor points, so query them
    # first. We gather every successful response (not just the first) because
    # generic endpoints like /me often answer without any points field.
    endpoints = [
        f"/campaigns/{CAMPAIGN_ID}/leaderboard/me",
        f"/campaigns/{CAMPAIGN_ID}/me",
        f"/campaigns/{CAMPAIGN_ID}/summary",
        f"/campaigns/{CAMPAIGN_ID}/profile",
        "/me",
        "/users/me",
        "/members/me",
        "/profile",
        "/be-auth/me",
    ]

    responses = []
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
                responses.append(data)

    return responses


def coerce_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return int(cleaned)
        except ValueError:
            try:
                return float(cleaned)
            except ValueError:
                return None
    return None


def iter_values_by_keys(data, normalized_keys):
    if isinstance(data, dict):
        for key, value in data.items():
            if normalize_key(key) in normalized_keys:
                yield value
        for value in data.values():
            yield from iter_values_by_keys(value, normalized_keys)
    elif isinstance(data, list):
        for item in data:
            yield from iter_values_by_keys(item, normalized_keys)


def extract_points(*objects):
    point_keys = {normalize_key(key) for key in POINT_KEYS}
    nested_keys = {normalize_key(key) for key in POINT_NESTED_KEYS} | point_keys
    fallback = None

    for data in objects:
        for value in iter_values_by_keys(data, point_keys):
            number = coerce_number(value)
            if number is None and isinstance(value, (dict, list)):
                for nested in iter_values_by_keys(value, nested_keys):
                    number = coerce_number(nested)
                    if number is not None:
                        break
            if number is None:
                continue
            if number:
                return number
            if fallback is None:
                fallback = number

    return fallback if fallback is not None else ""


def describe_account_source(source):
    if source["type"] == "file":
        return f"{source['name']}.session"
    if source["type"] == "query":
        return source["name"]

    return "session_string"


PYROGRAM_SESSION_SCHEMA = """
CREATE TABLE sessions
(
    dc_id     INTEGER PRIMARY KEY,
    api_id    INTEGER,
    test_mode INTEGER,
    auth_key  BLOB,
    date      INTEGER NOT NULL,
    user_id   INTEGER,
    is_bot    INTEGER
);

CREATE TABLE peers
(
    id             INTEGER PRIMARY KEY,
    access_hash    INTEGER,
    type           INTEGER NOT NULL,
    username       TEXT,
    phone_number   TEXT,
    last_update_on INTEGER NOT NULL DEFAULT (CAST(STRFTIME('%s', 'now') AS INTEGER))
);

CREATE TABLE version
(
    number INTEGER PRIMARY KEY
);

CREATE INDEX idx_peers_id ON peers (id);
CREATE INDEX idx_peers_username ON peers (username);
CREATE INDEX idx_peers_phone_number ON peers (phone_number);

CREATE TRIGGER trg_peers_last_update_on
    AFTER UPDATE
    ON peers
BEGIN
    UPDATE peers
    SET last_update_on = CAST(STRFTIME('%s', 'now') AS INTEGER)
    WHERE id = NEW.id;
END;
"""


def session_path_from_source(source):
    return Path(source["workdir"]) / f"{source['name']}.session"


def inspect_sqlite_session_schema(session_path):
    try:
        conn = sqlite3.connect(f"file:{session_path}?mode=ro", uri=True)
    except sqlite3.Error as e:
        return None, f"cannot open session sqlite database: {e}"

    try:
        version_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(version)").fetchall()
        }
        session_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
    except sqlite3.Error as e:
        return None, f"cannot inspect session database: {e}"
    finally:
        conn.close()

    return {
        "version_columns": version_columns,
        "session_columns": session_columns,
    }, None


def is_pyrogram_session_schema(schema):
    if not schema:
        return False

    required_session_columns = {"dc_id", "api_id", "auth_key", "user_id"}
    return (
        "number" in schema["version_columns"]
        and required_session_columns.issubset(schema["session_columns"])
    )


def is_telethon_session_schema(schema):
    if not schema:
        return False

    required_session_columns = {"dc_id", "server_address", "port", "auth_key"}
    return (
        "version" in schema["version_columns"]
        and required_session_columns.issubset(schema["session_columns"])
        and "number" not in schema["version_columns"]
    )


def invalid_pyrogram_session_message(schema):
    if not schema or "number" not in schema["version_columns"]:
        return (
            "invalid Pyrogram session format: missing version.number column. "
            "This usually means the file was made by Telethon, an older Pyrogram, "
            "or another bot. Telethon sessions are auto-converted when possible; "
            "otherwise use a Pyrogram v2 .session file, Pyrogram session string, "
            "or data.txt query instead."
        )

    required_session_columns = {"dc_id", "api_id", "auth_key", "user_id"}
    missing = sorted(required_session_columns - schema["session_columns"])
    if missing:
        return (
            "invalid Pyrogram session format: missing sessions column(s): "
            f"{', '.join(missing)}"
        )

    return None


def converted_session_path(source, source_path):
    key = hashlib.sha256(str(source_path.resolve()).encode("utf-8")).hexdigest()[:12]
    return CONVERTED_SESSION_DIR / f"{source['name']}_pyrogram_{key}.session"


def convert_telethon_session_file(source):
    source_path = session_path_from_source(source)
    destination = converted_session_path(source, source_path)

    try:
        conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT dc_id, auth_key FROM sessions WHERE auth_key IS NOT NULL LIMIT 1"
        ).fetchone()
    except sqlite3.Error as e:
        return None, f"cannot read Telethon session data: {e}"
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass

    if not row:
        return None, "Telethon session has no auth_key. Make a fresh session file."

    dc_id, auth_key = row
    if not dc_id or not auth_key:
        return None, "Telethon session is missing dc_id/auth_key. Make a fresh session file."

    CONVERTED_SESSION_DIR.mkdir(exist_ok=True)

    try:
        conn = sqlite3.connect(destination)
        with conn:
            conn.executescript(
                """
                DROP TRIGGER IF EXISTS trg_peers_last_update_on;
                DROP TABLE IF EXISTS peers;
                DROP TABLE IF EXISTS sessions;
                DROP TABLE IF EXISTS version;
                """
            )
            conn.executescript(PYROGRAM_SESSION_SCHEMA)
            conn.execute(
                "INSERT INTO version VALUES (?)",
                (PYROGRAM_SESSION_VERSION,),
            )
            conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    int(dc_id),
                    API_ID,
                    0,
                    sqlite3.Binary(bytes(auth_key)),
                    0,
                    1,
                    0,
                ),
            )
    except sqlite3.Error as e:
        return None, f"cannot create converted Pyrogram session: {e}"
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass

    return {
        **source,
        "name": destination.stem,
        "workdir": str(destination.parent),
        "converted_from": str(source_path),
    }, None


def prepare_pyrogram_file_session(source):
    if source["type"] != "file":
        return source, None

    session_path = session_path_from_source(source)
    if not session_path.exists():
        return source, f"session file not found: {session_path}"

    schema, error = inspect_sqlite_session_schema(session_path)
    if error:
        return source, error

    if is_pyrogram_session_schema(schema):
        return source, None

    if is_telethon_session_schema(schema):
        converted_source, convert_error = convert_telethon_session_file(source)
        if convert_error:
            return source, convert_error
        return converted_source, None

    return source, invalid_pyrogram_session_message(schema)


def validate_pyrogram_session_file(source):
    _, error = prepare_pyrogram_file_session(source)
    return error


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
        "tasks_skipped": 0,
        "tasks_failed": 0,
        "points": "",
        "status": "started",
        "error": "",
        "_x_token_raw": "",
        "_x_token_line": "",
        "_x_token_used": "",
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


def normalize_quiz_text(value):
    return " ".join(str(value).strip().casefold().split())


def option_text_values(option):
    if isinstance(option, (str, int, float)):
        return [str(option)]
    if not isinstance(option, dict):
        return []

    values = []
    for key in [
        "text",
        "label",
        "name",
        "title",
        "value",
        "answer",
        "option",
        "content",
    ]:
        value = option.get(key)
        if isinstance(value, (str, int, float)):
            values.append(str(value))
    return values


def iter_quiz_option_lists(task):
    option_keys = {
        "options",
        "answers",
        "choices",
        "quizoptions",
        "answeroptions",
    }

    for item in iter_nested(task):
        if not isinstance(item, dict):
            continue

        for key, value in item.items():
            normalized = key.replace("_", "").replace("-", "").lower()
            if normalized in option_keys and isinstance(value, list):
                yield value


def infer_quiz_answer_from_text(task, answer_lines):
    answers = [
        normalize_quiz_text(answer)
        for answer in answer_lines
        if answer and as_optional_int(answer) is None
    ]
    if not answers:
        return None

    for options in iter_quiz_option_lists(task):
        for index, option in enumerate(options):
            option_values = {
                normalize_quiz_text(value) for value in option_text_values(option)
            }
            for answer in answers:
                if answer in option_values:
                    return index

    return None


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

        for options in iter_quiz_option_lists(item):
            for index, option in enumerate(options):
                if not isinstance(option, dict):
                    continue
                for key, value in option.items():
                    normalized = key.replace("_", "").replace("-", "").lower()
                    if normalized in correct_flags and as_bool(value, False):
                        return index

    return None


def first_quiz_option_list(task):
    for options in iter_quiz_option_lists(task):
        if options:
            return options
    return None


def quiz_option_label(task, index):
    if index is None:
        return ""
    options = first_quiz_option_list(task)
    if not options or index < 0 or index >= len(options):
        return ""
    values = option_text_values(options[index])
    return values[0] if values else ""


def build_quiz_proof(task, config):
    answer_lines = load_quiz_answer_lines()

    # 1) Manual answer number from answers.txt / config. The number is the
    #    option position shown in the app (1 = first option). This is the
    #    reliable path because it does not depend on the option text being
    #    present in the task payload.
    answer_index = load_quiz_answer(config)

    # 2) Exact option-text match from answers.txt (legacy text answers).
    if answer_index is None:
        answer_index = infer_quiz_answer_from_text(task, answer_lines)

    # 3) Correct-answer hint embedded in the task response, if any.
    if answer_index is None and config.get("auto_quiz_answer", True):
        answer_index = infer_quiz_answer(task)

    if answer_index is None:
        return None

    return {"quizSelectedIndex": answer_index}


def is_quiz_task(task):
    task_kind = str(task.get("kind", "")).lower()
    task_name = str(task.get("name", "")).lower()
    return "quiz" in task_kind or "quiz" in task_name


def is_x_task(task):
    task_kind = str(task.get("kind", "")).strip().lower()
    if task_kind in X_TASK_KINDS or task_kind.startswith("twitter_"):
        return True

    for item in iter_nested(task):
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            normalized = normalize_key(key)
            if normalized in {"platform", "provider", "network", "socialplatform"}:
                platform = str(value).strip().lower()
                if platform in {"twitter", "x"}:
                    return True

    text_parts = []
    for key in [
        "name",
        "title",
        "description",
        "url",
        "targetUrl",
        "target_url",
        "actionUrl",
        "action_url",
    ]:
        value = task.get(key)
        if value not in (None, ""):
            text_parts.append(str(value).lower())

    text = " ".join(text_parts)
    return any(marker in text for marker in X_TASK_TEXT_MARKERS)


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
    if x_token:
        result["_x_token_raw"] = x_token["raw"]
        result["_x_token_line"] = x_token.get("line", index)
    elif config.get("preserve_x_token_lines", True):
        result["_x_token_line"] = expected_x_token_line(source, index)

    print(f"\n{'=' * 50}")
    print(f"[Account {index}] Starting...")

    init_data = None

    if source["type"] == "query":
        init_data = source["init_data"]
        telegram_user, telegram_id = extract_telegram_from_init_data(init_data)
        result["telegram_user"] = telegram_user or source["name"]
        result["telegram_id"] = telegram_id
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
            prepared_source, session_error = prepare_pyrogram_file_session(source)
            if session_error:
                result["status"] = "failed"
                result["error"] = session_error
                print(f"[Account {index}] [FAIL] {session_error}")
                return result

            client_kwargs["name"] = prepared_source["name"]
            client_kwargs["workdir"] = prepared_source["workdir"]
            if prepared_source.get("converted_from"):
                print(
                    f"[Account {index}] Telethon session converted: "
                    f"{Path(prepared_source['converted_from']).name}"
                )
            print(f"[Account {index}] Session file: {prepared_source['name']}.session")
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

    x_identity = None
    x_connect_attempted = False
    if config.get("auto_connect_x") and x_token:
        x_connect_attempted = True
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
        x_identity = x_result.get("identity")
        result["_x_token_used"] = "yes" if x_result.get("used_token") else "no"
        if x_result["status"] in {"connected", "connected_existing"}:
            detail = format_x_identity(x_identity)
            suffix = f": {detail}" if detail else ""
            if x_result["status"] == "connected_existing":
                print(f"[Account {index}] [OK] X already connected{suffix}")
            else:
                print(f"[Account {index}] [OK] X connected{suffix}")
        elif x_result["status"] == "dead":
            print(f"[Account {index}] [WARN] X token is invalid/dead")
        elif x_result["status"] == "already_linked":
            print(f"[Account {index}] [WARN] X account already linked to another Xeffy user")
        else:
            print(f"[Account {index}] [WARN] X connect skipped: {x_result['message']}")
    elif config.get("auto_connect_x"):
        expected_line = expected_x_token_line(source, index)
        print(
            f"[Account {index}] [WARN] auto_connect_x enabled but no X token assigned; "
            f"expected xtoken.txt line {expected_line}"
        )

    if not x_identity:
        x_identity, x_identity_error = await asyncio.to_thread(
            check_x_identity,
            session_token,
            user_agent,
            proxy,
            config,
        )
        if x_identity:
            result["x_connect"] = "connected_existing"
            detail = format_x_identity(x_identity)
            suffix = f": {detail}" if detail else ""
            print(f"[Account {index}] [OK] X identity verified{suffix}")
        elif x_identity_error:
            print(f"[Account {index}] [WARN] X identity check failed: {x_identity_error}")

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
        x_task = is_x_task(task)

        if not task_id or not can_submit:
            continue

        if x_task and not x_identity and x_token and not x_connect_attempted:
            x_connect_attempted = True
            print(f"[Account {index}] X identity missing before X task; connecting X account...")
            x_result = await asyncio.to_thread(
                connect_x_account,
                session_token,
                x_token,
                user_agent,
                proxy,
                config,
            )
            result["x_connect"] = x_result["status"]
            x_identity = x_result.get("identity")
            result["_x_token_used"] = "yes" if x_result.get("used_token") else "no"
            if x_identity:
                detail = format_x_identity(x_identity)
                suffix = f": {detail}" if detail else ""
                print(f"[Account {index}] [OK] X connected for tasks{suffix}")
            else:
                print(f"[Account {index}] [WARN] X connect failed before task: {x_result['message']}")

        if x_task and not x_identity:
            result["tasks_skipped"] += 1
            if x_token:
                reason = f"X identity is not connected in the mini app; connect status: {result['x_connect']}"
            else:
                expected_line = expected_x_token_line(source, index)
                reason = f"missing X token; put auth_token|ct0 at xtoken.txt line {expected_line}"
            print(
                f"[Account {index}] [SKIP] {task_name} "
                f"({reason})"
            )
            continue

        if is_quiz_task(task):
            proof = build_quiz_proof(task, config)
            if proof is None:
                print(f"[Account {index}] [WARN] Skipping quiz; no answer found: {task_name}")
                continue
            selected = proof.get("quizSelectedIndex")
            label = quiz_option_label(task, selected)
            label_suffix = f": {label}" if label else ""
            print(
                f"[Account {index}] [QUIZ] {task_name} -> option #{selected + 1}{label_suffix}"
            )
        else:
            proof = {}

        if x_task and config.get("x_task_actions", True):
            if x_token:
                action_ok, action_error = await asyncio.to_thread(
                    perform_x_task_action,
                    task,
                    x_token,
                    user_agent,
                    proxy,
                    config,
                )
                if action_ok:
                    print(f"[Account {index}] [OK] X action done: {task_name}")
                    if config.get("x_action_delay", 0):
                        await asyncio.sleep(config["x_action_delay"])
                else:
                    print(
                        f"[Account {index}] [WARN] X action failed before submit: "
                        f"{task_name}: {action_error}"
                    )
            else:
                print(f"[Account {index}] [WARN] No X token for X action: {task_name}")

        ok, submit_error = await asyncio.to_thread(
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
            suffix = f": {submit_error}" if submit_error else ""
            print(f"[Account {index}] [FAIL] {task_name}{suffix}")

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
    x_token = pick_x_token(x_tokens, index, config, source)

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


def export_tg_x_mapping(results, path="tg_x_mapping.csv"):
    if not results:
        return

    fieldnames = [
        "account_number",
        "telegram_user",
        "telegram_id",
        "source",
        "x_token_line",
        "x_connect",
        "x_token_used",
        "x_token",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(results, key=lambda item: item.get("account_number", 0)):
            writer.writerow(
                {
                    "account_number": row.get("account_number", ""),
                    "telegram_user": row.get("telegram_user", ""),
                    "telegram_id": row.get("telegram_id", ""),
                    "source": row.get("source", ""),
                    "x_token_line": row.get("_x_token_line", ""),
                    "x_connect": row.get("x_connect", ""),
                    "x_token_used": row.get("_x_token_used", ""),
                    "x_token": row.get("_x_token_raw", ""),
                }
            )

    print(f"[OK] Updated TG/X mapping: {path}")


def update_xtoken_files(results, x_tokens):
    if not x_tokens:
        return

    config = load_config()
    if config.get("preserve_x_token_lines", True):
        print("[OK] Preserved xtoken.txt line mapping; token file was not rewritten.")
        return

    connected_raw = {
        row.get("_x_token_raw")
        for row in results
        if row.get("_x_token_raw") and row.get("x_connect") == "connected"
        and row.get("_x_token_used") == "yes"
    }
    dead_raw = {
        row.get("_x_token_raw")
        for row in results
        if row.get("_x_token_raw") and row.get("x_connect") == "dead"
        and row.get("_x_token_used") == "yes"
    }
    already_linked_raw = {
        row.get("_x_token_raw")
        for row in results
        if row.get("_x_token_raw") and row.get("x_connect") == "already_linked"
        and row.get("_x_token_used") == "yes"
    }
    remove_raw = connected_raw | dead_raw | already_linked_raw

    if not remove_raw:
        return

    connected_tokens = [token for token in x_tokens if token["raw"] in connected_raw]
    already_linked_tokens = [
        token for token in x_tokens if token["raw"] in already_linked_raw
    ]
    remaining_tokens = [token for token in x_tokens if token["raw"] not in remove_raw]

    append_connected_x_tokens(connected_tokens)
    append_connected_x_tokens(already_linked_tokens, "x_already_linked.txt")
    write_x_tokens(remaining_tokens)
    print(
        "[OK] Updated xtoken.txt. Removed "
        f"{len(remove_raw)} connected/dead/already-linked token(s)."
    )


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


def mode_label(mode):
    labels = {
        "full": "Full: join + check-in + tasks",
        "daily": "Daily: check-in + tasks",
        "checkin": "Check-in only",
    }
    return labels.get(mode, mode or "unknown")


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
    print(f"Selected mode    : {mode_label(mode)}")
    if mode == "full" and not tele_links:
        print("[WARN] Full mode selected but channel.txt has no links; join step will be skipped.")

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

        export_tg_x_mapping(results)
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
