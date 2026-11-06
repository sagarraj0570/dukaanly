# Dukaanly — HTTPS Deployment & Mobile Geolocation Reliability Guide

This document specifies the HTTPS deployment architecture, reverse-proxy configurations, trusted-proxy header forwarding, and mobile geolocation reliability mechanisms for Dukaanly.

---

## 1. Architectural Overview & The Secure Context Mandate

In modern web security standards (W3C Geolocation API Level 2 and WHATWG HTML), browser geolocation (`navigator.geolocation`) is **strictly restricted to Secure Contexts** (`window.isSecureContext === true`):

```mermaid
flowchart TD
    Client[Mobile Phone / Browser] --> Check{Is Secure Context?<br/>(HTTPS or localhost)}
    Check -- Yes (HTTPS) --> GeoAllowed[navigator.geolocation Available<br/>Prompts User for GPS Permission]
    Check -- No (Plain HTTP / LAN IP) --> GeoBlocked[navigator.geolocation Blocked / Undefined<br/>Triggers PERMISSION_DENIED / Browser Security Block]
    GeoAllowed --> GPSLocation[High-Accuracy GPS Fix (Lat/Lng)]
    GeoBlocked --> PresetFallback[Automatic Neighbourhood Preset Fallback<br/>Boring Road / Kankarbagh / Rajendra Nagar / Bailey Road]
```

