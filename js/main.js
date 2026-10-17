// Лендинг мини-курса «ИИ на заказ» — поведение страницы. Без библиотек.
// Части взяты из js/main.js страницы курса (коммит 453d85f): события dataLayer, лента со стрелкой, нижняя панель, аккордеон, block_view.
// Метка для бота — js/attribution.js (из websites/intensiv-site). Заголовок под хук выбирает скрипт в <head>.
import { buildBotUrl, buildStartPayload, hasUtm, readUtm, resolveUtm } from './attribution.js';
import { initFiles } from './file.js';

/* ================= НАСТРОЙКИ ================= */
const BOT_USERNAME = ''; // имя бота мини-курса без @. Пусто — кнопки ведут на заглушку BOT_FALLBACK.
const BOT_FALLBACK = 'https://t.me/';
const LANDING_VERSION = 'm';
const UTM_KEY = 'mini_utm';

const doc = document.documentElement;
const qs = new URLSearchParams(location.search);
const SHOT = Boolean(qs.get('shot'));
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

const store = {
  get(key) {
    try { return JSON.parse(localStorage.getItem(key) ?? 'null'); } catch { return null; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* приватный режим — живём без памяти */ }
  },
};

if (SHOT) {
  doc.classList.add('shot');
  $$('img[loading=lazy]').forEach((img) => { img.loading = 'eager'; });
}

/* ---------- аналитика: события в window.dataLayer ---------- */
window.dataLayer = window.dataLayer || [];
const hook = doc.getAttribute('data-hook') || 'default';
function track(event, params = {}) {
  window.dataLayer.push({ event, hook, ...params });
}

/* ---------- метка рекламы → параметр start ссылки на бота (последнее касание) ---------- */
const urlUtm = readUtm(location.search);
if (hasUtm(urlUtm)) store.set(UTM_KEY, urlUtm);
const utm = resolveUtm(urlUtm, store.get(UTM_KEY));
const payload = buildStartPayload(LANDING_VERSION, utm);
const botUrl = buildBotUrl(BOT_USERNAME, payload);
$$('a[data-cta]').forEach((a) => {
  a.dataset.start = payload;
  if (botUrl) {
    a.href = botUrl;
    a.target = '_blank';
    a.rel = 'noopener';
  } else {
    a.href = BOT_FALLBACK;
  }
});
window.__AB = { start: payload, hook, bot: Boolean(botUrl) };

document.addEventListener('click', (e) => {
  const a = e.target.closest('[data-track]');
  if (a) track('cta_click', { place: a.getAttribute('data-place') || '', start: payload });
});

/* ---------- горизонтальная лента со стрелкой (телефон) ---------- */
$$('.hs-wrap').forEach((wrap) => {
  const list = $('.hscroll', wrap);
  const btn = $('.hs-next', wrap);
  if (!list || !btn) return;
  const atEnd = () => list.scrollLeft + list.clientWidth >= list.scrollWidth - 8;
  const upd = () => wrap.classList.toggle('at-end', atEnd());
  btn.addEventListener('click', () => {
    list.scrollBy({ left: atEnd() ? -list.scrollWidth : list.clientWidth * 0.8, behavior: 'smooth' });
  });
  list.addEventListener('scroll', upd, { passive: true });
  upd();
});

/* ---------- бонус-«файл»: листается (js/file.js) ---------- */
initFiles(track);

/* ---------- нижняя панель: после первого экрана; прячется, пока на экране другая кнопка ---------- */
const dock = $('.dock');
const heroCta = $('#cta-hero');
if (dock && heroCta && 'IntersectionObserver' in window) {
  const watch = $$('a.btn[data-cta]').filter((a) => !a.closest('.dock'));
  const onScreen = new Map();
  const updDock = () => {
    const passed = heroCta.getBoundingClientRect().bottom < 0;
    const busy = Array.from(onScreen.values()).some(Boolean);
    const on = passed && !busy;
    dock.classList.toggle('show', on);
    doc.classList.toggle('dock-on', on);
  };
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => onScreen.set(e.target, e.isIntersecting));
    updDock();
  });
  watch.forEach((el) => io.observe(el));
  window.addEventListener('scroll', updDock, { passive: true });
  updDock();
}

/* ---------- аккордеон вопросов: открыт один ---------- */
let acted = false;
['pointerdown', 'keydown', 'touchstart'].forEach((t) => document.addEventListener(t, () => { acted = true; }, { passive: true, once: true }));
$$('[data-acc]').forEach((acc) => {
  $$('details', acc).forEach((d) => {
    d.addEventListener('toggle', () => {
      if (!d.open) return;
      $$('details', acc).forEach((o) => { if (o !== d) o.open = false; });
      const q = $('summary [data-i18n]', d);
      if (acted) track('faq_open', { item: q ? q.getAttribute('data-i18n') : '' });
    });
  });
});

/* ---------- просмотр блоков: block_view один раз на блок ---------- */
if ('IntersectionObserver' in window && !SHOT) {
  const seen = new Set();
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      const b = e.target.getAttribute('data-b');
      if (e.isIntersecting && !seen.has(b)) {
        seen.add(b);
        track('block_view', { block: b, id: e.target.id || '' });
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.35 });
  $$('[data-b]').forEach((s) => io.observe(s));
}

track('page_view', { start: payload, utm_source: utm.source, utm_campaign: utm.campaign, utm_content: utm.content });
