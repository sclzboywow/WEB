# MCP 对接落地清单（基于 `work` 分支最新代码）

> 代码基线：`pan_client/ui/modern_pan.py` 中 `FileManagerUI` 仍直接使用 `ApiClient` 通过 REST 与 `netdisk` Flask 服务交互，尚未引入 MCP。
> 以下清单逐项对应当前代码中的真实模块与方法，便于直接按文件拆分改造。

## 0. 关键决策确认

1. **UI 事件模型**：保持现有的同步 + Worker 线程架构，在需要调用 MCP 异步接口的线程中统一通过 `asyncio.run_coroutine_threadsafe` 或封装的 `run_in_loop` 方法调度协程（对应问题选项 **a**）。这样可以复用当前的线程安全信号槽与进度更新机制，避免一次性把整个 `Qt` 事件循环迁移到 `qasync`。
2. **`modern_pan.py` 接口改造**：优先引入 `self.client` 抽象接口，并在过渡期通过一个 `RestCompatibilityAdapter` 适配旧的 `self.api` 调用（对应问题选项 **b**）。这样可以在不大规模重写 2000+ 行 UI 逻辑的前提下，逐步把核心调用迁移到抽象层。
3. **认证 / Token 管理**：以 MCP 服务器为真源，由服务器负责令牌生命周期管理，本地 `JSON` 仅作为缓存与离线展示用途（对应问题选项 **a**）。在 MCP 失联或未启用时才回退到本地缓存。

---

## 1. 核心层（`pan_client/core`）

### 1.1 `mcp_session.py`（新增）
- [ ] 参考 `netdisk-mcp-server-stdio/client_demo_stdio.py::ClientSession`，新增 `pan_client/core/mcp_session.py`：
  - `class McpSession` 持有 `ClientSession`，在 `__aenter__/__aexit__` 中启动 / 回收 `netdisk.py --transport stdio` 子进程。
  - `async def ensure_started()`：若子进程未启动则调用 `asyncio.create_subprocess_exec`，并缓存 `mcp.ClientSession` 实例。
  - `async def invoke_tool(self, tool_name: str, **kwargs)`：统一调用 `session.call_tool`，对常见错误（`timeout`, `rate_limited`, `unauthorized`）转换成自定义 `McpError`（放在本模块）。
  - `async def dispose()`：主动终止子进程、删除临时目录；UI 退出时调用。
  - 读取 `pan_client/core/config.py::load_config()`，复用其中的 `base_dir` 推导，避免重复计算。

### 1.2 `api.py`
- [ ] 保留现有 REST 逻辑为 `class RestNetdiskClient`，对 `ApiClient` 做无损重命名；新增抽象基类 `AbstractNetdiskClient`，定义 UI 会用到的接口（`list_files`、`get_cached_files`、`get_quota`、`upload_to_mine`、`stream_file`、`search_server`、`search_cache` 等）。
- [ ] 新增 `class McpNetdiskClient(AbstractNetdiskClient)`：
  - 构造函数接收 `McpSession` 和事件循环；所有方法通过 `await session.invoke_tool(...)` 获取结果。
  - 提供 `normalize_entry(self, raw: Mapping[str, Any]) -> FileEntry`，把 MCP 字段统一为 UI 期望的 `server_filename/fs_id/is_dir/path/size` 等键。
  - 上传 / 下载接口需要把 MCP 侧返回的临时文件路径同步到 `UploadWorker` / `DownloadWorker` 中使用的结构。
- [ ] 在模块底部提供工厂 `def create_client(mode: str, *, session: McpSession | None = None) -> AbstractNetdiskClient`，供 UI 根据配置选择 MCP 或 REST。
- [ ] 现有 `ApiClient` 专用方法（如 `set_local_access_token`、`switch_account`）迁移到 `AbstractNetdiskClient` / `RestNetdiskClient`，并为 MCP 实现调用对应工具（例如 `switch_account`, `list_accounts`）。

### 1.3 `token.py`
- [ ] `get_access_token` / `set_access_token` / `clear_token` / `list_accounts` / `switch_account` / `set_current_account` 在 MCP 模式下优先调用 `McpSession` 工具，保持与服务器一致；若工具返回 `None` 再回退到本地 JSON。
- [ ] 维护一个模块级 `_MCP_SESSION: McpSession | None`，由 `token.configure_mcp(session)` 注入，避免循环依赖。
- [ ] 在写入本地缓存后触发回调，把账号列表广播给 UI（可返回 `TypedDict`，供 UI 更新菜单）。

### 1.4 `baidu_oauth.py`
- [ ] `BaiduOAuthClient` 当前在 `_poll_authorization` 中直接创建 `ApiClient` 调 REST；改为在构造函数注入 `AbstractNetdiskClient`，并提供 `set_transport_client(client)` 接口便于 `LoginDialog` 注入。
- [ ] `_poll_authorization` 轮询逻辑改为调用 `client.fetch_latest_server_token(state=...)` 或新增 MCP 工具 `fetch_login_status`，避免读取 `config.json`。
- [ ] 登录成功后通过 `AbstractNetdiskClient.set_local_access_token` 回写本地缓存，并触发 `login_success.emit`。
- [ ] 停止轮询时调用 `McpSession.dispose`（如果 MCP 模式独占子进程）。

## 2. UI 层

