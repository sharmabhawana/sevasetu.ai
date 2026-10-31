# -*- coding: utf-8 -*-
"""
Block Officer MCP Tools for Sewa Setu.
Provides authorized departmental administrative tools for searching, reviewing,
auditing, approving, and rejecting pension applications.
Enforces officer-only role validation and statutory SLA monitoring.
"""

from typing import Dict, Any, Optional, List
from mcp.server.fastmcp import Context
from mcp_common.auth import get_current_officer_username, get_current_user_claims, verify_oauth_jwt
from mcp_common.db import (
    officer_search_applications,
    officer_get_application_details,
    officer_list_pending,
    officer_decide_application,
    officer_get_statistics,
    officer_get_sla_breach_report,
    get_db_connection
)


def _resolve_officer_username(ctx: Optional[Context] = None, auth_token: Optional[str] = None) -> Optional[str]:
    """
    Resolve the authenticated officer's username.
    Strictly derives the subject from verified OAuth officer token.
    Never trusts citizen tokens or unauthenticated callers.
    """
    # 1. From active MCP HTTP bearer context
    username = get_current_officer_username()
    if username:
        return username

    # 2. If token passed explicitly
    if auth_token:
        claims = verify_oauth_jwt(auth_token, expected_role="officer", expected_scope="officer")
        if claims and claims.get("role") == "officer":
            sub = claims.get("sub", "")
            if sub.startswith("officer:"):
                return sub.split(":", 1)[1]

    # 3. Check context meta
    if ctx and hasattr(ctx, "request_context") and ctx.request_context:
        meta = getattr(ctx.request_context, "meta", None)
        if meta and hasattr(meta, "claims"):
            claims = meta.claims
            if claims.get("role") == "officer":
                sub = claims.get("sub", "")
                if sub.startswith("officer:"):
                    return sub.split(":", 1)[1]

    return None


