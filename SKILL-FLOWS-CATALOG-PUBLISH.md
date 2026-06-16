# Cây luồng — Catalog Publish / Delete trực tiếp trên web (non-tech)

> Cây workflow cho tính năng **publish / xoá visual item thẳng trên trang catalog**,
> bổ sung vào hệ `SKILL-FLOWS.md`. Mục tiêu: user **non-tech** chỉ cần
> *chạy component-extractor → mở catalog coi preview → bấm Publish → xong*.
> **Đã triển khai & verify (2026-06-16)** — không phải đích đến tương lai.
>
> Ký hiệu: `[GIỮ]` không đổi · `[FIX]` sửa hành vi cũ · `[MỚI]` thêm mới

---

## 1. /component-extractor — KHÔNG ĐỔI

Extraction vẫn manual-only, sinh ra `outputs/component-extractions/<batch>/items/<item>/`
với `artifact/` + `evidence/` + `mapping.json` (+ `gallery.html` batch-level làm mặt review).
`preview/` **KHÔNG** tạo lúc extract — theo đúng SKILL component-extractor (§6): preview
được tạo *lúc publish*. Đó là lý do publish phải tự lo preview (xem [P2] bên dưới).

---

## 2. Luồng người dùng end-to-end (non-tech, 1 click)

```
[AI] chạy /component-extractor                                  [GIỮ]
        │  → draft items nằm ở outputs/component-extractions/...
        ▼
[A] Regen catalog data  (TỰ ĐỘNG — không phải bước user)        [FIX] build_component_catalog.py
        │   extractor (SKILL §5) đã chạy; server cũng tự regen          + publish_readiness{ready,blockers}
        │   sau mỗi mutate. Chạy tay chỉ khi sửa data ngoài luồng.      + deletable (chỉ library/) + staging_dir
        │                                                               + preview fallback cho published
        ▼
[B] Mở control server (KHÔNG dùng http.server)                  [MỚI] catalog_server.py
        │   python3 slide-system/catalog/catalog_server.py             bind 127.0.0.1:8799, serve repo
        │   → http://127.0.0.1:8799/slide-system/catalog/             + 2 endpoint POST /api/*
        ▼
[C] User mở tab Draft → click 1 item                            [GIỮ] modal Preview/Info/Compat
        │   • ảnh preview xem ngay (lấy từ evidence/source-with-text.svg)
        │   • thanh quản lý (modal-manage):
        │       Draft     → [ Publish ] (cam)  [ Delete draft ] (đỏ)
        │       Published → [ Delete ] (đỏ)
        ▼
[D] Bấm PUBLISH  ── 1 click, KHÔNG dialog                       [MỚI] onPublish() → POST /api/publish
        │   (xem cây §3)                                               busy spinner → toast → reload
        ▼
[E] Item chuyển Draft → Published, modal đóng, toast "Published" [MỚI]
```

Xoá đi nhánh phụ cũ (đã bỏ cho gọn non-tech): nút **Generate preview** riêng,
dòng note "missing preview", và **dialog xác nhận khi Publish**. Publish giờ 1 click thẳng.

---

## 3. POST /api/publish — cây server (catalog_server.py)

