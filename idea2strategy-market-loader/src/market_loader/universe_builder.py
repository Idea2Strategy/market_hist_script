from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
SUPPORTED_MICS = frozenset(EXCHANGE_TO_MIC.values())


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


@dataclass(frozen=True, slots=True)
class HistoricalAssetOverride:
    provider_symbol: str
    primary_exchange_mic: str


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


def read_historical_overrides(path: Path | None) -> dict[str, HistoricalAssetOverride]:
    if path is None:
        return {}
    result: dict[str, HistoricalAssetOverride] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"provider_symbol", "primary_exchange_mic"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise InputError(f"historical overrides are missing columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            symbol = canonical_alpaca_symbol(row["provider_symbol"])
            mic = row["primary_exchange_mic"].strip().upper()
            if not symbol:
                raise InputError(f"empty override symbol at {path}:{line_number}")
            if mic not in SUPPORTED_MICS:
                raise InputError(f"unsupported override MIC at {path}:{line_number}: {mic}")
            if symbol in result:
                raise InputError(f"duplicate historical override at {path}:{line_number}: {symbol}")
            result[symbol] = HistoricalAssetOverride(symbol, mic)
    return result


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


def fetch_assets_by_symbol(
    *,
    symbols: list[str],
    api_key: str,
    api_secret: str,
    base_url: str,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    if not api_key or not api_secret:
        raise PermanentAlpacaError("Alpaca credentials are required")
    owned = client is None
    http = client or httpx.Client(base_url=base_url, timeout=30)
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }
    found: list[dict[str, Any]] = []
    try:
        for symbol in symbols:
            response = http.get(f"/v2/assets/{quote(symbol, safe='')}", headers=headers)
            if response.status_code == 404:
                continue
            if response.status_code in {401, 403}:
                raise PermanentAlpacaError(
                    f"Alpaca asset lookup authentication failed: HTTP {response.status_code}"
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise PermanentAlpacaError(f"invalid Alpaca asset response for {symbol}")
            found.append(payload)
        return found
    except httpx.HTTPError as exc:
        raise PermanentAlpacaError(
            f"Alpaca individual asset lookup failed: {type(exc).__name__}"
        ) from exc
    finally:
        if owned:
            http.close()


def missing_asset_symbols(
    candidates: list[UniverseCandidate],
    assets: list[dict[str, Any]],
) -> list[str]:
    known = {
        canonical_alpaca_symbol(str(asset.get("symbol", "")))
        for asset in assets
        if asset.get("symbol")
    }
    return [item.provider_symbol for item in candidates if item.provider_symbol not in known]


def historical_probe_symbols(
    candidates: list[UniverseCandidate],
    assets: list[dict[str, Any]],
    overrides: dict[str, HistoricalAssetOverride],
) -> list[str]:
    asset_by_symbol = {
        canonical_alpaca_symbol(str(asset.get("symbol", ""))): asset
        for asset in assets
        if asset.get("symbol")
    }
    result: list[str] = []
    for candidate in candidates:
        asset = asset_by_symbol.get(candidate.provider_symbol)
        exchange = str(asset.get("exchange", "")).upper() if asset is not None else ""
        needs_override = asset is None or EXCHANGE_TO_MIC.get(exchange) is None
        is_inactive = (
            asset is not None and str(asset.get("status", "")).strip().lower() == "inactive"
        )
        if is_inactive or (needs_override and candidate.provider_symbol in overrides):
            result.append(candidate.provider_symbol)
    return result


def fetch_last_sip_bar_dates(
    *,
    symbols: list[str],
    start: date,
    end: date,
    api_key: str,
    api_secret: str,
    base_url: str,
    client: httpx.Client | None = None,
) -> dict[str, date]:
    if not api_key or not api_secret:
        raise PermanentAlpacaError("Alpaca credentials are required")
    owned = client is None
    http = client or httpx.Client(base_url=base_url, timeout=30)
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }
    result: dict[str, date] = {}
    try:
        for symbol in symbols:
            response = http.get(
                f"/v2/stocks/{quote(symbol, safe='')}/bars",
                headers=headers,
                params={
                    "timeframe": "1Day",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "adjustment": "raw",
                    "feed": "sip",
                    "sort": "desc",
                    "limit": 1,
                    "asof": "-",
                },
            )
            if response.status_code in {401, 403}:
                raise PermanentAlpacaError(
                    f"Alpaca SIP history authentication failed: HTTP {response.status_code}"
                )
            response.raise_for_status()
            payload = response.json()
            bars = payload.get("bars") if isinstance(payload, dict) else None
            if not isinstance(bars, list):
                raise PermanentAlpacaError(f"invalid Alpaca historical bars response for {symbol}")
            if not bars:
                continue
            timestamp = bars[0].get("t") if isinstance(bars[0], dict) else None
            if not isinstance(timestamp, str):
                raise PermanentAlpacaError(f"missing Alpaca bar timestamp for {symbol}")
            result[symbol] = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()
        return result
    except (httpx.HTTPError, ValueError) as exc:
        raise PermanentAlpacaError(
            f"Alpaca historical availability check failed: {type(exc).__name__}"
        ) from exc
    finally:
        if owned:
            http.close()


def resolve_candidates(
    candidates: list[UniverseCandidate],
    assets: list[dict[str, Any]],
    overrides: dict[str, HistoricalAssetOverride] | None = None,
    last_bar_dates: dict[str, date] | None = None,
) -> tuple[list[UniverseInstrument], list[UnresolvedCandidate]]:
    overrides = overrides or {}
    last_bar_dates = last_bar_dates or {}
    asset_by_symbol = {
        canonical_alpaca_symbol(str(asset.get("symbol", ""))): asset
        for asset in assets
        if asset.get("symbol")
    }
    resolved: list[UniverseInstrument] = []
    unresolved: list[UnresolvedCandidate] = []
    for candidate in candidates:
        asset = asset_by_symbol.get(candidate.provider_symbol)
        exchange = str(asset.get("exchange", "")).upper() if asset is not None else ""
        mic = EXCHANGE_TO_MIC.get(exchange)
        override = overrides.get(candidate.provider_symbol)
        needs_override = asset is None or mic is None
        if needs_override and override is None:
            reason = (
                "not returned by Alpaca Assets API"
                if asset is None
                else f"unsupported Alpaca exchange: {exchange or '<empty>'}"
            )
            unresolved.append(
                UnresolvedCandidate(
                    candidate.provider_symbol,
                    candidate.asset_type,
                    reason,
                )
            )
            continue
        if override is not None and needs_override:
            mic = override.primary_exchange_mic
        assert mic is not None
        is_inactive = (
            asset is not None and str(asset.get("status", "")).strip().lower() == "inactive"
        )
        effective_to = last_bar_dates.get(candidate.provider_symbol)
        if (needs_override or is_inactive) and effective_to is None:
            unresolved.append(
                UnresolvedCandidate(
                    candidate.provider_symbol,
                    candidate.asset_type,
                    "no historical SIP bars found for inactive or overridden symbol",
                )
            )
            continue
        if effective_to is not None and effective_to < candidate.effective_from:
            unresolved.append(
                UnresolvedCandidate(
                    candidate.provider_symbol,
                    candidate.asset_type,
                    "last historical SIP bar is before the requested universe start",
                )
            )
            continue
        resolved.append(
            UniverseInstrument(
                provider_symbol=candidate.provider_symbol,
                asset_type=candidate.asset_type,
                primary_exchange_mic=mic,
                effective_from=candidate.effective_from,
                effective_to=effective_to if needs_override or is_inactive else None,
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
