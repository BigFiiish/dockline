from __future__ import annotations

import os
from typing import Any

TENANTS: dict[str, dict[str, str]] = {
    "acme": {
        "client_id": "acme-ops",
        "client_secret": "acme-secret",
        "label": "Acme 3PL (ops)",
        "role": "ops",
    },
    "acme-read": {
        "client_id": "acme-read",
        "client_secret": "acme-read-secret",
        "label": "Acme 3PL (read-only)",
        "role": "read",
    },
    "globex": {
        "client_id": "globex-ops",
        "client_secret": "globex-secret",
        "label": "Globex Logistics (ops)",
        "role": "ops",
    },
}

CLEARBAY_BASE_URL = os.environ.get("CLEARBAY_BASE_URL", "https://clearbay.onrender.com").rstrip("/")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

MCP_TOOLS = (
    {
        "name": "inventory.lookup",
        "description": "Look up on-hand inventory for a SKU in the bound tenant only.",
        "parameters": {"sku": "string"},
        "required": ["sku"],
        "write": False,
    },
    {
        "name": "wave.release",
        "description": "Release a picking wave. Requires ROLE_OPS and an idempotency key.",
        "parameters": {"waveNumber": "string"},
        "required": ["waveNumber"],
        "write": True,
    },
    {
        "name": "report.inventory_summary",
        "description": "Tenant inventory counts. No arguments. additionalProperties false.",
        "parameters": {},
        "required": [],
        "write": False,
    },
)


def openai_tool_schemas() -> list[dict[str, Any]]:
    out = []
    for tool in MCP_TOOLS:
        props = {name: {"type": spec} for name, spec in tool["parameters"].items()}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"].replace(".", "_"),
                    "description": tool["description"],
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": tool["required"],
                        "additionalProperties": False,
                    },
                },
            }
        )
    return out


def mcp_name(function_name: str) -> str:
    return function_name.replace("_", ".", 1)
