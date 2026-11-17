"""Export ONLY public market data. Never instantiate portfolio or read user reports."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_provider.base import DataFetchError
from data_provider.moex_provider import MOSCOW
from src.services.moex_service import MOEXService, ROOT
from src.services.russian_macro import russian_macro


def export(destination):
    service = MOEXService()
    # Deliberately ignore local user watchlists and all runtime report/portfolio files.
    configured = json.loads((ROOT / "config/moex_watchlist.json").read_text(encoding="utf-8"))
    public_watch = {key: configured[key] for key in ("equities", "bonds", "indices")}
    market = service.market(watch=public_watch)
    if not market["instruments"]:
        raise RuntimeError("No real market data; refusing to publish an empty or synthetic snapshot")
    instruments = {}
    for q in market["instruments"]:
        try:
            instruments[q["secid"]] = service.instrument(q["secid"])
        except (DataFetchError, ValueError) as exc:
            market["errors"].append({"symbol": q["secid"], "error": str(exc)})
    public = {"demo": True, "generated_at": datetime.now(MOSCOW).isoformat(),
              "market": market, "instruments": instruments, "macro": russian_macro(),
              "report": service.report(market=market), "notice": "Публичный снимок реальных данных. Личные данные и ключи отсутствуют."}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(public, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"Exported {len(instruments)} instruments to {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    export(parser.parse_args().output)
