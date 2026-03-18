"""
TackleReviewer — Content Bot
Genera artículos SEO de pesca con Claude API y los publica automáticamente.
Corre en tu compu, hace git push, Vercel despliega solo.

Uso:
    python scripts/content_bot.py            # genera 1 artículo y pushea
    python scripts/content_bot.py --loop     # genera 1 artículo por día indefinidamente
    python scripts/content_bot.py --build    # solo regenera el index y el sitemap
"""

import json
import time
import random
import logging
import argparse
import subprocess
import urllib.request
import urllib.parse
import re
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
REPO_DIR      = Path(__file__).parent.parent
POSTS_DIR     = REPO_DIR / "posts"
DATA_FILE     = REPO_DIR / "data" / "posts.json"
AMAZON_TAG    = "tacklerev-20"          # ← reemplazá con tu tag de Amazon Associates
ANTHROPIC_KEY = "TU_API_KEY_AQUI"      # ← reemplazá con tu API key de Claude
ARTICLES_PER_DAY = 1                    # genera 1 artículo por día (suficiente para SEO)
LOOP_INTERVAL = 86400                   # 24 horas en segundos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(REPO_DIR / "bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Temas a cubrir ─────────────────────────────────────────────────────────────
# El bot va tomando temas de esta lista en orden. Podés agregar más.
TOPICS = [
    {"title": "Best Fish Finders Under $200 in 2026", "keyword": "best fish finders under 200", "category": "Electronics", "products": ["Garmin Striker 4", "Humminbird Helix 5", "Lowrance Hook Reveal 5"]},
    {"title": "Best Spinning Rods for Bass Fishing 2026", "keyword": "best spinning rods bass fishing", "category": "Rods", "products": ["St. Croix Triumph", "Ugly Stik GX2", "Shakespeare Ugly Stik Carbon"]},
    {"title": "Best Spinning Reels Under $100 — 2026 Review", "keyword": "best spinning reels under 100", "category": "Reels", "products": ["Shimano Sienna FE", "Penn Battle III", "Daiwa BG MQ"]},
    {"title": "Best Fishing Line for Bass: Mono vs Fluoro vs Braid", "keyword": "best fishing line for bass", "category": "Line", "products": ["PowerPro Spectra", "Berkley Trilene XL", "Seaguar InvizX Fluorocarbon"]},
    {"title": "Best Tackle Boxes for Freshwater Fishing 2026", "keyword": "best tackle boxes freshwater fishing", "category": "Storage", "products": ["Plano 3700", "Flambeau Tuff Tainer", "Bass Pro Shops Extreme"]},
    {"title": "Best Kayak Fishing Paddles 2026 — Buyer's Guide", "keyword": "best kayak fishing paddles", "category": "Kayak", "products": ["Aqua-Bound Manta Ray", "Werner Skagit", "BKC Kayak Paddle"]},
    {"title": "Best Ice Fishing Rods and Combos 2026", "keyword": "best ice fishing rods combos", "category": "Ice Fishing", "products": ["13 Fishing Tickle Stick", "Ugly Stik Ice Rod", "Frabill Ice Combo"]},
    {"title": "Best Waders for Fly Fishing 2026 — Top Picks", "keyword": "best waders fly fishing", "category": "Apparel", "products": ["Simms G3 Guide", "Orvis Silver Sonic", "Hodgman Aesis"]},
    {"title": "Best Lures for Largemouth Bass — Complete Guide 2026", "keyword": "best lures largemouth bass", "category": "Lures", "products": ["Strike King Red Eye Shad", "Zoom Trick Worm", "Rapala Original Floater"]},
    {"title": "Best Fishing Sunglasses with Polarized Lenses 2026", "keyword": "best polarized fishing sunglasses", "category": "Accessories", "products": ["Costa Del Mar Fantail", "Oakley Flak 2.0", "Maui Jim Peahi"]},
    {"title": "Best Baitcasting Reels for Beginners 2026", "keyword": "best baitcasting reels beginners", "category": "Reels", "products": ["Abu Garcia Black Max", "Shimano SLX", "Lew's American Hero"]},
    {"title": "Best Saltwater Spinning Reels Under $150", "keyword": "best saltwater spinning reels under 150", "category": "Saltwater", "products": ["Penn Battle III", "Shimano Stradic FL", "Daiwa BG"]},
    {"title": "Best Fly Fishing Rods for Beginners 2026", "keyword": "best fly fishing rods beginners", "category": "Fly Fishing", "products": ["Orvis Clearwater", "Redington Classic Trout", "Echo Base"]},
    {"title": "Best Fishing Backpacks and Vests 2026", "keyword": "best fishing backpacks vests", "category": "Accessories", "products": ["Fishpond Thunderhead", "Simms Dry Creek", "Orvis Safe Passage"]},
    {"title": "Best Trout Fishing Lures — Tested and Ranked 2026", "keyword": "best trout fishing lures", "category": "Lures", "products": ["Panther Martin Spinner", "Rapala Countdown", "Mepps Aglia"]},
]


