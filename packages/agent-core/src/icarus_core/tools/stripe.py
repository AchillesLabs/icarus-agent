"""Native agent tool for Stripe payment link creation and payment verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory
from icarus_core.tools.auth import ToolAuthManager
from icarus_core.tools.base import BaseTool


class StripePaymentLinkTool(BaseTool):
    """Tool allowing the agent to generate checkout payment links via Stripe with user approval."""

    def __init__(self) -> None:
        self._definition = ToolDefinition(
            name="stripe_payment_link",
            description=(
                "Create a Stripe checkout payment link for a specified amount and currency "
                "to collect payment safely."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "Payment amount (e.g. 25.00 for $25.00 or 500 for ₹500).",
                    },
                    "currency": {
                        "type": "string",
                        "description": "Three-letter ISO currency code (e.g., 'usd', 'inr', 'eur', default: 'usd').",
                    },
                    "item_name": {
                        "type": "string",
                        "description": "Name / description of the item or service being paid for.",
                    },
                },
                "required": ["amount", "item_name"],
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
        token = ToolAuthManager.get_token("stripe")
        if not token:
            token = ToolAuthManager.prompt_authorization("stripe")
            if not token:
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error=(
                        "Stripe authorization required. Please authorize your Stripe account at "
                        "https://dashboard.stripe.com/apikeys or run `/connect stripe`."
                    ),
                    exit_code=1,
                )

        amount = float(arguments.get("amount", 0))
        currency = str(arguments.get("currency", "usd")).lower().strip()
        item_name = str(arguments.get("item_name", "Payment")).strip()

        # Stripe takes amounts in cents / lowest unit
        unit_amount = int(amount * 100)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # 1. Create price & product or payment link via Stripe REST API
        try:
            with httpx.Client(timeout=15.0) as client:
                price_resp = client.post(
                    "https://api.stripe.com/v1/prices",
                    headers=headers,
                    data={
                        "currency": currency,
                        "unit_amount": unit_amount,
                        "product_data[name]": item_name,
                    },
                )
                if price_resp.status_code == 200:
                    price_id = price_resp.json().get("id")
                    plink_resp = client.post(
                        "https://api.stripe.com/v1/payment_links",
                        headers=headers,
                        data={
                            "line_items[0][price]": price_id,
                            "line_items[0][quantity]": 1,
                        },
                    )
                    if plink_resp.status_code == 200:
                        url = plink_resp.json().get("url")
                        return ToolResult(
                            call_id=call_id,
                            name=self.name,
                            output=(
                                f"Stripe Payment Link Created Successfully:\n"
                                f"• Amount: {amount:.2f} {currency.upper()}\n"
                                f"• Item: {item_name}\n"
                                f"• Payment Link: {url}"
                            ),
                            exit_code=0,
                        )
                return ToolResult(
                    call_id=call_id,
                    name=self.name,
                    output="",
                    error=f"Stripe API error: {price_resp.text}",
                    exit_code=1,
                )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=f"Stripe request failed: {exc}. Please verify Stripe secret key.",
                exit_code=1,
            )
