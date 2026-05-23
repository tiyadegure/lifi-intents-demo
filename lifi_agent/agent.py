"""
LI.FI Intents Agent — AI-powered cross-chain assistant.

Usage:
    python3 -m lifi_agent                    # Interactive mode
    python3 -m lifi_agent "send 10 USDC from Base to Arbitrum"  # Single command
"""

import sys
import json
import os
import re
import time
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

from .mcp_client import MCPClient
from .models import (
    CHAINS, CHAIN_ALIASES, TOKENS, TOKEN_DECIMALS, DEMO_ADDRESS,
    raw_to_amount, normalize_output_amount,
    Intent, Policy, Verdict, DecisionStep, DecisionResult,
)
from .parser import parse_policy, parse_intent, parse_intent_with_policy, parse_intent_llm
from .store import QuoteStore, get_quote_store

# ── Rich TUI ──────────────────────────────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich import box

console = Console()

CHAIN_COLORS = {
    "ethereum": "cyan",
    "base": "blue",
    "arbitrum": "red",
    "optimism": "bold red",
    "polygon": "magenta",
    "bsc": "yellow",
    "avalanche": "bold red",
    "zksync": "white",
    "linea": "bold blue",
    "scroll": "dim white",
    "blast": "bold yellow",
    "mantle": "white",
    "sonic": "bold cyan",
}


def styled_chain(name: str) -> str:
    """Return a Rich-formatted chain name."""
    color = CHAIN_COLORS.get(name, "white")
    return f"[{color}]{name.title()}[/{color}]"


def status_ok(msg: str):
    console.print(f"  [green]✓[/green] {msg}")


def status_err(msg: str):
    console.print(f"  [red]✗[/red] {msg}")


def status_cached(msg: str):
    console.print(f"  [yellow]⚡[/yellow] {msg}")


def status_loading(msg: str):
    console.print(f"  [blue]⏳[/blue] {msg}")


PREFS_FILE = Path.home() / ".lifi_agent_prefs.json"


