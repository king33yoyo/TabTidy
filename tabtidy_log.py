import logging
import os
from datetime import datetime
from typing import Optional

class TabTidyLogger:
    """TabTidy日志管理类
    
    用于管理TabTidy应用的日志记录，支持同时输出到控制台和文件。
    
    属性:
        log_dir (str): 日志文件存储目录
        log_file (str): 当前日志文件的完整路径
        logger (logging.Logger): 日志记录器实例
    """
    
    def __init__(self, log_dir: str = "logs", log_level: int = logging.INFO):
        """初始化日志管理器
        
        Args:
            log_dir (str): 日志文件存储目录，默认为'logs'
            log_level (int): 日志级别，默认为logging.INFO
        """
        self.log_dir = log_dir
        self._ensure_log_dir()
        
        # 生成日志文件名（使用当前日期）
        current_date = datetime.now().strftime("%Y-%m-%d")
        self.log_file = os.path.join(self.log_dir, f"tabtidy_{current_date}.log")
        
        # 配置日志记录器
        self.logger = logging.getLogger('TabTidy')
        self.logger.setLevel(log_level)
        
        # 清除可能存在的处理器
        self.logger.handlers.clear()
        
        # 添加文件处理器
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # 添加控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def _ensure_log_dir(self) -> None:
        """确保日志目录存在
        
        如果指定的日志目录不存在，则创建该目录
        """
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def get_logger(self) -> logging.Logger:
        """获取日志记录器实例
        
        Returns:
            logging.Logger: 配置好的日志记录器实例
        """
        return self.logger
    
    def set_level(self, level: int) -> None:
        """设置日志级别
        
        Args:
            level (int): 要设置的日志级别（如logging.DEBUG, logging.INFO等）
        """
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)
    
    def get_log_file(self) -> str:
        """获取当前日志文件路径
        
        Returns:
            str: 当前日志文件的完整路径
        """
        return self.log_file