# SECURITY ARCHITECTURE & ISOLATION DOCUMENTATION

**System:** Sewa Setu Old Age Pension Portal & MCP Agent-Ready Platform  
**Authority:** Department of Social Welfare, Government of Purvanchal  
**Classification:** Government Digital Public Infrastructure (DPI)  

---

## 1. Executive Security Overview

The Sewa Setu Agent-Ready platform bridges public welfare services to autonomous AI agents through the **Model Context Protocol (MCP)**. Because the system manages sensitive personal identifiable information (PII), direct bank transfer (DBT) details, and statutory benefit distributions for senior citizens, security and isolation are primary engineering constraints.

The platform implements **Zero-Trust Architecture (ZTA)** across six defense-in-depth layers:
1. Dual Independent MCP Process & Endpoint Isolation
2. OAuth 2.1 RFC-Compliant Token Minting & RS256 Verification
3. RFC 8707 Resource Indicators & Audience Binding
4. Cryptographic Subject Binding & Insecure Direct Object Reference (IDOR) Elimination
5. Two-Step Guardrails & Immutable Statutory Audit Logging
6. PII Masking and Data Minimization

---

## 2. Threat Modeling & Mitigations

| Threat ID | Threat Vector | Potential Impact | Architectural Mitigation |
|-----------|---------------|------------------|--------------------------|
| **TH-01** | **Privilege Escalation via Unified Registry** | Citizen AI client invokes departmental approval/rejection tools. | Complete physical process bifurcation. Citizen MCP contains zero officer tools in its registry. |
| **TH-02** | **Cross-Citizen IDOR Querying** | Malicious actor supplies another citizen's mobile or ID in tool call. | Citizen tools accept zero identity parameters; identity is extracted exclusively from cryptographic JWT claims (`sub`). |
| **TH-03** | **Token Masquerading / Cross-Role Abuse** | Citizen access token presented to Officer MCP server. | Strict `role` and `scope` validation (`role=officer`, `scope=officer`) enforced at transport layer before tool execution. |
| **TH-04** | **Token Replay Across Services** | Token minted for Citizen MCP used against other government endpoints. | RFC 8707 Resource Indicators: tokens strictly enforce `aud` matching the canonical target URL. |
| **TH-05** | **Premature Mutation by LLM Hallucination** | LLM triggers application withdrawal or approval during exploratory dialogue. | Mandatory two-step confirmation pattern (`confirm=True`) requiring explicit user confirmation before state transition. |
| **TH-06** | **PII & Financial Data Leakage** | Full bank account numbers or credentials exposed to LLM context window. | Bank account masking (`******5527`), zero exposure of passwords or OTPs, minimal response payloads. |
| **TH-07** | **Timing Attacks on Credentials** | Attacker probes admin/assessor passwords via response latency variations. | Constant-time password comparison using Python `secrets.compare_digest`. |

---

## 3. Dual MCP Server Isolation Architecture

```
                    +---------------------------------------+
                    |             INTERNET                  |
                    +---------------------------------------+
                                        |
                         +--------------+--------------+
                         |                             |
                         v                             v
           +---------------------------+ +---------------------------+
           |    External Citizen       | |    External Officer       |
           |    Client (Claude Code)   | |    Client (Claude Code)   |
           +---------------------------+ +---------------------------+
                         |                             |
     Bearer JWT:         |         Bearer JWT:         |
     scope=citizen       |         scope=officer       |
     aud=/mcp/citizen    |         aud=/mcp/officer    |
                         v                             v
           +---------------------------+ +---------------------------+
           |    CITIZEN MCP SERVER     | |    OFFICER MCP SERVER     |
           |      (Port 8001)          | |      (Port 8002)          |
           |  - get_my_profile         | |  - search_applications    |
           |  - get_my_application     | |  - get_application_details|
           |  - check_app_status       | |  - list_pending_apps      |
           |  - get_app_timeline       | |  - filter_applications    |
           |  - check_eligibility      | |  - get_app_audit_history  |
           |  - get_required_docs      | |  - approve_application    |
           |  - get_scheme_info        | |  - reject_application     |
           |  - withdraw_pending_app   | |  - get_block_statistics   |
           |  - get_connected_apps     | |  - get_sla_breach_report  |
           +---------------------------+ +---------------------------+
                         |                             |
                         +--------------+--------------+
                                        | Scoped SQL
                                        v
                    +---------------------------------------+
                    |         POSTGRESQL DATABASE           |
                    |         System of Record              |
                    +---------------------------------------+
```