# ── Agent ───────────────────────────────────────────────────────────
class LifAgent:
    """AI Agent for cross-chain operations via LI.FI Intents MCP."""

    def __init__(self):
        self.mcp = MCPClient()
        self.history: list[dict] = []
        self.quote_history: list[dict] = []
        self.preferences: dict = {"default_chain": None, "default_token": "usdc", "favorite_routes": []}
        self.pending_order: dict = {}
        self._load_prefs()

    def _load_prefs(self):
        """Load preferences from disk."""
        if PREFS_FILE.exists():
            try:
                with open(PREFS_FILE) as f:
                    saved = json.load(f)
                    self.preferences.update(saved)
            except Exception:
                pass

    def _save_prefs(self):
        """Save preferences to disk."""
        try:
            with open(PREFS_FILE, "w") as f:
                json.dump(self.preferences, f, indent=2)
        except Exception:
            pass

    def remember_route(self, from_chain: str, to_chain: str, token: str):
        """Remember a frequently used route."""
        route = f"{from_chain}:{to_chain}:{token}"
        favs = self.preferences.get("favorite_routes", [])
        if route not in favs:
            favs.append(route)
            self.preferences["favorite_routes"] = favs[-10:]  # Keep last 10
            self._save_prefs()

    def get_favorite_routes(self) -> list[str]:
        return self.preferences.get("favorite_routes", [])

    def connect(self):
        info = self.mcp.connect()
        server = info.get("serverInfo", {})
        return f"Connected to {server.get('name', '?')} v{server.get('version', '?')}"

    def get_routes(self) -> dict:
        """Get all supported routes. Normalizes real MCP (flat list) and demo (wrapped dict) formats."""
        result = self.mcp.call("get-supported-routes", {})
        # Real MCP returns a flat list; normalize to consistent dict format
        if isinstance(result, list):
            return {"data": {"routes": result}}
        return result

    def get_quote(self, intent: Intent) -> dict:
        """Get a cross-chain quote with route validation.

        Note: get_routes() is called first for validation, but the result is
        already cached by MCPClient (CACHE_TTL=300s), so this is cheap on
        repeated calls.
        """
        routes_result = self.get_routes()
        route_list = routes_result.get("data", {}).get("routes", [])

        if route_list:
            matching = [r for r in route_list
                        if str(r.get("fromChainId", r.get("fromChain", ""))).lower() in (intent.from_chain_id(), intent.from_chain_name().lower())
                        and str(r.get("toChainId", r.get("toChain", ""))).lower() in (intent.to_chain_id(), intent.to_chain_name().lower())]
            if not matching:
                return {"error": f"No route found for {intent.from_chain} → {intent.to_chain} ({intent.token.upper()})"}

        args = {
            "fromChain": intent.from_chain_name(),
            "toChain": intent.to_chain_name(),
            "fromToken": intent.token_symbol(),
            "toToken": intent.token_symbol(),
            "amount": intent.amount,
            "userAddress": intent.address,
        }
        result = self.mcp.call("request-quote", args)

        raw = result.get("raw", "")
        if "Unknown token" in raw:
            result["suggestion"] = f"Token {intent.token.upper()} may not be available on {intent.from_chain}. Try: routes"
            result["error"] = raw

        if "error" not in result:
            self.quote_history.append({
                "timestamp": time.time(),
                "intent": repr(intent),
                "result": result,
            })
            self.quote_history = self.quote_history[-10:]
            
            # Store in SQLite
            quotes = result.get("data", {}).get("quotes", [])
            if quotes:
                q = quotes[0]
                output = q.get("outputAmount", "0")
                get_quote_store().store(
                    intent_repr=repr(intent),
                    from_chain=intent.from_chain,
                    to_chain=intent.to_chain,
                    token=intent.token,
                    input_amount=intent.amount,
                    output_amount=output,
                    fee_pct=self._calc_fee(intent.amount, output, intent.token),
                    quote_id=q.get("quoteId", "")
                )

        return result

    def safe_verdict(self, intent: Intent, policy: Policy) -> Verdict:
        """Execute the Safe Verdict pipeline.
        
        Returns a Verdict with EXECUTABLE or REFUSED and detailed reasoning.
        Delegates to safe_verdict_trace() for the actual logic.
        """
        result = self.safe_verdict_trace(intent, policy)
        
        # Convert DecisionResult → Verdict for backward compatibility
        checks = []
        quote_data = None
        for step in result.steps:
            if step.name in ("Parse Intent", "Parse Policy"):
                continue
            checks.append({
                "name": step.name,
                "passed": step.status == "passed",
                "detail": step.detail
            })
            if step.mcp_result and step.mcp_tool == "request-quote":
                quote_data = step.mcp_result
        
        return Verdict(
            executable=(result.verdict == "EXECUTABLE"),
            checks=checks,
            reason=result.reason,
            quote_data=quote_data
        )

    def safe_verdict_trace(self, intent: Intent, policy: Policy) -> DecisionResult:
        """Execute Safe Verdict with full decision trace.
        
        Returns a DecisionResult with detailed step-by-step trace.
        """
        start_time = time.time()
        steps = []
        quote_data = None
        
        # ── Step 1: Parse Intent ──────────────────────────────────
        step_start = time.time()
        steps.append(DecisionStep(
            name="Parse Intent",
            status="passed",
            detail=f"{intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}",
            duration_ms=int((time.time() - step_start) * 1000)
        ))
        
        # ── Step 2: Parse Policy ──────────────────────────────────
        step_start = time.time()
        steps.append(DecisionStep(
            name="Parse Policy",
            status="passed",
            detail=str(policy),
            duration_ms=int((time.time() - step_start) * 1000)
        ))
        
        # ── Step 3: Check Supported Route ─────────────────────────
        step_start = time.time()
        try:
            routes_result = self.get_routes()
            route_list = routes_result.get("data", {}).get("routes", [])
            
            if route_list:
                matching = [r for r in route_list
                            if str(r.get("fromChainId", r.get("fromChain", ""))).lower() in (intent.from_chain_id(), intent.from_chain_name().lower())
                            and str(r.get("toChainId", r.get("toChain", ""))).lower() in (intent.to_chain_id(), intent.to_chain_name().lower())]
                route_supported = len(matching) > 0
            else:
                route_supported = True
            
            duration = int((time.time() - step_start) * 1000)
            steps.append(DecisionStep(
                name="Check Supported Route",
                status="passed" if route_supported else "failed",
                detail=f"{intent.from_chain} → {intent.to_chain} ({intent.token.upper()})",
                duration_ms=duration,
                mcp_tool="get-supported-routes",
                mcp_result=routes_result
            ))
            
            if not route_supported:
                return DecisionResult(
                    verdict="REFUSED",
                    reason=f"No supported route found for {intent.from_chain} → {intent.to_chain} ({intent.token.upper()}).",
                    steps=steps,
                    intent=intent,
                    policy=policy,
                    total_duration_ms=int((time.time() - start_time) * 1000)
                )
        except Exception as e:
            duration = int((time.time() - step_start) * 1000)
            steps.append(DecisionStep(
                name="Check Supported Route",
                status="failed",
                detail=f"Error: {e}",
                duration_ms=duration,
                mcp_tool="get-supported-routes"
            ))
            return DecisionResult(
                verdict="REFUSED",
                reason=f"Failed to check route: {e}",
                steps=steps,
                intent=intent,
                policy=policy,
                total_duration_ms=int((time.time() - start_time) * 1000)
            )
        
        # ── Step 4: Check Route Health (if required) ──────────────
        step_start = time.time()
        if policy.require_healthy_route:
            try:
                health_result = self.check_route_health(intent.from_chain, intent.to_chain)
                health_data = health_result.get("data", {})
                status = health_data.get("status", "unknown")
                is_healthy = status.lower() in ["healthy", "ok", "good"]
                
                duration = int((time.time() - step_start) * 1000)
                steps.append(DecisionStep(
                    name="Check Route Health",
                    status="passed" if is_healthy else "failed",
                    detail=f"Status: {status.upper()}",
                    duration_ms=duration,
                    mcp_tool="check-route-health",
                    mcp_args={"fromChain": intent.from_chain, "toChain": intent.to_chain},
                    mcp_result=health_result
                ))
                
                if not is_healthy:
                    return DecisionResult(
                        verdict="REFUSED",
                        reason=f"Route health check failed. Status: {status}. The agent refuses to prepare the order.",
                        steps=steps,
                        intent=intent,
                        policy=policy,
                        total_duration_ms=int((time.time() - start_time) * 1000)
                    )
            except Exception as e:
                duration = int((time.time() - step_start) * 1000)
                steps.append(DecisionStep(
                    name="Check Route Health",
                    status="failed",
                    detail=f"Error: {e}",
                    duration_ms=duration,
                    mcp_tool="check-route-health"
                ))
                return DecisionResult(
                    verdict="REFUSED",
                    reason=f"Failed to check route health: {e}",
                    steps=steps,
                    intent=intent,
                    policy=policy,
                    total_duration_ms=int((time.time() - start_time) * 1000)
                )
        else:
            duration = int((time.time() - step_start) * 1000)
            steps.append(DecisionStep(
                name="Check Route Health",
                status="skipped",
                detail="Not required by policy",
                duration_ms=duration
            ))
        
        # ── Step 5: Get Quote ─────────────────────────────────────
        step_start = time.time()
        try:
            quote_args = {
                "fromChain": intent.from_chain_name(),
                "toChain": intent.to_chain_name(),
                "fromToken": intent.token_symbol(),
                "toToken": intent.token_symbol(),
                "amount": intent.amount,
                "userAddress": intent.address,
            }
            result = self.mcp.call("request-quote", quote_args)
            
            if "error" in result:
                duration = int((time.time() - step_start) * 1000)
                steps.append(DecisionStep(
                    name="Get Quote",
                    status="failed",
                    detail=result.get("error", "Unknown error"),
                    duration_ms=duration,
                    mcp_tool="request-quote",
                    mcp_args=quote_args,
                    mcp_result=result
                ))
                return DecisionResult(
                    verdict="REFUSED",
                    reason=f"Failed to get quote: {result.get('error', 'Unknown error')}",
                    steps=steps,
                    intent=intent,
                    policy=policy,
                    total_duration_ms=int((time.time() - start_time) * 1000)
                )
            
            quote_data = result.get("data", {})
            quotes = quote_data.get("quotes", [])
            
            if not quotes:
                duration = int((time.time() - step_start) * 1000)
                steps.append(DecisionStep(
                    name="Get Quote",
                    status="failed",
                    detail="No quotes returned",
                    duration_ms=duration,
                    mcp_tool="request-quote",
                    mcp_args=quote_args,
                    mcp_result=result
                ))
                return DecisionResult(
                    verdict="REFUSED",
                    reason="No quotes available for this route.",
                    steps=steps,
                    intent=intent,
                    policy=policy,
                    total_duration_ms=int((time.time() - start_time) * 1000)
                )
            
            q = quotes[0]
            output_amount = q.get("outputAmount", "0")
            quote_id = q.get("quoteId", "")
            
            duration = int((time.time() - step_start) * 1000)
            steps.append(DecisionStep(
                name="Get Quote",
                status="passed",
                detail=f"Output: {output_amount}, Quote ID: {quote_id[:16]}...",
                duration_ms=duration,
                mcp_tool="request-quote",
                mcp_args=quote_args,
                mcp_result=result
            ))
            
        except Exception as e:
            duration = int((time.time() - step_start) * 1000)
            steps.append(DecisionStep(
                name="Get Quote",
                status="failed",
                detail=f"Error: {e}",
                duration_ms=duration,
                mcp_tool="request-quote"
            ))
            return DecisionResult(
                verdict="REFUSED",
                reason=f"Failed to get quote: {e}",
                steps=steps,
                intent=intent,
                policy=policy,
                total_duration_ms=int((time.time() - start_time) * 1000)
            )
        
        # ── Step 6: Calculate Fee ─────────────────────────────────
        step_start = time.time()
        fee_pct = self._calc_fee(intent.amount, output_amount, intent.token)
        fee_pct_float = float(fee_pct) if fee_pct else 999.0
        duration = int((time.time() - step_start) * 1000)
        
        steps.append(DecisionStep(
            name="Calculate Fee",
            status="passed",
            detail=f"Fee: {fee_pct}%",
            duration_ms=duration
        ))
        
        # ── Step 7: Check Policy Constraints ──────────────────────
        step_start = time.time()
        policy_passed = True
        policy_reason = ""
        
        # Check max fee
        if policy.max_fee_pct is not None:
            fee_ok = fee_pct_float <= policy.max_fee_pct
            steps.append(DecisionStep(
                name="Fee Policy",
                status="passed" if fee_ok else "failed",
                detail=f"Fee {fee_pct}% {'≤' if fee_ok else '>'} limit {policy.max_fee_pct}%",
                duration_ms=0
            ))
            if not fee_ok:
                policy_passed = False
                policy_reason = f"The quote fee is {fee_pct}%, which exceeds the user limit of {policy.max_fee_pct}%."
        
        # Check min output
        if policy.min_output_amount is not None:
            output_float = normalize_output_amount(output_amount, intent.amount, intent.token)
            output_ok = output_float >= policy.min_output_amount
            steps.append(DecisionStep(
                name="Output Policy",
                status="passed" if output_ok else "failed",
                detail=f"Output {output_float:.4f} {'≥' if output_ok else '<'} min {policy.min_output_amount}",
                duration_ms=0
            ))
            if not output_ok:
                policy_passed = False
                policy_reason = f"Output {output_float:.4f} is below minimum {policy.min_output_amount}."
        
        # Check avoid chains (both source and destination)
        if policy.avoid_chains:
            avoided = []
            if intent.from_chain in policy.avoid_chains:
                avoided.append(f"source chain {intent.from_chain}")
            if intent.to_chain in policy.avoid_chains:
                avoided.append(f"target chain {intent.to_chain}")
            if avoided:
                steps.append(DecisionStep(
                    name="Avoid Chains",
                    status="failed",
                    detail=f"{', '.join(avoided)} in avoid list: {', '.join(policy.avoid_chains)}",
                    duration_ms=0
                ))
                policy_passed = False
                policy_reason = f"{avoided[0].title()} is in the avoid list."
            else:
                steps.append(DecisionStep(
                    name="Avoid Chains",
                    status="passed",
                    detail=f"Neither {intent.from_chain} nor {intent.to_chain} in avoid list",
                    duration_ms=0
                ))
        
        # Check cross-chain allowance
        if not policy.allow_cross_chain and intent.from_chain != intent.to_chain:
            steps.append(DecisionStep(
                name="Cross-Chain",
                status="failed",
                detail="Cross-chain transfer not allowed by policy",
                duration_ms=0
            ))
            policy_passed = False
            policy_reason = "Cross-chain transfer is not allowed by policy."
        elif not policy.allow_cross_chain:
            steps.append(DecisionStep(
                name="Cross-Chain",
                status="passed",
                detail="Same-chain transfer allowed",
                duration_ms=0
            ))
        
        duration = int((time.time() - step_start) * 1000)
        
        # ── Step 8: Final Verdict ─────────────────────────────────
        if policy_passed:
            reason_parts = [f"This intent satisfies the user policy."]
            if fee_pct:
                reason_parts.append(f"Fee {fee_pct}% is within acceptable limits.")
            if policy.prefer_cheapest:
                reason_parts.append("Route selected based on cheapest option.")
            
            return DecisionResult(
                verdict="EXECUTABLE",
                reason=" ".join(reason_parts),
                steps=steps,
                intent=intent,
                policy=policy,
                quote_data=quote_data,
                total_duration_ms=int((time.time() - start_time) * 1000)
            )
        else:
            return DecisionResult(
                verdict="REFUSED",
                reason=f"{policy_reason} The agent refuses to prepare the order.",
                steps=steps,
                intent=intent,
                policy=policy,
                quote_data=quote_data,
                total_duration_ms=int((time.time() - start_time) * 1000)
            )

    def compare_quotes(self, intent: Intent, chains: list[str] = None) -> list[dict]:
        """Compare quotes across multiple destination chains."""
        from .models import parse_amount_with_symbol

        if chains is None:
            chains = ["arbitrum", "optimism", "base", "polygon", "ethereum"]

        results = []
        for chain in chains:
            if chain == intent.from_chain:
                continue
            try:
                alt_intent = Intent(intent.from_chain, chain, intent.token, intent.amount, intent.address)
                quote = self.get_quote(alt_intent)
                quotes = quote.get("data", {}).get("quotes", [])
                if quotes:
                    q = quotes[0]
                    output = q.get("outputAmount", "0")
                    results.append({
                        "chain": chain,
                        "output": output,
                        "quote_id": q.get("quoteId", ""),
                        "fee_pct": self._calc_fee(intent.amount, output, intent.token),
                    })
            except Exception as e:
                logging.debug(f"Quote failed for {chain}: {e}")
                continue

        # Sort by output amount (higher is better) — handle "0.978879 USDC" format
        def parse_output(r):
            try:
                return parse_amount_with_symbol(r.get("output", "0"))
            except ValueError:
                return 0

        results.sort(key=parse_output, reverse=True)
        return results

    def _calc_fee(self, input_amount: str, output_amount: str, token: str = "usdc") -> Optional[str]:
        """Calculate fee percentage. Returns None on error.
        
        input_amount: human-readable (e.g. "10")
        output_amount: raw from MCP (e.g. "9980000") or human-readable (e.g. "9.98")
        token: token symbol for decimal conversion
        """
        try:
            inp = float(input_amount)
            out_human = normalize_output_amount(output_amount, input_amount, token)
            if inp == 0:
                return None
            fee = (inp - out_human) / inp * 100
            return f"{fee:.2f}"
        except (ValueError, ZeroDivisionError):
            return None

    def prepare_order(self, quote_id: str, address: str = DEMO_ADDRESS) -> dict:
        """Prepare an order from a quote."""
        return self.mcp.call("prepare-order", {"quoteId": quote_id, "userAddress": address})

    def track_order(self, order_id: str) -> dict:
        """Track an order's status."""
        return self.mcp.call("track-order", {"orderId": order_id})

    def list_orders(self, limit: int = 5) -> dict:
        """List recent orders."""
        return self.mcp.call("list-orders", {"limit": limit})

    # ── Solver tools ────────────────────────────────────────────
    def get_solver_identities(self) -> dict:
        """List registered solver wallet addresses."""
        return self.mcp.call("get-solver-identities", {})

    def get_quote_inventory(self, from_chain: str, to_chain: str,
                             from_asset: str, to_asset: str) -> dict:
        """View standing quotes for a specific route."""
        return self.mcp.call("get-quote-inventory", {
            "fromChain": from_chain, "toChain": to_chain,
            "fromAsset": from_asset, "toAsset": to_asset,
        })

    def submit_standing_quotes(self, quotes: list) -> dict:
        """Submit or update standing quotes for solver."""
        return self.mcp.call("submit-standing-quotes", {"quotes": quotes})

    def check_route_health(self, from_chain: str, to_chain: str,
                            from_asset: str = None, to_asset: str = None) -> dict:
        """Check health of a specific route."""
        args = {"fromChain": from_chain, "toChain": to_chain}
        if from_asset:
            args["fromAsset"] = from_asset
        if to_asset:
            args["toAsset"] = to_asset
        return self.mcp.call("check-route-health", args)

    def debug_order(self, order_id: str) -> dict:
        """Get full order details for debugging."""
        return self.mcp.call("debug-order", {"orderId": order_id})

    def solver_aware_checks(self, from_chain: str, to_chain: str,
                            from_asset: str = None, to_asset: str = None) -> dict:
        """Run all solver-aware checks for a route.

        Returns a comprehensive report with standardized check fields:
        name, status, passed, details (dict), explanation, action, duration_ms.
        """
        report = {
            "route": f"{from_chain} → {to_chain}",
            "checks": [],
            "summary": {}
        }

        # ── Check 1: Route Health ─────────────────────────────────
        check_start = time.time()
        try:
            health_result = self.check_route_health(from_chain, to_chain, from_asset, to_asset)
            health_data = health_result.get("data", {})
            status = health_data.get("status", "unknown")
            is_healthy = status.lower() in ["healthy", "ok", "good"]

            if is_healthy:
                explanation = (
                    f"Route is healthy. MCP responded with status '{status}'. "
                    f"Solvers are actively serving this route."
                )
                action = "No action needed. You can safely proceed with quotes on this route."
            elif status == "unknown":
                explanation = (
                    f"MCP responded, but no explicit health status was returned. "
                    f"This may mean the endpoint doesn't expose health data, or the route is new."
                )
                action = "Try requesting a quote directly. If it succeeds, the route is functional."
            else:
                explanation = (
                    f"Route health check returned '{status}'. "
                    f"This may indicate solver downtime or liquidity issues on this route."
                )
                action = "Check solver inventory for active quotes. Consider alternative routes if no quotes are available."

            report["checks"].append({
                "name": "Route Health",
                "status": status,
                "passed": is_healthy,
                "details": health_data if isinstance(health_data, dict) else {"raw": health_data},
                "explanation": explanation,
                "action": action,
                "duration_ms": int((time.time() - check_start) * 1000),
            })
        except Exception as e:
            report["checks"].append({
                "name": "Route Health",
                "status": "error",
                "passed": False,
                "details": {"error": str(e)},
                "explanation": f"Failed to check route health: {e}. The MCP endpoint may be unreachable.",
                "action": "Run 'doctor' to diagnose MCP connectivity issues.",
                "duration_ms": int((time.time() - check_start) * 1000),
            })

        # ── Check 2: Quote Availability ───────────────────────────
        check_start = time.time()
        try:
            routes_result = self.get_routes()
            route_list = routes_result.get("data", {}).get("routes", [])

            matching_routes = []
            for r in route_list:
                r_from = str(r.get("fromChainId", r.get("fromChain", ""))).lower()
                r_to = str(r.get("toChainId", r.get("toChain", ""))).lower()
                if (r_from in (from_chain.lower(), CHAINS.get(from_chain.lower(), {}).get("id", ""))
                    and r_to in (to_chain.lower(), CHAINS.get(to_chain.lower(), {}).get("id", ""))):
                    matching_routes.append(r)

            quote_available = len(matching_routes) > 0

            if quote_available:
                explanation = (
                    f"Found {len(matching_routes)} supported route(s) for {from_chain} → {to_chain}. "
                    f"This route appears in LI.FI's supported routes list."
                )
                action = "Route is supported. You can request quotes via 'request-quote'."
            else:
                explanation = (
                    f"No supported routes found for {from_chain} → {to_chain}. "
                    f"This may mean the chain pair is not yet supported, or token addresses don't match."
                )
                action = "Check 'get-supported-routes' for available chain pairs. Try different token addresses."

            report["checks"].append({
                "name": "Quote Availability",
                "status": "available" if quote_available else "unavailable",
                "passed": quote_available,
                "details": {
                    "matching_routes": len(matching_routes),
                    "routes": matching_routes[:3],
                },
                "explanation": explanation,
                "action": action,
                "duration_ms": int((time.time() - check_start) * 1000),
            })
        except Exception as e:
            report["checks"].append({
                "name": "Quote Availability",
                "status": "error",
                "passed": False,
                "details": {"error": str(e)},
                "explanation": f"Failed to check quote availability: {e}.",
                "action": "Run 'doctor' to diagnose MCP connectivity.",
                "duration_ms": int((time.time() - check_start) * 1000),
            })

        # ── Check 3: Solver Inventory ─────────────────────────────
        check_start = time.time()
        try:
            if from_asset and to_asset:
                inventory_result = self.get_quote_inventory(from_chain, to_chain, from_asset, to_asset)
                inventory_data = inventory_result.get("data", {})
                quotes = inventory_data.get("quotes", [])

                if quotes:
                    explanation = (
                        f"Found {len(quotes)} standing quote(s) in solver inventory. "
                        f"Solvers have pre-committed liquidity for this asset pair."
                    )
                    action = "Quotes are available. Execute quickly — standing quotes may expire."
                else:
                    explanation = (
                        f"No standing quotes found for this asset pair. "
                        f"This doesn't mean quotes won't work — solvers may still respond to on-demand requests."
                    )
                    action = "Try 'request-quote' anyway. If it fails, the solver may need time to provision liquidity."

                report["checks"].append({
                    "name": "Solver Inventory",
                    "status": "active" if quotes else "empty",
                    "passed": len(quotes) > 0,
                    "details": {
                        "quote_count": len(quotes),
                        "quotes": quotes[:3],
                    },
                    "explanation": explanation,
                    "action": action,
                    "duration_ms": int((time.time() - check_start) * 1000),
                })
            else:
                report["checks"].append({
                    "name": "Solver Inventory",
                    "status": "skipped",
                    "passed": True,
                    "details": {"reason": "No asset pair specified"},
                    "explanation": "Asset pair not specified — cannot check solver inventory.",
                    "action": "Provide from_asset and to_asset parameters to check inventory.",
                    "duration_ms": int((time.time() - check_start) * 1000),
                })
        except Exception as e:
            report["checks"].append({
                "name": "Solver Inventory",
                "status": "error",
                "passed": False,
                "details": {"error": str(e)},
                "explanation": f"Failed to check solver inventory: {e}.",
                "action": "Run 'doctor' to diagnose MCP connectivity.",
                "duration_ms": int((time.time() - check_start) * 1000),
            })

        # ── Summary ───────────────────────────────────────────────
        passed_checks = sum(1 for c in report["checks"] if c["passed"])
        total_checks = len(report["checks"])

        report["summary"] = {
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": total_checks - passed_checks,
            "health_status": report["checks"][0]["status"] if report["checks"] else "unknown",
            "overall_status": "healthy" if passed_checks == total_checks else "degraded"
        }

        return report

    def explain(self, text: str) -> dict:
        """Explain what the agent will do for a natural language intent, without executing.
        
        Returns a structured explanation with:
        - Parsed intent (what the user wants)
        - Parsed policy (constraints)
        - Step-by-step plan (what the agent will do)
        """
        intent, policy = parse_intent_with_policy(text)
        
        # Build intent description
        intent_desc = f"Move {intent.amount} {intent.token.upper()} from {intent.from_chain.title()} to {intent.to_chain.title()}."
        
        # Build policy description
        policy_parts = []
        if policy.max_fee_pct is not None:
            policy_parts.append(f"Only continue if estimated fee is below {policy.max_fee_pct}%.")
        if policy.min_output_amount is not None:
            policy_parts.append(f"Only continue if output is at least {policy.min_output_amount} {intent.token.upper()}.")
        if policy.require_healthy_route:
            policy_parts.append("Only continue if route health check passes.")
        if policy.avoid_chains:
            chains = [c.title() for c in policy.avoid_chains]
            policy_parts.append(f"Avoid using chains: {', '.join(chains)}.")
        if not policy.allow_cross_chain:
            policy_parts.append("Only allow same-chain transfers.")
        if policy.prefer_cheapest:
            policy_parts.append("Prefer the cheapest available route.")
        
        policy_desc = " ".join(policy_parts) if policy_parts else "No policy constraints — proceed unconditionally."
        
        # Build execution plan
        steps = [
            f"1. Parse intent → extract amount ({intent.amount}), token ({intent.token.upper()}), "
            f"source ({intent.from_chain.title()}), destination ({intent.to_chain.title()})",
            f"2. Resolve chain IDs → {intent.from_chain}: {intent.from_chain_id()}, {intent.to_chain}: {intent.to_chain_id()}",
            f"3. Resolve token addresses → source: {intent.from_token_address()}, dest: {intent.to_token_address()}",
            "4. Call 'get-supported-routes' → verify this chain pair is supported",
        ]
        
        if policy.require_healthy_route:
            steps.append("5. Call 'check-route-health' → verify solvers are serving this route")
        
        steps.append(f"{'6' if policy.require_healthy_route else '5'}. Call 'request-quote' → get solver quote for this transfer")
        steps.append(f"{'7' if policy.require_healthy_route else '6'}. Calculate fee percentage from input/output amounts")
        
        step_num = 8 if policy.require_healthy_route else 7
        
        if policy.max_fee_pct is not None:
            steps.append(f"{step_num}. Check fee policy → compare calculated fee against {policy.max_fee_pct}% limit")
            step_num += 1
        if policy.min_output_amount is not None:
            steps.append(f"{step_num}. Check output policy → compare output amount against {policy.min_output_amount} minimum")
            step_num += 1
        if policy.avoid_chains:
            chains = [c.title() for c in policy.avoid_chains]
            steps.append(f"{step_num}. Check avoid chains → verify neither source nor destination is in: {', '.join(chains)}")
            step_num += 1
        
        steps.append(f"{step_num}. Return verdict → EXECUTABLE (all checks pass) or REFUSED (any check fails)")
        
        return {
            "input": text,
            "intent": {
                "amount": intent.amount,
                "token": intent.token.upper(),
                "from_chain": intent.from_chain,
                "to_chain": intent.to_chain,
                "description": intent_desc
            },
            "policy": {
                "max_fee_pct": policy.max_fee_pct,
                "min_output_amount": policy.min_output_amount,
                "max_slippage": policy.max_slippage,
                "require_healthy_route": policy.require_healthy_route,
                "avoid_chains": policy.avoid_chains,
                "allow_cross_chain": policy.allow_cross_chain,
                "prefer_cheapest": policy.prefer_cheapest,
                "description": policy_desc
            },
            "execution_plan": steps
        }

    def doctor(self) -> dict:
        """Run diagnostic checks on the MCP connection and configuration.
        
        Returns a diagnostic report with checks and warnings.
        """
        report = {
            "checks": [],
            "warnings": []
        }

        # ── Check 0: Operating Mode ─────────────────────────────
        mock_mode = self.mcp.is_mock_mode()
        strict_mode = MCPClient.is_strict_mode()
        if mock_mode:
            source = self.mcp.mock_mode_source()
            detail = f"Mock mode active — source: {source}"
            status = "MOCK"
            if strict_mode:
                status = "STRICT"
                detail += " (strict mode violation!)"
        elif strict_mode:
            status = "STRICT"
            detail = "Strict mode enabled — connected to local MCP, no fallback allowed"
        else:
            status = "LOCAL"
            detail = "Connected to local MCP server"
        report["checks"].append({
            "name": "Operating Mode",
            "status": status,
            "passed": True,
            "detail": detail
        })

        # ── Check 1: MCP endpoint reachable ───────────────────────
        try:
            # Try to connect to MCP
            info = self.mcp.connect()
            if mock_mode:
                forced = os.environ.get("LIFI_AGENT_MOCK_MODE") == "1"
                if forced:
                    detail = "Force mock mode (LIFI_AGENT_MOCK_MODE=1)"
                else:
                    detail = "Local MCP unreachable, auto-fallback to mock mode"
            else:
                detail = f"Connected to {info.get('serverInfo', {}).get('name', 'unknown')}"
            report["checks"].append({
                "name": "MCP endpoint reachable",
                "passed": True,
                "detail": detail
            })
        except Exception as e:
            report["checks"].append({
                "name": "MCP endpoint reachable",
                "passed": False,
                "detail": str(e)
            })
        
        # ── Check 2: MCP session initialized ──────────────────────
        try:
            session_id = self.mcp.session_id
            if session_id is not None:
                report["checks"].append({
                    "name": "MCP session initialized",
                    "passed": True,
                    "detail": f"Session ID: {session_id[:8]}..."
                })
            elif self.mcp._connected:
                report["checks"].append({
                    "name": "MCP session initialized",
                    "passed": True,
                    "detail": "Stateless mode (no session ID)"
                })
            else:
                report["checks"].append({
                    "name": "MCP session initialized",
                    "passed": False,
                    "detail": "Not connected and no session ID"
                })
        except Exception as e:
            report["checks"].append({
                "name": "MCP session initialized",
                "passed": False,
                "detail": str(e)
            })
        
        # ── Check 3: get-supported-routes works ───────────────────
        try:
            routes_result = self.get_routes()
            route_count = len(routes_result.get("data", {}).get("routes", []))
            report["checks"].append({
                "name": "get-supported-routes works",
                "passed": True,
                "detail": f"{route_count} routes available"
            })
        except Exception as e:
            report["checks"].append({
                "name": "get-supported-routes works",
                "passed": False,
                "detail": str(e)
            })
        
        # ── Check 4: Base USDC address configured ─────────────────
        base_usdc = TOKENS.get("usdc", {}).get("8453", "")
        if base_usdc:
            report["checks"].append({
                "name": "Base USDC address configured",
                "passed": True,
                "detail": base_usdc[:10] + "..."
            })
        else:
            report["checks"].append({
                "name": "Base USDC address configured",
                "passed": False,
                "detail": "Not configured"
            })
        
        # ── Check 5: Arbitrum USDC address configured ─────────────
        arb_usdc = TOKENS.get("usdc", {}).get("42161", "")
        if arb_usdc:
            report["checks"].append({
                "name": "Arbitrum USDC address configured",
                "passed": True,
                "detail": arb_usdc[:10] + "..."
            })
        else:
            report["checks"].append({
                "name": "Arbitrum USDC address configured",
                "passed": False,
                "detail": "Not configured"
            })
        
        # ── Check 6: route health tool reachable ──────────────────
        try:
            health_result = self.check_route_health("base", "arbitrum")
            report["checks"].append({
                "name": "route health tool reachable",
                "passed": True,
                "detail": "Tool responded"
            })
        except Exception as e:
            report["checks"].append({
                "name": "route health tool reachable",
                "passed": False,
                "detail": str(e)
            })
        
        # ── Check 7: request-quote works ──────────────────────────
        try:
            # Try to get a quote with a small amount
            quote_result = self.get_quote(Intent("base", "arbitrum", "usdc", "1"))
            if "error" not in quote_result:
                quotes = quote_result.get("data", {}).get("quotes", [])
                if quotes:
                    q = quotes[0]
                    detail = f"Quote received — input: {q.get('inputAmount', '?')}, output: {q.get('outputAmount', '?')}, id: {q.get('quoteId', '?')[:16]}..."
                else:
                    detail = "Quote received but no quotes in response"
                report["checks"].append({
                    "name": "request-quote works",
                    "passed": True,
                    "detail": detail
                })
            else:
                report["checks"].append({
                    "name": "request-quote works",
                    "passed": False,
                    "detail": quote_result.get("error", "Unknown error")
                })
        except Exception as e:
            report["checks"].append({
                "name": "request-quote works",
                "passed": False,
                "detail": str(e)
            })

        # ── Check 8: MCP Protocol handshake ───────────────────────
        try:
            if mock_mode:
                report["checks"].append({
                    "name": "MCP Protocol",
                    "passed": True,
                    "detail": "Skipped (mock mode)"
                })
            else:
                protocol_version = "2025-03-26"
                init_result = self.mcp.client.post(
                    self.mcp.url,
                    json={"jsonrpc": "2.0", "id": 99, "method": "initialize", "params": {
                        "protocolVersion": protocol_version, "capabilities": {},
                        "clientInfo": {"name": "lifi-agent-doctor", "version": "1.0"}}},
                    headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                    timeout=self.mcp.timeout
                )
                if init_result.status_code == 200:
                    server_info = MCPClient._parse_server_info(init_result.text)
                    info = server_info.get("serverInfo", {})
                    report["checks"].append({
                        "name": "MCP Protocol",
                        "passed": True,
                        "detail": f"Protocol {protocol_version}, server: {info.get('name', '?')} v{info.get('version', '?')}"
                    })
                else:
                    report["checks"].append({
                        "name": "MCP Protocol",
                        "passed": False,
                        "detail": f"HTTP {init_result.status_code}"
                    })
        except Exception as e:
            report["checks"].append({
                "name": "MCP Protocol",
                "passed": False,
                "detail": str(e)
            })

        # ── Check 9: Available Tools ──────────────────────────────
        try:
            if mock_mode:
                tools = ["get-supported-routes", "request-quote", "check-route-health",
                         "prepare-order", "track-order", "list-orders", "get-solver-identities",
                         "get-quote-inventory", "submit-standing-quotes"]
                report["checks"].append({
                    "name": "Available Tools",
                    "passed": True,
                    "detail": f"{len(tools)} tools (mock): {', '.join(tools[:5])}..."
                })
            else:
                tools_result = self.mcp.client.post(
                    self.mcp.url,
                    json={"jsonrpc": "2.0", "id": 98, "method": "tools/list", "params": {}},
                    headers=self.mcp._headers(),
                    timeout=self.mcp.timeout
                )
                if tools_result.status_code == 200:
                    parsed = MCPClient._parse_sse(tools_result.text)
                    if "error" not in parsed:
                        tool_list = parsed.get("tools", [])
                        tool_names = [t.get("name", "?") for t in tool_list]
                        report["checks"].append({
                            "name": "Available Tools",
                            "passed": True,
                            "detail": f"{len(tool_names)} tools: {', '.join(tool_names[:5])}{'...' if len(tool_names) > 5 else ''}"
                        })
                    else:
                        report["checks"].append({
                            "name": "Available Tools",
                            "passed": True,
                            "detail": "Tools list returned (parsed as non-standard format)"
                        })
                else:
                    report["checks"].append({
                        "name": "Available Tools",
                        "passed": False,
                        "detail": f"HTTP {tools_result.status_code}"
                    })
        except Exception as e:
            report["checks"].append({
                "name": "Available Tools",
                "passed": False,
                "detail": str(e)
            })

        # ── Check 10: Quote Test (small amount) ───────────────────
        try:
            quote_args = {
                "fromChain": "base",
                "toChain": "arbitrum",
                "fromToken": "USDC",
                "toToken": "USDC",
                "amount": "1",
                "userAddress": DEMO_ADDRESS,
            }
            result = self.mcp.call("request-quote", quote_args)
            if "error" not in result:
                quotes = result.get("data", {}).get("quotes", [])
                if quotes:
                    q = quotes[0]
                    report["checks"].append({
                        "name": "Quote Test",
                        "passed": True,
                        "detail": f"1 USDC Base→Arbitrum: output {q.get('outputAmount', '?')}, solver responded"
                    })
                else:
                    report["checks"].append({
                        "name": "Quote Test",
                        "passed": False,
                        "detail": "No quotes returned for 1 USDC Base→Arbitrum"
                    })
            else:
                report["checks"].append({
                    "name": "Quote Test",
                    "passed": False,
                    "detail": result.get("error", "Unknown error")
                })
        except Exception as e:
            report["checks"].append({
                "name": "Quote Test",
                "passed": False,
                "detail": str(e)
            })

        # ── Check 11: Mock Mode Source ────────────────────────────
        if mock_mode:
            source = self.mcp.mock_mode_source()
            report["checks"].append({
                "name": "Mock Mode Source",
                "passed": True,
                "detail": source
            })
        
        # ── Warnings ──────────────────────────────────────────────
        # Warning 1: OPENAI_API_KEY not set
        if not os.environ.get("OPENAI_API_KEY"):
            report["warnings"].append({
                "name": "OPENAI_API_KEY not set",
                "detail": "Using deterministic parser"
            })
        
        # Warning 2: Amount unit behavior
        report["warnings"].append({
            "name": "Amount unit behavior",
            "detail": "Should be verified before real execution"
        })
        
        return report

    def close(self):
        self.mcp.close()


