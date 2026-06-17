# Mô phỏng luồng /slide-generator SAU fix 3 lớp (export phase)

> Bản mô phỏng các phần **fix / bổ sung** vào cây workflow trong `SKILL-FLOWS.md`,
> theo plan `EXPORT-PPTX-3LAYER-PLAN.md` (2026-06-11→12, đã qua 6 vòng review:
> ① sửa 5 điểm; ② hợp nhất luồng — 1 manifest, 1 evaluate, 1 gate QA sau compare, 3 phase;
> ③ cách ly v1↔v2 — bảng mode, 6 luật, regression flat; ④ chốt open issues — compose-check,
> ngưỡng 2 tier, chất lượng trước, fixture; ⑤ vector_source giữ vector xuyên pipeline;
> ⑥ audit toàn trình — capture sinh 3 ảnh QA tham chiếu, compose là bước (c), regression
> "tương đương cấu trúc"). **P1 đã triển khai 2026-06-12.** P2 (autoshape, svgBlip) và P3 (REQUIREMENTS.md, smoke-test) chưa.
>
> Ký hiệu: `[GIỮ]` không đổi · `[FIX]` sửa hành vi hiện có · `[MỚI]` thêm mới

---

## 1. /component-extractor — KHÔNG ĐỔI

Extraction đã tối ưu xong 2026-06-11 (flatten background, shared assets, reference 1920px).
Plan 3 lớp **không đụng** vào cây này. Đầu ra `visual.svg` đã giữ sẵn separation
(1 ảnh nền + các `<path>` foreground riêng) — chính là nguyên liệu cho svgBlip ở P2.

---

## 2. /slide-generator — cây mới với các điểm fix

