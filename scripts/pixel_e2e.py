"""Сквозная проверка аналитики на живом aibuyurtma.com: пиксель Meta + Яндекс Метрика. События уходят ПО-НАСТОЯЩЕМУ.

Запуск — GitHub Actions → pixel-e2e → Run workflow (настоящий Google Chrome с окном под xvfb, чистая сеть).
Метка визита: utm_source=test&utm_content=claude_test_e2e_<время>. В Метрике такие заходы отфильтрованы
(фильтр «claude_test» в infra/metrika/ym.py), в Events Manager их видно по адресу страницы.
Start в боте не нажимает — только открывает ссылку t.me и сразу закрывает вкладку.

Сценарии, для UZ и RU:
  1. Путь посетителя: открыл → дочитал программу, «Кто ведёт», финал → открыл вопрос → листнул бонус →
     нажал кнопку первого экрана → нажал ещё одну. Ждём: PageView, Lead один раз, все 6 целей Метрики один раз.
  2. Каждая кнопка в отдельном заходе (program, final, faq, dock): Lead с правильным местом кнопки.

    python3 scripts/pixel_e2e.py        — код выхода 0, если всё сошлось
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import sync_playwright

SITE = "https://aibuyurtma.com/"
PIXEL_ID = "948019651369280"
METRIKA_ID = "114152022"
BOT = "https://t.me/uz_ai_school_bot?start="
GOALS = ["view_program", "view_mentor", "view_final", "faq_open", "bonus_flip", "lead"]
LANGS = [("UZ", ""), ("RU", "ru/")]
SINGLE_BUTTONS = ["program", "final", "faq", "dock"]


class Recorder:
    """Собирает отправки в Meta и Метрику и ответы на них."""

    def __init__(self, page) -> None:
        self.meta: list[tuple[str, str, str]] = []  # (событие, пиксель, место кнопки)
        self.meta_status: list[int] = []
        self.goals: list[str] = []
        self.metrika_hits = 0
        self.metrika_status: list[int] = []
        page.on("request", self.on_request)
        page.on("response", self.on_response)

    def on_request(self, req) -> None:
        url = req.url
        if "facebook.com/tr" in url and "ev=" in url:
            q = parse_qs(urlparse(url).query)
            self.meta.append((q.get("ev", ["?"])[0], q.get("id", ["?"])[0], q.get("cd[content_category]", [""])[0]))
        elif "mc.yandex." in url and f"/watch/{METRIKA_ID}" in url:
            self.metrika_hits += 1
            page_url = unquote(parse_qs(urlparse(url).query).get("page-url", [""])[0])
            if page_url.startswith("goal://"):
                self.goals.append(page_url.rsplit("/", 1)[-1])

    def on_response(self, resp) -> None:
        if "facebook.com/tr" in resp.url:
            self.meta_status.append(resp.status)
        elif "mc.yandex." in resp.url and f"/watch/{METRIKA_ID}" in resp.url:
            self.metrika_status.append(resp.status)

    def events(self, name: str) -> list[tuple[str, str, str]]:
        return [m for m in self.meta if m[0] == name]


def click_cta(ctx, page, locator) -> str:
    """Нажать кнопку в бота, вернуть адрес открывшейся вкладки и закрыть её (Start в боте не жмём)."""
    with ctx.expect_page(timeout=8000) as tg:
        locator.click()
    url = tg.value.url
    tg.value.close()
    page.wait_for_timeout(2500)
    return url


def journey(browser, lang: str, path: str, tag: str) -> tuple[list[str], list[str]]:
    ctx = browser.new_context(viewport={"width": 412, "height": 860})
    page = ctx.new_page()
    rec = Recorder(page)
    ok: list[str] = []
    bad: list[str] = []
    page.goto(f"{SITE}{path}?utm_source=test&utm_campaign=e2e&utm_content={tag}", wait_until="networkidle")
    page.wait_for_timeout(3000)
    for block in ("program", "mentor", "start", "faq"):
        page.locator(f"#{block}").scroll_into_view_if_needed()
        page.wait_for_timeout(900)
    page.locator("#faq details summary").first.click()
    page.wait_for_timeout(700)
    page.locator("[data-file-next]").first.scroll_into_view_if_needed()
    page.locator("[data-file-next]").first.click()
    page.wait_for_timeout(700)
    page.locator("#top").scroll_into_view_if_needed()
    bot_url = click_cta(ctx, page, page.locator("#cta-hero"))
    final = page.locator("a[data-cta][data-place='final']")
    final.scroll_into_view_if_needed()
    click_cta(ctx, page, final)
    page.wait_for_timeout(2000)
    ctx.close()

    def check(cond: bool, text: str) -> None:
        (ok if cond else bad).append(f"{lang}: {text}")

    pv = rec.events("PageView")
    leads = rec.events("Lead")
    check(len(pv) == 1 and pv[0][1] == PIXEL_ID, f"Meta PageView ×{len(pv)} → пиксель {pv[0][1] if pv else '—'}")
    check(len(leads) == 1 and leads[0][1] == PIXEL_ID and leads[0][2] == "hero",
          f"Meta Lead ×{len(leads)} после двух нажатий (место {leads[0][2] if leads else '—'})")
    check(bool(rec.meta_status) and all(s in (200, 302) for s in rec.meta_status),
          f"Meta отвечает: {dict(Counter(rec.meta_status))}")
    check(rec.metrika_hits > 0 and all(s in (200, 302) for s in rec.metrika_status),
          f"Метрика: {rec.metrika_hits} отправок, ответы {dict(Counter(rec.metrika_status))}")
    counts = Counter(rec.goals)
    for goal in GOALS:
        check(counts[goal] == 1, f"цель Метрики {goal} ×{counts[goal]}")
    check(bot_url.startswith(BOT) and tag in bot_url, f"кнопка открывает бота с меткой: {bot_url[:90]}")
    return ok, bad


def single_button(browser, lang: str, path: str, place: str, tag: str) -> tuple[list[str], list[str]]:
    ctx = browser.new_context(viewport={"width": 412, "height": 860})
    page = ctx.new_page()
    rec = Recorder(page)
    page.goto(f"{SITE}{path}?utm_source=test&utm_campaign=e2e&utm_content={tag}", wait_until="networkidle")
    page.wait_for_timeout(2500)
    if place == "dock":  # нижняя панель видна после первого экрана, пока на экране нет другой кнопки
        page.locator("#mentor").scroll_into_view_if_needed()
        page.wait_for_timeout(1200)
        btn = page.locator(".dock a[data-cta]")
    else:
        btn = page.locator(f"a[data-cta][data-place='{place}']")
        btn.scroll_into_view_if_needed()
        page.wait_for_timeout(600)
    try:
        url = click_cta(ctx, page, btn)
    except Exception as e:  # noqa: BLE001 — это отчёт
        url = f"не нажалась ({type(e).__name__})"
    ctx.close()
    leads = rec.events("Lead")
    good = len(leads) == 1 and leads[0][1] == PIXEL_ID and leads[0][2] == place and "lead" in rec.goals
    line = f"{lang}: кнопка «{place}» → Lead ×{len(leads)} место {leads[0][2] if leads else '—'}, цель lead {'есть' if 'lead' in rec.goals else 'нет'}, бот {'да' if url.startswith(BOT) else url}"
    return ([line], []) if good else ([], [line])


def main() -> int:
    tag = "claude_test_e2e_" + time.strftime("%m%d_%H%M", time.gmtime())
    print(f"метка: {tag} (UTC {time.strftime('%H:%M', time.gmtime())})")
    ok: list[str] = []
    bad: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False,
                                    args=["--disable-blink-features=AutomationControlled"])
        for lang, path in LANGS:
            o, b = journey(browser, lang, path, tag)
            ok += o
            bad += b
            for place in SINGLE_BUTTONS:
                o, b = single_button(browser, lang, path, place, tag)
                ok += o
                bad += b
        browser.close()
    print("\n".join(f"  ✓ {x}" for x in ok))
    if bad:
        print("\n".join(f"  ✗ {x}" for x in bad))
    print(f"\nИТОГ: {len(ok)} проверок прошло, {len(bad)} не прошло")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
