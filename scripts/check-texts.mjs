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

const md = readFileSync(APPROVED, 'utf8');
const expected = approvedStrings(md);
const missing = expected.filter((s) => !pageText.includes(s));

// Обратная проверка: каждый кусок текста страницы есть в согласованном тексте (как подстрока), иначе — в ALLOWED.
const mdText = norm(md);
const ALLOWED = new Set([
  'ИИ', 'НА ЗАКАЗ',                                          // логотип
  'Партнёр курса', '6 лет', 'в маркетинге', '80+', 'клиентов по HR и маркетингу', '30+', 'человек в команде', // регалии партнёра — решение 15.10.2026
  '7+',                                                       // число на плашке регалии Никиты
]);
const extra = [...new Set(pageNodes)].filter((s) => !mdText.includes(s) && !ALLOWED.has(s));

console.log(`Строк согласованного текста: ${expected.length}. Нет на странице: ${missing.length}. Лишнего на странице: ${extra.length}.`);
missing.forEach((s) => console.log('  НЕТ:', s));
extra.forEach((s) => console.log('  ЛИШНЕЕ:', s));
process.exit(missing.length || extra.length ? 1 : 0);
