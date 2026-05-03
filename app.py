"""
Kin Assistant — BeeWare Toga App
==================================
Kin is the subconscious. Senku is the brain.
Chat routes through Senku (Discord bot) via webhook/API.
Local modules (calc, tasks, notes, reminders, schedule) run offline.

Build in Termux:
  pkg install python git
  pip install briefcase toga
  briefcase create android
  briefcase build android
  briefcase run android

Remote updates:
  Kin checks UPDATE_URL on launch for a new version tag.
  If newer, downloads and replaces itself, then restarts.
"""

import os, json, math, random, datetime, threading, urllib.request, sys
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER, LEFT, RIGHT

# ── Config (edit these) ────────────────────────────────────────────────────────
SENKU_WEBHOOK   = os.environ.get("KIN_WEBHOOK", "")       # Discord webhook URL
SENKU_BOT_TOKEN = os.environ.get("KIN_BOT_TOKEN", "")     # Bot token for reading replies
SENKU_CHANNEL   = os.environ.get("KIN_CHANNEL_ID", "")    # Channel ID Kin talks in
UPDATE_URL      = os.environ.get("KIN_UPDATE_URL",
    "https://raw.githubusercontent.com/YOUR_USERNAME/kin/main/version.json")
UPDATE_RAW      = os.environ.get("KIN_UPDATE_RAW",
    "https://raw.githubusercontent.com/YOUR_USERNAME/kin/main/src/kin/app.py")
VERSION         = "2.1.0"

# ── Data paths ─────────────────────────────────────────────────────────────────
DATA_DIR       = os.path.expanduser("~/.kin")
os.makedirs(DATA_DIR, exist_ok=True)
TASKS_FILE     = os.path.join(DATA_DIR, "kin_tasks.json")
NOTES_FILE     = os.path.join(DATA_DIR, "kin_notes.json")
REMINDERS_FILE = os.path.join(DATA_DIR, "kin_reminders.json")
CONFIG_FILE    = os.path.join(DATA_DIR, "kin_config.json")

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except Exception: pass
    return default

def save_json(path, data):
    with open(path, "w") as f: json.dump(data, f, indent=2)

def load_config():
    return load_json(CONFIG_FILE, {
        "webhook": SENKU_WEBHOOK,
        "bot_token": SENKU_BOT_TOKEN,
        "channel_id": SENKU_CHANNEL,
        "auto_update": True,
    })

def save_config(cfg):
    save_json(CONFIG_FILE, cfg)

# ── Colours ───────────────────────────────────────────────────────────────────
BG      = "#0a0a0f"
SURFACE = "#11111a"
PANEL   = "#16161f"
ACCENT  = "#7cf2c5"
ACCENT2 = "#4fc3f7"
MUTED   = "#5a6070"
TEXT    = "#e2e8f0"
DANGER  = "#f87171"

# ── Helpers ───────────────────────────────────────────────────────────────────
def now_time():  return datetime.datetime.now().strftime("%I:%M %p")
def now_date():  return datetime.datetime.now().strftime("%A, %d %B %Y")
def today_str(): return datetime.date.today().isoformat()

TIMETABLE = {
    "Monday":    "Classes 8 AM – 2 PM",
    "Tuesday":   "Free day",
    "Wednesday": "Lab session at 10 AM",
    "Thursday":  "Lectures 9 AM – 1 PM",
    "Friday":    "Wrap-up session at 11 AM",
    "Saturday":  "No classes",
    "Sunday":    "No classes",
}

# ── Local intents (offline fallback) ──────────────────────────────────────────
LOCAL_INTENTS = [
    {"p": ["hello","hi","hey","sup"],
     "r": ["Hey! Routing you to Senku…", "Hi. Let me get Senku."]},
    {"p": ["time"], "r": [lambda: f"It's {now_time()}."]},
    {"p": ["date","today"], "r": [lambda: f"Today is {now_date()}."]},
    {"p": ["version"], "r": [f"Kin v{VERSION}"]},
    {"p": ["joke","funny"],
     "r": [
         "Why do programmers prefer dark mode? Light attracts bugs.",
         "My Wi-Fi is 'incorrect'. When asked, I say it's 'incorrect'.",
     ]},
]