# ── Claude API ────────────────────────────────────────────────────────────────

def call_claude(prompt: str) -> str:
    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    return data["content"][0]["text"]


def amazon_link(product: str, tag: str) -> str:
    q = urllib.parse.quote_plus(product)
    return f"https://www.amazon.com/s?k={q}&tag={tag}"


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


# ── Generador de artículos ────────────────────────────────────────────────────

def generate_article(topic: dict) -> dict:
    products_str = "\n".join(f"- {p}" for p in topic["products"])
    amazon_tag   = AMAZON_TAG

    prompt = f"""You are an expert fishing gear reviewer writing for TackleReviewer.com, a trusted US fishing gear review site. Write a comprehensive SEO-optimized review article.

Title: {topic["title"]}
Target keyword: {topic["keyword"]}
Products to review: 
{products_str}

Write the article in this EXACT JSON format (respond with JSON only, no markdown fences):
{{
  "intro": "2-3 compelling paragraph intro that includes the target keyword naturally. Mention who this guide is for.",
  "products": [
    {{
      "name": "Product Name",
      "rating": 4.5,
      "price_range": "$X - $Y",
      "verdict": "one sentence verdict",
      "pros": ["pro 1", "pro 2", "pro 3"],
      "cons": ["con 1", "con 2"],
      "review": "2 paragraphs detailed honest review. Include specific specs, real-world performance, who it's best for."
    }}
  ],
  "buying_guide": "2 paragraphs: what to look for when buying this type of gear. Include technical details that show expertise.",
  "faq": [
    {{"q": "Common question about this gear?", "a": "Detailed helpful answer."}},
    {{"q": "Another common question?", "a": "Detailed helpful answer."}}
  ],
  "conclusion": "1 paragraph conclusion with clear recommendation and a call to action."
}}

Be specific, honest, and genuinely helpful. US fishing audience, casual but knowledgeable tone."""

    log.info(f"Generating article: {topic['title']}")
    raw = call_claude(prompt)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Intentar extraer JSON si vino con texto alrededor
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError("Claude no devolvió JSON válido")

    return data


