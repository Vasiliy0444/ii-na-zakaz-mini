"""Сквозная проверка пикселя Meta и Метрики на живом aibuyurtma.com — события уходят ПО-НАСТОЯЩЕМУ.

Запуск — GitHub Actions → pixel-e2e → Run workflow (настоящий Google Chrome с окном под xvfb, чистая сеть).
Каждый заход помечен utm_content=claude_e2e_<время>: в Метрике такие визиты отфильтрованы,
в Events Manager их видно по адресу страницы. Нажимает кнопку на UZ и RU, Start в боте не нажимает.

    python3 scripts/pixel_e2e.py            — UZ и RU, по одному нажатию
"""
from __future__ import annotations

import json
import sys
import time

from playwright.sync_api import sync_playwright

SITE = "https://aibuyurtma.com/"
PIXEL_ID = "948019651369280"
PAGES = [("", "hero"), ("ru/", "program")]


def check_page(browser, path: str, place: str, tag: str) -> list[str]:
    log: list[str] = []
    ctx = browser.new_context(viewport={"width": 420, "height": 860})
    page = ctx.new_page()

    def on_response(resp) -> None:
        url = resp.url
        if "facebook.com/tr" in url:
            ev = url.split("ev=")[1].split("&")[0] if "ev=" in url else "POST"
            pid = url.split("id=")[1].split("&")[0] if "id=" in url else "?"
            log.append(f"META {ev} pixel={pid} -> {resp.status}")
        elif "mc.yandex.ru/watch" in url:
            log.append(f"METRIKA watch -> {resp.status}")

    page.on("response", on_response)
    page.goto(f"{SITE}{path}?utm_source=test&utm_campaign=e2e&utm_content={tag}", wait_until="networkidle")
    page.wait_for_timeout(3000)
    log.append("webdriver=%s, пиксели на странице: %s" % (
        page.evaluate("navigator.webdriver"),
        page.evaluate("window.fbq && fbq.getState ? fbq.getState().pixels.map(p => p.id) : 'нет fbq'")))
    log.append("бренды браузера: " + json.dumps(page.evaluate(
        "navigator.userAgentData ? navigator.userAgentData.brands.map(b => b.brand) : null")))
    cta = page.locator(f"a[data-cta][data-place='{place}']")
    cta.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    try:
        with ctx.expect_page(timeout=8000) as tg:
            cta.click()
        log.append(f"кнопка {place} → {tg.value.url[:80]}")
        tg.value.close()
    except Exception as e:  # noqa: BLE001 — отчёт, а не падение
        log.append(f"кнопка {place}: {type(e).__name__}: {e}")
    page.wait_for_timeout(4000)
    ctx.close()
    return log


def main() -> int:
    tag = "claude_e2e_" + time.strftime("%m%d_%H%M", time.gmtime())
    print(f"метка: {tag} (UTC {time.strftime('%H:%M', time.gmtime())})")
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False,
                                    args=["--disable-blink-features=AutomationControlled"])
        for path, place in PAGES:
            log = check_page(browser, path, place, tag)
            print(f"\n== {path or 'uz/'}\n" + "\n".join(log))
            sent = " ".join(log)
            ok &= f"META PageView pixel={PIXEL_ID} -> 200" in sent and f"META Lead pixel={PIXEL_ID} -> 200" in sent
        browser.close()
    print("\nИТОГ:", "PageView и Lead ушли в пиксель и приняты (200)" if ok else "НЕ все события ушли — смотри лог")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
