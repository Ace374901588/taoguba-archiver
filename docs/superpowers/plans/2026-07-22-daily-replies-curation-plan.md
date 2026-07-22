# 每日跟帖筛选与独立导出实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 自动筛除高置信度无意义跟帖，支持逐条删除/撤销，并导出只含保留内容和内嵌图片的单文件 HTML。

**架构：** `daily_replies.py` 对已定位的 `DailyReplyDetail` 做保守、确定性的 Python 分类；`browser.py` 将原始/自动筛除/保留计数写进 HTML 和元数据。阅读页的内联 JavaScript 只管理本地删除、单步撤销、图片转 data URL 与下载。

**技术栈：** Python 3、BeautifulSoup、`unittest`、已有 Playwright 抓取层、原生 HTML/CSS/JavaScript。

## 全局约束

- 只处理用户明确提供的淘股吧“最新跟帖”URL，不发现用户或批量抓取。
- 自动筛选必须保守：无法高置信度判断的内容一律保留。
- 不记录、导出或读取 Cookie、令牌、`Set-Cookie` 或 Chrome Profile 内容。
- 不增加远程请求；下载脚本只读取当前本地归档 `images/` 目录的相对图片，拒绝 `http`、`https` 和其他非本地 URL。
- 常规归档仍包含 HTML、`metadata.json` 和 `images/`；仅用户下载的精简版本为单文件。
- 保持 Windows/macOS 可用，不硬编码盘符、路径分隔符或系统字体。

---

### Task 1: 保守的自动筛选器

**Files:**
- Modify: `src/taoguba_archiver/daily_replies.py`
- Modify: `tests/test_daily_replies.py`

**Interfaces:**
- Consumes: `list[DailyReplyDetail]`。
- Produces: `DailyReplyCuration(details: list[DailyReplyDetail], original_count: int, automatic_filtered_count: int)` 与 `curate_daily_replies(details) -> DailyReplyCuration`。

- [ ] **Step 1: 写出失败的筛选测试**

```python
def test_curates_only_high_confidence_low_value_replies(self):
    details = [
        make_detail("收到"), make_detail("哈哈！！"), make_detail("600519 明天看承接"),
        make_detail("市场情绪感觉不太好"), make_detail("感谢"), make_detail("感谢"),
    ]
    result = curate_daily_replies(details)
    self.assertEqual(result.original_count, 6)
    self.assertEqual(result.automatic_filtered_count, 4)
    self.assertEqual([item.text for item in result.details], [
        "600519 明天看承接", "市场情绪感觉不太好",
    ])
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_daily_replies.LatestReplyFeedTests.test_curates_only_high_confidence_low_value_replies -v`

Expected: FAIL，提示 `curate_daily_replies` 未定义。

- [ ] **Step 3: 实现最小分类器**

在 `daily_replies.py` 定义冻结数据类和函数。规范化只做比较，绝不改变正文；低价值规则只匹配完全等于白名单的寒暄或规范化后为空的内容；仅过滤与上一个保留条目相同的紧邻重复。

```python
@dataclass(frozen=True)
class DailyReplyCuration:
    details: list[DailyReplyDetail]
    original_count: int
    automatic_filtered_count: int

_LOW_VALUE_REPLIES = frozenset({"收到", "感谢", "谢谢", "哈哈", "顶", "学习了", "路过", "打卡", "支持", "厉害", "牛", "赞", "加油", "ok", "666"})

def _normalise_reply_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE).casefold()

def _is_low_value_reply(text: str) -> bool:
    normalised = _normalise_reply_text(text)
    return not normalised or normalised in _LOW_VALUE_REPLIES

def curate_daily_replies(details: list[DailyReplyDetail]) -> DailyReplyCuration:
    kept, previous = [], None
    for detail in details:
        normalised = _normalise_reply_text(detail.text)
        if _is_low_value_reply(detail.text) or normalised == previous:
            continue
        kept.append(detail)
        previous = normalised
    return DailyReplyCuration(kept, len(details), len(details) - len(kept))
```

