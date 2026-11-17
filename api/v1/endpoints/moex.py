"""MOEX routes protected by the existing application auth middleware."""
import csv
from datetime import date
import io
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from data_provider.base import DataFetchError
from src.services.moex_service import MOEXService, ROOT, list_reports, save_report, watchlist
from src.services.portfolio_service import PortfolioService, PortfolioConflictError
from src.services.russian_macro import russian_macro

router = APIRouter()


def run(operation):
    try:
        return operation()
    except DataFetchError as exc:
        raise HTTPException(503, str(exc)) from exc
    except PortfolioConflictError as exc:
        raise HTTPException(409, "Операция с этим идентификатором уже существует") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/market")
def market():
    return run(lambda: MOEXService().market())


@router.get("/instruments/{symbol}")
def instrument(symbol: str, days: int = Query(365, ge=7, le=1500)):
    return run(lambda: MOEXService().instrument(symbol, days))


@router.get("/macro")
def macro():
    return russian_macro()


@router.get("/portfolio")
def portfolio():
    return run(lambda: MOEXService().portfolio())


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Account(Input):
    name: str = Field(min_length=1, max_length=100)


@router.post("/accounts")
def create_account(body: Account):
    return run(lambda: PortfolioService().create_account(name=body.name, broker=None, market="ru", base_currency="RUB"))


def ru_account(service, account_id):
    if not any(a["id"] == account_id and a["market"] == "ru" and a["base_currency"] == "RUB" for a in service.list_accounts()):
        raise ValueError("Не найден рублёвый счёт российского рынка")


class Trade(Input):
    account_id: int = Field(gt=0)
    symbol: str = Field(min_length=1, max_length=32)
    trade_date: date
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    price: float = Field(gt=0, description="Фактическая полная цена за бумагу в RUB, для облигаций включая НКД")
    fee: float = Field(0, ge=0)
    tax: float = Field(0, ge=0)
    price_basis: Literal["rub", "dirty_rub"] = "rub"
    trade_uid: str = Field(min_length=1, max_length=100)


def record_trade(body):
    service = PortfolioService()
    ru_account(service, body.account_id)
    inst = MOEXService().provider.instrument(body.symbol)
    if inst["market"] == "index" or inst["currency"] != "RUB":
        raise ValueError("Для портфеля требуется рублёвая акция, фонд или облигация")
    if inst["market"] == "bonds" and body.price_basis != "dirty_rub":
        raise ValueError("Укажите полную цену облигации в рублях, включая НКД, а не процент от номинала")
    return service.record_trade(account_id=body.account_id, symbol=inst["symbol"], trade_date=body.trade_date,
                                side=body.side, quantity=body.quantity, price=body.price, fee=body.fee,
                                tax=body.tax, market="ru", currency="RUB", trade_uid=body.trade_uid)


@router.post("/trades")
def trade(body: Trade):
    return run(lambda: record_trade(body))


class Cash(Input):
    account_id: int = Field(gt=0)
    event_date: date
    direction: Literal["in", "out"]
    amount: float = Field(gt=0)


@router.post("/cash")
def cash(body: Cash):
    def operation():
        service = PortfolioService()
        ru_account(service, body.account_id)
        return service.record_cash_ledger(**body.model_dump(), currency="RUB")
    return run(operation)


class Income(Input):
    account_id: int = Field(gt=0)
    symbol: str = Field(min_length=1, max_length=32)
    effective_date: date
    action_type: Literal["coupon", "cash_dividend"]
    amount_per_security: float = Field(gt=0)


@router.post("/income")
def income(body: Income):
    def operation():
        service = PortfolioService()
        ru_account(service, body.account_id)
        instrument = MOEXService().provider.instrument(body.symbol)
        if body.action_type == "coupon" and instrument["market"] != "bonds":
            raise ValueError("Купон применим только к облигациям")
        return service.record_corporate_action(account_id=body.account_id, symbol=instrument["symbol"],
            effective_date=body.effective_date, action_type=body.action_type, market="ru", currency="RUB",
            cash_dividend_per_share=body.amount_per_security)
    return run(operation)


class CsvImport(Input):
    account_id: int = Field(gt=0)
    content: str = Field(max_length=1_000_000)


@router.post("/import")
def import_csv(body: CsvImport):
    def operation():
        parsed = list(csv.DictReader(io.StringIO(body.content.lstrip("\ufeff"))))
        if not parsed or len(parsed) > 1000:
            raise ValueError("CSV должен содержать от 1 до 1000 операций")
        if any(None in row or "account_id" in row for row in parsed):
            raise ValueError("Проверьте заголовок CSV; счёт выбирается отдельно от файла")
        # Validate every row before writes; service transactions and trade_uid protect duplicates.
        trades = [Trade(**row, account_id=body.account_id) for row in parsed]
        results = []
        for index, row in enumerate(trades, 2):
            try:
                results.append({"row": index, "status": "imported", **record_trade(row)})
            except (ValueError, DataFetchError, PortfolioConflictError) as exc:
                results.append({"row": index, "status": "error", "error": str(exc)})
        return {"rows": results, "notice": "Каждая строка — отдельная транзакция; проверяйте статусы строк."}
    return run(operation)


class ReportInput(Input):
    period: Literal["morning", "evening"] = "evening"
    use_ai: bool = False


@router.get("/reports")
def reports():
    return list_reports()


@router.post("/reports")
def report(body: ReportInput):
    if body.use_ai and os.getenv("MOEX_ENABLE_AI", "false").lower() != "true":
        raise HTTPException(409, "ИИ отключён: настройте провайдера и MOEX_ENABLE_AI в окружении сервера")
    return run(lambda: save_report(MOEXService().report(body.period, use_ai=body.use_ai)))


class Watchlist(Input):
    equities: list[str] = Field(max_length=40)
    bonds: list[str] = Field(max_length=40)
    indices: list[str] = Field(max_length=40)


@router.get("/settings")
def settings():
    return {"watchlist": watchlist(), "ai_enabled": os.getenv("MOEX_ENABLE_AI", "false").lower() == "true",
            "telegram_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))}


@router.put("/settings/watchlist")
def update_watchlist(body: Watchlist):
    def operation():
        service = MOEXService()
        value = body.model_dump()
        for group in value:
            expected = {"equities": "shares", "bonds": "bonds", "indices": "index"}[group]
            for i, symbol in enumerate(value[group]):
                inst = service.provider.instrument(symbol)
                if inst["market"] != expected:
                    raise ValueError(f"Неверный тип инструмента {symbol}")
                value[group][i] = inst["secid"]
        path = Path(os.getenv("MOEX_WATCHLIST_PATH", str(ROOT / "data/moex_watchlist.json")))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return value
    return run(operation)
