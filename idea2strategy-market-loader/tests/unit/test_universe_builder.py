from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx

from market_loader.model.catalog import read_universe
from market_loader.universe_builder import (
    UniverseCandidate,
    canonical_alpaca_symbol,
    fetch_assets_by_symbol,
    fetch_last_sip_bar_dates,
    historical_probe_symbols,
    missing_asset_symbols,
    read_candidates,
    read_historical_overrides,
    resolve_candidates,
    write_universe,
)


def test_builds_stock_and_enabled_etf_universe(tmp_path: Path) -> None:
    stocks = tmp_path / "stocks.txt"
    stocks.write_text("AAPL\nBRK/B\n", encoding="utf-8")
    etfs = tmp_path / "etfs.csv"
    etfs.write_text(
        "ticker,inception_date,enabled\n"
        "SPY,1993-01-22,true\n"
        "NEW,2020-05-26,true\n"
        "OFF,2010-01-01,false\n",
        encoding="utf-8",
    )
    start = date(2016, 7, 30)

    candidates = read_candidates(stocks, etfs, start)
    resolved, unresolved = resolve_candidates(
        candidates,
        [
            {"symbol": "AAPL", "exchange": "NASDAQ"},
            {"symbol": "BRK.B", "exchange": "NYSE"},
            {"symbol": "SPY", "exchange": "ARCA"},
            {"symbol": "NEW", "exchange": "NYSEARCA"},
        ],
    )

    assert unresolved == []
    assert canonical_alpaca_symbol("brk/b") == "BRK.B"
    assert {row.provider_symbol: row.primary_exchange_mic for row in resolved} == {
        "AAPL": "XNAS",
        "BRK.B": "XNYS",
        "NEW": "ARCX",
        "SPY": "ARCX",
    }
    assert next(row for row in resolved if row.provider_symbol == "NEW").effective_from == date(
        2020, 5, 26
    )
    output = tmp_path / "universe.csv"
    write_universe(output, resolved, overwrite=False)
    assert len(read_universe(output)) == 4


def test_reports_missing_and_unsupported_assets(tmp_path: Path) -> None:
    stocks = tmp_path / "stocks.txt"
    stocks.write_text("MISSING\nOTCNAME\n", encoding="utf-8")
    etfs = tmp_path / "etfs.csv"
    etfs.write_text("ticker,inception_date,enabled\n", encoding="utf-8")

    candidates = read_candidates(stocks, etfs, date(2016, 1, 1))
    resolved, unresolved = resolve_candidates(
        candidates,
        [{"symbol": "OTCNAME", "exchange": "OTC"}],
    )

    assert resolved == []
    assert [row.provider_symbol for row in unresolved] == ["MISSING", "OTCNAME"]


def test_individual_asset_fallback_keeps_found_and_ignores_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/ABMD"):
            return httpx.Response(
                200,
                json={"symbol": "ABMD", "exchange": "NASDAQ", "status": "inactive"},
            )
        return httpx.Response(404, json={"message": "asset not found"})

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://paper-api.alpaca.markets",
    )
    assets = fetch_assets_by_symbol(
        symbols=["ABMD", "MISSING"],
        api_key="key",
        api_secret=uuid4().hex,
        base_url="https://paper-api.alpaca.markets",
        client=client,
    )

    assert assets == [{"symbol": "ABMD", "exchange": "NASDAQ", "status": "inactive"}]
    candidates = [
        UniverseCandidate("ABMD", "STOCK", date(2016, 1, 1)),
        UniverseCandidate("MISSING", "STOCK", date(2016, 1, 1)),
    ]
    assert missing_asset_symbols(candidates, assets) == ["MISSING"]


def test_historical_override_requires_and_uses_last_sip_bar(tmp_path: Path) -> None:
    overrides_path = tmp_path / "overrides.csv"
    overrides_path.write_text(
        "provider_symbol,primary_exchange_mic,reviewed_at\nSBNY,XNAS,2026-07-30\n",
        encoding="utf-8",
    )
    overrides = read_historical_overrides(overrides_path)
    candidates = [UniverseCandidate("SBNY", "STOCK", date(2016, 1, 1))]
    assets = [{"symbol": "SBNY", "exchange": "OTC", "status": "inactive"}]

    assert historical_probe_symbols(candidates, assets, overrides) == ["SBNY"]
    resolved, unresolved = resolve_candidates(
        candidates,
        assets,
        overrides,
        {"SBNY": date(2023, 3, 10)},
    )

    assert unresolved == []
    assert resolved[0].primary_exchange_mic == "XNAS"
    assert resolved[0].effective_to == date(2023, 3, 10)


def test_historical_sip_probe_uses_exact_symbol_and_returns_last_date() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/SBNY/bars"):
            return httpx.Response(200, json={"bars": [{"t": "2023-03-10T05:00:00Z"}]})
        return httpx.Response(200, json={"bars": []})

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://data.alpaca.markets",
    )
    dates = fetch_last_sip_bar_dates(
        symbols=["SBNY", "MISSING"],
        start=date(2016, 1, 1),
        end=date(2026, 1, 1),
        api_key="key",
        api_secret=uuid4().hex,
        base_url="https://data.alpaca.markets",
        client=client,
    )

    assert dates == {"SBNY": date(2023, 3, 10)}
    assert requests[0].url.params["asof"] == "-"
    assert requests[0].url.params["sort"] == "desc"
    assert requests[0].url.params["limit"] == "1"
