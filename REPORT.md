# 🛡️ Terra Shield — Project Audit & Deployment Report

**Project:** درع الأرض — Terra Shield (Defensethon v4.0)
**Stack:** FastAPI + Uvicorn + SQLite + WebSockets + Vanilla JS + Leaflet + Chart.js
**Audit date:** 2026-05-03

---

## 1. Executive Summary

The codebase is **functional, well-structured for a hackathon, and deployable today**. Architecture is sound (clean producer → fusion → broadcaster → dashboard pipeline), database queries are parameterized, and there are no hardcoded secrets. One real XSS vulnerability was found and **already fixed** in the latest `index.html` (`escHtml()` utility added).

For a hackathon demo or judges' presentation, **deploy as-is**. For real production with public traffic, follow the hardening checklist in §3.

---

## 2. Codebase Audit

### 2.1 File inventory

| File | Lines | Purpose |
|------|-------|---------|
| `backend/server.py` | 781 | FastAPI app, sensor fusion, AI report, SQLite, WebSocket |
| `dashboard/index.html` | 2,615 | Single-page UI (CSS + JS embedded), Leaflet map, charts |
| `backend/events.db` | — | Runtime SQLite (auto-created, do not commit) |

### 2.2 What works well ✅

- **Parameterized SQL everywhere.** No string concatenation in queries → no SQL injection vector.
- **No hardcoded secrets, API keys, or credentials.** Nothing to leak when pushed to a public repo.
- **Clean separation of concerns.** Sensor simulation, classification, persistence, and broadcasting are isolated functions.
- **Deterministic scenarios.** The 9 preset scenarios make the demo reproducible for judges.
- **Resilient WebSocket client.** After the latest fixes, the dashboard reconnects on disconnect, handles malformed messages, and gracefully degrades when the server is offline.
- **Map renders all 13 markers regardless of server state** thanks to the `RIYADH_LOCATIONS` fallback.

### 2.3 Issues found and resolved

| Severity | Issue | Status |
|----------|-------|--------|
| **High** | XSS via user-editable scenario content (`contenteditable` div fed back into `innerHTML` unescaped) | ✅ **Fixed** — added `escHtml()` and applied to `desc` + `actions` |
| Medium | WebSocket had no `onerror` handler; one bad message could break the whole socket | ✅ **Fixed** — added try/catch around message handling and `onerror` logger |
| Medium | Map markers didn't render reliably on first load (server sent `id`, frontend read `tile_id`) | ✅ **Fixed** — normalization layer added |
| Low | `fitBounds` only fit the markers the server sent, not all 13 known sites | ✅ **Fixed** — fits to full `RIYADH_LOCATIONS` |

### 2.4 Issues remaining (production hardening)

These don't block a demo deploy, but you should know about them:

- **CORS is wide open** (`allow_origins=["*"]`). Fine for a demo. For production, restrict to your actual domain: `allow_origins=["https://yourdomain.com"]`.
- **No Content-Security-Policy (CSP) header.** Three CDNs are loaded (`unpkg`, `jsdelivr`, `cartocdn`) without integrity hashes. A compromised CDN could execute arbitrary code in the dashboard.
- **No rate limiting on `/api/*` endpoints.** Anyone who finds the URL can spam `/api/scenario/preset/...` and disrupt the demo.
- **No authentication.** All endpoints are public. Fine for a hackathon, not for a real defense system.
- **`Math.random()` for synthetic metrics.** This is fine cosmetically (battery levels, ETAs), but never use it for anything cryptographic.
- **WebSocket auto-reconnects forever, every 2s, with no backoff cap.** A server that's permanently down means the browser keeps hammering it. Add exponential backoff if traffic matters.
- **`@app.on_event("startup")` is deprecated** in modern FastAPI. Migrate to lifespan handlers when convenient (it still works fine for now — just a warning).
- **SQLite is fine for a single instance**, but it can't span multiple workers. If you ever scale to multi-process, migrate to PostgreSQL.

---

## 3. AI Architecture Notes (for judges' Q&A)

The system uses **multi-sensor late fusion** with cosine similarity matching:

