import express from 'express';
import type { Request, Response, NextFunction } from 'express';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { GoogleGenAI } from '@google/genai';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = parseInt(process.env.PORT || '3000', 10);
const SITE_URL = process.env.SITE_URL || 'https://karif.up.railway.app';
const ADMIN_USER = process.env.ADMIN_USER || 'kirill';
const ADMIN_PASS = process.env.ADMIN_PASS || 'changeme123';

const ai = new GoogleGenAI({
  apiKey: process.env.GEMINI_API_KEY,
  httpOptions: {
    headers: {
      'User-Agent': 'aistudio-build',
    },
  },
});

app.use(express.json());

interface Lead {
  id: number;
  created_at: string;
  biz: string;
  city: string;
  name: string;
  contact_method: string;
  contact_value: string;
  source: string;
  ip: string;
  user_agent: string;
}

interface Brief {
  id: number;
  created_at: string;
  biz_name: string;
  city: string;
  contact_name: string;
  data: Record<string, string>;
  ip: string;
  user_agent: string;
}

let nextLeadId = 1;
const leads: Lead[] = [];

let nextBriefId = 1;
const briefs: Brief[] = [];

const CONTACT_LABELS: Record<string, string> = {
  telegram: 'Telegram',
  phone: 'Телефон',
  whatsapp: 'WhatsApp',
  other: 'Другое',
};

const BRIEF_GROUPS: [string, [string, string][]][] = [
  [
    'О бизнесе',
    [
      ['contact_name', 'Как обращаться'],
      ['biz_name', 'Название компании / бренда'],
      ['city', 'Город и район работы'],
      ['about', 'Чем занимаетесь'],
      ['years', 'Сколько лет на рынке'],
      ['legal_form', 'ИП / самозанятый / физлицо'],
    ],
  ],
  [
    'Клиенты и позиционирование',
    [
      ['audience', 'Типичный клиент'],
      ['problem', 'Какую проблему решаете'],
      ['why_you', 'Почему выбирают вас'],
      ['competitors', 'Конкуренты (нравится/не нравится)'],
    ],
  ],
  [
    'Услуги и цены',
    [
      ['services', 'Услуги и цены'],
      ['promo', 'Спецпредложение на старте'],
      ['booking_method', 'Как клиент записывается'],
    ],
  ],
  [
    'Контакты и график',
    [
      ['phone', 'Телефон'],
      ['telegram', 'Telegram / WhatsApp'],
      ['address', 'Адрес'],
      ['hours', 'Часы работы'],
      ['socials', 'Соцсети / карты'],
    ],
  ],
  [
    'Визуал и материалы',
    [
      ['logo', 'Логотип'],
      ['brand_color', 'Фирменный цвет'],
      ['photos', 'Сколько хороших фото'],
    ],
  ],
  [
    'Доверие',
    [
      ['reviews', 'Отзывы (сколько, где, рейтинг)'],
      ['awards', 'Награды / сертификаты'],
      ['testimonials', 'Цитаты клиентов'],
    ],
  ],
  [
    'Тексты и тон',
    [
      ['about_text', 'О себе от первого лица'],
      ['tone', 'Тон общения'],
      ['forbidden', 'Что нельзя писать'],
    ],
  ],
  [
    'Технические детали',
    [
      ['domain', 'Желаемый домен'],
      ['existing_site', 'Уже есть сайт'],
      ['booking_type', 'Онлайн-запись или кнопка'],
      ['map_needed', 'Нужна карта'],
    ],
  ],
  [
    'Что важно лично',
    [
      ['must_have', 'Обязательно должно быть'],
      ['must_not', 'Точно не должно быть'],
      ['refs', 'Референсы'],
    ],
  ],
];

const BRIEF_FIELDS: string[] = [];
for (const [, fields] of BRIEF_GROUPS) {
  for (const [key] of fields) {
    BRIEF_FIELDS.push(key);
  }
}

