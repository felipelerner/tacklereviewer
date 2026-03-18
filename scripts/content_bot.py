"""
TackleReviewer — Content Bot
Genera artículos SEO de pesca, camping y caza con Claude API.

Uso:
    python scripts/content_bot.py              # genera 1 artículo
    python scripts/content_bot.py --loop       # 1 artículo por día indefinidamente
    python scripts/content_bot.py --batch 10   # genera 10 artículos con fechas escalonadas
    python scripts/content_bot.py --build      # solo regenera index y sitemap
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
import re
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
REPO_DIR      = Path(__file__).parent.parent
POSTS_DIR     = REPO_DIR / "posts"
DATA_FILE     = REPO_DIR / "data" / "posts.json"
AMAZON_TAG    = "tacklereviewe-20"
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
LOOP_INTERVAL = 86400

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(REPO_DIR / "bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Temas ──────────────────────────────────────────────────────────────────────
TOPICS = [
    # Pesca — ya generados (el bot los saltea automáticamente)
    {"title": "Best Fish Finders Under $200 in 2026", "keyword": "best fish finders under 200", "category": "Electronics", "products": ["Garmin Striker 4", "Humminbird Helix 5", "Lowrance Hook Reveal 5"]},
    {"title": "Best Spinning Rods for Bass Fishing 2026", "keyword": "best spinning rods bass fishing", "category": "Rods", "products": ["St. Croix Triumph", "Ugly Stik GX2", "Shakespeare Ugly Stik Carbon"]},
    {"title": "Best Spinning Reels Under $100 — 2026 Review", "keyword": "best spinning reels under 100", "category": "Reels", "products": ["Shimano Sienna FE", "Penn Battle III", "Daiwa BG MQ"]},
    {"title": "Best Fishing Line for Bass: Mono vs Fluoro vs Braid", "keyword": "best fishing line for bass", "category": "Line", "products": ["PowerPro Spectra", "Berkley Trilene XL", "Seaguar InvizX Fluorocarbon"]},

    # Pesca — títulos variados
    {"title": "Shimano vs Daiwa: Which Reel Brand Wins in 2026?", "keyword": "shimano vs daiwa reels comparison", "category": "Reels", "products": ["Shimano Stradic FL", "Daiwa BG MQ", "Shimano Sahara FJ"]},
    {"title": "How to Choose a Fish Finder: Complete Buyer's Guide", "keyword": "how to choose a fish finder", "category": "Electronics", "products": ["Garmin Striker Vivid 7cv", "Humminbird Helix 7", "Lowrance Hook Reveal 7"]},
    {"title": "The 5 Best Lures for Largemouth Bass This Season", "keyword": "best lures largemouth bass 2026", "category": "Lures", "products": ["Strike King Red Eye Shad", "Zoom Trick Worm", "Rapala Original Floater", "Senko Worm Gary Yamamoto", "Booyah Spinnerbait"]},
    {"title": "Fly Fishing for Beginners: Gear You Actually Need", "keyword": "fly fishing gear beginners", "category": "Fly Fishing", "products": ["Orvis Clearwater Combo", "Redington Classic Trout", "Rio Gold Fly Line"]},
    {"title": "Ice Fishing Essentials: What to Buy Before the Season", "keyword": "ice fishing essentials gear list", "category": "Ice Fishing", "products": ["Clam Dave Genz Fish Trap", "13 Fishing Tickle Stick", "Frabill 371 Ice Combo", "Vexilar FL-8"]},
    {"title": "Saltwater vs Freshwater Reels: What's the Real Difference?", "keyword": "saltwater vs freshwater reels difference", "category": "Saltwater", "products": ["Penn Battle III", "Shimano Stradic SW", "Daiwa BG SW"]},
    {"title": "Top Trout Lures That Actually Work (Tested on the Water)", "keyword": "best trout lures tested", "category": "Lures", "products": ["Panther Martin Spinner", "Rapala Countdown", "Mepps Aglia", "PowerBait Trout Nuggets"]},
    {"title": "Waders Buying Guide: Breathable vs Neoprene in 2026", "keyword": "breathable vs neoprene waders guide", "category": "Apparel", "products": ["Simms G3 Guide", "Orvis Silver Sonic", "Hodgman Aesis Breathable"]},
    {"title": "7 Kayak Fishing Upgrades Worth Every Penny", "keyword": "kayak fishing upgrades accessories", "category": "Kayak", "products": ["YakAttack GearTrac", "Scotty Kayak Rod Holder", "Wilderness Systems Radar 115"]},
    {"title": "Polarized Fishing Sunglasses: Why They Matter and Which to Buy", "keyword": "polarized fishing sunglasses review", "category": "Accessories", "products": ["Costa Del Mar Fantail", "Oakley Flak 2.0", "Maui Jim Peahi"]},
    {"title": "Baitcasting for Beginners: The Honest Truth About Reels", "keyword": "baitcasting reels beginners honest review", "category": "Reels", "products": ["Abu Garcia Black Max", "Shimano SLX", "Lew's American Hero Speed Spool"]},

    # Camping & Outdoor
    {"title": "Best Camping Tents Under $200: Tried and Tested", "keyword": "best camping tents under 200", "category": "Camping", "products": ["REI Co-op Passage 2", "Coleman Sundome 4", "Kelty Acadia 4", "Marmot Tungsten 3P"]},
    {"title": "A Beginner's Guide to Backpacking Gear in 2026", "keyword": "backpacking gear beginners guide 2026", "category": "Camping", "products": ["Osprey Atmos AG 65", "Big Agnes Copper Spur HV UL2", "MSR PocketRocket 2", "Therm-a-Rest NeoAir XLite"]},
    {"title": "The Best Sleeping Bags for Cold Weather Camping", "keyword": "best sleeping bags cold weather camping", "category": "Camping", "products": ["Western Mountaineering Alpinlite", "Marmot Trestles 15", "REI Magma 15", "NEMO Disco 15"]},
    {"title": "Camp Kitchen Essentials: What You Really Need (And What You Don't)", "keyword": "camp kitchen essentials gear", "category": "Camping", "products": ["MSR PocketRocket Deluxe", "GSI Outdoors Pinnacle Camper", "Stanley Adventure Cook Set", "Jetboil Flash"]},
    {"title": "Best Headlamps for Camping and Hiking — 2026 Picks", "keyword": "best headlamps camping hiking 2026", "category": "Camping", "products": ["Black Diamond Spot 400", "Petzl Actik Core", "Fenix HM65R", "BioLite HeadLamp 330"]},
    {"title": "How We Tested 6 Portable Water Filters — Our Results", "keyword": "best portable water filters camping tested", "category": "Camping", "products": ["Sawyer Squeeze", "LifeStraw Personal", "Katadyn BeFree", "MSR TrailShot"]},
    {"title": "Camping Chairs for People with Bad Backs (Comfort Tested)", "keyword": "best camping chairs back support comfort", "category": "Camping", "products": ["Helinox Chair One", "ALPS Mountaineering King Kong", "Kijaro Dual Lock", "REI Co-op Flexlite Air"]},

    # Caza
    {"title": "Best Hunting Boots for Cold Weather: A Field Review", "keyword": "best hunting boots cold weather field review", "category": "Hunting", "products": ["Irish Setter Vaprtrek", "LaCrosse Alpha Agility", "Danner Pronghorn", "Muck Boot Arctic Pro"]},
    {"title": "Hunting Binoculars: What Magnification Do You Actually Need?", "keyword": "best hunting binoculars magnification guide", "category": "Hunting", "products": ["Vortex Diamondback HD 10x42", "Leupold BX-4 Pro Guide", "Nikon Monarch M5 10x42", "Bushnell Legend Ultra HD"]},
    {"title": "Tree Stand Safety: The Gear That Could Save Your Life", "keyword": "tree stand safety gear essential", "category": "Hunting", "products": ["Summit Viper SD", "XOP Vanish Evolution", "Hunter Safety System Ultra-Lite", "Muddy Safeguard Harness"]},
    {"title": "Best Game Cameras Under $100 — Hidden Gem Picks", "keyword": "best game cameras under 100 dollars", "category": "Hunting", "products": ["Browning Strike Force Pro", "Stealth Cam G42NG", "Bushnell Core S-1", "Moultrie A-40i"]},
    {"title": "Do You Actually Need a Rangefinder for Hunting? (Honest Answer)", "keyword": "rangefinders for hunters honest review", "category": "Hunting", "products": ["Vortex Ranger 1800", "Leupold RX-1400i TBR", "Bushnell Prime 1300", "SIG SAUER KILO3000BDX"]},

    # Supervivencia & EDC
    {"title": "Survival Knives: What Experts Actually Carry in the Field", "keyword": "best survival knives experts carry", "category": "Survival", "products": ["Morakniv Companion", "ESEE 6P", "Benchmade Bugout", "Ka-Bar Becker BK2"]},
    {"title": "Fire Starters That Work Even in Rain and Wind", "keyword": "best fire starters emergency rain wind", "category": "Survival", "products": ["Uberleben Zunden", "UST BlastMatch", "Light My Fire Swedish FireSteel", "Bayite Ferrocerium Rod"]},
    {"title": "The Best Multi-Tools for Every Outdoor Adventure", "keyword": "best multi tools outdoor adventure 2026", "category": "Survival", "products": ["Leatherman Wave Plus", "Victorinox SwissTool Spirit", "Gerber Center-Drive", "SOG PowerAccess Deluxe"]},

    # Senderismo
    {"title": "Hiking Boots vs Trail Runners: Which Should You Actually Buy?", "keyword": "hiking boots vs trail runners which to buy", "category": "Hiking", "products": ["Salomon X Ultra 4 GTX", "Brooks Cascadia 16", "Merrell Moab 3 GTX", "Hoka Speedgoat 5"]},
    {"title": "Trekking Poles for Bad Knees: What Actually Helps", "keyword": "best trekking poles bad knees pain", "category": "Hiking", "products": ["Black Diamond Trail Ergo Cork", "Leki Micro Vario Carbon", "REI Co-op Traverse", "Cascade Mountain Tech Carbon"]},
    {"title": "What's Inside a Pro Hiker's Daypack? (Full Gear List)", "keyword": "pro hiker daypack full gear list", "category": "Hiking", "products": ["Osprey Talon 22", "Gregory Zulu 35", "Deuter Speed Lite 21", "Arc'teryx Aerios 30"]},
]


# ── Claude API ─────────────────────────────────────────────────────────────────

def call_claude(prompt: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            payload = json.dumps({
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2500,
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
            text = data["content"][0]["text"]

            try:
                json.loads(text)
                return text
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if match:
                    json.loads(match.group())
                    return match.group()
                raise ValueError("JSON invalido")

        except Exception as e:
            log.warning(f"Intento {attempt+1}/{retries} fallido: {e}")
            if attempt < retries - 1:
                time.sleep(5)
    raise ValueError(f"Fallo despues de {retries} intentos")


def amazon_link(product: str, tag: str) -> str:
    q = urllib.parse.quote_plus(product)
    return f"https://www.amazon.com/s?k={q}&tag={tag}"


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


# ── Generador ─────────────────────────────────────────────────────────────────

def generate_article(topic: dict) -> dict:
    products_str = "\n".join(f"- {p}" for p in topic["products"])

    prompt = f"""You are an expert outdoor gear reviewer writing for TackleReviewer.com, a trusted US site covering fishing, hunting, camping and hiking. Write a comprehensive SEO-optimized article.

