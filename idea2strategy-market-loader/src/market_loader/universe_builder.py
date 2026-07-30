from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from market_loader.errors import InputError, PermanentAlpacaError
from market_loader.model.catalog import UniverseInstrument

EXCHANGE_TO_MIC = {
    "AMEX": "XASE",
    "ARCA": "ARCX",
    "BATS": "BATS",
    "NASDAQ": "XNAS",
    "NYSE": "XNYS",
    "NYSEARCA": "ARCX",
}


@dataclass(frozen=True, slots=True)
class UniverseCandidate:
    provider_symbol: str
    asset_type: str
    effective_from: date


@dataclass(frozen=True, slots=True)
class UnresolvedCandidate:
    provider_symbol: str
    asset_type: str
    reason: str


def canonical_alpaca_symbol(raw: str) -> str:
    return raw.strip().upper().replace("/", ".")


def read_candidates(stocks: Path, etfs: Path, start: date) -> list[UniverseCandidate]:
    candidates: dict[str, UniverseCandidate] = {}
    with stocks.open("r", encoding="utf-8-sig") as stream:
        for line_number, raw in enumerate(stream, start=1):
            symbol = canonical_alpaca_symbol(raw)
            if not symbol:
                continue
            _add_candidate(
                candidates,
                UniverseCandidate(symbol, "STOCK", start),
                source=f"{stocks}:{line_number}",
            )

    with etfs.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"ticker", "inception_date", "enabled"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise InputError(f"ETF universe is missing columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            if row["enabled"].strip().lower() != "true":
                continue
            symbol = canonical_alpaca_symbol(row["ticker"])
            try:
                inception = date.fromisoformat(row["inception_date"].strip())
            except ValueError as exc:
                raise InputError(f"invalid ETF inception_date at {etfs}:{line_number}") from exc
            _add_candidate(
                candidates,
                UniverseCandidate(symbol, "ETF", max(start, inception)),
                source=f"{etfs}:{line_number}",
            )
    if not candidates:
        raise InputError("universe sources contain no enabled symbols")
    return sorted(candidates.values(), key=lambda item: item.provider_symbol)


def _add_candidate(
    candidates: dict[str, UniverseCandidate],
    candidate: UniverseCandidate,
    *,
    source: str,
) -> None:
    existing = candidates.get(candidate.provider_symbol)
    if existing is not None and existing.asset_type != candidate.asset_type:
        raise InputError(
            f"conflicting asset types for {candidate.provider_symbol} at {source}: "
            f"{existing.asset_type} and {candidate.asset_type}"
        )
    candidates[candidate.provider_symbol] = candidate


def fetch_assets(
    *,
    api_key: str,
    api_secret: str,
    base_url: str,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    if not api_key or not api_secret:
        raise PermanentAlpacaError("Alpaca credentials are required")
    owned = client is None
    http = client or httpx.Client(base_url=base_url, timeout=60)
    try:
        response: httpx.Response | None = None
        for attempt in range(1, 4):
            response = http.get(
                "/v2/assets",
                params={"asset_class": "us_equity"},
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": api_secret,
                },
            )
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            if attempt < 3:
                time.sleep(2 ** (attempt - 1))
        assert response is not None
        if response.status_code in {401, 403}:
            raise PermanentAlpacaError(
                f"Alpaca Assets API authentication failed: HTTP {response.status_code}"
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise PermanentAlpacaError("invalid Alpaca assets response")
        return payload
    except httpx.HTTPError as exc:
        raise PermanentAlpacaError(
            f"Alpaca Assets API request failed: {type(exc).__name__}"
        ) from exc
    finally:
        if owned:
            http.close()


def resolve_candidates(
    candidates: list[UniverseCandidate],
    assets: list[dict[str, Any]],
) -> tuple[list[UniverseInstrument], list[UnresolvedCandidate]]:
    asset_by_symbol = {
        canonical_alpaca_symbol(str(asset.get("symbol", ""))): asset
        for asset in assets
        if asset.get("symbol")
    }
    resolved: list[UniverseInstrument] = []
    unresolved: list[UnresolvedCandidate] = []
    for candidate in candidates:
        asset = asset_by_symbol.get(candidate.provider_symbol)
        if asset is None:
            unresolved.append(
                UnresolvedCandidate(
                    candidate.provider_symbol,
                    candidate.asset_type,
                    "not returned by Alpaca Assets API",
                )
            )
            continue
        exchange = str(asset.get("exchange", "")).upper()
        mic = EXCHANGE_TO_MIC.get(exchange)
        if mic is None:
            unresolved.append(
                UnresolvedCandidate(
                    candidate.provider_symbol,
                    candidate.asset_type,
                    f"unsupported Alpaca exchange: {exchange or '<empty>'}",
                )
            )
            continue
        resolved.append(
            UniverseInstrument(
                provider_symbol=candidate.provider_symbol,
                asset_type=candidate.asset_type,
                primary_exchange_mic=mic,
                effective_from=candidate.effective_from,
                effective_to=None,
                support_status="ACTIVE",
                instrument_id=None,
            )
        )
    return resolved, unresolved


def write_universe(path: Path, rows: list[UniverseInstrument], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise InputError(f"output already exists (use --overwrite): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(
                [
                    "provider_symbol",
                    "asset_type",
                    "primary_exchange_mic",
                    "effective_from",
                    "effective_to",
                    "support_status",
                    "instrument_id",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row.provider_symbol,
                        row.asset_type,
                        row.primary_exchange_mic,
                        row.effective_from.isoformat(),
                        row.effective_to.isoformat() if row.effective_to else "",
                        row.support_status,
                        row.instrument_id or "",
                    ]
                )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_unresolved(path: Path, rows: list[UnresolvedCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["provider_symbol", "asset_type", "reason"])
        for row in rows:
            writer.writerow([row.provider_symbol, row.asset_type, row.reason])
