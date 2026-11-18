import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_START_LENGTH,
  buildBotUrl,
  buildStartPayload,
  hasUtm,
  readUtm,
  resolveUtm,
  sanitizePart,
  makeCid,
  CID_RE,
} from '../js/attribution.js';

const TELEGRAM_START_RE = /^[A-Za-z0-9_-]{1,64}$/;

test('метка без UTM — версия лендинга и direct', () => {
  assert.equal(buildStartPayload('e', { source: '', campaign: '', content: '' }), 've-direct');
});

test('метка с UTM собирается из трёх частей', () => {
  const utm = readUtm('?utm_source=instagram&utm_campaign=test_sep&utm_content=hook_math_v2');
  assert.equal(buildStartPayload('e', utm), 've-instagram-test_sep-hook_math_v2');
});

test('неизвестная версия помечается x', () => {
  assert.equal(buildStartPayload('auto', { source: 'ig', campaign: '', content: '' }), 'vx-ig-na-na');
  assert.equal(buildStartPayload('E', { source: 'ig', campaign: '', content: '' }), 'vx-ig-na-na');
});

test('кириллица, пробелы и спецсимволы вычищаются до допустимых Telegram символов', () => {
  const payload = buildStartPayload('e', { source: 'Инстаграм Reels!', campaign: 'Кампания №1 / сентябрь', content: 'хук: «математика»' });
  assert.match(payload, TELEGRAM_START_RE);
  assert.equal(payload, 've-reels-1-na');
});

test('метка никогда не длиннее 64 символов и проходит правила Telegram', () => {
  const long = 'x'.repeat(200);
  const payload = buildStartPayload('e', { source: long, campaign: long, content: long });
  assert.ok(payload.length <= MAX_START_LENGTH);
  assert.match(payload, TELEGRAM_START_RE);
});

test('sanitizePart не оставляет подчёркивания на концах после обрезки', () => {
  assert.equal(sanitizePart('ab_cd', 3), 'ab');
  assert.equal(sanitizePart('__hi__', 10), 'hi');
});

test('ссылка на бота строится только при корректном username', () => {
  assert.equal(buildBotUrl('', 've-direct'), null);
  assert.equal(buildBotUrl('1bad', 've-direct'), null);
  assert.equal(buildBotUrl('ai_na_zakaz_bot', 've-direct'), 'https://t.me/ai_na_zakaz_bot?start=ve-direct');
});

test('последнее касание: метки из адреса важнее сохранённых', () => {
  const stored = { source: 'tg', campaign: 'old', content: '' };
  const fromUrl = { source: 'instagram', campaign: 'new', content: '' };
  assert.deepEqual(resolveUtm(fromUrl, stored), fromUrl);
  assert.deepEqual(resolveUtm({ source: '', campaign: '', content: '' }, stored), stored);
  assert.equal(hasUtm(resolveUtm({ source: '', campaign: '', content: '' }, null)), false);
});

// ---------- метка v1 с ID клика (Conversions API, 18.11.2026) ----------

// Та же логика, что parseStartPayload в боте (tgcloud/lib/funnel/machine.js): v1_source_medium_campaign_content_term.
function botParse(payload) {
  const parts = payload.split('_');
  if (parts[0] === 'v1') parts.shift();
  const [s, m, campaign, c, ...rest] = parts;
  return { source: s, medium: m, campaign, content: c, term: rest.join('_') };
}

test('с ID клика метка — формат бота v1, бот раскладывает её по полям', () => {
  const payload = buildStartPayload('m', { source: 'fb', campaign: 'inst-diz-malo-text', content: '3' }, 'abc123xyz0');
  assert.equal(payload, 'v1_fb_vm_inst-diz-malo-text_3_kabc123xyz0');
  assert.deepEqual(botParse(payload), { source: 'fb', medium: 'vm', campaign: 'inst-diz-malo-text', content: '3', term: 'kabc123xyz0' });
});

test('подчёркивания из меток рекламы не ломают поля бота', () => {
  const payload = buildStartPayload('m', { source: 'f_b', campaign: 'insta_diz_mnogo_text', content: 'hook_math_v2' }, 'abc123xyz0');
  assert.equal(payload.split('_').length, 6);
  assert.equal(botParse(payload).term, 'kabc123xyz0');
});

test('без меток рекламы — direct, ID клика на месте', () => {
  assert.equal(buildStartPayload('m', { source: '', campaign: '', content: '' }, 'abc123xyz0'), 'v1_direct_vm_na_na_kabc123xyz0');
});

test('метка v1 с длинными метками не длиннее 64 и cid не обрезается', () => {
  const long = 'x'.repeat(200);
  const payload = buildStartPayload('m', { source: long, campaign: long, content: long }, 'abc123xyz0');
  assert.ok(payload.length <= MAX_START_LENGTH);
  assert.match(payload, TELEGRAM_START_RE);
  assert.ok(payload.endsWith('_kabc123xyz0'));
});

test('негодный cid — метка старого формата', () => {
  assert.equal(buildStartPayload('m', { source: 'fb', campaign: 'mems', content: '5' }, 'BAD'), 'vm-fb-mems-5');
  assert.equal(buildStartPayload('m', { source: 'fb', campaign: 'mems', content: '5' }), 'vm-fb-mems-5');
});

test('makeCid даёт 10 знаков a–z0–9 и каждый раз новый', () => {
  const a = makeCid();
  const b = makeCid();
  assert.match(a, CID_RE);
  assert.notEqual(a, b);
});
