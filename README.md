# Sewa Setu — Agent-Ready Old Age Pension Platform

Department of Social Welfare, Government of Purvanchal.  
Extended with Model Context Protocol (MCP) Streamable HTTP endpoints, OAuth 2.1 integration, and autonomous welfare agent evaluation.

---

## 1. Quick Start

### Running with Docker Compose
```bash
ADMIN_PASSWORD=pick-something ASSESSOR_PASSWORD=assessor-key docker compose up --build -d
```

- **Citizen Web Portal:** `http://localhost:8000` (or `https://${PUBLIC_BASE_URL}`)
- **Evaluation Dashboard:** `http://localhost:8000/eval-dashboard`
- **Departmental Admin Login:** `http://localhost:8000/admin`
- **Public Citizen MCP Endpoint:** `http://localhost:8000/mcp/citizen` (or `http://localhost:8001/mcp`)
- **Public Block Officer MCP Endpoint:** `http://localhost:8000/mcp/officer` (or `http://localhost:8002/mcp`)
- **Simulated SMS Gateway Console:** `http://localhost:8000/__gateway/`
- **OAuth 2.1 Server Metadata:** `http://localhost:8000/.well-known/oauth-authorization-server`
- **Public JWKS Endpoint:** `http://localhost:8000/.well-known/jwks.json`

---

## 2. Platform Architecture

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
                         |  ~100,000 application records |
                         +-------------------------------+
                                         ^
                                         | Nightly 02:00
                         +-------------------------------+
                         |      scheduler (cron)         |
                         |   RTPS 15-day SLA Deemed      |
                         +-------------------------------+
```

---

## 3. Dual MCP Servers & Tool Registries

The platform runs two completely independent Model Context Protocol (MCP) servers over **Streamable HTTP** with RFC 8707 audience binding:

### A. Citizen MCP Server (`/mcp/citizen`)
Provides 9 citizen-authorized welfare tools. Contains **zero** officer tools. Identity is strictly derived from the verified RS256 token subject (`sub = citizen:<mobile>`), making cross-citizen data tampering impossible.
1. `get_my_profile()`: Returns name, masked mobile, village, block, and masked bank info (`******5527`).
2. `get_my_application()`: Returns application details, submission timestamp, and current status.
3. `check_application_status()`: Quick status lookup in clear, reassuring senior-friendly terms.
4. `get_application_timeline()`: Full chronological event history from `audit_log`.
5. `check_scheme_eligibility(dob, block)`: Pre-flight check for age ($\ge 60$) and 6 sanctioned rural blocks.
6. `get_required_documents()`: Official document checklist (Age proof, Bank Passbook, Residence).
7. `get_scheme_information()`: Scheme overview, ₹1,000 monthly benefit details, and RTPS statutory rights.
8. `withdraw_pending_application(confirm=False)`: Two-step confirmation flow to withdraw a pending application.
9. `get_my_connected_applications()`: Lists active authorized third-party OAuth applications.

### B. Block Officer MCP Server (`/mcp/officer`)
Provides 9 departmental administrative tools. Rejects citizen tokens with HTTP 401/403.
1. `search_applications(query, search_type, block, limit)`: Search across applications by application number, mobile, or name.
2. `get_application_details(application_id)`: Fetches applicant record, document path, and audit history.
3. `list_pending_applications(limit, offset)`: Lists pending applications ordered by submission date for SLA compliance.
4. `filter_applications(status, block, page)`: Filter applications by status and/or block with pagination.
5. `get_application_audit_history(application_id)`: Retrieves full chronological audit history.
6. `approve_application(application_id, note, confirm=False)`: Validates `PENDING` state, executes approval, and logs to `audit_log`.
7. `reject_application(application_id, reason, confirm=False)`: Validates `PENDING` state, executes rejection with mandatory statutory reason.
8. `get_block_application_statistics()`: Aggregates volume, status breakdown, block distribution, and overdue count.
9. `get_sla_breach_report(threshold_days)`: Identifies applications nearing or exceeding the statutory 15-day SLA.

---

## 4. Connecting with External MCP Clients (Claude Code)

### Citizen Connection:
```bash
claude mcp add sewasetu-citizen --transport http https://${PUBLIC_BASE_URL}/mcp/citizen
```

### Block Officer Connection:
```bash
claude mcp add sewasetu-officer --transport http https://${PUBLIC_BASE_URL}/mcp/officer
```

Or configure via `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "sewasetu-citizen": {
      "url": "https://sewasetu.example.in/mcp/citizen",
      "headers": {
        "Authorization": "Bearer <CITIZEN_ACCESS_TOKEN>"
      }
    },
    "sewasetu-officer": {
      "url": "https://sewasetu.example.in/mcp/officer",
      "headers": {
        "Authorization": "Bearer <OFFICER_ACCESS_TOKEN>"
      }
    }
  }
}
```

---

## 5. Dedicated Assessor Administrator Credentials

A dedicated administrator account has been provisioned for evaluation and assessment:
* **Departmental Login URL:** `https://${PUBLIC_BASE_URL}/admin`
* **Username:** `assessor_admin`
* **Password:** `5KHjK!KHuZi6sjmeTAV@1$6B` (or configured via `ASSESSOR_PASSWORD`)
* **Resetting Credentials:** Update `ASSESSOR_PASSWORD` in `.env` and run `docker compose up -d app`.

