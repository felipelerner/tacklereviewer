# TackleReviewer — Setup completo

## Estructura
```
tacklereviewer/
├── index.html              ← Homepage (generado por el bot)
├── privacy.html            ← Requerido por AdSense y Amazon
├── robots.txt
├── sitemap.xml             ← Generado por el bot
├── vercel.json
├── posts/                  ← Artículos generados (1 por día)
│   └── *.html
├── data/
│   └── posts.json          ← Metadata de artículos publicados
└── scripts/
    └── content_bot.py      ← El bot generador
```

---

## Paso 1 — Conseguir tu API key de Claude (necesitás gastar los $10 aquí)

1. Entrá a **console.anthropic.com**
2. Creá una cuenta
3. En "API Keys" → "Create Key"
4. Cargá créditos: $5 alcanza para ~100 artículos con claude-haiku, $10 para ~50 con sonnet
5. Copiá la key y pegala en `scripts/content_bot.py` línea donde dice `ANTHROPIC_KEY`

> Costo real por artículo con claude-sonnet: ~$0.05–0.10
> Con $10 tenés 100–200 artículos — suficiente para 6 meses de contenido

---

## Paso 2 — Amazon Associates

1. Entrá a **affiliate-program.amazon.com**
2. Registrate con tu cuenta de Amazon
3. Necesitás una web (usá `tacklereviewer.vercel.app` que ya tenés)
4. Una vez aprobado, tu tag es algo como `tunombre-20`
5. Pegalo en `scripts/content_bot.py` donde dice `AMAZON_TAG = "tacklerev-20"`

> Amazon aprueba en 1–3 días. Necesitás hacer al menos 3 ventas en los primeros 180 días para no ser suspendido.

---

## Paso 3 — Subir a GitHub y deployar en Vercel

```bash
cd tacklereviewer
git init
git add .
git commit -m "init: tacklereviewer"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/tacklereviewer.git
git push -u origin main
```

Luego:
1. vercel.com → "Add New Project" → seleccioná `tacklereviewer`
2. Deploy sin cambiar nada
3. Tu sitio queda en `tacklereviewer.vercel.app`

---

## Paso 4 — Correr el bot

```bash
# Generar el primer artículo ahora
python scripts/content_bot.py

# Modo automático: 1 artículo por día, indefinidamente
python scripts/content_bot.py --loop
```

El bot:
1. Toma el próximo tema de la lista `TOPICS`
2. Llama a Claude API para generar el artículo completo
3. Guarda el HTML en `posts/`
4. Actualiza `index.html` y `sitemap.xml`
5. Hace `git push` → Vercel despliega en ~15 segundos
6. Espera 24 horas y repite

---

## Paso 5 — Google AdSense (cuando tengas 10+ artículos)

1. adsense.google.com → "Get Started"
2. Registrá `tacklereviewer.vercel.app`
3. Esperá aprobación (1–4 semanas, necesitás contenido real)
4. Una vez aprobado, reemplazá los comentarios `<!-- AdSense -->` en los HTMLs

---

## Proyección de ingresos (realista)

| Mes | Artículos | Visitas/mes | Ingresos est. |
|-----|-----------|-------------|---------------|
| 1–2 | 30–60     | 0–100       | $0 (indexando)|
| 3   | 90        | 500–2.000   | $5–20         |
| 6   | 180       | 3.000–8.000 | $30–120       |
| 12  | 365       | 10.000+     | $100–500      |

**Fuentes de ingreso:**
- AdSense: ~$2–5 RPM (por cada 1000 visitas)
- Amazon Associates: 4% comisión en productos de $150–600 = $6–24 por venta

---

## Agregar más temas

En `content_bot.py`, editá la lista `TOPICS` y agregá objetos:

```python
{"title": "Best Bass Fishing Kayaks Under $1000", "keyword": "best bass fishing kayaks", "category": "Kayak", "products": ["Perception Pescador 10", "Old Town Topwater 106", "Sun Dolphin Boss"]},
```

---

## Si la compu se apaga

El sitio sigue online (está en Vercel). Los artículos dejan de generarse hasta que volvás a correr el bot. Podés correrlo manualmente cuando quieras con:

```bash
python scripts/content_bot.py   # genera el próximo artículo
```