Title: {topic["title"]}
Target keyword: {topic["keyword"]}
Category: {topic["category"]}
Products to review:
{products_str}

IMPORTANT: Respond with ONLY a valid JSON object. No markdown, no code fences, no extra text before or after.

{{
  "intro": "2-3 paragraphs that naturally include the target keyword. Explain who this guide is for and what problem it solves.",
  "products": [
    {{
      "name": "Product Name",
      "rating": 4.5,
      "price_range": "$X - $Y",
      "verdict": "One sentence verdict.",
      "pros": ["pro 1", "pro 2", "pro 3"],
      "cons": ["con 1", "con 2"],
      "review": "2 paragraphs: specific specs, real-world performance, who it is best for."
    }}
  ],
  "buying_guide": "2 paragraphs on what to look for. Include technical details that show real expertise.",
  "faq": [
    {{"q": "Common question?", "a": "Detailed answer."}},
    {{"q": "Another question?", "a": "Detailed answer."}}
  ],
  "conclusion": "1 paragraph conclusion with a clear recommendation."
}}

Write for a US outdoor audience. Be specific and honest. Vary tone — not every article needs to sound identical."""

    log.info(f"Generating: {topic['title']}")
    raw = call_claude(prompt)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError("No se pudo parsear el JSON")


# ── HTML ───────────────────────────────────────────────────────────────────────

def render_html(topic: dict, content: dict, slug: str, date_display: str) -> str:
    products_html = ""
    for i, p in enumerate(content.get("products", []), 1):
        alink = amazon_link(p["name"], AMAZON_TAG)
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
    buying     = content.get("buying_guide", "").replace("\n", "<br>")
    intro      = content.get("intro", "").replace("\n", "<br>")
    conclusion = content.get("conclusion", "").replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="{topic['title']} — Expert reviews and buying guide updated {date_display[:4]}.">
<title>{topic['title']} | TackleReviewer</title>
<link rel="canonical" href="https://tacklereviewer.vercel.app/posts/{slug}.html">
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
.faq-item[open] summary::after{{content:"minus"}}
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
    <div class="logo">Tackle<span>Reviewer</span></div>
    <nav class="nav"><a href="/">Home</a><a href="/#fishing">Fishing</a><a href="/#camping">Camping</a><a href="/#hunting">Hunting</a></nav>
  </div>
</header>
<main class="container">
  <div class="article-category">{topic["category"]}</div>
  <h1>{topic["title"]}</h1>
  <div class="article-meta">
    <span>By TackleReviewer Staff</span><span>·</span>
    <span class="updated">Updated {date_display}</span><span>·</span>
    <span>{len(content.get("products", []))} products reviewed</span>
  </div>
  <div class="intro">{intro}</div>
  <div class="quick-nav">
    <h3>In This Review</h3>
    <ol>{quick_links}<li><a href="#buying-guide">Buying Guide</a></li><li><a href="#faq">FAQ</a></li></ol>
  </div>
  <div class="ad-slot">Advertisement</div>
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
  <p>TackleReviewer — Independent outdoor gear reviews</p>
  <p style="margin-top:6px">As an Amazon Associate we earn from qualifying purchases · <a href="/privacy.html">Privacy Policy</a></p>
</footer>
</body>
</html>"""


