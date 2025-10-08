"""支付记录管理模块"""
import json
import logging
import requests
import urllib3
from datetime import datetime, timedelta
from typing import Tuple
import os
from pan_client.log_utils import get_log_directory

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(get_log_directory(), 'payment.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('payment_record')

class PaymentRecord:
    """支付记录管理类"""
    
    def __init__(self):
        # WPS文档API配置
        self.base_url = "https://365.kdocs.cn"
        self.config = {
            "token": "77cSmhKcRXPO2PCbVYLuxr",
            "file_id": "ch71K5yeYadT",
            "script_id": "V2-6FwYngnKQgLPZrkKPfsZxc"
        }
        
        # 禁用SSL警告
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # 创建会话
        self.session = requests.Session()
        self.session.verify = False
        self.session.trust_env = False
        
        # 设置请求头
        self.headers = {
            "Content-Type": "application/json",
            "AirScript-Token": self.config['token']
        }
        
    def record_payment(self, order_id: str, machine_code: str, amount: float) -> Tuple[bool, str]:
        """记录支付信息
        
        Args:
            order_id: 支付宝订单号
            machine_code: 用户机器码
            amount: 支付金额
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            # 准备支付数据
            now = datetime.now()
            expire_time = now + timedelta(days=365)  # 一年会员期限
            
            context = {
                "argv": {
                    "action": "write",
                    "data": {
                        "订单号": order_id,
                        "机器码": machine_code,
                        "商品名称": "Modern Pan VIP会员",
                        "支付金额": str(amount),
                        "支付时间": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "支付状态": "已支付",
                        "开通时间": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "到期时间": expire_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "备注": ""
                    }
                }
            }
            
            # 构造请求数据
            payload = {
                "Context": context
            }
            
            # 发送到WPS文档
            url = f"{self.base_url}/api/v3/ide/file/{self.config['file_id']}/script/{self.config['script_id']}/sync_task"
            
            logger.info(f"准备记录支付数据: {json.dumps(context, ensure_ascii=False)}")
            
            response = self.session.post(url, json=payload, headers=self.headers)
            
            if response.status_code == 200:
                result = response.json()
                if result and 'data' in result and 'result' in result['data']:
                    try:
                        data = json.loads(result['data']['result'])
                        success = data.get('success', False)
                        if success:
                            logger.info("支付记录成功")
                            return True, "支付记录已保存"
                        else:
                            error_msg = data.get('error', '未知错误')
                            logger.error(f"支付记录失败: {error_msg}")
                            return False, f"支付记录失败: {error_msg}"
                    except Exception as e:
                        logger.error(f"解析响应失败: {e}")
                        
            logger.error(f"支付记录失败: {response.text}")
            return False, "支付记录失败,请稍后重试"
            
        except Exception as e:
            logger.error(f"记录支付异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, f"支付记录失败: {str(e)}" 