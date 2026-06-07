import html
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs


HOST = "127.0.0.1"
PORT = 8787
ROOT = Path(__file__).resolve().parent
RUN_DIR = ROOT / ".web_runs"
LOG_PATH = RUN_DIR / "latest.log"

EDITABLE_FILES = [
    ".env",
    "config.json",
    "sessions.txt",
    "data.txt",
    "channel.txt",
    "answers.txt",
    "proxy.txt",
    "useragents.txt",
    "xtoken.txt",
]

BOT_PROCESS = None
BOT_LOCK = threading.Lock()


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


def start_bot(accounts, mode, account_number):
    global BOT_PROCESS

    with BOT_LOCK:
        if BOT_PROCESS is not None and BOT_PROCESS.poll() is None:
            return False

        RUN_DIR.mkdir(exist_ok=True)
        log_file = open(LOG_PATH, "w", encoding="utf-8")
        command = [
            python_executable(),
            "-u",
            "xeffy_bot.py",
            "--accounts",
            accounts,
            "--mode",
            mode,
            "--account-number",
            str(account_number or 1),
        ]
        BOT_PROCESS = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return True


def stop_bot():
    global BOT_PROCESS

    with BOT_LOCK:
        if BOT_PROCESS is None or BOT_PROCESS.poll() is not None:
            return False
        BOT_PROCESS.terminate()
        return True


def render_page(message=""):
    running = process_running()
    file_blocks = []
    for file_name in EDITABLE_FILES:
        value = html.escape(read_text(file_name))
        file_blocks.append(
            f"""
            <section class="panel editor">
              <div class="panel-head">
                <h2>{html.escape(file_name)}</h2>
              </div>
              <textarea name="file::{html.escape(file_name)}" spellcheck="false">{value}</textarea>
            </section>
            """
        )

    status_text = "Running" if running else "Idle"
    status_class = "running" if running else "idle"
    notice = f"<div class='notice'>{html.escape(message)}</div>" if message else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Xeffy Bot Control</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --ink: #172033;
      --muted: #687386;
      --line: #d8dee9;
      --panel: #ffffff;
      --accent: #0b7a75;
      --accent-strong: #075f5b;
      --danger: #b42318;
      --soft: #e9f4f3;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 "Segoe UI", Arial, sans-serif;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 2;
      border-bottom: 1px solid var(--line);
      background: rgba(245, 247, 251, 0.96);
      backdrop-filter: blur(8px);
    }}
    .topbar {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    h1 {{
      margin: 0;
      font-size: 20px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 6px;
      font-weight: 600;
      border: 1px solid var(--line);
      background: var(--panel);
    }}
    .status.running {{ color: var(--accent-strong); background: var(--soft); }}
    .status.idle {{ color: var(--muted); }}
    main {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 20px;
    }}
    .notice {{
      margin-bottom: 14px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--accent-strong);
      font-weight: 600;
    }}
    .controls {{
      display: grid;
      grid-template-columns: repeat(4, minmax(150px, 1fr)) auto auto;
      gap: 10px;
      align-items: end;
      margin-bottom: 18px;
    }}
    label {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-weight: 600;
      font-size: 12px;
    }}
    select, input {{
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 9px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}
    button {{
      min-height: 38px;
      border: 1px solid transparent;
      border-radius: 6px;
      padding: 8px 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }}
    .primary {{ background: var(--accent); color: #fff; }}
    .primary:hover {{ background: var(--accent-strong); }}
    .secondary {{ background: #fff; border-color: var(--line); color: var(--ink); }}
    .danger {{ background: #fff; border-color: #f3b5ae; color: var(--danger); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }}
    .panel-head {{
      min-height: 42px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    h2 {{
      margin: 0;
      font-size: 14px;
      letter-spacing: 0;
    }}
    textarea {{
      width: 100%;
      min-height: 170px;
      resize: vertical;
      border: 0;
      padding: 12px;
      font: 13px/1.45 Consolas, "Courier New", monospace;
      color: var(--ink);
      background: #fff;
      outline: none;
    }}
    .log {{
      margin-top: 14px;
    }}
    pre {{
      min-height: 260px;
      max-height: 460px;
      margin: 0;
      overflow: auto;
      padding: 12px;
      white-space: pre-wrap;
      font: 13px/1.45 Consolas, "Courier New", monospace;
      background: #111827;
      color: #e5e7eb;
    }}
    @media (max-width: 900px) {{
      .controls {{ grid-template-columns: 1fr 1fr; }}
      .grid {{ grid-template-columns: 1fr; }}
      .topbar {{ align-items: flex-start; flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <h1>Xeffy Bot Control</h1>
      <span class="status {status_class}">{status_text}</span>
    </div>
  </header>
  <main>
    {notice}
    <form method="post" action="/save-run">
      <div class="controls">
        <label>Accounts
          <select name="accounts">
            <option value="all">All accounts</option>
            <option value="one">One account</option>
            <option value="start">Start from account</option>
          </select>
        </label>
        <label>Account number
          <input name="account_number" type="number" min="1" value="1">
        </label>
        <label>Mode
          <select name="mode">
            <option value="daily">Daily: check-in + tasks</option>
            <option value="full">Full: join + check-in + tasks</option>
            <option value="checkin">Check-in only</option>
          </select>
        </label>
        <label>Action
          <select name="action">
            <option value="save">Save only</option>
            <option value="run">Save and run</option>
          </select>
        </label>
        <button class="primary" type="submit">Apply</button>
        <button class="secondary" type="button" onclick="location.href='/'">Refresh</button>
      </div>
      <div class="grid">
        {''.join(file_blocks)}
      </div>
    </form>
    <form method="post" action="/stop" style="margin-top:14px">
      <button class="danger" type="submit">Stop bot</button>
    </form>
    <section class="panel log">
      <div class="panel-head">
        <h2>Live log</h2>
      </div>
      <pre id="log">Loading log...</pre>
    </section>
  </main>
  <script>
    async function refreshLog() {{
      const res = await fetch('/log?t=' + Date.now());
      document.getElementById('log').textContent = await res.text();
    }}
    refreshLog();
    setInterval(refreshLog, 2000);
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/log"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(read_text(str(LOG_PATH.relative_to(ROOT))).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(render_page().encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        values = parse_qs(body, keep_blank_values=True)

        if self.path == "/stop":
            stopped = stop_bot()
            self.respond_page("Bot stop signal sent." if stopped else "Bot is not running.")
            return

        if self.path == "/save-run":
            for key, value in values.items():
                if key.startswith("file::"):
                    file_name = key.split("::", 1)[1]
                    if file_name in EDITABLE_FILES:
                        write_text(file_name, value[0])

            action = values.get("action", ["save"])[0]
            if action == "run":
                started = start_bot(
                    values.get("accounts", ["all"])[0],
                    values.get("mode", ["daily"])[0],
                    values.get("account_number", ["1"])[0],
                )
                self.respond_page("Bot started." if started else "Bot is already running.")
            else:
                self.respond_page("Files saved.")
            return

        self.respond_page("Unknown action.")

    def respond_page(self, message):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(render_page(message).encode("utf-8"))

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
