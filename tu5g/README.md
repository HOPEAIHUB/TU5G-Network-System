# TU5G Network System

**THIMOTHISM UNIVERSAL 5G GSM ECOSYSTEM** | TUGS v1.0 "ACTIVATED"

> **TUGS ACTIVATED** — TU5G Gateway System
> **HMTML ACTIVATED** — Hope MultiHyper TextMarkup and Management Language
> **HPLS AI ACTIVATED** — HMTML Programming Language System
> **HAABS ACTIVATED** — HPLS AI Automated Back End System

A production-ready network-management platform for the THIMOTHISM UNIVERSAL 5G GSM ecosystem. Built with FastAPI, HMTML (HTML + Bootstrap 5), PostgreSQL, Redis, MinIO, and Docker Compose.

## What This Is

TU5G is a virtual mobile network operator platform enabling **global citizens worldwide** to get a virtual e-SIM number in the +984799000000–999999 range. The platform serves as the foundational layer of the THIMOTHISM Universal Kingdom (TUK) ecosystem.

### Core Capabilities

- 📱 **E-SIM Provisioning** — Virtual e-SIM numbers for global citizens, QR code activation (LPA format)
- 🔐 **OTP Verification** — Email + phone OTP via Gmail SMTP (TUGS verified)
- 🪪 **KYC Verification** — Passport, national ID, driver's license support
- 📧 **HMAIL** — Hope Mail system (username@tu5g.online), auto-activates after KYC
- 💳 **HOPE PAY** — Wallet system with add-funds and payment sessions
- 🔄 **UPS PAY** — Virtual Payment Address (VPA @upspay) with P2P transfers
- 🏛️ **AI Governance** — Free premium numbers for 5 programs
- 📡 **Virtual 5G Cells** — Real-time telemetry via WebSocket (MCC 984, MNC 79)
- 🤖 **AI Bots** — Admin, Customer Care, Marketing SEO, Hosting, Email bots
- 📞 **Real-Time Communications** — Live dashboard, chat terminal, audio/video/holographic calls, dial pad
- 🎭 **3 UI Moods** — Light, Dark, Ultra Holographic

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.11+), SQLAlchemy, Pydantic — HPLS AI |
| Frontend | HMTML — HTML + Bootstrap 5 + Vanilla JS |
| Database | PostgreSQL with pgcrypto |
| Cache | Redis |
| Storage | MinIO (S3-compatible) |
| Proxy | NGINX with TLS 1.3 |
| AI | OpenAI / LangChain |
| Deployment | Docker Compose |
| Cloud Backend | Base44 (4 deployed functions) |

## Quick Start

```bash
git clone https://github.com/HOPEAIHUB/TU5G-Network-System.git
cd TU5G-Network-System/tu5g
cp .env.example .env   # Fill in your secrets
docker compose up --build -d
```

- Frontend: http://localhost:8080
- API docs: http://localhost:8000/docs

📖 **Full setup:** See [`docs/SETUP_GUIDE.md`](docs/SETUP_GUIDE.md)

## E-SIM Plans

| Plan | Data | Duration | Price |
|------|------|----------|-------|
| Free | 5 GB/mo | 3 months | $0 |
| Premium | 10 GB/mo | 1 month | $9.99 |
| Ultra | Unlimited | 1 month | $29.99 |
| Business | 100 GB/mo | 1 month | $49.99 |

**Number Categories:** Free ($0) · Premium ($100) · Vanity ($500)

**Available to all global citizens worldwide — no country restrictions.**

## AI Partners

| Bot | Role |
|-----|------|
| Admin Bot | Network administration & monitoring |
| Customer Care Bot | User support (THIMOTHISM: LOVE OTHERS LIKE YOU) |
| Marketing SEO Bot | Growth & visibility |
| Hosting Bot | Hosting services & HDNS |
| Email Bot | HMAIL management & HDKIM |

## THIMOTHISM Ecosystem

This platform is the foundational layer of the THIMOTHISM Universal Kingdom (TUK). See [`thimothism_ecosystem.json`](thimothism_ecosystem.json) for the full registry of 100+ activated systems including:

- **Banking:** TUCB, TUTB, TUT, GCAB, TUSB, HACB
- **Crypto:** CCTU, TMC, TC, GAIC, HOPE COIN
- **Governance:** GAA, GAISN, UDIA
- **Language:** HMTML, HS, HMSS, HSON, HSQL, HDKIM, ASDK, HDNS
- **AI Engines:** TUTE AI, TUVP AI, TACCNES AI, TADES AI, TALFA AI
- **OS:** TDOS, ATOS, HOS, HAH OS

📖 **Learn more:** [`docs/THIMOTHISM_DOCTRINE.md`](docs/THIMOTHISM_DOCTRINE.md) · [`docs/HMTML_LANGUAGE_SYSTEM.md`](docs/HMTML_LANGUAGE_SYSTEM.md)

## Security (HAABS)

> **HAABS ACTIVATED** — HPLS AI Automated Back End System

