/* ---------- STATE ---------- */

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 2;
const ZOOM_STEP = 0.25;
const ZOOM_FIT = 1;

const state = {
  items: [],
  filtered: [],
  status: "published",
  currentIndex: -1,
  detailTab: "preview",
  slideIndex: 0,
  zoom: 1,
  pan: { x: 0, y: 0 },
};

/* ---------- DOM REFS ---------- */

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const dom = {
  grid: $("#grid"),
  skeleton: $("#skeleton"),
  summary: $("#summary"),
  search: $("#search"),
  searchClear: $("#search-clear"),
  typeFilter: $("#type-filter"),
  brandFilter: $("#brand-filter"),
  compatFilter: $("#compat-filter"),
  countPublished: $("#count-published"),
  countDraft: $("#count-draft"),
  backdrop: $("#backdrop"),
  modal: $("#modal"),
  modalClose: $("#modal-close"),
  modalTitle: $("#modal-title"),
  modalVisual: $("#modal-visual"),
  modalId: $("#modal-id"),
  subTabs: $("#sub-tabs"),
  panelPreview: $("#panel-preview"),
  panelInfo: $("#panel-info"),
  panelCompat: $("#panel-compat"),
  navPrev: $("#nav-prev"),
  navNext: $("#nav-next"),
  copyId: $("#copy-id"),
  copyPrompt: $("#copy-prompt"),
  toastStack: $("#toast-stack"),
  modalManage: $("#modal-manage"),
};

/* ---------- URL RESOLUTION ---------- */

function resolvePath(path) {
  if (!path) return null;
  if (path.startsWith("http")) return path;
  return "../../" + path;
}

function resolveImageUrl(item) {
  if (item.images?.length) return resolvePath(item.images[0].path);
  return null;
}

/* ---------- FILTERING ---------- */

function statusMatches(item) {
  return state.status === "published"
    ? item.status === "published"
    : ["staging", "qa"].includes(item.status);
}

function compatMatches(item) {
  const target = dom.compatFilter.value;
  if (!target) return true;
  return ["supported", "hybrid", "raster"].includes(item.compatibility?.[target]);
}

function filterItems() {
  const term = dom.search.value.trim().toLowerCase();
  state.filtered = state.items.filter((item) => {
    if (!statusMatches(item)) return false;
    if (dom.typeFilter.value && item.type !== dom.typeFilter.value) return false;
    if (dom.brandFilter.value && item.brand !== dom.brandFilter.value) return false;
    if (!compatMatches(item)) return false;
    if (term) {
      const hay = [item.id, item.name, item.type, item.brand, ...(item.intent || []), ...(item.tags || [])]
        .filter(Boolean).join(" ").toLowerCase();
      if (!hay.includes(term)) return false;
    }
    return true;
  });
}

/* ---------- SKELETON ---------- */

function showSkeleton() {
  let html = "";
  for (let i = 0; i < 8; i++) {
    html += `<div class="skeleton-tile"><div class="skeleton-preview"></div><div class="skeleton-meta"><div class="skeleton-line"></div><div class="skeleton-line"></div></div></div>`;
  }
  dom.skeleton.innerHTML = html;
  dom.skeleton.style.display = "";
  dom.grid.style.display = "none";
}

function hideSkeleton() {
  dom.skeleton.style.display = "none";
  dom.grid.style.display = "";
}

/* ---------- RENDER GALLERY ---------- */

function render() {
  filterItems();
  dom.summary.textContent = state.filtered.length + " item" + (state.filtered.length === 1 ? "" : "s");
  dom.grid.replaceChildren();

  if (state.filtered.length === 0) {
    dom.grid.innerHTML = `
      <div class="empty-state">
        <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="8" y="8" width="48" height="48" rx="8"/>
          <path d="M24 32h16M32 24v16" opacity=".4"/>
        </svg>
        <p>No items match your filters.</p>
        <button id="clear-filters">Clear all filters</button>
      </div>`;
    const btn = $("#clear-filters");
    if (btn) btn.addEventListener("click", clearFilters);
    return;
  }

  const frag = document.createDocumentFragment();
  state.filtered.forEach((item, idx) => frag.appendChild(createTile(item, idx)));
  dom.grid.appendChild(frag);
}

