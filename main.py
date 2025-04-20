# main.py - 애플리케이션 진입점
import os
import sys
import multiprocessing

# 컴파일된 실행파일인지 확인하고 작업 디렉토리 설정
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
    os.chdir(base_dir)  # 작업 디렉토리를 exe가 있는 폴더로 변경
    # 컴파일된 환경에서 멀티프로세싱 설정
    multiprocessing.freeze_support()
else:
    base_dir = os.getcwd()

# 필요한 디렉토리 생성
def create_required_directories():
    """필요한 디렉토리 생성"""
    dirs = [
        os.path.join(base_dir, "data"),
        os.path.join(base_dir, "data", "DB"),
        os.path.join(base_dir, "data", "logs"),
        os.path.join(base_dir, "data", "images"),
        os.path.join(base_dir, "win", "TEMP", "chromeTEMP1"),
        os.path.join(base_dir, "win", "TEMP", "threadsTEMP")
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"디렉토리 확인/생성: {d}")

# 애플리케이션 시작 전 기본 디렉토리 생성 
create_required_directories()

# 모듈 경로 설정 (필요한 경우)
if getattr(sys, 'frozen', False):
    # DLL 경로 및 리소스 경로 설정 (Windows 환경)
    os.environ['PATH'] = f"{base_dir};{base_dir}\\win;{os.environ['PATH']}"

# 예외 처리가 되지 않은 예외 핸들러 (디버깅용)
def unhandled_exception_handler(exc_type, exc_value, exc_traceback):
    import traceback
    # 로그 파일에 예외 기록
    log_dir = os.path.join(base_dir, "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    try:
        from datetime import datetime
        error_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"error_{error_time}.log")
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"예외 발생 시간: {error_time}\n")
            f.write(f"예외 유형: {exc_type.__name__}\n")
            f.write(f"예외 메시지: {exc_value}\n\n")
            f.write("상세 정보:\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
        
        print(f"오류가 발생했습니다. 상세 내용은 로그 파일에 기록되었습니다: {log_file}")
    except:
        print("오류 로깅 중 추가 오류가 발생했습니다.")
    
    # 기본 예외 처리기에 예외 전달
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# 예외 핸들러 설정
sys.excepthook = unhandled_exception_handler

# 애플리케이션 메인 함수 호출
from app_core import main

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"애플리케이션 시작 중 오류 발생: {e}")
        traceback.print_exc()