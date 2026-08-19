# TU5G Network System — Quick Setup Guide

## Prerequisites
- Docker 24+ and Docker Compose v2
- Python 3.11+ (for local dev without Docker)
- Node.js 18+ (optional, for frontend tooling)
- A Gmail account (for OTP email delivery)
- Domain pointing to your server (for production TLS)

---

## Option A: Docker Compose (Recommended)

### 1. Clone the repo
```bash
git clone https://github.com/HOPEAIHUB/TU5G-Network-System.git
cd TU5G-Network-System/tu5g
```

### 2. Copy and configure environment
```bash
cp .env.example .env
```
Edit `.env` and set the following:
```ini
# Core
JWT_SECRET=your-super-secret-jwt-key
DATABASE_URL=postgresql+asyncpg://tu5g:tu5gpass@postgres:5432/tu5g
REDIS_URL=redis://redis:6379/0

# MinIO (S3-compatible storage)
MINIO_ROOT_USER=tu5gadmin
MINIO_ROOT_PASSWORD=your-minio-password
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=tu5gadmin
MINIO_SECRET_KEY=your-minio-password

# Email (Gmail SMTP for OTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu5g.online@gmail.com
SMTP_PASSWORD=your-app-password

# AI / LLM
OPENAI_API_KEY=your-openai-api-key

# TU5G Network
COUNTRY_CODE=+984
MCC=984
MNC=79
SIM_RANGE_START=799000000
SIM_RANGE_END=799999999
HMAIL_DOMAIN=tu5g.online

# CORS (production)
ALLOWED_ORIGINS=https://tu5g.online,https://www.tu5g.online
```

### 3. Build and launch
```bash
docker compose up --build -d
```

### 4. Verify services
```bash
# Frontend (HMTML)
open http://localhost:8080

# FastAPI docs
open http://localhost:8000/docs

# Check all containers
docker compose ps
```

### 5. Run database migrations
```bash
docker compose exec backend alembic upgrade head
```

---

## Option B: Local Development (No Docker)

### Backend
```bash
cd tu5g/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set environment variables from .env
export $(cat ../.env | xargs)

# Start PostgreSQL & Redis locally (or use cloud instances)
# Run migrations
alembic upgrade head

# Start the API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd tu5g/frontend
npm install  # optional: for linting/formatting
# Serve templates with any static server
npx serve templates --listen 8080
# Or use nginx
nginx -c nginx.conf
```

---

## Service Architecture

| Service | Port | Description |
|---------|------|-------------|
| Frontend (HMTML) | 8080 | HTML + Bootstrap 5 UI |
| Backend (FastAPI) | 8000 | REST API + WebSocket |
| PostgreSQL | 5432 | Primary database |
| Redis | 6379 | Cache + sessions |
| MinIO | 9000 | S3-compatible file storage |
| NGINX | 80/443 | Reverse proxy + TLS |

---

## TU5G Network Configuration

| Setting | Value |
|---------|-------|
| Country Code | +984 |
| MCC | 984 |
| MNC | 79 |
| SIM Range | +984799000000 — +984799999999 |
| E-SIM Plans | Free (3 months), Premium ($9.99), Ultra ($29.99), Business ($49.99) |
| Number Categories | Free ($0), Premium ($100), Vanity ($500) |
| HMAIL Domain | tu5g.online |
| VPA Suffix | @upspay |

---

## Base44 Backend Functions (Cloud)

The platform also runs backend functions on Base44:

| Function | Purpose |
|----------|---------|
| `tu5gOtpVerification` | OTP generation + email verification |
| `tu5gEsimProvisioning` | E-SIM number listing, provisioning, plans |
| `tu5gPaymentService` | Wallet, VPA, transfers, payments |
| `tu5gGovernance` | Governance program applications + admin approval |

Test locally:
```bash
# After Base44 SDK setup
curl -X POST https://api.base44.com/functions/tu5gOtpVerification \
  -H "Content-Type: application/json" \
  -d '{"action":"generate","identifier":"user@tu5g.online","otpType":"email"}'
```

---

## Production Deployment

### TLS / HTTPS
```bash
# Generate Let's Encrypt certificates
certbot certonly --standalone -d tu5g.online -d www.tu5g.online

# Update nginx/conf.d/ssl.conf with cert paths
# Restart nginx
docker compose restart frontend
```

### Security Checklist
- [ ] Set strong JWT_SECRET (32+ characters)
- [ ] Restrict CORS to your domain only
- [ ] Enable pgcrypto for column-level encryption
- [ ] Configure rate limiting (slowapi)
- [ ] Set up audit logging → Loki/SIEM
- [ ] Enable Prometheus metrics
- [ ] Configure firewall (UFW/iptables)
- [ ] Set up automated database backups

---

## AI Bots

The platform includes 5 AI bot endpoints:

| Bot | Endpoint | Role |
|-----|----------|------|
| Admin-Bot | `/ai/admin-bot` | Network administration assistant |
| Customer-Care-Bot | `/ai/customer-care-bot` | User support |
| Marketing-SEO-Bot | `/ai/marketing-seo-bot` | Growth & visibility |
| Hosting-Bot | `/ai/hosting-bot` | Hosting management |
| Email-Bot | `/ai/email-bot` | Email management |

Configure your OpenAI API key in `.env` to enable AI bot responses.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Port 8000 in use | `lsof -i :8000` and kill process, or change port in docker-compose |
| PostgreSQL won't start | Check `pgdata` volume permissions |
| MinIO connection refused | Ensure MINIO_ROOT_USER/PASS match in .env |
| Email OTP not sending | Verify Gmail app password, enable 2FA on Gmail |
| Alembic errors | `alembic revision --autogenerate -m "initial"` then upgrade |

---

## Support
- **Email:** support@tu5g.online
- **Gmail:** tu5g.online@gmail.com
- **Author:** Timothy Abraham (T-Driven)
- **Docs:** See `/docs/HMTML_LANGUAGE_SYSTEM.md` and `/docs/THIMOTHISM_DOCTRINE.md`

---

*TU5G Network System — TUGS ACTIVATED — Clean World Project — CGT*
