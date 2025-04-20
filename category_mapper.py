# category_mapper.py
import os
import re
import logging
import json
from urllib.parse import urlparse, parse_qs

class CategoryMapper:
    """뉴스픽 URL에서 카테고리 정보를 추출하고 매핑하는 클래스"""
    
    def __init__(self, base_path):
        """
        초기화 함수
        
        Args:
            base_path (str): 애플리케이션 기본 경로
        """
        self.base_path = base_path
        self.logger = logging.getLogger(__name__)
        
        # 카테고리 매핑 파일 경로
        self.mapping_file = os.path.join(self.base_path, "data", "DB", "category_mapping.json")
        
        # 기본 카테고리 매핑 정보
        self.default_mapping = {
            # URL 해시값 -> 카테고리명
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
            "38": "NNA코리아",
            "39": "글로벌",
            "1": "메인"
        }
        
        # 디폴트 카테고리 값
        self.default_category = "기타"
        
        # 카테고리 매핑 로드 - 매핑 파일이 없으면 기본값으로 초기화
        self.category_mapping = self.load_mapping()
        
        # 매핑이 비어있거나 필수 매핑이 누락된 경우 기본값으로 초기화
        if not self.category_mapping or not self._validate_mapping():
            self.logger.warning("카테고리 매핑이 비어있거나 유효하지 않습니다. 기본값으로 초기화합니다.")
            self.category_mapping = self.default_mapping.copy()
            self.save_mapping()


    # 추가: 매핑 유효성 검사 함수
    def _validate_mapping(self):
        """
        카테고리 매핑의 유효성 검사
        
        Returns:
            bool: 유효한 매핑이면 True, 아니면 False
        """
        # 매핑 값이 비어있는지 확인
        for category_id, category_name in self.category_mapping.items():
            if not category_name or category_name.strip() == "":
                self.logger.warning(f"카테고리 ID {category_id}의 매핑값이 비어있습니다.")
                return False
        
        # 필수 카테고리 ID가 있는지 확인 (최소한 하나는 있어야 함)
        required_ids = ["31", "36", "53"]  # 정치, 연예가화제, 영화
        found = False
        for required_id in required_ids:
            if required_id in self.category_mapping:
                found = True
                break
        
        if not found:
            self.logger.warning("필수 카테고리 ID가 없습니다.")
            return False
        
        return True
        
    def load_mapping(self):
        """
        카테고리 매핑 정보 로드
        
        Returns:
            dict: 카테고리 매핑 정보
        """
        try:
            if os.path.exists(self.mapping_file):
                with open(self.mapping_file, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                
                # 매핑 결과 상세 로깅
                self.logger.info(f"카테고리 매핑 정보 {len(mapping)} 개 로드 완료")
                for category_id, category_name in mapping.items():
                    if not category_name or category_name.strip() == "":
                        self.logger.warning(f"카테고리 ID {category_id}의 매핑값이 비어있습니다.")
                    else:
                        self.logger.info(f"로드된 카테고리 매핑: {category_id} -> {category_name}")
                
                return mapping
            else:
                # 파일이 없으면 기본 매핑 정보 저장 후 반환
                os.makedirs(os.path.dirname(self.mapping_file), exist_ok=True)
                self.save_mapping(self.default_mapping)
                self.logger.info(f"기본 카테고리 매핑 정보 {len(self.default_mapping)} 개 생성")
                for category_id, category_name in self.default_mapping.items():
                    self.logger.info(f"기본 카테고리 매핑: {category_id} -> {category_name}")
                return self.default_mapping
        except Exception as e:
            self.logger.error(f"카테고리 매핑 정보 로드 중 오류: {e}")
            return self.default_mapping.copy()
    
    def save_mapping(self, mapping=None):
        """
        카테고리 매핑 정보 저장
        
        Args:
            mapping (dict, optional): 저장할 매핑 정보. 기본값은 현재 매핑 정보.
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            # 저장할 매핑 정보가 없으면 현재 매핑 정보 사용
            if mapping is None:
                mapping = self.category_mapping
            
            # 디렉토리 생성
            os.makedirs(os.path.dirname(self.mapping_file), exist_ok=True)
            
            # 매핑 정보 저장
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"카테고리 매핑 정보 {len(mapping)} 개 저장 완료")
            return True
        except Exception as e:
            self.logger.error(f"카테고리 매핑 정보 저장 중 오류: {e}")
            return False
    
    def extract_category_id(self, url):
        """
        URL에서 카테고리 ID 추출
        
        Args:
            url (str): 뉴스픽 URL
            
        Returns:
            str: 카테고리 ID 또는 None
        """
        try:
            # 해시태그 추출 - /main/index#89 형식
            if '#' in url:
                category_id = url.split('#')[-1]
                return category_id
            
            # channelNo 파라미터 추출 - ?channelNo=89 형식
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            
            if 'channelNo' in query_params:
                return query_params['channelNo'][0]
            
            return None
        except Exception as e:
            self.logger.error(f"카테고리 ID 추출 중 오류: {e}")
            return None
    
    def get_category_name(self, url):
        """
        URL에서 카테고리명 추출
        
        Args:
            url (str): 뉴스픽 URL
            
        Returns:
            str: 카테고리명 또는 기본 카테고리명
        """
        try:
            # 카테고리 ID 추출
            category_id = self.extract_category_id(url)
            
            if not category_id:
                return self.default_category
            
            # 카테고리 매핑에서 카테고리명 찾기
            return self.category_mapping.get(category_id, self.default_category)
        except Exception as e:
            self.logger.error(f"카테고리명 추출 중 오류: {e}")
            return self.default_category
    
    def update_mapping(self, category_id, category_name):
        """
        카테고리 매핑 정보 업데이트
        
        Args:
            category_id (str): 카테고리 ID
            category_name (str): 카테고리명
            
        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            # 카테고리 매핑 업데이트
            self.category_mapping[category_id] = category_name
            
            # 매핑 정보 저장
            return self.save_mapping()
        except Exception as e:
            self.logger.error(f"카테고리 매핑 정보 업데이트 중 오류: {e}")
            return False
    
    def update_from_html(self, html_content):
        """
        HTML 내용에서 카테고리 매핑 정보 업데이트
        
        Args:
            html_content (str): HTML 내용
            
        Returns:
            int: 업데이트된 매핑 수
        """
        try:
            # 카테고리 매핑 정보 추출 패턴 - 더 넓은 범위의 패턴으로 수정
            pattern_hash = r'href="[^"]*index#(\d+)[^"]*"[^>]*>([^<]+)<'
            pattern_channel = r'href="[^"]*channelNo=(\d+)[^"]*"[^>]*>([^<]+)<'
            
            # 두 가지 패턴으로 매칭 시도
            matches_hash = re.findall(pattern_hash, html_content)
            matches_channel = re.findall(pattern_channel, html_content)
            
            # 모든 매치 결과 합치기
            all_matches = matches_hash + matches_channel
            
            self.logger.info(f"패턴 매칭 결과: 해시태그 {len(matches_hash)}개, channelNo {len(matches_channel)}개")
            
            # 매핑 정보 업데이트
            update_count = 0
            for category_id, category_name in all_matches:
                category_name = category_name.strip()
                # 이모지와 같은 특수 텍스트 제거
                category_name = re.sub(r'[🆕📺🎬⚽⚾🐱]', '', category_name).strip()
                
                # 변경: 빈 값으로 업데이트하지 않음
                if not category_name:
                    self.logger.warning(f"카테고리 ID {category_id}의 이름이 비어있어 업데이트하지 않습니다.")
                    continue
                    
                if category_id in self.category_mapping and self.category_mapping[category_id] == category_name:
                    continue
                
                self.category_mapping[category_id] = category_name
                update_count += 1
                self.logger.info(f"카테고리 매핑 업데이트: {category_id} -> {category_name}")
            
            # 매핑 정보 저장
            if update_count > 0:
                self.save_mapping()
                self.logger.info(f"{update_count}개의 카테고리 매핑 정보 업데이트")
            
            return update_count
        except Exception as e:
            self.logger.error(f"HTML에서 카테고리 매핑 정보 업데이트 중 오류: {e}")
            return 0

    # 추가: 기본 매핑으로 강제 초기화하는 함수
    def reset_to_default_mapping(self):
        """
        카테고리 매핑을 기본값으로 강제 초기화
        
        Returns:
            bool: 성공 여부
        """
        try:
            self.category_mapping = self.default_mapping.copy()
            success = self.save_mapping()
            
            # 카테고리 매핑 결과 로깅
            if success:
                self.logger.info(f"카테고리 매핑을 기본값으로 초기화했습니다. ({len(self.default_mapping)}개)")
                for category_id, category_name in self.default_mapping.items():
                    self.logger.info(f"초기화된 카테고리 매핑: {category_id} -> {category_name}")
            
            return success
        except Exception as e:
            self.logger.error(f"카테고리 매핑 초기화 중 오류: {e}")
            return False
    
    def get_all_mappings(self):
        """
        모든 카테고리 매핑 정보 반환
        
        Returns:
            dict: 카테고리 ID -> 카테고리명 매핑
        """
        return self.category_mapping.copy()

# 사용 예시
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.INFO)
    
    # 현재 디렉토리를 기본 경로로 사용
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    # 카테고리 매퍼 인스턴스 생성
    mapper = CategoryMapper(base_path)
    
    # URL에서 카테고리명 추출 테스트
    test_urls = [
        "https://partners.newspic.kr/main/index#89",
        "https://partners.newspic.kr/category/categoryDetail?channelNo=89&recent=true",
        "https://example.com"
    ]
    
    for url in test_urls:
        category_name = mapper.get_category_name(url)
        print(f"URL: {url} -> 카테고리: {category_name}")
    
    # 모든 매핑 정보 출력
    print("\n모든 카테고리 매핑 정보:")
    for category_id, category_name in mapper.get_all_mappings().items():
        print(f"{category_id}: {category_name}")