1. **7 sensors per tile** — vibration, explosive, toxic_gas, narcotic, alcohol, metal_em, acoustic.
2. **Each tile produces a 7-dim reading vector** every 1.5s.
3. **Cosine similarity is computed against 9 known threat signatures** (EXPLOSIVE, WEAPON, NARCOTIC, TOXIC_GAS, ALCOHOL, INTRUSION, VEHICLE, FOOTSTEP, NORMAL).
4. **Best-matching signature wins**; if cosine similarity ≥ 0.85 → THREAT; ≥ 0.50 → SUSPICIOUS; else NORMAL.
5. **Confidence score** is the cosine similarity itself. The dashboard separates two concepts: **Confidence** (this reading) vs **Model Accuracy / Certainty** (synthetic — represents claimed reliability of the model on this kind of input).
6. **Events persist to SQLite** for the analytics endpoint and the AI report endpoint.

**Strengths to highlight:**
- Late fusion is the industry-standard approach for heterogeneous sensors.
- Cosine similarity is interpretable, explainable, and cheap to compute — important for an embedded edge device.
- The threat signatures are vector-based, so adding a new threat type is just adding one row to `THREAT_SIGNATURES`.

**What the demo simulates vs what would be real:**
- Sensor readings are synthetic (`generate_reading()`).
- The cosine similarity engine itself is real and would work on actual sensor inputs.
- The `/api/ai_report` endpoint generates a rule-based narrative (not an LLM). For a stronger pitch, you could optionally swap in a small LLM later, but the rule-based version is faster, deterministic, and demos better.

---

## 4. Free Deployment Options (ranked for this project)

