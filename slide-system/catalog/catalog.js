/* ============================================================
   SUN.STUDIO Visual Library — Unified Catalog + Template Picker
   Pure vanilla JS, no build step.
   ============================================================ */

/* ---------- SHARED UTILS ---------- */

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

function escHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function escAttr(s) {
  return String(s).replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

const BRAND_FONT_DIR = "/.agents/skills/sun-studio-design-system/assets/system/fonts/";
const BRAND_FONT_CSS = [
  ['ProximaNova-Regular',    'Proxima-Nova-Regular.otf',          null,  null],
  ['ProximaNova-Medium',     'Proxima-Nova-Medium.otf',           null,  null],
  ['ProximaNova-Semibold',   'Proxima-Nova-SemiBold.otf',         null,  null],
  ['ProximaNova-SemiboldIt', 'Proxima-Nova-SemiBold-Italic.otf',  null,  null],
  ['ProximaNova-Bold',       'Proxima-Nova-Bold.otf',             null,  null],
  ['ProximaNova-BoldIt',     'Proxima-Bold-Italic.otf',           null,  null],
  ['ProximaNova-Extrabld',   'Proxima-Black.otf',                 null,  null],
  ['ProximaNova-ExtrabldIt', 'Proxima-ExtraBold-Italic.otf',      null,  null],
  ['Proxima Nova', 'Proxima-Nova-Regular.otf',         '400', 'normal'],
  ['Proxima Nova', 'Proxima-Nova-Regular-Italic.otf',  '400', 'italic'],
  ['Proxima Nova', 'Proxima-Nova-Medium.otf',          '500', 'normal'],
  ['Proxima Nova', 'Proxima-Nova-SemiBold.otf',        '600', 'normal'],
  ['Proxima Nova', 'Proxima-Nova-SemiBold-Italic.otf', '600', 'italic'],
  ['Proxima Nova', 'Proxima-Nova-Bold.otf',            '700', 'normal'],
  ['Proxima Nova', 'Proxima-Bold-Italic.otf',          '700', 'italic'],
  ['Proxima Nova', 'Proxima-Black.otf',                '900', 'normal'],
].map(([family, file, weight, style]) => {
  let decl = `@font-face{font-family:"${family}";src:url("${BRAND_FONT_DIR}${file}") format("opentype")`;
  if (weight) decl += `;font-weight:${weight}`;
  if (style)  decl += `;font-style:${style}`;
  return decl + '}';
}).join("\n");

function injectFontsIntoSvgObject(obj) {
  try {
    const doc = obj.contentDocument;
    if (!doc) return;
    const svg = doc.querySelector("svg");
    if (!svg) return;
    let defs = svg.querySelector("defs");
    if (!defs) { defs = doc.createElementNS("http://www.w3.org/2000/svg", "defs"); svg.prepend(defs); }
    if (defs.querySelector(".brand-fonts")) return;
    const style = doc.createElementNS("http://www.w3.org/2000/svg", "style");
    style.setAttribute("class", "brand-fonts");
    style.textContent = BRAND_FONT_CSS;
    defs.prepend(style);
  } catch (_) { /* cross-origin or not loaded */ }
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
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

const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function smoothScrollTo(y) {
  try { window.scrollTo({ top: y, behavior: reduceMotion ? "auto" : "smooth" }); }
  catch (_) { window.scrollTo(0, y); }
}

/* ---------- TOAST STACK (shared) ---------- */

const TOAST_MAX = 3;
const TOAST_DURATION = 4000;
const TOAST_EXIT_MS = 320;
const toasts = [];
const toastStack = $("#toast-stack");

const TOAST_ICONS = {
  success: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 10.5l3.5 3.5L15 6.5"/></svg>',
  error: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 6v5M10 14h.01"/></svg>',
};

const TOAST_CLOSE_ICON = '<svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/></svg>';

function toast(html, type) {
  const kind = type === "error" ? "error" : "success";
  const node = document.createElement("div");
  node.className = "toast-item is-" + kind;
  node.innerHTML =
    '<span class="toast-icon">' + (TOAST_ICONS[kind] || "") + "</span>" +
    '<span class="toast-msg">' + html + "</span>" +
    '<button class="toast-x" type="button" aria-label="Dismiss">' + TOAST_CLOSE_ICON + "</button>";

  node.querySelector(".toast-x").addEventListener("click", () => dismissToast(node));
  node.addEventListener("pointerenter", () => pauseToast(node));
  node.addEventListener("pointerleave", () => resumeToast(node));

  toastStack.appendChild(node);
  const entry = { el: node, timer: null, remaining: TOAST_DURATION, startedAt: 0 };
  toasts.unshift(entry);
  requestAnimationFrame(() => { node.classList.add("is-in"); restackToasts(); });
  restackToasts();
  startToastTimer(entry);
  while (toasts.length > TOAST_MAX) dismissToast(toasts[toasts.length - 1].el);
  return node;
}

function startToastTimer(entry) {
  entry.startedAt = Date.now();
  entry.timer = setTimeout(() => dismissToast(entry.el), entry.remaining);
}

function pauseToast(node) {
  const entry = toasts.find(t => t.el === node);
  if (!entry?.timer) return;
  clearTimeout(entry.timer);
  entry.timer = null;
  entry.remaining = Math.max(600, entry.remaining - (Date.now() - entry.startedAt));
}

function resumeToast(node) {
  const entry = toasts.find(t => t.el === node);
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

function dismissToast(node) {
  const idx = toasts.findIndex(t => t.el === node);
  if (idx === -1) return;
  const [entry] = toasts.splice(idx, 1);
  if (entry.timer) clearTimeout(entry.timer);
  node.classList.add("is-out");
  node.classList.remove("is-in");
  restackToasts();
  setTimeout(() => node.remove(), TOAST_EXIT_MS);
}

/* ============================================================
   TOP-LEVEL TAB SWITCHING
   ============================================================ */

const topTabs = $$(".top-tab");
const SECTION_PANES = {
  components: $("#section-components"),
  templates: $("#section-templates"),
  review: $("#section-review"),
};
let activeSection = "components";
let reviewLoaded = false;

topTabs.forEach(tab => {
  tab.addEventListener("click", () => {
    const section = tab.dataset.section;
    if (section === activeSection) return;
    activeSection = section;
    topTabs.forEach(t => {
      const on = t.dataset.section === section;
      t.classList.toggle("is-active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    Object.entries(SECTION_PANES).forEach(([name, pane]) => {
      if (!pane) return;
      const on = name === section;
      pane.hidden = !on;
      pane.classList.toggle("is-active", on);
    });
    if (section === "review" && !reviewLoaded) { reviewLoaded = true; reviewLoadRuns(); }
  });
});

/* ============================================================
   COMPONENTS TAB
   ============================================================ */

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 2;
const ZOOM_STEP = 0.25;
const ZOOM_FIT = 1;

const compState = {
  items: [],
  filtered: [],
  status: "published",
  currentIndex: -1,
  detailTab: "preview",
  slideIndex: 0,
  zoom: 1,
  pan: { x: 0, y: 0 },
};

const compDom = {
  grid: $("#grid"),
  skeleton: $("#skeleton"),
  summary: $("#summary"),
  search: $("#search"),
  searchClear: $("#search-clear"),
  typeFilter: $("#type-filter"),
  brandFilter: $("#brand-filter"),
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
  navPrev: $("#nav-prev"),
  navNext: $("#nav-next"),
  copyId: $("#copy-id"),
  copyPrompt: $("#copy-prompt"),
  modalManage: $("#modal-manage"),
};

/* URL resolution */

function isSvgPath(url) { return url && url.split("?")[0].endsWith(".svg"); }

function compResolvePath(path) {
  if (!path) return null;
  if (path.startsWith("http")) return path;
  return "../../" + path;
}

function compResolveImageUrl(item) {
  if (item.images?.length) return compResolvePath(item.images[0].path);
  return null;
}

/* Filtering */

function compStatusMatches(item) {
  return compState.status === "published"
    ? item.status === "published"
    : ["staging", "qa"].includes(item.status);
}

function compFilterItems() {
  const term = compDom.search.value.trim().toLowerCase();
  compState.filtered = compState.items.filter(item => {
    if (item.type === "template") return false;
    if (!compStatusMatches(item)) return false;
    if (compDom.typeFilter.value && item.type !== compDom.typeFilter.value) return false;
    if (compDom.brandFilter.value && item.brand !== compDom.brandFilter.value) return false;
    if (term) {
      const hay = [item.id, item.name, item.type, item.brand, ...(item.intent || []), ...(item.tags || [])]
        .filter(Boolean).join(" ").toLowerCase();
      if (!hay.includes(term)) return false;
    }
    return true;
  });
}

/* Skeleton */

function compShowSkeleton() {
  let html = "";
  for (let i = 0; i < 8; i++) {
    html += '<div class="skeleton-tile"><div class="skeleton-preview"></div><div class="skeleton-meta"><div class="skeleton-line"></div><div class="skeleton-line"></div></div></div>';
  }
  compDom.skeleton.innerHTML = html;
  compDom.skeleton.style.display = "";
  compDom.grid.style.display = "none";
}

function compHideSkeleton() {
  compDom.skeleton.style.display = "none";
  compDom.grid.style.display = "";
}

/* Render grid */

function compRender() {
  compFilterItems();
  compDom.summary.textContent = compState.filtered.length + " item" + (compState.filtered.length === 1 ? "" : "s");
  compDom.grid.replaceChildren();

  if (compState.filtered.length === 0) {
    compDom.grid.innerHTML = `
      <div class="empty-state">
        <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="8" y="8" width="48" height="48" rx="8"/>
          <path d="M24 32h16M32 24v16" opacity=".4"/>
        </svg>
        <p>No items match your filters.</p>
        <button id="clear-filters">Clear all filters</button>
      </div>`;
    const btn = $("#clear-filters");
    if (btn) btn.addEventListener("click", compClearFilters);
    return;
  }

  const frag = document.createDocumentFragment();
  compState.filtered.forEach((item, idx) => frag.appendChild(compCreateTile(item, idx)));
  compDom.grid.appendChild(frag);
}

function compCreateTile(item, idx) {
  const tile = document.createElement("article");
  tile.className = "tile";
  tile.tabIndex = 0;
  tile.dataset.index = idx;

  const imgUrl = compResolveImageUrl(item);
  const svgTile = isSvgPath(imgUrl);
  const statusClass = item.status === "published" ? "published" : "draft";
  const statusLabel = item.status === "published" ? "Published" : "Draft";

  let previewHtml;
  if (!imgUrl) {
    previewHtml = `<div class="fallback">${escHtml(item.type)}</div>`;
  } else if (svgTile) {
    previewHtml = `<object data="${escAttr(imgUrl)}" type="image/svg+xml" class="tile-svg-obj" aria-label="${escAttr(item.name)}" tabindex="-1"></object>
      <div class="fallback" style="display:none">${escHtml(item.type)}</div>`;
  } else {
    previewHtml = `<img src="${escAttr(imgUrl)}" alt="${escAttr(item.name)}" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display=''">
      <div class="fallback" style="display:none">${escHtml(item.type)}</div>`;
  }

  tile.innerHTML = `
    <div class="tile-preview">${previewHtml}</div>
    <div class="tile-meta">
      <div class="tile-name" title="${escAttr(item.name)}">${escHtml(item.name)}</div>
      <div class="tile-info">
        <span>${escHtml(item.type)}</span>
        <span class="status-dot ${statusClass}">${statusLabel}</span>
      </div>
    </div>`;

  if (svgTile) {
    const obj = tile.querySelector(".tile-svg-obj");
    if (obj) obj.addEventListener("load", () => injectFontsIntoSvgObject(obj));
  }

  tile.addEventListener("click", () => compOpenModal(idx));
  tile.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); compOpenModal(idx); }
  });

  return tile;
}

