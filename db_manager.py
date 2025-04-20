# File: db_manager.py
import os
import json
import sqlite3
import logging
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

class DatabaseManager:
    """SQLite 데이터베이스 관리 클래스"""
    
    def __init__(self, base_path):
        """데이터베이스 초기화"""
        self.base_path = base_path
        self.data_dir = os.path.join(base_path, "data")
        self.db_dir = os.path.join(self.data_dir, "DB")
        os.makedirs(self.db_dir, exist_ok=True)
        
        self.db_path = os.path.join(self.db_dir, "newspick_data.db")
        self.connection = None
        
        # 로거 설정 추가
        self.logger = logging.getLogger(__name__)
        
        self.initialize_database()
    
    def get_connection(self):
        """데이터베이스 연결 반환"""
        if self.connection is None:
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            # 행 이름으로 접근할 수 있도록 설정
            self.connection.row_factory = sqlite3.Row
        return self.connection
    
    def close_connection(self):
        """데이터베이스 연결 종료"""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def initialize_database(self):
        """데이터베이스 테이블 초기화"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 뉴스픽 데이터 테이블 - "gpt_message"를 "summary_500"으로 변경
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS news_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                title TEXT,
                copy_link TEXT,
                original_link TEXT,
                collection_date TEXT,
                image_path TEXT,
                summary_500 TEXT,
                posting_time TEXT
            )
            ''')
            
            # 브라우저 프로세스 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS browser_processes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name TEXT,
                pid INTEGER,
                port INTEGER,
                start_time TEXT
            )
            ''')
            
            # 페이스북 포스팅 상태 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS posting_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER,
                page_id TEXT,
                page_name TEXT,
                status TEXT,
                post_date TEXT,
                FOREIGN KEY (news_id) REFERENCES news_data (id)
            )
            ''')
            
            # 페이스북 페이지 계정 정보 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS facebook_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                page_id TEXT,
                app_id TEXT,
                app_secret TEXT,
                access_token TEXT,
                token_expiry TEXT
            )
            ''')
            
            # URL 리스트 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS collection_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                added_date TEXT
            )
            ''')
            
            # 설정 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            ''')
            
            # 이미 처리된 제목 캐시 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_titles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT UNIQUE,
                processed_date TEXT
            )
            ''')
            
            conn.commit()
            logger.info("데이터베이스 테이블이 성공적으로 초기화되었습니다.")
            
        except Exception as e:
            logger.error(f"데이터베이스 초기화 중 오류: {e}")
    
    def save_urls(self, urls):
        """URL 목록 저장"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 기존 URL 삭제
            cursor.execute("DELETE FROM collection_urls")
            
            # 새 URL 추가
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for url in urls:
                cursor.execute(
                    "INSERT INTO collection_urls (url, added_date) VALUES (?, ?)",
                    (url, current_date)
                )
            
            conn.commit()
            logger.info(f"{len(urls)}개의 URL이 저장되었습니다.")
            return True
            
        except Exception as e:
            logger.error(f"URL 저장 중 오류: {e}")
            return False
    
    def load_urls(self):
        """URL 목록 로드"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT url FROM collection_urls ORDER BY id")
            urls = [row['url'] for row in cursor.fetchall()]
            
            logger.info(f"{len(urls)}개의 URL을 로드했습니다.")
            return urls
            
        except Exception as e:
            logger.error(f"URL 로드 중 오류: {e}")
            return []
    
    def save_settings(self, settings_dict):
        """설정 저장"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 설정을 JSON으로 변환하여 저장
            for key, value in settings_dict.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                else:
                    value = str(value)
                
                cursor.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, value)
                )
            
            conn.commit()
            logger.info("설정이 저장되었습니다.")
            return True
            
        except Exception as e:
            logger.error(f"설정 저장 중 오류: {e}")
            return False
    
    def load_settings(self):
        """설정 로드"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT key, value FROM settings")
            settings = {}
            
            for row in cursor.fetchall():
                key = row['key']
                value = row['value']
                
                # 값이 JSON인지 확인하고 파싱 시도
                if value.startswith('{') or value.startswith('['):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
                
                # 부울 값 변환
                elif value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                
                # 숫자 변환 시도
                elif value.isdigit():
                    value = int(value)
                
                settings[key] = value
            
            logger.info("설정을 로드했습니다.")
            return settings
            
        except Exception as e:
            logger.error(f"설정 로드 중 오류: {e}")
            return {}
    
    # db_manager.py의 save_facebook_pages 함수 수정 예
    def save_facebook_pages(self, pages):
        """
        페이스북 페이지 정보 저장 - 민감 정보는 암호화하여 별도 저장
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 보안 모듈 로드
            from account_security import AccountSecurity
            security = AccountSecurity(self.base_path)
            
            # 기존 데이터 삭제
            cursor.execute("DELETE FROM facebook_pages")
            
            # 민감 정보를 저장할 암호화 데이터 딕셔너리
            secure_data = {"pages": []}
            
            # 새 데이터 추가
            for page in pages:
                # 민감 정보와 비민감 정보 분리
                page_secure_info = {
                    "ref_id": page.get("page_id", ""),  # 참조 ID (페이지 ID 사용)
                    "app_id": page.get("app_id", ""),
                    "app_secret": page.get("app_secret", ""),
                    "access_token": page.get("access_token", "")
                }
                
                # 민감 정보는 암호화된 데이터에 추가
                secure_data["pages"].append(page_secure_info)
                
                # DB에는 비민감 정보만 저장
                cursor.execute(
                    """
                    INSERT INTO facebook_pages 
                    (name, page_id, app_id, app_secret, access_token, token_expiry) 
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        page.get("name", ""),
                        page.get("page_id", ""),
                        "[SECURED]",  # 민감 정보는 실제값 대신 표시자 저장
                        "[SECURED]",
                        "[SECURED]",
                        page.get("token_expiry", "")
                    )
                )
            
            # 변경사항 커밋
            conn.commit()
            
            # 민감 정보는 암호화하여 별도 파일에 저장
            # 기존 account_security 모듈의 암호화 메서드 사용
            success = security.encrypt_data(secure_data)
            
            if success:
                logger.info(f"{len(pages)}개의 페이스북 페이지 정보가 안전하게 저장되었습니다.")
            else:
                logger.warning("민감 정보 암호화에 실패했습니다. 일부 데이터만 저장되었습니다.")
            
            return success
            
        except Exception as e:
            logger.error(f"페이스북 페이지 정보 저장 중 오류: {e}")
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            return False
    
    def load_facebook_pages(self):
        """
        페이스북 페이지 정보 로드 - 암호화된 민감 정보 복호화하여 결합
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 보안 모듈 로드
            from account_security import AccountSecurity
            security = AccountSecurity(self.base_path)
            
            # DB에서 페이지 기본 정보 로드
            cursor.execute("""
                SELECT name, page_id, token_expiry 
                FROM facebook_pages
            """)
            
            db_pages = []
            for row in cursor.fetchall():
                page = {
                    "name": row['name'],
                    "page_id": row['page_id'],
                    "token_expiry": row['token_expiry'],
                    # 민감 정보는 일단 비워둠
                    "app_id": "",
                    "app_secret": "",
                    "access_token": ""
                }
                db_pages.append(page)
            
            # 암호화된 파일에서 민감 정보 로드
            secure_data = security.decrypt_file(security.config_file)
            
            if secure_data and "pages" in secure_data:
                secure_pages = secure_data["pages"]
                
                # 페이지 ID를 기준으로 민감 정보와 기본 정보를 결합
                for page in db_pages:
                    page_id = page["page_id"]
                    
                    # 암호화된 정보에서 해당 페이지 ID의 민감 정보 찾기
                    for secure_page in secure_pages:
                        if secure_page.get("ref_id") == page_id:
                            # 민감 정보 채우기
                            page["app_id"] = secure_page.get("app_id", "")
                            page["app_secret"] = secure_page.get("app_secret", "")
                            page["access_token"] = secure_page.get("access_token", "")
                            break
            else:
                logger.warning("암호화된 민감 정보를 찾을 수 없거나 복호화에 실패했습니다.")
            
            logger.info(f"{len(db_pages)}개의 페이스북 페이지 정보를 로드했습니다.")
            return db_pages
            
        except Exception as e:
            logger.error(f"페이스북 페이지 정보 로드 중 오류: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def add_news_item(self, category, title, copy_link, original_link, image_path, summary_500):
        """뉴스 항목 추가"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            collection_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute(
                """
                INSERT INTO news_data 
                (category, title, copy_link, original_link, collection_date, image_path, summary_500) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (category, title, copy_link, original_link, collection_date, image_path, summary_500)
            )
            
            news_id = cursor.lastrowid
            conn.commit()
            
            logger.info(f"뉴스 항목이 추가되었습니다. ID: {news_id}")
            return news_id
            
        except Exception as e:
            logger.error(f"뉴스 항목 추가 중 오류: {e}")
            return None
    
    def update_posting_status(self, news_id, page_id, page_name, status):
        """포스팅 상태 업데이트"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            post_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 기존 상태 확인
            cursor.execute(
                "SELECT id FROM posting_status WHERE news_id = ? AND page_id = ?",
                (news_id, page_id)
            )
            result = cursor.fetchone()
            
            if result:
                # 기존 상태 업데이트
                cursor.execute(
                    """
                    UPDATE posting_status 
                    SET status = ?, post_date = ? 
                    WHERE news_id = ? AND page_id = ?
                    """,
                    (status, post_date, news_id, page_id)
                )
            else:
                # 새 상태 추가
                cursor.execute(
                    """
                    INSERT INTO posting_status 
                    (news_id, page_id, page_name, status, post_date) 
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (news_id, page_id, page_name, status, post_date)
                )
            
            # 포스팅 시간 업데이트
            if "포스팅 완료" in status:
                cursor.execute(
                    "UPDATE news_data SET posting_time = ? WHERE id = ?",
                    (post_date, news_id)
                )
            
            conn.commit()
            logger.info(f"포스팅 상태가 업데이트되었습니다. 뉴스 ID: {news_id}, 페이지: {page_name}")
            return True
            
        except Exception as e:
            logger.error(f"포스팅 상태 업데이트 중 오류: {e}")
            return False
    
    def get_news_items(self, posted_only=False, unposted_only=False, page_id=None, limit=None):
        """뉴스 항목 조회"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 여기 쿼리에서 gpt_message를 summary_500으로 변경
            query = """
                SELECT n.id, n.category, n.title, n.copy_link, n.original_link, 
                    n.collection_date, n.image_path, n.summary_500, n.posting_time
                FROM news_data n
            """
            
            params = []
            
            # 포스팅 상태에 따른 필터링
            if posted_only or unposted_only or page_id:
                query += " LEFT JOIN posting_status ps ON n.id = ps.news_id"
                
                where_clauses = []
                
                if page_id:
                    where_clauses.append("ps.page_id = ?")
                    params.append(page_id)
                
                if posted_only:
                    where_clauses.append("ps.status LIKE '%포스팅 완료%'")
                
                if unposted_only:
                    if page_id:
                        where_clauses.append("(ps.status IS NULL OR ps.status NOT LIKE '%포스팅 완료%')")
                    else:
                        where_clauses.append("NOT EXISTS (SELECT 1 FROM posting_status ps2 WHERE ps2.news_id = n.id AND ps2.status LIKE '%포스팅 완료%')")
                
                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)
            
            query += " ORDER BY n.id DESC"
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor.execute(query, params)
            
            news_items = []
            for row in cursor.fetchall():
                item = {
                    "id": row['id'],
                    "카테고리": row['category'],
                    "게시물 제목": row['title'],
                    "복사링크": row['copy_link'],
                    "원본링크": row['original_link'],
                    "수집 날짜": row['collection_date'],
                    "이미지 경로": row['image_path'],
                    "500자 요약": row['summary_500'],  # GPT_문구에서 500자 요약으로 변경
                    "포스팅 시간": row['posting_time'] or ""
                }
                
                # 페이지별 포스팅 상태 가져오기
                sub_cursor = conn.cursor()
                sub_cursor.execute(
                    """
                    SELECT page_id, page_name, status, post_date
                    FROM posting_status
                    WHERE news_id = ?
                    """,
                    (row['id'],)
                )
                
                for status_row in sub_cursor.fetchall():
                    status_key = f"페이스북_상태_{status_row['page_id']}"
                    item[status_key] = status_row['status']
                
                news_items.append(item)
            
            logger.info(f"{len(news_items)}개의 뉴스 항목을 조회했습니다.")
            return news_items
            
        except Exception as e:
            logger.error(f"뉴스 항목 조회 중 오류: {e}")
            return []
    
    def get_unposted_items_by_page(self, page_id):
        """페이지별 미포스팅 항목 조회"""
        return self.get_news_items(unposted_only=True, page_id=page_id)
    
    def delete_news_item(self, news_id):
        """뉴스 항목 삭제"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 이미지 경로 가져오기
            cursor.execute("SELECT image_path FROM news_data WHERE id = ?", (news_id,))
            row = cursor.fetchone()
            
            if row and row['image_path']:
                image_path = row['image_path']
                # 이미지 파일 삭제
                if os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                        
                        # 부모 폴더가 비어있으면 삭제
                        parent_dir = os.path.dirname(image_path)
                        if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                            os.rmdir(parent_dir)
                            
                        logger.info(f"이미지 파일 삭제: {image_path}")
                    except Exception as e:
                        logger.error(f"이미지 파일 삭제 중 오류: {e}")
            
            # 포스팅 상태 삭제
            cursor.execute("DELETE FROM posting_status WHERE news_id = ?", (news_id,))
            
            # 뉴스 항목 삭제
            cursor.execute("DELETE FROM news_data WHERE id = ?", (news_id,))
            
            conn.commit()
            logger.info(f"뉴스 항목이 삭제되었습니다. ID: {news_id}")
            return True
            
        except Exception as e:
            logger.error(f"뉴스 항목 삭제 중 오류: {e}")
            return False
    
    def add_processed_title(self, title):
        """처리된 제목 추가"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            processed_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute(
                "INSERT OR IGNORE INTO processed_titles (title, processed_date) VALUES (?, ?)",
                (title, processed_date)
            )
            
            conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"처리된 제목 추가 중 오류: {e}")
            return False

    def delete_processed_title(self, title):
        """처리된 제목 삭제"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM processed_titles WHERE title = ?", (title,))
            
            conn.commit()
            logger.info(f"처리된 제목이 삭제되었습니다: {title}")
            return True
            
        except Exception as e:
            logger.error(f"처리된 제목 삭제 중 오류: {e}")
            return False

    def is_title_processed(self, title):
        """제목이 이미 처리되었는지 확인"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM processed_titles WHERE title = ?", (title,))
            return cursor.fetchone() is not None
            
        except Exception as e:
            logger.error(f"제목 처리 확인 중 오류: {e}")
            return False
    
    def get_processed_titles(self):
        """처리된 제목 목록 조회"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT title FROM processed_titles")
            titles = [row['title'] for row in cursor.fetchall()]
            
            return titles
            
        except Exception as e:
            logger.error(f"처리된 제목 목록 조회 중 오류: {e}")
            return []
    
    def convert_excel_to_db(self, excel_path):
        """엑셀 데이터를 데이터베이스로 변환"""
        try:
            if not os.path.exists(excel_path):
                logger.warning(f"변환할 엑셀 파일이 없습니다: {excel_path}")
                return False
            
            # 엑셀 파일 읽기
            df = pd.read_excel(excel_path)
            
            if df.empty:
                logger.warning("엑셀 파일에 데이터가 없습니다.")
                return False
            
            conn = self.get_connection()
            
            # 기존 테이블 내용 삭제
            conn.execute("DELETE FROM news_data")
            conn.execute("DELETE FROM posting_status")
            
            # 뉴스 데이터 추가
            for _, row in df.iterrows():
                cursor = conn.cursor()
                
                # 뉴스 데이터 추가
                cursor.execute(
                    """
                    INSERT INTO news_data 
                    (category, title, copy_link, original_link, collection_date, image_path, summary_500, posting_time) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("카테고리", ""),
                        row.get("게시물 제목", ""),
                        row.get("복사링크", ""),
                        row.get("원본링크", ""),
                        row.get("수집 날짜", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        row.get("이미지 경로", ""),
                        row.get("500자 요약", ""),
                        row.get("포스팅 시간", "")
                    )
                )
                
                news_id = cursor.lastrowid
                
                # 페이지별 상태 추가
                for col in row.index:
                    if col.startswith("페이스북_상태_"):
                        page_id = col.replace("페이스북_상태_", "")
                        status = row[col]
                        
                        if status and isinstance(status, str) and status.strip():
                            # 페이지 이름 추출 시도
                            page_name = "알 수 없는 페이지"
                            if "(" in status and ")" in status:
                                try:
                                    page_name = status.split("(")[1].split(",")[0].strip()
                                except:
                                    pass
                            
                            cursor.execute(
                                """
                                INSERT INTO posting_status 
                                (news_id, page_id, page_name, status, post_date) 
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (
                                    news_id,
                                    page_id,
                                    page_name,
                                    status,
                                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                )
                            )
            
            conn.commit()
            logger.info(f"{len(df)}개의 엑셀 데이터가 데이터베이스로 변환되었습니다.")
            return True
            
        except Exception as e:
            logger.error(f"엑셀 데이터 변환 중 오류: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def export_to_dataframe(self):
        """데이터베이스 내용을 pandas DataFrame으로 변환"""
        try:
            # 뉴스 데이터 조회
            news_items = self.get_news_items()
            
            # DataFrame 생성
            df = pd.DataFrame(news_items)
            
            return df
            
        except Exception as e:
            logger.error(f"DataFrame 변환 중 오류: {e}")
            return pd.DataFrame()
    
    def backup_database(self, backup_path=None):
        """데이터베이스 백업 (필요한 경우에만 실행)"""
        # 데이터베이스 사용 기간이 일정 시간 이상인 경우에만 백업
        # 또는 환경 변수나 설정으로 백업 활성화 여부 제어
        
        # 백업 비활성화 옵션: True로 설정하면 백업하지 않음
        disable_backup = False  # 여기를 True로 변경하면 백업이 생성되지 않음
        
        if disable_backup:
            logger.info("데이터베이스 백업이 비활성화되었습니다.")
            return False
        
        try:
            if self.connection:
                self.connection.commit()
                
            if backup_path is None:
                # 기본 백업 경로 생성
                backup_dir = os.path.join(self.data_dir, "backup")
                os.makedirs(backup_dir, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = os.path.join(backup_dir, f"newspick_data_{timestamp}.db")
            
            # pragmas 설정으로 안전한 백업
            source_conn = sqlite3.connect(self.db_path)
            source_conn.execute("PRAGMA foreign_keys=OFF")
            source_conn.execute("PRAGMA journal_mode=DELETE")
            
            # 백업 실행
            backup_conn = sqlite3.connect(backup_path)
            source_conn.backup(backup_conn)
            
            backup_conn.close()
            source_conn.close()
            
            logger.info(f"데이터베이스가 백업되었습니다: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"데이터베이스 백업 중 오류: {e}")
            return False

    def update_database_for_thread_columns(self):
        """쓰레드 관련 열을 데이터베이스에 추가"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 새로운 열 추가 (존재하지 않을 경우에만)
            new_columns = [
                "thread1 TEXT DEFAULT ''",
                "thread2 TEXT DEFAULT ''",
                "thread3 TEXT DEFAULT ''", 
                "thread4 TEXT DEFAULT ''",
                "thread5 TEXT DEFAULT ''",
                "created_status TEXT DEFAULT ''"
            ]
            
            # 각 열이 있는지 확인하고 없으면 추가
            for column_def in new_columns:
                column_name = column_def.split()[0]
                try:
                    # 열 존재 여부 확인
                    cursor.execute(f"SELECT {column_name} FROM news_data LIMIT 1")
                except:
                    # 열이 없으면 추가
                    cursor.execute(f"ALTER TABLE news_data ADD COLUMN {column_def}")
                    # 전역 logger 변수 사용
                    print(f"news_data 테이블에 {column_name} 열 추가됨")
            
            conn.commit()
            print("쓰레드 관련 열 추가 완료")
            return True
                
        except Exception as e:
            # 전역 logger 변수 사용
            print(f"쓰레드 열 추가 중 오류: {e}")
            return False

    def update_database_for_threads(self):
        """Threads SNS 기능을 위한 데이터베이스 업데이트"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 포스팅 상태 테이블에 platform 필드 추가 확인
            try:
                cursor.execute("SELECT platform_id FROM posting_status LIMIT 1")
            except:
                # platform_id 필드가 없으면 추가
                cursor.execute("ALTER TABLE posting_status ADD COLUMN platform_id TEXT DEFAULT 'facebook'")
                logger.info("posting_status 테이블에 platform_id 필드 추가")
                
            # threads 설정 테이블 추가
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS threads_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT,
                login_time TEXT,
                auto_post BOOLEAN DEFAULT 0,
                post_interval INTEGER DEFAULT 60,
                max_posts_per_run INTEGER DEFAULT 5
            )
            ''')
            
            # 기본 설정값 추가 (없는 경우에만)
            cursor.execute("SELECT COUNT(*) FROM threads_settings")
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO threads_settings (account_name, login_time, auto_post, post_interval, max_posts_per_run) VALUES (?, ?, ?, ?, ?)",
                    ("", "", 0, 60, 5)
                )
            
            conn.commit()
            logger.info("Threads SNS 기능을 위한 데이터베이스 업데이트 완료")
            return True
            
        except Exception as e:
            logger.error(f"Threads SNS 데이터베이스 업데이트 중 오류: {e}")
            return False

    def save_threads_settings(self, settings_dict):
        """Threads 설정 저장"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 이전 설정 확인
            cursor.execute("SELECT id FROM threads_settings LIMIT 1")
            result = cursor.fetchone()
            
            if result:
                # 기존 설정 업데이트
                cursor.execute(
                    """
                    UPDATE threads_settings 
                    SET account_name = ?, auto_post = ?, post_interval = ?, max_posts_per_run = ?
                    WHERE id = ?
                    """,
                    (
                        settings_dict.get("account_name", ""),
                        settings_dict.get("auto_post", False),
                        settings_dict.get("post_interval", 60),
                        settings_dict.get("max_posts_per_run", 5),
                        result[0]
                    )
                )
            else:
                # 새 설정 추가
                cursor.execute(
                    """
                    INSERT INTO threads_settings 
                    (account_name, auto_post, post_interval, max_posts_per_run) 
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        settings_dict.get("account_name", ""),
                        settings_dict.get("auto_post", False),
                        settings_dict.get("post_interval", 60),
                        settings_dict.get("max_posts_per_run", 5)
                    )
                )
            
            conn.commit()
            logger.info("Threads 설정이 저장되었습니다.")
            return True
            
        except Exception as e:
            logger.error(f"Threads 설정 저장 중 오류: {e}")
            return False

    def load_threads_settings(self):
        """Threads 설정 로드"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM threads_settings LIMIT 1")
            row = cursor.fetchone()
            
            if row:
                settings = {
                    "account_name": row["account_name"],
                    "login_time": row["login_time"],
                    "auto_post": bool(row["auto_post"]),
                    "post_interval": row["post_interval"],
                    "max_posts_per_run": row["max_posts_per_run"]
                }
                return settings
            else:
                # 기본값 반환
                return {
                    "account_name": "",
                    "login_time": "",
                    "auto_post": False,
                    "post_interval": 60,
                    "max_posts_per_run": 5
                }
                
        except Exception as e:
            logger.error(f"Threads 설정 로드 중 오류: {e}")
            return {
                "account_name": "",
                "login_time": "",
                "auto_post": False,
                "post_interval": 60,
                "max_posts_per_run": 5
            }

    def update_threads_login_time(self, login_time, account_name=""):
        """Threads 로그인 시간 업데이트"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM threads_settings LIMIT 1")
            result = cursor.fetchone()
            
            if result:
                cursor.execute(
                    "UPDATE threads_settings SET login_time = ?, account_name = ? WHERE id = ?",
                    (login_time, account_name, result[0])
                )
            else:
                cursor.execute(
                    "INSERT INTO threads_settings (login_time, account_name) VALUES (?, ?)",
                    (login_time, account_name)
                )
            
            conn.commit()
            logger.info(f"Threads 로그인 시간 업데이트: {login_time}")
            return True
            
        except Exception as e:
            logger.error(f"Threads 로그인 시간 업데이트 중 오류: {e}")
            return False

    def get_unposted_items_by_platform(self, platform_id, limit=None):
        """
        특정 플랫폼에 미게시된 항목 조회
        
        Args:
            platform_id (str): 플랫폼 ID (threads, facebook 등)
            limit (int, optional): 조회할 최대 항목 수
            
        Returns:
            list: 미게시 항목 목록
        """
        try:
            conn = self.get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = """
                SELECT n.id, n.category, n.title, n.copy_link, n.original_link, 
                    n.collection_date, n.image_path, n.summary_500, n.posting_time
                FROM news_data n
                WHERE NOT EXISTS (
                    SELECT 1 FROM posting_status ps 
                    WHERE ps.news_id = n.id 
                    AND ps.platform_id = ? 
                    AND ps.status LIKE '%포스팅 완료%'
                )
                ORDER BY n.id DESC
            """
            
            params = [platform_id]
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor.execute(query, params)
            
            news_items = []
            for row in cursor.fetchall():
                item = {
                    "id": row['id'],
                    "카테고리": row['category'],
                    "게시물 제목": row['title'],
                    "복사링크": row['copy_link'],
                    "원본링크": row['original_link'],
                    "수집 날짜": row['collection_date'],
                    "이미지 경로": row['image_path'],
                    "500자 요약": row['summary_500'],
                    "포스팅 시간": row['posting_time'] or ""
                }
                news_items.append(item)
            
            logger.info(f"{platform_id} 플랫폼용 미게시 항목 {len(news_items)}개 조회됨")
            return news_items
            
        except Exception as e:
            logger.error(f"{platform_id} 플랫폼용 미게시 항목 조회 중 오류: {e}")
            return []

    def update_posting_status(self, news_id, platform_id, platform_name, status):
        """
        포스팅 상태 업데이트 (플랫폼 지정 버전)
        
        Args:
            news_id (int): 뉴스 항목 ID
            platform_id (str): 플랫폼 ID
            platform_name (str): 플랫폼 이름
            status (str): 상태 메시지
            
        Returns:
            bool: 성공 여부
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            post_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 기존 상태 확인
            cursor.execute(
                "SELECT id FROM posting_status WHERE news_id = ? AND platform_id = ?",
                (news_id, platform_id)
            )
            result = cursor.fetchone()
            
            if result:
                # 기존 상태 업데이트
                cursor.execute(
                    """
                    UPDATE posting_status 
                    SET status = ?, post_date = ? 
                    WHERE news_id = ? AND platform_id = ?
                    """,
                    (status, post_date, news_id, platform_id)
                )
            else:
                # 새 상태 추가
                cursor.execute(
                    """
                    INSERT INTO posting_status 
                    (news_id, platform_id, page_id, page_name, status, post_date) 
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (news_id, platform_id, platform_id, platform_name, status, post_date)
                )
            
            # 포스팅 시간 업데이트
            if "포스팅 완료" in status:
                cursor.execute(
                    "UPDATE news_data SET posting_time = ? WHERE id = ?",
                    (post_date, news_id)
                )
            
            conn.commit()
            logger.info(f"포스팅 상태 업데이트: 뉴스 ID: {news_id}, 플랫폼: {platform_name}, 상태: {status}")
            return True
            
        except Exception as e:
            logger.error(f"포스팅 상태 업데이트 중 오류: {e}")
            return False

    def get_posting_status(self, news_id, platform_id='threads'):
        """
        특정 뉴스 항목의 포스팅 상태 확인
        
        Args:
            news_id (int): 뉴스 항목 ID
            platform_id (str): 플랫폼 ID (기본값: 'threads')
            
        Returns:
            str: 포스팅 상태 또는 None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT status FROM posting_status 
                WHERE news_id = ? AND platform_id = ?
                """,
                (news_id, platform_id)
            )
            result = cursor.fetchone()
            if result:
                return result[0]
            return None
            
        except Exception as e:
            logger.error(f"포스팅 상태 확인 중 오류: {e}")
        return None