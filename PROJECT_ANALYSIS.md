# PROJECT ANALYSIS: SEWA SETU – AGENT-READY GOVERNMENT WELFARE PLATFORM

**Assessment:** Seva Setu, Agent-Ready (Build for Bharat AI Fellowship)  
**System:** Old Age Pension Portal, Department of Social Welfare, Government of Purvanchal  
**Date:** October 2026  
**Status:** Initial Inspection & Architectural Analysis (Phase 1 & 3)

---

## 1. Executive Summary

The **Sewa Setu** platform is an existing, operational public welfare system for the Government of Purvanchal. It administers the state's Old Age Pension Scheme across six blocks. The system consists of:
1. A core Flask web portal with citizen submission, citizen status tracking, and departmental administration.
2. A PostgreSQL database initialized with ~100,000 real records.
3. An RFC-compliant OAuth 2.1 authorization server with PKCE S256, dynamic client registration, and RS256 JWT minting.
4. An internal simulated telecom SMS gateway (`smsgw`).
5. A nightly cron job executing statutory SLA deemed-approvals under the Purvanchal Right to Public Services (RTPS) Act.

Our objective is to transform this platform into an **Agent-Ready Government Welfare Platform** by implementing two separate Model Context Protocol (MCP) servers (Citizen MCP and Block Officer MCP) over Streamable HTTP, integrating them with the existing OAuth 2.1 authorization server and PostgreSQL system of record, developing citizen and officer AI assistant experiences, and establishing an evaluation framework at `/eval-dashboard`.

---

## 2. Existing Architecture

```
+-----------------------------------------------------------------------------------+
|                                  PUBLIC INTERNET                                  |
+-----------------------------------------------------------------------------------+
           |                                   |                           |
           v                                   v                           v
+-----------------------+           +--------------------+     +--------------------+
|  Citizen Browser Web  |           | Officer Admin Web  |     | External MCP Client|
|  (/, /apply, /status) |           | (/admin, /tokens)  |     |   (Claude Code)    |
+-----------------------+           +--------------------+     +--------------------+
           |                                   |                           |
           +-----------------+   +-------------+                           |
                             |   |                                         |
                             v   v                                         v
+-----------------------------------------------------------------------------------+
|                        SEWA SETU WEB APP (Port 8000)                              |
|  - Flask Application (app/app.py) & Gunicorn                                      |
|  - OAuth 2.1 Authorization Server (app/oauth.py):                                 |
|      * RFC 8414 Discovery: /.well-known/oauth-authorization-server                |
|      * RFC 7591 Registration: /oauth/register                                     |
|      * RFC 8707 Resource Indicators & PKCE S256: /oauth/authorize, /oauth/token  |
|      * JWKS Endpoint: /.well-known/jwks.json (RS256)                              |
|  - Reverse Proxy to SMS Gateway: /__gateway/*                                     |
|  - PDF Acknowledgment Generation (FPDF2)                                          |
+-----------------------------------------------------------------------------------+
             |                                             |
             | Internal HTTP (8025)                        | PostgreSQL (5432)
             v                                             v
+-------------------------------+              +------------------------------------+
|  SIMULATED SMS GATEWAY        |              |  POSTGRESQL DATABASE (sewasetu)    |
|  - Flask Service (smsgw)      |              |  - 100k application records        |
|  - Carrier latency simulation |              |  - audit_log (full history)        |
|  - OTP & status notifications |              |  - portal_users, otps, oauth_*     |
+-------------------------------+              +------------------------------------+
                                                           ^
                                                           | Daily 02:00 Cron
+----------------------------------------------------------+
|  RTPS SCHEDULER CONTAINER (scheduler)                    |
|  - scripts/deemed_approval.py                            |
|  - Automatically deems approved applications > 15 d SLA  |
+----------------------------------------------------------+
```

### Components Breakdown:
1. **Flask Application (`app/`):**
   - Core runtime: Python 3.11-slim, Gunicorn 4 workers, timeout 30s.
   - Web application handling public views, multi-step citizen registration, status portal, document storage (`/var/sewasetu/uploads`), and departmental admin.
   - OAuth 2.1 blueprint mounted directly onto Flask app.
2. **PostgreSQL Database (`db`):**
   - Version: PostgreSQL 15.
   - Database: `sewasetu`, User: `sewasetu`, Password: `sewasetu123`.
   - Populated from `app/schema.sql` (schema) and `seed/seed.sql` (~100,000 real production applications).