/* Detail modal */

function compOpenModal(idx) {
  compState.currentIndex = idx;
  compState.detailTab = "preview";
  compState.slideIndex = 0;
  compResetZoom();
  compRenderModal();
  compDom.backdrop.classList.add("is-open");
  compDom.modal.classList.add("is-open");
  document.body.style.overflow = "hidden";
}

function compCloseModal() {
  compDom.backdrop.classList.remove("is-open");
  compDom.modal.classList.remove("is-open");
  document.body.style.overflow = "";
  compState.currentIndex = -1;
}

function compNavigateModal(dir) {
  const next = compState.currentIndex + dir;
  if (next < 0 || next >= compState.filtered.length) return;
  compState.currentIndex = next;
  compState.detailTab = "preview";
  compState.slideIndex = 0;
  compResetZoom();
  compRenderModal();
  compDom.modal.scrollTop = 0;
}

function compRenderModal() {
  const item = compState.filtered[compState.currentIndex];
  if (!item) return;

  compDom.navPrev.disabled = compState.currentIndex === 0;
  compDom.navNext.disabled = compState.currentIndex === compState.filtered.length - 1;
  compDom.modalTitle.textContent = item.name;

  const images = item.images || [];
  const hasMultipleImages = images.length > 1;
  const hasImage = images.length > 0;

  let visualHtml = "";

  const iconSet = item.icon_set;
  if (iconSet && iconSet.icons && iconSet.icons.length) {
    const icons = iconSet.icons;
    visualHtml += `
      <div class="iconset">
        <div class="iconset-toolbar">
          <input type="search" id="iconset-search" class="iconset-search"
                 placeholder="Filter ${icons.length} icons by name…" autocomplete="off">
          <span class="iconset-count" id="iconset-count">${icons.length} icons</span>
        </div>
        <div class="iconset-grid" id="iconset-grid">
          ${icons.map((ic, i) => `
            <button class="iconset-cell" data-name="${escAttr((ic.name + " " + ic.slug).toLowerCase())}"
                    data-path="${escAttr(compResolvePath(ic.path))}" title="${escAttr(ic.name)}"
                    aria-label="${escAttr(ic.name)}">
              <img src="${compResolvePath(ic.path)}" alt="${escAttr(ic.name)}" loading="lazy" draggable="false">
              <span class="iconset-name">${escHtml(ic.name)}</span>
            </button>`).join("")}
        </div>
      </div>`;
    // wiring happens after the common innerHTML assignment below.
  } else if (hasImage) {
    const currentImg = images[compState.slideIndex] || images[0];
    const imgSrc = compResolvePath(currentImg.path);

    visualHtml += '<div class="carousel-container is-zoomable">';
    const isSvg = imgSrc && imgSrc.endsWith(".svg");
    if (isSvg) {
      visualHtml += `<object data="${imgSrc}" type="image/svg+xml" class="carousel-svg-obj" aria-label="${escAttr(item.name)}"></object>`;
    } else {
      visualHtml += `<img src="${imgSrc}" alt="${escAttr(item.name)}" draggable="false" onerror="this.style.display='none'">`;
    }
    visualHtml += `
      <div class="zoom-controls" role="group" aria-label="Zoom controls">
        <button class="zoom-btn" id="zoom-out" aria-label="Zoom out">&minus;</button>
        <span class="zoom-level" id="zoom-level">100%</span>
        <button class="zoom-btn" id="zoom-in" aria-label="Zoom in">+</button>
        <button class="zoom-btn zoom-fit" id="zoom-fit" aria-label="Fit to frame">Fit</button>
      </div>`;

    if (hasMultipleImages) {
      visualHtml += `
        <button class="carousel-btn carousel-prev" id="slide-prev" ${compState.slideIndex === 0 ? "disabled" : ""} aria-label="Previous image">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 3L5 8l5 5"/></svg>
        </button>
        <button class="carousel-btn carousel-next" id="slide-next" ${compState.slideIndex >= images.length - 1 ? "disabled" : ""} aria-label="Next image">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3l5 5-5 5"/></svg>
        </button>
        <div class="carousel-indicators">
          ${images.map((img, i) =>
            `<button class="carousel-dot ${i === compState.slideIndex ? "is-active" : ""}" data-slide="${i}" title="${escAttr(img.label)}" aria-label="${escAttr(img.label)}"></button>`
          ).join("")}
        </div>
        <div class="carousel-label">${escHtml(currentImg.label)} (${compState.slideIndex + 1}/${images.length})</div>`;
    }

    visualHtml += "</div>";
  } else {
    visualHtml += '<div class="carousel-container"><div class="fallback">' + escHtml(item.type) + "</div></div>";
  }

  compDom.modalVisual.innerHTML = visualHtml;

  const isIconSet = !!(iconSet && iconSet.icons && iconSet.icons.length);
  if (isIconSet) {
    compWireIconSet();
  } else {
    const svgObj = compDom.modalVisual.querySelector(".carousel-svg-obj");
    if (svgObj) svgObj.addEventListener("load", () => injectFontsIntoSvgObject(svgObj));
    if (hasImage) compWireZoom();

    if (hasMultipleImages) {
      const prevBtn = $("#slide-prev");
      const nextBtn = $("#slide-next");
      if (prevBtn) prevBtn.addEventListener("click", e => { e.stopPropagation(); compChangeSlide(-1); });
      if (nextBtn) nextBtn.addEventListener("click", e => { e.stopPropagation(); compChangeSlide(1); });
      compDom.modalVisual.querySelectorAll(".carousel-dot").forEach(dot => {
        dot.addEventListener("click", e => {
          e.stopPropagation();
          if (parseInt(dot.dataset.slide) === compState.slideIndex) return;
          compState.slideIndex = parseInt(dot.dataset.slide);
          compResetZoom();
          compRenderModal();
        });
      });
    }
  }

  const statusClass = item.status === "published" ? "published" : "draft";
  const statusLabel = item.status === "published" ? "Published" : "Draft";
  compDom.modalId.innerHTML = `
    <span>${escHtml(item.id)} &middot; v${escHtml(item.version)}</span>
    <span class="status-dot ${statusClass}">${statusLabel}</span>`;

  compRenderInfoPanel(item);
  compRenderManageBar(item);
  compSetActiveTab(compState.detailTab);
}

