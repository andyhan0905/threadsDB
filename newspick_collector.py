# File: newspick_collector.py
import os
import time
import json
import logging
import pandas as pd
import pyperclip
import sys
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from image_processor import ImageProcessor
from category_mapper import CategoryMapper
import random
from datetime import datetime
from db_manager import DatabaseManager
from perplexity_api_handler import PerplexityAPIHandler

logger = logging.getLogger(__name__)

class NewspickCollector:
    """
    뉴스픽 파트너스 페이지에서 데이터를 수집하는 클래스
    """
    def __init__(self, base_path, scroll_count=5, wait_time=3, headless=False, max_items=10, custom_message="", selected_option=0):
        self.logger = logger
        self.base_path = base_path
        self.scroll_count = scroll_count
        self.wait_time = wait_time
        self.headless = headless
        self.max_items = max_items
        self.category_mapper = CategoryMapper(base_path)
        # custom_message와 selected_option 변수는 남겨두지만 실제로는 사용하지 않음
        self.custom_message = ""  # 빈 문자열로 설정
        self.selected_option = 0  # 의미 없는 값으로 설정
        self.data_dir = os.path.join(base_path, "data")
        self.images_dir = os.path.join(base_path, "data", "images")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)
        
        # 데이터베이스 매니저 초기화 (SQLite로 변경)
        self.db_manager = DatabaseManager(base_path)
        
        self.image_processor = ImageProcessor(base_path)
        self.collected_titles = set()
        
        # 이미 처리된 제목들을 데이터베이스에서 로드
        self.load_titles_from_db()
        
        self.should_stop = False
        self.auto_mode = False  # 자동화 모드 플래그 추가
        logger.info("뉴스픽 데이터 수집기가 초기화되었습니다.")

        # 요약 처리 핸들러 초기화
        self.init_summary_handler()

    def init_summary_handler(self):
        """요약 처리 핸들러 초기화"""
        # 요약 API 핸들러 생성
        self.summary_api_handler = PerplexityAPIHandler(self.base_path)
        
        # 요약 처리 관련 설정
        self.auto_summary = False  # 자동 요약 활성화 여부 (기본값: 비활성화)
        self.generated_summaries = 0  # 생성된 요약 수 추적
        self.skipped_summaries = 0  # 건너뛴 요약 수 추적

    def check_and_create_summary(self, news_id, title, category):
        """
        뉴스 항목에 대해 요약 생성 확인 및 처리
        
        Args:
            news_id (int): 뉴스 항목 ID
            title (str): 뉴스 제목
            category (str): 뉴스 카테고리
            
        Returns:
            bool: 요약이 성공적으로 생성되었으면 True, 그렇지 않으면 False
        """
        # 자동 요약이 비활성화된 경우 처리하지 않음
        if not self.auto_summary:
            logger.info(f"자동 요약이 비활성화되어 있습니다. 요약을 생성하지 않습니다. (뉴스 ID: {news_id})")
            self.skipped_summaries += 1
            return False
        
        # API 키 확인
        if not self.summary_api_handler.api_key:
            logger.warning("Perplexity API 키가 설정되지 않았습니다. 요약을 생성하지 않습니다.")
            self.skipped_summaries += 1
            return False
        
        # 이미 요약이 있는지 확인
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT summary_500 FROM news_data WHERE id = ?", (news_id,))
        result = cursor.fetchone()
        
        if result and result[0] and len(result[0].strip()) > 0:
            logger.info(f"뉴스 ID {news_id}의 요약이 이미 존재합니다. 건너뜁니다.")
            self.skipped_summaries += 1
            return False
        
        # 요약 생성
        logger.info(f"요약 생성 시작: 뉴스 ID {news_id}, 제목: {title[:30]}...")
        summary = self.summary_api_handler.generate_summary(title, category)
        
        if summary:
            # DB 업데이트
            cursor.execute(
                "UPDATE news_data SET summary_500 = ? WHERE id = ?",
                (summary, news_id)
            )
            conn.commit()
            
            self.generated_summaries += 1
            logger.info(f"요약 저장 완료: 뉴스 ID {news_id}, 길이: {len(summary)}자")
            return True
        else:
            logger.error(f"요약 생성 실패: 뉴스 ID {news_id}")
            self.skipped_summaries += 1
            return False

    def load_titles_from_db(self):
        """
        데이터베이스에서 이미 처리된 제목 로드
        """
        try:
            # 데이터베이스에서 처리된 제목 가져오기
            titles = self.db_manager.get_processed_titles()
            self.collected_titles.update(titles)
            logger.info(f"데이터베이스에서 {len(titles)}개의 제목을 로드했습니다.")
        except Exception as e:
            logger.error(f"DB에서 제목 로드 중 오류: {e}")

    def load_titles_from_excel(self):
        """
        엑셀 로드는 더 이상 사용하지 않음 - DB에서만 로드
        """
        logger.info("엑셀에서 제목 로드 함수는 더 이상 사용하지 않습니다. DB에서만 로드합니다.")
        return

    def save_titles_to_cache(self):
        """
        처리된 제목을 캐시에 저장
        """
        cache_file = os.path.join(self.data_dir, "DB", "processed_titles_cache.json")
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(list(self.collected_titles), f, ensure_ascii=False)
                logger.info(f"캐시에 {len(self.collected_titles)}개의 제목을 저장했습니다.")
        except Exception as e:
            logger.error(f"제목 캐시 저장 중 오류: {e}")

    def normalize_title(self, title):
        """
        제목 표준화 (소문자 변환 및 공백 제거)
        """
        return title.strip().lower() if title else ""

    def initialize_db(self):
        """
        데이터베이스 초기화 또는 확인
        """
        # 데이터베이스 매니저가 이미 초기화되어 있으므로 별도 작업 필요 없음
        logger.info("데이터베이스 연결이 확인되었습니다.")

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
                    if "로그인_상태: 완료" in content:  # threads_login_status.cfg와 형식 맞춤
                        self.login_status = True
                        logger.info("Threads 로그인 상태 확인됨")
                        return True
            except Exception as e:
                logger.error(f"Threads 로그인 상태 파일 읽기 오류: {e}")
        
        self.login_status = False
        logger.warning("Threads 로그인 상태 확인 실패")
        return False

    def timeout_handler(self, func, args=(), kwargs={}, timeout_duration=10):
        """지정된 시간 내에 함수 실행을 제한하는 타임아웃 핸들러"""
        result = [None]
        exception = [None]
        
        def target():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout_duration)
        
        if thread.is_alive():
            logger.warning(f"작업 시간 초과 (>{timeout_duration}초)")
            return None
        
        if exception[0]:
            logger.error(f"작업 중 오류: {exception[0]}")
            return None
            
        return result[0]

    def setup_webdriver(self, module_name=None, base_port_range=None):
        """
        Selenium WebDriver 설정 - 로컬 Chromium 사용
        
        Args:
            module_name (str, optional): 모듈 이름 ('newspick_collector' 또는 'threads_manager')
            base_port_range (tuple, optional): 사용할 포트 범위 (시작, 끝) - 더 이상 사용하지 않음
            
        Returns:
            webdriver.Chrome: 웹드라이버 객체
        """
        # 모듈 이름이 제공되지 않으면 기본값 설정
        module_name = module_name or "newspick_collector"
        
        # 로컬 Chromium 바이너리 경로 설정
        base_dir = os.path.abspath(self.base_path)
        chromium_path = os.path.join(base_dir, "win", "chromium.exe")
        
        # 모듈별 사용자 데이터 디렉토리 설정 - 항상 고정 디렉토리 사용
        user_data_dir = os.path.join(base_dir, "win", "TEMP", "chromeTEMP1")
        os.makedirs(user_data_dir, exist_ok=True)
        
        # 경로 존재 확인
        if not os.path.exists(chromium_path):
            logger.error(f"로컬 Chromium이 존재하지 않습니다: {chromium_path}")
            return None
        
        # 모듈별 고정 포트 설정
        import socket
        
        # 포트 사용 가능 여부 확인 함수
        def is_port_in_use(port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(('localhost', port)) == 0
        
        # 고정 포트 설정 - newspick_collector용 9222 포트
        preferred_port = 9222
        
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
                logger.error("사용 가능한 디버깅 포트를 찾을 수 없습니다.")
                return None
        
        logger.info(f"{module_name}용 디버깅 포트: {debug_port}")
        
        # 크로미움 옵션 설정
        chrome_open_option = (
            ' --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36" '
            '--window-size=1920,1080 --lang=ko_KR --disable-gpu --mute-audio --disable-notifications --no-first-run'
        )
        
        # 헤드리스 모드 설정
        if self.headless:
            chrome_open_option += ' --headless --disable-gpu --disable-dev-shm-usage'
            chrome_open_option += ' --disable-web-security --allow-running-insecure-content'
            chrome_open_option += ' --no-sandbox --disable-setuid-sandbox --disable-popup-blocking'
            chrome_open_option += ' --disable-modal-animations --disable-client-side-phishing-detection'
            logger.info(f"{module_name}용 헤드리스 모드로 브라우저가 실행됩니다.")
        else:
            logger.info(f"{module_name}용 일반 모드로 브라우저가 실행됩니다.")
        
        # 디버깅 포트 설정
        chrome_open_option += f' --remote-debugging-port={debug_port} --user-data-dir="{user_data_dir}"'
        
        logger.info(f"{module_name}용 로컬 Chromium 실행: {chromium_path}")
        cmd = f'"{chromium_path}" {chrome_open_option}'
        
        # 크로미움 프로세스 시작
        import subprocess
        proc = subprocess.Popen(cmd)
        pid = proc.pid
        
        # 인스턴스 변수에 정보 저장
        self.chromium_pid = pid
        self.debug_port = debug_port
        
        logger.info(f"{module_name} Chromium 시작 (프로세스 ID: {pid}, 포트: {debug_port}")
        time.sleep(5)  # 크로미움 시작 대기
        
        # WebDriver 설정
        try:
            options = Options()
            options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
            
            driver_path = os.path.join(base_dir, "win", "driver", "chromedriver.exe")
            logger.info(f"{module_name}용 ChromeDriver 경로: {driver_path}")
            
            if not os.path.exists(driver_path):
                logger.error(f"ChromeDriver 파일이 존재하지 않습니다: {driver_path}")
                return None
            
            # Selenium 3.x 스타일로 초기화
            driver = webdriver.Chrome(executable_path=driver_path, options=options)
            
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
                    
                    console.log('알림창 비활성화 스크립트 실행 완료');
                """)
                
                # 알림창 핸들링 설정
                try:
                    alert = driver.switch_to.alert
                    alert.accept()
                except:
                    pass
            
            return driver
        except Exception as e:
            logger.error(f"{module_name}용 웹드라이버 설정 오류: {e}")
            return None

    def clean_temp_directory(self):
        """크로미움 임시 디렉토리 정리"""
        import shutil
        
        temp_dir = os.path.join(self.base_path, "win", "TEMP", "chromeTEMP1")
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                os.makedirs(temp_dir, exist_ok=True)
                logger.info(f"임시 디렉토리 정리 완료: {temp_dir}")
                return True
            except Exception as e:
                logger.error(f"임시 디렉토리 정리 중 오류: {e}")
        return False

    def kill_browser_processes(self):
        """브라우저 및 드라이버 프로세스를 종료"""
        import psutil
        import subprocess
        import time
        
        # 시작된 프로세스 PID가 있는 경우에만 해당 프로세스 종료
        if hasattr(self, 'chromium_pid') and self.chromium_pid:
            try:
                # 해당 PID로 프로세스 찾기
                process = psutil.Process(self.chromium_pid)
                process.terminate()
                logger.info(f"Chromium 프로세스 종료 요청 (PID: {self.chromium_pid})")
                
                # 종료 확인 (최대 2초 대기)
                try:
                    process.wait(timeout=2)
                except psutil.TimeoutExpired:
                    # 2초 후에도 종료되지 않으면 강제 종료
                    process.kill()
                    logger.info(f"Chromium 프로세스 강제 종료 (PID: {self.chromium_pid})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                logger.info(f"Chromium 프로세스가 이미 종료되었거나 액세스할 수 없습니다 (PID: {self.chromium_pid})")
        
        # 포트 종료 (특정 포트를 사용한 경우)
        if hasattr(self, 'debug_port') and self.debug_port:
            try:
                # Windows에서 해당 포트를 사용하는 프로세스 확인 및 종료
                netstat = subprocess.run(f'netstat -ano | findstr :{self.debug_port}', 
                                shell=True, text=True, capture_output=True)
                
                if netstat.stdout:
                    for line in netstat.stdout.splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            pid = parts[-1]
                            # 시작된 PID와 같은 경우에만 종료 (안전장치)
                            if hasattr(self, 'chromium_pid') and int(pid) == self.chromium_pid:
                                try:
                                    subprocess.run(f'taskkill /F /PID {pid}', shell=True)
                                    logger.info(f"포트 {self.debug_port} 사용 프로세스 종료 (PID: {pid})")
                                except:
                                    pass
            except:
                pass
        
        # ChromeDriver 종료
        # ChromeDriver PID를 저장하지 않았기 때문에 이름으로 검색
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if 'chromedriver' in proc.info['name'].lower():
                    # 추가 확인 - 현재 프로세스의 자식 프로세스인지 확인
                    try:
                        parent = psutil.Process(proc.info['pid']).parent()
                        if parent and parent.pid == os.getpid():
                            proc.terminate()
                            logger.info(f"ChromeDriver 종료 요청 (PID: {proc.info['pid']})")
                    except:
                        # 부모 프로세스 확인 불가 - 안전을 위해 종료하지 않음
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Windows 특화 명령으로 ChromeDriver 종료 (안전하게 수정)
        try:
            # 현재 프로세스에서 시작된 chromedriver.exe만 종료
            subprocess.run('wmic process where "name=\'chromedriver.exe\' and ParentProcessId=' + str(os.getpid()) + '" delete', 
                        shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            logger.info("ChromeDriver 프로세스 종료 시도 완료")
        except:
            pass

    # newspick_collector.py 파일의 collect_data 메서드 수정
    def collect_data(self, urls, progress_callback=None):
        # 데이터 수집 시작 시 should_stop 플래그 명시적으로 False로 설정
        self.should_stop = False
        self.kill_browser_processes()  # 기존 프로세스 종료
        self.initialize_db()  # 엑셀 대신 DB 초기화 함수 호출
        
        # 첫 실행 시 기본 매핑으로 초기화 시도
        try:
            # 카테고리 매핑 파일 존재 확인
            mapping_file = os.path.join(self.base_path, "data", "DB", "category_mapping.json")
            if not os.path.exists(mapping_file):
                # 파일이 없으면 기본 매핑으로 강제 초기화
                self.category_mapper.reset_to_default_mapping()
                self.logger.info("카테고리 매핑 파일이 없어 기본값으로 초기화했습니다.")
        except Exception as e:
            self.logger.error(f"카테고리 매핑 초기화 중 오류: {e}")
        
        total_urls = len(urls)
        new_items_total = 0

        for url_idx, url in enumerate(urls):
            if self.should_stop:
                self.logger.info("데이터 수집이 취소되었습니다.")
                break

            if progress_callback:
                progress_callback(url_idx, total_urls, f"URL 처리 중: {url}")
            self.logger.info(f"URL 처리 중 ({url_idx+1}/{total_urls}): {url}")
            
            # 브라우저 재시작 최대 시도 횟수
            max_restart_attempts = 3
            restart_count = 0
            driver = None  # 이 줄을 추가하여 driver 변수 초기화
            
            while restart_count <= max_restart_attempts:
                try:
                    # 드라이버 설정 부분
                    driver = self.setup_webdriver(module_name="newspick_collector")
                    
                    # 드라이버가 None인지 명시적으로 확인
                    if driver is None:
                        self.logger.error("웹드라이버 설정에 실패했습니다.")
                        if progress_callback:
                            progress_callback(1, 1, "웹드라이버 설정 실패")
                        return False
                    
                    # 이제 driver 변수를 사용해야 함 (self.driver가 아님)
                    driver.get(url)
                    time.sleep(self.wait_time)
                    
                    # 여기서 다시 한번 should_stop 체크 (브라우저 설정 중 취소된 경우)
                    if self.should_stop:
                        self.logger.info("브라우저 설정 후 데이터 수집이 취소되었습니다.")
                        try:
                            driver.quit()
                        except:
                            pass
                        self.kill_browser_processes()
                        return False
                    
                    # 로그인 상태를 먼저 기록에서 확인 - 추가된 코드
                    login_status_file = os.path.join(self.base_path, "data", "DB", "login_status.cfg")
                    login_from_file = False
                    
                    if os.path.exists(login_status_file):
                        try:
                            with open(login_status_file, 'r', encoding='utf-8') as f:
                                content = f.read()
                                if "로그인_상태: 완료" in content:
                                    login_from_file = True
                                    self.logger.info("로그인 상태 파일에서 확인됨. 로그인 검사 건너뜀.")
                        except Exception as e:
                            self.logger.error(f"로그인 상태 파일 읽기 중 오류: {e}")
                    
                    # 첫 번째 URL로 이동하여 HTML 내용에서 카테고리 매핑 업데이트
                    try:
                        # HTML 내용 가져오기
                        html_content = driver.page_source
                        
                        # 카테고리 매핑 업데이트
                        updated_count = self.category_mapper.update_from_html(html_content)
                        if updated_count > 0:
                            self.logger.info(f"{updated_count}개의 카테고리 매핑 정보가 업데이트되었습니다.")
                            
                        # 현재 모든 카테고리 매핑 정보 로깅
                        all_mappings = self.category_mapper.get_all_mappings()
                        self.logger.info(f"현재 카테고리 매핑 정보: {len(all_mappings)}개")
                        for category_id, category_name in all_mappings.items():
                            self.logger.info(f"카테고리 매핑: {category_id} -> {category_name}")
                    except Exception as e:
                        self.logger.warning(f"카테고리 매핑 업데이트 중 오류 (무시됨): {e}")
                    
                    # 로그인 상태 확인 (Selenium 3.x 스타일)
                    # 헤드리스 모드에서는 파일에서 확인된 로그인만 신뢰
                    if not login_from_file:
                        try:
                            login_button = driver.find_element_by_xpath("//button[contains(text(), '로그인')]")
                            self.logger.warning("로그인이 필요합니다. 로그인 페이지로 이동합니다.")
                            
                            # 로그인 페이지로 이동
                            login_button.click()
                            time.sleep(2)
                            
                            # 사용자에게 로그인 완료 요청
                            if not self.headless:
                                self.logger.info("로그인 페이지가 열렸습니다. 로그인을 진행해주세요...")
                                
                                # 현재 URL 저장 (로그인 페이지 URL)
                                login_url = driver.current_url
                                self.logger.info(f"로그인 페이지 URL: {login_url}")
                                
                                # URL 변경 감지 및 자동 진행
                                max_wait_time = 120  # 최대 대기 시간(초)
                                start_time = time.time()
                                
                                # URL 변경 감지
                                while time.time() - start_time < max_wait_time:
                                    # 취소 요청 확인 (추가)
                                    if self.should_stop:
                                        self.logger.info("로그인 대기 중 사용자가 취소했습니다.")
                                        return False
                                    
                                    # 현재 URL 확인
                                    current_url = driver.current_url
                                    
                                    # URL이 변경되었는지 확인 (로그인 완료로 판단)
                                    if current_url != login_url and "/login" not in current_url:
                                        self.logger.info(f"URL 변경이 감지되었습니다: {login_url} -> {current_url}")
                                        self.logger.info("로그인이 완료된 것으로 판단하고 다음 단계로 진행합니다.")
                                        break
                                        
                                    # 짧은 간격으로 체크
                                    time.sleep(1)
                                
                                # 시간 초과 확인
                                if time.time() - start_time >= max_wait_time:
                                    self.logger.warning("로그인 대기 시간이 초과되었습니다.")
                                    if progress_callback:
                                        progress_callback(1, 1, "로그인 대기 시간 초과")
                                    return False
                                
                                self.logger.info("로그인 확인됨. 데이터 수집을 계속합니다.")
                                
                                # 로그인 상태 저장
                                data_dir = os.path.join(self.base_path, "data")
                                db_dir = os.path.join(data_dir, "DB")
                                os.makedirs(db_dir, exist_ok=True)
                                login_status_file = os.path.join(db_dir, "login_status.cfg")
                                
                                with open(login_status_file, 'w', encoding='utf-8') as f:
                                    f.write(f"로그인_시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                    f.write(f"로그인_상태: 완료\n")
                                    f.write(f"최대_수집_항목: {self.max_items}\n")
                                    f.write(f"스크롤_횟수: {self.scroll_count}\n")
                                    f.write(f"대기_시간: {self.wait_time}\n")
                                    f.write(f"헤드리스_모드: {'활성화' if self.headless else '비활성화'}\n")
                                
                                self.logger.info(f"로그인 상태 파일 저장됨: {login_status_file}")
                                
                                # 원래 URL로 다시 이동
                                driver.get(url)
                                time.sleep(self.wait_time)
                            else:
                                # 헤드리스 모드에서는 로그인 상태 파일이 없으면 로그인 불가
                                self.logger.error("헤드리스 모드에서는 자동 로그인이 불가능합니다.")
                                if progress_callback:
                                    progress_callback(1, 1, "헤드리스 모드에서 로그인 실패")
                                return False
                        except Exception as e:
                            # NoSuchElementException이 발생하지 않거나 로그인 상태 파일이 있으면 이미 로그인된 상태로 간주
                            if login_from_file:
                                self.logger.info("로그인 상태 파일이 있고 로그인 버튼이 없어 이미 로그인된 상태로 판단합니다.")
                            else:
                                self.logger.info("로그인 버튼을 찾을 수 없어 이미 로그인된 상태로 간주합니다.")
                    else:
                        self.logger.info("로그인 상태 파일이 존재하므로 이미 로그인된 상태로 간주합니다.")

                    # 카테고리 추출
                    category = "기본 카테고리"
                    try:
                        hash_part = url.split('#')[-1] if '#' in url else ""
                        if hash_part:
                            category = f"카테고리 #{hash_part}"
                    except Exception as e:
                        self.logger.error(f"카테고리 추출 중 오류: {e}")

                    # 지정된 횟수만큼 스크롤 수행
                    for i in range(self.scroll_count):
                        if self.should_stop:
                            break
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        if progress_callback:
                            progress_callback(url_idx, total_urls, f"URL 스크롤 중: {i+1}/{self.scroll_count}")
                        time.sleep(3)  # 스크롤 후 대기

                    # 항목 처리
                    try:
                        # 취소 요청 확인 (추가)
                        if self.should_stop:
                            self.logger.info("스크롤 후 사용자가 취소했습니다.")
                            break
                            
                        new_items_count = self.process_items(driver, url, category, progress_callback, url_idx, total_urls)
                        new_items_total += new_items_count
                        self.logger.info(f"URL '{url}'에서 {new_items_count}개의 새 항목이 수집되었습니다.")
                        # 성공적인 처리 - 브라우저 재시작 루프 종료
                        break
                    except Exception as processing_error:
                        self.logger.error(f"항목 처리 중 오류: {processing_error}")
                        # 오류 발생 시 브라우저 재시작
                        restart_count += 1
                        self.logger.warning(f"브라우저 재시작 시도 ({restart_count}/{max_restart_attempts})")
                        
                        try:
                            driver.quit()
                        except:
                            pass
                        
                        self.kill_browser_processes()
                        time.sleep(5)  # 재시작 전 대기
                        
                        if restart_count > max_restart_attempts:
                            self.logger.error("최대 재시작 횟수 초과, URL 처리를 건너뜁니다.")
                            break
                            
                        # 루프 계속해서 브라우저 재시작
                        continue

                except Exception as e:
                    self.logger.error(f"URL '{url}' 처리 중 오류: {e}")
                    restart_count += 1
                    
                    if driver:
                        try:
                            driver.quit()
                        except:
                            pass
                    
                    # 최대 재시작 시도 횟수 초과 확인
                    if restart_count > max_restart_attempts:
                        self.logger.error(f"최대 재시작 횟수 초과, URL '{url}' 처리를 건너뜁니다.")
                        break
                    
                    self.kill_browser_processes()
                    time.sleep(5)  # 재시작 전 대기
                finally:
                    if driver:
                        try:
                            driver.quit()
                            self.logger.info("WebDriver를 정상적으로 종료했습니다.")
                        except Exception as e:
                            self.logger.error(f"드라이버 종료 중 오류: {e}")
                        
                    # 브라우저 프로세스 강제 종료
                    self.kill_browser_processes()

        # 수집 완료 후 캐시 저장
        self.save_titles_to_cache()
        self.logger.info(f"데이터 수집 완료. 총 {new_items_total}개의 새 항목 추가됨.")
        
        if progress_callback:
            progress_callback(total_urls, total_urls, f"수집 완료: {new_items_total}개 항목 추가")
        try:
            # 쓰레드 게시 작업이 활성 상태인지 확인
            threads_lock_file = os.path.join(self.base_path, "data", "DB", "threads_running.lock")
            if os.path.exists(threads_lock_file):
                self.logger.info("Threads 게시 작업이 진행 중입니다. 브라우저 종료를 건너뜁니다.")
                # 브라우저 프로세스는 종료하지 않고 드라이버만 종료
                if driver:
                    try:
                        driver.quit()
                        self.logger.info("WebDriver 객체만 종료했습니다.")
                    except:
                        pass
            else:
                # 다른 작업이 없으면 정상적으로 종료 진행
                if driver:
                    try:
                        driver.quit()
                        self.logger.info("WebDriver를 정상적으로 종료했습니다.")
                    except Exception as e:
                        self.logger.error(f"드라이버 종료 중 오류: {e}")
                    
                # 브라우저 프로세스 강제 종료
                self.kill_browser_processes()
        except Exception as e:
            self.logger.error(f"완료 처리 중 오류: {e}")

        # 요약 생성 통계 로깅
        if hasattr(self, 'auto_summary') and self.auto_summary:
            self.logger.info(f"요약 생성 통계: 성공 {self.generated_summaries}개, 건너뜀 {self.skipped_summaries}개")
        return True

    def process_items(self, driver, url, category, progress_callback, url_idx, total_urls):
        """
        페이지 내 항목들을 처리
        """
        # CSS 선택자로 버튼 찾기 (Selenium 3.x 스타일)
        copy_buttons = driver.find_elements_by_css_selector("button[data-type='copyurl']")
        
        # 디버깅 로그 추가
        self.logger.info(f"URL당 최대 항목 수: {self.max_items}")
        self.logger.info(f"복사 버튼 개수: {len(copy_buttons)}")
        
        if not copy_buttons:
            self.logger.warning(f"URL '{url}'에서 항목을 찾을 수 없습니다.")
            return 0
                    
        items_to_process = min(self.max_items, len(copy_buttons))
        self.logger.info(f"처리할 항목 수: {items_to_process}")
        
        new_items_count = 0
        
        # 초기 원본 URL 저장 (복구용)
        original_url = driver.current_url
        
        # 카테고리 추출 - 수정된 부분
        try:
            # URL에서 카테고리 ID 추출
            category_id = None
            
            # 해시태그 형식 확인 (#89)
            if '#' in url:
                category_id = url.split('#')[-1]
                self.logger.info(f"URL에서 해시태그로 카테고리 ID 추출: {category_id}")
            
            # channelNo 파라미터 확인 (?channelNo=89)
            else:
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                
                if 'channelNo' in query_params:
                    category_id = query_params['channelNo'][0]
                    self.logger.info(f"URL에서 channelNo 파라미터로 카테고리 ID 추출: {category_id}")
            
            # 카테고리 ID가 추출되었으면 매핑에서 이름 찾기
            if category_id:
                if category_id in self.category_mapper.category_mapping:
                    category_name = self.category_mapper.category_mapping[category_id]
                    if category_name and category_name.strip():
                        category = category_name
                        self.logger.info(f"카테고리 매핑에서 이름 찾음: {category_id} -> {category}")
                    else:
                        # 매핑은 있지만 값이 비어있는 경우 기본값 사용
                        category = f"카테고리 #{category_id}"
                        self.logger.warning(f"카테고리 ID {category_id}의 매핑값이 비어있습니다. 기본값 사용: {category}")
                        
                        # 매핑 자동 복구 시도
                        if category_id in self.category_mapper.default_mapping:
                            default_name = self.category_mapper.default_mapping[category_id]
                            self.category_mapper.update_mapping(category_id, default_name)
                            self.logger.info(f"카테고리 ID {category_id}의 매핑을 기본값으로 복구했습니다: {default_name}")
                            category = default_name
                else:
                    category = f"카테고리 #{category_id}"
                    self.logger.warning(f"카테고리 ID {category_id}에 대한 매핑 없음, 기본값 사용: {category}")
                    
                    # 매핑 자동 추가 시도
                    if category_id in self.category_mapper.default_mapping:
                        default_name = self.category_mapper.default_mapping[category_id]
                        self.category_mapper.update_mapping(category_id, default_name)
                        self.logger.info(f"카테고리 ID {category_id}의 매핑을 자동 추가했습니다: {default_name}")
                        category = default_name
            else:
                self.logger.warning(f"URL '{url}'에서 카테고리 ID를 추출할 수 없음, 기본값 사용: {category}")

        except Exception as e:
            self.logger.error(f"카테고리 추출 중 오류: {e}")
        
        for item_idx in range(items_to_process):
            if self.should_stop:
                break
                        
            if progress_callback:
                progress = url_idx + (item_idx / items_to_process) / total_urls
                progress_callback(progress, 1.0, f"항목 처리 중: {item_idx+1}/{items_to_process}", new_items_count)
            
            # 각 항목 처리를 위한 타임아웃 설정
            item_start_time = time.time()
            item_timeout = 40  # 40초 타임아웃 설정
            
            try:
                # 현재 URL 확인하고 필요하면 원래 페이지로 복귀
                try:
                    if driver.current_url != original_url:
                        self.logger.info(f"원래 URL로 복귀: {original_url}")
                        
                        # 모든 진행 중인 요청 중단 시도
                        try:
                            driver.execute_script("window.stop();")
                        except:
                            pass
                        
                        # 페이지로 이동 시도
                        driver.get(original_url)
                        time.sleep(self.wait_time)
                        
                        # 버튼 다시 가져오기
                        copy_buttons = driver.find_elements_by_css_selector("button[data-type='copyurl']")
                except Exception as e:
                    self.logger.error(f"페이지 복원 중 오류: {e}")
                    # 오류 발생 시 드라이버 재설정 시도
                    try:
                        # 드라이버 종료하지 않고 페이지 새로고침 시도
                        driver.refresh()
                        time.sleep(self.wait_time * 2)
                        driver.get(original_url)
                        time.sleep(self.wait_time)
                        copy_buttons = driver.find_elements_by_css_selector("button[data-type='copyurl']")
                    except Exception as refresh_error:
                        self.logger.error(f"페이지 새로고침 중 오류: {refresh_error}")
                        # 심각한 오류 - 다음 URL로 넘어가기
                        return new_items_count
                
                # 항목이 범위를 벗어나는지 확인
                if item_idx >= len(copy_buttons):
                    self.logger.warning(f"항목 인덱스 {item_idx}가 버튼 목록 길이 {len(copy_buttons)}를 초과합니다.")
                    continue
                
                # 통합된 _process_single_item 함수 호출
                result = self._process_single_item(driver, item_idx, copy_buttons, category, original_url)
                
                # 결과 처리
                if result:
                    if result.get('is_new_item', False):
                        new_items_count += 1
                    
                # 타임아웃 확인
                if time.time() - item_start_time > item_timeout:
                    self.logger.warning(f"항목 {item_idx+1} 처리 시간 초과")
                    self._reset_browser_state(driver, original_url)
            
            except Exception as e:
                self.logger.error(f"항목 {item_idx+1} 처리 중 예외 발생: {e}")
                # 브라우저 상태 복구 시도
                self._reset_browser_state(driver, original_url)
            
            # 처리 완료 후 복사 버튼 목록 갱신
            try:
                copy_buttons = driver.find_elements_by_css_selector("button[data-type='copyurl']")
            except:
                # 무시하고 계속 진행
                pass
        
        # 데이터 수집 완료 로그
        self.logger.info(f"URL '{url}'에서 {new_items_count}개의 새 항목이 수집되었습니다.")
        
        return new_items_count


    def _process_single_item(self, driver, item_idx, copy_buttons, category, original_url):
        """
        단일 항목 처리 - SQLite 데이터베이스에 저장
        """
        try:
            # 현재 페이지에서 버튼 목록 가져오기
            try:
                copy_buttons = driver.find_elements_by_css_selector("button[data-type='copyurl']")
            except:
                # 버튼을 찾을 수 없으면 원본 URL로 복귀 시도
                driver.get(original_url)
                time.sleep(self.wait_time)
                copy_buttons = driver.find_elements_by_css_selector("button[data-type='copyurl']")
            
            if item_idx >= len(copy_buttons):
                logger.warning(f"항목 인덱스 {item_idx}가 버튼 목록 길이 {len(copy_buttons)}를 초과합니다.")
                return None
                    
            btn = copy_buttons[item_idx]
            
            # 게시물 제목 가져오기
            try:
                article_title = btn.get_attribute("data-title")
                normalized_title = self.normalize_title(article_title)
            except:
                logger.error("제목 가져오기 실패")
                return None
            
            # 중복 제목 건너뛰기
            if normalized_title in self.collected_titles or self.db_manager.is_title_processed(normalized_title):
                logger.info(f"중복 제목 건너뜀: {article_title}")
                return {'is_new_item': False}
            
            # 제목이 이미 데이터베이스에 있는지 확인
            if self.db_manager.is_title_processed(normalized_title):
                logger.info(f"이미 DB에 저장된 제목 건너뜀: {article_title}")
                return {'is_new_item': False}
            
            # 원본 링크 추출 (참조용으로만 사용)
            try:
                nid = btn.get_attribute("data-nid") 
                pn = btn.get_attribute("data-pn")
                if nid and pn:
                    original_link = f"http://m.newspic.kr/view.html?nid={nid}&pn={pn}"
                else:
                    original_link = "링크 추출 실패"
                    return {'is_new_item': False}
            except Exception as e:
                logger.error(f"원본 링크 추출 실패: {e}")
                original_link = "링크 추출 실패"
                return {'is_new_item': False}
                    
            # 복사 링크 획득 시도
            copied_link = None
            
            # 헤드리스 모드 처리
            if self.headless:
                logger.info("헤드리스 모드에서 복사 링크 획득 시도")
                
                # 네트워크 요청 감시를 통해 클릭으로만 URL 획득
                js_script = """
                // 복사 링크를 저장할 변수
                let capturedUrl = '';
                
                // 네트워크 요청 감시를 위한 XHR 오버라이드
                const originalXhrOpen = XMLHttpRequest.prototype.open;
                const originalXhrSend = XMLHttpRequest.prototype.send;
                
                XMLHttpRequest.prototype.open = function(method, url, ...args) {
                    // URL에 단축 관련 문자열이 포함된 경우 추적
                    if (url && (url.includes('short') || url.includes('copy'))) {
                        this._isShortUrl = true;
                        this._requestUrl = url;
                    }
                    return originalXhrOpen.apply(this, [method, url, ...args]);
                };
                
                XMLHttpRequest.prototype.send = function(...args) {
                    if (this._isShortUrl) {
                        // 응답 이벤트 리스너 추가
                        this.addEventListener('load', function() {
                            try {
                                const response = JSON.parse(this.responseText);
                                if (response && response.result && response.result.shortUrl) {
                                    capturedUrl = response.result.shortUrl;
                                    console.log('XHR에서 URL 캡처: ' + capturedUrl);
                                }
                            } catch (e) {
                                console.error('XHR 응답 파싱 실패:', e);
                            }
                        });
                    }
                    return originalXhrSend.apply(this, args);
                };
                
                // fetch API 오버라이드
                const originalFetch = window.fetch;
                window.fetch = function(url, options) {
                    // URL에 단축 관련 문자열이 포함된 경우 추적
                    if (url && (url.includes('short') || url.includes('copy'))) {
                        const fetchPromise = originalFetch(url, options);
                        
                        fetchPromise.then(response => {
                            // 응답 복제 (응답은 한 번만 읽을 수 있음)
                            const clonedResponse = response.clone();
                            
                            clonedResponse.json().then(data => {
                                if (data && data.result && data.result.shortUrl) {
                                    capturedUrl = data.result.shortUrl;
                                    console.log('Fetch에서 URL 캡처: ' + capturedUrl);
                                }
                            }).catch(e => {
                                console.error('Fetch 응답 파싱 실패:', e);
                            });
                        });
                        
                        return fetchPromise;
                    }
                    return originalFetch(url, options);
                };
                
                // 클립보드 API 오버라이드
                const originalWriteText = navigator.clipboard ? navigator.clipboard.writeText : null;
                if (navigator.clipboard) {
                    navigator.clipboard.writeText = function(text) {
                        capturedUrl = text;
                        console.log('클립보드에 쓰기 감지: ' + text);
                        return Promise.resolve();
                    };
                }
                
                // document.execCommand 오버라이드 (레거시 클립보드 복사)
                const originalExecCommand = document.execCommand;
                document.execCommand = function(commandId, ...args) {
                    if (commandId === 'copy') {
                        // 선택된 텍스트 가져오기 시도
                        const selection = window.getSelection();
                        if (selection && selection.toString()) {
                            const selectedText = selection.toString();
                            if (selectedText.startsWith('http')) {
                                capturedUrl = selectedText;
                                console.log('execCommand에서 URL 캡처: ' + capturedUrl);
                            }
                        }
                    }
                    return originalExecCommand.apply(document, [commandId, ...args]);
                };
                
                // 복사 이벤트 리스너 추가
                document.addEventListener('copy', function(e) {
                    const textToCopy = window.getSelection().toString();
                    if (textToCopy && textToCopy.startsWith('http')) {
                        capturedUrl = textToCopy;
                        console.log('copy 이벤트에서 URL 캡처: ' + capturedUrl);
                    }
                }, {once: true});
                
                // 알림창 오버라이드
                window.alert = function(message) {
                    console.log('알림창: ' + message);
                    return true;
                };
                
                // 이벤트 리스너가 설정된 후 버튼 클릭
                console.log('버튼 클릭 시도...');
                arguments[0].click();
                console.log('버튼 클릭 완료');
                
                // 1초 기다린 후 결과 확인
                return new Promise(resolve => {
                    setTimeout(() => {
                        // 원래 함수 복원
                        XMLHttpRequest.prototype.open = originalXhrOpen;
                        XMLHttpRequest.prototype.send = originalXhrSend;
                        window.fetch = originalFetch;
                        
                        if (navigator.clipboard && originalWriteText) {
                            navigator.clipboard.writeText = originalWriteText;
                        }
                        document.execCommand = originalExecCommand;
                        
                        console.log('최종 캡처된 URL: ' + capturedUrl);
                        resolve(capturedUrl);
                    }, 1000);
                });
                """
                
                # 스크립트 실행 (최대 3회 시도)
                max_tries = 3
                for attempt in range(max_tries):
                    try:
                        logger.info(f"헤드리스 모드 URL 획득 시도 {attempt+1}/{max_tries}")
                        result = driver.execute_script(js_script, btn)
                        
                        # 알림창 처리 시도
                        try:
                            alert = driver.switch_to.alert
                            alert.accept()
                        except:
                            pass
                        
                        # 결과 확인
                        if result and isinstance(result, str) and result.startswith('http'):
                            logger.info(f"헤드리스 모드에서 성공적으로 URL 획득: {result[:50]}")
                            copied_link = result
                            break
                        else:
                            logger.warning(f"헤드리스 모드 시도 {attempt+1} 실패")
                            # 페이지 새로고침 후 재시도
                            if attempt < max_tries - 1:
                                driver.get(original_url)
                                time.sleep(self.wait_time)
                                copy_buttons = driver.find_elements_by_css_selector("button[data-type='copyurl']")
                                if item_idx < len(copy_buttons):
                                    btn = copy_buttons[item_idx]
                    except Exception as e:
                        logger.error(f"헤드리스 모드 시도 {attempt+1} 중 오류: {e}")
                
                # 모든 시도가 실패한 경우
                if not copied_link:
                    logger.error("헤드리스 모드에서 URL 획득 실패")
                    return {'is_new_item': False}
            else:
                # 일반 모드에서는 클립보드 사용
                logger.info("일반 모드에서 복사 링크 획득 시도")
                
                # 클립보드 초기화
                pyperclip.copy('')
                time.sleep(0.5)
                
                # 알림창 처리 설정
                try:
                    driver.execute_script("window.alert = function() { return true; };")
                except:
                    pass
                
                # 복사 버튼 클릭 시도 - 최대 3회
                max_attempts = 3
                
                for attempt in range(max_attempts):
                    try:
                        logger.info(f"복사 버튼 클릭 시도 {attempt+1}/{max_attempts}")
                        
                        # 버튼으로 스크롤
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.5)
                        
                        # 버튼 클릭
                        ActionChains(driver).move_to_element(btn).click().perform()
                        time.sleep(2)
                        
                        # 클립보드에서 복사된 링크 가져오기
                        copied_link = pyperclip.paste().strip()
                        
                        # 클립보드 내용 검증
                        if copied_link and copied_link.startswith(("http://", "https://")):
                            logger.info(f"URL 복사 성공: {copied_link[:50]}")
                            break
                        else:
                            logger.warning(f"URL 복사 실패, 재시도 중...")
                            
                            # 알림창 처리 시도
                            try:
                                alert = driver.switch_to.alert
                                alert.accept()
                            except:
                                pass
                            
                            # 페이지 새로고침 시도
                            if attempt < max_attempts - 1:
                                driver.get(original_url)
                                time.sleep(self.wait_time)
                                copy_buttons = driver.find_elements_by_css_selector("button[data-type='copyurl']")
                                if item_idx < len(copy_buttons):
                                    btn = copy_buttons[item_idx]
                    except Exception as e:
                        logger.error(f"URL 복사 시도 {attempt+1} 중 오류: {e}")
                
                # 복사 실패 시
                if not copied_link or not copied_link.startswith(("http://", "https://")):
                    logger.warning("클립보드에서 URL 획득 실패")
                    return {'is_new_item': False}
            
            # 이미지 처리
            image_path = ""
            current_page = None
            
            # 원본 링크가 유효한 경우 이미지 추출 시도
            if original_link and original_link != "링크 추출 실패":
                # 현재 페이지 저장
                current_page = driver.current_url
                
                try:
                    # 원본 페이지로 이동
                    driver.get(original_link)
                    time.sleep(self.wait_time)
                    
                    # 이미지 URL 추출
                    image_url = self.extract_image_url(driver)
                    
                    if image_url:
                        # 이미지 처리
                        image_path = self.timeout_handler(
                            self.image_processor.process_image,
                            args=(image_url, item_idx),
                            timeout_duration=20
                        )
                        
                        if not image_path:
                            logger.warning(f"이미지 처리 시간 초과 또는 실패: {image_url}")
                    else:
                        logger.warning("이미지 URL을 추출하지 못했습니다.")
                    
                    # 원래 페이지로 안전하게 돌아가기
                    try:
                        driver.get(original_url)
                        time.sleep(self.wait_time)
                    except Exception as e:
                        logger.error(f"원래 페이지로 돌아가기 실패: {e}")
                        time.sleep(3)
                        driver.get(original_url)
                        time.sleep(self.wait_time)
                    
                except Exception as e:
                    logger.error(f"이미지 처리 중 오류: {e}")
                    try:
                        if current_page:
                            driver.get(original_url)
                            time.sleep(self.wait_time)
                    except:
                        pass
            
            # 수집된 제목을 캐시와 데이터베이스에 추가
            self.collected_titles.add(normalized_title)
            self.db_manager.add_processed_title(normalized_title)
            
            # 변경전: 메시지 옵션을 제외하고 제목만 저장
            # gpt_msg = f"{article_title}"

            # 변경후: GPT 문구는 빈 문자열로 저장(나중에 기능 추가를 위해 필드 유지)
            summary_500 = ""

            # 데이터베이스에 뉴스 항목 추가
            news_id = self.db_manager.add_news_item(
                category=category,
                title=article_title,
                copy_link=copied_link,
                original_link=original_link,
                image_path=image_path,
                summary_500=summary_500  # 필드명 변경
            )
            
            # 요약 생성 (옵션)
            if news_id and self.auto_summary:
                self.check_and_create_summary(news_id, article_title, category)

            if news_id:
                logger.info(f"새 항목 처리 완료: {article_title}")
                return {'is_new_item': True}
            else:
                logger.error(f"새 항목 DB 저장 실패: {article_title}")
                return {'is_new_item': False}
            
        except Exception as e:
            logger.error(f"항목 처리 중 오류: {e}")
            try:
                driver.get(original_url)
                time.sleep(self.wait_time)
            except:
                pass
            return None
            
    def url_encode(self, text):
        """URL 인코딩 헬퍼 함수"""
        import urllib.parse
        return urllib.parse.quote(text)
    
    def _reset_browser_state(self, driver, original_url):
        """브라우저 상태를 복구하는 헬퍼 메서드"""
        try:
            # 모든 진행 중인 요청 중단
            try:
                driver.execute_script("window.stop();")
            except:
                pass
            
            # 빈 페이지 로드
            try:
                driver.get("about:blank")
                time.sleep(3)
            except:
                pass
            
            # 원래 페이지 다시 로드
            try:
                driver.get(original_url)
                time.sleep(self.wait_time * 2)
            except:
                pass
            
            logger.info("브라우저 상태 복구 성공")
            return True
        except Exception as e:
            logger.error(f"브라우저 상태 복구 실패: {e}")
            return False

    def _reset_browser_state(self, driver, original_url):
        """브라우저 상태를 복구하는 헬퍼 메서드"""
        try:
            # 모든 진행 중인 요청 중단
            try:
                driver.execute_script("window.stop();")
            except:
                pass
            
            # 빈 페이지 로드
            try:
                driver.get("about:blank")
                time.sleep(3)
            except:
                pass
            
            # 원래 페이지 다시 로드
            try:
                driver.get(original_url)
                time.sleep(self.wait_time * 2)
            except:
                pass
            
            logger.info("브라우저 상태 복구 성공")
            return True
        except Exception as e:
            logger.error(f"브라우저 상태 복구 실패: {e}")
            return False

    def extract_image_url(self, driver):
        """
        페이지에서 이미지 URL 추출
        
        Args:
            driver (WebDriver): Selenium WebDriver 인스턴스
            
        Returns:
            str or None: 이미지 URL 또는 실패 시 None
        """
        try:
            # 다양한 이미지 선택자 시도 (Selenium 3.x 스타일)
            selectors = [
                "div.link_photo_wrap img",
                "img.main-image",
                "div.content img",
                "article img",
                "div.photo img",
                "body img"
            ]
            
            for selector in selectors:
                try:
                    # 이미지 요소 찾기
                    elements = driver.find_elements_by_css_selector(selector)
                    
                    if elements:
                        # 첫 번째 이미지 사용
                        img_element = elements[0]
                        
                        # 고해상도 이미지 URL 찾기 (data-original 속성 우선)
                        img_url = (
                            img_element.get_attribute("data-original") or 
                            img_element.get_attribute("data-src") or 
                            img_element.get_attribute("src")
                        )
                        
                        if img_url:
                            logger.info(f"이미지 URL 찾음: {img_url}")
                            
                            # 여기서 추가: cboard.net 이미지 URL 처리
                            if 'img-api.cboard.net' in img_url and 'image_url=' in img_url:
                                # 프록시 URL에서 원본 이미지 URL 추출
                                try:
                                    original_url = img_url.split('image_url=')[1]
                                    logger.info(f"원본 이미지 URL로 교체: {original_url}")
                                    return original_url
                                except Exception as e:
                                    logger.error(f"원본 URL 추출 실패: {e}")
                            
                            # 브라우저에서 직접 이미지 다운로드 시도
                            try:
                                logger.info("브라우저 세션으로 이미지 다운로드 시도")
                                img_data = driver.execute_script("""
                                    return (async function(url) {
                                        try {
                                            const response = await fetch(url);
                                            if (!response.ok) throw new Error('Network response was not ok');
                                            const blob = await response.blob();
                                            return new Promise((resolve) => {
                                                const reader = new FileReader();
                                                reader.onloadend = () => resolve(reader.result);
                                                reader.readAsDataURL(blob);
                                            });
                                        } catch (e) {
                                            console.error('Error fetching image:', e);
                                            return null;
                                        }
                                    })(arguments[0]);
                                """, img_url)
                                
                                if img_data and isinstance(img_data, str) and img_data.startswith('data:image'):
                                    # Base64 이미지 데이터를 임시 파일로 저장
                                    import base64
                                    img_data = img_data.split(',')[1]
                                    img_binary = base64.b64decode(img_data)
                                    
                                    # 임시 파일 경로 생성
                                    tmp_dir = os.path.join(self.base_path, "data", "images", "temp")
                                    os.makedirs(tmp_dir, exist_ok=True)
                                    tmp_path = os.path.join(tmp_dir, f"temp_img_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
                                    
                                    # 이미지 저장
                                    with open(tmp_path, 'wb') as f:
                                        f.write(img_binary)
                                    
                                    logger.info(f"브라우저에서 직접 이미지 다운로드 성공: {tmp_path}")
                                    return tmp_path
                            except Exception as e:
                                logger.error(f"브라우저 이미지 다운로드 실패: {e}")
                            
                            # 일반 URL 반환
                            return img_url
                except Exception as img_e:
                    logger.debug(f"선택자 {selector} 처리 중 오류: {img_e}")
                    continue
            
            logger.warning("이미지 요소를 찾을 수 없습니다.")
            return None
            
        except Exception as e:
            logger.error(f"이미지 URL 추출 중 오류: {e}")
            return None

    def scroll_to_position(self, driver, item_index):
        """
        특정 항목 위치로 스크롤
        
        Args:
            driver (WebDriver): Selenium WebDriver 인스턴스
            item_index (int): 스크롤할 항목 인덱스
        """
        try:
            # 적절한 스크롤 위치 계산 (대략적인 위치)
            scroll_height = driver.execute_script("return document.body.scrollHeight")
            scroll_position = (item_index / self.max_items) * scroll_height * 0.8
            
            # 스크롤 실행
            driver.execute_script(f"window.scrollTo(0, {scroll_position});")
            time.sleep(1)
        except Exception as e:
            logger.error(f"스크롤 위치 조정 중 오류: {e}")

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