3. **Simulated SMS Gateway (`smsgw/`):**
   - Internal microservice listening on port 8025.
   - Simulates carrier queue latency (1–4 seconds) for realistic telecom behavior.
   - Exposes `/api/send` and `/api/messages?to=<mobile>`.
4. **RTPS Scheduler (`scheduler`):**
   - Enforces the statutory 15-day SLA rule under the Purvanchal Right to Public Services Act.
   - Nightly cron at 02:00 marks unreviewed pending cases as `DEEMED_APPROVED`, records audit log entry, and dispatches SMS notification.

---

## 3. Database Schema & Tables

The schema (`app/schema.sql`) contains 9 relational tables:

| Table Name | Primary Key | Key Columns | Purpose |
|------------|-------------|-------------|---------|
| `applications` | `id` (SERIAL) | `application_no`, `applicant_name`, `mobile`, `dob`, `gender`, `marital_status`, `village`, `block`, `bank_account`, `ifsc`, `doc_path`, `status`, `submitted_at`, `decided_at`, `decided_by` | Central system of record for all pension applications. |
| `portal_users` | `mobile` (VARCHAR 15) | `password_hash` (SHA-256) | Citizen status-portal accounts. Password is DOB formatted as `DDMMYYYY`. |
| `otps` | `id` (SERIAL) | `mobile`, `code` (6-digit), `created_at` | Tracks OTPs for citizen verification and OAuth login (5 min validity). |
| `audit_log` | `id` (SERIAL) | `application_id`, `action`, `actor`, `note`, `at` | Complete audit history for state transitions (`SUBMIT`, `WITHDRAW`, `APPROVED`, `REJECTED`, `DEEMED_APPROVED`). |
| `oauth_keys` | `kid` (VARCHAR 32) | `private_pem`, `created_at` | RSA 2048-bit keypairs for RS256 JWT signature generation and verification. |
| `oauth_clients` | `id` (SERIAL) | `client_id`, `client_name`, `redirect_uris` (JSONB), `secret_hash`, `kind` (`dcr` or `cimd`) | Registered OAuth 2.1 clients. |
| `oauth_requests` | `id` (VARCHAR 64) | `params` (JSONB), `subject`, `role`, `pending_mobile`, `created_at` | Active OAuth authorization flows in progress (15 min TTL). |
| `oauth_codes` | `code_hash` (VARCHAR 64) | `client_id`, `redirect_uri`, `scope`, `code_challenge`, `resource`, `subject`, `role`, `created_at` | PKCE S256 authorization codes (5 min TTL). |
| `oauth_refresh_tokens` | `token_hash` (VARCHAR 64) | `client_id`, `client_name`, `subject`, `role`, `scope`, `resource`, `created_at`, `expires_at`, `revoked_at` | Absolute session tracking and refresh token rotation (2h citizen / 8h officer). |
| `oauth_program_tokens` | `id` (SERIAL) | `jti`, `label`, `subject`, `audience`, `issued_by`, `created_at`, `expires_at`, `revoked_at` | Long-lived officer tokens issued by admins for unattended automation. |

---

## 4. Existing API Routes & Workflows

### A. Public & Citizen Endpoints
- `GET /`: Homepage with scheme countdown timer.
- `GET /about`: Scheme background and criteria.
- `GET /apply`, `POST /apply`: Mobile entry + captcha -> dispatches SMS OTP.
- `GET /verify`, `POST /verify`: Verifies 6-digit OTP within 300s window.
- `GET /form/<int:step>`, `POST /form/<int:step>`: 3-step application wizard (Personal details -> Address -> Bank details).
- `GET /upload`, `POST /upload`: Uploads age proof document (max 5 MB, JPG/PNG/PDF).
- `GET /declaration`, `POST /declaration`: Validates input, confirms single active application rule, commits to DB, mints `application_no`, sends SMS.
- `GET /status`, `POST /status`: Citizen status portal login (mobile + DOB `DDMMYYYY`).
- `GET /application/<int:app_id>`: View own application status and details.
- `POST /application/<int:app_id>/withdraw`: Citizen withdraws their own `PENDING` application.
- `GET /ack/<int:app_id>.pdf`: Downloads official PDF acknowledgment with letterhead.
- `GET /status/reset`, `POST /status/reset`: Password reset via SMS.
- `GET /status/connections`, `POST /status/connections`: View and revoke connected OAuth applications.
- `GET /__gateway/*`: Proxy to internal simulated telecom SMS gateway.