```
Input (prompt / file / hỗn hợp)
        │
        ▼
[1] Intake & triage                                          [GIỮ]
        ▼
[2] Recap brief → user xác nhận                              [GIỮ]
        ▼
[3] Tạo job + versioned run                                  [GIỮ]
        ▼
[4] Requirement checker                                      [FIX] check_base_requirements.py
        │                                                          thêm gate chuỗi export:
        │                                                          node + playwright chromium
        │                                                          + python-pptx + Pillow
        ▼
[5] Blocking requirement → DỪNG                              [GIỮ]
        ▼
[6] Phân tích content + source authority                     [GIỮ]
        ▼
[7] Slide plan + chấm điểm visual items                      [GIỮ]
        ▼
[8] Approval package → user duyệt                            [GIỮ]
        ▼
[9] Build HTML                                               [FIX] thêm LAYER TAGGING contract:
        │     data-export-layer="base"      → nền thụ động (nằm trong base PNG)
        │     data-export-layer="overlay"   → object phức tạp, + data-export-id
        │     data-export-group="<name>"    → gom nhóm semantic thành 1 overlay
        │     data-export-native="rect|…"   → autoshape native        (P2)
        │     data-export-skip              → text nung vào raster    [GIỮ]
        │     không tag → validator FAIL (B10) trừ khi --allow-untagged
        │     1 tag phủ ≥85% canvas → validator FAIL (B11, full-bleed)
        │
        │   [9b] Artwork full-page (visual.svg từ extraction)        [MỚI] decompose BẮT BUỘC:
        │        python3 slide-system/scripts/decompose_svg_objects.py
        │                --svg <item>/artifact/visual.svg --out-dir <job>/assets/page-NN
        │        │  measure_svg_groups.js → bbox từng group (Chromium, resolve transform)
        │        │  cluster liên tiếp chồng bbox → 1 object (card = ảnh+bóng+mặt)
        │        │  group rộng ≥50% canvas, con rời nhau → TỰ TÁCH thành object con
        │        │  cluster ≥85% canvas → base-candidate (CSS background, không tag)
        │        └─ output: fragment SVGs + snippet.html (div đã tag sẵn) + manifest
        ▼
[10] Export PPTX — TRƯỚC: 2 lệnh rời, 1 PNG full-slide + text box
     Export PPTX — SAU:   1 lệnh orchestrator, PPTX 3 lớp
        │
        │   python3 slide-system/scripts/export_pptx.py             [MỚI] entry point DUY NHẤT
        │           --run-dir <run> [--mode layered|flat]                  (cấm generator ad-hoc)
        │           │
        │           ├─ (0) cache: key = sha(capture-slides.js)       [MỚI] thiếu 1 trong 3 thành phần
        │           │       + sha(HTML+assets)                             là cache trả "render ma";
        │           │       + version pin Playwright/Chromium              --no-cache = escape hatch;
        │           │       khớp → bỏ qua capture, dùng render cũ          làm ngay ở P1
        │           │
        │           ├─ (a) capture-slides.js v2                      [FIX] multi-pass, 1 browser session
        │           │       │   chờ document.fonts.ready; font brand      [MỚI] lỗi vận hành của CAPTURE
        │           │       │   không load → capture exit non-zero             (không phải của build —
        │           │       │   + disable animation                            font load lúc Playwright chụp)
        │           │       │   (tái dùng hạ tầng strip/restore text,     [GIỮ] data-export-skip +
        │           │       │    chrome-hide có sẵn)                            export-hidden đã hoạt động
        │           │       ├─ MỘT page.evaluate trả {text[],        [FIX] gộp text layout + object inventory
        │           │       │     objects[]}                               cùng 1 DOM state (mở rộng evaluate
        │           │       │     · text: + lineHeight thật,               sẵn có ở capture-slides.js:268,
        │           │       │       text-transform, letter-spacing,        đỡ 1 round-trip/slide)
        │           │       │       fontFamily per-item, số dòng thật
        │           │       │     · objects: data-export-*: id, bbox,
        │           │       │       z toàn cục, transform, filter-extent
        │           │       ├─ pass REF-FULL: chụp đủ text+lớp       [MỚI] → slide-XX-ref-full.png — tham chiếu
        │           │       │     (trước khi strip, màu text thật)         parity tier-2 (QA ephemeral, xoá sau pass)
        │           │       ├─ pass REF-NOTEXT: strip text,          [MỚI] → slide-XX-ref-notext.png — tham chiếu
        │           │       │     mọi lớp visible                          tier-1 (= bg.png của v1; mode flat ghi
        │           │       │                                              thẳng thành bg.png, không chụp 2 lần)
        │           │       ├─ pass BASE: ẩn text + mọi overlay      [MỚI] → slide-XX-bg.png (1920×1080,
        │           │       │                                              GIỮ tên file hiện tại)
        │           │       ├─ pass OVERLAY (lặp từng group):        [MỚI] hiện đúng 1 group, omitBackground,
        │           │       │     rect nở thêm blur/shadow extent          → slide-XX-ov-<id>.png (transparent;
        │           │       │     (case C4)                                 2× chỉ là tham số deviceScaleFactor,
        │           │       │                                               không dựng subsystem — P2 svgBlip thay)
        │           │       ├─ pass TEXT-LAYER: chỉ text visible,    [MỚI] → slide-XX-text.png — nguyên liệu
        │           │       │     omitBackground                           compose tier-2 (QA ephemeral)
        │           │       └─ ghi export-manifest.json              [MỚI] MỘT file {manifest_version: 2, mode,
        │           │              (schema JSON kiểm được;                  slide, base, objects[], text[]} —
        │           │               mỗi overlay ghi vector_source          z hợp nhất sẵn; PNG là cách nhúng tạm,
        │           │               → P2 svgBlip không phải dò ngược)      vector không thất lạc giữa pipeline;
        │           │                                                       shim export-layout.json CHỈ emit ở mode
        │           │                                                       flat (layered emit shim = build v1 ăn
        │           │                                                       nhầm → deck mất overlay im lặng — cấm)
        │           │
        │           ├─ (b) build_hybrid_pptx.py v2                   [FIX] composition theo MỘT manifest:
        │           │       ├─ 1 picture base đáy slide
        │           │       ├─ N picture overlay, bounds EMU riêng,  [MỚI] shape.name = "Overlay: <id>"
        │           │       │     chèn theo z hợp nhất CÓ SẴN        [FIX] text có thể nằm DƯỚI object (C8);
        │           │       │     trong manifest (không merge file)        không còn bước merge 2 JSON
        │           │       ├─ text box: bỏ hack h×1.35              [FIX] line_spacing chính xác,
        │           │       │     + áp text-transform: uppercase     [P1!] bug sai ký tự, không phải polish
        │           │       │     (letter-spacing, font map           (P2) brand-pack latin + cs/ea
        │           │       │      per-item cho tiếng Việt có dấu)         vẫn ở P2
        │           │       ├─ (P2) autoshape native + svgBlip       [MỚI] shape đơn giản & vector scale ∞
        │           │       └─ build CHỈ crash trên lỗi vận hành:     [FIX] thiếu render / manifest UNPARSEABLE
        │           │             không ra verdict chất lượng              → crash; manifest hợp lệ nhưng PPTX
        │           │             (audit text-run giữ dạng print)          không khớp → verdict của (e),
        │           │                                                       KHÔNG phải của build
        │           │
        │           ├─ (c) compose candidate (trong orchestrator)    [MỚI] thuần PIL, không mở browser lần 2:
        │           │        · tier-1 = bg + ov-*.png theo bounds/z        nguyên liệu đã có sẵn từ (a);
        │           │        · tier-2 = tier-1 + text.png                  LibreOffice PPTX→PNG = option dự phòng,
        │           │                                                       chỉ thêm khi user duyệt lại
        │           │
        │           ├─ (d) compare_renders.py (parity)               [GIỮ] script thuần đo đạc — luôn exit 0,
        │           │        · tier-1 candidate vs ref-notext.png          chỉ emit report.json + evidence
        │           │        · tier-2 candidate vs ref-full.png            (KHÔNG phải gate)
        │           │
        │           ├─ (e) validate_export_objects.py                [MỚI] gate QA DUY NHẤT — chạy SAU compare
        │           │        · PPTX zip+XML vs manifest: số shape          vì nó tiêu thụ report.json:
        │           │          (FAIL nếu 1 picture mà manifest khai        mọi verdict pass/fail dồn về
        │           │          overlay) / bounds ±0.02in / z / tên         1 exit code duy nhất
        │           │        · report.json vs ngưỡng cấu hình
        │           │          (mean_err / changed_ratio, 2 tier)
        │           │        · manifest vs JSON Schema
        │           │
        │           └─ (f) in JSON kết quả máy-đọc                   [MỚI] LLM chỉ đọc metrics,
        │                   (pass/fail + metrics)                          không mở screenshot
        ▼
[11] Đóng gói run (package_job.py)                           [GIỮ] auto-prune folder rỗng đã có
```