### Key Security Principles:
1. **Desktop vs. Physical Mobile Testing**:
   - Browsers treat `http://localhost` and `http://127.0.0.1` as special-case secure origins on the host machine.
   - However, when connecting a physical smartphone over local Wi-Fi to a LAN IP (e.g. `http://192.168.1.50:5173`), `window.isSecureContext` is **`false`**. Plain HTTP on mobile blocks GPS access completely.
   - Therefore, a reverse proxy with TLS (automated Let's Encrypt or trusted self-signed certificates) is mandatory for physical mobile testing and field pilots.
2. **Non-Blocking Geolocation Fallback**:
   - Dukaanly's location store ([useLocationStore.ts](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/frontend/src/store/useLocationStore.ts)) detects non-secure contexts and permission errors gracefully.
   - Customers are never blocked: if GPS is unavailable, one-click neighbourhood presets for Central, South, East, and West Patna allow immediate discovery and ordering.

---

## 2. Reverse-Proxy Architectures

Dukaanly supports two deployment paradigms:

### Option A: Turnkey Self-Hosted Docker Compose (Caddy / Nginx)

For self-hosted Linux VPS (Hetzner, DigitalOcean, AWS EC2, or local staging VMs), Dukaanly provides a turnkey production Docker Compose stack ([docker-compose.prod.yml](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/docker-compose.prod.yml)):

```mermaid
flowchart LR
    subgraph Ingress[Public Ingress (Ports 80 / 443)]
        Caddy[Caddy Reverse Proxy<br/>Automated ACME TLS / ZeroSSL]
    end

    subgraph PrivateNet[Isolated Internal Network (dukaanly_private)]
        Frontend[Frontend Container<br/>Nginx SPA Server (Port 80)]
        API[FastAPI Backend (Port 8000)<br/>--proxy-headers --forwarded-allow-ips]
        Worker[Celery Worker]
        Beat[Celery Beat]
        Postgres[(PostgreSQL 16 + PostGIS 3.4<br/>NO PUBLIC PORT EXPOSURE)]
        Redis[(Redis 7 + Auth<br/>NO PUBLIC PORT EXPOSURE)]
    end

    Client[Browser / Mobile] -->|HTTPS :443| Caddy
    Caddy -->|Reverse Proxy /| Frontend
    Caddy -->|Reverse Proxy /api/* & WS| API
    API --> Postgres
    API --> Redis
    Worker --> Redis
    Beat --> Redis
```

#### Why Caddy for Automated TLS:
- **Zero-Touch Certificates**: When a valid FQDN is provided in `DOMAIN` (e.g. `DOMAIN=patna.dukaanly.com`) and `ACME_EMAIL` is set, Caddy handles ACME challenges (HTTP-01 / TLS-ALPN-01) with Let's Encrypt or ZeroSSL automatically and auto-renews certificates before expiration.
- **Local / Staging Fallback**: If `DOMAIN=localhost` or is left unset, Caddy generates an internal self-signed certificate (`tls internal`), avoiding failed public ACME challenges.
- **Zero Public Port Exposure for Data Tier**: In `docker-compose.prod.yml`, neither PostgreSQL (port 5432) nor Redis (port 6379) publishes ports to the host interface. Only Caddy publishes ports `80` and `443`.
- **Native WebSocket Upgrades**: Caddy handles HTTP/1.1 `Upgrade: websocket` and `Connection: Upgrade` headers automatically without manual map directives.

Configuration file: [deploy/caddy/Caddyfile](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/deploy/caddy/Caddyfile).

#### Alternative: Nginx Reverse Proxy
For organizations requiring Nginx, an equivalent production configuration with HTTP/2, WebSocket upgrade maps, security headers, and reverse proxy directives is provided in [deploy/nginx/nginx.conf](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/deploy/nginx/nginx.conf).

---

### Option B: Cloud PaaS (Render Blueprint)

Dukaanly's Render deployment ([render.yaml](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/render.yaml)) delegates TLS termination to Render's global Anycast edge:
- Frontend: Managed static site CDN (`https://dukaanly-frontend.onrender.com`).
- Backend: Containerized web service (`https://dukaanly-api.onrender.com`).
- TLS: Render edge terminates TLS 1.3, forwards `X-Forwarded-Proto: https` and `X-Forwarded-For` to Uvicorn.
- Data Tier: PostgreSQL and Redis reside on a private internal VPC with zero public ingress.

---

## 3. Trusted-Proxy & URL Configuration

### 1. Backend Uvicorn Ingress
FastAPI / Uvicorn runs with proxy headers enabled in both `start.sh` and `docker-compose.yml`:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
```
- `--proxy-headers`: Instructs Uvicorn to parse `X-Forwarded-Proto`, `X-Forwarded-For`, and `X-Forwarded-Port`. When an HTTPS client connects, `request.url.scheme` evaluates to `"https"`.
- `--forwarded-allow-ips`: Configures trusted reverse proxy CIDRs/IPs (defaults to `*` behind internal Docker bridge networks; can be restricted to specific subnet ranges like `"127.0.0.1,10.0.0.0/8,172.16.0.0/12"`).

### 2. Client IP Resolution for Rate Limiting
In [rate_limit.py](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/backend/app/core/rate_limit.py), `get_client_ip(request)` safely extracts the originating client IP from the first element of `X-Forwarded-For`, with fallback to `X-Real-IP` and socket host.

### 3. Frontend WebSocket URL Normalization & Mixed-Content Guard
In [utils.ts](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/frontend/src/lib/utils.ts), `getDeliveryWsUrl`:
- Dynamically converts `https://` $\to$ `wss://` and `http://` $\to$ `ws://`.
- **Mixed Content Protection**: If the client is browsing over HTTPS (`window.location.protocol === 'https:'`), any configured `ws://` URL is upgraded to `wss://`, preventing browsers from throwing `SecurityError: An insecure WebSocket connection may not be initiated from a page loaded over HTTPS`.

---

## 4. Mobile Geolocation & Telemetry Reliability

### 1. Customer Geolocation Flow
- Handled by `requestGpsLocation` in [useLocationStore.ts](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/frontend/src/store/useLocationStore.ts).
- If `window.isSecureContext === false`, immediately reports:
  `"Geolocation requires a secure HTTPS connection. Please access Dukaanly via HTTPS or select a neighbourhood preset below."`
- If permission is denied or GPS times out, provides non-blocking Patna neighbourhood presets:
  - Boring Road / Canal Road (Central Patna: `25.6144, 85.1158`)
  - Kankarbagh Main Road (South Patna: `25.5947, 85.1588`)
  - Rajendra Nagar Market (East Patna: `25.6022, 85.1633`)
  - Bailey Road / Raja Bazar (West Patna: `25.6083, 85.0892`)

### 2. Rider Location Broadcast Optimization
In [RiderDeliveryDetail.tsx](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/frontend/src/pages/RiderDeliveryDetail.tsx):
- Active only when delivery status is `out_for_delivery`.
- **Throttling & Battery Conservation**: Modern smartphones trigger `watchPosition` multiple times per second. To preserve rider battery life and prevent network flooding, updates are throttled to send at most once every 3 seconds unless the rider has moved $\ge 10$ meters.
- Updates are dispatched via `PATCH /api/v1/riders/me/location` and broadcast to subscribed customers via Redis pub/sub over WebSocket.

### 3. Live WebSocket Delivery Tracking & Reconnection
In [CustomerDeliveryTracker.tsx](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/frontend/src/components/CustomerDeliveryTracker.tsx):
- **Exponential Backoff**: If the connection drops (e.g. in an elevator or underpass), the client attempts reconnection with exponential backoff capped at 15 seconds (`Math.min(1000 * 1.5^n, 15000)`).
- **Mobile Sleep / Wake Recovery**: Listens to the `visibilitychange` and `online` browser events. When the customer unlocks their phone or network reconnects, an immediate reconnection is triggered.
- **Manual Reconnect**: An on-screen tactile "Reconnect" button allows manual reconnection when offline.

---

## 5. Environment Variables Reference

| Variable | Environment | Default | Description |
|---|---|---|---|
| `APP_ENV` | All | `development` | `development`, `staging`, or `production`. |
| `DOMAIN` | Production / Staging | `localhost` | FQDN for automated Let's Encrypt TLS (e.g. `patna.dukaanly.com`). |
| `ACME_EMAIL` | Production / Staging | *(empty)* | Contact email for Let's Encrypt certificate expiration notices. |
| `FORWARDED_ALLOW_IPS` | Production / Staging | `*` | Trusted proxy IP addresses or subnets passed to Uvicorn. |
| `TRUSTED_PROXIES` | Production / Staging | `127.0.0.1,10.0.0.0/8,...` | Internal proxy subnet CIDRs. |
| `ALLOWED_ORIGINS` | All | `http://localhost:5173,...` | Comma-separated list of allowed CORS origins (must include HTTPS domains). |
| `VITE_API_URL` | Frontend | `http://localhost:8000/api/v1` | Base REST API URL. |
| `VITE_WS_URL` | Frontend | *(empty / dynamic)* | Base WebSocket URL (automatically derived as `wss://` on HTTPS). |
| `REDIS_PASSWORD` | Production / Staging | *(empty in dev)* | Strong secret password for Redis authentication. |
| `JWT_SECRET_KEY` | Production | *(must be $\ge 32$ chars)* | Cryptographically random secret for HMAC-SHA256 JWT signing. |

---

## 6. Step-by-Step Deployment Runbook

### Prerequisites
1. **Server**: Linux VM / VPS (Ubuntu 22.04+ or Debian 12+) with Docker Engine 24+ and Docker Compose v2+.
2. **DNS**:
   - An `A` record pointing `patna.dukaanly.com` to the server's public IPv4 address.
   - Ports `80` and `443` open in cloud firewall / security groups.

### Step 1: Clone Repository & Configure Environment
```bash
git clone https://github.com/your-org/Dukaanly.git
cd Dukaanly

# Create production environment file
cp .env.example .env
nano .env
```
Ensure the following are set in `.env`:
```ini
APP_ENV=production
DEBUG=false
ALLOW_MOCK_PAYMENTS=false
DOMAIN=patna.dukaanly.com
ACME_EMAIL=admin@dukaanly.com
ALLOWED_ORIGINS=https://patna.dukaanly.com
FORWARDED_ALLOW_IPS=*
REDIS_PASSWORD=a_very_strong_random_redis_password_64_chars
JWT_SECRET_KEY=generate_with_openssl_rand_hex_32
```

### Step 2: Launch Production Services
```bash
# Build and launch all services with Caddy reverse proxy
docker compose -f docker-compose.prod.yml up -d --build

# Inspect container health
docker compose -f docker-compose.prod.yml ps
```

### Step 3: Verify Automated HTTPS & Ingress
```bash
# 1. Verify HTTP -> HTTPS redirect
curl -I http://patna.dukaanly.com
# Expected: HTTP/1.1 308 Permanent Redirect -> https://patna.dukaanly.com/

# 2. Verify TLS certificate and security headers
curl -I https://patna.dukaanly.com
# Expected: HTTP/2 200 OK
# Expected headers: strict-transport-security, permissions-policy: geolocation=(self)

# 3. Verify API Health Probe through reverse proxy
curl https://patna.dukaanly.com/api/v1/health/live
# Expected: {"status":"ok"}

curl https://patna.dukaanly.com/api/v1/health/ready
# Expected: {"status":"ready","database":true,"redis":true}
```

---

## 7. Testing & Quality Verification Checklist

### Automated Test Matrix (Verified in CI / Local Test Suite)
The following guarantees are verified by automated tests in [test_https_and_proxy_security.py](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/backend/tests/api/test_https_and_proxy_security.py), [utils.test.ts](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/frontend/src/lib/utils.test.ts), and [useLocationStore.test.ts](file:///c:/Users/ASUS/Documents/VIT/Dukaanly/frontend/src/store/useLocationStore.test.ts):

| Test | Subsystem | Automated Verification Command |
|---|---|---|
| Proxy Header Client IP Extraction | Backend Rate Limiter | `pytest backend/tests/api/test_https_and_proxy_security.py -k test_client_ip` |
| HTTPS CORS Preflight & Rejection | FastAPI / Starlette CORS | `pytest backend/tests/api/test_https_and_proxy_security.py -k test_cors` |
| Rider Geolocation Bounds Validation | Rider Location API | `pytest backend/tests/api/test_https_and_proxy_security.py -k test_rider_location` |
| Delivery Route & WS Authorization RBAC | Delivery Domain / WS | `pytest backend/tests/api/test_https_and_proxy_security.py -k test_delivery` |
| Insecure `ws://` $\to$ `wss://` Auto-Upgrade | Frontend WebSocket Client | `npm --prefix frontend test -- src/lib/utils.test.ts` |
| Non-Secure Context Detection (`isSecureContext`) | Frontend Location Store | `npm --prefix frontend test -- src/store/useLocationStore.test.ts` |

---

### Physical Mobile Device Testing Matrix (Manual Field Pilot Runbook)
Automated unit tests cannot simulate physical hardware GPS chips, OS battery management, or real-world cellular signal loss. The following **MUST** be verified on physical Android and iOS devices prior to commercial pilot launch:

| Check | Target Device | Procedure | Success Criteria |
|---|---|---|---|
| **Hardware GPS Fix** | Android Chrome / iOS Safari | Open `https://patna.dukaanly.com/customer` on real phone; tap "Current Location". | Browser prompts for GPS permission; upon approval, coordinates update with accuracy $\le 20\text{ m}$. |
| **Non-Secure Origin Diagnostic** | Android Chrome / iOS Safari | Open `http://<LAN_IP>:5173` on real phone over local Wi-Fi. | App shows clear diagnostic alert: `"Geolocation requires a secure HTTPS connection. Please access Dukaanly via HTTPS or select a neighbourhood preset below."` Presets remain usable. |
| **Rider GPS Movement Tracking** | Android Chrome (Rider) | Log in as rider; transition delivery to `out_for_delivery`; walk or drive 50 meters. | Telemetry indicator shows `"Live Location Sharing Active"`; backend receives throttled coordinates (interval $\ge 3\text{ s}$). |
| **Lock Screen / Background Tab Wakeup** | iOS Safari & Android Chrome | Customer opens tracking page; locks phone screen for 2 minutes; unlocks phone. | `visibilitychange` fires; WebSocket status transitions from `Offline` $\to$ `Live Connected` within 2 seconds without requiring page reload. |
| **Cellular $\leftrightarrow$ Wi-Fi Handover** | Physical Phone | Turn off Wi-Fi while tracking an active delivery so device switches to 4G/5G mobile data. | Connection briefly shows `Reconnecting...` and recovers to `Live Connected` with new IP; rate limiter does not lock out customer. |
| **Battery Life During Shift** | Rider Phone | Run continuous dispatch tracking for 2 hours during deliveries. | Battery drain remains within acceptable thresholds ($\le 12\%\text{ per hour}$) due to coordinate throttling. |
