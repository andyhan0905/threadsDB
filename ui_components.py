import os
import logging
import re
from datetime import datetime
import tkinter as tk

def setup_logging(base_path):
    """로깅 설정"""
    log_dir = os.path.join(base_path, "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"app_{datetime.now().strftime('%Y%m%d')}.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

class LogTextHandler(logging.Handler):
    """로그 텍스트 핸들러"""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
    
    def emit(self, record):
        msg = self.format(record)
        
        # 이미 타임스탬프 형식이 있는지 확인 (날짜-시간 패턴)
        if re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}', msg):
            # 기존 타임스탬프가 있는 로그 메시지는 대괄호 추가 없이 그대로 표시
            self.text_widget.insert(tk.END, msg + '\n')
        else:
            # 타임스탬프가 없는 메시지에는 대괄호 형식의 타임스탬프 추가
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_msg = f"[{timestamp}] {msg}"
            self.text_widget.insert(tk.END, formatted_msg + '\n')
            
        self.text_widget.see(tk.END)

def validate_numeric_input(P):
    """입력값이 숫자인지 검증하는 함수"""
    if P == "":  # 빈 문자열 허용
        return True
    if P.isdigit():  # 숫자만 허용
        return True
    return False