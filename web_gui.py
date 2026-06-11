import html
import json
import os
import subprocess
import sys
import threading
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from urllib.parse import parse_qs, urlparse


HOST = "127.0.0.1"
PORT = int(os.getenv("XEFFY_GUI_PORT", "8787"))
ROOT = Path(__file__).resolve().parent
RUN_DIR = ROOT / ".web_runs"
LOG_PATH = RUN_DIR / "latest.log"

EDITABLE_FILES = [
    ".env",
    "config.json",
    "sessions.txt",
    "data.txt",
    "ref.txt",
    "channel.txt",
    "answers.txt",
    "proxy.txt",
    "useragents.txt",
    "xtoken.txt",
]

FILE_TITLES = {
    ".env": "Telegram API",
    "config.json": "Bot Config",
    "sessions.txt": "Telegram Sessions",
    "data.txt": "WebApp Data",
    "ref.txt": "Referral",
    "channel.txt": "Channels",
    "answers.txt": "Quiz Answers",
    "proxy.txt": "Proxies",
    "useragents.txt": "User Agents",
    "xtoken.txt": "X Tokens",
}

BOT_PROCESS = None
BOT_LOCK = threading.Lock()
LAST_RUN_OPTIONS = {
    "accounts": "all",
    "mode": "daily",
    "account_number": "1",
}

ACCOUNT_LABELS = {
    "all": "All accounts",
    "one": "One account",
    "start": "Start from account",
}

MODE_LABELS = {
    "daily": "Daily: check-in + tasks",
    "full": "Full: join + check-in + tasks",
    "checkin": "Check-in only",
}

POINT_COLUMNS = {
    "points",
    "point",
    "total_points",
    "totalpoints",
    "total_point",
    "totalpoint",
    "score",
    "total_score",
    "totalscore",
    "balance",
    "xef",
    "total_xef",
    "totalxef",
}


def active_lines(path):
    return [
        line.strip()
        for line in read_text(path).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def read_text(path):
    target = ROOT / path
    if path == ".env" and not target.exists():
        target = ROOT / ".env.example"
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8", errors="replace")


def write_text(path, value):
    target = ROOT / path
    target.write_text(value.replace("\r\n", "\n"), encoding="utf-8")


def python_executable():
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    return str(venv_python) if venv_python.exists() else sys.executable


def process_running():
    global BOT_PROCESS
    with BOT_LOCK:
        return BOT_PROCESS is not None and BOT_PROCESS.poll() is None


def normalize_run_options(accounts, mode, account_number):
    accounts = accounts if accounts in ACCOUNT_LABELS else "all"
    mode = mode if mode in MODE_LABELS else "daily"
    try:
        account_number = str(max(1, int(account_number or 1)))
    except ValueError:
        account_number = "1"

    return {
        "accounts": accounts,
        "mode": mode,
        "account_number": account_number,
    }


def selected_attr(current, value):
    return " selected" if current == value else ""


def start_bot(options, submitted_mode=""):
    global BOT_PROCESS
    global LAST_RUN_OPTIONS

    with BOT_LOCK:
        if BOT_PROCESS is not None and BOT_PROCESS.poll() is None:
            return False

        LAST_RUN_OPTIONS = options.copy()
        RUN_DIR.mkdir(exist_ok=True)
        log_file = open(LOG_PATH, "w", encoding="utf-8")
        log_file.write(
            "Starting Xeffy bot from GUI\n"
            f"Accounts: {ACCOUNT_LABELS[options['accounts']]}\n"
            f"Account number: {options['account_number']}\n"
            f"Submitted mode: {submitted_mode or options['mode']}\n"
            f"Effective mode: {MODE_LABELS[options['mode']]}\n"
            "-" * 42
            + "\n"
        )
        log_file.flush()
        command = [
            python_executable(),
            "-u",
            "xeffy_bot.py",
            "--accounts",
            options["accounts"],
            "--mode",
            options["mode"],
            "--account-number",
            options["account_number"],
        ]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        BOT_PROCESS = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            env=env,
        )
        return True


def stop_bot():
    global BOT_PROCESS

    with BOT_LOCK:
        if BOT_PROCESS is None or BOT_PROCESS.poll() is not None:
            return False
        BOT_PROCESS.terminate()
        return True


