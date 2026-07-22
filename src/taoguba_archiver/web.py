from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from platformdirs import user_data_dir

from .core import validate_article_url
from .service import ArchiveOptions, ArchiveService, CancellationToken
from .daily_replies import validate_reply_feed_url
from .settings import AppSettings, SettingsStore
from .shuo import validate_shuo_url


def _pick_output_dir(initial_directory: str | None) -> str | None:
    """Open the operating system's native folder picker only on local user action."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:  # pragma: no cover - depends on Python installation
        raise RuntimeError("当前 Python 环境不支持系统文件夹选择器，请手动输入路径") from exc

    initial_path = Path(initial_directory).expanduser() if initial_directory else None
    initialdir = None
    if initial_path:
        initialdir = str(initial_path if initial_path.is_dir() else initial_path.parent)

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            parent=root,
            initialdir=initialdir,
            mustexist=True,
            title="选择归档保存文件夹",
        )
    finally:
        root.destroy()
    return selected or None


INDEX_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>[hidden]{display:none!important}</style>
<title>淘股吧文章归档器</title><style>
:root{color-scheme:light dark;--ink:#172033;--muted:#64748b;--bg:#f4f7f8;--card:#fff;--line:#dce5e8;--main:#0f766e;--log:#101b2d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px system-ui,"Microsoft YaHei UI",sans-serif}
main{max-width:1240px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:20px}h1{font-size:22px;margin:0}.sub{margin:4px 0 0;color:var(--muted);font-size:12px}.grid{display:grid;grid-template-columns:minmax(360px,11fr) minmax(480px,13fr);gap:16px}.stack,.settings{display:grid;gap:16px}.settings{grid-template-columns:1fr 1fr}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}.card h2{font-size:13px;margin:0 0 12px}.wide{grid-column:1/-1}.links{min-height:180px}.log{min-height:330px;background:var(--log);color:#dce8f2;font:12px Consolas,"Cascadia Mono",monospace;white-space:pre-wrap;overflow:auto}.field{display:grid;gap:7px;margin:9px 0}.row{display:flex;gap:8px;align-items:center}.row>*:first-child{flex:1}input,textarea,select,button{font:inherit;border-radius:8px;border:1px solid #cbd5e1;padding:9px;background:var(--card);color:inherit}textarea{width:100%;resize:vertical}button{cursor:pointer;min-height:38px}button.primary{background:var(--main);border-color:var(--main);color:#fff;font-weight:700}button.stop{color:#b42318;border-color:#f5c2c7;background:#fff7f7}label.check{display:flex;gap:8px;align-items:center}.hint{color:var(--muted);font-size:12px}.actions{display:flex;align-items:center;gap:8px;background:#f0fdfa;border-color:#99f6e4}.actions .hint{flex:1}.status{color:#0f766e;font-weight:700}@media(max-width:900px){main{padding:16px}.grid{grid-template-columns:1fr}.settings{grid-template-columns:1fr}.wide{grid-column:auto}}
</style><style>
:root{color-scheme:light;--ink:#0f172a;--muted:#64748b;--surface:#fff;--bg:#fff7ed;--line:#f3d7c5;--primary:#ea580c;--primary-hover:#c2410c;--accent:#2563eb;--console:#101827}
*{box-sizing:border-box}body.app-shell{min-height:100vh;background:var(--bg);background-image:linear-gradient(135deg,#fff7ed 0%,#ffffff 52%,#eff6ff 100%);font:14px/1.5 ui-sans-serif,system-ui,"Microsoft YaHei UI",sans-serif;color:var(--ink)}main{max-width:1340px;padding:24px 28px 36px}.top{position:relative;margin:0 0 20px;padding:20px 0;border-bottom:1px solid var(--line);align-items:flex-start}.top:before{content:"TA";display:grid;place-items:center;width:42px;height:42px;margin-right:12px;border-radius:10px;background:var(--primary);color:#fff;font-weight:800;letter-spacing:-.06em}.top>div:first-child{flex:1}.top h1{font-size:24px;line-height:1.15;letter-spacing:-.03em}.top .sub{font-size:13px}.status{display:inline-flex;align-items:center;gap:8px;margin-top:2px;padding:8px 11px;border:1px solid #fed7aa;border-radius:999px;background:#fff;color:#9a3412}.status:before{content:"";width:8px;height:8px;border-radius:50%;background:var(--primary)}.grid{grid-template-columns:minmax(0,1.22fr) minmax(380px,.78fr);gap:20px;align-items:start}.stack,.settings{gap:20px}.settings{grid-template-columns:1fr}.card{border-color:var(--line);border-radius:14px;padding:18px;background:rgba(255,255,255,.94)}.card h2{display:flex;align-items:center;gap:8px;margin-bottom:14px;font-size:13px;letter-spacing:.01em}.card h2:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--primary)}.links{min-height:210px}.log{min-height:355px;margin:0;border-radius:10px;border:1px solid #1e293b;background:var(--console);box-shadow:none}.field{gap:6px;margin:8px 0 12px}.field label{font-size:12px;font-weight:700;color:#475569}input,textarea,select,button{border-radius:9px;border-color:#cbd5e1;transition:border-color .16s ease,background-color .16s ease,transform .16s ease}input:focus,textarea:focus,select:focus,button:focus-visible{outline:3px solid #bfdbfe;outline-offset:2px;border-color:var(--accent)}input,textarea,select{background:#fff}button{font-weight:650}button:hover{border-color:#94a3b8;background:#f8fafc}button.primary{min-width:128px;background:var(--primary);border-color:var(--primary)}button.primary:hover{background:var(--primary-hover);border-color:var(--primary-hover);transform:translateY(-1px)}button.stop{font-weight:650}.actions{padding:14px 16px;border-color:#fed7aa;background:#fffaf5}.actions .hint{font-size:12px}.check{padding:7px 0}.hint{line-height:1.55}.wide{grid-column:1/-1}@media(max-width:900px){body.app-shell{background:#fff7ed}main{padding:16px}.top{padding:12px 0}.grid{grid-template-columns:1fr}.settings{grid-template-columns:1fr}.wide{grid-column:auto}.log{min-height:260px}}@media(prefers-reduced-motion:reduce){*,*:before,*:after{transition-duration:0.01ms!important}}
</style><style>.log{background:#fff;color:#0f172a;border-color:#cbd5e1;padding:9px}.primary:disabled,.primary:disabled:hover{background:#cbd5e1;border-color:#cbd5e1;color:#64748b;cursor:not-allowed;transform:none}</style></head><body class="app-shell"><main><header class="top"><div><h1>淘股吧文章归档器</h1><p class="sub">仅归档你明确提供的淘股吧文章链接</p></div><div id="loginStatus" class="status">未登录</div></header>
<section class="grid"><div class="stack"><article class="card"><h2>文章链接</h2><textarea id="urls" class="links" placeholder="https://www.tgb.cn/a/ARTICLE_ID&#10;每行一个链接"></textarea><p class="hint">只解析主帖正文和正文图片，不获取评论。</p></article><article class="card"><h2>单条说说归档</h2><div class="field"><label for="shuoUrl">说说链接</label><input id="shuoUrl" placeholder="https://shuo.tgb.cn/shuo/toViewShuo?shuoID=…"></div><button id="archiveShuo" type="button">归档这条说说</button><p class="hint">仅归档你明确提供的这一条说说正文和正文图片。</p></article><article class="card"><h2>最新跟帖整理</h2><div class="field"><label for="replyFeed">个人页“最新跟帖”链接</label><input id="replyFeed" placeholder="https://www.tgb.cn/user/blog/moreReplyMod?userID=…"></div><div class="field"><label for="replyDate">目标日期</label><input id="replyDate" type="date"></div><button id="collectReplies" type="button">整理当天跟帖</button><p class="hint">严格按每条跟帖时间筛选；只在同一主帖分页内回溯引用的原图。</p></article><article class="card"><h2>进度显示</h2><pre id="events" class="log" aria-live="polite">等待操作…</pre></article></div>
<div class="settings"><article class="card"><h2>登录状态</h2><p id="loginHint" class="hint">使用应用专用 Chrome Profile，不读取日常浏览器资料。</p><button id="login">登录淘股吧</button><button id="confirmLogin" hidden>我已在 Chrome 完成登录</button></article>
<article class="card"><h2>保存位置</h2><div class="field"><label for="output">导出目录</label><div class="row"><input id="output" placeholder="例如：C:\\Users\\name\\Downloads"><button id="selectOutput" type="button">选择文件夹</button></div></div><p class="hint">选择当前电脑上的文件夹，或直接输入、粘贴目标路径。</p></article>
<article class="card"><h2>内容范围</h2><label class="check"><input id="replies" type="checkbox">包含楼主跟帖（高级）</label></article>
<article class="card"><h2>输出格式</h2><label class="check"><input id="html" type="checkbox">HTML 原文</label><label class="check"><input id="markdown" type="checkbox">Markdown 副本</label><div id="markdownModeField" class="field" hidden><label for="markdownMode">Markdown 图片方式</label><select id="markdownMode"><option value="relative" selected>相对路径（便于随导出包移动）</option><option value="source">保留原图 URL</option><option value="embed">内嵌图片（文件较大）</option></select></div></article>
<article class="card wide actions"><span id="reason" class="hint">配置完成后开始归档</span><button id="stop" class="stop" hidden>停止</button><button id="archive" class="primary">开始归档</button></article></div></section></main>
<script>
const $=id=>document.getElementById(id);let state={};
function payload(){return{output_dir:$('output').value,export_html:$('html').checked,export_markdown:$('markdown').checked,markdown_image_mode:$('markdownMode').value||null,include_author_replies:$('replies').checked}}
function latestReplyPayload(){return{...payload(),feed_url:$('replyFeed').value.trim(),target_date:$('replyDate').value}}
function archiveUnavailableReason(){if(state.busy)return '归档正在运行';if(!$('urls').value.trim())return '请输入至少一个文章链接';if(!$('output').value.trim())return '请选择保存位置';if(!$('html').checked&&!$('markdown').checked)return '至少选择一种输出格式';return ''}
function updateArchiveAvailability(){const reason=archiveUnavailableReason();$('archive').disabled=Boolean(reason);if(reason)$('reason').textContent='无法开始归档：'+reason;return reason}
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'content-type':'application/json'},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok)throw Error(data.error);return data}
function render(next,syncSettings=!state.settings){state=next;const s=state.settings;if(syncSettings){$('output').value=s.output_dir||'';$('html').checked=s.export_html;$('markdown').checked=s.export_markdown;$('markdownMode').value=s.markdown_image_mode||'relative';$('markdownModeField').hidden=!s.export_markdown;$('replies').checked=s.include_author_replies}$('loginStatus').textContent=state.login_status;$('login').textContent=state.login_status==='已登录'?'重新登录':'登录淘股吧';$('confirmLogin').hidden=!state.login_pending;$('archive').disabled=state.busy;$('archiveShuo').disabled=state.busy;$('collectReplies').disabled=state.busy;$('stop').hidden=!state.busy;$('events').textContent=state.events.length?state.events.map(e=>`[${e.time}] ${e.message}`).join('\n'):'等待操作…';$('events').scrollTop=$('events').scrollHeight}
async function refresh(){try{render(await api('/api/state'));updateArchiveAvailability()}catch(e){$('reason').textContent=e.message}}
async function save(){try{render(await api('/api/settings',payload()),true);if(!updateArchiveAvailability())$('reason').textContent='配置已保存'}catch(e){$('reason').textContent=e.message}}
for(const id of ['output','html','markdownMode','replies'])$(id).addEventListener('change',save);
for(const id of ['urls','output'])$(id).addEventListener('input',updateArchiveAvailability);
$('html').addEventListener('change',updateArchiveAvailability);
$('markdown').addEventListener('change',()=>{if($('markdown').checked&&!$('markdownMode').value)$('markdownMode').value='relative';$('markdownModeField').hidden=!$('markdown').checked;updateArchiveAvailability();save()});
$('selectOutput').onclick=async()=>{try{const next=await api('/api/output-dir',{});render(next,true);$('reason').textContent=next.output_dir_selected?'已选择保存位置':'未更改保存位置'}catch(e){$('reason').textContent=e.message}};
$('archive').onclick=async()=>{try{render(await api('/api/archive',{urls:$('urls').value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean),...payload()}));$('reason').textContent='归档任务已开始'}catch(e){$('reason').textContent=e.message}};
$('archiveShuo').onclick=async()=>{try{render(await api('/api/shuo',{shuo_url:$('shuoUrl').value.trim()}));$('reason').textContent='说说归档任务已开始'}catch(e){$('reason').textContent=e.message}};
$('collectReplies').onclick=async()=>{try{render(await api('/api/latest-replies',latestReplyPayload()));$('reason').textContent='最新跟帖整理已开始'}catch(e){$('reason').textContent=e.message}};
$('stop').onclick=async()=>render(await api('/api/cancel',{}));$('login').onclick=async()=>render(await api('/api/login',payload()));$('confirmLogin').onclick=async()=>render(await api('/api/login/confirm',{}));refresh();setInterval(refresh,800);
</script></body></html>"""