function createTile(item, idx) {
  const tile = document.createElement("article");
  tile.className = "tile";
  tile.tabIndex = 0;
  tile.dataset.index = idx;

  const imgUrl = resolveImageUrl(item);
  const statusClass = item.status === "published" ? "published" : "draft";
  const statusLabel = item.status === "published" ? "Published" : "Draft";

  tile.innerHTML = `
    <div class="tile-preview">
      ${imgUrl
        ? `<img src="${imgUrl}" alt="${escAttr(item.name)}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display=''">`
        : ""}
      <div class="fallback" ${imgUrl ? 'style="display:none"' : ""}>${escHtml(item.type)}</div>
    </div>
    <div class="tile-meta">
      <div class="tile-name" title="${escAttr(item.name)}">${escHtml(item.name)}</div>
      <div class="tile-info">
        <span>${escHtml(item.type)}</span>
        <span class="status-dot ${statusClass}">${statusLabel}</span>
      </div>
    </div>`;

  tile.addEventListener("click", () => openModal(idx));
  tile.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openModal(idx); }
  });

  return tile;
}

/* ---------- DETAIL MODAL ---------- */

function openModal(idx) {
  state.currentIndex = idx;
  state.detailTab = "preview";
  state.slideIndex = 0;
  resetZoom();
  renderModal();
  dom.backdrop.classList.add("is-open");
  dom.modal.classList.add("is-open");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  dom.backdrop.classList.remove("is-open");
  dom.modal.classList.remove("is-open");
  document.body.style.overflow = "";
  state.currentIndex = -1;
}

function navigateModal(dir) {
  const next = state.currentIndex + dir;
  if (next < 0 || next >= state.filtered.length) return;
  state.currentIndex = next;
  state.detailTab = "preview";
  state.slideIndex = 0;
  resetZoom();
  renderModal();
  dom.modal.scrollTop = 0;
}

function renderModal() {
  const item = state.filtered[state.currentIndex];
  if (!item) return;

  dom.navPrev.disabled = state.currentIndex === 0;
  dom.navNext.disabled = state.currentIndex === state.filtered.length - 1;
  dom.modalTitle.textContent = item.name;

  const images = item.images || [];
  const hasMultipleImages = images.length > 1;
  const hasImage = images.length > 0;

  let visualHtml = "";

  if (hasImage) {
    const currentImg = images[state.slideIndex] || images[0];
    const imgSrc = resolvePath(currentImg.path);

    visualHtml += `<div class="carousel-container is-zoomable">`;
    visualHtml += `<img src="${imgSrc}" alt="${escAttr(item.name)}" draggable="false" onerror="this.style.display='none'">`;

    // zoom controls
    visualHtml += `
      <div class="zoom-controls" role="group" aria-label="Zoom controls">
        <button class="zoom-btn" id="zoom-out" aria-label="Zoom out">&minus;</button>
        <span class="zoom-level" id="zoom-level">100%</span>
        <button class="zoom-btn" id="zoom-in" aria-label="Zoom in">+</button>
        <button class="zoom-btn zoom-fit" id="zoom-fit" aria-label="Fit to frame">Fit</button>
      </div>`;

    if (hasMultipleImages) {
      visualHtml += `
        <button class="carousel-btn carousel-prev" id="slide-prev" ${state.slideIndex === 0 ? "disabled" : ""} aria-label="Previous image (Left arrow)">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 3L5 8l5 5"/></svg>
        </button>
        <button class="carousel-btn carousel-next" id="slide-next" ${state.slideIndex >= images.length - 1 ? "disabled" : ""} aria-label="Next image (Right arrow)">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3l5 5-5 5"/></svg>
        </button>
        <div class="carousel-indicators">
          ${images.map((img, i) =>
            `<button class="carousel-dot ${i === state.slideIndex ? "is-active" : ""}" data-slide="${i}" title="${escAttr(img.label)}" aria-label="${escAttr(img.label)}"></button>`
          ).join("")}
        </div>
        <div class="carousel-label">${escHtml(currentImg.label)} (${state.slideIndex + 1}/${images.length})</div>`;
    }

    visualHtml += `</div>`;
  } else {
    visualHtml += `<div class="carousel-container">`;
    visualHtml += `<div class="fallback">${escHtml(item.type)}</div>`;
    visualHtml += `</div>`;
  }

  dom.modalVisual.innerHTML = visualHtml;

  if (hasImage) wireZoom();

  if (hasMultipleImages) {
    const prevBtn = $("#slide-prev");
    const nextBtn = $("#slide-next");
    if (prevBtn) prevBtn.addEventListener("click", (e) => { e.stopPropagation(); changeSlide(-1); });
    if (nextBtn) nextBtn.addEventListener("click", (e) => { e.stopPropagation(); changeSlide(1); });
    dom.modalVisual.querySelectorAll(".carousel-dot").forEach((dot) => {
      dot.addEventListener("click", (e) => {
        e.stopPropagation();
        if (parseInt(dot.dataset.slide) === state.slideIndex) return;
        state.slideIndex = parseInt(dot.dataset.slide);
        resetZoom();
        renderModal();
      });
    });
  }

  const statusClass = item.status === "published" ? "published" : "draft";
  const statusLabel = item.status === "published" ? "Published" : "Draft";
  dom.modalId.innerHTML = `
    <span>${escHtml(item.id)} &middot; v${escHtml(item.version)}</span>
    <span class="status-dot ${statusClass}">${statusLabel}</span>`;

  renderInfoPanel(item);
  renderCompatPanel(item);
  renderManageBar(item);
  setActiveTab(state.detailTab);
}

