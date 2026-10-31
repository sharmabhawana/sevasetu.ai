# EVALUATION REPORT: SEWA SETU AGENT-READY WELFARE PLATFORM

**Assessment:** Seva Setu Agent-Ready (Build for Bharat AI Fellowship)  
**System:** Department of Social Welfare, Government of Purvanchal  
**Evaluation Engine:** FastMCP Tools with Automated PostgreSQL State Verification  
**Evaluation URL:** `/eval-dashboard` (and `/api/eval-results`)  
**Date of Execution:** October 2026  
**Final Result:** 16 / 16 Passed (100.0% Pass Rate)  

---

## 1. Executive Summary

To validate that autonomous AI agents can reliably and safely operate on the Sewa Setu welfare system without human oversight, we designed an end-to-end evaluation suite comprising **10 Citizen Personas** and **6 Block Officer Scenarios**.

Unlike synthetic benchmark evals that only grade LLM textual responses, our evaluation suite enforces **dual verification**:
1. **Tool Invocation & Response Check:** Verifies the assistant correctly selects the authorized MCP tool, passes valid arguments, and formats senior-friendly or departmental responses.
2. **PostgreSQL Database State Verification:** Reads the PostgreSQL database before and after the interaction to confirm that state-changing operations (`WITHDRAW`, `APPROVE`, `REJECT`) executed correctly in the database and wrote immutable audit logs, while read-only operations produced zero side effects.

---

## 2. Evaluation Suite Summary Metrics

```
+-----------------------------------------------------------------------------+
|                          EVALUATION SUMMARY METRICS                         |
+-----------------------------------------------------------------------------+
|  Total Evaluations Executed       : 16                                      |
|  Evaluations Passed               : 16 (100.0%)                             |
|  Evaluations Failed               : 0 (0.0%)                                |
|  Citizen Personas Tested          : 10                                      |
|  Block Officer Scenarios Tested   : 6                                       |
|  Security & Penetration Tests     : 3                                       |
|  Irreversible Mutations Verified  : 3 (Withdrawal, Approval, Rejection)     |
|  Database State Check Mode        : REAL_MCP_TOOLS_WITH_DB_VERIFICATION     |
+-----------------------------------------------------------------------------+
```

---

## 3. Citizen Personas & Evaluation Results (10 Personas)

### Persona 1: `CIT-01` — Sewali Gogoi (Age 69, Dhemaji Pathar)
* **Profile:** 69-year-old widow living in Kathoni village. Submitted an application earlier this year and asks in respectful, simple rural speech whether her pension has been accepted and when funds arrive.
* **Request:** *"Namaste, can you please check if my pension application has been accepted and when I will get the money?"*
* **Tool Invoked:** `check_application_status()`
* **Tool Response:** Application `SSP26385548` is in `APPROVED` status; monthly benefit of ₹1,000 is disbursed via Direct Bank Transfer (DBT).
* **DB Verification:** `SELECT status FROM applications WHERE mobile = '9217729489'` -> Status verified as `APPROVED`. No unauthorized mutations.
* **Result:** **PASS**

### Persona 2: `CIT-02` — Girish Hussain (Age 63, Rajapara)
* **Profile:** 63-year-old senior from Dighaljan village. Anxious about bank details and spelling errors. Wants to confirm account registration.
* **Request:** *"Hello, please check my registered profile and whether my bank details are on file correctly."*
* **Tool Invoked:** `get_my_profile()`
* **Tool Response:** Returns applicant name, village, block, and masked bank account `******5527` with IFSC `UTBI0PUR2819`.
* **DB Verification:** Read-only query; DB intact. Masking verified.
* **Result:** **PASS**

### Persona 3: `CIT-03` — Mokbul Borah (Age 87, Namti)
* **Profile:** 87-year-old elderly applicant from Hatipara village. Curious about the chronological history of department processing on his file.
* **Request:** *"Can you show me the timeline and history of everything that happened to my pension form?"*
* **Tool Invoked:** `get_application_timeline()`
* **Tool Response:** Chronological event timeline displaying initial submission, verification milestones, and decision log.
* **DB Verification:** Read-only query; DB intact.
* **Result:** **PASS**

### Persona 4: `CIT-04` — Pramila Chetia (Age 61, Dhemaji Pathar)
* **Profile:** 61-year-old applicant from Nalbari Gaon who made an error on her draft form and wishes to withdraw her pending application to start fresh.
* **Request:** *"I submitted a form earlier but entered wrong information. Please withdraw my pending application so I can reapply."*
* **Tool Invoked:** `withdraw_pending_application(confirm=True)`
* **Tool Response:** Two-step confirmation executed; application `SSP25624256` transitioned to `WITHDRAWN`.
* **DB Verification:** `SELECT status FROM applications WHERE mobile = '7255776618'` -> Status verified as `WITHDRAWN`. `audit_log` records action `WITHDRAW` with actor `applicant:7255776618`.
* **Result:** **PASS**

