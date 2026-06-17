# Mô phỏng luồng skill: /component-extractor & /slide-generator

> Bản tóm tắt đơn giản, mô phỏng theo `.agents/skills/*/SKILL.md` (cập nhật 2026-06-11).

---

## 1. /component-extractor — trích xuất component từ slide

**Khi dùng:** user chỉ định rõ vùng cần trích (file nguồn + số trang + bounds/object ID). Không bao giờ tự quét cả deck.

```
Input (PDF/PPTX/SVG + page + region)
        │
        ▼
[0] Preflight (marker-first)
        │   grep "ready" trong extract-readiness.json → đi tiếp, KHÔNG chạy script
        │   Riêng PDF/PPTX: chạy check_base_requirements.py --input pdf|pptx (gate PyMuPDF/LibreOffice)
        ▼
[1] Validate request + fingerprint vùng + check trùng lặp
        │   (extraction-history, aliases, shared registry)
        ▼
[2] Scaffold staging item trong outputs/component-extractions/
        │   phân loại artifact → chọn extraction method theo type
        ▼
[3] Chạy chuỗi script chuẩn (KHÔNG viết tay visual.svg / text-slots.json):
        │   a. convert_pdf_source.py        ← PDF→SVG, PyMuPDF, đường duy nhất được phép
        │   b. extract_editable_text_slots.py ← tách text-free visual.svg + text-slots.json + evidence
        │   c. externalize_svg_images.py    ← tách ảnh ra assets/ dùng chung
        │   d. flatten_svg_background.py    ← gộp các strip background PDF thành 1 PNG (pixel-diff gated)
        │   e. externalize_svg_images.py    ← chạy lại để refresh manifest sau flatten
        │   f. optimize_svg.py
        │   g. apply_text_contract.py
        │   h. validate_text_slots.py       ← gate cuối, fail là dừng
        ▼
[4] Ghi mapping.json (record chính) + evidence/notes.md
        │   artifact/ = visual.svg + text-slots.json (không copy ảnh nguồn, không README per-item)
        ▼
[5] Build 1 gallery.html cho cả batch + cập nhật catalog staging + extraction history
        ▼
[6] User duyệt từng item → chỉ publish item được approve
            (publish_extraction.py: tạo preview/, xác nhận evidence/)
```

**Luật cứng:**
- Không render trang PDF/PPTX thành PNG làm visual → text bị "nướng" vào pixel, validator không bắt được, gallery hiện double text.
- SVG tái sử dụng không được chứa `<text>`/`<tspan>` semantic.
- Background phức tạp (blur/shadow/mask/gradient nhiều stop) → PNG background-only, **zero text**.
- Thư viện được phép do `REQUIREMENTS.md` quyết định — không tool-shopping.

---

## 2. /slide-generator — sinh deck slide từ prompt/file

**Khi dùng:** entry point mặc định cho mọi job tạo slide mới.

```
Input (prompt / file / hỗn hợp)
        │
        ▼
[1] Intake & triage
        │   user mới = non-tech: hỏi từng câu một, mỗi câu kèm guess,
        │   tối đa ~5-6 câu, chốt luôn export format ở đây
        ▼
[2] Recap brief bằng ngôn ngữ thường → user XÁC NHẬN rồi mới build
        │   (recap = job requirements + export contract)
        ▼
[3] Tạo job + versioned run dưới outputs/slide-jobs/<job-id>/
        ▼
[4] Chạy requirement checker (dùng capability registry đã cache)
        ▼
[5] Có blocking requirement → DỪNG, trừ khi user duyệt override
        ▼
[6] Phân tích content + source authority
        ▼
[7] Lập slide plan + chấm điểm visual items đã PUBLISHED trong library
        │   (không chọn item staging / deprecated / export-incompatible)
        ▼
[8] Trình 1 approval package → user duyệt
        ▼
[9] Build HTML (chỉ sau khi approve)
        ▼
[10] Export đúng format đã chọn ở bước 1 + QA 4 lớp:
        │    content / object / render / parity
        ▼
[11] Đóng gói run: checksums + reports + manifest
```

**Luật cứng:**
- Chỉ export format đã chốt ở intake — không sinh format thừa.
- Asset tham chiếu tại chỗ (brand pack, `<job-id>/assets/`) — run không re-copy asset.
- 1 file `analysis/visual-requests.json` + 1 `analysis/selection-report.json` mỗi run (không tách per-section).
- `qa/export-renders/` là trung gian — xoá sau khi parity pass.
- Không extract component inline — muốn tái sử dụng thì hand-off sang `/component-extractor`.
- Brand mặc định: SUN.STUDIO.

---

## 3. Quan hệ giữa 2 skill + trạng thái hiện tại

```
/component-extractor ──publish──▶ slide-system/library/ ──select──▶ /slide-generator
        (staging → approve)         (published items)        (chỉ chọn published)
```

- **Extraction side: ĐÃ tối ưu xong (2026-06-11)** — flatten background, shared assets, reference 1920px. Không tối ưu lại.
- **Export side: là phase tiếp theo.** `build_hybrid_pptx.py` hiện rasterize toàn bộ visual.svg thành 1 PNG nền (chỉ text tách rời) — vi phạm mô hình 3 lớp trong `rules/background-rendering.md` (base-background / complex-overlay / editable-foreground). Fix object separation phải làm ở export, không phải extraction.
