# Mô phỏng luồng: Component Selection & Composition

> Luồng chọn visual item từ thư viện và ghép các standalone component lên slide.
> Dựa trên `rules/component-composition.md`, `scripts/score_visual_items.py`,
> và các workflow `select-visual-items.md`, `plan-slide-deck.md` (cập nhật 2026-06-17).

---

## Tổng quan

Khi agent tạo slide deck, nó cần:

1. **Chọn template** cho từng slide từ visual-library (scoring).
2. **Ghép standalone items** (logo, dio, shapes) lên slide đúng vị trí (composition).
3. **Giữ đồng bộ visual** trong cùng một deck (set preference).

```
User request
    │
    ▼
┌─────────────────────────────────────┐
│  INTAKE & TRIAGE                    │
│  → xác định base_template (nếu có) │
│  → ghi nhận set prefix             │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  PLAN SLIDE DECK                    │
│  → lên danh sách slide + intent    │
│  → note set prefix cho scoring     │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  SELECT VISUAL ITEMS                │
│  → score từng slide need            │
│  → áp dụng --prefer-set nếu có     │
│  → quyết định reuse / adapt / custom│
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  BUILD HTML DECK                    │
│  → đọc component-composition.md    │
│  → ghép standalone items theo layer │
└─────────────────────────────────────┘
```

---

## 1. Xác định template set (Intake → Plan)

Khi user chọn một template từ picker (ví dụ `sun.interview-workshop-sunriser.01-cover`),
agent trích set prefix từ ID:

```
sun.interview-workshop-sunriser.01-cover
 │          │                        │
 │          │                        └── slide slug
 │          └── set prefix = "interview-workshop-sunriser"
 └── brand prefix
```

**Cách derive:** `item_id.split(".")[1]` → `"interview-workshop-sunriser"`

Set prefix được ghi vào brief và truyền xuống scoring step.

---

## 2. Scoring visual items (chi tiết)

```
                    ┌──────────────────────────┐
                    │  visual-request.json      │
                    │  (intent, tags, density,  │
                    │   brand, required_exports) │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │  score_visual_items.py    │
                    │  --request <file>         │
                    │  --item-type template     │
                    │  --prefer-set <prefix>    │ ← mới
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
     ┌─────────────┐   ┌──────────────┐    ┌──────────────┐
     │ Candidate A  │   │ Candidate B  │    │ Candidate C  │
     │ cùng set     │   │ cùng set     │    │ khác set     │
     └──────┬──────┘   └──────┬───────┘    └──────┬───────┘
            │                  │                    │
            ▼                  ▼                    ▼
     ┌─────────────┐   ┌──────────────┐    ┌──────────────┐
     │ Base score   │   │ Base score   │    │ Base score   │
     │    77.5      │   │    70.0      │    │    73.75     │
     │  + SET +5    │   │  + SET +5    │    │  (no bonus)  │
     │  ─────────   │   │  ─────────   │    │  ─────────   │
     │  = 82.5  ✓   │   │  = 75.0  ✓   │    │  = 73.75     │
     │   REUSE      │   │   REUSE      │    │   ADAPT      │
     └─────────────┘   └──────────────┘    └──────────────┘
```

### Tiêu chí scoring (weights không đổi)

| Tiêu chí | Weight (component) | Weight (template) |
|---|---|---|
| semantic_intent | 35 | 35 |
| content_structure | 20 | **25** |
| density | 10 | **5** |
| brand | 10 | 10 |
| export_compatibility | 15 | 15 |
| accessibility | 10 | 10 |

### Set preference bonus

```
IF --prefer-set được truyền
   AND item eligible (published + export OK)
   AND score > 0
   AND item_id.split(".")[1] == prefer_set
THEN
   score = min(100, score + 5)
```

- Bonus = **+5 điểm** (cố định, không thay đổi weight).
- Không ảnh hưởng item khác set hoặc không có flag.
- Khi không truyền `--prefer-set`, scorer hoạt động y hệt trước đây.

### Ngưỡng quyết định

| Score | Quyết định | Ý nghĩa |
|---|---|---|
| ≥ 75 | **reuse** | Dùng nguyên published item |
| 55–74 | **adapt-local** | Dùng nhưng chỉnh cục bộ cho slide |
| < 55 | **custom-local** | Tạo mới cho slide này |
| 0 (không có eligible) | **blocked** | Không có item nào phù hợp |

---

## 3. Composition — ghép standalone items lên slide

Sau khi chọn template, agent đọc `rules/component-composition.md` để biết
đặt các standalone items ở đâu.

### Layer order (sau → trước)

```
┌──────────────────────────────────────────────┐
│                                              │
│  ⑤ Character (dio)           ┌──────┐       │
│                               │ dio  │       │
│  ④ Assets (logo)              │ 🌻  │       │
│     ┌─────────┐              └──────┘       │
│     │  LOGO   │                              │
│     └─────────┘                              │
│                                              │
│  ③ Content (text, charts, tables)            │
│     ┌────────────────────────────────┐       │
│     │  Heading text here             │       │
│     │  • Bullet point 1             │       │
│     │  • Bullet point 2             │       │
│     └────────────────────────────────┘       │
│                                              │
│  ② Style shapes (halo, hex, circles)         │
│     ░░░░░░░░░░░░░░░░░░                      │
│     ░░ halo-orange  ░░                       │
│     ░░░░░░░░░░░░░░░░░░                      │
│                                              │
│  ① Background (solid / gradient / PNG)       │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │
└──────────────────────────────────────────────┘
```