### 2.1 `pan_client/ui/modern_pan.py`
- [ ] `FileManagerUI.__init__`：
  - 新增参数 `client: AbstractNetdiskClient`，默认使用 `create_client(settings.transport_mode)`；保留对旧 `ApiClient` 的兼容封装。
  - 初始化时根据配置决定是否启动 MCP：当 `mode == "mcp"` 时提前创建 `asyncio` 事件循环并 `await session.ensure_started()`。
  - 新增 `self.mcp_status_label`（`QLabel`）挂在 `self.statusBar` 上，显示 “MCP已连接/断开/限流倒计时”。
- [ ] `bootstrap_and_load` / `load_dir`：
  - 使用 `await client.list_files` / `client.get_cached_files`；在共享资源视图中调用 `normalize_entry`，确保 UI 字段一致。
  - 将原有直接 `self.api.*` 的调用改为 `self.client.*`，并处理 `McpError` 提示（例如弹出 `QMessageBox`，或更新 `status_label`）。
- [ ] `display_files` / `_append_search_source`：改造为消费 `normalize_entry` 返回的统一结构，不再访问 REST 专有的 `server_filename`/`isdir` 等键。
- [ ] 搜索流程 `_start_search_threads`：
  - 保留两个线程，但线程函数通过 `asyncio.run_coroutine_threadsafe(self.client.search_server(...), loop)` 调用 MCP 工具，获取结果后发信号回主线程。
  - 对限流错误展示 `QMessageBox.information(self, 'MCP 限流', ...)`。
- [ ] 上传/下载/阅读：
  - `UploadWorker.run`、`DownloadWorker.run`、`SingleReadWorker.run` 改为调用 `AbstractNetdiskClient` 提供的统一接口；若 client 是 MCP 实例，则直接 await 工具；若为 REST，则走现有逻辑。
  - 在 UI 主线程中通过 `asyncio` 将任务派发给 MCP，返回的本地临时路径交给工作线程使用。
- [ ] 登录流程：`load_dir` 中触发登录时，改为调用 `LoginDialog(self.client, self.session)`（见下一节修改）。
- [ ] 在 `closeEvent` 中检测 MCP 模式，如果 `self.session` 存在则调用 `asyncio.run(self.session.dispose())` 并停止循环。

### 2.2 `pan_client/ui/login_dialog.py`
- [ ] 构造函数接受 `client: AbstractNetdiskClient` 和可选 `session: McpSession`，用于触发 `BaiduOAuthClient.set_transport_client`。
- [ ] 刷新二维码、轮询等流程全部改走 `client` 提供的接口；二维码获取可调用 `client.get_auth_qrcode_png()`，保证 REST/MCP 两端兼容。
- [ ] 登录成功后通过 `client.set_local_access_token` 写入缓存，并在对话框中关闭轮询（`oauth_client.stop()`）。

### 2.3 其它 UI 文件
- [ ] `pan_client/ui/dialogs/document_viewer.py`：确保 `SingleReadWorker` 在 MCP 模式下载的临时文件路径可直接传入构造函数；必要时增加异常提示。
- [ ] 若未来拆分状态栏逻辑，可在 `pan_client/ui/widgets` 下新增 `ConnectionIndicator` 小部件，用于展示 `McpSession` 状态事件。

## 3. 启动与配置
- [ ] `pan_client/config.json` 扩展为：
  ```json
  {
    "base_url": "http://127.0.0.1:5000",
    "transport": {
      "mode": "rest",
      "mcp": {
        "python_bin": "python3",
        "entry": "../netdisk-mcp-server-stdio/netdisk.py",
        "env": {}
      }
    }
  }
  ```
- [ ] `pan_client/core/config.py`：增加 `get_transport_config()` 与 `should_use_mcp()`，供 `main.py` / `FileManagerUI` 调用；当 `mode == "mcp"` 时跳过 `PAN_SERVER_BASE_URL` 校验。
- [ ] `pan_client/main.py`：
  - 新增命令行参数 `--transport {rest,mcp}`，解析后覆盖配置。
  - 当启用 MCP 时创建事件循环（`asyncio.new_event_loop()`）并在 `FileManagerUI` 初始化前 `loop.run_until_complete(session.ensure_started())`。
  - 应用退出时调用 `loop.run_until_complete(session.dispose())` 并关闭循环。

## 4. 依赖与测试
- [ ] `pan_client/requirements.txt` 添加 `mcp`, `pytest`, `pytest-asyncio`，并标注 Python 版本要求。
- [ ] 新增 `tests/integration/test_mcp_flow.py`：
  - 使用 `pytest.mark.asyncio` 启动 `McpSession`，调用 `list_files`/`upload_file` 工具验证返回的字段能被 `normalize_entry` 消费。
  - 断言 `FileManagerUI.display_files` 接收的数据包含 `__source`、`is_dir` 等统一字段。
- [ ] `README.md` / `docs/BAIDU_OAUTH_SETUP.md` 增补「MCP 模式使用方法」，包括环境变量、启动命令、常见错误（例如 `ToolTimeoutError`、`RateLimitExceeded`）。

## 5. 监控与日志
- [ ] 新增 `pan_client/core/logger.py`：封装 `logging.getLogger`，读取配置中的 `logging.level`。
- [ ] `McpSession.invoke_tool` 在调用前后记录耗时、参数摘要、错误码；与 UI 状态栏联动，出现重试/断线时提示用户。
- [ ] 根据需要把限流信息发送到系统托盘通知（`FileManagerUI.create_tray_icon` 中追加提示）。