function setActiveTab(id) {
  state.detailTab = id;
  dom.subTabs.querySelectorAll(".sub-tab").forEach((btn) => {
    const on = btn.dataset.tab === id;
    btn.classList.toggle("is-active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  [dom.panelPreview, dom.panelInfo, dom.panelCompat].forEach((p) => p.classList.remove("is-active"));
  const panel = $(`#panel-${id}`);
  if (panel) panel.classList.add("is-active");
}

function changeSlide(dir) {
  const item = state.filtered[state.currentIndex];
  if (!item || !item.images?.length) return;
  const next = state.slideIndex + dir;
  if (next < 0 || next >= item.images.length) return;
  state.slideIndex = next;
  resetZoom();
  renderModal();
}

/* ---------- ZOOM + PAN ---------- */

function currentImageEl() {
  return dom.modalVisual.querySelector("img");
}

function resetZoom() {
  state.zoom = 1;
  state.pan.x = 0;
  state.pan.y = 0;
}

function applyZoom() {
  const img = currentImageEl();
  if (!img) return;
  img.style.transform =
    `translate(${state.pan.x}px, ${state.pan.y}px) scale(${state.zoom})`;
  const container = img.closest(".carousel-container");
  if (container) container.classList.toggle("is-zoomed", state.zoom > 1);
}

function clampPan() {
  const img = currentImageEl();
  if (!img) return;
  const rect = img.getBoundingClientRect();
  // rect already reflects the scaled size; bound so we can't drag past the edge
  const maxX = Math.max(0, (rect.width - rect.width / state.zoom) / 2);
  const maxY = Math.max(0, (rect.height - rect.height / state.zoom) / 2);
  state.pan.x = Math.max(-maxX, Math.min(maxX, state.pan.x));
  state.pan.y = Math.max(-maxY, Math.min(maxY, state.pan.y));
}

function setZoom(z) {
  state.zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));
  if (state.zoom <= ZOOM_FIT) { state.pan.x = 0; state.pan.y = 0; }
  else clampPan();
  applyZoom();
  updateZoomUI();
}

function zoomBy(delta) { setZoom(state.zoom + delta); }

function updateZoomUI() {
  const level = $("#zoom-level");
  if (level) level.textContent = Math.round(state.zoom * 100) + "%";
  const out = $("#zoom-out");
  const inn = $("#zoom-in");
  if (out) out.disabled = state.zoom <= ZOOM_MIN;
  if (inn) inn.disabled = state.zoom >= ZOOM_MAX;
}

function wireZoom() {
  const container = dom.modalVisual.querySelector(".carousel-container");
  const img = currentImageEl();
  if (!container || !img) return;

  applyZoom();
  updateZoomUI();

  const out = $("#zoom-out");
  const inn = $("#zoom-in");
  const fit = $("#zoom-fit");
  if (out) out.addEventListener("click", (e) => { e.stopPropagation(); zoomBy(-ZOOM_STEP); });
  if (inn) inn.addEventListener("click", (e) => { e.stopPropagation(); zoomBy(ZOOM_STEP); });
  if (fit) fit.addEventListener("click", (e) => { e.stopPropagation(); setZoom(ZOOM_FIT); });

  // click image to zoom in one step (when not at max); ignore after a drag
  img.addEventListener("click", (e) => {
    if (img.dataset.dragged === "1") { img.dataset.dragged = "0"; return; }
    if (state.zoom < ZOOM_MAX) { e.stopPropagation(); zoomBy(ZOOM_STEP); }
  });

  // drag to pan when zoomed
  let dragging = false, startX = 0, startY = 0, baseX = 0, baseY = 0, moved = false;
  container.addEventListener("pointerdown", (e) => {
    // don't start a drag (and capture the pointer) when pressing a control,
    // otherwise the button's click is swallowed and zoom-out/fit stops working
    if (e.target.closest(".zoom-controls, .carousel-btn, .carousel-indicators")) return;
    if (state.zoom <= ZOOM_FIT) return;
    dragging = true; moved = false;
    startX = e.clientX; startY = e.clientY;
    baseX = state.pan.x; baseY = state.pan.y;
    container.classList.add("is-grabbing");
    container.setPointerCapture(e.pointerId);
  });
  container.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    state.pan.x = baseX + (e.clientX - startX);
    state.pan.y = baseY + (e.clientY - startY);
    if (Math.abs(e.clientX - startX) > 3 || Math.abs(e.clientY - startY) > 3) {
      moved = true;
      img.dataset.dragged = "1";
    }
    clampPan();
    applyZoom();
  });
  const endDrag = (e) => {
    if (!dragging) return;
    dragging = false;
    container.classList.remove("is-grabbing");
    try { container.releasePointerCapture(e.pointerId); } catch (_) {}
  };
  container.addEventListener("pointerup", endDrag);
  container.addEventListener("pointercancel", endDrag);
}

