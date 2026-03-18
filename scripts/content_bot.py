"""
Universal Affiliate Content Bot
Genera articulos SEO con titulos dinamicos basados en tendencias reales.

Uso:
    python scripts/content_bot.py                 # genera 1 articulo
    python scripts/content_bot.py --batch 10      # genera 10 con fechas escalonadas
    python scripts/content_bot.py --loop          # 1 articulo por dia indefinidamente
    python scripts/content_bot.py --gentitles 20  # genera y guarda 20 titulos nuevos
    python scripts/content_bot.py --build         # regenera index y sitemap
"""

import os
import json
import time
import random
import logging
import argparse
import subprocess
import urllib.request
import urllib.parse
import urllib.error
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ── Config ─────────────────────────────────────────────────────────────────────
SITE_NAME     = "TackleReviewer"
SITE_URL      = "https://tacklereviewer.vercel.app"
SITE_TOPIC    = "fishing, hunting, camping and hiking gear"
SITE_AUDIENCE = "US outdoor enthusiasts and anglers"
AMAZON_TAG    = "tacklereviewe-20"
AMAZON_STORE  = "amazon.com"

REPO_DIR      = Path(__file__).parent.parent
POSTS_DIR     = REPO_DIR / "posts"
DATA_FILE     = REPO_DIR / "data" / "posts.json"
TITLES_FILE   = REPO_DIR / "data" / "titles.json"
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
LOOP_INTERVAL = 86400

# Pausas entre llamadas a la API (segundos)
API_PAUSE_BETWEEN_CALLS = 30
API_PAUSE_ON_429        = 120
API_JSON_RETRY_PAUSE    = 12
BATCH_PAUSE_MIN         = 90
BATCH_PAUSE_MAX         = 180

# Flags
ENABLE_WEB_SEARCH_FOR_TITLES   = True
ENABLE_WEB_SEARCH_FOR_ARTICLES = False

# Límites más conservadores para Tier 1
MAX_TOKENS_TITLES  = 3500
MAX_TOKENS_ARTICLE = 3000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(REPO_DIR / "bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── Claude API ─────────────────────────────────────────────────────────────────

class ClaudeError(Exception):
    pass


class ClaudeRateLimitError(ClaudeError):
    pass


class ClaudeHTTPError(ClaudeError):
    pass


class ClaudeEmptyResponseError(ClaudeError):
    pass


def _extract_retry_after_seconds(error: urllib.error.HTTPError) -> Optional[int]:
    try:
        retry_after = error.headers.get("Retry-After")
        if retry_after and str(retry_after).isdigit():
            return int(retry_after)
    except Exception:
        pass
    return None


def _extract_text_from_anthropic_response(data: dict) -> str:
    parts = []
    for block in data.get("content", []):
        if block.get("type") == "text":
            txt = block.get("text", "")
            if txt:
                parts.append(txt)
    return "\n".join(parts).strip()


def call_claude(
    prompt: str,
    retries: int = 4,
    max_tokens: int = MAX_TOKENS_ARTICLE,
    use_web_search: bool = False,
) -> str:
    if not ANTHROPIC_KEY:
        raise ClaudeError("Falta ANTHROPIC_KEY en variables de entorno")

    last_error = None

    for attempt in range(retries):
        if attempt > 0:
            backoff = API_PAUSE_ON_429 + ((attempt - 1) * 45) + random.randint(5, 20)
            log.info(f"Esperando {backoff}s antes de reintentar Claude...")
            time.sleep(backoff)

        try:
            payload_dict = {
                "model": ANTHROPIC_MODEL,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }

            if use_web_search:
                payload_dict["tools"] = [
                    {"type": "web_search_20250305", "name": "web_search"}
                ]

            payload = json.dumps(payload_dict).encode("utf-8")

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                },
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))

            text = _extract_text_from_anthropic_response(data)

            if not text:
                raise ClaudeEmptyResponseError(
                    f"Respuesta vacia de Claude: {json.dumps(data)[:1200]}"
                )

            return text

        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""

            retry_after = _extract_retry_after_seconds(e)

            if e.code == 429:
                wait_hint = retry_after if retry_after is not None else API_PAUSE_ON_429
                log.warning(
                    f"Rate limit (429) en intento {attempt+1}/{retries}. "
                    f"Retry-After={retry_after}. Body={body[:700]}"
                )
                last_error = ClaudeRateLimitError(
                    f"429 rate limit. Retry-After={retry_after}. Body={body[:1000]}"
                )

                if attempt == retries - 1:
                    raise last_error

                sleep_for = max(wait_hint, API_PAUSE_ON_429) + random.randint(5, 15)
                log.info(f"Esperando {sleep_for}s por rate limit antes del siguiente intento...")
                time.sleep(sleep_for)
                continue

            last_error = ClaudeHTTPError(f"HTTP {e.code}: {body[:1000]}")
            log.warning(f"HTTP {e.code} en intento {attempt+1}/{retries}: {body[:700]}")

            if attempt == retries - 1:
                raise last_error

        except urllib.error.URLError as e:
            last_error = ClaudeError(f"Network error: {e}")
            log.warning(f"Error de red en intento {attempt+1}/{retries}: {e}")

            if attempt == retries - 1:
                raise last_error

        except ClaudeError as e:
            last_error = e
            log.warning(f"ClaudeError en intento {attempt+1}/{retries}: {e}")

            if attempt == retries - 1:
                raise last_error

        except Exception as e:
            last_error = ClaudeError(str(e))
            log.warning(f"Error en intento {attempt+1}/{retries}: {e}")

            if attempt == retries - 1:
                raise last_error

    raise ClaudeError(str(last_error) if last_error else "Claude fallo sin detalle")


