/* ============================================================
   app.js — Dashboard frontend logic
   
   WHAT THIS FILE DOES:
   1. Calls GET /news every time the scheduler fires (via polling)
   2. Calls GET /scheduler/status every 15 seconds to update
      the status panel and countdown timer
   3. Sends POST requests to start / stop / configure the scheduler
   4. Renders news cards, handles category filters and search
   5. Shows a "N new articles" toast when fresh data arrives
   ============================================================ */

// ── State ──────────────────────────────────────────────────────
const state = {
  articles:        [],        // current displayed articles
  allArticles:     [],        // all articles from last fetch
  selectedCategory: "All",   // current category filter
  searchKeyword:   "",        // current search text
  schedulerRunning: false,    // is the custom job active?
  selectedInterval: "5min",   // interval chosen in the UI
  nextRunISO:      null,      // ISO string of next run time
  lastRunISO:      null,      // ISO string of last run time
  lastSaved:       0,         // articles saved in last run
  lastDuplicates:  0,
  pollingTimer:    null,      // setInterval handle for status poll
  countdownTimer:  null,      // setInterval handle for countdown
  lastArticleCount: 0,        // used to detect new articles
};

// ── DOM shortcuts ──────────────────────────────────────────────
const $  = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

// ── Interval card definitions ──────────────────────────────────
const INTERVALS = [
  { key: "1min",  icon: "⚡", label: "1 Minute",  sub: "Real-time testing" },
  { key: "5min",  icon: "🕐", label: "5 Minutes", sub: "Frequent updates"  },
  { key: "1hour", icon: "⏰", label: "1 Hour",    sub: "Regular refresh"   },
  { key: "1day",  icon: "📅", label: "1 Day",     sub: "Daily briefing"    },
];

// ── Category definitions (for filter tabs) ─────────────────────
const CATEGORIES = [
  "All", "AI", "Agentic AI", "Quantum Computing", "Cloud Computing",
  "Cybersecurity", "Programming", "Developer Tools",
  "Startups", "Technology Companies", "Other Technology"
];

// Map category name → CSS class suffix
const CAT_CLASS = {
  "AI": "AI",
  "Agentic AI": "Agentic-AI",
  "Quantum Computing": "Quantum",
  "Cloud Computing": "Cloud",
  "Cybersecurity": "Cybersecurity",
  "Programming": "Programming",
  "Developer Tools": "DevTools",
  "Startups": "Startups",
  "Technology Companies": "TechCompanies",
  "Other Technology": "Other"
};

// ═══════════════════════════════════════════════════════════════
// INITIALISATION
// ═══════════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", () => {
  buildIntervalCards();
  buildCategoryTabs();
  attachEventListeners();
  loadNews();                   // fetch articles on page load
  pollSchedulerStatus();        // get scheduler state immediately
  startStatusPolling();         // then every 15 seconds
  startCountdown();             // tick the countdown every second
});

// ── Build interval selector cards ─────────────────────────────
function buildIntervalCards() {
  const grid = $("intervalGrid");
  if (!grid) return;

  INTERVALS.forEach(iv => {
    const label = document.createElement("label");
    label.className = "interval-card" + (iv.key === state.selectedInterval ? " selected" : "");
    label.dataset.key = iv.key;
    label.innerHTML = `
      <input type="radio" name="interval" value="${iv.key}" ${iv.key === state.selectedInterval ? "checked" : ""}>
      <div class="interval-icon">${iv.icon}</div>
      <div class="interval-label">${iv.label}</div>
      <div class="interval-sub">${iv.sub}</div>
    `;
    label.addEventListener("click", () => selectInterval(iv.key));
    grid.appendChild(label);
  });
}

