# perplexity_api_handler.py
import os
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class PerplexityAPIHandler:
    """Perplexity API와 통신하여 텍스트 요약을 생성하는 클래스"""
    
    def __init__(self, base_path):
        """
        초기화 함수
        
        Args:
            base_path (str): 애플리케이션 기본 경로
        """
        self.base_path = base_path
        self.api_dir = os.path.join(base_path, "data", "api")
        self.api_file = os.path.join(self.api_dir, "perplexity_api.json")
        self.api_key = self._load_api_key()
        
    def _load_api_key(self):
        """
        API 키 로드 - 추가 로깅 포함
        
        Returns:
            str or None: API 키 또는 실패 시 None
        """
        try:
            if os.path.exists(self.api_file):
                logger.info(f"API 키 파일 경로 확인: {self.api_file} (존재함)")
                with open(self.api_file, 'r', encoding='utf-8') as f:  # 인코딩 명시
                    data = json.load(f)
                    api_key = data.get('api_key')
                    if api_key:
                        logger.info("API 키 로드 성공")
                        return api_key
                    else:
                        logger.error("API 키 파일에 'api_key' 필드가 없거나 비어있습니다")
            else:
                logger.error(f"API 키 파일이 존재하지 않습니다: {self.api_file}")
            return None
        except Exception as e:
            logger.error(f"API 키 로드 중 오류 (상세): {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
            
    def reload_api_key(self):
        """API 키 재로드"""
        self.api_key = self._load_api_key()
        return self.api_key is not None
    
    def generate_summary(self, title, category, max_retries=3):
        """
        제목과 카테고리를 기반으로 500자 요약 생성
        
        Args:
            title (str): 뉴스 제목
            category (str): 뉴스 카테고리
            max_retries (int): 최대 재시도 횟수
            
        Returns:
            str or None: 생성된 요약 또는 실패 시 None
        """
        if not self.api_key:
            logger.error("API 키가 설정되지 않았습니다.")
            return None
        
        # API 요청 URL
        url = "https://api.perplexity.ai/chat/completions"
        
        # 프롬프트 작성 - 기존 프롬프트 유지
        prompt = f"""제목: {title}

위 제목을 바탕으로, 최신 정보를 참고하여 정확히 500자 이상 600자 이하로 (공백 포함) 분량으로 핵심 내용을 작성해줘. 반드시 요청한 글자 수에 맞춰 작성할 것.  

다음 지침을 따라주세요:
1. 항상 검색을 통해 최신 정보가 있다면 그 내용을 참고하여 작성할 것
2. 트렌디하고 흥미로운 내용으로 작성할 것
3. {category} 카테고리에 맞는 적절한 톤 사용할 것
4. 전체 세대가 쉽게 공감할 수 있는 내용으로 작성
5. 불필요한 링크번호, 인용번호, 해시태그 등은 포함하지 말 것
6. 반드시 정확히 500자 이상 600자가 되도록 작성하고, 글자 수가 부족하거나 넘치지 않도록 할 것"""
        
        # HTTP 요청 헤더
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # API 요청 페이로드 - 모델명만 수정
        payload = {
            "model": "sonar-pro",
            "messages": [
                {
                    "role": "system",
                    "content": "당신은 트렌디한 온라인 뉴스 및 소셜 미디어 콘텐츠 플랫폼의 작가입니다. 젊은 독자층을 위해 가십, 연예, 스포츠, 이슈 등 다양한 카테고리의 콘텐츠를 생성합니다."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 800,
            "temperature": 0.7
        }
        
        # 재시도 로직
        for attempt in range(max_retries):
            try:
                logger.info(f"요약 생성 시도 {attempt+1}/{max_retries}: {title}")
                
                # API 요청
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                
                # 응답 처리
                if response.status_code == 200:
                    response_data = response.json()
                    
                    # 응답에서 요약 텍스트 추출
                    if 'choices' in response_data and len(response_data['choices']) > 0:
                        summary = response_data['choices'][0]['message']['content']
                        
                        # 요약 길이 확인
                        summary_length = len(summary)
                        logger.info(f"요약 생성 완료: {summary_length}자")
                        
                        if 500 <= summary_length <= 600:
                            return summary
                        else:
                            logger.warning(f"생성된 요약이 요구 길이를 만족하지 않습니다: {summary_length}자")
                            # 마지막 시도인 경우 그냥 반환
                            if attempt == max_retries - 1:
                                return summary
                    else:
                        logger.error("API 응답에서 요약을 찾을 수 없습니다.")
                else:
                    error_message = f"API 요청 실패 (상태 코드: {response.status_code}): {response.text}"
                    logger.error(error_message)
                    
                    # 모델명 오류인 경우 모델 변경 시도
                    if response.status_code == 400 and "Invalid model" in response.text:
                        # 대체 모델 목록
                        alternative_models = ["sonar-pro", "mistral-7b-instruct", "llama-3-70b-instruct", "mixtral-8x7b-instruct"]
                        current_model = payload["model"]
                        
                        # 현재 모델이 실패하면 다음 모델로 시도
                        if current_model in alternative_models:
                            next_index = (alternative_models.index(current_model) + 1) % len(alternative_models)
                            payload["model"] = alternative_models[next_index]
                            logger.info(f"모델 변경 시도: {current_model} -> {payload['model']}")
                        
                    # 인증 오류인 경우 API 키 재로드 시도
                    elif response.status_code == 401:
                        logger.warning("API 키 인증 오류. API 키 재로드 시도.")
                        if self.reload_api_key():
                            headers["Authorization"] = f"Bearer {self.api_key}"
                        else:
                            logger.error("유효한 API 키를 로드할 수 없습니다.")
                            return None
            
            except Exception as e:
                logger.error(f"요약 생성 중 오류: {e}")
                
                # 마지막 시도인 경우
                if attempt == max_retries - 1:
                    return None
        
        return None
    
    def is_api_key_valid(self):
        """
        API 키 유효성 검사
        
        Returns:
            bool: API 키가 유효하면 True, 그렇지 않으면 False
        """
        if not self.api_key:
            return False
        
        # 간단한 요청으로 API 키 유효성 검사
        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # 최소한의 요청 페이로드 - 모델명 수정
        payload = {
            "model": "sonar-pro",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello"
                }
            ],
            "max_tokens": 1  # 토큰 수를 최소화하여 비용 절감
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"API 키 유효성 검사 중 오류: {e}")
            return False