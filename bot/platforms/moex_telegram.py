"""Private Telegram polling adapter using the existing sender and rate limiter."""
import json
import os
import time

import requests

from bot.dispatcher import RateLimiter
from src.config import get_config
from src.notification_sender.telegram_sender import TelegramSender
from src.services.moex_service import MOEXService, render_report
from src.services.russian_macro import russian_macro
from data_provider.base import DataFetchError

HELP = "/portfolio — портфель\n/market — рынок\n/stock SBER — акция\n/bond 26248 — облигация\n/news — новости ЦБ\n/risk — риски\n/help — справка"


class MOEXTelegram:
    def __init__(self, *, allowed_ids=None, service=None, sender=None):
        self.allowed = set(allowed_ids if allowed_ids is not None else
                           filter(None, os.getenv("MOEX_TELEGRAM_USER_IDS", "").split(",")))
        self.allowed = {str(i).strip() for i in self.allowed}
        self.service = service or MOEXService()
        self.sender = sender or TelegramSender(get_config())
        self.limiter = RateLimiter(max_requests=6, window_seconds=60)

    def handle(self, update):
        message = update.get("message") or {}
        user = str((message.get("from") or {}).get("id", ""))
        chat = message.get("chat") or {}
        # Authenticate before any data access; private chats only, deny by default.
        if user not in self.allowed or chat.get("type") != "private" or str(chat.get("id")) != user:
            return None
        if not self.limiter.is_allowed(user):
            return "Слишком много запросов. Повторите через минуту."
        parts = str(message.get("text", "")).split()
        command = parts[0].split("@")[0] if parts else "/help"
        if command == "/help" or command == "/start":
            return HELP
        if command == "/market":
            return render_report(self.service.report())
        if command in ("/portfolio", "/risk"):
            p = self.service.portfolio()
            return json.dumps({k: p[k] for k in ("total_equity", "profit", "issuer_weights", "complete", "limitations")}, ensure_ascii=False)
        if command in ("/stock", "/bond") and len(parts) == 2:
            data = self.service.instrument(parts[1])
            expected = "bonds" if command == "/bond" else "shares"
            if data["quote"]["market"] != expected:
                return "Тип инструмента не соответствует команде."
            q = data["quote"]
            return (f"{q['name']} ({q['secid']})\nЦена: {q['price']} {q['price_unit']}\n"
                    f"Время: {q['timestamp']} • {q['status']}\n{q['source']}\n" +
                    json.dumps(data["bond"] if expected == "bonds" else data["analysis"], ensure_ascii=False))
        if command == "/news":
            return "\n\n".join(f"{n['title']}\n{n['source']}" for n in russian_macro()["news"][:8]) or "Новости недоступны."
        return HELP

    def poll(self):
        token = get_config().telegram_bot_token
        if not token or not self.allowed:
            raise ValueError("Настройте TELEGRAM_BOT_TOKEN и MOEX_TELEGRAM_USER_IDS")
        offset = 0
        while True:
            try:
                response = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"offset": offset, "timeout": 25, "allowed_updates": '["message"]'}, timeout=35)
                response.raise_for_status()
                for update in response.json().get("result", []):
                    try:
                        text = self.handle(update)
                    except (ValueError, DataFetchError):
                        text = "Источник временно недоступен или инструмент не найден. Повторите позже."
                    if text is not None:
                        self.sender.send_to_telegram(text, chat_id=str(update["message"]["chat"]["id"]))
                    offset = update["update_id"] + 1
            except requests.RequestException:
                # Do not log URLs: Telegram embeds the credential in the URL.
                time.sleep(5)


if __name__ == "__main__":
    MOEXTelegram().poll()
