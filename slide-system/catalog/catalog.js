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
  ['ProximaNova-Regular',    'Proxima-Nova-Regular.otf'],
  ['ProximaNova-Medium',     'Proxima-Nova-Medium.otf'],
  ['ProximaNova-Semibold',   'Proxima-Nova-SemiBold.otf'],
  ['ProximaNova-SemiboldIt', 'Proxima-Nova-SemiBold-Italic.otf'],
  ['ProximaNova-Bold',       'Proxima-Nova-Bold.otf'],
  ['ProximaNova-BoldIt',     'Proxima-Bold-Italic.otf'],
  ['ProximaNova-Extrabld',   'Proxima-Black.otf'],
  ['ProximaNova-ExtrabldIt', 'Proxima-ExtraBold-Italic.otf'],
].map(([family, file]) =>
  `@font-face{font-family:"${family}";src:url("${BRAND_FONT_DIR}${file}")format("opentype")}`
).join("\n");

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
const sectionComponents = $("#section-components");
const sectionTemplates = $("#section-templates");
let activeSection = "components";

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
    sectionComponents.hidden = section !== "components";
    sectionComponents.classList.toggle("is-active", section === "components");
    sectionTemplates.hidden = section !== "templates";
    sectionTemplates.classList.toggle("is-active", section === "templates");
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
  modalManage: $("#modal-manage"),
};

/* URL resolution */

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

function compCompatMatches(item) {
  const target = compDom.compatFilter.value;
  if (!target) return true;
  return ["supported", "hybrid", "raster"].includes(item.compatibility?.[target]);
}

function compFilterItems() {
  const term = compDom.search.value.trim().toLowerCase();
  compState.filtered = compState.items.filter(item => {
    if (item.type === "template") return false;
    if (!compStatusMatches(item)) return false;
    if (compDom.typeFilter.value && item.type !== compDom.typeFilter.value) return false;
    if (compDom.brandFilter.value && item.brand !== compDom.brandFilter.value) return false;
    if (!compCompatMatches(item)) return false;
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

  if (hasImage) {
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

  const statusClass = item.status === "published" ? "published" : "draft";
  const statusLabel = item.status === "published" ? "Published" : "Draft";
  compDom.modalId.innerHTML = `
    <span>${escHtml(item.id)} &middot; v${escHtml(item.version)}</span>
    <span class="status-dot ${statusClass}">${statusLabel}</span>`;

  compRenderInfoPanel(item);
  compRenderCompatPanel(item);
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
  [compDom.panelPreview, compDom.panelInfo, compDom.panelCompat].forEach(p => p.classList.remove("is-active"));
  const panel = $(`#panel-${id}`);
  if (panel) panel.classList.add("is-active");
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

/* Compat panel */

function compRenderCompatPanel(item) {
  const targets = ["html", "pptx", "pdf", "canva"];
  const compat = item.compatibility || {};
  compDom.panelCompat.innerHTML = '<div class="compat-grid">' + targets.map(t => {
    const val = compat[t] || "untested";
    const icon = compCompatIcon(val);
    const cls = "compat-" + (val === "supported" ? "supported" : val === "hybrid" ? "hybrid" : val === "raster" ? "raster" : "untested");
    return '<div class="compat-cell ' + cls + '"><div class="compat-icon">' + icon + '</div><div class="compat-label">' + t + '</div><div class="compat-status">' + val + "</div></div>";
  }).join("") + "</div>";
}

function compCompatIcon(val) {
  if (val === "supported") return '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 10l3.5 3.5L15 7"/></svg>';
  if (val === "hybrid") return '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="10" cy="10" r="6"/><path d="M10 4a6 6 0 010 12" fill="currentColor" opacity=".3"/></svg>';
  if (val === "raster") return '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="5" width="14" height="10" rx="2"/><circle cx="7" cy="9" r="1.5" fill="currentColor"/><path d="M3 13l4-3 3 2 4-4 3 3"/></svg>';
  return '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 10h8"/></svg>';
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
  [compDom.typeFilter, compDom.brandFilter, compDom.compatFilter].forEach(sel => {
    sel.classList.toggle("has-value", !!sel.value);
  });
}

function compClearFilters() {
  compDom.search.value = "";
  compDom.typeFilter.value = "";
  compDom.brandFilter.value = "";
  compDom.compatFilter.value = "";
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
  const isDraft = item.status !== "published";
  compConfirmDialog({
    title: isDraft ? "Delete draft permanently?" : "Delete published item?",
    body: isDraft
      ? `Draft <strong>${escHtml(item.name)}</strong> lives in gitignored <code>outputs/</code> and <strong>cannot be recovered from git</strong>. This permanently removes its extraction folder.`
      : `This removes <strong>${escHtml(item.name)}</strong> from the library folder and registry. It is git-tracked, so you can restore it with <code>git checkout</code>.`,
    confirmLabel: isDraft ? "Delete forever" : "Delete",
    danger: true,
    requireType: isDraft ? "DELETE" : null,
  }).then(ok => {
    if (!ok) return;
    compBusy(btn, true);
    compApi("/api/delete", { id: item.id, status: item.status })
      .then(() => {
        compCloseModal();
        return compLoadData().then(() => toast(`Deleted <code>${escHtml(item.id)}</code>.`));
      })
      .catch(e => toast(escHtml(e.message), "error"))
      .finally(() => compBusy(btn, false));
  });
}

function compConfirmDialog(opts) {
  return new Promise(resolve => {
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
      input.addEventListener("input", () => { okBtn.disabled = input.value.trim() !== opts.requireType; });
      setTimeout(() => input.focus(), 60);
    }
    okBtn.addEventListener("click", () => { if (!okBtn.disabled) close(true); });
    cancelBtn.addEventListener("click", () => close(false));
    overlay.addEventListener("click", e => { if (e.target === overlay) close(false); });
    function onKey(e) {
      if (e.key === "Escape") { e.stopPropagation(); close(false); }
      else if (e.key === "Enter" && !okBtn.disabled && document.activeElement !== cancelBtn) {
        e.stopPropagation(); close(true);
      }
    }
    document.addEventListener("keydown", onKey, true);
  });
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

[compDom.search, compDom.typeFilter, compDom.brandFilter, compDom.compatFilter].forEach(el => {
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
  if (document.querySelector(".confirm-overlay")) return;
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
  if (src) {
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
  if (src) {
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
    if (src) {
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
  if (src) {
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
