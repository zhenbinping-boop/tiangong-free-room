/**
 * TIANGONG FREE CLASSROOM - PWA APPLICATION LOGIC (PRD v2.0)
 * High-performance 5-bit bitmask filtering & local time auto-matching.
 */

// Application State
const state = {
  data: null,
  selectedBuilding: 'ALL', // 'ALL', '第一公共教学楼', '第二公共教学楼'
  selectedSlots: new Set(),
  allDayFree: false,
  searchQuery: '',
  sortBy: 'room_asc',
  theme: localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
};

// DOM References
const dom = {
  buildingTabs: document.getElementById('buildingTabs'),
  slotGrid: document.getElementById('slotGrid'),
  allDayCheckbox: document.getElementById('allDayCheckbox'),
  searchInput: document.getElementById('searchInput'),
  sortSelect: document.getElementById('sortSelect'),
  classroomList: document.getElementById('classroomList'),
  resultsCount: document.getElementById('resultsCount'),
  updatedAtText: document.getElementById('updatedAtText'),
  liveClock: document.getElementById('liveClock'),
  recommendedSlotText: document.getElementById('recommendedSlotText'),
  themeToggleBtn: document.getElementById('themeToggleBtn'),
  emptyState: document.getElementById('emptyState'),
  pwaInstallBanner: document.getElementById('pwaInstallBanner'),
  installPwaBtn: document.getElementById('installPwaBtn')
};

let deferredPrompt = null;

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initTimeDetector();
  fetchScheduleData();
  bindEvents();
  registerServiceWorker();
});

// Theme Management
function initTheme() {
  document.documentElement.setAttribute('data-theme', state.theme);
  updateThemeIcon();
}

function toggleTheme() {
  state.theme = state.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('theme', state.theme);
  document.documentElement.setAttribute('data-theme', state.theme);
  updateThemeIcon();
}

function updateThemeIcon() {
  if (dom.themeToggleBtn) {
    dom.themeToggleBtn.textContent = state.theme === 'dark' ? '☀️' : '🌙';
  }
}

// Auto Time Slot Recommendation (PRD v2.0 5-Slot Rules)
function getAutoSlotNumber() {
  const now = new Date();
  const minutes = now.getHours() * 60 + now.getMinutes();
  if (minutes <= 10 * 60) return 1;          // 10:00 前 -> 第1大节 (08:20-10:00)
  if (minutes <= 12 * 60 + 30) return 2;     // 12:30 前 -> 第2大节 (10:20-12:00)
  if (minutes <= 15 * 60 + 40) return 3;     // 15:40 前 -> 第3大节 (14:00-15:40)
  if (minutes <= 17 * 60 + 40) return 4;     // 17:40 前 -> 第4大节 (16:00-17:40)
  return 5;                                  // 17:40 后 -> 第5大节 (18:30-20:10)
}

function initTimeDetector() {
  updateLiveClock();
  setInterval(updateLiveClock, 10000);
}

function updateLiveClock() {
  const now = new Date();
  const hours = String(now.getHours()).padStart(2, '0');
  const minutes = String(now.getMinutes()).padStart(2, '0');
  const timeStr = `${hours}:${minutes}`;

  if (dom.liveClock) {
    dom.liveClock.textContent = timeStr;
  }

  const autoSlot = getAutoSlotNumber();
  const slotNames = ["", "第1大节 (08:20-10:00)", "第2大节 (10:20-12:00)", "第3大节 (14:00-15:40)", "第4大节 (16:00-17:40)", "第5大节 (18:30-20:10)"];

  if (dom.recommendedSlotText) {
    dom.recommendedSlotText.innerHTML = `已根据当前时间推荐 <span>${slotNames[autoSlot]}</span>`;
  }

  // Auto select on first load if user hasn't selected manually
  if (state.selectedSlots.size === 0 && !state.allDayFree) {
    state.selectedSlots.add(autoSlot);
  }
}

