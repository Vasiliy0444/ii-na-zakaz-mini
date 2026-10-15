"""Проверка страницы в Chromium (Playwright). Запуск из корня репозитория:
    python3 scripts/qa.py               — локально (поднимает http.server)
    python3 scripts/qa.py <url>         — по живому адресу
    python3 scripts/qa.py <url> --shots <папка>  — плюс скрины блоков 1440 и 390

Проверяет: кнопка первого экрана видна без прокрутки (все 8 заголовков), нет прокрутки вбок,
нет ошибок в консоли и неудачных запросов, метка для бота собрана, нижняя панель появляется,
в вопросах открыт один пункт, мельче 14 px текста нет.
"""
from __future__ import annotations

import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
VIEWS = [(1440, 900), (1024, 768), (768, 1024), (390, 844), (375, 667), (320, 568)]
HOOKS = ["", "compare", "math_a", "math_b", "now", "zero", "clients", "home"]


def serve() -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}/", httpd


def main() -> int:
    args = sys.argv[1:]
    shots = None
    if "--shots" in args:
        shots = Path(args[args.index("--shots") + 1])
        shots.mkdir(parents=True, exist_ok=True)
        args = args[: args.index("--shots")]
    httpd = None
    base = args[0] if args else None
    if not base:
        base, httpd = serve()
    problems: list[str] = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        for w, h in VIEWS:
            mobile = w < 768
            ctx = br.new_context(viewport={"width": w, "height": h}, is_mobile=mobile, has_touch=mobile,
                                 device_scale_factor=2 if mobile else 1)
            for hook in HOOKS:
                pg = ctx.new_page()
                errors: list[str] = []
                pg.on("console", lambda m, e=errors: e.append(m.text) if m.type == "error" else None)
                pg.on("pageerror", lambda exc, e=errors: e.append(str(exc)))
                pg.on("requestfailed", lambda r, e=errors: e.append("FAILED " + r.url))
                pg.on("response", lambda r, e=errors: e.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
                url = base + (f"?utm_content=hook_{hook}_v1&utm_source=ig&utm_campaign=test" if hook else "")
                pg.goto(url, wait_until="networkidle")
                pg.evaluate("document.fonts.ready")
                info = pg.evaluate("""() => {
                  const cta = document.querySelector('#cta-hero').getBoundingClientRect();
                  const h1 = [...document.querySelectorAll('.hero h1')].filter(x => getComputedStyle(x).display !== 'none');
                  return {ctaBottom: cta.bottom, vh: innerHeight, scrollW: document.documentElement.scrollWidth, vw: innerWidth,
                          h1: h1.map(x => x.textContent.replace(/\\s+/g, ' ').trim()), hookAttr: document.documentElement.getAttribute('data-hook'),
                          start: window.__AB && window.__AB.start};
                }""")
                tag = f"{w}x{h} hook={hook or 'default'}"
                if info["ctaBottom"] > info["vh"]:
                    problems.append(f"{tag}: кнопка ниже первого экрана ({info['ctaBottom']:.0f} > {info['vh']})")
                if info["scrollW"] > info["vw"]:
                    problems.append(f"{tag}: прокрутка вбок ({info['scrollW']} > {info['vw']})")
                if len(info["h1"]) != 1:
                    problems.append(f"{tag}: видимых H1 {len(info['h1'])}")
                if hook and (info["hookAttr"] != hook):
                    problems.append(f"{tag}: data-hook={info['hookAttr']}")
                if not (info["start"] or "").startswith("vm-"):
                    problems.append(f"{tag}: метка start={info['start']}")
                if hook == "" :
                    # нижняя панель и вопросы — один раз на ширину
                    pg.evaluate("window.scrollTo({top: document.querySelector('#learn').offsetTop + 200, behavior: 'instant'})")
                    pg.wait_for_timeout(500)
                    if not pg.evaluate("document.querySelector('.dock').classList.contains('show')"):
                        problems.append(f"{tag}: нижняя панель не появилась после первого экрана")
                    pg.evaluate("document.querySelector('#start .btn').scrollIntoView({block: 'center', behavior: 'instant'})")
                    pg.wait_for_timeout(400)
                    if pg.evaluate("document.querySelector('.dock').classList.contains('show')"):
                        problems.append(f"{tag}: нижняя панель не спряталась рядом с другой кнопкой")
                    opened = pg.evaluate("""() => { const d=[...document.querySelectorAll('.qas details')]; d[2].open=true; return new Promise(r=>setTimeout(()=>r(d.filter(x=>x.open).length),200)); }""")
                    if opened != 1:
                        problems.append(f"{tag}: в вопросах открыто {opened}")
                    small = pg.evaluate("""() => [...document.querySelectorAll('body *')].filter(el => {
                        if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return false;
                        const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') return false;
                        const r = el.getBoundingClientRect(); if (!r.width || !r.height) return false;
                        return parseFloat(cs.fontSize) < 14; }).map(el => el.className + ': ' + getComputedStyle(el).fontSize).slice(0, 5)""")
                    if small:
                        problems.append(f"{tag}: мельче 14 px: {small}")
                    if shots and w in (1440, 390):
                        pg.goto(base + "?shot=1", wait_until="networkidle")
                        pg.evaluate("document.fonts.ready")
                        pg.wait_for_timeout(500)
                        for i, sec in enumerate(pg.query_selector_all(".page > section, .page > footer"), 1):
                            sec.screenshot(path=str(shots / f"{w}_{i:02d}-{sec.get_attribute('id')}.jpg"), type="jpeg", quality=82)
                        pg.goto(base, wait_until="networkidle")
                        pg.wait_for_timeout(800)
                        pg.screenshot(path=str(shots / f"{w}_00-first-screen.jpg"), type="jpeg", quality=85)
                for e in errors:
                    problems.append(f"{tag}: {e}")
                pg.close()
            ctx.close()
        br.close()
    if httpd:
        httpd.shutdown()
    if problems:
        print("ПРОБЛЕМЫ:")
        for pr in dict.fromkeys(problems):
            print(" -", pr)
        return 1
    print(f"OK: {len(VIEWS)} экранов × {len(HOOKS)} заголовков — кнопка в первом экране, без прокрутки вбок и ошибок")
    return 0


if __name__ == "__main__":
    sys.exit(main())
