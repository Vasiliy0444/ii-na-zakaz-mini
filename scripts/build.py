"""Собирает index.html из src/index.src.html.

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
OUT = ROOT / "index.html"

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


def hook_h1s(hooks: dict[str, list[str]]) -> str:
    rows = []
    for key, lines in hooks.items():
        spans = []
        for cls, text in zip(("line a", "line b pink", "line c"), lines):
            spans.append(f'<span class="{cls}" data-i18n="hook.{key}.{cls[-1] if cls != "line b pink" else "b"}">{text}</span>')
        rows.append(f'        <h1 class="d1 d1--hook worn" data-hook-for="{key}">{" ".join(spans)}</h1>')
    return "\n".join(rows)


def typography(text: str) -> str:
    text = re.sub(r"(\d)–(\d)", rf"\1{WJ}–{WJ}\2", text)
    text = re.sub(rf"(?<![0-9A-Za-zА-Яа-яЁё])({SHORT_WORDS})[ ]+(?=\S)", rf"\1{NBSP}", text, flags=re.IGNORECASE)
    text = re.sub(r"[ ]+—", f"{NBSP}—", text)
    text = re.sub(r"(\d)[ ]+(млн|тыс|сум|лет|компан|заказ|урок|вечер|клиент|человек|услуг)", rf"\1{NBSP}\2", text)
    return text


def apply_typography(html: str) -> str:
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
            out.append(part if skip else typography(part))
    return "".join(out)


def bust(html: str) -> str:
    def repl(m: re.Match) -> str:
        path = m.group(2)
        digest = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()[:8]
        return f'{m.group(1)}{path}?v={digest}"'

    return re.sub(r'((?:href|src)=")((?:css|js)/[\w.-]+\.(?:css|js))"', repl, html)


def main() -> None:
    html = SRC.read_text(encoding="utf-8")
    parts = json.loads(PARTS.read_text(encoding="utf-8"))
    html = html.replace("{{HEAD_HOOK_SCRIPT}}", HEAD_HOOK_SCRIPT)
    html = html.replace("{{HOOK_H1S}}", hook_h1s(read_hooks()))
    for key, value in parts.items():
        if not key.startswith("_"):
            html = html.replace("{{" + key + "}}", value)
    left = re.findall(r"\{\{[A-Z_a-z]+\}\}", html)
    if left:
        raise SystemExit(f"не заполнены места: {sorted(set(left))}")
    html = bust(apply_typography(html))
    OUT.write_text(html, encoding="utf-8")
    print(f"index.html собран: {len(html) // 1024} КБ")


if __name__ == "__main__":
    main()
