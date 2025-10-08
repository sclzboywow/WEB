"""支付宝PC网站支付实现"""
from alipay import AliPay
import time
import webbrowser
import os
import json
from .config import ALIPAY_F2F_CONFIG, GATEWAY_URLS, ORDER_CONFIG, KEY_PATH_CONFIG
from .payment_record import PaymentRecord

class AlipayPC:
    """支付宝PC网站支付"""
    def __init__(self):
        """初始化支付宝客户端"""
        try:
            # 读取密钥文件
            current_dir = os.path.dirname(os.path.abspath(__file__))
            private_key_path = os.path.join(current_dir, "private_key.pem")
            public_key_path = os.path.join(current_dir, "public_key.pem")
            
            with open(private_key_path, 'r') as f:
                app_private_key = f.read().strip()
            with open(public_key_path, 'r') as f:
                alipay_public_key = f.read().strip()
            
            # 初始化支付宝客户端
            self.client = AliPay(
                appid=ALIPAY_F2F_CONFIG["app_id"],
                app_private_key_string=app_private_key,
                alipay_public_key_string=alipay_public_key,
                sign_type="RSA2",
                debug=ALIPAY_F2F_CONFIG["use_sandbox"]
            )
            
            # 设置网关
            self.gateway = GATEWAY_URLS["sandbox"] if ALIPAY_F2F_CONFIG["use_sandbox"] else GATEWAY_URLS["production"]
            
        except FileNotFoundError as e:
            raise
        except Exception as e:
            raise
            
        self.order_config = ORDER_CONFIG
        self.payment_record = PaymentRecord()

    def create_web_pay(self, amount: float, subject: str, user_id: str) -> dict:
        """创建PC网站支付订单
        
        Args:
            amount: 支付金额
            subject: 订单标题
            user_id: 用户ID
            
        Returns:
            dict: 包含支付链接和订单信息
        """
        # 参数验证
        if not isinstance(amount, (int, float)) or amount <= 0:
            return {"success": False, "error": "无效的金额"}
        if not subject or not user_id:
            return {"success": False, "error": "订单标题和用户ID不能为空"}
            
        order_id = f"{self.order_config['prefix']}_{int(time.time())}_{user_id}"
        
        try:
            # 创建PC支付订单
            order_string = self.client.api_alipay_trade_page_pay(
                out_trade_no=order_id,
                total_amount=str(round(amount, 2)),
                subject=subject,
                return_url="",  # 支付完成后的跳转地址（本地软件不需要）
                notify_url="",  # 回调通知地址（本地软件不需要）
            )
            
            # 生成完整支付链接
            pay_url = f"{self.gateway}?{order_string}"
            
            # 打开浏览器
            webbrowser.open(pay_url)
            
            return {
                "success": True,
                "order_id": order_id,
                "pay_url": pay_url
            }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def query_order(self, order_id: str) -> dict:
        """查询订单状态
        
        Args:
            order_id: 订单号
            
        Returns:
            dict: 订单状态信息
        """
        try:
            # 添加重试机制
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    result = self.client.api_alipay_trade_query(out_trade_no=order_id)
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        raise e
                    time.sleep(1)
            
            if result.get('code') == '10000':
                is_paid = result.get('trade_status') == "TRADE_SUCCESS"
                
                # 如果支付成功，记录到表格
                if is_paid:
                    try:
                        success, msg = self.payment_record.record_payment(
                            order_id=order_id,
                            machine_code=order_id.split('_')[-1],  # 从订单号获取机器码
                            amount=float(result.get('total_amount', 0))
                        )
                        if not success:
                            print(f"支付记录失败: {msg}")
                    except Exception as e:
                        print(f"支付记录异常: {e}")
                
                return {
                    "success": True,
                    "paid": is_paid,
                    "status": result.get('trade_status'),
                    "amount": float(result.get('total_amount', 0))
                }
            else:
                error_msg = result.get('sub_msg') or result.get('msg', '查询失败')
                print(f"查询订单失败: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except Exception as e:
            print(f"查询订单异常: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