// ── Build category filter tabs ─────────────────────────────────
function buildCategoryTabs() {
  const tabs = $("categoryTabs");
  if (!tabs) return;

  CATEGORIES.forEach(cat => {
    const btn = document.createElement("button");
    btn.className = "cat-tab" + (cat === state.selectedCategory ? " active" : "");
    btn.textContent = cat;
    btn.addEventListener("click", () => {
      state.selectedCategory = cat;
      $$(".cat-tab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      applyFilters();
    });
    tabs.appendChild(btn);
  });
}

// ── Wire up all buttons ────────────────────────────────────────
function attachEventListeners() {
  $("btnStart")    ?.addEventListener("click", onStartScheduler);
  $("btnStop")     ?.addEventListener("click", onStopScheduler);
  $("btnSave")     ?.addEventListener("click", onSaveSchedule);
  $("btnFetchNow") ?.addEventListener("click", onFetchNow);
  $("themeToggle") ?.addEventListener("click", toggleTheme);

  $("searchInput")?.addEventListener("input", e => {
    state.searchKeyword = e.target.value.trim().toLowerCase();
    applyFilters();
  });
}

// ═══════════════════════════════════════════════════════════════
// INTERVAL SELECTION
// ═══════════════════════════════════════════════════════════════

function selectInterval(key) {
  state.selectedInterval = key;

  $$(".interval-card").forEach(card => {
    card.classList.toggle("selected", card.dataset.key === key);
  });
}

// ═══════════════════════════════════════════════════════════════
// SCHEDULER API CALLS
// ═══════════════════════════════════════════════════════════════

async function onStartScheduler() {
  setButtonsLoading(true);
  try {
    const res = await fetch("/scheduler/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval: state.selectedInterval })
    });
    const data = await res.json();

    if (data.success !== false) {
      showToast(`✅ Scheduler started — ${data.interval_label || state.selectedInterval}`, "green");
      await pollSchedulerStatus();
    } else {
      showError(data.message || "Failed to start scheduler");
    }
  } catch (e) {
    showError("Network error: " + e.message);
  } finally {
    setButtonsLoading(false);
  }
}

async function onStopScheduler() {
  setButtonsLoading(true);
  try {
    const res  = await fetch("/scheduler/stop", { method: "POST" });
    const data = await res.json();

    if (data.success !== false) {
      showToast("🛑 Scheduler stopped", "red");
      await pollSchedulerStatus();
    } else {
      showError(data.message || "Failed to stop scheduler");
    }
  } catch (e) {
    showError("Network error: " + e.message);
  } finally {
    setButtonsLoading(false);
  }
}

async function onSaveSchedule() {
  try {
    const res  = await fetch("/scheduler/configure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval: state.selectedInterval })
    });
    const data = await res.json();

    if (data.success !== false) {
      showToast(`💾 Schedule saved — ${data.interval_label || state.selectedInterval}`, "green");
    } else {
      showError(data.message || "Failed to save schedule");
    }
  } catch (e) {
    showError("Network error: " + e.message);
  }
}

async function onFetchNow() {
  const btn = $("btnFetchNow");
  if (btn) { btn.disabled = true; btn.textContent = "⏳ Fetching..."; }

  try {
    const res  = await fetch("/news/fetch-now", { method: "POST" });
    const data = await res.json();

    if (res.status === 409) {
      showToast("⚠️ A fetch is already running, please wait.", "yellow");
    } else {
      showToast("🔄 Fetch started — news will update shortly", "green");
      // Poll for new articles after a brief delay
      setTimeout(() => { loadNews(); pollSchedulerStatus(); }, 35000);
    }
  } catch (e) {
    showError("Network error: " + e.message);
  } finally {
    setTimeout(() => {
      if (btn) { btn.disabled = false; btn.textContent = "⚡ Fetch News Now"; }
    }, 5000);
  }
}

// ═══════════════════════════════════════════════════════════════
// SCHEDULER STATUS POLLING
// Every 15 seconds, fetch /scheduler/status and update the panel
// ═══════════════════════════════════════════════════════════════

function startStatusPolling() {
  // Clear any existing timer
  if (state.pollingTimer) clearInterval(state.pollingTimer);
  // Poll every 15 seconds
  state.pollingTimer = setInterval(pollSchedulerStatus, 15000);
}

