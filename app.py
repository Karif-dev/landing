import html
import json
import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, Response, send_from_directory, g

app = Flask(__name__, static_folder=None)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "leads.db")

ADMIN_USER = os.environ.get("ADMIN_USER", "kirill")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "changeme123")


def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            biz TEXT,
            city TEXT,
            name TEXT,
            contact_method TEXT,
            contact_value TEXT,
            source TEXT,
            ip TEXT,
            user_agent TEXT
        )
        """
    )
    existing = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}
    for col in ("contact_method", "contact_value"):
        if col not in existing:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            biz_name TEXT,
            city TEXT,
            contact_name TEXT,
            data TEXT,
            ip TEXT,
            user_agent TEXT
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


def check_auth(u, p):
    return u == ADMIN_USER and p == ADMIN_PASS


def requires_auth(f):
    @wraps(f)
    def decorated(*a, **kw):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "Нужен вход", 401, {"WWW-Authenticate": 'Basic realm="Admin"'}
            )
        return f(*a, **kw)

    return decorated


SITE_URL = os.environ.get("SITE_URL", "https://karif.up.railway.app")


# ---- static site ----
@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/brief")
def brief_page():
    return send_from_directory(BASE_DIR, "brief.html")


@app.route("/robots.txt")
def robots():
    body = f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /brief\nSitemap: {SITE_URL}/sitemap.xml\n"
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{SITE_URL}/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>"
        "</urlset>"
    )
    return Response(body, mimetype="application/xml")


@app.route("/<path:path>")
def static_files(path):
    if path in ("app.py", "leads.db", "requirements.txt", "Procfile") or path.startswith("."):
        return "Not found", 404
    full = os.path.join(BASE_DIR, path)
    if os.path.isfile(full):
        return send_from_directory(BASE_DIR, path)
    return "Not found", 404


# ---- API ----
CONTACT_LABELS = {
    "telegram": "Telegram",
    "phone": "Телефон",
    "whatsapp": "WhatsApp",
    "other": "Другое",
}


@app.route("/api/leads", methods=["POST"])
def create_lead():
    data = request.get_json(silent=True) or {}
    biz = (data.get("biz") or "").strip()[:200]
    city = (data.get("city") or "").strip()[:200]
    name = (data.get("name") or "").strip()[:200]
    contact_method = (data.get("contact_method") or "telegram").strip()[:20]
    if contact_method not in CONTACT_LABELS:
        contact_method = "other"
    contact_value = (data.get("contact_value") or "").strip()[:200]
    source = (data.get("source") or "form").strip()[:50]
    if not biz:
        return jsonify({"ok": False, "error": "biz required"}), 400
    db = get_db()
    db.execute(
        "INSERT INTO leads (created_at, biz, city, name, contact_method, contact_value, source, ip, user_agent) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.utcnow().isoformat(timespec="seconds") + "Z",
            biz,
            city,
            name,
            contact_method,
            contact_value,
            source,
            request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            request.headers.get("User-Agent", "")[:300],
        ),
    )
    db.commit()
    return jsonify({"ok": True})


BRIEF_GROUPS = [
    ("О бизнесе", [
        ("contact_name", "Как обращаться"),
        ("biz_name", "Название компании / бренда"),
        ("city", "Город и район работы"),
        ("about", "Чем занимаетесь"),
        ("years", "Сколько лет на рынке"),
        ("legal_form", "ИП / самозанятый / физлицо"),
    ]),
    ("Клиенты и позиционирование", [
        ("audience", "Типичный клиент"),
        ("problem", "Какую проблему решаете"),
        ("why_you", "Почему выбирают вас"),
        ("competitors", "Конкуренты (нравится/не нравится)"),
    ]),
    ("Услуги и цены", [
        ("services", "Услуги и цены"),
        ("promo", "Спецпредложение на старте"),
        ("booking_method", "Как клиент записывается"),
    ]),
    ("Контакты и график", [
        ("phone", "Телефон"),
        ("telegram", "Telegram / WhatsApp"),
        ("address", "Адрес"),
        ("hours", "Часы работы"),
        ("socials", "Соцсети / карты"),
    ]),
    ("Визуал и материалы", [
        ("logo", "Логотип"),
        ("brand_color", "Фирменный цвет"),
        ("photos", "Сколько хороших фото"),
    ]),
    ("Доверие", [
        ("reviews", "Отзывы (сколько, где, рейтинг)"),
        ("awards", "Награды / сертификаты"),
        ("testimonials", "Цитаты клиентов"),
    ]),
    ("Тексты и тон", [
        ("about_text", "О себе от первого лица"),
        ("tone", "Тон общения"),
        ("forbidden", "Что нельзя писать"),
    ]),
    ("Технические детали", [
        ("domain", "Желаемый домен"),
        ("existing_site", "Уже есть сайт"),
        ("booking_type", "Онлайн-запись или кнопка"),
        ("map_needed", "Нужна карта"),
    ]),
    ("Что важно лично", [
        ("must_have", "Обязательно должно быть"),
        ("must_not", "Точно не должно быть"),
        ("refs", "Референсы"),
    ]),
]
BRIEF_FIELDS = [key for _, fields in BRIEF_GROUPS for key, _ in fields]


@app.route("/api/brief", methods=["POST"])
def create_brief():
    data = request.get_json(silent=True) or {}
    clean = {}
    for key in BRIEF_FIELDS:
        v = data.get(key)
        if v is None:
            continue
        v = str(v).strip()[:4000]
        if v:
            clean[key] = v
    biz_name = clean.get("biz_name", "")[:200]
    if not biz_name:
        return jsonify({"ok": False, "error": "biz_name required"}), 400
    db = get_db()
    db.execute(
        "INSERT INTO briefs (created_at, biz_name, city, contact_name, data, ip, user_agent) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.utcnow().isoformat(timespec="seconds") + "Z",
            biz_name,
            clean.get("city", "")[:200],
            clean.get("contact_name", "")[:200],
            json.dumps(clean, ensure_ascii=False),
            request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            request.headers.get("User-Agent", "")[:300],
        ),
    )
    db.commit()
    return jsonify({"ok": True})


# ---- admin ----
ADMIN_PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Заявки — админка</title>
<meta name="robots" content="noindex,nofollow">
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0B0B0F;color:#F4F4F6;font:15px/1.5 -apple-system,Segoe UI,Inter,Arial,sans-serif;padding:28px}
h1{font-size:22px;margin:0 0 20px}
table{width:100%;border-collapse:collapse;background:#15151B;border:1px solid #23232C;border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:12px 14px;border-bottom:1px solid #23232C;vertical-align:top}
th{color:#9A9AA6;font-weight:600;font-size:13px;text-transform:uppercase;letter-spacing:.05em}
tr:last-child td{border-bottom:0}
.empty{padding:40px;text-align:center;color:#9A9AA6}
.tag{display:inline-block;padding:2px 8px;border-radius:99px;background:#23232C;font-size:12px;color:#4FA3FF}
.top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:20px}
.cnt{color:#9A9AA6;font-size:14px}
a.rl{color:#4FA3FF;text-decoration:none;font-size:14px}
.nav{display:flex;gap:16px;margin-bottom:4px}
.nav a{color:#9A9AA6;text-decoration:none;font-size:13.5px;font-weight:600;padding-bottom:8px;border-bottom:2px solid transparent}
.nav a.on{color:#F4F4F6;border-color:#4FA3FF}
</style></head><body>
<div class="nav"><a href="/admin" class="__NAV_LEADS__">Заявки</a><a href="/admin/briefs" class="__NAV_BRIEFS__">Брифы</a></div>
<div class="top"><h1>Заявки с сайта</h1><div class="cnt">__COUNT__ шт. · <a class="rl" href="">обновить</a></div></div>
__TABLE__
</body></html>"""