- [ ] **Step 4: 运行聚焦测试，确认通过**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_daily_replies.LatestReplyFeedTests.test_curates_only_high_confidence_low_value_replies -v`

Expected: PASS。

- [ ] **Step 5: 提交筛选器**

Run: `git add src/taoguba_archiver/daily_replies.py tests/test_daily_replies.py; git commit -m "feat: curate low-value daily replies"`

### Task 2: 将筛选结果写入归档与元数据

**Files:**
- Modify: `src/taoguba_archiver/browser.py`
- Modify: `src/taoguba_archiver/daily_replies.py`
- Modify: `tests/test_browser_export.py`
- Modify: `tests/test_daily_replies.py`

**Interfaces:**
- Consumes: `DailyReplyCuration` 与 `local_images: dict[str, str]`。
- Produces: `render_daily_replies_html(author, date, curation, local_images) -> str`；元数据键 `original_reply_count`、`automatic_filtered_count`、`retained_reply_count`。

- [ ] **Step 1: 写出失败的渲染和元数据测试**

```python
self.assertIn('data-original-count="3"', html)
self.assertIn("原始 3 条 · 自动筛除 1 条 · 当前保留 2 条", html)
self.assertEqual(metadata["original_reply_count"], 3)
self.assertEqual(metadata["automatic_filtered_count"], 1)
self.assertEqual(metadata["retained_reply_count"], 2)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_daily_replies tests.test_browser_export -v`

Expected: FAIL，旧渲染器不接受 curation，旧元数据没有计数。

- [ ] **Step 3: 接入筛选结果**

在 `browser.py` 组装 `details` 后调用 `curate_daily_replies`。下载图片和渲染卡片只使用 `curation.details`；`DailyReplyFetchResult.reply_count` 仍使用 `len(details)`，保持 CLI 的“已定位总数”语义。元数据写入全部三种计数。调用 `_portable_fragment(..., strip_context_metadata=True)` 的关联回复必须继续只在 `.context-meta` 中展示一次作者和时间；筛选与导出不得恢复正文中的重复元数据。

```python
curation = curate_daily_replies(details)
all_image_urls = [
    url for detail in curation.details
    for url in detail.image_urls + (detail.context.image_urls if detail.context else [])
    if is_content_image_url(url)
]
output_html = render_daily_replies_html(author, target_date, curation, local_images)
metadata.update({
    "original_reply_count": curation.original_count,
    "automatic_filtered_count": curation.automatic_filtered_count,
    "retained_reply_count": len(curation.details),
})
```

- [ ] **Step 4: 运行聚焦测试，确认通过**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_daily_replies tests.test_browser_export -v`

Expected: PASS。

- [ ] **Step 5: 提交归档统计**

Run: `git add src/taoguba_archiver/browser.py src/taoguba_archiver/daily_replies.py tests/test_browser_export.py tests/test_daily_replies.py; git commit -m "feat: report daily reply curation counts"`

### Task 3: 阅读页删除、撤销与单文件下载

**Files:**
- Modify: `src/taoguba_archiver/daily_replies.py`
- Modify: `tests/test_daily_replies.py`

**Interfaces:**
- Consumes: `.timeline-item` 与相对本地图片地址。
- Produces: `data-curation-control`、`data-deleted`、单步撤销和“下载精简 HTML”。

- [ ] **Step 1: 写出失败的 HTML 合同测试**

```python
self.assertIn('class="delete-reply"', html)
self.assertIn('id="undoDelete"', html)
self.assertIn('id="downloadCuratedHtml"', html)
self.assertIn('data-curation-control', html)
self.assertIn('async function inlineImages', html)
self.assertIn('querySelectorAll("[data-curation-control]")', html)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_daily_replies.LatestReplyFeedTests.test_renders_portable_daily_html_without_remote_images -v`

Expected: FAIL，旧 HTML 没有控件和下载脚本。

- [ ] **Step 3: 实现本地交互**

