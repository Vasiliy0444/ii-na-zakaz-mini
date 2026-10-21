"""Собирает страницу на двух языках из src/index.src.html.

Узбекская версия (главная, реклама идёт на Узбекистан) — index.html в корне, тексты из src/i18n/uz.json.
Русская — ru/index.html, тексты прямо из src/index.src.html. Переключатель языка — в первом экране.

Что делает:
1. Подставляет детали образца из src/parts.json: рваные края, силуэт города, иконки, начинку кнопки.
2. Делает 7 заголовков под хуки из js/hooks.js (один источник текста) и скрипт в <head>, который выбирает хук до отрисовки.
3. Типографика в тексте: неразрывные пробелы после коротких слов и перед тире, склеенные диапазоны «2–3».
4. Добавляет к css/js метку версии ?v=<хеш>, чтобы GitHub Pages не отдавал старые файлы из кэша.

Запуск из корня репозитория: python3 scripts/build.py
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "index.src.html"
PARTS = ROOT / "src" / "parts.json"
HOOKS_JS = ROOT / "js" / "hooks.js"
UZ = ROOT / "src" / "i18n" / "uz.json"
SITE = "https://aibuyurtma.com/"
CYRILLIC = re.compile(r"[А-Яа-яЁё]")

# Та же логика, что pickHook в js/hooks.js; совпадение проверяет tests/hooks.test.mjs.
HEAD_HOOK_SCRIPT = (
    '<script id="hook-head">/* до отрисовки: какой заголовок показать по метке utm_content (логика = pickHook из js/hooks.js) */\n'
    "(function(){try{var w=(new URLSearchParams(location.search).get('utm_content')||'').toLowerCase().split(/[^a-z0-9]+/)"
    ".filter(Boolean),k=null,i=w.indexOf('math');if(i!==-1){k=w[i+1]==='a'?'math_a':'math_b';}else{var keys=['compare','clients','zero','home','now'];"
    "for(var j=0;j<keys.length;j++){if(w.indexOf(keys[j])!==-1){k=keys[j];break;}}}"
    "if(k){document.documentElement.setAttribute('data-hook',k);}"
    # вариант первого экрана для выбора (?hero=b|c), без метки — вариант a
    "var h=(new URLSearchParams(location.search).get('hero')||'').toLowerCase();"
    "if(h==='b'||h==='c'){document.documentElement.setAttribute('data-hero',h);}}catch(e){}})();</script>"
)

SHORT_WORDS = (
    "в|во|к|ко|с|со|у|о|об|и|а|но|на|по|за|из|от|до|не|ни|же|бы|для|без|при|про|под|что|как|это|чем|или|их|ты|мы|её|его|им"
)
NBSP = " "
WJ = "⁠"


def read_hooks() -> dict[str, list[str]]:
    body = HOOKS_JS.read_text(encoding="utf-8").split("export const HOOKS = {", 1)[1].split("};", 1)[0]
    hooks = {}
    for key, arr in re.findall(r"(\w+):\s*\[(.*?)\],", body):
        hooks[key] = re.findall(r"'((?:[^'\\]|\\.)*)'", arr)
    if len(hooks) != 7:
        raise SystemExit(f"ожидалось 7 хуков в js/hooks.js, найдено {len(hooks)}")
    return hooks


def hook_h1s(hooks: dict[str, list[str]]) -> str:  # тексты RU; узбекские подставит translate() по data-i18n
    rows = []
    for key, lines in hooks.items():
        spans = []
        for cls, text in zip(("line a", "line b pink", "line c"), lines):
            spans.append(f'<span class="{cls}" data-i18n="hook.{key}.{cls[-1] if cls != "line b pink" else "b"}">{text}</span>')
        rows.append(f'        <h1 class="d1 d1--hook worn" data-hook-for="{key}">{" ".join(spans)}</h1>')
    return "\n".join(rows)


def typography(text: str, lang: str = "ru") -> str:
    text = re.sub(r"(\d)–(\d)", rf"\1{WJ}–{WJ}\2", text)
    text = re.sub(r"[ ]+→", f"{NBSP}→", text)  # стрелка кнопки не уезжает на отдельную строку
    if lang == "uz":
        text = text.replace("AI-", "AI\u2011")  # неразрывный дефис: «AI-mutaxassis» не рвётся по строкам
        text = re.sub(r"[ ]+—", f"{NBSP}—", text)
        return re.sub(r"(\d)[ ]+(ta|mln|ming|so‘m|kishi|mijoz|oy|yil)\b", rf"\1{NBSP}\2", text)
    text = re.sub(rf"(?<![0-9A-Za-zА-Яа-яЁё])({SHORT_WORDS})[ ]+(?=\S)", rf"\1{NBSP}", text, flags=re.IGNORECASE)
    text = re.sub(r"[ ]+—", f"{NBSP}—", text)
    text = re.sub(r"(\d)[ ]+(млн|тыс|сум|лет|компан|заказ|урок|вечер|клиент|человек|услуг)", rf"\1{NBSP}\2", text)
    return text


def apply_typography(html: str, lang: str = "ru") -> str:
    out, skip = [], False
    for part in re.split(r"(<[^>]+>)", html):
        if part.startswith("<"):
            tag = part.lower()
            if tag.startswith(("<script", "<style", "<title")):
                skip = True
            elif tag.startswith(("</script", "</style", "</title")):
                skip = False
            out.append(part)
        else:
            out.append(part if skip else typography(part, lang))
    return "".join(out)


def bust(html: str) -> str:
    def repl(m: re.Match) -> str:
        path = m.group(2)
        digest = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()[:8]
        return f'{m.group(1)}{path}?v={digest}"'

    return re.sub(r'((?:href|src)=")((?:css|js)/[\w.-]+\.(?:css|js))"', repl, html)


def element_spans(html: str, key: str) -> list[tuple[int, int]]:
    """Границы содержимого всех элементов с data-i18n="key" (между > открывающего и </tag> закрывающего тега)."""
    spans = []
    for m in re.finditer(rf'<(\w+)\b[^>]*\sdata-i18n="{re.escape(key)}"[^>]*>', html):
        tag, depth, pos = m.group(1), 1, m.end()
        for t in re.finditer(rf"<(/?){tag}\b[^>]*>", html[pos:]):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                spans.append((pos, pos + t.start()))
                break
        else:
            raise SystemExit(f"не закрыт тег {tag} у {key}")
    return spans


def translate(html: str, uz: dict) -> str:
    keys = set(re.findall(r'data-i18n="([\w.]+)"', html))
    missing, extra = keys - uz["text"].keys(), uz["text"].keys() - keys
    if missing or extra:
        raise SystemExit(f"src/i18n/uz.json: нет перевода {sorted(missing)}; лишние ключи {sorted(extra)}")
    for key in keys:
        for start, end in reversed(element_spans(html, key)):
            html = html[:start] + uz["text"][key] + html[end:]
    for ru, tr in uz["replace"] + list(uz["img"].items()):
        if ru not in html:
            raise SystemExit(f"src/i18n/uz.json: не найдено для замены: {ru[:70]}")
        html = html.replace(ru, tr)
    html = html.replace('<html lang="ru">', '<html lang="uz">')
    visible = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    left = sorted(set(m.group(0) for m in re.finditer(r"[^<>\"]{0,30}[А-Яа-яЁё][^<>\"]{0,30}", visible)))
    if left:
        raise SystemExit(f"в узбекской версии осталась кириллица: {left[:5]}")
    return html


def lang_switch(lang: str) -> str:
    uz_href, ru_href = ("./", "ru/") if lang == "uz" else ("../", "./")
    cur = {"uz": ' aria-current="page"', "ru": ""} if lang == "uz" else {"uz": "", "ru": ' aria-current="page"'}
    return (f'<nav class="lang-sw" aria-label="{"Til" if lang == "uz" else "Язык"}">'
            f'<a href="{uz_href}" lang="uz" hreflang="uz"{cur["uz"]}>UZ</a>'
            f'<a href="{ru_href}" lang="ru" hreflang="ru"{cur["ru"]}>RU</a></nav>')


def to_subdir(html: str) -> str:
    """Русская версия лежит в ru/: свои файлы — на уровень выше."""
    html = re.sub(r'((?:href|src|srcset)=")((?:assets|css|js)/|privacy\.html)', r"\1../\2", html)
    return html.replace(f'content="{SITE}"', f'content="{SITE}ru/"')


def render(lang: str) -> str:
    html = SRC.read_text(encoding="utf-8")
    parts = json.loads(PARTS.read_text(encoding="utf-8"))
    html = html.replace("{{HEAD_HOOK_SCRIPT}}", HEAD_HOOK_SCRIPT)
    html = html.replace("{{HOOK_H1S}}", hook_h1s(read_hooks()))
    for key, value in parts.items():
        if not key.startswith("_"):
            html = html.replace("{{" + key + "}}", value)
    html = html.replace("{{LANG_SWITCH}}", lang_switch(lang))
    left = re.findall(r"\{\{[A-Z_a-z]+\}\}", html)
    if left:
        raise SystemExit(f"не заполнены места: {sorted(set(left))}")
    if lang == "uz":
        html = translate(html, json.loads(UZ.read_text(encoding="utf-8")))
    html = bust(apply_typography(html, lang))
    return to_subdir(html) if lang == "ru" else html


def main() -> None:
    for lang, out in (("uz", ROOT / "index.html"), ("ru", ROOT / "ru" / "index.html")):
        html = render(lang)
        out.parent.mkdir(exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"{out.relative_to(ROOT)} собран ({lang}): {len(html) // 1024} КБ")


if __name__ == "__main__":
    main()
