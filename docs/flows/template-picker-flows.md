# Luồng template-picker: thư viện → picker → prompt → slide-generator

> Bản tóm tắt mô phỏng theo cấu trúc thực tế của `slide-system/template-picker/`
> và pipeline registry (cập nhật 2026-06-16). Cùng style với `SKILL-FLOWS.md`.

Template-picker là một **UI tĩnh** (HTML/CSS/JS, không build step, không framework)
cho người không kỹ thuật chọn **một slide-template hoàn chỉnh** (full-bleed
1920×1080) từ thư viện đã publish, rồi copy một **prompt ngôn ngữ thường** để đưa
sang `/slide-generator`. Picker KHÔNG sinh slide — nó chỉ chọn + sinh prompt.

---

## 1. Pipeline dữ liệu: từ item published → picker-data.json

```
slide-system/registries/visual-library.json   (nguồn sự thật duy nhất)
        │   chỉ item: status == "published" && type == "template"
        ▼
[A] build_template_picker_data.py
        │   • lọc published + template (KHÔNG đọc catalog-data.json —
        │     tránh 14 trang sun-goal-* rò vào picker người dùng)
        │   • derive_deck(item): gom slide theo DECK NGUỒN từ source.path
        │       basename → deck_id (slug) + name; slide cùng deck = 1 set
        │   • derive_thumbnail(): ưu tiên <preview-dir>/thumbnail.png
        │   • derive_use_case(): bucket theo intent/tags
        │       (Cover/Section/Data/Content/Closing/Other)
        │   • path → ĐỔI sang relative theo thư mục picker (../library/...)
        │   • sort slide trong deck theo slide_number;
        │     sort deck theo slide_count giảm dần rồi alphabet
        ▼
slide-system/template-picker/picker-data.json   (GENERATED — đừng sửa tay)
        │   { decks: [ { deck_id, name, source, slide_count,
        │               slides: [ {id, name, intent, tags,
        │                          content_structure, slide_number,
        │                          preview, thumbnail, use_case} ] } ],
        │     templates: [...] }
        ▼
[B] index.html + picker.js + picker.css   (fetch picker-data.json lúc load)
        │   • load ./picker-data.json; FAIL → fallback ./picker-data.sample.json
        │     (fixture checked-in) để UI render trước khi publish gì
        │   • source-pill: "Live library" / "Sample data" / "Load error"
        │   • decksOf() nhận CẢ shape deck-grouped LẪN list `templates` phẳng
        │     (bọc thành 1 deck "Full-slide templates")
```

**Mấu chốt:** gom set là **registry-driven qua `source.path`**, KHÔNG phụ thuộc
layout folder. Đổi/di chuyển folder template không làm hỏng grouping — chỉ chuỗi
path đổi. (Vì vậy đợt restructure gom folder theo set không động tới logic picker.)

---

## 2. Vòng đời 1 template trên đĩa (sau khi publish)

`/component-extractor` publish item `type=template` với id `sun.<set>.<slide>` →
`publish_extraction.py` đặt vào layout **gom theo set**:

```
slide-system/library/templates/
  <set-slug>/                          ví dụ interview-workshop-sunriser/
    <slide-slug>/                      ví dụ 01-cover/   (id: sun.interview-workshop-sunriser.01-cover)
      visual.svg              ← nền editable, KHÔNG <text>; đổ nội dung mới lên
      text-slots.json         ← hợp đồng text editable (bounds chuẩn hoá + typography)
      preview/
        thumbnail.png         ← ẢNH PICKER: render PDF gốc (có chữ), 1920×1080
        preview.html          ← composite editable: visual.svg + slot positioned;
                                  đây là lớp /slide-generator dùng để dựng slide
      evidence/
        source-with-text.svg  ← bản gốc full slide (bằng chứng, có chữ baked-in)
        notes.md              ← ghi chú trích xuất
```

| File | Có chữ? | Vai trò | Picker dùng? |
|---|---|---|---|
| `visual.svg` | không (cố ý) | nền editable để overlay nội dung mới | gián tiếp (preview.html) |
| `text-slots.json` | — | hợp đồng vị trí + typography của text | không |
| `preview/thumbnail.png` | có | ảnh hiển thị trong picker (PDF raster gốc) | **CÓ** |
| `preview/preview.html` | có (mẫu) | composite editable cho bước build | không |
| `evidence/source-with-text.svg` | có | bản gốc làm bằng chứng đối chiếu | không |
| `evidence/notes.md` | — | ghi chú trích xuất | không |

**Tại sao picker dùng `thumbnail.png` chứ không render `source-with-text.svg`:**
render evidence SVG dễ **nhân đôi chữ** (chữ vector chồng lên raster đã có chữ),
nên picker lấy thẳng raster PDF gốc cho sạch.

**`thumbnail.png` là BẮT BUỘC.** Picker (`thumbSrc`) ưu tiên `thumbnail`, fallback
sang `preview` — nhưng với template `preview` = `preview/preview.html`, không dùng
làm `<img src>` được → thiếu thumbnail thì ô hiện placeholder "No preview".

