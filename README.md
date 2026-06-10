# Relay — Trade skills, not money.

A campus network where students teach what they know and learn what they want — paid in time credits, not cash.

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/KingAbda/Relay.git
cd Relay

# Install dependencies
pip install -r requirements.txt

# Set your secret key (generate one: python -c "import secrets; print(secrets.token_hex(32))")
export RELAY_SECRET_KEY="your-secret-key-here"

# Run the app
python app/main.py
```

Visit **http://localhost:8000** to see it live.

## 🧱 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask (Python) |
| ORM | SQLAlchemy |
| Database | SQLite (dev) / PostgreSQL (production) |
| Frontend | HTML/CSS with Chakra Petch + Sora fonts |
| Security | CSRFProtect, Bleach (XSS), Rate Limiting, Security Headers |
| Deployment | Render (see `render.yaml`) |

## 📋 Features

- ✅ **Time-based credit system** — 30 minutes of teaching = 1 credit
- ✅ **Skill marketplace** — Browse, request, and complete skill sessions
- ✅ **Rating & reviews** — Post-session feedback builds reputation
- ✅ **Referral program** — Both parties earn +1 credit
- ✅ **.edu email verification** — Students-only community
- ✅ **Pilot mode** — Launch with a single vertical to build density
- ✅ **Email verification** — Verify your .edu address
- ✅ **Security hardened** — CSP headers, CSRF protection, rate limiting, XSS prevention

## 🧪 Pilot Mode

Relay launches with a single vertical (default: **Fitness & Wellness**) to build campus density first. Set the `RELAY_PILOT_VERTICAL` env var to change the pilot category.

## 📖 Full Business Plan

See [RELAY_DOC.md](./RELAY_DOC.md) for the complete master document — market research, unit economics, competitive analysis, and growth strategy.

## 🗺️ Roadmap

- **Phase 1:** 🟢 Google Form + Airtable + Discord pilot (50 users)
- **Phase 2:** 🟢 Simple web platform with credit ledger, profiles, matching *(current)*
- **Phase 3:** 🔄 Revenue — memberships, badges, university sponsorships
- **Phase 4:** 🔄 Multi-campus expansion

## 🔒 Security

Relay takes security seriously:

- All POST/PUT/DELETE requests require CSRF tokens
- Input sanitization via Bleach (strip all HTML tags)
- Rate limiting on auth endpoints (10 signups/hour, 20 logins/hour)
- Security headers: HSTS, X-Content-Type-Options, X-Frame-Options, CSP
- Account lockout after repeated failed login attempts
- Password strength enforcement (8+ chars, upper, lower, number)
- Session cookies are HTTP-only with SameSite=Lax

## 📄 License

MIT — built by students, for students.

## 👤 Founder

**Abdurrahman Touray (Abda)** — NYU 2026, HEOP Scholar, First Gen Gambian American from the Bronx.