function compSetActiveTab(id) {
  compState.detailTab = id;
  compDom.subTabs.querySelectorAll(".sub-tab").forEach(btn => {
    const on = btn.dataset.tab === id;
    btn.classList.toggle("is-active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  [compDom.panelPreview, compDom.panelInfo].forEach(p => p.classList.remove("is-active"));
  const panel = $(`#panel-${id}`);
  if (panel) panel.classList.add("is-active");
}

function compWireIconSet() {
  const search = $("#iconset-search");
  const grid = $("#iconset-grid");
  const count = $("#iconset-count");
  if (!grid) return;
  const cells = Array.from(grid.querySelectorAll(".iconset-cell"));
  if (search) {
    search.addEventListener("input", () => {
      const q = search.value.trim().toLowerCase();
      let shown = 0;
      cells.forEach(c => {
        const hit = !q || c.dataset.name.includes(q);
        c.style.display = hit ? "" : "none";
        if (hit) shown++;
      });
      if (count) count.textContent = `${shown} / ${cells.length} icons`;
    });
  }
  cells.forEach(c => {
    c.addEventListener("click", e => {
      e.stopPropagation();
      const path = c.dataset.path;
      if (navigator.clipboard && path) {
        navigator.clipboard.writeText(path).then(() => {
          c.classList.add("is-copied");
          setTimeout(() => c.classList.remove("is-copied"), 900);
        }).catch(() => window.open(path, "_blank"));
      } else if (path) {
        window.open(path, "_blank");
      }
    });
  });
}

function compChangeSlide(dir) {
  const item = compState.filtered[compState.currentIndex];
  if (!item?.images?.length) return;
  const next = compState.slideIndex + dir;
  if (next < 0 || next >= item.images.length) return;
  compState.slideIndex = next;
  compResetZoom();
  compRenderModal();
}

/* Zoom + Pan */

function compCurrentImageEl() { return compDom.modalVisual.querySelector(".carousel-svg-obj") || compDom.modalVisual.querySelector("img"); }

function compResetZoom() { compState.zoom = 1; compState.pan.x = 0; compState.pan.y = 0; }

function compApplyZoom() {
  const img = compCurrentImageEl();
  if (!img) return;
  img.style.transform = `translate(${compState.pan.x}px, ${compState.pan.y}px) scale(${compState.zoom})`;
  const container = img.closest(".carousel-container");
  if (container) container.classList.toggle("is-zoomed", compState.zoom > 1);
}

function compClampPan() {
  const img = compCurrentImageEl();
  if (!img) return;
  const rect = img.getBoundingClientRect();
  const maxX = Math.max(0, (rect.width - rect.width / compState.zoom) / 2);
  const maxY = Math.max(0, (rect.height - rect.height / compState.zoom) / 2);
  compState.pan.x = Math.max(-maxX, Math.min(maxX, compState.pan.x));
  compState.pan.y = Math.max(-maxY, Math.min(maxY, compState.pan.y));
}

function compSetZoom(z) {
  compState.zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));
  if (compState.zoom <= ZOOM_FIT) { compState.pan.x = 0; compState.pan.y = 0; }
  else compClampPan();
  compApplyZoom();
  compUpdateZoomUI();
}

function compZoomBy(delta) { compSetZoom(compState.zoom + delta); }

function compUpdateZoomUI() {
  const level = $("#zoom-level");
  if (level) level.textContent = Math.round(compState.zoom * 100) + "%";
  const out = $("#zoom-out");
  const inn = $("#zoom-in");
  if (out) out.disabled = compState.zoom <= ZOOM_MIN;
  if (inn) inn.disabled = compState.zoom >= ZOOM_MAX;
}

function compWireZoom() {
  const container = compDom.modalVisual.querySelector(".carousel-container");
  const img = compCurrentImageEl();
  if (!container || !img) return;

  compApplyZoom();
  compUpdateZoomUI();

  const out = $("#zoom-out");
  const inn = $("#zoom-in");
  const fit = $("#zoom-fit");
  if (out) out.addEventListener("click", e => { e.stopPropagation(); compZoomBy(-ZOOM_STEP); });
  if (inn) inn.addEventListener("click", e => { e.stopPropagation(); compZoomBy(ZOOM_STEP); });
  if (fit) fit.addEventListener("click", e => { e.stopPropagation(); compSetZoom(ZOOM_FIT); });

  img.addEventListener("click", e => {
    if (img.dataset.dragged === "1") { img.dataset.dragged = "0"; return; }
    if (compState.zoom < ZOOM_MAX) { e.stopPropagation(); compZoomBy(ZOOM_STEP); }
  });

  let dragging = false, startX = 0, startY = 0, baseX = 0, baseY = 0;
  container.addEventListener("pointerdown", e => {
    if (e.target.closest(".zoom-controls, .carousel-btn, .carousel-indicators")) return;
    if (compState.zoom <= ZOOM_FIT) return;
    dragging = true;
    startX = e.clientX; startY = e.clientY;
    baseX = compState.pan.x; baseY = compState.pan.y;
    container.classList.add("is-grabbing");
    container.setPointerCapture(e.pointerId);
  });
  container.addEventListener("pointermove", e => {
    if (!dragging) return;
    compState.pan.x = baseX + (e.clientX - startX);
    compState.pan.y = baseY + (e.clientY - startY);
    if (Math.abs(e.clientX - startX) > 3 || Math.abs(e.clientY - startY) > 3) {
      img.dataset.dragged = "1";
    }
    compClampPan();
    compApplyZoom();
  });
  const endDrag = e => {
    if (!dragging) return;
    dragging = false;
    container.classList.remove("is-grabbing");
    try { container.releasePointerCapture(e.pointerId); } catch (_) {}
  };
  container.addEventListener("pointerup", endDrag);
  container.addEventListener("pointercancel", endDrag);
}

/* Info panel */

function compRenderInfoPanel(item) {
  let html = "";
  if (item.brand) html += compInfoRow("Brand", escHtml(item.brand));
  if (item.intent?.length) html += compInfoRow("Intent", '<div class="pills">' + item.intent.map(compPill).join("") + "</div>");
  if (item.tags?.length) html += compInfoRow("Tags", '<div class="pills">' + item.tags.map(compPill).join("") + "</div>");
  if (item.source) {
    const src = typeof item.source === "string" ? item.source : (item.source.path || JSON.stringify(item.source));
    html += compInfoRow("Source", '<span style="font-family:var(--mono);font-size:11px;word-break:break-all">' + escHtml(String(src)) + "</span>");
  }
  if (item.variants?.length) html += compInfoRow("Variants", '<div class="pills">' + item.variants.map(compPill).join("") + "</div>");
  if (item.limitations?.length) html += compInfoRow("Limitations", '<ul class="limitations-list">' + item.limitations.map(l => "<li>" + escHtml(l) + "</li>").join("") + "</ul>");
  const imageCount = item.images?.length || 0;
  if (imageCount > 1) html += compInfoRow("Images", imageCount + " visuals available (use the carousel or ←/→)");
  compDom.panelInfo.innerHTML = html || '<p style="color:var(--ink-soft);font-size:13px">No additional info.</p>';
}

function compInfoRow(label, value) {
  return '<div class="info-row"><span class="info-label">' + label + '</span><div class="info-value">' + value + "</div></div>";
}

function compPill(text) {
  return '<span class="pill">' + escHtml(text) + "</span>";
}

/* Filter controls */

function compAddOptions(select, values) {
  const current = select.value;
  while (select.options.length > 1) select.remove(1);
  [...new Set(values.filter(Boolean))].sort().forEach(v => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    select.appendChild(opt);
  });
  if ([...select.options].some(o => o.value === current)) select.value = current;
}

