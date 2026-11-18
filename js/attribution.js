// Скопировано из websites/intensiv-site/src/lib/attribution.js (15.10.2026). Версия лендинга мини-курса — m.
// Метка для Telegram-бота: версия лендинга + метки рекламы.
// Telegram принимает в параметре start до 64 символов: A–Z, a–z, 0–9, _ и -.
// Формат: v{версия}-{utm_source}-{utm_campaign}-{utm_content}, без меток — v{версия}-direct.
// Версия — одна строчная латинская буква: m — лендинг мини-курса в системе «ИИ на заказ», 15.10.2026.

export const MAX_START_LENGTH = 64;

const PART_LIMITS = { source: 10, campaign: 18, content: 20 };
const VERSION_RE = /^[a-z]$/;
const BOT_USERNAME_RE = /^[A-Za-z][A-Za-z0-9_]{3,31}$/;
// ID клика для Meta Conversions API (сервис uz-capi на сервере, 18.11.2026): 10 знаков a–z0–9.
export const CID_RE = /^[a-z0-9]{10}$/;
const V1_LIMITS = { source: 10, campaign: 20, content: 12 };

/**
 * Приводит часть метки к символам, допустимым в Telegram start, и обрезает до limit.
 * @param {unknown} value
 * @param {number} limit
 * @returns {string}
 */
export function sanitizePart(value, limit) {
  const cleaned = String(value ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '');
  return cleaned.slice(0, limit).replace(/_+$/g, '');
}

/**
 * @typedef {{ source: string, campaign: string, content: string }} Utm
 */

/**
 * @param {string} search — location.search
 * @returns {Utm}
 */
export function readUtm(search) {
  const params = new URLSearchParams(search);
  return {
    source: params.get('utm_source') ?? '',
    campaign: params.get('utm_campaign') ?? '',
    content: params.get('utm_content') ?? '',
  };
}

/**
 * @param {Utm | null | undefined} utm
 * @returns {boolean}
 */
export function hasUtm(utm) {
  return Boolean(utm && (utm.source || utm.campaign || utm.content));
}

/**
 * @param {string} version — одна строчная латинская буква, иначе x
 * @param {Utm} utm
 * @returns {string} не длиннее 64 символов, только A–Z a–z 0–9 _ -
 */
export function buildStartPayload(version, utm, cid = '') {
  if (CID_RE.test(cid)) return buildStartPayloadV1(version, utm, cid);
  const v = VERSION_RE.test(version) ? version : 'x';
  const parts = hasUtm(utm)
    ? [
        sanitizePart(utm.source, PART_LIMITS.source) || 'na',
        sanitizePart(utm.campaign, PART_LIMITS.campaign) || 'na',
        sanitizePart(utm.content, PART_LIMITS.content) || 'na',
      ]
    : ['direct'];
  return [`v${v}`, ...parts].join('-').slice(0, MAX_START_LENGTH);
}

/**
 * Часть метки v1: внутри части только a–z, 0–9 и дефис — подчёркивание у бота разделяет поля.
 * @param {unknown} value
 * @param {number} limit
 * @returns {string}
 */
export function sanitizeV1Part(value, limit) {
  const cleaned = String(value ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '');
  return cleaned.slice(0, limit).replace(/-+$/g, '');
}

/**
 * Метка в формате бота v1: v1_{источник}_v{версия}_{кампания}_{объявление}_k{cid}.
 * Бот (parseStartPayload) раскладывает её по utm_source / medium / campaign / content / term,
 * сервис uz-capi достаёт cid из хвоста и связывает человека с кликом по рекламе.
 * @param {string} version
 * @param {Utm} utm
 * @param {string} cid
 * @returns {string}
 */
export function buildStartPayloadV1(version, utm, cid) {
  const v = VERSION_RE.test(version) ? version : 'x';
  const has = hasUtm(utm);
  const parts = [
    'v1',
    has ? sanitizeV1Part(utm.source, V1_LIMITS.source) || 'na' : 'direct',
    `v${v}`,
    has ? sanitizeV1Part(utm.campaign, V1_LIMITS.campaign) || 'na' : 'na',
    has ? sanitizeV1Part(utm.content, V1_LIMITS.content) || 'na' : 'na',
    `k${cid}`,
  ];
  return parts.join('_').slice(0, MAX_START_LENGTH);
}

/**
 * Случайный ID клика: 10 знаков a–z0–9. Без crypto — пустая строка (метка останется старого формата).
 * @returns {string}
 */
export function makeCid() {
  try {
    const abc = 'abcdefghijklmnopqrstuvwxyz0123456789';
    const bytes = new Uint8Array(10);
    globalThis.crypto.getRandomValues(bytes);
    return Array.from(bytes, (b) => abc[b % 36]).join('');
  } catch {
    return '';
  }
}

/**
 * @param {string} botUsername — без @
 * @param {string} payload
 * @returns {string | null} null, если username пустой или некорректный
 */
export function buildBotUrl(botUsername, payload) {
  if (!BOT_USERNAME_RE.test(botUsername ?? '')) return null;
  return `https://t.me/${botUsername}?start=${encodeURIComponent(payload)}`;
}

// Последнее касание: метки из адреса важнее сохранённых, сохранённые — если в адресе меток нет.
/**
 * @param {Utm} urlUtm
 * @param {Utm | null} storedUtm
 * @returns {Utm}
 */
export function resolveUtm(urlUtm, storedUtm) {
  if (hasUtm(urlUtm)) return urlUtm;
  if (hasUtm(storedUtm)) return storedUtm;
  return { source: '', campaign: '', content: '' };
}
