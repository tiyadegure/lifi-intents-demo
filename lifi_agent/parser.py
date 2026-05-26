"""
LI.FI Intents Agent — Intent & policy parsing (regex + LLM).
"""

import json
import logging
import os
import re

import httpx

from .models import CHAINS, CHAIN_ALIASES, Intent, Policy


def parse_policy(text: str) -> Policy:
    """Extract safety policy from natural language.

    Examples:
        "send 10 USDC from Base to Arbitrum only if fee < 0.5%"
        "bridge 50 USDT if route is healthy and fee < 1%"
        "transfer 0.5 ETH if output >= 0.49"
        "avoid Ethereum"
        "prefer cheapest route"
        "do not execute if no quote"
    """
    policy = Policy()
    text_lower = text.lower()

    # Extract fee limit: "fee < 0.5%", "fee under 1%", "max fee 0.3%"
    fee_match = re.search(r'(?:fee|fees?)\s*(?:<|<=|under|below|max(?:imum)?)\s*(\d+\.?\d*)\s*%', text)
    if fee_match:
        policy.max_fee_pct = float(fee_match.group(1))

    # Extract route health requirement: "if route is healthy", "healthy route"
    if re.search(r'(?:route|routes?)\s*(?:is|are)?\s*healthy', text_lower):
        policy.require_healthy_route = True
    if re.search(r'healthy\s*(?:route|routes?)', text_lower):
        policy.require_healthy_route = True

    # Extract minimum output: "output >= 9.95", "min output 9.9", "min output 100"
    output_match = re.search(r'(?:output|min(?:imum)?\s*output)\s*(?:>=|>|at\s*least)?\s*(\d+\.?\d*)', text)
    if output_match and output_match.group(1):
        policy.min_output_amount = float(output_match.group(1))

    # Extract slippage: "slippage < 0.5%", "max slippage 1%"
    slippage_match = re.search(r'slippage\s*(?:<|<=|under|below|max(?:imum)?)\s*(\d+\.?\d*)\s*%', text)
    if slippage_match:
        policy.max_slippage = float(slippage_match.group(1))

    # Extract avoid chains: "avoid Ethereum", "avoid eth and polygon", "avoid Base min output 9.5"
    # Use known chain names to avoid greedy capture issues
    all_chain_names = sorted(set(list(CHAINS.keys()) + list(CHAIN_ALIASES.keys())), key=len, reverse=True)
    chain_pattern = '|'.join(re.escape(c) for c in all_chain_names)
    avoid_match = re.search(
        rf'avoid\s+({chain_pattern})(?:\s*(?:and|,)\s*({chain_pattern}))?',
        text_lower
    )
    if avoid_match:
        for g in avoid_match.groups():
            if g:
                chain = CHAIN_ALIASES.get(g, g)
                if chain in CHAINS and chain not in policy.avoid_chains:
                    policy.avoid_chains.append(chain)

    # Extract prefer cheapest: "prefer cheapest route", "cheapest route"
    if re.search(r'prefer\s+cheapest(?:\s+route)?', text_lower):
        policy.prefer_cheapest = True
    if re.search(r'cheapest\s+route', text_lower):
        policy.prefer_cheapest = True

    # Extract no quote requirement: "do not execute if no quote", "no quote = no execute"
    if re.search(r'do\s+not\s+execute\s+if\s+no\s+quote', text_lower):
        policy.require_quote = True
    if re.search(r'no\s+quote\s*=\s*no\s+execute', text_lower):
        policy.require_quote = True

    # Extract no cross-chain: "same chain only", "no cross-chain"
    if re.search(r'same\s+chain\s+only', text_lower):
        policy.allow_cross_chain = False
    if re.search(r'no\s+cross[- ]chain', text_lower):
        policy.allow_cross_chain = False

    return policy


def parse_intent_with_policy(text: str) -> tuple[Intent, Policy]:
    """Parse both intent and policy from natural language.

    Returns: (Intent, Policy) tuple
    """
    # Extract policy conditions before parsing intent
    # Remove policy clauses from text for intent parsing
    intent_text = re.sub(
        r'\b(?:only\s+)?if\b.*$',
        '',
        text,
        flags=re.IGNORECASE
    ).strip()

    intent = parse_intent(intent_text)
    policy = parse_policy(text)

    return intent, policy