```
nhận { id }
        │
        ├─ ID không khớp regex stable-id ───────────────► 400 "Invalid item id"   [MỚI] guard
        │
        ▼
[P1] find_staging(id): quét outputs/.../items/*/mapping.json    [MỚI]
        │   khớp candidate_stable_id | id | tên folder
        │   không thấy ───────────────────────────────► 404 "Draft item not found"
        ▼
[P2] preview/ thiếu? → TỰ TẠO                                   [MỚI] generate_item_preview.py
        │   python3 generate_item_preview.py --item-dir <item>          (lý do: extract không tạo
        │     ├─ type == template ─► generate_template_preview.py        preview/, publish phải lo)
        │     └─ atomic (component/asset/style/icon/…)
        │             render_svg.js (Playwright) render
        │            evidence/source-with-text.svg | artifact/visual.svg
        │            → preview/thumbnail.png + preview.html
        │   gen fail ─────────────────────────────────► 500 "Could not build a preview"
        ▼
[P3] Ghi duyệt: mapping.approval = approved                     [MỚI] CLICK PUBLISH = sự duyệt
        │   { status:"approved", approved_by:"catalog-ui", approved_at }      của con người (gate
        │                                                                      approval của script đòi)
        ▼
[P4] publish_extraction.py --extraction-dir <batch> --item-id <folder>  [GIỮ] script promote sẵn có
        │     ├─ copy artifact/ → library/<TYPE_FOLDER>/<stable_id>/
        │     ├─ copy preview/ + evidence/ vào đó
        │     ├─ sửa evidence SVG: "../artifact/assets/" → "../assets/"
        │     ├─ upsert entry vào registries/visual-library.json
        │     ├─ mapping.status = published (+ published_at, published_path)
        │     └─ append registries/extraction-history.json
        │   script FAIL (gate untested compat / thiếu evidence) ─► 500 "Publish failed" + log
        ▼
[P5] prune_staging(item_dir)                                    [MỚI] dọn bản staging dư:
        │   rm -rf outputs/.../items/<item>; rmdir items/ + batch/      artifact đã nằm trong library/,
        │   nếu rỗng (outputs/ gitignored, ephemeral)                   staging chỉ là bản tạm
        ▼
[P6] regen_catalog()                                            [MỚI] build_component_catalog.py
        ▼
200 { ok, message:"Published to library" }
        ▼
[UI] closeModal() → loadData() → toast                          [MỚI] tab Published +1, Draft −1
```

---

## 4. POST /api/delete — cây server

```
nhận { id, status }
        │
        ├─ status == "published"                                [MỚI]
        │     ├─ find_published(id) trong registry
        │     ├─ GUARD canonical: paths.artifact phải bắt đầu      [MỚI] bảo vệ AGENTS.md:
        │     │     "slide-system/library/" — nếu không ─► 403         logo/dio nằm ở .agents/,
        │     │     "protected/canonical asset"                         deletable=False, KHÔNG xoá
        │     ├─ target ∈ library/ (within_repo) — nếu không ─► 403
        │     ├─ target.is_dir() → rmtree · is_file() → unlink     [MỚI] xử lý cả artifact-file
        │     ├─ gỡ entry khỏi visual-library.json
        │     └─ regen_catalog()
        │     → an toàn: file git-tracked, KHÔI PHỤC được bằng git checkout
        │
        └─ status == "draft" | "staging"                        [MỚI]
              ├─ find_staging(id)
              ├─ guard: target nằm trong outputs/component-extractions/
              ├─ rm -rf <item_dir>            (cả artifact+evidence+mapping)
              └─ regen_catalog()
              → CẢNH BÁO: outputs/ là gitignored → MẤT VĨNH VIỄN, không revert được

[UI] confirm dialog                                             [MỚI] khác nhau theo status:
        ├─ published, deletable=False → KHÔNG hiện nút Delete (canonical: logo, dio)
        ├─ published, deletable=True  → confirm thường, nút "Delete"
        └─ draft     → confirm NGUY HIỂM: phải gõ đúng "DELETE" mới bật nút
                       "Delete forever" (vì xoá vĩnh viễn)
```

---

## 5. Bảng gate — điều gì CHẶN nút Publish (publish_readiness)

```
Điều kiện của draft item
        │
        ├─ artifact/ rỗng ───────────────────────► CHẶN "No artifacts in this extraction"
        ├─ evidence/ rỗng ───────────────────────► CHẶN "No source evidence in this extraction"
        ├─ compatibility có giá trị "untested" ──► CHẶN "Compatibility not tested: …"
        │
        ├─ preview/ thiếu ───────────────────────► KHÔNG chặn  (P2 tự tạo lúc publish)
        └─ approval == pending ──────────────────► KHÔNG chặn  (P3 click = duyệt)
```

`ready=True` → nút Publish bật (cam). `ready=False` → Publish mờ + tooltip + dòng note
"Can't publish yet: …". 4 draft guideline hiện tại đều `ready=True` (artifact+evidence đủ,
compat đã test) → chỉ cần 1 click.

