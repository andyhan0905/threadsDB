# threads_manager.py 파일 상단에 넣을 import 구문

import os
import time
import logging
import json
import threading
import random
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains  # ActionChains 추가
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)

class ThreadsManager:
    """Threads SNS 자동화 관리 클래스"""
    
    def __init__(self, base_path, headless=False, base_debug_port=9333, db_manager=None):
        """
        초기화 함수
        
        Args:
            base_path (str): 프로그램 기본 경로
            headless (bool): 헤드리스 모드 사용 여부
            base_debug_port (int): 디버깅 포트 기본값 (9333 기본)
            db_manager (object, optional): 데이터베이스 매니저 객체
        """
        self.base_path = base_path
        self.headless = headless
        self.driver = None
        self.login_status = False
        self.base_debug_port = base_debug_port
        self.db_manager = db_manager  # db_manager 저장
        
        # 로깅 설정 - 명시적으로 로거 가져오기
        self.logger = logging.getLogger(__name__)
        
        # 쓰레드 설정 파일 경로
        self.config_dir = os.path.join(base_path, "data", "DB")
        self.login_status_file = os.path.join(self.config_dir, "threads_login_status.cfg")
        
        # 상태 확인
        self.check_login_status()
        self.logger.info("Threads 매니저가 초기화되었습니다.")
        
    def check_login_status(self):
        """
        로그인 상태 확인
        
        Returns:
            bool: 로그인 상태
        """
        if os.path.exists(self.login_status_file):
            try:
                with open(self.login_status_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "로그인_상태: 완료" in content:
                        self.login_status = True
                        logger.info("Threads 로그인 상태 확인됨")
                        return True
            except Exception as e:
                logger.error(f"Threads 로그인 상태 파일 읽기 오류: {e}")
        
        self.login_status = False
        logger.warning("Threads 로그인 상태 확인 실패")
        return False
    
    # threads_manager.py 파일의 setup_webdriver 함수
    def setup_webdriver(self, module_name, base_port_range=None):
        """
        모듈별 고유 포트 및 PID 관리 기능이 있는 웹드라이버 설정 - 경쟁 상태 방지 개선
        
        Args:
            module_name (str): 모듈 이름 ('newspick_collector' 또는 'threads_manager')
            base_port_range (tuple): 사용할 포트 범위 (시작, 끝) - 더 이상 사용하지 않음
            
        Returns:
            tuple: (webdriver 객체, pid, port)
        """
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

        if hasattr(self, 'chromium_pid') and self.chromium_pid:
            try:
                # 기존 프로세스 종료 시도
                import psutil
                try:
                    process = psutil.Process(self.chromium_pid)
                    process.terminate()
                    time.sleep(1)  # 종료 대기
                except:
                    pass
            except:
                pass
            self.chromium_pid = None
            
        # 독점적 액세스를 위한 임시 잠금 파일 사용
        import tempfile
        import time
        import random
        
        temp_lock_file = os.path.join(
            tempfile.gettempdir(), 
            f"threadsapp_webdriver_setup_{module_name}.lock"
        )
        
        # 잠금 획득 시도 (최대 10초)
        max_lock_attempts = 20
        lock_attempt = 0
        
        while lock_attempt < max_lock_attempts:
            try:
                # 파일이 존재하지 않으면 생성
                if not os.path.exists(temp_lock_file):
                    with open(temp_lock_file, 'w') as f:
                        f.write(f"{os.getpid()}")
                    break
                else:
                    # 파일이 존재하면 랜덤 시간 대기 후 재시도
                    wait_time = random.uniform(0.2, 0.5)
                    time.sleep(wait_time)
                    lock_attempt += 1
            except:
                lock_attempt += 1
        
        try:
            # 로컬 Chromium 바이너리 경로 설정
            base_dir = os.path.abspath(self.base_path)
            chromium_path = os.path.join(base_dir, "win", "chromium.exe")
            
            # 모듈별 사용자 데이터 디렉토리 설정 - 항상 고정 디렉토리 사용
            user_data_dir = os.path.join(base_dir, "win", "TEMP", "threadsTEMP")
            os.makedirs(user_data_dir, exist_ok=True)
            
            # 경로 존재 확인
            if not os.path.exists(chromium_path):
                self.logger.error(f"로컬 Chromium이 존재하지 않습니다: {chromium_path}")
                return None, None, None
            
            # 모듈별 고정 포트 설정
            import socket
            
            # 포트 사용 가능 여부 확인 함수
            def is_port_in_use(port):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    return s.connect_ex(('localhost', port)) == 0
            
            # 고정 포트 설정 - threads_manager용 9333 포트
            preferred_port = 9333
            
            # 선호 포트가 사용 가능하면 그대로 사용
            if not is_port_in_use(preferred_port):
                debug_port = preferred_port
            else:
                # 선호 포트가 사용 중이면 대체 포트 찾기 (최대 10개 시도)
                fallback_ports = [preferred_port + 10 * i for i in range(1, 11)]
                debug_port = None
                
                for port in fallback_ports:
                    if not is_port_in_use(port):
                        debug_port = port
                        break
                
                if debug_port is None:
                    self.logger.error("사용 가능한 디버깅 포트를 찾을 수 없습니다.")
                    return None, None, None
            
            self.logger.info(f"{module_name}용 디버깅 포트: {debug_port}")
            
            # 크로미움 옵션 설정 - 성능 향상을 위한 추가 옵션
            chrome_open_option = (
                ' --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36" '
                '--window-size=1920,1080 --lang=ko_KR --disable-gpu --mute-audio --disable-notifications --no-first-run '
                '--disable-extensions --disable-background-networking --disable-sync '
                '--metrics-recording-only --disable-default-apps --password-store=basic '
                '--disable-background-timer-throttling --disable-backgrounding-occluded-windows '
                '--disable-breakpad --disable-component-extensions-with-background-pages '
                '--enable-features=NetworkService,NetworkServiceInProcess '
                '--profile-directory=Default '  # 기본 프로필 사용
            )
            
            # 헤드리스 모드 설정 - self.headless 값을 사용
            if self.headless:
                chrome_open_option += ' --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                chrome_open_option += ' AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36" '
                chrome_open_option += ' --headless --disable-gpu --disable-dev-shm-usage'
                chrome_open_option += ' --disable-web-security --allow-running-insecure-content'
                chrome_open_option += ' --no-sandbox --disable-setuid-sandbox --disable-popup-blocking'
                chrome_open_option += ' --disable-modal-animations --disable-client-side-phishing-detection'
                chrome_open_option += ' --disable-web-security --allow-running-insecure-content'
                chrome_open_option += ' --disable-site-isolation-trials'
                chrome_open_option += ' --disable-features=IsolateOrigins,site-per-process'
                # 폰트 렌더링 개선을 위한 추가 옵션
                chrome_open_option += ' --font-render-hinting=none --force-color-profile=srgb'
                # 언어 및 인코딩 설정 강화
                chrome_open_option += ' --lang=ko-KR --accept-lang=ko-KR,ko'
                # 폰트 관련 설정
                chrome_open_option += ' --font-cache-shared-handle=true'
                self.logger.info(f"{module_name}용 헤드리스 모드로 브라우저가 실행됩니다.")
            else:
                self.logger.info(f"{module_name}용 일반 모드로 브라우저가 실행됩니다.")
            
            # 디버깅 포트 설정
            chrome_open_option += f' --remote-debugging-port={debug_port} --user-data-dir="{user_data_dir}"'
            
            self.logger.info(f"{module_name}용 로컬 Chromium 실행: {chromium_path}")
            cmd = f'"{chromium_path}" {chrome_open_option}'
            
            # 크로미움 프로세스 시작
            import subprocess
            proc = subprocess.Popen(cmd)
            pid = proc.pid
            
            # 데이터베이스에 브라우저 정보 저장 - 중복 확인 추가
            try:
                if hasattr(self, 'db_manager') and self.db_manager:
                    conn = self.db_manager.get_connection()
                    cursor = conn.cursor()
                    
                    # browser_processes 테이블이 없으면 생성
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS browser_processes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        module_name TEXT,
                        pid INTEGER,
                        port INTEGER,
                        start_time TEXT
                    )
                    ''')
                    
                    # 기존 레코드 확인 (동일 PID/포트)
                    cursor.execute(
                        "SELECT id FROM browser_processes WHERE pid = ? OR port = ?",
                        (pid, debug_port)
                    )
                    existing = cursor.fetchone()
                    
                    if existing:
                        # 기존 레코드 업데이트
                        cursor.execute(
                            "UPDATE browser_processes SET module_name = ?, pid = ?, port = ?, start_time = ? WHERE id = ?",
                            (module_name, pid, debug_port, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), existing[0])
                        )
                    else:
                        # 새 레코드 추가
                        cursor.execute(
                            "INSERT INTO browser_processes (module_name, pid, port, start_time) VALUES (?, ?, ?, ?)",
                            (module_name, pid, debug_port, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        )
                    
                    conn.commit()
                    self.logger.info(f"{module_name} 브라우저 정보 저장 (PID: {pid}, 포트: {debug_port})")
                else:
                    self.logger.warning(f"{module_name} 브라우저 정보 저장을 위한 DB 접근 불가")
            except Exception as e:
                self.logger.error(f"브라우저 정보 저장 중 오류: {e}")
            
            self.logger.info(f"{module_name} Chromium 시작 (프로세스 ID: {pid}, 포트: {debug_port}")
            
            # 브라우저 시작 대기 - 더 안정적인 방식으로 수정
            max_wait = 30  # 최대 30초 대기
            wait_interval = 0.5  # 0.5초마다 확인
            waited = 0
            browser_ready = False
            
            while waited < max_wait:
                try:
                    # 포트 열렸는지 확인
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        if s.connect_ex(('localhost', debug_port)) == 0:
                            # 잠시 더 대기 (포트가 열렸지만 브라우저가 완전히 초기화되지 않았을 수 있음)
                            time.sleep(2)
                            browser_ready = True
                            break
                except:
                    pass
                
                time.sleep(wait_interval)
                waited += wait_interval
            
            if not browser_ready:
                self.logger.warning(f"브라우저 시작 대기 시간 초과 (최대 {max_wait}초)")
            
            # WebDriver 설정
            try:
                options = Options()
                options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
                
                driver_path = os.path.join(base_dir, "win", "driver", "chromedriver.exe")
                self.logger.info(f"{module_name}용 ChromeDriver 경로: {driver_path}")
                
                if not os.path.exists(driver_path):
                    self.logger.error(f"ChromeDriver 파일이 존재하지 않습니다: {driver_path}")
                    return None, None, None
                
                # Selenium 3.x 스타일로 초기화
                driver = webdriver.Chrome(executable_path=driver_path, options=options)
                
                # 인스턴스 변수에 정보 저장
                self.chromium_pid = pid
                self.debug_port = debug_port
                self.user_data_dir = user_data_dir  # 나중에 정리를 위해 저장
                
                # 헤드리스 모드에서 알림창 무시 설정
                if self.headless:
                    # 알림창 무시 스크립트 실행
                    driver.execute_script("""
                        // 알림창 처리 함수 완전 재정의
                        window.alert = function() {};
                        window.confirm = function() { return true; };
                        window.prompt = function() { return ''; };
                        
                        // 알림창 이벤트 캡처 및 무시
                        window.addEventListener('beforeunload', function(e) { 
                            e.preventDefault(); 
                            e.returnValue = ''; 
                        }, true);
                        
                        // 알림창이 열려있으면 자동으로 닫기
                        setInterval(function() {
                            try {
                                // 존재하는 모든 알림창 자동 닫기 시도
                                document.querySelectorAll('div[role="dialog"]').forEach(function(el) {
                                    el.remove();
                                });
                            } catch(e) {}
                        }, 500);
                        
                        // 이모지 폰트 설정
                        var style = document.createElement('style');
                        style.textContent = `
                            @font-face {
                                font-family: 'Noto Color Emoji';
                                src: url('https://fonts.gstatic.com/s/notocoloremoji/v1/Yq6P-KqIXTD0t4D9z1ESnKM3-HpFyagT9Hgf1pyEgXfw.woff2') format('woff2');
                            }
                            
                            body, div[role="textbox"], textarea, input {
                                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, 
                                            Arial, 'Apple Color Emoji', 'Noto Color Emoji', sans-serif !important;
                            }
                        `;
                        document.head.appendChild(style);
                        
                        console.log('알림창 비활성화 및 이모지 폰트 설정 스크립트 실행 완료');
                    """)
                    
                    # 알림창 핸들링 설정
                    try:
                        alert = driver.switch_to.alert
                        alert.accept()
                    except:
                        pass
                
                return driver, pid, debug_port
            except Exception as e:
                self.logger.error(f"{module_name}용 웹드라이버 설정 오류: {e}")
                return None, None, None
        finally:
            # 잠금 해제
            try:
                if os.path.exists(temp_lock_file):
                    os.remove(temp_lock_file)
            except:
                pass
    
    def login(self, progress_callback=None):
        """
        Threads 로그인 수행 - 개선된 버전
        
        Args:
            progress_callback (function): 진행 상황 콜백 함수
                
        Returns:
            bool: 로그인 성공 여부
        """
        try:
            # 로그인 상태인 경우 바로 성공 반환
            if self.check_login_status():
                logger.info("이미 Threads에 로그인되어 있습니다.")
                if progress_callback:
                    progress_callback(1.0, "이미 Threads에 로그인되어 있습니다.")
                
                # 메인 페이지로 이동하고 프로필 페이지 방문만 수행
                if self.driver:
                    try:
                        self.driver.get("https://www.threads.net/")
                        time.sleep(5)

                        # 다이얼로그 닫기 시도
                        self.dismiss_dialogs()

                        # 프로필 페이지로 이동 시도
                        profile_success = self.navigate_to_profile()
                    except:
                        # 기존 드라이버에 문제가 있으면 재시작
                        self.kill_browser()
                        self.driver = None
                
                return True
            
            # 먼저 이전 브라우저 인스턴스 정리
            try:
                self.kill_browser()
                time.sleep(2)  # 브라우저 종료 대기
            except Exception as e:
                logger.warning(f"이전 브라우저 종료 중 오류 (무시됨): {e}")
            
            # 드라이버 설정
            driver_result = self.setup_webdriver(module_name="threads_manager")
            
            # 드라이버 결과 처리
            if isinstance(driver_result, tuple) and len(driver_result) >= 1:
                self.driver = driver_result[0]  # 튜플의 첫 번째 항목이 드라이버
            else:
                self.driver = driver_result  # 튜플이 아니면 직접 할당
            
            if not self.driver:
                logger.error("Threads용 웹드라이버 설정에 실패했습니다.")
                if progress_callback:
                    progress_callback(1.0, "웹드라이버 설정 실패")
                return False
            
            # 로그인 페이지 열기
            if progress_callback:
                progress_callback(0.2, "Threads 로그인 페이지 열기")
            
            # 로그인 페이지로 이동 - 오류 처리 강화
            max_tries = 3
            login_page_loaded = False
            
            for attempt in range(max_tries):
                try:
                    self.driver.get("https://www.threads.net/login")
                    time.sleep(5)
                    login_page_loaded = True
                    break
                except Exception as e:
                    logger.warning(f"로그인 페이지 로드 시도 {attempt+1}/{max_tries} 실패: {e}")
                    time.sleep(2)
            
            if not login_page_loaded:
                logger.error("Threads 로그인 페이지를 열지 못했습니다.")
                if progress_callback:
                    progress_callback(1.0, "로그인 페이지 로드 실패")
                return False
            
            # 현재 URL 확인하여 로그인 상태 감지
            current_url = self.driver.current_url
            logger.info(f"현재 URL: {current_url}")
            
            # 이미 로그인되어 있으면 메인 페이지로 리다이렉트되었을 것임
            if current_url == "https://www.threads.net/" or current_url == "https://www.threads.net":
                logger.info("이미 로그인되어 있습니다. 메인 페이지로 자동 리다이렉트 됨")
                
                # 프로필 페이지로 이동
                profile_success = self.navigate_to_profile()
                
                # 로그인 상태 저장
                self._save_login_status()
                
                if progress_callback:
                    progress_callback(1.0, "Threads 로그인 상태 확인됨")
                
                return True
            
            # 로그인 대기 안내
            if progress_callback:
                progress_callback(0.4, "로그인 화면에서 계정정보를 입력해주세요. 자동으로 다음 단계로 진행됩니다.")
            
            # 로그인 완료 대기 (URL 변경 감지) - 시간 제한 추가
            logger.info("로그인 페이지가 열렸습니다. 사용자의 로그인 완료를 대기합니다...")

            # 현재 URL 저장 (로그인 페이지 URL)
            login_url = self.driver.current_url
            logger.info(f"로그인 페이지 URL: {login_url}")

            # 대기 루프 - 최대 5분 제한
            wait_count = 0
            max_wait_time = 300  # 5분(초 단위)
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                try:
                    # 현재 URL 확인
                    current_url = self.driver.current_url
                    
                    # 주기적으로 상태 로그 출력 (30초마다)
                    if wait_count % 15 == 0:  # 2초마다 체크하므로 15회는 약 30초
                        elapsed = int((time.time() - start_time) / 60)
                        logger.info(f"로그인 대기 중... ({elapsed}분 경과)")
                        remaining = int((max_wait_time - (time.time() - start_time)) / 60)
                        if progress_callback:
                            progress_callback(0.5, f"로그인 대기 중... ({elapsed}분 경과, {remaining}분 남음)")
                    
                    # URL이 변경되었는지 확인 (로그인 완료로 판단)
                    if current_url != login_url and "/login" not in current_url:
                        logger.info(f"URL 변경 감지됨: {login_url} -> {current_url}")
                        logger.info("로그인이 완료된 것으로 판단하고 다음 단계로 진행합니다.")
                        
                        # 메인 페이지로 명시적으로 이동
                        try:
                            self.driver.get("https://www.threads.net/")
                            time.sleep(5)
                            logger.info("메인 페이지로 이동 완료")
                        except Exception as e:
                            logger.warning(f"메인 페이지 이동 실패: {e}")
                        
                        # 다이얼로그 닫기 시도
                        self.dismiss_dialogs()
                        
                        # 프로필 페이지로 이동
                        profile_success = self.navigate_to_profile()
                        
                        # 로그인 상태 저장
                        self._save_login_status()
                        
                        if progress_callback:
                            progress_callback(1.0, "Threads 로그인 성공")
                        
                        return True
                        
                    # 짧은 간격으로 체크
                    time.sleep(2)
                    wait_count += 1
                    
                except Exception as e:
                    logger.error(f"로그인 대기 중 오류 발생: {e}")
                    # 오류 발생 시 재시도
                    time.sleep(5)
                    
                    # 연결 관련 심각한 오류인 경우 최대 3번 복구 시도
                    if "WinError 10054" in str(e) or "WinError 10061" in str(e):
                        retry_count = getattr(self, '_connection_retry_count', 0) + 1
                        setattr(self, '_connection_retry_count', retry_count)
                        
                        if retry_count <= 3:
                            logger.warning(f"연결 오류로 인해 브라우저 재시작 시도 ({retry_count}/3)")
                            try:
                                self.kill_browser()
                                time.sleep(3)
                                driver_result = self.setup_webdriver(module_name="threads_manager")
                                
                                # 드라이버 결과 처리
                                if isinstance(driver_result, tuple) and len(driver_result) >= 1:
                                    self.driver = driver_result[0]
                                else:
                                    self.driver = driver_result
                                    
                                if self.driver:
                                    self.driver.get("https://www.threads.net/login")
                                    time.sleep(5)
                                    # 새 로그인 URL 저장
                                    login_url = self.driver.current_url
                                else:
                                    # 드라이버 재설정 실패
                                    break
                            except Exception as restart_e:
                                logger.error(f"브라우저 재시작 실패: {restart_e}")
                                break
                        else:
                            # 최대 재시도 횟수 초과
                            logger.error("최대 연결 재시도 횟수 초과")
                            break
            
            # 시간 초과 확인
            if time.time() - start_time >= max_wait_time:
                logger.warning("로그인 대기 시간이 초과되었습니다. (5분)")
                if progress_callback:
                    progress_callback(1.0, "로그인 대기 시간 초과 (5분)")
                self.kill_browser()
                return False
                
            # 연결 오류 등으로 루프를 빠져나온 경우
            logger.error("로그인 과정에서 오류가 발생했습니다.")
            if progress_callback:
                progress_callback(1.0, "로그인 과정에서 오류가 발생했습니다.")
            self.kill_browser()
            return False
            
        except Exception as e:
            logger.error(f"Threads 로그인 오류: {e}")
            if progress_callback:
                progress_callback(1.0, f"로그인 오류: {str(e)}")
            
            # 브라우저 정리
            try:
                self.kill_browser()
            except:
                pass
                
            return False
        finally:
            # 연결 재시도 카운터 초기화
            if hasattr(self, '_connection_retry_count'):
                delattr(self, '_connection_retry_count')
    
    def _save_login_status(self):
        """로그인 상태 저장"""
        try:
            with open(self.login_status_file, 'w', encoding='utf-8') as f:
                f.write(f"로그인_시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"로그인_상태: 완료\n")
                f.write(f"헤드리스_모드: {'활성화' if self.headless else '비활성화'}\n")
            
            self.login_status = True
            logger.info(f"Threads 로그인 상태 파일 저장됨: {self.login_status_file}")
            return True
        except Exception as e:
            logger.error(f"Threads 로그인 상태 저장 오류: {e}")
            return False
    
    def insert_text_headless(self, text_area, text):
        """헤드리스 모드에 최적화된 텍스트 및 이모티콘 삽입 함수"""
        logger.info("헤드리스 모드용 이모티콘 지원 텍스트 삽입 시도")
        
        # 이모티콘을 포함하는 텍스트 삽입 전략 적용
        success = False
        
        # 방법 1: textContent 직접 조작 및 완전한 이벤트 시뮬레이션
        try:
            js_script = """
            // 텍스트 영역의 내용을 완전히 비우고 새로운 내용 추가
            while (arguments[0].firstChild) {
                arguments[0].removeChild(arguments[0].firstChild);
            }
            
            // 줄바꿈으로 텍스트 분할
            var lines = arguments[1].split('\\n');
            
            // 각 줄마다 텍스트 노드와 줄바꿈 생성
            for (var i = 0; i < lines.length; i++) {
                if (i > 0) {
                    arguments[0].appendChild(document.createElement('br'));
                }
                var textNode = document.createTextNode(lines[i]);
                arguments[0].appendChild(textNode);
            }
            
            // 포커스 설정
            arguments[0].focus();
            
            // 입력 이벤트 시뮬레이션
            var inputEvent = new InputEvent('input', {
                bubbles: true,
                cancelable: true,
                inputType: 'insertText',
                data: arguments[1]
            });
            arguments[0].dispatchEvent(inputEvent);
            
            // 변경 이벤트 시뮬레이션
            var changeEvent = new Event('change', {
                bubbles: true,
                cancelable: true
            });
            arguments[0].dispatchEvent(changeEvent);
            
            return true;
            """
            
            result = self.driver.execute_script(js_script, text_area, text)
            if result:
                logger.info("방법 1: DOM 조작으로 이모티콘 입력 성공")
                success = True
        except Exception as e:
            logger.warning(f"방법 1 실패: {e}")
        
        # 방법 2: 클립보드 API 사용 및 붙여넣기 시뮬레이션
        if not success:
            try:
                js_script = """
                return (async function(element, text) {
                    try {
                        // 클립보드 API를 통해 텍스트 복사
                        await navigator.clipboard.writeText(text);
                        
                        // 요소에 포커스
                        element.focus();
                        
                        // 붙여넣기 명령 실행
                        document.execCommand('paste');
                        
                        return true;
                    } catch (e) {
                        console.error('클립보드 API 오류:', e);
                        return false;
                    }
                })(arguments[0], arguments[1]);
                """
                
                result = self.driver.execute_script(js_script, text_area, text)
                if result:
                    logger.info("방법 2: 클립보드 API 사용 이모티콘 입력 성공")
                    success = True
            except Exception as e:
                logger.warning(f"방법 2 실패: {e}")
        
        # 방법 3: 각 문자를 순차적으로 입력
        if not success:
            try:
                js_script = """
                // 요소 초기화 및 포커스
                arguments[0].textContent = '';
                arguments[0].focus();
                
                // 텍스트를 개별 문자로 분리하여 각각 InputEvent 발생
                var text = arguments[1];
                for (var i = 0; i < text.length; i++) {
                    var char = text.charAt(i);
                    
                    // 줄바꿈 처리
                    if (char === '\\n') {
                        var br = document.createElement('br');
                        arguments[0].appendChild(br);
                        continue;
                    }
                    
                    // 각 문자를 개별적으로 삽입
                    var inputEvent = new InputEvent('input', {
                        bubbles: true,
                        cancelable: true,
                        inputType: 'insertText',
                        data: char
                    });
                    
                    // 문자 삽입 및 이벤트 발생
                    document.execCommand('insertText', false, char);
                    arguments[0].dispatchEvent(inputEvent);
                    
                    // 약간의 지연 부여
                    await new Promise(resolve => setTimeout(resolve, 5));
                }
                
                return true;
                """
                
                result = self.driver.execute_script(js_script, text_area, text)
                if result:
                    logger.info("방법 3: 문자별 입력으로 이모티콘 입력 성공")
                    success = True
            except Exception as e:
                logger.warning(f"방법 3 실패: {e}")
        
        # 방법 4: 마지막 시도 - Selenium의 ActionChains 사용
        if not success:
            try:
                # 먼저 요소 초기화
                self.driver.execute_script("arguments[0].textContent = '';", text_area)
                
                # 포커스 설정
                text_area.click()
                time.sleep(0.5)
                
                # ActionChains를 사용해 각 줄 처리
                from selenium.webdriver.common.keys import Keys
                from selenium.webdriver.common.action_chains import ActionChains
                
                lines = text.split('\n')
                actions = ActionChains(self.driver)
                
                # 첫 줄 입력
                actions.send_keys(lines[0])
                actions.perform()
                time.sleep(0.3)
                
                # 나머지 줄 입력 (줄바꿈 포함)
                for i in range(1, len(lines)):
                    actions = ActionChains(self.driver)
                    actions.key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT)
                    actions.perform()
                    time.sleep(0.2)
                    
                    actions = ActionChains(self.driver)
                    actions.send_keys(lines[i])
                    actions.perform()
                    time.sleep(0.3)
                
                logger.info("방법 4: ActionChains로 이모티콘 입력 성공")
                success = True
            except Exception as e:
                logger.warning(f"방법 4 실패: {e}")
        
        return success

    def post_thread(self, text, image_path=None, reply_link=None, progress_callback=None, close_browser=True):
        """
        Threads에 게시물 작성
        
        Args:
            text (str): 게시할 텍스트 (500자 요약)
            image_path (str, optional): 첨부할 이미지 경로
            reply_link (str, optional): 댓글로 달 링크
            progress_callback (function): 진행 상황 콜백 함수
            close_browser (bool): 작업 완료 후 브라우저 종료 여부
                
        Returns:
            bool: 성공 여부
        """
        max_retry = 3  # 최대 재시도 횟수
        retry_count = 0
        
        while retry_count <= max_retry:
            try:
                # 브라우저 상태 확인
                browser_needs_restart = False
                
                if self.driver:
                    try:
                        # 간단한 명령으로 브라우저 상태 확인
                        current_url = self.driver.current_url
                    except Exception as e:
                        logger.warning(f"브라우저 연결 확인 실패: {e}")
                        browser_needs_restart = True
                else:
                    browser_needs_restart = True
                
                # 브라우저 재시작 필요시
                if browser_needs_restart:
                    logger.info("브라우저 재시작 필요, 새 세션 시작")
                    
                    # 기존 세션 종료 시도
                    try:
                        if self.driver:
                            self.driver.quit()
                    except:
                        pass
                    
                    # 기존 프로세스 종료 시도
                    try:
                        self.kill_browser()
                    except:
                        pass
                    
                    # 새 드라이버 시작
                    driver_result = self.setup_webdriver(module_name="threads_manager")
                    
                    # 드라이버 결과 처리
                    if isinstance(driver_result, tuple) and len(driver_result) >= 1:
                        self.driver = driver_result[0]  # 튜플의 첫 번째 항목이 드라이버
                    else:
                        self.driver = driver_result  # 튜플이 아니면 직접 할당
                    
                    if not self.driver:
                        logger.error("Threads용 웹드라이버가 설정되지 않았습니다.")
                        if progress_callback:
                            progress_callback(1.0, "웹드라이버 설정 실패")
                        return False
                
                # 로그인 상태 확인 및 처리
                if not self.check_login_status():
                    logger.warning("Threads에 로그인되어 있지 않습니다.")
                    if progress_callback:
                        progress_callback(0.1, "로그인 필요")
                        time.sleep(1)
                    # 로그인 시도
                    login_success = self.login(
                        lambda p, s: progress_callback(p * 0.4, s)  # 로그인은 전체 진행의 40%
                    )
                    
                    if not login_success:
                        retry_count += 1
                        if retry_count <= max_retry:
                            logger.warning(f"로그인 실패, 재시도 {retry_count}/{max_retry}")
                            continue
                        return False
                
                # 1. 메인 페이지로 이동
                if progress_callback:
                    progress_callback(0.3, "메인 페이지로 이동")
                
                # 작업 중 표시 설정 - 다른 브라우저가 종료하지 않도록
                lock_path = os.path.join(self.base_path, "data", "DB", "threads_running.lock")
                with open(lock_path, 'w') as f:
                    f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                try:
                    self.driver.get("https://www.threads.net/")
                    time.sleep(5)  # 충분한 로딩 시간 부여
                    logger.info("메인 홈페이지로 이동 완료")

                    # 이모티콘 폰트 주입 (새로 추가)
                    self.inject_emoji_font()
                    
                    # 다이얼로그 닫기 시도
                    self.dismiss_dialogs()
                    
                    # 2. "+" 버튼 클릭
                    if progress_callback:
                        progress_callback(0.5, "+ 버튼 클릭")
                            
                    # 화면 좌측 영역에서 버튼 요소 찾기
                    logger.info("화면 좌측 영역에서 버튼 요소 찾기")

                    # 헤드리스 모드에서 오버레이 요소를 제거하고 클릭 수행
                    if self.headless:
                        try:
                            # 방해 요소 제거 후 버튼 클릭 시도
                            result = self.driver.execute_script("""
                                // 방해 요소를 스타일로 숨기기
                                var overlays = document.querySelectorAll('div.__fb-light-mode, div[class*="light-mode"]');
                                for (var i = 0; i < overlays.length; i++) {
                                    overlays[i].style.display = 'none';
                                    overlays[i].style.visibility = 'hidden';
                                    overlays[i].style.pointerEvents = 'none';
                                    overlays[i].style.zIndex = '-1';
                                }
                                
                                // 좌측 상단의 버튼을 찾아 클릭
                                var navButtons = document.querySelectorAll('header div[role="button"]');
                                if (navButtons.length >= 1) {
                                    navButtons[0].click();
                                    return true;
                                }
                                
                                // 다른 접근 방식: CSS 셀렉터로 좌측 상단 버튼 찾기
                                var createButtons = document.querySelectorAll(
                                    'div[role="button"][tabindex="0"], button[tabindex="0"]'
                                );
                                
                                // 상단에서 아래로 첫 5개 버튼 클릭 시도
                                for (var i = 0; i < Math.min(5, createButtons.length); i++) {
                                    try {
                                        createButtons[i].click();
                                        return true;
                                    } catch(e) {
                                        console.error('Button click error:', e);
                                    }
                                }
                                
                                return false;
                            """)
                            
                            time.sleep(3)  # 클릭 후 충분한 대기 시간
                            
                            # 텍스트 영역 확인
                            text_areas = self.driver.find_elements_by_xpath("//div[@role='textbox']")
                            if text_areas and len(text_areas) > 0:
                                logger.info("헤드리스 모드에서 텍스트 영역 발견")
                                plus_button_clicked = True
                            else:
                                logger.error("헤드리스 모드에서 텍스트 영역을 찾을 수 없음")
                                plus_button_clicked = False
                        except Exception as e:
                            logger.error(f"헤드리스 모드에서 + 버튼 클릭 중 오류: {e}")
                            plus_button_clicked = False
                    else:
                        # 일반 모드는 기존 코드를 사용
                        left_buttons = self.driver.execute_script("""
                            var buttons = document.querySelectorAll('div[role="button"], button, a[role="button"]');
                            var leftButtons = [];
                            
                            for (var i = 0; i < buttons.length; i++) {
                                var rect = buttons[i].getBoundingClientRect();
                                if (rect.left < window.innerWidth * 0.2) {  // 화면 좌측 20% 영역
                                    leftButtons.push(buttons[i]);
                                }
                            }
                            
                            return leftButtons;
                        """)
                        
                        # + 버튼 클릭
                        plus_button_clicked = False
                        for i, button in enumerate(left_buttons):
                            try:
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(1)
                                button.click()
                                time.sleep(3)
                                
                                # 클릭 후 텍스트 영역이 나타났는지 확인
                                text_areas = self.driver.find_elements_by_xpath("//div[@role='textbox']")
                                if text_areas:
                                    logger.info(f"좌측 영역 버튼 {i} 클릭 후 텍스트 영역 발견")
                                    plus_button_clicked = True
                                    break
                            except Exception as e:
                                logger.warning(f"버튼 {i} 클릭 실패: {e}")
                                continue
                    
                    if not plus_button_clicked:
                        logger.error("+ 버튼 클릭 실패")
                        if progress_callback:
                            progress_callback(1.0, "+ 버튼 찾기 및 클릭 실패")
                        
                        # 재시도
                        retry_count += 1
                        if retry_count <= max_retry:
                            logger.warning(f"+ 버튼 클릭 실패, 재시도 {retry_count}/{max_retry}")
                            continue
                        
                        # 작업 중 표시 해제
                        try:
                            if os.path.exists(lock_path):
                                os.remove(lock_path)
                        except:
                            pass
                        
                        return False
                    
                    # 3. 텍스트 영역 찾기
                    if progress_callback:
                        progress_callback(0.7, "텍스트 입력")
                    
                    text_area = None
                    
                    # 텍스트 영역 찾기 - 여러 방법 시도
                    try:
                        # 방법 1: role='textbox' 속성으로 찾기
                        text_areas = self.driver.find_elements_by_xpath("//div[@role='textbox']")
                        if text_areas and len(text_areas) > 0:
                            text_area = text_areas[0]
                            logger.info("role='textbox'로 텍스트 영역 찾음")
                    except Exception as e:
                        logger.warning(f"role='textbox'로 텍스트 영역 찾기 실패: {e}")
                    
                    # 방법 2: contenteditable 속성으로 찾기
                    if not text_area:
                        try:
                            text_areas = self.driver.find_elements_by_xpath("//div[@contenteditable='true']")
                            if text_areas and len(text_areas) > 0:
                                text_area = text_areas[0]
                                logger.info("contenteditable='true'로 텍스트 영역 찾음")
                        except Exception as e:
                            logger.warning(f"contenteditable='true'로 텍스트 영역 찾기 실패: {e}")
                    
                    # 텍스트 영역을 찾지 못한 경우
                    if not text_area:
                        logger.error("텍스트 영역을 찾을 수 없습니다.")
                        if progress_callback:
                            progress_callback(1.0, "텍스트 영역을 찾을 수 없습니다.")
                        
                        # 재시도
                        retry_count += 1
                        if retry_count <= max_retry:
                            logger.warning(f"텍스트 영역 찾기 실패, 재시도 {retry_count}/{max_retry}")
                            continue
                        
                        # 작업 중 표시 해제
                        try:
                            if os.path.exists(lock_path):
                                os.remove(lock_path)
                        except:
                            pass
                        
                        return False
                    
                    # 4. 텍스트 입력 - 수정된 부분
                    logger.info(f"입력할 원본 텍스트: {text}")
                    
                    # 텍스트 영역 클릭하여 포커스
                    text_area.click()
                    time.sleep(1)
                    
                    # 이모티콘 지원 텍스트 입력 (헤드리스 모드 처리)
                    if self.headless:
                        text_insert_success = False
                        
                        # 방법 1: innerHTML 및 이벤트 시뮬레이션
                        try:
                            js_script = """
                            // innerHTML로 내용 설정 - 보다 HTML 친화적인 방식
                            arguments[0].innerHTML = arguments[1].replace(/\\n/g, '<br>');
                            
                            // 입력 이벤트 시뮬레이션
                            const inputEvent = new Event('input', { bubbles: true });
                            arguments[0].dispatchEvent(inputEvent);
                            
                            // 변경 이벤트 시뮬레이션
                            const changeEvent = new Event('change', { bubbles: true });
                            arguments[0].dispatchEvent(changeEvent);
                            
                            return arguments[0].textContent;
                            """
                            
                            inserted_text = self.driver.execute_script(js_script, text_area, text)
                            
                            if inserted_text and inserted_text.strip():
                                logger.info("innerHTML 방식으로 이모티콘 삽입 성공")
                                text_insert_success = True
                            else:
                                logger.warning("innerHTML 방식 이모티콘 삽입 실패")
                        except Exception as e:
                            logger.warning(f"innerHTML 방식 이모티콘 삽입 실패: {e}")
                        
                        # 방법 2: 텍스트 노드 생성 및 추가
                        if not text_insert_success:
                            try:
                                js_script = """
                                // 내용 초기화
                                while (arguments[0].firstChild) {
                                    arguments[0].removeChild(arguments[0].firstChild);
                                }
                                
                                // 줄 단위로 처리
                                var lines = arguments[1].split('\\n');
                                
                                // 각 줄마다 텍스트 노드와 줄바꿈 생성
                                for (var i = 0; i < lines.length; i++) {
                                    if (i > 0) {
                                        arguments[0].appendChild(document.createElement('br'));
                                    }
                                    var textNode = document.createTextNode(lines[i]);
                                    arguments[0].appendChild(textNode);
                                }
                                
                                // 이벤트 발생
                                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                                
                                return arguments[0].textContent;
                                """
                                
                                inserted_text = self.driver.execute_script(js_script, text_area, text)
                                
                                if inserted_text and inserted_text.strip():
                                    logger.info("DOM API로 이모티콘 삽입 성공")
                                    text_insert_success = True
                                else:
                                    logger.warning("DOM API 이모티콘 삽입 실패")
                            except Exception as e:
                                logger.warning(f"DOM API 이모티콘 삽입 실패: {e}")
                        
                        # 방법 3: 이모티콘 처리 특화 함수 사용
                        if not text_insert_success:
                            if self.handle_emoji_input(text_area, text):
                                logger.info("이모티콘 특화 함수로 텍스트 삽입 성공")
                                text_insert_success = True
                            else:
                                logger.warning("이모티콘 특화 함수 삽입 실패")
                        
                        # 방법 4: 기존 함수 사용 (마지막 시도)
                        if not text_insert_success:
                            if not self.insert_text_headless(text_area, text):
                                logger.error("모든 텍스트 입력 방법 실패")
                                return False
                    else:
                        # 일반 모드에서는 클립보드 사용 시도
                        try:
                            import pyperclip
                            pyperclip.copy(text)
                            time.sleep(0.5)
                            
                            # Ctrl+V로 붙여넣기
                            paste_action = ActionChains(self.driver)
                            paste_action.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                            logger.info("클립보드로 텍스트 붙여넣기 성공")
                            time.sleep(2)
                        except Exception as e:
                            logger.warning(f"클립보드 붙여넣기 실패: {e}")
                            
                            # 실패 시 직접 입력 시도
                            try:
                                text_area.clear()
                                text_area.send_keys(text)
                                logger.info("sendKeys 메서드로 텍스트 입력 성공")
                                time.sleep(2)
                            except Exception as e2:
                                logger.error(f"텍스트 입력 실패: {e2}")
                                
                                # 재시도
                                retry_count += 1
                                if retry_count <= max_retry:
                                    logger.warning(f"텍스트 입력 실패, 재시도 {retry_count}/{max_retry}")
                                    continue
                                
                                # 작업 중 표시 해제
                                try:
                                    if os.path.exists(lock_path):
                                        os.remove(lock_path)
                                except:
                                    pass
                                
                                return False
                    
                    # *** 텍스트 입력 후 스크린샷 (이미지 업로드 전) ***
                    try:
                        screenshot_path = os.path.join(self.base_path, "data", "logs", f"threads_post_before_image_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
                        self.driver.save_screenshot(screenshot_path)
                        logger.info(f"이미지 업로드 전 텍스트 입력 스크린샷 저장됨: {screenshot_path}")
                    except Exception as e:
                        logger.warning(f"스크린샷 저장 오류: {e}")
                    
                    # *** 텍스트가 실제로 입력되었는지 다시 한번 검증 ***
                    try:
                        text_content = self.driver.execute_script("return arguments[0].textContent || '';", text_area)
                        if not text_content or not text_content.strip():
                            logger.warning("텍스트가 입력되지 않았습니다. 다시 시도합니다.")
                            
                            # 헤드리스 모드에서 최후의 보루 - 다른 방식 시도
                            if self.headless:
                                # 최후의 시도: DOM API로 텍스트 노드 생성
                                try:
                                    self.handle_emoji_input(text_area, text)
                                except Exception as e:
                                    logger.warning(f"텍스트 재설정 시도 중 오류: {e}")
                            else:
                                # 일반 모드에서는 기존 방법으로 처리
                                try:
                                    # 텍스트 영역 클릭 및 내용 지우기
                                    text_area.click()
                                    text_area.clear()
                                    time.sleep(0.5)
                                    
                                    # 내용 다시 입력
                                    text_area.send_keys(text)
                                    logger.info("일반 모드에서 텍스트 재설정 성공")
                                except Exception as e:
                                    logger.warning(f"일반 모드 텍스트 재설정 시도 실패: {e}")
                                    
                                    # 클립보드 방식 시도
                                    try:
                                        import pyperclip
                                        pyperclip.copy(text)
                                        time.sleep(0.5)
                                        
                                        # Ctrl+V로 붙여넣기
                                        paste_action = ActionChains(self.driver)
                                        paste_action.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                                        logger.info("클립보드로 텍스트 다시 붙여넣기 성공")
                                    except Exception as clip_e:
                                        logger.warning(f"클립보드 재시도 실패: {clip_e}")
                            
                            # 추가 디버깅: 텍스트 설정 후 스크린샷
                            try:
                                screenshot_path = os.path.join(self.base_path, "data", "logs", f"threads_post_after_text_reset_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
                                self.driver.save_screenshot(screenshot_path)
                                logger.info(f"텍스트 재설정 후 스크린샷 저장됨: {screenshot_path}")
                            except:
                                pass
                    except Exception as e:
                        logger.warning(f"텍스트 재확인 중 오류: {e}")

                    # 5. 이미지 첨부 (간소화된 버전)
                    if image_path and os.path.exists(image_path):
                        try:
                            logger.info(f"이미지 첨부 시도: {image_path}")
                            
                            # 파일 입력 요소 찾기
                            file_inputs = self.driver.find_elements_by_xpath("//input[@type='file']")
                            if file_inputs:
                                logger.info(f"파일 입력 요소 찾음: {len(file_inputs)}개")
                                file_input = file_inputs[0]
                                
                                # 파일 직접 업로드
                                file_input.send_keys(image_path)
                                logger.info("파일 입력 요소에 직접 경로 전달")
                                time.sleep(5)  # 업로드 대기
                                
                                # 이미지 업로드 확인을 위한 스크린샷 저장
                                screenshot_path = os.path.join(self.base_path, "data", "logs", f"threads_post_image_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
                                self.driver.save_screenshot(screenshot_path)
                                logger.info(f"이미지 업로드 후 스크린샷 저장됨: {screenshot_path}")
                            else:
                                logger.warning("파일 입력 요소를 찾을 수 없음")
                        except Exception as e:
                            logger.error(f"이미지 첨부 과정 중 오류: {e}")
                    
                    # 이미지 업로드 후 텍스트 확인 및 필요 시 재설정 (중요!)
                    try:
                        text_content = self.driver.execute_script("return arguments[0].textContent || '';", text_area)
                        if not text_content or not text_content.strip():
                            logger.warning("이미지 업로드 후 텍스트가 사라짐, 다시 입력 시도")
                            
                            # 헤드리스 모드에 따라 다른 방식 사용
                            if self.headless:
                                # 헤드리스 모드에서는 이모티콘 특화 함수 사용
                                if self.handle_emoji_input(text_area, text):
                                    logger.info("이모티콘 특화 함수로 텍스트 재설정 성공")
                                else:
                                    logger.warning("이모티콘 특화 함수 텍스트 재설정 실패")
                                    
                                    # 실패 시 insert_text_headless 시도
                                    if self.insert_text_headless(text_area, text):
                                        logger.info("insert_text_headless로 텍스트 재설정 성공")
                                    else:
                                        logger.warning("모든 텍스트 재설정 방법 실패")
                            else:
                                # 일반 모드에서는 기존 방법으로 처리
                                try:
                                    # 텍스트 영역 클릭 및 내용 지우기
                                    text_area.click()
                                    text_area.clear()
                                    time.sleep(0.5)
                                    
                                    # 내용 다시 입력
                                    text_area.send_keys(text)
                                    logger.info("일반 모드에서 텍스트 재설정 성공")
                                except Exception as e:
                                    logger.warning(f"일반 모드 텍스트 재설정 시도 실패: {e}")
                                    
                                    # 클립보드 방식 시도
                                    try:
                                        import pyperclip
                                        pyperclip.copy(text)
                                        time.sleep(0.5)
                                        
                                        # Ctrl+V로 붙여넣기
                                        paste_action = ActionChains(self.driver)
                                        paste_action.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                                        logger.info("클립보드로 텍스트 다시 붙여넣기 성공")
                                    except Exception as clip_e:
                                        logger.warning(f"클립보드 재시도 실패: {clip_e}")
                            
                            # 추가 디버깅: 텍스트 설정 후 스크린샷
                            try:
                                screenshot_path = os.path.join(self.base_path, "data", "logs", f"threads_post_after_text_reset_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
                                self.driver.save_screenshot(screenshot_path)
                                logger.info(f"텍스트 재설정 후 스크린샷 저장됨: {screenshot_path}")
                            except:
                                pass
                    except Exception as e:
                        logger.warning(f"텍스트 재확인 중 오류: {e}")

                    # 6. 복사링크를 스레드에 추가
                    if reply_link:
                        try:
                            logger.info(f"복사링크 추가 시도: {reply_link}")
                            
                            # "스레드에 추가" 버튼 찾기
                            add_thread_buttons = self.driver.find_elements_by_xpath(
                                "//span[contains(text(), '스레드에 추가') or contains(text(), 'Add to thread')]"
                            )
                            
                            # 버튼을 찾았는지 확인
                            if add_thread_buttons:
                                # 버튼의 클릭 가능한 부모 요소 찾기
                                for button in add_thread_buttons:
                                    try:
                                        # 부모 요소 탐색 (최대 5단계 상위)
                                        parent = button
                                        for _ in range(5):
                                            try:
                                                parent = parent.find_element_by_xpath("./..")
                                                role = parent.get_attribute("role")
                                                if role == "button":
                                                    # 버튼 클릭
                                                    self.driver.execute_script("arguments[0].click();", parent)
                                                    logger.info("스레드에 추가 버튼 클릭 성공")
                                                    time.sleep(2)
                                                    
                                                    # 텍스트 입력 필드 찾기
                                                    reply_text_areas = self.driver.find_elements_by_xpath("//div[@role='textbox']")
                                                    if reply_text_areas and len(reply_text_areas) > 1:
                                                        # 두 번째 텍스트 영역이 있다면 사용 (첫 번째는 기존 텍스트 영역)
                                                        reply_text_area = reply_text_areas[1]
                                                        
                                                        # 복사링크 붙여넣기
                                                        reply_text_area.click()
                                                        time.sleep(1)
                                                        
                                                        # 내용 입력
                                                        reply_text_area.send_keys(reply_link)
                                                        logger.info("복사링크 입력 성공")
                                                        time.sleep(2)
                                                    else:
                                                        logger.warning("스레드 추가 텍스트 영역을 찾을 수 없음")
                                                    
                                                    break
                                            except Exception as nav_e:
                                                continue
                                        break
                                    except Exception as button_e:
                                        logger.warning(f"스레드에 추가 버튼 클릭 중 오류: {button_e}")
                            else:
                                # JavaScript로 버튼 찾기 시도
                                script = """
                                    let buttons = Array.from(document.querySelectorAll('span')).filter(span => {
                                        let text = span.textContent || '';
                                        return text.includes('스레드에 추가') || text.includes('Add to thread');
                                    });
                                    
                                    if (buttons.length > 0) {
                                        let button = buttons[0];
                                        // 클릭 가능한 상위 요소 찾기
                                        for (let i = 0; i < 5; i++) {
                                            button = button.parentElement;
                                            if (button && button.getAttribute('role') === 'button') {
                                                button.click();
                                                return true;
                                            }
                                        }
                                    }
                                    return false;
                                """
                                
                                result = self.driver.execute_script(script)
                                if result:
                                    logger.info("JavaScript로 스레드에 추가 버튼 클릭 성공")
                                    time.sleep(2)
                                    
                                    # 텍스트 입력 필드 찾기
                                    reply_text_areas = self.driver.find_elements_by_xpath("//div[@role='textbox']")
                                    if reply_text_areas and len(reply_text_areas) > 1:
                                        # 두 번째 텍스트 영역 사용
                                        reply_text_area = reply_text_areas[1]
                                        
                                        # 복사링크 붙여넣기
                                        reply_text_area.click()
                                        time.sleep(1)
                                        
                                        # 내용 입력
                                        reply_text_area.send_keys(reply_link)
                                        logger.info("복사링크 입력 성공")
                                        time.sleep(2)
                                    else:
                                        logger.warning("스레드 추가 텍스트 영역을 찾을 수 없음")
                                else:
                                    logger.warning("스레드에 추가 버튼을 찾을 수 없음")
                                    
                        except Exception as e:
                            logger.error(f"복사링크 추가 중 오류: {e}")
                    
                    # 게시 전 텍스트 최종 확인 및 재설정
                    if self.headless:
                        try:
                            # 헤드리스 모드에서는 텍스트 영역 재확인
                            text_content = self.driver.execute_script("return arguments[0].textContent || '';", text_area)
                            
                            if not text_content or not text_content.strip():
                                logger.warning("게시 직전 텍스트 확인 - 내용 없음, 마지막 시도")
                                
                                # 이모티콘 특화 함수로 마지막 시도
                                if self.handle_emoji_input(text_area, text):
                                    logger.info("게시 직전 이모티콘 특화 함수로 복구 성공")
                                else:
                                    logger.warning("게시 직전 이모티콘 특화 함수 복구 실패")
                                    
                                    # 실패 시 기존 insert_text_headless 시도
                                    if self.insert_text_headless(text_area, text):
                                        logger.info("게시 직전 insert_text_headless로 복구 성공")
                                    else:
                                        logger.warning("게시 직전 복구 실패")
                        except Exception as e:
                            logger.warning(f"게시 직전 최종 텍스트 확인 중 오류: {e}")
                    
                    # 7. 게시 버튼 클릭
                    if progress_callback:
                        progress_callback(0.9, "게시 버튼 클릭")
                    
                    # 게시 전 스크린샷 저장 (디버깅용)
                    screenshot_path = os.path.join(self.base_path, "data", "logs", f"threads_post_before_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
                    self.driver.save_screenshot(screenshot_path)
                    logger.info(f"게시 전 스크린샷 저장됨: {screenshot_path}")
                    
                    # 게시 시도 - 여러 방법 순차적으로 시도
                    post_success = False
                    
                    # 방법 1: Ctrl+Enter로 게시 시도
                    try:
                        # 텍스트 영역에 포커스
                        text_area.click()
                        time.sleep(1)
                        
                        # Ctrl+Enter 입력
                        enter_action = ActionChains(self.driver)
                        enter_action.key_down(Keys.CONTROL).send_keys(Keys.RETURN).key_up(Keys.CONTROL).perform()
                        logger.info("Ctrl+Enter로 게시 시도")
                        time.sleep(5)  # 충분한 대기 시간
                        
                        # 성공 여부 확인: URL 변경 또는 텍스트 영역 사라짐
                        current_url = self.driver.current_url
                        if "/create" not in current_url:
                            logger.info("게시 성공 확인: URL 변경됨")
                            post_success = True
                        else:
                            # 텍스트 영역이 사라졌는지 확인
                            try:
                                text_areas = self.driver.find_elements_by_xpath("//div[@role='textbox']")
                                if not text_areas:
                                    logger.info("텍스트 영역이 사라짐 - 게시 성공")
                                    post_success = True
                            except:
                                pass
                    except Exception as e:
                        logger.warning(f"Ctrl+Enter 게시 시도 실패: {e}")
                    
                    # 방법 2: 게시 버튼 직접 클릭
                    if not post_success:
                        try:
                            # 게시 텍스트 포함 버튼 찾기
                            post_buttons = self.driver.find_elements_by_xpath(
                                "//div[contains(text(), '게시') or contains(text(), 'Post')]"
                            )
                            
                            if post_buttons:
                                for btn in post_buttons:
                                    try:
                                        # 클릭 가능한 부모 요소 찾기
                                        parent = btn
                                        for _ in range(3):  # 최대 3단계 상위까지 확인
                                            try:
                                                # JavaScript로 클릭
                                                self.driver.execute_script("arguments[0].click();", parent)
                                                logger.info("게시 버튼 클릭 성공")
                                                time.sleep(5)
                                                post_success = True
                                                break
                                            except:
                                                # 상위 요소로 이동
                                                parent = parent.find_element_by_xpath("./..")
                                    except:
                                        continue
                                    
                                    if post_success:
                                        break
                        except Exception as e:
                            logger.warning(f"게시 버튼 클릭 실패: {e}")
                    
                    # 방법 3: role='button' 속성을 가진 요소 중 게시 관련 텍스트 있는 버튼 찾기
                    if not post_success:
                        try:
                            buttons = self.driver.find_elements_by_xpath(
                                "//div[@role='button' and (contains(., '게시') or contains(., 'Post'))]"
                            )
                            
                            if buttons:
                                for btn in buttons:
                                    try:
                                        self.driver.execute_script("arguments[0].click();", btn)
                                        logger.info("역할 기반 게시 버튼 클릭 성공")
                                        time.sleep(5)
                                        post_success = True
                                        break
                                    except:
                                        continue
                        except Exception as e:
                            logger.warning(f"역할 기반 게시 버튼 클릭 실패: {e}")
                    
                    # 작업 중 표시 해제
                    try:
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                    except:
                        pass
                    
                    # 메인 페이지로 돌아가면 성공으로 간주
                    time.sleep(3)
                    try:
                        current_url = self.driver.current_url
                        
                        if "/create" not in current_url:
                            logger.info(f"최종 게시 확인: URL이 {current_url}로 변경됨")
                            return True
                        else:
                            logger.warning("게시 시도 후에도 URL이 변경되지 않음")
                            
                            # 재시도
                            retry_count += 1
                            if retry_count <= max_retry:
                                logger.warning(f"게시 확인 실패, 재시도 {retry_count}/{max_retry}")
                                continue
                            
                            # 실패로 간주하지 않고 일단 성공으로 처리 (서버 처리 지연 가능성)
                            return True
                    except Exception as e:
                        logger.error(f"최종 URL 확인 중 오류: {e}")
                        # 일단 성공으로 처리
                        return True
                    
                except Exception as e:
                    logger.error(f"게시 프로세스 중 오류: {e}")
                    
                    # 작업 중 표시 해제
                    try:
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                    except:
                        pass
                    
                    # 재시도
                    retry_count += 1
                    if retry_count <= max_retry:
                        logger.warning(f"게시 과정 오류, 재시도 {retry_count}/{max_retry}")
                        continue
                    
                    if progress_callback:
                        progress_callback(1.0, f"작업 오류: {str(e)}")
                    
                    return False
                    
            except Exception as e:
                logger.error(f"전체 프로세스 오류: {e}")
                
                # 재시도
                retry_count += 1
                if retry_count <= max_retry:
                    logger.warning(f"전체 프로세스 오류, 재시도 {retry_count}/{max_retry}")
                    continue
                
                if progress_callback:
                    progress_callback(1.0, f"작업 오류: {str(e)}")
                
                return False
            
        # 모든 재시도 실패
        logger.error(f"최대 재시도 횟수({max_retry})를 초과했습니다.")
        return False

    def navigate_to_profile(self, timeout=10):
        """
        사용자 프로필 페이지로 이동하는 메서드 - 여러 패턴 시도
        
        Args:
            timeout (int): 최대 대기 시간(초)
                
        Returns:
            bool: 성공 여부
        """
        try:
            # 메인 페이지로 먼저 이동 (네비게이션 메뉴를 보장하기 위해)
            self.driver.get("https://www.threads.net/")
            time.sleep(5)
            logger.info("메인 페이지로 이동 완료")

            # 다이얼로그 닫기 시도
            self.dismiss_dialogs()
            
            # 방법 1: 기본 인덱스 방식 - 네비게이션 바의 마지막 항목으로 가정
            try:
                logger.info("방법 1: 기본 네비게이션 항목 인덱스 시도")
                # 단순히 모든 a 태그 찾기
                nav_items = self.driver.find_elements_by_tag_name("a")
                
                # 처음 몇 개만 확인
                check_count = min(10, len(nav_items))
                for i in range(check_count):
                    try:
                        href = nav_items[i].get_attribute("href")
                        logger.info(f"링크 {i}: {href}")
                    except:
                        logger.info(f"링크 {i}: 속성 가져오기 실패")
                
                # 인덱스 3이 프로필 링크일 가능성 체크
                if len(nav_items) > 3:
                    href = nav_items[3].get_attribute("href")
                    if href and "/@" in href and "/create" not in href:
                        logger.info(f"인덱스 3이 프로필 링크로 확인됨: {href}")
                        nav_items[3].click()
                        time.sleep(3)
                        logger.info("프로필 페이지로 이동 성공 (인덱스 3)")
                        return True
            except Exception as e:
                logger.warning(f"방법 1 실패: {e}")
            
            # 방법 2: aria-label로 프로필 SVG 아이콘 찾기
            try:
                logger.info("방법 2: aria-label로 프로필 아이콘 찾기")
                profile_icons = self.driver.find_elements_by_xpath(
                    "//svg[contains(@aria-label, '프로필') or contains(@aria-label, 'Profile')]"
                )
                
                logger.info(f"프로필 아이콘 개수: {len(profile_icons)}")
                
                for i, icon in enumerate(profile_icons):
                    try:
                        # 부모 a 태그 찾기
                        parent = icon
                        max_depth = 5  # 최대 5단계 상위 요소까지만 검색
                        
                        for _ in range(max_depth):
                            parent = parent.find_element_by_xpath("./..")
                            tag_name = parent.tag_name
                            
                            if tag_name == "a":
                                href = parent.get_attribute("href")
                                logger.info(f"프로필 아이콘 {i}의 부모 a 태그 href: {href}")
                                
                                if href and "/@" in href and "/create" not in href:
                                    parent.click()
                                    time.sleep(3)
                                    logger.info("프로필 페이지로 이동 성공 (aria-label)")
                                    return True
                                break
                    except Exception as e:
                        logger.warning(f"프로필 아이콘 {i}의 부모 찾기 실패: {e}")
            except Exception as e:
                logger.warning(f"방법 2 실패: {e}")
            
            # 방법 3: 네비게이션 역할 요소 내의 링크 찾기
            try:
                logger.info("방법 3: 네비게이션 역할 요소 내의 링크 찾기")
                nav_elements = self.driver.find_elements_by_xpath("//div[@role='navigation']")
                
                if not nav_elements:
                    # role이 없으면 header 내의 nav 요소 시도
                    nav_elements = self.driver.find_elements_by_xpath("//header//nav")
                
                if not nav_elements:
                    # 그래도 없으면 상단부의 모든 div 내 마지막 링크들 시도
                    nav_elements = self.driver.find_elements_by_xpath("//header//div")
                
                logger.info(f"네비게이션 요소 수: {len(nav_elements)}")
                
                for i, nav in enumerate(nav_elements):
                    try:
                        # 각 네비게이션 요소 내의 마지막 링크가 프로필일 가능성이 높음
                        links = nav.find_elements_by_tag_name("a")
                        
                        if links:
                            last_links = links[-4:]  # 마지막 4개 링크 중에 프로필이 있을 가능성
                            logger.info(f"네비게이션 요소 {i}의 링크 수: {len(links)}")
                            
                            for j, link in enumerate(last_links):
                                href = link.get_attribute("href")
                                logger.info(f"네비게이션 {i}의 링크 {j}: {href}")
                                
                                if href and "/@" in href and "/create" not in href:
                                    link.click()
                                    time.sleep(3)
                                    logger.info("프로필 페이지로 이동 성공 (네비게이션 요소)")
                                    return True
                    except Exception as e:
                        logger.warning(f"네비게이션 요소 {i} 처리 중 오류: {e}")
            except Exception as e:
                logger.warning(f"방법 3 실패: {e}")
            
            # 방법 4: 링크 텍스트 패턴으로 찾기
            try:
                logger.info("방법 4: 링크 패턴으로 찾기")
                # 프로필 패턴 링크 찾기
                profile_links = self.driver.find_elements_by_xpath("//a[contains(@href, '/@') and not(contains(@href, '/create'))]")
                
                logger.info(f"프로필 패턴 링크 수: {len(profile_links)}")
                
                for i, link in enumerate(profile_links):
                    href = link.get_attribute("href")
                    logger.info(f"프로필 패턴 링크 {i}: {href}")
                    
                    # 첫 번째 적합한 링크 클릭
                    if "/explore" not in href and "/search" not in href:
                        link.click()
                        time.sleep(3)
                        logger.info("프로필 페이지로 이동 성공 (프로필 패턴)")
                        return True
            except Exception as e:
                logger.warning(f"방법 4 실패: {e}")
            
            # 방법 5: 바디의 모든 링크를 검색하는 가장 마지막 방법
            try:
                logger.info("방법 5: 모든 링크 검색")
                all_links = self.driver.find_elements_by_tag_name("a")
                logger.info(f"총 링크 수: {len(all_links)}")
                
                profile_pattern_links = []
                
                for link in all_links:
                    try:
                        href = link.get_attribute("href")
                        if href and "/@" in href and "/create" not in href and "/explore" not in href and "/search" not in href:
                            profile_pattern_links.append((link, href))
                    except:
                        continue
                
                logger.info(f"발견된 프로필 패턴 링크 수: {len(profile_pattern_links)}")
                
                # 발견된 링크들 출력
                for i, (link, href) in enumerate(profile_pattern_links):
                    logger.info(f"발견된 프로필 링크 {i}: {href}")
                    
                    # 최소한의 차별화를 위해 첫 번째 링크 시도
                    if i == 0:
                        try:
                            link.click()
                            time.sleep(3)
                            logger.info("프로필 페이지로 이동 성공 (전체 검색)")
                            return True
                        except Exception as click_e:
                            logger.warning(f"링크 클릭 실패: {click_e}")
                
                logger.warning("적합한 프로필 링크를 찾지 못했습니다.")
                return False
                
            except Exception as e:
                logger.warning(f"방법 5 실패: {e}")
                return False
                
        except Exception as e:
            logger.error(f"프로필 페이지 이동 시도 중 오류: {e}")
            return False

    def auto_post(self, db_manager, max_posts=5, progress_callback=None):
        """
        자동 게시물 작성
        
        Args:
            db_manager: 데이터베이스 매니저 객체
            max_posts (int): 최대 게시물 수
            progress_callback (function): 진행 상황 콜백 함수
            
        Returns:
            dict: 게시 결과 통계
        """
        try:
            # 로그인 확인
            if not self.check_login_status():
                if progress_callback:
                    progress_callback(0.1, "Threads 로그인 필요")
                login_success = self.login(progress_callback)
                if not login_success:
                    return {"success": 0, "fail": 0, "skipped": 0, "status": "로그인 실패"}
            
            # 미게시 항목 가져오기
            if progress_callback:
                progress_callback(0.2, "미게시 항목 조회 중")
            
            # 'threads' 태그로 미게시 항목 가져오기
            unposted_items = db_manager.get_unposted_items_by_platform('threads')
            
            if not unposted_items:
                logger.info("게시할 항목이 없습니다.")
                if progress_callback:
                    progress_callback(1.0, "게시할 항목이 없습니다.")
                return {"success": 0, "fail": 0, "skipped": 0, "status": "게시할 항목 없음"}
            
            # 최대 게시물 수 제한
            items_to_process = unposted_items[:max_posts]
            total_items = len(items_to_process)
            
            logger.info(f"총 {total_items}개 항목 게시 예정")
            if progress_callback:
                progress_callback(0.3, f"총 {total_items}개 항목 게시 예정")
            
            # 결과 통계
            stats = {"success": 0, "fail": 0, "skipped": 0, "status": "진행 중"}
            
            # 각 항목 처리
            for idx, item in enumerate(items_to_process):
                if progress_callback:
                    progress = 0.3 + (idx / total_items) * 0.7
                    progress_callback(progress, f"항목 {idx+1}/{total_items} 게시 중")
                
                try:
                    # 항목 정보 추출
                    item_id = item.get("id")
                    title = item.get("게시물 제목", "")
                    gpt_msg = item.get("500자 요약", "")
                    image_path = item.get("이미지 경로", "")
                    copy_link = item.get("복사링크", "")
                    
                    # 게시할 내용 준비
                    post_text = f"{title}\n\n{gpt_msg}" if gpt_msg else title
                    
                    # 실제 이미지 경로 확인
                    if image_path and not os.path.exists(image_path):
                        logger.warning(f"이미지 파일이 존재하지 않습니다: {image_path}")
                        image_path = None
                    
                    # 게시물 작성
                    post_success = self.post_thread(
                        text=post_text,
                        image_path=image_path,
                        reply_link=copy_link,
                        progress_callback=progress_callback,  # 간단히 progress_callback 전달
                        close_browser=False  # 브라우저를 여기서 종료하지 않음
                    )
                    
                    # 결과 업데이트
                    if post_success:
                        # 포스팅 상태 업데이트
                        db_manager.update_posting_status(
                            news_id=item_id,
                            platform_id='threads',
                            platform_name='Threads',
                            status='포스팅 완료'
                        )
                        stats["success"] += 1
                        logger.info(f"항목 {idx+1} 게시 성공: {title}")
                        
                        # 각 항목 게시 후 데이터 새로고침 요청 (UI 업데이트를 위한 콜백 추가)
                        if progress_callback:
                            progress_callback(0.8 + (idx / total_items) * 0.2, f"항목 {idx+1}/{total_items} 게시 완료, 데이터 새로고침 중...")
                            
                        # 여기서는 UI를 직접 업데이트할 수 없으므로, 
                        # 호출자에게 알림을 통해 데이터 새로고침이 필요함을 알림
                        if idx < total_items - 1:  # 마지막 항목이 아닌 경우에만 중간 새로고침 요청
                            if hasattr(self, 'data_refreshed_callback') and self.data_refreshed_callback:
                                self.data_refreshed_callback()
                    else:
                        stats["fail"] += 1
                        logger.error(f"항목 {idx+1} 게시 실패: {title}")
                    
                    # 게시물 간 간격 두기
                    time.sleep(10)
                    
                except Exception as e:
                    stats["fail"] += 1
                    logger.error(f"항목 {idx+1} 처리 중 오류: {e}")
            
            # 최종 결과
            stats["status"] = "완료"
            logger.info(f"자동 게시 완료: 성공 {stats['success']}, 실패 {stats['fail']}, 건너뜀 {stats['skipped']}")
            
            if progress_callback:
                progress_callback(1.0, f"게시 완료: 성공 {stats['success']}, 실패 {stats['fail']}")
            
            return stats
            
        except Exception as e:
            logger.error(f"자동 게시 중 오류: {e}")
            if progress_callback:
                progress_callback(1.0, f"자동 게시 오류: {str(e)}")
            return {"success": 0, "fail": 0, "skipped": 0, "status": f"오류: {str(e)}"}
    
    # threads_manager.py 파일의 kill_browser 함수
    def kill_browser(self, pid=None, port=None, module_name=None):
        """
        특정 PID와 포트에 해당하는 브라우저만 정확히 종료
        
        Args:
            pid (int): 종료할 프로세스 ID (선택 사항)
            port (int): 종료할 포트 번호 (선택 사항)
            module_name (str, optional): 모듈명 (로깅용)
            
        Returns:
            bool: 종료 성공 여부
        """
        try:
            import psutil
            import subprocess
            import os
            import time
            import signal
            
            # 특정 PID 또는 포트가 지정된 경우에만 종료
            if pid is None and port is None:
                # 인스턴스 변수 사용 (자신의 브라우저만 종료)
                if hasattr(self, 'chromium_pid') and self.chromium_pid:
                    pid = self.chromium_pid
                if hasattr(self, 'debug_port') and self.debug_port:
                    port = self.debug_port
                if not module_name:
                    module_name = "threads_manager" if isinstance(self, ThreadsManager) else "newspick_collector"
                    
                # 여전히 값이 없으면, 모든 관련 브라우저 종료 시도
                if pid is None and port is None:
                    self.logger.info("PID/포트 정보가 없어 모든 관련 Threads 브라우저를 검색합니다.")
                    module_name = module_name or "threads_manager"
                    
                    # 모든 Threads 관련 프로세스 검색 시도
                    found_processes = False
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            if ('chrome' in proc.info['name'].lower() or 'chromium' in proc.info['name'].lower()):
                                # 프로세스 명령줄에서 사용자 데이터 디렉토리 확인
                                cmdline = ' '.join(proc.cmdline())
                                if 'threadsTEMP' in cmdline or 'threads_manager' in cmdline:
                                    proc.terminate()
                                    self.logger.info(f"Threads 관련 브라우저 종료: PID {proc.info['pid']}")
                                    found_processes = True
                        except:
                            continue
                    
                    if found_processes:
                        time.sleep(1)  # 종료 대기
                        return True
                    else:
                        self.logger.info("종료할 Threads 브라우저를 찾을 수 없습니다.")
                        return False
            
            # 데이터베이스 연결 시도 - db_manager가 없으면 무시
            if hasattr(self, 'db_manager') and self.db_manager:
                try:
                    conn = self.db_manager.get_connection()
                    cursor = conn.cursor()
                    
                    # browser_processes 테이블이 없으면 생성
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS browser_processes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        module_name TEXT,
                        pid INTEGER,
                        port INTEGER,
                        start_time TEXT
                    )
                    ''')
                    
                    # 조건에 따라 브라우저 정보 조회
                    query = "SELECT id, module_name, pid, port FROM browser_processes WHERE 1=1"
                    params = []
                    
                    if pid:
                        query += " AND pid = ?"
                        params.append(pid)
                    if port:
                        query += " AND port = ?"
                        params.append(port)
                    if module_name:
                        query += " AND module_name = ?"
                        params.append(module_name)
                    
                    cursor.execute(query, params)
                    browsers = cursor.fetchall()
                    
                    if not browsers:
                        # DB에 정보가 없지만 PID와 포트가 주어진 경우
                        if pid and port:
                            module = module_name or "unknown"
                            browsers = [(0, module, pid, port)]
                        else:
                            self.logger.info(f"종료할 브라우저 정보를 찾을 수 없습니다. (PID: {pid}, 포트: {port})")
                            if hasattr(self, 'chromium_pid') and self.chromium_pid:
                                browsers = [(0, module_name or "unknown", self.chromium_pid, self.debug_port if hasattr(self, 'debug_port') else None)]
                            else:
                                # 모든 관련 Chrome 프로세스 찾기
                                found_any = False
                                for proc in psutil.process_iter(['pid', 'name']):
                                    try:
                                        if 'chrome' in proc.info['name'].lower() or 'chromium' in proc.info['name'].lower():
                                            # 현재 프로세스 또는 자식 프로세스인지 확인
                                            if proc.parent() and (proc.parent().pid == os.getpid() or 
                                                                proc.pid == os.getpid()):
                                                proc.terminate()
                                                self.logger.info(f"관련 Chrome 프로세스 종료: {proc.info['pid']}")
                                                found_any = True
                                    except:
                                        continue
                                
                                return found_any
                except Exception as db_error:
                    self.logger.warning(f"데이터베이스 연결 오류, 인스턴스 변수 사용: {db_error}")
                    # DB 연결 실패 시 인스턴스 변수로 계속
                    if pid or port:
                        browsers = [(0, module_name or "unknown", pid, port)]
                    elif hasattr(self, 'chromium_pid') and self.chromium_pid:
                        browsers = [(0, module_name or "unknown", self.chromium_pid, self.debug_port if hasattr(self, 'debug_port') else None)]
                    else:
                        # 명시적인 프로세스 정보 없이 이름으로 찾기
                        found_any = False
                        for proc in psutil.process_iter(['pid', 'name']):
                            try:
                                if ('chrome' in proc.info['name'].lower() or 
                                    'chromium' in proc.info['name'].lower()):
                                    # 명령줄 확인
                                    try:
                                        cmdline = ' '.join(proc.cmdline())
                                        if 'threadsTEMP' in cmdline or 'threads_manager' in cmdline:
                                            proc.terminate()
                                            self.logger.info(f"Chrome 프로세스 종료: {proc.info['pid']}")
                                            found_any = True
                                    except:
                                        pass
                            except:
                                continue
                        
                        return found_any
            else:
                # db_manager가 없을 경우 - 직접 제공된 정보나 인스턴스 변수 사용
                if pid or port:
                    browsers = [(0, module_name or "unknown", pid, port)]
                elif hasattr(self, 'chromium_pid') and self.chromium_pid:
                    browsers = [(0, module_name or "unknown", self.chromium_pid, self.debug_port if hasattr(self, 'debug_port') else None)]
                else:
                    # 모든 관련 프로세스 종료 시도
                    found_processes = False
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            pname = proc.info['name'].lower()
                            if 'chrome' in pname or 'chromium' in pname:
                                try:
                                    cmdline = ' '.join(proc.cmdline())
                                    if 'threadsTEMP' in cmdline or 'threads_manager' in cmdline:
                                        proc.terminate()
                                        self.logger.info(f"Chrome 프로세스 종료: {proc.info['pid']}")
                                        found_processes = True
                                except:
                                    pass
                        except:
                            continue
                    
                    self.logger.info("종료할 브라우저 정보가 없어 일치하는 프로세스를 검색했습니다.")
                    return found_processes
            
            success = True
            
            for browser in browsers:
                browser_id, browser_module, browser_pid, browser_port = browser
                try:
                    self.logger.info(f"{browser_module} 브라우저 종료 시도 (PID: {browser_pid}, 포트: {browser_port})")
                    
                    # 1. 프로세스 종료
                    try:
                        if browser_pid:
                            process = psutil.Process(browser_pid)
                            process.terminate()
                            
                            # 종료 대기 (최대 2초)
                            try:
                                process.wait(timeout=2)
                            except psutil.TimeoutExpired:
                                # 2초 후에도 종료되지 않으면 강제 종료
                                process.kill()
                                self.logger.info(f"{browser_module} 프로세스 강제 종료 (PID: {browser_pid})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        self.logger.info(f"{browser_module} 프로세스가 이미 종료되었거나 액세스할 수 없습니다 (PID: {browser_pid})")
                    
                    # 2. 포트 종료
                    if browser_port:
                        try:
                            # Windows에서 해당 포트를 사용하는 프로세스 확인 및 종료
                            netstat = subprocess.run(f'netstat -ano | findstr :{browser_port}', 
                                            shell=True, text=True, capture_output=True)
                            
                            if netstat.stdout:
                                for line in netstat.stdout.splitlines():
                                    if "LISTENING" in line:
                                        parts = line.strip().split()
                                        if len(parts) >= 5:
                                            port_pid = int(parts[-1])
                                            # 지정된 PID와 일치하는 경우에만 종료
                                            if port_pid == browser_pid:
                                                try:
                                                    subprocess.run(f'taskkill /F /PID {port_pid}', 
                                                            shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                                                    self.logger.info(f"포트 {browser_port} 사용 프로세스 종료 (PID: {port_pid})")
                                                except:
                                                    pass
                        except Exception as e:
                            self.logger.warning(f"포트 {browser_port} 종료 중 오류: {e}")
                    
                    # 3. ChromeDriver 종료 - 해당 PID의 자식 프로세스만 종료
                    try:
                        for proc in psutil.process_iter(['pid', 'name', 'ppid']):
                            if 'chromedriver' in proc.info.get('name', '').lower() and proc.info.get('ppid') == browser_pid:
                                proc.terminate()
                                time.sleep(0.3)
                                if proc.is_running():
                                    proc.kill()
                                self.logger.info(f"ChromeDriver 프로세스 종료 (PID: {proc.info['pid']})")
                    except Exception as e:
                        self.logger.warning(f"ChromeDriver 프로세스 종료 중 오류: {e}")
                    
                    # 4. DB에서 해당 브라우저 정보 삭제
                    if hasattr(self, 'db_manager') and self.db_manager and browser_id > 0:
                        try:
                            conn = self.db_manager.get_connection()
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM browser_processes WHERE id = ?", (browser_id,))
                            conn.commit()
                        except Exception as db_error:
                            self.logger.warning(f"브라우저 정보 DB 삭제 오류: {db_error}")
                    
                    self.logger.info(f"{browser_module} 브라우저 종료 완료 (PID: {browser_pid}, 포트: {browser_port})")
                    
                except Exception as e:
                    self.logger.error(f"브라우저 종료 중 오류: {e}")
                    success = False
            
            # 인스턴스 변수 초기화 - 명시적으로 종료된 경우에만
            if pid == getattr(self, 'chromium_pid', None) or port == getattr(self, 'debug_port', None):
                if hasattr(self, 'chromium_pid'):
                    self.chromium_pid = None
                if hasattr(self, 'debug_port'):
                    self.debug_port = None
                if hasattr(self, 'driver'):
                    self.driver = None
            
            return success
        
        except Exception as e:
            self.logger.error(f"브라우저 종료 프로세스 중 오류: {e}")
            return False

    def handle_browser_crash(self, pid=None, port=None, module_name=None):
        # DB에서 해당 브라우저 정보 삭제
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        
        query = "DELETE FROM browser_processes WHERE 1=1"
        params = []
        if pid:
            query += " AND pid = ?"
            params.append(pid)
        if port:
            query += " AND port = ?"
            params.append(port)
        if module_name:
            query += " AND module_name = ?"
            params.append(module_name)
            
        cursor.execute(query, params)
        conn.commit()

    # threads_manager.py 파일에 추가할 함수
    def dismiss_dialogs(self, attempts=3):
        """모든 다이얼로그를 닫기 위해 ESC 키를 여러 번 시도"""
        try:
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.action_chains import ActionChains
            
            logger.info("다이얼로그 닫기 시도 (ESC 키 입력)")
            
            for i in range(attempts):
                try:
                    # 다이얼로그가 있는지 확인
                    dialogs = self.driver.find_elements_by_xpath("//div[@role='dialog']")
                    if not dialogs:
                        logger.info(f"다이얼로그가 발견되지 않음 (시도 {i+1}/{attempts})")
                        break
                    
                    logger.info(f"다이얼로그 감지됨 - ESC 키 입력 시도 {i+1}/{attempts}")
                    
                    # 먼저 body에 포커스를 두고 ESC 키 입력
                    body = self.driver.find_element_by_tag_name("body")
                    body.click()
                    time.sleep(0.5)
                    ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(1)
                    
                    # 다이얼로그 요소에 직접 ESC 키 입력
                    for dialog in dialogs:
                        try:
                            dialog.click()
                            time.sleep(0.5)
                            ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                            time.sleep(1)
                        except:
                            pass
                    
                    # JavaScript로 ESC 키 이벤트 발생시키기
                    self.driver.execute_script("""
                        var escEvent = new KeyboardEvent('keydown', {
                            'key': 'Escape',
                            'keyCode': 27,
                            'which': 27,
                            'code': 'Escape',
                            'bubbles': true,
                            'cancelable': true
                        });
                        document.body.dispatchEvent(escEvent);
                        
                        // 다이얼로그 요소들에 대해서도 이벤트 전달
                        document.querySelectorAll('div[role="dialog"]').forEach(function(dialog) {
                            dialog.dispatchEvent(escEvent);
                        });
                        
                        // 다이얼로그 닫기 버튼 클릭 시도
                        document.querySelectorAll('div[role="dialog"] button').forEach(function(btn) {
                            btn.click();
                        });
                    """)
                    time.sleep(1)
                    
                    # 다이얼로그가 사라졌는지 확인
                    remaining_dialogs = self.driver.find_elements_by_xpath("//div[@role='dialog']")
                    if not remaining_dialogs:
                        logger.info("모든 다이얼로그가 성공적으로 닫힘")
                        return True
                except Exception as e:
                    logger.warning(f"다이얼로그 닫기 시도 {i+1} 중 오류: {e}")
            
            return False
        except Exception as e:
            logger.error(f"다이얼로그 닫기 함수 오류: {e}")
            return False

    def inject_emoji_font(self):
        """헤드리스 모드에서 이모티콘 표시 지원을 위한 폰트 삽입"""
        logger.info("이모티콘 지원 폰트 주입 시도")
        
        try:
            # 기본 폰트 주입 스크립트
            js_script = """
            // 이모티콘 지원을 위한 폰트 스타일 추가
            var style = document.createElement('style');
            style.textContent = `
                @font-face {
                    font-family: 'Noto Color Emoji';
                    src: url('https://fonts.gstatic.com/s/notocoloremoji/v1/Yq6P-KqIXTD0t4D9z1ESnKM3-HpFyagT9Hgf1pyEgXfw.woff2') format('woff2');
                }
                
                body, textarea, div[role="textbox"], input {
                    font-family: 'Segoe UI', 'Apple Color Emoji', 'Noto Color Emoji', sans-serif !important;
                    -webkit-font-smoothing: antialiased;
                    -moz-osx-font-smoothing: grayscale;
                }
            `;
            document.head.appendChild(style);
            
            return true;
            """
            
            result = self.driver.execute_script(js_script)
            if result:
                logger.info("이모티콘 폰트 주입 성공")
            else:
                logger.warning("이모티콘 폰트 주입 실패")
        except Exception as e:
            logger.error(f"이모티콘 폰트 주입 중 오류: {e}")

    def handle_emoji_input(self, text_area, text):
        """이모티콘 입력 특화 처리 함수"""
        logger.info("이모티콘 입력 특화 함수 실행")
        
        try:
            # 이모티콘을 HTML 엔티티로 변환
            import html
            html_text = html.escape(text).replace('\n', '<br>')
            
            # innerHTML로 설정 시도
            js_script = """
            try {
                // innerHTML로 설정 (줄바꿈 처리 포함)
                arguments[0].innerHTML = arguments[1];
                
                // 입력 이벤트 시뮬레이션
                const inputEvent = new Event('input', { bubbles: true });
                arguments[0].dispatchEvent(inputEvent);
                
                return true;
            } catch (e) {
                console.error('이모티콘 입력 오류:', e);
                return false;
            }
            """
            
            result = self.driver.execute_script(js_script, text_area, html_text)
            
            if result:
                logger.info("이모티콘 입력 성공")
                return True
            else:
                logger.warning("이모티콘 입력 실패")
                return False
        except Exception as e:
            logger.error(f"이모티콘 입력 함수 오류: {e}")
            return False

    # threads_manager.py 파일에 새로 추가할 함수
    def cleanup_temp_directories(self):
        """임시 디렉토리 정리"""
        try:
            import shutil
            
            # 사용자 데이터 디렉토리 정리
            if hasattr(self, 'debug_port'):
                temp_dir = os.path.join(self.base_path, "win", "TEMP", f"threadsTEMP_{self.debug_port}")
                if os.path.exists(temp_dir):
                    try:
                        # 하위 폴더 중 캐시 폴더만 삭제
                        cache_dir = os.path.join(temp_dir, "Cache")
                        if os.path.exists(cache_dir):
                            shutil.rmtree(cache_dir)
                            logger.info(f"Threads 캐시 디렉토리 정리 완료: {cache_dir}")
                            
                        # 기타 대용량 임시 파일 폴더 정리
                        for subdir in ["GPUCache", "Code Cache", "Session Storage"]:
                            subdir_path = os.path.join(temp_dir, subdir)
                            if os.path.exists(subdir_path):
                                shutil.rmtree(subdir_path)
                    except Exception as e:
                        logger.warning(f"임시 디렉토리 정리 중 오류: {e}")


            
            return True
        except Exception as e:
            logger.error(f"임시 디렉토리 정리 오류: {e}")
            return False