### Architectural Guarantees:
1. **Zero Shared Registries:** `mcp_citizen/server.py` and `mcp_officer/server.py` instantiate completely separate `FastMCP` objects with independent tool managers.
2. **Tool Discovery Boundary:** Running `tools/list` on `/mcp/citizen` returns exactly 9 citizen tools and 0 officer tools. A citizen agent cannot discover officer tools even if instructed to do so.
3. **Transport-Level Token Rejection:** If a citizen token is presented to `/mcp/officer`, the `OfficerTokenVerifier` rejects the request with HTTP 401/403 before any tool dispatch can occur.

---

## 4. OAuth 2.1 & Cryptographic Token Verification

All access tokens are RS256 JSON Web Tokens (JWT) minted by the Sewa Setu OAuth 2.1 server (`app/oauth.py`) and verified against public keys published at `/.well-known/jwks.json`.

### Token Claims Structure:
```json
{
  "iss": "https://sewasetu.example.in",
  "sub": "citizen:9217729489",
  "aud": "https://sewasetu.example.in/mcp/citizen",
  "scope": "citizen",
  "role": "citizen",
  "client_id": "claude-code-client",
  "iat": 1798700000,
  "exp": 1798701200,
  "jti": "jwt-unique-id"
}
```

### Verification Pipeline (`mcp_common/auth.py`):
1. **Header Inspection:** Reads `kid` from unverified JWT header.
2. **JWKS Key Lookup:** Retrieves matching RSA public key from cached JWKS (5-minute TTL).
3. **Signature Validation:** Verifies RS256 cryptographic signature using public key.
4. **Issuer Enforcement:** Verifies `iss == PUBLIC_BASE_URL`.
5. **Audience Enforcement:** Verifies `aud == canonical_mcp_audience`.
6. **Role & Scope Verification:**
   - Citizen MCP: `role == "citizen"` AND `"citizen" in scope`.
   - Officer MCP: `role == "officer"` AND `"officer" in scope`.
7. **Session Expiry:** Rejects expired tokens (`exp < now`). Enforces absolute session cap (2 hours for citizens, 8 hours for officers).

---

## 5. Data Isolation & Minimization

### Citizen Scoping:
All citizen queries derive the applicant's mobile directly from the token:
```python
sub = claims.get("sub", "")  # e.g. "citizen:9217729489"
mobile = sub.split(":", 1)[1]
cur.execute("SELECT ... FROM applications WHERE mobile = %s", (mobile,))
```
It is mathematically impossible for Citizen A to query or alter Citizen B's record because the SQL query filter is bound to the verified token identity, not user input.

### PII Masking:
Bank account numbers are masked before leaving the database layer:
```python
def mask_bank_account(account_number: str) -> str:
    if not account_number or len(account_number) < 4:
        return "******"
    return "******" + account_number[-4:]
```
This ensures financial data is never exposed in LLM context logs, prompt histories, or client-side transcripts.

---

## 6. Audit Trail & Non-Repudiation

All state mutations write an immutable entry to `audit_log`:
```sql
INSERT INTO audit_log (application_id, action, actor, note, at)
VALUES (%s, %s, %s, %s, %s);
```
- `action`: `SUBMIT`, `WITHDRAW`, `APPROVED`, `REJECTED`, or `DEEMED_APPROVED`.
- `actor`: `citizen:<mobile>`, `officer:<username>`, or `system:rtps-cron`.
- `note`: Statutory officer justifications or system logs.
- `at`: Exact server timestamp in Indian Standard Time (IST).

Once written, audit records are immutable and cannot be updated or deleted via the application layer.
