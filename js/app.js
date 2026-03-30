/* ===========================
   DerBLNguide — App Logic
   =========================== */

const CAT_LABELS = {
  general:     '🎪 Festival',
  music:       '🎵 Music',
  photography: '📷 Photo',
  exhibition:  '🖼 Exhibition',
};

const SOURCE_LABELS = {
  rausgegangen:        'Rausgegangen',
  'tip-berlin':        'Tip Berlin',
  filmriss:            'Filmriss',
  'photography-berlin':'Photo.Berlin',
  ra:                  'Resident Advisor',
};

// --- State ---
let allEvents = [];
let activeCategory = 'all';
let weekOffset = 0;   // 0 = current week, -1 = last week, +1 = next week

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  setupCategoryFilter();
  setupWeekNav();
  loadEvents();
});

// --- Data Loading ---
async function loadEvents() {
  showLoading(true);
  try {
    // Cache-bust so GitHub Pages always serves fresh data
    const res = await fetch(`data/events.json?v=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allEvents = data.events || [];
    updateLastUpdated(data.last_updated);
    render();
  } catch (err) {
    console.error('Failed to load events:', err);
    showError(true);
  } finally {
    showLoading(false);
  }
}

function updateLastUpdated(ts) {
  const el = document.getElementById('last-updated');
  if (!ts) { el.textContent = ''; return; }
  const d = new Date(ts);
  const rel = relativeTime(d);
  el.textContent = `Updated ${rel}`;
  el.title = d.toLocaleString('de-DE', { timeZone: 'Europe/Berlin' });
}

// --- Week helpers ---
function getMondayOfWeek(offset) {
  const now = new Date();
  const day = now.getDay(); // 0=Sun
  const diffToMonday = (day === 0 ? -6 : 1 - day) + offset * 7;
  const mon = new Date(now);
  mon.setDate(now.getDate() + diffToMonday);
  mon.setHours(0, 0, 0, 0);
  return mon;
}

function getWeekDays(offset) {
  const mon = getMondayOfWeek(offset);
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(mon);
    d.setDate(mon.getDate() + i);
    return d;
  });
}

function toDateString(d) {
  return d.toISOString().slice(0, 10); // YYYY-MM-DD
}

// --- Render ---
function render() {
  const days = getWeekDays(weekOffset);
  updateWeekLabel(days);

  const today = toDateString(new Date());
  const container = document.getElementById('days-container');
  container.innerHTML = '';

  const filtered = activeCategory === 'all'
    ? allEvents
    : allEvents.filter(e => e.category === activeCategory);

  days.forEach(day => {
    const ds = toDateString(day);
    const dayEvents = filtered.filter(e => e.date === ds);

    const section = document.createElement('section');
    section.className = 'day-section';
    section.dataset.date = ds;

    const isToday = ds === today;
    section.innerHTML = `
      <div class="day-header">
        <span class="day-name ${isToday ? 'today' : ''}">${formatDayName(day)}</span>
        ${isToday ? '<span class="today-badge">Today</span>' : ''}
        <span class="day-date">${formatDayDate(day)}</span>
        <span class="day-count">${dayEvents.length} event${dayEvents.length !== 1 ? 's' : ''}</span>
      </div>
      <div class="events-grid" id="grid-${ds}"></div>
    `;
    container.appendChild(section);

    const grid = section.querySelector(`#grid-${ds}`);

    if (dayEvents.length === 0) {
      grid.innerHTML = '<div class="no-events">No events found for this day yet.</div>';
    } else {
      dayEvents.sort((a, b) => (a.time || '').localeCompare(b.time || ''));
      dayEvents.forEach(event => grid.appendChild(buildCard(event)));
    }
  });
}

function buildCard(event) {
  const card = document.createElement('article');
  card.className = `event-card cat-${event.category || 'general'}`;

  const catLabel = CAT_LABELS[event.category] || event.category || 'Event';
  const srcLabel = SOURCE_LABELS[event.source] || event.source || '';
  const timeStr  = event.time ? formatTime(event.time) : '';

  let imageHtml = '';
  if (event.image_url) {
    imageHtml = `<img class="event-card-image" src="${escHtml(event.image_url)}" alt="" loading="lazy" onerror="this.style.display='none'" />`;
  }

  card.innerHTML = `
    <div class="event-card-stripe"></div>
    ${imageHtml}
    <div class="event-card-body">
      <div class="event-card-meta">
        <span class="cat-tag ${escHtml(event.category || 'general')}">${escHtml(catLabel)}</span>
        ${timeStr ? `<span class="event-time">${escHtml(timeStr)}</span>` : ''}
      </div>
      <div class="event-title">${escHtml(event.title || 'Untitled')}</div>
      ${event.venue ? `<div class="event-venue">📍 ${escHtml(event.venue)}</div>` : ''}
      ${event.description ? `<div class="event-desc">${escHtml(event.description)}</div>` : ''}
    </div>
    <div class="event-card-footer">
      <span class="source-tag">${escHtml(srcLabel)}</span>
      ${event.url ? `<a class="event-link" href="${escHtml(event.url)}" target="_blank" rel="noopener noreferrer">Details →</a>` : ''}
    </div>
  `;
  return card;
}

// --- UI Helpers ---
function setupCategoryFilter() {
  document.querySelectorAll('.cat-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.cat-chip').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeCategory = btn.dataset.cat;
      render();
    });
  });
}

function setupWeekNav() {
  document.getElementById('prev-week').addEventListener('click', () => {
    weekOffset--;
    render();
  });
  document.getElementById('next-week').addEventListener('click', () => {
    weekOffset++;
    render();
  });
}

function updateWeekLabel(days) {
  const first = days[0];
  const last  = days[6];
  const opts  = { day: 'numeric', month: 'short' };
  const label = weekOffset === 0
    ? `This week · ${first.toLocaleDateString('en-GB', opts)} – ${last.toLocaleDateString('en-GB', opts)}`
    : `${first.toLocaleDateString('en-GB', opts)} – ${last.toLocaleDateString('en-GB', opts)}`;
  document.getElementById('week-label').textContent = label;
}

function showLoading(on) {
  document.getElementById('loading').classList.toggle('hidden', !on);
}
function showError(on) {
  document.getElementById('error').classList.toggle('hidden', !on);
}

// --- Formatting ---
function formatDayName(d) {
  return d.toLocaleDateString('en-GB', { weekday: 'long' });
}
function formatDayDate(d) {
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long' });
}
function formatTime(t) {
  if (!t) return '';
  // Accept HH:MM or HH:MM:SS
  const parts = t.split(':');
  if (parts.length >= 2) return `${parts[0]}:${parts[1]}`;
  return t;
}

function relativeTime(d) {
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 2)  return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