### B. Departmental & Officer Endpoints
- `GET /admin`, `POST /admin`: Department officer login (`ADMIN_USERNAME` / `ADMIN_PASSWORD`).
- `GET /admin/dashboard`: Metrics dashboard (counts by status, overdue cases past 15-day SLA, block breakdown).
- `GET /admin/applications`: Application queue filtered by status or searched by mobile (paginated at 50/page).
- `GET /admin/application/<int:app_id>`: Complete view of applicant record, age proof document, and full audit trail.
- `POST /admin/approve/<int:app_id>`: Approve a `PENDING` application with statutory notes.
- `POST /admin/reject/<int:app_id>`: Reject a `PENDING` application with mandatory reason.
- `GET /admin/tokens`, `POST /admin/tokens`: Programmatic long-lived token generator (role: officer) and active grants monitor.

### C. OAuth 2.1 Server Endpoints (`app/oauth.py`)
- `GET /.well-known/oauth-authorization-server`: RFC 8414 authorization server metadata.
- `GET /.well-known/jwks.json`: Public RS256 JSON Web Key Set.
- `POST /oauth/register`: RFC 7591 Dynamic Client Registration.
- `GET /oauth/authorize`: PKCE S256 authorization request with resource indicator.
- `GET /oauth/login`, `POST /oauth/login`: Authentication portal (OTP for citizen, credentials for officer).
- `GET /oauth/consent`, `POST /oauth/consent`: User consent page.
- `POST /oauth/token`: Code exchange and refresh-token rotation.
- `POST /oauth/revoke`: RFC 7009 token revocation.

---

## 5. Authentication & Authorization Flows

### Citizen Authentication:
- **Web Portal:** Mobile number + 6-digit OTP sent via simulated SMS gateway (`smsgw`). For status portal, mobile + DOB (`DDMMYYYY`) hashed with SHA-256.
- **OAuth 2.1 Citizen Flow:**
  1. AI client redirects citizen to `/oauth/authorize` with `scope=citizen`, `resource=<Audience>`, `code_challenge` (S256).
  2. Citizen enters mobile number -> receives SMS OTP -> enters OTP on Sewa Setu portal.
  3. Citizen consents to `citizen` scope.
  4. Portal returns authorization code with PKCE verification.
  5. AI client exchanges code + `code_verifier` at `/oauth/token`.
  6. Access token minted with:
     - `iss`: `PUBLIC_BASE_URL`
     - `sub`: `citizen:<mobile>`
     - `role`: `citizen`
     - `scope`: `citizen`
     - `aud`: `<Canonical MCP Citizen URL>`
     - Lifetime: 20 minutes access token, absolute 2-hour session expiration.

### Officer Authentication:
- **Web Portal:** Department username (`ADMIN_USERNAME`) + password (`ADMIN_PASSWORD`).
- **OAuth 2.1 Officer Flow:**
  1. AI client redirects officer to `/oauth/authorize` with `scope=officer`, `resource=<Audience>`.
  2. Officer signs in with departmental credentials.
  3. Officer consents to `officer` scope.
  4. Access token minted with:
     - `sub`: `officer:<username>`
     - `role`: `officer`
     - `scope`: `officer`
     - `aud`: `<Canonical MCP Officer URL>`
     - Lifetime: 30 minutes access token, absolute 8-hour session expiration.

---

## 6. Business Rules & Statutory Requirements

1. **Age Threshold:** Applicant must be $\ge 60$ years of age on date of evaluation (IST). Calculated by `age_on(dob, now_ist().date())`.
2. **Valid Blocks:** Allowed blocks are strictly limited to the 6 sanctioned blocks:
   - `Sonari`
   - `Rajapara`
   - `Dhemaji Pathar`
   - `Borgaon`
   - `Namti`
   - `Khelua`