# ── Index & Sitemap ────────────────────────────────────────────────────────────

def rebuild_index(posts_meta: list):
    cards = "".join(
        f'<a class="post-card" href="posts/{p["slug"]}.html"><div class="post-cat">{p["category"]}</div><h2 class="post-title">{p["title"]}</h2><div class="post-meta">{p["date"]} · {p.get("product_count",3)} products reviewed</div></a>'
        for p in sorted(posts_meta, key=lambda x: x["date"], reverse=True)
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="TackleReviewer — Expert fishing, hunting and camping gear reviews. Honest picks for every budget.">
<title>TackleReviewer — Fishing, Hunting and Camping Gear Reviews 2026</title>
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
<header class="site-header"><div class="header-inner"><div class="logo">Tackle<span>Reviewer</span></div></div></header>
<section class="hero"><div class="hero-inner">
  <h1>Honest Outdoor Gear Reviews You Can Trust</h1>
  <p>Independent reviews of fishing, hunting, camping and hiking gear so you spend less time researching and more time outdoors.</p>
</div></section>
<main>
  <div class="section-label">Latest Reviews</div>
  <div class="posts-grid">{cards if cards else "<p style='color:var(--muted);padding:40px 0'>No articles yet.</p>"}</div>
</main>
<footer>
  <p>TackleReviewer — Independent outdoor gear reviews</p>
  <p style="margin-top:6px">As an Amazon Associate we earn from qualifying purchases · <a href="/privacy.html">Privacy Policy</a></p>
</footer>
</body></html>"""
    with open(REPO_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html)
    log.info("index.html rebuilt")


def rebuild_sitemap(posts_meta: list):
    base = "https://tacklereviewer.vercel.app"
    urls = [f"<url><loc>{base}/</loc></url>"] + [
        f"<url><loc>{base}/posts/{p['slug']}.html</loc><lastmod>{p['date']}</lastmod></url>"
        for p in posts_meta
    ]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"
    with open(REPO_DIR / "sitemap.xml", "w") as f:
        f.write(xml)
    log.info("sitemap.xml rebuilt")


# ── Git ────────────────────────────────────────────────────────────────────────

def git_push(message: str):
    for cmd in [
        ["git", "-C", str(REPO_DIR), "add", "-A"],
        ["git", "-C", str(REPO_DIR), "commit", "-m", message],
        ["git", "-C", str(REPO_DIR), "push"],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 and "nothing to commit" not in r.stdout + r.stderr:
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


def get_next_topic(published: list):
    published_titles = {p["title"] for p in published}
    return next((t for t in TOPICS if t["title"] not in published_titles), None)


def run_once(date_override: str = None) -> bool:
    posts_meta = load_posts_meta()
    topic = get_next_topic(posts_meta)
    if not topic:
        log.info("Todos los temas cubiertos.")
        return False

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

    posts_meta.append({
        "title":         topic["title"],
        "slug":          slug,
        "category":      topic["category"],
        "date":          date_iso,
        "keyword":       topic["keyword"],
        "product_count": len(content.get("products", [])),
    })
    save_posts_meta(posts_meta)
    rebuild_index(posts_meta)
    rebuild_sitemap(posts_meta)
    git_push(f"content: {topic['title'][:60]}")
    remaining = sum(1 for t in TOPICS if t["title"] not in {p["title"] for p in posts_meta})
    log.info(f"Done. {remaining} topics remaining.")
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop",  action="store_true", help="1 articulo por dia indefinidamente")
    parser.add_argument("--batch", type=int, metavar="N", help="Genera N articulos con fechas escalonadas")
    parser.add_argument("--build", action="store_true", help="Solo regenera index y sitemap")
    args = parser.parse_args()

    if args.build:
        m = load_posts_meta()
        rebuild_index(m)
        rebuild_sitemap(m)
        git_push("build: rebuild index and sitemap")
        return

    if args.batch:
        log.info(f"Modo batch: {args.batch} articulos con fechas escalonadas")
        for i in range(args.batch):
            date = (datetime.now() - timedelta(days=args.batch - i - 1)).strftime("%Y-%m-%d")
            log.info(f"Articulo {i+1}/{args.batch} — fecha: {date}")
            if not run_once(date_override=date):
                break
            if i < args.batch - 1:
                pause = random.randint(20, 50)
                log.info(f"Pausa {pause}s...")
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