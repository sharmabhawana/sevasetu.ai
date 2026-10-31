# One-Page Design Note: Seva Setu Agent-Ready Platform

**Author:** Antigravity AI Engineering Team  
**System:** Department of Social Welfare, Government of Purvanchal  
**Scope:** Architecture and Design Rationale for Dual MCP Endpoints, OAuth 2.1 Integration, and Welfare Guardrails  

---

## 1. The Three Decisions That Mattered Most

### Decision 1: Complete Architectural Bifurcation of Citizen and Officer MCP Servers
Instead of running a single unified MCP server with internal role flags or conditional tool visibility, we built two physically independent FastMCP server processes mounted at distinct streamable endpoints (`/mcp/citizen` on port 8001 and `/mcp/officer` on port 8002).

* **Rationale:** In public welfare administration, privilege escalation is a catastrophic failure mode. Standard LLM agents inspect the entire tool registry presented during MCP initialization (`initialize` / `tools/list`). If administrative tools (`approve_application`, `reject_application`, `get_sla_breach_report`) exist in the schema—even if guarded by runtime permission checks—the model may attempt unauthorized tool execution, hallucinatory social-engineering attacks, or tool confusion.
* **Impact:** The Citizen MCP server contains zero officer tools in its registry. An external citizen client running a compact model (such as Claude Code in citizen mode) has zero visibility into departmental capabilities. Even if an attacker tampers with client-side prompts, the officer tools do not exist in the citizen process. Conversely, the Officer MCP server strictly enforces `role=officer` and `scope=officer`, rejecting citizen tokens at the transport layer with HTTP 401/403.

### Decision 2: Zero-Trust Identity Derivation via OAuth 2.1 RFC 8707 Resource Indicators
We anchored all MCP operations to cryptographic identity claims extracted strictly from RS256 JWT access tokens minted by the existing Sewa Setu OAuth 2.1 server, forbidding citizen identification parameters in tool signatures.

* **Rationale:** A naive tool signature like `get_my_application(mobile: str)` creates an Insecure Direct Object Reference (IDOR) vulnerability, allowing an agent or prompt injection to query another citizen's records simply by passing their mobile number.
* **Impact:** Citizen tools (`get_my_profile()`, `get_my_application()`, `get_application_timeline()`) take zero identity arguments. The server extracts the authenticated subject (`sub = citizen:<mobile>`) directly from the verified JWT context. Data queries are strictly scoped to the token's subject in SQL (`WHERE mobile = %s`). Furthermore, by enforcing RFC 8707 `resource` indicators (matching `aud` to the canonical MCP server URL), we prevent token replay across different government services.

### Decision 3: Mandatory Two-Step Confirmation with Pre-Flight State Verification for State Mutations
For irreversible or sensitive welfare operations (`withdraw_pending_application`, `approve_application`, `reject_application`), we designed a stateful two-step confirmation pattern backed by atomic database preconditions.

* **Rationale:** AI models can suffer from premature tool calling when processing conversational queries (e.g., an elderly citizen asking *"What if I withdraw my form?"* or an officer asking *"What happens if I reject this?"*).
* **Impact:** Any mutation invoked without `confirm=True` does not execute; instead, it returns an explicit preview of the pending action, affected applicant details, and a clear confirmation prompt. When `confirm=True` is received, the operation validates that the target application is in `PENDING` status (`WHERE id = %s AND status = 'PENDING'`), commits the transition atomically, and creates an immutable row in `audit_log` with the exact actor (`citizen:<mobile>` or `officer:<username>`) and timestamp. An application already `APPROVED`, `REJECTED`, or `DEEMED_APPROVED` cannot be mutated.

---

## 2. The Decision We Would Make Differently With More Time

### Asynchronous Event-Driven Task Queue for RTPS Statutory SLA Deemed-Approvals
In the current implementation, statutory deemed-approval under the Purvanchal Right to Public Services (RTPS) Act is executed via a nightly scheduled cron job (`scripts/deemed_approval.py`) running in a separate container at 02:00.

* **Limitation of Current Approach:** The batch sweep model evaluates SLA compliance on a 24-hour cadence. For applications whose 15-day statutory window expires at 10:00 AM, the applicant remains in `PENDING` limbo until 02:00 AM the following morning. Furthermore, in high-volume production (~100,000 applications), batch database sweeps lock rows and create CPU spikes.
* **What We Would Build Differently:** With additional engineering runway, we would implement an asynchronous, event-driven task queue (using Celery/Redis or PostgreSQL `LISTEN/NOTIFY` with temporal scheduling). Upon application submission, an exact statutory deadline timestamp (`submitted_at + INTERVAL '15 days'`) would be indexed. An asynchronous worker pool would process deemed approvals the exact minute an SLA expires, push real-time Server-Sent Events (SSE) to connected citizen assistants, and trigger immediate carrier SMS dispatch without batch locking.