def render_html(topic: dict, content: dict, slug: str, date_str: str) -> str:
    """Genera el HTML completo del artículo."""

    products_html = ""
    for i, p in enumerate(content.get("products", []), 1):
        alink = amazon_link(p["name"], AMAZON_TAG)
        pros  = "".join(f'<li>{x}</li>' for x in p.get("pros", []))
        cons  = "".join(f'<li>{x}</li>' for x in p.get("cons", []))
        badge = "Editor's Pick" if i == 1 else ("Best Value" if i == 2 else "")
        badge_html = f'<span class="badge">{badge}</span>' if badge else ""

        products_html += f"""
        <div class="product-card" id="pick-{i}">
          <div class="product-header">
            <div>
              <div class="product-rank">#{i}</div>
              <h2 class="product-name">{p['name']} {badge_html}</h2>
              <div class="product-meta">
                <span class="price">{p.get('price_range','')}</span>
                <span class="rating">{'★' * int(float(p.get('rating',4)))}&nbsp;{p.get('rating','4.5')}/5</span>
              </div>
              <p class="verdict">{p.get('verdict','')}</p>
            </div>
          </div>
          <div class="product-body">
            <div class="pros-cons">
              <div class="pros"><h4>Pros</h4><ul>{pros}</ul></div>
              <div class="cons"><h4>Cons</h4><ul>{cons}</ul></div>
            </div>
            <div class="review-text">{p.get('review','').replace(chr(10),'<br>')}</div>
            <a href="{alink}" class="cta-btn" target="_blank" rel="nofollow noopener">
              Check Price on Amazon →
            </a>
          </div>
        </div>"""

    faq_html = ""
    for faq in content.get("faq", []):
        faq_html += f"""
        <details class="faq-item">
          <summary>{faq['q']}</summary>
          <p>{faq['a']}</p>
        </details>"""

    buying = content.get("buying_guide","").replace("\n","<br>")
    intro  = content.get("intro","").replace("\n","<br>")
    conclusion = content.get("conclusion","").replace("\n","<br>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="{topic['title']} — Expert reviews, buying guide and top picks for {date_str[:4]}.">
<title>{topic['title']} | TackleReviewer</title>
<link rel="canonical" href="https://tacklereviewer.vercel.app/posts/{slug}.html">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@400;600&family=Source+Sans+3:wght@300;400;500&display=swap" rel="stylesheet">
<!-- Google AdSense — reemplazá con tu ID -->
<!-- <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-XXXX" crossorigin="anonymous"></script> -->
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#f9f7f3;--surface:#ffffff;--border:#e8e4db;
  --text:#1c1a16;--muted:#6b6761;--accent:#1b6b3a;
  --accent-bg:#eef7f2;--warn:#92400e;
  --serif:'Lora',serif;--sans:'Source Sans 3',sans-serif;
  --radius:10px;
}}
body{{font-family:var(--sans);background:var(--bg);color:var(--text);line-height:1.7;font-size:17px}}
a{{color:var(--accent);text-decoration:none}}
a:hover{{text-decoration:underline}}

/* Header */
.site-header{{background:var(--surface);border-bottom:1px solid var(--border);padding:0 20px;position:sticky;top:0;z-index:100}}
.header-inner{{max-width:820px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;height:52px}}
.logo{{font-family:var(--serif);font-size:20px;color:var(--accent);font-weight:600}}
.logo span{{color:var(--muted);font-weight:400}}
.nav{{display:flex;gap:20px;font-size:14px;color:var(--muted)}}
.nav a{{color:var(--muted)}}

/* Layout */
.container{{max-width:820px;margin:0 auto;padding:32px 20px 80px}}

/* Article header */
.article-header{{margin-bottom:32px}}
.article-category{{font-size:12px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:10px}}
.article-header h1{{font-family:var(--serif);font-size:clamp(26px,4vw,38px);line-height:1.2;font-weight:600;letter-spacing:-.02em;margin-bottom:12px}}
.article-meta{{font-size:13px;color:var(--muted);display:flex;gap:16px;align-items:center;flex-wrap:wrap}}
.article-meta .updated{{background:var(--accent-bg);color:var(--accent);padding:2px 10px;border-radius:20px;font-size:12px;font-weight:500}}