def account_count():
    lines = active_lines("sessions.txt")
    if lines:
        total = 0
        for line in lines:
            item_path = (ROOT / line).resolve() if not Path(line).is_absolute() else Path(line)
            if item_path.is_dir():
                total += len(list(item_path.glob("*.session")))
            else:
                total += 1
        return total
    sessions_dir = ROOT / "sessions"
    if sessions_dir.exists():
        return len(list(sessions_dir.glob("*.session")))
    return 0


def line_count(path):
    return len(active_lines(path))


def x_token_count():
    total = 0
    for line in active_lines("xtoken.txt"):
        normalized = line.strip().lower()
        if normalized in {"auth token|ct0", "auth_token|ct0"}:
            continue
        if "|" in line:
            total += 1
    return total


def latest_export_path():
    export_dir = ROOT / "exports"
    if not export_dir.exists():
        return None
    paths = sorted(export_dir.glob("xeffy_run_*.csv"), key=lambda p: p.stat().st_mtime)
    return paths[-1] if paths else None


def as_number(value):
    text = str(value or "").replace(",", "").strip()
    if not text:
        return 0
    try:
        number = float(text)
    except ValueError:
        return 0
    return int(number) if number.is_integer() else number


def normalized_key(value):
    return str(value).replace("_", "").replace("-", "").strip().lower()


def row_points(row):
    point_columns = {normalized_key(key) for key in POINT_COLUMNS}
    fallback = 0
    for key, value in row.items():
        if normalized_key(key) not in point_columns:
            continue
        number = as_number(value)
        if number:
            return number
        if str(value or "").strip():
            fallback = number
    return fallback


def format_number(value):
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{int(value):,}"


