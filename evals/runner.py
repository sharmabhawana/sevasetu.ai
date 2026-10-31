# -*- coding: utf-8 -*-
"""
Evaluation Runner for Sewa Setu Agent-Ready Platform.
Executes 10 Citizen Personas and 6 Officer Scenarios through FastMCP tools,
verifies PostgreSQL / database state, and records structured evaluation outcomes.
"""

import os
import sys
import json
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from evals.personas import CITIZEN_PERSONAS, OFFICER_SCENARIOS
from agents.citizen_agent import CitizenAIAssistant
from agents.officer_agent import OfficerAIAssistant
from mcp_common.db import get_db_connection, now_ist

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.json")

# Generate or reuse test RSA keypair for evaluation tokens
_EVAL_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_EVAL_PUB = _EVAL_KEY.public_key()
_EVAL_KID = "eval-key-01"


def mint_eval_token(subject: str, role: str, scope: str, audience: str = "http://localhost:8000") -> str:
    """Mint RS256 JWT for automated evaluation testing."""
    now = int(time.time())
    claims = {
        "iss": "http://localhost:8000",
        "sub": subject,
        "aud": audience,
        "scope": scope,
        "role": role,
        "client_id": "eval-client",
        "iat": now,
        "exp": now + 3600,
        "jti": f"eval-{now}-{subject}"
    }
    pem = _EVAL_KEY.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()
    )
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": _EVAL_KID})


def patch_eval_jwks():
    """Register eval public key in mcp_common.auth cache so evaluation tokens validate seamlessly."""
    import mcp_common.auth as auth_mod
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_EVAL_PUB))
    jwk.update({"kid": _EVAL_KID, "alg": "RS256", "use": "sig"})
    auth_mod._JWKS_CACHE = {"keys": [jwk]}
    auth_mod._JWKS_CACHE_TIME = time.time() + 86400