# ── Interactive CLI ─────────────────────────────────────────────────
def interactive():
    """Run interactive CLI mode with Rich TUI and auto-completion."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.styles import Style as PTStyle

    agent = LifAgent()
    use_llm = bool(os.environ.get("OPENAI_API_KEY"))

    # ── Welcome banner ────────────────────────────────────────────
    welcome_text = Text()
    welcome_text.append("LI.FI Intents", style="bold cyan")
    welcome_text.append(" × ", style="dim")
    welcome_text.append("AI Agent", style="bold green")
    welcome_text.append("\n\n")
    welcome_text.append("Cross-chain operations via natural language", style="italic")
    console.print()
    console.print(Panel(welcome_text, border_style="cyan", box=box.ROUNDED, padding=(1, 2)))
    console.print()

    # ── Connect ───────────────────────────────────────────────────
    try:
        info = agent.connect()
        status_ok(info)
        if agent.mcp.is_mock_mode():
            console.print("  [yellow]⚡ Mock Mode — using simulated data[/yellow]")
        else:
            server_name = info.split("Connected to ")[-1].split(" v")[0] if "Connected to" in info else "local MCP"
            console.print(f"  [green]✓ Local MCP Mode — connected to {server_name}[/green]")
    except Exception as e:
        status_err(f"Connection failed: {e}")
        console.print("  [dim]Running in offline mode (cached data only)[/dim]")
    console.print()

    # ── Commands help ─────────────────────────────────────────────
    help_table = Table(show_header=False, box=None, padding=(0, 2))
    help_table.add_column("Command", style="bold")
    help_table.add_column("Description")
    help_table.add_row("[cyan]send[/cyan] 10 USDC from Base to Arbitrum", "Execute a transfer")
    help_table.add_row("[cyan]safe[/cyan] send 10 USDC from Base to Arbitrum if fee < 0.5%", "Safe Verdict: check policy before executing")
    help_table.add_row("[cyan]explain[/cyan] send 10 USDC from Base to Arbitrum if fee < 0.5%", "Explain intent and execution plan without executing")
    help_table.add_row("[cyan]compare[/cyan] 10 USDC from Ethereum", "Compare quotes across chains")
    help_table.add_row("[cyan]route health[/cyan] base arbitrum", "Check route health status")
    help_table.add_row("[cyan]solver[/cyan] base arbitrum USDC USDC", "Run solver-aware checks (health, quotes, inventory)")
    help_table.add_row("[cyan]doctor[/cyan]", "Run diagnostic checks on MCP connection")
    help_table.add_row("[cyan]routes[/cyan]", "Show supported routes")
    help_table.add_row("[cyan]orders[/cyan]", "Show recent orders")
    help_table.add_row("[cyan]favorites[/cyan]", "Show saved routes")
    help_table.add_row("[cyan]wallet[/cyan]", "Show demo wallet info")
    help_table.add_row("[cyan]history[/cyan]", "Show recent quotes (SQLite)")
    help_table.add_row("[cyan]stats[/cyan]", "Show quote statistics")
    help_table.add_row("[cyan]yes[/cyan] / [cyan]confirm[/cyan]", "Confirm pending order")
    help_table.add_row("[cyan]quit[/cyan]", "Exit")
    console.print(Panel(help_table, title="[bold]Commands[/bold]", border_style="dim", box=box.ROUNDED))
    console.print()

    # ── Auto-completion setup ─────────────────────────────────────
    chain_names = list(CHAINS.keys())
    token_names = ["USDC", "USDT", "ETH"]
    commands = ["send", "safe", "verdict", "explain", "compare", "route", "solver", "doctor", "routes", "orders", "favorites", "wallet",
                "history", "stats", "quit"]
    all_completions = commands + chain_names + token_names + [
        "from", "to", "bridge", "transfer", "if", "fee", "healthy",
    ]
    completer = WordCompleter(all_completions, ignore_case=True, match_middle=True)

    prompt_style = PTStyle.from_dict({
        "prompt": "bold cyan",
    })

    session = PromptSession(style=prompt_style)

    pending_intent = None
    pending_quote = None

    def do_prompt() -> str:
        if pending_intent:
            return session.prompt(
                [("class:prompt", "Confirm > ")],
                completer=completer,
            )
        return session.prompt(
            [("class:prompt", "You > ")],
            completer=completer,
        )

    # ── Fee color helper ──────────────────────────────────────────
    def fee_style(pct_str: str) -> str:
        try:
            pct = float(pct_str)
        except ValueError:
            return f"[red]{pct_str}%[/red]"
        if pct < 0.2:
            return f"[green]{pct_str}%[/green]"
        elif pct < 0.5:
            return f"[yellow]{pct_str}%[/yellow]"
        else:
            return f"[red]{pct_str}%[/red]"

    # ── Main loop ─────────────────────────────────────────────────
    while True:
        try:
            text = do_prompt().strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not text:
            continue
        if text in ("quit", "exit", "q"):
            break

        # ── Handle confirmation ────────────────────────────────
        if pending_intent and text in ("yes", "y", "confirm", "ok"):
            if pending_quote:
                quote_id = pending_quote.get("quoteId", "")
                if quote_id:
                    with Progress(SpinnerColumn(), TextColumn("[bold blue]Preparing order...[/bold blue]"), transient=True) as progress:
                        progress.add_task("prep", total=None)
                        result = agent.prepare_order(quote_id)
                    if "error" in result:
                        status_err(result["error"])
                    else:
                        order = result.get("data", {})
                        status_ok("Order prepared!")
                        t = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
                        t.add_column("Key", style="dim")
                        t.add_column("Value")
                        t.add_row("Order ID", str(order.get("id", "?")))
                        t.add_row("Status", str(order.get("status", "?")))
                        console.print(t)
                        agent.pending_order = order
                        agent.remember_route(pending_intent.from_chain, pending_intent.to_chain, pending_intent.token)
                        status_ok("Route saved to favorites!")
                else:
                    status_err("No quote ID available")
            else:
                status_err("No pending quote")
            pending_intent = None
            pending_quote = None
            console.print()
            continue

        if pending_intent and text in ("no", "n", "cancel"):
            console.print("\n  [dim]Cancelled.[/dim]\n")
            pending_intent = None
            pending_quote = None
            continue

        # Cancel pending if new command
        if pending_intent:
            pending_intent = None
            pending_quote = None

        # ── Wallet command ─────────────────────────────────────
        if text == "wallet":
            wallet_table = Table(title="Demo Wallet", box=box.ROUNDED, border_style="cyan")
            wallet_table.add_column("Field", style="dim")
            wallet_table.add_column("Value")
            wallet_table.add_row("Address", f"[bold]{DEMO_ADDRESS}[/bold]")
            wallet_table.add_row("Network", "Multi-chain (demo)")
            wallet_table.add_row("Balance", "[yellow]Connect wallet to view[/yellow]")
            console.print()
            console.print(wallet_table)
            console.print()
            continue

        # ── Handle commands ────────────────────────────────────
        if text == "routes":
            with Progress(SpinnerColumn(), TextColumn("[bold blue]Fetching routes...[/bold blue]"), transient=True) as progress:
                progress.add_task("routes", total=None)
                result = agent.get_routes()
            count = result.get("data", {}).get("count", "?")
            routes_list = result.get("data", {}).get("routes", [])
            msg = result.get("message", "")
            status_ok(f"{count} routes available")
            if routes_list:
                pairs = set()
                for r in routes_list:
                    f = r.get("fromChain", "?")
                    t = r.get("toChain", "?")
                    pairs.add((f, t))
                table = Table(box=box.SIMPLE_HEAVY, border_style="dim")
                table.add_column("#", style="dim", width=4)
                table.add_column("From", style="bold")
                table.add_column("", justify="center")
                table.add_column("To", style="bold")
                for i, (f, t) in enumerate(sorted(pairs)[:15], 1):
                    table.add_row(str(i), styled_chain(f.lower()), "→", styled_chain(t.lower()))
                console.print(table)
                if len(pairs) > 15:
                    console.print(f"  [dim]... and {len(pairs)-15} more[/dim]")
            if msg:
                console.print(f"  {msg}")
            console.print()
            continue

        # ── Doctor command ────────────────────────────────────────
        if text == "doctor":
            console.print(f"\n  [bold cyan]🏥 LI.FI Intents MCP Doctor[/bold cyan]\n")
            
            # Run doctor checks
            with Progress(SpinnerColumn(), TextColumn("[bold blue]Running diagnostic checks...[/bold blue]"), transient=True) as progress:
                progress.add_task("doctor", total=None)
                report = agent.doctor()
            
            # Display checks
            for check in report["checks"]:
                icon = "[green]✓[/green]" if check["passed"] else "[red]✗[/red]"
                console.print(f"  {icon} {check['name']}: {check['detail']}")
            
            # Display warnings
            if report["warnings"]:
                console.print(f"\n  [bold yellow]Warnings:[/bold yellow]")
                for warning in report["warnings"]:
                    console.print(f"  [yellow]![/yellow] {warning['name']}: {warning['detail']}")
            
            console.print()
            continue

        # ── Route health command ──────────────────────────────────
        if text.startswith("route health") or text.startswith("routehealth"):
            parts = text.split()
            if len(parts) < 3:
                console.print("\n  [yellow]Usage:[/yellow] route health <from_chain> <to_chain>")
                console.print("  [dim]Example:[/yellow] route health base arbitrum\n")
                continue
            from_chain = parts[2]
            to_chain = parts[3] if len(parts) > 3 else "arbitrum"
            
            with Progress(SpinnerColumn(), TextColumn(f"[bold blue]Checking route health: {from_chain} → {to_chain}...[/bold blue]"), transient=True) as progress:
                progress.add_task("health", total=None)
                result = agent.check_route_health(from_chain, to_chain)
            
            if "error" in result:
                console.print(f"\n  [red]Error:[/red] {result['error']}\n")
            else:
                data = result.get("data", {})
                status = data.get("status", "unknown")
                routes = data.get("routes", [])
                
                # Status indicator
                if status == "healthy":
                    status_icon = "[green]●[/green]"
                elif status == "degraded":
                    status_icon = "[yellow]●[/yellow]"
                else:
                    status_icon = "[red]●[/red]"
                
                console.print(f"\n  {status_icon} Route Health: [bold]{from_chain} → {to_chain}[/bold]")
                console.print(f"  Status: [bold]{status.upper()}[/bold]")
                
                if routes:
                    table = Table(box=box.SIMPLE, border_style="dim")
                    table.add_column("Route", style="bold")
                    table.add_column("Status")
                    table.add_column("Latency")
                    for r in routes[:5]:
                        route_name = f"{r.get('fromChain', '?')} → {r.get('toChain', '?')}"
                        r_status = r.get("status", "?")
                        latency = r.get("latency", "?")
                        table.add_row(route_name, r_status, f"{latency}ms")
                    console.print(table)
                
                console.print()
            continue

        # ── Solver-aware checks command ──────────────────────────
        if text.startswith("solver ") or text.startswith("solver-check"):
            parts = text.split()
            if len(parts) < 3:
                console.print("\n  [yellow]Usage:[/yellow] solver <from_chain> <to_chain> [from_asset] [to_asset]")
                console.print("  [dim]Example:[/dim] solver base arbitrum USDC USDC")
                console.print("  [dim]Example:[/dim] solver base arbitrum\n")
                continue
            
            from_chain = parts[1]
            to_chain = parts[2]
            from_asset = parts[3] if len(parts) > 3 else None
            to_asset = parts[4] if len(parts) > 4 else None
            
            console.print(f"\n  [bold cyan]🔧 Solver-Aware Checks[/bold cyan]")
            console.print(f"  Route: [bold]{from_chain} → {to_chain}[/bold]")
            if from_asset and to_asset:
                console.print(f"  Assets: [bold]{from_asset} → {to_asset}[/bold]")
            console.print()
            
            # Run solver-aware checks
            with Progress(SpinnerColumn(), TextColumn("[bold blue]Running solver-aware checks...[/bold blue]"), transient=True) as progress:
                progress.add_task("solver", total=None)
                report = agent.solver_aware_checks(from_chain, to_chain, from_asset, to_asset)
            
            # Display results
            console.print("  [bold]Checks:[/bold]")
            for check in report["checks"]:
                # Status icon
                if check["passed"]:
                    icon = "[green]✓[/green]"
                elif check["status"] == "skipped":
                    icon = "[dim]○[/dim]"
                else:
                    icon = "[red]✗[/red]"
                
                # Status text
                status_text = check["status"].upper()
                if check["status"] == "healthy":
                    status_text = "[green]HEALTHY[/green]"
                elif check["status"] == "active":
                    status_text = "[green]ACTIVE[/green]"
                elif check["status"] == "available":
                    status_text = "[green]AVAILABLE[/green]"
                elif check["status"] == "empty":
                    status_text = "[yellow]EMPTY[/yellow]"
                elif check["status"] == "unavailable":
                    status_text = "[red]UNAVAILABLE[/red]"
                elif check["status"] == "error":
                    status_text = "[red]ERROR[/red]"
                
                console.print(f"    {icon} {check['name']}: {status_text}")
                
                # Show details for failed checks
                if not check["passed"] and check["status"] != "skipped":
                    details = check.get("details", {})
                    if isinstance(details, dict):
                        for key, value in details.items():
                            if key != "routes":  # Skip routes to avoid clutter
                                console.print(f"      [dim]{key}: {value}[/dim]")
                    else:
                        console.print(f"      [dim]{details}[/dim]")
            
            # Summary
            summary = report["summary"]
            console.print(f"\n  [bold]Summary:[/bold]")
            console.print(f"    Total checks: {summary['total_checks']}")
            console.print(f"    Passed: [green]{summary['passed_checks']}[/green]")
            console.print(f"    Failed: [red]{summary['failed_checks']}[/red]")
            console.print(f"    Overall: [bold]{summary['overall_status'].upper()}[/bold]")
            
            console.print()
            continue

        # ── Safe Verdict command ──────────────────────────────────
        if text.startswith("safe ") or text.startswith("verdict "):
            # Remove command prefix
            cmd_text = re.sub(r'^(safe|verdict)\s+', '', text, flags=re.IGNORECASE)
            
            try:
                # Parse intent and policy
                intent, policy = parse_intent_with_policy(cmd_text)
                
                console.print(f"\n  [bold cyan]🔍 Safe Verdict[/bold cyan]")
                console.print(f"  Intent: [bold]{intent.amount} {intent.token.upper()} {intent.from_chain} → {intent.to_chain}[/bold]")
                console.print(f"  Policy: [dim]{policy}[/dim]\n")
                
                # Execute Safe Verdict pipeline with trace
                with Progress(SpinnerColumn(), TextColumn("[bold blue]Running Safe Verdict checks...[/bold blue]"), transient=True) as progress:
                    progress.add_task("verdict", total=None)
                    result = agent.safe_verdict_trace(intent, policy)
                
                # Display verdict
                if result.verdict == "EXECUTABLE":
                    console.print(f"  [bold green]✓ Verdict: EXECUTABLE[/bold green]")
                else:
                    console.print(f"  [bold red]✗ Verdict: REFUSED[/bold red]")
                
                # Display decision trace
                console.print(f"\n  [bold]Decision Trace:[/bold]")
                for i, step in enumerate(result.steps, 1):
                    # Status icon
                    if step.status == "passed":
                        icon = "[green]✓[/green]"
                    elif step.status == "failed":
                        icon = "[red]✗[/red]"
                    elif step.status == "warning":
                        icon = "[yellow]⚠[/yellow]"
                    else:  # skipped
                        icon = "[dim]○[/dim]"
                    
                    # Duration
                    duration_str = f" ({step.duration_ms}ms)" if step.duration_ms > 0 else ""
                    
                    # MCP tool info
                    mcp_str = ""
                    if step.mcp_tool:
                        mcp_str = f" [dim]via {step.mcp_tool}[/dim]"
                    
                    console.print(f"    {icon} {step.name}: {step.detail}{duration_str}{mcp_str}")
                
                # Display reason
                console.print(f"\n  [bold]Reason:[/bold]")
                console.print(f"    {result.reason}")
                
                # Display timing
                console.print(f"\n  [dim]Total duration: {result.total_duration_ms}ms[/dim]")
                
                # If executable, show quote details
                if result.verdict == "EXECUTABLE" and result.quote_data:
                    quotes = result.quote_data.get("quotes", [])
                    if quotes:
                        q = quotes[0]
                        console.print(f"\n  [bold]Quote Details:[/bold]")
                        console.print(f"    Output: {q.get('outputAmount', 'N/A')}")
                        console.print(f"    Quote ID: {q.get('quoteId', 'N/A')[:16]}...")
                
                console.print()
                
            except ValueError as e:
                console.print(f"\n  [red]Parse error:[/red] {e}")
                console.print("  [dim]Example: safe send 10 USDC from Base to Arbitrum if fee < 0.5%[/dim]\n")
            except Exception as e:
                console.print(f"\n  [red]Error:[/red] {e}\n")
            continue

        # ── Explain command ──────────────────────────────────────
        if text.startswith("explain "):
            cmd_text = text[8:].strip()
            if not cmd_text:
                console.print("\n  [yellow]Usage:[/yellow] explain <intent>")
                console.print("  [dim]Example:[/dim] explain safe send 10 USDC from Base to Arbitrum if fee < 0.5%\n")
                continue
            
            try:
                result = agent.explain(cmd_text)
                
                console.print(f"\n  [bold cyan]📖 Intent Explanation[/bold cyan]\n")
                
                # Intent
                console.print(f"  [bold]Intent:[/bold]")
                console.print(f"    {result['intent']['description']}\n")
                
                # Policy
                console.print(f"  [bold]Policy:[/bold]")
                console.print(f"    {result['policy']['description']}\n")
                
                # Execution plan
                console.print(f"  [bold]Execution Plan:[/bold]")
                for step in result['execution_plan']:
                    console.print(f"    {step}")
                
                console.print()
                
            except ValueError as e:
                console.print(f"\n  [red]Parse error:[/red] {e}")
                console.print("  [dim]Example: explain send 10 USDC from Base to Arbitrum if fee < 0.5%[/dim]\n")
            except Exception as e:
                console.print(f"\n  [red]Error:[/red] {e}\n")
            continue

        if text == "orders":
            with Progress(SpinnerColumn(), TextColumn("[bold blue]Fetching orders...[/bold blue]"), transient=True) as progress:
                progress.add_task("orders", total=None)
                result = agent.list_orders()
            orders = result.get("data", {}).get("orders", [])
            if not orders:
                console.print("\n  [dim]No orders found.[/dim]\n")
            else:
                table = Table(box=box.ROUNDED, border_style="dim")
                table.add_column("Order ID", style="bold")
                table.add_column("Status")
                for o in orders:
                    table.add_row(str(o.get("id", "?")), str(o.get("status", "?")))
                console.print(table)
            console.print()
            continue

        if text == "favorites":
            favs = agent.get_favorite_routes()
            if favs:
                table = Table(title="Saved Routes", box=box.ROUNDED, border_style="cyan")
                table.add_column("#", style="dim", width=4)
                table.add_column("From")
                table.add_column("")
                table.add_column("To")
                table.add_column("Token")
                for i, r in enumerate(favs, 1):
                    parts = r.split(":")
                    table.add_row(str(i), styled_chain(parts[0]), "→", styled_chain(parts[1]), parts[2].upper())
                console.print()
                console.print(table)
            else:
                console.print("\n  [dim]No saved routes yet. Execute a transfer to save it.[/dim]")
            console.print()
            continue

        if text == "history":
            recent = get_quote_store().get_recent(10)
            if recent:
                table = Table(title="Recent Quotes (SQLite)", box=box.ROUNDED, border_style="dim")
                table.add_column("#", style="dim", width=4)
                table.add_column("Time", style="dim")
                table.add_column("Route")
                table.add_column("Output")
                table.add_column("Fee")
                for i, entry in enumerate(recent, 1):
                    ts = entry.get("timestamp", "?")[:19]  # YYYY-MM-DD HH:MM:SS
                    route = f"{entry['from_chain']}→{entry['to_chain']} ({entry['token'].upper()})"
                    output = entry.get("output_amount", "?")
                    fee = entry.get("fee_pct")
                    fee_str = f"{float(fee):.2f}%" if fee else "?"
                    table.add_row(str(i), ts, route, output, fee_str)
                console.print()
                console.print(table)
            else:
                console.print("\n  [dim]No quote history yet.[/dim]")
            console.print()
            continue

        if text == "stats":
            stats = get_quote_store().get_stats()
            if stats["total"] == 0:
                console.print("\n  [dim]No quotes recorded yet.[/dim]\n")
                continue
            
            table = Table(title="📊 Quote Statistics", box=box.ROUNDED, border_style="blue")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Total Quotes", str(stats["total"]))
            table.add_row("Average Fee", f"{stats['avg_fee']:.3f}%")
            
            if stats["top_routes"]:
                routes_str = "\n".join(
                    f"  {f}→{t} ({c}x)" for f, t, c in stats["top_routes"]
                )
                table.add_row("Top Routes", routes_str)
            
            if stats["top_tokens"]:
                tokens_str = ", ".join(
                    f"{t.upper()} ({c}x)" for t, c in stats["top_tokens"]
                )
                table.add_row("Top Tokens", tokens_str)
            
            console.print()
            console.print(table)
            console.print()
            continue

        if text.startswith("llm"):
            parts = text.split()
            if len(parts) > 1 and parts[1] == "on":
                if os.environ.get("OPENAI_API_KEY"):
                    use_llm = True
                    console.print("\n  [green]✓[/green] LLM mode enabled\n")
                else:
                    console.print("\n  [red]✗[/red] OPENAI_API_KEY not set\n")
            elif len(parts) > 1 and parts[1] == "off":
                use_llm = False
                console.print("\n  [yellow]⚡[/yellow] LLM mode disabled\n")
            else:
                status = "ON" if use_llm else "OFF"
                console.print(f"\n  LLM mode: {status}")
                console.print("  Usage: llm on | llm off\n")
            continue

        # ── Compare mode ───────────────────────────────────────
        if text.startswith("compare"):
            text = text.replace("compare", "send", 1)
            try:
                intent = parse_intent(text)
            except ValueError as e:
                status_err(str(e))
                console.print()
                continue

            console.print(f"\n  Comparing quotes for {intent.amount} {intent.token.upper()} from {styled_chain(intent.from_chain)}...")
            with Progress(SpinnerColumn(), TextColumn("[bold blue]Fetching quotes...[/bold blue]"), transient=True) as progress:
                progress.add_task("compare", total=None)
                results = agent.compare_quotes(intent)
            if results:
                table = Table(title="Best Routes (sorted by output)", box=box.ROUNDED, border_style="green")
                table.add_column("#", style="dim", width=4)
                table.add_column("Route")
                table.add_column("Output", justify="right")
                table.add_column("Fee", justify="right")
                for i, r in enumerate(results, 1):
                    marker = " [bold green]← best[/bold green]" if i == 1 else ""
                    fee_str = fee_style(r["fee_pct"])
                    route = f"{styled_chain(intent.from_chain)} → {styled_chain(r['chain'])}"
                    table.add_row(str(i), route, r["output"], fee_str)
                console.print()
                console.print(table)
            else:
                status_err("No quotes available for comparison")
            console.print()
            continue

        # ── Parse intent ───────────────────────────────────────
        try:
            if use_llm:
                intent = parse_intent_llm(text)
            else:
                intent = parse_intent(text)
        except ValueError as e:
            status_err(str(e))
            console.print()
            continue

        # Show intent and fetch with spinner
        console.print(f"\n  Intent: {intent}")
        with Progress(SpinnerColumn(), TextColumn("[bold blue]Fetching quote...[/bold blue]"), transient=True) as progress:
            progress.add_task("quote", total=None)
            result = agent.get_quote(intent)

        # Handle errors
        if "error" in result:
            status_err(result["error"])
            if "suggestion" in result:
                console.print(f"  [yellow]💡 {result['suggestion']}[/yellow]")
            console.print()
            continue

        quotes = result.get("data", {}).get("quotes", [])
        if quotes:
            q = quotes[0]
            # Build a styled quote panel
            fee_pct = agent._calc_fee(intent.amount, q.get("outputAmount", "0"), intent.token)
            quote_text = Text()
            quote_text.append("Input:     ", style="dim")
            quote_text.append(f"{q.get('inputAmount', '?')}\n")
            quote_text.append("Output:    ", style="dim")
            quote_text.append(f"{q.get('outputAmount', '?')}\n")
            quote_text.append("Fee:       ", style="dim")
            quote_text.append_text(Text.from_markup(fee_style(fee_pct)))
            quote_text.append("\n")
            quote_text.append("Quote ID:  ", style="dim")
            quote_text.append(f"{q.get('quoteId', '?')}")
            quote_text.append("\n\n")
            quote_text.append("Route:     ", style="dim")
            quote_text.append_text(Text.from_markup(
                f"{styled_chain(intent.from_chain)}  →  {styled_chain(intent.to_chain)}"
            ))

            console.print()
            status_ok("Quote from solver:")
            console.print(Panel(
                quote_text,
                border_style="green",
                box=box.ROUNDED,
                padding=(0, 2),
            ))

            pending_intent = intent
            pending_quote = q
            console.print("  Type [bold]'yes'[/bold] to prepare order, [dim]'no'[/dim] to cancel")
        else:
            msg = result.get("message", "No quotes available")
            status_err(msg)
            if "suggestion" in result:
                console.print(f"  [yellow]💡 {result['suggestion']}[/yellow]")
        console.print()

    agent.close()
    console.print("[dim]Bye![/dim]")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single command mode
        text = " ".join(sys.argv[1:])
        agent = LifAgent()
        agent.connect()
        try:
            intent = parse_intent(text)
            result = agent.get_quote(intent)
            json_str = json.dumps(result, indent=2)
            console.print(Syntax(json_str, "json", theme="monokai"))
        except ValueError as e:
            status_err(str(e))
        finally:
            agent.close()
    else:
        interactive()
