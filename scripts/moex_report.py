"""Daily reports with persistent files; Telegram sends only with explicit --send."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_provider.moex_provider import MOSCOW
from src.config import get_config
from src.notification_sender.telegram_sender import TelegramSender
from src.services.moex_service import MOEXService, render_report, reports_dir, save_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", choices=["morning", "evening"], default="evening")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--ai", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(MOSCOW).date().isoformat()
    marker = reports_dir() / f"sent-{stamp}-{args.period}.marker"
    if args.send and marker.exists():
        print("Report already sent for this Moscow date and period")
        return
    report = save_report(MOEXService().report(args.period, use_ai=args.ai))
    if args.send:
        if not TelegramSender(get_config()).send_to_telegram(render_report(report)):
            raise SystemExit("Telegram delivery failed; report retained for retry")
        marker.write_text(report["id"], encoding="utf-8")
    print(json.dumps({"report_id": report["id"], "source_errors": report["errors"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
