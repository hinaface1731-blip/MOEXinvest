"""Deterministic ISS contract, financial math, identity, and privacy regression tests."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from data_provider.base import DataFetchError, DataFetcherManager
from data_provider.moex_provider import MOEXProvider, is_moex, normalize_moex, rows
from src.services.moex_analytics import bond_analysis, cashflow_yield, equity_indicators
from src.services.moex_analytics import money_weighted_return
from bot.platforms.moex_telegram import MOEXTelegram

FIXTURES = Path(__file__).parent / "fixtures/moex"


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def response(payload, status=200):
    result = Mock(status_code=status, headers={})
    result.json.return_value = payload
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError()
    return result


@pytest.mark.parametrize("code,expected", [("moex:sber", "SBER"), (" YDEX ", "YDEX"), ("X5", "X5"),
    ("RU000A108EH4", "RU000A108EH4"), ("26248", "26248"), ("MOEX:SU26248RMFS3", "SU26248RMFS3")])
def test_normalization(code, expected):
    assert normalize_moex(code) == expected


@pytest.mark.parametrize("code", ["", "../SBER", "SBER?x=1", "MOEX:", "SBER/AAPL", "a" * 33])
def test_bad_identity(code):
    with pytest.raises(ValueError):
        normalize_moex(code)


def test_foreign_ticker_not_claimed():
    assert not is_moex("AAPL") and not is_moex("SBER") and is_moex("MOEX:SBER")


def test_real_instrument_contract():
    session = Mock()
    session.get.return_value = response(fixture("sber"))
    p = MOEXProvider(session, interval=0)
    instrument = p.instrument("SBER")
    assert instrument["isin"] == "RU0009029540"
    assert instrument["board"] == "TQBR"
    assert instrument["currency"] == "RUB"
    instrument["description"].clear()
    assert p.instrument("SBER")["name"]
    assert session.get.call_count == 1


def test_bond_series_resolved_not_guessed():
    session = Mock()
    session.get.side_effect = [response(fixture("ofz248")), response(fixture("bond"))]
    inst = MOEXProvider(session, interval=0).instrument("26248")
    assert inst["secid"] == "SU26248RMFS3" and inst["isin"] == "RU000A108EH4"


def test_unknown_security_not_synthesized():
    session = Mock()
    session.get.return_value = response({"description": {"columns": ["name", "value"], "data": []}})
    with pytest.raises(ValueError):
        MOEXProvider(session, interval=0).instrument("UNKNOWN")


def test_schema_validation():
    with pytest.raises(DataFetchError):
        rows({"candles": {"columns": ["a"], "data": [[1, 2]]}}, "candles")
    with pytest.raises(DataFetchError):
        rows(fixture("sber"), "dividends")  # ISS can return valid JSON for an unsupported path.


def test_pages_use_returned_row_count():
    p = MOEXProvider(interval=0)
    empty = {"coupons": {"columns": fixture("coupons")["coupons"]["columns"], "data": []}}
    p.get = Mock(side_effect=[fixture("coupons"), fixture("coupons_page2"), empty])
    result = p.pages("unused", "coupons", start_key="coupons.start")
    assert len(result) == 32
    assert [c.kwargs['coupons.start'] for c in p.get.call_args_list] == [0, 20, 32]


def test_ignored_pagination_fails_closed():
    p = MOEXProvider(interval=0)
    p.get = Mock(return_value=fixture("coupons"))
    with pytest.raises(DataFetchError, match="пагинацию"):
        p.pages("unused", "coupons")


def test_retry_429_then_success():
    session = Mock()
    session.get.side_effect = [response({}, 429), response(fixture("sber"))]
    with patch("data_provider.moex_provider.time.sleep"):
        assert MOEXProvider(session, interval=0).instrument("SBER")["secid"] == "SBER"
    assert session.get.call_count == 2


def test_nonretryable_status():
    session = Mock()
    session.get.return_value = response({}, 404)
    with pytest.raises(DataFetchError):
        MOEXProvider(session, interval=0).get("missing")
    assert session.get.call_count == 1


def test_retry_timeout_bounded():
    session = Mock()
    session.get.side_effect = requests.Timeout()
    with pytest.raises(DataFetchError):
        MOEXProvider(session, interval=0, retries=2).get("timeout")
    assert session.get.call_count == 2


def bond_quote():
    p = MOEXProvider(interval=0)
    p.get = Mock(side_effect=[fixture("bond"), fixture("bondquote")])
    return p.snapshot("SU26248RMFS3")


def test_quote_missing_last_never_uses_previous_price():
    raw = fixture("bondquote")
    raw["marketdata"]["data"][0][raw["marketdata"]["columns"].index("LAST")] = None
    p = MOEXProvider(interval=0)
    p.get = Mock(side_effect=[fixture("bond"), raw])
    q = p.snapshot("SU26248RMFS3")
    assert q["price"] is None and q["status"] == "unavailable"


def test_bond_price_is_percent_and_metadata_present():
    q = bond_quote()
    assert q["price_unit"] == "percent_of_face"
    assert q["timestamp"] and q["source"].startswith("https://iss.moex.com/")


def test_no_foreign_fallback_for_explicit_moex():
    manager = DataFetcherManager.__new__(DataFetcherManager)
    provider = Mock()
    provider.instrument.return_value = {"market": "shares"}
    provider.get_daily_data.side_effect = DataFetchError("offline")
    with patch("data_provider.moex_provider.get_moex_provider", return_value=provider):
        with pytest.raises(DataFetchError, match="offline"):
            manager.get_daily_data("MOEX:SBER")


def test_bonds_rejected_by_equity_pipeline():
    manager = DataFetcherManager.__new__(DataFetcherManager)
    provider = Mock()
    provider.instrument.return_value = {"market": "bonds"}
    with patch("data_provider.moex_provider.get_moex_provider", return_value=provider):
        with pytest.raises(ValueError, match="Bond"):
            manager.get_daily_data("MOEX:SU26248RMFS3")


def test_ytm_duration_and_price_sensitivity():
    settled = date(2025, 1, 1)
    result = cashflow_yield(100, [(settled + timedelta(days=365), 110)], settled)
    assert result['yield_pct'] == pytest.approx(10)
    assert result['duration_years'] == pytest.approx(1)
    assert result['modified_duration_years'] == pytest.approx(1 / 1.1)
    assert result['price_change_plus_100bp_pct'] < 0


def test_coupon_yield_is_not_ytm():
    settled = date(2025, 1, 1)
    result = cashflow_yield(90, [(settled + timedelta(days=365), 105)], settled)
    assert result['yield_pct'] == pytest.approx(100 * (105 / 90 - 1))
    assert result['yield_pct'] != pytest.approx(100 * 5 / 90)


def test_negative_yield_supported():
    settled = date(2025, 1, 1)
    assert cashflow_yield(110, [(settled + timedelta(days=365), 100)], settled)['yield_pct'] < 0


def test_unknown_coupon_does_not_produce_yield():
    q = bond_quote()
    schedule = {k: rows(fixture('coupons'), k) for k in ('coupons', 'amortizations', 'offers')}
    schedule['coupons'] += rows(fixture('coupons_page2'), 'coupons')
    schedule['coupons'][-1]['value'] = None
    assert bond_analysis(q, schedule)['calculated'] is None


def test_real_ofz_complete_schedule_calculates():
    q = bond_quote()
    schedule = {k: rows(fixture('coupons'), k) for k in ('coupons', 'amortizations', 'offers')}
    schedule['coupons'] += rows(fixture('coupons_page2'), 'coupons')
    result = bond_analysis(q, schedule)
    assert result['dirty_price'] > result['clean_price_pct'] * result['face_value'] / 100
    assert result['calculated'] is not None
    assert result['calculated']['duration_years'] > 0


def test_empty_history_has_no_indicators():
    assert equity_indicators([])['status'] == 'unavailable'


def test_flat_history_and_lookback():
    candles = [{'begin': str(date(2025, 1, 1) + timedelta(days=i)), 'open': 100, 'high': 101,
                'low': 99, 'close': 100, 'volume': 10} for i in range(60)]
    metrics = equity_indicators(candles)['indicators']
    assert metrics['sma50'] == 100
    assert metrics['atr14'] == 2
    assert metrics['MACD_DIF'] == 0
    assert metrics['max_drawdown_pct'] == 0
    assert equity_indicators(candles[:5])['indicators']['sma20'] is None


@pytest.mark.parametrize('allowed,user,chat_type,chat_id', [([], 1, 'private', 1), (['1'], 2, 'private', 2),
    (['1'], 1, 'group', -2), (['1'], 1, 'private', 2)])
def test_telegram_authorizes_before_access(allowed, user, chat_type, chat_id):
    service = Mock()
    bot = MOEXTelegram(allowed_ids=allowed, service=service, sender=Mock())
    assert bot.handle({'message': {'from': {'id': user}, 'chat': {'id': chat_id, 'type': chat_type}, 'text': '/portfolio'}}) is None
    service.portfolio.assert_not_called()


def test_telegram_help_never_calls_financial_service():
    service = Mock()
    bot = MOEXTelegram(allowed_ids=['1'], service=service, sender=Mock())
    text = bot.handle({'message': {'from': {'id': 1}, 'chat': {'id': 1, 'type': 'private'}, 'text': '/help'}})
    assert '/bond' in text
    assert not service.mock_calls


def test_xirr_does_not_count_deposit_as_profit():
    events = [{"event_date": "2025-01-01", "direction": "in", "amount": 1000}]
    assert money_weighted_return(events, 1100, date(2026, 1, 1)) == pytest.approx(10)
    events.append({"event_date": "2026-01-01", "direction": "in", "amount": 1000})
    assert money_weighted_return(events, 2100, date(2026, 1, 1)) == pytest.approx(10)


def test_xirr_insufficient_history():
    assert money_weighted_return([], 100, date(2026, 1, 1)) is None
    assert money_weighted_return([{"event_date": "2026-01-01", "direction": "in", "amount": 100}], 100, date(2026, 1, 1)) is None


@pytest.fixture
def portfolio_service(tmp_path, monkeypatch):
    from src.config import Config
    from src.storage import DatabaseManager
    from src.services.portfolio_service import PortfolioService
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ENV_FILE", str(tmp_path / "absent.env"))
    monkeypatch.setenv("ENABLE_REALTIME_QUOTE", "false")
    Config.reset_instance()
    DatabaseManager.reset_instance()
    service = PortfolioService()
    yield service
    DatabaseManager.reset_instance()
    Config.reset_instance()


def test_ruble_portfolio_cashflows_and_coupon(portfolio_service):
    service = portfolio_service
    account = service.create_account(name="RU", broker=None, market="ru", base_currency="RUB")
    aid = account["id"]
    on = date.today()
    service.record_cash_ledger(account_id=aid, event_date=on, direction="in", amount=10000)
    service.record_trade(account_id=aid, symbol="MOEX:SU26248RMFS3", trade_date=on,
                         side="buy", quantity=10, price=900, fee=10, market="ru", currency="RUB", trade_uid="first")
    service.record_corporate_action(account_id=aid, symbol="MOEX:SU26248RMFS3", effective_date=on + timedelta(days=1),
        action_type="coupon", market="ru", currency="RUB", cash_dividend_per_share=50)
    with patch.object(service, '_prefetch_realtime_position_prices', return_value={'MOEX:SU26248RMFS3': (900, 'moex')}):
        snapshot = service.get_portfolio_snapshot(account_id=aid)
    assert snapshot['currency'] == 'RUB'
    assert snapshot['total_cash'] == pytest.approx(990)
    assert snapshot['total_equity'] == pytest.approx(9990)
    future = service.get_portfolio_snapshot(account_id=aid, as_of=on + timedelta(days=1), include_realtime=False)
    assert future['total_cash'] == pytest.approx(1490)  # Coupon income, not an external deposit.
    flows = service.list_cash_ledger_events(account_id=aid)
    assert flows['total'] == 1
    from src.services.portfolio_service import PortfolioConflictError
    with pytest.raises(PortfolioConflictError):
        service.record_trade(account_id=aid, symbol="MOEX:SU26248RMFS3", trade_date=on,
                             side="buy", quantity=10, price=900, trade_uid="first")


def test_moex_api_rejects_nan_and_auth_protects_private_routes(portfolio_service):
    from fastapi.testclient import TestClient
    from api.app import create_app
    with patch('api.middlewares.auth.is_auth_enabled', return_value=True):
        client = TestClient(create_app())
        assert client.get('/api/v1/moex/portfolio').status_code == 401
        assert client.post('/api/v1/moex/accounts', json={'name': 'private'}).status_code == 401
    from api.v1.endpoints.moex import Trade
    with pytest.raises(ValueError):
        Trade(account_id=1, symbol='SBER', trade_date=date.today(), side='buy', quantity=1, price=float('nan'), trade_uid='bad')


@pytest.mark.parametrize("file_value,expected", [(None, True), ("false", False), ("true", True)])
def test_container_auth_environment_and_editable_file(monkeypatch, tmp_path, file_value, expected):
    from fastapi.testclient import TestClient
    from api.app import create_app
    import src.auth as auth
    env_path = tmp_path / "container.env"
    if file_value is not None:
        env_path.write_text(f"ADMIN_AUTH_ENABLED={file_value}\n")
    monkeypatch.setenv("ENV_FILE", str(env_path))
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "true")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "private.db"))
    monkeypatch.setattr(auth, "_auth_enabled", None)
    assert auth.is_auth_enabled() is expected
    if expected:
        client = TestClient(create_app())
        assert client.get('/api/v1/auth/status').json()['authEnabled'] is True
        assert client.get('/api/v1/moex/portfolio').status_code == 401
        assert client.post('/api/v1/moex/accounts', json={'name': 'private'}).status_code == 401


def test_future_deposit_not_counted_in_current_profit(portfolio_service):
    from src.services.moex_service import MOEXService
    s = portfolio_service
    a = s.create_account(name='RUB', broker=None, market='ru', base_currency='RUB')
    s.record_cash_ledger(account_id=a['id'], event_date=date.today(), direction='in', amount=1000)
    s.record_cash_ledger(account_id=a['id'], event_date=date.today() + timedelta(days=1), direction='in', amount=2000)
    with patch('src.services.portfolio_service.PortfolioService', return_value=s):
        result = MOEXService(provider=Mock()).portfolio()
    assert result['total_equity'] == 1000
    assert result['net_contributions'] == 1000
    assert result['profit'] == 0


def test_cbr_html_contracts_and_observation_dates():
    from datetime import datetime
    from src.services.russian_macro import _macro
    def fetch(url):
        if url.endswith('/infl/'):
            return Mock(text=(FIXTURES / 'cbr-inflation.html').read_text())
        if url.endswith('/cal_mp/'):
            return Mock(text=(FIXTURES / 'cbr-calendar.html').read_text())
        raise requests.Timeout()
    _macro.cache_clear()
    with patch('src.services.russian_macro._fetch', side_effect=fetch), patch('src.services.russian_macro.datetime', wraps=datetime) as clock:
        clock.now.return_value = datetime(2026, 11, 17)
        result = _macro(0)
    inflation = next(o for o in result['observations'] if o['name'] == 'Инфляция')
    assert inflation['observed_at'] == '2026-09'
    assert inflation['published_at'] is None
    assert result['events'] and result['events'][0]['date'] >= '2026-11-17'
    assert result['events'] == sorted(result['events'], key=lambda e: e['date'])
    _macro.cache_clear()


def test_llm_unknown_fact_ids_are_rejected():
    from src.services.moex_service import MOEXService
    market = {'instruments': [], 'fetched_at': '2026-11-17T12:00:00+03:00', 'errors': []}
    with patch('src.services.moex_service.russian_macro', return_value={'observations': []}), \
         patch('src.analyzer.GeminiAnalyzer') as analyzer:
        analyzer.return_value.generate_text.return_value = '{"fact_ids":["invented_price"],"risk_ids":[]}'
        report = MOEXService().report(use_ai=True, market=market)
    assert report['ai_status'] == 'rejected_response'
    assert report['facts'] == []


def test_public_export_does_not_read_private_portfolio_or_watchlist(tmp_path):
    from scripts.export_moex_demo import export
    market = {'instruments': [{'secid': 'SBER'}], 'errors': []}
    with patch('scripts.export_moex_demo.MOEXService') as factory, \
         patch('scripts.export_moex_demo.russian_macro', return_value={}):
        service = factory.return_value
        service.market.return_value = market
        service.instrument.return_value = {'quote': {'secid': 'SBER'}}
        service.report.return_value = {'facts': []}
        export(tmp_path / 'public.json')
        service.portfolio.assert_not_called()
        passed_watch = service.market.call_args.kwargs['watch']
        assert set(passed_watch) == {'equities', 'bonds', 'indices'}
        assert passed_watch['equities'] == ['SBER', 'YDEX', 'X5']
        output = json.loads((tmp_path / 'public.json').read_text())
        assert set(output) == {'demo', 'generated_at', 'market', 'instruments', 'macro', 'report', 'notice'}


@pytest.mark.network
def test_live_moex_contract():
    p = MOEXProvider()
    q = p.snapshot('SBER')
    assert q['secid'] == 'SBER' and q['isin'] == 'RU0009029540'
    assert p.bond_schedule('26248')['coupons']
