"""
LI.FI Intents MCP Client
Handles session management, rate limiting, connection pooling, and caching.
Supports both sync and async interfaces with parallel call capability.
"""

import asyncio
import httpx
import json
import os
import time
import logging
import threading
from typing import Optional, Any

logger = logging.getLogger(__name__)

MCP_URL = os.environ.get("LIFI_MCP_URL", "http://localhost:3333/mcp")
SOLVER_API_KEY = os.environ.get("SOLVER_API_KEY")

def _is_mock_forced() -> bool:
    """Check if mock mode is forced via env var. Supports both LIFI_AGENT_MOCK_MODE and deprecated LIFI_AGENT_DEMO_MODE."""
    if os.environ.get("LIFI_AGENT_DEMO_MODE") == "1":
        logger.warning("LIFI_AGENT_DEMO_MODE is deprecated, use LIFI_AGENT_MOCK_MODE instead")
        return True
    return os.environ.get("LIFI_AGENT_MOCK_MODE") == "1"
CACHE_TTL = 300  # 5 min cache
MAX_CACHE_SIZE = 200  # Max cache entries
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
        # Check mock-forced ONCE at init — never call _is_mock_forced() again
        self._mock_mode = _is_mock_forced()
        self._mock_fallback = False  # True when auto-fallback triggered
        # Rate limiting — separate timestamps for sync/async to avoid cross-contamination
        self._last_call_time_sync = 0.0
        self._last_call_time_async = 0.0
        self._rate_lock = asyncio.Lock()
        self._rate_lock_sync = threading.Lock()

    def _cleanup_cache(self):
        """Remove expired cache entries and enforce max size."""
        now = time.time()
        expired = [k for k, (ts, _) in self._cache.items() if now - ts >= CACHE_TTL]
        for k in expired:
            del self._cache[k]
        # Enforce max cache size (keep most recent)
        if len(self._cache) > MAX_CACHE_SIZE:
            sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k][0])
            for k in sorted_keys[:len(self._cache) - MAX_CACHE_SIZE]:
                del self._cache[k]

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
            elapsed = now - self._last_call_time_sync
            if elapsed < MIN_CALL_INTERVAL:
                time.sleep(MIN_CALL_INTERVAL - elapsed)
            self._last_call_time_sync = time.monotonic()

    async def _rate_limit_async(self):
        """Enforce minimum interval between calls (async)."""
        async with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_call_time_async
            if elapsed < MIN_CALL_INTERVAL:
                await asyncio.sleep(MIN_CALL_INTERVAL - elapsed)
            self._last_call_time_async = time.monotonic()

    def _headers(self, session_id: str = None) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        sid = session_id or self.session_id
        if sid:
            h["mcp-session-id"] = sid
        if SOLVER_API_KEY:
            h["x-api-key"] = SOLVER_API_KEY
        return h

    @staticmethod
    def _parse_sse(text: str) -> dict:
        """Parse SSE response text and extract tool result from the last valid data line."""
        last_result = None
        for line in text.split('\n'):
            s = line.strip()
            if s.startswith('data:'):
                js = s[5:].strip()
                if js:
                    try:
                        d = json.loads(js)
                    except json.JSONDecodeError:
                        continue
                    for c in d.get("result", {}).get("content", []):
                        if c.get("type") == "text":
                            try:
                                last_result = json.loads(c["text"])
                            except json.JSONDecodeError:
                                last_result = {"raw": c["text"]}
        if last_result is not None:
            return last_result
        return {"error": "No data in response"}

    @staticmethod
    def _parse_server_info(text: str) -> dict:
        """Parse server info from initialize SSE response."""
        for line in text.split('\n'):
            if line.strip().startswith('data:'):
                js = line.strip()[5:].strip()
                if js:
                    try:
                        d = json.loads(js)
                    except json.JSONDecodeError:
                        continue
                    return d.get("result", {})
        return {}

    def _init_session_sync(self) -> str:
        """Initialize a new MCP session (sync). Returns session ID."""
        if self._mock_mode:
            self._connected = True
            return "demo-session"
        try:
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
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if self.is_strict_mode():
                raise
            logger.warning("Local MCP not available at %s, falling back to mock mode", self.url)
            self._mock_mode = True
            self._mock_fallback = True
            self._connected = True
            return "demo-session"

    async def _init_session_async(self) -> str:
        """Initialize a new MCP session (async). Returns session ID."""
        if self._mock_mode:
            self._connected = True
            return "demo-session"
        try:
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
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if self.is_strict_mode():
                raise
            logger.warning("Local MCP not available at %s, falling back to mock mode", self.url)
            self._mock_mode = True
            self._mock_fallback = True
            self._connected = True
            return "demo-session"

    def connect(self) -> dict:
        """Initialize MCP session (sync). Returns server info."""
        if self.is_strict_mode() and self._mock_mode:
            raise RuntimeError("LIFI_AGENT_STRICT_MODE=1 conflicts with LIFI_AGENT_MOCK_MODE=1")
        if self._mock_mode:
            self._connected = True
            return {'serverInfo': {'name': 'lifi-intents-demo', 'version': '1.0.0'}}
        try:
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
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if self.is_strict_mode():
                raise
            logger.warning("Local MCP not available at %s, falling back to mock mode", self.url)
            self._mock_mode = True
            self._mock_fallback = True
            self._connected = True
            return {'serverInfo': {'name': 'lifi-intents-demo', 'version': '1.0.0'}}

    async def connect_async(self) -> dict:
        """Initialize MCP session (async). Returns server info."""
        if self.is_strict_mode() and self._mock_mode:
            raise RuntimeError("LIFI_AGENT_STRICT_MODE=1 conflicts with LIFI_AGENT_MOCK_MODE=1")
        if self._mock_mode:
            self._connected = True
            return {'serverInfo': {'name': 'lifi-intents-demo', 'version': '1.0.0'}}
        try:
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
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if self.is_strict_mode():
                raise
            logger.warning("Local MCP not available at %s, falling back to mock mode", self.url)
            self._mock_mode = True
            self._mock_fallback = True
            self._connected = True
            return {'serverInfo': {'name': 'lifi-intents-demo', 'version': '1.0.0'}}

    def _demo_call(self, tool: str, args: dict = None) -> dict:
        """Return mock data for mock mode. Set LIFI_AGENT_MOCK_MODE=1 to activate."""
        args = args or {}

        if tool == "get-supported-routes":
            return [
                {"fromChainId": 8453, "toChainId": 42161, "fromChain": "Base", "toChain": "Arbitrum",
                 "fromToken": {"symbol": "USDC", "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
                 "toToken": {"symbol": "USDC", "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"},
                 "isActive": True},
                {"fromChainId": 1, "toChainId": 8453, "fromChain": "Ethereum", "toChain": "Base",
                 "fromToken": {"symbol": "USDC", "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"},
                 "toToken": {"symbol": "USDC", "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
                 "isActive": True},
                {"fromChainId": 1, "toChainId": 42161, "fromChain": "Ethereum", "toChain": "Arbitrum",
                 "fromToken": {"symbol": "USDC", "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"},
                 "toToken": {"symbol": "USDC", "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"},
                 "isActive": True},
            ]

        if tool == "check-route-health":
            # Always return healthy in demo mode (real API would require a solver API key)
            return {"data": {"routeSupported": True, "matchingRoutes": 6, "quoteCount": 2, "quotes": [], "recentOrders": [{"catalystOrderId": "demo-order", "status": "Settled"}]}, "message": "Route looks healthy — supported, quotes active, and recent orders present."}

        if tool == "request-quote":
            # Simulate ~0.2% fee with new human-readable format
            amount_str = args.get("amount", "10")
            try:
                amount_float = float(amount_str)
                out = amount_float * 0.998
                out_str = f"{out:.6f}"
            except (ValueError, TypeError):
                out_str = "9.980000"
            from_token = args.get("fromToken", "USDC")
            to_token = args.get("toToken", "USDC")
            return {"data": {"quotes": [
                {"inputAmount": f"{amount_str} {from_token}", "outputAmount": f"{out_str} {to_token}",
                 "quoteId": "demo-quote-001", "validUntil": 9999999999, "partialFill": False}
            ], "cacheKey": "demo-cache-key"}}

        if tool == "get-solver-identities":
            return {"data": {"solverIdentities": [
                {"id": "solver-1", "name": "Demo Solver A"},
                {"id": "solver-2", "name": "Demo Solver B"},
            ]}}

        if tool == "get-quote-inventory":
            return {"data": {"quotes": [{"solver": "demo-solver", "inputAmount": "10 USDC", "outputAmount": "9.98 USDC"}]}}

        if tool == "prepare-order":
            return {"data": {"orderId": "demo-order-001", "status": "pending"}}

        if tool == "track-order":
            return {"data": {"id": args.get("orderId", "demo-order-001"), "status": "completed"}}

        if tool == "list-orders":
            return {"data": {"orders": [{"id": "demo-order-001", "status": "completed", "createdAt": "2026-05-22T10:00:00Z"}]}}

        return {"data": {"message": f"Demo mode: no mock for {tool}"}}

    def call(self, tool: str, args: dict = None, use_cache: bool = True, retries: int = 2) -> dict:
        """Call an MCP tool (sync) with rate limiting, connection pooling, caching, and retry."""
        # Strict mode: never allow mock fallback
        if self.is_strict_mode() and self._mock_mode:
            raise RuntimeError("LIFI_AGENT_STRICT_MODE=1: refusing to use mock mode in call()")
        # Mock mode: return mock data without hitting real MCP
        if self._mock_mode:
            return self._demo_call(tool, args)

        self._cleanup_cache()
        cache_key = f"{tool}:{json.dumps(args or {}, sort_keys=True)}"

        if use_cache and cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time.time() - ts < CACHE_TTL:
                return data

        last_error = None
        for attempt in range(retries + 1):
            self._rate_limit_sync()
            try:
                # Only re-init session if we don't have one yet
                if self.session_id is None:
                    self._init_session_sync()

                r = self.client.post(self.url,
                    json={"jsonrpc": "2.0", "id": 2,
                           "method": "tools/call",
                           "params": {"name": tool, "arguments": args or {}}},
                    headers=self._headers(),
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
                        self.session_id = None  # Force re-init on next attempt
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
        # Strict mode: never allow mock fallback
        if self.is_strict_mode() and self._mock_mode:
            raise RuntimeError("LIFI_AGENT_STRICT_MODE=1: refusing to use mock mode in call_async()")
        # Mock mode: return mock data without hitting real MCP
        if self._mock_mode:
            return self._demo_call(tool, args)

        self._cleanup_cache()
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
                # Only re-init session if we don't have one yet
                if self.session_id is None:
                    await self._init_session_async()

                r = await ac.post(self.url,
                    json={"jsonrpc": "2.0", "id": 2,
                           "method": "tools/call",
                           "params": {"name": tool, "arguments": args or {}}},
                    headers=self._headers(),
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
                        self.session_id = None  # Force re-init on next attempt
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

    def is_mock_mode(self) -> bool:
        """Check if client is running in mock/fallback mode."""
        return self._mock_mode

    @staticmethod
    def is_strict_mode() -> bool:
        """Check if strict mode is enabled (never fall back to mock)."""
        return os.environ.get("LIFI_AGENT_STRICT_MODE") == "1"

    @property
    def mode(self) -> str:
        """Return the current operating mode as a clear string.
        
        Modes:
        - "mock_forced": LIFI_AGENT_MOCK_MODE=1 (or deprecated LIFI_AGENT_DEMO_MODE=1)
        - "strict": LIFI_AGENT_STRICT_MODE=1 (real MCP only, no fallback)
        - "mock_fallback": local MCP was unreachable, auto-fell back to mock
        - "local_mcp": connected to real local MCP server
        """
        if self._mock_mode and self._mock_fallback:
            return "mock_fallback"
        if self._mock_mode:
            return "mock_forced"
        if self.is_strict_mode():
            return "strict"
        return "local_mcp"

    def mock_mode_source(self) -> str:
        """Return why mock mode is active, or empty string if not in mock mode."""
        if not self._mock_mode:
            return ""
        if os.environ.get("LIFI_AGENT_DEMO_MODE") == "1":
            return "LIFI_AGENT_DEMO_MODE=1 (deprecated)"
        if os.environ.get("LIFI_AGENT_MOCK_MODE") == "1":
            return "LIFI_AGENT_MOCK_MODE=1"
        if self._mock_fallback:
            return "auto-fallback (local MCP unreachable)"
        return "unknown"

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
