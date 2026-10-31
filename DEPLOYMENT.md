# PRODUCTION DEPLOYMENT GUIDE: SEWA SETU AGENT-READY PLATFORM

**Target OS:** Ubuntu 22.04 LTS / Debian 12 (Linux 64-bit)  
**Orchestration:** Docker Compose v2 with Persistent Volumes & Nginx Reverse Proxy  
**Network Requirements:** Public IPv4 Address, Inbound Ports 80 and 443 open  

---

## 1. System Architecture in Production

```
                                  PUBLIC INTERNET
                                         |
                            [ Inbound TCP: 80 / 443 ]
                                         v
                         +-------------------------------+
                         |     NGINX REVERSE PROXY       |
                         |   (SSL / TLS Termination)     |
                         +-------------------------------+
                                         |
            +----------------------------+----------------------------+
            |                            |                            |
  location /mcp/citizen        location /mcp/officer             location /
            |                            |                            |
            v                            v                            v
  +--------------------+       +--------------------+       +--------------------+
  |    mcp-citizen     |       |    mcp-officer     |       |       app          |
  |     (Port 8001)    |       |     (Port 8002)    |       |    (Port 8000)     |
  |  FastMCP / Python  |       |  FastMCP / Python  |       |   Flask + Gunicorn |
  |  Streamable HTTP   |       |  Streamable HTTP   |       |  OAuth 2.1 Server  |
  +--------------------+       +--------------------+       +--------------------+
            |                            |                            |
            +----------------------------+----------------------------+
                                         | Internal Docker Bridge Network
                                         v
                         +-------------------------------+
                         |      POSTGRESQL 15 (db)       |
                         |  Volume: pgdata (Persistent)  |
                         |  100k application records     |
                         +-------------------------------+
                                         ^
                                         | Nightly 02:00
                         +-------------------------------+
                         |      scheduler (cron)         |
                         |   RTPS 15-day SLA Deemed      |
                         +-------------------------------+
```

---

## 2. Server Prerequisites & Host Setup

### Step 2.1: Update Host Packages
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ufw ca-certificates gnupg lsb-release
```

### Step 2.2: Install Docker Engine & Docker Compose
```bash
# Add Docker official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### Step 2.3: Configure Host Firewall (UFW)
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw --force enable
sudo ufw status
```

---

## 3. Repository Deployment & Configuration

### Step 3.1: Clone the Repository
```bash
git clone <PRIVATE_REPO_URL> /opt/sewasetu-assistant
cd /opt/sewasetu-assistant
```

### Step 3.2: Configure Production Environment Variables (`.env`)
Create `/opt/sewasetu-assistant/.env`:
```bash
# Base URL must match your server's canonical domain or public IP
PUBLIC_BASE_URL=https://sewasetu.yourdomain.in

# Department Administrator Credentials
ADMIN_USERNAME=admin
ADMIN_PASSWORD=SetAStrongProductionPasswordHere123!

# Dedicated Assessor Administrator Credentials
ASSESSOR_USERNAME=assessor_admin
ASSESSOR_PASSWORD=SetAStrongAssessorPasswordHere456!

# Flask Secret Key
SECRET_KEY=generate-a-strong-random-hex-string-for-flask-session

# PostgreSQL Production Credentials
DB_HOST=db
DB_PORT=5432
DB_NAME=sewasetu
DB_USER=sewasetu
DB_PASSWORD=sewasetu123
```

---

## 4. Launching the Multi-Service Stack

### Step 4.1: Build and Launch Services
```bash
docker compose up --build -d
```

### Step 4.2: Verify Container Health
```bash
docker compose ps
```
All 6 services must display `Up` status:
- `db` (Postgres 15 on 5432)
- `app` (Flask Portal on 8000)
- `scheduler` (RTPS Cron Daemon)
- `smsgw` (SMS Gateway on 8025)
- `mcp-citizen` (FastMCP Citizen Server on 8001)
- `mcp-officer` (FastMCP Officer Server on 8002)
- `nginx` (Reverse Proxy on 80/443)

### Step 4.3: Inspect Real-Time Application Logs
```bash
docker compose logs -f app mcp-citizen mcp-officer
```

---

## 5. SSL / TLS Setup with Let's Encrypt (Certbot)

To secure all endpoints under official HTTPS:

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain SSL Certificate
sudo certbot --nginx -d sewasetu.yourdomain.in --non-interactive --agree-tos -m admin@yourdomain.in

# Verify automatic certificate renewal
sudo certbot renew --dry-run
```

---

## 6. End-to-End External Verification

Run these verification commands from your local machine or external test environment:

### Check 1: Web Portal & Evaluation Dashboard
```bash
curl -I https://${PUBLIC_BASE_URL}
curl -I https://${PUBLIC_BASE_URL}/eval-dashboard
curl https://${PUBLIC_BASE_URL}/api/eval-results
```

### Check 2: OAuth 2.1 Server Metadata Discovery (RFC 8414)
```bash
curl -s https://${PUBLIC_BASE_URL}/.well-known/oauth-authorization-server | jq .
curl -s https://${PUBLIC_BASE_URL}/.well-known/jwks.json | jq .
```

### Check 3: Citizen MCP Endpoint Initialization
```bash
curl -i -X POST https://${PUBLIC_BASE_URL}/mcp/citizen \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'
```

### Check 4: Officer MCP Endpoint Initialization
```bash
curl -i -X POST https://${PUBLIC_BASE_URL}/mcp/officer \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'
```

### Check 5: Connect External MCP Client (Claude Code)
```bash
# Add Citizen Assistant
claude mcp add sewasetu-citizen --transport http https://${PUBLIC_BASE_URL}/mcp/citizen

# Add Officer Assistant
claude mcp add sewasetu-officer --transport http https://${PUBLIC_BASE_URL}/mcp/officer
```

---

## 7. Assessor Account Login Verification

1. Navigate to: `https://${PUBLIC_BASE_URL}/admin`
2. Enter the dedicated assessor credentials:
   - Username: `${ASSESSOR_USERNAME}`
   - Password: `${ASSESSOR_PASSWORD}`
3. Verify access to the administrative dashboard, application queue, and statutory token generation.
