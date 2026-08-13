from __future__ import annotations

import uuid
from typing import Any

import httpx

from dockline.config import CLEARBAY_BASE_URL, TENANTS


class ClearbayError(RuntimeError):
    def __init__(self, message: str, status_code: int = 0, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ClearbayClient:
    def __init__(self, base_url: str | None = None, timeout: float = 45.0):
        self.base_url = (base_url or CLEARBAY_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._tokens: dict[str, str] = {}

    async def token(self, tenant_key: str) -> str:
        if tenant_key not in TENANTS:
            raise ClearbayError(f"unknown tenant {tenant_key}")
        if tenant_key in self._tokens:
            return self._tokens[tenant_key]
        spec = TENANTS[tenant_key]
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            res = await http.post(
                f"{self.base_url}/oauth/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": spec["client_id"],
                    "client_secret": spec["client_secret"],
                },
            )
        if res.status_code >= 400:
            raise ClearbayError("oauth failed", res.status_code, _body(res))
        token = res.json()["access_token"]
        self._tokens[tenant_key] = token
        return token

    async def me(self, tenant_key: str) -> dict[str, Any]:
        token = await self.token(tenant_key)
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            res = await http.get(
                f"{self.base_url}/api/v1/me",
                headers={"Authorization": f"Bearer {token}", "X-Tenant-Id": "22222222-2222-2222-2222-222222222222"},
            )
        if res.status_code >= 400:
            raise ClearbayError("me failed", res.status_code, _body(res))
        return res.json()

    async def call_tool(
        self,
        tenant_key: str,
        name: str,
        arguments: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        token = await self.token(tenant_key)
        params: dict[str, Any] = {"name": name, "arguments": arguments or {}}
        if idempotency_key:
            params["idempotencyKey"] = idempotency_key
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            res = await http.post(
                f"{self.base_url}/mcp",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params},
            )
        body = _body(res)
        if res.status_code == 403:
            return {"ok": False, "status_code": 403, "error": "ROLE_OPS required for writes", "body": body}
        if res.status_code >= 400:
            return {"ok": False, "status_code": res.status_code, "error": str(body), "body": body}
        if isinstance(body, dict) and body.get("error"):
            err = body["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            return {"ok": False, "status_code": res.status_code, "error": msg, "body": body}
        return {"ok": True, "status_code": res.status_code, "result": body.get("result") if isinstance(body, dict) else body}

    async def lookup(self, tenant_key: str, sku: str) -> dict[str, Any]:
        return await self.call_tool(tenant_key, "inventory.lookup", {"sku": sku})

    async def summary(self, tenant_key: str) -> dict[str, Any]:
        return await self.call_tool(tenant_key, "report.inventory_summary", {})

    async def release(self, tenant_key: str, wave_number: str = "W-100") -> dict[str, Any]:
        return await self.call_tool(
            tenant_key,
            "wave.release",
            {"waveNumber": wave_number},
            idempotency_key=f"dockline-{tenant_key}-{wave_number}-{uuid.uuid4().hex[:8]}",
        )


def _body(res: httpx.Response) -> Any:
    try:
        return res.json()
    except Exception:
        return res.text
