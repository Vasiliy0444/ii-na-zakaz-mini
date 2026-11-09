"""Мониторинг aibuyurtma.com: если сайт лёг — сообщение Васе в Телеграм.

Запускается из GitHub Actions каждые 10 минут (.github/workflows/uptime.yml). Только стандартная библиотека.

Что проверяет:
1. Домен не заблокирован регистратором (сервера имён в реестре .com, RDAP verisign).
   2.11.2026 Hostinger заблокировал домен за неподтверждённую почту — сервера имён стали *.dns-suspended.com.
2. Страница отдаёт 200, в ней есть пиксель Meta и счётчик Метрики (если номер задан), бот в js/main.js.
3. HTTPS-сертификат живёт ещё больше 14 дней.
4. До окончания домена больше 30 дней (автопродление выключено).

Пишет только при смене состояния («упал» / «снова работает») и напоминает, пока не починят:
раз в 3 часа, если сайт лежит, раз в сутки — если это предупреждение.

Запуск:
    python3 scripts/monitor.py           — проверить и при необходимости написать
    python3 scripts/monitor.py --dry     — только показать результат, ничего не слать
    python3 scripts/monitor.py --test    — прислать пробное сообщение с текущим состоянием
Переменные: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, METRIKA_ID (необязательно), MONITOR_STATE (файл состояния).
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

DOMAIN = "aibuyurtma.com"
SITE = f"https://{DOMAIN}/"
PIXEL_ID = "1825945541747362"
BOT_USERNAME = "uz_ai_school_bot"
RDAP_URL = f"https://rdap.verisign.com/com/v1/domain/{DOMAIN}"
DOH_NS_URL = f"https://dns.google/resolve?name={DOMAIN}&type=NS"
SUSPENDED_MARKERS = ("dns-suspended", "verification-hold", "suspended")

CERT_MIN_DAYS = 14
DOMAIN_MIN_DAYS = 30
REPEAT_DOWN_SEC = 3 * 3600
REPEAT_WARN_SEC = 24 * 3600
# Если реестр или сертификат не ответили, а до этого была проблема, состояние не трогаем (иначе ложные
# «упал / поднялся»), но не дольше 6 часов — чтобы вечный сбой реестра не заглушил мониторинг.
MAX_HOLD_SEC = 6 * 3600
PAGE_ATTEMPTS = 2
PAGE_RETRY_PAUSE_SEC = 20
TIMEOUT_SEC = 20
USER_AGENT = "aibuyurtma-uptime-monitor/1.0"

DOWN = "down"
WARN = "warn"


@dataclass(frozen=True)
class Problem:
    key: str
    level: str  # DOWN — сайт не работает, WARN — работает, но скоро сломается
    text: str


@dataclass(frozen=True)
class Response:
    status: int
    body: str


Fetch = Callable[[str], Response]


def http_get(url: str) -> Response:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as r:
            return Response(r.status, r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return Response(e.code, "")


def days_until(iso_or_dt: str | datetime, now: datetime) -> float:
    dt = iso_or_dt if isinstance(iso_or_dt, datetime) else datetime.fromisoformat(iso_or_dt.replace("Z", "+00:00"))
    return (dt - now).total_seconds() / 86400


# ---------- проверки: каждая возвращает (проблемы, проверка прошла полностью) ----------

def is_suspended(ns: list[str]) -> bool:
    return any(m in name for name in ns for m in SUSPENDED_MARKERS)


def suspended_problem(ns: list[str]) -> Problem:
    return Problem(
        "domain_suspended", DOWN,
        "Домен заблокирован регистратором (Hostinger): сервера имён "
        f"{', '.join(ns)}.\nЧто сделать: подтверди почту владельца — письмо от Hostinger "
        "«Verify your email» или hPanel → Домены → aibuyurtma.com → «Подтвердить». "
        "После подтверждения сайт поднимется за 1–24 часа.",
    )


def nameservers_from_doh(fetch: Fetch) -> list[str]:
    """Запасной путь, если реестр не ответил: сервера имён через публичный DNS Google."""
    try:
        resp = fetch(DOH_NS_URL)
        answers = json.loads(resp.body).get("Answer", []) if resp.status == 200 else []
    except (OSError, ValueError) as e:
        print(f"DNS Google недоступен: {e}", file=sys.stderr)
        return []
    return [a.get("data", "").lower().rstrip(".") for a in answers]


def check_registry(fetch: Fetch, now: datetime) -> tuple[list[Problem], bool]:
    """Сервера имён и срок домена — из реестра .com (RDAP)."""
    data = None
    try:
        resp = fetch(RDAP_URL)
        data = json.loads(resp.body) if resp.status == 200 else None
        if not data:
            print(f"RDAP ответил {resp.status}", file=sys.stderr)
    except (OSError, ValueError) as e:
        print(f"RDAP недоступен: {e}", file=sys.stderr)
    if not data:
        ns = nameservers_from_doh(fetch)
        return ([suspended_problem(ns)] if is_suspended(ns) else []), False

    problems: list[Problem] = []
    ns = [n.get("ldhName", "").lower() for n in data.get("nameservers", [])]
    if is_suspended(ns):
        problems.append(suspended_problem(ns))
    expiry = next((e["eventDate"] for e in data.get("events", []) if e.get("eventAction") == "expiration"), None)
    if expiry:
        left = days_until(expiry, now)
        if left < DOMAIN_MIN_DAYS:
            problems.append(Problem(
                "domain_expiring", WARN,
                f"Домен {DOMAIN} истекает через {max(int(left), 0)} дн. ({expiry[:10]}). "
                "Автопродление выключено — продли в hPanel → Домены.",
            ))
    return problems, True


def check_page(fetch: Fetch, metrika_id: str, sleep: Callable[[float], None] = time.sleep) -> list[Problem]:
    """Страница открывается и в ней на месте пиксель, Метрика и бот. Две попытки, чтобы не дёргать из-за мигания."""
    error = ""
    for attempt in range(PAGE_ATTEMPTS):
        try:
            resp = fetch(SITE)
            if resp.status == 200:
                break
            error = f"сайт ответил кодом {resp.status}"
        except (OSError, ValueError) as e:
            error = f"сайт не отвечает ({type(e).__name__})"
            print(f"попытка {attempt + 1}: {e}", file=sys.stderr)
        if attempt + 1 < PAGE_ATTEMPTS:
            sleep(PAGE_RETRY_PAUSE_SEC)
    else:
        return [Problem(
            "site_down", DOWN,
            f"Сайт {SITE} не открывается: {error}.\nЧто сделать: проверь DNS домена в hPanel (A-записи на GitHub Pages) "
            "и статус GitHub Pages в репозитории ii-na-zakaz-mini → Settings → Pages.",
        )]

    problems: list[Problem] = []
    if PIXEL_ID not in resp.body:
        problems.append(Problem("pixel_missing", DOWN, f"На странице нет пикселя Meta {PIXEL_ID} — реклама не видит заявки."))
    if metrika_id and metrika_id not in resp.body:
        problems.append(Problem("metrika_missing", WARN, f"На странице нет счётчика Яндекс Метрики {metrika_id}."))
    try:
        js = fetch(SITE + "js/main.js")
        if js.status != 200 or BOT_USERNAME not in js.body:
            problems.append(Problem("bot_link_missing", DOWN, f"Кнопки не ведут в бота @{BOT_USERNAME} (js/main.js)."))
    except (OSError, ValueError) as e:
        problems.append(Problem("bot_link_missing", DOWN, f"Не загрузился js/main.js — кнопки не работают ({e})."))
    return problems


def cert_expiry(host: str) -> datetime:
    ctx = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=TIMEOUT_SEC) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            not_after = tls.getpeercert()["notAfter"]
    return datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), tz=timezone.utc)


def check_cert(get_expiry: Callable[[str], datetime], now: datetime) -> tuple[list[Problem], bool]:
    try:
        left = days_until(get_expiry(DOMAIN), now)
    except (OSError, ValueError, KeyError) as e:
        print(f"сертификат не проверить: {e}", file=sys.stderr)
        return [], False  # если HTTPS не работает совсем, это уже поймала check_page
    if left < CERT_MIN_DAYS:
        return [Problem(
            "cert_expiring", WARN,
            f"HTTPS-сертификат истекает через {max(int(left), 0)} дн. GitHub Pages продлевает его сам, "
            "если домен смотрит на GitHub — проверь DNS в Hostinger.",
        )], True
    return [], True


def run_checks(
    fetch: Fetch, get_expiry: Callable[[str], datetime], metrika_id: str, now: datetime
) -> tuple[list[Problem], bool]:
    """(проблемы, все проверки получили ответ)."""
    registry, registry_ok = check_registry(fetch, now)
    if any(p.key == "domain_suspended" for p in registry):
        return registry, registry_ok  # причина ясна: страница и сертификат упали из-за блокировки
    cert, cert_ok = check_cert(get_expiry, now)
    return registry + check_page(fetch, metrika_id) + cert, registry_ok and cert_ok


# ---------- когда писать ----------

def decide(prev: dict, problems: list[Problem], now_ts: float) -> tuple[str | None, dict]:
    """Возвращает (текст сообщения или None, новое состояние). prev не меняется."""
    keys = sorted(p.key for p in problems)
    prev_keys = sorted(prev.get("problems", []))
    last_alert = float(prev.get("last_alert", 0))

    if not problems:
        state = {"problems": [], "last_alert": 0, "since": None}
        if prev_keys:
            return f"✅ {DOMAIN} снова работает. Всё на месте: страница, пиксель, бот.", state
        return None, state

    since = prev.get("since") if prev_keys else now_ts
    since = since or now_ts
    is_down = any(p.level == DOWN for p in problems)
    repeat = REPEAT_DOWN_SEC if is_down else REPEAT_WARN_SEC
    changed = keys != prev_keys
    if not changed and now_ts - last_alert < repeat:
        return None, {"problems": keys, "last_alert": last_alert, "since": since}

    head = f"🔴 {DOMAIN} НЕ РАБОТАЕТ — подними сайт" if is_down else f"⚠️ {DOMAIN}: скоро сломается"
    if not changed:
        hours = int((now_ts - since) // 3600)
        head += f" (напоминание: проблема уже {hours} ч)"
    body = "\n\n".join(f"• {p.text}" for p in problems)
    text = f"{head}\n\n{body}\n\nПроверка: {SITE}"
    return text, {"problems": keys, "last_alert": now_ts, "since": since}


def plan_alert(prev: dict, problems: list[Problem], complete: bool, now_ts: float) -> tuple[str | None, dict]:
    """decide() + защита от ложных «упал / поднялся», когда часть проверок не получила ответа."""
    if not complete and prev.get("problems"):
        held = float(prev.get("held_since") or now_ts)
        if now_ts - held < MAX_HOLD_SEC:
            print("проверка неполная — состояние не меняю", file=sys.stderr)
            return None, {**prev, "held_since": held}
    return decide(prev, problems, now_ts)


# ---------- состояние и Телеграм ----------

def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def send_telegram(token: str, chat_id: str, text: str) -> None:
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as r:
            ok = json.loads(r.read()).get("ok")
    except urllib.error.HTTPError as e:
        # токен в текст ошибки не попадает: печатаем только код и описание Телеграма
        raise SystemExit(f"Телеграм не принял сообщение: {e.code} {e.read().decode('utf-8', 'replace')[:200]}") from None
    if not ok:
        raise SystemExit("Телеграм ответил ok=false")


def main(argv: list[str]) -> int:
    dry, test = "--dry" in argv, "--test" in argv
    now = datetime.now(timezone.utc)
    problems, complete = run_checks(http_get, cert_expiry, os.environ.get("METRIKA_ID", "").strip(), now)
    for p in problems:
        print(f"[{p.level}] {p.key}: {p.text}")
    if not problems:
        print("всё в порядке")

    if test:
        status = "сейчас всё работает ✅" if not problems else "сейчас есть проблемы:\n" + "\n".join(f"• {p.text}" for p in problems)
        text = (f"Мониторинг {DOMAIN} подключён. Проверка каждые 10 минут, пишу только когда что-то сломалось "
                f"или починилось.\n\n{status}\n\nВажно: GitHub выключает расписание, если в репозитории "
                "60 дней не было изменений, — тогда придёт письмо от GitHub, нажми в нём «Enable».")
    state_path = Path(os.environ.get("MONITOR_STATE", ".monitor/state.json"))
    state = None
    if not test:
        text, state = plan_alert(load_state(state_path), problems, complete, now.timestamp())

    if text and dry:
        print("--- сообщение ---\n" + text)
    elif text:
        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat:
            # Не падаем: иначе GitHub шлёт письмо об ошибке каждые 10 минут, пока бот не подключён.
            # Состояние не сохраняем — после подключения первое же сообщение уйдёт.
            print("нет TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID — запусти «Подключить уведомления о сайте.command»",
                  file=sys.stderr)
            return 0
        send_telegram(token, chat, text)  # упадёт — состояние ниже не сохранится, следующий запуск повторит
        print("сообщение отправлено")
    # состояние — только после успешной отправки, иначе сообщение потеряется
    if state is not None and not dry:
        save_state(state_path, state)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
