/* Date Night: app logic. The ideas live in ideas.js. */
(function () {
  "use strict";

  /* ---------- Setup ---------- */
  const TIERS = {
    in:   { emoji: "🛋️", label: "Stay in, upgraded" },
    ease: { emoji: "🌅", label: "Ease out" },
    send: { emoji: "🚀", label: "Full send" }
  };
  const WHEN = { day: "☀️ Daytime", night: "🌙 Evening", any: "🕐 Anytime" };
  const BUDGET = ["Free", "$", "$$", "$$$"];

  const FILTERS = [
    { key: "budget", label: "Budget", options: [[0, "Free"], [1, "$"], [2, "$$"], [3, "$$$"]] },
    { key: "energy", label: "Energy", options: [["lazy", "Lazy"], ["chill", "Chill"], ["active", "Active"]] },
    { key: "time",   label: "Time",   options: [["short", "Under 2 hrs"], ["half", "Half day"], ["full", "Full day"]] },
    { key: "tier",   label: "Setting", options: [["in", "Stay in"], ["ease", "Ease out"], ["send", "Full send"]] },
    { key: "when",   label: "Time of day", options: [["day", "☀️ Day"], ["night", "🌙 Night"]] }
  ];

  const MONTH = new Date().getMonth() + 1;
  const IDEAS = (Array.isArray(window.DATE_IDEAS) ? window.DATE_IDEAS : [])
    .filter(i => i && i.id && i.title && TIERS[i.tier]);

  /* ---------- Storage (on this phone only) ---------- */
  const store = {
    get(key, fallback) {
      try {
        const v = localStorage.getItem("dn." + key);
        return v ? JSON.parse(v) : fallback;
      } catch (e) { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem("dn." + key, JSON.stringify(value)); } catch (e) {}
    }
  };

  const state = {
    filters: store.get("filters", {}),
    saved: store.get("saved", []),
    history: store.get("history", []),
    current: null,
    recent: [],
    spinning: false
  };

  /* ---------- Helpers ---------- */
  const $ = sel => document.querySelector(sel);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const byId = id => IDEAS.find(i => i.id === id);
  const inSeason = i => !i.months || i.months.includes(MONTH);

  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => t.classList.remove("show"), 2000);
  }

  /* ---------- Filtering & picking ---------- */
  function matches(idea) {
    if (!inSeason(idea)) return false;
    const f = state.filters;
    if (f.budget != null && idea.budget !== f.budget) return false;
    if (f.energy && idea.energy !== f.energy) return false;
    if (f.time && idea.time !== f.time) return false;
    if (f.tier && idea.tier !== f.tier) return false;
    if (f.when && idea.when !== "any" && idea.when !== f.when) return false;
    return true;
  }
  const pool = () => IDEAS.filter(matches);

  function weightOf(idea) {
    let w = 1;
    if (idea.months) w *= 2.5;                          // in-season specials show up more
    if (state.recent.includes(idea.id)) w *= 0.1;        // avoid repeats
    if (state.history.some(h => h.ideaId === idea.id)) w *= 0.6; // done before
    return w;
  }

  function pickFrom(list, excludeId) {
    const options = list.length > 1 ? list.filter(i => i.id !== excludeId) : list;
    const total = options.reduce((s, i) => s + weightOf(i), 0);
    let r = Math.random() * total;
    for (const i of options) {
      r -= weightOf(i);
      if (r <= 0) return i;
    }
    return options[options.length - 1];
  }

  /* ---------- Pick screen ---------- */
  function renderGreeting() {
    const d = new Date();
    const day = d.toLocaleDateString(undefined, { weekday: "long" });
    const h = d.getHours();
    const part = h < 12 ? "morning ☀️" : h < 17 ? "afternoon 🌤️" : "night 🌙";
    $("#greeting").textContent = `${day} ${part}`;
  }

  function renderFilters() {
    $("#filter-rows").innerHTML = FILTERS.map(f => `
      <div class="f-row">
        <div class="f-label">${f.label}</div>
        <div class="chips">
          ${f.options.map(([v, label]) => `
            <button class="chip ${state.filters[f.key] === v ? "on" : ""}"
              data-key="${f.key}" data-val='${JSON.stringify(v)}'>${label}</button>`).join("")}
        </div>
      </div>`).join("");
    const any = Object.values(state.filters).some(v => v != null);
    $("#clear-filters").hidden = !any;
    renderCount();
  }

  function renderCount() {
    const n = pool().length;
    const seasonal = pool().filter(i => i.months).length;
    const el = $("#pick-count");
    if (!IDEAS.length) {
      el.textContent = "⚠️ Couldn't read ideas.js (maybe a missing comma?)";
    } else if (n === 0) {
      el.textContent = "No ideas match all of those. Try removing a filter.";
    } else {
      el.textContent = `${n} idea${n === 1 ? "" : "s"} in the hat` +
        (seasonal ? ` · 🍂 ${seasonal} in season right now` : "");
    }
  }

  $("#filter-rows").addEventListener("click", e => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const key = chip.dataset.key;
    const val = JSON.parse(chip.dataset.val);
    state.filters[key] = state.filters[key] === val ? null : val;
    store.set("filters", state.filters);
    renderFilters();
  });

  $("#clear-filters").addEventListener("click", () => {
    state.filters = {};
    store.set("filters", state.filters);
    renderFilters();
  });

  $("#pick-btn").addEventListener("click", () => {
    const btn = $("#pick-btn");
    btn.classList.remove("rolling");
    void btn.offsetWidth; // restart the dice animation
    btn.classList.add("rolling");
    spin();
  });

  /* ---------- The idea card ---------- */
  function cardHTML(idea) {
    const t = TIERS[idea.tier];
    const tags = [];
    if (idea.months) tags.push(`<span class="tag season">🍂 In season</span>`);
    if (idea.age21) tags.push(`<span class="tag adult">🍺 21+</span>`);
    tags.push(`<span class="tag">${BUDGET[idea.budget] || ""}</span>`);
    tags.push(`<span class="tag">${esc(idea.energy)}</span>`);

    return `
      <span class="tier-badge">${t.emoji} ${t.label}</span>
      <h2 class="card-title">${esc(idea.title)}</h2>
      <p class="card-desc">${esc(idea.desc)}</p>
      <div class="meta">
        <div><small>Cost</small>${esc(idea.cost || BUDGET[idea.budget])}</div>
        <div><small>Takes</small>${esc(idea.duration || "")}</div>
        <div><small>Where</small>📍 ${esc(idea.area || "")}</div>
        <div><small>When</small>${WHEN[idea.when] || WHEN.any}</div>
      </div>
      <div class="tags">${tags.join("")}</div>
      ${idea.verify ? `<div class="verify-note">📞 This is a real place. Check that it's open (and the hours) before you go. Things change!</div>` : ""}
      ${idea.place ? `<button class="dir-btn" id="dir-btn">🧭 Get directions</button>` : ""}
    `;
  }

  function showIdea(idea, animate) {
    state.current = idea;
    state.recent = [idea.id, ...state.recent.filter(id => id !== idea.id)].slice(0, 8);
    const card = $("#card");
    card.className = "card" + (animate ? " landed" : "");
    card.dataset.tier = idea.tier;
    card.innerHTML = cardHTML(idea);
    updateSaveBtn();
    setActionsDisabled(false);
  }

  function emptyCard() {
    const card = $("#card");
    card.className = "card";
    card.dataset.tier = "ease";
    card.innerHTML = `
      <div class="empty">
        <span class="big">🤷</span>
        <p>Nothing matches all of those filters right now. Loosen one up and try again.</p>
        <button class="btn" id="empty-clear">Clear filters</button>
      </div>`;
    state.current = null;
    setActionsDisabled(true);
    $("#act-reroll").disabled = true;
  }

  function setActionsDisabled(off) {
    ["#act-reroll", "#act-save", "#act-done"].forEach(s => { $(s).disabled = off; });
  }

  function updateSaveBtn() {
    const saved = state.current && state.saved.includes(state.current.id);
    $("#act-save").innerHTML = saved ? "<span>❤️</span>Saved" : "<span>🤍</span>Save";
  }

  /* Slot-machine shuffle, then land on the pick */
  function spin() {
    if (state.spinning) return;
    openResult();
    const list = pool();
    if (!list.length) { emptyCard(); return; }

    const final = pickFrom(list, state.current && state.current.id);
    const card = $("#card");
    state.spinning = true;
    setActionsDisabled(true);

    let delay = 45;
    const step = () => {
      const fake = list[Math.floor(Math.random() * list.length)];
      card.className = "card spinning";
      card.dataset.tier = fake.tier;
      card.innerHTML = `
        <span class="tier-badge">${TIERS[fake.tier].emoji} Shuffling…</span>
        <h2 class="card-title">${esc(fake.title)}</h2>
        <p class="spin-hint">🎲 🎲 🎲</p>`;
      delay *= 1.13;
      if (delay < 300) {
        setTimeout(step, delay);
      } else {
        setTimeout(() => {
          state.spinning = false;
          showIdea(final, true);
        }, 260);
      }
    };
    step();
  }

  function openResult() {
    $("#result").hidden = false;
  }
  function closeResult() {
    if (state.spinning) return;
    $("#result").hidden = true;
  }

  $("#close-result").addEventListener("click", closeResult);
  $("#act-reroll").addEventListener("click", spin);

  $("#card").addEventListener("click", e => {
    if (e.target.closest("#dir-btn")) openDirections(state.current);
    if (e.target.closest("#empty-clear")) {
      state.filters = {};
      store.set("filters", state.filters);
      renderFilters();
      spin();
    }
  });

  $("#act-save").addEventListener("click", () => {
    const idea = state.current;
    if (!idea) return;
    if (state.saved.includes(idea.id)) {
      state.saved = state.saved.filter(id => id !== idea.id);
      toast("Removed from saved");
    } else {
      state.saved = [idea.id, ...state.saved];
      toast("Saved for later ❤️");
    }
    store.set("saved", state.saved);
    updateSaveBtn();
    renderSaved();
  });

  $("#act-done").addEventListener("click", () => {
    if (state.current) openLogSheet(state.current);
  });

  /* ---------- Bottom sheet ---------- */
  function openSheet(html) {
    $("#sheet").innerHTML = html;
    $("#sheet").hidden = false;
    $("#sheet-backdrop").hidden = false;
  }
  function closeSheet() {
    $("#sheet").hidden = true;
    $("#sheet-backdrop").hidden = true;
  }
  $("#sheet-backdrop").addEventListener("click", closeSheet);

  function openDirections(idea) {
    if (!idea || !idea.place) return;
    const q = encodeURIComponent(idea.place);
    openSheet(`
      <h2>🧭 ${esc(idea.title)}</h2>
      <p class="sub">${esc(idea.place)}</p>
      <a class="sheet-btn primary" href="https://maps.apple.com/?q=${q}" target="_blank" rel="noopener">Open in Apple Maps</a>
      <a class="sheet-btn" href="https://www.google.com/maps/search/?api=1&query=${q}" target="_blank" rel="noopener">Open in Google Maps</a>
      <button class="sheet-btn" data-close>Cancel</button>
    `);
  }

  function openLogSheet(idea) {
    let rating = 0;
    openSheet(`
      <h2>🎉 You did it!</h2>
      <p class="sub">${esc(idea.title)}. How was it?</p>
      <div class="rating" id="rating">
        ${[1, 2, 3, 4, 5].map(n => `<button data-r="${n}" aria-label="${n} of 5">❤️</button>`).join("")}
      </div>
      <label for="note">A note for future you (optional)</label>
      <textarea id="note" maxlength="280" placeholder="Best part? Funniest moment?"></textarea>
      <button class="sheet-btn primary" id="log-save" disabled>Save to history</button>
      <button class="sheet-btn" data-close>Cancel</button>
    `);
    $("#rating").addEventListener("click", e => {
      const b = e.target.closest("button");
      if (!b) return;
      rating = Number(b.dataset.r);
      [...$("#rating").children].forEach((el, i) => el.classList.toggle("on", i < rating));
      $("#log-save").disabled = false;
    });
    $("#log-save").addEventListener("click", () => {
      state.history.unshift({
        id: Date.now(),
        ideaId: idea.id,
        title: idea.title,
        tier: idea.tier,
        area: idea.area || "",
        rating,
        note: $("#note").value.trim(),
        at: new Date().toISOString()
      });
      store.set("history", state.history);
      closeSheet();
      $("#result").hidden = true;
      renderHistory();
      switchTab("history");
      toast(idea.tier === "in" ? "Logged! Cozy night counts ❤️" : "Logged! That's an out-date 🔥");
    });
  }

  $("#sheet").addEventListener("click", e => {
    if (e.target.closest("[data-close]")) closeSheet();
    if (e.target.closest("a.sheet-btn")) setTimeout(closeSheet, 300);
  });

  /* ---------- Saved screen ---------- */
  function renderSaved() {
    const ideas = state.saved.map(byId).filter(Boolean);
    $("#saved-list").innerHTML = ideas.length ? ideas.map(i => `
      <div class="row">
        <button class="row-ic" data-open="${esc(i.id)}">${TIERS[i.tier].emoji}</button>
        <button class="row-main" data-open="${esc(i.id)}" style="text-align:left">
          <p class="row-title">${esc(i.title)}</p>
          <p class="row-sub">📍 ${esc(i.area)} · ${esc(i.cost || BUDGET[i.budget])}</p>
        </button>
        <button class="row-x" data-unsave="${esc(i.id)}" aria-label="Remove">✕</button>
      </div>`).join("") : `
      <div class="empty">
        <span class="big">❤️</span>
        <p>Nothing saved yet. When an idea looks good but tonight's not the night, tap <b>Save</b>.</p>
      </div>`;
  }

  $("#saved-list").addEventListener("click", e => {
    const open = e.target.closest("[data-open]");
    const unsave = e.target.closest("[data-unsave]");
    if (unsave) {
      state.saved = state.saved.filter(id => id !== unsave.dataset.unsave);
      store.set("saved", state.saved);
      renderSaved();
    } else if (open) {
      const idea = byId(open.dataset.open);
      if (idea) { openResult(); showIdea(idea, true); }
    }
  });

  /* ---------- History screen ---------- */
  function weekKey(date) {
    const d = new Date(date);
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); // back to Monday
    return d.getTime();
  }

  // Weeks in a row (Mon–Sun) with at least one out-date
  function weekStreak(outDates) {
    const weeks = new Set(outDates.map(h => weekKey(h.at)));
    const monday = new Date(weekKey(new Date()));
    if (!weeks.has(monday.getTime())) monday.setDate(monday.getDate() - 7); // this week isn't over yet
    let streak = 0;
    while (weeks.has(monday.getTime())) {
      streak++;
      monday.setDate(monday.getDate() - 7);
    }
    return streak;
  }

  function renderHistory() {
    const now = new Date();
    const thisMonth = state.history.filter(h => {
      const d = new Date(h.at);
      return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
    });
    const outMonth = thisMonth.filter(h => h.tier !== "in").length;
    const streak = weekStreak(state.history.filter(h => h.tier !== "in"));

    $("#stats").innerHTML = `
      <div class="stat hero"><b>${outMonth}</b><span>Out this month</span></div>
      <div class="stat"><b>${thisMonth.length}</b><span>Dates this month</span></div>
      <div class="stat green"><b>${streak}</b><span>Week streak${streak ? " 🔥" : ""}</span></div>`;

    $("#cheer").textContent =
      outMonth === 0 ? "No pressure. Even one sunset counts. 🌅" :
      outMonth === 1 ? "One out-date this month. Look at you two. ❤️" :
      outMonth <= 3  ? "Getting out more already! 🔥" :
                       "Okay, social butterflies. 🦋";

    $("#history-list").innerHTML = state.history.length ? state.history.map(h => `
      <div class="row">
        <div class="row-ic">${(TIERS[h.tier] || TIERS.ease).emoji}</div>
        <div class="row-main">
          <p class="row-title">${esc(h.title)}</p>
          <p class="row-sub">${new Date(h.at).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
            · <span class="hearts">${"❤️".repeat(h.rating)}</span></p>
          ${h.note ? `<p class="row-note">“${esc(h.note)}”</p>` : ""}
        </div>
        <button class="row-x" data-del="${h.id}" aria-label="Delete">✕</button>
      </div>`).join("") : `
      <div class="empty">
        <span class="big">📖</span>
        <p>No dates logged yet. Pick one, go do it, then tap <b>We did it</b>.</p>
      </div>`;
  }

  $("#history-list").addEventListener("click", e => {
    const del = e.target.closest("[data-del]");
    if (!del) return;
    const entry = state.history.find(h => String(h.id) === del.dataset.del);
    if (!entry) return;
    openSheet(`
      <h2>Delete this date?</h2>
      <p class="sub">${esc(entry.title)} will be removed from your history.</p>
      <button class="sheet-btn danger" id="confirm-del">Delete</button>
      <button class="sheet-btn" data-close>Keep it</button>
    `);
    $("#confirm-del").addEventListener("click", () => {
      state.history = state.history.filter(h => h !== entry);
      store.set("history", state.history);
      closeSheet();
      renderHistory();
    });
  });

  /* ---------- Tabs ---------- */
  function switchTab(name) {
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
    ["pick", "saved", "history"].forEach(s => { $("#screen-" + s).hidden = s !== name; });
  }
  document.querySelector(".tabbar").addEventListener("click", e => {
    const tab = e.target.closest(".tab");
    if (tab) switchTab(tab.dataset.tab);
  });

  /* ---------- Start ---------- */
  renderGreeting();
  renderFilters();
  renderSaved();
  renderHistory();

  if ("serviceWorker" in navigator && location.protocol === "https:") {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
})();