/* ---------- INFO PANEL ---------- */

function renderInfoPanel(item) {
  let html = "";

  if (item.brand) html += infoRow("Brand", escHtml(item.brand));
  if (item.intent?.length) html += infoRow("Intent", `<div class="pills">${item.intent.map(pill).join("")}</div>`);
  if (item.tags?.length) html += infoRow("Tags", `<div class="pills">${item.tags.map(pill).join("")}</div>`);

  if (item.source) {
    const src = typeof item.source === "string" ? item.source : (item.source.path || JSON.stringify(item.source));
    html += infoRow("Source", `<span style="font-family:var(--mono);font-size:11px;word-break:break-all">${escHtml(String(src))}</span>`);
  }

  if (item.variants?.length) html += infoRow("Variants", `<div class="pills">${item.variants.map(pill).join("")}</div>`);
  if (item.limitations?.length) html += infoRow("Limitations", `<ul class="limitations-list">${item.limitations.map((l) => `<li>${escHtml(l)}</li>`).join("")}</ul>`);

  const imageCount = item.images?.length || 0;
  if (imageCount > 1) html += infoRow("Images", imageCount + " visuals available (use the carousel or \u2190/\u2192)");

  dom.panelInfo.innerHTML = html || '<p style="color:var(--muted);font-size:13px">No additional info.</p>';
}

function infoRow(label, value) {
  return `<div class="info-row"><span class="info-label">${label}</span><div class="info-value">${value}</div></div>`;
}

function pill(text) {
  return `<span class="pill">${escHtml(text)}</span>`;
}

/* ---------- COMPAT PANEL ---------- */

