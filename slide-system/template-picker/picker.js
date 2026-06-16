/* ============================================================
   SUN.STUDIO Template Picker — vanilla, no build step.
   Loads ./picker-data.json (real, Phase 3) and falls back to
   ./picker-data.sample.json (checked-in fixture) so the UI
   renders before any template is published.

   Two-level navigation:
     1. SETS view   — a gallery of template SETS (source decks),
                      each shown as a stacked "deck cover" card.
      2. DETAIL view — click a set to open the full deck: every
                       slide as a card, plus "Copy prompt" (whole set).
   Smooth scrolling is used on every view transition (and on
   in-page anchors via CSS), unless the user prefers reduced motion.
   ============================================================ */
(function () {
  "use strict";

  var els = {
    sourcePill: document.getElementById("source-pill"),
    count: document.getElementById("template-count"),
    jumpNav: document.getElementById("jump-nav"),
    heroLede: document.getElementById("hero-lede"),
    gallery: document.getElementById("gallery"),
    stateMessage: document.getElementById("state-message"),
    modal: document.getElementById("modal"),
    modalClose: document.getElementById("modal-close"),
    viewerDeck: document.getElementById("viewer-deck"),
    viewerCounter: document.getElementById("viewer-counter"),
    viewerSetBtn: document.getElementById("viewer-setbtn"),
    filmstrip: document.getElementById("filmstrip"),
    stageFrame: document.getElementById("stage-frame"),
    stagePrev: document.getElementById("stage-prev"),
    stageNext: document.getElementById("stage-next"),
    usecase: document.getElementById("stage-usecase"),
    title: document.getElementById("stage-name"),
    id: document.getElementById("stage-id"),
    chips: document.getElementById("stage-chips"),
    selectBtn: document.getElementById("select-btn"),
    toastStack: document.getElementById("toast-stack"),
  };

  var state = {
    decks: [],
    view: "sets", // "sets" | "detail"
    activeDeck: null,
    active: null,
    viewerSlides: [],
    viewerDeck: null,
    activeIndex: 0,
    filmItems: [],
    lastFocus: null,
    toastTimer: null,
  };

  var reduceMotion =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- data loading with fixture fallback ---------- */
  function load() {
    return fetchJson("./picker-data.json")
      .then(function (data) {
        return { data: data, state: "live" };
      })
      .catch(function () {
        return fetchJson("./picker-data.sample.json").then(function (data) {
          return { data: data, state: "fixture" };
        });
      });
  }

  function fetchJson(url) {
    return fetch(url, { cache: "no-store" }).then(function (res) {
      if (!res.ok) throw new Error(url + " -> " + res.status);
      return res.json();
    });
  }

  /* ---------- helpers ---------- */
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function thumbSrc(card) {
    if (!card) return null;
    var t = card.thumbnail;
    if (t && String(t).trim() !== "") return t;
    if (card.preview && String(card.preview).trim() !== "") return card.preview;
    return null;
  }

  function deckSlides(deck) {
    return (deck && deck.slides) || [];
  }
  function deckAnchor(deck, i) {
    return "deck-" + (deck.deck_id || i);
  }

  function smoothScrollTo(y) {
    try {
      window.scrollTo({ top: y, behavior: reduceMotion ? "auto" : "smooth" });
    } catch (e) {
      window.scrollTo(0, y);
    }
  }

  // Accept either the new deck-grouped shape or a flat templates list.
  function decksOf(payload) {
    if (payload && payload.decks && payload.decks.length) return payload.decks;
    var templates = (payload && payload.templates) || [];
    if (!templates.length) return [];
    return [
      {
        deck_id: "all",
        name: "Full-slide templates",
        slides: templates,
        slide_count: templates.length,
      },
    ];
  }

  /* ---------- top-level render ---------- */
  function render(payload, sourceState) {
    state.decks = decksOf(payload).filter(function (d) {
      return deckSlides(d).length;
    });
    var total = state.decks.reduce(function (n, d) {
      return n + deckSlides(d).length;
    }, 0);

    els.count.textContent = String(total);
    els.sourcePill.setAttribute("data-state", sourceState);
    els.sourcePill.textContent =
      sourceState === "fixture"
        ? "Sample data"
        : sourceState === "live"
          ? "Live library"
          : "Loaded";

    if (!total) {
      showState(
        "<strong>No published templates yet.</strong> " +
          "Publish templates into the visual library, then regenerate picker-data.json.",
      );
      return;
    }
    els.stateMessage.hidden = true;
    showSets(false);
  }

  function clearGallery() {
    Array.prototype.slice
      .call(
        els.gallery.querySelectorAll(
          ".set-section, .deck-section, .detail-bar",
        ),
      )
      .forEach(function (n) {
        n.remove();
      });
  }

  /* ---------- SETS view ---------- */
  function showSets(scroll) {
    state.view = "sets";
    state.activeDeck = null;
    clearGallery();
    els.jumpNav.innerHTML = "";
    els.jumpNav.hidden = true;

    if (els.heroLede) {
      els.heroLede.textContent =
        "Published templates, grouped into full deck sets. Pick a set to " +
        "browse every slide, preview it as the original, and build a deck on top of it.";
    }

    var section = el("section", "set-section");
    var head = el("div", "set-section-head");
    head.appendChild(
      el(
        "p",
        "section-kicker",
        state.decks.length +
          (state.decks.length === 1 ? " template set" : " template sets"),
      ),
    );
    head.appendChild(el("h2", null, "Template sets"));
    section.appendChild(head);

    var grid = el("div", "set-grid");
    state.decks.forEach(function (deck, i) {
      grid.appendChild(buildSetCard(deck, i));
    });
    section.appendChild(grid);
    els.gallery.appendChild(section);

    if (scroll !== false) smoothScrollTo(0);
  }

  function buildSetCard(deck, i) {
    var slides = deckSlides(deck);
    var btn = el("button", "set-card");
    btn.type = "button";
    btn.setAttribute(
      "aria-label",
      "Open the " +
        (deck.name || "deck") +
        " set, " +
        slides.length +
        " slides",
    );

    // Stacked cover: two ghost cards behind the front cover image.
    var cover = el("div", "set-cover");
    cover.appendChild(el("span", "set-cover-layer set-cover-back"));
    cover.appendChild(el("span", "set-cover-layer set-cover-mid"));

    var front = el("div", "set-cover-front");
    var src = thumbSrc(slides[0]);
    if (src) {
      var img = el("img");
      img.src = src;
      img.alt = "Cover slide of the " + (deck.name || "deck") + " set";
      img.loading = "lazy";
      img.addEventListener("error", function () {
        img.remove();
        front.appendChild(placeholder(slides[0] || { name: deck.name }));
      });
      front.appendChild(img);
    } else {
      front.appendChild(placeholder(slides[0] || { name: deck.name }));
    }
    cover.appendChild(front);
    cover.appendChild(el("span", "set-count-badge", String(slides.length)));
    btn.appendChild(cover);

    var body = el("div", "set-body");
    body.appendChild(el("p", "set-kicker", "Full deck set"));
    body.appendChild(el("div", "set-name", deck.name || "Deck"));

    var meta = el("div", "set-meta");
    meta.appendChild(
      el(
        "span",
        "set-meta-count",
        slides.length + (slides.length === 1 ? " slide" : " slides"),
      ),
    );
    var open = el("span", "set-open");
    open.appendChild(document.createTextNode("Open set"));
    open.appendChild(el("span", "set-open-arrow", "\u2192"));
    meta.appendChild(open);
    body.appendChild(meta);
    btn.appendChild(body);

    btn.addEventListener("click", function () {
      openDeck(deck, i);
    });
    return btn;
  }

  /* ---------- DETAIL view ---------- */
  function openDeck(deck, i) {
    state.view = "detail";
    state.activeDeck = deck;
    clearGallery();

    if (els.heroLede) {
      els.heroLede.textContent =
        "Open a slide to preview it as the original, copy one slide's id, or " +
        "grab the whole set to build a deck on top of it.";
    }

    // Back bar
    var bar = el("div", "detail-bar");
    var back = el("button", "back-btn");
    back.type = "button";
    back.appendChild(el("span", "back-arrow", "\u2190"));
    back.appendChild(document.createTextNode("All template sets"));
    back.addEventListener("click", function () {
      showSets(true);
    });
    bar.appendChild(back);
    els.gallery.appendChild(bar);

    // Jump nav = set switcher (only meaningful with >1 deck)
    renderJumpNav(deck);

    var slides = deckSlides(deck);
    var anchor = deckAnchor(deck, i);

    var section = el("section", "deck-section");
    section.id = anchor;
    section.setAttribute("aria-labelledby", anchor + "-h");

    var head = el("div", "section-head");
    var heads = el("div", "section-head-text");
    heads.appendChild(
      el(
        "p",
        "section-kicker",
        slides.length > 1 ? "Full deck set" : "Single slide",
      ),
    );
    var h2 = el("h2", null, deck.name || "Deck");
    h2.id = anchor + "-h";
    heads.appendChild(h2);
    head.appendChild(heads);

    var actions = el("div", "section-actions");
    actions.appendChild(
      el(
        "span",
        "section-count",
        slides.length + (slides.length === 1 ? " slide" : " slides"),
      ),
    );
    var setBtn = el("button", "set-btn", "Copy prompt");
    setBtn.type = "button";
    setBtn.setAttribute("aria-label", "Copy a ready-to-paste prompt for the whole set");
    setBtn.addEventListener("click", function () {
      selectDeck(deck);
    });
    actions.appendChild(setBtn);
    head.appendChild(actions);
    section.appendChild(head);

    var grid = el("div", "card-grid");
    slides.forEach(function (card, idx) {
      card._deckName = deck.name;
      grid.appendChild(buildCard(card, deck, idx));
    });
    section.appendChild(grid);
    els.gallery.appendChild(section);

    smoothScrollTo(0);
    if (back.focus) back.focus();
  }

  function renderJumpNav(activeDeck) {
    els.jumpNav.innerHTML = "";
    if (state.decks.length < 2) {
      els.jumpNav.hidden = true;
      return;
    }
    els.jumpNav.hidden = false;
    state.decks.forEach(function (deck, i) {
      var a = el("button", "jump-pill");
      a.type = "button";
      if (deck === activeDeck) a.setAttribute("aria-current", "true");
      a.appendChild(document.createTextNode(deck.name || "Deck"));
      a.appendChild(el("span", "n", String(deckSlides(deck).length)));
      a.addEventListener("click", function () {
        if (deck !== state.activeDeck) openDeck(deck, i);
        else smoothScrollTo(0);
      });
      els.jumpNav.appendChild(a);
    });
  }

  function buildCard(card, deck, index) {
    var btn = el("button", "card");
    btn.type = "button";
    btn.setAttribute("aria-haspopup", "dialog");
    btn.setAttribute("aria-label", "Open template " + (card.name || card.id));

    var thumb = el("div", "thumb");
    var src = thumbSrc(card);
    if (src) {
      var img = el("img");
      img.src = src;
      img.alt = "Preview of the " + (card.name || card.id) + " template";
      img.loading = "lazy";
      img.addEventListener("error", function () {
        img.remove();
        thumb.insertBefore(placeholder(card), thumb.firstChild);
      });
      thumb.appendChild(img);
    } else {
      thumb.appendChild(placeholder(card));
    }
    if (card.slide_number != null) {
      thumb.appendChild(el("span", "slide-badge", String(card.slide_number)));
    }
    btn.appendChild(thumb);

    var body = el("div", "card-body");
    body.appendChild(el("div", "card-name", card.name || card.id));

    var chips = el("div", "chip-row");
    (card.intent || []).slice(0, 2).forEach(function (i) {
      chips.appendChild(el("span", "chip chip-intent", i));
    });
    (card.tags || []).slice(0, 3).forEach(function (t) {
      chips.appendChild(el("span", "chip", t));
    });
    if (chips.childNodes.length) body.appendChild(chips);

    btn.appendChild(body);

    btn.addEventListener("click", function () {
      openModal(deck, index, btn);
    });
    return btn;
  }

  function placeholder(card) {
    var ph = el("div", "thumb-placeholder");
    var initials = ((card && (card.name || card._deckName)) || "T")
      .slice(0, 1)
      .toUpperCase();
    ph.appendChild(el("span", "ph-mark", initials));
    ph.appendChild(el("span", "ph-label", "No preview"));
    return ph;
  }

  function showState(html) {
    els.stateMessage.innerHTML = html;
    els.stateMessage.hidden = false;
  }

  /* ---------- slide viewer ---------- */
  function openModal(deck, index, trigger) {
    state.viewerDeck = deck;
    state.viewerSlides = deckSlides(deck);
    state.lastFocus = trigger || document.activeElement;
    if (!state.viewerSlides.length) return;

    els.viewerDeck.textContent = deck.name || "Deck";
    renderFilmstrip(deck);

    els.modal.classList.remove("is-closing");
    els.modal.hidden = false;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeydown);

    goTo(index, 0);
    els.modalClose.focus();
  }

  function renderFilmstrip(deck) {
    var slides = deckSlides(deck);
    els.filmstrip.innerHTML = "";
    state.filmItems = slides.map(function (card, i) {
      var item = el("button", "film-item");
      item.type = "button";
      item.setAttribute(
        "aria-label",
        "Go to slide " + (i + 1) + ": " + (card.name || card.id),
      );

      var thumb = el("div", "film-thumb");
      var src = thumbSrc(card);
      if (src) {
        var img = el("img");
        img.src = src;
        img.alt = "";
        img.loading = "lazy";
        img.addEventListener("error", function () {
          img.remove();
          var ph = placeholder(card);
          ph.classList.add("film-ph");
          thumb.appendChild(ph);
        });
        thumb.appendChild(img);
      } else {
        var ph = placeholder(card);
        ph.classList.add("film-ph");
        thumb.appendChild(ph);
      }
      thumb.appendChild(
        el(
          "span",
          "film-num",
          String(card.slide_number != null ? card.slide_number : i + 1),
        ),
      );
      item.appendChild(thumb);

      item.addEventListener("click", function () {
        goTo(i, i > state.activeIndex ? 1 : i < state.activeIndex ? -1 : 0);
      });
      els.filmstrip.appendChild(item);
      return item;
    });
  }

  function goTo(index, dir) {
    var slides = state.viewerSlides;
    if (!slides.length) return;
    index = Math.max(0, Math.min(index, slides.length - 1));
    state.activeIndex = index;
    var card = slides[index];
    state.active = card;

    renderStageImage(card, dir);

    // Kicker shows the use-case bucket (Cover/Section/Data/Content/Closing);
    // the slide's position is already in the "N / M" counter + filmstrip. Fall
    // back to "Slide N" when the bucket is missing or the catch-all "Other".
    var bucket = card.use_case;
    els.usecase.textContent =
      bucket && bucket !== "Other"
        ? bucket
        : "Slide " + (card.slide_number != null ? card.slide_number : index + 1);
    els.title.textContent = card.name || card.id;
    els.id.textContent = card.id;
    fillChips(card);

    els.viewerCounter.textContent = index + 1 + " / " + slides.length;
    els.stagePrev.disabled = index === 0;
    els.stageNext.disabled = index === slides.length - 1;

    updateActiveThumb(index);
  }

  function renderStageImage(card, dir) {
    els.stageFrame.innerHTML = "";
    var src = thumbSrc(card);
    var node;
    if (src) {
      node = el("img");
      node.src = src;
      node.alt = "Full preview of " + (card.name || card.id);
      node.addEventListener("error", function () {
        els.stageFrame.innerHTML = "";
        var ph = placeholder(card);
        ph.classList.add("frame-enter");
        els.stageFrame.appendChild(ph);
      });
    } else {
      node = placeholder(card);
    }
    node.classList.add("frame-enter");
    if (!reduceMotion && dir === 1) node.classList.add("from-next");
    else if (!reduceMotion && dir === -1) node.classList.add("from-prev");
    els.stageFrame.appendChild(node);
  }

  function updateActiveThumb(index) {
    state.filmItems.forEach(function (item, i) {
      if (i === index) {
        item.setAttribute("aria-current", "true");
        try {
          item.scrollIntoView({
            block: "nearest",
            inline: "nearest",
            behavior: reduceMotion ? "auto" : "smooth",
          });
        } catch (e) {
          item.scrollIntoView(false);
        }
      } else {
        item.removeAttribute("aria-current");
      }
    });
  }

  function next() {
    goTo(state.activeIndex + 1, 1);
  }
  function prev() {
    goTo(state.activeIndex - 1, -1);
  }

  function fillChips(card) {
    els.chips.innerHTML = "";
    (card.intent || []).slice(0, 2).forEach(function (v) {
      if (v == null || String(v).trim() === "") return;
      els.chips.appendChild(el("span", "chip chip-intent", v));
    });
    (card.tags || []).slice(0, 3).forEach(function (v) {
      if (v == null || String(v).trim() === "") return;
      els.chips.appendChild(el("span", "chip", v));
    });
  }

  function closeModal() {
    if (els.modal.hidden) return;
    document.removeEventListener("keydown", onKeydown);
    var finish = function () {
      els.modal.classList.remove("is-closing");
      els.modal.hidden = true;
      document.body.style.overflow = "";
      if (state.lastFocus && state.lastFocus.focus) state.lastFocus.focus();
      state.active = null;
    };
    if (reduceMotion) {
      finish();
      return;
    }
    els.modal.classList.add("is-closing");
    var done = false;
    var once = function () {
      if (done) return;
      done = true;
      finish();
    };
    els.modal.addEventListener("animationend", once, { once: true });
    setTimeout(once, 240);
  }

  function onKeydown(e) {
    switch (e.key) {
      case "Escape":
        e.preventDefault();
        closeModal();
        return;
      case "ArrowRight":
      case "ArrowDown":
      case "PageDown":
        e.preventDefault();
        next();
        return;
      case "ArrowLeft":
      case "ArrowUp":
      case "PageUp":
        e.preventDefault();
        prev();
        return;
      case "Home":
        e.preventDefault();
        goTo(0, -1);
        return;
      case "End":
        e.preventDefault();
        goTo(state.viewerSlides.length - 1, 1);
        return;
      case "Tab":
        trapFocus(e);
        return;
    }
  }

  function trapFocus(e) {
    var focusables = Array.prototype.filter.call(
      els.modal.querySelectorAll(
        'button, [href], input, [tabindex]:not([tabindex="-1"])',
      ),
      function (n) {
        return !n.disabled && n.offsetParent !== null;
      },
    );
    if (!focusables.length) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  /* ---------- copy prompt + clipboard + toast ---------- */
  function slidePrompt(card) {
    var name = card.name || card.id;
    return (
      "I want to build a slide on top of a published SUN.STUDIO template.\n" +
      "Please use the template \u201c" +
      name +
      "\u201d (id: " +
      card.id +
      ") " +
      "from the visual library as the base, keep its layout and brand styling, " +
      "and put my content into it."
    );
  }

  function deckPrompt(deck, ids) {
    var name = deck.name || "this set";
    return (
      "I want to build a deck on top of a published SUN.STUDIO template set.\n" +
      "Please use the whole \u201c" +
      name +
      "\u201d set (" +
      ids.length +
      " slides) " +
      "from the visual library as the base, keep the layout and brand styling, " +
      "and put my content into it.\n" +
      "Template ids: " +
      ids.join(", ")
    );
  }

  function selectActive() {
    if (!state.active) return;
    var card = state.active;
    copyToClipboard(slidePrompt(card))
      .then(function () {
        toast(
          "Copied a ready-to-paste prompt for \u201c" +
            (card.name || card.id) +
            "\u201d \u2014 paste it to your agent to build on this slide.",
        );
      })
      .catch(function () {
        toast("Copy failed. Template id: " + card.id, "error");
      });
  }

  function selectDeck(deck) {
    var slides = deckSlides(deck);
    var ids = slides
      .map(function (s) {
        return s.id;
      })
      .filter(Boolean);
    if (!ids.length) return;
    copyToClipboard(deckPrompt(deck, ids))
      .then(function () {
        toast(
          "Copied a ready-to-paste prompt for the whole \u201c" +
            (deck.name || "deck") +
            "\u201d set (" +
            ids.length +
            " slides) \u2014 paste it to your agent.",
        );
      })
      .catch(function () {
        toast("Copy failed. Set ids: " + ids.join(", "), "error");
      });
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function () {
        return legacyCopy(text);
      });
    }
    return legacyCopy(text);
  }

  function legacyCopy(text) {
    return new Promise(function (resolve, reject) {
      try {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "absolute";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        var ok = document.execCommand("copy");
        document.body.removeChild(ta);
        ok ? resolve() : reject(new Error("execCommand failed"));
      } catch (err) {
        reject(err);
      }
    });
  }

  /* ---------- toast stack ---------- */
  var TOAST_MAX = 3;
  var TOAST_DURATION = 4200;
  var TOAST_EXIT_MS = 320;
  var toastList = []; // newest first: { el, timer, remaining, startedAt }

  var TOAST_ICON_SUCCESS =
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" ' +
    'stroke-linecap="round" stroke-linejoin="round"><path d="M5 10.5l3.5 3.5L15 6.5"/></svg>';
  var TOAST_ICON_ERROR =
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" ' +
    'stroke-linecap="round" stroke-linejoin="round"><path d="M10 6v5M10 14h.01"/></svg>';
  var TOAST_CLOSE_SVG =
    '<svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" ' +
    'stroke-linecap="round"><path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/></svg>';

  function toast(message, type) {
    var kind = type === "error" ? "error" : "success";
    var item = el("div", "toast-item is-" + kind);
    var icon = el("span", "toast-icon");
    icon.innerHTML = kind === "error" ? TOAST_ICON_ERROR : TOAST_ICON_SUCCESS;
    var msg = el("span", "toast-msg", message);
    var x = el("button", "toast-x");
    x.type = "button";
    x.setAttribute("aria-label", "Dismiss");
    x.innerHTML = TOAST_CLOSE_SVG;
    x.addEventListener("click", function () {
      dismissToast(item);
    });
    item.appendChild(icon);
    item.appendChild(msg);
    item.appendChild(x);
    item.addEventListener("pointerenter", function () {
      pauseToast(item);
    });
    item.addEventListener("pointerleave", function () {
      resumeToast(item);
    });

    els.toastStack.appendChild(item);
    var entry = {
      el: item,
      timer: null,
      remaining: TOAST_DURATION,
      startedAt: 0,
    };
    toastList.unshift(entry);

    requestAnimationFrame(function () {
      item.classList.add("is-in");
      restackToasts();
    });
    restackToasts();
    startToastTimer(entry);

    while (toastList.length > TOAST_MAX) {
      dismissToast(toastList[toastList.length - 1].el);
    }
  }

  function startToastTimer(entry) {
    entry.startedAt = Date.now();
    entry.timer = setTimeout(function () {
      dismissToast(entry.el);
    }, entry.remaining);
  }

  function pauseToast(node) {
    var entry = findToast(node);
    if (!entry || !entry.timer) return;
    clearTimeout(entry.timer);
    entry.timer = null;
    entry.remaining = Math.max(
      600,
      entry.remaining - (Date.now() - entry.startedAt),
    );
  }

  function resumeToast(node) {
    var entry = findToast(node);
    if (!entry || entry.timer) return;
    startToastTimer(entry);
  }

  function findToast(node) {
    for (var i = 0; i < toastList.length; i++) {
      if (toastList[i].el === node) return toastList[i];
    }
    return null;
  }

  function restackToasts() {
    toastList.forEach(function (t, i) {
      t.el.style.setProperty("--i", i);
      t.el.style.zIndex = String(TOAST_MAX + 2 - i);
      t.el.classList.toggle("is-buried", i >= TOAST_MAX);
    });
  }

  function dismissToast(node) {
    var idx = -1;
    for (var i = 0; i < toastList.length; i++) {
      if (toastList[i].el === node) {
        idx = i;
        break;
      }
    }
    if (idx === -1) return;
    var entry = toastList.splice(idx, 1)[0];
    if (entry.timer) clearTimeout(entry.timer);
    node.classList.add("is-out");
    node.classList.remove("is-in");
    restackToasts();
    setTimeout(function () {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, TOAST_EXIT_MS);
  }

  /* ---------- wire up ---------- */
  els.modalClose.addEventListener("click", closeModal);
  els.modal.addEventListener("click", function (e) {
    if (e.target === els.modal) closeModal();
  });
  els.selectBtn.addEventListener("click", selectActive);
  els.stagePrev.addEventListener("click", function () {
    prev();
  });
  els.stageNext.addEventListener("click", function () {
    next();
  });
  els.viewerSetBtn.addEventListener("click", function () {
    if (state.viewerDeck) selectDeck(state.viewerDeck);
  });

  load()
    .then(function (result) {
      render(result.data, result.state);
    })
    .catch(function (err) {
      els.sourcePill.setAttribute("data-state", "error");
      els.sourcePill.textContent = "Load error";
      showState(
        "<strong>Could not load template data.</strong> " +
          "Serve this folder over HTTP (for example <code>python3 -m http.server</code>) " +
          "and ensure picker-data.json or picker-data.sample.json is present.",
      );
      if (window.console) console.error(err);
    });
})();