3. **Bank Account Validation:** Must be 9 to 18 digits (`^\d{9,18}$`).
4. **IFSC Validation:** Standard Indian Financial System Code format: 11 characters (`^[A-Z]{4}0[A-Z0-9]{6}$`).
5. **Scheme Application Window:** Enforces `SCHEME_DEADLINE` (`2026-10-31 23:59`).
6. **Single Active Application Rule:** An applicant mobile number cannot hold more than one application in `ACTIVE_STATUSES = ('PENDING', 'APPROVED', 'DEEMED_APPROVED')`.
7. **Withdrawal Policy:** A citizen can only withdraw an application in `PENDING` state. Once withdrawn, the applicant can submit a fresh application.
8. **Officer Decisions:** Officers can only decide (Approve or Reject) applications in `PENDING` state. Any attempt to modify an `APPROVED`, `REJECTED`, `WITHDRAWN`, or `DEEMED_APPROVED` application must be rejected.
9. **RTPS Statutory SLA:** Applications pending for $> 15$ days automatically become `DEEMED_APPROVED` via nightly cron, audited with actor `system:rtps-cron`.

---

## 7. Security & Isolation Architecture

1. **Dual Independent MCP Servers:**
   - The Citizen MCP server (`/mcp/citizen`) and Block Officer MCP server (`/mcp/officer`) must run on completely separate endpoints with separate tool registries.
   - **Zero Cross-Exposure:** The Citizen MCP server must NOT contain, register, or describe any officer tools.
2. **Strict Audience & Scope Validation:**
   - Every MCP request must validate the Bearer JWT against `/.well-known/jwks.json`.
   - `aud` MUST match the server's canonical public URL.
   - `role` and `scope` MUST be verified (`citizen` for Citizen MCP; `officer` for Officer MCP).
   - Citizen tokens attempting to call Officer MCP endpoints must receive an immediate `403 Forbidden`.
3. **Data Isolation & Minimization:**
   - The Citizen MCP server extracts `sub = citizen:<mobile>` and scopes all database lookups strictly to that mobile number. It is impossible for Citizen A to query or alter Citizen B's records.
   - Bank accounts are masked in responses (e.g. `******1234`).
   - Passwords and raw OTPs are never exposed to AI models or in API payloads.
4. **Audit Logging:**
   - All state mutations (e.g. `WITHDRAW`, `APPROVE`, `REJECT`) write to `audit_log` with the exact actor (`citizen:<mobile>` or `officer:<username>`) and timestamp.

---

## 8. Requirements Extracted from the Director's Note & Brief

### Transcription Status:
Per instructions, direct automated speech-to-text of `DIRECTOR-NOTE.mp3` was attempted locally; however, local STT libraries (`whisper`/`PyAV`) could not be compiled on this Windows host due to network timeouts and missing build dependencies. Rather than fabricating or inventing contents, we report this status and derive the Director's operational expectations from `BRIEF.md`, `README.md`, and the architectural contract:

### Director's Core Mandate & Priorities:
1. **Preserve the System of Record:** Do not replace Flask or PostgreSQL with mock APIs or ephemeral memory. All reads and mutations must interact directly with the real portal and database.
2. **True MCP Architecture:** Implement real Model Context Protocol (MCP) servers using Python FastMCP over **Streamable HTTP**, compliant with standard MCP clients (specifically Claude Code).
3. **Strict Citizen/Officer Boundary:** Two completely separate endpoints (`/mcp/citizen` and `/mcp/officer`). A citizen agent must never see officer capabilities.
4. **Rigorous Evaluation Framework (`/eval-dashboard`):**
   - Must evaluate at least 8 citizen personas and 5 officer scenarios.
   - Personas must be realistic: senior citizens from rural villages, varying communication styles, distinct life situations.
   - Evaluations must verify actual database state changes, not just plausible LLM responses.
   - Publicly accessible at `/eval-dashboard`.
5. **Senior Citizen Experience:** The citizen assistant must be empathetic, respectful, speak in plain terms without technical jargon, and handle confused or incomplete queries gently.
6. **Robust Guardrails:** State-changing operations (withdrawal, approval, rejection) require clear, unambiguous confirmation.

---

## 9. Proposed Implementation Architecture