function renderCompatPanel(item) {
  const targets = ["html", "pptx", "pdf", "canva"];
  const compat = item.compatibility || {};

  dom.panelCompat.innerHTML = `<div class="compat-grid">${targets.map((t) => {
    const val = compat[t] || "untested";
    const icon = compatIcon(val);
    const cls = "compat-" + (val === "supported" ? "supported" : val === "hybrid" ? "hybrid" : val === "raster" ? "raster" : "untested");
    return `<div class="compat-cell ${cls}">
      <div class="compat-icon">${icon}</div>
      <div class="compat-label">${t}</div>
      <div class="compat-status">${val}</div>
    </div>`;
  }).join("")}</div>`;
}

function compatIcon(val) {
  if (val === "supported") return '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 10l3.5 3.5L15 7"/></svg>';
  if (val === "hybrid") return '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="10" cy="10" r="6"/><path d="M10 4a6 6 0 010 12" fill="currentColor" opacity=".3"/></svg>';
  if (val === "raster") return '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="5" width="14" height="10" rx="2"/><circle cx="7" cy="9" r="1.5" fill="currentColor"/><path d="M3 13l4-3 3 2 4-4 3 3"/></svg>';
  return '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 10h8"/></svg>';
}

/* ---------- FILTER CONTROLS ---------- */

function addOptions(select, values) {
  const current = select.value;
  // Keep the first ("All …") option; rebuild the rest so reloads don't duplicate.
  while (select.options.length > 1) select.remove(1);
  [...new Set(values.filter(Boolean))].sort().forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    select.appendChild(opt);
  });
  if ([...select.options].some((o) => o.value === current)) select.value = current;
}

function updateFilterStyles() {
  [dom.typeFilter, dom.brandFilter, dom.compatFilter].forEach((sel) => {
    sel.classList.toggle("has-value", !!sel.value);
  });
}

function clearFilters() {
  dom.search.value = "";
  dom.typeFilter.value = "";
  dom.brandFilter.value = "";
  dom.compatFilter.value = "";
  updateFilterStyles();
  render();
}

/* ---------- EVENTS ---------- */

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => { t.classList.remove("is-active"); t.setAttribute("aria-selected", "false"); });
    tab.classList.add("is-active");
    tab.setAttribute("aria-selected", "true");
    state.status = tab.dataset.status;
    render();
  });
});

[dom.search, dom.typeFilter, dom.brandFilter, dom.compatFilter].forEach((el) => {
  el.addEventListener("input", () => { updateFilterStyles(); render(); });
});

dom.searchClear.addEventListener("click", () => {
  dom.search.value = "";
  render();
});

dom.modalClose.addEventListener("click", closeModal);
dom.backdrop.addEventListener("click", closeModal);
dom.navPrev.addEventListener("click", () => navigateModal(-1));
dom.navNext.addEventListener("click", () => navigateModal(1));

dom.subTabs.querySelectorAll(".sub-tab").forEach((btn) => {
  btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
});

dom.copyId.addEventListener("click", () => {
  const item = state.filtered[state.currentIndex];
  if (!item) return;
  copyText(item.id, dom.copyId).then(
    () => toast(`Copied id: <code>${escHtml(item.id)}</code>`),
    () => toast(`Copy failed. Component id: ${escHtml(item.id)}`, "error")
  );
});

dom.copyPrompt.addEventListener("click", () => {
  const item = state.filtered[state.currentIndex];
  if (!item) return;
  const prompt = buildPrompt(item);
  copyText(prompt, dom.copyPrompt).then(
    () => toast("Copied prompt &mdash; paste it into the conversation to use this component."),
    () => toast("Copy failed.", "error")
  );
});

document.addEventListener("keydown", (e) => {
  if (state.currentIndex === -1) return;
  if (document.querySelector(".confirm-overlay")) return;
  switch (e.key) {
    case "Escape": closeModal(); break;
    case "ArrowLeft":
      if (e.shiftKey) { e.preventDefault(); navigateModal(-1); } else changeSlide(-1);
      break;
    case "ArrowRight":
      if (e.shiftKey) { e.preventDefault(); navigateModal(1); } else changeSlide(1);
      break;
    case "+": case "=": e.preventDefault(); zoomBy(ZOOM_STEP); break;
    case "-": case "_": e.preventDefault(); zoomBy(-ZOOM_STEP); break;
    case "0": e.preventDefault(); setZoom(ZOOM_FIT); break;
  }
});

