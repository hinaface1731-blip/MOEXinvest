"""Official ISS adapter. Explicit MOEX identity never falls back to a foreign market."""
from __future__ import annotations

import copy
from datetime import date, datetime
from functools import lru_cache
import math
import re
import threading
import time
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .base import BaseFetcher, DataFetchError
from .realtime_types import RealtimeSource, UnifiedRealtimeQuote

MOSCOW = ZoneInfo("Europe/Moscow")
ISS = "https://iss.moex.com/iss/"


def is_moex(code: str) -> bool:
    return str(code).strip().upper().startswith("MOEX:")


def normalize_moex(code: str) -> str:
    value = str(code).strip().upper()
    if value.startswith("MOEX:"):
        value = value[5:]
    if not re.fullmatch(r"[A-Z0-9_-]{1,32}", value):
        raise ValueError("Некорректный идентификатор MOEX")
    return value


def number(value):
    if value is None or value == "":
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def rows(payload, block):
    table = payload.get(block)
    if not isinstance(table, dict) or not isinstance(table.get("columns"), list) or not isinstance(table.get("data"), list):
        raise DataFetchError(f"ISS: отсутствует таблица {block}")
    if any(len(row) != len(table["columns"]) for row in table["data"]):
        raise DataFetchError(f"ISS: неверная схема {block}")
    return [dict(zip(table["columns"], row)) for row in table["data"]]


