import { useCallback, useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  BookOpen,
  CalendarDays,
  ChevronRight,
  CircleHelp,
  Globe2,
  Landmark,
  LayoutDashboard,
  Moon,
  Newspaper,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  Wallet,
} from "lucide-react";
import "./moex.css";

type Quote = {
  secid: string;
  name: string;
  market: string;
  isin: string | null;
  board: string;
  currency: string | null;
  price: number | null;
  price_unit: string;
  change_pct: number | null;
  timestamp: string | null;
  fetched_at: string;
  status: string;
  source: string;
  security: { MATDATE?: string };
  marketdata: { YIELD?: number | null };
};
type Candle = {
  begin: string;
  close: number;
  open: number;
  high: number;
  low: number;
  volume: number;
};
type Analysis = {
  indicators: Record<string, number | null>;
  limitations: string[];
  observations: number;
};
type Bond = {
  clean_price_pct: number | null;
  face_value: number | null;
  accrued_interest: number | null;
  dirty_price: number | null;
  maturity: string | null;
  coupon: number | null;
  exchange_yield_pct: number | null;
  calculated: {
    yield_pct: number;
    duration_years: number;
    modified_duration_years: number;
    convention: string;
  } | null;
  limitations: string[];
  schedule: {
    coupons: { coupondate: string; value: number | null }[];
    amortizations: { amortdate: string; value: number | null }[];
  };
};
type Instrument = {
  quote: Quote;
  candles: Candle[];
  analysis: Analysis | null;
  bond: Bond | null;
};
type Watch = { equities: string[]; bonds: string[]; indices: string[] };
type Market = {
  fetched_at: string;
  instruments: Quote[];
  errors: { symbol: string; error: string }[];
  watchlist: Watch;
};
type Macro = {
  events: { date: string; title: string; source: string }[];
  observations: {
    name: string;
    value: number;
    unit: string;
    observed_at: string;
    published_at: string | null;
    source: string;
  }[];
  news: { title: string; source: string; published_at: string | null }[];
  errors: { source: string; error: string }[];
  limitations: string[];
};
type Report = {
  id: string;
  summary: string;
  created_at: string;
  facts: {
    id: string;
    symbol: string;
    price: number | null;
    source: string;
    status: string;
  }[];
  risks: string[];
  scenarios: Record<string, string>;
  invalidated_by: string;
  ai_status: string;
  fundamentals: string;
  technical: string;
  disclaimer: string;
  macro: Macro;
};
type Position = {
  symbol: string;
  quantity: number;
  last_price: number;
  market_value_base: number;
  price_available: boolean;
  price_stale: boolean;
};
type Portfolio = {
  accounts: {
    account_id: number;
    account_name: string;
    total_equity: number;
  }[];
  positions: Position[];
  total_equity: number | null;
  known_equity: number;
  profit: number | null;
  net_contributions: number;
  complete: boolean;
  issuer_weights: Record<string, number | null>;
  limitations: string[];
  calendar: { symbol: string; date: string; amount: number | null }[];
  return_pct: number | null;
  drawdown_pct: number | null;
  drawdown_since: string | null;
};
type Demo = {
  generated_at: string;
  market: Market;
  instruments: Record<string, Instrument>;
  macro: Macro;
  report: Report;
};
const demo = import.meta.env.VITE_MOEX_DEMO === "true";
let demoPromise: Promise<Demo> | null = null;
const loadDemo = () =>
  (demoPromise ??= fetch(`${import.meta.env.BASE_URL}moex-demo.json`)
    .then((r) => {
      if (!r.ok) throw new Error("Снимок данных временно недоступен");
      return r.json() as Promise<Demo>;
    })
    .catch((e) => {
      demoPromise = null;
      throw e;
    }));
