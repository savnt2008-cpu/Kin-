import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import json, os, math, random, datetime, threading, urllib.request

VERSION = "2.1.0"
DATA_DIR = os.path.expanduser("~/.kin")
os.makedirs(DATA_DIR, exist_ok=True)
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")
NOTES_FILE = os.path.join(DATA_DIR, "notes.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f: return json.load(f)
        except: pass
    return default

def save_json(path, data):
    with open(path, 'w') as f: json.dump(data, f)

def now_time(): return datetime.datetime.now().strftime("%I:%M %p")
def now_date(): return datetime.datetime.now().strftime("%A, %d %B %Y")

TIMETABLE = {
    "Monday": "Classes 8 AM - 2 PM",
    "Tuesday": "Free day",
    "Wednesday": "Lab session at 10 AM",
    "Thursday": "Lectures 9 AM - 1 PM",
    "Friday": "Wrap-up at 11 AM",
    "Saturday": "No classes",
    "Sunday": "No classes",
}

INTENTS = [
    {"p": ["hello","hi","hey","sup"], "r": ["Hey! What do you need?", "Hi there.", "What's good?"]},
    {"p": ["bye","goodbye","later"], "r": ["Later.", "See you.", "Take care."]},
    {"p": ["thanks","thank you","thx"], "r": ["No problem.", "Anytime."]},
    {"p": ["who are you","your name"], "r": ["I'm Kin. Your assistant."]},
    {"p": ["how are you"], "r": ["Running smooth.", "All good."]},
    {"p": ["joke","funny"], "r": [
        "Why do programmers prefer dark mode? Light attracts bugs.",
        "My Wi-Fi is 'incorrect'. When asked I say it's 'incorrect'.",
    ]},
    {"p": ["time"], "r": [lambda: f"It's {now_time()}."]},
    {"p": ["date","today"], "r": [lambda: f"Today is {now_date()}."]},
    {"p": ["version"], "r": [f"Kin v{VERSION}"]},
    {"p": ["help","what can you do"], "r": ["Use the tabs at the top — Chat, Calc, Tasks, Notes, Schedule."]},
]

def get_response(text):
    q = text.lower()
    for intent in INTENTS:
        for p in intent["p"]:
            if p in q:
                r = random.choice(intent["r"])
                return r() if callable(r) else r
    return "Not sure about that. Try asking something else."

def send_to_senku(message, on_reply, on_error):
    cfg = load_json(CONFIG_FILE, {})
    webhook = cfg.get("webhook", "")
    if not webhook:
        on_error("Senku not configured. Go to Settings.")
        return
    def _work():
        try:
            payload = json.dumps({"content": f"[KIN] {message}", "username": "Kin"}).encode()
            req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=8)
            on_reply("Sent to Senku.")
        except Exception as e:
            on_error(f"Senku unreachable: {e}")
    threading.Thread(target=_work, daemon=True).start()