每个卡片增加唯一 `data-reply-url` 和删除按钮；顶部增加统计、撤销和下载按钮。脚本删除时只设置 `data-deleted="true"` 与 `hidden`，撤销时恢复最近一张卡片。下载时克隆根节点，移除控件、脚本和已删除卡片，再以内联 data URL 替换图片；只允许处理形如 `images/<文件名>` 的相对本地来源，跳过 `http`、`https`、`data:`、绝对路径和其他来源。单张图片跳过或失败时保留原 `src`，不得中止导出，也不得发起远程请求。

```javascript
async function inlineImages(root) {
  await Promise.all([...root.querySelectorAll('img')].map(async image => {
    const source = image.getAttribute('src') || '';
    if (!/^images\\/[^?#]+$/.test(source)) return;
    try {
      const blob = await (await fetch(source)).blob();
      image.src = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      });
    } catch (_) {}
  }));
}
async function downloadCuratedHtml() {
  const clone = document.documentElement.cloneNode(true);
  clone.querySelectorAll('[data-curation-control], script[data-curation-script]').forEach(node => node.remove());
  clone.querySelectorAll('.timeline-item[data-deleted="true"]').forEach(node => node.remove());
  await inlineImages(clone);
  const blob = new Blob(['<!doctype html>\n', clone.outerHTML], {type: 'text/html;charset=utf-8'});
  const link = Object.assign(document.createElement('a'), {href: URL.createObjectURL(blob), download: 'daily-replies-curated.html'});
  link.click();
  URL.revokeObjectURL(link.href);
}
```

- [ ] **Step 4: 运行聚焦测试，确认通过**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_daily_replies -v`

Expected: PASS。

- [ ] **Step 5: 提交阅读页交互**

Run: `git add src/taoguba_archiver/daily_replies.py tests/test_daily_replies.py; git commit -m "feat: export curated daily reply html"`

### Task 4: 文档、完整验证与真实导出

**Files:**
- Modify: `README.md`
- Modify: `tests/test_cli.py`（若需固定 CLI 原始计数语义）

**Interfaces:**
- Consumes: 完成的筛选器、HTML 控件和元数据字段。
- Produces: 使用说明及“不修改原始归档”的安全说明。

- [ ] **Step 1: 补齐 CLI 计数回归测试**

```python
self.assertEqual(result.reply_count, 3)
self.assertEqual(metadata["retained_reply_count"], 2)
```

- [ ] **Step 2: 运行测试，确认失败或记录已有覆盖**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_cli -v`

Expected: 新增断言时先 FAIL；若夹具没有筛选路径，由 Task 2 的浏览器归档测试覆盖元数据。

- [ ] **Step 3: 更新 README**

说明只自动移除明确寒暄和紧邻重复；无法判断的内容保留；用户可逐条删除、撤销最近删除、下载内嵌图片的精简单文件 HTML；不得声称下载会修改原始归档。

- [ ] **Step 4: 完整自动化验证**

Run: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v; .\.venv\Scripts\ruff.exe check .; git diff --check`

Expected: 全部单测通过、Ruff 输出 `All checks passed!`、diff 检查无输出。

- [ ] **Step 5: 已登录 Profile 的真实 CLI 冒烟导出**

Run: `.\.venv\Scripts\python.exe -m taoguba_archiver --timeout 60 --settle-ms 800 --output-dir .\exports --reply-feed "https://www.tgb.cn/user/blog/moreReplyMod?userID=6671396" --reply-date 2026-07-21`

Expected: 退出码 0；新目录含 HTML、元数据和图片；HTML 有 `downloadCuratedHtml`；三种元数据计数相互一致。

- [ ] **Step 6: 安全检查与提交**

Run: `rg -n --glob '!exports/**' '(?i)(set-cookie|authorization:\\s*bearer|api[_-]?key\\s*=|password\\s*=|cookies?\\s*=)' README.md docs src tests; rg -n --glob '!exports/**' '([A-Za-z]:\\\\|file:///)' README.md docs src tests; git diff --check`

只允许既有安全说明、测试模拟值和通用路径占位符；不得引入真实凭据或本机绝对路径。

Run: `git add README.md tests/test_cli.py tests/test_browser_export.py tests/test_daily_replies.py src/taoguba_archiver/browser.py src/taoguba_archiver/daily_replies.py; git commit -m "docs: explain daily reply curation"`
