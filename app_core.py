import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import logging
from datetime import datetime
import threading
import time
import json  # API 상태 확인에 필요

# 구매자 정보 - 여기만 수정하면 됩니다
BUYER_NAME = "김크몽"  # 여기에 구매자 이름을 입력하세요

# 자체 모듈 임포트
from db_manager import DatabaseManager
from data_collector import DataCollectorUI
from threads_module import ThreadsUI
from api_manager import APIManagerUI  # 추가된 부분
from ui_components import setup_logging, LogTextHandler

class NewspickCollectorApp(tk.Tk):
    """뉴스픽 데이터 수집 프로그램 메인 클래스"""

    def __init__(self):
        super().__init__()
        
        # 구매자 이름이 있으면 제목에 포함, 없으면 기본 제목만 사용
        if BUYER_NAME:
            self.title(f"뉴스픽 데이터 수집 & 쓰레드 자동 포스팅 프로그램 - 크몽 {BUYER_NAME}님")
        else:
            self.title("뉴스픽 데이터 수집 & 쓰레드 자동 포스팅 프로그램")
            
        self.geometry("1000x900")
        
        # 여기서부터는 기존 코드 그대로 유지
        # 종료 이벤트 처리
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 기본 경로 및 로깅 설정
        self.base_path = self.get_base_path()
        self.logger = setup_logging(self.base_path)
        
        # 다른 인스턴스 실행 확인
        self.check_instance_running()
        
        # 이전 실행에서 남은 임시 디렉토리 정리 (새로 추가)
        self.cleanup_previous_temp_directories()
        
        # 필요한 디렉토리 생성
        self.create_required_directories()
        
        # 데이터베이스 매니저 초기화
        self.db_manager = DatabaseManager(self.base_path)

        # 쓰레드 열 업데이트 - 이 줄 추가
        self.db_manager.update_database_for_thread_columns()
        
        # 통합 스케줄러 초기화
        self.scheduled_tasks = []
        self.scheduler_running = True
        self.unified_scheduler_thread = threading.Thread(target=self._unified_scheduler_loop, daemon=True)
        self.unified_scheduler_thread.start()
        
        # 기본 UI 구성요소 생성 (탭 포함)
        self.create_main_frame()
        
        # 모듈별 UI 초기화
        self.data_collector = DataCollectorUI(self)
        self.threads_ui = ThreadsUI(self)
        self.api_manager = APIManagerUI(self)  # api_tab 생성 후에 호출되어야 함
        
        # 초기 데이터 로드
        self.data_collector.load_data()
        
        self.logger.info("프로그램이 시작되었습니다.")

    def get_base_path(self):
        """실행 경로 반환"""
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def check_instance_running(self):
        """다른 인스턴스 실행 확인 및 제한 (파일 락 사용)"""
        import os
        import tempfile
        
        # Windows에서만 msvcrt 사용
        if os.name == 'nt':
            import msvcrt
        else:  # Linux/macOS인 경우에만 fcntl 가져오기
            import fcntl
        
        # 락 파일 경로 (고유 이름 사용)
        lock_file_path = os.path.join(tempfile.gettempdir(), "newspick_collector_instance.lock")
        
        try:
            # 락 파일 생성 또는 열기
            self.lock_file = open(lock_file_path, 'w')
            
            # 운영체제별 락 획득 시도
            if os.name == 'nt':  # Windows
                try:
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    return True
                except IOError:
                    self.lock_file.close()
                    messagebox.showwarning("경고", "이 프로그램은 이미 실행 중입니다.")
                    sys.exit(0)
            else:  # Linux, macOS
                try:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return True
                except IOError:
                    self.lock_file.close()
                    messagebox.showwarning("경고", "이 프로그램은 이미 실행 중입니다.")
                    sys.exit(0)
        
        except Exception as e:
            self.logger.error(f"인스턴스 체크 중 오류: {e}")
            return True

    def create_required_directories(self):
        """필요한 디렉토리 생성"""
        dirs = [
            os.path.join(self.base_path, "data"),
            os.path.join(self.base_path, "data", "DB"),
            os.path.join(self.base_path, "data", "logs"),
            os.path.join(self.base_path, "data", "images"),
            os.path.join(self.base_path, "data", "api"),  # 추가된 부분
            os.path.join(self.base_path, "win", "TEMP", "chromeTEMP1"),
            os.path.join(self.base_path, "win", "TEMP", "threadsTEMP")
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
            self.logger.debug(f"디렉토리 확인/생성: {d}")

    def _unified_scheduler_loop(self):
        """통합 스케줄러 루프 - 모든 자동화 작업 관리"""
        while self.scheduler_running:
            try:
                now = datetime.now()
                
                # 각 예약된 작업 확인
                tasks_to_remove = []
                
                for i, (module, next_run_time, task_func) in enumerate(self.scheduled_tasks):
                    if next_run_time and now >= next_run_time:
                        # 실행할 작업 인덱스 저장
                        tasks_to_remove.append(i)
                        
                        # 작업 시작
                        self.logger.info(f"{module} 예약 작업 시작 ({next_run_time.strftime('%H:%M:%S')})")
                        threading.Thread(target=task_func, daemon=True).start()
                
                # 실행한 작업 제거 (뒤에서부터 제거해야 인덱스가 꼬이지 않음)
                for i in sorted(tasks_to_remove, reverse=True):
                    try:
                        self.scheduled_tasks.pop(i)
                    except IndexError:
                        pass
                
                # 5초마다 확인 (CPU 부하 감소)
                time.sleep(5)
                
            except Exception as e:
                self.logger.error(f"통합 스케줄러 오류: {e}")
                time.sleep(30)  # 오류 발생 시 30초 대기

    def add_scheduled_task(self, module_name, next_run_time, task_func):
        """스케줄러에 작업 추가"""
        self.scheduled_tasks.append((module_name, next_run_time, task_func))
        self.logger.info(f"{module_name} 작업이 {next_run_time.strftime('%H:%M:%S')}에 실행되도록 예약됨")

    def remove_scheduled_tasks(self, module_name):
        """모듈 관련 예약 작업 제거"""
        self.scheduled_tasks = [task for task in self.scheduled_tasks if task[0] != module_name]
        self.logger.info(f"{module_name} 관련 예약 작업이 모두 제거됨")

    def create_main_frame(self):
        """메인 프레임과 탭 생성"""
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 탭 인터페이스 생성
        self.tab_control = ttk.Notebook(self.main_frame)
        
        # 각 탭 생성
        self.data_tab = ttk.Frame(self.tab_control)
        self.threads_tab = ttk.Frame(self.tab_control)
        self.api_tab = ttk.Frame(self.tab_control)  # 추가된 부분
        
        # 탭 추가
        self.tab_control.add(self.data_tab, text="데이터 수집")
        self.tab_control.add(self.threads_tab, text="Threads SNS")
        self.tab_control.add(self.api_tab, text="API 관리")  # 추가된 부분
        
        # 탭 변경 이벤트 바인딩 추가
        self.tab_control.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
        # 탭 컨트롤 배치
        self.tab_control.pack(fill=tk.BOTH, expand=True)
        
        # 스타일 설정
        style = ttk.Style()
        style.configure("TButton", foreground="black")
        style.configure("Green.TButton", foreground="green")
        style.configure("Red.TButton", foreground="red")

    def on_tab_changed(self, event):
        """탭 변경 이벤트 핸들러 - API 상태 업데이트"""
        # 현재 선택된 탭 인덱스 가져오기
        current_tab = self.tab_control.index("current")
        
        # API 탭에서 다른 탭으로 변경된 경우 API 상태 업데이트
        if hasattr(self, 'previous_tab') and self.previous_tab == 2:  # API 탭 인덱스 = 2
            # 데이터 수집 탭의 API 상태 업데이트
            if hasattr(self, 'data_collector') and hasattr(self.data_collector, 'check_api_status'):
                self.data_collector.check_api_status()
        
        # 현재 탭 인덱스 저장
        self.previous_tab = current_tab

    # app_core.py
    def on_closing(self):
        """프로그램 종료 시 처리"""
        if messagebox.askokcancel("종료", "프로그램을 종료하시겠습니까?"):
            # 스케줄러 종료
            self.scheduler_running = False
            if hasattr(self, 'unified_scheduler_thread') and self.unified_scheduler_thread:
                try:
                    self.unified_scheduler_thread.join(timeout=2)
                except:
                    pass
            
            # 모듈별 정리 작업 수행
            self.data_collector.cleanup()
            self.threads_ui.cleanup()
            if hasattr(self, 'api_manager'):
                self.api_manager.cleanup()  # 추가된 부분, 조건부 체크 추가
            
            # 실행 중인 모든 브라우저 프로세스 정리 (추가)
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT pid, port, module_name FROM browser_processes")
            for browser in cursor.fetchall():
                pid, port, module_name = browser
                # 브라우저 종료 함수 호출
                # 어느 모듈의 함수를 호출할지 결정
                if module_name == "newspick_collector":
                    self.data_collector.kill_browser(pid=pid, port=port)
                elif module_name == "threads_manager":
                    self.threads_ui.kill_browser(pid=pid, port=port)
            
            # 브라우저 프로세스 테이블 비우기
            cursor.execute("DELETE FROM browser_processes")
            conn.commit()
            
            # 데이터베이스 연결 종료
            if hasattr(self, 'db_manager'):
                self.db_manager.close_connection()
            
            # 종료 로그
            self.logger.info("프로그램이 종료되었습니다.")
            
            # UI 종료
            self.destroy()
    
    def setup_unified_scheduler(self):
        """통합 스케줄러 설정 - 모든 자동화 기능을 하나의 스케줄러에서 관리"""
        self.unified_scheduler_thread = None
        self.scheduler_running = False
        self.scheduled_tasks = []  # (모듈, 시간, 함수) 형태의 튜플 리스트
        
        # 스케줄러 시작
        def start_unified_scheduler():
            self.scheduler_running = True
            scheduler_thread = threading.Thread(target=self._unified_scheduler_loop, daemon=True)
            scheduler_thread.start()
            self.unified_scheduler_thread = scheduler_thread
            self.logger.info("통합 스케줄러 시작됨")
        
        # 최초 실행 시 바로 시작
        start_unified_scheduler()

    def cleanup_temp_directories(self):
        """불필요한 임시 디렉토리 정리 (chromeTEMP1과 threadsTEMP만 유지)"""
        import shutil
        import glob
        
        try:
            temp_base = os.path.join(self.base_path, "win", "TEMP")
            
            # 보존할 디렉토리들
            keep_dirs = [
                os.path.join(temp_base, "chromeTEMP1"),
                os.path.join(temp_base, "threadsTEMP")
            ]
            
            # 디렉토리가 없으면 생성
            for dir_path in keep_dirs:
                os.makedirs(dir_path, exist_ok=True)
            
            # 나머지 임시 디렉토리 삭제
            for dir_path in glob.glob(os.path.join(temp_base, "*")):
                if os.path.isdir(dir_path) and dir_path not in keep_dirs:
                    try:
                        shutil.rmtree(dir_path)
                        self.logger.info(f"불필요한 임시 디렉토리 삭제: {dir_path}")
                    except Exception as e:
                        self.logger.warning(f"디렉토리 삭제 중 오류 (무시됨): {dir_path} - {e}")
        except Exception as e:
            self.logger.error(f"임시 디렉토리 정리 중 오류: {e}")

    # app_core.py 파일에 이 메서드 추가
    def cleanup_previous_temp_directories(self):
        """이전 실행에서 남은 임시 디렉토리 정리"""
        import shutil
        import glob
        
        try:
            temp_base = os.path.join(self.base_path, "win", "TEMP")
            self.logger.info(f"이전 실행에서 남은 임시 디렉토리 정리 시작: {temp_base}")
            
            # 보존할 디렉토리
            preserved_dirs = [
                os.path.join(temp_base, "chromeTEMP1"),
                os.path.join(temp_base, "threadsTEMP")
            ]
            
            # 디렉토리가 없으면 생성
            for dir_path in preserved_dirs:
                os.makedirs(dir_path, exist_ok=True)
            
            # 나머지 임시 디렉토리 삭제
            for dir_path in glob.glob(os.path.join(temp_base, "*")):
                if os.path.isdir(dir_path) and dir_path not in preserved_dirs:
                    try:
                        shutil.rmtree(dir_path)
                        self.logger.info(f"불필요한 임시 디렉토리 삭제: {dir_path}")
                    except Exception as e:
                        self.logger.warning(f"디렉토리 삭제 중 오류 (무시됨): {dir_path} - {e}")
        except Exception as e:
            self.logger.error(f"임시 디렉토리 정리 중 오류: {e}")

def main():
    """메인 함수"""
    app = NewspickCollectorApp()
    app.mainloop()

if __name__ == "__main__":
    main()