async function pollSchedulerStatus() {
  try {
    const res  = await fetch("/scheduler/status");
    const data = await res.json();

    if (!data.success && data.data === undefined) return;

    const s = data.data || data;  // handle both wrapped and raw responses

    const wasRunning = state.schedulerRunning;
    state.schedulerRunning = s.running === true;
    state.nextRunISO       = s.next_run  || null;
    state.lastRunISO       = s.last_run  || null;
    state.lastSaved        = s.last_summary?.total_saved      || 0;
    state.lastDuplicates   = s.last_summary?.total_duplicates || 0;

    // Sync the selected interval from backend (e.g. after a restore)
    if (s.interval && INTERVALS.find(i => i.key === s.interval)) {
      state.selectedInterval = s.interval;
      $$(".interval-card").forEach(card => {
        card.classList.toggle("selected", card.dataset.key === s.interval);
      });
    }

    updateStatusPanel(s);

    // If the scheduler just fired (lastRun changed), refresh articles
    if (state.schedulerRunning && s.last_run && s.last_run !== state.lastRunISO) {
      loadNews();
    }

    // If job finished and new articles were saved, reload
    if (!s.job_in_progress && wasRunning && state.lastSaved > 0) {
      loadNews();
    }

  } catch (e) {
    // silent — don't crash the page if the server is temporarily unreachable
    console.warn("Status poll failed:", e.message);
  }
}

// ── Update the status panel DOM ────────────────────────────────
function updateStatusPanel(s) {
  // Running badge
  const badge = $("statusBadge");
  if (badge) {
    if (s.running) {
      badge.className = "badge badge-green";
      badge.innerHTML = `<span class="dot"></span> Running`;
    } else {
      badge.className = "badge badge-red";
      badge.innerHTML = `<span class="dot"></span> Stopped`;
    }
  }

  // Interval label
  setEl("currentInterval", s.interval_label || s.interval || "—");

  // Last run time
  setEl("lastRun", s.last_run ? formatDateTime(s.last_run) : "Never");

  // Next run time
  setEl("nextRun", s.next_run ? formatDateTime(s.next_run) : (s.running ? "Calculating..." : "—"));

  // Last run summary
  const saved = s.last_summary?.total_saved || 0;
  const dups  = s.last_summary?.total_duplicates || 0;
  setEl("lastSaved",      saved > 0 ? `${saved} new` : "0 new");
  setEl("lastDuplicates", dups  > 0 ? `${dups} skipped` : "0 skipped");

  // Error message
  const errEl = $("lastError");
  if (errEl) {
    errEl.textContent = s.last_error || "";
    errEl.style.display = s.last_error ? "block" : "none";
  }

  // In-progress indicator
  const prog = $("jobInProgress");
  if (prog) prog.style.display = s.job_in_progress ? "flex" : "none";

  // Update buttons
  const btnStart = $("btnStart");
  const btnStop  = $("btnStop");
  if (btnStart) btnStart.disabled = s.running === true;
  if (btnStop)  btnStop.disabled  = s.running !== true;
}

// ═══════════════════════════════════════════════════════════════
// COUNTDOWN TIMER
// Ticks every second, counts down to state.nextRunISO
// ═══════════════════════════════════════════════════════════════

function startCountdown() {
  if (state.countdownTimer) clearInterval(state.countdownTimer);
  state.countdownTimer = setInterval(tickCountdown, 1000);
}

function tickCountdown() {
  const el = $("countdownValue");
  if (!el) return;

  if (!state.schedulerRunning || !state.nextRunISO) {
    el.textContent = "--:--:--";
    return;
  }

  const now      = Date.now();
  const next     = new Date(state.nextRunISO).getTime();
  const diffMs   = next - now;

  if (diffMs <= 0) {
    el.textContent = "00:00:00";
    // Re-poll status since the job should have fired
    setTimeout(pollSchedulerStatus, 3000);
    setTimeout(loadNews, 35000);
    return;
  }

  const totalSec = Math.floor(diffMs / 1000);
  const h  = Math.floor(totalSec / 3600);
  const m  = Math.floor((totalSec % 3600) / 60);
  const s  = totalSec % 60;

  el.textContent =
    String(h).padStart(2, "0") + ":" +
    String(m).padStart(2, "0") + ":" +
    String(s).padStart(2, "0");
}

// ═══════════════════════════════════════════════════════════════
// NEWS LOADING
// ═══════════════════════════════════════════════════════════════

async function loadNews(showSpinner = true) {
  if (showSpinner) showLoading();

  try {
    const res  = await fetch("/news?limit=60");
    const data = await res.json();

    if (!data.success && data.data === undefined) {
      showNewsError("Could not load articles.");
      return;
    }

    const articles = data.data?.articles || data.articles || [];
    const prevCount = state.lastArticleCount;

    state.allArticles        = articles;
    state.lastArticleCount   = articles.length;

    // Show "new articles" toast if count increased
    const diff = articles.length - prevCount;
    if (prevCount > 0 && diff > 0) {
      showNewArticlesToast(diff);
    }

    applyFilters();

    // Update article count stat
    setEl("articleCount", articles.length);

  } catch (e) {
    showNewsError("Network error loading news.");
    console.error(e);
  }
}