---

## 6. Evaluation Dashboard (`/eval-dashboard`)

The live evaluation framework is available at `/eval-dashboard` (and `/api/eval-results`).
* **10 Citizen Personas:** Evaluates senior citizens with varying communication styles, rural dialects, and life situations.
* **6 Officer Scenarios:** Evaluates SLA audits, authorized approvals/rejections, guardrails, and security penetration attempts.
* **PostgreSQL Verification:** Every evaluation checks both the assistant's response and the real PostgreSQL database state before and after execution.
* **Pass Rate:** 16 / 16 Passed (100.0%).

To execute evals locally:
```bash
python evals/runner.py
```

---

## 7. Automated Test Suite

Run the complete 24-test pytest suite:
```bash
pytest
```
Covers:
- `tests/test_citizen_mcp.py`: Citizen tool discovery, profile lookups, record isolation, eligibility, withdrawal confirmation.
- `tests/test_officer_mcp.py`: Officer tool discovery, queue review, SLA breach reports, audited approvals/rejections, invalid state transitions.
- `tests/test_portal_regression.py`: Portal routes, RFC 8414 OAuth metadata, public JWKS, `/eval-dashboard`, assessor admin login.
- `tests/test_security_isolation.py`: Zero cross-exposure, citizen token rejection on officer endpoints, expired JWT rejection, audience validation.

---

## 8. Directory Layout

```
sewasetu-assistant/
├── app/                          # Preserved Flask Portal & OAuth 2.1 Server
│   ├── app.py                   # Core Flask application, proxy routes, admin auth
│   ├── oauth.py                 # RFC 8414 & RFC 8707 OAuth 2.1 Authorization Server
│   ├── schema.sql               # Database schema
│   ├── templates/               # Portal and OAuth HTML templates
│   ├── config/                  # INI configuration files
│   └── scripts/                 # RTPS cron and assessor setup scripts
├── mcp_citizen/                  # FastMCP Citizen Server (Streamable HTTP, Port 8001)
│   ├── server.py                # Server initialization and tool registration
│   └── tools.py                 # 9 Citizen tools with subject isolation
├── mcp_officer/                  # FastMCP Officer Server (Streamable HTTP, Port 8002)
│   ├── server.py                # Server initialization and tool registration
│   └── tools.py                 # 9 Officer tools with audit logging
├── mcp_common/                   # Shared MCP Utilities
│   ├── auth.py                  # RS256 JWKS token verifiers & context resolution
│   └── db.py                    # Scoped PostgreSQL operations & fallback
├── agents/                       # Conversational AI Assistant Implementations
│   ├── citizen_agent.py         # Citizen assistant with empathetic prompt design
│   └── officer_agent.py         # Officer assistant with statutory workflows
├── evals/                        # Evaluation Suite & Public Dashboard
│   ├── personas.py              # 10 Citizen Personas & 6 Officer Scenarios
│   ├── runner.py                # FastMCP Evaluation Runner with DB verification
│   ├── dashboard.py             # Dashboard blueprint mounted on portal
│   ├── results.json             # Structured evaluation outcomes
│   └── templates/eval_dashboard.html # Modern dark-mode dashboard interface
├── tests/                        # Comprehensive Pytest Suite (24 tests)
├── deploy/                       # Production Nginx reverse proxy configuration
├── docker-compose.yml            # Production Multi-Service Orchestration
├── BRIEF.md                      # Original assessment logistics
├── README.md                     # Platform overview and instructions
├── PROJECT_ANALYSIS.md           # Deep architectural analysis
├── DESIGN_NOTE.md                # One-page design note (3 decisions + 1 future change)
├── SECURITY.md                   # Security architecture and threat model
├── EVALUATION_REPORT.md          # Comprehensive evaluation report
├── DEPLOYMENT.md                 # Production Linux host deployment guide
├── LOOM_SCRIPT.md                # 3-minute video demonstration script
└── SUBMISSION_CHECKLIST.md       # Final 14-field submission checklist
```
