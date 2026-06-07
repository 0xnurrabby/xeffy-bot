import argparse
import asyncio
import json
from pathlib import Path

import requests as req

import xeffy_bot as bot


def print_json(label, data):
    if data is None:
        print(f"{label}: null")
        return
    print(f"{label}: {json.dumps(data, ensure_ascii=False, indent=2)}")


def get_x_identity(session_token, user_agent, proxy, config):
    web_session = bot.make_xeffy_web_session(session_token)
    r = web_session.get(
        f"{bot.BASE_URL}/registrations/x-identity",
        headers=bot.xeffy_session_headers(None, user_agent, json_body=False),
        proxies=proxy,
        timeout=config["request_timeout"],
    )
    if r.status_code == 204:
        return None, None
    if r.status_code == 200:
        return bot.safe_json(r), None
    return None, f"x-identity: {r.status_code} {r.text[:200]}"


def unlink_x_identity(session_token, user_agent, proxy, config):
    web_session = bot.make_xeffy_web_session(session_token)
    r = web_session.post(
        f"{bot.BASE_URL}/be-auth/unlink-account",
        json={"providerId": "twitter"},
        headers=bot.xeffy_session_headers(None, user_agent),
        proxies=proxy,
        timeout=config["request_timeout"],
    )
    if r.status_code in {200, 201, 204}:
        return bot.safe_json(r), None
    return None, f"unlink-account: {r.status_code} {r.text[:200]}"


def describe_x_token(x_token, user_agent, proxy, config):
    x_session = bot.make_x_session(x_token)
    headers = {
        "authorization": bot.X_WEB_BEARER,
        "x-csrf-token": x_token["ct0"],
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "user-agent": user_agent or bot.DEFAULT_USER_AGENT,
        "accept": "application/json, text/plain, */*",
        "origin": "https://x.com",
        "referer": "https://x.com/",
    }
    endpoints = [
        "https://x.com/i/api/1.1/account/verify_credentials.json?skip_status=true",
        "https://twitter.com/i/api/1.1/account/verify_credentials.json?skip_status=true",
        "https://api.x.com/1.1/account/verify_credentials.json?skip_status=true",
        "https://api.twitter.com/1.1/account/verify_credentials.json?skip_status=true",
    ]
    for endpoint in endpoints:
        try:
            r = x_session.get(
                endpoint,
                headers=headers,
                proxies=proxy,
                timeout=config["request_timeout"],
            )
        except req.RequestException as e:
            last_error = str(e)
            continue

        if r.status_code == 200:
            data = bot.safe_json(r) or {}
            return {
                "id": data.get("id_str") or str(data.get("id") or ""),
                "screen_name": data.get("screen_name"),
                "name": data.get("name"),
            }, None
        last_error = f"{r.status_code} {r.text[:160]}"

    return None, f"x token verify failed: {last_error}"


async def init_data_for_source(source, account_number, config):
    if source["type"] == "query":
        return source["init_data"], f"data.txt account {account_number}"

    if not bot.ensure_pyrogram():
        raise RuntimeError(f"pyrogram is not installed: {bot.PYROGRAM_IMPORT_ERROR}")
    if bot.API_ID == 0 or not bot.API_HASH:
        raise RuntimeError("missing API_ID/API_HASH in .env")

    client_kwargs = {"api_id": bot.API_ID, "api_hash": bot.API_HASH}
    if source["type"] == "file":
        prepared_source, error = bot.prepare_pyrogram_file_session(source)
        if error:
            raise RuntimeError(error)
        client_kwargs["name"] = str(
            bot.session_path_from_source(prepared_source).with_suffix("")
        )
        label = f"{prepared_source['name']}.session"
    else:
        client_kwargs.update(
            {
                "name": f"x_tools_{account_number}",
                "session_string": source["value"],
                "in_memory": True,
            }
        )
        label = f"session string {account_number}"

    async with bot.Client(**client_kwargs) as app:
        me = await app.get_me()
        username = f"@{me.username}" if me.username else "(no username)"
        print(f"Telegram: {username} ({me.id})")
        init_data = await bot.get_init_data(app, account_number, None)
        if not init_data:
            raise RuntimeError("could not get Telegram Mini App initData")
        return init_data, label


