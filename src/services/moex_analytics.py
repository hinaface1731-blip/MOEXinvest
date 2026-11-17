"""Deterministic calculations. No financial number is supplied by a language model."""
from datetime import date
import math

import pandas as pd

from data_provider.moex_provider import number
from src.stock_analyzer import StockTrendAnalyzer


def equity_indicators(candles, benchmark=None):
    if not candles:
        return {"status": "unavailable", "reason": "Нет истории торгов", "indicators": {}}
    df = pd.DataFrame(candles).sort_values("begin").drop_duplicates("begin")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close", "high", "low"])
    if df.empty or (df.close <= 0).any():
        return {"status": "unavailable", "reason": "Недостаточно корректных цен", "indicators": {}}
    close = df.close
    engine = StockTrendAnalyzer()
    # Reuse the project's RSI and MACD definitions, without its China-specific signal labels.
    computed = engine._calculate_macd(engine._calculate_rsi(df.copy()))
    returns = close.pct_change(fill_method=None)
    tr = pd.concat([df.high - df.low, (df.high - close.shift()).abs(), (df.low - close.shift()).abs()], axis=1).max(axis=1)
    values = {"sma20": close.rolling(20).mean().iloc[-1], "sma50": close.rolling(50).mean().iloc[-1],
              "ema20": close.ewm(span=20, adjust=False, min_periods=20).mean().iloc[-1],
              "bollinger_upper": (close.rolling(20).mean() + 2 * close.rolling(20).std(ddof=0)).iloc[-1],
              "bollinger_lower": (close.rolling(20).mean() - 2 * close.rolling(20).std(ddof=0)).iloc[-1],
              "atr14": tr.rolling(14).mean().iloc[-1],
              "volatility_annual_pct": returns.std(ddof=1) * math.sqrt(252) * 100 if len(df) >= 20 else None,
              "max_drawdown_pct": ((close / close.cummax()) - 1).min() * 100,
              "price_return_pct": (close.iloc[-1] / close.iloc[0] - 1) * 100,
              "support20": df.low.tail(20).min(), "resistance20": df.high.tail(20).max(),
              "average_volume20": df.volume.rolling(20).mean().iloc[-1]}
    for name in ("RSI", "RSI_6", "RSI_12", "RSI_24", "MACD_DIF", "MACD_DEA", "MACD_BAR"):
        if name in computed:
            values[name] = computed[name].iloc[-1] if len(df) >= 26 else None
    excess = None
    if benchmark:
        b = pd.DataFrame(benchmark).drop_duplicates("begin").set_index("begin")
        paired = pd.concat([df.set_index("begin").close.rename("asset"), b.close.rename("index")], axis=1).dropna()
        if len(paired) > 1 and (paired > 0).all().all():
            excess = ((paired.asset.iloc[-1] / paired.asset.iloc[0] - 1) -
                      (paired['index'].iloc[-1] / paired['index'].iloc[0] - 1)) * 100
    values["excess_return_imoex_pp"] = excess
    return {"status": "ok" if len(df) >= 50 else "partial", "observations": len(df),
            "from": str(df.iloc[0]['begin']), "to": str(df.iloc[-1]['begin']),
            "indicators": {k: number(v) for k, v in values.items()},
            "total_return_pct": None,
            "limitations": ["Цены без поправки на корпоративные действия; доходность не включает дивиденды.",
                            "Волатильность: 252 наблюдения в год; ATR — простое среднее true range.",
                            "Технические показатели не являются прогнозом."]}


def cashflow_yield(price, flows, settlement):
    """Positive dated cash flows: unique effective annual IRR, ACT/365F.

    No inferred coupons, reinvestments, weekend shifts or synthetic maturity payment.
    This convention is explicit and may differ from the exchange's quoted yield.
    """
    if not math.isfinite(price) or price <= 0 or not flows:
        raise ValueError("Положительная цена и известные денежные потоки обязательны")
    periods = []
    for when, amount in flows:
        if when <= settlement or not math.isfinite(amount) or amount <= 0:
            raise ValueError("Денежные потоки должны быть положительными и будущими")
        periods.append(((when - settlement).days / 365, amount))
    # Solve in log(1+y) space to cover negative yields without singularities.
    def pv(log_rate):
        return sum(amount * math.exp(max(-700, min(700, -log_rate * t))) for t, amount in periods)
    lo, hi = -10.0, 10.0
    if not pv(lo) >= price >= pv(hi):
        raise ValueError("Доходность вне поддерживаемого диапазона")
    for _ in range(160):
        mid = (lo + hi) / 2
        if pv(mid) > price:
            lo = mid
        else:
            hi = mid
    log_rate = (lo + hi) / 2
    y = math.expm1(log_rate)
    duration = sum(t * amount * math.exp(-log_rate * t) for t, amount in periods) / price
    modified = duration / (1 + y)
    return {"yield_pct": y * 100, "duration_years": duration,
            "modified_duration_years": modified, "price_change_plus_100bp_pct": -modified,
            "convention": "ACT/365F, effective annual IRR; approximate +100bp sensitivity",
            "settlement": settlement.isoformat()}


