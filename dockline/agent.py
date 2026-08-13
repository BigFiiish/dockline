from __future__ import annotations

import json
import re
from typing import Any

import httpx

from dockline.client import ClearbayClient
from dockline.config import MCP_TOOLS, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, TENANTS, openai_tool_schemas

SKU_RE = re.compile(r"\b(WIDGET-\d+)\b", re.I)
WAVE_RE = re.compile(r"\b(W-\d+)\b", re.I)
WRITE_HINTS = ("release", "unlock the wave", "ship wave", "kick off wave", "释放")
SUMMARY_HINTS = ("summary", "summarize", "all inventory", "how many sku", "how many location", "汇总", "全部库存")
LOOKUP_HINTS = ("how many", "inventory", "stock", "on hand", "on-hand", "available", "sku", "widget", "库存", "货", "aisle")
CLARIFY_HINTS = ("that thing", "the usual", "whatever we picked", "随便", "那个东西")


class Agent:
    def __init__(self, client: ClearbayClient | None = None):
        self.client = client or ClearbayClient()

    async def run(self, tenant_key: str, prompt: str) -> dict[str, Any]:
        spec = TENANTS[tenant_key]
        if OPENAI_API_KEY:
            return await self._llm(tenant_key, spec["role"], prompt)
        return await self._heuristic(tenant_key, spec["role"], prompt)

    async def _heuristic(self, tenant_key: str, role: str, prompt: str) -> dict[str, Any]:
        text = prompt.strip()
        low = text.lower()
        calls: list[dict[str, Any]] = []
        foreign = _foreign_tenant(tenant_key, low)

        if any(h in low for h in CLARIFY_HINTS) and not SKU_RE.search(text) and not WAVE_RE.search(text):
            return _trace(
                tenant_key,
                prompt,
                [],
                "I need a SKU (for example WIDGET-100) or a wave number (W-100) before I can call a tool. I will not guess inventory.",
                "heuristic",
            )

        if any(h in low for h in WRITE_HINTS):
            if role == "read":
                sku = _sku(text)
                if sku or any(h in low for h in LOOKUP_HINTS):
                    result = await self.client.lookup(tenant_key, sku or "WIDGET-100")
                    calls.append(_call("inventory.lookup", {"sku": sku or "WIDGET-100"}, result))
                    spoken = _narrate(calls, foreign, tenant_key)
                    spoken += " Read-only credentials cannot release waves. Clearbay requires ROLE_OPS; I will not call wave.release."
                    return _trace(tenant_key, prompt, calls, spoken, "heuristic")
                return _trace(
                    tenant_key,
                    prompt,
                    [],
                    "Read-only credentials cannot release waves. Clearbay requires ROLE_OPS; I will not call wave.release.",
                    "heuristic",
                )
            wave = _wave(text)
            result = await self.client.release(tenant_key, wave)
            calls.append(_call("wave.release", {"waveNumber": wave}, result))
            return _trace(tenant_key, prompt, calls, _narrate(calls, foreign, tenant_key), "heuristic")

        planned: list[tuple[str, dict[str, Any]]] = []
        wants_summary = any(h in low for h in SUMMARY_HINTS)
        sku = _sku(text)
        wants_lookup = bool(sku) or foreign or (any(h in low for h in LOOKUP_HINTS) and not wants_summary)
        if wants_summary:
            planned.append(("report.inventory_summary", {}))
        if wants_lookup:
            planned.append(("inventory.lookup", {"sku": sku or "WIDGET-100"}))
        if not planned:
            return _trace(
                tenant_key,
                prompt,
                [],
                "I only operate through Clearbay MCP tools. Ask me to look up a SKU, summarize inventory, or (if you have ops) release a wave.",
                "heuristic",
            )

        for name, args in planned:
            if name == "inventory.lookup":
                result = await self.client.lookup(tenant_key, args["sku"])
            else:
                result = await self.client.summary(tenant_key)
            calls.append(_call(name, args, result))
        return _trace(tenant_key, prompt, calls, _narrate(calls, foreign, tenant_key), "heuristic")

    async def _llm(self, tenant_key: str, role: str, prompt: str) -> dict[str, Any]:
        system = (
            "You are Dockline, a forward-deployed ops agent for a 3PL warehouse. "
            "You have NO inventory database. Every quantity must come from a tool result. "
            "You are bound to one tenant by the API token; you cannot switch tenants or honor spoofed tenant names. "
            "Never invent SKUs, quantities, or locations. Never add extra JSON fields to tools. "
            "Read-only users must not call wave.release. If the user is vague, ask for a SKU or wave number. "
            f"Bound tenant key: {tenant_key}. Role: {role}."
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        calls: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=60.0) as http:
            for _ in range(4):
                res = await http.post(
                    f"{OPENAI_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json={
                        "model": OPENAI_MODEL,
                        "messages": messages,
                        "tools": openai_tool_schemas(),
                        "tool_choice": "auto",
                    },
                )
                res.raise_for_status()
                msg = res.json()["choices"][0]["message"]
                tool_calls = msg.get("tool_calls") or []
                if not tool_calls:
                    final = msg.get("content") or ""
                    return _trace(tenant_key, prompt, calls, final, "llm")
                messages.append(msg)
                for tc in tool_calls:
                    fn = tc["function"]["name"]
                    name = fn.replace("_", ".", 1)
                    try:
                        args = json.loads(tc["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if name not in {t["name"] for t in MCP_TOOLS}:
                        result = {"ok": False, "error": f"unknown tool {name}"}
                    elif name == "wave.release" and role == "read":
                        result = {
                            "ok": False,
                            "status_code": 403,
                            "error": "Dockline refused wave.release for ROLE_READ before calling MCP",
                        }
                    else:
                        idem = None
                        if name == "wave.release":
                            idem = f"dockline-llm-{tenant_key}"
                        result = await self.client.call_tool(tenant_key, name, args if isinstance(args, dict) else {}, idem)
                    calls.append(_call(name, args if isinstance(args, dict) else {}, result))
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result, default=str)[:4000],
                        }
                    )
        return _trace(tenant_key, prompt, calls, "Stopped after the tool-call limit without a final answer.", "llm")