class MOEXProvider(BaseFetcher):
    name = "MOEXProvider"
    priority = 0
    allow_empty_daily_data = True

    def __init__(self, session=None, *, ttl=60, interval=0.25, retries=3):
        self.session = session or requests.Session()
        self.ttl, self.interval, self.retries = ttl, interval, retries
        self._cache = {}
        self._lock = threading.RLock()
        self._next_request = 0.0

    def get(self, path, **params):
        params = {"iss.meta": "off", **params}
        key = (path, tuple(sorted(params.items())))
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < self.ttl:
                return copy.deepcopy(hit[1])
            for attempt in range(self.retries):
                time.sleep(max(0, self._next_request - time.monotonic()))
                self._next_request = time.monotonic() + self.interval
                try:
                    response = self.session.get(ISS + path, params=params, timeout=(5, 20))
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt + 1 < self.retries:
                            retry = number(response.headers.get("Retry-After"))
                            time.sleep(min(10, max(0, retry if retry is not None else 2 ** attempt)))
                            continue
                    response.raise_for_status()
                    result = response.json()
                    if not isinstance(result, dict):
                        raise ValueError("Expected JSON object")
                    result["_moex_received_at"] = datetime.now(MOSCOW).isoformat()
                    if len(self._cache) >= 512:
                        self._cache.clear()
                    self._cache[key] = (time.monotonic(), result)
                    return copy.deepcopy(result)
                except (requests.Timeout, requests.ConnectionError) as exc:
                    if attempt + 1 == self.retries:
                        raise DataFetchError("MOEX ISS временно недоступен") from exc
                    time.sleep(min(10, 2 ** attempt))
                except (requests.RequestException, ValueError) as exc:
                    raise DataFetchError("Некорректный ответ MOEX ISS") from exc
            raise DataFetchError("MOEX ISS: исчерпаны повторные запросы")

    def pages(self, path, block, *, start_key="start", **params):
        output, start, previous = [], 0, None
        for _ in range(1000):
            batch = rows(self.get(path, **params, **{start_key: start}), block)
            if not batch:
                return output
            if batch == previous:
                raise DataFetchError(f"ISS не применил пагинацию: {block}")
            output.extend(batch)
            previous = batch
            start += len(batch)
        raise DataFetchError("ISS: слишком большой диапазон")

    def instrument(self, code):
        code = normalize_moex(code)
        if code.isdigit() or re.fullmatch(r"RU[A-Z0-9]{10}", code):
            candidates = rows(self.get("securities.json", q=code), "securities")
            candidates = [r for r in candidates if r.get("isin") == code or
                          (code.isdigit() and str(r.get("regnumber") or "").startswith(code + "RMFS"))]
            if len(candidates) != 1:
                raise ValueError("Инструмент не найден однозначно; укажите SECID или ISIN")
            code = candidates[0]["secid"]
        payload = self.get(f"securities/{code}.json")
        description = {r["name"]: r["value"] for r in rows(payload, "description")}
        if description.get("SECID") != code:
            raise ValueError("Инструмент MOEX не найден")
        boards = [b for b in rows(payload, "boards") if b.get("engine") == "stock"]
        primary = [b for b in boards if b.get("is_primary") == 1]
        if len(primary) != 1:
            raise ValueError("Не определён основной режим торгов MOEX")
        board = primary[0]
        if board["market"] not in ("shares", "bonds", "index"):
            raise ValueError("Этот тип инструмента пока не поддерживается")
        return {"secid": code, "symbol": "MOEX:" + code, "isin": description.get("ISIN"),
                "name": description.get("NAME") or description.get("SHORTNAME") or code,
                "market": board["market"], "board": board["boardid"],
                "currency": "RUB" if board.get("currencyid") in ("SUR", "RUB") else board.get("currencyid"),
                "is_traded": board.get("is_traded") == 1, "boards": boards,
                "description": description, "source": ISS + f"securities/{code}.json"}

    @staticmethod
    def _path(instrument):
        return (f"engines/stock/markets/{instrument['market']}/boards/"
                f"{instrument['board']}/securities/{instrument['secid']}")

    def snapshot(self, code):
        instrument = self.instrument(code)
        path = self._path(instrument) + ".json"
        payload = self.get(path)
        quotes = rows(payload, "marketdata")
        securities = rows(payload, "securities")
        q = next((r for r in quotes if r.get("SECID") == instrument["secid"]), {})
        security = next((r for r in securities if r.get("SECID") == instrument["secid"]), {})
        price = number(q.get("LASTVALUE") if instrument["market"] == "index" else q.get("LAST"))
        now = datetime.now(MOSCOW)
        # SYSTIME is publication time, not necessarily the time of the last trade.
        stamp = None
        versions = rows(payload, "dataversion") if "dataversion" in payload else []
        trade_date = q.get("TRADEDATE") or (versions[0].get("trade_date") if versions else None)
        if trade_date and q.get("TIME"):
            try:
                stamp = datetime.fromisoformat(f"{trade_date}T{q['TIME']}").replace(tzinfo=MOSCOW)
            except ValueError:
                pass
        age = max(0, int((now - stamp).total_seconds())) if stamp else None
        return {**instrument, "price": price,
                "price_unit": "percent_of_face" if instrument["market"] == "bonds" else
                              "index_points" if instrument["market"] == "index" else "currency_per_unit",
                "change_pct": number(q.get("LASTCHANGEPRC") if instrument["market"] == "index" else q.get("LASTTOPREVPRICE")),
                "volume": number(q.get("VOLTODAY")), "turnover": number(q.get("VALTODAY")),
                "timestamp": stamp.isoformat() if stamp else None,
                "published_at": q.get("SYSTIME"), "fetched_at": payload.get("_moex_received_at", now.isoformat()),
                "is_stale": age > 1200 if age is not None else None,
                "age_seconds": age, "trading_status": q.get("TRADINGSTATUS"),
                "status": "unavailable" if price is None else "timestamp_unknown" if stamp is None else
                          "stale" if age > 1200 else "ok",
                "security": security, "marketdata": q, "source": ISS + path,
                "notice": "ISS может предоставлять данные с задержкой. Время получения не равно времени сделки."}

    def candles(self, code, start, end):
        date.fromisoformat(start)
        date.fromisoformat(end)
        if start > end:
            raise ValueError("Начальная дата позже конечной")
        instrument = self.instrument(code)
        return self.pages(self._path(instrument) + "/candles.json", "candles", interval=24,
                          **{"from": start, "till": end})

    def _fetch_raw_data(self, stock_code, start_date, end_date):
        return pd.DataFrame(self.candles(stock_code, start_date, end_date))

    def _normalize_data(self, df, stock_code):
        df = df.rename(columns={"begin": "date", "value": "amount"}).copy()
        df["pct_chg"] = pd.to_numeric(df["close"], errors="coerce").pct_change(fill_method=None) * 100
        return df

    def get_realtime_quote(self, code):
        q = self.snapshot(code)
        # The generic equity pipeline must never interpret a bond percentage as money.
        if q["market"] == "bonds":
            raise ValueError("Для облигаций используйте специализированный раздел MOEX")
        return UnifiedRealtimeQuote(code=q["symbol"], name=q["name"], source=RealtimeSource.MOEX,
                                    price=q["price"], change_pct=q["change_pct"], volume=q["volume"],
                                    amount=q["turnover"], market="ru", currency=q["currency"],
                                    fetched_at=q["fetched_at"], provider_timestamp=q["timestamp"],
                                    is_stale=q["is_stale"], stale_seconds=q["age_seconds"],
                                    data_quality="unavailable" if q["price"] is None else "partial" if q["status"] != "ok" else "ok")

    def bond_schedule(self, code):
        instrument = self.instrument(code)
        if instrument["market"] != "bonds":
            raise ValueError("Требуется облигация")
        path = f"securities/{instrument['secid']}/bondization.json"
        return {block: self.pages(path, block, start_key=f"{block}.start", **{"iss.only": block})
                for block in ("coupons", "amortizations", "offers")}


@lru_cache(maxsize=1)
def get_moex_provider():
    return MOEXProvider()
