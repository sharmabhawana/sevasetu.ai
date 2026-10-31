# -*- coding: utf-8 -*-
"""
Citizen MCP Tools for Sewa Setu.
All tools strictly respect citizen record isolation and senior-friendly output formatting.
"""

from typing import Dict, Any, Optional, List
from mcp.server.fastmcp import Context
from mcp_common.auth import get_current_citizen_mobile, get_current_user_claims, verify_oauth_jwt
from mcp_common.db import (
    citizen_get_profile,
    citizen_get_application,
    citizen_get_timeline,
    citizen_withdraw_application,
    citizen_get_connected_applications,
    parse_dob_any,
    calculate_age,
    BLOCKS,
    MIN_AGE,
    now_ist
)


def _resolve_citizen_mobile(ctx: Optional[Context] = None, token: Optional[str] = None) -> Optional[str]:
    """
    Resolve the authenticated citizen's mobile number.
    Strictly derives the subject from the verified OAuth token.
    Never trusts an arbitrary user-supplied mobile number.
    """
    # 1. From active MCP HTTP bearer context
    mobile = get_current_citizen_mobile()
    if mobile:
        return mobile

    # 2. If token passed explicitly (e.g. testing or CLI client without HTTP headers)
    if token:
        claims = verify_oauth_jwt(token, expected_role="citizen", expected_scope="citizen")
        if claims and claims.get("role") == "citizen":
            sub = claims.get("sub", "")
            if sub.startswith("citizen:"):
                return sub.split(":", 1)[1]

    # 3. Check context meta if available
    if ctx and hasattr(ctx, "request_context") and ctx.request_context:
        meta = getattr(ctx.request_context, "meta", None)
        if meta and hasattr(meta, "claims"):
            sub = meta.claims.get("sub", "")
            if sub.startswith("citizen:"):
                return sub.split(":", 1)[1]

    return None