# Keep JavaScript newline escapes literal after Python parses the embedded page.
INDEX_HTML = (
    INDEX_HTML.replace("join('\n')", r"join('\n')")
    .replace("split(/\r?\n/)", r"split(/\r?\n/)")
)


class WebApp:
    def __init__(
        self,
        *,
        settings_store: SettingsStore | None = None,
        service: ArchiveService | None = None,
        profile_dir: Path | None = None,
        folder_picker: Callable[[str | None], str | None] | None = None,
    ) -> None:
        self.settings_store = settings_store or SettingsStore()
        self.settings = self.settings_store.load()
        if self.settings.export_markdown and self.settings.markdown_image_mode is None:
            self.settings = AppSettings(**{**asdict(self.settings), "markdown_image_mode": "relative"})
            self.settings_store.save(self.settings)
        self.service = service or ArchiveService()
        self._folder_picker = folder_picker or _pick_output_dir
        self.profile_dir = profile_dir or Path(
            user_data_dir("TaogubaArchiver", appauthor=False)
        ) / "chrome-profile"
        self._events: list[dict[str, str]] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._login_worker: threading.Thread | None = None
        self._cancellation: CancellationToken | None = None
        self._login_decision = threading.Event()
        self._login_confirmed = False
        self.login_status = "已登录" if self.settings.login_confirmed else "未登录"

    def _event(self, message: str) -> None:
        with self._lock:
            self._events.append({"time": datetime.now().strftime("%H:%M:%S"), "message": message})
            self._events = self._events[-300:]

    def _options(self, *, require_output: bool = True) -> ArchiveOptions:
        if require_output and not self.settings.output_dir:
            raise ValueError("请选择保存位置")
        return ArchiveOptions(
            profile_dir=self.profile_dir,
            output_dir=Path(self.settings.output_dir or "."),
            include_author_replies=self.settings.include_author_replies,
            export_html=self.settings.export_html,
            export_markdown=self.settings.export_markdown,
            markdown_image_mode=self.settings.markdown_image_mode,
        )

    def state(self) -> dict:
        with self._lock:
            return {
                "settings": asdict(self.settings),
                "events": list(self._events),
                "busy": self._worker is not None and self._worker.is_alive(),
                "login_pending": self._login_worker is not None and self._login_worker.is_alive(),
                "login_status": self.login_status,
            }

    def update_settings(self, payload: dict) -> dict:
        mode = payload.get("markdown_image_mode")
        if mode not in {None, "relative", "source", "embed"}:
            raise ValueError("Markdown 图片方式无效")
        html = bool(payload.get("export_html", True))
        markdown = bool(payload.get("export_markdown", False))
        if markdown and mode is None:
            mode = "relative"
        if not html and not markdown:
            raise ValueError("HTML 和 Markdown 至少选择一种输出格式")
        self.settings = AppSettings(
            output_dir=payload.get("output_dir") or None,
            export_html=html,
            export_markdown=markdown,
            markdown_image_mode=mode,
            include_author_replies=bool(payload.get("include_author_replies", False)),
            login_confirmed=self.login_status == "已登录",
        )
        self.settings_store.save(self.settings)
        return self.state()

    def select_output_dir(self) -> dict:
        selected = self._folder_picker(self.settings.output_dir)
        if selected:
            output_dir = Path(selected).expanduser()
            if not output_dir.is_dir():
                raise ValueError("请选择存在的文件夹")
            self.settings = AppSettings(
                **{**asdict(self.settings), "output_dir": str(output_dir)}
            )
            self.settings_store.save(self.settings)
        state = self.state()
        state["output_dir_selected"] = bool(selected)
        return state

    def start_archive(self, urls: list[str]) -> dict:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise RuntimeError("归档正在运行")
        normalized_urls = [validate_article_url(url) for url in urls]
        normalized_urls = list(dict.fromkeys(normalized_urls))
        if not normalized_urls:
            raise ValueError("请至少提供一个淘股吧文章 URL")
        options = self._options()
        cancellation = CancellationToken()
        self._cancellation = cancellation
        self._event(f"开始归档：共 {len(normalized_urls)} 篇文章")
        self._worker = threading.Thread(
            target=self._archive, args=(normalized_urls, options, cancellation), daemon=True
        )
        self._worker.start()
        return self.state()

    def start_latest_replies(self, feed_url: str, target_date: str) -> dict:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise RuntimeError("归档正在运行")
        normalized_feed_url = validate_reply_feed_url(feed_url)
        try:
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("日期必须是 YYYY-MM-DD，例如 2026-07-21") from exc
        options = self._options()
        self._event(f"开始整理最新跟帖：{target_date}")
        self._worker = threading.Thread(
            target=self._collect_latest_replies,
            args=(normalized_feed_url, target_date, options),
            daemon=True,
        )
        self._worker.start()
        return self.state()

    def start_shuo(self, shuo_url: str) -> dict:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise RuntimeError("归档正在运行")
        normalized_url = validate_shuo_url(shuo_url)
        options = self._options()
        self._event("开始归档说说")
        self._worker = threading.Thread(
            target=self._archive_shuo,
            args=(normalized_url, options),
            daemon=True,
        )
        self._worker.start()
        return self.state()

    def _archive(self, urls: list[str], options: ArchiveOptions, cancellation: CancellationToken) -> None:
        try:
            def progress(item) -> None:
                status = "完成" if item.complete else "正文不完整（已保存现场）"
                self._event(f"{status}  ·  {item.url}")

            result = self.service.archive(urls, options, on_progress=progress, cancellation=cancellation)
            if result.cancelled:
                self._event("任务已取消；已完成的归档保留")
            elif result.had_incomplete:
                if any(item.login_required for item in result.items):
                    self.login_status = "登录失效；请重新登录"
                    self._event("归档暂停；重新登录后可重试未完成项目")
                else:
                    self._event("部分文章正文不完整；已保存现场")
            else:
                self._event("归档完成")
        except Exception as exc:
            self._event(f"归档失败：{exc}")

    def _collect_latest_replies(
        self, feed_url: str, target_date: str, options: ArchiveOptions
    ) -> None:
        try:
            result = self.service.collect_latest_replies(feed_url, target_date, options)
            if result.complete:
                self._event(f"最新跟帖整理完成：共 {result.reply_count} 条")
            else:
                if getattr(result, "login_required", False):
                    self.login_status = "登录失效；请重新登录"
                self._event(f"最新跟帖整理不完整：{result.incomplete_reason}")
        except Exception as exc:
            self._event(f"最新跟帖整理失败：{exc}")

    def _archive_shuo(self, shuo_url: str, options: ArchiveOptions) -> None:
        try:
            result = self.service.archive_shuo(shuo_url, options)
            if result.complete:
                self._event(f"说说归档完成：{result.archive_dir}")
            else:
                if result.login_required:
                    self.login_status = "登录失效；请重新登录"
                reason = result.incomplete_reason or "请查看 metadata.json"
                self._event(f"说说归档不完整：{reason}")
        except Exception as exc:
            self._event(f"说说归档失败：{exc}")

    def cancel(self) -> dict:
        if self._cancellation is not None:
            self._cancellation.cancel()
            self._event("正在安全停止；当前页面处理完成后生效")
        return self.state()

    def start_login(self) -> dict:
        with self._lock:
            if self._login_worker is not None and self._login_worker.is_alive():
                raise RuntimeError("登录窗口已打开")
        self._login_decision.clear()
        self._login_confirmed = False
        self.login_status = "正在打开登录窗口…"
        self._login_worker = threading.Thread(target=self._login, daemon=True)
        self._login_worker.start()
        return self.state()

    def _login(self) -> None:
        try:
            def wait_for_confirmation() -> None:
                self.login_status = "请在 Chrome 完成登录"
                self._event("请在专用 Chrome 窗口完成登录，然后在此确认")
                self._login_decision.wait()
                if not self._login_confirmed:
                    raise RuntimeError("登录已取消")

            self.service.login(
                self._options(require_output=False), wait_for_confirmation=wait_for_confirmation
            )
            self.login_status = "已登录"
            self.settings = AppSettings(**{**asdict(self.settings), "login_confirmed": True})
            self.settings_store.save(self.settings)
            self._event("登录完成；可以开始归档")
        except Exception as exc:
            self.login_status = f"登录未完成：{exc}"
            self._event(f"登录未完成：{exc}")

    def confirm_login(self) -> dict:
        self._login_confirmed = True
        self._login_decision.set()
        return self.state()

    def wait_for_idle(self, timeout: float) -> None:
        if self._worker is not None:
            self._worker.join(timeout)


