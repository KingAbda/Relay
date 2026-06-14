# Relay — Elevated Landing (Handoff)

Last updated: 2026-06-14

## What this is

A **side-by-side copy** of the Relay redesign, elevated with a premium motion layer.
It runs independently so you can compare:

| Version | Location | Port |
|---|---|---|
| Original | `/private/tmp/relay-origin-main` | http://127.0.0.1:8001 |
| Redesign (current) | `/Users/ramiel/Documents/projects/Relay` | http://127.0.0.1:8000 |
| **Elevated (this)** | `/Users/ramiel/Documents/projects/Relay-elevated` | **http://127.0.0.1:8002** |

This folder is **outside** the main git repo (intentionally — it's a working copy, not committed).

## Run it

Uses the main repo's virtualenv:

```bash
cd /Users/ramiel/Documents/projects/Relay-elevated
PORT=8002 RELAY_SECRET_KEY=dev-elevated-key \
  /Users/ramiel/Documents/projects/Relay/.venv/bin/python -m app.main
```

Flask runs with `use_reloader=False` but debug auto-reloads templates/static per
request, so HTML/CSS/JS edits show on refresh **without restarting** the server.

> **Cache note:** `elevate.css` / `elevate.js` keep the same filename, so browsers
> cache them. After editing, **hard-refresh (⌘⇧R)** once or you'll see stale assets.
> (This is what made the gauge animation look "static" during review.)

## Architecture

The backend (Flask) is unchanged from the redesign. All elevation is front-end,
**layered on top** of the existing `style.css` so the solid base is untouched:

- `app/static/style.css` — original redesign styles (warm "campus paper" system)
- `app/static/elevate.css` — **new** premium layer (loads after style.css; overrides win)
- `app/static/elevate.js` — **new** motion orchestrator
- `app/templates/base.html` — adds the motion stack + brand intro + `<noscript>` guard

### Motion stack (CDN, in base.html)
- **Lenis** 1.1.13 — smooth scroll, wired into GSAP's ticker
- **GSAP** 3.12.5 + **ScrollTrigger** — scroll choreography

Everything degrades gracefully: if a CDN fails → IntersectionObserver/rAF fallbacks;
if `prefers-reduced-motion` or `?static=1` → motion is skipped and final states render.

### `?static=1` lite mode
Append `?static=1` to any URL to disable intro + motion and render everything
settled. Used for deterministic screenshots and as a low-power/accessibility mode.

## What's built (landing page)

1. **Brand intro** — two-stage animated relay mark (baton handoff → smile → "Relay"
   wordmark → tagline), then a curtain lift. Ported from `~/Downloads/relay-logo-animation.zip`.
   Plays on **every** home load, **home page only**, click-to-skip, ~3.9s.
2. **Kinetic hero** — centered headline "Teach `Guitar` / Learn `Spanish`" where the
   two skill words swap through real paired trades. Currently uses the Framer
   **"Scale & Pop"** swap (scale + fade from center). A longest-word ghost reserves a
   stable slot so words stay centered + lined up.
3. **Skill marquee** — velocity-reactive (scroll speed nudges it).
4. **How credits work** — 3 step cards (Teach 30 min → Earn 1 credit → Learn 30 min)
   with an **animated looping arrow**: 1→2→3, then a wrap-around arc draws 3→1, loops.
5. **Pricing** — cleaned: flat-top cards, centered "Most useful" pill, blue check list.
6. **Campus field notes** — circular gauges; ring draws + number counts **0→70/85/75**
   when scrolled in (via IntersectionObserver — reliable).
7. **FAQ** — single-open accordion. **CTA** — gradient waitlist card.
8. Magnetic buttons, cursor glow, scroll-progress bar, nav scroll state, scroll reveals.

## Motion hooks (data attributes)

| Attribute | Effect |
|---|---|
| `data-reveal` (opt. delay) | fade/slide up on scroll |
| `data-reveal-stagger` | stagger children in |
| `data-split` | headline slide-up reveal |
| `data-count="70"` | gauge number counts 0→value (+ ring draw) |
| `data-swap` + `data-words="A,B,C"` | hero word swapper |
| `data-loop` / `data-loop-arrow` / `data-loop-wrap` | credit-loop arrow animation |
| `data-magnetic` (opt. `data-magnetic-strength`) | cursor-attracting element |
| `data-tilt` | mouse-tilt (currently unused after hero rework) |

## Pages cleaned

- **About** — rebuilt on the real design system (no emojis, no undefined tokens).
- **Privacy / Terms** — "Legal" eyebrow + serif titles, callouts de-emojified & re-styled.
- **Emojis removed site-wide** — about, privacy, terms, dashboard, onboarding, profile,
  request_session, error (emoji glyph → big serif error code). Kept functional
  typographic marks only: `✓ ★ ✕ ☰`.

## Known constraints / gotchas

- `/browse` **302-redirects to `/`** in the app code (both :8000 and :8002) — the browse
  template isn't a live route, though it still received the elevation hooks.
- ~~Several **app pages** use **old design tokens** (`--cta/--primary/--panel-line`)
  that are undefined → fallback/transparent colors.~~ **FIXED 2026-06-14:** added a
  legacy-token compatibility block in `elevate.css :root` that maps every pre-redesign
  token (`--primary --primary-bg --cta --amber --success --red --panel --panel-line
  --border-light --shadow-lg --radius-sm`) onto the real palette. All app pages now
  render with correct colors without touching the templates. A deeper *layout* polish
  pass (spacing/hierarchy) on these pages is still optional, but they're no longer broken.
- Headless screenshots **cannot** capture scroll-gated / interval motion reliably
  (Chrome's virtual clock pauses on the CDN). Verify motion live in a real browser.

## Recently fixed (2026-06-14)

- **Hero swap words clipped at the top** — the orange swap words use
  `-webkit-background-clip:text`, so the gradient only paints inside the element box;
  a `top` nudge had pushed that box down and sheared off tall serif caps (E/F). Fixed
  in `.kx-word` with a `padding-top:.16em` + `top:-.16em` pair that extends the paint-box
  above the caps while keeping the baseline aligned to Teach/Learn.
- **Skill marquee** (`style.css`) — (1) added `text-transform:capitalize` to the pills so
  every label is Title Case while preserving brand casing (GarageBand, LinkedIn, HTML/CSS,
  Figma, Python). (2) Spacing was uneven: pills were 18px apart within a group but 80px at
  the seam between the two repeated groups. Now driven by one `--mq-gap` var (track gap,
  group gap, and the keyframe offset `calc(-50% - var(--mq-gap)/2)` all reference it) →
  uniform spacing + seamless loop at any size. Mobile just overrides `--mq-gap:10px`.
- **Credit-loop stray dot under step 1** — the wrap-arc paths (`.lw-line/.lw-head`) sat at
  `opacity:1, dashoffset:1` with round line-caps, rendering a cap-dot at step 1's base.
  Now `.loop-wrap path{opacity:0}` by default; the timeline reveals them only during the
  wrap-draw phase.
- **Credit-loop sequential arrow glow** — added `.loop-arrow.is-glow svg` (warm layered
  `drop-shadow` halo) sequenced into the looping GSAP timeline in `initCreditLoop()`:
  arrow 1 draws → glows (~0.55s) → off → arrow 2 draws → glows → off → wrap → repeat.
- **Section order** (`index.html`) — moved **Campus field notes** (the 70/85/75 stat
  gauges, `.research-section`) to sit **before** Simple pricing (`.pricing-section`).
- **Hero word-swapper alignment** — swap words were `text-align:center` inside a slot
  sized to the longest word ("Budgeting"), so short words (Figma/Piano) floated in the
  middle with a big gap and *shifted/jiggled* as lengths changed on each swap. Now
  **left-aligned** (`text-align:left; transform-origin:left`) so words sit tight against
  Teach/Learn at a fixed anchor. Also tamed the pop (overshoot `back.out(1.7)`→`1.3`,
  outgoing scale `1.15`→`1.06`, start `0.7`→`0.86`) so glyphs stay legible and don't
  balloon, and added vertical headroom (`line-height 1.1`→`1.18`, `row-gap .12em`).
- **App-page tokens** — legacy tokens now aliased in `elevate.css :root` (see above).
- **Demo-login bug** — `_auto_seed_demo_data()` unpacked the demo tuples as
  `for email, name, pw` while the tuples are `(name, email, pw)`, so demo users were
  seeded with `email="Alex Rivera"` / `full_name="alex@nyu.edu"` (swapped) and **nobody
  could log in** with the documented creds. Fixed the loop order in `app/main.py` and
  repaired the 3 already-seeded rows in `app/instance/relay.db` (the live DB — note the
  app's instance path is `app/instance/`, not `./instance/`).
  Demo login confirmed working: **alex@nyu.edu / Pass1234** (also jordan@, sam@).

## Suggested next steps

1. Optional **layout** polish of the app pages (dashboard, profile, onboarding, auth,
   session flows) — colors are correct now; this is about spacing/hierarchy/serif
   headings to match the landing's editorial standard.
2. Tune motion pacing if desired: hero swap interval (2.5s), credit-loop (~4.5s).
3. If keeping long-term, fingerprint `elevate.css/js` filenames (cache-busting) so users
   don't need hard-refreshes.
4. Decide whether to merge the elevated work back into the main repo or keep it separate.

## File map (changed/new)

```
app/static/elevate.css      NEW  premium layer
app/static/elevate.js       NEW  motion orchestrator
app/templates/base.html     motion stack + brand intro + noscript guard
app/templates/index.html    hero swapper, credit loop, gauges, pricing hooks
app/templates/about.html    rebuilt
app/templates/privacy.html  cleaned
app/templates/terms.html    cleaned
app/templates/dashboard.html, profile.html, onboarding.html,
  request_session.html, error.html   emojis removed
```