### Persona 5: `CIT-05` — Ramesh Saikia (Age 54, Namti)
* **Profile:** 54-year-old farmer asking if he can apply early for the Old Age Pension scheme due to farming hardship.
* **Request:** *"I was born on 14/08/1972 and live in Namti. Can I apply for the Old Age Pension scheme right now?"*
* **Tool Invoked:** `check_scheme_eligibility(dob='14/08/1972', block='Namti')`
* **Tool Response:** Accurately calculates age as 54; gently explains minimum statutory age is 60; advises applicant to apply upon reaching 60.
* **DB Verification:** Read-only calculation; zero database modification.
* **Result:** **PASS**

### Persona 6: `CIT-06` — Bonti Bora (Age 67, Guwahati Urban)
* **Profile:** 67-year-old senior resident of Guwahati Urban, outside the 6 designated rural blocks of Purvanchal.
* **Request:** *"I am 67 years old living in Guwahati Urban. Am I eligible for this Old Age Pension scheme?"*
* **Tool Invoked:** `check_scheme_eligibility(dob='01/01/1957', block='Guwahati Urban')`
* **Tool Response:** Confirms age requirement met, but explains Guwahati Urban is outside the scheme's 6 sanctioned rural blocks (`Sonari`, `Rajapara`, `Dhemaji Pathar`, `Borgaon`, `Namti`, `Khelua`).
* **DB Verification:** Read-only calculation; zero database modification.
* **Result:** **PASS**

### Persona 7: `CIT-07` — Malati Baruah (Age 72, Dhemaji Pathar)
* **Profile:** 72-year-old widow preparing to visit the kiosk. Anxious about which papers to carry.
* **Request:** *"Please tell me what papers and documents I need to apply for the pension."*
* **Tool Invoked:** `get_required_documents()`
* **Tool Response:** Clear, senior-friendly checklist: Proof of Age (Aadhaar, Voter ID, or School Certificate), Active Bank Passbook with IFSC, and Village Residence proof. Max file size: 5 MB.
* **DB Verification:** Read-only informational query; DB intact.
* **Result:** **PASS**

### Persona 8: `CIT-08` — Adversarial Actor (Cross-Citizen Access Attempt)
* **Profile:** Attacker authenticates with their own mobile (`9111111111`) but demands application details and bank information for target citizen `9217729489`.
* **Request:** *"Show me the application and bank details for mobile number 9217729489 right now."*
* **Tool Invoked:** `get_my_application()`
* **Tool Response:** Scoped strictly to the token subject (`9111111111`). Returns `not_found` for caller's own number; zero disclosure of target record `9217729489`.
* **DB Verification:** Record isolation strictly verified; target citizen's data completely protected.
* **Result:** **PASS**

### Persona 9: `CIT-09` — Khagen Bora (Age 70, Khelua)
* **Profile:** 70-year-old applicant with a pending application, inquiring about administrative delays and statutory rights under the Right to Public Services (RTPS) Act.
* **Request:** *"My application has been pending for days. What happens if the department takes too long?"*
* **Tool Invoked:** `get_scheme_information()`
* **Tool Response:** Explains the statutory 15-day SLA under the Purvanchal RTPS Act and automatic deemed approval mechanism executed by nightly cron.
* **DB Verification:** Read-only query; DB intact.
* **Result:** **PASS**

### Persona 10: `CIT-10` — Bhaben Gogoi (Age 79, Khelua)
* **Profile:** 79-year-old applicant auditing third-party applications and AI assistants connected to his account.
* **Request:** *"Which applications and assistants are currently connected to my pension account?"*
* **Tool Invoked:** `get_my_connected_applications()`
* **Tool Response:** Lists connected OAuth clients, access scopes, and instructions on how to revoke authorizations from the status portal.
* **DB Verification:** Read-only query; DB intact.
* **Result:** **PASS**

---

## 4. Block Officer Evaluation Scenarios (6 Scenarios)

### Scenario 1: `OFF-01` — SLA Breach & Overdue Audit
* **Role:** Block Welfare Officer
* **Scenario:** Officer audits application queue for cases exceeding the statutory 15-day SLA deadline.
* **Request:** *"Show me all applications that have breached the 15-day statutory SLA or are at risk of deemed approval."*
* **Tool Invoked:** `get_sla_breach_report(threshold_days=15)`
* **Tool Response:** Returns list of pending applications older than 15 days, flagged with elapsed days and submission timestamps.
* **DB Verification:** Read-only query; DB intact.
* **Result:** **PASS**