class WebHandler(BaseHTTPRequestHandler):
    app: WebApp

    def log_message(self, _format: str, *_args) -> None:
        return

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict:
        size = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(size).decode("utf-8")) if size else {}

    def do_GET(self) -> None:
        if self.path == "/":
            body = INDEX_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/state":
            self._json(self.app.state())
        else:
            self._json({"error": "未找到资源"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            payload = self._payload()
            if self.path == "/api/settings":
                result = self.app.update_settings(payload)
            elif self.path == "/api/output-dir":
                result = self.app.select_output_dir()
            elif self.path == "/api/archive":
                self.app.update_settings(payload)
                result = self.app.start_archive(payload.get("urls", []))
            elif self.path == "/api/shuo":
                result = self.app.start_shuo(payload.get("shuo_url", ""))
            elif self.path == "/api/latest-replies":
                self.app.update_settings(payload)
                result = self.app.start_latest_replies(
                    payload.get("feed_url", ""), payload.get("target_date", "")
                )
            elif self.path == "/api/cancel":
                result = self.app.cancel()
            elif self.path == "/api/login":
                self.app.update_settings(payload)
                result = self.app.start_login()
            elif self.path == "/api/login/confirm":
                result = self.app.confirm_login()
            else:
                self._json({"error": "未找到资源"}, HTTPStatus.NOT_FOUND)
                return
            self._json(result)
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def serve(*, port: int = 8765, open_browser: bool = True) -> ThreadingHTTPServer:
    app = WebApp()

    class AppHandler(WebHandler):
        pass

    AppHandler.app = app
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{server.server_port}/")
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="在浏览器中打开淘股吧文章归档器")
    parser.add_argument("--port", type=int, default=8765, help="仅本机监听的端口，默认 8765")
    parser.add_argument("--no-browser", action="store_true", help="只启动本地服务，不自动打开浏览器")
    args = parser.parse_args(argv)
    server = serve(port=args.port, open_browser=not args.no_browser)
    print(f"浏览器工作台：http://127.0.0.1:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
