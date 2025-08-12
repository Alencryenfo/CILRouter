# -*- coding: utf-8 -*-
"""
日志模块
支持分等级日志记录，自动文件轮转，详细记录请求和响应信息
"""

import os
import json
import logging
import logging.handlers
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import Request, Response

# 模型回复字段预览长度
MODEL_PREVIEW_LENGTH = 200


def truncate_model_content(data: Any, limit: int = MODEL_PREVIEW_LENGTH) -> Any:
    """截断模型回复字段以限制日志体积"""
    if not isinstance(data, dict):
        return data

    choices = data.get("choices")
    if not isinstance(choices, list):
        return data

    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and len(content) > limit:
                message["content"] = content[:limit]
        text = choice.get("text")
        if isinstance(text, str) and len(text) > limit:
            choice["text"] = text[:limit]
    return data


class UTC8Formatter(logging.Formatter):
    """UTC+8时区的日志格式器"""
    
    def formatTime(self, record, datefmt=None):
        """格式化时间为UTC+8"""
        # 获取UTC时间并转换为UTC+8
        utc_time = datetime.fromtimestamp(record.created, timezone.utc)
        utc8_time = utc_time + timedelta(hours=8)
        
        if datefmt:
            return utc8_time.strftime(datefmt)
        else:
            return utc8_time.strftime('%Y-%m-%d %H:%M:%S')
    
    def converter(self, timestamp):
        """时间戳转换器"""
        return datetime.fromtimestamp(timestamp, timezone.utc) + timedelta(hours=8)