This project needs **persistent WebSocket connections + a Python ASGI runtime**. That rules out static hosts like GitHub Pages, Netlify, and Vercel for the *backend* (they only do serverless functions, which can't hold a WebSocket open).

### 🥇 Render — Recommended

- **Free tier:** 750 hours/month, 512 MB RAM, automatic HTTPS, custom domain support, native WebSocket support.
- **Catch:** Service spins down after 15 min of no traffic; first request after sleep takes ~30s. Fine for a judging demo if you wake it up before they look.
- **Why it wins for this project:** Single-service deploy (frontend + backend in one box), zero config beyond `requirements.txt`, free SSL, supports custom domain, and WebSockets work without tweaking.

### 🥈 Railway — Strong runner-up

- **Free trial:** $5/month credit (no permanent free tier as of 2026).
- **Why consider it:** Better DX than Render, no cold starts during the trial period, supports WebSockets natively. Use this if you're presenting and want zero risk of cold-start lag.
- **Catch:** When the $5 runs out, the project goes offline unless you upgrade.

### 🥉 Fly.io — For if you want global edge

- **Free allowance:** Generous for small apps.
- **Pros:** Always-on, deploys close to users, WebSockets work great.
- **Cons:** Steeper learning curve (`flyctl`, `fly.toml`), Docker-first.

### Don't use these (for the backend)

- ❌ **Vercel / Netlify / Cloudflare Pages** — serverless, no persistent processes → WebSockets won't work
- ❌ **GitHub Pages** — static only, no Python runtime
- ❌ **PythonAnywhere free tier** — no WebSocket support on free plan

### Hugging Face Spaces (special case)

- Free, supports FastAPI + WebSockets via Docker space.
- Good if you want to lean into the AI angle ("hosted on HF, the AI community platform").
- Public by default — judges can look around.

---

## 5. Step-by-Step Deployment to Render (recommended path)

### Prerequisites
- A GitHub account (free)
- A Render account (free, sign up with GitHub)

### Step 1: Prepare the repo

In the project root, you should now have:

```
TILE-SHIELD/
├── backend/
│   └── server.py
├── dashboard/
│   └── index.html
├── firmware/        (optional)
├── hardware/        (optional)
├── requirements.txt   ← I just created this for you
├── Procfile           ← I just created this for you
├── render.yaml        ← I just created this for you
└── .gitignore         ← I just created this for you
```

Move the four new files I generated into `Desktop/TILE-SHIELD/` (the project root, *not* into `backend/` or `dashboard/`).

### Step 2: Push to GitHub

Open Terminal in `Desktop/TILE-SHIELD/` and run:

```bash
git init
git add .
git commit -m "Initial commit — Terra Shield Defensethon v4.0"
gh repo create terra-shield --public --source=. --push
```

If you don't have the GitHub CLI (`gh`), do it manually: create an empty repo on github.com called `terra-shield`, then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/terra-shield.git
git branch -M main
git push -u origin main
```

### Step 3: Deploy on Render

1. Go to https://render.com and sign in with GitHub.
2. Click **New +** → **Web Service**.
3. Connect your `terra-shield` repo.
4. Render will auto-detect `render.yaml` and pre-fill everything. Just click **Create Web Service**.
5. Wait ~3 minutes for the build to finish.
6. You'll get a URL like `https://terra-shield.onrender.com` — share this with the judges.

### Step 4: Verify

Open the URL. You should see the dashboard with the 13 markers, LIVE indicator, and all the AI features working. WebSockets work over `wss://` automatically.

---

## 6. Free Domain Options

You have three realistic paths.

### 🥇 Path 1: GitHub Student Developer Pack (best — free for a year)

If you're a student (any university with a `.edu`-equivalent email or student ID), apply for the **GitHub Student Developer Pack**:

1. Go to https://education.github.com/pack
2. Verify your student status (school email is fastest, ID upload also works).
3. Once approved, claim **one of these free domains:**
   - **Namecheap** — free `.me` domain for 1 year (most popular)
   - **Name.com** — free domain (many TLDs to pick from)
   - **.tech** — free `.tech` domain for 1 year (great for a tech project)
   - **.live, .studio, .software, .app, .dev** — various partners

For Terra Shield I'd recommend `terra-shield.tech` or `terrashield.me`.

### 🥈 Path 2: Render's free subdomain (zero effort)

You automatically get `https://terra-shield.onrender.com`. It's free forever, has SSL, and looks fine for a hackathon demo. **This is what I'd use for the judging session.**

### 🥉 Path 3: Free TLDs from Freenom (.tk, .ml, .ga, .cf, .gq)

⚠️ **Warning:** Freenom registrations have been broken / suspended for new users since 2023. As of mid-2026 it is **not a reliable option**. Skip this.

### Connecting your custom domain to Render

Once you have a domain (say `terrashield.me`):

1. In Render dashboard → your service → **Settings** → **Custom Domains** → **Add Custom Domain**.
2. Enter `terrashield.me`.
3. Render shows you a DNS record to add (usually a `CNAME` pointing to `terra-shield.onrender.com`).
4. In Namecheap (or wherever you bought the domain) → DNS settings → add the CNAME record.
5. Wait 5–30 minutes for DNS to propagate. Render auto-provisions free SSL via Let's Encrypt.

---

## 7. My recommendation for the judging session

**Tonight / before the demo:**
1. Push the project to GitHub (public repo so judges can browse the code).
2. Deploy to Render using the free tier and the included `render.yaml`.
3. Use the free `*.onrender.com` URL — it's clean, has SSL, works.
4. **Wake the service up 5–10 minutes before the judges arrive** by visiting the URL once (otherwise the first request will lag 30s after the cold start).

**For a custom domain (if you have time):**
5. Apply to GitHub Student Pack and grab a free `.tech` or `.me` domain.
6. Connect it to Render via CNAME. Done.

---

## 8. Production hardening (post-hackathon, if you want to take this further)

If Terra Shield becomes a real product, do these in order:

1. **Add CSP and SRI headers** — pin the three CDN scripts with integrity hashes.
2. **Add authentication** — even basic API key auth on `/api/*` endpoints.
3. **Restrict CORS** to your actual domain.
4. **Rate limit** the API (e.g., `slowapi` package).
5. **Sanitize all server-broadcast strings** before injecting into the DOM (defense in depth — even though the server is trusted now, that may not always be the case).
6. **Migrate from SQLite to PostgreSQL** when you need multiple workers.
7. **Add structured logging** with rotation, ship to a log aggregator.
8. **Add monitoring** — Render has built-in metrics; for more, plug in Sentry (free tier).

None of this is needed for the hackathon. But it's good to have a credible answer when judges ask "what's next?"

---

## Files generated for you in this directory

- `index.html` — secured dashboard (192 KB, XSS fix included)
- `requirements.txt` — Python dependencies pinned to known-good versions
- `Procfile` — for Render / Railway / Heroku-style platforms
- `render.yaml` — one-click Render config
- `.gitignore` — keeps your repo clean (no `events.db` or `__pycache__`)
- `REPORT.md` — this file

🇸🇦 بالتوفيق في المركز الأول 🏆
