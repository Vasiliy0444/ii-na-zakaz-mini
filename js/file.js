// Бонус-«файл»: превью подборки листается кнопками, нажатием на страницу, свайпом и стрелками клавиатуры.
// Движение — только transform и opacity (css/mini.css); при «уменьшить движение» страницы меняются без поворота.
const SWIPE_PX = 40;
const PEEK_MS = 1200;
const MAX_DEPTH = 2;

export function initFiles(track) {
  document.querySelectorAll('[data-file]').forEach((root) => initFile(root, track));
}

function initFile(root, track) {
  const stack = root.querySelector('.file-stack');
  const pages = Array.from(root.querySelectorAll('.fp'));
  const counter = root.querySelector('.file-count b');
  const prev = root.querySelector('[data-file-prev]');
  const next = root.querySelector('[data-file-next]');
  if (!stack || pages.length < 2 || !counter || !prev || !next) return;

  let cur = 0;
  const show = (index, how) => {
    cur = index >= pages.length ? 0 : Math.max(0, index); // после последней страницы — снова обложка
    pages.forEach((page, k) => {
      const depth = k - cur;
      page.classList.toggle('is-gone', depth < 0);
      page.classList.toggle('is-cur', depth === 0);
      page.style.setProperty('--d', String(Math.max(0, Math.min(depth, MAX_DEPTH))));
      page.setAttribute('aria-hidden', depth === 0 ? 'false' : 'true');
    });
    counter.textContent = String(cur + 1);
    prev.disabled = cur === 0;
    if (how) track('bonus_flip', { page: cur + 1, how });
  };

  prev.addEventListener('click', () => show(cur - 1, 'button'));
  next.addEventListener('click', () => show(cur + 1, 'button'));
  root.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight') { e.preventDefault(); show(cur + 1, 'key'); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); show(cur - 1, 'key'); }
  });

  // нажатие на страницу — дальше; свайп влево — дальше, вправо — назад
  let startX = null;
  stack.addEventListener('pointerdown', (e) => { startX = e.clientX; });
  stack.addEventListener('pointerup', (e) => {
    if (startX === null) return;
    const dx = e.clientX - startX;
    startX = null;
    if (dx > SWIPE_PX) show(cur - 1, 'swipe');
    else if (dx < -SWIPE_PX) show(cur + 1, 'swipe');
    else show(cur + 1, 'tap');
  });
  stack.addEventListener('pointercancel', () => { startX = null; });

  // подсказка «можно листать»: страница один раз приподнимается, когда файл впервые на экране
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!still && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      io.disconnect();
      root.classList.add('peek');
      setTimeout(() => root.classList.remove('peek'), PEEK_MS);
    }, { threshold: 0.6 });
    io.observe(root);
  }

  show(0);
}
