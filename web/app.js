/**
 * TIANGONG FREE CLASSROOM - PWA APPLICATION LOGIC
 * High-performance bitmask filtering & local time detection.
 */

// Application State
const state = {
  data: null,
  selectedBuilding: '全部',
  selectedSlots: new Set(),
  allDayFree: false,
  searchQuery: '',
  sortBy: 'room_asc', // 'room_asc', 'cap_desc', 'free_slots'
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

// Time Detector & Auto Slot Recommendation
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

  // Determine auto-selected slot based on current time
  const currentMinutes = now.getHours() * 60 + now.getMinutes();
  let recommendedSlot = 1; // Default Slot 1 (08:00 - 09:35)
  let slotName = "第1-2节";

  if (currentMinutes >= 480 && currentMinutes <= 575) { // 08:00 - 09:35
    recommendedSlot = 1; slotName = "第1-2节 (正在进行)";
  } else if (currentMinutes >= 576 && currentMinutes <= 690) { // 09:36 - 11:30
    recommendedSlot = 2; slotName = "第3-4节 (正在进行)";
  } else if (currentMinutes >= 691 && currentMinutes <= 809) { // 11:31 - 13:29
    recommendedSlot = 3; slotName = "第5节 (即将开始)";
  } else if (currentMinutes >= 810 && currentMinutes <= 905) { // 13:30 - 15:05
    recommendedSlot = 4; slotName = "第6-7节 (正在进行)";
  } else if (currentMinutes >= 906 && currentMinutes <= 1020) { // 15:06 - 17:00
    recommendedSlot = 5; slotName = "第8-9节 (正在进行)";
  } else if (currentMinutes >= 1021 && currentMinutes <= 1205) { // 17:01 - 20:05
    recommendedSlot = 6; slotName = "第10-11节 (正在进行/即将开始)";
  } else if (currentMinutes > 1205) {
    recommendedSlot = 1; slotName = "第1-2节 (明日推荐)";
  } else {
    recommendedSlot = 1; slotName = "第1-2节 (即将开始)";
  }

  if (dom.recommendedSlotText) {
    dom.recommendedSlotText.innerHTML = `根据当前时间，推荐查询 <span>${slotName}</span>`;
  }

  // Only auto-select on initial load if user hasn't toggled manually
  if (state.selectedSlots.size === 0 && !state.allDayFree) {
    state.selectedSlots.add(recommendedSlot);
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

  if (dom.updatedAtText && fetchedData.updated_at) {
    dom.updatedAtText.textContent = `数据更新于: ${fetchedData.updated_at}`;
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

// Render Building Capsules
function renderBuildingTabs() {
  if (!dom.buildingTabs || !state.data) return;

  const buildings = ['全部', ...state.data.buildings];
  dom.buildingTabs.innerHTML = buildings.map(b => `
    <button class="tab-btn ${state.selectedBuilding === b ? 'active' : ''}" data-building="${b}">
      ${b}
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

// Render Time Slot Selector Chips
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
        // Prevent clearing all slots (keep at least 1)
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

// Fast Local Bitmask Filtering & Classroom Cards Rendering
function renderClassrooms() {
  if (!dom.classroomList || !state.data) return;

  // Compute Target Bitmask
  let targetMask = 0;
  if (state.allDayFree) {
    targetMask = 2047; // Bit0..Bit10 all 1s
  } else {
    for (const slotNum of state.selectedSlots) {
      const slotObj = state.data.time_slots.find(s => s.slot === slotNum);
      if (slotObj) {
        targetMask |= slotObj.mask;
      }
    }
  }

  // Pure JS Bitwise Filter: (room.occ & targetMask) === 0
  let filtered = state.data.classrooms.filter(room => {
    // 1. Building Filter
    if (state.selectedBuilding !== '全部' && room.b !== state.selectedBuilding) {
      return false;
    }

    // 2. Bitmask Protocol Check
    if ((room.occ & targetMask) !== 0) {
      return false;
    }

    // 3. Search Filter
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
      // Default: room_asc
      return a.r.localeCompare(b.r, undefined, { numeric: true });
    }
  });

  // Update Results Count
  if (dom.resultsCount) {
    dom.resultsCount.textContent = filtered.length;
  }

  // Render Empty State or Cards
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

// Card Renderer with 6-Slot Timeline Bar
function renderRoomCard(room) {
  const timeSlots = state.data.time_slots;
  
  const timelineHtml = timeSlots.map(slot => {
    const isFree = (room.occ & slot.mask) === 0;
    const shortLabel = slot.name.replace('第', '').replace('节', '');
    return `
      <div class="timeline-slot ${isFree ? 'free' : 'busy'}" title="${slot.name}: ${isFree ? '空闲' : '有课'}">
        <div class="slot-indicator"></div>
        <div class="slot-label">${shortLabel}</div>
      </div>
    `;
  }).join('');

  return `
    <div class="classroom-card">
      <div class="card-header">
        <div class="room-title-group">
          <span class="room-building">${room.b}</span>
          <span class="room-name">${room.r}</span>
        </div>
        <div class="room-badges">
          <span class="badge badge-capacity">${room.c}座</span>
          <span class="badge">${room.t}</span>
        </div>
      </div>
      <div class="timeline-bar">
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
        <div class="empty-desc">请检查网络连接或确认 public/data/today.json 文件是否存在</div>
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
