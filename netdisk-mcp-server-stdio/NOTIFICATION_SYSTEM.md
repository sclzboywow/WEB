# 通知系统文档

## 概述

本系统实现了完整的通知中心功能，支持实时通知推送、状态管理、前端展示等功能，提升用户体验和平台交互性。

## 功能特性

### 1. 通知类型

| 通知类型 | 发送对象 | 触发场景 | 示例内容 |
|---------|---------|---------|---------|
| 支付成功 | 买家 | 订单支付成功 | "您的订单 123 支付成功，金额 ¥99.00" |
| 新订单 | 卖家 | 买家下单 | "您有新的订单 123，买家：user001，金额：¥99.00" |
| 提现审核通过 | 卖家 | 提现申请通过 | "您的提现申请 456 已审核通过，金额 ¥500.00" |
| 提现审核拒绝 | 卖家 | 提现申请被拒 | "您的提现申请 456 未通过审核，原因：信息不完整" |
| 订单交付 | 买家 | 订单交付完成 | "您的订单 123 已交付完成，商品已添加到您的已购清单中" |
| 商品审核通过 | 卖家 | 商品审核通过 | "您的商品「测试商品」已通过审核，现在可以正常销售了" |
| 商品审核拒绝 | 卖家 | 商品审核被拒 | "您的商品「测试商品」未通过审核，原因：描述不清晰" |
| 系统维护 | 所有用户 | 系统维护 | "系统将于今晚22:00-24:00进行维护" |

### 2. 通知状态

- **unread**: 未读状态，显示红色徽章
- **read**: 已读状态，正常显示

### 3. 通知优先级

| 优先级 | 类型 | 颜色 | 说明 |
|--------|------|------|------|
| 高 | error | 红色 | 错误、失败类通知 |
| 中 | warning | 黄色 | 警告、提醒类通知 |
| 中 | success | 绿色 | 成功、完成类通知 |
| 低 | info | 蓝色 | 信息、一般类通知 |

## 技术实现

### 1. 后端服务

#### 通知服务 (`services/notify_service.py`)

```python
# 核心函数
def create_notification(user_id, title, content, notification_type, sender_role)
def get_user_notifications(user_id, limit, offset, status)
def mark_notification_read(notification_id, user_id)
def mark_all_notifications_read(user_id)
def get_unread_count(user_id)

# 专用通知函数
def send_payment_success_notification(buyer_id, order_id, amount_cents)
def send_order_created_notification(seller_id, order_id, buyer_id, amount_cents)
def send_payout_approved_notification(seller_id, payout_id, amount_cents)
def send_payout_rejected_notification(seller_id, payout_id, reason)
def send_order_delivered_notification(buyer_id, order_id, seller_id)
def send_listing_approved_notification(seller_id, listing_id, title)
def send_listing_rejected_notification(seller_id, listing_id, title, reason)
def send_system_maintenance_notification(user_id, message)
```

#### API端点 (`api/notify.py`)

```python
GET /api/notify/{user_id}              # 获取用户通知列表
GET /api/notify/{user_id}/unread-count # 获取未读通知数量
POST /api/notify/{notification_id}/read # 标记通知为已读
POST /api/notify/{user_id}/read-all    # 标记所有通知为已读
```

### 2. 前端实现

#### 通知组件

**通知徽章**
```html
<div id="notification-badge" class="relative">
  <button id="btn-notifications" class="btn btn-secondary">通知</button>
  <span id="unread-count" class="absolute -top-2 -right-2 bg-red-500 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center hidden">0</span>
</div>
```

**通知模态框**
```html
<div id="notification-modal" class="modal hidden">
  <div class="modal-content max-w-2xl">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold">我的通知</h3>
      <div class="flex gap-2">
        <button id="btn-mark-all-read" class="btn btn-secondary text-sm">全部已读</button>
        <button id="close-notification-modal" class="text-gray-500 hover:text-gray-700 text-xl">&times;</button>
      </div>
    </div>
    <div id="notification-content">
      <!-- 通知列表内容 -->
    </div>
  </div>
</div>
```

#### JavaScript功能

**核心函数**
```javascript
// 显示通知模态框
async function showNotificationModal()

// 隐藏通知模态框
function hideNotificationModal()

// 渲染通知列表
function renderNotifications(notifications)

// 标记通知已读
async function markNotificationRead(notificationId)

// 标记所有通知已读
async function markAllNotificationsRead()

// 加载未读数量
async function loadUnreadCount()

// 通知类型样式
function getNotificationTypeColor(type)
function getNotificationTypeText(type)
```

**轮询机制**
```javascript
// 每30秒检查一次未读通知
setInterval(() => {
  if (currentUserId) {
    loadUnreadCount();
  }
}, 30000);
```

### 3. 数据库设计

#### 通知表结构