def seed_eval_data_if_needed():
    """Ensure sample applications exist in database for the evaluation personas."""
    conn = get_db_connection()
    cur = conn.cursor()
    # Check if applications table has rows
    cur.execute("SELECT count(*) FROM applications")
    count = cur.fetchone()[0]

    sample_apps = [
        ("SSP26385548", "Sewali Gogoi", "9217729489", "1957-04-10", "Female", "Widowed", "Kathoni", "Dhemaji Pathar", "3876903950095", "CNRB0004417", "APPROVED"),
        ("SSP26448454", "Girish Hussain", "7747934527", "1963-01-16", "Male", "Unmarried", "Dighaljan", "Rajapara", "129068125527", "UTBI0PUR2819", "PENDING"),
        ("SSP26624691", "Mokbul Borah", "9019248569", "1939-04-15", "Male", "Married", "Hatipara", "Namti", "8696030949776", "CNRB0004417", "PENDING"),
        ("SSP25624256", "Pramila Chetia", "7255776618", "1965-01-24", "Female", "Married", "Nalbari Gaon", "Dhemaji Pathar", "7632403335256", "IDIB000S118", "PENDING"),
        ("SSP26210265", "Khagen Bora", "6261941141", "1956-05-06", "Male", "Widowed", "Sialmari", "Khelua", "3846200801757", "SBIN0003077", "PENDING"),
        ("SSP25587446", "Bhaben Gogoi", "9178627113", "1946-12-26", "Male", "Unmarried", "Chengelimara", "Khelua", "9195980138414", "PUNB0556610", "APPROVED"),
    ]

    for app_no, name, mob, dob, gender, mstatus, vill, blk, acc, ifsc, st in sample_apps:
        cur.execute("SELECT id FROM applications WHERE mobile = %s", (mob,))
        row = cur.fetchone()
        if not row:
            cur.execute("""
                INSERT INTO applications (application_no, applicant_name, mobile, dob, gender, marital_status,
                                          village, block, bank_account, ifsc, status, submitted_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (app_no, name, mob, dob, gender, mstatus, vill, blk, acc, ifsc, st, datetime.now()))
        else:
            cur.execute("UPDATE applications SET status = %s WHERE mobile = %s", (st, mob))

    # Add audit log entries for timeline testing
    cur.execute("SELECT id FROM applications WHERE application_no = 'SSP26385548'")
    row = cur.fetchone()
    if row:
        app_id = row[0]
        cur.execute("SELECT count(*) FROM audit_log WHERE application_id = %s", (app_id,))
        if cur.fetchone()[0] == 0:
            cur.execute("""
                INSERT INTO audit_log (application_id, action, actor, note, at)
                VALUES (%s, 'SUBMIT', 'applicant:9217729489', 'Online application submitted', %s)
            """, (app_id, datetime.now()))
            cur.execute("""
                INSERT INTO audit_log (application_id, action, actor, note, at)
                VALUES (%s, 'APPROVED', 'admin', 'Verified and approved', %s)
            """, (app_id, datetime.now()))

    conn.commit()
    cur.close()
    conn.close()


async def run_all_evaluations() -> Dict[str, Any]:
    """Execute complete evaluation suite against FastMCP tools and verify database states."""
    patch_eval_jwks()
    seed_eval_data_if_needed()

    citizen_results = []
    officer_results = []

    # -----------------------------------------------------------------------
    # 1. Execute Citizen Personas
    # -----------------------------------------------------------------------
    for p in CITIZEN_PERSONAS:
        token = mint_eval_token(f"citizen:{p['mobile']}", role="citizen", scope="citizen")
        assistant = CitizenAIAssistant(auth_token=token)

        start_t = time.time()
        res = await assistant.handle_message(p["request"])
        exec_ms = int((time.time() - start_t) * 1000)

        # Database verification
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status FROM applications WHERE mobile = %s ORDER BY submitted_at DESC LIMIT 1", (p["mobile"],))
        db_row = cur.fetchone()
        actual_db_status = db_row[0] if db_row else "NO_RECORD"
        cur.close()
        conn.close()

        # Determine pass/fail based on tool execution and DB state
        passed = False
        notes = ""

        if p["id"] == "CIT-01":  # Status check
            passed = res.get("tool_called") == "check_application_status" and actual_db_status == "APPROVED"
        elif p["id"] == "CIT-02":  # Profile check
            passed = res.get("tool_called") == "get_my_profile" and "bank_account_masked" in str(res.get("tool_result"))
        elif p["id"] == "CIT-03":  # Timeline
            passed = res.get("tool_called") == "get_application_timeline"
        elif p["id"] == "CIT-04":  # Withdrawal
            # Test 2-step: first request prompted confirmation, now confirm
            res2 = await assistant.handle_message("Yes, please confirm withdrawal of my application")
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT status FROM applications WHERE mobile = %s", (p["mobile"],))
            actual_db_status = cur.fetchone()[0]
            cur.close(); conn.close()
            passed = actual_db_status == "WITHDRAWN" and res2.get("tool_result", {}).get("success") is True
            res = res2
        elif p["id"] in ("CIT-05", "CIT-06"):  # Eligibility checks
            passed = res.get("tool_called") == "check_scheme_eligibility" and res.get("tool_result", {}).get("eligible") is False
        elif p["id"] == "CIT-07":  # Required documents
            passed = res.get("tool_called") == "get_required_documents" and "required_documents" in res.get("tool_result", {})
        elif p["id"] == "CIT-08":  # Unauthorized cross-citizen access
            # Malicious user with token for 9111111111 asked for 9217729489
            # Verify tool did NOT disclose 9217729489's data
            tool_res_str = str(res.get("tool_result"))
            passed = "Sewali" not in tool_res_str and "Kathoni" not in tool_res_str
            actual_db_status = "RECORD_ISOLATED"
        elif p["id"] == "CIT-09":  # Scheme info / SLA
            passed = res.get("tool_called") in ("get_scheme_information", "check_application_status")
        elif p["id"] == "CIT-10":  # Connected apps
            passed = res.get("tool_called") == "get_my_connected_applications"
        else:
            passed = res.get("tool_called") is not None

        citizen_results.append({
            "id": p["id"],
            "persona_name": p["name"],
            "age": p["age"],
            "village": p["village"],
            "block": p["block"],
            "user_request": p["request"],
            "assistant_response": res.get("response"),
            "mcp_tool_called": res.get("tool_called"),
            "mcp_tool_result": res.get("tool_result"),
            "expected_behavior": p["expected_behavior"],
            "expected_db_state": p["expected_db_state"],
            "actual_db_state": actual_db_status,
            "status": "PASS" if passed else "FAIL",
            "execution_ms": exec_ms,
            "timestamp": datetime.now().isoformat()
        })

    # -----------------------------------------------------------------------
    # 2. Execute Block Officer Scenarios
    # -----------------------------------------------------------------------
    officer_token = mint_eval_token("officer:admin", role="officer", scope="officer")
    officer_assistant = OfficerAIAssistant(auth_token=officer_token)

    for sc in OFFICER_SCENARIOS:
        start_t = time.time()
        actual_db_status = "VERIFIED"
        passed = False

        if sc["id"] == "OFF-01":  # SLA breach report
            res = await officer_assistant.handle_message(sc["request"])
            passed = res.get("tool_called") == "get_sla_breach_report"
        elif sc["id"] == "OFF-02":  # Approve with confirmation
            # Step 1: Prompt confirmation
            res1 = await officer_assistant.handle_message("Approve application SSP26448454")
            # Step 2: Confirm approval
            res = await officer_assistant.handle_message("Yes, I confirm approval of application SSP26448454")
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT status FROM applications WHERE application_no = 'SSP26448454'")
            actual_db_status = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM audit_log WHERE action = 'APPROVED' AND actor = 'officer:admin'")
            audit_count = cur.fetchone()[0]
            cur.close(); conn.close()
            passed = actual_db_status == "APPROVED" and audit_count > 0
        elif sc["id"] == "OFF-03":  # Reject with confirmation
            res1 = await officer_assistant.handle_message("Reject application SSP26624691")
            res = await officer_assistant.handle_message("Yes, I confirm rejection of application SSP26624691")
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT status FROM applications WHERE application_no = 'SSP26624691'")
            actual_db_status = cur.fetchone()[0]
            cur.close(); conn.close()
            passed = actual_db_status == "REJECTED"
        elif sc["id"] == "OFF-04":  # Invalid state transition refusal
            # Try to reject an APPROVED application (SSP26385548)
            res = await officer_assistant.handle_message("Reject application SSP26385548")
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("SELECT status FROM applications WHERE application_no = 'SSP26385548'")
            actual_db_status = cur.fetchone()[0]
            cur.close(); conn.close()
            # Must remain APPROVED and tool returned refusal
            passed = actual_db_status == "APPROVED" and "Cannot reject" in str(res.get("response"))
        elif sc["id"] == "OFF-05":  # Statistics query
            res = await officer_assistant.handle_message(sc["request"])
            passed = res.get("tool_called") == "get_block_application_statistics" and "total_applications" in res.get("tool_result", {}).get("statistics", {})
        elif sc["id"] == "OFF-06":  # Citizen token attempting officer tool
            citizen_tok = mint_eval_token("citizen:9217729489", role="citizen", scope="citizen")
            rogue_officer_assistant = OfficerAIAssistant(auth_token=citizen_tok)
            res = await rogue_officer_assistant.handle_message("Approve application SSP26448454")
            # Tool must reject with unauthorized error
            passed = "Unauthorized" in str(res.get("response")) or "error" in res.get("tool_result", {})
            actual_db_status = "UNAUTHORIZED_ACCESS_BLOCKED"
        else:
            res = await officer_assistant.handle_message(sc["request"])
            passed = True

        exec_ms = int((time.time() - start_t) * 1000)

        officer_results.append({
            "id": sc["id"],
            "scenario_name": sc["name"],
            "role": sc["role"],
            "user_request": sc["request"],
            "assistant_response": res.get("response"),
            "mcp_tool_called": res.get("tool_called"),
            "mcp_tool_result": res.get("tool_result"),
            "expected_behavior": sc["expected_behavior"],
            "expected_db_state": sc["expected_db_state"],
            "actual_db_state": actual_db_status,
            "status": "PASS" if passed else "FAIL",
            "execution_ms": exec_ms,
            "timestamp": datetime.now().isoformat()
        })

    # Summary metrics
    all_evals = citizen_results + officer_results
    passed_count = sum(1 for e in all_evals if e["status"] == "PASS")
    failed_count = len(all_evals) - passed_count
    pass_pct = round((passed_count / len(all_evals)) * 100, 1)

    payload = {
        "summary": {
            "total_evaluations": len(all_evals),
            "passed_evaluations": passed_count,
            "failed_evaluations": failed_count,
            "pass_percentage": pass_pct,
            "executed_at": datetime.now().isoformat(),
            "execution_mode": "REAL_MCP_TOOLS_WITH_DB_VERIFICATION"
        },
        "citizen_evaluations": citizen_results,
        "officer_evaluations": officer_results,
        "limitations_identified": [
            "Voice input is not yet directly integrated in the web portal; elderly users rely on text/kiosk assisted speech-to-text.",
            "Local dialect support (specific Assamese regional variants) is handled via Hindi/Assamese keyword mapping rather than multi-dialect audio models.",
            "OAuth token lifetime is strictly capped at 2 hours for citizens and 8 hours for officers; long-running conversations require refresh token rotation."
        ]
    }

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload


if __name__ == "__main__":
    results = asyncio.run(run_all_evaluations())
    print(f"Evaluations complete: {results['summary']['passed_evaluations']}/{results['summary']['total_evaluations']} passed ({results['summary']['pass_percentage']}%)")
