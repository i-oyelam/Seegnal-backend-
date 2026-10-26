"""Seegnal API backend starter. See README/instructions in chat before deploying."""
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Seegnal API", version="0.1.0")

# Set ALLOWED_ORIGINS to your exact Netlify site URL in production.
_origins = os.getenv("ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in _origins.split(",") if x.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

DEX_BASE = "https://api.dexscreener.com"
GOPLUS_BASE = "https://api.gopluslabs.io/api/v1"


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "Seegnal API", "status": "online", "docs": "/docs"}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "seegnal-api"}


@app.get("/api/records")
async def records(
    mode: str = Query("boosts", pattern="^(boosts|profiles)$"),
    chain: str = Query("base", min_length=1, max_length=40),
    limit: int = Query(12, ge=1, le=30),
) -> dict[str, Any]:
    """Fetch latest DEX Screener boosts or token profiles; these are discovery signals, not safety ratings."""
    endpoint = (
        f"{DEX_BASE}/token-boosts/latest/v1"
        if mode == "boosts"
        else f"{DEX_BASE}/token-profiles/latest/v1"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"DEX Screener request failed: {exc}") from exc

    if isinstance(payload, dict):
        payload = payload.get("data", [])
    if not isinstance(payload, list):
        payload = []

    filtered = [
        item for item in payload
        if isinstance(item, dict)
        and str(item.get("chainId", "")).lower() == chain.lower()
    ][:limit]
    return {
        "mode": mode,
        "chain": chain,
        "count": len(filtered),
        "notice": "Discovery/visibility data only; not a quality or safety rating.",
        "records": filtered,
    }


@app.get("/api/security")
async def security(
    chain: str = Query(..., min_length=1, max_length=40),
    address: str = Query(..., min_length=3, max_length=128),
) -> dict[str, Any]:
    """Fetch GoPlus token-security data for a supported EVM chain."""
    chain_ids = {
        "ethereum": "1", "eth": "1", "bsc": "56", "bnb": "56",
        "polygon": "137", "arbitrum": "42161", "optimism": "10",
        "base": "8453", "avalanche": "43114", "avax": "43114",
        "fantom": "250", "opbnb": "204", "linea": "59144",
        "scroll": "534352", "mantle": "5000", "ronin": "2020",
    }
    chain_id = chain_ids.get(chain.lower())
    if not chain_id:
        raise HTTPException(status_code=400, detail=f"Unsupported chain alias: {chain}")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{GOPLUS_BASE}/token_security/{chain_id}",
                params={"contract_addresses": address},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"GoPlus request failed: {exc}") from exc

    return {
        "chain": chain,
        "chain_id": chain_id,
        "address": address,
        "source": "GoPlus",
        "data": payload,
        "interpretation_note": (
            "Provider output can be incomplete. A missing flag is not proof that a token is safe; "
            "verify the contract address and chain."
        ),
    }
