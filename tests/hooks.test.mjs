import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { HOOKS, pickHook } from '../js/hooks.js';

// Заголовки под хуки — дословно из texts/ЛЕНДИНГ-ФИНАЛ-RU.md, раздел «Заголовки под хуки рекламы».
const APPROVED = {
  compare: 'Такси, смены, Uzum или онлайн-профессия: на чём реально выйти на $1000 в месяц в 2026 году',
  math_a: '$1000 в месяц — это не пассивный доход, а 3–4 заказа от бизнеса. Считаем открыто',
  math_b: '$1000 в месяц — это 3–4 заказа от бизнеса по $300. Считаем открыто',
  now: 'Раньше сайт учились делать годами. Сейчас AI-специалист собирает его за день — а бизнес платит те же 2,5–5 млн сум',
  zero: 'Можно ли освоить онлайн-профессию с нуля, если ты студент и не программист?',
  clients: 'Умеешь делать с ИИ, но нет клиентов? Покажем, где студенты находят первых заказчиков — без бирж и без опыта',
  home: 'Научим делать сайты и ботов для бизнеса твоего города — и находить заказчиков дома',
};

test('каждый хук собирается из строк в согласованный текст слово в слово', () => {
  for (const [key, text] of Object.entries(APPROVED)) {
    assert.ok(HOOKS[key], `нет хука ${key}`);
    assert.equal(HOOKS[key].join(' '), text, key);
  }
});

test('у каждого хука есть розовая вторая строка', () => {
  for (const [key, lines] of Object.entries(HOOKS)) {
    assert.ok(lines.length >= 2 && lines[1].trim(), key);
  }
});

test('без метки и с чужой меткой хука нет — остаётся заголовок блока 1', () => {
  assert.equal(pickHook(''), null);
  assert.equal(pickHook(null), null);
  assert.equal(pickHook('brand_video_v1'), null);
});

test('метка находится внутри utm_content, регистр не важен', () => {
  assert.equal(pickHook('hook_compare_v2'), 'compare');
  assert.equal(pickHook('Zero'), 'zero');
  assert.equal(pickHook('reels_clients_1'), 'clients');
  assert.equal(pickHook('home'), 'home');
  assert.equal(pickHook('now_a'), 'now');
});

test('математика: math_a — вариант A, math_b и просто math — вариант B', () => {
  assert.equal(pickHook('math_a'), 'math_a');
  assert.equal(pickHook('hook_math_b_v1'), 'math_b');
  assert.equal(pickHook('math'), 'math_b');
  assert.equal(pickHook('hook_math_v2'), 'math_b');
});

test('метка — целое слово: knowhow и homepage хук не включают', () => {
  assert.equal(pickHook('knowhow'), null);
  assert.equal(pickHook('homepage'), null);
  assert.equal(pickHook('hook-home-v1'), 'home');
});

// Скрипт в <head> index.html выбирает хук до отрисовки. Его логика должна совпадать с pickHook.
test('скрипт в <head> выбирает тот же хук, что и pickHook', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const code = html.match(/<script id="hook-head">([\s\S]*?)<\/script>/)[1];
  const samples = ['', 'hook_compare_v2', 'math', 'math_a', 'hook_math_b_v1', 'Zero', 'reels_clients_1', 'now_a', 'knowhow', 'homepage', 'brand_video', 'HOME'];
  for (const s of samples) {
    const attrs = {};
    const sandbox = {
      location: { search: s ? '?utm_content=' + encodeURIComponent(s) : '' },
      URLSearchParams,
      document: { documentElement: { setAttribute: (k, v) => { attrs[k] = v; } } },
    };
    vm.runInNewContext(code, sandbox);
    assert.equal(attrs['data-hook'] ?? null, pickHook(s), s);
  }
});
