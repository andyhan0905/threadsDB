import os
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import logging
from datetime import datetime, timedelta
import time

from threads_manager import ThreadsManager
from ui_components import validate_numeric_input

class ThreadsUI:

    # 클래스 상수 정의
    THREADS_LOCK_FILE = "threads_running.lock"
    DATA_COLLECTOR_LOCK_FILE = "collector_running.lock"

    """Threads SNS 관련 UI 모듈"""
    
# 1. ThreadsUI 클래스의 초기화 부분 수정

    def __init__(self, parent):
        """
        Threads UI 초기화
        
        Args:
            parent: 부모 애플리케이션 객체
        """
        self.parent = parent
        self.base_path = parent.base_path
        self.db_manager = parent.db_manager
        self.logger = parent.logger
        self.main_frame = parent.threads_tab  # Threads 탭으로 변경
        self.collect_log_text = parent.collect_log_text  # 공유된 로그 텍스트 위젯
        
        # Threads 매니저
        self.threads_manager = None
        
        # DB 업데이트
        self.db_manager.update_database_for_threads()
        
        # 설정 로드
        self.threads_settings = self.db_manager.load_threads_settings()
        
        # 자동화 관련 변수 초기화
        self.threads_auto_scheduler = None
        self.threads_collecting = False
        self.threads_last_run_time = None
        self.threads_next_run_time = None
        
        # UI 생성
        self.create_widgets()
        
        # 초기에 자동화 관련 UI 요소 비활성화
        self.threads_auto_var.set(False)
        self.threads_auto_checkbox.config(state="disabled")  # 체크박스 비활성화
        self.threads_auto_button.config(state="disabled")    # 자동화 시작 버튼 비활성화
        
        # 로그인 상태 확인
        self.check_threads_login_status()
        
        # 카운트다운 타이머 시작
        self.update_threads_countdown()

        # 초기 데이터 로드
        self.load_thread_data()

        # 저장된 열 너비 복원 (여기에 추가)
        self.restore_thread_column_widths()
    
    def create_widgets(self):
        """Threads UI 위젯 생성 - 일반 포스팅과 감성 포스팅 영역으로 분리"""
        from ui_components import validate_numeric_input
        
        # 최상단에 Threads 로그인 관리 섹션 추가
        login_manage_frame = ttk.LabelFrame(self.main_frame, text="Threads 로그인 관리")
        login_manage_frame.pack(fill=tk.X, expand=False, padx=10, pady=5)
        
        # 로그인 상태 표시 및 버튼
        login_status_frame = ttk.Frame(login_manage_frame)
        login_status_frame.pack(fill=tk.X, pady=5)
        
        # 왼쪽: 상태 표시
        status_container = ttk.Frame(login_status_frame)
        status_container.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(status_container, text="Threads 로그인 상태:").pack(side=tk.LEFT, padx=5)
        self.threads_login_status_var = tk.StringVar(value="로그인 필요")
        ttk.Label(status_container, textvariable=self.threads_login_status_var).pack(side=tk.LEFT, padx=5)
        
        # 오른쪽: 로그인 버튼
        button_container = ttk.Frame(login_status_frame)
        button_container.pack(side=tk.RIGHT, padx=10)
        
        self.login_button = ttk.Button(
            button_container,
            text="로그인",
            style="TButton",
            command=self.login_threads
        )
        self.login_button.pack(side=tk.RIGHT, padx=5)
        
        # 헤드리스 모드 체크박스 (로그인 관리 섹션으로 이동)
        headless_frame = ttk.Frame(login_manage_frame)
        headless_frame.pack(fill=tk.X, pady=2)
        self.threads_headless_var = tk.BooleanVar(value=self.threads_settings.get("headless_mode", False))
        self.threads_headless_checkbox = ttk.Checkbutton(
            headless_frame, 
            text="헤드리스 모드 사용 (브라우저 숨기기, 로그인 후 가능)", 
            variable=self.threads_headless_var,
            command=self.update_headless_mode,
            state="disabled"
        )
        self.threads_headless_checkbox.pack(side=tk.LEFT, padx=5)
        
        # 상위 컨테이너 프레임 생성 (일반 포스팅과 감성 포스팅 영역을 수평으로 배치)
        container_frame = ttk.Frame(self.main_frame)
        container_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 일반 포스팅 영역 (왼쪽) - width 설정으로 가로 크기 고정
        self.general_frame = ttk.LabelFrame(container_frame, text="일반 포스팅", width=480)
        self.general_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.general_frame.pack_propagate(False)  # 크기 고정
        
        # 감성 포스팅 영역 (오른쪽) - width 설정으로 가로 크기 고정
        self.emotional_frame = ttk.LabelFrame(container_frame, text="감성 포스팅", width=480)
        self.emotional_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        self.emotional_frame.pack_propagate(False)  # 크기 고정
        
        # ===== 일반 포스팅 영역 구성 =====
        # Threads 설정 프레임
        threads_settings_frame = ttk.Frame(self.general_frame)
        threads_settings_frame.pack(fill=tk.X, expand=False, padx=5, pady=5)
        
        # 자동화 설정
        auto_threads_frame = ttk.Frame(threads_settings_frame)
        auto_threads_frame.pack(fill=tk.X, pady=2)
        self.threads_auto_var = tk.BooleanVar(value=self.threads_settings.get("auto_post", False))
        
        # 체크박스 참조 저장
        self.threads_auto_checkbox = ttk.Checkbutton(
            auto_threads_frame, 
            text="자동 게시 활성화", 
            variable=self.threads_auto_var,
            command=self.toggle_threads_auto
        )
        self.threads_auto_checkbox.pack(side=tk.LEFT, padx=5)

        # 수집 간격
        interval_frame = ttk.Frame(threads_settings_frame)
        interval_frame.pack(fill=tk.X, pady=2)
        ttk.Label(interval_frame, text="게시 간격(분):").pack(side=tk.LEFT, padx=5)
        
        self.threads_interval_var = tk.StringVar(value=str(self.threads_settings.get("post_interval", 15)))
        vcmd = (self.parent.register(validate_numeric_input), '%P')
        ttk.Spinbox(
            interval_frame, 
            from_=1,
            to=1440, 
            width=5, 
            textvariable=self.threads_interval_var,
            validate="key", 
            validatecommand=vcmd
        ).pack(side=tk.LEFT, padx=5)
        
        # 경고 메시지 추가 - 빨간색으로 표시 (줄인 메시지)
        warning_label = ttk.Label(interval_frame, 
                                text="최소 15분 권장",
                                foreground="red")
        warning_label.pack(side=tk.LEFT, padx=5)
        
        # 메시지 옵션 설정 - 고정 너비로 변경
        message_frame = ttk.Frame(threads_settings_frame)
        message_frame.pack(fill=tk.X, pady=2)
        
        # 왼쪽 레이블 프레임
        message_label_frame = ttk.Frame(message_frame)
        message_label_frame.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(message_label_frame, text="메시지 옵션:").pack(side=tk.LEFT, padx=5)
        
        # 메시지 옵션 콤보박스
        self.threads_message_options = ["(아래 링크👇)", "(댓글 링크👇)", "(하단 링크👇)", "사용자 정의 입력"]
        self.threads_message_var = tk.StringVar(value=self.threads_message_options[0])
        
        # 콤보박스 프레임
        combo_frame = ttk.Frame(message_frame)
        combo_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        self.threads_message_combo = ttk.Combobox(
            combo_frame, 
            textvariable=self.threads_message_var,
            values=self.threads_message_options,
            width=15,  # 너비 줄임
            state="readonly"
        )
        self.threads_message_combo.current(0)  # 기본값 설정
        self.threads_message_combo.pack(side=tk.LEFT, padx=5)
        self.threads_message_combo.bind("<<ComboboxSelected>>", self.on_threads_message_change)
        
        # 사용자 정의 입력 필드 - 너비 제한
        entry_frame = ttk.Frame(message_frame)
        entry_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        self.threads_custom_message_entry = ttk.Entry(entry_frame, width=20)  # 너비 줄임
        self.threads_custom_message_entry.pack(side=tk.LEFT, padx=5)
        self.threads_custom_message_entry.insert(0, "")  # 초기값
        self.threads_custom_message_entry.config(state="disabled")  # 초기 상태는 비활성화

        # 최대 항목 수
        max_items_frame = ttk.Frame(threads_settings_frame)
        max_items_frame.pack(fill=tk.X, pady=2)
        ttk.Label(max_items_frame, text="최대 게시물 수:").pack(side=tk.LEFT, padx=5)
        self.threads_max_posts_var = tk.StringVar(value=str(self.threads_settings.get("max_posts_per_run", 5)))
        ttk.Spinbox(
            max_items_frame, 
            from_=1, 
            to=20, 
            width=5, 
            textvariable=self.threads_max_posts_var,
            validate="key", 
            validatecommand=vcmd
        ).pack(side=tk.LEFT, padx=5)
        ttk.Label(max_items_frame, text="(한 번에 처리할 항목 수)").pack(side=tk.LEFT, padx=5)

        # 자동화 상태 표시
        status_frame = ttk.Frame(threads_settings_frame)
        status_frame.pack(fill=tk.X, pady=2)
        ttk.Label(status_frame, text="자동화 상태:").pack(side=tk.LEFT, padx=5)
        self.threads_status_var = tk.StringVar(value="비활성화됨")
        ttk.Label(status_frame, textvariable=self.threads_status_var).pack(side=tk.LEFT, padx=5)

        # 다음 실행 시간
        next_frame = ttk.Frame(threads_settings_frame)
        next_frame.pack(fill=tk.X, pady=2)
        ttk.Label(next_frame, text="다음 실행 예정:").pack(side=tk.LEFT, padx=5)
        self.threads_next_run_var = tk.StringVar(value="없음")
        ttk.Label(next_frame, textvariable=self.threads_next_run_var).pack(side=tk.LEFT, padx=5)

        # 버튼 프레임 - 수정된 부분
        threads_button_frame = ttk.Frame(self.general_frame)
        threads_button_frame.pack(fill=tk.X, pady=5)

        # 자동화 버튼 - 이름 변경
        self.threads_auto_button = ttk.Button(
            threads_button_frame,
            text="일반 자동화 시작",  # 수정된 부분
            style="Green.TButton",
            command=self.toggle_threads_auto
        )
        self.threads_auto_button.pack(side=tk.LEFT, padx=5)

        # 단일 게시 버튼 - 이름 변경 및 위치 변경
        self.post_threads_button = ttk.Button(
            threads_button_frame,
            text="일반 포스팅",  # 수정된 부분 
            style="TButton",
            command=self.single_post_to_threads
        )
        self.post_threads_button.pack(side=tk.LEFT, padx=5)  # 왼쪽으로 이동
        
        # ===== 감성 포스팅 영역 구성 =====
        # 감성 포스팅 내용 구성 - 일반 포스팅과 유사하게 구성
        emotional_settings_frame = ttk.Frame(self.emotional_frame)
        emotional_settings_frame.pack(fill=tk.X, expand=False, padx=5, pady=5)

        # 자동화 설정
        auto_emotional_frame = ttk.Frame(emotional_settings_frame)
        auto_emotional_frame.pack(fill=tk.X, pady=2)
        self.emotional_auto_var = tk.BooleanVar(value=False)  # 초기값은 비활성화

        # 체크박스 참조 저장
        self.emotional_auto_checkbox = ttk.Checkbutton(
            auto_emotional_frame, 
            text="자동 게시 활성화", 
            variable=self.emotional_auto_var,
            command=self.toggle_emotional_auto
        )
        self.emotional_auto_checkbox.pack(side=tk.LEFT, padx=5)

        # 수집 간격
        interval_frame = ttk.Frame(emotional_settings_frame)
        interval_frame.pack(fill=tk.X, pady=2)
        ttk.Label(interval_frame, text="게시 간격(분):").pack(side=tk.LEFT, padx=5)

        self.emotional_interval_var = tk.StringVar(value="30")  # 기본값 30분
        vcmd = (self.parent.register(validate_numeric_input), '%P')
        ttk.Spinbox(
            interval_frame, 
            from_=15,  # 최소 15분
            to=1440,   # 최대 24시간
            width=5, 
            textvariable=self.emotional_interval_var,
            validate="key", 
            validatecommand=vcmd
        ).pack(side=tk.LEFT, padx=5)

        # 경고 메시지 추가
        warning_label = ttk.Label(interval_frame, 
                                text="최소 15분 권장",
                                foreground="red")
        warning_label.pack(side=tk.LEFT, padx=5)

        # 쓰레드 갯수 설정 - 새로 추가된 부분
        threads_count_frame = ttk.Frame(emotional_settings_frame)
        threads_count_frame.pack(fill=tk.X, pady=2)
        ttk.Label(threads_count_frame, text="쓰레드 갯수:").pack(side=tk.LEFT, padx=5)

        self.threads_count_var = tk.StringVar(value="3")  # 기본값 3개
        ttk.Spinbox(
            threads_count_frame, 
            from_=1, 
            to=5,      # 최대 5개로 제한
            width=5, 
            textvariable=self.threads_count_var,
            validate="key", 
            validatecommand=vcmd
        ).pack(side=tk.LEFT, padx=5)

        ttk.Label(threads_count_frame, text="(최대 5개)").pack(side=tk.LEFT, padx=5)

        # 최대 항목 수
        max_items_frame = ttk.Frame(emotional_settings_frame)
        max_items_frame.pack(fill=tk.X, pady=2)
        ttk.Label(max_items_frame, text="최대 게시물 수:").pack(side=tk.LEFT, padx=5)
        self.emotional_max_posts_var = tk.StringVar(value="5")  # 기본값 5개
        ttk.Spinbox(
            max_items_frame, 
            from_=1, 
            to=20, 
            width=5, 
            textvariable=self.emotional_max_posts_var,
            validate="key", 
            validatecommand=vcmd
        ).pack(side=tk.LEFT, padx=5)
        ttk.Label(max_items_frame, text="(한 번에 처리할 항목 수)").pack(side=tk.LEFT, padx=5)

        # 자동화 상태 표시
        status_frame = ttk.Frame(emotional_settings_frame)
        status_frame.pack(fill=tk.X, pady=2)
        ttk.Label(status_frame, text="자동화 상태:").pack(side=tk.LEFT, padx=5)
        self.emotional_status_var = tk.StringVar(value="비활성화됨")
        ttk.Label(status_frame, textvariable=self.emotional_status_var).pack(side=tk.LEFT, padx=5)

        # 다음 실행 시간
        next_frame = ttk.Frame(emotional_settings_frame)
        next_frame.pack(fill=tk.X, pady=2)
        ttk.Label(next_frame, text="다음 실행 예정:").pack(side=tk.LEFT, padx=5)
        self.emotional_next_run_var = tk.StringVar(value="없음")
        ttk.Label(next_frame, textvariable=self.emotional_next_run_var).pack(side=tk.LEFT, padx=5)

        # 버튼 프레임
        emotional_button_frame = ttk.Frame(self.emotional_frame)
        emotional_button_frame.pack(fill=tk.X, pady=5)

        # 테스트 버튼 - [쓰레드 채우기]
        self.fill_threads_button = ttk.Button(
            emotional_button_frame,
            text="쓰레드 채우기",
            style="TButton",
            command=self.fill_threads_test
        )
        self.fill_threads_button.pack(side=tk.LEFT, padx=5)

        # 감성 자동화 버튼 - 초기에는 비활성화
        self.emotional_auto_button = ttk.Button(
            emotional_button_frame,
            text="감성 자동화 시작",
            style="Green.TButton",
            command=self.toggle_emotional_auto,
            state="disabled"  # 초기에는 비활성화
        )
        self.emotional_auto_button.pack(side=tk.LEFT, padx=5)

        # 감성 선택 포스팅 버튼 - 초기에는 비활성화
        self.emotional_post_button = ttk.Button(
            emotional_button_frame,
            text="감성 선택 포스팅",
            style="TButton",
            command=self.emotional_single_post,
            state="disabled"  # 초기에는 비활성화
        )
        self.emotional_post_button.pack(side=tk.LEFT, padx=5)

        # 초기 상태에서는 자동화 관련 UI 요소 비활성화
        self.emotional_auto_checkbox.config(state="disabled")
        
        # 데이터 미리보기 섹션 - 공통으로 사용
        threads_preview_frame = ttk.LabelFrame(self.main_frame, text="데이터 미리보기")
        threads_preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 트리뷰 생성 및 설정
        tree_frame = ttk.Frame(threads_preview_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 스크롤바 생성
        tree_y_scroll = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tree_x_scroll = ttk.Scrollbar(tree_frame, orient="horizontal")
        tree_x_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        # 트리뷰 생성 및 스크롤바 연결
        self.threads_data_tree = ttk.Treeview(tree_frame, 
                                    columns=("선택", "카테고리", "게시물 제목", "복사링크", "수집날짜", "이미지", "500자 요약", "포스팅 상태", "포스팅 날짜",
                                            "쓰레드1", "쓰레드2", "쓰레드3", "쓰레드4", "쓰레드5", "생성 여부"),
                                    yscrollcommand=tree_y_scroll.set, 
                                    xscrollcommand=tree_x_scroll.set, 
                                    height=6,
                                    selectmode="extended")
                                    
        tree_y_scroll.config(command=self.threads_data_tree.yview)
        tree_x_scroll.config(command=self.threads_data_tree.xview)

        # 트리뷰 컬럼 설정
        self.threads_data_tree.heading("#0", text="인덱스")
        self.threads_data_tree.heading("선택", text="선택")
        self.threads_data_tree.heading("카테고리", text="카테고리")
        self.threads_data_tree.heading("게시물 제목", text="게시물 제목")
        self.threads_data_tree.heading("복사링크", text="복사링크")
        self.threads_data_tree.heading("수집날짜", text="수집 날짜")
        self.threads_data_tree.heading("이미지", text="이미지")
        self.threads_data_tree.heading("500자 요약", text="500자 요약")
        self.threads_data_tree.heading("포스팅 상태", text="포스팅 상태")
        self.threads_data_tree.heading("포스팅 날짜", text="포스팅 날짜")
        self.threads_data_tree.heading("쓰레드1", text="쓰레드1")
        self.threads_data_tree.heading("쓰레드2", text="쓰레드2")
        self.threads_data_tree.heading("쓰레드3", text="쓰레드3")
        self.threads_data_tree.heading("쓰레드4", text="쓰레드4")
        self.threads_data_tree.heading("쓰레드5", text="쓰레드5")
        self.threads_data_tree.heading("생성 여부", text="생성 여부")

        # 컬럼 너비 설정
        self.threads_data_tree.column("#0", width=50, stretch=tk.NO)
        self.threads_data_tree.column("선택", width=40, stretch=tk.NO)
        self.threads_data_tree.column("카테고리", width=80, stretch=tk.NO)
        self.threads_data_tree.column("게시물 제목", width=150, stretch=tk.NO)
        self.threads_data_tree.column("복사링크", width=80, stretch=tk.NO)
        self.threads_data_tree.column("수집날짜", width=80, stretch=tk.NO)
        self.threads_data_tree.column("이미지", width=40, stretch=tk.NO)
        self.threads_data_tree.column("500자 요약", width=150, stretch=tk.NO)
        self.threads_data_tree.column("포스팅 상태", width=70, stretch=tk.NO)
        self.threads_data_tree.column("포스팅 날짜", width=120, stretch=tk.NO)
        self.threads_data_tree.column("쓰레드1", width=70, stretch=tk.NO)
        self.threads_data_tree.column("쓰레드2", width=70, stretch=tk.NO)
        self.threads_data_tree.column("쓰레드3", width=70, stretch=tk.NO)
        self.threads_data_tree.column("쓰레드4", width=70, stretch=tk.NO)
        self.threads_data_tree.column("쓰레드5", width=70, stretch=tk.NO)
        self.threads_data_tree.column("생성 여부", width=70, stretch=tk.NO)

        # 트리뷰 행 클릭 이벤트 추가
        self.threads_data_tree.bind("<ButtonRelease-1>", self.toggle_thread_selection)

        # 컬럼 가운데 정렬 설정
        for col in ("카테고리", "복사링크", "수집날짜", "이미지", "포스팅 상태", "포스팅 날짜"):
            self.threads_data_tree.column(col, anchor='center')

        # 트리뷰 배치
        self.threads_data_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 데이터 조작 버튼 프레임
        data_button_frame = ttk.Frame(threads_preview_frame)
        data_button_frame.pack(fill=tk.X, pady=5)

        # 데이터 새로고침 버튼 추가
        ttk.Button(data_button_frame, text="데이터 새로고침", command=self.load_thread_data).pack(side=tk.LEFT, padx=5)
        
        # 초기 데이터 로드
        self.load_thread_data()

    def login_threads(self):
        """Threads 로그인 전용 함수"""
        try:
            # 이미 로그인되어 있는지 확인 - 올바르게 수정
            if self.check_threads_login_status():
                messagebox.showinfo("안내", "이미 Threads에 로그인되어 있습니다.")
                return True
                
            # 프로그레스 창 생성
            progress_window = tk.Toplevel(self.parent)
            progress_window.title("Threads 로그인")
            progress_window.geometry("450x150")
            progress_window.resizable(False, False)
            
            # 프로그레스 라벨
            progress_label = ttk.Label(progress_window, text="Threads 로그인 창을 엽니다...")
            progress_label.pack(pady=10)
            
            # 프로그레스 바
            progress_bar = ttk.Progressbar(progress_window, orient="horizontal", length=400, mode="determinate")
            progress_bar.pack(pady=10)
            progress_bar["value"] = 10
            
            # 상태 라벨
            status_label = ttk.Label(progress_window, text="")
            status_label.pack(pady=5)
            
            # 취소 버튼
            cancel_button = ttk.Button(
                progress_window, 
                text="취소", 
                command=lambda: self.cancel_threads_posting(progress_window)
            )
            cancel_button.pack(pady=5)
            
            # 진행 상황 콜백
            def progress_callback(progress, status_text):
                try:
                    if progress_window.winfo_exists():
                        progress_bar["value"] = progress * 100
                        status_label.config(text=status_text)
                        progress_window.update()
                        
                    # 로그에 상태 기록
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.collect_log_text.insert(tk.END, f"[{timestamp}] {status_text}\n")
                    self.collect_log_text.see(tk.END)
                except Exception as e:
                    self.logger.error(f"프로그레스 콜백 오류: {e}")
            
            # 처리 스레드
            def processing_thread():
                try:
                    # 브라우저 실행 중 표시
                    self.set_threads_running(True)
                    
                    # 브라우저 선행 종료 - 충돌 방지를 위해 먼저 모든 브라우저 종료
                    try:
                        self.close_threads_browser()
                    except Exception as e:
                        self.logger.warning(f"브라우저 사전 종료 중 오류 (무시됨): {e}")
                    
                    time.sleep(2)  # 브라우저 종료 대기
                    
                    # Threads 매니저 초기화 (없으면)
                    if not self.threads_manager:
                        # 데이터 수집이 9222 포트를 사용한다면, Threads는 다른 포트(9400+) 사용
                        base_port = 9400
                        # 데이터 수집 중이면 더 높은 포트 번호 사용
                        if hasattr(self.parent.data_collector, 'collecting') and self.parent.data_collector.collecting:
                            base_port = 9500  # 더 안전한 포트 범위 사용
                        
                        # 헤드리스 모드 변수 접근 수정
                        is_headless = self.threads_headless_var.get() if hasattr(self, 'threads_headless_var') else False
                        
                        self.threads_manager = ThreadsManager(
                            self.base_path, 
                            headless=is_headless,  # 수정된 헤드리스 설정 접근
                            base_debug_port=base_port,
                            db_manager=self.db_manager
                        )
                    
                    # 로그인 시도
                    login_success = self.threads_manager.login(
                        lambda p, s: progress_callback(p, s)  # 진행 상황 콜백
                    )
                    
                    if login_success:
                        # 로그인 상태 확인 및 UI 업데이트
                        self.check_threads_login_status()
                        
                        # 브라우저 종료 처리
                        self.close_threads_browser()
                        
                        # 완료 메시지
                        if progress_window.winfo_exists():
                            progress_callback(1.0, "Threads 로그인 성공")
                            # 2초 후 프로그레스 창 자동 닫기
                            self.parent.after(2000, lambda: self.close_progress_window(progress_window))
                        
                        messagebox.showinfo("성공", "Threads 로그인에 성공했습니다.")
                    else:
                        if progress_window.winfo_exists():
                            progress_callback(1.0, "Threads 로그인 실패")
                            progress_window.destroy()
                        
                        messagebox.showerror("오류", "Threads 로그인에 실패했습니다.")
                    
                except Exception as e:
                    self.logger.error(f"로그인 스레드 오류: {e}")
                    
                    if progress_window.winfo_exists():
                        progress_window.destroy()
                    
                    messagebox.showerror("오류", f"Threads 로그인 중 오류가 발생했습니다: {e}")
                    
                finally:
                    # 실행 중 표시 해제
                    self.set_threads_running(False)
            
            # 취소 상태 초기화
            self.cancel_posting = False
            
            # 스레드 시작
            processing_task = threading.Thread(target=processing_thread)
            processing_task.daemon = True
            processing_task.start()
            
            return True
            
        except Exception as e:
            self.logger.error(f"로그인 시작 중 오류: {e}")
            messagebox.showerror("오류", f"로그인 시작 중 오류가 발생했습니다: {e}")
            self.set_threads_running(False)
            return False

    # [추가] 메시지 옵션 변경 핸들러 추가
    def on_threads_message_change(self, event=None):
        """메시지 옵션 변경 이벤트 처리"""
        selected_index = self.threads_message_combo.current()
        
        # "사용자 정의 입력"이 선택되면 입력 필드를 활성화
        if selected_index == 3:  # 사용자 정의 입력
            self.threads_custom_message_entry.config(state="normal")
        else:
            self.threads_custom_message_entry.config(state="disabled")
        
        # 설정 저장
        self.save_threads_settings()

    def update_headless_mode(self):
        """헤드리스 모드 설정 변경 시 처리"""
        if hasattr(self, 'threads_manager') and self.threads_manager:
            # 기존 매니저의 헤드리스 설정 업데이트
            self.threads_manager.headless = self.threads_headless_var.get()
            self.logger.info(f"Threads 헤드리스 모드 변경: {self.threads_headless_var.get()}")
            
            # 브라우저가 실행 중인 경우에는 알림
            if hasattr(self.threads_manager, 'driver') and self.threads_manager.driver:
                messagebox.showinfo("안내", "헤드리스 모드 변경 사항은 다음 브라우저 실행 시 적용됩니다.")
        
        # 설정 저장
        self.save_threads_settings()

    def check_threads_login_status(self):
        """Threads 로그인 상태 확인 및 UI 업데이트"""
        try:
            # Threads 매니저가 없으면 초기화
            if not self.threads_manager:
                self.threads_manager = ThreadsManager(
                    self.base_path, 
                    headless=self.threads_headless_var.get(),  # 변경: headless_var → threads_headless_var
                    db_manager=self.db_manager
                )
                    
            # 로그인 상태 확인
            login_status = self.threads_manager.check_login_status()
                
            if login_status:
                # 로그인 상태 업데이트
                self.threads_login_status_var.set("로그인됨")
                self.post_threads_button.config(text="일반 선택 포스팅")
                    
                # 헤드리스 모드 활성화
                self.threads_headless_checkbox.config(state="normal")
                
                # 자동화 UI 요소 활성화
                self.threads_auto_checkbox.config(state="normal")
                self.threads_auto_button.config(state="normal")
                
                # 로그인 버튼 비활성화 (추가)
                if hasattr(self, 'login_button'):
                    self.login_button.config(state="disabled")
                    
                # 최근 로그인 정보를 DB에 저장
                login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.db_manager.update_threads_login_time(login_time)
                    
                # 설정 다시 로드
                self.threads_settings = self.db_manager.load_threads_settings()

                # 설정에 헤드리스 모드 상태 저장
                self.threads_settings["headless_mode"] = self.threads_headless_var.get()  # 변경: headless_var → threads_headless_var
                self.save_threads_settings()
                    
                return True
            else:
                # 미로그인 상태 표시
                self.threads_login_status_var.set("로그인 필요")
                self.post_threads_button.config(text="선택 게시")
                    
                # 헤드리스 모드 비활성화
                self.threads_headless_var.set(False)  # 변경: headless_var → threads_headless_var
                self.threads_headless_checkbox.config(state="disabled")
                
                # 자동화 UI 요소 비활성화
                self.threads_auto_var.set(False)
                self.threads_auto_checkbox.config(state="disabled")
                self.threads_auto_button.config(state="disabled")
                
                # 로그인 버튼 활성화 (추가)
                if hasattr(self, 'login_button'):
                    self.login_button.config(state="normal")
                    
                return False
                    
        except Exception as e:
            self.logger.error(f"Threads 로그인 상태 확인 중 오류: {e}")
            self.threads_login_status_var.set("상태 확인 오류")
            
            # 로그인 버튼 활성화 (추가)
            if hasattr(self, 'login_button'):
                self.login_button.config(state="normal")
                
            return False

    def toggle_thread_selection(self, event):
        """트리뷰 항목 클릭 시 선택 상태 토글"""
        item = self.threads_data_tree.identify_row(event.y)
        column = self.threads_data_tree.identify_column(event.x)
        
        if column == "#1":  # 첫 번째 컬럼(선택)을 클릭한 경우
            if item:
                current_val = self.threads_data_tree.item(item, "values")
                if current_val:
                    # '✓' 또는 '' 토글
                    check_val = '✓' if current_val[0] != '✓' else ''
                    new_vals = (check_val,) + current_val[1:]
                    self.threads_data_tree.item(item, values=new_vals)

    def load_thread_data(self):
        """DB 데이터 로드하여 트리뷰에 표시"""
        try:
            # 기존 데이터 삭제
            try:
                children = self.threads_data_tree.get_children()
                if children:
                    self.threads_data_tree.delete(*children)
            except Exception as e:
                self.logger.warning(f"트리뷰 초기화 중 오류: {e}")
                
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
                
                # 트리뷰에 데이터 추가
                try:
                    self.threads_data_tree.insert("", tk.END, text=str(idx+1), 
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
                    
            self.logger.info(f"Threads 탭에 {len(news_items)}개 항목을 로드했습니다.")
            
        except Exception as e:
            self.logger.error(f"Threads 탭 데이터 로드 오류: {e}")

        # 마지막 행 이후에 추가
        self.logger.info(f"Threads 탭에 {len(news_items)}개 항목을 로드했습니다.")

        # 저장된 열 너비 복원
        self.restore_thread_column_widths()

    # threads_module.py 파일의 single_post_to_threads 함수 전체
    def single_post_to_threads(self):
        """선택 게시 기능 - 다중 선택 지원"""
        try:
            # 선택된 항목 확인 - 체크박스 선택 항목으로 변경 ('✓' 체크된 것 우선)
            checked_items = []
            
            # 체크박스 선택된 항목 찾기 (Threads 탭)
            for item in self.threads_data_tree.get_children():
                values = self.threads_data_tree.item(item, "values")
                if values and values[0] == '✓':  # 체크박스 선택된 항목
                    index = int(self.threads_data_tree.item(item, "text")) - 1
                    checked_items.append((index, item))
            
            # 체크박스 선택된 항목 찾기 (데이터 수집 탭)
            data_tree = self.parent.data_collector.data_tree
            for item in data_tree.get_children():
                values = data_tree.item(item, "values")
                if values and values[0] == '✓':  # 체크박스 선택된 항목
                    index = int(data_tree.item(item, "text")) - 1
                    checked_items.append((index, item))
                        
            # 체크박스 선택 항목이 없으면 트리뷰 선택 항목 확인
            if not checked_items:
                # 선택된 항목 확인 (트리뷰 선택)
                selected_items_data = self.parent.data_collector.data_tree.selection()
                selected_items_threads = self.threads_data_tree.selection()
                
                # 어느 탭에서 선택했는지 확인
                if selected_items_threads:
                    for item in selected_items_threads:
                        index = int(self.threads_data_tree.item(item, "text")) - 1
                        checked_items.append((index, item))
                elif selected_items_data:
                    for item in selected_items_data:
                        index = int(data_tree.item(item, "text")) - 1
                        checked_items.append((index, item))
            
            # 선택된 항목 없음
            if not checked_items:
                messagebox.showinfo("알림", "게시할 항목을 선택해주세요.")
                return
                    
            # 수정된 코드:
            if self.check_collector_running():
                # 로그 기록만 남기고 경고 메시지 없이 진행
                self.logger.info("데이터 수집 중이지만, 다른 포트/PID를 사용하므로 진행합니다.")
                    
            # Threads 작업 중 표시
            self.set_threads_running(True)
                
            # 로그 출력 (디버그)
            self.logger.info(f"선택된 항목 수: {len(checked_items)}")
            
            # 전체 뉴스 아이템 가져오기
            news_items = self.db_manager.get_news_items()
            
            # 선택된 항목들의 데이터 가져오기
            items_to_post = []
            for index, _ in checked_items:
                if 0 <= index < len(news_items):
                    items_to_post.append(news_items[index])
                    self.logger.info(f"게시 대상 항목 ID: {news_items[index].get('id')}")
            
            if not items_to_post:
                messagebox.showinfo("알림", "게시할 유효한 항목이 없습니다.")
                self.set_threads_running(False)
                return
            
            # 게시물 개수 알림
            if len(items_to_post) > 1:
                # 자동화 모드에서는 확인 없이 진행
                if hasattr(self, 'auto_mode') and self.auto_mode:
                    self.logger.info(f"자동화 모드: 총 {len(items_to_post)}개 항목을 Threads에 게시합니다.")
                else:
                    # 수동 모드에서만 확인 대화상자 표시
                    if not messagebox.askyesno("확인", f"총 {len(items_to_post)}개 항목을 Threads에 게시하려고 합니다. 계속하시겠습니까?"):
                        self.set_threads_running(False)
                        return
            
            # 프로그레스 창 생성 (자동화 모드에서는 생성하지 않음)
            progress_window = None
            if not (hasattr(self, 'auto_mode') and self.auto_mode):
                progress_window = tk.Toplevel(self.parent)
                progress_window.title("Threads 다중 게시")  # 제목 변경
                progress_window.geometry("450x150")
                progress_window.resizable(False, False)
                
                # 프로그레스 라벨
                progress_label = ttk.Label(progress_window, text="Threads 로그인 확인 중...")
                progress_label.pack(pady=10)
                
                # 프로그레스 바
                progress_bar = ttk.Progressbar(progress_window, orient="horizontal", length=400, mode="determinate")
                progress_bar.pack(pady=10)
                progress_bar["value"] = 10
                
                # 상태 라벨
                status_label = ttk.Label(progress_window, text="")
                status_label.pack(pady=5)
                
                # 취소 버튼
                cancel_button = ttk.Button(
                    progress_window, 
                    text="취소", 
                    command=lambda: self.cancel_threads_posting(progress_window)
                )
                cancel_button.pack(pady=5)
            
            # 진행 상황 콜백
            def progress_callback(progress, status_text):
                try:
                    # 자동화 모드가 아닐 때만 GUI 업데이트
                    if progress_window and progress_window.winfo_exists():
                        progress_bar["value"] = progress * 100
                        status_label.config(text=status_text)
                        progress_window.update()
                        
                    # 로그에 상태 기록
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.collect_log_text.insert(tk.END, f"[{timestamp}] {status_text}\n")
                    self.collect_log_text.see(tk.END)
                except Exception as e:
                    self.logger.error(f"프로그레스 콜백 오류: {e}")
            
            # 처리 스레드
            def processing_thread():
                try:
                    # Threads 매니저 초기화 (없으면)
                    if not self.threads_manager:
                        # 데이터 수집이 9222 포트를 사용한다면, Threads는 다른 포트(9400+) 사용
                        base_port = 9400
                        # 데이터 수집 중이면 더 높은 포트 번호 사용
                        if hasattr(self.parent.data_collector, 'collecting') and self.parent.data_collector.collecting:
                            base_port = 9500  # 더 안전한 포트 범위 사용
                        
                        self.threads_manager = ThreadsManager(
                            self.base_path, 
                            headless=self.threads_headless_var.get(),  # 헤드리스 설정 적용
                            base_debug_port=base_port,
                            db_manager=self.db_manager
                        )
                    else:
                        # 이미 존재하는 매니저의 헤드리스 설정 업데이트
                        self.threads_manager.headless = self.threads_headless_var.get()
                        self.logger.info(f"Threads 매니저 헤드리스 모드 설정: {self.threads_headless_var.get()}")
                    
                    # 로그인 상태 확인
                    login_status = self.check_threads_login_status()
                    
                    if not login_status:
                        progress_callback(0.2, "Threads 로그인 필요. 브라우저를 실행합니다...")
                        
                        # 브라우저 선행 종료 - 충돌 방지를 위해 먼저 모든 브라우저 종료
                        try:
                            self.close_threads_browser()
                        except Exception as e:
                            self.logger.warning(f"브라우저 사전 종료 중 오류 (무시됨): {e}")
                        
                        time.sleep(2)  # 브라우저 종료 대기
                        
                        # 로그인 시도
                        login_success = self.threads_manager.login(
                            lambda p, s: progress_callback(p * 0.4, s)  # 로그인은 전체 진행의 40%
                        )
                        
                        if not login_success:
                            progress_callback(1.0, "Threads 로그인 실패")
                            if progress_window and progress_window.winfo_exists():
                                progress_window.destroy()
                            # 자동화 모드에서는 메시지 박스 표시하지 않음
                            if not (hasattr(self, 'auto_mode') and self.auto_mode):
                                messagebox.showerror("오류", "Threads 로그인에 실패했습니다.")
                            self.set_threads_running(False)
                            return
                        
                        # UI 상태 업데이트
                        login_status = self.check_threads_login_status()
                    else:
                        progress_callback(0.4, "이미 로그인되어 있습니다. 게시를 진행합니다...")
                    
                    # 로그인 성공 후 자동화 UI 요소 활성화
                    if login_status:
                        self.threads_auto_checkbox.config(state="normal")
                        self.threads_auto_button.config(state="normal")
                        
                    # 로그인 후 게시 작업 실행
                    total_items = len(items_to_post)
                    success_count = 0
                    fail_count = 0
                    
                    # 진행 중 취소 확인 플래그
                    if not hasattr(self, 'cancel_posting'):
                        self.cancel_posting = False
                        
                    self.logger.info(f"총 {total_items}개 항목 게시 시작")
                    
                    # 현재 선택된 메시지 옵션 가져오기
                    selected_index = self.threads_message_combo.current()
                    message_options = self.threads_message_combo["values"]
                    
                    if selected_index == 3:  # 사용자 정의 입력
                        custom_message = self.threads_custom_message_entry.get()
                    else:
                        custom_message = message_options[selected_index]
                    
                    # 각 항목 처리
                    for idx, item in enumerate(items_to_post):
                        # 취소 확인
                        if self.cancel_posting:
                            self.logger.info("사용자에 의해 게시 작업이 취소되었습니다.")
                            break
                        
                        if progress_window and progress_window.winfo_exists():
                            pass
                        elif not (hasattr(self, 'auto_mode') and self.auto_mode):
                            self.logger.info("게시 작업이 사용자에 의해 취소되었습니다.")
                            break
                        
                        try:
                            # 항목 정보 추출
                            item_id = item.get("id")
                            title = item.get("게시물 제목", "")
                            image_path = item.get("이미지 경로", "")
                            copy_link = item.get("복사링크", "")
                            
                            # 진행 상황 업데이트
                            base_progress = 0.4  # 로그인까지의 진행률
                            item_progress = (idx / total_items) * 0.6  # 게시는 전체 진행의 60%
                            progress = base_progress + item_progress
                            
                            # 명확하게 현재 항목 번호와 총 항목 수 표시
                            progress_callback(progress, f"항목 {idx+1}/{total_items} 게시 중: {title[:30]}...")
                            
                            self.logger.info(f"항목 {idx+1}/{total_items} 처리 시작: ID {item_id}, 제목: {title}")
                            
                            # 게시할 내용: 제목만 사용
                            post_text = title
                            
                            # 제목 뒤에 메시지 옵션 추가 (하나의 줄바꿈만 추가)
                            post_text += "\n" + custom_message
                            
                            # 로그에 실제 입력될 텍스트 표시
                            self.logger.info(f"입력할 원본 텍스트:\n{post_text}")
                            
                            # 실제 이미지 경로 확인
                            if image_path and not os.path.exists(image_path):
                                self.logger.warning(f"이미지 파일이 존재하지 않습니다: {image_path}")
                                image_path = None
                            
                            # 여러 항목이 있을 때 브라우저 종료 방지
                            post_success = self.threads_manager.post_thread(
                                text=post_text,
                                image_path=image_path,
                                reply_link=copy_link,
                                progress_callback=lambda p, s: progress_callback(
                                    base_progress + item_progress + (p * 0.6 / total_items), 
                                    f"항목 {idx+1}/{total_items}: {s}"
                                ),
                                close_browser=(idx == total_items - 1)  # 마지막 항목인 경우에만 브라우저 종료
                            )
                            
                            # 결과 업데이트
                            if post_success:
                                # 포스팅 상태 업데이트
                                self.db_manager.update_posting_status(
                                    news_id=item_id,
                                    platform_id='threads',
                                    platform_name='Threads',
                                    status='포스팅 완료'
                                )
                                success_count += 1
                                self.logger.info(f"항목 {idx+1}/{total_items} 게시 성공: {title}")
                                
                                # 포스팅 시간 표시를 위해 즉시 데이터 새로고침
                                # 모든 항목을 한번에 처리한 후 마지막에 새로고침 하는 대신
                                # 각 항목이 게시될 때마다 바로 새로고침하여 포스팅 시간이 즉시 표시되도록 함
                                if idx < total_items - 1:  # 마지막 항목이 아닌 경우에만 중간 새로고침
                                    self.parent.data_collector.load_data()
                                    self.load_thread_data()
                            else:
                                fail_count += 1
                                self.logger.error(f"항목 {idx+1}/{total_items} 게시 실패: {title}")
                            
                            # 게시물 간 간격 두기 (5초)
                            if idx < total_items - 1:  # 마지막 항목이 아닌 경우에만
                                progress_callback(progress, f"다음 항목으로 넘어가기 전 대기 중... ({idx+1}/{total_items} 완료)")
                                time.sleep(5)
                            
                        except Exception as e:
                            fail_count += 1
                            self.logger.error(f"항목 {idx+1}/{total_items} 처리 중 오류: {e}")
                    
                    # 모든 항목 처리 후 결과 표시
                    if progress_window and progress_window.winfo_exists():
                        progress_callback(1.0, f"게시 완료: 성공 {success_count}, 실패 {fail_count}")
                        
                        # 로그에 결과 기록
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        self.collect_log_text.insert(tk.END, f"[{timestamp}] Threads 게시 완료: 성공 {success_count}, 실패 {fail_count}\n")
                        self.collect_log_text.see(tk.END)
                        
                        # 모든 항목 처리 완료 후 브라우저 종료
                        self.close_threads_browser()
                        
                        # 2초 후 팝업창 자동 닫기
                        self.parent.after(2000, lambda: self.close_progress_window(progress_window))
                    
                    # 완료 메시지 표시
                    if not (hasattr(self, 'auto_mode') and self.auto_mode):
                        messagebox.showinfo("완료", f"Threads 게시 결과:\n성공: {success_count}\n실패: {fail_count}")
                    else:
                        # 자동화 모드에서는 로그만 남김
                        self.logger.info(f"자동화 모드: Threads 게시 완료: 성공 {success_count}, 실패 {fail_count}")
                    
                    # 데이터 새로고침
                    self.parent.data_collector.load_data()
                    self.load_thread_data()
                    
                    # 작업 중 표시 해제
                    self.set_threads_running(False)
                    
                except Exception as e:
                    self.logger.error(f"Threads 게시 스레드 오류: {e}")
                    
                    if progress_window and progress_window.winfo_exists():
                        # 브라우저 종료 시도
                        self.close_threads_browser()
                        progress_window.destroy()
                    
                    # 자동화 모드가 아닐 때만 메시지 박스 표시
                    if not (hasattr(self, 'auto_mode') and self.auto_mode):
                        messagebox.showerror("오류", f"Threads 게시 중 오류가 발생했습니다: {e}")
                    else:
                        self.logger.error(f"자동화 모드: Threads 게시 중 오류 발생: {e}")
                    
                    # 작업 중 표시 해제
                    self.set_threads_running(False)
            
            # 취소 상태 초기화
            self.cancel_posting = False
            
            # 스레드 시작
            processing_task = threading.Thread(target=processing_thread)
            processing_task.daemon = True
            processing_task.start()
            
        except Exception as e:
            self.logger.error(f"단일 게시 시작 중 오류: {e}")
            self.set_threads_running(False)
            messagebox.showerror("오류", f"처리 중 오류가 발생했습니다: {e}")

    def cancel_threads_posting(self, progress_window):
        """Threads 게시 취소 처리"""
        try:
            # 취소 확인
            if messagebox.askyesno("확인", "정말로 게시 작업을 취소하시겠습니까?"):
                # 취소 플래그 설정
                self.cancel_posting = True
                
                # 브라우저 종료
                self.close_threads_browser()
                
                # 팝업창 닫기
                if progress_window and progress_window.winfo_exists():
                    progress_window.destroy()
                    
                # 로그 기록
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.collect_log_text.insert(tk.END, f"[{timestamp}] Threads 게시 작업이 취소되었습니다.\n")
                self.collect_log_text.see(tk.END)
                
                self.logger.info("Threads 게시 작업이 취소되었습니다.")
        except Exception as e:
            self.logger.error(f"게시 취소 중 오류: {e}")

    def close_threads_browser(self):
        """Threads 브라우저 종료 - 안전하게 개선"""
        try:
            if hasattr(self, 'threads_manager') and self.threads_manager:
                # PID/포트 정보가 없어도 안전하게 호출할 수 있도록 수정
                try:
                    self.threads_manager.kill_browser()
                    self.logger.info("Threads 브라우저가 종료되었습니다.")
                    return True
                except Exception as e:
                    # 에러 메시지 개선
                    self.logger.warning(f"Threads 브라우저 종료 중 문제 발생: {e}")
                    
                    # PID나 포트 정보가 없는 경우 대안적인 방법으로 종료 시도
                    import psutil
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            if 'chrome' in proc.info['name'].lower() or 'chromium' in proc.info['name'].lower():
                                # 프로세스 이름에 'threadsTEMP'가 있는지 확인
                                cmdline = ' '.join(proc.cmdline())
                                if 'threadsTEMP' in cmdline or 'threads_manager' in cmdline:
                                    proc.terminate()
                                    self.logger.info(f"Threads 관련 브라우저 프로세스 종료: {proc.info['pid']}")
                        except:
                            continue
                    
                    return True
            else:
                self.logger.info("Threads 매니저가 초기화되지 않았습니다.")
            return False
        except Exception as e:
            self.logger.error(f"Threads 브라우저 종료 중 오류: {e}")
            return False

    def close_progress_window(self, window):
        """진행 팝업창 종료"""
        try:
            if window and window.winfo_exists():
                window.destroy()
                self.logger.info("게시 진행 창이 닫혔습니다.")
        except Exception as e:
            self.logger.error(f"진행 창 종료 중 오류: {e}")
    
    def toggle_threads_auto(self):
        """Threads 자동 게시 토글 - 통합 스케줄러 사용"""
        current_state = self.threads_auto_var.get()
        
        if current_state:  # 활성화 -> 비활성화
            # 기존 예약 작업 제거
            self.parent.remove_scheduled_tasks("threads_module")
            self.threads_auto_var.set(False)
            self.threads_status_var.set("비활성화됨")
            self.threads_next_run_var.set("없음")
            self.threads_auto_button.config(text="일반 자동화 시작", style="Green.TButton")  # 버튼 텍스트 변경
            
            # 타이머 관련 변수 초기화
            self.threads_next_run_time = None
            self.threads_last_run_time = None
            
            # 로그에 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] Threads 자동 게시가 중지되었습니다.\n")
            self.collect_log_text.see(tk.END)
            
            self.logger.info("Threads 자동 게시가 중지되었습니다.")
        else:  # 비활성화 -> 활성화
            # 로그인 상태 확인
            if not self.check_threads_login_status():
                messagebox.showwarning("경고", "자동화를 시작하기 전에 Threads에 로그인하세요.")
                # 체크박스 상태 복원
                self.threads_auto_var.set(False)
                return
                        
            # 게시 간격 검증
            try:
                post_interval = int(self.threads_interval_var.get())
                if post_interval < 15:
                    # 15분 미만인 경우 경고 표시만 하고 진행
                    messagebox.showwarning("경고", "게시 간격이 15분 미만입니다. 계정에 불이익이 발생할 수 있습니다. 그래도 진행하시겠습니까?")
                    # 사용자가 OK 버튼을 누르면 계속 진행
                elif post_interval <= 0:
                    # 0 이하인 경우는 오류 처리
                    messagebox.showerror("오류", "게시 간격은 최소 1분 이상이어야 합니다.")
                    self.threads_interval_var.set("1")
                    # 체크박스 상태 복원
                    self.threads_auto_var.set(False)
                    return
            except ValueError:
                messagebox.showwarning("경고", "유효한 게시 간격을 입력하세요.")
                # 체크박스 상태 복원
                self.threads_auto_var.set(False)
                return
            
            # 활성화 처리
            self.threads_auto_var.set(True)
            self.threads_status_var.set("활성화됨")
            self.threads_auto_button.config(text="일반 자동화 중지", style="Red.TButton")  # 버튼 텍스트 변경
            
            # 시간 정보 설정
            now = datetime.now()
            self.threads_last_run_time = now
            self.threads_next_run_time = now + timedelta(minutes=post_interval)
            
            # 카운트다운 표시 업데이트
            self.threads_next_run_var.set(f"{post_interval}분 후 (예정: {self.threads_next_run_time.strftime('%H:%M')})")
            
            # 로그에 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] Threads 자동 게시가 시작되었습니다. 게시 간격: {post_interval}분\n")
            self.collect_log_text.see(tk.END)
            
            self.logger.info(f"Threads 자동 게시가 시작되었습니다. 게시 간격: {post_interval}분")
            
            # 통합 스케줄러에 작업 추가
            self.parent.add_scheduled_task("threads_module", self.threads_next_run_time, self.run_auto_threads_posting)
        
        # 설정 저장
        self.save_threads_settings()

    def save_thread_column_widths(self):
        """트리뷰 열 너비 설정 저장"""
        column_widths = {}
        # 모든 열의 현재 너비 가져오기
        for col in self.threads_data_tree["columns"] + ("#0",):
            width = self.threads_data_tree.column(col, "width")
            column_widths[col] = width
        
        # 설정에 열 너비 저장
        threads_settings = self.db_manager.load_threads_settings()
        threads_settings["column_widths"] = column_widths
        self.db_manager.save_threads_settings(threads_settings)

    def restore_thread_column_widths(self):
        """저장된 트리뷰 열 너비 복원"""
        threads_settings = self.db_manager.load_threads_settings()
        if "column_widths" in threads_settings:
            column_widths = threads_settings["column_widths"]
            for col, width in column_widths.items():
                try:
                    # 저장된 너비로 열 설정
                    self.threads_data_tree.column(col, width=width)
                except:
                    pass

    def save_threads_settings(self):
        """Threads 설정 저장"""
        try:
            # 현재 UI 상태에서 설정값 가져오기
            settings = {
                "auto_post": self.threads_auto_var.get(),
                "post_interval": int(self.threads_interval_var.get()),
                "max_posts_per_run": int(self.threads_max_posts_var.get()),
                "account_name": self.threads_settings.get("account_name", ""),
                "login_time": self.threads_settings.get("login_time", ""),
                "headless_mode": self.threads_headless_var.get(),  # 헤드리스 모드 설정 추가
                # 메시지 옵션 설정 추가
                "message_option_index": self.threads_message_combo.current(),
                "custom_message": self.threads_custom_message_entry.get() if self.threads_message_combo.current() == 3 else ""
            }
            
            # DB에 설정 저장
            self.db_manager.save_threads_settings(settings)
            
            # 설정 객체 업데이트
            self.threads_settings = settings
            
            # ThreadsManager의 헤드리스 설정도 함께 업데이트
            if hasattr(self, 'threads_manager') and self.threads_manager:
                self.threads_manager.headless = settings["headless_mode"]
            
            self.logger.info("Threads 설정이 저장되었습니다.")
            return True
        except Exception as e:
            self.logger.error(f"Threads 설정 저장 중 오류: {e}")
            return False
    
    def start_threads_scheduler(self):
        """Threads 자동화 스케줄러 시작"""
        if hasattr(self, 'threads_auto_scheduler') and self.threads_auto_scheduler:
            self.logger.info("Threads 스케줄러가 이미 실행 중입니다.")
            return
        
        # 스케줄러 스레드 시작
        self.threads_auto_scheduler = threading.Thread(
            target=self._threads_scheduler_loop, 
            daemon=True
        )
        self.threads_auto_scheduler.start()
        
        self.logger.info("Threads 자동화 스케줄러 시작")
    
    def stop_threads_scheduler(self):
        """Threads 자동화 스케줄러 중지 - 안전하게 종료"""
        if hasattr(self, 'threads_auto_scheduler') and self.threads_auto_scheduler:
            self.logger.info("Threads 자동화 스케줄러 중지")
            
            # 스케줄러 종료 플래그 설정
            self.threads_auto_var.set(False)
            
            # 스케줄러 루프 종료 플래그 설정
            if hasattr(self, '_scheduler_running'):
                self._scheduler_running = False
            
            # 스레드가 종료될 때까지 잠시 대기 (최대 2초)
            if self.threads_auto_scheduler.is_alive():
                self.threads_auto_scheduler.join(timeout=2)
                
            self.threads_auto_scheduler = None
        else:
            self.logger.info("실행 중인 Threads 스케줄러가 없습니다.")
    
    def _threads_scheduler_loop(self):
        """Threads 자동화 스케줄러 루프 - 성능 최적화 버전"""
        self.logger.info("Threads 자동화 스케줄러 루프 시작")
        
        # 스케줄러 루프가 실행 중임을 표시하는 플래그
        self._scheduler_running = True
        
        while self.threads_auto_var.get() and self._scheduler_running:
            try:
                # 현재 시간
                now = datetime.now()
                
                # 다음 실행 시간이 되었는지 확인
                if self.threads_next_run_time and now >= self.threads_next_run_time and not self.threads_collecting:
                    self.logger.info(f"Threads 자동 게시 시간 도달: {self.threads_next_run_time.strftime('%Y-%m-%d %H:%M')}")
                    
                    # 다음 실행 시간 초기화 (새로운 실행 후 다시 계산하기 위해)
                    self.threads_next_run_time = None
                    
                    # 자동 게시 실행 - 새 스레드에서 실행
                    thread = threading.Thread(target=self.run_auto_threads_posting, daemon=True)
                    thread.start()
                    
                    # 스레드가 시작되고 나면 바로 다음 루프로 진행
                    time.sleep(2)
                    continue
                
                # 다음 실행 시간 카운트다운 업데이트 - 1초마다 하지 않고 5초마다 업데이트
                if hasattr(self, 'threads_next_run_var') and self.threads_next_run_time:
                    remaining = self.threads_next_run_time - now
                    if remaining.total_seconds() > 0:
                        # 남은 시간 계산
                        minutes = int(remaining.total_seconds() // 60)
                        seconds = int(remaining.total_seconds() % 60)
                        
                        # UI 업데이트는 메인 스레드에서 안전하게 처리
                        def update_ui():
                            if hasattr(self, 'threads_next_run_var'):
                                self.threads_next_run_var.set(f"{minutes}분 {seconds}초 후 (예정: {self.threads_next_run_time.strftime('%H:%M')})")
                        
                        # 메인 스레드에서 UI 업데이트 수행
                        if self.parent and hasattr(self.parent, 'after'):
                            self.parent.after(0, update_ui)
                    else:
                        def update_ui_soon():
                            if hasattr(self, 'threads_next_run_var'):
                                self.threads_next_run_var.set("곧 실행")
                        
                        if self.parent and hasattr(self.parent, 'after'):
                            self.parent.after(0, update_ui_soon)
                
                # 부하 감소를 위해 대기 시간 증가 (1초 -> 5초)
                time.sleep(5)
                
            except Exception as e:
                self.logger.error(f"Threads 스케줄러 루프 중 오류: {e}")
                time.sleep(30)  # 에러 발생 시 30초 대기 후 재시도
        
        self._scheduler_running = False
        self.logger.info("Threads 자동화 스케줄러 루프 종료")
    
    # threads_module.py 파일의 run_auto_threads_posting 함수
    def run_auto_threads_posting(self):
        """Threads 자동 게시 실행"""
        if self.threads_collecting:
            self.logger.warning("이미 Threads 게시가 진행 중입니다.")
            return False
                
        # 데이터 수집 중이면 대기
        if self.check_collector_running():
            self.logger.warning("데이터 수집 중이므로 Threads 게시를 연기합니다.")
            # 다음 실행 시간 조정 (5분 후)
            self.threads_next_run_time = datetime.now() + timedelta(minutes=5)
            self.threads_next_run_var.set(f"5분 후 (데이터 수집 중)")
            
            # 로그에 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] 데이터 수집 중이므로 Threads 게시를 5분 후로 연기합니다.\n")
            self.collect_log_text.see(tk.END)
            return False
        
        # Threads 실행 중 표시
        self.set_threads_running(True)
        self.threads_collecting = True
        
        try:
            # 로그에 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] Threads 자동 게시를 시작합니다.\n")
            self.collect_log_text.see(tk.END)
            
            # 로그인 상태 확인
            if not self.check_threads_login_status():
                # 로그인 필요 메시지
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.collect_log_text.insert(tk.END, f"[{timestamp}] Threads 로그인이 필요합니다.\n")
                self.collect_log_text.see(tk.END)
                self.logger.warning("Threads 로그인이 필요합니다.")
                self.threads_collecting = False
                self.set_threads_running(False)
                return False
            
            # 자동화 모드 플래그 설정
            self.auto_mode = True
            
            # 미게시 항목 가져오기
            unposted_items = self.db_manager.get_unposted_items_by_platform('threads')
            
            if not unposted_items:
                self.logger.info("게시할 항목이 없습니다.")
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.collect_log_text.insert(tk.END, f"[{timestamp}] 게시할 항목이 없습니다.\n")
                self.collect_log_text.see(tk.END)
                
                # 다음 실행 시간 설정
                now = datetime.now()
                self.last_collect_time = now
                post_interval = int(self.threads_interval_var.get())
                self.threads_next_run_time = now + timedelta(minutes=post_interval)
                
                # 다음 실행 예약
                if self.threads_auto_var.get() and hasattr(self.parent, 'add_scheduled_task'):
                    self.parent.add_scheduled_task(
                        "threads_module", 
                        self.threads_next_run_time, 
                        self.run_auto_threads_posting
                    )
                
                self.threads_collecting = False
                self.set_threads_running(False)
                self.auto_mode = False
                return True
            
            # 최대 게시물 수 제한
            max_posts = int(self.threads_max_posts_var.get())
            items_to_process = unposted_items[:max_posts]
            
            self.logger.info(f"총 {len(items_to_process)}개 항목 게시 예정")
            
            # 진행 상황 콜백
            def progress_callback(progress, status_text):
                # 로그에 상태 기록
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.collect_log_text.insert(tk.END, f"[{timestamp}] {status_text}\n")
                self.collect_log_text.see(tk.END)
            
            # 성공/실패 카운터
            success_count = 0
            fail_count = 0
            
            # 현재 선택된 메시지 옵션 가져오기
            selected_index = self.threads_message_combo.current()
            message_options = self.threads_message_combo["values"]
            
            if selected_index == 3:  # 사용자 정의 입력
                custom_message = self.threads_custom_message_entry.get()
            else:
                custom_message = message_options[selected_index]
            
            # 각 항목 처리 시 자동화 모드 지정
            for idx, item in enumerate(items_to_process):
                # 항목 정보 추출
                item_id = item.get("id")
                title = item.get("게시물 제목", "")
                image_path = item.get("이미지 경로", "")
                copy_link = item.get("복사링크", "")
                
                # 로깅
                self.logger.info(f"항목 {idx+1}/{len(items_to_process)} 처리 시작: ID {item_id}, 제목: {title}")
                
                # 게시할 내용: 제목만 사용
                post_text = title
                
                # 제목 뒤에 메시지 옵션 추가 (하나의 줄바꿈만 추가)
                post_text += "\n" + custom_message
                
                # 로그에 실제 입력될 텍스트 표시
                self.logger.info(f"입력할 원본 텍스트:\n{post_text}")
                
                # 각 항목마다 새 브라우저 인스턴스 사용
                try:
                    # 기존 브라우저 종료
                    if hasattr(self, 'threads_manager') and self.threads_manager:
                        try:
                            self.threads_manager.kill_browser()
                            time.sleep(2)  # 브라우저 종료 대기
                        except Exception as e:
                            self.logger.warning(f"브라우저 종료 중 오류 (무시됨): {e}")
                    
                    # 새 매니저 생성 (명시적 헤드리스 모드 지정)
                    self.threads_manager = ThreadsManager(
                        self.base_path, 
                        headless=self.threads_headless_var.get(),
                        base_debug_port=9333,  # 명시적 포트 지정
                        db_manager=self.db_manager
                    )
                    
                    # 게시물 작성
                    post_success = self.threads_manager.post_thread(
                        text=post_text,
                        image_path=image_path,
                        reply_link=copy_link,
                        progress_callback=progress_callback,
                        close_browser=True  # 항상 브라우저 종료
                    )
                    
                    # 결과 처리
                    if post_success:
                        # 포스팅 상태 업데이트
                        self.db_manager.update_posting_status(
                            news_id=item_id,
                            platform_id='threads',
                            platform_name='Threads',
                            status='포스팅 완료'
                        )
                        success_count += 1
                        self.logger.info(f"항목 {idx+1}/{len(items_to_process)} 게시 성공: {title}")
                        
                        # 데이터 새로고침
                        self.parent.data_collector.load_data()
                        self.load_thread_data()
                    else:
                        fail_count += 1
                        self.logger.error(f"항목 {idx+1}/{len(items_to_process)} 게시 실패: {title}")
                    
                    # 다음 항목 처리 전 대기 (마지막 항목이 아닌 경우)
                    if idx < len(items_to_process) - 1:
                        time.sleep(10)
                        
                except Exception as e:
                    fail_count += 1
                    self.logger.error(f"항목 {idx+1} 처리 중 오류: {e}")
                    
                    # 오류 발생 시 브라우저 정리
                    try:
                        if hasattr(self, 'threads_manager') and self.threads_manager:
                            self.threads_manager.kill_browser()
                    except:
                        pass
            
            # 다음 실행 시간 설정
            now = datetime.now()
            self.last_collect_time = now
            post_interval = int(self.threads_interval_var.get())
            self.threads_next_run_time = now + timedelta(minutes=post_interval)
            
            # 결과 로깅
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result_msg = f"Threads 자동 게시 완료: 성공 {success_count}, 실패 {fail_count}. 다음 실행: {self.threads_next_run_time.strftime('%H:%M')}"
            self.collect_log_text.insert(tk.END, f"[{timestamp}] {result_msg}\n")
            self.collect_log_text.see(tk.END)
            self.logger.info(result_msg)
            
            # 데이터 새로고침
            self.parent.data_collector.load_data()
            self.load_thread_data()
            
            # 다음 실행 예약
            if self.threads_auto_var.get() and hasattr(self.parent, 'add_scheduled_task'):
                self.parent.add_scheduled_task(
                    "threads_module", 
                    self.threads_next_run_time, 
                    self.run_auto_threads_posting
                )
            
            # 자동화 모드 플래그 해제
            self.auto_mode = False
            
            return True
                
        except Exception as e:
            self.logger.error(f"Threads 자동 게시 중 오류: {e}")
            
            # 로그에 기록
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.collect_log_text.insert(tk.END, f"[{timestamp}] Threads 자동 게시 중 오류: {str(e)}\n")
            self.collect_log_text.see(tk.END)
            
            # 자동화 모드 플래그 해제
            self.auto_mode = False
            
            return False
        finally:
            self.threads_collecting = False
            self.set_threads_running(False)

    # threads_module.py 파일 ThreadsUI 클래스에 추가할 함수들
    def check_collector_running(self):
        """데이터 수집 프로세스가 실행 중인지 확인 - 브라우저 관리 개선으로 충돌 걱정 없음"""
        lock_path = os.path.join(self.base_path, "data", "DB", self.DATA_COLLECTOR_LOCK_FILE)
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
            self.logger.info("데이터 수집이 실행 중이지만, 다른 포트/PID를 사용하므로 충돌 위험 없음")
            return False  # False 반환하여 경고 대화 상자 표시 안 함
        return False

    def set_threads_running(self, running=True):
        """Threads 작업 상태 설정"""
        lock_path = os.path.join(self.base_path, "data", "DB", self.THREADS_LOCK_FILE)
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

    def update_threads_countdown(self):
        """Threads 카운트다운 업데이트 - 분과 초 단위로 표시"""
        try:
            if hasattr(self, 'threads_next_run_var') and hasattr(self, 'threads_next_run_time') and self.threads_next_run_time:
                # 현재 시간
                now = datetime.now()
                
                # 다음 실행 시간과의 차이 계산
                remaining = self.threads_next_run_time - now
                if remaining.total_seconds() > 0:
                    # 남은 시간 계산
                    minutes = int(remaining.total_seconds() // 60)
                    seconds = int(remaining.total_seconds() % 60)
                    
                    # 표시할 텍스트 생성
                    update_text = f"{minutes}분 {seconds}초 후 (예정: {self.threads_next_run_time.strftime('%H:%M')})"
                    
                    # 필요한 경우에만 UI 업데이트
                    self.threads_next_run_var.set(update_text)
                else:
                    self.threads_next_run_var.set("곧 실행")
            else:
                # 자동화가 비활성화된 경우
                if hasattr(self, 'threads_auto_var') and not self.threads_auto_var.get():
                    self.threads_next_run_var.set("없음")
        except Exception as e:
            # 오류 무시
            pass
        
        # 5초마다 업데이트
        self.parent.after(5000, self.update_threads_countdown)

    def cleanup(self):
        """리소스 정리 - 개선된 버전"""
        # 자동화 중지
        if hasattr(self, 'threads_auto_var') and self.threads_auto_var.get():
            self.stop_threads_scheduler()
        
        # Threads 매니저 정리
        if hasattr(self, 'threads_manager') and self.threads_manager:
            try:
                self.threads_manager.kill_browser()
                self.logger.info("Threads 브라우저 종료됨")
            except Exception as e:
                self.logger.warning(f"Threads 브라우저 종료 중 오류 (무시됨): {e}")
        
        # 열 너비 설정 저장 - 이 줄 추가
        self.save_thread_column_widths()
        
        # 설정 저장
        self.save_threads_settings()
        
        # 작업 중 표시 해제
        self.set_threads_running(False)
        
        # 임시 파일 정리
        try:
            if hasattr(self, 'threads_manager') and self.threads_manager:
                if hasattr(self.threads_manager, 'cleanup_temp_directories'):
                    self.threads_manager.cleanup_temp_directories()
        except Exception as e:
            self.logger.warning(f"임시 파일 정리 중 오류: {e}")
        
        # 스케줄러 스레드 정리
        if hasattr(self, 'threads_auto_scheduler') and self.threads_auto_scheduler:
            if hasattr(self, '_scheduler_running'):
                self._scheduler_running = False
                
            # 10초 이상 실행 중인 경우에만 로깅
            if self.threads_auto_scheduler.is_alive():
                self.logger.info("Threads 스케줄러 스레드 종료 대기 중...")
                self.threads_auto_scheduler.join(timeout=1)
        
        self.logger.info("Threads UI 리소스 정리 완료")