### Quyết định đặt từng item

```
                ┌─────────────────────┐
                │ Slide cần component │
                │ nào ngoài template? │
                └─────────┬───────────┘
                          │
           ┌──────────────┼──────────────┐
           ▼              ▼              ▼
     Cover/Closing?    Divider?      Data/Formal?
           │           Callout?           │
           │              │               │
           ▼              ▼               ▼
     ┌──────────┐  ┌───────────┐   ┌───────────┐
     │ ✅ Logo  │  │ ✅ Dio    │   │ ❌ Dio    │
     │ top-left │  │ corner    │   │ (quá nặng)│
     │ 120-180px│  │ 80-140px  │   │           │
     └──────────┘  └───────────┘   └───────────┘
           │              │
           ▼              ▼
     Chọn variant?   Chọn variant?
           │              │
           │         ┌────┴────────────────────────┐
           │         │ Xem mood/context của slide:  │
           │         │ celebration → dancing         │
           │         │ problem    → annoyed          │
           │         │ neutral    → normal           │
           │         │ surprise   → bewildered       │
           │         │ tips       → wink             │
           │         └─────────────────────────────┘
           │
           ▼
     Shape accent?
           │
     ┌─────┴──────────────────────────────┐
     │ Xem nội dung slide:                │
     │ key metric    → halo-blue          │
     │ warning/alert → halo-orange        │
     │ growth/win    → halo-lime          │
     │ process/steps → hex-formula        │
     │ relationships → overlap-circles    │
     └────────────────────────────────────┘
```

---

## 4. Ví dụ end-to-end

### Scenario: Tạo deck "Interview Workshop" 12 slides, user chọn template set

```
Step 1: Intake
    User: "Tạo bộ slide workshop phỏng vấn, dùng template interview workshop"
    → base_template = sun.interview-workshop-sunriser.01-cover
    → set_prefix = "interview-workshop-sunriser"

Step 2: Plan
    Slide 1: cover          intent=[cover, branded]
    Slide 2: agenda         intent=[agenda, list]
    Slide 3: timeline       intent=[timeline, process]
    Slide 4: tips           intent=[emphasis, tips]
    ...
    → Ghi note: set_prefix = interview-workshop-sunriser

Step 3: Score (per slide)
    Slide 1 (cover):
      score_visual_items.py --item-type template \
                            --prefer-set interview-workshop-sunriser
      → sun.interview-workshop-sunriser.01-cover = 82.5 (reuse)
      → sun.salary-benefits-2026.01-cover        = 73.75 (no bonus)
      → Chọn: .01-cover ✓

    Slide 3 (timeline):
      → sun.interview-workshop-sunriser.02-timeline = 82.5 (reuse)
      → Chọn: .02-timeline ✓  (cùng set, đồng bộ visual)

Step 4: Compose
    Slide 1 (cover):
      Layer 1: background từ template
      Layer 2: (không có shape accent cho cover)
      Layer 3: heading + subheading từ text-slots
      Layer 4: sun.asset.logo → top-left, 150px
      Layer 5: sun.character.dio (normal) → bottom-right, 120px

    Slide 4 (tips):
      Layer 1: background
      Layer 2: halo-blue accent bên cạnh key tip
      Layer 3: tip content
      Layer 4: (không cần logo ở slide giữa)
      Layer 5: sun.character.dio (wink) → bottom-right
```

---

## 5. Luồng quyết định tổng hợp (flowchart)

```
START: Agent nhận slide plan
  │
  ├── Có base_template trong brief?
  │     │
  │     ├── CÓ → derive set prefix từ ID
  │     │         truyền --prefer-set cho scorer
  │     │
  │     └── KHÔNG → scorer chạy bình thường (không bonus)
  │
  ▼
FOR mỗi slide trong deck:
  │
  ├── [SCORE] Chạy score_visual_items.py
  │     │
  │     ├── score ≥ 75 → REUSE template nguyên bản
  │     ├── score 55-74 → ADAPT template + chỉnh cục bộ
  │     └── score < 55 → CUSTOM build từ đầu
  │
  ├── [COMPOSE] Đọc component-composition.md
  │     │
  │     ├── Slide là cover/closing?
  │     │     └── Thêm logo (layer 4)
  │     │
  │     ├── Slide cần emphasis/divider?
  │     │     └── Thêm dio character (layer 5)
  │     │         Chọn variant theo mood
  │     │
  │     ├── Slide có metric/process/relationship cần accent?
  │     │     └── Thêm shape variant (layer 2)
  │     │         Chọn variant theo nội dung
  │     │
  │     └── Stack theo layer order:
  │           background → shapes → content → assets → characters
  │
  └── → Slide hoàn tất, sang slide tiếp
  │
  ▼
DONE: Deck đồng bộ visual nhờ set preference + composition rules
```

---

## Tham chiếu

| File | Vai trò |
|---|---|
| `slide-system/rules/component-composition.md` | Quy tắc đặt standalone items |
| `slide-system/scripts/score_visual_items.py` | Scorer với `--prefer-set` |
| `slide-system/workflows/select-visual-items.md` | Luồng chọn visual items |
| `slide-system/workflows/plan-slide-deck.md` | Lên kế hoạch slide + note set prefix |
| `slide-system/workflows/intake-and-triage.md` | Xác định base_template |
| `slide-system/registries/visual-library.json` | Registry chứa tất cả published items |
| `.agents/skills/slide-generator/SKILL.md` | Pipeline chính, item 7 trỏ đến composition guide |
