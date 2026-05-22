"""
LI.FI Intents MCP Client
Handles session management, rate limiting, and fallback to cache.
"""

import httpx
import json
import time
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

MCP_URL = "https://intents-mcp.li.fi/mcp"
CACHE_TTL = 300  # 5 min cache


class MCPClient:
    """Persistent MCP client with auto-reconnect and caching."""

    def __init__(self, url: str = MCP_URL, timeout: int = 30):
        self.url = url
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self.client = httpx.Client(timeout=timeout)
        self._cache: dict[str, tuple[float, Any]] = {}
        self._call_id = 0
        self._connected = False

    def connect(self) -> dict:
        """Initialize MCP session."""
        self._call_id = 0
        r = self.client.post(self.url,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "lifi-agent", "version": "1.0"}}},
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
        self.session_id = r.headers.get("mcp-session-id")
        self._call_id = 1
        self._connected = True

        # Send initialized notification
        self.client.post(self.url,
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            headers=self._headers())

        # Parse server info
        for line in r.text.split('\n'):
            if line.strip().startswith('data:'):
                js = line.strip()[5:].strip()
                if js:
                    d = json.loads(js)
                    return d.get("result", {})
        return {}

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session_id:
            h["mcp-session-id"] = self.session_id
        return h

    def call(self, tool: str, args: dict = None, use_cache: bool = True, retries: int = 2) -> dict:
        """Call an MCP tool with per-call session, caching, and retry."""
        cache_key = f"{tool}:{json.dumps(args or {}, sort_keys=True)}"

        # Check cache
        if use_cache and cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time.time() - ts < CACHE_TTL:
                return data

        last_error = None
        for attempt in range(retries + 1):
            # Fresh session per call to avoid rate limit
            self._call_id = 0
            try:
                # Initialize
                r = self.client.post(self.url,
                    json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "lifi-agent", "version": "1.0"}}},
                    headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                    timeout=self.timeout)
                sid = r.headers.get("mcp-session-id")
                self._call_id = 1

                # Send initialized notification
                self.client.post(self.url,
                    json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                    headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "mcp-session-id": sid})

                # Make tool call
                self._call_id += 1
                r = self.client.post(self.url,
                    json={"jsonrpc": "2.0", "id": self._call_id,
                           "method": "tools/call",
                           "params": {"name": tool, "arguments": args or {}}},
                    headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "mcp-session-id": sid},
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
                return {"error": f"HTTP 400", "body": r.text[:500]}

            if r.status_code != 200:
                return {"error": f"HTTP {r.status_code}", "body": r.text[:500]}

            # Parse SSE response
            for line in r.text.split('\n'):
                s = line.strip()
                if s.startswith('data:'):
                    js = s[5:].strip()
                    if js:
                        d = json.loads(js)
                        for c in d.get("result", {}).get("content", []):
                            if c.get("type") == "text":
                                try:
                                    data = json.loads(c["text"])
                                    self._cache[cache_key] = (time.time(), data)
                                    return data
                                except json.JSONDecodeError:
                                    return {"raw": c["text"]}
            return {"error": "No data in response"}

        return last_error or {"error": "Max retries exceeded"}

    def warmup(self):
        """Prime the session cache by calling get-supported-routes once."""
        self.call("get-supported-routes", {})

    def close(self):
        self.client.close()
        self._connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()
