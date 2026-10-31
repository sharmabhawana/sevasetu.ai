# -*- coding: utf-8 -*-
"""
Citizen AI Assistant for Sewa Setu.
Interacts with senior citizens using empathetic, respectful, and clear language.
Discovers and executes tools from the Citizen MCP Server.
"""

import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
from mcp_citizen.server import citizen_mcp
from mcp_citizen import tools as citizen_tools
from mcp_common.db import now_ist

logger = logging.getLogger("sewasetu.agent.citizen")


class CitizenAIAssistant:
    def __init__(self, auth_token: Optional[str] = None):
        self.auth_token = auth_token
        self.discovered_tools = {t.name: t for t in citizen_mcp._tool_manager.list_tools()}

    async def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke a tool on the Citizen MCP Server."""
        if tool_name not in self.discovered_tools:
            return {"error": f"Tool '{tool_name}' not available on Citizen MCP server."}

        fn = getattr(citizen_tools, tool_name, None)
        if not fn:
            return {"error": f"Tool implementation '{tool_name}' not found."}

        args = dict(arguments)
        # Pass auth_token if available
        if "auth_token" not in args and self.auth_token:
            args["auth_token"] = self.auth_token

        try:
            # Check if fn accepts auth_token
            import inspect
            sig = inspect.signature(fn)
            filtered_args = {k: v for k, v in args.items() if k in sig.parameters}
            return await fn(**filtered_args)
        except Exception as e:
            logger.error(f"Error executing MCP tool {tool_name}: {e}")
            return {"error": str(e)}

    async def handle_message(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process a citizen's natural language message, identify intent,
        invoke the corresponding MCP tool, and return a respectful explanation.
        """
        msg = message.strip().lower()

        # 1. Scheme Information / Benefit Details
        if any(w in msg for w in ["what is this scheme", "scheme information", "about pension", "how much money", "benefit amount", "kitna paisa"]):
            tool_name = "get_scheme_information"
            result = await self.call_mcp_tool(tool_name, {})
            text = (
                f"Namaste! The Old Age Pension Scheme provides ₹1,000 per month directly into your bank account. "
                f"It is available for respected senior citizens aged 60 and above living in our 6 blocks: "
                f"Sonari, Rajapara, Dhemaji Pathar, Borgaon, Namti, and Khelua. "
                f"Under the Right to Public Services Act, applications are decided within 15 working days."
            )
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 2. Required Documents
        if any(w in msg for w in ["document", "kagaz", "what do i need", "certificate", "proof", "requirements"]):
            tool_name = "get_required_documents"
            result = await self.call_mcp_tool(tool_name, {})
            text = (
                "To apply for the Old Age Pension, you need just three things:\n"
                "1. Proof of age (Aadhaar card, Voter ID, birth certificate, or school leaving certificate) showing you are 60 or older.\n"
                "2. Your bank account details (account number and 11-digit IFSC code).\n"
                "3. Your residential village and block in Purvanchal.\n"
                "Make sure your name on the bank account matches your age certificate."
            )
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 3. Profile / Personal Info (check before generic check status)
        if any(w in msg for w in ["profile", "my profile", "bank details", "my details", "who am i", "my name", "registered profile"]):
            tool_name = "get_my_profile"
            result = await self.call_mcp_tool(tool_name, {})
            p = result.get("profile")
            if p:
                text = (
                    f"Respected {p['applicant_name']},\n"
                    f"Village: {p['village']}, Block: {p['block']}\n"
                    f"Bank Account: {p['bank_account_masked']} (IFSC: {p['ifsc']})\n"
                    f"Latest status: {p['latest_application_status']}"
                )
            else:
                text = result.get("message", "No profile found.")
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 4. Check Eligibility
        dob_match = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2})", message)
        age_match = re.search(r"(\d{2})\s*(?:years|yr|saal)", message, re.IGNORECASE)
        if dob_match or age_match or any(w in msg for w in ["eligible", "can i apply", "am i allowed", "age requirement"]):
            if dob_match:
                dob_str = dob_match.group(1)
            elif age_match:
                age_val = int(age_match.group(1))
                curr_year = now_ist().year
                dob_str = f"01/01/{curr_year - age_val}"
            else:
                dob_str = "01/01/1960"

            # Look for block in message
            blocks = ["sonari", "rajapara", "dhemaji pathar", "borgaon", "namti", "khelua"]
            matched_block = None
            for b in blocks:
                if b in msg:
                    matched_block = b.title()
                    break

            if not matched_block:
                # Check if an explicit block/city was mentioned (e.g. Guwahati, Dispur)
                loc_match = re.search(r"(?:living in|in|at)\s+([A-Za-z\s]+?)(?:\.|\?|,|$)", message, re.IGNORECASE)
                if loc_match:
                    matched_block = loc_match.group(1).strip()
                else:
                    matched_block = "Unknown"

            tool_name = "check_scheme_eligibility"
            result = await self.call_mcp_tool(tool_name, {"date_of_birth": dob_str, "block": matched_block})
            if result.get("eligible"):
                text = (
                    f"Great news! Based on your date of birth ({dob_str}, age {result['calculated_age']} years) "
                    f"and block ({matched_block}), you are eligible to receive the Old Age Pension. "
                    f"You may apply on the Sewa Setu portal."
                )
            else:
                reasons = " ".join(result.get("reasons", []))
                text = f"We checked your details: {reasons} Please check the requirements or visit your local Block office."
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 5. Withdraw Application
        if any(w in msg for w in ["withdraw", "cancel application", "take back", "cancel my"]):
            # Only confirm if user explicitly says yes or confirm
            confirm = "yes" in msg or "confirm" in msg
            tool_name = "withdraw_pending_application"
            result = await self.call_mcp_tool(tool_name, {"confirm": confirm})
            if result.get("requires_confirmation"):
                text = (
                    f"You have requested to withdraw your pending application ({result.get('application_no')}). "
                    f"Please confirm: are you sure you want to withdraw this application? "
                    f"Reply 'Yes, I confirm withdrawal' to proceed."
                )
            elif result.get("success"):
                text = (
                    f"Your application {result.get('application_no')} has been successfully withdrawn. "
                    f"You are now free to submit a fresh application on the portal."
                )
            else:
                text = result.get("message", "Unable to withdraw application.")
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 5. Application Timeline / History
        if any(w in msg for w in ["timeline", "history", "what happened", "events", "progress"]):
            tool_name = "get_application_timeline"
            result = await self.call_mcp_tool(tool_name, {})
            events = result.get("events", [])
            if events:
                desc = "\n".join([f"- {e['timestamp']}: {e['description']}" for e in events])
                text = f"Here is the history of your application:\n{desc}"
            else:
                text = "No history found for your application."
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 6. Profile / Personal Info
        if any(w in msg for w in ["my profile", "my details", "who am i", "my name", "bank account"]):
            tool_name = "get_my_profile"
            result = await self.call_mcp_tool(tool_name, {})
            p = result.get("profile")
            if p:
                text = (
                    f"Respected {p['applicant_name']},\n"
                    f"Village: {p['village']}, Block: {p['block']}\n"
                    f"Bank Account: {p['bank_account_masked']} (IFSC: {p['ifsc']})\n"
                    f"Latest status: {p['latest_application_status']}"
                )
            else:
                text = result.get("message", "No profile found.")
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # 7. Connected Applications
        if any(w in msg for w in ["connected", "apps", "authorized", "sessions"]):
            tool_name = "get_my_connected_applications"
            result = await self.call_mcp_tool(tool_name, {})
            count = result.get("connected_applications_count", 0)
            text = f"You have {count} third-party application(s) connected to your Sewa Setu account."
            return {"response": text, "tool_called": tool_name, "tool_result": result}

        # Default: Check Status / Application
        tool_name = "check_application_status"
        result = await self.call_mcp_tool(tool_name, {})
        summary = result.get("summary") or result.get("message") or "Your application status is available."
        text = f"Namaste! {summary}"
        return {"response": text, "tool_called": tool_name, "tool_result": result}