function compUpdateFilterStyles() {
  [compDom.typeFilter, compDom.brandFilter].forEach(sel => {
    sel.classList.toggle("has-value", !!sel.value);
  });
}

function compClearFilters() {
  compDom.search.value = "";
  compDom.typeFilter.value = "";
  compDom.brandFilter.value = "";
  compUpdateFilterStyles();
  compRender();
}

/* Manage bar (publish / delete) */

const MANAGE_ICONS = {
  publish: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 11V3M5 6l3-3 3 3M3.5 13h9"/></svg>',
  trash: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4.5h10M6.5 4.5V3h3v1.5M5 4.5l.5 8h5l.5-8"/></svg>',
};

function compManageBtn(label, iconKey, cls) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = cls;
  b.innerHTML = MANAGE_ICONS[iconKey] + "<span>" + escHtml(label) + "</span>";
  return b;
}

function compRenderManageBar(item) {
  const bar = compDom.modalManage;
  if (!bar) return;
  bar.innerHTML = "";
  const isDraft = item.status !== "published";

  if (isDraft) {
    const readiness = item.publish_readiness || { ready: true, blockers: [] };
    const pub = compManageBtn("Publish", "publish", "manage-btn manage-btn-primary");
    if (!readiness.ready) {
      pub.disabled = true;
      pub.title = "This extraction is incomplete:\n- " + (readiness.blockers || []).join("\n- ");
    } else {
      pub.title = "Add this to the published library";
    }
    pub.addEventListener("click", () => compOnPublish(item, pub));
    bar.appendChild(pub);

    const del = compManageBtn("Delete draft", "trash", "manage-btn manage-btn-danger");
    del.addEventListener("click", () => compOnDelete(item, del));
    bar.appendChild(del);

    if (!readiness.ready && (readiness.blockers || []).length) {
      const note = document.createElement("div");
      note.className = "manage-note";
      note.textContent = "Can’t publish yet: " + readiness.blockers.join("; ");
      bar.appendChild(note);
    }
  } else {
    if (item.deletable === false) return;
    const del = compManageBtn("Delete", "trash", "manage-btn manage-btn-danger");
    del.addEventListener("click", () => compOnDelete(item, del));
    bar.appendChild(del);
  }
}

function compBusy(btn, on) {
  if (!btn) return;
  btn.disabled = on;
  btn.classList.toggle("is-busy", on);
}

function compApi(path, body) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(
    async r => {
      let data = {};
      try { data = await r.json(); } catch (_) {}
      if (r.status === 404 && !data.error) {
        throw new Error("Control server not running. Start it with: python3 slide-system/catalog/catalog_server.py");
      }
      if (!r.ok || !data.ok) throw new Error(data.error || ("Request failed (" + r.status + ")"));
      return data;
    },
    () => { throw new Error("Control server not reachable. Start it with: python3 slide-system/catalog/catalog_server.py"); }
  );
}

function compOnPublish(item, btn) {
  compBusy(btn, true);
  toast(`Publishing <code>${escHtml(item.id)}</code>&hellip;`);
  compApi("/api/publish", { id: item.id })
    .then(() => {
      compCloseModal();
      return compLoadData().then(() => toast(`Published <code>${escHtml(item.id)}</code> to the library.`));
    })
    .catch(e => toast(escHtml(e.message), "error"))
    .finally(() => compBusy(btn, false));
}

function compOnDelete(item, btn) {
  compBusy(btn, true);
  compApi("/api/delete", { id: item.id, status: item.status })
    .then(() => {
      compCloseModal();
      return compLoadData().then(() => toast(`Deleted <code>${escHtml(item.id)}</code>.`));
    })
    .catch(e => toast(escHtml(e.message), "error"))
    .finally(() => compBusy(btn, false));
}


/* Copy + prompt */

function compBuildPrompt(item) {
  const label = item.name && item.name !== item.id ? `"${item.name}" ` : "";
  const where = item.status === "published" ? "published " : "";
  return `Use the ${where}${item.type || "visual"} component ${label}(${item.id}) from the SUN.STUDIO visual library.`;
}

const COPIED_HTML =
  '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8.5l3 3 6-7"/></svg>Copied';

function compCopyText(text, btn) {
  return clipboardWrite(text).then(() => { if (btn) compMarkCopied(btn); });
}

function compMarkCopied(btn) {
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

/* Component events */

$$(".status-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    $$(".status-tab").forEach(t => { t.classList.remove("is-active"); t.setAttribute("aria-selected", "false"); });
    tab.classList.add("is-active");
    tab.setAttribute("aria-selected", "true");
    compState.status = tab.dataset.status;
    compRender();
  });
});

[compDom.search, compDom.typeFilter, compDom.brandFilter].forEach(el => {
  el.addEventListener("input", () => { compUpdateFilterStyles(); compRender(); });
});

compDom.searchClear.addEventListener("click", () => { compDom.search.value = ""; compRender(); });
compDom.modalClose.addEventListener("click", compCloseModal);
compDom.backdrop.addEventListener("click", compCloseModal);
compDom.navPrev.addEventListener("click", () => compNavigateModal(-1));
compDom.navNext.addEventListener("click", () => compNavigateModal(1));

compDom.subTabs.querySelectorAll(".sub-tab").forEach(btn => {
  btn.addEventListener("click", () => compSetActiveTab(btn.dataset.tab));
});

compDom.copyId.addEventListener("click", () => {
  const item = compState.filtered[compState.currentIndex];
  if (!item) return;
  compCopyText(item.id, compDom.copyId).then(
    () => toast(`Copied id: <code>${escHtml(item.id)}</code>`),
    () => toast(`Copy failed. Component id: ${escHtml(item.id)}`, "error")
  );
});

compDom.copyPrompt.addEventListener("click", () => {
  const item = compState.filtered[compState.currentIndex];
  if (!item) return;
  const prompt = compBuildPrompt(item);
  compCopyText(prompt, compDom.copyPrompt).then(
    () => toast("Copied prompt &mdash; paste it into the conversation to use this component."),
    () => toast("Copy failed.", "error")
  );
});

/* Component keyboard */

document.addEventListener("keydown", e => {
  // Only handle keys when component modal is open
  if (compState.currentIndex === -1) return;
  switch (e.key) {
    case "Escape": compCloseModal(); break;
    case "ArrowLeft":
      if (e.shiftKey) { e.preventDefault(); compNavigateModal(-1); } else compChangeSlide(-1);
      break;
    case "ArrowRight":
      if (e.shiftKey) { e.preventDefault(); compNavigateModal(1); } else compChangeSlide(1);
      break;
    case "+": case "=": e.preventDefault(); compZoomBy(ZOOM_STEP); break;
    case "-": case "_": e.preventDefault(); compZoomBy(-ZOOM_STEP); break;
    case "0": e.preventDefault(); compSetZoom(ZOOM_FIT); break;
  }
});

/* Component data loading */

compShowSkeleton();

function compLoadData() {
  return fetch("catalog-data.json?t=" + Date.now())
    .then(r => {
      if (!r.ok) throw new Error("Failed to load catalog: " + r.status);
      return r.json();
    })
    .then(data => {
      compState.items = data.items || [];
      const nonTpl = compState.items.filter(i => i.type !== "template");
      const pubCount = nonTpl.filter(i => i.status === "published").length;
      const draftCount = nonTpl.filter(i => ["staging", "qa"].includes(i.status)).length;
      compDom.countPublished.textContent = pubCount;
      compDom.countDraft.textContent = draftCount;

      $("#count-components").textContent = nonTpl.length;

      compAddOptions(compDom.typeFilter, nonTpl.map(i => i.type));
      compAddOptions(compDom.brandFilter, nonTpl.map(i => i.brand));

      compHideSkeleton();
      compRender();
    })
    .catch(err => {
      compHideSkeleton();
      compDom.summary.textContent = err.message;
      compDom.grid.style.display = "";
    });
}

compLoadData();


