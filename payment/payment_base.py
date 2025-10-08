"""支付基类，定义支付接口的基本规范"""
from abc import ABC, abstractmethod

class PaymentBase(ABC):
    """支付抽象基类"""
    
    @abstractmethod
    def create_order(self, amount: float, subject: str, **kwargs) -> dict:
        """创建订单
        
        Args:
            amount: 支付金额
            subject: 订单标题
            **kwargs: 其他参数
            
        Returns:
            dict: 包含订单信息的字典
        """
        pass
    
    @abstractmethod
    def verify_payment(self, order_id: str) -> bool:
        """验证支付状态
        
        Args:
            order_id: 订单ID
            
        Returns:
            bool: 支付是否成功
        """
        pass 