**`reference.png` là staging-only:** `convert_pdf_source.py` sinh nó làm raster
QA render-parity (`page.get_pixmap`), pixel-identical với `thumbnail.png`.
`publish_extraction.py` **loại nó khỏi folder published** (chỉ giữ ở
`outputs/component-extractions/...` cho QA). Không mang vào library.

---

## 3. UX picker: hai tầng + slide-viewer modal

```
[1] Sets list   (màn đầu)
        │   mỗi set = 1 card deck (tên deck, thumbnail đại diện, số slide)
        │   KHÔNG hiển thị "slot count" ở bất kỳ đâu
        ▼  click card → smooth scroll (tôn trọng prefers-reduced-motion)
[2] Deck slide grid   (openDeck)
        │   lưới các slide trong deck; mỗi ô = thumbnail + tên + nút
        │   back-bar "All template sets" + jump-nav (set switcher) ở hero —
        │     jump-nav CHỈ hiện khi ≥2 deck (giờ 1 deck nên ẩn)
        ▼  click slide → openModal(deck, index)
[3] Slide-viewer modal
        │   • top bar: close · tên deck · "N / M" counter · nút whole-set
        │   • filmstrip dọc (thumb đánh số, active ring cam, auto scroll-into-view)
        │   • stage giữa: container-query fit width:min(100cqw,100cqh*16/9) + gutter
        │   • nav: SVG chevron trái/phải (không glyph), single-step,
        │     disabled ở đầu/cuối deck
        │   • info bar: kicker(use_case bucket, fallback "Slide N") / name /
        │     intent+tags chips / id
        │   • footer: gợi ý phím (CHỈ hiện ← → / Home·End / Esc — tập con của
        │     phím thực sự hoạt động)
        │
        │   JS chính: openModal · goTo · renderFilmstrip · next · prev · trapFocus
        ▼
[4] Copy prompt  (3 nút, đều nhãn "Copy prompt")
        │   • slidePrompt(card)      → prompt 1 slide (name + id)   [info bar]
        │   • deckPrompt(deck, ids)  → prompt cả set (tên deck + ids) [top bar + detail head]
        │   prompt = tiếng Anh, ngôn ngữ thường, KÈM id để generator tra cứu
        │   clipboard: navigator.clipboard → fallback execCommand
        │   → toast xác nhận (stack tối đa 3, hover-pause, auto-dismiss ~4.2s)
        ▼
   user dán prompt sang /slide-generator → chọn item published → build
```

**Phím tắt:** `←/→` `↑/↓` `PageUp/PageDown` `Home/End` (điều hướng) ·
`Esc` (đóng) · `Tab` (trap focus trong modal).
`C`/`S` đã **gỡ bỏ** (đụng phím hệ thống) — chọn item nay qua nút trên màn hình.
Footer chỉ quảng cáo một tập con (`← →`, `Home/End`, `Esc`).

---

## 4. Regenerate & validate (chạy sau mỗi lần đổi registry)

```
# từ slide-system/
python3 scripts/build_template_picker_data.py    # → template-picker/picker-data.json
python3 scripts/build_component_catalog.py        # → catalog/catalog-data.json
python3 scripts/validate_registry.py              # gate: id pattern + path tồn tại

# xem thử (macOS không có `timeout`):
python3 -m http.server 8777    # từ repo root
# mở http://localhost:8777/slide-system/template-picker/index.html
```

---

## 5. Luật cứng

- `picker-data.json` và `catalog-data.json` là **GENERATED** — luôn regenerate
  bằng script, KHÔNG sửa tay.
- Picker chỉ đọc `visual-library.json`, chỉ item `status==published` &
  `type==template`. Item staging/deprecated không bao giờ lọt vào.
- "Template" = **một slide hoàn chỉnh** 1920×1080, không phải section/card/icon.
- Ảnh preview phải là **slide gốc đầy đủ** (PDF raster), không phải bản dựng lại
  có thể lệch nguồn → dùng `thumbnail.png`, không render `source-with-text.svg`.
- Gom set theo `source.path` (registry-driven), độc lập với layout folder.
- Id mirror layout: `sun.<set-slug>.<slide-slug>` ↔ `templates/<set>/<slide>/`.
- Prompt copy bằng **tiếng Anh**, kèm id; tên slide nhúng có thể là tiếng Việt (data).
- Mọi animation tôn trọng `prefers-reduced-motion` (modal đóng dùng `is-closing`
  + `animationend`/fallback 240ms; reduced-motion bỏ qua).
- Không "slot count" ở bất kỳ đâu trong UI.

---

## 6. Quan hệ với 2 skill gốc

```
/component-extractor ──publish──▶ library/templates/<set>/<slide>/
        (staging → approve)              │
                                         ▼  build_template_picker_data.py
                                  template-picker/picker-data.json
                                         │
                                         ▼  UI tĩnh, Copy prompt
                                  prompt (id + ngôn ngữ thường)
                                         │
                                         ▼  user dán
                                  /slide-generator (chỉ chọn published)
```

Picker nằm **giữa** thư viện published và `/slide-generator`: nó không trích xuất,
không build slide — chỉ là lớp *khám phá + sinh prompt* để người không kỹ thuật
chọn đúng template hoàn chỉnh rồi bàn giao cho generator.