// Data Fetching
async function fetchScheduleData() {
  const paths = ['./data/today.json', '../public/data/today.json'];
  let fetchedData = null;

  for (const path of paths) {
    try {
      const resp = await fetch(path);
      if (resp.ok) {
        fetchedData = await resp.json();
        break;
      }
    } catch (e) {
      console.warn(`Failed to load data from ${path}`, e);
    }
  }

  if (!fetchedData) {
    console.error('Could not load classroom JSON data');
    renderErrorState();
    return;
  }

  state.data = fetchedData;

  // P0 数据诚实性检查：source 非 live，或数据日期不是今天 → 显示横幅
  const staleBanner = document.getElementById('staleDataBanner');
  if (staleBanner) {
    const todayStr = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }); // YYYY-MM-DD
    const isStale = fetchedData.source !== 'live' || (fetchedData.data_date && fetchedData.data_date !== todayStr);
    staleBanner.style.display = isStale ? 'block' : 'none';
  }

  if (dom.updatedAtText && fetchedData.updated_at) {
    const timeOnly = fetchedData.updated_at.split(' ')[1] || fetchedData.updated_at;
    dom.updatedAtText.textContent = `更新于 ${timeOnly}`;
  }

  renderBuildingTabs();
  renderSlotGrid();
  renderClassrooms();
}

// UI Event Handlers
function bindEvents() {
  if (dom.themeToggleBtn) {
    dom.themeToggleBtn.addEventListener('click', toggleTheme);
  }

  if (dom.allDayCheckbox) {
    dom.allDayCheckbox.addEventListener('change', (e) => {
      state.allDayFree = e.target.checked;
      renderSlotGrid();
      renderClassrooms();
    });
  }

  if (dom.searchInput) {
    dom.searchInput.addEventListener('input', (e) => {
      state.searchQuery = e.target.value.trim().toLowerCase();
      renderClassrooms();
    });
  }

  if (dom.sortSelect) {
    dom.sortSelect.addEventListener('change', (e) => {
      state.sortBy = e.target.value;
      renderClassrooms();
    });
  }

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    if (dom.pwaInstallBanner) {
      dom.pwaInstallBanner.style.display = 'flex';
    }
  });

  if (dom.installPwaBtn) {
    dom.installPwaBtn.addEventListener('click', async () => {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        console.log(`User prompt outcome: ${outcome}`);
        deferredPrompt = null;
        dom.pwaInstallBanner.style.display = 'none';
      }
    });
  }
}

// Render Building Capsules (第一公共教学楼, 第二公共教学楼)
function renderBuildingTabs() {
  if (!dom.buildingTabs) return;

  // 楼栋标签由真实数据推导，避免出现"有标签但无数据"的空楼栋
  const present = [...new Set((state.data.classrooms || []).map(r => r.b))];
  const buildings = [{ key: 'ALL', label: '全部' }].concat(
    present.map(b => ({ key: b, label: b.replace('公共教学楼', '公教') }))
  );
  if (!buildings.some(b => b.key === state.selectedBuilding)) {
    state.selectedBuilding = 'ALL';
  }

  dom.buildingTabs.innerHTML = buildings.map(b => `
    <button class="tab-btn ${state.selectedBuilding === b.key ? 'active' : ''}" data-building="${b.key}">
      ${b.label}
    </button>
  `).join('');

  dom.buildingTabs.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const b = e.target.getAttribute('data-building');
      state.selectedBuilding = b;
      renderBuildingTabs();
      renderClassrooms();
    });
  });
}

// Render Time Slot Grid (5 Big Slots)
function renderSlotGrid() {
  if (!dom.slotGrid || !state.data) return;

  dom.slotGrid.innerHTML = state.data.time_slots.map(slot => {
    const isSelected = state.allDayFree || state.selectedSlots.has(slot.slot);
    return `
      <div class="slot-chip ${isSelected ? 'selected' : ''}" data-slot="${slot.slot}">
        <span class="name">${slot.name}</span>
        <span class="time">${slot.time}</span>
      </div>
    `;
  }).join('');

  dom.slotGrid.querySelectorAll('.slot-chip').forEach(chip => {
    chip.addEventListener('click', (e) => {
      if (state.allDayFree) {
        state.allDayFree = false;
        if (dom.allDayCheckbox) dom.allDayCheckbox.checked = false;
        state.selectedSlots.clear();
      }

      const slotNum = parseInt(chip.getAttribute('data-slot'), 10);
      if (state.selectedSlots.has(slotNum)) {
        if (state.selectedSlots.size > 1) {
          state.selectedSlots.delete(slotNum);
        }
      } else {
        state.selectedSlots.add(slotNum);
      }

      renderSlotGrid();
      renderClassrooms();
    });
  });
}