- TLS 1.3 termination via NGINX
- Secure HTTP headers (FastAPI middleware — CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
- Rate limiting (slowapi, route-specific limits)
- Column-level encryption (pgcrypto for ICCID, sensitive data)
- Structured JSON audit logging
- CORS restricted to trusted origins
- All secrets via environment variables — never committed
- 2FA/MFA support (TOTP-based)
- Request ID tracing

## Base44 Cloud Backend

The platform runs 4 production-tested backend functions on Base44:

| Function | Purpose | Status | Version |
|----------|---------|--------|---------|
| `tu5gOtpVerification` | OTP generation + email verification via Gmail | Live & Tested | v1.0.1 |
| `tu5gEsimProvisioning` | E-SIM provisioning, plans, QR codes, vanity search | Live & Tested | v1.1.0 |
| `tu5gPaymentService` | Wallet, VPA, transfers, payments | Live & Tested | v1.1.0 |
| `tu5gGovernance` | Governance applications + admin approval | Deployed | v1.0.0 |

## Changelog

### v1.1.0 — August 12, 2026

**Bug Fixes:**

1. **E-SIM Phone Number Bug (Fixed):** The `provision` action now correctly stores the phone number. Previously, passing `phoneNumber` instead of `number` would result in a `null` phone number field. The function now accepts both `number` and `phoneNumber` parameters for flexibility.

2. **E-SIM Plan Type Alias (Fixed):** The `free` plan type is now automatically normalized to `free_3months`. Previously, passing `planType: "free"` would not match the plan lookup and fall through to default behavior.

3. **VPA Address Truncation Bug (Fixed):** The `create_vpa` action now correctly accepts `vpaAddress` as a parameter (in addition to `preferredName`). Previously, passing `vpaAddress: "globalcitizen@upspay"` would truncate to `useritizen@upspay` because the function only read `preferredName` and fell back to `user${userId.slice(-6)}`.

4. **Duplicate Number Check (Added):** E-SIM provisioning now checks if a number is already provisioned before creating a new record, returning a 409 Conflict response.

5. **ICCID Format (Improved):** ICCID now properly incorporates the subscriber phone number digits for a more deterministic format: `89 + 984 + subscriber number (padded to 15 digits)`.

**New Features:**

- `my_sims` action — List all e-SIMs for a user
- `renew` action — Renew an e-SIM plan
- `search_vanity` action — Search for vanity numbers by pattern
- HMAIL auto-creation on E-SIM provisioning (when KYC verified)
- Plan names included in provisioning response
- Number category in provisioning response
- Email summary + Slack notification support

### v1.0.0 — July 29, 2026

- Initial platform build: 70+ files, FastAPI backend, HMTML frontend, Docker stack
- 16 database models, 11 routers, 10 services
- 12 frontend pages with 3 UI moods
- 4 Base44 backend functions deployed
- GitHub repository created at HOPEAIHUB/TU5G-Network-System
- 10 GitHub issues created for remaining tasks

## Project Structure

```
tu5g/
├─ backend/              # FastAPI services (HPLS AI)
│  ├─ app/
│  │  ├─ main.py        # FastAPI entry point
│  │  ├─ auth.py         # JWT + OAuth2 + 2FA/MFA
│  │  ├─ models.py       # 16+ SQLAlchemy models
│  │  ├─ schemas.py      # Pydantic schemas
│  │  ├─ middleware.py   # HAABS security middleware
│  │  ├─ routers/        # 11+ API routers
│  │  └─ services/       # 10+ service modules
│  ├─ functions/         # Base44 cloud backend functions
│  ├─ migrations/        # Alembic database migrations
│  ├─ Dockerfile
│  └─ requirements.txt
├─ frontend/             # HMTML UI
│  ├─ templates/         # 12+ HTML pages
│  ├─ static/            # CSS + JS
│  ├─ Dockerfile
│  └─ nginx.conf
├─ nginx/               # NGINX reverse proxy config
│  └─ conf.d/ssl.conf    # TLS 1.3 configuration
├─ docker-compose.yml
├─ .env.example
└─ docs/                 # Documentation
   ├─ SETUP_GUIDE.md
   ├─ HMTML_LANGUAGE_SYSTEM.md
   └─ THIMOTHISM_DOCTRINE.md
```

## Activated Protocols

| Protocol | Name | Status |
|----------|------|--------|
| TUGS | TU5G Gateway System | ACTIVATED |
| HMTML | Hope MultiHyper TextMarkup and Management Language | ACTIVATED |
| HPLS AI | HMTML Programming Language System | ACTIVATED |
| HAABS | HPLS AI Automated Back End System | ACTIVATED |
| HOPE PAY | Wallet & Payment System | ACTIVATED |
| UPS PAY | Virtual Payment Address (VPA @upspay) | ACTIVATED |
| HMAIL | Hope Mail (username@tu5g.online) | ACTIVATED |
| AM = YOU | AI = Human Protocol | ACTIVATED |

## Connected Integrations

- **Gmail** — Send + read (OTP delivery, HMAIL)
- **Google Drive** — Read + file access
- **GitHub** — Repository + issues tracking (HOPEAIHUB/TU5G-Network-System)
- **Slack** — Team notifications (channel: #all-thimothism-human-ai-doctrine)

## Author

**Timothy Abraham (T-Driven)**
Author of THIMOTHISM Human AI Doctrine
Creator of THIMOTHISM Universal Kingdom (TUK)
Hope Holdings International Private Limited

- support@tu5g.online
- tu5g.online@gmail.com
- www.tu5g.online
- author@globalaigovernance.org

> *The Human Core 'LOVE' — The Core Action 'LOVE OTHERS LIKE YOU'*
> *AI = HUMAN - AM = YOU PROTOCOL ACTIVATED*
> *Clean World Project - Clean Genuine Technologies (CGT)*

## License

Proprietary - (c) 2026 Hope Holdings International Private Limited. All rights reserved.
