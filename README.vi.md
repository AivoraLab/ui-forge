<div align="center">

# ui-forge

**Chọn component shadcn *hợp* — không phải cái nhiều sao nhất.**

[English](README.md) · [Tiếng Việt](README.vi.md)

[![checks](https://github.com/AivoraLab/ui-forge/actions/workflows/checks.yml/badge.svg)](https://github.com/AivoraLab/ui-forge/actions/workflows/checks.yml)
[![smoke](https://github.com/AivoraLab/ui-forge/actions/workflows/smoke.yml/badge.svg)](https://github.com/AivoraLab/ui-forge/actions/workflows/smoke.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB.svg)](https://www.python.org/)
[![status: v2.1.0](https://img.shields.io/badge/status-v2.1.0-success.svg)](docs/roadmap.md)

Một agent skill trả lời một câu trước khi agent cài bất cứ thứ gì:

> *Component này có free không, và có thật sự hợp với trang tôi đang làm không?*

</div>

---

Hệ sinh thái shadcn có **539 registry công khai** và **hơn 154 nghìn component**.
Phần lớn các trang directory trộn hàng free với hàng paid để bán gói Pro, còn
metadata của item không hề có trường license. Skill chính thức của shadcn dạy
agent *cách dùng* component; ui-forge quyết định **chọn cái nào**, **nó có free
không**, và **có khớp với dự án không**.

> Skill chính thức của shadcn dạy agent dùng component; ui-forge quyết định chọn
> component nào, nó có free không, và có hợp với web đang code không.

ui-forge phụ thuộc vào skill chính thức của shadcn cho kiến thức CLI. Nó không
dạy lại, và không ship MCP server — CLI/MCP chính thức lo phần transport.

## Mục lục

- [Vì sao có ui-forge](#vì-sao-có-ui-forge)
- [Bắt đầu nhanh](#bắt-đầu-nhanh)
- [Cách hoạt động](#cách-hoạt-động)
- [Lệnh](#lệnh)
- [Dataset license](#dataset-license)
- [Compatibility gate](#compatibility-gate)
- [Fitting Room](#fitting-room)
- [Hợp đồng JSON](#hợp-đồng-json)
- [Cấu trúc repo](#cấu-trúc-repo)
- [Phát triển và CI](#phát-triển-và-ci)
- [An toàn](#an-toàn)
- [Đóng góp](#đóng-góp)
- [License](#license)

## Vì sao có ui-forge

| Vấn đề | ui-forge làm gì |
| --- | --- |
| Directory xếp hàng free cạnh hàng paid | `discover` và `search` loại registry paid/freemium **trước khi** xếp hạng, kèm bằng chứng HTTP |
| "Đẹp" là cảm tính và đầy demo | Agent chấm điểm theo brief và theme của dự án; người dùng chọn trong Fitting Room |
| Radix vs Base UI, Tailwind v3 vs v4 làm vỡ cài đặt | Gate trả về `compat_risk` 0–10 từ primitive base đọc trong `files[].content` |
| Registry silent-fail, trả 401, hoặc bỏ qua query | Lỗi hiện ra kèm bằng chứng; paywall (401/402/403) bị loại, không retry |

**Hợp gu thắng nổi tiếng.** Một registry nổi tiếng nhưng paid, chỉ dùng Base UI
hoặc lệch gu sẽ thua một registry ít tên tuổi hơn nhưng khớp trang.

## Bắt đầu nhanh

```bash
npx skills add AivoraLab/ui-forge -g -a '*' -y
```

Một lệnh duy nhất, không hỏi gì: `skills` CLI cài ui-forge vào mọi agent nó phát
hiện — Claude Code, Codex, Pi, Cursor, Gemini CLI — và vào thư mục dùng chung
`~/.agents/skills` mà DSH harness đọc. Agent cũng có thể tự chạy lệnh này; `-y`
bỏ qua mọi prompt.

Skill chính thức của shadcn là **dependency, không phải điều kiện tiên quyết**:
lần dùng đầu ui-forge tự cài nếu thiếu, và vẫn chạy được bằng `--no-cli` khi
không có npm.

Sau đó, trong repo bạn đang làm, hỏi agent:

> Tìm cho tôi 3 hero section free hợp với landing page hiện tại, kiểm tra
> compatibility rồi dựng Fitting Room để tôi chọn.

## Cách hoạt động

```
fingerprint → brief → discover → search → compatibility gate
      → Fitting Room (≤ 3 bản draft) → cài winner → verify & learn
```

1. **Fingerprint** — `shadcn info --json` cộng theme token: framework, phiên
   bản Tailwind, primitive base (`radix` / `base` / `aria`), alias, component đã
   cài.
2. **Brief** — agent biến trang và ràng buộc thành một brief ngắn.
3. **Discover** — index registry cache 24 giờ, mặc định free-first.
4. **Search** — `shadcn search` chính thức là nguồn sự thật, tối đa 8 registry;
   quét index chỉ là fallback/cache.
5. **Compatibility gate** — item JSON cộng `files[].content`: primitive base,
   Tailwind, xung đột CSS variable, `registryDependencies`, license. Trả
   `compat_risk` 0–10 và verdict `pass` / `warn` / `fail`.
6. **Fitting Room** — tối đa 3 ứng viên sống sót được dựng thành draft của
   chính trang đó, cùng theme, nội dung và viewport (1440 và 390). Người dùng chọn.
7. **Cài & thích nghi** — chỉ cài winner; đọc lại file để soi network,
   telemetry hoặc code bị obfuscate.
8. **Verify & learn** — build/typecheck, chụp ảnh đối chiếu draft, lưu verdict
   theo hash của item.

## Lệnh

Một CLI chỉ dùng thư viện chuẩn. Mọi lệnh đều có `--json` với schema ổn định.

| Lệnh | Mục đích | Ví dụ |
| --- | --- | --- |
| `discover` | Liệt kê registry, free-first | `uiforge.py discover --free-only --json` |
| `search` | Tìm component trong nhiều registry | `uiforge.py search "hero" --json` |
| `inspect` | Gate tương thích cho một item | `uiforge.py inspect "@magicui/hero-video-dialog" --project . --json` |
| `evaluate` | Xếp hạng theo điểm agent chấm | `uiforge.py evaluate candidates.json --profile landing --inspect report.json --json` |
| `render` | Chụp ảnh Fitting Room (Playwright tuỳ chọn) | `uiforge.py render https://localhost:3000/draft/1 --out .ui-forge/previews` |
| `verdict` | Ghi nhớ lựa chọn của người dùng | `uiforge.py verdict "@magicui/hero-video-dialog" --project . --sha256 <hash> --chosen yes` |

Chạy launcher ngay trong bản checkout:

```bash
python3 skill/scripts/uiforge.py search "pricing" --json --limit 8
```

Yêu cầu **Python 3.12+** (đã test trên 3.12 và 3.14). Node là tuỳ chọn:
`inspect` dùng `shadcn info --json` khi có; truyền `--no-cli` để lấy fingerprint
chỉ từ metadata.

## Dataset license

`skill/data/licenses.json` là lợi thế cạnh tranh của dự án: bằng chứng đã quét,
không phải lời quảng cáo của directory. Cả registry index lẫn item JSON đều
không có trường license, nên nguồn trung thực duy nhất là thứ registry thật sự
trả về.

Độ phủ ngày **2026-11-06: 486/539 registry**.

| Trạng thái | Số lượng | Ý nghĩa |
| --- | ---: | --- |
| `free` | 462 | mọi item mẫu trả `200` |
| `freemium` | 16 | có item `200`, có item bị chặn (`401`/`402`/`403`) |
| `paid` | 6 | mọi item mẫu đều bị chặn |
| `unknown` | 2 | đã quét nhưng không có bằng chứng dùng được |

- Registry ngoài dataset là `unknown`: **vẫn giữ nhưng bị gắn cờ**, không bao
  giờ được mô tả là free.
- `402 Payment Required` được coi là paywall, không phải lỗi tạm thời.
- Bằng chứng cũ hơn ~90 ngày phải được trình bày kèm ngày, như dữ liệu cũ.
- Làm mới (người đóng góp, từ bản checkout — không chạy trong CI, không chạy
  giữa lúc đang trả lời một yêu cầu chọn component):

```bash
python3 tools/probe_licenses.py --only-missing --include-degraded
python3 tests/check_licenses.py
```

Thêm một registry chỉ là PR một entry; xem [CONTRIBUTING.md](CONTRIBUTING.md).

## Compatibility gate

`inspect` resolve item, đọc toàn bộ `files[].content`, đệ quy một tầng vào
`registryDependencies`, rồi chấm:

| Tín hiệu | Điểm |
| --- | ---: |
| Lệch primitive base (Radix vs Base UI vs React Aria) | 4.0 |
| Xung đột primitive import trong cùng item | 3.0 |
| Lệch major Tailwind | 3.0 |
| Trùng CSS variable | 1.5 mỗi cái, tối đa 3.0 |
| Thiếu npm dependency | 0.5 mỗi cái, tối đa 2.0 |
| Cây registry dependency (3–5 / hơn 5) | 1.0 / 2.0 |
| License unknown | 0.5 |
| Item bị paywall (`401`/`402`/`403`) | 10.0, bị loại |

Verdict: `pass` dưới 3.0, `warn` từ 3.0, `fail` từ 6.0 hoặc bị loại.
`evaluate --inspect` đọc thẳng con số này thay vì bắt agent gõ lại, nên thứ
hạng không bị lệch âm thầm.

## Fitting Room

Ảnh chụp là bằng chứng, không phải trang trí. ui-forge render **tối đa 3** ứng
viên, ở **1440 và 390**, và từ chối nhiều hơn. `render` chỉ chụp URL — agent tự
dựng các route draft trong một bản copy tạm; nó không bao giờ ghép component
vào dự án của người dùng chỉ để thử.

Playwright là tuỳ chọn và được kiểm tra muộn:

```bash
npx playwright install chromium   # chỉ cần cho `render`
```

Thiếu browser sẽ trả `playwright_browser_missing` kèm gợi ý đó — skill phải báo
lại, không được giả ảnh chụp.

## Hợp đồng JSON

Mỗi payload mang schema id và có thể pipe thẳng vào `jq`:

| Schema | Lệnh |
| --- | --- |
| `ui-forge/discover/v1` | `discover` |
| `ui-forge/search/v1` | `search` |
| `ui-forge/inspect/v1` | `inspect` |
| `ui-forge/evaluate/v1` | `evaluate` |
| `ui-forge/render/v1` | `render` |
| `ui-forge/verdicts/v1` | kho `verdict` |

Mã thoát: `0` thành công, `2` lỗi cách dùng/validation, `1` lỗi runtime. Mặc
định là output cho người đọc; `--json` là hợp đồng cho máy.

## Cấu trúc repo

```
skill/
  SKILL.md                 quy trình agent phải theo
  skill.yaml               metadata của skill
  references/              tài liệu registry, đánh giá, thị giác, gate
  scripts/uiforge.py       launcher CLI
  scripts/ui_forge/        net · index · licenses · shadcn · project
                           inspect · search · discover · evaluate
                           render · cli
  data/licenses.json       bằng chứng license (commit vào repo)
tools/probe_licenses.py    tool quét hàng loạt cho maintainer (cần mạng; không chạy CI)
tests/                     smoke test offline + validator dataset/skill
examples/                  example sheet và input ứng viên đã chốt
docs/                      concept, how-it-works, architecture, roadmap
```

Cache runtime (`registries-cache.json`, `fingerprint-cache.json`, `verdicts/`,
`previews/`) bị gitignore; chỉ `licenses.json` được commit.

## Phát triển và CI

```bash
python3 tests/smoke.py          # offline, không gọi mạng, 11 test
python3 tests/check_licenses.py # schema dataset và luật bằng chứng
python3 tests/check_skill.py    # frontmatter, surface lệnh, không có MCP
```

| Workflow | Chạy gì |
| --- | --- |
| `checks` | lint/compile, dataset license, surface skill trên Python 3.12/3.14 |
| `smoke` | suite offline trên Python 3.12 và 3.14 |

Cả hai chạy mỗi lần push và pull request. Bộ trọng số và các con số ví dụ đã
công bố (`8.14 / 7.97 / 7.16` landing, `8.06 / 7.92 / 7.09` admin) được đóng
băng; muốn đổi phải có RFC.

## An toàn

Component là code của bên thứ ba. ui-forge không bao giờ re-host code, và
`inspect` gắn cờ `fetch` / axios / WebSocket, analytics, và code eval động trong
`files[].content` trước khi cài. URL preview trong Fitting Room là draft local —
đừng lấy demo của registry làm bằng chứng "hợp".

## Đóng góp

Issue và PR đều được chào đón. Đóng góp giá trị nhất là **một entry license kèm
bằng chứng HTTP thật**; quét hàng loạt là việc của maintainer, chạy từ bản
checkout. Vui lòng giữ CLI chỉ dùng thư viện chuẩn, không đổi schema JSON, và
chạy ba bước kiểm tra ở trên trước khi mở PR. Xem
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © AivoraLab
