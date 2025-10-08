"""支付宝PC网站支付测试脚本"""
import sys
import time
import os

# 添加当前目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from alipay_client import AlipayPC

def print_divider():
    print("\n" + "="*50 + "\n")

def test_payment():
    print("支付宝PC网站支付测试程序")
    print_divider()
    
    try:
        # 初始化支付宝客户端
        alipay = AlipayPC()
        
        # 输入测试金额
        while True:
            try:
                amount = float(input("请输入测试金额（元）: "))
                if amount <= 0:
                    print("金额必须大于0")
                    continue
                break
            except ValueError:
                print("请输入有效的金额数字")
        
        print_divider()
        print(f"正在创建{amount}元的测试订单...")
        
        # 创建支付订单
        result = alipay.create_web_pay(
            amount=amount,
            subject=f"测试商品 - {amount}元",
            user_id="test001"
        )
        
        if not result["success"]:
            print(f"创建订单失败: {result['error']}")
            return
            
        order_id = result["order_id"]
        print(f"订单创建成功！\n订单号: {order_id}")
        print("\n已在浏览器中打开支付页面，请完成支付...")
        
        print_divider()
        print("开始监听支付状态...")
        
        # 循环查询支付状态
        query_count = 0
        max_queries = 60  # 最多等待2分钟
        
        while query_count < max_queries:
            query_count += 1
            status = alipay.query_order(order_id)
            
            if status["success"]:
                if status["paid"]:
                    print_divider()
                    print("✓ 支付成功！")
                    return True
                    
                print(f"等待支付中... ({query_count}/{max_queries})")
                print(f"当前状态: {status['status']}")
            else:
                print(f"查询失败: {status['error']}")
            
            time.sleep(2)  # 每2秒查询一次
        
        print_divider()
        print("❌ 支付超时，请重新测试")
        return False
        
    except KeyboardInterrupt:
        print_divider()
        print("\n测试已取消")
        return False
        
    except Exception as e:
        print_divider()
        print(f"测试过程发生错误: {str(e)}")
        return False

if __name__ == "__main__":
    try:
        test_payment()
    except KeyboardInterrupt:
        print("\n\n程序已退出")
    finally:
        print_divider()
        input("按回车键退出...")
