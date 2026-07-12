# AGENTS.md

- 这是一个独立、准备开源的跨平台桌面软件项目，不属于任何 Obsidian Vault。
- 默认使用中文与用户沟通，代码、公开 API 和提交信息使用清晰一致的英文命名。
- 不得引入 StockVault、Obsidian、`10_RawSources`、`40_Extracts` 或 `source_docs` 等外部项目约定。
- 软件只处理用户明确输入的淘股吧文章 URL，不做文章发现、用户遍历或批量爬取。
- 默认只解析主帖正文和正文图片；评论与楼主跟帖必须由用户显式开启。
- 登录态保存在独立 Chrome Profile 中。不得把 Cookie、`Set-Cookie`、令牌或 Profile 内容写入日志、导出文件或测试夹具。
- 通用导出包应保持可移植：HTML、可选 Markdown、`metadata.json` 和图片目录。
- HTML 与 Markdown 是可叠加的输出选项，不是互斥格式；Markdown 后端尚未实现时，不得在文档中写成已实现。
- GUI 不能阻塞主线程。Playwright 必须在工作线程内创建、使用并关闭。
- Windows 与 macOS 都是目标平台；不要硬编码盘符、路径分隔符、系统字体或 Chrome 可执行路径。
- 修改功能前先补测试；完成前运行单元测试、CLI 冒烟测试，并检查没有秘密或本机绝对路径进入仓库。
- 不要替用户选择开源许可证、GitHub 仓库名、发布账号、代码签名证书或自动更新服务；这些需要用户确认。
