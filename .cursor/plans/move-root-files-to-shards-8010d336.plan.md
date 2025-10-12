<!-- 8010d336-f865-4b3e-830a-4301ca3907da 889c058f-6bb8-4996-bff1-1a0b5ee1b33c -->
# MCP基础文件管理功能落地计划

## 1. 客户端UI层改造 (`pan_client/ui/`)

### 1.1 统一字段处理 - `modern_pan.py`

**问题**：`load_dir`/`display_files` 直接消费REST格式（`server_filename`、`list`等），需统一到抽象接口。

**改造**：

- `load_dir` (L1230-1320): 改用 `self.client.list_files()` 和 `normalize_entry()`
- `display_files`: 检查 `__source`、`is_dir`、`path` 等统一键
- 确保共享资源与个人网盘视图使用同一渲染逻辑

### 1.2 Worker线程适配

**UploadWorker/DownloadWorker/SingleReadWorker** (L2103-2253):

- 构造函数接受 `AbstractNetdiskClient` 而非硬编码 `ApiClient`
- `run()` 方法通过协程适配层调用MCP工具
- **关键修复**：修正 `DownloadWorker.run` 中的缩进问题（`for chunk` 缩进异常）

### 1.3 批量操作封装

**上下文菜单操作** (L1604-1864):

- `_paste_files`、`_paste_files_to_folder`、`_context_menu_requested`
- 当MCP工具只支持单文件时，在客户端循环调用并聚合结果
- 保留冲突对话框与状态栏提示

### 1.4 错误处理统一

**搜索/阅读/下载入口**:

- `_start_search_threads`、`_read_single`、`_download_multiple`
- 返回统一的 `FileEntry`
- 捕获 `McpError` 并展示限流/鉴权信息（避免暴露REST错误码）

### 1.5 客户端抽象层完善

**`pan_client/core/` 改造**:

- 重命名 `api.py` → `rest_client.py`（保留为 `RestNetdiskClient`）
- 完善 `McpNetdiskClient` 覆盖所有文件管理方法：
  - 列举文件、缓存列表
  - 上传、流式下载
  - 批量删除/移动/复制
  - 冲突检查

## 2. MCP服务器端改造 (`netdisk-mcp-server-stdio/`)

### 2.1 新增缓存列表工具

**问题**：缺少 `get_cached_files` / `list_shared_resources` 接口

**方案**：

- 新增工具返回缓存条目，标记 `__source="shared"`
- 与Flask版 `/cache/files` 行为一致
- 支持共享资源视图

### 2.2 批量操作支持

**当前限制**：`copy_file`/`move_file` 仅处理单项

**改进方案**（二选一）：

- **方案A**：新增 `copy_files_batch`/`move_files_batch` 工具
- **方案B**：客户端循环调用单项工具，暴露失败条目

**匹配UI需求**：

- 支持批量传输 `{path,dest}` 列表
- 配合冲突对话框设计

### 2.3 下载机制优化

**问题**：`download_file` 返回服务器本地路径，客户端无法直接消费

**改进方案**（二选一）：

- **方案A**：返回可读取的本地临时路径，客户端通过SSH/SFTP获取
- **方案B**：生成签名的HTTP下载URL
- **方案C**：MCP二进制流接口传输文件内容

**配合现有Worker**：

- `DownloadWorker` (L2132-2247) 需要能获取文件内容
- `SingleReadWorker` 需要临时文件路径

### 2.4 限流与校验优化

**问题**：批量操作前的存在性校验可能触发频控

**优化**：

- 与客户端约定缓存目录树
- 增加"跳过校验"快速路径
- 限流时返回结构化错误供UI渲染

## 3. 端到端验证

### 3.1 集成测试扩展

**`tests/integration/test_mcp_flow.py`** 补充：

```python
async def test_file_management_flow(mcp_session):
    # 1. 列举初始文件
    initial = await mcp_session.invoke_tool('list_files', path='/')
    
    # 2. 上传临时文件
    with tempfile.NamedTemporaryFile() as f:
        upload_result = await mcp_session.invoke_tool(
            'upload_file', 
            local_path=f.name, 
            remote_dir='/'
        )
    
    # 3. 确认列表增加
    after_upload = await mcp_session.invoke_tool('list_files', path='/')
    assert len(after_upload['list']) == len(initial['list']) + 1
    
    # 4. 下载并校验
    download_result = await mcp_session.invoke_tool(
        'download_file',
        path=upload_result['path']
    )
    # 验证文件内容
    
    # 5. 删除并验证回滚
    await mcp_session.invoke_tool('delete_file', path=upload_result['path'])
    final = await mcp_session.invoke_tool('list_files', path='/')
    assert len(final['list']) == len(initial['list'])
```

### 3.2 UI烟雾测试

**使用 pytest-qt**:

```python
def test_file_manager_ui_smoke(qtbot, mcp_client):
    window = FileManagerUI(client=mcp_client)
    qtbot.addWidget(window)
    
    # 模拟上传
    with qtbot.waitSignal(window.upload_complete):
        # 触发上传操作
        pass
    
    # 验证状态栏
    assert "上传成功" in window.statusBar().currentMessage()
    
    # 验证client调用次数
    assert mcp_client.upload_file.call_count == 1
```

**验证点**：

- 状态栏消息
- 进度条信号
- `AbstractNetdiskClient` 调用次数
- 同步+线程模型兼容性

## 4. 实施顺序

1. **阶段1**：客户端抽象层完善（`rest_client.py` + `McpNetdiskClient` 批量方法）
2. **阶段2**：服务器端工具扩展（缓存列表、批量操作、下载优化）
3. **阶段3**：UI层Worker适配（修复缩进、接受抽象客户端）
4. **阶段4**：统一字段与错误处理（`normalize_entry`、`McpError`）
5. **阶段5**：端到端验证（集成测试 + UI烟雾测试）

## 5. 关键文件清单

- `pan_client/ui/modern_pan.py` (L1230-1320, L2103-2253, L1604-1864)
- `pan_client/core/api.py` → `rest_client.py` (L16-197, L200-264)
- `pan_client/core/mcp_client.py` (新增批量方法)
- `netdisk-mcp-server-stdio/netdisk.py` (L696-780, L842-989, L900-1018)
- `tests/integration/test_mcp_flow.py`
- `tests/ui/test_file_manager_smoke.py` (新建)

### To-dos

- [ ] 在modern_pan.py中集成重连对话框