def bond_analysis(quote, schedule):
    s, m = quote["security"], quote["marketdata"]
    face, accrued, price = number(s.get("FACEVALUEONSETTLEDATE") or s.get("FACEVALUE")), number(s.get("ACCRUEDINT")), quote["price"]
    dirty = price * face / 100 + accrued if all(v is not None for v in (face, accrued, price)) else None
    limitations = []
    metrics = None
    try:
        settlement = date.fromisoformat(s["SETTLEDATE"])
        maturity = date.fromisoformat(s["MATDATE"])
        future_coupons = [c for c in schedule["coupons"] if date.fromisoformat(c["coupondate"]) > settlement]
        future_principal = [a for a in schedule["amortizations"] if date.fromisoformat(a["amortdate"]) > settlement]
        if not future_principal or max(date.fromisoformat(a["amortdate"]) for a in future_principal) != maturity:
            raise ValueError("Неполный график погашения")
        if not future_coupons:
            raise ValueError("Не подтверждён полный график купонов")
        flows = []
        for entries, field in ((future_coupons, "coupondate"), (future_principal, "amortdate")):
            for flow in entries:
                value = number(flow.get("value"))
                if value is None or value <= 0 or str(flow.get("faceunit")).replace("SUR", "RUB") != str(s.get("FACEUNIT")).replace("SUR", "RUB"):
                    raise ValueError("Неизвестные выплаты или валюта денежного потока")
                flows.append((date.fromisoformat(flow[field]), value))
        if dirty is None:
            raise ValueError("Нет цены, номинала или НКД")
        if schedule["offers"] or s.get("CALLOPTIONDATE") or s.get("PUTOPTIONDATE"):
            limitations.append("Расчёт до погашения условный: есть оферта или опцион; YTO не моделируется.")
        metrics = cashflow_yield(dirty, flows, settlement)
    except (KeyError, TypeError, ValueError) as exc:
        limitations.append(str(exc) or "Нет полных данных для расчёта доходности")
    limitations.extend(["Будущие выплаты используются только из опубликованного графика ISS.",
                        "Неизвестные плавающие купоны не прогнозируются. Кредитный рейтинг не подтверждён.",
                        "Расчётная доходность может отличаться от биржевой из-за конвенций."])
    return {"clean_price_pct": price, "face_value": face, "accrued_interest": accrued,
            "dirty_price": dirty, "coupon": number(s.get("COUPONVALUE")),
            "coupon_period_days": number(s.get("COUPONPERIOD")), "maturity": s.get("MATDATE"),
            "offer_date": s.get("OFFERDATE"), "exchange_yield_pct": number(m.get("YIELD")),
            "exchange_yield_to_offer_pct": number(m.get("YIELDTOOFFER")),
            "calculated": metrics, "schedule": schedule, "limitations": limitations}


def money_weighted_return(events, terminal_value, terminal_date):
    """Annual XIRR from dated external flows; reject ambiguous/multiple roots."""
    if terminal_value is None or terminal_value < 0 or not events:
        return None
    cash = {}
    for event in events:
        when = date.fromisoformat(event["event_date"])
        if when > terminal_date:
            continue
        amount = float(event["amount"]) * (-1 if event["direction"] == "in" else 1)
        cash[when] = cash.get(when, 0) + amount
    cash[terminal_date] = cash.get(terminal_date, 0) + terminal_value
    cash = {d: v for d, v in cash.items() if v != 0}
    if len(cash) < 2 or not any(v < 0 for v in cash.values()) or not any(v > 0 for v in cash.values()):
        return None
    ordered = sorted(cash.items())
    # More than one sign change can have multiple economic IRRs. Do not pick one silently.
    signs = [1 if v > 0 else -1 for _, v in ordered]
    if sum(a != b for a, b in zip(signs, signs[1:])) != 1:
        return None
    origin = ordered[0][0]
    def npv(log_rate):
        return sum(value * math.exp(max(-600, min(600, -log_rate * (d - origin).days / 365)))
                   for d, value in ordered)
    lo, hi = -10.0, 10.0
    left, right = npv(lo), npv(hi)
    if left * right > 0:
        return None
    for _ in range(150):
        mid = (lo + hi) / 2
        value = npv(mid)
        if (value > 0) == (left > 0):
            lo, left = mid, value
        else:
            hi = mid
    return math.expm1((lo + hi) / 2) * 100