async def get_my_profile(ctx: Optional[Context] = None, auth_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve your registered applicant profile details.
    Displays your name, masked mobile number, village, block, and masked bank account.
    Personal bank details are masked for your privacy and security.
    """
    mobile = _resolve_citizen_mobile(ctx, auth_token)
    if not mobile:
        return {
            "error": "Authentication required. Please authenticate via the Sewa Setu portal to view your profile.",
            "status": "unauthenticated"
        }

    profile = citizen_get_profile(mobile)
    if not profile:
        return {
            "status": "not_found",
            "message": "No registered pension application found for your authenticated mobile number. You can check eligibility or start a new application on the portal."
        }

    return {
        "status": "success",
        "profile": profile,
        "message": f"Profile retrieved successfully for {profile['applicant_name']}."
    }


async def get_my_application(ctx: Optional[Context] = None, auth_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve full details of your pension application.
    Returns your application number, current status, submission date, village, block, and bank IFSC.
    """
    mobile = _resolve_citizen_mobile(ctx, auth_token)
    if not mobile:
        return {
            "error": "Authentication required. Please authenticate via the Sewa Setu portal to view your application.",
            "status": "unauthenticated"
        }

    app_data = citizen_get_application(mobile)
    if not app_data:
        return {
            "status": "not_found",
            "message": "No application found for your registered mobile number."
        }

    status = app_data["status"]
    status_explanations = {
        "PENDING": "Your application is currently under review by the Block Social Welfare Officer. Statutory processing SLA is 15 working days.",
        "APPROVED": "Congratulations! Your pension application has been approved. Monthly disbursements of ₹1,000 will be deposited directly to your bank account.",
        "DEEMED_APPROVED": "Your application has been automatically approved under the Purvanchal Right to Public Services Act (RTPS) after exceeding the 15-day SLA.",
        "REJECTED": "Your application could not be approved. Please review the officer remarks or contact your Block Social Welfare office.",
        "WITHDRAWN": "You withdrew this application. You are eligible to submit a fresh application on the portal."
    }

    return {
        "status": "success",
        "application": app_data,
        "status_explanation": status_explanations.get(status, f"Status: {status}"),
        "can_withdraw": status == "PENDING"
    }


async def check_application_status(ctx: Optional[Context] = None, auth_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Quick status check of your pension application.
    Returns a simple, clear explanation of where your application stands in plain language.
    """
    mobile = _resolve_citizen_mobile(ctx, auth_token)
    if not mobile:
        return {
            "error": "Please sign in with your mobile number to check your application status.",
            "status": "unauthenticated"
        }

    app_data = citizen_get_application(mobile)
    if not app_data:
        return {
            "status": "no_application",
            "message": "We could not find any active pension application for your mobile number."
        }

    status = app_data["status"]
    app_no = app_data["application_no"]

    explanations = {
        "PENDING": f"Application {app_no} is PENDING review by the Block Officer. It was submitted on {app_data['submitted_at']}.",
        "APPROVED": f"Application {app_no} is APPROVED! Monthly pension will be credited to your bank account via Direct Benefit Transfer.",
        "DEEMED_APPROVED": f"Application {app_no} stands DEEMED APPROVED under the Right to Public Services statutory timeline guarantee.",
        "REJECTED": f"Application {app_no} was REJECTED. You may submit a new application with corrected documents.",
        "WITHDRAWN": f"Application {app_no} was WITHDRAWN by you. You can apply again anytime."
    }

    return {
        "application_no": app_no,
        "current_status": status,
        "summary": explanations.get(status, f"Current status: {status}"),
        "submitted_at": app_data["submitted_at"],
        "decided_at": app_data["decided_at"]
    }


async def get_application_timeline(ctx: Optional[Context] = None, auth_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve the complete event history and timeline of your application.
    Shows every step from initial submission to verification and decisions.
    """
    mobile = _resolve_citizen_mobile(ctx, auth_token)
    if not mobile:
        return {
            "error": "Authentication required. Please sign in to view your timeline.",
            "status": "unauthenticated"
        }

    timeline = citizen_get_timeline(mobile)
    if not timeline:
        return {
            "timeline": [],
            "message": "No timeline history found for your application."
        }

    readable_events = []
    for ev in timeline:
        action = ev["action"]
        ts = ev["timestamp"]
        actor = ev["actor"]
        note = ev["note"]

        if action == "SUBMIT":
            desc = f"Application submitted online on {ts}."
        elif action == "WITHDRAW":
            desc = f"Application withdrawn by applicant on {ts}."
        elif action == "APPROVED":
            desc = f"Application approved on {ts}. Note: {note}"
        elif action == "REJECTED":
            desc = f"Application rejected on {ts}. Reason: {note}"
        elif action == "DEEMED_APPROVED":
            desc = f"Application automatically deemed approved on {ts} under the RTPS Act (15-day statutory SLA)."
        else:
            desc = f"Action '{action}' recorded on {ts}."

        readable_events.append({
            "action": action,
            "timestamp": ts,
            "description": desc
        })

    return {
        "status": "success",
        "total_events": len(readable_events),
        "events": readable_events
    }


async def check_scheme_eligibility(date_of_birth: str, block: str) -> Dict[str, Any]:
    """
    Check if a person is eligible for the Old Age Pension Scheme before applying.
    Args:
        date_of_birth: Date of birth (formats accepted: DD/MM/YYYY, YYYY-MM-DD, or DDMMYYYY).
        block: Residential block name in Purvanchal (must be one of: Sonari, Rajapara, Dhemaji Pathar, Borgaon, Namti, Khelua).
    """
    dob = parse_dob_any(date_of_birth)
    if not dob:
        return {
            "eligible": False,
            "reason": "Invalid date of birth format. Please provide date of birth as DD/MM/YYYY (e.g., 15/04/1955)."
        }

    age = calculate_age(dob)
    age_eligible = age >= MIN_AGE

    block_clean = (block or "").strip().title()
    matched_block = None
    for b in BLOCKS:
        if b.lower() == block_clean.lower():
            matched_block = b
            break
    block_eligible = matched_block is not None

    eligible = age_eligible and block_eligible
    reasons = []
    if not age_eligible:
        reasons.append(f"Age criterion not met: applicant is {age} years old, but minimum age is {MIN_AGE} years.")
    if not block_eligible:
        reasons.append(f"Block '{block}' is not covered. Eligible blocks are: {', '.join(BLOCKS)}.")

    return {
        "eligible": eligible,
        "calculated_age": age,
        "minimum_age_required": MIN_AGE,
        "block_validated": matched_block or block,
        "eligible_blocks": BLOCKS,
        "status_summary": "Eligible to apply for Old Age Pension Scheme" if eligible else "Not currently eligible",
        "reasons": reasons,
        "next_steps": "You can apply on the Sewa Setu portal with your mobile number, bank account, and age-proof document." if eligible else "Please verify age and residential block eligibility criteria."
    }


async def get_required_documents() -> Dict[str, Any]:
    """
    Get the official checklist of documents required for applying for the pension.
    """
    return {
        "scheme": "Old Age Pension Scheme (Department of Social Welfare)",
        "required_documents": [
            {
                "document": "Proof of Age (Mandatory)",
                "acceptable_types": [
                    "Aadhaar Card",
                    "Electoral Photo Identity Card (Voter ID)",
                    "School Leaving Certificate / Matriculation Certificate",
                    "Birth Certificate issued by Registrar of Births & Deaths",
                    "Medical Board Age Certificate"
                ],
                "format": "JPG, PNG, or PDF file",
                "max_size": "5 MB"
            },
            {
                "document": "Bank Account Details (Mandatory)",
                "details": "Active single bank account in applicant's name with valid 11-digit IFSC code for Direct Benefit Transfer (DBT)."
            },
            {
                "document": "Residential Details (Mandatory)",
                "details": "Village and Block within sanctioned jurisdictions (Sonari, Rajapara, Dhemaji Pathar, Borgaon, Namti, Khelua)."
            }
        ],
        "important_note": "Ensure the applicant's name on the bank account matches the name on the age-proof document to prevent DBT payment rejections."
    }


async def get_scheme_information() -> Dict[str, Any]:
    """
    Get comprehensive information about the Old Age Pension Scheme, benefits, and rules.
    """
    return {
        "scheme_name": "Old Age Pension Scheme (Indira Gandhi National Old Age Pension Scheme component)",
        "department": "Department of Social Welfare, Government of Purvanchal",
        "monthly_pension_amount": "₹1,000 per month directly deposited to bank account",
        "eligibility_criteria": {
            "minimum_age": f"{MIN_AGE} years of age or older",
            "residence": "Resident of one of the 6 sanctioned blocks: Sonari, Rajapara, Dhemaji Pathar, Borgaon, Namti, Khelua",
            "active_applications": "At most one active application per mobile number"
        },
        "statutory_guarantee": {
            "sla_working_days": 15,
            "statutory_act": "Purvanchal Right to Public Services Act",
            "deemed_approval": "If no decision is rendered within 15 working days, application stands automatically approved by law."
        },
        "application_deadline": "2026-10-31 23:59 IST",
        "how_to_apply": "Visit the Sewa Setu portal at /apply using any mobile phone. An OTP will be sent to verify your identity."
    }


async def withdraw_pending_application(
    confirm: bool = False,
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Withdraw your pending pension application so that you can correct details or apply afresh.
    Only applications in PENDING status can be withdrawn.
    Requires explicit confirmation (confirm=True) to prevent accidental withdrawals.
    Args:
        confirm: Must be explicitly set to True to confirm the withdrawal.
    """
    mobile = _resolve_citizen_mobile(ctx, auth_token)
    if not mobile:
        return {
            "error": "Authentication required. Please sign in to withdraw your application.",
            "status": "unauthenticated"
        }

    return citizen_withdraw_application(mobile, confirm=confirm)


async def get_my_connected_applications(
    ctx: Optional[Context] = None,
    auth_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    List third-party AI assistants and applications that currently have permission to act on your behalf.
    """
    mobile = _resolve_citizen_mobile(ctx, auth_token)
    if not mobile:
        return {
            "error": "Authentication required.",
            "status": "unauthenticated"
        }

    apps = citizen_get_connected_applications(mobile)
    return {
        "status": "success",
        "connected_applications_count": len(apps),
        "applications": apps,
        "note": "You can revoke access to any connected application anytime at the Sewa Setu Status Portal under Connected Applications."
    }