// ── Apply category filter + search ────────────────────────────
function applyFilters() {
  let filtered = state.allArticles;

  // Category filter
  if (state.selectedCategory !== "All") {
    filtered = filtered.filter(a => a.category === state.selectedCategory);
  }

  // Search filter
  if (state.searchKeyword) {
    const kw = state.searchKeyword;
    filtered = filtered.filter(a =>
      (a.title       || "").toLowerCase().includes(kw) ||
      (a.description || "").toLowerCase().includes(kw) ||
      (a.category    || "").toLowerCase().includes(kw)
    );
  }

  state.articles = filtered;
  renderCards(filtered);
  setEl("filteredCount", filtered.length);
}

// ── Render news cards ─────────────────────────────────────────
function renderCards(articles) {
  const grid = $("newsGrid");
  if (!grid) return;

  if (articles.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="empty-icon">📭</div>
        <h3>No articles found</h3>
        <p>${state.selectedCategory !== "All" || state.searchKeyword
          ? "Try a different category or search term."
          : 'Click "Fetch News Now" or start the scheduler to collect articles.'}</p>
      </div>`;
    return;
  }

  grid.innerHTML = articles.map(a => buildCard(a)).join("");
}

function buildCard(article) {
  const catClass = CAT_CLASS[article.category] || "Other";
  const date     = article.published_at
    ? new Date(article.published_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })
    : "";
  const desc  = article.description || "No description available.";
  const title = article.title || "No title";
  const url   = article.url   || "#";
  const src   = article.source || "Unknown";

  return `
    <div class="news-card">
      <div class="card-header">
        <span class="card-category cat-${catClass}">${article.category || "Other"}</span>
        <span class="card-date">${date}</span>
      </div>
      <div class="card-title">${escHtml(title)}</div>
      <div class="card-desc">${escHtml(desc)}</div>
      <div class="card-footer">
        <span class="card-source">📰 ${escHtml(src)}</span>
        <a class="card-link" href="${url}" target="_blank" rel="noopener">
          Read →
        </a>
      </div>
    </div>`;
}

// ═══════════════════════════════════════════════════════════════
// UI HELPERS
// ═══════════════════════════════════════════════════════════════

function showLoading() {
  const grid = $("newsGrid");
  if (grid) grid.innerHTML = `
    <div class="loading-overlay" style="grid-column:1/-1">
      <div class="spinner"></div>
      <span>Loading articles...</span>
    </div>`;
}

function showNewsError(msg) {
  const grid = $("newsGrid");
  if (grid) grid.innerHTML = `
    <div class="empty-state" style="grid-column:1/-1">
      <div class="empty-icon">⚠️</div>
      <h3>Could not load news</h3>
      <p>${escHtml(msg)}</p>
    </div>`;
}

function showNewArticlesToast(count) {
  const el = $("newArticlesToast");
  if (!el) return;
  el.textContent = `✅ ${count} new article${count > 1 ? "s" : ""} added!`;
  el.style.display = "block";
  setTimeout(() => { el.style.display = "none"; }, 6000);
}

function showToast(message, type = "green") {
  const el = $("toastMessage");
  if (!el) return;
  el.textContent    = message;
  el.className      = type === "green" ? "new-articles-toast" : "error-toast";
  el.style.display  = "block";
  setTimeout(() => { el.style.display = "none"; }, 5000);
}

function showError(msg) {
  const el = $("errorMessage");
  if (!el) return;
  el.textContent   = msg;
  el.style.display = "block";
  setTimeout(() => { el.style.display = "none"; }, 8000);
}

function setEl(id, text) {
  const el = $(id);
  if (el) el.textContent = text;
}

function setButtonsLoading(loading) {
  const start = $("btnStart");
  const stop  = $("btnStop");
  if (start) start.disabled = loading;
  if (stop)  stop.disabled  = loading;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatDateTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit"
    });
  } catch { return iso; }
}

function toggleTheme() {
  document.body.classList.toggle("light");
  const btn = $("themeToggle");
  if (btn) btn.textContent = document.body.classList.contains("light") ? "🌙" : "☀️";
}
