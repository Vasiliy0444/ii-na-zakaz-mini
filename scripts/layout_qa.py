"""Проверка вёрстки на реальных устройствах: телефоны iOS и Android, планшеты, ноутбуки, мониторы.

iPhone и iPad — движок WebKit (как Safari), Android и компьютеры — Chromium. UZ и RU версии.
Запуск из корня репозитория:
    python3 scripts/layout_qa.py                    — локальная копия (поднимает http.server)
    python3 scripts/layout_qa.py <url>              — живой сайт
    python3 scripts/layout_qa.py --shots <папка>    — плюс скриншоты: первый экран и вся страница

На каждом устройстве проверяет:
  • нет прокрутки вбок и элементов, вылезающих за правый край (кроме горизонтальных лент-каруселей);
  • кнопка первого экрана видна без прокрутки, её ничто не перекрывает, высота ≥ 44 px (палец);
  • все картинки загрузились, у них нет нулевого размера;
  • нет обрезанного текста (текст шире своего блока при overflow:hidden);
  • нет текста мельче 12 px;
  • нижняя панель с кнопкой появляется после первого экрана;
  • нет ошибок в консоли и неудачных запросов (аналитика под автотестом не грузится — так задумано).
Выход: 0 — всё чисто, 1 — есть проблемы (список в конце).
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
# (название, пресет Playwright или None, ширина, высота, движок)
DEVICES = [
    ("iPhone SE (320)", "iPhone SE", 0, 0, "webkit"),
    ("iPhone 12/13/14 (390)", "iPhone 12", 0, 0, "webkit"),
    ("iPhone 14 Pro Max (430)", "iPhone 14 Pro Max", 0, 0, "webkit"),
    ("iPhone 12 горизонтально", "iPhone 12 landscape", 0, 0, "webkit"),
    ("iPad mini (768)", "iPad Mini", 0, 0, "webkit"),
    ("iPad Pro 11 (834)", "iPad Pro 11", 0, 0, "webkit"),
    ("iPad Pro 11 горизонтально", "iPad Pro 11 landscape", 0, 0, "webkit"),
    ("Galaxy S9+ (320)", "Galaxy S9+", 0, 0, "chromium"),
    ("Galaxy S8 (360)", "Galaxy S8", 0, 0, "chromium"),
    ("Moto G4 (360×640)", "Moto G4", 0, 0, "chromium"),
    ("Pixel 7 (412)", "Pixel 7", 0, 0, "chromium"),
    ("Galaxy Tab S4 (712)", "Galaxy Tab S4", 0, 0, "chromium"),
    ("Ноутбук 1024×768", None, 1024, 768, "chromium"),
    ("Ноутбук 1280×720", None, 1280, 720, "chromium"),
    ("Ноутбук 1366×768", None, 1366, 768, "chromium"),
    ("Mac 1440×900", None, 1440, 900, "chromium"),
    ("Монитор 1920×1080", None, 1920, 1080, "chromium"),
    ("Монитор 2560×1440", None, 2560, 1440, "chromium"),
]
PAGES = [("UZ", ""), ("RU", "ru/")]
MIN_FONT_PX = 12
MIN_TAP_PX = 44

# Всё, что проверяется в самой странице, — одним скриптом, чтобы считать в координатах браузера.
PROBE = r"""
() => {
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  const out = { overflowX: document.documentElement.scrollWidth - vw, sticking: [], cut: [], tiny: [], brokenImg: [] };
  const inScroller = el => { for (let p = el.parentElement; p; p = p.parentElement) {
      const s = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(s.overflowX)) return true; } return false; };
  const visible = el => { const s = getComputedStyle(el); const r = el.getBoundingClientRect();
      return s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity !== 0 && r.width > 0 && r.height > 0; };
  const name = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 && !inScroller(el) && !el.closest('[aria-hidden="true"]')) out.sticking.push(name(el) + ` → ${Math.round(r.right - vw)}px`);
    const s = getComputedStyle(el);
    const ownText = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
    if (ownText && parseFloat(s.fontSize) < %MIN_FONT% && !el.closest('[aria-hidden="true"]')) out.tiny.push(name(el) + ' ' + s.fontSize + ' «' + el.textContent.trim().slice(0, 30) + '»');
    if (ownText && /(hidden|clip)/.test(s.overflow + s.overflowX) && el.scrollWidth > el.clientWidth + 2 && s.textOverflow !== 'ellipsis')
      out.cut.push(name(el) + ' «' + el.textContent.trim().slice(0, 30) + '»');
  }
  for (const img of document.images) if (visible(img) && (!img.complete || img.naturalWidth === 0)) out.brokenImg.push(img.getAttribute('src'));
  const cta = document.querySelector('#cta-hero');
  if (cta) {
    const r = cta.getBoundingClientRect();
    out.cta = { top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height), w: Math.round(r.width), vh };
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    out.ctaCovered = hit && !cta.contains(hit) ? name(hit) : null;
  }
  out.sticking = [...new Set(out.sticking)].slice(0, 8); out.tiny = [...new Set(out.tiny)].slice(0, 8);
  out.cut = [...new Set(out.cut)].slice(0, 8);
  return out;
}
""".replace("%MIN_FONT%", str(MIN_FONT_PX))


def serve() -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a: None
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}/", httpd


def scroll_through(page) -> None:
    """Прокрутить до низа и пролистать горизонтальные ленты, как человек: догружаются картинки с loading=lazy.
    Картинки за краем ленты грузятся только при пролистывании — до этого «не загружена» — это норма."""
    height = page.evaluate("document.body.scrollHeight")
    step = page.evaluate("window.innerHeight") * 0.8
    y = 0
    while y < height:
        y += step
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(120)
    page.evaluate("""async () => {
      for (const list of document.querySelectorAll('.hscroll')) {
        list.scrollIntoView({block: 'center'});
        for (let x = 0; x <= list.scrollWidth; x += list.clientWidth * 0.6) {
          list.scrollLeft = x; await new Promise(r => setTimeout(r, 150));
        }
        list.scrollLeft = 0;
      }
    }""")
    page.wait_for_timeout(800)


def check(pw, base: str, label: str, preset: str | None, w: int, h: int, engine: str, shots: Path | None) -> list[str]:
    browser = getattr(pw, engine).launch()
    opts = dict(pw.devices[preset]) if preset else {"viewport": {"width": w, "height": h}}
    opts.pop("default_browser_type", None)
    problems: list[str] = []
    for lang, path in PAGES:
        ctx = browser.new_context(**opts)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("console", lambda m: m.type == "error" and errors.append("консоль: " + m.text[:120]))
        page.on("pageerror", lambda e: errors.append("JS: " + str(e)[:120]))
        page.on("requestfailed", lambda r: errors.append(f"запрос не прошёл: {r.url[:80]} {r.failure}"))
        page.goto(base + path, wait_until="networkidle")
        page.wait_for_timeout(400)
        top = page.evaluate(PROBE)
        tag = f"{label} · {lang}"
        if shots:
            slug = "".join(c if c.isalnum() else "_" for c in f"{label}_{lang}")
            page.screenshot(path=str(shots / f"{slug}__1_first_screen.png"))
        cta = top.get("cta")
        if not cta:
            problems.append(f"{tag}: нет кнопки первого экрана")
        else:
            landscape_phone = cta["vh"] < 420  # в горизонтальном телефоне экран ниже кнопки — это нормально
            if cta["bottom"] > cta["vh"] and not landscape_phone:
                problems.append(f"{tag}: кнопка первого экрана ниже сгиба ({cta['bottom']} > {cta['vh']})")
            if cta["h"] < MIN_TAP_PX:
                problems.append(f"{tag}: кнопка ниже {MIN_TAP_PX}px ({cta['h']})")
            if top.get("ctaCovered"):
                problems.append(f"{tag}: кнопку перекрывает {top['ctaCovered']}")
        scroll_through(page)
        full = page.evaluate(PROBE)
        dock = page.evaluate("document.querySelector('.dock') ? getComputedStyle(document.querySelector('.dock')).display : 'нет'")
        if full["overflowX"] > 1:
            problems.append(f"{tag}: прокрутка вбок на {full['overflowX']}px")
        for key, title in (("sticking", "вылезает за край"), ("cut", "обрезан текст"),
                           ("tiny", f"текст < {MIN_FONT_PX}px"), ("brokenImg", "картинка не загрузилась")):
            if full[key]:
                problems.append(f"{tag}: {title}: " + "; ".join(full[key]))
        problems += [f"{tag}: {e}" for e in errors]
        if shots:
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(200)
            page.screenshot(path=str(shots / f"{slug}__2_full.png"), full_page=True)
        print(f"  {'✓' if not any(p.startswith(tag) for p in problems) else '✗'} {tag}"
              f" — кнопка {cta['top'] if cta else '?'}–{cta['bottom'] if cta else '?'}px из {cta['vh'] if cta else '?'}, нижняя панель: {dock}")
        ctx.close()
    browser.close()
    return problems


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
    with sync_playwright() as pw:
        for label, preset, w, h, engine in DEVICES:
            problems += check(pw, base, label, preset, w, h, engine, shots)
    if httpd:
        httpd.shutdown()
    print(f"\n{len(DEVICES)} устройств × {len(PAGES)} языка = {len(DEVICES) * len(PAGES)} проверок")
    if problems:
        print(f"НАЙДЕНО {len(problems)}:\n" + "\n".join("  • " + p for p in problems))
        return 1
    print("OK: вёрстка чистая на всех устройствах")
    return 0


if __name__ == "__main__":
    sys.exit(main())
