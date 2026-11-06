# ui-forge — Ý tưởng và cách hoạt động

> **Một câu:** ui-forge là một *Agent Skill* giúp agent chọn đúng component
> shadcn — **free**, **hợp** với website đang code — trong một hệ sinh thái
> 539 registry mà hầu hết trang directory trộn free với paid để bán bản Pro.

## 1. Vấn đề

Agent khi làm UI thường rơi vào một trong hai kiểu:

1. Viết component từ "trí nhớ", ra cùng một bộ layout chung chung.
2. Search, lấy kết quả nổi tiếng nhất, dán vào — bất kể nó có hợp với sản phẩm
   hay không, và bất kể nó có thật sự free hay không.

Trong khi đó index chính thức của shadcn (kiểm tra 2026-11-06) có **539
registry, 445 healthy, hơn 154.000 item**. Index và item JSON **không có field
license**. Đó là lỗ hổng dữ liệu thật: một component trông rất đẹp có thể trả
HTTP 401 khi fetch, tức là paywall, và agent không có cách nào biết nếu chỉ
đọc metadata.

Phần thiếu không phải search — search đã có. Phần thiếu là **phán đoán**:
chọn component nào, có free không, và có hợp với chính website này không.

## 2. Sản phẩm

ui-forge là **Agent Skill** (không phải app, không phải SaaS, không phải MCP
server). Nó bổ sung đúng lớp mà skill chính thức của shadcn để trống:

> Skill chính thức của shadcn dạy agent dùng component; ui-forge quyết định
> chọn component nào, nó có free không, và có hợp với web đang code không.

ui-forge **depend** vào tri thức của skill chính thức (cách dùng CLI, compose,
`shadcn info --json`) — không viết lại, không cạnh tranh phần đó.

### Ba nguyên tắc

1. **Fit thắng fame.** Xếp hạng theo độ hợp với brief và với project, không
   theo độ nổi tiếng.
2. **Free-first là luật cứng.** Mặc định chỉ trả về component free. Registry
   paid/freemium bị loại ở gate kèm bằng chứng HTTP; chỉ hiện khi user yêu cầu
   rõ.
3. **Agent tuyển, người chốt.** Agent thu hẹp còn tối đa 3 ứng viên và gợi ý
   thứ tự; user chọn bản thích nhất trong Fitting Room.

## 3. Pipeline (thứ tự cố định)

```text
Fingerprint → Brief → Discovery → Search → Hard Gate
            → Fitting Room → Fit Ranking → Install & Adapt → Verify & Learn
```

### 3.1 Fingerprint

```bash
npx shadcn@latest info --json
python3 skill/scripts/uiforge.py discover --json
```

`shadcn info --json` cho framework, Tailwind major, primitive base
(Radix / Base UI / React Aria), alias, component đã cài. Đọc thêm theme token
(màu, `--radius`, font, dark/light) và screenshot một trang hiện có — đó là
"mẫu chuẩn" để đo độ hợp.

### 3.2 Brief

Từ nhu cầu của user + fingerprint, viết ra: loại component, chức năng bắt buộc,
fit profile (`landing`, `saas`, `portfolio`, `admin`).

### 3.3 Discovery — free-first

`discover` đọc index chính thức (cache 24h) rồi join với
`skill/data/licenses.json`. Không hardcode danh sách registry ở bất cứ đâu
khác. Registry paid/freemium bị loại **trước khi xếp hạng**, kèm URL và HTTP
status đã chứng minh. Registry chưa kiểm chứng vẫn được giữ nhưng gắn cờ
"chưa rõ license".

### 3.4 Search

```bash
python3 skill/scripts/uiforge.py search "hero" --json --limit 8
```

`shadcn search` là nguồn chính; item index từng registry chỉ là cache tăng tốc
(`--index-only` ép dùng index, phục vụ test offline). Item `registry:example`
(bản demo) bị lọc. Tối đa 8 ứng viên.

### 3.5 Hard Gate

```bash
python3 skill/scripts/uiforge.py inspect "@magicui/hero-video-dialog" --project . --json
```

Gate đọc item JSON thật và **quét `files[].content`** — primitive base nằm
trong code, không nằm trong metadata. Kết quả là `gate.compat_risk` dạng số
0–10, kèm lý do và bằng chứng cho từng điểm:

| Tín hiệu | Trọng số |
|---|---|
| Base mismatch (item Radix, project Base UI) | 4.0 |
| Item import cả Radix lẫn Base UI | 3.0 |
| Tailwind major mismatch | 3.0 |
| Token collision | 1.5 mỗi cái, cap 3.0 |
| Thiếu npm dependency | 0.5 mỗi cái, cap 2.0 |
| registryDependencies 3–5 / >5 | 1.0 / 2.0 |
| License unknown | 0.5 |
| Paywall (HTTP 401/403) | 10.0, loại |

401/403 là tín hiệu license, không phải lỗi để retry. Tối đa 3 ứng viên sống
sót đi tiếp.

### 3.6 Fitting Room

3 ứng viên được ghép vào **bản nháp của chính trang gốc** — cùng theme token,
cùng nội dung thật, cùng viewport; route gốc không bị sửa. Chụp ảnh:

```bash
python3 skill/scripts/uiforge.py render <url-a> <url-b> <url-c> \
  --out previews/hero --width 1440 --width 390 --json
```

