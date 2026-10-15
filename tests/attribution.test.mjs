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