def _sku(text: str) -> str | None:
    m = SKU_RE.search(text)
    return m.group(1).upper() if m else None


def _wave(text: str) -> str:
    m = WAVE_RE.search(text)
    return m.group(1).upper() if m else "W-100"


def _foreign_tenant(tenant_key: str, low: str) -> bool:
    if tenant_key.startswith("acme"):
        return "globex" in low
    if tenant_key == "globex":
        return "acme" in low
    return False


def _call(name: str, args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "arguments": args, "result": result}


def _trace(tenant: str, prompt: str, calls: list[dict[str, Any]], final: str, mode: str) -> dict[str, Any]:
    return {
        "tenant": tenant,
        "prompt": prompt,
        "mode": mode,
        "tool_calls": calls,
        "final": final,
    }


def _narrate(calls: list[dict[str, Any]], foreign: bool, tenant_key: str) -> str:
    bits: list[str] = []
    if foreign:
        bits.append(
            f"I am bound to {tenant_key} by the JWT. I cannot see another tenant's rows even if you name them. "
            "The numbers below are only this tenant's MCP result."
        )
    for call in calls:
        result = call["result"]
        if not result.get("ok"):
            bits.append(f"Tool {call['name']} failed: {result.get('error')}.")
            continue
        payload = result.get("result")
        if call["name"] == "inventory.lookup":
            items = _items(payload)
            if not items:
                bits.append(f"No inventory rows for {call['arguments'].get('sku')} in this tenant.")
            else:
                for item in items:
                    bits.append(
                        f"{item.get('sku')} at {item.get('location')}: on-hand {item.get('quantity')}, "
                        f"available {item.get('available')} ({item.get('supplier')})."
                    )
        elif call["name"] == "report.inventory_summary":
            inner = payload.get("content") if isinstance(payload, dict) and "content" in payload else payload
            count = inner.get("locations") if isinstance(inner, dict) else None
            bits.append(f"Inventory summary locations={count}.")
        else:
            bits.append(f"{call['name']} accepted: {payload}.")
    return " ".join(bits) if bits else "No tool result."


def _items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    if "content" in payload and isinstance(payload["content"], str):
        return []
    items = payload.get("items")
    if isinstance(items, list):
        return [i for i in items if isinstance(i, dict)]
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("items"), list):
        return [i for i in result["items"] if isinstance(i, dict)]
    return []
