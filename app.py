import html
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


@app.route("/robots.txt")
def robots():
    body = f"User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {SITE_URL}/sitemap.xml\n"
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
.tag{display:inline-block;padding:2px 8px;border-radius:99px;background:#23232C;font-size:12px;color:#E9B44C}
.top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:20px}
.cnt{color:#9A9AA6;font-size:14px}
a.rl{color:#E9B44C;text-decoration:none;font-size:14px}
</style></head><body>
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
    return ADMIN_PAGE.replace("__COUNT__", str(len(rows))).replace("__TABLE__", table)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