/* ============================================================
   TEMPLATES TAB
   ============================================================ */

const tplState = {
  decks: [],
  view: "sets",
  activeDeck: null,
  active: null,
  viewerSlides: [],
  viewerDeck: null,
  activeIndex: 0,
  filmItems: [],
  lastFocus: null,
};

const tplDom = {
  kicker: $("#tpl-kicker"),
  title: $("#tpl-title"),
  lede: $("#tpl-lede"),
  jumpNav: $("#jump-nav"),
  gallery: $("#tpl-gallery"),
  stateMessage: $("#tpl-state-message"),
  modal: $("#tpl-modal"),
  modalClose: $("#tpl-modal-close"),
  viewerDeck: $("#viewer-deck"),
  viewerCounter: $("#viewer-counter"),
  viewerSetBtn: $("#viewer-setbtn"),
  filmstrip: $("#filmstrip"),
  stageFrame: $("#stage-frame"),
  stagePrev: $("#stage-prev"),
  stageNext: $("#stage-next"),
  usecase: $("#stage-usecase"),
  stageName: $("#stage-name"),
  stageId: $("#stage-id"),
  stageChips: $("#stage-chips"),
  selectBtn: $("#select-btn"),
};

/* Helpers */

function tplThumbSrc(card) {
  if (!card) return null;
  const t = card.thumbnail;
  if (t && String(t).trim()) return t;
  if (card.preview && String(card.preview).trim()) return card.preview;
  return null;
}

function tplDeckSlides(deck) { return (deck && deck.slides) || []; }
function tplDeckAnchor(deck, i) { return "deck-" + (deck.deck_id || i); }

function tplDecksOf(payload) {
  if (payload?.decks?.length) return payload.decks;
  const templates = payload?.templates || [];
  if (!templates.length) return [];
  return [{ deck_id: "all", name: "Full-slide templates", slides: templates, slide_count: templates.length }];
}

function tplPlaceholder(card) {
  const ph = el("div", "thumb-placeholder");
  const initials = ((card && (card.name || card._deckName)) || "T").slice(0, 1).toUpperCase();
  ph.appendChild(el("span", "ph-mark", initials));
  ph.appendChild(el("span", "ph-label", "No preview"));
  return ph;
}

/* Data loading */

function tplLoad() {
  const base = "../template-picker/";
  return fetch(base + "picker-data.json", { cache: "no-store" })
    .then(r => { if (!r.ok) throw new Error(); return r.json(); })
    .then(data => ({ data, state: "live" }))
    .catch(() =>
      fetch(base + "picker-data.sample.json", { cache: "no-store" })
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(data => ({ data, state: "fixture" }))
    );
}

/* Render entry */

function tplRender(payload, sourceState) {
  tplState.decks = tplDecksOf(payload).filter(d => tplDeckSlides(d).length);
  const total = tplState.decks.reduce((n, d) => n + tplDeckSlides(d).length, 0);

  // Update top-tab count
  $("#count-templates").textContent = tplState.decks.length;

  tplDom.kicker.textContent = total + " template" + (total === 1 ? "" : "s") + " · " +
    tplState.decks.length + " set" + (tplState.decks.length === 1 ? "" : "s") +
    (sourceState === "fixture" ? " · Sample data" : "");

  if (!total) {
    tplShowState("<strong>No published templates yet.</strong> Publish templates into the visual library, then regenerate picker-data.json.");
    return;
  }
  tplDom.stateMessage.hidden = true;
  tplShowSets(false);
}

function tplShowState(html) {
  tplDom.stateMessage.innerHTML = html;
  tplDom.stateMessage.hidden = false;
}

function tplClearGallery() {
  tplDom.gallery.querySelectorAll(".set-section, .deck-section, .detail-bar").forEach(n => n.remove());
}

/* SETS view */

function tplShowSets(scroll) {
  tplState.view = "sets";
  tplState.activeDeck = null;
  tplClearGallery();
  tplDom.jumpNav.innerHTML = "";
  tplDom.jumpNav.hidden = true;

  tplDom.lede.textContent = "Published templates, grouped into full deck sets. Pick a set to browse every slide, preview it as the original, and build a deck on top of it.";

  const section = el("section", "set-section");
  const head = el("div", "set-section-head");
  head.appendChild(el("p", "section-kicker", tplState.decks.length + (tplState.decks.length === 1 ? " template set" : " template sets")));
  head.appendChild(el("h2", null, "Template sets"));
  section.appendChild(head);

  const grid = el("div", "set-grid");
  tplState.decks.forEach((deck, i) => grid.appendChild(tplBuildSetCard(deck, i)));
  section.appendChild(grid);
  tplDom.gallery.appendChild(section);

  if (scroll !== false) smoothScrollTo(0);
}

function tplBuildSetCard(deck, i) {
  const slides = tplDeckSlides(deck);
  const btn = el("button", "set-card");
  btn.type = "button";
  btn.setAttribute("aria-label", "Open the " + (deck.name || "deck") + " set, " + slides.length + " slides");

  const cover = el("div", "set-cover");
  cover.appendChild(el("span", "set-cover-layer set-cover-back"));
  cover.appendChild(el("span", "set-cover-layer set-cover-mid"));

  const front = el("div", "set-cover-front");
  const src = tplThumbSrc(slides[0]);
  if (src && isSvgPath(src)) {
    const obj = document.createElement("object");
    obj.data = src;
    obj.type = "image/svg+xml";
    obj.style.cssText = "width:100%;height:100%;display:block;pointer-events:none";
    obj.addEventListener("load", () => injectFontsIntoSvgObject(obj));
    obj.addEventListener("error", () => { obj.remove(); front.appendChild(tplPlaceholder(slides[0] || { name: deck.name })); });
    front.appendChild(obj);
  } else if (src) {
    const img = el("img");
    img.src = src;
    img.alt = "Cover slide of the " + (deck.name || "deck") + " set";
    img.loading = "lazy";
    img.addEventListener("error", () => { img.remove(); front.appendChild(tplPlaceholder(slides[0] || { name: deck.name })); });
    front.appendChild(img);
  } else {
    front.appendChild(tplPlaceholder(slides[0] || { name: deck.name }));
  }
  cover.appendChild(front);
  cover.appendChild(el("span", "set-count-badge", String(slides.length)));
  btn.appendChild(cover);

  const body = el("div", "set-body");
  body.appendChild(el("p", "set-kicker", "Full deck set"));
  body.appendChild(el("div", "set-name", deck.name || "Deck"));

  const meta = el("div", "set-meta");
  meta.appendChild(el("span", "set-meta-count", slides.length + (slides.length === 1 ? " slide" : " slides")));
  const open = el("span", "set-open");
  open.appendChild(document.createTextNode("Open set"));
  open.appendChild(el("span", "set-open-arrow", "→"));
  meta.appendChild(open);
  body.appendChild(meta);
  btn.appendChild(body);

  btn.addEventListener("click", () => tplOpenDeck(deck, i));
  return btn;
}

/* DETAIL view */

function tplOpenDeck(deck, i) {
  tplState.view = "detail";
  tplState.activeDeck = deck;
  tplClearGallery();

  tplDom.lede.textContent = "Open a slide to preview it as the original, copy one slide’s id, or grab the whole set to build a deck on top of it.";

  const bar = el("div", "detail-bar");
  const back = el("button", "back-btn");
  back.type = "button";
  back.appendChild(el("span", "back-arrow", "←"));
  back.appendChild(document.createTextNode("All template sets"));
  back.addEventListener("click", () => tplShowSets(true));
  bar.appendChild(back);
  tplDom.gallery.appendChild(bar);

  tplRenderJumpNav(deck);

  const slides = tplDeckSlides(deck);
  const anchor = tplDeckAnchor(deck, i);

  const section = el("section", "deck-section");
  section.id = anchor;
  section.setAttribute("aria-labelledby", anchor + "-h");

  const head = el("div", "section-head");
  const heads = el("div", "section-head-text");
  heads.appendChild(el("p", "section-kicker", slides.length > 1 ? "Full deck set" : "Single slide"));
  const h2 = el("h2", null, deck.name || "Deck");
  h2.id = anchor + "-h";
  heads.appendChild(h2);
  head.appendChild(heads);

  const actions = el("div", "section-actions");
  actions.appendChild(el("span", "section-count", slides.length + (slides.length === 1 ? " slide" : " slides")));
  const setBtn = el("button", "set-btn", "Copy set prompt");
  setBtn.type = "button";
  setBtn.title = "Copy a prompt for the whole deck (" + slides.length + " slides)";
  setBtn.addEventListener("click", () => tplSelectDeck(deck));
  actions.appendChild(setBtn);
  head.appendChild(actions);
  section.appendChild(head);

  const grid = el("div", "card-grid");
  slides.forEach((card, idx) => {
    card._deckName = deck.name;
    grid.appendChild(tplBuildCard(card, deck, idx));
  });
  section.appendChild(grid);
  tplDom.gallery.appendChild(section);

  smoothScrollTo(0);
  if (back.focus) back.focus();
}