// Bitmask Protocol Filter (occ & mask === 0)
function renderClassrooms() {
  if (!dom.classroomList || !state.data) return;

  let targetMask = 0;
  if (state.allDayFree) {
    targetMask = 31; // 1 | 2 | 4 | 8 | 16 = 31
  } else {
    for (const slotNum of state.selectedSlots) {
      const slotObj = state.data.time_slots.find(s => s.slot === slotNum);
      if (slotObj) {
        targetMask |= slotObj.mask;
      }
    }
  }

  let filtered = state.data.classrooms.filter(room => {
    // 1. Building match
    if (state.selectedBuilding !== 'ALL' && room.b !== state.selectedBuilding) {
      return false;
    }

    // 2. 5-Bit Bitmask protocol: (room.occ & targetMask) === 0
    if ((room.occ & targetMask) !== 0) {
      return false;
    }

    // 3. Search query filter
    if (state.searchQuery) {
      const q = state.searchQuery;
      const fullId = `${room.b}${room.r}`.toLowerCase();
      const type = room.t.toLowerCase();
      if (!fullId.includes(q) && !room.r.toLowerCase().includes(q) && !type.includes(q)) {
        return false;
      }
    }

    return true;
  });

  // Sorting
  filtered.sort((a, b) => {
    if (state.sortBy === 'cap_desc') {
      return b.c - a.c;
    } else if (state.sortBy === 'free_slots') {
      const freeA = countFreeSlots(a.occ);
      const freeB = countFreeSlots(b.occ);
      return freeB - freeA;
    } else {
      return a.r.localeCompare(b.r, undefined, { numeric: true });
    }
  });

  if (dom.resultsCount) {
    dom.resultsCount.textContent = filtered.length;
  }

  if (filtered.length === 0) {
    dom.classroomList.style.display = 'none';
    if (dom.emptyState) dom.emptyState.style.display = 'block';
    return;
  }

  if (dom.emptyState) dom.emptyState.style.display = 'none';
  dom.classroomList.style.display = 'grid';

  dom.classroomList.innerHTML = filtered.map(room => renderRoomCard(room)).join('');
}

function countFreeSlots(occ) {
  let count = 0;
  for (const slot of state.data.time_slots) {
    if ((occ & slot.mask) === 0) count++;
  }
  return count;
}

// Classroom Card Renderer with 5-Slot Timeline Bar
function renderRoomCard(room) {
  const timeSlots = state.data.time_slots;
  const shortBuildingName = room.b === '第一公共教学楼' ? '第一公教' : (room.b === '第二公共教学楼' ? '第二公教' : room.b);

  const timelineHtml = timeSlots.map(slot => {
    const isFree = (room.occ & slot.mask) === 0;
    return `
      <div class="timeline-slot ${isFree ? 'free' : 'busy'}" title="${slot.name}: ${isFree ? '空闲' : '有课'}">
        <div class="slot-indicator"></div>
        <div class="slot-label">${slot.name}</div>
      </div>
    `;
  }).join('');

  return `
    <div class="classroom-card">
      <div class="card-header">
        <div class="room-title-group">
          <span class="room-building">${shortBuildingName}</span>
          <span class="room-name">${room.r}</span>
        </div>
        <div class="room-badges">
          <span class="badge badge-capacity">${room.c}座</span>
          ${room.t ? `<span class="badge">${room.t}</span>` : ''}
        </div>
      </div>
      <div class="timeline-bar grid-5">
        ${timelineHtml}
      </div>
    </div>
  `;
}

function renderErrorState() {
  if (dom.classroomList) {
    dom.classroomList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">⚠️</div>
        <div class="empty-title">无法加载数据</div>
        <div class="empty-desc">请检查网络连接或确认 data/today.json 结构</div>
      </div>
    `;
  }
}

// Service Worker Registration for PWA
function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('./sw.js')
        .then(reg => console.log('[PWA] Service Worker registered:', reg.scope))
        .catch(err => console.warn('[PWA] Service Worker registration failed:', err));
    });
  }
}
