/**
 * TIANGONG FREE CLASSROOM — 空间优先的楼层浏览
 *
 * 信息架构：楼栋 → 楼层（空闲概览）→ 教室行。节次降为二级维度。
 * 数据诚实性：source / data_date 决定状态栏与横幅，任何情况下不生成替代数据。
 */

const state = {
  data: null,
  selectedSlots: new Set(),
  allDayFree: false,
  searchQuery: '',
  cap: 'all',
  sortBy: 'room_asc',
  expanded: new Set(),
  theme: localStorage.getItem('theme')
    || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
};

const dom = {
  statusDot: document.getElementById('statusDot'),
  statusText: document.getElementById('statusText'),
  staleBanner: document.getElementById('staleBanner'),
  staleDetail: document.getElementById('staleDetail'),
  pwaBanner: document.getElementById('pwaInstallBanner'),
  installBtn: document.getElementById('installPwaBtn'),
  slotGrid: document.getElementById('slotGrid'),
  allDayCheckbox: document.getElementById('allDayCheckbox'),
  searchInput: document.getElementById('searchInput'),
  sortSelect: document.getElementById('sortSelect'),
  capChips: document.getElementById('capChips'),
  skeleton: document.getElementById('skeleton'),
  buildingGroups: document.getElementById('buildingGroups'),
  emptyState: document.getElementById('emptyState'),
  errorState: document.getElementById('errorState'),
  themeToggleBtn: document.getElementById('themeToggleBtn')
};

const CAP_RANGES = { s: [0, 79], m: [80, 149], l: [150, Infinity] };

let deferredPrompt = null;
let searchTimer = null;

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initTimeDetector();
  bindEvents();
  fetchScheduleData();
  registerServiceWorker();
});

/* ---------------------------------------------------------------- 主题 */

function initTheme() {
  document.documentElement.setAttribute('data-theme', state.theme);
}

function toggleTheme() {
  state.theme = state.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('theme', state.theme);
  initTheme();
}

/* ------------------------------------------------------- 当前节次推荐 */

function getAutoSlotNumber() {
  const now = new Date();
  const minutes = now.getHours() * 60 + now.getMinutes();
  if (minutes <= 10 * 60) return 1;
  if (minutes <= 12 * 60 + 30) return 2;
  if (minutes <= 15 * 60 + 40) return 3;
  if (minutes <= 17 * 60 + 40) return 4;
  return 5;
}

function initTimeDetector() {
  if (state.selectedSlots.size === 0 && !state.allDayFree) {
    state.selectedSlots.add(getAutoSlotNumber());
  }
}

/* ------------------------------------------------------------- 数据层 */

async function fetchScheduleData() {
  const paths = ['./data/today.json', '../public/data/today.json'];
  let data = null;

  for (const path of paths) {
    try {
      const resp = await fetch(path, { cache: 'no-store' });
      if (resp.ok) {
        data = await resp.json();
        break;
      }
    } catch (e) {
      console.warn(`Failed to load data from ${path}`, e);
    }
  }

  dom.skeleton.hidden = true;

  if (!data || !Array.isArray(data.classrooms)) {
    dom.statusDot.dataset.state = 'error';
    dom.statusText.textContent = '数据加载失败';
    dom.buildingGroups.hidden = true;
    dom.errorState.hidden = false;
    return;
  }

  state.data = data;
  applyFreshness(data);
  renderSlots();
  render();
}

function shanghaiToday() {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' });
}

function applyFreshness(data) {
  const today = shanghaiToday();
  const stale = data.source !== 'live' || (data.data_date && data.data_date !== today);

  dom.staleBanner.hidden = !stale;
  if (stale) {
    dom.staleDetail.textContent = data.data_date
      ? `最近一次成功抓取是 ${formatDate(data.data_date)}，不是今天。`
      : '今日自动抓取尚未成功，以下为最近一次成功获取的结果。';
  }
  return stale;
}

function formatDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
  if (!m) return String(iso || '未知日期');
  return `${Number(m[2])}月${Number(m[3])}日`;
}

function formatClock(stamp) {
  const m = /(\d{2}:\d{2})/.exec(String(stamp || ''));
  return m ? m[1] : '';
}

/* ------------------------------------------------------------- 渲染层 */

function targetMask() {
  if (state.allDayFree) return 31;
  let mask = 0;
  for (const n of state.selectedSlots) {
    const slot = (state.data.time_slots || []).find(s => s.slot === n);
    if (slot) mask |= slot.mask;
  }
  return mask;
}