function tplRenderJumpNav(activeDeck) {
  tplDom.jumpNav.innerHTML = "";
  if (tplState.decks.length < 2) { tplDom.jumpNav.hidden = true; return; }
  tplDom.jumpNav.hidden = false;
  tplState.decks.forEach((deck, i) => {
    const a = el("button", "jump-pill");
    a.type = "button";
    if (deck === activeDeck) a.setAttribute("aria-current", "true");
    a.appendChild(document.createTextNode(deck.name || "Deck"));
    a.appendChild(el("span", "n", String(tplDeckSlides(deck).length)));
    a.addEventListener("click", () => {
      if (deck !== tplState.activeDeck) tplOpenDeck(deck, i);
      else smoothScrollTo(0);
    });
    tplDom.jumpNav.appendChild(a);
  });
}

function tplBuildCard(card, deck, index) {
  const btn = el("button", "card");
  btn.type = "button";
  btn.setAttribute("aria-haspopup", "dialog");
  btn.setAttribute("aria-label", "Open template " + (card.name || card.id));

  const thumb = el("div", "thumb");
  const src = tplThumbSrc(card);
  if (src && isSvgPath(src)) {
    const obj = document.createElement("object");
    obj.data = src;
    obj.type = "image/svg+xml";
    obj.style.cssText = "width:100%;height:100%;object-fit:cover;display:block;pointer-events:none";
    obj.addEventListener("load", () => injectFontsIntoSvgObject(obj));
    obj.addEventListener("error", () => { obj.remove(); thumb.insertBefore(tplPlaceholder(card), thumb.firstChild); });
    thumb.appendChild(obj);
  } else if (src) {
    const img = el("img");
    img.src = src;
    img.alt = "Preview of the " + (card.name || card.id) + " template";
    img.loading = "lazy";
    img.addEventListener("error", () => { img.remove(); thumb.insertBefore(tplPlaceholder(card), thumb.firstChild); });
    thumb.appendChild(img);
  } else {
    thumb.appendChild(tplPlaceholder(card));
  }
  if (card.slide_number != null) thumb.appendChild(el("span", "slide-badge", String(card.slide_number)));
  btn.appendChild(thumb);

  const body = el("div", "card-body");
  body.appendChild(el("div", "card-name", card.name || card.id));

  const chips = el("div", "chip-row");
  (card.intent || []).slice(0, 2).forEach(i => chips.appendChild(el("span", "chip chip-intent", i)));
  (card.tags || []).slice(0, 3).forEach(t => chips.appendChild(el("span", "chip", t)));
  if (chips.childNodes.length) body.appendChild(chips);

  btn.appendChild(body);
  btn.addEventListener("click", () => tplOpenModal(deck, index, btn));
  return btn;
}

/* Viewer modal */

function tplOpenModal(deck, index, trigger) {
  tplState.viewerDeck = deck;
  tplState.viewerSlides = tplDeckSlides(deck);
  tplState.lastFocus = trigger || document.activeElement;
  if (!tplState.viewerSlides.length) return;

  tplDom.viewerDeck.textContent = deck.name || "Deck";
  tplRenderFilmstrip(deck);

  tplDom.modal.classList.remove("is-closing");
  tplDom.modal.hidden = false;
  document.body.style.overflow = "hidden";
  document.addEventListener("keydown", tplOnKeydown);

  tplGoTo(index, 0);
  tplDom.modalClose.focus();
}

function tplRenderFilmstrip(deck) {
  const slides = tplDeckSlides(deck);
  tplDom.filmstrip.innerHTML = "";
  tplState.filmItems = slides.map((card, i) => {
    const item = el("button", "film-item");
    item.type = "button";
    item.setAttribute("aria-label", "Go to slide " + (i + 1) + ": " + (card.name || card.id));

    const thumb = el("div", "film-thumb");
    const src = tplThumbSrc(card);
    if (src && isSvgPath(src)) {
      const obj = document.createElement("object");
      obj.data = src;
      obj.type = "image/svg+xml";
      obj.style.cssText = "width:100%;height:100%;display:block;pointer-events:none";
      obj.addEventListener("load", () => injectFontsIntoSvgObject(obj));
      obj.addEventListener("error", () => {
        obj.remove();
        const ph = tplPlaceholder(card);
        ph.classList.add("film-ph");
        thumb.appendChild(ph);
      });
      thumb.appendChild(obj);
    } else if (src) {
      const img = el("img");
      img.src = src;
      img.alt = "";
      img.loading = "lazy";
      img.addEventListener("error", () => {
        img.remove();
        const ph = tplPlaceholder(card);
        ph.classList.add("film-ph");
        thumb.appendChild(ph);
      });
      thumb.appendChild(img);
    } else {
      const ph = tplPlaceholder(card);
      ph.classList.add("film-ph");
      thumb.appendChild(ph);
    }
    thumb.appendChild(el("span", "film-num", String(card.slide_number != null ? card.slide_number : i + 1)));
    item.appendChild(thumb);

    item.addEventListener("click", () => {
      tplGoTo(i, i > tplState.activeIndex ? 1 : i < tplState.activeIndex ? -1 : 0);
    });
    tplDom.filmstrip.appendChild(item);
    return item;
  });
}

function tplGoTo(index, dir) {
  const slides = tplState.viewerSlides;
  if (!slides.length) return;
  index = Math.max(0, Math.min(index, slides.length - 1));
  tplState.activeIndex = index;
  const card = slides[index];
  tplState.active = card;

  tplRenderStageImage(card, dir);

  const bucket = card.use_case;
  tplDom.usecase.textContent = bucket && bucket !== "Other"
    ? bucket : "Slide " + (card.slide_number != null ? card.slide_number : index + 1);
  tplDom.stageName.textContent = card.name || card.id;
  tplDom.stageId.textContent = card.id;
  tplFillChips(card);

  tplDom.viewerCounter.textContent = (index + 1) + " / " + slides.length;
  tplDom.stagePrev.disabled = index === 0;
  tplDom.stageNext.disabled = index === slides.length - 1;

  tplUpdateActiveThumb(index);
}

function tplRenderStageImage(card, dir) {
  tplDom.stageFrame.innerHTML = "";
  const src = tplThumbSrc(card);
  let node;
  if (src && isSvgPath(src)) {
    node = document.createElement("object");
    node.data = src;
    node.type = "image/svg+xml";
    node.className = "stage-svg-obj";
    node.setAttribute("aria-label", "Full preview of " + (card.name || card.id));
    node.addEventListener("load", () => injectFontsIntoSvgObject(node));
    node.addEventListener("error", () => {
      tplDom.stageFrame.innerHTML = "";
      const ph = tplPlaceholder(card);
      ph.classList.add("frame-enter");
      tplDom.stageFrame.appendChild(ph);
    });
  } else if (src) {
    node = el("img");
    node.src = src;
    node.alt = "Full preview of " + (card.name || card.id);
    node.addEventListener("error", () => {
      tplDom.stageFrame.innerHTML = "";
      const ph = tplPlaceholder(card);
      ph.classList.add("frame-enter");
      tplDom.stageFrame.appendChild(ph);
    });
  } else {
    node = tplPlaceholder(card);
  }
  node.classList.add("frame-enter");
  if (!reduceMotion && dir === 1) node.classList.add("from-next");
  else if (!reduceMotion && dir === -1) node.classList.add("from-prev");
  tplDom.stageFrame.appendChild(node);
}

function tplUpdateActiveThumb(index) {
  tplState.filmItems.forEach((item, i) => {
    if (i === index) {
      item.setAttribute("aria-current", "true");
      try { item.scrollIntoView({ block: "nearest", inline: "nearest", behavior: reduceMotion ? "auto" : "smooth" }); }
      catch (_) { item.scrollIntoView(false); }
    } else {
      item.removeAttribute("aria-current");
    }
  });
}