async def login_account(account_number):
    config = bot.load_config()
    accounts = bot.load_account_sources()
    if not accounts:
        raise RuntimeError("no accounts found in sessions.txt/data.txt")
    if account_number < 1 or account_number > len(accounts):
        raise RuntimeError(f"account number must be between 1 and {len(accounts)}")

    user_agents = bot.load_user_agents("useragents.txt")
    proxies = bot.load_proxies("proxy.txt")
    user_agent = bot.pick_user_agent(user_agents)
    proxy = bot.pick_proxy(proxies, account_number, config)

    init_data, label = await init_data_for_source(
        accounts[account_number - 1], account_number, config
    )
    print(f"Source: {label}")
    login = bot.xeffy_login(init_data, user_agent, proxy, config)
    if not login:
        raise RuntimeError("Xeffy login failed")
    print("Xeffy login: ok")
    return login["session_token"], user_agent, proxy, config


async def command_check(args):
    session_token, user_agent, proxy, config = await login_account(args.account_number)
    identity, error = get_x_identity(session_token, user_agent, proxy, config)
    if error:
        print(f"[FAIL] {error}")
        return 1
    if identity:
        print("[OK] This Telegram/Xeffy user has an X account connected.")
        print_json("X identity", identity)
    else:
        print("[INFO] This Telegram/Xeffy user has no X account connected.")
    return 0


async def command_unlink(args):
    session_token, user_agent, proxy, config = await login_account(args.account_number)
    before, error = get_x_identity(session_token, user_agent, proxy, config)
    if error:
        print(f"[FAIL] {error}")
        return 1
    if before:
        print("[INFO] Before unlink: connected")
        print_json("X identity", before)
    else:
        print("[INFO] Before unlink: not connected")

    data, error = unlink_x_identity(session_token, user_agent, proxy, config)
    if error:
        print(f"[FAIL] {error}")
        return 1
    print_json("Unlink response", data)

    after, error = get_x_identity(session_token, user_agent, proxy, config)
    if error:
        print(f"[FAIL] {error}")
        return 1
    if after:
        print("[WARN] After unlink: still connected")
        print_json("X identity", after)
    else:
        print("[OK] After unlink: not connected")
    return 0


def command_xwho(args):
    config = bot.load_config()
    user_agent = bot.pick_user_agent(bot.load_user_agents("useragents.txt"))
    proxy = None
    if args.token:
        x_token = bot.parse_x_token(args.token)
        tokens = [x_token] if x_token else []
    else:
        tokens = bot.load_x_tokens(args.file)

    if not tokens:
        print(f"No valid X tokens found in {args.file}.")
        return 1

    for index, x_token in enumerate(tokens, start=1):
        info, error = describe_x_token(x_token, user_agent, proxy, config)
        prefix = f"X token {index}"
        if error:
            print(f"{prefix}: [FAIL] {error}")
        else:
            screen_name = info.get("screen_name") or "(unknown)"
            name = info.get("name") or ""
            user_id = info.get("id") or ""
            print(f"{prefix}: @{screen_name} {name} {user_id}".strip())
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Xeffy X connect/unlink helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Check current X link state.")
    check.add_argument("--account-number", type=int, default=1)

    unlink = subparsers.add_parser("unlink", help="Unlink X from this Xeffy user.")
    unlink.add_argument("--account-number", type=int, default=1)

    xwho = subparsers.add_parser("xwho", help="Show which X account a token belongs to.")
    xwho.add_argument("--file", default="xtoken.txt")
    xwho.add_argument("--token", default="")

    return parser


async def async_main():
    args = build_parser().parse_args()
    if args.command == "check":
        return await command_check(args)
    if args.command == "unlink":
        return await command_unlink(args)
    if args.command == "xwho":
        return command_xwho(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