def local_response(text):
    q = text.lower()
    for intent in LOCAL_INTENTS:
        for p in intent["p"]:
            if p in q:
                r = random.choice(intent["r"])
                return r() if callable(r) else r
    return None

# ── Senku bridge ──────────────────────────────────────────────────────────────
def send_to_senku(message: str, on_reply, on_error):
    """
    Send message to Senku via Discord webhook.
    Senku processes it and (optionally) posts reply to the channel.
    We then fetch the latest message from the channel as the reply.
    """
    cfg = load_config()
    webhook = cfg.get("webhook", "")
    token   = cfg.get("bot_token", "")
    channel = cfg.get("channel_id", "")

    def _work():
        if not webhook:
            on_error("Senku not configured. Go to Settings → Senku Link.")
            return
        try:
            # 1. Send to Senku via webhook
            payload = json.dumps({
                "content": f"[KIN] {message}",
                "username": "Kin"
            }).encode()
            req = urllib.request.Request(
                webhook,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=8)

            # 2. If bot token + channel set, poll for Senku's reply
            if token and channel:
                import time
                time.sleep(2)  # give Senku time to respond
                api_url = f"https://discord.com/api/v10/channels/{channel}/messages?limit=5"
                req2 = urllib.request.Request(
                    api_url,
                    headers={"Authorization": f"Bot {token}"}
                )
                resp = urllib.request.urlopen(req2, timeout=8)
                msgs = json.loads(resp.read())
                # Find first message NOT from Kin (i.e. Senku's reply)
                for m in msgs:
                    if "[KIN]" not in m.get("content", ""):
                        on_reply(m["content"])
                        return
                on_reply("Senku is thinking…")
            else:
                on_reply("✓ Sent to Senku.")
        except Exception as e:
            on_error(f"Senku unreachable: {e}")

    threading.Thread(target=_work, daemon=True).start()

# ── Remote update ─────────────────────────────────────────────────────────────
def check_for_update(on_update_available, on_current):
    def _work():
        cfg = load_config()
        if not cfg.get("auto_update", True):
            return
        try:
            req = urllib.request.Request(UPDATE_URL)
            resp = urllib.request.urlopen(req, timeout=6)
            data = json.loads(resp.read())
            remote_version = data.get("version", VERSION)
            if remote_version != VERSION:
                on_update_available(remote_version)
            else:
                on_current()
        except Exception:
            pass  # silent fail — no network or no repo yet
    threading.Thread(target=_work, daemon=True).start()