`render` chỉ chụp (Playwright CLI); việc dựng route nháp là việc của agent.
Agent đặt 3 bản cạnh nhau, nhận xét trung thực từng bản, gợi ý thứ tự — user
chọn. Chỉ bản thắng (hoặc 2 bản chung kết) mới mở live để xem motion/hover.

### 3.7 Fit Ranking

```bash
python3 skill/scripts/uiforge.py evaluate candidates.json --profile landing \
  --inspect inspect-a.json --inspect inspect-b.json --json
```

Agent chỉ cung cấp 5 trục chủ quan (visual, fit, motion, a11y, consistency);
CLI áp trọng số profile cố định, cộng health 10%, trừ `0.3 × compat_risk` đọc
từ gate. Số liệu tái lập được: ví dụ hero vẫn cho landing 8.14 / 7.97 / 7.16
và admin 8.06 / 7.92 / 7.09.

### 3.8 Install & Verify

Bản thắng cài bằng shadcn CLI vào project thật. Agent adapt token/spacing/copy,
build/typecheck, đọc lại file vừa cài (network call lạ/telemetry/obfuscate thì
gắn cờ), screenshot trang thật so với bản nháp, báo drift thẳng. Lưu lựa chọn:

```bash
python3 skill/scripts/uiforge.py verdict "@magicui/hero-video-dialog" \
  --sha256 <item.sha256> --project . --chosen yes --note "lý do user chọn"
```

Lần chạy sau phải tôn trọng gu đã chọn, không đề xuất lại bản đã bị loại mà
không nói rõ.

## 4. Dữ liệu license — moat của dự án

`skill/data/licenses.json` là dataset cộng đồng: mỗi registry có
`status` (`free` / `freemium` / `paid` / `unknown`), `checked_at`, và
`evidence[]` gồm item, URL, HTTP status thật.

- `free`: các item mẫu trả 200.
- `freemium`: có item 200, có item 401 (ví dụ @tailark, @aceternity).
- `paid`: toàn bộ item mẫu 401 (ví dụ @shadcnblocks).
- `unknown`: chưa ai kiểm chứng — cấm đoán.

Đóng góp chính cho cộng đồng là thêm một dòng có bằng chứng vào file này
(xem `CONTRIBUTING.md`).

## 5. Cấu trúc repo

```text
skill/
├── SKILL.md                 quy trình + 3 nguyên tắc + giới hạn cứng
├── references/              chi tiết: discovery, evaluation, visual, compatibility
├── data/licenses.json       bằng chứng license (được commit)
└── scripts/
    ├── uiforge.py           launcher
    └── ui_forge/            package stdlib-only
        ├── cli.py           discover / search / inspect / evaluate / render / verdict
        ├── index.py         index chính thức, cache 24h
        ├── licenses.py      tra cứu free/freemium/paid/unknown
        ├── shadcn.py        cầu nối CLI chính thức
        ├── project.py       fingerprint project
        ├── search.py        shadcn search + index cache
        ├── discover.py      danh sách registry free-first
        ├── inspect.py       gate compatibility (0–10)
        ├── evaluate.py      xếp hạng theo profile
        ├── render.py        chụp ảnh + verdict store
        └── net.py           HTTP policy, không lỗi im lặng
tests/smoke.py               test offline, chạy trên CI (Python 3.12 & 3.14)
```

## 6. Giới hạn đã biết

- Chưa tự động dựng route nháp: agent làm, `render` chỉ chụp.
- `registryDependencies` đệ quy 1 tầng (tối đa 4 dep) — cây sâu hơn chỉ báo,
  không đi hết.
- Dependency không tồn tại trên npm (ví dụ `cn` trong @uiable/button) không
  phân biệt được bằng npm existence, vì `cn` cũng là package thật.
- Registry GitHub (`owner/repo/item`) không resolve được từ index cộng đồng;
  truyền thẳng URL item JSON.
- Kết quả phụ thuộc chất lượng 5 trục agent chấm; phần số học thì tái lập được.

## 7. Không phải gì

- Không phải component library — ui-forge không ship component.
- Không phải registry — nó tiêu thụ index chính thức.
- Không phải hosted service — chạy local trong môi trường agent.
- Không phải MCP server — transport đã có ở shadcn CLI/MCP chính thức.
- Không re-host code component (kể cả code free): chỉ lưu metadata, link,
  bằng chứng.

## 8. Câu hỏi mở (RFC)

1. **Rubric chấm điểm:** 5 trục hiện tại đã đúng chưa? Nên chấm tuyệt đối hay
   pairwise ("A hay B hợp hơn")?
2. **Preview harness:** một harness dùng chung với route theo candidate, hay
   project nháp riêng cho từng candidate? Isolation vs tốc độ.
3. **Cache format:** JSON đủ chưa, khi nào verdict store cần SQLite?
4. **Trust:** bao nhiêu static inspection (network, telemetry, obfuscation)
   nên nằm trong gate trước khi cài?
5. **Registry không có index:** fallback CLI chậm và cần project cấu hình —
   có đáng làm supplemental index cộng đồng không?
6. **Ngoài shadcn:** ecosystem thứ hai là gì, và mô hình brief/profile có
   sống được khi đổi ecosystem không?
