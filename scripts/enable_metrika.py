"""Включает Яндекс Метрику на лендинге одной командой (из корня репозитория):

    python3 scripts/enable_metrika.py 12345678

1. Вписывает номер счётчика в scripts/build.py (METRIKA_ID).
2. Добавляет абзац о Метрике в политику — privacy.html (UZ) и ru/privacy.html (RU), если его там ещё нет.
   Политика обещает обновиться до подключения новых сервисов, поэтому без абзаца счётчик не ставим.
3. Пересобирает index.html и ru/index.html.
Дальше: тесты, коммит, push и `gh variable set METRIKA_ID` — чтобы мониторинг проверял счётчик.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "scripts" / "build.py"
MARK = 'id="metrika"'

PARAGRAPHS = {
    ROOT / "ru" / "privacy.html": (
        f'<p {MARK}>На странице установлена Яндекс Метрика — сервис веб-аналитики Яндекса. Она записывает, '
        "как посетители пользуются страницей: просмотры, нажатия, прокрутку и запись действий на странице (Вебвизор), "
        "и передаёт технические данные: IP-адрес, сведения о браузере и устройстве, адрес страницы с меткой рекламы "
        "и идентификаторы в файлах cookie. Это нужно, чтобы понимать, какие блоки страницы читают и где уходят, "
        "и улучшать страницу. Яндекс обрабатывает эти данные по своей политике: "
        '<a href="https://yandex.ru/legal/confidential/">политика Яндекса</a>.</p>'
    ),
    # Узбекский абзац — перевод Claude 09.11.2026, носитель ещё не читал.
    ROOT / "privacy.html": (
        f'<p {MARK}>Sahifada Yandex Metrika o‘rnatilgan — Yandex’ning veb-analitika xizmati. U tashrif buyuruvchilar '
        "sahifadan qanday foydalanishini qayd etadi: ko‘rishlar, bosishlar, sahifani aylantirish va sahifadagi harakatlar "
        "yozuvi (Vebvizor), shuningdek texnik ma’lumotlarni uzatadi: IP-manzil, brauzer va qurilma haqidagi ma’lumotlar, "
        "reklama belgisi bilan sahifa manzili va cookie fayllaridagi identifikatorlar. Bu sahifaning qaysi bloklari "
        "o‘qilayotganini va qayerda chiqib ketishayotganini tushunib, sahifani yaxshilash uchun kerak. Yandex bu "
        "ma’lumotlarga o‘z siyosatiga ko‘ra ishlov beradi: "
        '<a href="https://yandex.com/legal/confidential/">Yandex siyosati</a>.</p>'
    ),
}
# Абзац ставим сразу после абзаца о пикселе Meta.
PIXEL_PARAGRAPH = re.compile(r"(<p>(?:На странице установлен пиксель Meta|Sahifada Meta pikseli o‘rnatilgan)[^\n]*</p>\n)")


def set_counter(counter_id: str) -> None:
    text = BUILD.read_text(encoding="utf-8")
    new, n = re.subn(r'^METRIKA_ID = ".*"$', f'METRIKA_ID = "{counter_id}"', text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("в scripts/build.py не найдена строка METRIKA_ID")
    BUILD.write_text(new, encoding="utf-8")


def add_privacy(path: Path, paragraph: str) -> None:
    html = path.read_text(encoding="utf-8")
    if MARK in html:
        print(f"{path.relative_to(ROOT)}: абзац о Метрике уже есть")
        return
    new, n = PIXEL_PARAGRAPH.subn(lambda m: m.group(1) + "  " + paragraph + "\n", html, count=1)
    if n != 1:
        raise SystemExit(f"{path.relative_to(ROOT)}: не найден абзац о пикселе Meta — вставь абзац о Метрике руками")
    path.write_text(new, encoding="utf-8")
    print(f"{path.relative_to(ROOT)}: добавлен абзац о Метрике")


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not re.fullmatch(r"\d{5,10}", argv[0]):
        raise SystemExit("нужен номер счётчика цифрами: python3 scripts/enable_metrika.py 12345678")
    counter_id = argv[0]
    for path, paragraph in PARAGRAPHS.items():
        add_privacy(path, paragraph)
    set_counter(counter_id)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build.py")], check=True)
    print(f"Метрика {counter_id} вписана. Дальше: тесты, коммит, push, gh variable set METRIKA_ID --body {counter_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