function checkAuth(req: Request, res: Response, next: NextFunction): void {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Basic ')) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Admin"');
    res.status(401).send('Нужен вход');
    return;
  }
  const b64 = authHeader.slice(6);
  const credentials = Buffer.from(b64, 'base64').toString('utf-8');
  const [user, pass] = credentials.split(':');
  if (user === ADMIN_USER && pass === ADMIN_PASS) {
    return next();
  }
  res.setHeader('WWW-Authenticate', 'Basic realm="Admin"');
  res.status(401).send('Нужен вход');
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const ADMIN_PAGE = `<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
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
<div class="top"><h1>__HEADING__</h1><div class="cnt">__COUNT__ шт. · <a class="rl" href="">обновить</a></div></div>
__TABLE__
</body></html>`;

const BRIEF_DETAIL_PAGE = `<!doctype html><html lang="ru"><head><meta charset="utf-8">
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
</body></html>`;

// ---- static site ----
app.get('/', (_req: Request, res: Response) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.get('/brief', (_req: Request, res: Response) => {
  res.sendFile(path.join(__dirname, 'brief.html'));
});

app.get('/robots.txt', (_req: Request, res: Response) => {
  const body = `User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /brief\nSitemap: ${SITE_URL}/sitemap.xml\n`;
  res.type('text/plain').send(body);
});

app.get('/sitemap.xml', (_req: Request, res: Response) => {
  const body =
    '<?xml version="1.0" encoding="UTF-8"?>' +
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
    `<url><loc>${SITE_URL}/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>` +
    '</urlset>';
  res.type('application/xml').send(body);
});

// ---- API ----
app.post('/api/leads', (req: Request, res: Response) => {
  const data = req.body || {};
  const biz = String(data.biz || '').trim().slice(0, 200);
  const city = String(data.city || '').trim().slice(0, 200);
  const name = String(data.name || '').trim().slice(0, 200);
  let contact_method = String(data.contact_method || 'telegram').trim().slice(0, 20);
  if (!(contact_method in CONTACT_LABELS)) {
    contact_method = 'other';
  }
  const contact_value = String(data.contact_value || '').trim().slice(0, 200);
  const source = String(data.source || 'form').trim().slice(0, 50);

  if (!biz) {
    return res.status(400).json({ ok: false, error: 'biz required' });
  }

  const rawIp = req.headers['x-forwarded-for'];
  const ip = typeof rawIp === 'string' ? rawIp : (Array.isArray(rawIp) ? rawIp[0] : req.socket.remoteAddress || '');
  const user_agent = (req.headers['user-agent'] || '').slice(0, 300);

  const newLead: Lead = {
    id: nextLeadId++,
    created_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    biz,
    city,
    name,
    contact_method,
    contact_value,
    source,
    ip,
    user_agent,
  };
  leads.push(newLead);

  return res.json({ ok: true });
});

app.post('/api/brief', (req: Request, res: Response) => {
  const data = req.body || {};
  const clean: Record<string, string> = {};

  for (const key of BRIEF_FIELDS) {
    const v = data[key];
    if (v === undefined || v === null) continue;
    const s = String(v).trim().slice(0, 4000);
    if (s) {
      clean[key] = s;
    }
  }

  const biz_name = (clean['biz_name'] || '').slice(0, 200);
  if (!biz_name) {
    return res.status(400).json({ ok: false, error: 'biz_name required' });
  }

  const rawIp = req.headers['x-forwarded-for'];
  const ip = typeof rawIp === 'string' ? rawIp : (Array.isArray(rawIp) ? rawIp[0] : req.socket.remoteAddress || '');
  const user_agent = (req.headers['user-agent'] || '').slice(0, 300);

  const newBrief: Brief = {
    id: nextBriefId++,
    created_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    biz_name,
    city: (clean['city'] || '').slice(0, 200),
    contact_name: (clean['contact_name'] || '').slice(0, 200),
    data: clean,
    ip,
    user_agent,
  };
  briefs.push(newBrief);

  return res.json({ ok: true });
});

// ---- admin ----
app.get('/admin', checkAuth, (_req: Request, res: Response) => {
  const rows = [...leads].sort((a, b) => b.id - a.id);
  let table: string;
  if (rows.length === 0) {
    table = '<div class="empty">Пока пусто. Заявки появятся здесь.</div>';
  } else {
    const trs = rows.map((r) => {
      const dt = escapeHtml(r.created_at).replace('T', ' ').replace('Z', '');
      const biz = escapeHtml(r.biz) || '—';
      const city = escapeHtml(r.city) || '—';
      const name = escapeHtml(r.name) || '—';
      const methodLabel = CONTACT_LABELS[r.contact_method] || r.contact_method || '—';
      const contactHtml = escapeHtml(r.contact_value) || '—';
      const src = escapeHtml(r.source) || 'form';

      return `<tr><td>${r.id}</td><td>${dt}</td><td>${biz}</td><td>${city}</td><td>${name}</td>` +
        `<td><span class="tag">${escapeHtml(methodLabel)}</span> ${contactHtml}</td>` +
        `<td><span class="tag">${src}</span></td></tr>`;
    });

    table =
      '<table><thead><tr><th>#</th><th>Когда</th><th>Бизнес</th>' +
      '<th>Город</th><th>Имя</th><th>Контакт</th><th>Источник</th></tr></thead>' +
      `<tbody>${trs.join('')}</tbody></table>`;
  }

  const html = ADMIN_PAGE
    .replace('__TITLE__', 'Заявки — админка')
    .replace('__HEADING__', 'Заявки с сайта')
    .replace('__COUNT__', String(rows.length))
    .replace('__TABLE__', table)
    .replace('__NAV_LEADS__', 'on')
    .replace('__NAV_BRIEFS__', '');

  res.send(html);
});

app.get('/admin/briefs', checkAuth, (_req: Request, res: Response) => {
  const rows = [...briefs].sort((a, b) => b.id - a.id);
  let table: string;
  if (rows.length === 0) {
    table = '<div class="empty">Пока пусто. Брифы появятся здесь.</div>';
  } else {
    const trs = rows.map((r) => {
      const dt = escapeHtml(r.created_at).replace('T', ' ').replace('Z', '');
      const biz = escapeHtml(r.biz_name) || '—';
      const city = escapeHtml(r.city) || '—';
      const name = escapeHtml(r.contact_name) || '—';

      return `<tr><td>${r.id}</td><td>${dt}</td><td>${biz}</td><td>${city}</td><td>${name}</td>` +
        `<td><a class="rl" href="/admin/brief/${r.id}">открыть →</a></td></tr>`;
    });

    table =
      '<table><thead><tr><th>#</th><th>Когда</th><th>Бизнес</th>' +
      '<th>Город</th><th>Имя</th><th></th></tr></thead>' +
      `<tbody>${trs.join('')}</tbody></table>`;
  }

  const html = ADMIN_PAGE
    .replace('__TITLE__', 'Брифы — админка')
    .replace('__HEADING__', 'Брифы с сайта')
    .replace('__COUNT__', String(rows.length))
    .replace('__TABLE__', table)
    .replace('__NAV_LEADS__', '')
    .replace('__NAV_BRIEFS__', 'on');

  res.send(html);
});

app.get('/admin/brief/:id', checkAuth, (req: Request, res: Response) => {
  const paramId = Array.isArray(req.params.id) ? req.params.id[0] : req.params.id;
  const briefId = parseInt(paramId, 10);
  const r = briefs.find((b) => b.id === briefId);
  if (!r) {
    return res.status(404).send('Не найдено');
  }

  const data = r.data || {};
  const cards: string[] = [];
  for (const [title, fields] of BRIEF_GROUPS) {
    const rowsHtml: string[] = [];
    for (const [key, label] of fields) {
      const v = data[key];
      if (!v) continue;
      rowsHtml.push(`<div class="row"><b>${escapeHtml(label)}</b><div>${escapeHtml(v)}</div></div>`);
    }
    if (rowsHtml.length > 0) {
      cards.push(`<div class="card"><h2>${escapeHtml(title)}</h2>${rowsHtml.join('')}</div>`);
    }
  }

  const body = cards.join('') || '<div class="empty">Пустой бриф.</div>';
  const dt = escapeHtml(r.created_at).replace('T', ' ').replace('Z', '');
  const meta = `${dt} · IP ${escapeHtml(r.ip)}`;

  const html = BRIEF_DETAIL_PAGE
    .replace('__BIZ__', escapeHtml(r.biz_name) || 'Без названия')
    .replace('__META__', meta)
    .replace('__BODY__', body);

  return res.send(html);
});

app.post('/api/generate-concept', async (req: Request, res: Response) => {
  const { biz } = req.body || {};
  const query = typeof biz === 'string' && biz.trim() ? biz.trim() : 'Барбершоп';

  try {
    if (process.env.GEMINI_API_KEY) {
      const prompt = `Ты — топовый маркетолог и веб-разработчик. Создай продающий экспресс-концепт первого экрана для сайта ниши: "${query}".
Верни ТОЛЬКО валидный JSON без markdown блоков, следующей структуры:
{
  "headline": "Мощный броский заголовок (до 7 слов)",
  "subhead": "Убедительный подзаголовок с выгодой для клиента (1-2 предложения)",
  "triggers": ["триггер 1 с галочкой", "триггер 2 с галочкой", "триггер 3 с галочкой"],
  "leadMagnet": "Спецпредложение для первой заявки (например: Скидка 20% на первое посещение или Бесплатная диагностика)",
  "cta": "Текст на кнопке (например: Записаться со скидкой 20% →)"
}`;

      const response = await ai.models.generateContent({
        model: 'gemini-3.8-flash',
        contents: prompt,
      });

      const text = response.text?.trim() || '';
      const cleanJson = text.replace(/^```json\s*/i, '').replace(/```\s*$/i, '').trim();
      const parsed = JSON.parse(cleanJson);
      return res.json({ ok: true, data: parsed });
    }
  } catch (err) {
    console.error('Gemini concept generation error:', err);
  }

  // Fallback if no key or error:
  return res.json({
    ok: true,
    data: {
      headline: `${query}: премиум-качество с гарантией результата`,
      subhead: `Качественные услуги для требовательных клиентов. Запишитесь онлайн за 30 секунд и получите приятный бонус на первый визит.`,
      triggers: ['✓ Домен и онлайн-оплата включены', '✓ Заявки прямо в Telegram', '✓ 100% готовность на смартфонах'],
      leadMagnet: 'Спецпредложение: Скидка 15% на первое посещение',
      cta: 'Записаться онлайн со скидкой →'
    }
  });
});

// Protect internal/source files from being served statically
const BLOCKED_FILES = new Set([
  'app.py',
  'server.ts',
  'package.json',
  'package-lock.json',
  'tsconfig.json',
  'requirements.txt',
  'Procfile',
  'leads.db',
  '.env',
  '.env.example',
  'metadata.json',
]);

app.use((req: Request, res: Response, next: NextFunction) => {
  const reqPath = req.path.replace(/^\/+/, '');
  if (BLOCKED_FILES.has(reqPath) || reqPath.startsWith('.')) {
    return res.status(404).send('Not found');
  }
  const fullPath = path.join(__dirname, reqPath);
  if (fs.existsSync(fullPath) && fs.statSync(fullPath).isFile()) {
    return res.sendFile(fullPath);
  }
  return next();
});

app.use((_req: Request, res: Response) => {
  res.status(404).send('Not found');
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Server listening on http://0.0.0.0:${PORT}`);
});