def parse_intent(text: str) -> Intent:
    """Parse natural language into a cross-chain intent.

    Examples:
        "send 10 USDC from Base to Arbitrum"
        "bridge 50 USDT polygon to ethereum"
        "transfer 0.5 ETH from optimism to base"
    """
    text = text.lower().strip()

    # Normalize arrow syntax: "base->arb", "base to arb", "bridge X eth to poly"
    arrow_match = re.search(r'(\w+)\s*(?:->|→)\s*(\w+)', text)
    if arrow_match:
        src, dst = arrow_match.group(1), arrow_match.group(2)
        src_full = CHAIN_ALIASES.get(src, src)
        dst_full = CHAIN_ALIASES.get(dst, dst)
        if src_full in CHAINS and dst_full in CHAINS:
            text = text[:arrow_match.start()] + f"from {src_full} to {dst_full}" + text[arrow_match.end():]

    # Extract amount + token
    amount_match = re.search(r'(\d+\.?\d*)\s*(usdc|usdt|eth|weth)', text)
    if not amount_match:
        raise ValueError("Couldn't find amount and token. Try: 'send 10 USDC from Base to Arbitrum'")
    amount = amount_match.group(1)
    token = amount_match.group(2)  # Keep weth as-is, MCP expects WETH

    # Extract chains by position in text (earliest = from, latest = to)
    chain_positions = []
    for alias, full_name in CHAIN_ALIASES.items():
        pos = text.find(alias)
        # Avoid matching substrings (e.g. "base" inside "database")
        if pos >= 0:
            end = pos + len(alias)
            if (pos == 0 or not text[pos-1].isalpha()) and (end >= len(text) or not text[end].isalpha()):
                chain_positions.append((pos, full_name))
    chain_positions.sort()

    if len(chain_positions) < 2:
        found = [c[1] for c in chain_positions]
        raise ValueError(f"Need two chains. Found: {found}. Supported: {', '.join(CHAINS.keys())}")

    # Use "from X to Y" pattern if available, else use text position
    from_match = re.search(r'from\s+(\w+)', text)
    to_match = re.search(r'to\s+(\w+)', text)

    if from_match:
        src = from_match.group(1)
        if src in CHAINS:
            from_chain = src
        elif src in CHAIN_ALIASES:
            from_chain = CHAIN_ALIASES[src]
        else:
            from_chain = chain_positions[0][1]
    else:
        from_chain = chain_positions[0][1]

    if to_match:
        dst = to_match.group(1)
        if dst in CHAINS:
            to_chain = dst
        elif dst in CHAIN_ALIASES:
            to_chain = CHAIN_ALIASES[dst]
        else:
            to_chain = chain_positions[-1][1]
    else:
        to_chain = chain_positions[-1][1]

    if from_chain == to_chain:
        raise ValueError("Source and destination chains must be different")

    return Intent(from_chain, to_chain, token, amount)


def parse_intent_llm(text: str, api_key: str = None, model: str = "gpt-4o-mini") -> Intent:
    """Parse natural language using LLM for more flexible understanding.

    Requires OPENAI_API_KEY env var or api_key parameter.
    Falls back to regex parser if LLM fails.
    """
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return parse_intent(text)  # Fallback to regex

    try:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{
                    "role": "system",
                    "content": """Extract cross-chain transfer intent. Return JSON:
{"from_chain": "base", "to_chain": "arbitrum", "token": "usdc", "amount": "10"}

Supported chains: ethereum, base, arbitrum, optimism, polygon, bsc, avalanche, zksync, linea, scroll, blast, mantle, sonic
Supported tokens: usdc, usdt, eth

Examples:
- "send 10 USDC base->arb" -> {"from_chain": "base", "to_chain": "arbitrum", "token": "usdc", "amount": "10"}
- "bridge 50 USDT eth to poly" -> {"from_chain": "ethereum", "to_chain": "polygon", "token": "usdt", "amount": "50"}
- "move 0.5 ETH from optimism" -> {"from_chain": "optimism", "to_chain": "arbitrum", "token": "eth", "amount": "0.5"}"""
                }, {
                    "role": "user",
                    "content": text
                }],
                "temperature": 0,
                "max_tokens": 100
            },
            timeout=5
        )

        if response.status_code == 200:
            result = response.json()["choices"][0]["message"]["content"]
            data = json.loads(result)
            return Intent(
                from_chain=data["from_chain"],
                to_chain=data["to_chain"],
                token=data["token"],
                amount=data["amount"]
            )
    except Exception as e:
        logging.debug(f"LLM parsing failed, falling back to regex: {e}")

    return parse_intent(text)  # Fallback to regex