def apply_update(on_done, on_error):
    def _work():
        try:
            req = urllib.request.Request(UPDATE_RAW)
            resp = urllib.request.urlopen(req, timeout=15)
            new_code = resp.read()
            this_file = os.path.abspath(__file__)
            backup = this_file + ".bak"
            os.rename(this_file, backup)
            with open(this_file, "wb") as f:
                f.write(new_code)
            on_done()
        except Exception as e:
            on_error(str(e))
    threading.Thread(target=_work, daemon=True).start()


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  MAIN APP                                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
class KinApp(toga.App):

    def startup(self):
        self.main_window = toga.MainWindow(title=f"Kin  v{VERSION}")
        self.main_window.content = self._build_ui()
        self.main_window.show()
        # Check for updates in background
        check_for_update(
            on_update_available=self._prompt_update,
            on_current=lambda: None
        )
        # Check due reminders
        self._check_reminders()

    # ── UI builder ──────────────────────────────────────────────────────────
    def _build_ui(self):
        # Option box (tab bar simulation via OptionContainer)
        self._tabs = toga.OptionContainer(
            content=[
                toga.OptionItem("💬 Chat",     self._chat_tab()),
                toga.OptionItem("🧮 Calc",     self._calc_tab()),
                toga.OptionItem("✅ Tasks",    self._tasks_tab()),
                toga.OptionItem("📝 Notes",    self._notes_tab()),
                toga.OptionItem("🔔 Remind",   self._reminders_tab()),
                toga.OptionItem("📅 Schedule", self._schedule_tab()),
                toga.OptionItem("⚙ Settings",  self._settings_tab()),
            ],
            style=Pack(flex=1)
        )
        return self._tabs

    # ── CHAT ────────────────────────────────────────────────────────────────
    def _chat_tab(self):
        self._chat_log = toga.MultilineTextInput(
            readonly=True,
            style=Pack(flex=1, background_color=PANEL, color=TEXT, font_size=13)
        )
        self._chat_input = toga.TextInput(
            placeholder="Talk to Kin / Senku…",
            style=Pack(flex=1, font_size=14)
        )
        send_btn = toga.Button(
            "Send",
            on_press=self._chat_send,
            style=Pack(width=80, background_color=ACCENT, color=BG, font_weight="bold")
        )
        input_row = toga.Box(
            children=[self._chat_input, send_btn],
            style=Pack(direction=ROW, padding=6, spacing=6)
        )
        box = toga.Box(
            children=[self._chat_log, input_row],
            style=Pack(direction=COLUMN, flex=1, background_color=BG)
        )
        # Greeting
        h = datetime.datetime.now().hour
        g = ("Good morning!" if h < 12 else
             "Good afternoon." if h < 18 else
             "Good evening." if h < 22 else "Still up?")
        self._log(f"[Kin]  {g} I'm online. Senku is my brain — I'll relay your messages.")
        return box

    def _log(self, text):
        current = self._chat_log.value or ""
        self._chat_log.value = (current + "\n" + text).strip()

    def _chat_send(self, widget=None):
        text = self._chat_input.value.strip()
        if not text: return
        self._chat_input.value = ""
        self._log(f"\n[You]  {text}")

        # Try local first (time, date, jokes, version)
        local = local_response(text)
        if local:
            self._log(f"[Kin]  {local}")
            return

        # Route to Senku
        self._log("[Kin]  → Routing to Senku…")
        send_to_senku(
            text,
            on_reply=lambda r: self._on_main(lambda: self._log(f"[Senku]  {r}")),
            on_error=lambda e: self._on_main(lambda: self._log(f"[Kin]  ⚠ {e}"))
        )

    def _on_main(self, fn):
        """Run fn on main thread (Toga requirement)."""
        self.loop.call_soon_threadsafe(fn)

    # ── CALCULATOR ──────────────────────────────────────────────────────────
    def _calc_tab(self):
        self._calc_expr   = ""
        self._calc_last   = None

        self._calc_expr_lbl   = toga.Label("", style=Pack(
            color=MUTED, font_size=11, text_align=RIGHT, padding_bottom=2))
        self._calc_result_lbl = toga.Label("0", style=Pack(
            color=ACCENT, font_size=28, font_weight="bold", text_align=RIGHT, padding_bottom=6))

        display = toga.Box(
            children=[self._calc_expr_lbl, self._calc_result_lbl],
            style=Pack(direction=COLUMN, background_color=PANEL,
                       padding=10, margin_bottom=8)
        )

        def btn(label, cb, color=TEXT, bg=PANEL):
            return toga.Button(label, on_press=cb,
                style=Pack(flex=1, height=52, background_color=bg,
                           color=color, font_weight="bold", font_size=15, margin=3))

        def inp(v):
            return lambda w: self._ci(v)
        def fn(f):
            return lambda w: self._cf(f)

        rows = [
            [btn("AC", fn("clear"), DANGER, PANEL), btn("⌫", fn("del"), ACCENT2, PANEL),
             btn("%",  inp("%"),  ACCENT2, PANEL),  btn("÷", inp("/"), ACCENT2, PANEL)],
            [btn("7",  inp("7")), btn("8", inp("8")), btn("9", inp("9")),
             btn("×",  inp("*"),  ACCENT2, PANEL)],
            [btn("4",  inp("4")), btn("5", inp("5")), btn("6", inp("6")),
             btn("−",  inp("-"),  ACCENT2, PANEL)],
            [btn("1",  inp("1")), btn("2", inp("2")), btn("3", inp("3")),
             btn("+",  inp("+"),  ACCENT2, PANEL)],
            [btn("0",  inp("0")), btn(".", inp(".")),
             btn("xʸ", inp("**"), "#f472b6", PANEL), btn("=", fn("eq"), BG, ACCENT)],
            [btn("√",  fn("sqrt"), "#f472b6", PANEL), btn("sin", fn("sin"), "#f472b6", PANEL),
             btn("cos", fn("cos"), "#f472b6", PANEL), btn("π", fn("pi"), "#f472b6", PANEL)],
        ]

        grid = toga.Box(style=Pack(direction=COLUMN, flex=1))
        for row in rows:
            grid.add(toga.Box(children=row, style=Pack(direction=ROW)))

        return toga.Box(
            children=[display, grid],
            style=Pack(direction=COLUMN, flex=1, background_color=BG, padding=8)
        )

    def _ci(self, val):
        if self._calc_last is not None and val not in "+-*/%**":
            self._calc_expr = ""; self._calc_last = None
        if self._calc_last is not None and val in "+-*/%**":
            self._calc_expr = str(self._calc_last); self._calc_last = None
        self._calc_expr += val
        self._calc_expr_lbl.text = self._calc_expr
        self._calc_result_lbl.text = self._calc_expr or "0"

    def _cf(self, fn):
        if fn == "clear":
            self._calc_expr = ""; self._calc_last = None
            self._calc_expr_lbl.text = ""; self._calc_result_lbl.text = "0"; return
        if fn == "del":
            self._calc_expr = self._calc_expr[:-1]
            self._calc_expr_lbl.text = self._calc_expr
            self._calc_result_lbl.text = self._calc_expr or "0"; return
        try:
            base = float(self._calc_expr) if self._calc_expr else 0
            if fn == "sqrt": res = math.sqrt(base)
            elif fn == "sin": res = math.sin(math.radians(base))
            elif fn == "cos": res = math.cos(math.radians(base))
            elif fn == "pi":  self._ci(str(math.pi)); return
            elif fn == "eq":
                res = eval(self._calc_expr, {"__builtins__": {}}, {
                    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
                    "pi": math.pi, "e": math.e, "abs": abs,
                })
            else: return
            disp = int(res) if isinstance(res, float) and res == int(res) else round(res, 8)
            self._calc_expr_lbl.text = self._calc_expr + " ="
            self._calc_result_lbl.text = str(disp)
            self._calc_last = disp; self._calc_expr = str(disp)
        except Exception:
            self._calc_result_lbl.text = "Error"; self._calc_expr = ""

    # ── TASKS ───────────────────────────────────────────────────────────────
    def _tasks_tab(self):
        self._task_input = toga.TextInput(
            placeholder="New task…", style=Pack(flex=1, font_size=14))
        add_btn = toga.Button("Add", on_press=self._add_task,
            style=Pack(width=70, background_color=ACCENT, color=BG, font_weight="bold"))
        self._task_scroll = toga.ScrollContainer(
            style=Pack(flex=1), horizontal=False)
        self._task_box = toga.Box(style=Pack(direction=COLUMN, padding=4))
        self._task_scroll.content = self._task_box
        self._render_tasks()
        return toga.Box(
            children=[
                toga.Box(children=[self._task_input, add_btn],
                         style=Pack(direction=ROW, padding=8, spacing=6)),
                self._task_scroll,
            ],
            style=Pack(direction=COLUMN, flex=1, background_color=BG)
        )

    def _add_task(self, widget=None):
        text = self._task_input.value.strip()
        if not text: return
        tasks = load_json(TASKS_FILE, [])
        tasks.append({"task": text, "added": today_str()})
        save_json(TASKS_FILE, tasks)
        self._task_input.value = ""
        self._render_tasks()

    def _render_tasks(self):
        self._task_box.clear()
        tasks = load_json(TASKS_FILE, [])
        if not tasks:
            self._task_box.add(toga.Label("No tasks yet.",
                style=Pack(color=MUTED, font_size=13, padding=12)))
            return
        for i, t in enumerate(tasks):
            lbl = toga.Label(f"• {t['task']}",
                style=Pack(flex=1, color=TEXT, font_size=13))
            meta = toga.Label(t.get("added",""),
                style=Pack(color=MUTED, font_size=10, width=90, text_align=RIGHT))
            idx = i
            del_btn = toga.Button("✕", on_press=lambda w, x=idx: self._del_task(x),
                style=Pack(width=32, height=32, background_color=PANEL, color=DANGER))
            row = toga.Box(
                children=[lbl, meta, del_btn],
                style=Pack(direction=ROW, padding=6, margin_bottom=4,
                           background_color=PANEL)
            )
            self._task_box.add(row)

    def _del_task(self, idx):
        tasks = load_json(TASKS_FILE, [])
        tasks.pop(idx)
        save_json(TASKS_FILE, tasks)
        self._render_tasks()

    # ── NOTES ───────────────────────────────────────────────────────────────
    def _notes_tab(self):
        self._note_title = toga.TextInput(
            placeholder="Title…", style=Pack(flex=1, font_size=14))
        self._note_body = toga.MultilineTextInput(
            placeholder="Note content…",
            style=Pack(height=90, font_size=13, background_color=PANEL, color=TEXT))
        save_btn = toga.Button("Save Note", on_press=self._add_note,
            style=Pack(background_color=ACCENT, color=BG, font_weight="bold", padding_top=4))
        self._note_scroll = toga.ScrollContainer(style=Pack(flex=1), horizontal=False)
        self._note_box = toga.Box(style=Pack(direction=COLUMN, padding=4))
        self._note_scroll.content = self._note_box
        self._render_notes()
        return toga.Box(
            children=[
                toga.Box(children=[self._note_title],
                         style=Pack(direction=ROW, padding=(8,8,4,8))),
                self._note_body,
                toga.Box(children=[save_btn],
                         style=Pack(direction=ROW, padding=(4,8,8,8))),
                self._note_scroll,
            ],
            style=Pack(direction=COLUMN, flex=1, background_color=BG)
        )

    def _add_note(self, widget=None):
        title = self._note_title.value.strip() or "Untitled"
        body  = self._note_body.value.strip()
        if not body and title == "Untitled": return
        notes = load_json(NOTES_FILE, [])
        notes.insert(0, {"title": title, "body": body, "date": today_str()})
        save_json(NOTES_FILE, notes)
        self._note_title.value = ""
        self._note_body.value  = ""
        self._render_notes()

    def _render_notes(self):
        self._note_box.clear()
        notes = load_json(NOTES_FILE, [])
        if not notes:
            self._note_box.add(toga.Label("No notes yet.",
                style=Pack(color=MUTED, font_size=13, padding=12)))
            return
        for i, n in enumerate(notes):
            title_lbl = toga.Label(n["title"],
                style=Pack(flex=1, color=ACCENT, font_size=13, font_weight="bold"))
            idx = i
            del_btn = toga.Button("✕", on_press=lambda w, x=idx: self._del_note(x),
                style=Pack(width=32, height=28, background_color=PANEL, color=DANGER))
            header = toga.Box(children=[title_lbl, del_btn],
                style=Pack(direction=ROW, margin_bottom=2))
            body_lbl = toga.Label(n["body"],
                style=Pack(color=TEXT, font_size=12))
            date_lbl = toga.Label(n.get("date",""),
                style=Pack(color=MUTED, font_size=10, margin_top=4))
            card = toga.Box(
                children=[header, body_lbl, date_lbl],
                style=Pack(direction=COLUMN, padding=10, margin_bottom=6,
                           background_color=PANEL)
            )
            self._note_box.add(card)

    def _del_note(self, idx):
        notes = load_json(NOTES_FILE, [])
        notes.pop(idx)
        save_json(NOTES_FILE, notes)
        self._render_notes()

    # ── REMINDERS ───────────────────────────────────────────────────────────
    def _reminders_tab(self):
        self._rem_text = toga.TextInput(
            placeholder="Reminder text…", style=Pack(flex=1, font_size=14))
        self._rem_date = toga.TextInput(
            placeholder="Date  YYYY-MM-DD",
            value=today_str(), style=Pack(flex=1, font_size=13))
        self._rem_time = toga.TextInput(
            placeholder="Time  HH:MM", style=Pack(width=110, font_size=13))
        set_btn = toga.Button("Set Reminder", on_press=self._add_reminder,
            style=Pack(background_color=ACCENT, color=BG, font_weight="bold"))
        self._rem_scroll = toga.ScrollContainer(style=Pack(flex=1), horizontal=False)
        self._rem_box = toga.Box(style=Pack(direction=COLUMN, padding=4))
        self._rem_scroll.content = self._rem_box
        self._render_reminders()
        return toga.Box(
            children=[
                toga.Box(children=[self._rem_text],
                         style=Pack(direction=ROW, padding=(8,8,4,8))),
                toga.Box(children=[self._rem_date, self._rem_time],
                         style=Pack(direction=ROW, padding=(0,8,4,8), spacing=6)),
                toga.Box(children=[set_btn],
                         style=Pack(direction=ROW, padding=(0,8,8,8))),
                self._rem_scroll,
            ],
            style=Pack(direction=COLUMN, flex=1, background_color=BG)
        )

    def _add_reminder(self, widget=None):
        text = self._rem_text.value.strip()
        date = self._rem_date.value.strip()
        time = self._rem_time.value.strip()
        if not text or not date or not time: return
        try:
            dt = datetime.datetime.fromisoformat(f"{date} {time}:00")
        except ValueError: return
        reminders = load_json(REMINDERS_FILE, [])
        reminders.append({"text": text, "time": dt.isoformat()})
        save_json(REMINDERS_FILE, reminders)
        self._rem_text.value = ""
        self._rem_time.value = ""
        self._render_reminders()

    def _render_reminders(self):
        self._rem_box.clear()
        reminders = load_json(REMINDERS_FILE, [])
        if not reminders:
            self._rem_box.add(toga.Label("No reminders set.",
                style=Pack(color=MUTED, font_size=13, padding=12)))
            return
        now = datetime.datetime.now()
        for i, r in enumerate(reminders):
            try:
                dt = datetime.datetime.fromisoformat(r["time"])
                dt_str = dt.strftime("%d %b  %I:%M %p")
                past = dt < now
            except Exception:
                dt_str = r.get("time",""); past = False
            color = MUTED if past else TEXT
            lbl  = toga.Label(r["text"],
                style=Pack(flex=1, color=color, font_size=13))
            meta = toga.Label(dt_str,
                style=Pack(color=MUTED, font_size=10, width=110, text_align=RIGHT))
            idx = i
            del_btn = toga.Button("✕", on_press=lambda w, x=idx: self._del_reminder(x),
                style=Pack(width=32, height=32, background_color=PANEL, color=DANGER))
            row = toga.Box(children=[lbl, meta, del_btn],
                style=Pack(direction=ROW, padding=6, margin_bottom=4,
                           background_color=PANEL))
            self._rem_box.add(row)

    def _del_reminder(self, idx):
        reminders = load_json(REMINDERS_FILE, [])
        reminders.pop(idx)
        save_json(REMINDERS_FILE, reminders)
        self._render_reminders()

    def _check_reminders(self):
        reminders = load_json(REMINDERS_FILE, [])
        now = datetime.datetime.now()
        due = [r for r in reminders
               if datetime.datetime.fromisoformat(r["time"]) <= now
               if "time" in r]
        if due:
            msg = "\n".join(f"• {r['text']}" for r in due)
            self.main_window.info_dialog("🔔 Reminders Due", msg)

    # ── SCHEDULE ────────────────────────────────────────────────────────────
    def _schedule_tab(self):
        today = datetime.datetime.now().strftime("%A")
        box = toga.Box(style=Pack(direction=COLUMN, padding=10, background_color=BG))
        for day, entry in TIMETABLE.items():
            is_today = day == today
            bg = "#0d1f18" if is_today else PANEL
            day_lbl = toga.Label(
                day[:3].upper() + (" ◀" if is_today else ""),
                style=Pack(
                    color=ACCENT if is_today else MUTED,
                    font_size=11, font_weight="bold", width=60
                )
            )
            entry_lbl = toga.Label(
                entry,
                style=Pack(flex=1, color=TEXT if not is_today else BG,
                           font_size=13)
            )
            row = toga.Box(
                children=[day_lbl, entry_lbl],
                style=Pack(direction=ROW, padding=10, margin_bottom=5,
                           background_color=bg)
            )
            box.add(row)
        return toga.ScrollContainer(content=box, horizontal=False,
                                    style=Pack(flex=1))

    # ── SETTINGS ────────────────────────────────────────────────────────────
    def _settings_tab(self):
        cfg = load_config()
        self._s_webhook = toga.TextInput(
            value=cfg.get("webhook",""),
            placeholder="Discord Webhook URL",
            style=Pack(flex=1, font_size=13))
        self._s_token = toga.TextInput(
            value=cfg.get("bot_token",""),
            placeholder="Bot Token (optional — for reading replies)",
            style=Pack(flex=1, font_size=13))
        self._s_channel = toga.TextInput(
            value=cfg.get("channel_id",""),
            placeholder="Channel ID (optional)",
            style=Pack(flex=1, font_size=13))
        save_btn = toga.Button("Save Senku Config", on_press=self._save_settings,
            style=Pack(background_color=ACCENT, color=BG, font_weight="bold",
                       margin_top=8))
        update_btn = toga.Button("Check for Updates", on_press=self._manual_update,
            style=Pack(background_color=PANEL, color=ACCENT2, margin_top=6))
        ver_lbl = toga.Label(f"Kin v{VERSION}",
            style=Pack(color=MUTED, font_size=11, padding_top=12, text_align=CENTER))

        box = toga.Box(style=Pack(direction=COLUMN, padding=16, spacing=10,
                                   background_color=BG))
        box.add(toga.Label("⚡ Senku Link", style=Pack(
            color=ACCENT, font_size=16, font_weight="bold", margin_bottom=6)))
        box.add(toga.Label("Webhook URL", style=Pack(color=MUTED, font_size=11)))
        box.add(self._s_webhook)
        box.add(toga.Label("Bot Token", style=Pack(color=MUTED, font_size=11)))
        box.add(self._s_token)
        box.add(toga.Label("Channel ID", style=Pack(color=MUTED, font_size=11)))
        box.add(self._s_channel)
        box.add(save_btn)
        box.add(toga.Box(style=Pack(height=1, background_color="#1e1e2e", margin=8)))
        box.add(toga.Label("🔄 Updates", style=Pack(
            color=ACCENT, font_size=16, font_weight="bold", margin_bottom=4)))
        box.add(toga.Label(
            f"Update URL: {UPDATE_URL}",
            style=Pack(color=MUTED, font_size=10)))
        box.add(update_btn)
        box.add(ver_lbl)
        return toga.ScrollContainer(content=box, horizontal=False, style=Pack(flex=1))

    def _save_settings(self, widget=None):
        cfg = load_config()
        cfg["webhook"]    = self._s_webhook.value.strip()
        cfg["bot_token"]  = self._s_token.value.strip()
        cfg["channel_id"] = self._s_channel.value.strip()
        save_config(cfg)
        self.main_window.info_dialog("✓ Saved", "Senku link config saved.")

    def _manual_update(self, widget=None):
        check_for_update(
            on_update_available=self._prompt_update,
            on_current=lambda: self._on_main(
                lambda: self.main_window.info_dialog("Up to date", f"Kin v{VERSION} is current."))
        )

    def _prompt_update(self, new_version):
        def _show():
            if self.main_window.confirm_dialog(
                "Update Available",
                f"Kin {new_version} is available. Update now?"
            ):
                apply_update(
                    on_done=lambda: self._on_main(lambda: self.main_window.info_dialog(
                        "Updated", f"Updated to {new_version}. Restart Kin.")),
                    on_error=lambda e: self._on_main(lambda: self.main_window.error_dialog(
                        "Update Failed", str(e)))
                )
        self._on_main(_show)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    return KinApp("Kin", "org.savant.kin")


