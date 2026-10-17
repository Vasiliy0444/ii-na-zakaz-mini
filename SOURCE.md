# Откуда что взято

Лендинг бесплатного мини-курса собран в дизайн-системе страницы курса «ИИ на заказ»:
https://npopko55-cmd.github.io/ii-na-zakaz/ (репозиторий github.com/npopko55-cmd/ii-na-zakaz, коммит `453d85f` от 15.10.2026).
Разрешение взять стили, шрифты и картинки страницы курса — Вася, 15.10.2026.

## Взято у страницы курса без изменений

| Что | Где у нас | Как сверить |
|---|---|---|
| Стили | `css/style.css`, `css/fonts.css` | байт в байт с коммитом 453d85f: `shasum -a 256 css/style.css` → `73daaa35…`, `css/fonts.css` → `35aa182b…` |
| Шрифты | `assets/fonts/*.woff2` | лицензия — `assets/fonts/OFL.txt` |
| Картинки | `assets/img/`: `bg_hero_*`, `bg_desk_*`, `bill_*`, `nikita_crossed`, `nikita_phone`, `nikita_present`, `ic_*`, `map_iso`, `pin`, `old_desk`, `neon_laptop`, `laptop_build`, `medal_coin`, `shield` | имена как у образца |
| Рваные края, силуэт города, иконки | `src/parts.json` | вырезаны из `index.html` образца |
| Иконки сайта | `assets/favicon-64.png`, `assets/apple-touch-icon.png` | — |

Свои правки поверх образца — только в `css/mini.css`: новых цветов, радиусов и кеглей там нет.

## Сделано для мини-курса

- **Картинки Higgsfield**, 15.10.2026. Модель GPT Image 2.5, качество high, 2K, прозрачный фон; образцом стиля служили картинки страницы курса. Всего 7 генераций по 2,75 кредита — 19,25 кредита.
  - `nikita_laptop` — Никита за ноутбуком; образцы `nikita_present`, `nikita_crossed`, `laptop_build`; выбран вариант 2 из 3.
  - `gift` — 3D-подарок; образцы `ic_site`, `medal_coin`; выбран вариант 2 из 2.
  - `certificate` — 3D-сертификат; образцы `medal_coin`, `shield`; выбран вариант 1 из 2.
- **`assets/og.jpg`** — снимок первого экрана, 1200×630.
- **`js/attribution.js`** — из `websites/intensiv-site/src/lib/attribution.js` (метка в параметр start бота). Буква версии — `m`.
- **Раскладки трёх новых блоков** — Superdesign MCP, по 2 варианта, все в `superdesign/`. Выбраны `band_after_hero_1`, `lessons_1`, `final_faq_1`.
- **Тексты** — один в один из `АКТУАЛЬНЫЙ-ЛЕНДИНГ_мини-курс_RU.docx`, согласован 11.10.2026. Сверку делает `scripts/check-texts.mjs`.
  - Исключение — блок «Кто ведёт» по решению Васи от 15.10.2026: на странице только Никита.
  - Регалии команды (6 лет, 80+, 30+) — плашками у фигуры Никиты с подписью «команда курса». Под именем Никиты их не пишем: это не его регалии.
  - Правки Васи от 17.10.2026 (что снято и что добавлено) — списки `REMOVED` и `ADDED` в `scripts/check-texts.mjs`.
- **`privacy.html`** — политика сайта курса от 28.09.2026 (`websites/course-site/privacy.html`), обновлена под эту страницу 17.10.2026: шрифты свои (без Google Fonts), кнопки ведут в бота Telegram, метка рекламы хранится в браузере.