def call_claude_json(
    prompt: str,
    retries: int = 4,
    max_tokens: int = MAX_TOKENS_ARTICLE,
    use_web_search: bool = False
) -> dict:
    last_raw = ""

    for attempt in range(retries):
        try:
            if attempt > 0 and last_raw:
                fix_prompt = (
                    "The following content was intended to be a valid JSON object but may be malformed.\n"
                    "Return ONLY the corrected valid JSON object.\n"
                    "No markdown fences. No explanation. No extra text.\n\n"
                    + last_raw[:6000]
                )
                raw = call_claude(
                    fix_prompt,
                    retries=3,
                    max_tokens=max_tokens,
                    use_web_search=False,
                )
            else:
                raw = call_claude(
                    prompt,
                    retries=3,
                    max_tokens=max_tokens,
                    use_web_search=use_web_search,
                )

            last_raw = raw
            return parse_json_robust(raw)

        except json.JSONDecodeError as e:
            log.warning(f"JSON invalido en intento {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(API_JSON_RETRY_PAUSE)

        except ClaudeRateLimitError as e:
            log.warning(f"Rate limit real en intento JSON {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(API_PAUSE_ON_429 + random.randint(10, 25))

        except ClaudeError as e:
            log.warning(f"Claude fallo en intento JSON {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(API_JSON_RETRY_PAUSE)

        except Exception as e:
            log.warning(f"Fallo inesperado en intento JSON {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(API_JSON_RETRY_PAUSE)

    raise ValueError("No se pudo obtener JSON valido despues de todos los intentos")


def parse_json_robust(text: str) -> dict:
    text = text.strip()
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    for closing in [']}', '}}', '}']:
        try:
            return json.loads(text + closing)
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("No se pudo parsear", text, 0)


# ── Generador de titulos ───────────────────────────────────────────────────────

def generate_titles(count: int = 20) -> list:
    log.info(f"Generando {count} titulos con busqueda de tendencias...")

    prompt = f"""You are an SEO expert building a content strategy for {SITE_NAME}, 
an affiliate site about {SITE_TOPIC} targeting {SITE_AUDIENCE}.

Use web_search to research:
- Current trending searches related to {SITE_TOPIC} in 2026
- High-volume, low-competition keywords in this niche
- Popular product comparisons and buyer-intent searches

Then generate {count} article titles optimized for SEO and Amazon affiliate conversions.

Title format requirements:
- VARY the format: comparisons, how-tos, guides, questions, "vs" articles, "under $X", seasonal content
- NOT all "Best X" titles — mix it up
- Target long-tail keywords with real search volume
- High buyer intent
- Natural, human-sounding

Return ONLY a valid JSON array, no markdown, no extra text:
[
  {{
    "title": "Article title here",
    "keyword": "target keyword",
    "category": "Category Name",
    "products": ["Brand Model 1", "Brand Model 2", "Brand Model 3"],
    "search_volume": "high"
  }}
]"""

    raw = call_claude(
        prompt,
        retries=4,
        max_tokens=MAX_TOKENS_TITLES,
        use_web_search=ENABLE_WEB_SEARCH_FOR_TITLES,
    )

    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        raise ValueError("Claude no devolvio un array JSON")

    titles = json.loads(match.group())
    log.info(f"Titulos generados: {len(titles)}")
    return titles


def load_titles() -> list:
    if TITLES_FILE.exists():
        return json.loads(TITLES_FILE.read_text())
    return []


def save_titles(titles: list):
    TITLES_FILE.parent.mkdir(exist_ok=True)
    TITLES_FILE.write_text(json.dumps(titles, indent=2, ensure_ascii=False))
    log.info(f"Guardados {len(titles)} titulos en {TITLES_FILE}")


def get_next_title(published: list, titles: list):
    published_titles = {p["title"] for p in published}
    available = [t for t in titles if t["title"] not in published_titles]
    high = [t for t in available if t.get("search_volume") == "high"]
    med  = [t for t in available if t.get("search_volume") == "medium"]
    low  = [t for t in available if t.get("search_volume") == "low"]
    queue = high + med + low
    return queue[0] if queue else None


def ensure_titles(min_titles: int = 10) -> list:
    published = load_posts_meta()
    published_titles = {p["title"] for p in published}
    titles = load_titles()
    available = [t for t in titles if t["title"] not in published_titles]

    if len(available) < min_titles:
        log.info(f"Solo {len(available)} titulos disponibles — generando mas...")
        new_titles = generate_titles(count=20)
        existing = {t["title"] for t in titles}
        for t in new_titles:
            if t["title"] not in existing:
                titles.append(t)
        save_titles(titles)
        available = [t for t in titles if t["title"] not in published_titles]
        log.info(f"Ahora hay {len(available)} titulos disponibles")

    return titles


# ── Generador de articulos ─────────────────────────────────────────────────────

def generate_article(topic: dict) -> dict:
    products_str = "\n".join(f"- {p}" for p in topic["products"])

    prompt = f"""You are an expert gear reviewer for {SITE_NAME}, a trusted site about {SITE_TOPIC}.
Write a comprehensive SEO-optimized review for {SITE_AUDIENCE}.

Title: {topic["title"]}
Target keyword: {topic["keyword"]}
Category: {topic["category"]}
Products:
{products_str}

Return ONLY a valid JSON object. No markdown, no text before or after.

{{
  "intro": "2-3 paragraphs. Include the target keyword naturally. Explain who this is for.",
  "products": [
    {{
      "name": "Exact product name",
      "rating": 4.5,
      "price_range": "$X - $Y",
      "verdict": "One punchy sentence.",
      "pros": ["pro 1", "pro 2", "pro 3"],
      "cons": ["con 1", "con 2"],
      "review": "2 paragraphs. Specific specs, real-world performance, who it suits best."
    }}
  ],
  "buying_guide": "2 paragraphs. What to look for. Show real expertise.",
  "faq": [
    {{"q": "Question buyers ask?", "a": "Detailed answer."}},
    {{"q": "Another question?", "a": "Detailed answer."}}
  ],
  "conclusion": "1 paragraph. Clear recommendation with call to action."
}}"""

    log.info(f"Generating: {topic['title']}")
    return call_claude_json(
        prompt,
        retries=4,
        max_tokens=MAX_TOKENS_ARTICLE,
        use_web_search=ENABLE_WEB_SEARCH_FOR_ARTICLES,
    )


# ── Render HTML ────────────────────────────────────────────────────────────────

def amazon_link(product: str) -> str:
    q = urllib.parse.quote_plus(product)
    return f"https://www.{AMAZON_STORE}/s?k={q}&tag={AMAZON_TAG}"


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")[:80]


def render_html(topic: dict, content: dict, slug: str, date_display: str) -> str:
    products_html = ""
    for i, p in enumerate(content.get("products", []), 1):
        alink = amazon_link(p["name"])
        pros  = "".join(f"<li>{x}</li>" for x in p.get("pros", []))
        cons  = "".join(f"<li>{x}</li>" for x in p.get("cons", []))
        badge = "Editor's Pick" if i == 1 else ("Best Value" if i == 2 else "")
        badge_html = f'<span class="badge">{badge}</span>' if badge else ""
        products_html += f"""
        <div class="product-card" id="pick-{i}">
          <div class="product-header">
            <div class="product-rank">#{i}</div>
            <h2 class="product-name">{p["name"]} {badge_html}</h2>
            <div class="product-meta">
              <span class="price">{p.get("price_range","")}</span>
              <span class="rating">{"&#9733;" * int(float(p.get("rating",4)))}&nbsp;{p.get("rating","4.5")}/5</span>
            </div>
            <p class="verdict">{p.get("verdict","")}</p>
          </div>
          <div class="product-body">
            <div class="pros-cons">
              <div class="pros"><h4>Pros</h4><ul>{pros}</ul></div>
              <div class="cons"><h4>Cons</h4><ul>{cons}</ul></div>
            </div>
            <div class="review-text">{p.get("review","").replace(chr(10),"<br>")}</div>
            <a href="{alink}" class="cta-btn" target="_blank" rel="nofollow noopener">Check Price on Amazon</a>
          </div>
        </div>"""

    faq_html = "".join(
        f'<details class="faq-item"><summary>{f["q"]}</summary><p>{f["a"]}</p></details>'
        for f in content.get("faq", [])
    )
    quick_links = "".join(
        f'<li><a href="#pick-{i+1}">{p["name"]}</a></li>'
        for i, p in enumerate(content.get("products", []))
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="{topic['title']} — Expert reviews updated {date_display[:4]}.">
<title>{topic['title']} | {SITE_NAME}</title>
<link rel="canonical" href="{SITE_URL}/posts/{slug}.html">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@400;600&family=Source+Sans+3:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#f9f7f3;--surface:#fff;--border:#e8e4db;--text:#1c1a16;--muted:#6b6761;--accent:#1b6b3a;--accent-bg:#eef7f2;--warn:#92400e;--serif:'Lora',serif;--sans:'Source Sans 3',sans-serif;--radius:10px}}
body{{font-family:var(--sans);background:var(--bg);color:var(--text);line-height:1.7;font-size:17px}}
a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}
.site-header{{background:var(--surface);border-bottom:1px solid var(--border);padding:0 20px;position:sticky;top:0;z-index:100}}
.header-inner{{max-width:820px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;height:52px}}
.logo{{font-family:var(--serif);font-size:20px;color:var(--accent);font-weight:600}}
.logo span{{color:var(--muted);font-weight:400}}
.nav{{display:flex;gap:20px;font-size:14px}}.nav a{{color:var(--muted)}}
.container{{max-width:820px;margin:0 auto;padding:32px 20px 80px}}
.article-category{{font-size:12px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:10px}}
h1{{font-family:var(--serif);font-size:clamp(24px,4vw,36px);line-height:1.2;font-weight:600;letter-spacing:-.02em;margin-bottom:12px}}
.article-meta{{font-size:13px;color:var(--muted);display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px}}
.updated{{background:var(--accent-bg);color:var(--accent);padding:2px 10px;border-radius:20px;font-size:12px;font-weight:500}}
.intro{{font-size:18px;line-height:1.75;color:#2a2820;margin-bottom:32px;padding-bottom:32px;border-bottom:1px solid var(--border)}}
.quick-nav{{background:var(--accent-bg);border-radius:var(--radius);padding:16px 20px;margin-bottom:32px;border:1px solid rgba(27,107,58,.15)}}
.quick-nav h3{{font-size:13px;font-weight:500;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px}}
.quick-nav ol{{padding-left:18px;font-size:14px;line-height:2}}.quick-nav a{{color:var(--text)}}
.ad-slot{{background:var(--bg);border:1px dashed var(--border);border-radius:8px;padding:20px;text-align:center;color:var(--muted);font-size:12px;margin:28px 0;min-height:90px;display:flex;align-items:center;justify-content:center}}
.product-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);margin-bottom:24px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.product-header{{padding:20px 24px 12px}}
.product-rank{{font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:4px}}
.product-name{{font-family:var(--serif);font-size:22px;font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.badge{{font-size:11px;font-weight:500;background:var(--accent);color:#fff;padding:2px 10px;border-radius:20px}}
.product-meta{{display:flex;gap:16px;font-size:14px;margin-bottom:8px}}
.rating{{color:#d97706}}.verdict{{font-size:15px;color:var(--muted);font-style:italic}}
.product-body{{padding:0 24px 24px}}
.pros-cons{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0 20px}}
.pros h4,.cons h4{{font-size:13px;font-weight:500;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}}
.pros h4{{color:var(--accent)}}.cons h4{{color:var(--warn)}}
.pros-cons ul{{padding-left:16px;font-size:14px;line-height:1.9;color:var(--muted)}}
.review-text{{font-size:15px;line-height:1.75;margin-bottom:20px;color:#2a2820}}
.cta-btn{{display:inline-block;background:var(--accent);color:#fff;padding:12px 24px;border-radius:8px;font-size:15px;font-weight:500;transition:background .15s}}
.cta-btn:hover{{background:#145a2e;text-decoration:none}}
.section-title{{font-family:var(--serif);font-size:26px;font-weight:600;margin:40px 0 16px}}
.buying-guide{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;font-size:15px;line-height:1.8}}
.faq-item{{border:1px solid var(--border);border-radius:8px;margin-bottom:10px;overflow:hidden}}
.faq-item summary{{padding:14px 18px;font-size:15px;font-weight:500;cursor:pointer;list-style:none;display:flex;justify-content:space-between}}
.faq-item summary::after{{content:"+"}}
.faq-item[open] summary::after{{content:"-"}}
.faq-item p{{padding:0 18px 16px;font-size:14px;color:var(--muted);line-height:1.7}}
.conclusion{{background:var(--accent-bg);border-radius:var(--radius);padding:24px;font-size:15px;line-height:1.8;border:1px solid rgba(27,107,58,.15)}}
footer{{border-top:1px solid var(--border);margin-top:56px;padding:24px 20px;text-align:center;font-size:12px;color:var(--muted)}}
footer a{{color:var(--muted)}}
@media(max-width:600px){{.pros-cons{{grid-template-columns:1fr}}.product-header,.product-body{{padding-left:16px;padding-right:16px}}}}
</style>
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <div class="logo">{SITE_NAME}<span> Reviews</span></div>
    <nav class="nav"><a href="/">Home</a></nav>
  </div>
</header>
<main class="container">
  <div class="article-category">{topic["category"]}</div>
  <h1>{topic["title"]}</h1>
  <div class="article-meta">
    <span>By {SITE_NAME} Staff</span><span>·</span>
    <span class="updated">Updated {date_display}</span><span>·</span>
    <span>{len(content.get("products",[]))} products reviewed</span>
  </div>
  <div class="intro">{content.get("intro","").replace(chr(10),"<br>")}</div>
  <div class="quick-nav">
    <h3>In This Review</h3>
    <ol>{quick_links}<li><a href="#buying-guide">Buying Guide</a></li><li><a href="#faq">FAQ</a></li></ol>
  </div>
  <div class="ad-slot">Advertisement</div>
  {products_html}
  <div class="ad-slot">Advertisement</div>
  <h2 class="section-title" id="buying-guide">Buying Guide</h2>
  <div class="buying-guide">{content.get("buying_guide","").replace(chr(10),"<br>")}</div>
  <h2 class="section-title" id="faq">Frequently Asked Questions</h2>
  {faq_html}
  <h2 class="section-title">Our Verdict</h2>
  <div class="conclusion">{content.get("conclusion","").replace(chr(10),"<br>")}</div>
</main>
<footer>
  <p>{SITE_NAME} — Independent gear reviews</p>
  <p style="margin-top:6px">As an Amazon Associate we earn from qualifying purchases · <a href="/privacy.html">Privacy Policy</a></p>
</footer>
</body>
</html>"""


# ── Index & Sitemap ────────────────────────────────────────────────────────────

def rebuild_index(posts_meta: list):
    cards = "".join(
        f'<a class="post-card" href="posts/{p["slug"]}.html">'
        f'<div class="post-cat">{p["category"]}</div>'
        f'<h2 class="post-title">{p["title"]}</h2>'
        f'<div class="post-meta">{p["date"]} · {p.get("product_count",3)} products reviewed</div>'
        f'</a>'
        for p in sorted(posts_meta, key=lambda x: x["date"], reverse=True)
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="{SITE_NAME} — Expert {SITE_TOPIC} reviews. Honest picks for every budget.">
<title>{SITE_NAME} — Gear Reviews 2026</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@400;600&family=Source+Sans+3:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#f9f7f3;--surface:#fff;--border:#e8e4db;--text:#1c1a16;--muted:#6b6761;--accent:#1b6b3a;--serif:'Lora',serif;--sans:'Source Sans 3',sans-serif}}
body{{font-family:var(--sans);background:var(--bg);color:var(--text)}}
.site-header{{background:var(--surface);border-bottom:1px solid var(--border);padding:0 20px;position:sticky;top:0;z-index:100}}
.header-inner{{max-width:1000px;margin:0 auto;display:flex;align-items:center;height:52px}}
.logo{{font-family:var(--serif);font-size:20px;color:var(--accent);font-weight:600}}
.logo span{{color:var(--muted);font-weight:400}}
.hero{{background:var(--surface);border-bottom:1px solid var(--border);padding:56px 20px}}
.hero-inner{{max-width:680px;margin:0 auto;text-align:center}}
.hero h1{{font-family:var(--serif);font-size:clamp(28px,5vw,42px);font-weight:600;line-height:1.2;letter-spacing:-.02em;margin-bottom:14px}}
.hero p{{font-size:17px;color:var(--muted);line-height:1.6}}
main{{max-width:1000px;margin:0 auto;padding:40px 20px 80px}}
.section-label{{font-size:11px;font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:16px}}
.posts-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}}
.post-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px;text-decoration:none;color:var(--text);transition:all .15s;display:block}}
.post-card:hover{{border-color:#1b6b3a;box-shadow:0 0 0 3px rgba(27,107,58,.08);transform:translateY(-1px)}}
.post-cat{{font-size:11px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:8px}}
.post-title{{font-family:var(--serif);font-size:17px;font-weight:600;line-height:1.3;margin-bottom:8px}}
.post-meta{{font-size:12px;color:var(--muted)}}
footer{{border-top:1px solid var(--border);padding:24px 20px;text-align:center;font-size:12px;color:var(--muted)}}
footer a{{color:var(--muted)}}
</style>
</head>
<body>
<header class="site-header"><div class="header-inner"><div class="logo">{SITE_NAME}<span> Reviews</span></div></div></header>
<section class="hero"><div class="hero-inner">
  <h1>Honest Gear Reviews You Can Trust</h1>
  <p>Independent reviews of {SITE_TOPIC} so you spend less time researching and more time outdoors.</p>
</div></section>
<main>
  <div class="section-label">Latest Reviews</div>
  <div class="posts-grid">{cards or "<p style='color:var(--muted);padding:40px 0'>No articles yet.</p>"}</div>
</main>
<footer>
  <p>{SITE_NAME} — Independent gear reviews</p>
  <p style="margin-top:6px">As an Amazon Associate we earn from qualifying purchases · <a href="/privacy.html">Privacy Policy</a></p>
</footer>
</body></html>"""
    with open(REPO_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html)
    log.info("index.html rebuilt")


def rebuild_sitemap(posts_meta: list):
    urls = [f"<url><loc>{SITE_URL}/</loc></url>"] + [
        f"<url><loc>{SITE_URL}/posts/{p['slug']}.html</loc><lastmod>{p['date']}</lastmod></url>"
        for p in posts_meta
    ]
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>")
    with open(REPO_DIR / "sitemap.xml", "w", encoding="utf-8") as f:
        f.write(xml)
    log.info("sitemap.xml rebuilt")


# ── Git ────────────────────────────────────────────────────────────────────────

def git_push(message: str) -> bool:
    for cmd in [
        ["git", "-C", str(REPO_DIR), "add", "-A"],
        ["git", "-C", str(REPO_DIR), "commit", "-m", message],
        ["git", "-C", str(REPO_DIR), "push"],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
            log.warning(f"git: {r.stderr.strip()}")
            return False
    log.info(f"Pushed: {message}")
    return True


# ── Core ───────────────────────────────────────────────────────────────────────

def load_posts_meta() -> list:
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else []


def save_posts_meta(meta: list):
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False))


def run_once(date_override: str = None) -> bool:
    titles    = ensure_titles(min_titles=5)
    published = load_posts_meta()
    topic     = get_next_title(published, titles)

    if not topic:
        log.info("Sin titulos disponibles — generando nuevos...")
        titles    = ensure_titles(min_titles=0)
        published = load_posts_meta()
        topic     = get_next_title(published, titles)
        if not topic:
            log.error("No se pudieron generar titulos.")
            return False

    log.info(f"Pausa de {API_PAUSE_BETWEEN_CALLS}s antes de generar...")
    time.sleep(API_PAUSE_BETWEEN_CALLS)

    try:
        content = generate_article(topic)
    except Exception as e:
        log.error(f"Error generando articulo: {e}")
        return False

    slug         = slugify(topic["title"])
    date_iso     = date_override or datetime.now().strftime("%Y-%m-%d")
    date_display = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%B %d, %Y")

    POSTS_DIR.mkdir(exist_ok=True)
    (POSTS_DIR / f"{slug}.html").write_text(
        render_html(topic, content, slug, date_display), encoding="utf-8"
    )
    log.info(f"Saved: {slug}.html")

    published.append({
        "title":         topic["title"],
        "slug":          slug,
        "category":      topic["category"],
        "date":          date_iso,
        "keyword":       topic["keyword"],
        "product_count": len(content.get("products", [])),
    })
    save_posts_meta(published)
    rebuild_index(published)
    rebuild_sitemap(published)
    git_push(f"content: {topic['title'][:60]}")

    remaining = sum(1 for t in titles if t["title"] not in {p["title"] for p in published})
    log.info(f"Done. ~{remaining} titulos restantes.")
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Universal Affiliate Content Bot")
    parser.add_argument("--loop",      action="store_true", help="1 articulo por dia indefinidamente")
    parser.add_argument("--batch",     type=int, metavar="N", help="Genera N articulos con fechas escalonadas")
    parser.add_argument("--gentitles", type=int, metavar="N", help="Solo genera N titulos nuevos")
    parser.add_argument("--build",     action="store_true", help="Solo regenera index y sitemap")
    args = parser.parse_args()

    if args.build:
        m = load_posts_meta()
        rebuild_index(m)
        rebuild_sitemap(m)
        git_push("build: rebuild index and sitemap")
        return

    if args.gentitles:
        log.info(f"Generando {args.gentitles} titulos nuevos...")
        titles     = load_titles()
        new_titles = generate_titles(count=args.gentitles)
        existing   = {t["title"] for t in titles}
        added = sum(1 for t in new_titles if t["title"] not in existing and titles.append(t) is None)
        save_titles(titles)
        log.info(f"Agregados {added} titulos. Total: {len(titles)}")
        git_push(f"titles: generated {added} new SEO titles")
        return

    if args.batch:
        log.info(f"Modo batch: {args.batch} articulos con fechas escalonadas")
        for i in range(args.batch):
            date = (datetime.now() - timedelta(days=args.batch - i - 1)).strftime("%Y-%m-%d")
            log.info(f"Articulo {i+1}/{args.batch} — fecha: {date}")
            run_once(date_override=date)
            if i < args.batch - 1:
                pause = random.randint(BATCH_PAUSE_MIN, BATCH_PAUSE_MAX)
                log.info(f"Pausa {pause}s entre articulos...")
                time.sleep(pause)
        return

    if args.loop:
        log.info("Modo loop: 1 articulo por dia")
        while True:
            run_once()
            sleep = LOOP_INTERVAL + random.randint(-1800, 1800)
            log.info(f"Proximo en {sleep//3600}h {(sleep%3600)//60}m")
            time.sleep(sleep)
    else:
        run_once()


if __name__ == "__main__":
    main()