def latest_run_summary():
    export_path = latest_export_path()
    rows = []
    if export_path:
        try:
            with open(export_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        except (OSError, csv.Error):
            rows = []

    total_accounts = len(rows) if rows else account_count()
    total_points = sum(row_points(row) for row in rows)
    submitted_tasks = sum(as_number(row.get("tasks_submitted")) for row in rows)
    skipped_tasks = sum(as_number(row.get("tasks_skipped")) for row in rows)
    failed_tasks = sum(as_number(row.get("tasks_failed")) for row in rows)
    finished_accounts = sum(1 for row in rows if row.get("status") == "done")
    x_connected = sum(
        1
        for row in rows
        if row.get("x_connect") in {"connected", "connected_existing"}
    )

    return {
        "has_export": bool(rows),
        "export_name": export_path.name if export_path else "none",
        "total_accounts": total_accounts,
        "total_points": total_points,
        "submitted_tasks": submitted_tasks,
        "skipped_tasks": skipped_tasks,
        "failed_tasks": failed_tasks,
        "finished_accounts": finished_accounts,
        "x_connected": x_connected,
    }


def status_data():
    running = process_running()
    return {
        "running": running,
        "statusText": "Running" if running else "Idle",
        "statusClass": "running" if running else "idle",
    }


def page_shell(active, body, message=""):
    status = status_data()
    notice = (
        f"<div class='notice'>{html.escape(message)}</div>"
        if message
        else ""
    )
    dashboard_class = "active" if active == "dashboard" else ""
    settings_class = "active" if active == "settings" else ""

    return PAGE_TEMPLATE.substitute(
        status_text=status["statusText"],
        status_class=status["statusClass"],
        dashboard_class=dashboard_class,
        settings_class=settings_class,
        notice=notice,
        body=body,
    )


def render_dashboard(message=""):
    summary = latest_run_summary()
    run_options = LAST_RUN_OPTIONS.copy()
    stats = [
        ("Total accounts", summary["total_accounts"], "latest run / sessions", "blue"),
        ("Total points", format_number(summary["total_points"]), "latest export", "green"),
        ("Done tasks", format_number(summary["submitted_tasks"]), "submitted tasks", "red"),
        ("Skipped tasks", format_number(summary["skipped_tasks"]), "latest run", "yellow"),
        ("X connected", summary["x_connected"], "latest run", "yellow"),
        ("Finished", summary["finished_accounts"], "completed accounts", "blue"),
        ("Failed tasks", format_number(summary["failed_tasks"]), "latest run", "red"),
        ("X token lines", x_token_count(), "xtoken.txt", "green"),
        ("Quiz answers", line_count("answers.txt"), "answers.txt", "yellow"),
    ]
    stat_cards = "\n".join(
        f"""
        <article class="stat-card tone-{html.escape(tone)}">
          <span>{html.escape(label)}</span>
          <strong>{html.escape(str(value))}</strong>
          <small>{html.escape(source)}</small>
        </article>
        """
        for label, value, source, tone in stats
    )

    referral = active_lines("ref.txt")
    referral_text = html.escape(referral[0]) if referral else "none"
    body = f"""
      <section class="hero-band">
        <div>
          <p class="eyebrow">Dashboard</p>
          <h1>Xeffy Bot Control</h1>
        </div>
        <div class="hero-actions">
          <a class="button ghost" href="/settings">Open settings</a>
        </div>
      </section>

      <section class="stats-grid">
        {stat_cards}
      </section>

      <section class="work-grid">
        <form class="tool-panel run-panel" method="post" action="/run">
          <div class="section-head">
            <div>
              <p class="eyebrow">Run</p>
              <h2>Start bot</h2>
            </div>
          </div>
          <div class="form-grid">
            <label>Accounts
              <select name="accounts">
                <option value="all"{selected_attr(run_options["accounts"], "all")}>All accounts</option>
                <option value="one"{selected_attr(run_options["accounts"], "one")}>One account</option>
                <option value="start"{selected_attr(run_options["accounts"], "start")}>Start from account</option>
              </select>
            </label>
            <label>Account number
              <input name="account_number" type="number" min="1" value="{html.escape(run_options["account_number"])}">
            </label>
            <label class="wide">Mode
              <select name="selected_mode">
                <option value="daily"{selected_attr(run_options["mode"], "daily")}>Daily: check-in + tasks</option>
                <option value="full"{selected_attr(run_options["mode"], "full")}>Full: join + check-in + tasks</option>
                <option value="checkin"{selected_attr(run_options["mode"], "checkin")}>Check-in only</option>
              </select>
            </label>
          </div>
          <div class="button-row">
            <button class="button primary" type="submit">Run bot</button>
          </div>
        </form>

        <section class="tool-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Status</p>
              <h2>Current run</h2>
            </div>
          </div>
          <dl class="run-meta">
            <div>
              <dt>Referral</dt>
              <dd>{referral_text}</dd>
            </div>
            <div>
              <dt>Log file</dt>
              <dd>.web_runs/latest.log</dd>
            </div>
            <div>
              <dt>Latest export</dt>
              <dd>{html.escape(summary["export_name"])}</dd>
            </div>
            <div>
              <dt>Selected mode</dt>
              <dd>{html.escape(MODE_LABELS[run_options["mode"]])}</dd>
            </div>
            <div>
              <dt>TG/X mapping</dt>
              <dd>tg_x_mapping.csv</dd>
            </div>
          </dl>
          <form method="post" action="/stop" class="button-row">
            <button class="button danger" type="submit">Stop bot</button>
            <a class="button ghost" href="/">Refresh</a>
          </form>
        </section>
      </section>

      <section class="tool-panel log-panel">
        <div class="section-head">
          <div>
            <p class="eyebrow">Output</p>
            <h2>Live log</h2>
          </div>
          <span id="logState" class="mini-state">syncing</span>
        </div>
        <pre id="log">Loading log...</pre>
      </section>
    """
    return page_shell("dashboard", body, message)


def render_settings(message=""):
    editors = []
    for file_name in EDITABLE_FILES:
        value = html.escape(read_text(file_name))
        title = FILE_TITLES.get(file_name, file_name)
        editors.append(
            f"""
            <form class="editor-card" data-file="{html.escape(file_name)}">
              <div class="editor-head">
                <div>
                  <p class="eyebrow">{html.escape(file_name)}</p>
                  <h2>{html.escape(title)}</h2>
                </div>
                <span class="save-state">Saved</span>
              </div>
              <textarea name="content" spellcheck="false">{value}</textarea>
              <div class="editor-actions">
                <button class="button primary" type="submit">Save</button>
                <button class="button ghost" type="button" data-reload>Reload</button>
              </div>
            </form>
            """
        )

    body = f"""
      <section class="hero-band">
        <div>
          <p class="eyebrow">Settings</p>
          <h1>Files</h1>
        </div>
        <div class="hero-actions">
          <a class="button ghost" href="/">Back to dashboard</a>
        </div>
      </section>
      <section class="settings-grid">
        {''.join(editors)}
      </section>
    """
    return page_shell("settings", body, message)


PAGE_TEMPLATE = Template("""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Xeffy Bot Control</title>
  <style>
    :root {
      color-scheme: light;
      --blue: #1a73e8;
      --blue-hover: #1558b0;
      --green: #188038;
      --red: #d93025;
      --yellow: #fbbc04;
      --bg: #f8fafd;
      --surface: #ffffff;
      --surface-2: #f1f5f9;
      --text: #202124;
      --muted: #5f6368;
      --line: #dadce0;
      --shadow: 0 1px 2px rgba(60, 64, 67, 0.12), 0 1px 3px rgba(60, 64, 67, 0.10);
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 Arial, "Segoe UI", sans-serif;
    }
    a { color: inherit; text-decoration: none; }
    .appbar {
      position: sticky;
      top: 0;
      z-index: 10;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.96);
      backdrop-filter: blur(10px);
    }
    .appbar-inner {
      max-width: 1180px;
      margin: 0 auto;
      min-height: 64px;
      padding: 0 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 190px;
      font-size: 18px;
      font-weight: 700;
    }
    .brand-mark {
      width: 28px;
      height: 28px;
      border-radius: 8px;
      background:
        linear-gradient(135deg, var(--blue) 0 48%, transparent 48%),
        linear-gradient(225deg, var(--red) 0 48%, transparent 48%),
        linear-gradient(45deg, var(--green) 0 48%, transparent 48%),
        linear-gradient(315deg, var(--yellow) 0 48%, transparent 48%);
      border: 1px solid rgba(60, 64, 67, 0.16);
    }
    .nav {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--surface-2);
    }
    .nav a {
      min-height: 34px;
      display: inline-flex;
      align-items: center;
      padding: 0 14px;
      border-radius: 999px;
      color: var(--muted);
      font-weight: 700;
      white-space: nowrap;
    }
    .nav a.active {
      background: var(--surface);
      color: var(--blue);
      box-shadow: var(--shadow);
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      padding: 0 12px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--surface);
      color: var(--muted);
      font-weight: 700;
      white-space: nowrap;
    }
    .status::before {
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--muted);
    }
    .status.running { color: var(--green); }
    .status.running::before { background: var(--green); }
    main {
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px 20px 36px;
    }
    .notice {
      margin-bottom: 16px;
      padding: 12px 14px;
      border: 1px solid #c4d7ff;
      border-radius: var(--radius);
      background: #e8f0fe;
      color: #174ea6;
      font-weight: 700;
    }
    .hero-band {
      min-height: 96px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
      padding: 22px 0;
      border-bottom: 1px solid var(--line);
    }
    .eyebrow {
      margin: 0 0 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0;
      text-transform: uppercase;
    }
    h1, h2 {
      margin: 0;
      letter-spacing: 0;
      color: var(--text);
    }
    h1 { font-size: 28px; line-height: 1.2; }
    h2 { font-size: 16px; }
    .hero-actions,
    .button-row,
    .editor-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .button {
      min-height: 38px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid transparent;
      border-radius: 6px;
      padding: 8px 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      background: var(--surface);
    }
    .button.primary {
      background: var(--blue);
      color: #fff;
      box-shadow: var(--shadow);
    }
    .button.primary:hover { background: var(--blue-hover); }
    .button.danger {
      border-color: #f4c7c3;
      color: var(--red);
    }
    .button.danger:hover { background: #fce8e6; }
    .button.ghost {
      border-color: var(--line);
      color: var(--text);
    }
    .button.ghost:hover { background: var(--surface-2); }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .stat-card,
    .tool-panel,
    .editor-card {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: var(--shadow);
    }
    .stat-card {
      min-height: 112px;
      padding: 16px;
      display: grid;
      align-content: space-between;
      gap: 8px;
      position: relative;
      overflow: hidden;
    }
    .stat-card::before {
      content: "";
      position: absolute;
      inset: 0 0 auto;
      height: 4px;
      background: var(--blue);
    }
    .stat-card span,
    .stat-card small {
      color: var(--muted);
      font-weight: 700;
    }
    .stat-card strong {
      font-size: 30px;
      line-height: 1;
      color: var(--blue);
    }
    .stat-card.tone-blue { background: #f8fbff; }
    .stat-card.tone-blue::before { background: var(--blue); }
    .stat-card.tone-blue strong { color: var(--blue); }
    .stat-card.tone-green { background: #f7fcf8; }
    .stat-card.tone-green::before { background: var(--green); }
    .stat-card.tone-green strong { color: var(--green); }
    .stat-card.tone-red { background: #fff8f7; }
    .stat-card.tone-red::before { background: var(--red); }
    .stat-card.tone-red strong { color: var(--red); }
    .stat-card.tone-yellow { background: #fffdf2; }
    .stat-card.tone-yellow::before { background: var(--yellow); }
    .stat-card.tone-yellow strong { color: #b06000; }
    .work-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(300px, 0.7fr);
      gap: 14px;
      margin-bottom: 14px;
    }
    .tool-panel {
      padding: 16px;
    }
    .section-head,
    .editor-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .form-grid .wide { grid-column: 1 / -1; }
    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    select,
    input {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: var(--surface);
      color: var(--text);
      font: inherit;
      outline: none;
    }
    select:focus,
    input:focus,
    textarea:focus {
      border-color: var(--blue);
      box-shadow: 0 0 0 3px rgba(26, 115, 232, 0.14);
    }
    .run-meta {
      display: grid;
      gap: 10px;
      margin: 0 0 16px;
    }
    .run-meta div {
      min-width: 0;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }
    .run-meta dt {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .run-meta dd {
      margin: 2px 0 0;
      overflow-wrap: anywhere;
      font-weight: 700;
    }
    .log-panel { padding: 0; overflow: hidden; }
    .log-panel .section-head {
      min-height: 56px;
      padding: 14px 16px;
      margin: 0;
      border-bottom: 1px solid var(--line);
    }
    .mini-state,
    .save-state {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }
    pre {
      min-height: 320px;
      max-height: 520px;
      margin: 0;
      overflow: auto;
      padding: 16px;
      white-space: pre-wrap;
      font: 13px/1.5 Consolas, "Courier New", monospace;
      background: #202124;
      color: #f8fafd;
    }
    .settings-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .editor-card {
      overflow: hidden;
    }
    .editor-head {
      min-height: 62px;
      padding: 14px 16px;
      margin: 0;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }
    textarea {
      width: 100%;
      min-height: 210px;
      display: block;
      resize: vertical;
      border: 0;
      border-bottom: 1px solid var(--line);
      padding: 14px 16px;
      color: var(--text);
      background: #fff;
      font: 13px/1.5 Consolas, "Courier New", monospace;
      outline: none;
    }
    .editor-actions {
      padding: 12px 16px;
      justify-content: flex-end;
      background: #fff;
    }
    @media (max-width: 960px) {
      .appbar-inner { align-items: flex-start; flex-direction: column; padding: 12px 16px; }
      .nav { width: 100%; }
      .nav a { flex: 1; justify-content: center; }
      main { padding: 18px 16px 28px; }
      .hero-band { align-items: flex-start; flex-direction: column; }
      .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .work-grid, .settings-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 560px) {
      h1 { font-size: 24px; }
      .stats-grid, .form-grid { grid-template-columns: 1fr; }
      .status { width: 100%; justify-content: center; }
    }
  </style>
</head>
<body>
  <header class="appbar">
    <div class="appbar-inner">
      <a class="brand" href="/">
        <span class="brand-mark" aria-hidden="true"></span>
        <span>Xeffy Bot</span>
      </a>
      <nav class="nav" aria-label="Primary">
        <a class="$dashboard_class" href="/">Dashboard</a>
        <a class="$settings_class" href="/settings">Settings</a>
      </nav>
      <span id="statusBadge" class="status $status_class">$status_text</span>
    </div>
  </header>
  <main>
    $notice
    $body
  </main>
  <script>
    async function refreshLog() {
      var log = document.getElementById("log");
      if (!log) return;
      var state = document.getElementById("logState");
      try {
        var res = await fetch("/log?t=" + Date.now());
        log.textContent = await res.text();
        log.scrollTop = log.scrollHeight;
        if (state) state.textContent = "synced";
      } catch (error) {
        if (state) state.textContent = "offline";
      }
    }

    async function refreshStatus() {
      var badge = document.getElementById("statusBadge");
      if (!badge) return;
      try {
        var res = await fetch("/state?t=" + Date.now());
        var data = await res.json();
        badge.textContent = data.statusText;
        badge.className = "status " + data.statusClass;
      } catch (error) {
        badge.textContent = "Offline";
        badge.className = "status idle";
      }
    }

    document.querySelectorAll(".editor-card").forEach(function(form) {
      var textarea = form.querySelector("textarea");
      var state = form.querySelector(".save-state");
      var fileName = form.getAttribute("data-file");

      textarea.addEventListener("input", function() {
        state.textContent = "Unsaved";
        state.style.color = "#d93025";
      });

      form.addEventListener("submit", async function(event) {
        event.preventDefault();
        state.textContent = "Saving";
        state.style.color = "#5f6368";
        var body = new URLSearchParams();
        body.set("file", fileName);
        body.set("content", textarea.value);
        try {
          var res = await fetch("/save-file", {
            method: "POST",
            headers: {"Content-Type": "application/x-www-form-urlencoded"},
            body: body.toString()
          });
          var data = await res.json();
          if (!data.ok) throw new Error(data.message || "Save failed");
          textarea.value = data.content;
          state.textContent = "Saved";
          state.style.color = "#188038";
        } catch (error) {
          state.textContent = "Failed";
          state.style.color = "#d93025";
        }
      });

      var reload = form.querySelector("[data-reload]");
      reload.addEventListener("click", async function() {
        var res = await fetch("/file?name=" + encodeURIComponent(fileName));
        var data = await res.json();
        textarea.value = data.content || "";
        state.textContent = "Saved";
        state.style.color = "#188038";
      });
    });

    refreshLog();
    refreshStatus();
    setInterval(refreshLog, 2000);
    setInterval(refreshStatus, 2000);
  </script>
</body>
</html>""")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/log":
            self.send_text(read_text(str(LOG_PATH.relative_to(ROOT))))
            return

        if path == "/state":
            self.send_json(status_data())
            return

        if path == "/file":
            values = parse_qs(parsed.query, keep_blank_values=True)
            file_name = values.get("name", [""])[0]
            if file_name not in EDITABLE_FILES:
                self.send_json({"ok": False, "message": "Unknown file"}, status=400)
                return
            self.send_json({"ok": True, "content": read_text(file_name)})
            return

        if path == "/settings":
            self.send_html(render_settings())
            return

        self.send_html(render_dashboard())

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        values = parse_qs(body, keep_blank_values=True)

        if parsed.path == "/stop":
            stopped = stop_bot()
            message = "Bot stop signal sent." if stopped else "Bot is not running."
            self.send_html(render_dashboard(message))
            return

        if parsed.path == "/run":
            selected_mode = values.get(
                "selected_mode",
                values.get("mode", ["daily"]),
            )[0]
            options = normalize_run_options(
                values.get("accounts", ["all"])[0],
                selected_mode,
                values.get("account_number", ["1"])[0],
            )
            started = start_bot(options, selected_mode)
            message = "Bot started." if started else "Bot is already running."
            if not started:
                message = "Bot is already running. Stop it before changing mode."
            self.send_html(render_dashboard(message))
            return

        if parsed.path == "/save-file":
            file_name = values.get("file", [""])[0]
            if file_name not in EDITABLE_FILES:
                self.send_json({"ok": False, "message": "Unknown file"}, status=400)
                return
            write_text(file_name, values.get("content", [""])[0])
            self.send_json({"ok": True, "content": read_text(file_name)})
            return

        if parsed.path == "/save-run":
            for key, value in values.items():
                if key.startswith("file::"):
                    file_name = key.split("::", 1)[1]
                    if file_name in EDITABLE_FILES:
                        write_text(file_name, value[0])
            self.send_html(render_dashboard("Files saved."))
            return

        self.send_html(render_dashboard("Unknown action."))

    def send_html(self, text, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def send_text(self, text, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, format, *args):
        return


def main():
    os.chdir(ROOT)
    RUN_DIR.mkdir(exist_ok=True)
    if not LOG_PATH.exists():
        LOG_PATH.write_text("", encoding="utf-8")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Xeffy web GUI: http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop the GUI server.")
    server.serve_forever()


if __name__ == "__main__":
    main()
