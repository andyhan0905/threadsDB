import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
import logging
from datetime import datetime, timedelta
import time
import schedule
import json

from newspick_collector import NewspickCollector
from ui_components import LogTextHandler, validate_numeric_input
from summary_integration import SummaryProcessor

class DataCollectorUI:

    THREADS_LOCK_FILE = "threads_running.lock"
    DATA_COLLECTOR_LOCK_FILE = "collector_running.lock"

    def check_threads_running(self):
        """Threads 작업이 실행 중인지 확인 - 브라우저 관리 개선으로 충돌 걱정 없음"""
        lock_path = os.path.join(self.base_path, "data", "DB", self.THREADS_LOCK_FILE)
        if os.path.exists(lock_path):
            # 파일 유효성 검사만 수행 (5분 이상 된 파일은 무시)
            file_time = os.path.getmtime(lock_path)
            if time.time() - file_time > 300:  # 5분
                try:
                    os.remove(lock_path)
                    return False
                except:
                    pass
            
            # 경고 불필요 - 각 브라우저가 다른 포트와 PID 사용
            # 단지 로그만 기록
            self.logger.info("Threads 작업이 실행 중이지만, 다른 포트/PID를 사용하므로 충돌 위험 없음")
            return False  # False 반환하여 경고 대화 상자 표시 안 함
        return False

    def set_collector_running(self, running=True):
        """데이터 수집 작업 상태 설정"""
        lock_path = os.path.join(self.base_path, "data", "DB", self.DATA_COLLECTOR_LOCK_FILE)
        if running:
            # 실행 중 상태 설정
            with open(lock_path, 'w') as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            # 실행 중 아님 상태 설정
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except:
                    pass

    """뉴스픽 데이터 수집 UI 모듈"""    
    def __init__(self, parent):
        """
        데이터 수집 UI 초기화
        
        Args:
            parent: 부모 애플리케이션 객체
        """
        self.parent = parent
        self.base_path = parent.base_path
        self.db_manager = parent.db_manager
        self.logger = parent.logger
        self.main_frame = parent.data_tab
        
        # 로그 텍스트 위젯은 로그 섹션을 제거해도, 로깅 기능을 위해 임시 텍스트 위젯 생성
        self.collect_log_text = tk.Text(self.main_frame)
        self.collect_log_text.pack_forget()  # UI에는 표시하지 않음
        
        # 부모 객체에 로그 텍스트 위젯 공유
        self.parent.collect_log_text = self.collect_log_text
        
        # 로그 핸들러 설정
        from ui_components import LogTextHandler
        collect_log_handler = LogTextHandler(self.collect_log_text)
        collect_log_handler.setLevel(logging.INFO)
        collect_log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        collect_log_handler.setFormatter(collect_log_formatter)
        self.logger.addHandler(collect_log_handler)
        
        # 설정 로드
        self.settings = self.load_settings()
        
        # 자동화 관련 변수 초기화
        self.running = False
        self.scheduler_thread = None
        self.collecting = False
        self.last_collect_time = None
        self.next_collect_time = None
        self.running_tasks = []
        
        # UI 생성
        self.create_widgets()
        
        # URL 목록 로드
        self.load_urls_from_db()
        
        # 카운트다운 타이머 시작
        self.start_countdown_timer()
        
        # 헤드리스 모드 초기 상태 강제 비활성화
        self.headless_var.set(False)
        self.headless_checkbox.config(state="disabled")
        
        # 자동화 UI 초기 비활성화
        self.auto_collect_var.set(False)
        self.auto_collect_checkbox.config(state="disabled")
        self.collect_auto_button.config(state="disabled")
        
        # 로그인 상태 확인하여 UI 업데이트
        self.check_headless_login_status()
        
        # API 상태 초기 확인
        if hasattr(self, 'check_api_status'):
            self.check_api_status()

        # 요약 처리기 초기화
        self.init_summary_processor()

    def init_summary_processor(self):
        """요약 처리기 초기화"""
        # 요약 처리기 생성
        self.summary_processor = SummaryProcessor(self.base_path, self.db_manager)
        
        # 진행 상황 콜백 설정
        self.summary_processor.set_progress_callback(self.update_summary_progress)
        
        # 요약 처리 상태 변수
        self.summary_processing = False
        self.summary_progress_text = "요약 처리 대기 중"

    # DataCollectorUI 클래스에 추가할 메서드
    def update_summary_progress(self, processed_count, total_count, current_item):
        """
        요약 진행 상황 업데이트
        
        Args:
            processed_count (int): 처리된 항목 수
            total_count (int): 전체 항목 수
            current_item (dict): 현재 처리 중인 항목 정보
        """
        try:
            if total_count > 0:
                progress_percent = (processed_count / total_count) * 100
                
                if current_item:
                    status_text = f"요약 처리 중: {processed_count}/{total_count} ({progress_percent:.1f}%) - {current_item['title'][:30]}..."
                else:
                    status_text = f"요약 처리 중: {processed_count}/{total_count} ({progress_percent:.1f}%)"
                    
                # 상태 업데이트
                self.summary_progress_text = status_text
                    
                # 로그에 기록 (10% 단위로만 기록)
                if progress_percent % 10 < 1 or processed_count == total_count:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.collect_log_text.insert(tk.END, f"[{timestamp}] {status_text}\n")
                    self.collect_log_text.see(tk.END)
                    
                # 모든 항목이 처리되었는지 확인
                if processed_count >= total_count:
                    self.summary_processing = False
                    
                    # 데이터 새로고침
                    self.load_data()
                    
                    # 완료 메시지
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    complete_msg = f"요약 처리 완료: 총 {processed_count}개 항목 처리됨"
                    self.collect_log_text.insert(tk.END, f"[{timestamp}] {complete_msg}\n")
                    self.collect_log_text.see(tk.END)
                    self.summary_progress_text = "요약 처리 완료"
                    
                    # UI 업데이트를 위해 특정 버튼 상태 변경 등 필요한 경우
                    # 여기에 코드 추가
                    
        except Exception as e:
            self.logger.error(f"요약 진행 상황 업데이트 중 오류: {e}")

    # DataCollectorUI 클래스에 추가할 메서드
    def process_summaries(self):
        """수집된 항목에 대한 요약 처리 시작"""
        try:
            # 이미 처리 중인지 확인
            if self.summary_processing:
                messagebox.showinfo("알림", "이미 요약 처리가 진행 중입니다.")
                return
                
            # API 키 확인
            if not self.check_perplexity_api_key():
                messagebox.showerror("오류", "Perplexity API 키가 설정되지 않았습니다. API 관리 탭에서 API 키를 설정해주세요.")
                return
                
            # 처리할 데이터 가져오기
            news_items = self.db_manager.get_news_items()
            
            if not news_items:
                messagebox.showinfo("알림", "처리할 데이터가 없습니다.")
                return
                
            # 요약이 없는 항목 수 확인
            items_without_summary = [item for item in news_items 
                                    if not item.get("500자 요약") or len(item.get("500자 요약", "").strip()) == 0]
            
            if not items_without_summary:
                messagebox.showinfo("알림", "모든 항목이 이미 요약되어 있습니다.")
                return
                
            # 사용자 확인
            if not messagebox.askyesno("확인", f"총 {len(items_without_summary)}개 항목에 대한 요약을 생성하시겠습니까?\n\n이 작업은 Perplexity API 사용량에 따라 비용이 발생할 수 있습니다."):
                return
                
            # 요약 처리 시작
            self.summary_processing = True
            
            # 로그에 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 요약 처리 시작: 총 {len(items_without_summary)}개 항목\n")
            self.collect_log_text.see(tk.END)
            
            # 요약 작업 추가
            self.summary_processor.add_bulk_summary_tasks(items_without_summary)
            
        except Exception as e:
            self.logger.error(f"요약 처리 시작 중 오류: {e}")
            messagebox.showerror("오류", f"요약 처리 중 오류가 발생했습니다: {e}")
            self.summary_processing = False

    # DataCollectorUI 클래스에 추가할 메서드
    def check_perplexity_api_key(self):
        """Perplexity API 키 확인"""
        from perplexity_api_handler import PerplexityAPIHandler
        api_handler = PerplexityAPIHandler(self.base_path)
        
        # API 키 존재 여부 확인
        if not api_handler.api_key:
            return False
            
        # 필요한 경우 API 키 유효성 검사
        # 이 부분은 필요에 따라 주석 해제
        # is_valid = api_handler.is_api_key_valid()
        # return is_valid
        
        return True

    # DataCollectorUI의 create_widgets 메서드에서 요약 버튼 추가 (data_button_frame에 추가)
    def add_summary_button(self, data_button_frame):
        """요약 버튼 추가"""
        # 요약 생성 버튼 추가
        self.summary_button = ttk.Button(
            data_button_frame, 
            text="500자 요약 생성", 
            command=self.process_summaries
        )
        self.summary_button.pack(side=tk.LEFT, padx=5)

    # DataCollectorUI 클래스의 cleanup 메서드에 추가할 코드
    def cleanup_summary_processor(self):
        """요약 처리기 정리"""
        if hasattr(self, 'summary_processor'):
            self.summary_processor.stop_processing()
  
    def load_settings(self):
        """설정 로드"""
        # 설정의 기본값 정의
        default_settings = {
            "scroll_count": 3,
            "wait_time": 3,
            "headless_mode": False,
            "max_items_per_url": 3,
            # 메시지 옵션 관련 설정 제거
            # "custom_message_options": ["(아래 링크👇)", "(댓글 링크👇)", "(하단 링크👇)", "사용자 정의 입력"],
            # "last_used_message_option": 0,
            "data_path": os.path.join(self.base_path, "data"),
            "auto_collect_enabled": False,
            "collect_interval": 30  # 120에서 30으로 변경
        }
        
        try:
            # DB에서 설정 로드
            settings = self.db_manager.load_settings()
            
            # 누락된 키가 있다면 기본값으로 채우기
            for key, value in default_settings.items():
                if key not in settings:
                    settings[key] = value
            
            self.logger.info("설정을 로드했습니다.")
            return settings
            
        except Exception as e:
            self.logger.error(f"설정 로드 중 오류: {e}")
            return default_settings
    
    def save_settings(self):
        """설정 저장"""
        try:
            # 현재 UI 상태에서 설정값 가져오기
            self.settings["scroll_count"] = int(self.scroll_count_var.get())
            self.settings["wait_time"] = int(self.wait_time_var.get())
            self.settings["headless_mode"] = self.headless_var.get()
            self.settings["max_items_per_url"] = int(self.max_items_var.get())
            
            # 데이터 경로 설정
            self.settings["data_path"] = self.data_path_var.get()
            
            # 자동화 설정 추가
            if hasattr(self, 'auto_collect_var'):
                self.settings["auto_collect_enabled"] = self.auto_collect_var.get()
            if hasattr(self, 'collect_interval_var'):
                self.settings["collect_interval"] = int(self.collect_interval_var.get())
            
            # DB에 설정 저장
            success = self.db_manager.save_settings(self.settings)
            
            if success:
                self.logger.info("설정이 저장되었습니다.")
                return True
            else:
                self.logger.error("설정 저장 실패")
                return False
                
        except Exception as e:
            self.logger.error(f"설정 저장 중 오류: {e}")
            return False
    
    def create_widgets(self):
        """UI 위젯 생성"""
        # 1. 데이터 수집 URL 섹션 (수정된 함수 사용)
        self.create_url_section()
        
        # 2. 수집 옵션 및 설정
        self.create_options_section()
        
        # 3. 데이터 / 이미지 설정
        self.create_data_settings_section()
        
        # 4. 데이터 수집 자동화
        self.create_automation_section()
        
        # 5. 데이터 미리보기
        self.create_preview_section()     

    def create_url_section(self):
        """URL 입력 영역 생성 - 왼쪽으로 배치"""
        # 상위 컨테이너 프레임 생성 (URL 섹션과 API 상태 섹션을 수평으로 배치)
        container_frame = ttk.Frame(self.main_frame)
        container_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)
        
        # URL 섹션 (왼쪽에 배치)
        url_frame = ttk.LabelFrame(container_frame, text="데이터 수집 URL")
        url_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # URL 목록 레이블 - URL 개수 표시 추가
        url_header_frame = ttk.Frame(url_frame)
        url_header_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(url_header_frame, text="URL 목록:").pack(side=tk.LEFT)
        
        # URL 개수 표시 레이블 추가
        self.url_count_var = tk.StringVar(value="(0개)")
        ttk.Label(url_header_frame, textvariable=self.url_count_var).pack(side=tk.LEFT, padx=5)
        
        # URL 목록 표시용 리스트박스 (편집 불가)
        url_list_frame = ttk.Frame(url_frame)
        url_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 높이를 5에서 3으로 줄임
        self.url_listbox = tk.Listbox(url_list_frame, height=3)
        self.url_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        url_scroll = ttk.Scrollbar(url_list_frame, orient="vertical", command=self.url_listbox.yview)
        self.url_listbox.configure(yscrollcommand=url_scroll.set)
        url_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # URL 관리 버튼
        url_button_frame = ttk.Frame(url_frame)
        url_button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(url_button_frame, text="URL 추가", style="TButton", command=self.add_url).pack(side=tk.LEFT, padx=5)
        ttk.Button(url_button_frame, text="URL 삭제", style="TButton", command=self.delete_url).pack(side=tk.LEFT, padx=5)
        
        # API 상태 섹션 추가 (오른쪽에 배치)
        self.create_api_status_section(container_frame)

    # data_collector.py 파일의 create_api_status_section 함수 수정
    def create_api_status_section(self, parent_frame):
        """API 상태 표시 섹션 생성 (오른쪽에 배치)"""
        # width 옵션을 사용하지 않고 API 상태 프레임 생성
        api_status_frame = ttk.LabelFrame(parent_frame, text="API 상태", width=200)
        api_status_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(5, 0))
        
        # 프레임의 크기가 변경되지 않도록 설정
        api_status_frame.pack_propagate(False)
        
        # API 상태 테이블 - 그리드 레이아웃 사용
        status_frame = ttk.Frame(api_status_frame)
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 상태 라벨들
        ttk.Label(status_frame, text="GPT API 키:", anchor="w").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(status_frame, text="Perplexity API 키:", anchor="w").grid(row=1, column=0, sticky="w", pady=2)
        
        # 상태 텍스트 (색상 적용을 위해 Text 위젯 사용)
        self.gpt_api_status_text = tk.Text(status_frame, height=1, width=10, 
                                font=("TkDefaultFont", 9), borderwidth=0, 
                                bg=self.parent.cget('bg'))
        self.gpt_api_status_text.grid(row=0, column=1, sticky="w", pady=2)
        self.gpt_api_status_text.insert(tk.END, "확인 중...")
        
        self.perplexity_api_status_text = tk.Text(status_frame, height=1, width=10, 
                                        font=("TkDefaultFont", 9), borderwidth=0, 
                                        bg=self.parent.cget('bg'))
        self.perplexity_api_status_text.grid(row=1, column=1, sticky="w", pady=2)
        self.perplexity_api_status_text.insert(tk.END, "확인 중...")
        
        # 읽기 전용으로 설정
        self.gpt_api_status_text.config(state=tk.DISABLED)
        self.perplexity_api_status_text.config(state=tk.DISABLED)
        
        # 텍스트 태그 생성 - 색상 설정용
        self.gpt_api_status_text.tag_configure("complete", foreground="green")
        self.gpt_api_status_text.tag_configure("empty", foreground="red")
        self.perplexity_api_status_text.tag_configure("complete", foreground="green")
        self.perplexity_api_status_text.tag_configure("empty", foreground="red")
        
        # API 관리 탭으로 이동 버튼
        button_frame = ttk.Frame(api_status_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(button_frame, text="API 관리", 
                command=self.go_to_api_tab).pack(side=tk.LEFT, padx=5)
        
        # 상태 새로고침 버튼
        ttk.Button(button_frame, text="새로고침", 
                command=self.refresh_api_status).pack(side=tk.RIGHT, padx=5)
        
        # 초기 상태 업데이트 (타이머 제거)
        self.check_api_status()

    def go_to_api_tab(self):
        """API 관리 탭으로 이동"""
        self.parent.tab_control.select(self.parent.api_tab)

    def check_api_status(self):
        """API 상태 확인 및 업데이트"""
        try:
            # API 키 파일 경로
            gpt_api_file = os.path.join(self.base_path, "data", "api", "gpt_api.json")
            perplexity_api_file = os.path.join(self.base_path, "data", "api", "perplexity_api.json")
            
            # GPT API 상태 확인
            gpt_status = "입력 완료" if os.path.exists(gpt_api_file) else "비어 있음"
            if os.path.exists(gpt_api_file):
                try:
                    with open(gpt_api_file, 'r') as f:
                        data = json.load(f)
                        gpt_status = "입력 완료" if data.get('api_key') else "비어 있음"
                except:
                    gpt_status = "오류"
            
            # Perplexity API 상태 확인
            perplexity_status = "입력 완료" if os.path.exists(perplexity_api_file) else "비어 있음"
            if os.path.exists(perplexity_api_file):
                try:
                    with open(perplexity_api_file, 'r') as f:
                        data = json.load(f)
                        perplexity_status = "입력 완료" if data.get('api_key') else "비어 있음"
                except:
                    perplexity_status = "오류"
            
            # 상태 텍스트 업데이트
            self.update_api_status_text(self.gpt_api_status_text, gpt_status)
            self.update_api_status_text(self.perplexity_api_status_text, perplexity_status)
            
            # INFO 로깅에서 DEBUG 로깅으로 변경
            self.logger.debug("API 상태 업데이트 완료")
        except Exception as e:
            self.logger.error(f"API 상태 확인 중 오류: {e}")

    def update_api_status_text(self, status_text, new_status):
        """
        상태 텍스트 업데이트 및 색상 적용
        
        Args:
            status_text (tk.Text): 상태 텍스트 위젯
            new_status (str): 새 상태 메시지
        """
        # 텍스트 위젯을 수정 가능하게 설정
        status_text.config(state=tk.NORMAL)
        
        # 기존 내용 삭제
        status_text.delete('1.0', tk.END)
        
        # 새 내용 삽입
        status_text.insert(tk.END, new_status)
        
        # 태그 적용
        if new_status == "입력 완료":
            status_text.tag_add("complete", '1.0', tk.END)
        else:
            status_text.tag_add("empty", '1.0', tk.END)
        
        # 다시 읽기 전용으로 설정
        status_text.config(state=tk.DISABLED)

    def refresh_api_status(self):
        """API 상태 수동 새로고침"""
        self.check_api_status()
        # API 키 상태에 따라 자동 요약 체크박스 상태 업데이트
        self.check_api_summary_availability()
        messagebox.showinfo("알림", "API 상태가 새로고침되었습니다.")

    # 메시지 옵션 초기화 부분 수정 (create_options_section 함수의 일부)
    def create_options_section(self):
        """수집 옵션 영역 생성"""
        from ui_components import validate_numeric_input
        
        options_frame = ttk.LabelFrame(self.main_frame, text="수집 옵션 및 설정")
        options_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)

        # 왼쪽 옵션: 스크롤 횟수, 대기 시간, 헤드리스 모드
        left_options = ttk.Frame(options_frame)
        left_options.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 스크롤 횟수
        scroll_frame = ttk.Frame(left_options)
        scroll_frame.pack(fill=tk.X, pady=2)
        ttk.Label(scroll_frame, text="스크롤 횟수:").pack(side=tk.LEFT, padx=5)
        self.scroll_count_var = tk.StringVar(value=str(self.settings["scroll_count"]))
        # 숫자 검증 등록
        vcmd = (self.parent.register(validate_numeric_input), '%P')
        self.scroll_count_spinbox = ttk.Spinbox(scroll_frame, from_=1, to=20, width=5, 
                                            textvariable=self.scroll_count_var, 
                                            validate="key", validatecommand=vcmd)
        self.scroll_count_spinbox.pack(side=tk.LEFT, padx=5)

        # 대기 시간
        wait_frame = ttk.Frame(left_options)
        wait_frame.pack(fill=tk.X, pady=2)
        ttk.Label(wait_frame, text="대기 시간(초):").pack(side=tk.LEFT, padx=5)
        self.wait_time_var = tk.StringVar(value=str(self.settings["wait_time"]))
        self.wait_time_spinbox = ttk.Spinbox(wait_frame, from_=1, to=10, width=5, 
                                        textvariable=self.wait_time_var,
                                        validate="key", validatecommand=vcmd)
        self.wait_time_spinbox.pack(side=tk.LEFT, padx=5)

        # 헤드리스 모드
        headless_frame = ttk.Frame(left_options)
        headless_frame.pack(fill=tk.X, pady=2)
        self.headless_var = tk.BooleanVar(value=False)  # 항상 False로 초기화
        self.headless_checkbox = ttk.Checkbutton(
            headless_frame, 
            text="헤드리스 모드 사용 (브라우저를 숨기는 기능)", 
            variable=self.headless_var,
            command=self.check_headless_available,
            state="disabled"  # 초기 상태는 비활성화
        )
        self.headless_checkbox.pack(side=tk.LEFT, padx=5)

        # 오른쪽 옵션: 최대 수집 항목만 포함
        right_options = ttk.Frame(options_frame)
        right_options.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 최대 수집 항목
        max_frame = ttk.Frame(right_options)
        max_frame.pack(fill=tk.X, pady=2)
        ttk.Label(max_frame, text="URL당 최대 항목:").pack(side=tk.LEFT, padx=5)
        self.max_items_var = tk.StringVar(value=str(self.settings["max_items_per_url"]))
        self.max_items_spinbox = ttk.Spinbox(max_frame, from_=1, to=50, width=5, 
                                        textvariable=self.max_items_var,
                                        validate="key", validatecommand=vcmd)
        self.max_items_spinbox.pack(side=tk.LEFT, padx=5)

        # 자동 요약 생성 체크박스
        auto_summary_frame = ttk.Frame(left_options)
        auto_summary_frame.pack(fill=tk.X, pady=2)
        self.auto_summary_var = tk.BooleanVar(value=False)
        self.auto_summary_checkbox = ttk.Checkbutton(
            auto_summary_frame, 
            text="자동 요약 생성 (Perplexity API 사용)", 
            variable=self.auto_summary_var
        )
        self.auto_summary_checkbox.pack(side=tk.LEFT, padx=5)
    
    def create_data_settings_section(self):
        """데이터 저장 및 이미지 설정 영역 생성"""
        data_setting_frame = ttk.LabelFrame(self.main_frame, text="데이터 / 이미지 설정")
        data_setting_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)
        
        # 실제 경로는 설정에 저장 (기본 data 경로로 고정)
        self.data_path_var = tk.StringVar(value=os.path.join(self.base_path, "data"))
        
        # 경로 표시 프레임
        path_frame = ttk.Frame(data_setting_frame)
        path_frame.pack(fill=tk.X, pady=2)
        ttk.Label(path_frame, text="데이터 저장 경로:").pack(side=tk.LEFT, padx=5)
        
        # 입력 필드 대신 레이블 사용 - 항상 "\data"로 표시
        path_label = ttk.Label(path_frame, text=f"{os.path.sep}data")
        path_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 찾아보기 버튼 - 실제 폴더만 열어줌
        ttk.Button(path_frame, text="찾아보기", command=self.open_data_folder).pack(side=tk.RIGHT, padx=5)
        
        # 이미지 설정 프레임
        image_frame = ttk.Frame(data_setting_frame)
        image_frame.pack(fill=tk.X, pady=2)
        ttk.Label(image_frame, text="이미지 크기:").pack(side=tk.LEFT, padx=5)
        ttk.Label(image_frame, text="500 x 500 픽셀 (고정)").pack(side=tk.LEFT, padx=5)

    def create_options_section_updated(self):
        """수집 옵션 영역 생성 - 자동 요약 옵션 추가"""
        from ui_components import validate_numeric_input
        
        options_frame = ttk.LabelFrame(self.main_frame, text="수집 옵션 및 설정")
        options_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)

        # 왼쪽 옵션: 스크롤 횟수, 대기 시간, 헤드리스 모드, 자동 요약
        left_options = ttk.Frame(options_frame)
        left_options.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 스크롤 횟수
        scroll_frame = ttk.Frame(left_options)
        scroll_frame.pack(fill=tk.X, pady=2)
        ttk.Label(scroll_frame, text="스크롤 횟수:").pack(side=tk.LEFT, padx=5)
        self.scroll_count_var = tk.StringVar(value=str(self.settings["scroll_count"]))
        # 숫자 검증 등록
        vcmd = (self.parent.register(validate_numeric_input), '%P')
        self.scroll_count_spinbox = ttk.Spinbox(scroll_frame, from_=1, to=20, width=5, 
                                            textvariable=self.scroll_count_var, 
                                            validate="key", validatecommand=vcmd)
        self.scroll_count_spinbox.pack(side=tk.LEFT, padx=5)

        # 대기 시간
        wait_frame = ttk.Frame(left_options)
        wait_frame.pack(fill=tk.X, pady=2)
        ttk.Label(wait_frame, text="대기 시간(초):").pack(side=tk.LEFT, padx=5)
        self.wait_time_var = tk.StringVar(value=str(self.settings["wait_time"]))
        self.wait_time_spinbox = ttk.Spinbox(wait_frame, from_=1, to=10, width=5, 
                                        textvariable=self.wait_time_var,
                                        validate="key", validatecommand=vcmd)
        self.wait_time_spinbox.pack(side=tk.LEFT, padx=5)

        # 헤드리스 모드
        headless_frame = ttk.Frame(left_options)
        headless_frame.pack(fill=tk.X, pady=2)
        self.headless_var = tk.BooleanVar(value=False)  # 항상 False로 초기화
        self.headless_checkbox = ttk.Checkbutton(
            headless_frame, 
            text="헤드리스 모드 사용 (브라우저를 숨기는 기능)", 
            variable=self.headless_var,
            command=self.check_headless_available,
            state="disabled"  # 초기 상태는 비활성화
        )
        self.headless_checkbox.pack(side=tk.LEFT, padx=5)
        
        # 자동 요약 체크박스 추가 (NEW!)
        auto_summary_frame = ttk.Frame(left_options)
        auto_summary_frame.pack(fill=tk.X, pady=2)
        self.auto_summary_var = tk.BooleanVar(value=self.settings.get("auto_summary", False))
        self.auto_summary_checkbox = ttk.Checkbutton(
            auto_summary_frame, 
            text="자동 요약 생성 (Perplexity API 사용)", 
            variable=self.auto_summary_var,
            command=self.check_auto_summary_availability
        )
        self.auto_summary_checkbox.pack(side=tk.LEFT, padx=5)

        # 오른쪽 옵션: 최대 수집 항목만 포함
        right_options = ttk.Frame(options_frame)
        right_options.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 최대 수집 항목
        max_frame = ttk.Frame(right_options)
        max_frame.pack(fill=tk.X, pady=2)
        ttk.Label(max_frame, text="URL당 최대 항목:").pack(side=tk.LEFT, padx=5)
        self.max_items_var = tk.StringVar(value=str(self.settings["max_items_per_url"]))
        self.max_items_spinbox = ttk.Spinbox(max_frame, from_=1, to=50, width=5, 
                                        textvariable=self.max_items_var,
                                        validate="key", validatecommand=vcmd)
        self.max_items_spinbox.pack(side=tk.LEFT, padx=5)

    # data_collector.py 파일에 추가할 메서드
    def check_auto_summary_availability(self):
        """자동 요약 체크박스 클릭 시 호출되는 함수"""
        if self.auto_summary_var.get():
            # API 키 확인
            if not self.check_perplexity_api_key():
                messagebox.showwarning("경고", "Perplexity API 키가 설정되어 있지 않습니다.\nAPI 관리 탭에서 API 키를 설정해주세요.")
                self.auto_summary_var.set(False)
            else:
                # 설정에 저장
                self.settings["auto_summary"] = True
                self.save_settings()
                self.logger.info("자동 요약 생성이 활성화되었습니다.")
        else:
            # 설정에서 제거
            self.settings["auto_summary"] = False
            self.save_settings()
            self.logger.info("자동 요약 생성이 비활성화되었습니다.")

    def open_data_folder(self):
        """데이터 폴더 열기 - 탐색기만 실행"""
        try:
            # 실제 데이터 폴더 경로
            data_path = self.data_path_var.get()
            
            # 경로가 존재하는지 확인
            if not os.path.exists(data_path):
                # 존재하지 않으면 기본 data 폴더 사용
                data_path = os.path.join(self.base_path, "data")
                os.makedirs(data_path, exist_ok=True)
            
            # 플랫폼에 따라 적절한 명령으로 폴더 열기
            import platform
            import subprocess
            
            if platform.system() == "Windows":
                os.startfile(data_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", data_path])
            else:  # Linux
                subprocess.Popen(["xdg-open", data_path])
                
            # 로그에 기록
            self.logger.info(f"데이터 폴더 열기: {data_path}")
            
        except Exception as e:
            self.logger.error(f"데이터 폴더 열기 오류: {e}")
            messagebox.showerror("오류", f"폴더를 열 수 없습니다: {e}")
    
    def create_automation_section(self):
        """자동화 설정 영역 생성"""
        from ui_components import validate_numeric_input
        
        auto_frame = ttk.LabelFrame(self.main_frame, text="데이터 수집 자동화")
        auto_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)
        
        # 자동화 활성화 체크박스
        auto_check_frame = ttk.Frame(auto_frame)
        auto_check_frame.pack(fill=tk.X, pady=2)
        self.auto_collect_var = tk.BooleanVar(value=self.settings.get("auto_collect_enabled", False))
        # 체크박스 참조 변수 저장
        self.auto_collect_checkbox = ttk.Checkbutton(
            auto_check_frame, 
            text="자동 수집 활성화", 
            variable=self.auto_collect_var,
            command=self.toggle_auto_collect
        )
        self.auto_collect_checkbox.pack(side=tk.LEFT, padx=5)
        
        # 수집 간격
        interval_frame = ttk.Frame(auto_frame)
        interval_frame.pack(fill=tk.X, pady=2)
        ttk.Label(interval_frame, text="수집 간격(분):").pack(side=tk.LEFT, padx=5)
        self.collect_interval_var = tk.StringVar(value=str(self.settings.get("collect_interval", 30)))
        vcmd = (self.parent.register(validate_numeric_input), '%P')
        ttk.Spinbox(
            interval_frame, 
            from_=30, 
            to=1440, 
            width=5, 
            textvariable=self.collect_interval_var,
            validate="key", 
            validatecommand=vcmd
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(interval_frame, text="(최소 30분 권장)").pack(side=tk.LEFT, padx=5)
        
        # 자동화 상태 표시
        status_frame = ttk.Frame(auto_frame)
        status_frame.pack(fill=tk.X, pady=2)
        ttk.Label(status_frame, text="자동화 상태:").pack(side=tk.LEFT, padx=5)
        self.collect_status_var = tk.StringVar(value="비활성화됨")
        
        # 상태 텍스트용 라벨 (색상 변경을 위해 Text 위젯 사용)
        self.status_label_frame = ttk.Frame(status_frame)
        self.status_label_frame.pack(side=tk.LEFT, padx=5)
        
        # Text 위젯을 사용하여 색상을 적용할 수 있는 라벨 생성
        self.status_text = tk.Text(self.status_label_frame, height=1, width=15, 
                                font=("TkDefaultFont", 9), borderwidth=0, 
                                bg=self.parent.cget('bg'))  # 배경색을 부모와 동일하게 설정
        self.status_text.pack(side=tk.LEFT, fill=tk.X)
        self.status_text.insert(tk.END, "비활성화됨")
        
        # 읽기 전용으로 설정
        self.status_text.config(state=tk.DISABLED)
        
        # 텍스트 태그 생성 - 색상 설정용
        self.status_text.tag_configure("active", foreground="green")
        self.status_text.tag_configure("inactive", foreground="black")
        
        # 다음 수집 시간
        next_frame = ttk.Frame(auto_frame)
        next_frame.pack(fill=tk.X, pady=2)
        ttk.Label(next_frame, text="다음 수집 예정:").pack(side=tk.LEFT, padx=5)
        self.next_collect_var = tk.StringVar(value="없음")
        ttk.Label(next_frame, textvariable=self.next_collect_var).pack(side=tk.LEFT, padx=5)

        # 버튼 영역
        button_frame = ttk.Frame(auto_frame)
        button_frame.pack(fill=tk.X, pady=5)
            
        # 자동화 버튼
        self.collect_auto_button = ttk.Button(
            button_frame,
            text="자동화 시작",
            style="Green.TButton",
            command=self.toggle_auto_collect
        )
        self.collect_auto_button.pack(side=tk.LEFT, padx=5)
        
        # 데이터 수집 시작 버튼
        self.collect_start_button = ttk.Button(button_frame, text="데이터 수집 시작", style="TButton", command=self.start_data_collection)
        self.collect_start_button.pack(side=tk.RIGHT, padx=5)

    def update_status_text(self, text, is_active=False):
        """자동화 상태 텍스트 업데이트 및 색상 적용"""
        # 텍스트 위젯을 수정 가능하게 설정
        self.status_text.config(state=tk.NORMAL)
        
        # 기존 내용 삭제
        self.status_text.delete('1.0', tk.END)
        
        # 새 내용 삽입
        self.status_text.insert(tk.END, text)
        
        # 태그 적용
        if is_active:
            self.status_text.tag_add("active", '1.0', tk.END)
        else:
            self.status_text.tag_add("inactive", '1.0', tk.END)
        
        # 다시 읽기 전용으로 설정
        self.status_text.config(state=tk.DISABLED)

    def create_preview_section(self):
        """데이터 미리보기 영역 생성"""
        preview_frame = ttk.LabelFrame(self.main_frame, text="데이터 미리보기")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 트리뷰 생성 및 설정
        tree_frame = ttk.Frame(preview_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 스크롤바 생성
        tree_y_scroll = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tree_x_scroll = ttk.Scrollbar(tree_frame, orient="horizontal")
        tree_x_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        # 트리뷰 생성 및 스크롤바 연결
        self.data_tree = ttk.Treeview(tree_frame, 
                                    columns=("선택", "카테고리", "게시물 제목", "복사링크", "수집날짜", "이미지", "500자 요약", 
                                        "포스팅 상태", "포스팅 날짜", "쓰레드1", "쓰레드2", "쓰레드3", "쓰레드4", "쓰레드5", "생성 여부"),
                                    yscrollcommand=tree_y_scroll.set, 
                                    xscrollcommand=tree_x_scroll.set, 
                                    height=10)

        tree_y_scroll.config(command=self.data_tree.yview)
        tree_x_scroll.config(command=self.data_tree.xview)

        # 트리뷰 컬럼 설정
        self.data_tree.heading("#0", text="인덱스")
        self.data_tree.heading("선택", text="선택")
        self.data_tree.heading("카테고리", text="카테고리")
        self.data_tree.heading("게시물 제목", text="게시물 제목")
        self.data_tree.heading("복사링크", text="복사링크")
        self.data_tree.heading("수집날짜", text="수집 날짜")
        self.data_tree.heading("이미지", text="이미지")
        self.data_tree.heading("500자 요약", text="500자 요약")
        self.data_tree.heading("포스팅 상태", text="포스팅 상태")
        self.data_tree.heading("포스팅 날짜", text="포스팅 날짜")
        self.data_tree.heading("쓰레드1", text="쓰레드1")
        self.data_tree.heading("쓰레드2", text="쓰레드2")
        self.data_tree.heading("쓰레드3", text="쓰레드3")
        self.data_tree.heading("쓰레드4", text="쓰레드4")
        self.data_tree.heading("쓰레드5", text="쓰레드5")
        self.data_tree.heading("생성 여부", text="생성 여부")

        # 컬럼 너비 설정
        self.data_tree.column("#0", width=50, minwidth=30, stretch=tk.NO)
        self.data_tree.column("선택", width=40, minwidth=30, stretch=tk.NO)
        self.data_tree.column("카테고리", width=80, minwidth=60, stretch=tk.NO)
        self.data_tree.column("게시물 제목", width=200, minwidth=100, stretch=tk.NO)
        self.data_tree.column("복사링크", width=100, minwidth=60, stretch=tk.NO)
        self.data_tree.column("수집날짜", width=100, minwidth=80, stretch=tk.NO)
        self.data_tree.column("이미지", width=40, minwidth=30, stretch=tk.NO)
        self.data_tree.column("500자 요약", width=200, minwidth=100, stretch=tk.NO)
        self.data_tree.column("포스팅 상태", width=80, minwidth=60, stretch=tk.NO)
        self.data_tree.column("포스팅 날짜", width=130, minwidth=100, stretch=tk.NO)
        self.data_tree.column("쓰레드1", width=70, minwidth=50, stretch=tk.NO)
        self.data_tree.column("쓰레드2", width=70, minwidth=50, stretch=tk.NO)
        self.data_tree.column("쓰레드3", width=70, minwidth=50, stretch=tk.NO)
        self.data_tree.column("쓰레드4", width=70, minwidth=50, stretch=tk.NO)
        self.data_tree.column("쓰레드5", width=70, minwidth=50, stretch=tk.NO)
        self.data_tree.column("생성 여부", width=70, minwidth=50, stretch=tk.NO)

        # 트리뷰 행 클릭 이벤트 추가
        self.data_tree.bind("<ButtonRelease-1>", self.toggle_selection)
        
        # 더블 클릭 이벤트 추가 - 500자 요약 수정용
        self.data_tree.bind("<Double-1>", self.edit_summary)

        # 트리뷰 컬럼 가운데 정렬 설정
        for col in ("카테고리", "복사링크", "수집날짜", "이미지", "포스팅 상태", "포스팅 날짜"):
            self.data_tree.column(col, anchor='center')

        # 트리뷰 배치
        self.data_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 데이터 조작 버튼 프레임
        data_button_frame = ttk.Frame(preview_frame)
        data_button_frame.pack(fill=tk.X, pady=5)

        # 삭제 버튼 추가
        ttk.Button(data_button_frame, text="✓ 선택 항목 삭제", style="TButton", command=self.delete_selected_items).pack(side=tk.LEFT, padx=5)
        ttk.Button(data_button_frame, text="데이터 새로고침", command=self.load_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(data_button_frame, text="데이터 내보내기", command=self.export_data).pack(side=tk.LEFT, padx=5)

        # 카테고리 매핑 편집 버튼 추가
        ttk.Button(data_button_frame, text="카테고리 매핑 관리", command=self.open_category_mapping_editor).pack(side=tk.LEFT, padx=5)

        # 요약 생성 버튼 추가
        self.summary_button = ttk.Button(
            data_button_frame, 
            text="500자 요약 생성", 
            command=self.process_summaries
        )
        self.summary_button.pack(side=tk.LEFT, padx=5)

        # 저장된 열 너비 복원
        self.restore_column_widths()

    def edit_summary(self, event):  # 함수명 변경
        """500자 요약 편집 - 더블 클릭 이벤트 핸들러"""
        # 클릭된 행과 열 식별
        region = self.data_tree.identify_region(event.x, event.y)
        column = self.data_tree.identify_column(event.x)
        item = self.data_tree.identify_row(event.y)
        
        # cell 영역의 500자 요약 열인 경우에만 처리
        if region == "cell" and column == "#7" and item:  # #7은 500자 요약 열
            try:
                # 현재 행의 값들 가져오기
                values = self.data_tree.item(item, "values")
                if not values:
                    return
                
                # 현재 500자 요약 값 가져오기
                current_message = values[6]  # 인덱스 6은 500자 요약 열
                
                # 행 인덱스 (1부터 시작하므로 -1)
                row_index = int(self.data_tree.item(item, "text")) - 1
                
                # 해당 행의 데이터 가져오기
                news_items = self.db_manager.get_news_items()
                if row_index >= len(news_items):
                    return
                    
                news_item = news_items[row_index]
                news_id = news_item.get("id")
                
                # 편집 대화상자 생성
                edit_dialog = tk.Toplevel(self.parent)
                edit_dialog.title("500자 요약 편집")  # 제목 변경
                edit_dialog.geometry("500x300")
                edit_dialog.resizable(True, True)
                edit_dialog.grab_set()
                
                # 창 위치 조정 (부모 창 중앙)
                window_width = edit_dialog.winfo_reqwidth()
                window_height = edit_dialog.winfo_reqheight()
                position_right = int(self.parent.winfo_rootx() + (self.parent.winfo_width() / 2) - (window_width / 2))
                position_down = int(self.parent.winfo_rooty() + (self.parent.winfo_height() / 2) - (window_height / 2))
                edit_dialog.geometry(f"+{position_right}+{position_down}")
                
                # 프레임 생성
                main_frame = ttk.Frame(edit_dialog, padding=10)
                main_frame.pack(fill=tk.BOTH, expand=True)
                
                # 타이틀 표시
                title_frame = ttk.Frame(main_frame)
                title_frame.pack(fill=tk.X, pady=(0, 10))
                
                # 게시물 제목 표시
                post_title = news_item.get("게시물 제목", "")
                ttk.Label(title_frame, text=f"게시물 제목: {post_title}", font=("", 10, "bold")).pack(anchor=tk.W)
                
                # 구분선
                ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=5)
                
                # 문구 편집 영역 레이블 - 텍스트 변경
                ttk.Label(main_frame, text="500자 요약:").pack(anchor=tk.W, pady=(5, 0))
                
                # 텍스트 편집 영역
                text_frame = ttk.Frame(main_frame)
                text_frame.pack(fill=tk.BOTH, expand=True, pady=5)
                
                # 스크롤바가 있는 텍스트 에디터
                from tkinter import scrolledtext
                message_editor = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, width=50, height=10)
                message_editor.pack(fill=tk.BOTH, expand=True)
                message_editor.insert(tk.END, current_message)
                message_editor.focus_set()
                
                # 버튼 프레임
                button_frame = ttk.Frame(main_frame)
                button_frame.pack(fill=tk.X, pady=(10, 0))
                
                def on_save():
                    """저장 버튼 클릭 핸들러"""
                    new_message = message_editor.get("1.0", tk.END).strip()
                    
                    try:
                        # DB 업데이트 - 필드명 변경
                        conn = self.db_manager.get_connection()
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE news_data SET summary_500 = ? WHERE id = ?",
                            (new_message, news_id)
                        )
                        conn.commit()
                        
                        # 트리뷰 업데이트
                        new_values = list(values)
                        new_values[6] = new_message
                        self.data_tree.item(item, values=tuple(new_values))
                        
                        # 로그 기록
                        self.logger.info(f"500자 요약이 업데이트되었습니다. 뉴스 ID: {news_id}")
                        
                        # 대화상자 닫기
                        edit_dialog.destroy()
                        
                        # 성공 메시지
                        messagebox.showinfo("성공", "500자 요약이 성공적으로 저장되었습니다.")
                        
                    except Exception as e:
                        self.logger.error(f"500자 요약 업데이트 중 오류: {e}")
                        messagebox.showerror("오류", f"500자 요약 저장 중 오류가 발생했습니다: {e}")
                        
                def on_cancel():
                    """취소 버튼 클릭 핸들러"""
                    edit_dialog.destroy()
                
                # 버튼 배치 (오른쪽 정렬)
                ttk.Frame(button_frame).pack(side=tk.LEFT, fill=tk.X, expand=True)
                ttk.Button(button_frame, text="저장", command=on_save).pack(side=tk.RIGHT, padx=5)
                ttk.Button(button_frame, text="취소", command=on_cancel).pack(side=tk.RIGHT, padx=5)
                
                # Enter 키로 저장, Escape 키로 취소
                edit_dialog.bind("<Return>", lambda event: on_save())
                edit_dialog.bind("<Escape>", lambda event: on_cancel())
                
            except Exception as e:
                self.logger.error(f"GPT 문구 편집 팝업 생성 중 오류: {e}")
                messagebox.showerror("오류", f"편집 창을 열 수 없습니다: {e}")

    def on_message_option_change(self, event=None):
        """메시지 옵션 변경 이벤트 처리"""
        selected_index = self.message_combo.current()
        
        # "사용자 정의 입력"이 선택되면 입력 필드를 활성화
        if selected_index == 3:
            self.custom_message_entry.config(state="normal")
        else:
            self.custom_message_entry.config(state="disabled")
        
        # 선택된 옵션 인덱스 저장
        self.settings["last_used_message_option"] = selected_index
        
        # 콤보박스의 현재 값들 가져오기
        current_options = list(self.message_combo["values"])
        
        # 기존 custom_message_options 설정 업데이트
        self.settings["custom_message_options"] = current_options
    
    def check_headless_available(self):
        """헤드리스 체크박스가 클릭될 때 호출되는 함수"""
        if self.headless_var.get():  # 체크박스가 선택되었을 때
            if not self.check_headless_login_status():
                # 로그인 상태가 없으면 체크박스를 해제하고 비활성화
                self.headless_var.set(False)
                self.headless_checkbox.config(state="disabled")
    
    def check_headless_login_status(self):
        """로그인 상태를 확인하고 헤드리스 모드 및 자동 요약 사용 가능 여부를 결정합니다."""
        # 수정: data/DB 폴더에서 login_status.cfg 파일 찾기
        data_dir = os.path.join(self.base_path, "data")
        db_dir = os.path.join(data_dir, "DB")
        login_file = os.path.join(db_dir, "login_status.cfg")
        
        # 로그인 파일이 존재하는지 확인
        login_status = False
        if not os.path.exists(login_file):
            # 로그인 파일이 없으면 헤드리스 모드 및 자동화 기능 비활성화
            self.headless_var.set(False)
            self.headless_checkbox.config(state="disabled")
            
            # 자동화 기능 비활성화
            self.auto_collect_var.set(False)
            self.auto_collect_checkbox.config(state="disabled")
            self.collect_auto_button.config(state="disabled")
        else:
            # 파일 내용 확인 - 로그인 상태 체크
            try:
                with open(login_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "로그인_상태: 완료" in content:
                        # 로그인 확인되면 헤드리스 모드와 자동화 기능 활성화
                        self.headless_checkbox.config(state="normal")
                        
                        # 자동화 기능 활성화
                        self.auto_collect_checkbox.config(state="normal")
                        self.collect_auto_button.config(state="normal")
                        
                        login_status = True
                    else:
                        # 로그인 상태가 아니면 비활성화
                        self.headless_var.set(False)
                        self.headless_checkbox.config(state="disabled")
                        
                        # 자동화 기능 비활성화
                        self.auto_collect_var.set(False)
                        self.auto_collect_checkbox.config(state="disabled")
                        self.collect_auto_button.config(state="disabled")
            except:
                # 파일 읽기 실패 시 비활성화
                self.headless_var.set(False)
                self.headless_checkbox.config(state="disabled")
                
                # 자동화 기능 비활성화
                self.auto_collect_var.set(False)
                self.auto_collect_checkbox.config(state="disabled")
                self.collect_auto_button.config(state="disabled")
        
        # API 키 상태 확인하여 자동 요약 체크박스 제어
        self.check_api_summary_availability()
        
        return login_status

    def check_api_summary_availability(self):
        """Perplexity API 키 상태를 확인하고 자동 요약 체크박스 상태를 제어합니다."""
        # auto_summary_checkbox가 있는지 확인
        if not hasattr(self, 'auto_summary_checkbox'):
            return
            
        # API 키 파일 경로
        perplexity_api_file = os.path.join(self.base_path, "data", "api", "perplexity_api.json")
        
        # API 키 존재 확인
        api_key_exists = False
        if os.path.exists(perplexity_api_file):
            try:
                with open(perplexity_api_file, 'r') as f:
                    import json
                    data = json.load(f)
                    if data.get('api_key'):
                        api_key_exists = True
            except:
                pass
        
        # 자동 요약 체크박스 상태 제어
        if api_key_exists:
            # API 키가 있으면 체크박스 활성화
            self.auto_summary_checkbox.config(state="normal")
        else:
            # API 키가 없으면 체크박스 비활성화 및 체크 해제
            self.auto_summary_var.set(False)
            self.auto_summary_checkbox.config(state="disabled")

    def browse_data_path(self):
        """데이터 저장 경로 선택 - 항상 기본 data 폴더에서 시작"""
        # 항상 기본 data 폴더를 초기 디렉토리로 사용
        default_data_path = os.path.join(self.base_path, "data")
        
        # 파일 다이얼로그 실행 - 기본 data 폴더에서 시작
        path = filedialog.askdirectory(initialdir=default_data_path)
        
        if path:
            # 선택한 경로 저장
            self.data_path_var.set(path)
            
            # 설정 저장
            self.save_settings()
            
            # 경로 선택 후 확인 메시지 (선택한 실제 경로 표시 없음)
            messagebox.showinfo("경로 설정", "데이터 저장 경로가 설정되었습니다.")
    
    def load_urls_from_db(self):
        """DB에서 URL 목록 로드하여 리스트박스에 표시"""
        try:
            # DB에서 URL 목록 가져오기
            urls = self.db_manager.load_urls()
            
            # 리스트박스 초기화
            self.url_listbox.delete(0, tk.END)
            
            # URL 목록 추가
            for url in urls:
                if url:  # 빈 문자열 제외
                    self.url_listbox.insert(tk.END, url)
            
            # URL 개수 업데이트
            self.update_url_count()
            
            self.logger.info(f"DB에서 {len(urls)}개의 URL을 로드했습니다.")
        except Exception as e:
            self.logger.error(f"DB에서 URL 로드 중 오류: {e}")

    # URL 개수 업데이트 함수 추가
    def update_url_count(self):
        """URL 목록 개수 업데이트"""
        count = self.url_listbox.size()
        self.url_count_var.set(f"({count}개)")


    # delete_url 함수 수정
    def delete_url(self):
        """선택된 URL 삭제"""
        selection = self.url_listbox.curselection()
        if not selection:
            messagebox.showinfo("알림", "삭제할 URL을 선택하세요.")
            return
        
        # 선택된 URL 가져오기
        selected_url = self.url_listbox.get(selection[0])
        
        # 리스트박스에서 삭제
        self.url_listbox.delete(selection)
        
        # DB에 저장
        self.save_urls()
        
        # URL 개수 업데이트 - URL 목록 크기로 직접 업데이트
        count = self.url_listbox.size()
        self.url_count_var.set(f"({count}개)")
        
        # 로그에 기록
        self.logger.info(f"URL 삭제됨: {selected_url}, 남은 URL 수: {count}")

    def add_url(self):
        """URL 추가 대화상자 - 중복 검사 추가"""
        # 커스텀 대화창 생성
        dialog = tk.Toplevel(self.parent)
        dialog.title("URL 추가")
        dialog.geometry("500x100")  # 더 넓은 창 크기 설정
        dialog.resizable(False, False)
        dialog.grab_set()  # 모달 창으로 설정
        
        # URL 입력 프레임
        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="새 URL을 입력하세요:").pack(anchor=tk.W)
        
        # URL 입력 필드 (넓게 설정)
        url_var = tk.StringVar()
        url_entry = ttk.Entry(frame, width=70, textvariable=url_var)
        url_entry.pack(fill=tk.X, pady=5)
        url_entry.focus_set()  # 입력 필드에 포커스
        
        result = [False]  # 결과 저장용 리스트
        
        # 확인/취소 버튼 프레임
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        def on_ok():
            url = url_var.get().strip()
            if not url:
                messagebox.showwarning("경고", "URL을 입력해주세요.")
                return  # 함수 종료하고 대화상자 유지
            
            # URL 유효성 검사 (간단한 확인)
            if not url.startswith(("http://", "https://")):
                messagebox.showwarning("경고", "유효한 URL을 입력하세요 (http:// 또는 https:// 포함)")
                return  # 함수 종료하고 대화상자 유지
            
            # 중복 URL 검사 추가
            existing_urls = [self.url_listbox.get(i) for i in range(self.url_listbox.size())]
            if url in existing_urls:
                messagebox.showwarning("경고", "이미 등록된 URL입니다.")
                return  # 함수 종료하고 대화상자 유지
            
            result[0] = True
            dialog.destroy()
            
        def on_cancel():
            dialog.destroy()
        
        # 오른쪽 정렬을 위한 여백 프레임
        ttk.Frame(button_frame).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 확인 버튼과 취소 버튼 (확인 버튼이 왼쪽, 취소 버튼이 오른쪽)
        ttk.Button(button_frame, text="확인", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="취소", command=on_cancel).pack(side=tk.RIGHT, padx=5)
        
        # Enter 키로 확인 버튼 누르기
        dialog.bind("<Return>", lambda event: on_ok())
        # Escape 키로 취소 버튼 누르기
        dialog.bind("<Escape>", lambda event: on_cancel())
        
        # 창이 닫힐 때까지 대기
        self.parent.wait_window(dialog)
        
        # 결과 처리
        if result[0]:
            url = url_var.get().strip()
            # 리스트박스에 추가
            self.url_listbox.insert(tk.END, url)
            
            # DB에 URL 저장
            self.save_urls()
            
            # URL 개수 업데이트
            self.update_url_count()
    
    def delete_url(self):
        """선택된 URL 삭제"""
        selection = self.url_listbox.curselection()
        if not selection:
            messagebox.showinfo("알림", "삭제할 URL을 선택하세요.")
            return
        
        # 선택된 URL 가져오기
        selected_url = self.url_listbox.get(selection[0])
        
        # 리스트박스에서 삭제
        self.url_listbox.delete(selection)
        
        # DB에 저장
        self.save_urls()
    
    def save_urls(self):
        """URL 목록 저장 (DB에만 저장)"""
        try:
            # 리스트박스에서 모든 URL 가져오기
            urls = [self.url_listbox.get(i) for i in range(self.url_listbox.size())]
            
            # DB에 URL 저장
            success = self.db_manager.save_urls(urls)
            
            if success:
                self.logger.info("URL 목록이 DB에 저장되었습니다.")
                
                # URL 개수 업데이트
                count = self.url_listbox.size()
                self.url_count_var.set(f"({count}개)")
                
                return True
            else:
                self.logger.error("URL 목록 저장 실패")
                return False
                    
        except Exception as e:
            self.logger.error(f"URL 목록 저장 오류: {e}")
            messagebox.showerror("오류", f"URL 목록 저장 중 오류가 발생했습니다: {e}")
            return False
    
    def start_countdown_timer(self):
        """카운트다운 타이머 시작"""
        self.update_countdown()
        
    def update_countdown(self):
        """카운트다운 업데이트 - 정확한 시간 표시 버전"""
        try:
            if hasattr(self, 'next_collect_var') and self.next_collect_time:
                # 현재 시간
                now = datetime.now()
                
                # 다음 수집 시간과의 차이 계산
                if isinstance(self.next_collect_time, datetime):
                    remaining = self.next_collect_time - now
                    if remaining.total_seconds() > 0:
                        # 남은 시간 계산
                        minutes = int(remaining.total_seconds() // 60)
                        seconds = int(remaining.total_seconds() % 60)
                        
                        # 표시할 텍스트 생성
                        update_text = f"{minutes}분 {seconds}초 후 (예정: {self.next_collect_time.strftime('%H:%M')})"
                        
                        # 필요한 경우에만 UI 업데이트 (불필요한 업데이트 방지)
                        if not hasattr(self, '_last_countdown_text') or self._last_countdown_text != update_text:
                            self.next_collect_var.set(update_text)
                            self._last_countdown_text = update_text
                    else:
                        self.next_collect_var.set("곧 실행")
            else:
                # 자동화가 비활성화된 경우
                if hasattr(self, 'auto_collect_var') and not self.auto_collect_var.get():
                    self.next_collect_var.set("없음")
        except Exception as e:
            # 오류 로깅만 하고 계속 진행
            self.logger.debug(f"카운트다운 업데이트 중 오류 (무시됨): {e}")
        
        # 5초마다 업데이트 (1초에서 5초로 변경하여 CPU 부하 감소)
        self.parent.after(5000, self.update_countdown)
    
    def toggle_auto_collect(self):
        """자동 수집 토글 - 통합 스케줄러 사용"""
        current_state = self.auto_collect_var.get()
        
        if current_state:  # 활성화 -> 비활성화
            # 기존 예약 작업 제거
            self.parent.remove_scheduled_tasks("data_collector")
            self.auto_collect_var.set(False)
            
            # 상태 텍스트 업데이트
            self.update_status_text("비활성화됨", False)
            
            self.collect_status_var.set("비활성화됨")
            self.next_collect_var.set("없음")
            self.collect_auto_button.config(text="자동화 시작", style="Green.TButton")
            self.collect_start_button.config(state="normal")
            
            # 타이머 관련 변수 초기화
            self.next_collect_time = None
            self.last_collect_time = None
            
            # 로그에 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 자동 수집이 중지되었습니다.\n")
            self.collect_log_text.see(tk.END)
            
            self.logger.info("자동 수집이 중지되었습니다.")
        else:  # 비활성화 -> 활성화
            # 로그인 상태 확인
            if not self.check_headless_login_status():
                messagebox.showwarning("경고", "자동화를 시작하기 전에 로그인이 필요합니다.")
                # 체크박스 상태 복원
                self.auto_collect_var.set(False)
                return
                    
            # URL 검증
            urls = [self.url_listbox.get(i) for i in range(self.url_listbox.size())]
            if not urls:
                messagebox.showwarning("경고", "자동화를 시작하기 전에 URL을 추가하세요.")
                # 체크박스 상태 복원
                self.auto_collect_var.set(False)
                return
                    
            # 수집 간격 검증
            try:
                collect_interval = int(self.collect_interval_var.get())
                if collect_interval < 30:
                    messagebox.showwarning("경고", "수집 간격은 최소 30분 이상이어야 합니다.")
                    self.collect_interval_var.set("30")
                    # 체크박스 상태 복원
                    self.auto_collect_var.set(False)
                    return
            except ValueError:
                messagebox.showwarning("경고", "유효한 수집 간격을 입력하세요.")
                # 체크박스 상태 복원
                self.auto_collect_var.set(False)
                return
                    
            # 활성화 처리
            self.auto_collect_var.set(True)
            
            # 상태 텍스트 업데이트
            self.update_status_text("활성화됨", True)
            
            self.collect_status_var.set("활성화됨")
            self.collect_auto_button.config(text="자동화 중지", style="Red.TButton")
            self.collect_start_button.config(state="disabled")
            
            # 시간 정보 설정
            now = datetime.now()
            self.last_collect_time = now
            self.next_collect_time = now + timedelta(minutes=collect_interval)
            
            # 카운트다운 표시 업데이트
            self.next_collect_var.set(f"{collect_interval}분 후 (예정: {self.next_collect_time.strftime('%H:%M')})")
            
            # 로그에 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 자동 수집이 시작되었습니다. 수집 간격: {collect_interval}분\n")
            self.collect_log_text.see(tk.END)
            
            self.logger.info(f"자동 수집이 시작되었습니다. 수집 간격: {collect_interval}분")
            
            # 통합 스케줄러에 작업 추가
            self.parent.add_scheduled_task("data_collector", self.next_collect_time, self.run_auto_collection)
        
        # 설정 저장
        self.save_settings()
    
    def start_scheduler(self):
        """스케줄러 시작"""
        if self.running:
            self.logger.info("스케줄러가 이미 실행 중입니다.")
            return
            
        self.running = True
        
        # 스케줄 초기화
        schedule.clear()
        
        # 스케줄러 스레드 시작
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        
        self.logger.info("자동 스케줄러 시작")
    
    def stop_scheduler(self):
        """스케줄러 중지"""
        if not self.running:
            self.logger.info("스케줄러가 이미 중지되었습니다.")
            return
            
        self.running = False
        schedule.clear()
        
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            # 스레드 종료 대기
            self.scheduler_thread.join(timeout=2)
            
        self.logger.info("자동 스케줄러 중지")
    
    def _scheduler_loop(self):
        """스케줄러 루프 - 성능 최적화 버전"""
        while self.running:
            try:
                # 현재 시간
                now = datetime.now()
                
                # 수집 주기 확인
                if self.next_collect_time and now >= self.next_collect_time and not self.collecting:
                    self.logger.info(f"수집 주기 도달: {self.next_collect_time.strftime('%Y-%m-%d %H:%M')}")
                    # 수집 시작 전에 다음 수집 시간을 초기화 (새로운 수집 후 다시 계산하기 위해)
                    self.next_collect_time = None
                    threading.Thread(target=self.run_auto_collection, daemon=True).start()
                
                time.sleep(1)  # 1초마다 확인 - 부하 감소를 위해 변경 가능
                
                # 메인 스레드 블로킹 방지를 위한 yield - 더 이상 필요하지 않으므로 제거
                # time.sleep(0.001) 같은 짧은 대기도 제거 가능
            except Exception as e:
                self.logger.error(f"스케줄러 루프 중 오류: {e}")
                time.sleep(5)  # 에러 발생 시 더 긴 대기 시간 설정
    
    # data_collector.py 파일의 run_auto_collection 함수
    def run_auto_collection(self):
        """자동 데이터 수집 실행 - 메모리 관리 개선"""
        if self.collecting:
            self.logger.warning("이미 데이터 수집 중입니다.")
            return False
            
        # Threads 작업 중이면 건너뛰기
        if self.check_threads_running():
            self.logger.warning("Threads 게시 작업이 진행 중이므로 데이터 수집을 연기합니다.")
            # 로그에 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] Threads 게시 작업 진행 중, 데이터 수집 연기됨\n")
            self.collect_log_text.see(tk.END)
            
            # 다음 실행 시간 조정 (5분 후)
            self.next_collect_time = datetime.now() + timedelta(minutes=5)
            self.next_collect_var.set(f"5분 후 (Threads SNS 작업 중)")
            return False
        
        # 수집 중 표시
        self.set_collector_running(True)
        self.collecting = True
        
        try:
            # 로그에 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 자동 데이터 수집을 시작합니다.\n")
            self.collect_log_text.see(tk.END)
            
            # URL 목록 가져오기
            urls = [self.url_listbox.get(i) for i in range(self.url_listbox.size())]
            
            if not urls:
                self.logger.warning("URL 목록이 비어 있습니다.")
                self.collecting = False
                self.set_collector_running(False)
                return False
                    
            # 수집 옵션 설정
            scroll_count = int(self.scroll_count_var.get())
            wait_time = int(self.wait_time_var.get())
            headless = self.headless_var.get()
            max_items = int(self.max_items_var.get())
            
            # 메시지 옵션 설정
            custom_message = ""  # 빈 문자열로 설정
            selected_option = 0  # 기본 옵션 인덱스
            
            # 뉴스픽 수집기 생성
            collector = NewspickCollector(
                base_path=self.base_path,
                scroll_count=scroll_count,
                wait_time=wait_time,
                headless=headless,
                max_items=max_items,
                custom_message="",  # 빈 문자열로 설정
                selected_option=0   # 기본 옵션 인덱스
            )

            # 자동 요약 설정
            collector.auto_summary = self.auto_summary_var.get()
            if collector.auto_summary:
                # API 키 확인
                if not self.check_perplexity_api_key():
                    # 자동화 모드에서는 로그만 남기고 UI 경고는 표시하지 않음
                    self.logger.warning("Perplexity API 키가 설정되지 않았습니다. 자동 요약이 비활성화됩니다.")
                    collector.auto_summary = False
                else:
                    self.logger.info("자동 요약 생성이 활성화된 상태로 데이터 수집을 시작합니다.")

            # 자동화 모드 플래그 설정
            collector.auto_mode = True
            
            # 진행 상황 업데이트 함수
            def progress_callback(current, total, status_text, processed_items=0):
                # 로그에 상태 기록 - 시간 표시 추가
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.collect_log_text.insert(tk.END, f"[{timestamp}] {status_text}\n")
                self.collect_log_text.see(tk.END)
            
            # 데이터 수집 실행
            result = collector.collect_data(urls, progress_callback)
            
            # 다음 수집 시간 설정
            self.last_collect_time = datetime.now()
            collect_interval = int(self.collect_interval_var.get())
            self.next_collect_time = self.last_collect_time + timedelta(minutes=collect_interval)
            
            # 로그 기록
            if result:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.collect_log_text.insert(tk.END, f"[{timestamp}] 자동 데이터 수집이 완료되었습니다. 다음 수집: {self.next_collect_time.strftime('%Y-%m-%d %H:%M')}\n")
                self.collect_log_text.see(tk.END)
                self.logger.info(f"자동 데이터 수집 완료. 다음 수집: {self.next_collect_time.strftime('%Y-%m-%d %H:%M')}")
                
                # 데이터 미리보기 업데이트
                self.load_data()
                # Threads 탭의 데이터도 함께 새로고침
                if hasattr(self.parent, 'threads_ui') and self.parent.threads_ui:
                    self.parent.threads_ui.load_thread_data()
            else:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 수집 중 오류가 발생했습니다.\n")
                self.collect_log_text.see(tk.END)
                self.logger.error("데이터 수집 중 오류가 발생했습니다.")
            
            # 자동화 모드 플래그 해제
            collector.auto_mode = False
            
            # 수집 후 메모리 정리 추가
            try:
                # 가비지 컬렉션 강제 실행
                import gc
                gc.collect()
                
                # 임시 디렉토리 정리
                self.clean_temp_directory()
            except Exception as e:
                self.logger.warning(f"메모리 정리 중 오류 (무시됨): {e}")
            
            # 다음 수집 스케줄링 (통합 스케줄러 사용)
            if hasattr(self, 'auto_collect_var') and self.auto_collect_var.get():
                # 다음 실행 예약
                if hasattr(self.parent, 'add_scheduled_task'):
                    self.parent.add_scheduled_task("data_collector", self.next_collect_time, self.run_auto_collection)
                else:
                    # 통합 스케줄러가 없는 경우, 기존 방식으로 예약
                    pass
            
            return result
                
        except Exception as e:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 수집 중 예외 발생: {str(e)}\n")
            self.collect_log_text.see(tk.END)
            self.logger.error(f"데이터 수집 중 예외 발생: {e}")
            return False
            
        finally:
            self.collecting = False
            self.set_collector_running(False)
    
    def start_data_collection(self):
        """데이터 수집 시작"""
        self.save_settings()
        
        # Threads 작업 중이면 경고 - 이 부분을 수정
        # 기존 코드 제거:
        # if self.check_threads_running():
        #     if not messagebox.askyesno("주의", "현재 Threads 게시 작업이 진행 중입니다."):
        #         return
        
        # 수정된 코드:
        if self.check_threads_running():
            # 로그 기록만 남기고 경고 메시지 없이 진행
            self.logger.info("Threads 게시 작업이 진행 중이지만, 다른 포트/PID를 사용하므로 진행합니다.")
        
        # 리스트박스에서 URL 목록 가져오기
        urls = [self.url_listbox.get(i) for i in range(self.url_listbox.size())]
        
        if not urls:
            messagebox.showwarning("경고", "URL 목록이 비어 있습니다.")
            return
                
        # 헤드리스 모드 확인
        if self.headless_var.get():
            if not self.check_headless_login_status():
                return  # 헤드리스 모드를 사용할 수 없으면 함수 종료
        
        # 설정 값 가져오기
        scroll_count = int(self.scroll_count_var.get())
        wait_time = int(self.wait_time_var.get())
        headless = self.headless_var.get()
        max_items = int(self.max_items_var.get())
        
        # 뉴스픽 수집기 생성 - 메시지 옵션 관련 매개변수 제거
        collector = NewspickCollector(
            base_path=self.base_path,
            scroll_count=scroll_count,
            wait_time=wait_time,
            headless=headless,
            max_items=max_items,
            custom_message="",  # 빈 문자열로 변경
            selected_option=0   # 의미 없는 값으로 변경
        )
        
        # 명시적으로 collector의 should_stop 플래그를 False로 설정 (추가)
        collector.should_stop = False
        collector.auto_mode = False  # 수동 모드임을 명시
        
        # 데이터 수집 중 표시
        self.set_collector_running(True)
        
        # 진행 상황을 표시할 프로그레스 바 생성
        progress_window = tk.Toplevel(self.parent)
        progress_window.title("데이터 수집 중...")
        progress_window.geometry("450x200")
        progress_window.resizable(False, False)
        
        progress_label = ttk.Label(progress_window, text="데이터 수집을 시작합니다...")
        progress_label.pack(pady=10)
        
        progress_bar = ttk.Progressbar(progress_window, orient="horizontal", length=400, mode="determinate")
        progress_bar.pack(pady=10)
        
        status_label = ttk.Label(progress_window, text="")
        status_label.pack(pady=5)
        
        time_label = ttk.Label(progress_window, text="예상 남은 시간: 계산 중...")
        time_label.pack(pady=5)
        
        cancel_button = ttk.Button(
            progress_window, 
            text="취소", 
            command=lambda: self.cancel_collection(collector, progress_window)
        )
        cancel_button.pack(pady=5)
        
        # 시작 시간 기록
        start_time = time.time()
        total_processed = [0]  # 처리된 총 항목 수
        
        # 진행 상태 업데이트 함수 - 퍼센테이지 대신 카테고리와 현재 URL 정보 표시
        def update_progress(current_url_idx, total_urls, status_text, processed_items=None):
            if progress_window.winfo_exists():
                # 프로그레스바는 전체 URL 중 현재 URL의 진행 상태를 표시
                progress = int(((current_url_idx + 1) / total_urls) * 100)
                progress_bar["value"] = progress
                status_label.config(text=status_text)
                
                # 로그에 상태 기록 - 시간 표시 추가
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.collect_log_text.insert(tk.END, f"[{timestamp}] {status_text}\n")
                self.collect_log_text.see(tk.END)
                
                # 예상 남은 시간 계산
                elapsed_time = time.time() - start_time
                
                if processed_items is not None:
                    total_processed[0] = processed_items
                
                if total_processed[0] > 0 and elapsed_time > 5:  # 최소 5초 이상 경과 후 계산
                    items_per_second = total_processed[0] / elapsed_time
                    
                    if items_per_second > 0:
                        # 남은 항목 수 (URL별 최대 항목 * URL 수) - 처리 완료 항목
                        remaining_items = collector.max_items * len(urls) - total_processed[0]
                        remaining_time = remaining_items / items_per_second
                        
                        # 시간 형식화
                        if remaining_time > 3600:
                            time_text = f"예상 남은 시간: {int(remaining_time//3600)}시간 {int((remaining_time%3600)//60)}분"
                        elif remaining_time > 60:
                            time_text = f"예상 남은 시간: {int(remaining_time//60)}분 {int(remaining_time%60)}초"
                        else:
                            time_text = f"예상 남은 시간: {int(remaining_time)}초"
                        
                        time_label.config(text=time_text)
                
                progress_window.update()
        
        # 데이터 수집을 별도 스레드에서 실행
        def collection_thread():
            try:
                # 수집 시작 기록
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 수집 시작 (URL: {len(urls)}개)\n")
                self.collect_log_text.see(tk.END)
                
                result = collector.collect_data(urls, update_progress)
                
                # should_stop 플래그 확인에 더 명확한 조건 추가
                if result and not collector.should_stop:
                    if progress_window.winfo_exists():
                        progress_window.destroy()
                    
                    # 여기서 로그인 상태 확인 및 UI 업데이트 추가
                    login_success = self.check_headless_login_status()
                    
                    messagebox.showinfo("완료", "데이터 수집이 완료되었습니다.")
                    
                    # 로그인 상태가 확인되면 헤드리스 모드와 자동화 기능 활성화
                    if login_success:
                        self.headless_checkbox.config(state="normal")
                        self.auto_collect_checkbox.config(state="normal")  # 추가된 부분
                        self.collect_auto_button.config(state="normal")    # 추가된 부분
                        # UI 반영을 위해 update_idletasks 호출
                        self.parent.update_idletasks()
                    
                    # 수집 완료 기록
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 수집 완료\n")
                    self.collect_log_text.see(tk.END)
                    
                    # 데이터 새로고침
                    self.load_data()
                    # Threads 탭의 데이터도 함께 새로고침
                    if hasattr(self.parent, 'threads_ui') and self.parent.threads_ui:
                        self.parent.threads_ui.load_thread_data()
                    
                elif collector.should_stop:
                    self.logger.info("사용자에 의해 데이터 수집이 취소되었습니다.")
                    
                    # 수집 취소 기록
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 수집 취소됨\n")
                    self.collect_log_text.see(tk.END)
                    
                    # progress_window는 이미 cancel_collection에서 닫았으므로 여기서는 처리 안 함
                else:
                    if progress_window.winfo_exists():
                        progress_window.destroy()
                    messagebox.showerror("오류", "데이터 수집 중 오류가 발생했습니다.")
                    
                    # 수집 오류 기록
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 수집 오류 발생\n")
                    self.collect_log_text.see(tk.END)
            except Exception as e:
                self.logger.error(f"데이터 수집 중 오류: {e}")
                if progress_window.winfo_exists():
                    progress_window.destroy()
                messagebox.showerror("오류", f"데이터 수집 중 오류가 발생했습니다: {e}")
                
                # 수집 오류 상세 기록
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 수집 중 오류: {str(e)}\n")
                self.collect_log_text.see(tk.END)
            finally:
                # 작업 완료 후 실행 중 표시 해제
                self.set_collector_running(False)
        
        # 스레드 시작
        collection_task = threading.Thread(target=collection_thread)
        collection_task.daemon = True
        self.running_tasks.append((collection_task, collector))
        collection_task.start()

        # 자동 요약 설정
        collector.auto_summary = self.auto_summary_var.get()
        if collector.auto_summary:
            # API 키 확인
            if not self.check_perplexity_api_key():
                messagebox.showwarning("경고", "Perplexity API 키가 설정되지 않았습니다. 자동 요약이 비활성화됩니다.")
                collector.auto_summary = False
                self.auto_summary_var.set(False)
            else:
                self.logger.info("자동 요약 생성이 활성화되었습니다.")

        # 자동 요약 설정
        collector.auto_summary = self.auto_summary_var.get()
        if collector.auto_summary:
            # API 키 확인 (이미 체크박스 클릭 시 확인하지만 안전성을 위해 한번 더 확인)
            if not self.check_perplexity_api_key():
                self.logger.warning("Perplexity API 키가 설정되지 않았습니다. 자동 요약이 비활성화됩니다.")
                collector.auto_summary = False
                self.auto_summary_var.set(False)
            else:
                self.logger.info("자동 요약 생성이 활성화된 상태로 데이터 수집을 시작합니다.")
    
    
    def cancel_collection(self, collector, progress_window=None):
        """데이터 수집 취소"""
        if messagebox.askyesno("확인", "정말로 데이터 수집을 취소하시겠습니까?"):
            # 명시적으로 collector의 should_stop 플래그를 True로 설정
            collector.should_stop = True
            self.logger.info("데이터 수집이 취소되었습니다.")
            
            # 로그에 취소 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 수집 취소 요청\n")
            self.collect_log_text.see(tk.END)
            
            # 프로그레스 창이 있으면 닫기
            if progress_window and progress_window.winfo_exists():
                progress_window.destroy()
                
            # 브라우저 프로세스 강제 종료
            try:
                collector.kill_browser_processes()
                self.logger.info("브라우저 프로세스가 종료되었습니다.")
            except Exception as e:
                self.logger.error(f"브라우저 종료 중 오류: {e}")
    
    # data_collector.py 파일의 load_data 메서드 수정

    def load_data(self):
        """DB 데이터 로드하여 트리뷰에 표시"""
        try:
            # 기존 데이터 삭제
            try:
                # 안전한 방식으로 모든 항목 삭제
                children = self.data_tree.get_children()
                if children:  # 항목이 있는 경우에만 삭제 시도
                    self.data_tree.delete(*children)
            except Exception as e:
                self.logger.warning(f"트리뷰 초기화 중 오류: {e}")
                for item in list(self.data_tree.get_children()):
                    try:
                        self.data_tree.delete(item)
                    except Exception as item_e:
                        self.logger.debug(f"항목 {item} 삭제 중 무시된 오류: {item_e}")
                        continue
                                
            # DB에서 뉴스 항목 가져오기
            news_items = self.db_manager.get_news_items()
            
            if not news_items:
                self.logger.info("표시할 데이터가 없습니다.")
                return
                                
            # 각 행을 트리뷰에 추가
            for idx, item in enumerate(news_items):
                # 이미지 경로 존재 여부 확인
                image_path = item.get("이미지 경로", "")
                image_status = "O" if image_path and os.path.exists(image_path) else "X"
                
                # 포스팅 상태 및 시간 확인 - threads 플랫폼 상태 확인
                posting_status = "미게시"
                posting_time = ""
                item_id = item.get("id")
                
                # DB에서 포스팅 상태 확인
                try:
                    conn = self.db_manager.get_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT status, post_date FROM posting_status 
                        WHERE news_id = ? AND platform_id = 'threads'
                        """,
                        (item_id,)
                    )
                    result = cursor.fetchone()
                    if result:
                        if '포스팅 완료' in result[0]:
                            posting_status = "완료"
                        # 포스팅 시간 처리 - 전체 날짜 시간 표시로 변경
                        if result[1]:  # post_date가 있는 경우
                            posting_time = result[1]  # 원본 날짜시간 그대로 사용
                            
                except Exception as e:
                    self.logger.error(f"포스팅 상태 확인 중 오류: {e}")
                
                # 트리뷰에 데이터 추가 (선택 열을 추가)
                try:
                    self.data_tree.insert("", tk.END, text=str(idx+1), 
                                    values=("", # 선택 열 추가 
                                            item.get("카테고리", ""), 
                                            item.get("게시물 제목", ""), 
                                            item.get("복사링크", ""),
                                            item.get("수집 날짜", ""),
                                            image_status,
                                            item.get("500자 요약", ""),
                                            posting_status,
                                            posting_time,
                                            item.get("thread1", ""),
                                            item.get("thread2", ""),
                                            item.get("thread3", ""),
                                            item.get("thread4", ""),
                                            item.get("thread5", ""),
                                            item.get("created_status", "")))
                except Exception as insert_e:
                    self.logger.warning(f"항목 추가 중 오류 (행 {idx+1}): {insert_e}")
                    # 계속 진행
                                
            self.logger.info(f"데이터베이스에서 {len(news_items)}개 항목을 로드했습니다.")
            
            # 로그에 데이터 새로고침 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 새로고침 완료: {len(news_items)}개 항목\n")
            self.collect_log_text.see(tk.END)
            
        except Exception as e:
            self.logger.error(f"데이터 로드 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            
            # 로그에 오류 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 로드 중 오류: {str(e)}\n")
            self.collect_log_text.see(tk.END)

    def save_column_widths(self):
        """트리뷰 열 너비 설정 저장"""
        column_widths = {}
        # 모든 열의 현재 너비 가져오기
        for col in self.data_tree["columns"] + ("#0",):
            width = self.data_tree.column(col, "width")
            column_widths[col] = width
        
        # 설정에 열 너비 저장
        self.settings["column_widths"] = column_widths
        self.save_settings()

    def restore_column_widths(self):
        """저장된 트리뷰 열 너비 복원"""
        if "column_widths" in self.settings:
            column_widths = self.settings["column_widths"]
            for col, width in column_widths.items():
                try:
                    # 저장된 너비로 열 설정
                    self.data_tree.column(col, width=width)
                except:
                    pass

    def toggle_selection(self, event):
        """트리뷰 항목 클릭 시 선택 상태 토글"""
        item = self.data_tree.identify_row(event.y)
        column = self.data_tree.identify_column(event.x)
        
        if column == "#1":  # 첫 번째 컬럼(선택)을 클릭한 경우
            if item:
                current_val = self.data_tree.item(item, "values")
                if current_val:
                    # '✓' 또는 '' 토글
                    check_val = '✓' if current_val[0] != '✓' else ''
                    new_vals = (check_val,) + current_val[1:]
                    self.data_tree.item(item, values=new_vals)

    # 3. delete_selected_items 메소드 수정 - normalize_title 메소드 추가
    def normalize_title(self, title):
        """제목 표준화 (소문자 변환 및 공백 제거)"""
        return title.strip().lower() if title else ""

    # data_collector.py 파일의 open_category_mapping_editor 메소드 수정
    def open_category_mapping_editor(self):
        """카테고리 매핑 편집 화면 열기"""
        try:
            # 카테고리 매퍼 인스턴스 생성
            from category_mapper import CategoryMapper
            category_mapper = CategoryMapper(self.base_path)
            
            # 카테고리 매핑 정보 가져오기
            mappings = category_mapper.get_all_mappings()
            
            # 편집 창 생성
            editor_window = tk.Toplevel(self.parent)
            editor_window.title("카테고리 매핑 관리")
            editor_window.geometry("600x600")  # 창 크기 확장
            editor_window.resizable(True, True)
            
            # 메인 프레임
            main_frame = ttk.Frame(editor_window, padding=10)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # 설명 레이블
            ttk.Label(main_frame, text="URL 해시값과 카테고리명 매핑을 관리합니다.").pack(fill=tk.X, pady=(0, 10))
            
            # URL 매핑 정보 표시 레이블
            ttk.Label(main_frame, text="URL 예시: https://partners.newspic.kr/main/index#89 → 유머/이슈", 
                    font=("", 9, "italic")).pack(fill=tk.X, pady=(0, 5))
            
            # 매핑 테이블 프레임
            table_frame = ttk.Frame(main_frame)
            table_frame.pack(fill=tk.BOTH, expand=True, pady=10)
            
            # 스크롤바 설정
            y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
            y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            # 트리뷰 생성
            columns = ("id", "category")
            mapping_tree = ttk.Treeview(table_frame, columns=columns, yscrollcommand=y_scroll.set, show="headings")
            mapping_tree.pack(fill=tk.BOTH, expand=True)
            
            # 스크롤바 연결
            y_scroll.config(command=mapping_tree.yview)
            
            # 컬럼 설정
            mapping_tree.heading("id", text="ID")
            mapping_tree.heading("category", text="카테고리명")
            
            mapping_tree.column("id", width=80, stretch=False)
            mapping_tree.column("category", width=400, stretch=True)
            
            # 데이터 로드
            for category_id, category_name in sorted(mappings.items()):
                mapping_tree.insert("", tk.END, values=(category_id, category_name))
            
            # 편집 프레임
            edit_frame = ttk.LabelFrame(main_frame, text="카테고리 매핑 편집")
            edit_frame.pack(fill=tk.X, pady=10)
            
            # ID 입력 필드
            id_frame = ttk.Frame(edit_frame)
            id_frame.pack(fill=tk.X, pady=5)
            ttk.Label(id_frame, text="ID:").pack(side=tk.LEFT, padx=5)
            id_var = tk.StringVar()
            id_entry = ttk.Entry(id_frame, width=10, textvariable=id_var)
            id_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            
            # 카테고리명 입력 필드
            category_frame = ttk.Frame(edit_frame)
            category_frame.pack(fill=tk.X, pady=5)
            ttk.Label(category_frame, text="카테고리명:").pack(side=tk.LEFT, padx=5)
            category_var = tk.StringVar()
            category_entry = ttk.Entry(category_frame, width=30, textvariable=category_var)
            category_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            
            # 트리뷰 선택 이벤트 핸들러
            def on_tree_select(event):
                # 선택된 항목 가져오기
                selected_items = mapping_tree.selection()
                if selected_items:
                    # 첫 번째 선택된 항목의 값 가져오기
                    item = selected_items[0]
                    values = mapping_tree.item(item, "values")
                    
                    # 입력 필드에 값 설정
                    id_var.set(values[0])
                    category_var.set(values[1])
            
            # 트리뷰 선택 이벤트 연결
            mapping_tree.bind("<<TreeviewSelect>>", on_tree_select)
            
            # 버튼 프레임
            button_frame = ttk.Frame(edit_frame)
            button_frame.pack(fill=tk.X, pady=10)
            
            # 추가/업데이트 버튼
            def update_mapping():
                category_id = id_var.get().strip()
                category_name = category_var.get().strip()
                
                if not category_id or not category_name:
                    messagebox.showerror("오류", "ID와 카테고리명을 모두 입력해주세요.")
                    return
                
                # 카테고리 매핑 업데이트
                category_mapper.update_mapping(category_id, category_name)
                
                # 트리뷰 업데이트
                for item in mapping_tree.get_children():
                    if mapping_tree.item(item, "values")[0] == category_id:
                        mapping_tree.item(item, values=(category_id, category_name))
                        break
                else:
                    # 없으면 새로 추가
                    mapping_tree.insert("", tk.END, values=(category_id, category_name))
                
                # 입력 필드 초기화
                id_var.set("")
                category_var.set("")
                
                messagebox.showinfo("성공", f"카테고리 매핑 '{category_id}: {category_name}'이(가) 저장되었습니다.")
            
            ttk.Button(button_frame, text="저장", command=update_mapping).pack(side=tk.LEFT, padx=5)
            
            # 삭제 버튼
            def delete_mapping():
                selected_items = mapping_tree.selection()
                if not selected_items:
                    messagebox.showerror("오류", "삭제할 항목을 선택해주세요.")
                    return
                
                # 확인 대화상자
                if not messagebox.askyesno("확인", "선택한 매핑을 삭제하시겠습니까?"):
                    return
                
                # 선택된 항목 삭제
                for item in selected_items:
                    values = mapping_tree.item(item, "values")
                    category_id = values[0]
                    
                    # 매핑에서 삭제
                    mappings.pop(category_id, None)
                    
                    # 트리뷰에서 삭제
                    mapping_tree.delete(item)
                
                # 매핑 저장
                category_mapper.save_mapping(mappings)
                
                # 입력 필드 초기화
                id_var.set("")
                category_var.set("")
                
                messagebox.showinfo("성공", "선택한 카테고리 매핑이 삭제되었습니다.")
            
            ttk.Button(button_frame, text="삭제", command=delete_mapping).pack(side=tk.LEFT, padx=5)
            
            # 기본값 초기화 버튼 추가
            def reset_to_default():
                if messagebox.askyesno("확인", "모든 카테고리 매핑을 기본값으로 초기화하시겠습니까?\n기존 매핑은 모두 삭제됩니다."):
                    # 기본 매핑으로 초기화
                    success = category_mapper.reset_to_default_mapping()
                    
                    if success:
                        # 트리뷰 초기화
                        for item in mapping_tree.get_children():
                            mapping_tree.delete(item)
                        
                        # 기본 매핑 데이터 로드
                        default_mappings = category_mapper.get_all_mappings()
                        for cid, cname in sorted(default_mappings.items()):
                            mapping_tree.insert("", tk.END, values=(cid, cname))
                        
                        messagebox.showinfo("성공", "카테고리 매핑이 기본값으로 초기화되었습니다.")
                    else:
                        messagebox.showerror("오류", "기본값 초기화 중 오류가 발생했습니다.")
            
            ttk.Button(button_frame, text="기본값 초기화", command=reset_to_default).pack(side=tk.LEFT, padx=5)
            
            # 대량 추가 버튼 - 제공된 매핑 정보 일괄 추가
            def bulk_add_mappings():
                # 여기에 미리 정의된 매핑 정보
                predefined_mappings = {
                    "89": "유머/이슈",
                    "87": "스토리",
                    "36": "연예가화제",
                    "31": "정치",
                    "14": "경제",
                    "32": "사회",
                    "12": "사건사고",
                    "51": "TV연예",
                    "53": "영화",
                    "57": "K-뮤직",
                    "7": "스포츠",
                    "15": "축구",
                    "16": "야구",
                    "3": "반려동물",
                    "33": "생활픽",
                    "58": "해외연예",
                    "11": "BBC NEWS",
                    "38": "NNA 코리아",
                    "39": "글로벌"
                }
                
                if messagebox.askyesno("확인", "미리 정의된 매핑 정보를 모두 추가하시겠습니까?"):
                    # 현재 매핑에 미리 정의된 매핑 추가
                    current_mappings = category_mapper.get_all_mappings()
                    
                    # 미리 정의된 매핑 추가
                    update_count = 0
                    for cid, cname in predefined_mappings.items():
                        # 해당 ID가 없거나 카테고리 이름이 다른 경우에만 업데이트
                        if cid not in current_mappings or current_mappings[cid] != cname:
                            category_mapper.update_mapping(cid, cname)
                            update_count += 1
                    
                    # 트리뷰 초기화
                    for item in mapping_tree.get_children():
                        mapping_tree.delete(item)
                    
                    # 업데이트된 매핑 데이터 로드
                    updated_mappings = category_mapper.get_all_mappings()
                    for cid, cname in sorted(updated_mappings.items()):
                        mapping_tree.insert("", tk.END, values=(cid, cname))
                    
                    messagebox.showinfo("성공", f"{update_count}개의 매핑 정보가 추가되었습니다.")
            
            ttk.Button(button_frame, text="미리 정의된 매핑 추가", command=bulk_add_mappings).pack(side=tk.LEFT, padx=5)
            
            # 닫기 버튼
            ttk.Button(main_frame, text="닫기", command=editor_window.destroy).pack(side=tk.RIGHT, pady=10)
            
        except Exception as e:
            self.logger.error(f"카테고리 매핑 편집기 열기 중 오류: {e}")
            messagebox.showerror("오류", f"카테고리 매핑 편집기를 열 수 없습니다: {e}")

    def delete_selected_items(self):
        """선택된 항목 삭제 (DB에서 삭제)"""
        selected_items = []
        
        # 체크된 항목 찾기
        for item in self.data_tree.get_children():
            values = self.data_tree.item(item, "values")
            if values and values[0] == '✓':  # 체크된 항목
                index = int(self.data_tree.item(item, "text")) - 1  # 인덱스는 1부터 시작하므로 -1
                selected_items.append((item, index))
        
        if not selected_items:
            messagebox.showinfo("알림", "삭제할 항목을 선택해주세요.")
            return
        
        # 삭제 확인
        if not messagebox.askyesno("확인", f"선택한 {len(selected_items)}개 항목을 삭제하시겠습니까?"):
            return
        
        try:
            # 선택된 항목들의 ID 가져오기
            news_items = self.db_manager.get_news_items()
            
            deleted_count = 0
            titles_to_remove = []  # 삭제할 제목 목록
            
            for tree_item, index in selected_items:
                if 0 <= index < len(news_items):
                    news_id = news_items[index].get("id")
                    title = news_items[index].get("게시물 제목", "")
                    titles_to_remove.append(self.normalize_title(title))
                    
                    # DB에서 항목 삭제
                    if self.db_manager.delete_news_item(news_id):
                        deleted_count += 1
            
            # 삭제된 제목을 중복 캐시에서도 제거
            for title in titles_to_remove:
                # DB의 processed_titles 테이블에서도 삭제
                self.db_manager.delete_processed_title(title)
            
            # 삭제 완료 메시지
            messagebox.showinfo("완료", f"{deleted_count}개 항목이 삭제되었습니다.")
            
            # 로그에 삭제 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] {deleted_count}개 항목이 삭제되었습니다.\n")
            self.collect_log_text.see(tk.END)
            
            # 데이터 새로 로드
            self.load_data()
            
        except Exception as e:
            self.logger.error(f"항목 삭제 중 오류: {e}")
            messagebox.showerror("오류", f"항목 삭제 중 오류가 발생했습니다: {e}")
            
            # 로그에 오류 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 항목 삭제 중 오류: {str(e)}\n")
            self.collect_log_text.see(tk.END)
    
    def export_data(self):
        """수집된 데이터를 엑셀 파일로 내보내기"""
        try:
            # 데이터프레임으로 변환
            df = self.db_manager.export_to_dataframe()
            
            if df.empty:
                messagebox.showwarning("경고", "내보낼 데이터가 없습니다.")
                return
                
            # 저장 대화상자 표시
            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel 파일", "*.xlsx"), ("모든 파일", "*.*")],
                initialdir=self.settings["data_path"],
                title="데이터 내보내기"
            )
            
            if not file_path:
                return  # 사용자가 취소한 경우
                
            # 엑셀 파일로 저장
            df.to_excel(file_path, index=False)
            
            # 로그 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터가 '{file_path}'로 내보내졌습니다.\n")
            self.collect_log_text.see(tk.END)
            
            messagebox.showinfo("완료", f"데이터가 '{file_path}'로 내보내졌습니다.")
            
        except Exception as e:
            self.logger.error(f"데이터 내보내기 중 오류: {e}")
            messagebox.showerror("오류", f"데이터 내보내기 중 오류가 발생했습니다: {e}")
            
            # 로그 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 내보내기 중 오류: {str(e)}\n")
            self.collect_log_text.see(tk.END)
    
    def cleanup(self):
        """리소스 정리"""
   
        # 스케줄러 중지
        self.stop_scheduler()
        
        # 실행 중인 작업 중지
        for task, collector in self.running_tasks:
            if hasattr(collector, 'should_stop'):
                collector.should_stop = True

        # 열 너비 설정 저장
        self.save_column_widths()
        
        # 설정 저장
        self.save_settings()
        
        # 작업 중 표시 해제
        self.set_collector_running(False)