---

## 3. Bảng case ở bước capture/build (quyết định lớp cho từng element)

```
Element trên slide
        │
        ├─ nền gradient/texture full-slide ──────────────► BASE                (C1)
        ├─ vector decor / blob ──────────────────────────► OVERLAY riêng       (C2)
        ├─ chart / diagram ──────────────────────────────► OVERLAY group       (C3)
        ├─ có shadow/glow tràn bbox ─────────────────────► OVERLAY, rect nở    (C4)
        ├─ backdrop-filter (frosted glass)
        │       ├─ sau nó chỉ có base ───────────────────► OVERLAY đục (kèm nền) (C5a)
        │       └─ sau nó có overlay khác ───────────────► bake vào BASE + warn  (C5b)
        ├─ mix-blend-mode ───────────────────────────────► bake vào BASE + warn  (C6)
        ├─ text trong overlay (label chart)
        │       ├─ user cần sửa ─────────────────────────► NATIVE TEXT, strip khỏi PNG (C7a)
        │       └─ trang trí ────────────────────────────► data-export-skip → nung vào overlay (C7b)
        ├─ text nằm DƯỚI object ─────────────────────────► z hợp nhất, build tôn trọng (C8)
        ├─ rotate(θ) thuần ──────────────────────────────► ghi góc, PPTX rot    (C9a)
        ├─ skew/matrix phức tạp ─────────────────────────► bake vào BASE + warn (C9b)
        ├─ ảnh photo bo góc/mask ────────────────────────► OVERLAY PNG trong suốt (C10)
        ├─ deck cố ý full-image ─────────────────────────► --keep-bg-text       (C11)
        │       (flag capture độc lập, kết hợp được với --mode flat;
        │        KHÔNG phải định nghĩa của mode flat — flat = v1 hybrid strip-text)
        ├─ card/pill/line fill đặc ──────────────────────► (P2) autoshape NATIVE (C12)
        └─ hai overlay chồng nhau cùng vùng ─────────────► cho phép, z ghi đúng   (C13)
                (shadow của cái trên nằm trong PNG của nó — chấp nhận
                 vì thứ tự compose giữ nguyên)
```

---

## 4. Luật cứng — thay đổi so với SKILL-FLOWS.md

Giữ nguyên toàn bộ luật cũ, **thêm**:

- `export_pptx.py` là đường export PPTX duy nhất — không viết generator per-job
  (cùng tinh thần "PyMuPDF là provider PDF→SVG duy nhất").