---

## 6. Luật cứng

- **`catalog_server.py` là cổng mutate DUY NHẤT.** Trang tĩnh (`http.server`/`file://`)
  không sửa được file → nút Publish/Delete sẽ báo *"Control server not running. Start it
  with: python3 slide-system/catalog/catalog_server.py"*. Không có đường mutate nào khác.
- **Chỉ local.** Server bind `127.0.0.1`, là công cụ authoring xoá/ghi file — KHÔNG expose
  ra mạng.
- **Click Publish = sự duyệt của con người** (P3). Không tự duyệt ở bất kỳ chỗ nào khác;
  gate `approval=approved` của `publish_extraction.py` chỉ được thỏa bằng hành động này.
- **Preview do publish tự tạo** (P2), không bắt user thao tác — đúng tinh thần
  component-extractor §6 "author preview at publish".
- **Tái dùng script đã kiểm thử**, không reimplement bằng JS: promote = `publish_extraction.py`,
  preview = `generate_item_preview.py` (→ `generate_template_preview.py` | `render_svg.js`),
  catalog = `build_component_catalog.py`. JS chỉ gọi `fetch()`.
- **Xoá published = git khôi phục được; xoá draft = vĩnh viễn** → draft-delete bắt gõ `DELETE`.
- **Chỉ xoá item thuộc `slide-system/library/`.** Item canonical (logo, Dio ở `.agents/…`)
  có `deletable=False` → UI ẩn nút Delete và server trả 403 (bảo vệ theo AGENTS.md).
- **Mọi mutate → regen catalog** rồi UI `loadData()` (cache-bust `?t=`), KHÔNG sửa
  `catalog-data.json` bằng tay (file generated). Extractor (SKILL §5) + server tự regen —
  user non-tech không cần chạy `build_component_catalog.py` thủ công.
- Guard path: id phải khớp regex stable-id; published rm chỉ trong `library/`;
  draft rm chỉ trong `outputs/component-extractions/`.
- **Phụ thuộc preview atomic:** `render_svg.js` cần `node` + Playwright/Chromium. Thiếu →
  publish trả 500 "Could not build a preview" (chạy preflight/`setup.sh` trước).
- **Sau publish, bản staging được tự dọn** (P5: rm item + prune batch rỗng) — artifact đã
  nằm trong `library/`. Không còn rác trong `outputs/`.
- **Không có nút/endpoint "regenerate preview".** Render lại từ cùng nguồn SVG cho ra
  preview Y HỆT (deterministic) → vô nghĩa. Muốn preview đẹp hơn phải sửa nguồn =
  **re-extract** (việc của agent `/component-extractor`), không phải thao tác web.
- Server single-user, không khoá concurrency (1 người dùng local).

---

## 7. File & lệnh

```
slide-system/catalog/catalog_server.py        [MỚI] server 127.0.0.1:8799 + POST /api/{publish,delete}
                                                     (publish: auto-preview + promote + dọn staging)
slide-system/scripts/generate_item_preview.py [MỚI] preview theo type (template | atomic) — gọi NỘI BỘ trong publish
slide-system/scripts/build_component_catalog.py [FIX] publish_readiness + deletable + staging_dir + preview fallback published
slide-system/catalog/index.html               [FIX] thêm <div id="modal-manage">
slide-system/catalog/catalog.js               [FIX] renderManageBar + onPublish(1-click) + onDelete(confirm) + api() + loadData()
slide-system/catalog/catalog.css              [FIX] .manage-btn / -primary / -danger / .manage-note / .confirm-*

# Script sẵn có được tái dùng (KHÔNG sửa)
slide-system/scripts/publish_extraction.py    [GIỮ] promote staging → library + registry + history
slide-system/scripts/generate_template_preview.py [GIỮ] preview full-slide template (PyMuPDF)
slide-system/scripts/render_svg.js            [GIỮ] render SVG → PNG (Playwright)

# Chạy
python3 slide-system/catalog/catalog_server.py
# → http://127.0.0.1:8799/slide-system/catalog/
```
