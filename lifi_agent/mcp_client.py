"""
LI.FI Intents MCP Client
Handles session management, rate limiting, connection pooling, and caching.
Supports both sync and async interfaces with parallel call capability.
"""

import asyncio
import httpx
import json
import time
import logging
import threading
from typing import Optional, Any

logger = logging.getLogger(__name__)

MCP_URL = "https://intents-mcp.li.fi/mcp"
CACHE_TTL = 300  # 5 min cache
MIN_CALL_INTERVAL = 1.0  # Rate limit: min 1s between calls


class MCPClient:
    """Persistent MCP client with async support, rate limiting, connection pooling, and caching."""

    def __init__(self, url: str = MCP_URL, timeout: int = 30):
        self.url = url
        self.timeout = timeout
        self.session_id: Optional[str] = None
        # Connection pooling: lazy-init reusable clients
        self._sync_client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._connected = False
        # Rate limiting
        self._last_call_time = 0.0
        self._rate_lock = asyncio.Lock()
        self._rate_lock_sync = threading.Lock()

    @property
    def client(self) -> httpx.Client:
        """Lazy-init sync client with connection pooling."""
        if self._sync_client is None:
            self._sync_client = httpx.Client(timeout=self.timeout)
        return self._sync_client

    async def _get_async_client(self) -> httpx.AsyncClient:
        """Lazy-init async client with connection pooling."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client

    def _rate_limit_sync(self):
        """Enforce minimum interval between calls (sync)."""
        with self._rate_lock_sync:
            now = time.monotonic()
            elapsed = now - self._last_call_time
            if elapsed < MIN_CALL_INTERVAL:
                time.sleep(MIN_CALL_INTERVAL - elapsed)
            self._last_call_time = time.monotonic()

    async def _rate_limit_async(self):
        """Enforce minimum interval between calls (async)."""
        async with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_call_time
            if elapsed < MIN_CALL_INTERVAL:
                await asyncio.sleep(MIN_CALL_INTERVAL - elapsed)
            self._last_call_time = time.monotonic()

    def _headers(self, session_id: str = None) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        sid = session_id or self.session_id
        if sid:
            h["mcp-session-id"] = sid
        return h

    @staticmethod
    def _parse_sse(text: str) -> dict:
        """Parse SSE response text and extract tool result."""
        for line in text.split('\n'):
            s = line.strip()
            if s.startswith('data:'):
                js = s[5:].strip()
                if js:
                    d = json.loads(js)
                    for c in d.get("result", {}).get("content", []):
                        if c.get("type") == "text":
                            try:
                                return json.loads(c["text"])
                            except json.JSONDecodeError:
                                return {"raw": c["text"]}
        return {"error": "No data in response"}

    @staticmethod
    def _parse_server_info(text: str) -> dict:
        """Parse server info from initialize SSE response."""
        for line in text.split('\n'):
            if line.strip().startswith('data:'):
                js = line.strip()[5:].strip()
                if js:
                    d = json.loads(js)
                    return d.get("result", {})
        return {}

    def _init_session_sync(self) -> str:
        """Initialize a new MCP session (sync). Returns session ID."""
        r = self.client.post(self.url,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "lifi-agent", "version": "1.0"}}},
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            timeout=self.timeout)
        sid = r.headers.get("mcp-session-id")

        self.client.post(self.url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers=self._headers(sid),
            timeout=self.timeout)

        self.session_id = sid
        self._connected = True
        return sid

    async def _init_session_async(self) -> str:
        """Initialize a new MCP session (async). Returns session ID."""
        ac = await self._get_async_client()
        r = await ac.post(self.url,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "lifi-agent", "version": "1.0"}}},
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            timeout=self.timeout)
        sid = r.headers.get("mcp-session-id")

        await ac.post(self.url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers=self._headers(sid),
            timeout=self.timeout)

        self.session_id = sid
        self._connected = True
        return sid

    def connect(self) -> dict:
        """Initialize MCP session (sync). Returns server info."""
        r = self.client.post(self.url,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "lifi-agent", "version": "1.0"}}},
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            timeout=self.timeout)
        self.session_id = r.headers.get("mcp-session-id")
        self._connected = True

        self.client.post(self.url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers=self._headers(),
            timeout=self.timeout)

        return self._parse_server_info(r.text)

    async def connect_async(self) -> dict:
        """Initialize MCP session (async). Returns server info."""
        ac = await self._get_async_client()
        r = await ac.post(self.url,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "lifi-agent", "version": "1.0"}}},
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            timeout=self.timeout)
        self.session_id = r.headers.get("mcp-session-id")
        self._connected = True

        await ac.post(self.url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers=self._headers(),
            timeout=self.timeout)

        return self._parse_server_info(r.text)

    def call(self, tool: str, args: dict = None, use_cache: bool = True, retries: int = 2) -> dict:
        """Call an MCP tool (sync) with rate limiting, connection pooling, caching, and retry."""
        cache_key = f"{tool}:{json.dumps(args or {}, sort_keys=True)}"

        if use_cache and cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time.time() - ts < CACHE_TTL:
                return data

        last_error = None
        for attempt in range(retries + 1):
            self._rate_limit_sync()
            try:
                sid = self._init_session_sync()

                r = self.client.post(self.url,
                    json={"jsonrpc": "2.0", "id": 2,
                           "method": "tools/call",
                           "params": {"name": tool, "arguments": args or {}}},
                    headers=self._headers(sid),
                    timeout=self.timeout)
            except Exception as e:
                last_error = {"error": str(e)}
                if attempt < retries:
                    delay = 2 ** (attempt + 1)
                    logger.warning("Retry %d/%d for %s after error: %s (waiting %ds)", attempt + 1, retries, tool, e, delay)
                    time.sleep(delay)
                continue

            if r.status_code == 400:
                try:
                    err_msg = r.json().get("error", {}).get("message", "")
                    last_error = {"error": err_msg}
                    if "No valid session" in err_msg and attempt < retries:
                        delay = 2 ** (attempt + 1)
                        logger.warning("Retry %d/%d for %s: session expired (waiting %ds)", attempt + 1, retries, tool, delay)
                        time.sleep(delay)
                        continue
                except Exception:
                    pass
                return {"error": "HTTP 400", "body": r.text[:500]}

            if r.status_code != 200:
                return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}

            data = self._parse_sse(r.text)
            if "error" not in data:
                self._cache[cache_key] = (time.time(), data)
            return data

        return last_error or {"error": "Max retries exceeded"}

    async def call_async(self, tool: str, args: dict = None, use_cache: bool = True, retries: int = 2) -> dict:
        """Call an MCP tool (async) with rate limiting, connection pooling, caching, and retry.
        Supports parallel calls via asyncio.gather()."""
        cache_key = f"{tool}:{json.dumps(args or {}, sort_keys=True)}"

        if use_cache and cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time.time() - ts < CACHE_TTL:
                return data

        ac = await self._get_async_client()
        last_error = None
        for attempt in range(retries + 1):
            await self._rate_limit_async()
            try:
                sid = await self._init_session_async()

                r = await ac.post(self.url,
                    json={"jsonrpc": "2.0", "id": 2,
                           "method": "tools/call",
                           "params": {"name": tool, "arguments": args or {}}},
                    headers=self._headers(sid),
                    timeout=self.timeout)
            except Exception as e:
                last_error = {"error": str(e)}
                if attempt < retries:
                    delay = 2 ** (attempt + 1)
                    logger.warning("Retry %d/%d for %s after error: %s (waiting %ds)", attempt + 1, retries, tool, e, delay)
                    await asyncio.sleep(delay)
                continue

            if r.status_code == 400:
                try:
                    err_msg = r.json().get("error", {}).get("message", "")
                    last_error = {"error": err_msg}
                    if "No valid session" in err_msg and attempt < retries:
                        delay = 2 ** (attempt + 1)
                        logger.warning("Retry %d/%d for %s: session expired (waiting %ds)", attempt + 1, retries, tool, delay)
                        await asyncio.sleep(delay)
                        continue
                except Exception:
                    pass
                return {"error": "HTTP 400", "body": r.text[:500]}

            if r.status_code != 200:
                return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}

            data = self._parse_sse(r.text)
            if "error" not in data:
                self._cache[cache_key] = (time.time(), data)
            return data

        return last_error or {"error": "Max retries exceeded"}

    def warmup(self):
        """Prime the session cache by calling get-supported-routes once."""
        self.call("get-supported-routes", {})

    def close(self):
        """Close sync client."""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
        self._connected = False

    async def close_async(self):
        """Close both sync and async clients."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
        self._connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    async def __aenter__(self):
        await self.connect_async()
        return self

    async def __aexit__(self, *args):
        await self.close_async()
