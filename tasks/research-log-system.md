# Research — Hệ thống log hiệu quả cho agent

Mục tiêu: log để **agent đọc nhanh, hiểu context đúng**, tận dụng codegraph +
codebase-memory MCP + rtk để giảm token và tránh đọc nhầm code đã cũ.

Ngày: 2026-06-24. Người yêu cầu: Linh Le.

---

## 1. Hệ thống log hiện tại (đã verify)

- **Nơi:** `docs/logs/SESSION-LOG-<YYYY-MM-DD>.md`, một file/ngày, append-only.
- **Định dạng:** entry đánh số chạy (`## N — title`) với 4 trường
  Request / Actions / Result / State. Rule ở `AGENTS.md` → "Task Logging",
  template ở `docs/logs/_TEMPLATE.md`.
- **Quy mô thực tế:** file ngày 06-24 = **282 dòng / 26.8 KB** cho ~2 ngày.

## 2. Vấn đề (đã verify từ file thật)

| # | Vấn đề | Bằng chứng |
|---|--------|-----------|
| 1 | **File phình to, đọc tuyến tính** — muốn hiểu 1 file/feature phải đọc cả 26 KB | 282 dòng, 25 entry trong 1 file |
| 2 | **Số chạy toàn cục đã vỡ** — thiếu entry 6, 21, 22 | `grep "^## "` cho thấy nhảy 5→7, 20→23 |
| 3 | **Sai ngày header** — file tên `06-24` nhưng header ghi `06-23 → 06-24` | dòng 1 của file |
| 4 | **Prose thuần, không query được bằng máy** — file/symbol/commit nằm trong câu văn | mọi entry |
| 5 | **Số liệu cũ bị tin nhầm** — "registry 127 → 80" đúng lúc viết, nay có thể sai → vi phạm rule no-guessing | entry 2 |
| 6 | **Không link tới code** — entry nêu `scaffold_extraction.py` nhưng không nêu symbol → muốn xem "đã đổi gì" phải đọc cả file | entry 14 |

## 3. Công cụ — thực trạng (đã verify)

- **codegraph**: ĐÃ index, chạy tốt. Dùng để: từ log → kéo **source hiện tại**
  của symbol (`codegraph node <symbol>`), không tin số liệu cũ trong log.
- **codebase-memory MCP**: **CHƯA index** (`list_projects → []`). `manage_adr`,
  `query_graph` chưa dùng được → cần chạy `index_repository` 1 lần trước.
- **rtk 0.42.1**: có `grep / read / json / git / log`. Dùng để đọc index rẻ token.

## 4. Đề xuất — "Index mỏng + entry có link"

Ý tưởng cốt lõi: **tách index máy-đọc-được (rẻ) khỏi prose chi tiết, và để entry
trỏ vào code graph thay vì chép lại code.**

### 4.1 Hai tầng

1. **`docs/logs/INDEX.jsonl`** — 1 dòng JSON / entry:
   `{id, date, title, status, commit, files:[], symbols:[], supersedes}`.
   Agent đọc cái này TRƯỚC bằng `rtk grep`/`rtk json` (token nhỏ) để chọn ra
   1–3 entry liên quan, rồi mới đọc prose của đúng các entry đó.
2. **`SESSION-LOG-<date>.md`** — giữ prose người-đọc như cũ (nguồn sự thật).
   INDEX.jsonl được **sinh ra** từ file này (không nhập tay 2 lần).

### 4.2 Sửa đánh số

Bỏ số chạy toàn cục → dùng `<date>.<n>` (vd `2026-06-24.3`). Per-day, không
tranh chấp giữa session/agent, không còn lỗ hổng số.

### 4.3 Giao thức đọc cho agent (đây mới là phần "hiệu quả")

```
Cần context về 1 file/feature
  → rtk grep <file|symbol> docs/logs/INDEX.jsonl   # rẻ, ra entry id
  → đọc prose CHỈ các entry đó
  → entry nêu symbol → codegraph node <symbol>      # source HIỆN TẠI, không tin số cũ
Quyết định kiến trúc cần sống lâu
  → manage_adr (sau khi index_repository codebase-memory 1 lần)
```

### 4.4 Sinh index

Script `slide-system/scripts/build_log_index.py` parse session log của ngày →
regenerate `INDEX.jsonl`. Đúng pattern họ đã có với `build_registry.py`
(`--check` để CI bắt drift, `--write` để rebuild).

## 5. Mức độ triển khai (cần user chọn)

- **A. Nhẹ:** chỉ sửa rule + template (số `<date>.<n>`, mỗi entry kèm dòng
  `Files:`/`Symbols:` để grep được). Không thêm script. ~30 phút.
- **B. Vừa (đề xuất):** A + `build_log_index.py` sinh `INDEX.jsonl` + cập nhật
  AGENTS.md với "giao thức đọc log" (rtk → codegraph). ~1–2 giờ.
- **C. Đầy đủ:** B + index codebase-memory + chuyển "decisions" thành ADR
  query được. Cần chạy index_repository (tốn thời gian 1 lần).