async function api<T>(
  path: string,
  body?: unknown,
  method = "POST",
): Promise<T> {
  const r = await fetch(
    `/api/v1/moex${path}`,
    body === undefined
      ? { credentials: "same-origin" }
      : {
          method,
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const value = await r.json();
  if (!r.ok)
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : "Не удалось выполнить запрос. Проверьте данные и вход в аккаунт.",
    );
  return value as T;
}
const format = (n: number | null | undefined, digits = 2) =>
  n == null || !Number.isFinite(n)
    ? "—"
    : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(
        n,
      );
const when = (s: string | null) =>
  s
    ? new Date(s).toLocaleString("ru-RU", {
        timeZone: "Europe/Moscow",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "время не подтверждено";
const sections = [
  { id: "market", title: "Обзор рынка", icon: LayoutDashboard },
  { id: "portfolio", title: "Мой портфель", icon: Wallet },
  { id: "shares", title: "Акции", icon: BarChart3 },
  { id: "bonds", title: "Облигации", icon: Landmark },
  { id: "macro", title: "Макроэкономика", icon: Globe2 },
  { id: "news", title: "Новости", icon: Newspaper },
  { id: "ai", title: "ИИ-аналитик", icon: Sparkles },
  { id: "reports", title: "История отчётов", icon: BookOpen },
  { id: "settings", title: "Настройки", icon: Settings2 },
];
const labels: Record<string, string> = {
  sma20: "SMA 20",
  sma50: "SMA 50",
  ema20: "EMA 20",
  RSI_6: "RSI 6",
  RSI_12: "RSI 12",
  RSI_24: "RSI 24",
  MACD_DIF: "MACD",
  MACD_DEA: "Сигнальная линия",
  MACD_BAR: "Гистограмма MACD",
  atr14: "ATR 14",
  volatility_annual_pct: "Волатильность, % годовых",
  max_drawdown_pct: "Макс. просадка, %",
  price_return_pct: "Изменение цены, %",
  excess_return_imoex_pp: "К IMOEX, п.п.",
  support20: "Поддержка 20",
  resistance20: "Сопротивление 20",
  bollinger_upper: "Bollinger — верх",
  bollinger_lower: "Bollinger — низ",
  average_volume20: "Средний объём 20",
};
function Status({ quote }: { quote: Quote }) {
  return (
    <span className={`mx-status ${quote.status === "ok" ? "good" : ""}`}>
      {quote.status === "ok"
        ? "Данные ISS"
        : quote.status === "stale"
          ? "Устаревшие данные"
          : quote.status === "unavailable"
            ? "Нет котировки"
            : "Время неизвестно"}
    </span>
  );
}
function Source({ quote }: { quote: Quote }) {
  return (
    <div className="mx-source">
      <a href={quote.source} target="_blank" rel="noreferrer">
        MOEX ISS ↗
      </a>
      <span>Сделка: {when(quote.timestamp)} МСК</span>
      <span>Получено: {when(quote.fetched_at)} МСК</span>
    </div>
  );
}
function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-notice">
      <CircleHelp size={17} />
      <div>{children}</div>
    </div>
  );
}
function Stat({
  label,
  value,
  hint,
  green = false,
}: {
  label: string;
  value: string;
  hint: string;
  green?: boolean;
}) {
  return (
    <div className="mx-stat">
      <span>{label}</span>
      <strong className={green ? "mx-positive" : ""}>{value}</strong>
      <small>{hint}</small>
    </div>
  );
}

export default function MoexPage() {
  const [section, setSection] = useState("market");
  const [market, setMarket] = useState<Market | null>(null);
  const [macro, setMacro] = useState<Macro | null>(null);
  const [detail, setDetail] = useState<Instrument | null>(null);
  const [symbol, setSymbol] = useState("SBER");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [dark, setDark] = useState(
    () => localStorage.getItem("moex-theme") === "dark",
  );
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [actionMessage, setActionMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [tradeKind, setTradeKind] = useState("trade");
  useEffect(() => {
    let active = true;
    const work = async () => {
      await Promise.resolve();
      if (!active) return;
      setLoading(true);
      setError("");
      try {
        if (demo) {
          const d = await loadDemo();
          if (active) {
            setMarket(d.market);
            setMacro(d.macro);
            setReports([d.report]);
          }
        } else {
          const [m, x] = await Promise.all([
            api<Market>("/market"),
            api<Macro>("/macro"),
          ]);
          if (active) {
            setMarket(m);
            setMacro(x);
          }
        }
      } catch (e) {
        if (active)
          setError(e instanceof Error ? e.message : "Ошибка загрузки");
      } finally {
        if (active) setLoading(false);
      }
    };
    void work();
    return () => {
      active = false;
    };
  }, [refresh]);
  useEffect(() => {
    let active = true;
    const work = async () => {
      await Promise.resolve();
      if (!active) return;
      setDetailLoading(true);
      setDetail(null);
      try {
        const value = demo
          ? (await loadDemo()).instruments[symbol]
          : await api<Instrument>(`/instruments/${encodeURIComponent(symbol)}`);
        if (active) {
          setDetail(value ?? null);
          if (!value) setError("Этого инструмента нет в публичном снимке.");
        }
      } catch (e) {
        if (active)
          setError(e instanceof Error ? e.message : "Инструмент недоступен");
      } finally {
        if (active) setDetailLoading(false);
      }
    };
    void work();
    return () => {
      active = false;
    };
  }, [symbol, refresh]);
  useEffect(() => {
    if (demo || !["portfolio", "reports", "ai"].includes(section)) return;
    let active = true;
    const work = async () => {
      try {
        if (section === "portfolio") {
          const p = await api<Portfolio>("/portfolio");
          if (active) setPortfolio(p);
        } else {
          const r = await api<Report[]>("/reports");
          if (active) setReports(r);
        }
      } catch (e) {
        if (active)
          setError(e instanceof Error ? e.message : "Данные недоступны");
      }
    };
    void work();
    return () => {
      active = false;
    };
  }, [section, refresh]);
  const action = useCallback(
    async (path: string, body: unknown, method = "POST") => {
      setBusy(true);
      setActionMessage("");
      try {
        const result = await api<unknown>(path, body, method);
        setActionMessage(
          path === "/import" ? JSON.stringify(result) : "Сохранено",
        );
        setRefresh((r) => r + 1);
      } catch (e) {
        setActionMessage(e instanceof Error ? e.message : "Ошибка");
      } finally {
        setBusy(false);
      }
    },
    [],
  );
  const choose = (q: Quote) => {
    setSymbol(q.secid);
    setSection(q.market === "bonds" ? "bonds" : "shares");
    setError("");
  };
  const title = sections.find((s) => s.id === section)?.title ?? "Обзор рынка";
  const quotes = market?.instruments ?? [];
  const index = quotes.find((q) => q.secid === "IMOEX");
  const rate = macro?.observations.find((o) => o.name === "Ключевая ставка ЦБ");
  const filtered = quotes.filter(
    (q) =>
      (section !== "shares" || q.market === "shares") &&
      (section !== "bonds" || q.market === "bonds") &&
      `${q.secid} ${q.name}`.toLowerCase().includes(query.toLowerCase()),
  );
  const today = new Date().toLocaleDateString("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const renderChart = () =>
    detailLoading ? (
      <div className="mx-loading">Загружаем историю…</div>
    ) : detail?.candles.length ? (
      <div className="mx-chart">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={detail.candles}>
            <defs>
              <linearGradient id="moex-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#12a078" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#12a078" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 5"
              vertical={false}
              stroke="var(--mx-line)"
            />
            <XAxis
              dataKey="begin"
              tickFormatter={(v) => String(v).slice(5, 10)}
              minTickGap={45}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#83938e", fontSize: 11 }}
            />
            <YAxis
              domain={["auto", "auto"]}
              orientation="right"
              tickFormatter={(v) => format(Number(v), 0)}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#83938e", fontSize: 11 }}
            />
            <Tooltip
              labelFormatter={(v) => String(v).slice(0, 10)}
              formatter={(v) => [
                format(Number(v)),
                detail?.quote.price_unit === "percent_of_face"
                  ? "% номинала"
                  : "Закрытие",
              ]}
              contentStyle={{
                background: "var(--mx-card)",
                border: "1px solid var(--mx-line)",
                borderRadius: 10,
              }}
            />
            <Area
              type="linear"
              dataKey="close"
              stroke="#12a078"
              strokeWidth={2}
              fill="url(#moex-fill)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    ) : (
      <div className="mx-loading">История торгов недоступна</div>
    );
  const renderTable = () => (
    <div className="mx-table-wrap">
      <table className="mx-table">
        <thead>
          <tr>
            <th>Инструмент</th>
            <th>Цена</th>
            <th>Изменение</th>
            <th>Актуальность</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {filtered.map((q, i) => (
            <tr key={q.secid} onClick={() => choose(q)}>
              <td>
                <button className="mx-instrument" onClick={() => choose(q)}>
                  <span className={`mx-logo tone-${i % 4}`}>
                    {q.secid.slice(0, 2)}
                  </span>
                  <span>
                    <b>{q.secid}</b>
                    <small>{q.name}</small>
                  </span>
                </button>
              </td>
              <td>
                <b>{format(q.price)}</b>
                <small>
                  {q.price_unit === "percent_of_face"
                    ? "% номинала"
                    : q.price_unit === "index_points"
                      ? "пунктов"
                      : q.currency}
                </small>
              </td>
              <td
                className={
                  (q.change_pct ?? 0) >= 0 ? "mx-positive" : "mx-negative"
                }
              >
                {q.change_pct == null
                  ? "—"
                  : `${q.change_pct >= 0 ? "+" : ""}${format(q.change_pct)}%`}
              </td>
              <td>
                <Status quote={q} />
                <small>{when(q.timestamp)} МСК</small>
              </td>
              <td>
                <ChevronRight size={16} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!filtered.length && (
        <div className="mx-empty">
          {loading ? "Загружаем инструменты…" : "Инструменты не найдены"}
        </div>
      )}
    </div>
  );
  const renderReport = (r: Report) => (
    <article className="mx-panel mx-report" key={r.id}>
      <span className="mx-eyebrow">
        {r.ai_status === "validated_selection"
          ? "Факты отобраны ИИ · числа из источников"
          : "Обзор на основе проверенных данных"}
      </span>
      <h2>{r.summary}</h2>
      <p className="mx-muted">{when(r.created_at)} МСК</p>
      <h3>Подтверждённые факты</h3>
      <div className="mx-report-facts">
        {r.facts.map((f) => (
          <a href={f.source} target="_blank" rel="noreferrer" key={f.id}>
            <b>{f.symbol}</b>
            <span>{format(f.price)}</span>
            <small>{f.status} ↗</small>
          </a>
        ))}
      </div>
      <h3>Технические показатели</h3>
      <p>{r.technical}</p>
      <h3>Фундаментальные факторы</h3>
      <p>{r.fundamentals}</p>
      <h3>Макроэкономика</h3>
      <p>
        {r.macro.observations
          .map((o) => `${o.name}: ${format(o.value)} ${o.unit}`)
          .join(" · ") || "Нет подтверждённых данных"}
      </p>
      <h3>Основные риски</h3>
      <ul>
        {r.risks.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
      <div className="mx-scenarios">
        {Object.entries(r.scenarios).map(([k, v]) => (
          <div key={k}>
            <span>
              {
                (
                  {
                    positive: "Позитивный",
                    base: "Базовый",
                    negative: "Негативный",
                  } as Record<string, string>
                )[k]
              }
            </span>
            <p>{v}</p>
          </div>
        ))}
      </div>
      <Notice>
        Условия неактуальности: {r.invalidated_by} {r.disclaimer}
      </Notice>
    </article>
  );
  return (
    <div className={`mx-app ${dark ? "mx-dark" : ""}`}>
      <aside className="mx-sidebar">
        <a className="mx-brand" href={demo ? "./" : "/moex"}>
          <span>
            <Activity size={23} />
          </span>
          <b>
            MOEX<span>invest</span>
          </b>
        </a>
        <div className="mx-workspace">
          <span className="mx-avatar">М</span>
          <div>
            <b>Российский рынок</b>
            <small>
              {demo ? "Публичная демонстрация" : "Личное пространство"}
            </small>
          </div>
          <ChevronRight size={14} />
        </div>
        <span className="mx-nav-label">РАБОЧЕЕ ПРОСТРАНСТВО</span>
        <nav>
          {sections.map((s) => (
            <button
              key={s.id}
              className={section === s.id ? "active" : ""}
              onClick={() => {
                setSection(s.id);
                setError("");
                if (s.id === "bonds" && detail?.quote.market !== "bonds")
                  setSymbol(market?.watchlist.bonds[0] ?? "SU26248RMFS3");
                if (s.id === "shares" && detail?.quote.market !== "shares")
                  setSymbol(market?.watchlist.equities[0] ?? "SBER");
              }}
            >
              <s.icon size={18} />
              <span>{s.title}</span>
              {s.id === "ai" && <small>AI</small>}
            </button>
          ))}
        </nav>
        <div className="mx-sidebar-bottom">
          <ShieldCheck size={23} />
          <b>Данные с источником</b>
          <p>Московская биржа и Банк России. Никаких выдуманных котировок.</p>
          {!demo && <a href="/">Иностранные рынки ↗</a>}
        </div>
      </aside>
      <div className="mx-main">
        <header className="mx-topbar">
          <div>
            <span className="mx-breadcrumb">Рабочее пространство</span>
            <ChevronRight size={13} />
            <b>{title}</b>
          </div>
          <div>
            <span className="mx-date">{today}</span>
            <button
              className="mx-icon-button"
              aria-label="Переключить тему"
              onClick={() => {
                localStorage.setItem("moex-theme", dark ? "light" : "dark");
                setDark(!dark);
              }}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <span className="mx-profile">М</span>
          </div>
        </header>
        <main className="mx-content">
          <div className="mx-page-heading">
            <div>
              <div className="mx-eyebrow">
                <span className="mx-dot" />
                {demo
                  ? "ПУБЛИЧНЫЕ БИРЖЕВЫЕ ДАННЫЕ"
                  : "ВАШ ИНВЕСТИЦИОННЫЙ ОБЗОР"}
              </div>
              <h1>
                {title}
                <span>.</span>
              </h1>
              <p>
                {section === "market"
                  ? "Главное о рынке. Факты, динамика и контекст для ваших решений."
                  : "Проверяемые данные и прозрачные расчёты."}
              </p>
            </div>
            <button
              className="mx-button secondary"
              disabled={loading}
              onClick={() => {
                if (demo) demoPromise = null;
                setRefresh((r) => r + 1);
              }}
            >
              <RefreshCw size={15} className={loading ? "mx-spin" : ""} />
              {loading ? "Загрузка" : "Обновить"}
            </button>
          </div>
          {demo && (
            <div className="mx-demo-banner">
              <Globe2 size={16} />
              <span>
                Демонстрация · реальный снимок на{" "}
                {when(market?.fetched_at ?? null)} МСК. Котировки могут быть с
                задержкой.
              </span>
              <a
                href="https://github.com/hinaface1731-blip/MOEXinvest"
                target="_blank"
                rel="noreferrer"
              >
                О проекте ↗
              </a>
            </div>
          )}
          {error && (
            <div role="alert" className="mx-error">
              {error}
              <button onClick={() => setRefresh((r) => r + 1)}>
                Повторить
              </button>
            </div>
          )}
          {market?.errors.length ? (
            <Notice>
              Некоторые источники недоступны:{" "}
              {market.errors.map((e) => e.symbol).join(", ")}. Отсутствующие
              данные не заменяются прогнозом.
            </Notice>
          ) : null}
          {["market", "shares", "bonds"].includes(section) && (
            <>
              {section === "market" && (
                <>
                  <div className="mx-stats">
                    <Stat
                      label="Индекс Мосбиржи"
                      value={format(index?.price)}
                      hint={
                        index?.change_pct == null
                          ? "Нет подтверждённой котировки"
                          : `${index.change_pct >= 0 ? "+" : ""}${format(index.change_pct)}% · MOEX ISS`
                      }
                      green={(index?.change_pct ?? -1) >= 0}
                    />
                    <Stat
                      label="Ключевая ставка"
                      value={rate ? `${format(rate.value)}%` : "—"}
                      hint={
                        rate
                          ? `Банк России · ${rate.observed_at}`
                          : "Данные недоступны"
                      }
                    />
                    <Stat
                      label="В списке наблюдения"
                      value={String(
                        quotes.filter((q) => q.market !== "index").length,
                      )}
                      hint="Акции и облигации"
                    />
                    <Stat
                      label="Время данных"
                      value={
                        market
                          ? new Date(market.fetched_at).toLocaleTimeString(
                              "ru-RU",
                              {
                                timeZone: "Europe/Moscow",
                                hour: "2-digit",
                                minute: "2-digit",
                              },
                            )
                          : "—"
                      }
                      hint="МСК · время получения снимка"
                    />
                  </div>
                </>
              )}
              <div className="mx-chart-layout">
                <section className="mx-panel">
                  <div className="mx-panel-heading">
                    <div>
                      <span className="mx-eyebrow">
                        {detail?.quote.market === "bonds"
                          ? "ЦЕНА В % ОТ НОМИНАЛА"
                          : "ДИНАМИКА ИНСТРУМЕНТА"}
                      </span>
                      <h2>{detail?.quote.name ?? symbol}</h2>
                    </div>
                    <select
                      aria-label="Выбрать инструмент"
                      value={symbol}
                      onChange={(e) => {
                        setSymbol(e.target.value);
                        setError("");
                      }}
                    >
                      {quotes.length ? (
                        quotes.map((q) => (
                          <option key={q.secid}>{q.secid}</option>
                        ))
                      ) : (
                        <option>{symbol}</option>
                      )}
                    </select>
                  </div>
                  <div className="mx-chart-value">
                    <strong>{format(detail?.quote.price)}</strong>
                    <span
                      className={
                        (detail?.quote.change_pct ?? 0) >= 0
                          ? "mx-positive"
                          : "mx-negative"
                      }
                    >
                      {format(detail?.quote.change_pct)}%
                    </span>
                    <small>Последняя доступная цена</small>
                  </div>
                  {renderChart()}
                  {detail && <Source quote={detail.quote} />}
                </section>
                <aside className="mx-panel mx-insight">
                  <div className="mx-insight-icon">
                    <Sparkles size={21} />
                  </div>
                  <span className="mx-eyebrow">КОНТЕКСТ РЫНКА</span>
                  <h2>
                    Смотрите шире
                    <br />
                    одной котировки
                  </h2>
                  <p>
                    Ставки, ликвидность и события эмитента помогают оценить
                    риск. Рост в прошлом не гарантирует будущую доходность.
                  </p>
                  <div className="mx-context-row">
                    <Landmark size={17} />
                    <span>Ключевая ставка ЦБ</span>
                    <b>{format(rate?.value)}%</b>
                  </div>
                  <div className="mx-context-row">
                    <CalendarDays size={17} />
                    <span>Часовой пояс</span>
                    <b>Москва</b>
                  </div>
                  <button
                    className="mx-button"
                    onClick={() => setSection("ai")}
                  >
                    Открыть обзор <ArrowUpRight size={16} />
                  </button>
                  <small>Факты отдельно от интерпретации</small>
                </aside>
              </div>
              <section className="mx-panel">
                <div className="mx-panel-heading">
                  <div>
                    <h2>
                      {section === "market" ? "Список наблюдения" : title}
                    </h2>
                    <p>Выберите инструмент для подробного анализа</p>
                  </div>
                  <label className="mx-search">
                    <Search size={16} />
                    <input
                      aria-label="Поиск инструмента"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Тикер или название"
                    />
                  </label>
                </div>
                {renderTable()}
              </section>
              {section !== "market" && detail?.analysis && (
                <section className="mx-panel">
                  <h2>Технический анализ</h2>
                  <div className="mx-indicators">
                    {Object.entries(detail.analysis.indicators).map(
                      ([k, v]) => (
                        <div key={k}>
                          <span>{labels[k] ?? k}</span>
                          <b>{format(v)}</b>
                        </div>
                      ),
                    )}
                  </div>
                  <Notice>{detail.analysis.limitations.join(" ")}</Notice>
                </section>
              )}
              {section === "bonds" && detail?.bond && (
                <section className="mx-panel">
                  <h2>Денежные потоки и доходность</h2>
                  <p className="mx-muted">
                    {detail.quote.isin} · {detail.quote.board}
                  </p>
                  <div className="mx-indicators">
                    {[
                      ["Номинал, ₽", detail.bond.face_value],
                      ["НКД, ₽", detail.bond.accrued_interest],
                      ["Полная цена, ₽", detail.bond.dirty_price],
                      ["Купон, ₽", detail.bond.coupon],
                      [
                        "Биржевая доходность, %",
                        detail.bond.exchange_yield_pct,
                      ],
                      ["Расчётная YTM, %", detail.bond.calculated?.yield_pct],
                      ["Дюрация, лет", detail.bond.calculated?.duration_years],
                      [
                        "Модифицированная дюрация",
                        detail.bond.calculated?.modified_duration_years,
                      ],
                    ].map(([k, v]) => (
                      <div key={String(k)}>
                        <span>{k}</span>
                        <b>{format(v as number | null)}</b>
                      </div>
                    ))}
                  </div>
                  <p>Погашение: {detail.bond.maturity ?? "неизвестно"}</p>
                  <Notice>
                    {detail.bond.limitations.join(" ")}{" "}
                    {detail.bond.calculated?.convention}
                  </Notice>
                  <h3>Купонный календарь</h3>
                  <div className="mx-table-wrap">
                    <table className="mx-table">
                      <thead>
                        <tr>
                          <th>Дата выплаты</th>
                          <th>На одну облигацию, ₽</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.bond.schedule.coupons
                          .filter(
                            (c) =>
                              c.coupondate >=
                              new Date().toISOString().slice(0, 10),
                          )
                          .map((c) => (
                            <tr key={c.coupondate}>
                              <td>{c.coupondate}</td>
                              <td>{format(c.value)}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )}
          {section === "macro" && (
            <>
              <div className="mx-stats">
                {macro?.observations.map((o) => (
                  <Stat
                    key={o.name}
                    label={o.name}
                    value={format(o.value)}
                    hint={`${o.unit} · ${o.observed_at}`}
                  />
                ))}
              </div>
              <section className="mx-panel">
                <h2>Официальные наблюдения</h2>
                {macro?.observations.map((o) => (
                  <div className="mx-macro-row" key={o.name}>
                    <div>
                      <b>{o.name}</b>
                      <p>
                        Дата наблюдения: {o.observed_at} · Публикация:{" "}
                        {o.published_at ?? "источник не сообщает"}
                      </p>
                    </div>
                    <a href={o.source} target="_blank" rel="noreferrer">
                      Банк России ↗
                    </a>
                  </div>
                ))}
                <h3>Ближайшие заседания</h3>
                {macro?.events?.slice(0, 5).map((e) => (
                  <div className="mx-macro-row" key={e.date}>
                    <b>{e.date}</b>
                    <a href={e.source} target="_blank" rel="noreferrer">
                      {e.title} ↗
                    </a>
                  </div>
                ))}
                <Notice>{macro?.limitations.join(" ")}</Notice>
              </section>
              <section className="mx-panel">
                <h2>Доходности выбранных ОФЗ</h2>
                <p>
                  Биржевые показатели по последним доступным сделкам. Это
                  выборка бумаг, а не полная бескупонная кривая.
                </p>
                <div className="mx-table-wrap">
                  <table className="mx-table">
                    <thead>
                      <tr>
                        <th>Выпуск</th>
                        <th>Погашение</th>
                        <th>Доходность, %</th>
                        <th>Время сделки</th>
                      </tr>
                    </thead>
                    <tbody>
                      {quotes
                        .filter((q) => q.market === "bonds")
                        .sort((a, b) =>
                          (a.security.MATDATE ?? "").localeCompare(
                            b.security.MATDATE ?? "",
                          ),
                        )
                        .map((q) => (
                          <tr key={q.secid} onClick={() => choose(q)}>
                            <td>{q.secid}</td>
                            <td>{q.security.MATDATE ?? "—"}</td>
                            <td>{format(q.marketdata.YIELD)}</td>
                            <td>{when(q.timestamp)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                <button
                  className="mx-button"
                  onClick={() => {
                    setSection("bonds");
                    setSymbol("SU26248RMFS3");
                  }}
                >
                  Перейти к облигациям <ArrowUpRight size={16} />
                </button>
              </section>
            </>
          )}
          {(section === "news" || section === "market") && (
            <section className="mx-panel">
              <div className="mx-panel-heading">
                <div>
                  <span className="mx-eyebrow">ОФИЦИАЛЬНЫЙ ИСТОЧНИК</span>
                  <h2>Новости Банка России</h2>
                </div>
                <Newspaper size={20} />
              </div>
              <div className="mx-news">
                {macro?.news
                  .slice(0, section === "market" ? 3 : 15)
                  .map((n) => (
                    <a
                      key={n.source}
                      href={n.source}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <span className="mx-news-tag">БАНК РОССИИ</span>
                      <h3>{n.title}</h3>
                      <div>
                        <small>
                          {n.published_at
                            ? when(n.published_at)
                            : "Дата не указана"}
                        </small>
                        <ArrowUpRight size={17} />
                      </div>
                    </a>
                  ))}
              </div>
              {!macro?.news.length && (
                <Notice>
                  Лента временно недоступна. Новости не заменяются
                  сгенерированным текстом.
                </Notice>
              )}
            </section>
          )}
          {section === "portfolio" && (
            <>
              {demo ? (
                <section className="mx-panel mx-private">
                  <div className="mx-insight-icon">
                    <Wallet size={26} />
                  </div>
                  <h2>Ваш портфель — только для вас</h2>
                  <p>
                    Публичная версия показывает рыночные данные. Счета, операции
                    и личные отчёты доступны в локальном приложении с защищённым
                    входом.
                  </p>
                  <a
                    className="mx-button"
                    href="https://github.com/hinaface1731-blip/MOEXinvest/blob/main/docs/PORTFOLIO_GUIDE.md"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Как подключить личный портфель <ArrowUpRight size={16} />
                  </a>
                </section>
              ) : (
                <>
                  <div className="mx-stats">
                    <Stat
                      label="Стоимость портфеля"
                      value={`${format(portfolio?.total_equity)} ₽`}
                      hint={
                        portfolio?.complete
                          ? "Все позиции оценены"
                          : "Оценка неполная"
                      }
                    />
                    <Stat
                      label="Прибыль / убыток"
                      value={`${format(portfolio?.profit)} ₽`}
                      hint="Без пополнений и выводов"
                    />
                    <Stat
                      label="Чистые пополнения"
                      value={`${format(portfolio?.net_contributions)} ₽`}
                      hint="Пополнения минус выводы"
                    />
                  </div>
                  <section className="mx-panel">
                    <h2>Счета и операции</h2>
                    <form
                      className="mx-inline-form"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void action("/accounts", {
                          name: new FormData(e.currentTarget).get("name"),
                        });
                      }}
                    >
                      <input
                        name="name"
                        placeholder="Название нового счёта"
                        required
                        maxLength={100}
                      />
                      <button className="mx-button" disabled={busy}>
                        Создать счёт
                      </button>
                    </form>
                    <div className="mx-tabs">
                      {[
                        ["trade", "Покупка / продажа"],
                        ["cash", "Пополнение / вывод"],
                        ["income", "Дивиденды / купоны"],
                        ["csv", "Импорт CSV"],
                      ].map(([k, t]) => (
                        <button
                          key={k}
                          className={tradeKind === k ? "active" : ""}
                          onClick={() => setTradeKind(k)}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                    <form
                      className="mx-form"
                      key={tradeKind}
                      onSubmit={(e) => {
                        e.preventDefault();
                        const f = new FormData(e.currentTarget);
                        const account_id = Number(f.get("account_id"));
                        const d = String(f.get("date"));
                        if (tradeKind === "trade")
                          void action("/trades", {
                            account_id,
                            symbol: f.get("symbol"),
                            trade_date: d,
                            side: f.get("side"),
                            quantity: Number(f.get("quantity")),
                            price: Number(f.get("price")),
                            fee: Number(f.get("fee")),
                            price_basis: f.get("price_basis"),
                            trade_uid: f.get("trade_uid"),
                          });
                        else if (tradeKind === "cash")
                          void action("/cash", {
                            account_id,
                            event_date: d,
                            direction: f.get("direction"),
                            amount: Number(f.get("amount")),
                          });
                        else if (tradeKind === "income")
                          void action("/income", {
                            account_id,
                            symbol: f.get("symbol"),
                            effective_date: d,
                            action_type: f.get("action_type"),
                            amount_per_security: Number(f.get("amount")),
                          });
                        else
                          void action("/import", {
                            account_id,
                            content: f.get("content"),
                          });
                      }}
                    >
                      <label>
                        Счёт
                        <select name="account_id" required>
                          {portfolio?.accounts.map((a) => (
                            <option key={a.account_id} value={a.account_id}>
                              {a.account_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      {tradeKind !== "csv" && (
                        <label>
                          Дата
                          <input
                            name="date"
                            type="date"
                            required
                            defaultValue={new Date().toISOString().slice(0, 10)}
                          />
                        </label>
                      )}
                      {["trade", "income"].includes(tradeKind) && (
                        <label>
                          Инструмент
                          <input
                            name="symbol"
                            placeholder="SBER или SECID облигации"
                            required
                          />
                        </label>
                      )}
                      {tradeKind === "trade" && (
                        <>
                          <label>
                            Операция
                            <select name="side">
                              <option value="buy">Покупка</option>
                              <option value="sell">Продажа</option>
                            </select>
                          </label>
                          <label>
                            Количество бумаг
                            <input
                              name="quantity"
                              type="number"
                              min="0.000001"
                              step="any"
                              required
                            />
                          </label>
                          <label>
                            Цена за бумагу в рублях
                            <input
                              name="price"
                              type="number"
                              min="0.000001"
                              step="any"
                              required
                            />
                          </label>
                          <label>
                            Тип цены
                            <select name="price_basis">
                              <option value="rub">Акция / фонд: рубли</option>
                              <option value="dirty_rub">
                                Облигация: рубли, включая НКД
                              </option>
                            </select>
                          </label>
                          <label>
                            Комиссия, ₽
                            <input
                              name="fee"
                              type="number"
                              min="0"
                              step="any"
                              defaultValue="0"
                              required
                            />
                          </label>
                          <label>
                            Уникальный номер операции
                            <input
                              name="trade_uid"
                              required
                              placeholder="Из отчёта брокера"
                            />
                          </label>
                        </>
                      )}
                      {tradeKind === "cash" && (
                        <label>
                          Направление
                          <select name="direction">
                            <option value="in">Пополнение</option>
                            <option value="out">Вывод</option>
                          </select>
                        </label>
                      )}
                      {tradeKind === "income" && (
                        <label>
                          Выплата
                          <select name="action_type">
                            <option value="cash_dividend">Дивиденды</option>
                            <option value="coupon">Купон</option>
                          </select>
                        </label>
                      )}
                      {["cash", "income"].includes(tradeKind) && (
                        <label>
                          {tradeKind === "income"
                            ? "Выплата на одну бумагу, ₽"
                            : "Сумма, ₽"}
                          <input
                            name="amount"
                            type="number"
                            step="any"
                            min="0.000001"
                            required
                          />
                        </label>
                      )}
                      {tradeKind === "csv" && (
                        <label className="mx-full">
                          CSV с колонками
                          symbol,trade_date,side,quantity,price,fee,price_basis,trade_uid
                          <textarea
                            name="content"
                            rows={6}
                            required
                            placeholder="SBER,2026-11-17,buy,10,294.58,0,rub,operation-1"
                          />
                        </label>
                      )}
                      <button
                        className="mx-button"
                        disabled={busy || !portfolio?.accounts.length}
                      >
                        {busy ? "Сохраняем…" : "Добавить операцию"}
                      </button>
                    </form>
                    {actionMessage && <Notice>{actionMessage}</Notice>}
                  </section>
                  <section className="mx-panel">
                    <h2>Позиции</h2>
                    <div className="mx-table-wrap">
                      <table className="mx-table">
                        <thead>
                          <tr>
                            <th>Бумага</th>
                            <th>Количество</th>
                            <th>Стоимость, ₽</th>
                            <th>Оценка</th>
                          </tr>
                        </thead>
                        <tbody>
                          {portfolio?.positions.map((p, i) => (
                            <tr key={`${p.symbol}-${i}`}>
                              <td>{p.symbol}</td>
                              <td>{format(p.quantity)}</td>
                              <td>
                                {p.price_available
                                  ? format(p.market_value_base)
                                  : "—"}
                              </td>
                              <td>
                                {!p.price_available
                                  ? "Нет котировки"
                                  : p.price_stale
                                    ? "Устарела"
                                    : "ISS"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {!portfolio?.positions.length && (
                      <div className="mx-empty">
                        Добавьте счёт и операции из вашего брокерского отчёта
                      </div>
                    )}
                    <h3>Доходность и риск</h3>
                    <div className="mx-indicators">
                      <div>
                        <span>XIRR, % годовых</span>
                        <b>{format(portfolio?.return_pct)}</b>
                      </div>
                      <div>
                        <span>
                          Просадка после{" "}
                          {portfolio?.drawdown_since ?? "начала наблюдений"}, %
                        </span>
                        <b>{format(portfolio?.drawdown_pct)}</b>
                      </div>
                    </div>
                    <h3>Концентрация по эмитентам</h3>
                    {Object.entries(portfolio?.issuer_weights ?? {}).map(
                      ([k, v]) => (
                        <div className="mx-macro-row" key={k}>
                          <span>Эмитент {k}</span>
                          <b>{v == null ? "—" : format(v * 100)}%</b>
                        </div>
                      ),
                    )}
                    <h3>Ожидаемые купоны</h3>
                    {portfolio?.calendar.slice(0, 20).map((c, i) => (
                      <div className="mx-macro-row" key={i}>
                        <span>
                          {c.date} · {c.symbol}
                        </span>
                        <b>{format(c.amount)} ₽</b>
                      </div>
                    ))}
                    <Notice>{portfolio?.limitations.join(" ")}</Notice>
                  </section>
                </>
              )}
            </>
          )}
          {["ai", "reports"].includes(section) && (
            <>
              {section === "ai" && (
                <Notice>
                  Числа и ссылки формируются из структурированных данных. ИИ
                  может отбирать подтверждённые факты; сценарии условны. В
                  публичной демонстрации платные модели не вызываются.
                </Notice>
              )}
              {!demo && (
                <div className="mx-report-actions">
                  <button
                    className="mx-button"
                    disabled={busy}
                    onClick={() =>
                      void action("/reports", {
                        period: "evening",
                        use_ai: false,
                      })
                    }
                  >
                    Сформировать обзор <BookOpen size={16} />
                  </button>
                  <button
                    className="mx-button secondary"
                    disabled={busy}
                    onClick={() =>
                      void action("/reports", {
                        period: "evening",
                        use_ai: true,
                      })
                    }
                  >
                    Отбор фактов с ИИ <Sparkles size={16} />
                  </button>
                </div>
              )}
              {actionMessage && <Notice>{actionMessage}</Notice>}
              {reports.length ? (
                reports.slice(0, section === "ai" ? 1 : 50).map(renderReport)
              ) : (
                <section className="mx-panel mx-empty">
                  Отчётов пока нет. Сформируйте первый обзор.
                </section>
              )}
            </>
          )}
          {section === "settings" && (
            <section className="mx-panel">
              <h2>Список наблюдения</h2>
              <p className="mx-muted">
                Инструменты разделяются по рынку. SECID и ISIN проверяются по
                справочнику MOEX.
              </p>
              {demo ? (
                <Notice>
                  В демонстрации настройки доступны для просмотра. Изменение
                  списка выполняется в локальном приложении.
                </Notice>
              ) : null}
              <form
                className="mx-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  const values = Object.fromEntries(
                    ["equities", "bonds", "indices"].map((k) => [
                      k,
                      String(f.get(k) ?? "")
                        .split(/[\s,]+/)
                        .filter(Boolean),
                    ]),
                  );
                  void action("/settings/watchlist", values, "PUT");
                }}
              >
                {[
                  ["equities", "Акции и фонды"],
                  ["bonds", "Облигации"],
                  ["indices", "Индексы"],
                ].map(([k, label]) => (
                  <label className="mx-full" key={k}>
                    {label}
                    <input
                      name={k}
                      disabled={demo}
                      defaultValue={market?.watchlist[k as keyof Watch].join(
                        ", ",
                      )}
                    />
                  </label>
                ))}
                {!demo && (
                  <button className="mx-button" disabled={busy}>
                    Сохранить список
                  </button>
                )}
              </form>
              {actionMessage && <Notice>{actionMessage}</Notice>}
              <hr />
              <h3>Подключения и приватность</h3>
              <p>
                Ключи ИИ и Telegram настраиваются на сервере через переменные
                окружения. Они никогда не включаются в публичную сборку.
              </p>
              <a
                href="https://github.com/hinaface1731-blip/MOEXinvest/blob/main/docs/RUSSIAN_MARKET_SETUP.md"
                target="_blank"
                rel="noreferrer"
              >
                Инструкция по запуску ↗
              </a>
            </section>
          )}
          <footer className="mx-footer">
            <span>
              <ShieldCheck size={14} /> Проверяемые источники · прозрачные
              расчёты
            </span>
            <span>Не является индивидуальной инвестиционной рекомендацией</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