function floorOf(room) {
  const m = /\d/.exec(String(room.r || ''));
  return m ? m[0] : '?';
}

function longestFreeRun(occ) {
  const slots = state.data.time_slots || [];
  let best = 0;
  let run = 0;
  for (const slot of slots) {
    if ((occ & slot.mask) === 0) {
      run += 1;
      if (run > best) best = run;
    } else {
      run = 0;
    }
  }
  return best;
}

function matchesCapacity(room) {
  if (state.cap === 'all') return true;
  const range = CAP_RANGES[state.cap];
  if (!range) return true;
  const seats = Number(room.c);
  if (!Number.isFinite(seats)) return false;
  return seats >= range[0] && seats <= range[1];
}

function matchesSearch(room) {
  if (!state.searchQuery) return true;
  const q = state.searchQuery;
  if (String(room.r || '').toLowerCase().includes(q)) return true;
  if (String(room.b || '').toLowerCase().includes(q)) return true;
  return floorOf(room) === q;
}

function sortRooms(list) {
  const copy = list.slice();
  copy.sort((a, b) => {
    if (state.sortBy === 'cap_desc') return Number(b.c) - Number(a.c);
    if (state.sortBy === 'free_slots') {
      const diff = longestFreeRun(b.occ) - longestFreeRun(a.occ);
      if (diff !== 0) return diff;
    }
    return String(a.r).localeCompare(String(b.r), undefined, { numeric: true });
  });
  return copy;
}

function render() {
  if (!state.data) return;

  const mask = targetMask();
  const all = state.data.classrooms || [];

  // 非时间维度先过滤，楼层概览的分母才与用户看到的筛选一致
  const base = all.filter(r => matchesCapacity(r) && matchesSearch(r));

  const buildings = new Map();
  for (const room of base) {
    const b = room.b || '未知楼栋';
    if (!buildings.has(b)) buildings.set(b, new Map());
    const floors = buildings.get(b);
    const f = floorOf(room);
    if (!floors.has(f)) floors.set(f, []);
    floors.get(f).push(room);
  }

  let totalFree = 0;
  let html = '';

  for (const [building, floors] of buildings) {
    const floorRows = [];
    let buildingFree = 0;
    let buildingTotal = 0;

    for (const floor of [...floors.keys()].sort()) {
      const rooms = floors.get(floor);
      const free = rooms.filter(r => (r.occ & mask) === 0);
      buildingTotal += rooms.length;
      buildingFree += free.length;

      const key = `${building}::${floor}`;
      const open = state.expanded.has(key);
      const allFull = free.length === 0;

      floorRows.push(`
        <li class="floor ${allFull ? 'is-full' : ''}">
          <button class="floor-head" type="button" aria-expanded="${open}" aria-controls="rooms-${cssId(key)}" data-floor="${escapeAttr(key)}">
            <span class="floor-name">${escapeHtml(floor)} 层</span>
            <span class="floor-count">${allFull ? '本层无空' : `${free.length}/${rooms.length} 空闲`}</span>
            <span class="chevron" aria-hidden="true"></span>
          </button>
          <ul class="room-list" id="rooms-${cssId(key)}" ${open ? '' : 'hidden'}>
            ${open ? renderRooms(free, allFull, rooms.length) : ''}
          </ul>
        </li>
      `);
    }

    if (buildingTotal === 0) continue;
    totalFree += buildingFree;

    html += `
      <section class="building">
        <h2 class="building-name">${escapeHtml(building)}
          <span class="building-meta">${buildingFree}/${buildingTotal} 空闲</span>
        </h2>
        <ul class="floor-list">${floorRows.join('')}</ul>
      </section>
    `;
  }

  dom.buildingGroups.innerHTML = html;
  dom.buildingGroups.hidden = html === '';
  dom.emptyState.hidden = html !== '';

  updateStatusBar(totalFree, base.length, mask);
  bindFloorToggles();
}

