const state = { items: [], status: "published" };
const groups = document.querySelector("#groups");
const summary = document.querySelector("#summary");
const search = document.querySelector("#search");
const typeFilter = document.querySelector("#type-filter");
const brandFilter = document.querySelector("#brand-filter");
const compatibilityFilter = document.querySelector("#compatibility-filter");
const dialog = document.querySelector("#detail-dialog");
const detail = document.querySelector("#detail");

const statusMatches = (item) =>
  state.status === "published"
    ? item.status === "published"
    : ["staging", "qa"].includes(item.status);

const supportMatches = (item) => {
  const target = compatibilityFilter.value;
  if (!target) return true;
  return ["supported", "hybrid", "raster"].includes(item.compatibility?.[target]);
};

function previewUrl(path) {
  if (!path) return null;
  if (path.startsWith("/") || path.startsWith("http")) return path;
  return `../../${path}`;
}

function render() {
  const term = search.value.trim().toLowerCase();
  const filtered = state.items.filter((item) => {
    const haystack = JSON.stringify([
      item.id, item.name, item.intent, item.tags, item.source, item.limitations,
    ]).toLowerCase();
    return statusMatches(item)
      && (!term || haystack.includes(term))
      && (!typeFilter.value || item.type === typeFilter.value)
      && (!brandFilter.value || item.brand === brandFilter.value)
      && supportMatches(item);
  });
  summary.textContent = `${filtered.length} matching item${filtered.length === 1 ? "" : "s"}.`;
  groups.replaceChildren();
  const byGroup = filtered.reduce((result, item) => {
    const key = item.category || item.type;
    (result[key] ||= []).push(item);
    return result;
  }, {});
  Object.keys(byGroup).sort().forEach((name) => {
    const section = document.createElement("section");
    section.className = "group";
    section.innerHTML = `<h2>${name}</h2><div class="grid"></div>`;
    const grid = section.querySelector(".grid");
    byGroup[name].forEach((item) => grid.append(createTile(item)));
    groups.append(section);
  });
}

function createTile(item) {
  const tile = document.createElement("article");
  tile.className = "tile";
  tile.tabIndex = 0;
  const url = previewUrl(item.paths?.preview);
  const canFrame = url && /\.html?(?:$|\?)/i.test(url);
  tile.innerHTML = `
    <div class="preview">
      ${canFrame ? `<iframe src="${url}" title="${item.name} preview"></iframe>` : `<span class="preview-fallback">${item.type}</span>`}
    </div>
    <div class="meta">
      <div class="id">${item.id} · ${item.version}</div>
      <h3>${item.name}</h3>
      <div>${(item.intent || []).join(", ")}</div>
      <div class="badges">
        <span class="badge">${item.status}</span>
        ${Object.entries(item.compatibility || {}).map(([key, value]) => `<span class="badge">${key}: ${value}</span>`).join("")}
      </div>
    </div>`;
  const open = () => {
    detail.innerHTML = `<h2>${item.name}</h2><p class="id">${item.id} · ${item.version}</p><pre>${JSON.stringify(item, null, 2)}</pre>`;
    dialog.showModal();
  };
  tile.addEventListener("click", open);
  tile.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") open();
  });
  return tile;
}

function addOptions(select, values) {
  [...new Set(values.filter(Boolean))].sort().forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  });
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("is-active"));
    tab.classList.add("is-active");
    state.status = tab.dataset.status;
    render();
  });
});
[search, typeFilter, brandFilter, compatibilityFilter].forEach((control) =>
  control.addEventListener("input", render));
document.querySelector("#close-dialog").addEventListener("click", () => dialog.close());

fetch("catalog-data.json")
  .then((response) => {
    if (!response.ok) throw new Error(`Catalog data failed: ${response.status}`);
    return response.json();
  })
  .then((data) => {
    state.items = data.items;
    addOptions(typeFilter, state.items.map((item) => item.type));
    addOptions(brandFilter, state.items.map((item) => item.brand));
    render();
  })
  .catch((error) => {
    summary.textContent = error.message;
  });