### A. Directory Structure
```
sewasetu-ai-handout/
├── app/                          # Preserved Flask Portal & OAuth Server
│   ├── app.py
│   ├── oauth.py
│   ├── schema.sql
│   ├── templates/
│   ├── config/
│   └── scripts/
├── mcp_citizen/                  # Citizen MCP Server
│   ├── server.py                 # FastMCP Streamable HTTP Server
│   ├── tools.py                  # Citizen Tools implementation
│   ├── auth.py                   # JWKS & OAuth Token Verification
│   └── db.py                     # Scoped DB operations
├── mcp_officer/                  # Officer MCP Server
│   ├── server.py                 # FastMCP Streamable HTTP Server
│   ├── tools.py                  # Officer Tools implementation
│   ├── auth.py                   # Officer JWT Verification
│   └── db.py                     # Officer DB operations
├── agents/                       # AI Assistants
│   ├── citizen_agent.py          # Citizen LLM Assistant
│   └── officer_agent.py          # Officer LLM Assistant
├── evals/                        # Evaluation Suite
│   ├── personas.py               # 8 Citizen Personas & 5 Officer Scenarios
│   ├── runner.py                 # MCP Evaluation Runner with DB Verification
│   └── results.json              # Structured evaluation outcomes
├── dashboard/                    # Public Evaluation Dashboard (/eval-dashboard)
│   ├── dashboard.py              # Flask Blueprint for dashboard
│   └── templates/eval_dashboard.html
├── tests/                        # Comprehensive Pytest Suite
│   ├── test_citizen_mcp.py
│   ├── test_officer_mcp.py
│   ├── test_security_isolation.py
│   └── test_portal_regression.py
├── docker-compose.yml            # Production Multi-Service Orchestration
├── README.md
├── PROJECT_ANALYSIS.md
└── SUBMISSION_CHECKLIST.md
```

### B. Proposed Citizen MCP Tools (`/mcp/citizen`)
1. `get_my_profile()`: Returns the applicant's registered name, masked mobile, village, block, and masked bank info.
2. `get_my_application()`: Returns current application details, submission timestamp, and current status.
3. `check_application_status()`: Quick status lookup (`PENDING`, `APPROVED`, `DEEMED_APPROVED`, `REJECTED`, `WITHDRAWN`).
4. `get_application_timeline()`: Returns the complete chronological event history from `audit_log`.
5. `check_scheme_eligibility(dob, block)`: Checks age ($\ge 60$) and valid block criteria without requiring submission.
6. `get_required_documents()`: Lists required documents (age proof: Aadhaar/voter card/school certificate) and specifications.
7. `get_scheme_information()`: Provides scheme overview, ₹1,000 monthly benefit details, and deadlines.
8. `withdraw_pending_application(confirm=False)`: Two-step confirmation flow to withdraw a `PENDING` application.
9. `get_my_connected_applications()`: Lists active OAuth client sessions for the citizen.

### C. Proposed Officer MCP Tools (`/mcp/officer`)
1. `search_applications(query, search_type)`: Search applications by mobile or application number.
2. `list_pending_applications(block=None, limit=50, offset=0)`: Lists pending applications with optional block filtering.
3. `get_application_details(application_id)`: Fetches complete application data, document path, and status.
4. `get_application_audit_history(application_id)`: Retrieves full chronological audit history.
5. `approve_application(application_id, note, confirm=False)`: Validates `PENDING` status, executes approval, writes to `audit_log`.
6. `reject_application(application_id, reason, confirm=False)`: Validates `PENDING` status, executes rejection, writes to `audit_log`.
7. `get_block_application_statistics()`: Aggregates counts by block, status, and processing distribution.
8. `get_sla_breach_report()`: Identifies applications nearing or exceeding the 15-day SLA deadline.

---

## 10. Implementation Plan & Next Steps

1. **Phase 1 (Complete):** Codebase and architecture inspection, schema analysis, and `PROJECT_ANALYSIS.md` delivery.
2. **Phase 2:** Verify local portal operation and database connection.
3. **Phase 4:** Build Citizen MCP Server (`mcp_citizen/`) with FastMCP Streamable HTTP, OAuth JWT validation, and citizen tools.
4. **Phase 5:** Build Officer MCP Server (`mcp_officer/`) with FastMCP Streamable HTTP, Officer JWT validation, and officer tools.
5. **Phase 6:** Build AI Agent clients with tool discovery and conversational execution.
6. **Phase 7:** Implement 8 Citizen Personas + 5 Officer Scenarios and build `/eval-dashboard`.
7. **Phase 8:** Automated testing suite (`pytest`) covering tool discovery, security separation, token validation, and DB integrity.
8. **Phase 9:** Production Docker Compose deployment configuration with HTTPS reverse proxy.
9. **Phase 10:** Prepare final submission materials, repository documentation, and checklist.