@app.route("/admin")
@requires_auth
def admin():
    db = get_db()
    rows = db.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
    if not rows:
        table = '<div class="empty">Пока пусто. Заявки появятся здесь.</div>'
    else:
        trs = []
        for r in rows:
            e = lambda v: html.escape(v or "")
            method = r["contact_method"] if "contact_method" in r.keys() else None
            value = r["contact_value"] if "contact_value" in r.keys() else None
            method_label = CONTACT_LABELS.get(method or "", method or "—")
            contact_html = e(value) or "—"
            trs.append(
                "<tr><td>{id}</td><td>{dt}</td><td>{biz}</td><td>{city}</td><td>{name}</td>"
                '<td><span class="tag">{method}</span> {contact}</td>'
                '<td><span class="tag">{src}</span></td></tr>'.format(
                    id=r["id"],
                    dt=e(r["created_at"]).replace("T", " ").replace("Z", ""),
                    biz=e(r["biz"]) or "—",
                    city=e(r["city"]) or "—",
                    name=e(r["name"]) or "—",
                    method=e(method_label),
                    contact=contact_html,
                    src=e(r["source"]) or "form",
                )
            )
        table = (
            "<table><thead><tr><th>#</th><th>Когда</th><th>Бизнес</th>"
            "<th>Город</th><th>Имя</th><th>Контакт</th><th>Источник</th></tr></thead>"
            "<tbody>" + "".join(trs) + "</tbody></table>"
        )
    return (
        ADMIN_PAGE.replace("__COUNT__", str(len(rows)))
        .replace("__TABLE__", table)
        .replace("__NAV_LEADS__", "on")
        .replace("__NAV_BRIEFS__", "")
        .replace("<title>Заявки — админка</title>", "<title>Заявки — админка</title>")
    )


