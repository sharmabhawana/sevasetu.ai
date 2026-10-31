# -*- coding: utf-8 -*-
"""
Block Officer AI Assistant for Sewa Setu.
Assists departmental officers with queue inspection, SLA breach tracking,
application review, and audited approvals/rejections with explicit confirmation.
"""

import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
from mcp_officer.server import officer_mcp
from mcp_officer import tools as officer_tools

logger = logging.getLogger("sewasetu.agent.officer")


class OfficerAIAssistant:
    def __init__(self, auth_token: Optional[str] = None):
        self.auth_token = auth_token
        self.discovered_tools = {t.name: t for t in officer_mcp._tool_manager.list_tools()}

    async def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke a tool on the Officer MCP Server."""
        if tool_name not in self.discovered_tools:
            return {"error": f"Tool '{tool_name}' not available on Officer MCP server."}

        fn = getattr(officer_tools, tool_name, None)
        if not fn:
            return {"error": f"Tool implementation '{tool_name}' not found."}

        args = dict(arguments)
        if "auth_token" not in args and self.auth_token:
            args["auth_token"] = self.auth_token

        try:
            import inspect
            sig = inspect.signature(fn)
            filtered_args = {k: v for k, v in args.items() if k in sig.parameters}
            return await fn(**filtered_args)
        except Exception as e:
            logger.error(f"Error executing Officer MCP tool {tool_name}: {e}")
            return {"error": str(e)}

    async def handle_message(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process an officer's administrative query, discover and invoke Officer MCP tools,
        and generate a concise departmental summary.
        """
        msg = message.strip().lower()

        # 1. Statistics / Dashboard Metrics (check before generic SLA mention)
        if any(w in msg for w in ["statistical", "statistics", "stats", "summary", "overview", "total applications", "volume"]):
            tool_name = "get_block_application_statistics"
            result = await self.call_mcp_tool(tool_name, {})
            stats = result.get("statistics", {})
            text = (
                f"Departmental Overview: {stats.get('total_applications', 0):,} total applications. "
                f"Status Breakdown: {stats.get('status_breakdown', {})}. "
                f"Overdue pending past 15-day SLA: {stats.get('overdue_pending_past_sla', 0):,}."
            )
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 2. SLA Breach Report / Overdue Alerts
        if any(w in msg for w in ["sla", "overdue", "breach", "delayed", "late", "statutory risk"]):
            tool_name = "get_sla_breach_report"
            result = await self.call_mcp_tool(tool_name, {"threshold_days": 15})
            count = result.get("overdue_cases_count", 0)
            text = (
                f"SLA Breach Report: Found {count} pending application(s) exceeding or nearing the "
                f"15-day statutory SLA under the RTPS Act. These cases require immediate review "
                f"before the nightly deemed-approval cron job runs."
            )
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 3. Approve Application
        if "approve" in msg or "approval" in msg:
            app_match = re.search(r"(ssp\d+|\d+)", msg, re.IGNORECASE)
            app_id = app_match.group(1).upper() if app_match else "SSP26000001"
            confirm = "yes" in msg or "confirm" in msg
            tool_name = "approve_application"
            result = await self.call_mcp_tool(tool_name, {
                "application_id": app_id,
                "note": "Approved by block officer via assistant",
                "confirm": confirm
            })
            if result.get("requires_confirmation"):
                text = (
                    f"Action Required: {result.get('message')} "
                    f"Please confirm to commit this approval to the database."
                )
            elif result.get("success"):
                text = f"Confirmed: Application {result.get('application_no')} has been successfully approved."
            else:
                text = f"Approval halted: {result.get('error', 'Unknown error')}"
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 4. Reject Application
        if "reject" in msg or "rejection" in msg:
            app_match = re.search(r"(ssp\d+|\d+)", msg, re.IGNORECASE)
            app_id = app_match.group(1).upper() if app_match else "SSP26000001"
            confirm = "yes" in msg or "confirm" in msg
            reason = "Age documentation invalid or below statutory requirement"
            tool_name = "reject_application"
            result = await self.call_mcp_tool(tool_name, {
                "application_id": app_id,
                "reason": reason,
                "confirm": confirm
            })
            if result.get("requires_confirmation"):
                text = (
                    f"Action Required: {result.get('message')} "
                    f"Please confirm to commit this rejection."
                )
            elif result.get("success"):
                text = f"Confirmed: Application {result.get('application_no')} has been rejected. Reason logged in audit trail."
            else:
                text = f"Rejection halted: {result.get('error', 'Unknown error')}"
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 5. Audit History
        if any(w in msg for w in ["audit", "history", "who approved", "logs", "trail"]):
            app_match = re.search(r"(ssp\d+|\d+)", msg, re.IGNORECASE)
            app_id = app_match.group(1).upper() if app_match else "1"
            tool_name = "get_application_audit_history"
            result = await self.call_mcp_tool(tool_name, {"application_id": app_id})
            history = result.get("audit_history", [])
            text = f"Audit History for {app_id} ({len(history)} events):\n" + "\n".join([f"- {h['timestamp']}: {h['action']} by {h['actor']} ({h['note']})" for h in history])
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 6. List Pending
        if any(w in msg for w in ["pending", "queue", "to review", "unprocessed"]):
            tool_name = "list_pending_applications"
            result = await self.call_mcp_tool(tool_name, {"limit": 10})
            cases = result.get("pending_applications", [])
            text = f"Queue Summary: {len(cases)} pending case(s) retrieved (oldest first for SLA management)."
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 7. Search Applications
        app_match = re.search(r"(ssp\d+|\d{10})", msg, re.IGNORECASE)
        query = app_match.group(1).upper() if app_match else message
        tool_name = "search_applications"
        result = await self.call_mcp_tool(tool_name, {"query": query})
        total = result.get("total_results", 0)
        text = f"Search Results: Found {total} application(s) matching '{query}'."
        return {"response": text, "tool_called": tool_name, "tool_result": result}
