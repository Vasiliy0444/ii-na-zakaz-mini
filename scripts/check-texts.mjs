// Сверка текстов «один в один»: каждая строка согласованного текста (research/13-lending-intensiva/ЛЕНДИНГ-ФИНАЛ-RU.md,
// он же АКТУАЛЬНЫЙ-ЛЕНДИНГ_мини-курс_RU.docx от 11.10.2026) должна дословно стоять на странице index.html.
// И обратно: на странице нет текста, которого нет в согласованном, кроме короткого списка ALLOWED.
// Запуск из корня репозитория после сборки: node scripts/check-texts.mjs
import { readFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const APPROVED = resolve(root, '../../research/13-lending-intensiva/ЛЕНДИНГ-ФИНАЛ-RU.md');
if (!existsSync(APPROVED)) {
  console.log('Согласованный текст не найден рядом (', APPROVED, ') — проверка пропущена.');
  process.exit(0);
}

const norm = (s) => s
  .replace(/[  ]/g, ' ')
  .replace(/⁠/g, '')
  .replace(/&nbsp;/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/\*\*/g, '')
  .replace(/`/g, '')
  .replace(/\s+/g, ' ')
  .trim();

// Не проверяем: служебные пометки текста, блок Василия (решение Васи 15.10.2026: на странице только Никита)
// и заголовки под хуки (их сверяет tests/hooks.test.mjs).
function approvedStrings(md) {
  const out = [];
  let skip = false;
  for (const raw of md.split('\n')) {
    const line = raw.trim();
    if (!line || line === '---') continue;
    if (line.startsWith('# Заголовки под хуки')) break;
    if (line.startsWith('**Василий Беляков**')) { skip = true; continue; }
    if (skip && line.startsWith('# Блок 4')) skip = false;
    if (skip) continue;
    if (line.startsWith('Согласовано Васей') || line.startsWith('**Фото:**') || line.startsWith('[Фото')) continue;
    if (line.startsWith('#')) {
      const h = line.replace(/^#+\s*/, '');
      if (h === 'Частые вопросы') out.push(h);
      continue;
    }
    const lesson = line.match(/^\*\*(Урок \d)\. (.+)\*\*$/);
    if (lesson) { out.push(lesson[1], lesson[2]); continue; }
    const labelled = line.match(/^\*\*([^*]+?):\*\*\s*(.*)$/);
    if (labelled) {
      const [, label, value] = labelled;
      if (label === 'Строка под заголовком' || label === 'Подвал') value.split(' · ').forEach((p) => out.push(p));
      else if (label === 'Плашка' || label === 'Подпись к фото') out.push(value);
      else if (['Заголовок (H1)', 'Заголовок (H2)', 'Подзаголовок', 'Кнопка', 'Под кнопкой', 'Бонус'].includes(label)) out.push(value);
      else out.push(`${label}: ${value}`); // «Результат: …», «Что это даёт тебе: …»
      continue;
    }
    out.push(line.replace(/^-\s+/, '').replace(/^\*\*(.+)\*\*$/, '$1'));
  }
  return [...new Set(out.map(norm).filter(Boolean))];
}

// Текст страницы: без <head>, скриптов и стилей; теги → пробел; атрибуты не считаются.
const html = readFileSync(resolve(root, 'index.html'), 'utf8');
const body = html.split('<body>')[1]
  .replace(/<script[\s\S]*?<\/script>/g, ' ')
  .replace(/<style[\s\S]*?<\/style>/g, ' ')
  .replace(/<svg[\s\S]*?<\/svg>/g, ' ');
const pageText = norm(body.replace(/<[^>]+>/g, ' ').replace(/\s+([.,:;!?»)])/g, '$1').replace(/([«(])\s+/g, '$1'));
const pageNodes = body.split(/<[^>]+>/).map(norm).filter(Boolean);

// Правки Васи 17.10.2026 поверх согласованного текста: что снято со страницы и что добавлено.
const REMOVED = new Set([
  'Бесплатный мини-курс в Telegram · 3 урока и практика',                  // плашка → «Бесплатный мини-курс»
  'С нуля', '2–3 вечера в неделю', 'Смотреть можно с телефона',          // пункты под заголовком → результаты мини-курса
  'Делаешь для бизнеса сайты, Telegram-ботов, контент и дизайн с нейросетями — по вечерам, из дома. 3–4 заказа по $300 в месяц — это и есть $1000.',
  'Уроки придут в Telegram, смотреть можно с телефона. Денег и карту не просим.',
  'Ведёт Никита Попко',
  'Сначала три урока теории, потом практика. Всё в Telegram, шаги открываются по порядку.',
  '🔒 Практика без своих компаний — это снова теория. Поэтому урок откроется тем, кто досмотрел 3 урока и прислал 3 компании. Как — расскажем в боте.',
  'Что это даёт тебе: Покажет, что в ИИ реально работает для малого бизнеса, а что только красиво звучит. И научит делать услугу так, чтобы клиент заказывал снова.',
  'Бесплатный мини-курс в Telegram: три урока и практика.',
  '🎁 «Топ-10 каналов, где найти клиентов на ИИ-услуги». Где малый бизнес ищет исполнителей и с какого канала начать, если среди знакомых нет предпринимателей. Придёт вместе с первым уроком.',
  'Первый урок придёт сразу после старта бота. Отписаться можно одной кнопкой.',
  'ИНН [указать]',
].map(norm));
export const ADDED = [
  'Первый сайт — для настоящей компании', 'План до $1000: 3–4 заказа по $300', 'Топ-10 каналов, где искать клиентов',
  'опыт команды курса в маркетинге', 'клиентов у команды по HR и маркетингу', 'человек в команде курса',   // регалии — как команды курса
  'Бонус мини-курса', '2GIS и Google Карты: компании без сайта', 'Uzum Market: карточки, фото и видео', 'OLX, раздел «Работа»',  // превью файла бонуса
  'Telegram-каналы с разовыми задачами', 'Откроется в боте', 'С какого канала начать, если среди знакомых нет предпринимателей', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '1', '2', '3', '/ 4',
  'Что сейчас приносит деньги', 'Смены, такси', 'Сайт за вечер — 2,5–5 млн сум', 'Контент', 'Дизайн',          // слайды в кадрах уроков — из описаний уроков
  '3–4 заказа по $300 =', 'Где искать первых заказчиков', 'Сайт для твоей компании',
  'ИП Беляков Василий Александрович · ИНН 772440246130', 'Р/с 40802810120000927878 в ООО «Банк Точка» · БИК 044525104 · К/с 30101810745374525104',
];

const md = readFileSync(APPROVED, 'utf8');
const expected = approvedStrings(md).filter((s) => !REMOVED.has(s));
const missing = expected.filter((s) => !pageText.includes(s));

// Обратная проверка: каждый кусок текста страницы есть в согласованном тексте (как подстрока), иначе — в ALLOWED.
const mdText = norm(md);
const ALLOWED = new Set([
  'ИИ', 'НА ЗАКАЗ',                                          // логотип
  ...ADDED.map(norm),
]);
const extra = [...new Set(pageNodes)].filter((s) => !mdText.includes(s) && !ALLOWED.has(s));

console.log(`Строк согласованного текста: ${expected.length}. Нет на странице: ${missing.length}. Лишнего на странице: ${extra.length}.`);
missing.forEach((s) => console.log('  НЕТ:', s));
extra.forEach((s) => console.log('  ЛИШНЕЕ:', s));
process.exit(missing.length || extra.length ? 1 : 0);