async def search_applications(
    query: str,
    search_type: str = "auto",
    block: Optional[str] = None,
    limit: int = 50,
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search pension applications by application number (e.g. SSP26...), 10-digit mobile number, or applicant name.
    Args:
        query: Search string (application number, mobile, or name).
        search_type: Search mode ('auto', 'application_no', 'mobile', or 'name').
        block: Optional block name to narrow results.
        limit: Max results to return (default 50, max 100).
    """
    officer = _resolve_officer_username(ctx, auth_token)
    if not officer:
        return {"error": "Unauthorized. Officer authentication required.", "status": "unauthorized"}

    results = officer_search_applications(query=query, search_type=search_type, block_filter=block, limit=limit)
    return {
        "status": "success",
        "query": query,
        "search_type": search_type,
        "total_results": len(results),
        "results": results
    }


async def get_application_details(
    application_id: str,
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get full departmental details of an application including status, verification documents, and audit history.
    Args:
        application_id: Application ID (integer) or Application Number (e.g. SSP26123456).
    """
    officer = _resolve_officer_username(ctx, auth_token)
    if not officer:
        return {"error": "Unauthorized. Officer authentication required.", "status": "unauthorized"}

    details = officer_get_application_details(application_id)
    if not details:
        return {
            "status": "not_found",
            "message": f"Application '{application_id}' was not found in the database."
        }

    return {
        "status": "success",
        "application": details
    }


async def list_pending_applications(
    block: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    List pending applications requiring review, ordered from oldest to newest to prioritize statutory SLA compliance.
    Args:
        block: Optional block filter (Sonari, Rajapara, Dhemaji Pathar, Borgaon, Namti, Khelua).
        limit: Number of records to return (default 50).
        offset: Pagination offset.
    """
    officer = _resolve_officer_username(ctx, auth_token)
    if not officer:
        return {"error": "Unauthorized. Officer authentication required.", "status": "unauthorized"}

    pending = officer_list_pending(block=block, limit=limit, offset=offset)
    return {
        "status": "success",
        "block_filter": block or "All blocks",
        "count": len(pending),
        "offset": offset,
        "pending_applications": pending
    }


async def filter_applications(
    status: Optional[str] = None,
    block: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Filter applications by status and/or block with pagination.
    Args:
        status: Application status (PENDING, APPROVED, DEEMED_APPROVED, REJECTED, WITHDRAWN).
        block: Block name.
        limit: Number of records (max 100).
        offset: Offset.
    """
    officer = _resolve_officer_username(ctx, auth_token)
    if not officer:
        return {"error": "Unauthorized. Officer authentication required.", "status": "unauthorized"}

    conn = get_db_connection()
    cur = conn.cursor()
    sql = "SELECT id, application_no, applicant_name, mobile, block, village, status, submitted_at FROM applications WHERE 1=1"
    params = []

    if status:
        sql += " AND status = %s"
        params.append(status.upper())
    if block:
        sql += " AND block = %s"
        params.append(block)

    sql += " ORDER BY submitted_at DESC LIMIT %s OFFSET %s"
    params.extend([max(1, min(limit, 100)), max(0, offset)])

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    results = [
        {
            "application_id": r[0],
            "application_no": r[1],
            "applicant_name": r[2],
            "mobile": r[3],
            "block": r[4],
            "village": r[5],
            "status": r[6],
            "submitted_at": str(r[7]) if r[7] else None
        }
        for r in rows
    ]

    return {
        "status": "success",
        "filtered_count": len(results),
        "status_filter": status,
        "block_filter": block,
        "applications": results
    }


async def get_application_audit_history(
    application_id: str,
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve the statutory audit trail for an application, showing all historical actions, actors, and notes.
    Args:
        application_id: Application ID or number.
    """
    officer = _resolve_officer_username(ctx, auth_token)
    if not officer:
        return {"error": "Unauthorized. Officer authentication required.", "status": "unauthorized"}

    details = officer_get_application_details(application_id)
    if not details:
        return {"error": "Application not found", "status": "not_found"}

    return {
        "status": "success",
        "application_no": details.get("application_no"),
        "audit_history": details.get("audit_history", [])
    }


async def approve_application(
    application_id: str,
    note: str = "Verified and approved per scheme criteria",
    confirm: bool = False,
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Approve a PENDING pension application.
    Requires explicit confirmation (confirm=True). Validates that the application is currently PENDING.
    Records officer identity and timestamp into audit_log.
    Args:
        application_id: Application ID or application number.
        note: Approval remarks or statutory verification notes.
        confirm: Must be explicitly set to True to confirm the approval.
    """
    officer = _resolve_officer_username(ctx, auth_token)
    if not officer:
        return {"error": "Unauthorized. Officer authentication required.", "status": "unauthorized"}

    return officer_decide_application(
        application_id=application_id,
        action="APPROVED",
        note=note,
        officer_username=officer,
        confirm=confirm
    )


async def reject_application(
    application_id: str,
    reason: str,
    confirm: bool = False,
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reject a PENDING pension application with mandatory statutory reason.
    Requires explicit confirmation (confirm=True). Validates that the application is currently PENDING.
    Records officer identity and reason into audit_log.
    Args:
        application_id: Application ID or application number.
        reason: Justification for rejection (e.g., 'Age criteria not met', 'Illegible document').
        confirm: Must be explicitly set to True to confirm rejection.
    """
    officer = _resolve_officer_username(ctx, auth_token)
    if not officer:
        return {"error": "Unauthorized. Officer authentication required.", "status": "unauthorized"}

    if not reason or not reason.strip():
        return {
            "success": False,
            "error": "A valid rejection reason is required by statutory guidelines."
        }

    return officer_decide_application(
        application_id=application_id,
        action="REJECTED",
        note=reason.strip(),
        officer_username=officer,
        confirm=confirm
    )


async def get_block_application_statistics(
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get aggregated welfare statistics: total volume, status distribution, overdue SLA cases, and block distribution.
    """
    officer = _resolve_officer_username(ctx, auth_token)
    if not officer:
        return {"error": "Unauthorized. Officer authentication required.", "status": "unauthorized"}

    stats = officer_get_statistics()
    return {
        "status": "success",
        "statistics": stats
    }


async def get_sla_breach_report(
    threshold_days: int = 15,
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve report of pending applications that have breached or are about to breach the 15-day statutory SLA.
    Such cases are at imminent risk of automatic deemed approval by the RTPS nightly cron job.
    Args:
        threshold_days: SLA threshold in days (default 15).
    """
    officer = _resolve_officer_username(ctx, auth_token)
    if not officer:
        return {"error": "Unauthorized. Officer authentication required.", "status": "unauthorized"}

    overdue_cases = officer_get_sla_breach_report(threshold_days=threshold_days)
    return {
        "status": "success",
        "sla_threshold_days": threshold_days,
        "overdue_cases_count": len(overdue_cases),
        "cases": overdue_cases
    }
