import os
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

class GPTAPIHandler:
    """GPT API 통신 핸들러"""
    
    def __init__(self, base_path):
        """
        초기화
        
        Args:
            base_path (str): 애플리케이션 기본 경로
        """
        self.base_path = base_path
        self.api_dir = os.path.join(base_path, "data", "api")
        self.api_file = os.path.join(self.api_dir, "gpt_api.json")
        self.api_key = self._load_api_key()
        self.client = None
        
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
    
    def _load_api_key(self):
        """API 키 로드"""
        try:
            if os.path.exists(self.api_file):
                with open(self.api_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    api_key = data.get('api_key')
                    if api_key:
                        logger.info("GPT API 키 로드 성공")
                        return api_key
                    else:
                        logger.error("API 키 파일에 'api_key' 필드가 없거나 비어있습니다")
            else:
                logger.error(f"API 키 파일이 존재하지 않습니다: {self.api_file}")
            return None
        except Exception as e:
            logger.error(f"API 키 로드 중 오류: {e}")
            return None
    
    def reload_api_key(self):
        """API 키 재로드"""
        self.api_key = self._load_api_key()
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
        return self.api_key is not None
    
    def generate_threads(self, category, title, summary, num_threads=3):
        """
        쓰레드 메시지 생성
        
        Args:
            category (str): 뉴스 카테고리
            title (str): 뉴스 제목
            summary (str): 500자 요약
            num_threads (int): 생성할 쓰레드 수
            
        Returns:
            list or None: 생성된 쓰레드 메시지 리스트 또는 실패 시 None
        """
        if not self.client:
            logger.error("API 클라이언트가 초기화되지 않았습니다.")
            return None
            
        try:
            # 프롬프트 구성
            prompt = f"""[카테고리]: {category}
[제목]: {title}
[요약]: {summary}

위 정보를 기반으로 Twitter(X) 스타일의 감성적인 쓰레드를 작성해줘.
문장들은 짧고 줄바꿈이 많아야 하며, 이모지, 감탄사, 해시태그, 말줄임표, 구어체가 섞인 스타일이 좋아.
쓰레드는 총 {num_threads}개 항목으로 나눠줘.
각 항목은 250자 이내, 너무 길지 않게 줄바꿈 포함해서.

톤은 카테고리에 맞춰 자연스럽게 설정해줘.
각 쓰레드는 다음과 같은 형식으로 보여줘:
Thread 1: (내용)
Thread 2: (내용)
..."""

            # API 요청
            response = self.client.chat.completions.create(
                model="gpt-4",  # 임시로 gpt-4 사용 (gpt-4o 사용 시 변경 필요)
                messages=[
                    {"role": "system", "content": "너는 트위터 감성 콘텐츠 전문 작가야."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9
            )
            
            # 응답 처리
            content = response.choices[0].message.content
            
            # 쓰레드 메시지 파싱
            messages = []
            current_message = ""
            
            for line in content.split('\n'):
                if line.startswith('Thread '):
                    if current_message:
                        messages.append(current_message.strip())
                    current_message = line.split(':', 1)[1].strip()
                else:
                    if current_message or line.strip():
                        current_message += '\n' + line.strip()
            
            # 마지막 메시지 추가
            if current_message:
                messages.append(current_message.strip())
            
            # 메시지 수 확인 및 조정
            if len(messages) > num_threads:
                messages = messages[:num_threads]
            elif len(messages) < num_threads:
                logger.warning(f"생성된 쓰레드 수({len(messages)})가 요청한 수({num_threads})보다 적습니다.")
            
            return messages
            
        except Exception as e:
            logger.error(f"쓰레드 생성 중 오류: {e}")
            return None
    
    def is_api_key_valid(self):
        """API 키 유효성 검사"""
        if not self.client:
            return False
            
        try:
            # 간단한 요청으로 API 키 유효성 검사
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "user", "content": "Hello"}
                ],
                max_tokens=1
            )
            return True
        except Exception as e:
            logger.error(f"API 키 유효성 검사 중 오류: {e}")
            return False 