/* ---------- MANAGE (preview / publish / delete) ---------- */

const MANAGE_ICONS = {
  preview:
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ' +
    'stroke-linecap="round" stroke-linejoin="round"><path d="M8 2.5l1.4 3 3.1.4-2.3 2.1.6 3L8 9.6 5.2 11l.6-3L3.5 5.9l3.1-.4z"/></svg>',
  publish:
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ' +
    'stroke-linecap="round" stroke-linejoin="round"><path d="M8 11V3M5 6l3-3 3 3M3.5 13h9"/></svg>',
  trash:
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ' +
    'stroke-linecap="round" stroke-linejoin="round"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M5 4.5l.5 8h5l.5-8"/></svg>',
};

function manageBtn(label, iconKey, cls) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = cls;
  b.innerHTML = MANAGE_ICONS[iconKey] + "<span>" + escHtml(label) + "</span>";
  return b;
}

function renderManageBar(item) {
  const bar = dom.modalManage;
  if (!bar) return;
  bar.innerHTML = "";
  const isDraft = item.status !== "published";

  if (isDraft) {
    const readiness = item.publish_readiness || { ready: true, blockers: [] };

    const pub = manageBtn("Publish", "publish", "manage-btn manage-btn-primary");
    if (!readiness.ready) {
      pub.disabled = true;
      pub.title = "This extraction is incomplete:\n- " + (readiness.blockers || []).join("\n- ");
    } else {
      pub.title = "Add this to the published library";
    }
    pub.addEventListener("click", () => onPublish(item, pub));
    bar.appendChild(pub);

    const del = manageBtn("Delete draft", "trash", "manage-btn manage-btn-danger");
    del.addEventListener("click", () => onDelete(item, del));
    bar.appendChild(del);

    if (!readiness.ready && (readiness.blockers || []).length) {
      const note = document.createElement("div");
      note.className = "manage-note";
      note.textContent = "Can't publish yet: " + readiness.blockers.join("; ");
      bar.appendChild(note);
    }
  } else {
    if (item.deletable === false) return; // canonical/protected asset: no actions
    const del = manageBtn("Delete", "trash", "manage-btn manage-btn-danger");
    del.addEventListener("click", () => onDelete(item, del));
    bar.appendChild(del);
  }
}

function busy(btn, on) {
  if (!btn) return;
  btn.disabled = on;
  btn.classList.toggle("is-busy", on);
}

function api(path, body) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(
    async (r) => {
      let data = {};
      try { data = await r.json(); } catch (_) {}
      if (r.status === 404 && !data.error) {
        throw new Error("Control server not running. Start it with: python3 slide-system/catalog/catalog_server.py");
      }
      if (!r.ok || !data.ok) {
        throw new Error(data.error || ("Request failed (" + r.status + ")"));
      }
      return data;
    },
    () => {
      throw new Error("Control server not reachable. Start it with: python3 slide-system/catalog/catalog_server.py");
    }
  );
}

function onPublish(item, btn) {
  // One click for non-technical users: publish straight away, no dialog.
  // The server authors the preview, records approval, and promotes the item.
  busy(btn, true);
  toast(`Publishing <code>${escHtml(item.id)}</code>&hellip;`);
  api("/api/publish", { id: item.id })
    .then(() => {
      closeModal();
      return loadData().then(() => toast(`Published <code>${escHtml(item.id)}</code> to the library.`));
    })
    .catch((e) => toast(escHtml(e.message), "error"))
    .finally(() => busy(btn, false));
}