class KinApp(toga.App):

    def startup(self):
        self._calc_expr = ""
        self._calc_last = None
        self.main_window = toga.MainWindow(title=f"Kin v{VERSION}")
        self.main_window.content = self._build_ui()
        self.main_window.show()

    def _build_ui(self):
        self._tabs = toga.OptionContainer(content=[
            toga.OptionItem("Chat", self._chat_tab()),
            toga.OptionItem("Calc", self._calc_tab()),
            toga.OptionItem("Tasks", self._tasks_tab()),
            toga.OptionItem("Notes", self._notes_tab()),
            toga.OptionItem("Schedule", self._schedule_tab()),
            toga.OptionItem("Settings", self._settings_tab()),
        ])
        return self._tabs

    def _chat_tab(self):
        self._chat_log = toga.MultilineTextInput(readonly=True, style=Pack(flex=1))
        self._chat_input = toga.TextInput(placeholder="Talk to Kin...", style=Pack(flex=1))
        send_btn = toga.Button("Send", on_press=self._send_chat, style=Pack(width=80))
        row = toga.Box(children=[self._chat_input, send_btn], style=Pack(direction=ROW, padding=5))
        box = toga.Box(children=[self._chat_log, row], style=Pack(direction=COLUMN, flex=1))
        h = datetime.datetime.now().hour
        g = "Good morning!" if h < 12 else "Good afternoon." if h < 18 else "Good evening."
        self._chat_log.value = f"Kin: {g} I'm online.\n"
        return box

    def _send_chat(self, widget):
        text = self._chat_input.value.strip()
        if not text: return
        self._chat_log.value += f"\nYou: {text}"
        self._chat_input.value = ""
        local = get_response(text)
        if local:
            self._chat_log.value += f"\nKin: {local}\n"
        else:
            self._chat_log.value += "\nKin: Routing to Senku...\n"
            send_to_senku(text,
                on_reply=lambda r: setattr(self._chat_log, 'value', self._chat_log.value + f"Senku: {r}\n"),
                on_error=lambda e: setattr(self._chat_log, 'value', self._chat_log.value + f"Kin: {e}\n")
            )

    def _calc_tab(self):
        self._expr_lbl = toga.Label("", style=Pack(padding=(5,10), font_size=11))
        self._result_lbl = toga.Label("0", style=Pack(padding=(0,10,10,10), font_size=28))
        display = toga.Box(children=[self._expr_lbl, self._result_lbl], style=Pack(direction=COLUMN))

        def b(label, cb, flex=1):
            return toga.Button(label, on_press=cb, style=Pack(flex=flex, height=55, padding=2))

        def inp(v): return lambda w: self._ci(v)
        def fn(f):  return lambda w: self._cf(f)

        grid = toga.Box(style=Pack(direction=COLUMN, flex=1))
        rows = [
            [b("AC", fn("clear")), b("⌫", fn("del")), b("%", inp("%")), b("÷", inp("/"))],
            [b("7", inp("7")), b("8", inp("8")), b("9", inp("9")), b("×", inp("*"))],
            [b("4", inp("4")), b("5", inp("5")), b("6", inp("6")), b("−", inp("-"))],
            [b("1", inp("1")), b("2", inp("2")), b("3", inp("3")), b("+", inp("+"))],
            [b("0", inp("0")), b(".", inp(".")), b("√", fn("sqrt")), b("=", fn("eq"))],
        ]
        for row in rows:
            grid.add(toga.Box(children=row, style=Pack(direction=ROW)))

        return toga.Box(children=[display, grid], style=Pack(direction=COLUMN, flex=1))

    def _ci(self, val):
        if self._calc_last is not None and val not in "+-*/%":
            self._calc_expr = ""; self._calc_last = None
        if self._calc_last is not None and val in "+-*/%":
            self._calc_expr = str(self._calc_last); self._calc_last = None
        self._calc_expr += val
        self._expr_lbl.text = self._calc_expr
        self._result_lbl.text = self._calc_expr or "0"

    def _cf(self, fn):
        if fn == "clear":
            self._calc_expr = ""; self._calc_last = None
            self._expr_lbl.text = ""; self._result_lbl.text = "0"; return
        if fn == "del":
            self._calc_expr = self._calc_expr[:-1]
            self._expr_lbl.text = self._calc_expr
            self._result_lbl.text = self._calc_expr or "0"; return
        try:
            base = float(self._calc_expr) if self._calc_expr else 0
            if fn == "sqrt": res = math.sqrt(base)
            elif fn == "eq":
                res = eval(self._calc_expr, {"__builtins__": {}},
                           {"sqrt": math.sqrt, "pi": math.pi, "abs": abs})
            else: return
            disp = int(res) if isinstance(res, float) and res == int(res) else round(res, 8)
            self._expr_lbl.text = self._calc_expr + " ="
            self._result_lbl.text = str(disp)
            self._calc_last = disp; self._calc_expr = str(disp)
        except:
            self._result_lbl.text = "Error"; self._calc_expr = ""

    def _tasks_tab(self):
        self._task_input = toga.TextInput(placeholder="New task...", style=Pack(flex=1))
        add_btn = toga.Button("Add", on_press=self._add_task, style=Pack(width=70))
        self._task_scroll = toga.ScrollContainer(horizontal=False, style=Pack(flex=1))
        self._task_box = toga.Box(style=Pack(direction=COLUMN, padding=5))
        self._task_scroll.content = self._task_box
        self._render_tasks()
        return toga.Box(children=[
            toga.Box(children=[self._task_input, add_btn], style=Pack(direction=ROW, padding=5)),
            self._task_scroll
        ], style=Pack(direction=COLUMN, flex=1))

    def _add_task(self, widget=None):
        text = self._task_input.value.strip()
        if not text: return
        tasks = load_json(TASKS_FILE, [])
        tasks.append({"task": text, "date": datetime.date.today().isoformat()})
        save_json(TASKS_FILE, tasks)
        self._task_input.value = ""
        self._render_tasks()

    def _render_tasks(self):
        self._task_box.clear()
        tasks = load_json(TASKS_FILE, [])
        if not tasks:
            self._task_box.add(toga.Label("No tasks yet.", style=Pack(padding=10)))
            return
        for i, t in enumerate(tasks):
            lbl = toga.Label(f"• {t['task']}", style=Pack(flex=1, padding=5))
            idx = i
            del_btn = toga.Button("✕", on_press=lambda w, x=idx: self._del_task(x), style=Pack(width=40))
            self._task_box.add(toga.Box(children=[lbl, del_btn], style=Pack(direction=ROW)))

    def _del_task(self, idx):
        tasks = load_json(TASKS_FILE, [])
        tasks.pop(idx)
        save_json(TASKS_FILE, tasks)
        self._render_tasks()

    def _notes_tab(self):
        self._note_title = toga.TextInput(placeholder="Title...", style=Pack(padding=5))
        self._note_body = toga.MultilineTextInput(placeholder="Note...", style=Pack(flex=1, padding=5))
        save_btn = toga.Button("Save", on_press=self._add_note, style=Pack(padding=5))
        self._note_scroll = toga.ScrollContainer(horizontal=False, style=Pack(flex=1))
        self._note_box = toga.Box(style=Pack(direction=COLUMN, padding=5))
        self._note_scroll.content = self._note_box
        self._render_notes()
        return toga.Box(children=[
            self._note_title, self._note_body, save_btn, self._note_scroll
        ], style=Pack(direction=COLUMN, flex=1))

    def _add_note(self, widget=None):
        title = self._note_title.value.strip() or "Untitled"
        body = self._note_body.value.strip()
        if not body: return
        notes = load_json(NOTES_FILE, [])
        notes.insert(0, {"title": title, "body": body, "date": datetime.date.today().isoformat()})
        save_json(NOTES_FILE, notes)
        self._note_title.value = ""
        self._note_body.value = ""
        self._render_notes()

    def _render_notes(self):
        self._note_box.clear()
        notes = load_json(NOTES_FILE, [])
        if not notes:
            self._note_box.add(toga.Label("No notes yet.", style=Pack(padding=10)))
            return
        for i, n in enumerate(notes):
            title = toga.Label(n["title"], style=Pack(flex=1, padding=5))
            idx = i
            del_btn = toga.Button("✕", on_press=lambda w, x=idx: self._del_note(x), style=Pack(width=40))
            body = toga.Label(n["body"], style=Pack(padding=(0,5,5,5)))
            self._note_box.add(toga.Box(children=[title, del_btn], style=Pack(direction=ROW)))
            self._note_box.add(body)

    def _del_note(self, idx):
        notes = load_json(NOTES_FILE, [])
        notes.pop(idx)
        save_json(NOTES_FILE, notes)
        self._render_notes()

    def _schedule_tab(self):
        today = datetime.datetime.now().strftime("%A")
        box = toga.Box(style=Pack(direction=COLUMN, padding=10))
        for day, entry in TIMETABLE.items():
            is_today = day == today
            text = f"{'► ' if is_today else '   '}{day[:3].upper()}  {entry}"
            lbl = toga.Label(text, style=Pack(padding=8, font_size=13))
            box.add(lbl)
        return toga.ScrollContainer(content=box, horizontal=False, style=Pack(flex=1))

    def _settings_tab(self):
        cfg = load_json(CONFIG_FILE, {})
        self._s_webhook = toga.TextInput(value=cfg.get("webhook",""), placeholder="Discord Webhook URL", style=Pack(padding=5))
        save_btn = toga.Button("Save Senku Config", on_press=self._save_settings, style=Pack(padding=5))
        ver = toga.Label(f"Kin v{VERSION}", style=Pack(padding=10))
        box = toga.Box(children=[
            toga.Label("Senku Webhook URL:", style=Pack(padding=(10,5,0,5))),
            self._s_webhook,
            save_btn,
            ver,
        ], style=Pack(direction=COLUMN, flex=1))
        return box

    def _save_settings(self, widget=None):
        cfg = load_json(CONFIG_FILE, {})
        cfg["webhook"] = self._s_webhook.value.strip()
        save_json(CONFIG_FILE, cfg)
        self.main_window.info_dialog("Saved", "Senku config saved.")

def main():
    return KinApp("Kin", "org.savant.kin")
