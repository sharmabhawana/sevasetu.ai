# LOOM DEMONSTRATION VIDEO SCRIPT (MAXIMUM 3 MINUTES)

**Platform:** Seva Setu Agent-Ready Government Welfare System  
**Target Video Duration:** Exactly 2 minutes 55 seconds (Under 3:00 limit)  
**Recording Mode:** Loom screen recording with active webcam bubble (face + screen)  
**Presenter:** Antigravity Full-Stack AI & MCP Engineer  

---

## 1. Demo Environment Preparation Checklist

Before recording, ensure your screen has these 4 tabs open in clean, dark-mode browser windows:
1. **Tab 1: Live Web Portal** (`https://${PUBLIC_BASE_URL}`) showing the Old Age Pension scheme countdown and navigation.
2. **Tab 2: Evaluation Dashboard** (`https://${PUBLIC_BASE_URL}/eval-dashboard`) showing 16/16 passed evaluations (100%), summary stats, and persona cards.
3. **Tab 3: Terminal / Claude Code Client** ready with citizen and officer MCP configurations.
4. **Tab 4: Admin Portal / DB View** (`https://${PUBLIC_BASE_URL}/admin/applications`) displaying the live queue and audit trail.

---

## 2. Second-by-Second Video Script

### [0:00 – 0:25] Segment 1: Introduction & Problem Statement (25 seconds)
* **Visual:** Full face camera or screen showing the Seva Setu homepage (`https://${PUBLIC_BASE_URL}`) with camera bubble in bottom-left corner.
* **Audio / Spoken Dialogue:**
  > *"Hello! I am presenting the Seva Setu Agent-Ready platform for the Department of Social Welfare, Government of Purvanchal. Public welfare portals manage critical social safety nets for elderly citizens, but traditional portals present complex digital barriers. Our mission was to transform Seva Setu into a production-grade, Agent-Ready system using the Model Context Protocol (MCP)—preserving the 100,000-application database as the strict system of record, integrating with RFC-compliant OAuth 2.1, and enforcing ironclad security boundaries between citizens and departmental officers."*

---

### [0:25 – 1:00] Segment 2: Citizen AI Assistant Experience (35 seconds)
* **Visual:** Switch to Terminal running Claude Code connected to `/mcp/citizen`, then show portal verification.
* **Action:** Run a query as Persona `CIT-01` (Sewali Gogoi, Age 69).
* **Audio / Spoken Dialogue:**
  > *"Let's test our Citizen Assistant. An elderly citizen, Sewali Gogoi from Dhemaji Pathar, asks: 'Namaste, can you please check if my pension application has been accepted?'*
  > *Notice what happens: The assistant discovers only citizen tools. It invokes `check_application_status()`. Crucially, the tool takes no mobile number parameter—identity is cryptographically derived from the verified OAuth token's subject (`sub = citizen:9217729489`). The assistant responds with empathy in plain terms, confirming application SSP26385548 is Approved with ₹1,000 monthly direct bank transfer. If she checks her profile, her bank account is safely masked as `******5009`."*

---

### [1:00 – 1:35] Segment 3: Block Officer AI Assistant & Administrative Workflow (35 seconds)
* **Visual:** Switch to Terminal running Claude Code connected to `/mcp/officer`, then show `/admin/applications` audit log.
* **Action:** Run `approve_application` with note.
* **Audio / Spoken Dialogue:**
  > *"Now let's switch to the Block Officer Assistant at `/mcp/officer`. Officers manage high-volume queues under the statutory 15-day SLA of the Purvanchal RTPS Act.*
  > *The officer asks: 'Approve application SSP26448454 with note: Age proof verified.'*
  > *Watch the guardrail in action: Because approval is state-changing, the tool enforces a two-step confirmation contract (`confirm=True`). When confirmed, the server updates PostgreSQL atomically, only if the case is currently `PENDING`. Refreshing the portal admin view confirms status changed to `APPROVED` and an immutable record was written to `audit_log` with actor `officer:admin`."*

---

### [1:35 – 2:05] Segment 4: MCP Architecture & Boundary Separation (30 seconds)
* **Visual:** Show code architecture diagram in `PROJECT_ANALYSIS.md` or `SECURITY.md`.
* **Audio / Spoken Dialogue:**
  > *"Architecturally, the core design decision was total physical bifurcation. We do not run a single MCP server with role flags. We run two completely independent FastMCP servers over Streamable HTTP: `/mcp/citizen` on port 8001 and `/mcp/officer` on port 8002.*
  > *Citizen assistants cannot see or discover officer tools—`approve_application` does not exist in the citizen tool schema. Furthermore, if a citizen token is replayed against the officer endpoint, our `OfficerTokenVerifier` rejects it at the transport layer with 401/403 before any tool logic executes."*

---

### [2:05 – 2:35] Segment 5: Evaluation Dashboard & Live Results (30 seconds)
* **Visual:** Switch to browser tab at `/eval-dashboard`. Scroll through metrics, personas, and test cards.
* **Audio / Spoken Dialogue:**
  > *"Here is our live public evaluation dashboard at `/eval-dashboard`. We designed 10 diverse citizen personas—varying in age, rural dialect, and life situations—and 6 officer scenarios.*
  > *Every single evaluation is executed through real FastMCP tool invocations followed by direct PostgreSQL database verification. Across all 16 evaluations, we achieved a 100% pass rate. We tested underage rejections (age 54 < 60), non-sanctioned blocks, chronological timelines, and adversarial attempts where a user tried to access another citizen's bank record—which was strictly blocked."*

---

### [2:35 – 3:00] Segment 6: Key Design Decisions & Future Improvements (25 seconds)
* **Visual:** Show `DESIGN_NOTE.md` or return to camera bubble.
* **Audio / Spoken Dialogue:**
  > *"To summarize our design choices: First, complete MCP bifurcation to prevent privilege escalation. Second, zero-trust cryptographic subject binding via RFC 8707 to eliminate IDOR. Third, mandatory confirmation guardrails on mutations.*
  > *With more time, we would replace the nightly batch SLA deemed-approval cron job with an asynchronous event-driven task queue using PostgreSQL LISTEN/NOTIFY and temporal triggers for minute-by-minute statutory compliance.*
  > *Thank you—the entire platform is live, tested, and ready for evaluation!"*

---

## 3. Post-Recording Checklist & Submission Verification

1. **Verify Duration:** Check the video length in Loom. It MUST be $\le 3:00$ (3 minutes 0 seconds).
2. **Verify Visibility:** Ensure the webcam video bubble shows your face clearly and the screen text is legible at 1080p.
3. **Verify Audio Quality:** Ensure spoken voice is crisp and background noise is minimal.
4. **Publish Settings:** Set Loom privacy to **"Public"** or **"Anyone with the link can view"**.
5. **Paste Loom URL:** Add your final Loom URL to `SUBMISSION_CHECKLIST.md`.
