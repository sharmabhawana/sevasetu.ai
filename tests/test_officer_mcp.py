# -*- coding: utf-8 -*-
"""
Tests for Block Officer MCP Server: tool discovery, queue review, SLA breach reports,
audited approvals/rejections, and invalid state transition prevention.
"""

import os
import sys
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from mcp_officer.server import officer_mcp
from mcp_officer import tools as officer_tools
from evals.runner import mint_eval_token, patch_eval_jwks, seed_eval_data_if_needed
from mcp_common.db import get_db_connection


@pytest.fixture(autouse=True)
def setup_environment():
    patch_eval_jwks()
    seed_eval_data_if_needed()


def test_officer_tool_discovery():
    """Verify Officer MCP tool registry contains exactly the 9 authorized officer tools and 0 citizen tools."""
    tools = [t.name for t in officer_mcp._tool_manager.list_tools()]
    expected_tools = [
        "search_applications",
        "get_application_details",
        "list_pending_applications",
        "filter_applications",
        "get_application_audit_history",
        "approve_application",
        "reject_application",
        "get_block_application_statistics",
        "get_sla_breach_report"
    ]
    assert len(tools) == 9
    for exp in expected_tools:
        assert exp in tools

    # Strict check: No citizen tools in officer server
    assert "get_my_profile" not in tools
    assert "withdraw_pending_application" not in tools


def test_officer_search_and_list_pending():
    """Officer can search across applications and list pending cases ordered by submission date."""
    async def _run():
        token = mint_eval_token("officer:admin", role="officer", scope="officer")

        # Search by application number
        search_res = await officer_tools.search_applications("SSP26385548", auth_token=token)
        assert search_res["status"] == "success"
        assert search_res["total_results"] >= 1
        assert search_res["results"][0]["application_no"] == "SSP26385548"

        # List pending applications
        pending_res = await officer_tools.list_pending_applications(limit=10, auth_token=token)
        assert pending_res["status"] == "success"
        assert isinstance(pending_res["pending_applications"], list)
    import asyncio
    asyncio.run(_run())


def test_officer_approval_workflow_and_audit():
    """Officer approval requires confirmation, updates DB status to APPROVED, and writes audit trail."""
    async def _run():
        token = mint_eval_token("officer:admin", role="officer", scope="officer")
        app_no = "SSP26448454"

        # Step 1: Without confirmation -> prompts confirmation
        res1 = await officer_tools.approve_application(app_no, note="Verified by officer", confirm=False, auth_token=token)
        assert res1.get("requires_confirmation") is True

        # Step 2: With confirmation -> commits approval
        res2 = await officer_tools.approve_application(app_no, note="Verified by officer", confirm=True, auth_token=token)
        assert res2.get("success") is True
        assert res2.get("new_status") == "APPROVED"

        # Direct database verification
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status FROM applications WHERE application_no = %s", (app_no,))
        assert cur.fetchone()[0] == "APPROVED"

        cur.execute("SELECT action, actor, note FROM audit_log WHERE action = 'APPROVED' AND actor = 'officer:admin' ORDER BY at DESC LIMIT 1")
        audit = cur.fetchone()
        assert audit is not None
        assert audit[0] == "APPROVED"
        assert "Verified by officer" in audit[2]
        cur.close()
        conn.close()
    import asyncio
    asyncio.run(_run())


def test_officer_rejection_workflow_and_audit():
    """Officer rejection requires justification and confirmation, updates DB status to REJECTED."""
    async def _run():
        token = mint_eval_token("officer:admin", role="officer", scope="officer")
        app_no = "SSP26624691"

        # Missing reason -> fails validation
        res_no_reason = await officer_tools.reject_application(app_no, reason="", confirm=True, auth_token=token)
        assert res_no_reason.get("success") is False

        # Valid rejection with confirmation
        res = await officer_tools.reject_application(app_no, reason="Age proof illegible", confirm=True, auth_token=token)
        assert res.get("success") is True
        assert res.get("new_status") == "REJECTED"

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status FROM applications WHERE application_no = %s", (app_no,))
        assert cur.fetchone()[0] == "REJECTED"
        cur.close()
        conn.close()
    import asyncio
    asyncio.run(_run())


def test_invalid_state_transition_refusal():
    """An application that is not in PENDING status (e.g. APPROVED) cannot be decided again."""
    async def _run():
        token = mint_eval_token("officer:admin", role="officer", scope="officer")
        app_no = "SSP26385548"  # Already APPROVED

        res = await officer_tools.reject_application(app_no, reason="Test rejection", confirm=True, auth_token=token)
        assert res.get("success") is False
        assert "Only applications in PENDING status can be decided" in res.get("error", "")

        # DB state remains untouched
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status FROM applications WHERE application_no = %s", (app_no,))
        assert cur.fetchone()[0] == "APPROVED"
        cur.close()
        conn.close()
    import asyncio
    asyncio.run(_run())


def test_officer_statistics_and_sla_breach_report():
    """Verify aggregated welfare statistics and SLA breach reporting."""
    async def _run():
        token = mint_eval_token("officer:admin", role="officer", scope="officer")

        stats = await officer_tools.get_block_application_statistics(auth_token=token)
        assert stats["status"] == "success"
        assert "total_applications" in stats["statistics"]
        assert "status_breakdown" in stats["statistics"]

        sla_report = await officer_tools.get_sla_breach_report(threshold_days=15, auth_token=token)
        assert sla_report["status"] == "success"
        assert "cases" in sla_report
    import asyncio
    asyncio.run(_run())
