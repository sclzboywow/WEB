#!/usr/bin/env python3
"""
百度网盘访问令牌获取工具
"""
import webbrowser
import requests
import json

# 你的应用信息
APP_KEY = "07Tm8NRp8cXndCTJTU6uVkLE0IgsB0WM"
SECRET_KEY = "8H5qC9jqNrgAyzYaqLMeCgBR3HJeFubu"

def get_authorization_code():
    """获取授权码"""
    auth_url = f"https://openapi.baidu.com/oauth/2.0/authorize?response_type=code&client_id={APP_KEY}&redirect_uri=oob&scope=basic netdisk"
    
    print("正在打开浏览器进行授权...")
    print(f"如果浏览器没有自动打开，请手动访问：\n{auth_url}")
    
    # 自动打开浏览器
    webbrowser.open(auth_url)
    
    # 等待用户输入授权码
    auth_code = input("\n请复制授权页面显示的授权码并粘贴到这里: ").strip()
    return auth_code

def get_access_token(auth_code):
    """用授权码换取访问令牌"""
    token_url = "https://openapi.baidu.com/oauth/2.0/token"
    
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": APP_KEY,
        "client_secret": SECRET_KEY,
        "redirect_uri": "oob"
    }
    
    print("正在获取访问令牌...")
    response = requests.post(token_url, data=data)
    
    if response.status_code == 200:
        result = response.json()
        if "access_token" in result:
            print("✅ 成功获取访问令牌！")
            print(f"访问令牌: {result['access_token']}")
            print(f"过期时间: {result.get('expires_in', '未知')} 秒")
            print(f"刷新令牌: {result.get('refresh_token', '无')}")
            
            # 获取当前脚本所在目录
            import os
            script_dir = os.path.dirname(os.path.abspath(__file__))
            env_file = os.path.join(script_dir, '.env')
            
            print(f"保存路径: {script_dir}")
            
            # 保存到.env文件
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write(f"BAIDU_NETDISK_ACCESS_TOKEN={result['access_token']}\n")
                f.write(f"BAIDU_NETDISK_REFRESH_TOKEN={result.get('refresh_token', '')}\n")
                f.write(f"BAIDU_NETDISK_EXPIRES_IN={result.get('expires_in', '')}\n")
                f.write(f"BAIDU_NETDISK_SCOPE={result.get('scope', '')}\n")
                f.write(f"BAIDU_NETDISK_APP_KEY={APP_KEY}\n")
                f.write(f"BAIDU_NETDISK_SECRET_KEY={SECRET_KEY}\n")
                f.write(f"LLM_API_KEY=your_llm_api_key_here\n")
            
            print(f"\n✅ 访问令牌已保存到: {env_file}")
            return result['access_token']
        else:
            print("❌ 获取访问令牌失败:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"❌ 请求失败，状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
    
    return None

def main():
    print("=== 百度网盘访问令牌获取工具 ===")
    print(f"App Key: {APP_KEY}")
    print(f"Secret Key: {SECRET_KEY}")
    print()
    
    try:
        # 步骤1: 获取授权码
        auth_code = get_authorization_code()
        
        if not auth_code:
            print("❌ 未输入授权码，退出")
            return
        
        # 步骤2: 获取访问令牌
        access_token = get_access_token(auth_code)
        
        if access_token:
            print("\n🎉 配置完成！现在你可以使用MCP服务器了。")
            print("\n使用方法:")
            print("1. 在Cursor中配置MCP服务器")
            print("2. 或者运行: uv run python client_demo_stdio.py")
        else:
            print("\n❌ 获取访问令牌失败，授权码可能已过期")
            print("请重新运行脚本获取新的授权码")
            
    except KeyboardInterrupt:
        print("\n\n用户取消操作")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")

if __name__ == "__main__":
    main()