function tplFillChips(card) {
  tplDom.stageChips.innerHTML = "";
  (card.intent || []).slice(0, 2).forEach(v => {
    if (!v?.trim()) return;
    tplDom.stageChips.appendChild(el("span", "chip chip-intent", v));
  });
  (card.tags || []).slice(0, 3).forEach(v => {
    if (!v?.trim()) return;
    tplDom.stageChips.appendChild(el("span", "chip", v));
  });
}

function tplCloseModal() {
  if (tplDom.modal.hidden) return;
  document.removeEventListener("keydown", tplOnKeydown);
  const finish = () => {
    tplDom.modal.classList.remove("is-closing");
    tplDom.modal.hidden = true;
    document.body.style.overflow = "";
    if (tplState.lastFocus?.focus) tplState.lastFocus.focus();
    tplState.active = null;
  };
  if (reduceMotion) { finish(); return; }
  tplDom.modal.classList.add("is-closing");
  let done = false;
  const once = () => { if (done) return; done = true; finish(); };
  tplDom.modal.addEventListener("animationend", once, { once: true });
  setTimeout(once, 240);
}

function tplOnKeydown(e) {
  switch (e.key) {
    case "Escape": e.preventDefault(); tplCloseModal(); return;
    case "ArrowRight": case "ArrowDown": case "PageDown":
      e.preventDefault(); tplGoTo(tplState.activeIndex + 1, 1); return;
    case "ArrowLeft": case "ArrowUp": case "PageUp":
      e.preventDefault(); tplGoTo(tplState.activeIndex - 1, -1); return;
    case "Home": e.preventDefault(); tplGoTo(0, -1); return;
    case "End": e.preventDefault(); tplGoTo(tplState.viewerSlides.length - 1, 1); return;
    case "Tab": tplTrapFocus(e); return;
  }
}

function tplTrapFocus(e) {
  const focusables = [...tplDom.modal.querySelectorAll('button, [href], input, [tabindex]:not([tabindex="-1"])')].filter(n => !n.disabled && n.offsetParent !== null);
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

/* Prompts */

function tplSlidePrompt(card) {
  const name = card.name || card.id;
  return "I want to build a slide on top of a published SUN.STUDIO template.\n" +
    "Please use the template “" + name + "” (id: " + card.id + ") " +
    "from the visual library as the base, keep its layout and brand styling, " +
    "and put my content into it.";
}

function tplDeckPrompt(deck, ids) {
  const name = deck.name || "this set";
  return "I want to build a deck on top of a published SUN.STUDIO template set.\n" +
    "Please use the whole “" + name + "” set (" + ids.length + " slides) " +
    "from the visual library as the base, keep the layout and brand styling, " +
    "and put my content into it.\nTemplate ids: " + ids.join(", ");
}

function tplSelectActive() {
  if (!tplState.active) return;
  const card = tplState.active;
  clipboardWrite(tplSlidePrompt(card))
    .then(() => toast("Copied a ready-to-paste prompt for “" + escHtml(card.name || card.id) + "” — paste it to your agent to build on this slide."))
    .catch(() => toast("Copy failed. Template id: " + escHtml(card.id), "error"));
}

function tplSelectDeck(deck) {
  const slides = tplDeckSlides(deck);
  const ids = slides.map(s => s.id).filter(Boolean);
  if (!ids.length) return;
  clipboardWrite(tplDeckPrompt(deck, ids))
    .then(() => toast("Copied a ready-to-paste prompt for the whole “" + escHtml(deck.name || "deck") + "” set (" + ids.length + " slides) — paste it to your agent."))
    .catch(() => toast("Copy failed. Set ids: " + ids.join(", "), "error"));
}

/* Template events */

tplDom.modalClose.addEventListener("click", tplCloseModal);
tplDom.modal.addEventListener("click", e => { if (e.target === tplDom.modal) tplCloseModal(); });
tplDom.selectBtn.addEventListener("click", tplSelectActive);
tplDom.stagePrev.addEventListener("click", () => tplGoTo(tplState.activeIndex - 1, -1));
tplDom.stageNext.addEventListener("click", () => tplGoTo(tplState.activeIndex + 1, 1));
tplDom.viewerSetBtn.addEventListener("click", () => { if (tplState.viewerDeck) tplSelectDeck(tplState.viewerDeck); });

/* Template data loading */

tplLoad()
  .then(result => tplRender(result.data, result.state))
  .catch(err => {
    tplDom.kicker.textContent = "Load error";
    tplShowState("<strong>Could not load template data.</strong> Ensure picker-data.json or picker-data.sample.json is present in template-picker/.");
    console.error(err);
  });


/* ============================================================
   REVIEW TAB — Docling candidate rename / metadata / approval
   Analysis-only: never publishes or mutates the registry.
   ============================================================ */

const reviewState = {
  runs: [],
  extractionId: null,
  sourcePath: null,
  candidates: [],
  currentId: null,
};

const reviewDom = {
  runList: $("#review-run-list"),
  empty: $("#review-empty"),
  content: $("#review-content"),
  title: $("#review-run-title"),
  meta: $("#review-run-meta"),
  candidateList: $("#candidate-list"),
  form: $("#candidate-form"),
  count: $("#count-review"),
  refresh: $("#review-refresh"),
};

const REVIEW_TEXT = [
  ["item_id", "Semantic item ID", "e.g. kickoff-2026-hero-visual"],
  ["display_name", "Display name", "Human-friendly name"],
  ["requested_type", "Requested type", "component / section / template / icon / background"],
  ["component_type", "Component type", "card / chart / table / hero / icon-set …"],
  ["layout_role", "Layout role", "hero / sidebar / footer / full-bleed …"],
];
const REVIEW_LIST = [
  ["semantic_intent", "Semantic intent", "What it is for — one per line or comma-separated"],
  ["content_structure", "Content structure", "title, body, metric, label …"],
  ["tags", "Tags", "free tags for retrieval"],
  ["keywords", "Keywords", "search keywords"],
  ["use_cases", "Use cases", "when to reach for this"],
  ["anti_use_cases", "Anti use-cases (optional)", "when NOT to use this"],
];
const REVIEW_NOTES = [
  ["quality_notes", "Quality notes (optional)"],
  ["retrieval_notes", "Retrieval notes (optional)"],
];

const REVIEW_STATUS_LABEL = {
  pending: "Pending",
  approved_for_extraction: "Approved",
  rejected: "Rejected",
};

function reviewApi(method, path, body) {
  return fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  }).then(
    async r => {
      let data = {};
      try { data = await r.json(); } catch (_) {}
      if (!r.ok || !data.ok) {
        const err = new Error(data.error || ("Request failed (" + r.status + ")"));
        err.errors = data.errors || null;
        err.status = r.status;
        throw err;
      }
      return data;
    },
    () => { throw new Error("Control server not reachable. Start it with: python3 slide-system/catalog/catalog_server.py"); }
  );
}

function reviewLoadRuns() {
  reviewApi("GET", "/api/candidates")
    .then(data => {
      reviewState.runs = data.runs || [];
      const pending = reviewState.runs.reduce((n, r) => n + (r.pending || 0), 0);
      reviewDom.count.textContent = pending;
      reviewRenderRuns();
    })
    .catch(e => {
      reviewDom.runList.innerHTML =
        '<li class="run-error">' + escHtml(e.message) + "</li>";
    });
}

function reviewRenderRuns() {
  reviewDom.runList.innerHTML = "";
  if (!reviewState.runs.length) {
    reviewDom.runList.innerHTML =
      '<li class="run-error">No analysis runs with candidates yet.</li>';
    return;
  }
  reviewState.runs.forEach(run => {
    const li = el("li", "run-item");
    if (run.extraction_id === reviewState.extractionId) li.classList.add("is-active");
    li.innerHTML =
      '<span class="run-name">' + escHtml(run.extraction_id) + "</span>" +
      '<span class="run-badges">' +
        '<span class="run-badge is-pending" title="Pending">' + run.pending + "</span>" +
        '<span class="run-badge is-approved" title="Approved">' + run.approved + "</span>" +
        '<span class="run-badge is-rejected" title="Rejected">' + run.rejected + "</span>" +
      "</span>";
    li.addEventListener("click", () => reviewOpenRun(run.extraction_id));
    reviewDom.runList.appendChild(li);
  });
}