```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    type TEXT DEFAULT 'info',
    status TEXT DEFAULT 'unread',
    sender_role TEXT DEFAULT 'system',
    created_at REAL DEFAULT (strftime('%s','now')),
    read_at REAL,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

#### 索引优化

```sql
-- 用户通知查询索引
CREATE INDEX idx_notifications_user_status ON notifications(user_id, status);
CREATE INDEX idx_notifications_created_at ON notifications(created_at DESC);
```

## 使用指南

### 1. 发送通知

#### 在服务层发送通知

```python
from services.notify_service import send_payment_success_notification

# 发送支付成功通知
result = send_payment_success_notification(
    buyer_id="user123",
    order_id=456,
    amount_cents=9900
)
```

#### 通过API发送通知

```python
# 创建通知
POST /api/notify/create
{
    "user_id": "user123",
    "title": "测试通知",
    "content": "这是一个测试通知",
    "type": "info"
}
```

### 2. 前端集成

#### 在页面中添加通知功能

```html
<!-- 1. 添加通知徽章 -->
<div id="notification-badge" class="relative">
  <button id="btn-notifications" class="btn btn-secondary">通知</button>
  <span id="unread-count" class="hidden">0</span>
</div>

<!-- 2. 添加通知模态框 -->
<div id="notification-modal" class="modal hidden">
  <!-- 模态框内容 -->
</div>

<!-- 3. 引入通知脚本 -->
<script>
  // 通知相关函数
  // 事件绑定
  // 轮询机制
</script>
```

#### 初始化通知功能

```javascript
// 在页面初始化时
async function init() {
  // 其他初始化代码...
  
  // 加载未读通知数量
  loadUnreadCount();
  
  // 启动轮询
  setInterval(() => {
    if (currentUserId) {
      loadUnreadCount();
    }
  }, 30000);
}
```

### 3. 通知管理

#### 查看通知列表

```javascript
// 获取用户通知
const response = await fetch(`/api/notify/${userId}?limit=20&offset=0`);
const data = await response.json();
```

#### 标记通知已读

```javascript
// 标记单个通知已读
await fetch(`/api/notify/${notificationId}/read?user_id=${userId}`, {
  method: 'POST'
});

// 标记所有通知已读
await fetch(`/api/notify/${userId}/read-all`, {
  method: 'POST'
});
```

## 配置选项

### 1. 轮询间隔

```javascript
// 修改轮询间隔（毫秒）
setInterval(() => {
  loadUnreadCount();
}, 60000); // 改为60秒
```

### 2. 通知显示数量

```javascript
// 修改通知列表显示数量
const response = await fetch(`/api/notify/${userId}?limit=50`);
```

### 3. 通知类型样式

```javascript
// 自定义通知类型样式
function getNotificationTypeColor(type) {
  const colors = {
    'success': 'bg-green-100 text-green-800',
    'warning': 'bg-yellow-100 text-yellow-800',
    'error': 'bg-red-100 text-red-800',
    'info': 'bg-blue-100 text-blue-800',
    'custom': 'bg-purple-100 text-purple-800' // 添加自定义类型
  };
  return colors[type] || 'bg-gray-100 text-gray-800';
}
```

## 性能优化

### 1. 数据库优化

- 使用索引优化查询性能
- 定期清理过期通知
- 分页加载通知列表

### 2. 前端优化

- 使用防抖避免频繁请求
- 缓存通知数据
- 懒加载通知内容

### 3. 轮询优化

- 根据用户活跃度调整轮询频率
- 页面隐藏时暂停轮询
- 使用WebSocket实现实时推送（可选）

## 监控指标

### 1. 关键指标

- 通知发送成功率
- 通知读取率
- 用户活跃度
- 系统响应时间

### 2. 告警阈值

- 通知发送失败率 > 5%
- 系统响应时间 > 2秒
- 未读通知积压 > 1000条

## 故障排除

### 1. 常见问题

**通知不显示**
- 检查用户ID是否正确
- 确认通知API端点可访问
- 查看浏览器控制台错误

**轮询不工作**
- 检查JavaScript错误
- 确认用户已登录
- 验证API响应格式

**通知样式异常**
- 检查CSS类名是否正确
- 确认Tailwind CSS已加载
- 验证HTML结构

### 2. 调试方法

```javascript
// 开启调试模式
console.log('通知数据:', notifications);
console.log('未读数量:', unreadCount);

// 检查API响应
fetch('/api/notify/user123/unread-count')
  .then(response => response.json())
  .then(data => console.log('API响应:', data));
```

## 扩展功能

### 1. 实时推送

- 使用WebSocket实现实时通知
- 支持浏览器推送通知
- 移动端推送支持

### 2. 通知模板

- 支持HTML格式通知
- 自定义通知模板
- 多语言支持

### 3. 通知分组

- 按类型分组显示
- 按时间分组显示
- 按重要性分组显示

## 联系方式

如有通知系统相关问题，请联系系统管理员或查看相关API文档。
