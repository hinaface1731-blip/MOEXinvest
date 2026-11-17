"""Public official CBR observations. Publication timestamps are never invented."""
from datetime import datetime
from functools import lru_cache
import time
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from defusedxml import ElementTree
import requests


def _fetch(url):
    response = requests.get(url, timeout=(5, 20))
    response.raise_for_status()
    return response


@lru_cache(maxsize=2)
def _macro(bucket):
    del bucket
    fetched = datetime.now().astimezone().isoformat()
    result = {"fetched_at": fetched, "observations": [], "news": [], "events": [], "errors": [],
              "limitations": ["Публикация показателя и дата наблюдения могут различаться; неизвестная дата публикации не подставляется.",
                              "Новости — официальные сообщения ЦБ; это не полная лента эмитентов."]}
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    try:
        root = ElementTree.fromstring(_fetch(url).content)
        on = datetime.strptime(root.attrib["Date"], "%d.%m.%Y").date().isoformat()
        for node in root.findall("Valute"):
            code = node.findtext("CharCode")
            if code in ("USD", "EUR", "CNY"):
                value = float(node.findtext("Value").replace(",", ".")) / int(node.findtext("Nominal"))
                result["observations"].append({"name": f"{code}/RUB", "value": value,
                    "unit": "RUB за единицу валюты", "observed_at": on, "published_at": None, "source": url})
    except (requests.RequestException, ValueError, KeyError, TypeError, ElementTree.ParseError) as exc:
        result["errors"].append({"source": url, "error": type(exc).__name__})
    url = "https://www.cbr.ru/hd_base/KeyRate/"
    try:
        soup = BeautifulSoup(_fetch(url).text, "html.parser")
        table = soup.select_one("table.data")
        if table is None:
            raise ValueError("CBR schema changed")
        cells = table.select("tr")[1].find_all("td")
        on = datetime.strptime(cells[0].get_text(strip=True), "%d.%m.%Y").date().isoformat()
        value = float(cells[1].get_text(strip=True).replace(",", "."))
        result["observations"].append({"name": "Ключевая ставка ЦБ", "value": value, "unit": "% годовых",
            "observed_at": on, "published_at": None, "source": url})
    except (requests.RequestException, ValueError, IndexError, TypeError) as exc:
        result["errors"].append({"source": url, "error": type(exc).__name__})
    url = "https://www.cbr.ru/hd_base/infl/"
    try:
        soup = BeautifulSoup(_fetch(url).text, "html.parser")
        table = soup.select_one("table.data")
        if table is None:
            raise ValueError("CBR inflation schema changed")
        cells = table.select("tr")[1].find_all("td")
        on = datetime.strptime(cells[0].get_text(strip=True), "%m.%Y").strftime("%Y-%m")
        value = float(cells[2].get_text(strip=True).replace(",", "."))
        result["observations"].append({"name": "Инфляция", "value": value, "unit": "% год к году",
            "observed_at": on, "published_at": None, "source": url})
    except (requests.RequestException, ValueError, IndexError, TypeError) as exc:
        result["errors"].append({"source": url, "error": type(exc).__name__})
    url = "https://www.cbr.ru/DKP/cal_mp/"
    try:
        soup = BeautifulSoup(_fetch(url).text, "html.parser")
        text = (soup.select_one("main") or soup).get_text(" ", strip=True)
        months = {name: i for i, name in enumerate("января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(), 1)}
        matches = re.findall(r"(\d{1,2})\s+(\w+)\s+(\d{4})\s+года\s+Заседание Совета директоров Банка России по\s+ключевой ставке", text)
        if not matches:
            raise ValueError("CBR calendar schema changed")
        for day, month, year in matches:
            on = datetime(int(year), months[month], int(day)).date().isoformat()
            if on >= datetime.now().date().isoformat():
                result["events"].append({"date": on, "title": "Заседание ЦБ по ключевой ставке", "source": url})
        result["events"] = sorted(result["events"], key=lambda e: e["date"])
    except (requests.RequestException, ValueError, KeyError) as exc:
        result["errors"].append({"source": url, "error": type(exc).__name__})
    url = "https://www.cbr.ru/rss/RssPress"
    try:
        root = ElementTree.fromstring(_fetch(url).content)
        for node in root.findall("./channel/item")[:15]:
            link = urljoin("https://www.cbr.ru/", node.findtext("link") or "")
            if not link.startswith("https://www.cbr.ru/"):
                continue
            result["news"].append({"title": node.findtext("title"), "source": link,
                                   "published_at": node.findtext("pubDate")})
    except (requests.RequestException, ValueError, ElementTree.ParseError) as exc:
        result["errors"].append({"source": url, "error": type(exc).__name__})
    return result


def russian_macro():
    return _macro(int(time.time() // 1800))
