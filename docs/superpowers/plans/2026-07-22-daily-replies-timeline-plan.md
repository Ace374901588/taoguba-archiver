# Daily Replies Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render each daily reply as a compact horizontal timeline entry and regenerate the existing 2026-07-21 export.

**Architecture:** Keep parsing, metadata and image localization unchanged. Update only `render_daily_replies_html` to emit a timeline rail plus a flexible content column, then verify the generated HTML contract through the renderer test and regenerate the existing export with the application-owned logged-in Profile.

**Tech Stack:** Python 3.10+, Beautiful Soup, standalone HTML/CSS, `unittest`, Playwright through the existing browser adapter.

## Global Constraints

- The software processes only user-supplied Taoguba URLs and must not discover users or bulk crawl.
- Login remains in the independent Chrome Profile; never log or export cookies, `Set-Cookie`, tokens or profile contents.
- HTML remains a portable offline output with `metadata.json` and local `images/`.
- Windows and macOS remain supported; do not add hard-coded platform paths or fonts.
- Playwright is created, used and closed in background-owned browser work.

---

### Task 1: Render compact timeline markup and responsive CSS

**Files:**
- Modify: `src/taoguba_archiver/daily_replies.py:235-269`
- Modify: `tests/test_daily_replies.py:91-107`

**Interfaces:**
- Consumes: `render_daily_replies_html(author: str | None, date: str, details: list[DailyReplyDetail], local_images: dict[str, str]) -> str`
- Produces: Offline HTML containing one `.timeline-item` for each `DailyReplyDetail`, with `.timeline-rail`, `.timeline-content`, and local image paths.

- [ ] **Step 1: Write the failing renderer test**

  Add these assertions to `test_renders_portable_daily_html_without_remote_images`:

  ```python
  self.assertIn('class="timeline-item"', html)
  self.assertIn('class="timeline-rail"', html)
  self.assertIn('class="timeline-content"', html)
  self.assertIn('>22:16<', html)
  self.assertIn('width:min(100% - 48px,1440px)', html)
  self.assertIn('@media(max-width:720px)', html)
  ```

- [ ] **Step 2: Run the focused test and verify it fails**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m unittest tests.test_daily_replies.LatestReplyFeedTests.test_renders_portable_daily_html_without_remote_images -v
  ```

  Expected: failure because `timeline-item`, the time-only rail, and compact responsive CSS are absent.

- [ ] **Step 3: Update the renderer with timeline rows**

  In `render_daily_replies_html`, derive the rail label from each entry:

  ```python
  time_label = entry.published_at.split(" ", 1)[-1]
  ```

  Replace the card wrapper with this exact string assembly while retaining the existing `body` and
  `context` variables:

  ```python
  cards.append(
      f'<article class="timeline-item"><div class="timeline-rail"><time>{escape(time_label)}</time><span class="timeline-node"></span></div>'
      f'<div class="timeline-content"><header class="reply-meta"><a href="{escape(entry.article_url, quote=True)}" target="_blank" rel="noreferrer">{escape(entry.article_title)}</a>'
      f'<a class="source" href="{escape(entry.reply_url, quote=True)}" target="_blank" rel="noreferrer">原帖定位</a></header>'
      f'<section class="reply-body">{body}</section>{context}</div></article>'
  )
  ```

  Replace the generated CSS with compact layout rules including:

  ```css
  main{width:min(100% - 48px,1440px);margin:24px auto 48px}
  .timeline-item{display:grid;grid-template-columns:88px minmax(0,1fr);gap:0}
  .timeline-rail{position:relative;padding:20px 20px 0 0;text-align:right;color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
  .timeline-rail:after{content:"";position:absolute;right:0;top:38px;bottom:-1px;width:1px;background:var(--line)}
  .timeline-node{position:absolute;right:-5px;top:24px;width:10px;height:10px;border:2px solid var(--page);border-radius:50%;background:var(--brand)}
  .timeline-content{min-width:0;padding:18px 0 22px 30px;border-bottom:1px solid var(--line)}
  @media(max-width:720px){main{width:min(100% - 24px,1440px);margin:12px auto 28px}.timeline-item{grid-template-columns:60px minmax(0,1fr)}.timeline-rail{padding-right:15px}.timeline-content{padding-left:20px}.source{margin-left:0}}
  ```

- [ ] **Step 4: Run the focused test and verify it passes**

  Run the command from Step 2.

  Expected: `OK`.

- [ ] **Step 5: Run all local verification**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m unittest discover -s tests -v
  .\.venv\Scripts\ruff.exe check .
  git diff --check
  ```

  Expected: all tests and Ruff pass; no whitespace errors.

- [ ] **Step 6: Commit the renderer change**

  Run:

  ```powershell
  git add src/taoguba_archiver/daily_replies.py tests/test_daily_replies.py
  git commit -m "feat: render daily replies as a timeline"
  ```

### Task 2: Regenerate and inspect the requested export

**Files:**
- Regenerate: `exports/<timestamp>-latest-replies-亿百万实盘-2026-07-21/daily-replies.html`
- Verify: corresponding `metadata.json`

**Interfaces:**
- Consumes: the updated renderer and the explicit URL `https://www.tgb.cn/user/blog/moreReplyMod?userID=6671396`.
- Produces: a portable local HTML file with 52 replies, direct associated contexts when present, local images, and timeline markup.

- [ ] **Step 1: Run the explicit export command**

  Run:

  ```powershell
  .\.venv\Scripts\python.exe -m taoguba_archiver --timeout 60 --settle-ms 800 --output-dir .\exports --reply-feed "https://www.tgb.cn/user/blog/moreReplyMod?userID=6671396" --reply-date 2026-07-21
  ```

  Expected: a new timestamped `latest-replies-亿百万实盘-2026-07-21` directory.

- [ ] **Step 2: Verify the generated result without reading sensitive browser state**

  Run:

  ```powershell
  $latest = Get-ChildItem -Directory .\exports | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  $metadata = Get-Content -Raw (Join-Path $latest.FullName 'metadata.json') | ConvertFrom-Json
  [pscustomobject]@{Directory=$latest.FullName; ReplyCount=$metadata.reply_count; ContextCount=@($metadata.replies | Where-Object { $_.has_context }).Count; Html=(Join-Path $latest.FullName 'daily-replies.html')}
  ```

  Expected: 52 replies, at least one associated context, and a valid `daily-replies.html` path.

- [ ] **Step 3: Verify timeline markup in the generated file**

  Run:

  ```powershell
  Select-String -Path (Join-Path $latest.FullName 'daily-replies.html') -Pattern 'timeline-item','timeline-rail','timeline-content'
  ```

  Expected: all three timeline classes are present.
