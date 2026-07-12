# Main Window Page Overrides

> **PROJECT:** Taoguba Article Archiver
> **PAGE:** Main desktop window
> Rules here override `../MASTER.md`. The Master remains the generated baseline.

## Product posture

- Desktop utility, not a dashboard or landing page.
- Calm, native, trustworthy and compact; no oversized display type.
- One primary task: archive explicitly entered article URLs.
- Light mode follows system by default; dark mode is a paired theme, not the default.

## Window and layout

- Default window: `1040 × 720`; minimum: `860 × 620`.
- Single-screen shell: 64 px title bar, scrollable content, 56 px status/action footer.
- Main content uses a 12-column grid: URL composer 8 columns, session/settings rail 4 columns.
- At widths below 900 px, stack the settings rail below the composer.
- Use an 8 px rhythm. Page padding 24 px; card padding 20 px; card gap 16 px.
- No permanent sidebar and no nested scrolling regions.

## Light theme tokens

| Role | Value |
|---|---|
| App background | `#F4F6F8` |
| Surface | `#FFFFFF` |
| Surface subtle | `#F8FAFC` |
| Primary text | `#18212F` |
| Secondary text | `#5E6B7A` |
| Disabled text | `#8B96A5` |
| Border | `#DCE2E8` |
| Primary action | `#2563EB` |
| Primary hover | `#1D4ED8` |
| Focus ring | `#93C5FD` |
| Success | `#16803C` |
| Warning | `#B45309` |
| Error | `#B42318` |

## Dark theme tokens

| Role | Value |
|---|---|
| App background | `#0F1722` |
| Surface | `#172131` |
| Surface subtle | `#1C2839` |
| Primary text | `#F3F6FA` |
| Secondary text | `#AAB5C3` |
| Border | `#344154` |
| Primary action | `#60A5FA` |
| Primary hover | `#93C5FD` |
| Focus ring | `#3B82F6` |
| Success | `#4ADE80` |
| Warning | `#FBBF24` |
| Error | `#FB7185` |

## Typography

- Use platform UI fonts to keep the app lightweight:
  `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `PingFang SC`, `Microsoft YaHei`, `Noto Sans SC`, sans-serif.
- Window title: 18 px / 600.
- Card title: 14 px / 600.
- Body and input: 14 px / 400, line-height 1.5.
- Supporting text: 12 px / 400. Never use body text below 12 px.
- URLs and counts use tabular figures; URLs may use the platform monospace font.

## Components

### Header

- Product mark + “淘股吧文章归档器” on the left.
- Login state pill and labeled “设置” button on the right.
- No custom draggable title bar in MVP; retain native Windows/macOS window controls.

### URL composer

- Visible label: “文章链接”. Placeholder is an example, never the only label.
- Multiline input supports paste, one URL per line, and drag/drop of a `.txt` file.
- Helper text states “只解析主帖正文和正文图片，不获取评论”.
- Validate on blur or submit, not on every keystroke.
- Invalid rows show an inline message with the offending line and correction action.

### Session card

- Status uses icon + label + color: “未登录 / 已登录 / 登录失效”.
- Primary recovery action is “登录淘股吧” or “重新登录”.
- Never display or expose Cookie values.

### Destination card

- Show the selected path in a read-only field with a labeled “选择” button.
- “打开目录” is secondary and disabled until the directory exists.

### Scope card

- Default text: “主帖正文 + 正文图片”.
- “包含楼主跟帖” is an advanced checkbox and remains off.
- Full response preservation is described as traceability, not as comment import.

### Output format card

- Use independent checkboxes, never a mutually exclusive radio group.
- Options: “HTML 原文” and “Markdown 副本”. Both may be enabled at the same time.
- HTML is selected by default. Selecting Markdown adds an `.md` file without replacing HTML.
- Helper text when both are selected: “每篇文章将同时生成 HTML 和 Markdown 文件”.
- At least one format must remain selected; if the user tries to clear the last option, keep it selected and show inline guidance.
- Format selection is remembered locally for the next launch.

### Queue

- Rows show title or URL, state icon, status text, and a contextual action.
- States: queued, fetching, complete, incomplete, failed, cancelled.
- Progress is determinate by item count; current row may use an indeterminate spinner.
- Error rows include a recovery action such as “重试” or “重新登录”.

### Primary action

- Exactly one primary button: “开始归档”.
- While running it becomes disabled and reads “正在归档 2 / 3”.
- “停止” is a separate secondary button and only appears during a job.

## Icons

- Use a single outline family based on Phosphor semantics: archive/download, folder-open, sign-in, gear, check-circle, warning-circle and x-circle.
- Standard icon 18 px, status icon 16 px, 1.75 px stroke.
- Icon-only buttons are allowed only for window-adjacent utilities and require tooltips and accessible names.
- Never use emoji as structural icons.

## Motion and feedback

- 160–200 ms color/opacity transitions; no card lift or decorative animation.
- Show progress feedback after 300 ms.
- Success uses a row transition plus text; never rely on green alone.
- Toasts last 4 seconds, do not steal focus, and are only for global completion.
- Respect reduced motion by disabling nonessential fades.

## Keyboard and accessibility

- Logical tab order: URL input → choose folder → login → output formats → advanced option → start.
- `Ctrl/Cmd + Enter`: start archive. `Esc`: request cancellation while running.
- All controls have visible 2 px focus rings and at least 36 px desktop hit height.
- Status is announced through an accessible live/status region.
- Contrast targets: 4.5:1 for text, 3:1 for large glyphs and boundaries.

## Empty, running and error states

- Empty queue: compact instructional row, not an illustration.
- Running: keep inputs visible but locked; do not replace the entire window with a spinner.
- Login expired: preserve entered URLs, focus the “重新登录” action, then resume on success.
- HTTP/site failure: preserve raw response and show “已保存现场，正文不完整”.

## Forbidden patterns

- No oversized typography, hero section, metrics dashboard or marketing CTA.
- No red/green-only status semantics.
- No hidden advanced behavior or automatic batch discovery.
- No glassmorphism, gradients, animated background, pulsing status dot or heavy shadows.
- No modal for the normal archive flow; only login guidance and destructive confirmation may use a dialog.
