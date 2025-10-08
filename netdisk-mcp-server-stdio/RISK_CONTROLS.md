# 风控系统配置文档

## 概述

本系统实现了完整的风控机制，包括频控、限额、重复购买检查等功能，确保平台安全和用户体验。

## 频控配置

### 配置参数

```python
RATE_LIMITS = {
    'create_order': {'max_requests': 10, 'window_seconds': 60},  # 1分钟内最多10次下单
    'create_payout': {'max_requests': 3, 'window_seconds': 60},  # 1分钟内最多3次提现申请
    'payment_config': {'max_requests': 5, 'window_seconds': 300},  # 5分钟内最多5次配置修改
}
```

### 频控规则

| 操作类型 | 时间窗口 | 最大次数 | 说明 |
|---------|---------|---------|------|
| 创建订单 | 60秒 | 10次 | 防止恶意刷单 |
| 提现申请 | 60秒 | 3次 | 防止频繁提现 |
| 支付配置 | 300秒 | 5次 | 防止误操作 |

## 限额配置

### 提现限额

```python
LIMITS = {
    'min_payout_amount': 100,      # 最小提现金额（分） = 1.00元
    'max_payout_amount': 1000000,  # 最大提现金额（分） = 10000.00元
    'daily_payout_limit': 5000000, # 每日提现限额（分） = 50000.00元
}
```

### 限额规则

| 限制类型 | 最小值 | 最大值 | 说明 |
|---------|--------|--------|------|
| 单次提现 | 1.00元 | 10,000.00元 | 防止小额测试和超大额风险 |
| 每日提现 | - | 50,000.00元 | 防止大额资金风险 |

## 重复购买检查

### 功能说明

- 检查用户是否已购买过相同商品
- 返回警告信息，提示用户确认
- 支持批量商品检查

### 检查逻辑

```python
def check_duplicate_purchase(buyer_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    # 查询用户已购买的商品
    # 对比当前购买商品列表
    # 返回重复商品信息
```

## 提现状态检查

### 功能说明

- 防止用户同时有多个pending状态的提现申请
- 确保提现流程的完整性
- 避免资金冻结风险

### 检查逻辑

```python
def check_pending_payout_requests(user_id: str) -> Dict[str, Any]:
    # 查询用户pending状态的提现申请数量
    # 如果 > 0，则拒绝新的提现申请
```

## 审计日志

### 日志类型

| 日志表 | 记录内容 | 用途 |
|--------|---------|------|
| `rate_limit_logs` | 频控操作记录 | 监控异常操作 |
| `order_logs` | 订单操作记录 | 订单流程审计 |
| `wallet_logs` | 钱包变动记录 | 资金流水审计 |
| `payout_logs` | 提现操作记录 | 提现流程审计 |
| `payment_callback_logs` | 支付回调记录 | 支付流程审计 |

### 日志字段

```sql
-- 频控日志
CREATE TABLE rate_limit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at REAL NOT NULL
);

-- 订单日志
CREATE TABLE order_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    user_id TEXT,
    created_at REAL NOT NULL
);
```

## 风控流程

### 订单创建流程

1. 检查用户频控限制
2. 检查重复购买
3. 验证商品状态
4. 创建订单
5. 记录操作日志

### 提现申请流程

1. 检查用户频控限制
2. 检查提现金额限制
3. 检查pending状态
4. 验证钱包余额
5. 创建提现申请
6. 冻结资金
7. 记录操作日志

### 支付配置流程

1. 检查管理员频控限制
2. 验证配置参数
3. 加密敏感数据
4. 保存配置
5. 记录操作日志

## 错误处理

### 频控错误

```json
{
    "status": "error",
    "message": "操作过于频繁，60秒内最多允许10次create_order操作",
    "retry_after": 60
}
```

### 限额错误

```json
{
    "status": "error",
    "message": "提现金额不能少于1.00元"
}
```

### 重复购买警告

```json
{
    "status": "warning",
    "message": "您已购买过以下商品: 商品A, 商品B，是否继续？",
    "duplicate_items": ["商品A", "商品B"]
}
```

## 监控指标

### 关键指标

- 频控触发次数
- 限额拒绝次数
- 重复购买警告次数
- 异常操作频率

### 告警阈值

- 单用户1小时内频控触发 > 5次
- 单用户1日内限额拒绝 > 10次
- 系统1小时内异常操作 > 100次

## 配置调整

### 调整频控参数

修改 `services/risk_service.py` 中的 `RATE_LIMITS` 配置：

```python
RATE_LIMITS = {
    'create_order': {'max_requests': 20, 'window_seconds': 60},  # 调整为20次
    # ... 其他配置
}
```

### 调整限额参数

修改 `services/risk_service.py` 中的 `LIMITS` 配置：

```python
LIMITS = {
    'min_payout_amount': 200,      # 调整为2.00元
    'max_payout_amount': 2000000,  # 调整为20,000.00元
    # ... 其他配置
}
```

## 测试验证

### 运行风控测试

```bash
cd netdisk-mcp-server-stdio
python test_risk_controls.py
```

### 测试覆盖

- ✅ 订单创建频控测试
- ✅ 提现申请频控测试
- ✅ 支付配置频控测试
- ✅ 提现限额测试
- ✅ 重复购买检查测试
- ✅ 提现状态检查测试

## 安全建议

1. **定期审查日志** - 监控异常操作模式
2. **动态调整参数** - 根据业务情况调整限制
3. **异常告警** - 设置关键指标告警
4. **数据备份** - 定期备份审计日志
5. **权限控制** - 限制风控配置修改权限

## 联系方式

如有风控相关问题，请联系系统管理员或查看相关API文档。