function reviewOpenRun(extractionId) {
  reviewApi("GET", "/api/candidates/" + encodeURIComponent(extractionId))
    .then(data => {
      reviewState.extractionId = data.extraction_id;
      reviewState.sourcePath = data.source_path;
      reviewState.candidates = data.candidates || [];
      reviewState.currentId = null;
      reviewDom.empty.hidden = true;
      reviewDom.content.hidden = false;
      reviewDom.title.textContent = data.extraction_id;
      reviewDom.meta.textContent = "Source: " + (data.source_path || "—") +
        " · " + reviewState.candidates.length + " candidate" +
        (reviewState.candidates.length === 1 ? "" : "s");
      reviewRenderRuns();
      reviewRenderCandidates();
      if (reviewState.candidates.length) reviewSelect(reviewState.candidates[0].candidate_id);
      else reviewDom.form.hidden = true;
    })
    .catch(e => toast(escHtml(e.message), "error"));
}

function reviewRenderCandidates() {
  reviewDom.candidateList.innerHTML = "";
  reviewState.candidates.forEach(c => {
    const status = c.review.review_status || "pending";
    const li = el("li", "candidate-item is-" + status);
    if (c.candidate_id === reviewState.currentId) li.classList.add("is-active");
    li.innerHTML =
      '<span class="cand-id">' + escHtml(c.review.item_id || c.candidate_id) + "</span>" +
      '<span class="cand-sub">' + escHtml(c.candidate_id) + " · p" + escHtml(String(c.slide_or_page)) + "</span>" +
      '<span class="cand-status status-' + status + '">' + (REVIEW_STATUS_LABEL[status] || status) + "</span>";
    li.addEventListener("click", () => reviewSelect(c.candidate_id));
    reviewDom.candidateList.appendChild(li);
  });
}

function reviewCandidate(cid) {
  return reviewState.candidates.find(c => c.candidate_id === cid);
}

function reviewField(label, name, value, placeholder, type) {
  const v = value == null ? "" : value;
  if (type === "list") {
    return '<label class="rf"><span class="rf-label">' + escHtml(label) + "</span>" +
      '<textarea class="rf-input rf-list" name="' + name + '" rows="2" placeholder="' +
      escAttr(placeholder || "") + '">' + escHtml((v || []).join("\n")) + "</textarea></label>";
  }
  if (type === "area") {
    return '<label class="rf"><span class="rf-label">' + escHtml(label) + "</span>" +
      '<textarea class="rf-input" name="' + name + '" rows="3" placeholder="' +
      escAttr(placeholder || "") + '">' + escHtml(v) + "</textarea></label>";
  }
  return '<label class="rf"><span class="rf-label">' + escHtml(label) + "</span>" +
    '<input class="rf-input" name="' + name + '" type="text" value="' + escAttr(v) +
    '" placeholder="' + escAttr(placeholder || "") + '"></label>';
}

function reviewSelect(cid) {
  reviewState.currentId = cid;
  reviewRenderCandidates();
  const c = reviewCandidate(cid);
  if (!c) return;
  const r = c.review;
  const region = c.region || {};
  const status = r.review_status || "pending";

  let html =
    '<div class="cf-context">' +
      '<div class="cf-ctx-row"><span>Candidate</span><code>' + escHtml(c.candidate_id) + "</code></div>" +
      '<div class="cf-ctx-row"><span>Detected as</span><code>' + escHtml(c.detected_type) + "</code></div>" +
      '<div class="cf-ctx-row"><span>Slide / page</span><code>' + escHtml(String(c.slide_or_page)) + "</code></div>" +
      '<div class="cf-ctx-row"><span>Region</span><code>x ' + reviewNum(region.x) + " · y " + reviewNum(region.y) +
        " · w " + reviewNum(region.width) + " · h " + reviewNum(region.height) + "</code></div>" +
      (c.detected_intent && c.detected_intent.length
        ? '<div class="cf-ctx-row"><span>Detected text</span><code>' + escHtml(c.detected_intent.join(" / ")) + "</code></div>"
        : "") +
      '<div class="cf-ctx-row"><span>Status</span><span class="cand-status status-' + status + '">' +
        (REVIEW_STATUS_LABEL[status] || status) + "</span></div>" +
      (r.reject_reason ? '<div class="cf-ctx-row"><span>Reject reason</span><code>' + escHtml(r.reject_reason) + "</code></div>" : "") +
    "</div>";

  html += '<form class="cf-form" autocomplete="off">';
  REVIEW_TEXT.forEach(([name, label, ph]) => html += reviewField(label, name, r[name], ph));
  html += reviewField("Visual summary", "visual_summary", r.visual_summary, "What it looks like, in a sentence or two.", "area");
  REVIEW_LIST.forEach(([name, label, ph]) => html += reviewField(label, name, r[name], ph, "list"));
  REVIEW_NOTES.forEach(([name, label]) => html += reviewField(label, name, r[name], "", "area"));
  html += "</form>";

  html += '<div class="cf-errors" id="cf-errors" hidden></div>';
  html +=
    '<div class="cf-actions">' +
      '<button type="button" class="manage-btn" id="cf-save">Save draft</button>' +
      '<button type="button" class="manage-btn manage-btn-primary" id="cf-approve">Approve for extraction</button>' +
      '<div class="cf-reject"><input type="text" id="cf-reason" class="rf-input" placeholder="Reason to reject…">' +
        '<button type="button" class="manage-btn manage-btn-danger" id="cf-reject">Reject</button></div>' +
    "</div>";

  reviewDom.form.hidden = false;
  reviewDom.form.innerHTML = html;

  $("#cf-save").addEventListener("click", () => reviewSave(cid));
  $("#cf-approve").addEventListener("click", () => reviewApprove(cid));
  $("#cf-reject").addEventListener("click", () => reviewReject(cid));
}

function reviewNum(v) {
  return v == null ? "—" : (Math.round(Number(v) * 1000) / 1000).toString();
}

function reviewCollect() {
  const form = reviewDom.form.querySelector(".cf-form");
  const metadata = {};
  form.querySelectorAll("[name]").forEach(node => { metadata[node.name] = node.value; });
  return metadata;
}

function reviewShowErrors(errors) {
  const box = $("#cf-errors");
  if (!box) return;
  if (!errors || !errors.length) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  box.innerHTML = "<strong>Can’t approve yet:</strong><ul>" +
    errors.map(e => "<li>" + escHtml(e) + "</li>").join("") + "</ul>";
}

function reviewAfterMutation(cid, review, message) {
  const c = reviewCandidate(cid);
  if (c) { c.review = review; c.saved = true; }
  reviewRenderCandidates();
  reviewLoadRuns();
  toast(message);
}

function reviewSave(cid) {
  reviewShowErrors(null);
  reviewApi("PATCH", "/api/candidates/" + encodeURIComponent(reviewState.extractionId) +
    "/" + encodeURIComponent(cid), { metadata: reviewCollect() })
    .then(data => { reviewAfterMutation(cid, data.review, "Saved draft for " + escHtml(cid) + "."); reviewSelect(cid); })
    .catch(e => toast(escHtml(e.message), "error"));
}

function reviewApprove(cid) {
  reviewShowErrors(null);
  // Save the current edits first so approval validates exactly what is shown.
  reviewApi("PATCH", "/api/candidates/" + encodeURIComponent(reviewState.extractionId) +
    "/" + encodeURIComponent(cid), { metadata: reviewCollect() })
    .then(() => reviewApi("POST", "/api/candidates/" + encodeURIComponent(reviewState.extractionId) +
      "/" + encodeURIComponent(cid) + "/approve", {}))
    .then(data => {
      reviewAfterMutation(cid, data.review, "Approved — wrote " + escHtml(data.approved_request_path));
      reviewSelect(cid);
    })
    .catch(e => {
      if (e.errors) { reviewShowErrors(e.errors); toast("Fix the listed fields, then approve.", "error"); }
      else toast(escHtml(e.message), "error");
    });
}

function reviewReject(cid) {
  const reason = ($("#cf-reason").value || "").trim();
  if (!reason) { $("#cf-reason").focus(); toast("Add a short reason to reject.", "error"); return; }
  reviewApi("POST", "/api/candidates/" + encodeURIComponent(reviewState.extractionId) +
    "/" + encodeURIComponent(cid) + "/reject", { reason })
    .then(data => { reviewAfterMutation(cid, data.review, "Rejected " + escHtml(cid) + "."); reviewSelect(cid); })
    .catch(e => toast(escHtml(e.message), "error"));
}

if (reviewDom.refresh) reviewDom.refresh.addEventListener("click", reviewLoadRuns);