- **Cách ly v1↔v2** (6 luật đầy đủ trong plan §1): `--mode flat` = v1 đóng băng
  (strip text + text box, output không đổi); `--keep-bg-text` = flag full-image riêng,
  không phải mode. Script cũ chạy trực tiếp giữ default v1 — default `layered` CHỈ ở
  orchestrator mới. Manifest bắt buộc khai `manifest_version` + `mode`; ngữ nghĩa
  `slide-XX-bg.png` đọc từ manifest, không suy từ tên file; validator mode-aware.
  Regression test flat-mode cố định trong `test_export_stack.py` — P1/P2 không được làm
  đổi output v1.
- `compare_renders.py` không phải gate (luôn exit 0) — `validate_export_objects.py` là gate
  QA **duy nhất**, chạy **sau** compare, đọc `report.json` + áp ngưỡng + check count/bounds.
- Ranh giới lỗi: capture fail khi font không load; build crash khi thiếu render / manifest
  unparseable; manifest hợp lệ-nhưng-PPTX-lệch là verdict của validator. Không script nào
  ngoài validator được ra verdict chất lượng.
- Capture FAIL (không warning) khi font brand không load — font fallback làm sai
  cả base PNG lẫn metrics text.
- Slide có overlay khai báo mà PPTX chỉ chứa 1 picture là FAIL — bắt tại validator (e),
  sau compare (validator tiêu thụ report.json nên không thể chạy trước parity).
- Regression flat-mode = "tương đương cấu trúc" (PNG so pixel, PPTX so XML/shape/geometry,
  layout.json so nội dung) — KHÔNG phải byte-level, vì PPTX là zip có timestamp; manifest
  là artifact bổ sung, không tính là output đổi.
- Overlay PNG render 2× kích thước hiển thị (scale tới ~200% không vỡ); vector gốc
  → svgBlip ở P2 (manifest đã giữ `vector_source` từ P1).
- "Never describe a full-slide image deck as editable" [GIỮ] — giờ enforce được bằng
  gate (e).

## 5. Bổ sung REQUIREMENTS.md (cho LLM ngoài Claude app)

**Không thêm row mới** — stack giống hệt row "Standalone machine (no Claude app)" sẵn có
(`REQUIREMENTS.md:44`). Chỉ **update row đó** để gọi tên flow export tường minh:

```
| Standalone machine (no Claude app) / Export editable PPTX 3 lớp — export_pptx.py
| Node.js 18+ → ./slide-system/scripts/setup.sh (installs Playwright, python-pptx, Pillow) |
```

+ pin version Playwright/chromium trong setup.sh để render deterministic giữa các agent.

## 6. Lộ trình (3 phase — vòng verify 2 gộp P0 doc-only vào P1)

Fixture chuẩn cho cả lộ trình: deck sinh từ `input/Interview_Workshop_Sunriser.pdf`
(12 trang 1920×1080, thuần vector + text tiếng Việt — phục vụ prototype, regression flat,
calibrate ngưỡng; plan §10.4).

```
P1  bước 0: PROTOTYPE transparent-overlay 1 slide  ◄── GATE trước mọi code khác:
    │       chứng minh ẩn-siblings + omitBackground          ẩn cả CSS background của slide root,
    │       ra PNG trong suốt đúng pixel                      compose lại phải khớp pixel
    │       FAIL → fallback đã định trước:
    │         (a) toàn bộ overlay đi đường C5 bake-with-background
    │             (PNG đục kèm nền — vẫn là object rời trên nền tĩnh), hoặc
    │         (b) dừng, rethink layered approach
    │       — không build capture v2 trên kỹ thuật chưa chứng minh
    └─► P1 MVP: schema manifest + sửa rule/docs + capture v2 (1 evaluate, multi-pass)
                + build v2 + validator (gate duy nhất, sau compare) + orchestrator
                + cache fingerprint (key 3 thành phần) + fix uppercase
                + regression test flat-mode (output v1 KHÔNG ĐỔI — luật cách ly #5)
                → kéo overlay ra khỏi slide → base còn nguyên
        ──► P2 (autoshape, svgBlip thay PNG 2× cho overlay gốc-vector,
                rich text còn lại: letter-spacing / per-item font / multi-run)
        ──► P3 (update REQUIREMENTS.md:44, test_export_stack,
                smoke-test agent ngoài Claude)
```