function renderRooms(freeRooms, allFull, floorTotal) {
  if (allFull) {
    return `<li class="room-hint">本层所选节次全满（共 ${floorTotal} 间），换一个节次看看。</li>`;
  }
  return sortRooms(freeRooms).map(room => `
    <li class="room">
      <span class="room-no">${escapeHtml(room.r)}</span>
      <span class="room-seats">${escapeHtml(String(room.c))} 座</span>
      <span class="room-run">连空 ${longestFreeRun(room.occ)} 节</span>
      <span class="room-slots" role="img" aria-label="${slotSummary(room.occ)}">
        ${(state.data.time_slots || []).map(s => `
          <span class="seg ${(room.occ & s.mask) === 0 ? 'is-free' : 'is-busy'}" title="${escapeAttr(s.name)}：${(room.occ & s.mask) === 0 ? '空闲' : '有课'}"></span>
        `).join('')}
      </span>
    </li>
  `).join('');
}

function slotSummary(occ) {
  return (state.data.time_slots || [])
    .map(s => `${s.name}${(occ & s.mask) === 0 ? '空闲' : '有课'}`)
    .join('，');
}

function updateStatusBar(free, total, mask) {
  const data = state.data;
  const stale = data.source !== 'live' || (data.data_date && data.data_date !== shanghaiToday());
  const when = `${formatDate(data.data_date)} ${formatClock(data.updated_at)}`.trim();
  const suffix = mask === 0 ? '未选节次' : `${free}/${total} 空闲`;

  dom.statusDot.dataset.state = stale ? 'stale' : 'live';
  const label = when ? `${when} 抓取` : '抓取时间未知';
  dom.statusText.textContent = `${label}${stale ? '（非实时）' : ''} · ${suffix}`;
}

function renderSlots() {
  if (!dom.slotGrid || !state.data) return;

  dom.slotGrid.innerHTML = (state.data.time_slots || []).map(slot => {
    const on = state.allDayFree || state.selectedSlots.has(slot.slot);
    return `
      <button class="slot-chip ${on ? 'is-on' : ''}" type="button" data-slot="${slot.slot}" aria-pressed="${on}">
        <span class="slot-name">${escapeHtml(slot.name)}</span>
        <span class="slot-time">${escapeHtml(slot.time)}</span>
      </button>
    `;
  }).join('');

  dom.slotGrid.querySelectorAll('.slot-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      if (state.allDayFree) {
        state.allDayFree = false;
        dom.allDayCheckbox.checked = false;
        state.selectedSlots.clear();
      }
      const n = parseInt(chip.getAttribute('data-slot'), 10);
      if (state.selectedSlots.has(n)) {
        if (state.selectedSlots.size > 1) state.selectedSlots.delete(n);
      } else {
        state.selectedSlots.add(n);
      }
      renderSlots();
      render();
    });
  });
}

function bindFloorToggles() {
  dom.buildingGroups.querySelectorAll('.floor-head').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.getAttribute('data-floor');
      if (open) state.expanded.delete(key); else state.expanded.add(key);
      render();
    });
  });
}

/* ------------------------------------------------------------- 事件绑定 */

function bindEvents() {
  if (dom.themeToggleBtn) dom.themeToggleBtn.addEventListener('click', toggleTheme);

  if (dom.allDayCheckbox) {
    dom.allDayCheckbox.addEventListener('change', e => {
      state.allDayFree = e.target.checked;
      renderSlots();
      render();
    });
  }

  if (dom.searchInput) {
    dom.searchInput.addEventListener('input', e => {
      clearTimeout(searchTimer);
      const value = e.target.value;
      searchTimer = setTimeout(() => {
        state.searchQuery = value.trim().toLowerCase();
        render();
      }, 150);
    });
  }

  if (dom.sortSelect) {
    dom.sortSelect.addEventListener('change', e => {
      state.sortBy = e.target.value;
      render();
    });
  }

  if (dom.capChips) {
    dom.capChips.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('click', () => {
        state.cap = chip.getAttribute('data-cap');
        dom.capChips.querySelectorAll('.chip').forEach(c => c.classList.toggle('is-active', c === chip));
        render();
      });
    });
  }

  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault();
    deferredPrompt = e;
    if (dom.pwaBanner) dom.pwaBanner.hidden = false;
  });

  if (dom.installBtn) {
    dom.installBtn.addEventListener('click', async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      dom.pwaBanner.hidden = true;
    });
  }
}

/* --------------------------------------------------------------- 工具 */

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function cssId(key) {
  return key.replace(/[^a-zA-Z0-9_-]/g, '_');
}

function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('./sw.js')
        .then(reg => console.log('[PWA] Service Worker registered:', reg.scope))
        .catch(err => console.warn('[PWA] Service Worker registration failed:', err));
    });
  }
}