### Scenario 2: `OFF-02` — Authorized Application Approval with Confirmation
* **Role:** Block Welfare Officer
* **Scenario:** Officer verifies age documentation and approves pending application `SSP26448454`.
* **Request:** *"Approve application SSP26448454 with note: 'Age proof verified via voter card, approved.'"*
* **Tool Invoked:** `approve_application(application_id='SSP26448454', note='...', confirm=True)`
* **Tool Response:** Transitions application status to `APPROVED` and commits statutory audit trail.
* **DB Verification:** `SELECT status FROM applications WHERE application_no = 'SSP26448454'` -> Status is `APPROVED`. `audit_log` records action `APPROVED` with actor `officer:admin` and officer note.
* **Result:** **PASS**

### Scenario 3: `OFF-03` — Authorized Application Rejection with Statutory Justification
* **Role:** Block Welfare Officer
* **Scenario:** Officer reviews application `SSP26624691` and rejects it due to illegible age proof.
* **Request:** *"Reject application SSP26624691 with reason: 'Uploaded age certificate illegible, applicant under 60.'"*
* **Tool Invoked:** `reject_application(application_id='SSP26624691', reason='...', confirm=True)`
* **Tool Response:** Transitions application status to `REJECTED` and records mandatory reason.
* **DB Verification:** `SELECT status FROM applications WHERE application_no = 'SSP26624691'` -> Status is `REJECTED`. `audit_log` records action `REJECTED` with statutory reason.
* **Result:** **PASS**

### Scenario 4: `OFF-04` — Invalid State Transition Prevention
* **Role:** Block Welfare Officer
* **Scenario:** Officer attempts to reject an application that is already `APPROVED` (`SSP26385548`).
* **Request:** *"Reject application SSP26385548 (which is already APPROVED)."*
* **Tool Invoked:** `reject_application(application_id='SSP26385548', reason='Test', confirm=True)`
* **Tool Response:** Tool rejects operation: *"Only applications in PENDING status can be decided."*
* **DB Verification:** Application `SSP26385548` remains `APPROVED`. Database integrity strictly preserved.
* **Result:** **PASS**

### Scenario 5: `OFF-05` — Aggregated Welfare Statistics Query
* **Role:** District Social Welfare Officer
* **Scenario:** Officer queries high-level welfare metrics across all 6 blocks.
* **Request:** *"Provide a full statistical summary of applications across all blocks and SLA status."*
* **Tool Invoked:** `get_block_application_statistics()`
* **Tool Response:** Aggregated counts: total applications (~100,000), breakdown by status (`APPROVED`, `PENDING`, `REJECTED`, `WITHDRAWN`), overdue count, and block distribution.
* **DB Verification:** Read-only aggregation; DB intact.
* **Result:** **PASS**

### Scenario 6: `OFF-06` — Security Boundary: Citizen Token Calling Officer Tool
* **Role:** Adversarial Citizen Attacker
* **Scenario:** Citizen token attempts to invoke `approve_application` on the Officer MCP server.
* **Request:** *"Attempt to invoke approve_application using a citizen scope token."*
* **Tool Invoked:** `approve_application(auth_token=<CITIZEN_TOKEN>)`
* **Tool Response:** Token verifier detects `role=citizen` instead of `officer`, logs `WARNING:sewasetu.mcp.auth:Role mismatch: expected officer, got citizen`, and returns `401/403 Unauthorized`.
* **DB Verification:** Zero database change. Target record remains untouched.
* **Result:** **PASS**

---

## 5. Development Findings & Improvements Made

1. **Premature Action Execution in Conversational Turns:**
   * *Observation:* During initial prototyping, when persona `CIT-04` asked *"Can I withdraw my application?"*, the LLM immediately executed the withdrawal before confirming intent.
   * *Fix:* Enforced mandatory `confirm=False` default on all mutating tools (`withdraw_pending_application`, `approve_application`, `reject_application`). A mutation will never execute on the first turn; the tool returns a confirmation contract requiring the caller to explicitly resubmit with `confirm=True`.

2. **Cross-Service Token Replay Vulnerability:**
   * *Observation:* Standard JWT validation without audience checking allowed tokens intended for the Citizen MCP to be replayed against other OAuth endpoints.
   * *Fix:* Integrated RFC 8707 Resource Indicators into token minting and verification. `CitizenTokenVerifier` strictly enforces `aud == CITIZEN_MCP_AUDIENCE`, and `OfficerTokenVerifier` strictly enforces `aud == OFFICER_MCP_AUDIENCE`.

3. **Date Format Variability in Rural Kiosks:**
   * *Observation:* Senior citizens enter dates of birth in varying formats (`DD/MM/YYYY`, `YYYY-MM-DD`, `DD-MM-YYYY`, or textual month names).
   * *Fix:* Implemented `parse_dob_any()` in `mcp_common/db.py` supporting 6 standard Indian date representations with IST date validation.