class CILRouterLogger:
    """CIL Router 专用日志记录器"""
    
    def __init__(self, log_level: str = "NONE", log_dir: str = "app/data/log"):
        """
        初始化日志记录器
        
        Args:
            log_level: 日志等级 (NONE, DEBUG, INFO, WARNING, ERROR)
            log_dir: 日志目录
        """
        self.log_level = log_level.upper()
        self.log_dir = Path(log_dir)
        self.logger = None
        
        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化日志记录器
        self._setup_logger()
    
    def _setup_logger(self):
        """设置日志记录器"""
        if self.log_level == "NONE":
            # 禁用所有日志
            self.logger = None
            return
        
        # 创建logger
        self.logger = logging.getLogger("cilrouter")
        for handler in list(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)
        
        # 设置日志等级
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR
        }
        self.logger.setLevel(level_map.get(self.log_level, logging.DEBUG))
        
        # 创建轮转文件处理器 (12MB轮转，最多8192份)
        log_file = self.log_dir / "cilrouter.log"
        handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=12 * 1024 * 1024,  # 12MB
            backupCount=8192,
            encoding='utf-8'
        )
        
        # 设置日志格式（使用UTC+8时区）
        formatter = UTC8Formatter(
            fmt='[%(asctime)s|%(levelname)-8s|%(name)s|%(filename)s:%(funcName)s():%(lineno)d]:%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            style='%'
        )
        handler.setFormatter(formatter)
        
        self.logger.addHandler(handler)
        
        # 防止日志传播到根logger
        self.logger.propagate = False
    
    def is_enabled(self) -> bool:
        """检查日志是否启用"""
        return self.logger is not None
    
    def debug(self, message: str, extra_data: Dict[str, Any] = None):
        """记录DEBUG级别日志"""
        if self.logger and self.logger.isEnabledFor(logging.DEBUG):
            self._log_with_data(logging.DEBUG, message, extra_data)
    
    def info(self, message: str, extra_data: Dict[str, Any] = None):
        """记录INFO级别日志"""
        if self.logger and self.logger.isEnabledFor(logging.INFO):
            self._log_with_data(logging.INFO, message, extra_data)
    
    def warning(self, message: str, extra_data: Dict[str, Any] = None):
        """记录WARNING级别日志"""
        if self.logger and self.logger.isEnabledFor(logging.WARNING):
            self._log_with_data(logging.WARNING, message, extra_data)
    
    def error(self, message: str, extra_data: Dict[str, Any] = None):
        """记录ERROR级别日志"""
        if self.logger and self.logger.isEnabledFor(logging.ERROR):
            self._log_with_data(logging.ERROR, message, extra_data)
    
    def _log_with_data(self, level: int, message: str, extra_data: Dict[str, Any] = None):
        """记录带有额外数据的日志"""
        if not self.logger:
            return
        
        log_entry = {"message": message}
        if extra_data:
            # 处理不可序列化的数据
            sanitized_data = self._sanitize_data(extra_data)
            log_entry.update(sanitized_data)
        
        try:
            # 将字典转换为JSON字符串
            json_str = json.dumps(log_entry, ensure_ascii=False, separators=(',', ':'))
            self.logger.log(level, json_str)
        except (TypeError, ValueError) as e:
            # 如果仍然无法序列化，记录简化版本
            simple_entry = {"message": message, "serialization_error": str(e)}
            json_str = json.dumps(simple_entry, ensure_ascii=False, separators=(',', ':'))
            self.logger.log(level, json_str)
    
    def _sanitize_data(self, data: Any) -> Any:
        """清理数据，使其可以JSON序列化"""
        if isinstance(data, dict):
            return {k: self._sanitize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        elif isinstance(data, bytes):
            try:
                # 尝试解码为字符串
                return data.decode('utf-8')
            except UnicodeDecodeError:
                # 如果无法解码，转换为十六进制字符串
                return f"<binary:{data.hex()[:100]}{'...' if len(data) > 50 else ''}>"
        elif hasattr(data, '__dict__'):
            # 处理自定义对象
            return f"<object:{data.__class__.__name__}>"
        elif callable(data):
            # 处理函数/方法
            return f"<callable:{data.__name__ if hasattr(data, '__name__') else 'unknown'}>"
        else:
            try:
                # 测试是否可序列化
                json.dumps(data)
                return data
            except (TypeError, ValueError):
                # 如果不可序列化，转换为字符串
                return str(data)
    
    def log_request_start(self, request: Request, client_ip: str):
        """记录请求开始"""
        if not self.is_enabled():
            return
        
        # 获取请求体（如果有）
        # 注意：在中间件中，request.body()只能调用一次
        request_data = {
            "type": "request_start",
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query": dict(request.query_params),
            "headers": dict(request.headers),
            "client_ip": client_ip,
            "timestamp": get_utc8_timestamp()
        }
        
        self.debug("请求开始", request_data)
    
    def log_request_body(self, body: bytes):
        """记录请求体"""
        if not self.is_enabled():
            return
        
        try:
            # 尝试解析为UTF-8文本
            if body:
                body_text = body.decode('utf-8')
                # 尝试解析为JSON，如果失败就记录原始文本
                try:
                    body_json = json.loads(body_text)
                    body_data = {"type": "request_body", "body": body_json}
                except json.JSONDecodeError:
                    body_data = {"type": "request_body", "body": body_text}
            else:
                body_data = {"type": "request_body", "body": None}
            
            self.debug("请求体", body_data)
        except UnicodeDecodeError:
            # 如果不能解码为UTF-8，记录为二进制数据
            body_data = {
                "type": "request_body", 
                "body": f"<binary data: {len(body)} bytes>"
            }
            self.debug("请求体", body_data)
    
    def log_response(self, response: Response, body_content: bytes = None):
        """记录响应信息"""
        if not self.is_enabled():
            return
        
        response_data = {
            "type": "response",
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "timestamp": get_utc8_timestamp()
        }
        
        # 记录响应体（如果有）
        if body_content is not None:
            try:
                if body_content:
                    body_text = body_content.decode('utf-8')
                    # 尝试解析为JSON
                    try:
                        body_json = json.loads(body_text)
                        response_data["body"] = truncate_model_content(body_json)
                    except json.JSONDecodeError:
                        response_data["body"] = body_text
                else:
                    response_data["body"] = None
            except UnicodeDecodeError:
                response_data["body"] = f"<binary data: {len(body_content)} bytes>"
        
        self.debug("响应", response_data)
    
    def log_forward_request(self, method: str, url: str, headers: Dict[str, str], body: bytes = None, attempt: int = 1):
        """记录转发请求"""
        if not self.is_enabled():
            return
        
        forward_data = {
            "type": "forward_request",
            "method": method,
            "url": url,
            "headers": headers,
            "attempt": attempt,
            "timestamp": get_utc8_timestamp()
        }
        
        # 记录请求体
        if body is not None:
            try:
                if body:
                    body_text = body.decode('utf-8')
                    try:
                        body_json = json.loads(body_text)
                        forward_data["body"] = truncate_model_content(body_json)
                    except json.JSONDecodeError:
                        forward_data["body"] = body_text
                else:
                    forward_data["body"] = None
            except UnicodeDecodeError:
                forward_data["body"] = f"<binary data: {len(body)} bytes>"
        
        self.debug("转发请求", forward_data)
    
    def log_forward_response(self, status_code: int, headers: Dict[str, str], body: bytes = None):
        """记录转发响应"""
        if not self.is_enabled():
            return
        
        response_data = {
            "type": "forward_response",
            "status_code": status_code,
            "headers": headers,
            "timestamp": get_utc8_timestamp()
        }
        
        # 记录响应体
        if body is not None:
            try:
                if body:
                    body_text = body.decode('utf-8')
                    try:
                        body_json = json.loads(body_text)
                        response_data["body"] = truncate_model_content(body_json)
                    except json.JSONDecodeError:
                        response_data["body"] = body_text
                else:
                    response_data["body"] = None
            except UnicodeDecodeError:
                response_data["body"] = f"<binary data: {len(body)} bytes>"
        
        self.debug("转发响应", response_data)
    
    def log_rate_limit(self, client_ip: str, allowed: bool, bucket_status: Dict[str, Any] = None):
        """记录限流信息"""
        if not self.is_enabled():
            return
        
        rate_limit_data = {
            "type": "rate_limit",
            "client_ip": client_ip,
            "allowed": allowed,
            "timestamp": get_utc8_timestamp()
        }
        
        if bucket_status:
            rate_limit_data["bucket_status"] = bucket_status
        
        if allowed:
            self.debug("限流检查通过", rate_limit_data)
        else:
            self.warning("请求被限流", rate_limit_data)
    
    def log_ip_block(self, client_ip: str, blocked: bool):
        """记录IP阻止信息"""
        if not self.is_enabled():
            return
        
        block_data = {
            "type": "ip_block",
            "client_ip": client_ip,
            "blocked": blocked,
            "timestamp": get_utc8_timestamp()
        }
        
        if blocked:
            self.warning("IP被阻止", block_data)
        else:
            self.debug("IP检查通过", block_data)
    
    def log_provider_switch(self, old_index: int, new_index: int, success: bool):
        """记录供应商切换"""
        if not self.is_enabled():
            return
        
        switch_data = {
            "type": "provider_switch",
            "old_index": old_index,
            "new_index": new_index,
            "success": success,
            "timestamp": get_utc8_timestamp()
        }
        
        if success:
            self.info("供应商切换成功", switch_data)
        else:
            self.error("供应商切换失败", switch_data)
    
    def log_error(self, error_type: str, error_message: str, error_details: Dict[str, Any] = None):
        """记录错误信息"""
        if not self.is_enabled():
            return
        
        error_data = {
            "type": "error",
            "error_type": error_type,
            "error_message": error_message,
            "timestamp": get_utc8_timestamp()
        }
        
        if error_details:
            error_data["error_details"] = error_details
        
        self.error("系统错误", error_data)


def get_utc8_timestamp() -> str:
    """获取UTC+8时区的时间戳字符串"""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()


# 全局日志实例，将在配置加载后初始化
logger: Optional[CILRouterLogger] = None


def init_logger(log_level: str = "NONE", log_dir: str = "app/data/log"):
    """初始化全局日志实例"""
    global logger
    logger = CILRouterLogger(log_level=log_level, log_dir=log_dir)


def get_logger() -> Optional[CILRouterLogger]:
    """获取全局日志实例"""
    return logger