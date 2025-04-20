# File: image_processor.py
import os
import logging
from PIL import Image
import requests
from io import BytesIO

logger = logging.getLogger(__name__)

class ImageProcessor:
    """
    이미지 다운로드 및 처리를 위한 클래스
    500x500 크기로 이미지를 조정하고 필요시 패딩 또는 크롭 수행
    """
    def __init__(self, base_path):
        self.base_path = base_path
        self.target_size = (500, 500)
        self.images_dir = os.path.join(base_path, "data", "images")  # data/images 폴더로 변경
        os.makedirs(self.images_dir, exist_ok=True)

    def download_image(self, image_url, timeout=10):
        """
        이미지 URL에서 이미지 다운로드
        
        Args:
            image_url (str): 다운로드할 이미지 URL
            timeout (int): 요청 타임아웃 (초)
            
        Returns:
            PIL.Image or None: 다운로드된 이미지 객체 또는 실패 시 None
        """
        try:
            # 일반적인 브라우저처럼 보이는 헤더 추가
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
                'Referer': 'https://fmkorea.com/',  # 이미지 출처 사이트로 보이는 리퍼러
                'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
            
            # 도메인별 리퍼러 설정
            if 'cboard.net' in image_url:
                headers['Referer'] = 'https://fmkorea.com/'
            elif 'image.fmkorea.com' in image_url:
                headers['Referer'] = 'https://fmkorea.com/'
            # 필요에 따라 다른 도메인에 대한 리퍼러 추가
            
            response = requests.get(image_url, timeout=timeout, headers=headers)
            
            if response.status_code != 200:
                logger.warning(f"이미지 다운로드 실패 (상태 코드: {response.status_code}): {image_url}")
                return None
                
            return Image.open(BytesIO(response.content))
            
        except Exception as e:
            logger.error(f"이미지 다운로드 중 오류: {e}")
            return None

    def process_image(self, image_src, row_index):
        """
        이미지 다운로드 후 가로 500px 기준으로 크기 조절,
        세로가 500px 미만이면 패딩, 500px 초과이면 중앙 크롭하여 500x500로 조정.
        
        Args:
            image_src (str): 이미지 URL 또는 파일 경로
            row_index (int): 엑셀에서 해당 행 인덱스 (이미지 저장 폴더 구분용)
            
        Returns:
            str or None: 처리된 이미지의 저장 경로 또는 실패 시 None
        """
        try:
            # 로컬 파일인지 URL인지 확인
            if os.path.exists(image_src):
                # 로컬 파일인 경우
                img = Image.open(image_src)
            elif image_src.startswith(('http://', 'https://')):
                # URL인 경우
                img = self.download_image(image_src)
                if img is None:
                    return None
            else:
                logger.warning(f"이미지 파일/URL이 유효하지 않습니다: {image_src}")
                return None
                
            # 원본 이미지 크기
            width, height = img.size
            logger.info(f"원본 이미지 크기: {width}x{height}")
            
            # 가로 500px 기준으로 크기 조절
            if width != 500:
                ratio = 500 / width
                new_height = int(height * ratio)
                img = img.resize((500, new_height), Image.LANCZOS)
                width, height = img.size
                logger.info(f"이미지 가로 크기 조정: {width}x{height}")
            
            # 세로 크기에 따른 처리
            if height < 500:
                # 500px 미만인 경우 패딩 추가
                new_img = Image.new("RGB", (500, 500), (255, 255, 255))
                paste_y = (500 - height) // 2
                new_img.paste(img, (0, paste_y))
                img = new_img
                logger.info(f"이미지 패딩 추가: 세로 {height} -> 500px")
            elif height > 500:
                # 500px 초과인 경우 중앙 크롭
                crop_top = (height - 500) // 2
                img = img.crop((0, crop_top, 500, crop_top + 500))
                logger.info(f"이미지 세로 크롭: {height} -> 500px")
            
            # 저장 경로 설정
            save_dir = os.path.join(self.images_dir, f"row_{row_index+2}")
            os.makedirs(save_dir, exist_ok=True)
            
            # 파일명 설정 (URL인 경우 고유 타임스탬프 사용)
            if os.path.exists(image_src):
                filename = "processed_" + os.path.basename(image_src)
            else:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"image_{timestamp}.jpg"
            
            # 저장 전에 모드 변환 (P 모드를 RGB로 변환)
            if img.mode in ('P', 'RGBA'):
                img = img.convert('RGB')
                
            save_path = os.path.join(save_dir, filename)
            img.save(save_path)
            logger.info(f"이미지 처리 완료: {save_path}")
            
            return save_path
            
        except Exception as e:
            logger.error(f"이미지 처리 중 오류: {e}")
            return None