BRIEF_LIST_PAGE = ADMIN_PAGE.replace(
    "<title>Заявки — админка</title>", "<title>Брифы — админка</title>"
).replace("<h1>Заявки с сайта</h1>", "<h1>Брифы с сайта</h1>")


@app.route("/admin/briefs")
@requires_auth
def admin_briefs():
    db = get_db()
    rows = db.execute("SELECT * FROM briefs ORDER BY id DESC").fetchall()
    if not rows:
        table = '<div class="empty">Пока пусто. Брифы появятся здесь.</div>'
    else:
        e = lambda v: html.escape(v or "")
        trs = []
        for r in rows:
            trs.append(
                "<tr><td>{id}</td><td>{dt}</td><td>{biz}</td><td>{city}</td><td>{name}</td>"
                '<td><a class="rl" href="/admin/brief/{id}">открыть →</a></td></tr>'.format(
                    id=r["id"],
                    dt=e(r["created_at"]).replace("T", " ").replace("Z", ""),
                    biz=e(r["biz_name"]) or "—",
                    city=e(r["city"]) or "—",
                    name=e(r["contact_name"]) or "—",
                )
            )
        table = (
            "<table><thead><tr><th>#</th><th>Когда</th><th>Бизнес</th>"
            "<th>Город</th><th>Имя</th><th></th></tr></thead>"
            "<tbody>" + "".join(trs) + "</tbody></table>"
        )
    return (
        BRIEF_LIST_PAGE.replace("__COUNT__", str(len(rows)))
        .replace("__TABLE__", table)
        .replace("__NAV_LEADS__", "")
        .replace("__NAV_BRIEFS__", "on")
    )


BRIEF_DETAIL_PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Бриф — админка</title>
<meta name="robots" content="noindex,nofollow">
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0B0B0F;color:#F4F4F6;font:15px/1.5 -apple-system,Segoe UI,Inter,Arial,sans-serif;padding:28px}
.wrap{max-width:760px;margin:0 auto}
.back{color:#9A9AA6;text-decoration:none;font-size:13.5px;display:inline-block;margin-bottom:16px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:#9A9AA6;font-size:13.5px;margin-bottom:22px}
.card{background:#15151B;border:1px solid #23232C;border-radius:14px;padding:16px 18px;margin-bottom:10px}
.card h2{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#4FA3FF;font-weight:700;margin-bottom:12px}
.row{margin-bottom:10px}
.row:last-child{margin-bottom:0}
.row b{display:block;font-size:12.5px;color:#9A9AA6;font-weight:600;margin-bottom:2px}
.row div{white-space:pre-wrap;word-break:break-word}
.empty{color:#9A9AA6}
</style></head><body>
<div class="wrap">
<a class="back" href="/admin/briefs">← ко всем брифам</a>
<h1>__BIZ__</h1>
<div class="sub">__META__</div>
__BODY__
</div>
</body></html>"""


@app.route("/admin/brief/<int:brief_id>")
@requires_auth
def admin_brief_detail(brief_id):
    db = get_db()
    r = db.execute("SELECT * FROM briefs WHERE id = ?", (brief_id,)).fetchone()
    if not r:
        return "Не найдено", 404
    e = lambda v: html.escape(v or "")
    try:
        data = json.loads(r["data"] or "{}")
    except ValueError:
        data = {}
    cards = []
    for title, fields in BRIEF_GROUPS:
        rows_html = []
        for key, label in fields:
            v = data.get(key)
            if not v:
                continue
            rows_html.append(f'<div class="row"><b>{e(label)}</b><div>{e(v)}</div></div>')
        if rows_html:
            cards.append(f'<div class="card"><h2>{e(title)}</h2>{"".join(rows_html)}</div>')
    body = "".join(cards) or '<div class="empty">Пустой бриф.</div>'
    dt = e(r["created_at"]).replace("T", " ").replace("Z", "")
    meta = f'{dt} · IP {e(r["ip"])}'
    return (
        BRIEF_DETAIL_PAGE.replace("__BIZ__", e(r["biz_name"]) or "Без названия")
        .replace("__META__", meta)
        .replace("__BODY__", body)
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
