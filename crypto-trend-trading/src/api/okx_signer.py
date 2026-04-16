"""OKX API 签名和工具"""

import hmac
import base64
import hashlib
from typing import Dict, Optional


class OKXSigner:
    """OKX API请求签名器"""
    
    def __init__(self, api_key: str, secret_key: str, passphrase: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
    
    def sign(self, message: str) -> str:
        """
        生成签名
        
        Args:
            message: 待签名的消息 (timestamp + method + path + body)
            
        Returns:
            Base64编码的签名字符串
        """
        mac = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()
    
    def sign_request(
        self,
        timestamp: str,
        method: str,
        path: str,
        body: str = ""
    ) -> Dict[str, str]:
        """
        为请求生成签名头
        
        Args:
            timestamp: ISO 8601格式时间
            method: HTTP方法 (GET, POST等)
            path: 请求路径
            body: 请求体
            
        Returns:
            包含签名的请求头
        """
        message = f"{timestamp}{method}{path}{body}"
        signature = self.sign(message)
        
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }


def get_server_time() -> int:
    """获取服务器时间戳(毫秒)"""
    import time
    return int(time.time() * 1000)
