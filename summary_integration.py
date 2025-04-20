# summary_integration.py
import logging
import threading
import queue
import time
from datetime import datetime

# Perplexity API 핸들러 임포트
from perplexity_api_handler import PerplexityAPIHandler

logger = logging.getLogger(__name__)

class SummaryProcessor:
    """뉴스 제목을 처리하여 요약을 생성하는 클래스"""
    
    def __init__(self, base_path, db_manager):
        """
        초기화 함수
        
        Args:
            base_path (str): 애플리케이션 기본 경로
            db_manager: 데이터베이스 매니저 객체
        """
        self.base_path = base_path
        self.db_manager = db_manager
        self.api_handler = PerplexityAPIHandler(base_path)
        
        # 요약 작업 큐 및 처리 관련 변수
        self.summary_queue = queue.Queue()
        self.processing_thread = None
        self.is_running = False
        self.processed_count = 0
        self.total_count = 0
        self.current_item = None
        
        # 콜백 함수 (진행 상황 업데이트용)
        self.progress_callback = None
    
    def set_progress_callback(self, callback):
        """진행 상황 콜백 함수 설정"""
        self.progress_callback = callback
    
    def start_processing(self):
        """요약 처리 스레드 시작"""
        if self.processing_thread and self.processing_thread.is_alive():
            logger.info("요약 처리 스레드가 이미 실행 중입니다.")
            return
            
        self.is_running = True
        self.processed_count = 0
        self.processing_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.processing_thread.start()
        
        logger.info("요약 처리 스레드 시작됨")
    
    def stop_processing(self):
        """요약 처리 스레드 중지"""
        self.is_running = False
        
        if self.processing_thread and self.processing_thread.is_alive():
            # 스레드 종료 대기 (최대 5초)
            self.processing_thread.join(timeout=5)
            
        # 큐 비우기
        while not self.summary_queue.empty():
            try:
                self.summary_queue.get_nowait()
                self.summary_queue.task_done()
            except queue.Empty:
                break
                
        logger.info("요약 처리 스레드 중지됨")
    
    def add_summary_task(self, news_id, title, category):
        """
        요약 작업 추가
        
        Args:
            news_id (int): 뉴스 항목 ID
            title (str): 뉴스 제목
            category (str): 뉴스 카테고리
        """
        # 이미 요약이 있는지 확인
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT summary_500 FROM news_data WHERE id = ?", (news_id,))
        result = cursor.fetchone()
        
        if result and result[0] and len(result[0].strip()) > 0:
            logger.info(f"뉴스 ID {news_id}의 요약이 이미 존재합니다. 건너뜁니다.")
            return
            
        # 작업 큐에 추가
        self.summary_queue.put((news_id, title, category))
        self.total_count = self.summary_queue.qsize() + self.processed_count
        
        logger.info(f"요약 작업 추가: 뉴스 ID {news_id}, 제목: {title[:30]}...")
        
        # 처리 스레드가 실행 중이 아니면 시작
        if not self.is_running or not self.processing_thread or not self.processing_thread.is_alive():
            self.start_processing()
    
    def add_bulk_summary_tasks(self, news_items):
        """
        여러 뉴스 항목에 대한 요약 작업 일괄 추가
        
        Args:
            news_items (list): 뉴스 항목 목록
        """
        added_count = 0
        for item in news_items:
            news_id = item.get("id")
            title = item.get("게시물 제목", "")
            category = item.get("카테고리", "")
            
            # 이미 요약이 있는지 확인
            summary = item.get("500자 요약", "")
            
            if not summary or len(summary.strip()) == 0:
                self.summary_queue.put((news_id, title, category))
                added_count += 1
        
        self.total_count = self.summary_queue.qsize() + self.processed_count
        
        logger.info(f"{added_count}개의 요약 작업이 큐에 추가되었습니다. 총 {self.total_count}개 작업 예정")
        
        # 처리 스레드가 실행 중이 아니면 시작
        if added_count > 0 and (not self.is_running or not self.processing_thread or not self.processing_thread.is_alive()):
            self.start_processing()
    
    def get_progress(self):
        """
        요약 진행 상황 반환
        
        Returns:
            tuple: (처리된 항목 수, 전체 항목 수, 현재 처리 중인 항목)
        """
        return (self.processed_count, self.total_count, self.current_item)
    
    def _process_queue(self):
        """요약 작업 큐 처리 (내부 메서드)"""
        logger.info("요약 작업 처리 시작")

        # API 키 명시적 재로드 추가
        self.api_handler.reload_api_key()
        if not self.api_handler.api_key:
            logger.error("API 키를 로드할 수 없어 요약 작업을 중단합니다.")
            self.is_running = False
            return
        
        while self.is_running:
            try:
                # 큐에서 작업 가져오기 (1초 타임아웃으로 주기적 상태 확인)
                try:
                    news_id, title, category = self.summary_queue.get(timeout=1)
                except queue.Empty:
                    # 큐가 비어있으면 루프 계속
                    continue
                    
                # 현재 처리 중인 항목 업데이트
                self.current_item = {"id": news_id, "title": title, "category": category}
                
                # 진행 상황 업데이트
                if self.progress_callback:
                    self.progress_callback(self.processed_count, self.total_count, self.current_item)
                
                # 요약 생성
                logger.info(f"요약 작업 시작: 뉴스 ID {news_id}, 제목: {title[:30]}...")
                summary = self.api_handler.generate_summary(title, category)
                
                if summary:
                    # DB 업데이트
                    conn = self.db_manager.get_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE news_data SET summary_500 = ? WHERE id = ?",
                        (summary, news_id)
                    )
                    conn.commit()
                    
                    logger.info(f"요약 저장 완료: 뉴스 ID {news_id}, 길이: {len(summary)}자")
                else:
                    logger.error(f"요약 생성 실패: 뉴스 ID {news_id}")
                
                # 작업 완료 표시
                self.summary_queue.task_done()
                self.processed_count += 1
                
                # 진행 상황 업데이트
                if self.progress_callback:
                    self.progress_callback(self.processed_count, self.total_count, None)
                
                # API 속도 제한을 고려한 대기
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"요약 작업 처리 중 오류: {e}")
                
                # 현재 작업이 설정되어 있으면 오류로 표시
                if self.current_item:
                    logger.error(f"오류 발생 항목: 뉴스 ID {self.current_item['id']}")
                    
                    # 작업 완료 표시
                    self.summary_queue.task_done()
                    self.current_item = None
                
                # 오류 발생 시 잠시 대기 후 계속
                time.sleep(3)
        
        logger.info(f"요약 작업 처리 종료. {self.processed_count}개 작업 완료.")