function onDelete(item, btn) {
  const isDraft = item.status !== "published";
  confirmDialog({
    title: isDraft ? "Delete draft permanently?" : "Delete published item?",
    body: isDraft
      ? `Draft <strong>${escHtml(item.name)}</strong> lives in gitignored <code>outputs/</code> and <strong>cannot be recovered from git</strong>. This permanently removes its extraction folder.`
      : `This removes <strong>${escHtml(item.name)}</strong> from the library folder and registry. It is git-tracked, so you can restore it with <code>git checkout</code>.`,
    confirmLabel: isDraft ? "Delete forever" : "Delete",
    danger: true,
    requireType: isDraft ? "DELETE" : null,
  }).then((ok) => {
    if (!ok) return;
    busy(btn, true);
    api("/api/delete", { id: item.id, status: item.status })
      .then(() => {
        closeModal();
        return loadData().then(() => toast(`Deleted <code>${escHtml(item.id)}</code>.`));
      })
      .catch((e) => toast(escHtml(e.message), "error"))
      .finally(() => busy(btn, false));
  });
}

function confirmDialog(opts) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "confirm-overlay";
    const dangerCls = opts.danger ? " is-danger" : "";
    const typeGate = opts.requireType
      ? `<label class="confirm-type">Type <b>${escHtml(opts.requireType)}</b> to confirm
           <input type="text" class="confirm-type-input" autocomplete="off" spellcheck="false"></label>`
      : "";
    overlay.innerHTML = `
      <div class="confirm-box${dangerCls}" role="alertdialog" aria-modal="true" aria-label="${escAttr(opts.title)}">
        <h3 class="confirm-title">${escHtml(opts.title)}</h3>
        <p class="confirm-body">${opts.body}</p>
        ${typeGate}
        <div class="confirm-actions">
          <button class="confirm-cancel" type="button">Cancel</button>
          <button class="confirm-ok${dangerCls}" type="button">${escHtml(opts.confirmLabel || "Confirm")}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add("is-open"));

    const okBtn = overlay.querySelector(".confirm-ok");
    const cancelBtn = overlay.querySelector(".confirm-cancel");
    const input = overlay.querySelector(".confirm-type-input");

    function close(result) {
      overlay.classList.remove("is-open");
      setTimeout(() => overlay.remove(), 180);
      document.removeEventListener("keydown", onKey, true);
      resolve(result);
    }
    if (input) {
      okBtn.disabled = true;
      input.addEventListener("input", () => {
        okBtn.disabled = input.value.trim() !== opts.requireType;
      });
      setTimeout(() => input.focus(), 60);
    }
    okBtn.addEventListener("click", () => { if (!okBtn.disabled) close(true); });
    cancelBtn.addEventListener("click", () => close(false));
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(false); });
    function onKey(e) {
      if (e.key === "Escape") { e.stopPropagation(); close(false); }
      else if (e.key === "Enter" && !okBtn.disabled && document.activeElement !== cancelBtn) {
        e.stopPropagation(); close(true);
      }
    }
    document.addEventListener("keydown", onKey, true);
  });
}

/* ---------- COPY + PROMPT + TOAST ---------- */

function buildPrompt(item) {
  const label = item.name && item.name !== item.id ? `"${item.name}" ` : "";
  const where = item.status === "published" ? "published " : "";
  return `Use the ${where}${item.type || "visual"} component ${label}(${item.id}) ` +
    `from the SUN.STUDIO visual library.`;
}

const COPIED_HTML =
  '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" ' +
  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8.5l3 3 6-7"/></svg>Copied';

function copyText(text, btn) {
  return clipboardWrite(text).then(() => {
    if (btn) markCopied(btn);
  });
}

function markCopied(btn) {
  if (btn.dataset.copying === "1") return;
  btn.dataset.copying = "1";
  btn.dataset.label = btn.innerHTML;
  btn.classList.add("is-copied");
  btn.innerHTML = COPIED_HTML;
  setTimeout(() => {
    btn.classList.remove("is-copied");
    btn.innerHTML = btn.dataset.label;
    delete btn.dataset.label;
    btn.dataset.copying = "0";
  }, 1600);
}

function clipboardWrite(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text).catch(() => legacyCopy(text));
  }
  return legacyCopy(text);
}

function legacyCopy(text) {
  return new Promise((resolve, reject) => {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "absolute";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      ok ? resolve() : reject(new Error("execCommand failed"));
    } catch (err) { reject(err); }
  });
}

/* ---------- TOAST STACK ---------- */

const TOAST_MAX = 3;
const TOAST_DURATION = 4000;
const TOAST_EXIT_MS = 320;
const toasts = []; // newest first: { el, timer }

const TOAST_ICONS = {
  success:
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" ' +
    'stroke-linecap="round" stroke-linejoin="round"><path d="M5 10.5l3.5 3.5L15 6.5"/></svg>',
  error:
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" ' +
    'stroke-linecap="round" stroke-linejoin="round"><path d="M10 6v5M10 14h.01"/></svg>',
};

const TOAST_CLOSE_ICON =
  '<svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" ' +
  'stroke-linecap="round"><path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/></svg>';

function toast(html, type) {
  const kind = type === "error" ? "error" : "success";
  const el = document.createElement("div");
  el.className = "toast-item is-" + kind;
  el.innerHTML =
    '<span class="toast-icon">' + (TOAST_ICONS[kind] || "") + "</span>" +
    '<span class="toast-msg">' + html + "</span>" +
    '<button class="toast-x" type="button" aria-label="Dismiss">' + TOAST_CLOSE_ICON + "</button>";

  el.querySelector(".toast-x").addEventListener("click", () => dismissToast(el));
  // pause auto-dismiss while pointer is over the stack item
  el.addEventListener("pointerenter", () => pauseToast(el));
  el.addEventListener("pointerleave", () => resumeToast(el));

  dom.toastStack.appendChild(el);
  const entry = { el, timer: null, remaining: TOAST_DURATION, startedAt: 0 };
  toasts.unshift(entry);

  // entrance: next frame, switch from pre-state to stacked position
  requestAnimationFrame(() => {
    el.classList.add("is-in");
    restackToasts();
  });
  restackToasts();
  startToastTimer(entry);

  // trim overflow (oldest first)
  while (toasts.length > TOAST_MAX) dismissToast(toasts[toasts.length - 1].el);

  return el;
}

function startToastTimer(entry) {
  entry.startedAt = Date.now();
  entry.timer = setTimeout(() => dismissToast(entry.el), entry.remaining);
}

function pauseToast(el) {
  const entry = toasts.find((t) => t.el === el);
  if (!entry || !entry.timer) return;
  clearTimeout(entry.timer);
  entry.timer = null;
  entry.remaining = Math.max(600, entry.remaining - (Date.now() - entry.startedAt));
}

function resumeToast(el) {
  const entry = toasts.find((t) => t.el === el);
  if (!entry || entry.timer) return;
  startToastTimer(entry);
}

function restackToasts() {
  toasts.forEach((t, i) => {
    t.el.style.setProperty("--i", i);
    t.el.style.zIndex = String(TOAST_MAX + 2 - i);
    t.el.classList.toggle("is-buried", i >= TOAST_MAX);
  });
}

function dismissToast(el) {
  const idx = toasts.findIndex((t) => t.el === el);
  if (idx === -1) return;
  const [entry] = toasts.splice(idx, 1);
  if (entry.timer) clearTimeout(entry.timer);
  el.classList.add("is-out");
  el.classList.remove("is-in");
  restackToasts();
  setTimeout(() => el.remove(), TOAST_EXIT_MS);
}

/* ---------- UTILS ---------- */

function escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function escAttr(s) {
  return String(s).replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

/* ---------- INIT ---------- */

showSkeleton();

function loadData() {
  return fetch("catalog-data.json?t=" + Date.now())
    .then((r) => {
      if (!r.ok) throw new Error("Failed to load catalog: " + r.status);
      return r.json();
    })
    .then((data) => {
      state.items = data.items || [];
      dom.countPublished.textContent = data.counts?.published ?? state.items.filter((i) => i.status === "published").length;
      dom.countDraft.textContent = data.counts?.staging ?? state.items.filter((i) => ["staging", "qa"].includes(i.status)).length;

      addOptions(dom.typeFilter, state.items.map((i) => i.type));
      addOptions(dom.brandFilter, state.items.map((i) => i.brand));

      hideSkeleton();
      render();
    })
    .catch((err) => {
      hideSkeleton();
      dom.summary.textContent = err.message;
      dom.grid.style.display = "";
    });
}

loadData();