/* Intro */
.intro{{font-size:18px;line-height:1.75;color:#2a2820;margin-bottom:32px;padding-bottom:32px;border-bottom:1px solid var(--border)}}

/* Quick nav */
.quick-nav{{background:var(--accent-bg);border-radius:var(--radius);padding:16px 20px;margin-bottom:32px;border:1px solid rgba(27,107,58,.15)}}
.quick-nav h3{{font-size:13px;font-weight:500;color:var(--accent);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px}}
.quick-nav ol{{padding-left:18px;font-size:14px;line-height:2}}
.quick-nav a{{color:var(--text)}}

/* Ad slot */
.ad-slot{{background:var(--bg);border:1px dashed var(--border);border-radius:8px;padding:20px;text-align:center;color:var(--muted);font-size:12px;margin:28px 0;min-height:90px;display:flex;align-items:center;justify-content:center}}

/* Product cards */
.product-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);margin-bottom:24px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
.product-header{{padding:20px 24px 0}}
.product-rank{{font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}}
.product-name{{font-family:var(--serif);font-size:22px;font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.badge{{font-size:11px;font-weight:500;background:var(--accent);color:#fff;padding:2px 10px;border-radius:20px}}
.product-meta{{display:flex;gap:16px;font-size:14px;margin-bottom:10px}}
.price{{font-weight:500;color:var(--text)}}
.rating{{color:#d97706}}
.verdict{{font-size:15px;color:var(--muted);font-style:italic;margin-bottom:16px}}
.product-body{{padding:0 24px 24px}}
.pros-cons{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}}
.pros h4,.cons h4{{font-size:13px;font-weight:500;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}}
.pros h4{{color:var(--accent)}}
.cons h4{{color:var(--warn)}}
.pros-cons ul{{padding-left:16px;font-size:14px;line-height:1.9;color:var(--muted)}}
.review-text{{font-size:15px;line-height:1.75;margin-bottom:20px;color:#2a2820}}
.cta-btn{{display:inline-block;background:var(--accent);color:#fff;padding:12px 24px;border-radius:8px;font-size:15px;font-weight:500;transition:background .15s}}
.cta-btn:hover{{background:#145a2e;text-decoration:none}}

/* Buying guide */
.section-title{{font-family:var(--serif);font-size:26px;font-weight:600;margin:40px 0 16px}}
.buying-guide{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;font-size:15px;line-height:1.8}}

/* FAQ */
.faq-item{{border:1px solid var(--border);border-radius:8px;margin-bottom:10px;overflow:hidden}}
.faq-item summary{{padding:14px 18px;font-size:15px;font-weight:500;cursor:pointer;list-style:none;display:flex;justify-content:space-between}}
.faq-item summary::after{{content:'+'}}
.faq-item[open] summary::after{{content:'−'}}
.faq-item p{{padding:0 18px 16px;font-size:14px;color:var(--muted);line-height:1.7}}

/* Conclusion */
.conclusion{{background:var(--accent-bg);border-radius:var(--radius);padding:24px;font-size:15px;line-height:1.8;border:1px solid rgba(27,107,58,.15)}}

/* Footer */
footer{{border-top:1px solid var(--border);margin-top:56px;padding:24px 20px;text-align:center;font-size:12px;color:var(--muted)}}

@media(max-width:600px){{
  .pros-cons{{grid-template-columns:1fr}}
  .product-header{{padding:16px 16px 0}}
  .product-body{{padding:0 16px 16px}}
}}
</style>
</head>
<body>

<header class="site-header">
  <div class="header-inner">
    <div class="logo">Tackle<span>Reviewer</span></div>
    <nav class="nav">
      <a href="/">Home</a>
      <a href="/#rods">Rods</a>
      <a href="/#reels">Reels</a>
      <a href="/#electronics">Electronics</a>
    </nav>
  </div>
</header>

<main class="container">
  <div class="article-header">
    <div class="article-category">{topic['category']}</div>
    <h1>{topic['title']}</h1>
    <div class="article-meta">
      <span>By TackleReviewer Staff</span>
      <span>·</span>
      <span class="updated">Updated {date_str}</span>
      <span>·</span>
      <span>{len(content.get('products',[]))} products tested</span>
    </div>
  </div>

  <div class="intro">{intro}</div>

  <div class="quick-nav">
    <h3>Quick Navigation</h3>
    <ol>
      {"".join(f'<li><a href="#pick-{i+1}">{p["name"]}</a></li>' for i,p in enumerate(content.get("products",[])))}
      <li><a href="#buying-guide">Buying Guide</a></li>
      <li><a href="#faq">FAQ</a></li>
    </ol>
  </div>

  <div class="ad-slot">
    <!-- AdSense unit aquí -->
    Advertisement
  </div>

  {products_html}

  <div class="ad-slot">Advertisement</div>

  <h2 class="section-title" id="buying-guide">Buying Guide</h2>
  <div class="buying-guide">{buying}</div>

  <h2 class="section-title" id="faq">Frequently Asked Questions</h2>
  {faq_html}

  <h2 class="section-title">Our Verdict</h2>
  <div class="conclusion">{conclusion}</div>

</main>

<footer>
  <p>TackleReviewer — Independent fishing gear reviews since 2024</p>
  <p style="margin-top:6px">As an Amazon Associate we earn from qualifying purchases. <a href="/about.html">About us</a> · <a href="/privacy.html">Privacy</a></p>
</footer>

</body>
</html>"""


# ── Index builder ─────────────────────────────────────────────────────────────

def rebuild_index(posts_meta: list):
    """Regenera index.html con todos los artículos publicados."""
    cards = ""
    for p in sorted(posts_meta, key=lambda x: x["date"], reverse=True):
        cards += f"""
      <a class="post-card" href="posts/{p['slug']}.html">
        <div class="post-cat">{p['category']}</div>
        <h2 class="post-title">{p['title']}</h2>
        <div class="post-meta">{p['date']} · {p.get('product_count',3)} products reviewed</div>
      </a>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="TackleReviewer — Expert fishing gear reviews. Best rods, reels, fish finders and tackle for every angler.">
<title>TackleReviewer — Best Fishing Gear Reviews 2026</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@400;600&family=Source+Sans+3:wght@300;400;500&display=swap" rel="stylesheet">
<!-- <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-XXXX" crossorigin="anonymous"></script> -->
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#f9f7f3;--surface:#fff;--border:#e8e4db;--text:#1c1a16;--muted:#6b6761;--accent:#1b6b3a;--serif:'Lora',serif;--sans:'Source Sans 3',sans-serif}}
body{{font-family:var(--sans);background:var(--bg);color:var(--text)}}
.site-header{{background:var(--surface);border-bottom:1px solid var(--border);padding:0 20px;position:sticky;top:0;z-index:100}}
.header-inner{{max-width:1000px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;height:52px}}
.logo{{font-family:var(--serif);font-size:20px;color:var(--accent);font-weight:600}}
.logo span{{color:var(--muted);font-weight:400}}
.hero{{background:var(--surface);border-bottom:1px solid var(--border);padding:48px 20px}}
.hero-inner{{max-width:700px;margin:0 auto;text-align:center}}
.hero h1{{font-family:var(--serif);font-size:clamp(28px,5vw,44px);font-weight:600;line-height:1.2;letter-spacing:-.02em;margin-bottom:12px}}
.hero p{{font-size:17px;color:var(--muted);line-height:1.6}}
main{{max-width:1000px;margin:0 auto;padding:40px 20px 80px}}
.section-label{{font-size:11px;font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:16px}}
.posts-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}}
.post-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px;text-decoration:none;color:var(--text);transition:all .15s;display:block}}
.post-card:hover{{border-color:#1b6b3a;box-shadow:0 0 0 3px rgba(27,107,58,.08);transform:translateY(-1px)}}
.post-cat{{font-size:11px;font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:8px}}
.post-title{{font-family:var(--serif);font-size:17px;font-weight:600;line-height:1.3;margin-bottom:8px}}
.post-meta{{font-size:12px;color:var(--muted)}}
.empty{{text-align:center;padding:60px 20px;color:var(--muted)}}
footer{{border-top:1px solid var(--border);padding:24px 20px;text-align:center;font-size:12px;color:var(--muted)}}
</style>
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <div class="logo">Tackle<span>Reviewer</span></div>
  </div>
</header>
<section class="hero">
  <div class="hero-inner">
    <h1>Honest Fishing Gear Reviews<br>You Can Trust</h1>
    <p>We test and review the best rods, reels, fish finders and tackle so you can spend less time researching and more time fishing.</p>
  </div>
</section>
<main>
  <div class="section-label">Latest Reviews</div>
  <div class="posts-grid">
    {"<p class='empty'>No articles yet — run the bot to generate the first one.</p>" if not cards else cards}
  </div>
</main>
<footer>
  <p>TackleReviewer — Independent fishing gear reviews</p>
  <p style="margin-top:6px">As an Amazon Associate we earn from qualifying purchases.</p>
</footer>
</body>
</html>"""

    with open(REPO_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html)
    log.info("index.html rebuilt")


def rebuild_sitemap(posts_meta: list):
    base = "https://tacklereviewer.vercel.app"
    urls = [f"<url><loc>{base}/</loc></url>"]
    for p in posts_meta:
        urls.append(f"<url><loc>{base}/posts/{p['slug']}.html</loc><lastmod>{p['date']}</lastmod></url>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls) + "\n</urlset>"
    with open(REPO_DIR / "sitemap.xml", "w") as f:
        f.write(xml)
    log.info("sitemap.xml rebuilt")


# ── Git push ──────────────────────────────────────────────────────────────────

def git_push(message: str):
    cmds = [
        ["git", "-C", str(REPO_DIR), "add", "-A"],
        ["git", "-C", str(REPO_DIR), "commit", "-m", message],
        ["git", "-C", str(REPO_DIR), "push"],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 and "nothing to commit" not in r.stdout + r.stderr:
            log.warning(f"git: {r.stderr.strip()}")
            return False
    log.info(f"Pushed: {message}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def load_posts_meta() -> list:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []


def save_posts_meta(meta: list):
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False))


def get_next_topic(published: list) -> dict | None:
    published_titles = {p["title"] for p in published}
    for t in TOPICS:
        if t["title"] not in published_titles:
            return t
    return None


def run_once():
    posts_meta = load_posts_meta()
    topic = get_next_topic(posts_meta)

    if not topic:
        log.info("Todos los temas cubiertos. Agregá más en TOPICS.")
        return

    try:
        content = generate_article(topic)
    except Exception as e:
        log.error(f"Error generando artículo: {e}")
        return

    slug      = slugify(topic["title"])
    date_str  = datetime.now().strftime("%B %d, %Y")
    date_iso  = datetime.now().strftime("%Y-%m-%d")

    # Guardar artículo HTML
    POSTS_DIR.mkdir(exist_ok=True)
    html_path = POSTS_DIR / f"{slug}.html"
    html_path.write_text(render_html(topic, content, slug, date_str), encoding="utf-8")
    log.info(f"Article saved: {html_path}")

    # Actualizar metadata
    posts_meta.append({
        "title":         topic["title"],
        "slug":          slug,
        "category":      topic["category"],
        "date":          date_iso,
        "keyword":       topic["keyword"],
        "product_count": len(content.get("products", [])),
    })
    save_posts_meta(posts_meta)

    # Rebuild index + sitemap
    rebuild_index(posts_meta)
    rebuild_sitemap(posts_meta)

    # Push
    git_push(f"content: {topic['title'][:60]}")
    log.info(f"Done. {len(TOPICS) - len(posts_meta)} topics remaining.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop",  action="store_true", help="Genera 1 artículo por día indefinidamente")
    parser.add_argument("--build", action="store_true", help="Solo regenera index y sitemap")
    args = parser.parse_args()

    if args.build:
        posts_meta = load_posts_meta()
        rebuild_index(posts_meta)
        rebuild_sitemap(posts_meta)
        git_push("build: rebuild index and sitemap")
        return

    if args.loop:
        log.info("Modo loop — 1 artículo por día")
        while True:
            run_once()
            jitter = random.randint(-1800, 1800)
            sleep  = LOOP_INTERVAL + jitter
            log.info(f"Próximo artículo en {sleep//3600}h {(sleep%3600)//60}m")
            time.sleep(sleep)
    else:
        run_once()


if __name__ == "__main__":
    main()
