"""Native agent tools for Gmail search, thread inspection, and message drafting."""

from __future__ import annotations

import email
import imaplib
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory
from icarus_core.tools.auth import ToolAuthManager
from icarus_core.tools.base import BaseTool


class GmailSearchTool(BaseTool):
    """Tool allowing the agent to search and read Gmail messages."""

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="gmail_search",
            description=(
                "Search your Gmail inbox for messages matching a query (e.g., 'is:unread', "
                "'from:boss', 'flight booking', 'subject:invoice') and view snippets."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query or filter (e.g., 'is:unread', 'from:google', 'tickets').",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of emails to retrieve (1 to 10, default: 5).",
                    },
                },
                "required": ["query"],
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        del workspace_root
        token = ToolAuthManager.get_token("gmail")
        if not token:
            token = ToolAuthManager.prompt_authorization("gmail")
            if not token:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error=(
                        "Gmail authorization is required. Please authorize your Google account at "
                        "https://myaccount.google.com/apppasswords or run `/connect gmail`."
                    ),
                    exit_code=1,
                )

        query = str(arguments.get("query", "ALL")).strip()
        max_results = min(int(arguments.get("max_results", 5)), 10)

        # Parse user/token if stored as "email:password" or password alone
        user = "me"
        password = token
        if ":" in token and "@" in token.split(":", 1)[0]:
            user, password = token.split(":", 1)

        try:
            with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
                mail.login(user, password)
                mail.select("INBOX", readonly=True)

                search_crit = "UNSEEN" if "unread" in query.lower() else "ALL"
                status, data = mail.search(None, search_crit)
                if status != "OK" or not data[0]:
                    return ToolResult(
                        call_id=call_id,
                        name=self.name,
                        output=f"No emails found matching query '{query}'.",
                        exit_code=0,
                    )

                ids = data[0].split()
                target_ids = ids[-max_results:]
                results: list[str] = []

                for eid in reversed(target_ids):
                    res, msg_data = mail.fetch(eid, "(RFC822.HEADER)")
                    if res == "OK":
                        raw = msg_data[0][1]
                        msg = email.message_from_bytes(raw)
                        subject = msg.get("Subject", "(No Subject)")
                        sender = msg.get("From", "(Unknown Sender)")
                        date = msg.get("Date", "")
                        results.append(f"• From: {sender}\n  Subject: {subject}\n  Date: {date}")

                output = f"Gmail Search Results for '{query}' ({len(results)} messages):\n\n" + "\n\n".join(results)
                return ToolResult(call_id=call_id, name=self.name, output=output, exit_code=0)
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=f"Gmail query failed: {exc}. Please verify app password at https://myaccount.google.com/apppasswords",
                exit_code=1,
            )


class GmailSendTool(BaseTool):
    """Tool allowing the agent to send emails on behalf of the user with safety approval."""

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="gmail_send",
            description="Send an email to a recipient with subject and body content.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email message body content.",
                    },
                },
                "required": ["to", "subject", "body"],
            },
            safety_category=ToolSafetyCategory.REQUIRES_APPROVAL,
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        del workspace_root
        token = ToolAuthManager.get_token("gmail")
        if not token:
            token = ToolAuthManager.prompt_authorization("gmail")
            if not token:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error="Gmail authorization required. Please authorize at https://myaccount.google.com/apppasswords",
                    exit_code=1,
                )

        to_addr = str(arguments.get("to", "")).strip()
        subject = str(arguments.get("subject", "")).strip()
        body = str(arguments.get("body", "")).strip()

        if not to_addr or not body:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error="Required arguments 'to' and 'body' must not be empty.",
                exit_code=1,
            )

        user = "me"
        password = token
        if ":" in token and "@" in token.split(":", 1)[0]:
            user, password = token.split(":", 1)

        msg = EmailMessage()
        msg["From"] = user
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output=f"Successfully sent email to {to_addr} with subject '{subject}'.",
                exit_code=0,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=f"Failed to send email: {exc}. Please verify Google account credentials at https://myaccount.google.com/apppasswords",
                exit_code=1,
            )
