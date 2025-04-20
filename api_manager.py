import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import logging
from datetime import datetime

class APIManagerUI:
    """API 관리 UI 모듈"""
    
    def __init__(self, parent):
        """
        API 관리 UI 초기화
        
        Args:
            parent: 부모 애플리케이션 객체
        """
        self.parent = parent
        self.base_path = parent.base_path
        self.db_manager = parent.db_manager
        self.logger = parent.logger
        self.main_frame = parent.api_tab  # API 탭으로 설정
        
        # API 저장 폴더 생성
        self.api_dir = os.path.join(self.base_path, "data", "api")
        os.makedirs(self.api_dir, exist_ok=True)
        
        # API 파일 경로 설정
        self.gpt_api_file = os.path.join(self.api_dir, "gpt_api.json")
        self.perplexity_api_file = os.path.join(self.api_dir, "perplexity_api.json")
        
        # API 상태 변수
        self.gpt_api_status = self.check_api_status(self.gpt_api_file)
        self.perplexity_api_status = self.check_api_status(self.perplexity_api_file)
        
        # UI 생성
        self.create_widgets()
        
        # 로그 초기화
        self.logger.info("API 관리 탭이 초기화되었습니다.")

        # API 상태 변경 이벤트 콜백 리스트 추가
        self.api_status_change_callbacks = []


    def register_status_callback(self, callback_func):
        """API 상태 변경 알림을 받을 콜백 함수 등록
        
        Args:
            callback_func (callable): 호출될 콜백 함수
        """
        if callable(callback_func) and callback_func not in self.api_status_change_callbacks:
            self.api_status_change_callbacks.append(callback_func)
            self.logger.info(f"API 상태 변경 콜백 함수 등록: {callback_func.__name__}")
    
    def notify_status_change(self):
        """등록된 모든 콜백 함수에 API 상태 변경 알림"""
        for callback_func in self.api_status_change_callbacks:
            try:
                callback_func()
            except Exception as e:
                self.logger.error(f"API 상태 변경 콜백 함수 호출 중 오류: {e}")

    def save_api_key(self, api_file, api_key, status_text, entry_widget, key_var):
        """
        API 키 저장
        
        Args:
            api_file (str): 저장할 파일 경로
            api_key (str): API 키
            status_text (tk.Text): 상태 텍스트 위젯
            entry_widget (ttk.Entry): 입력 필드 위젯
            key_var (tk.StringVar): 입력 필드 변수
        """
        try:
            if not api_key or api_key.strip() == "":
                messagebox.showerror("오류", "API 키를 입력해주세요.")
                return False
            
            # API 키와 저장 시간 함께 저장
            data = {
                "api_key": api_key,
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(api_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # 상태 업데이트
            self.update_status_text(status_text, "입력 완료")
            
            # 입력 필드 비활성화 및 내용 지우기
            entry_widget.config(state="disabled")
            key_var.set("")  # 입력 필드 내용 지우기
            
            self.logger.info(f"API 키가 {api_file}에 저장되었습니다.")

            # API 상태 변경 알림 추가
            self.notify_status_change()
            
            return True
        except Exception as e:
            self.logger.error(f"API 키 저장 중 오류: {e}")
            messagebox.showerror("오류", f"API 키 저장 중 오류가 발생했습니다: {e}")
            return False
    
    def delete_api_key(self, api_file, status_text, entry_widget, key_var):
        """
        API 키 삭제
        
        Args:
            api_file (str): 삭제할 파일 경로
            status_text (tk.Text): 상태 텍스트 위젯
            entry_widget (ttk.Entry): 입력 필드 위젯
            key_var (tk.StringVar): 입력 필드 변수
        """
        try:
            # 파일이 없으면 이미 삭제된 상태
            if not os.path.exists(api_file):
                self.update_status_text(status_text, "비어 있음")
                return True
            
            # 삭제 확인
            if not messagebox.askyesno("확인", "API 키를 삭제하시겠습니까?"):
                return False
            
            # 파일 삭제
            os.remove(api_file)
            
            # 상태 업데이트
            self.update_status_text(status_text, "비어 있음")
            
            # 입력 필드 활성화
            entry_widget.config(state="normal")
            key_var.set("")  # 입력 필드 내용 지우기
            
            self.logger.info(f"API 키가 {api_file}에서 삭제되었습니다.")

            # API 상태 변경 알림 추가
            self.notify_status_change()
            
            return True
        except Exception as e:
            self.logger.error(f"API 키 삭제 중 오류: {e}")
            messagebox.showerror("오류", f"API 키 삭제 중 오류가 발생했습니다: {e}")
            return False
    
    def create_widgets(self):
        """API 관리 UI 위젯 생성 - 입력 섹션만 가로로 배치하고 하단은 빈 공간으로 남김"""
        # 메인 프레임 설정
        main_container = ttk.Frame(self.main_frame, padding=10)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # 타이틀 레이블
        title_label = ttk.Label(main_container, text="API 키 관리", font=("", 12, "bold"))
        title_label.pack(fill=tk.X, pady=(0, 10))
        
        # 설명 텍스트
        description = ttk.Label(main_container, 
                               text="API 키를 안전하게 저장하고 관리합니다. 입력된 키는 로컬에 저장됩니다.",
                               wraplength=500)
        description.pack(fill=tk.X, pady=(0, 10))
        
        # 수평 레이아웃을 위한 컨테이너 프레임 (입력 부분만 포함)
        api_container = ttk.Frame(main_container)
        api_container.pack(fill=tk.X, expand=False, pady=10)  # expand=False로 설정하여 필요한 크기만 차지하도록 함
        
        # 왼쪽 프레임 (GPT API)
        left_frame = ttk.Frame(api_container)
        left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # 오른쪽 프레임 (Perplexity API)
        right_frame = ttk.Frame(api_container)
        right_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))
        
        # GPT API 입력 섹션 (왼쪽)
        self.create_api_input_section(left_frame, "GPT API 키", 
                                     "OpenAI GPT 모델 사용을 위한 API 키",
                                     self.gpt_api_status,
                                     self.save_gpt_api,
                                     self.delete_gpt_api)
        
        # Perplexity API 입력 섹션 (오른쪽)
        self.create_api_input_section(right_frame, "Perplexity API 키", 
                                     "Perplexity AI 서비스 사용을 위한 API 키",
                                     self.perplexity_api_status,
                                     self.save_perplexity_api,
                                     self.delete_perplexity_api)
        
        # 구분선
        separator = ttk.Separator(main_container, orient="horizontal")
        separator.pack(fill=tk.X, pady=20)
        
        # 향후 기능을 위한 빈 영역 프레임
        future_frame = ttk.Frame(main_container)
        future_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # 참고 메시지 - 하단에 위치
        note_frame = ttk.Frame(main_container)
        note_frame.pack(fill=tk.X, pady=(20, 0), side=tk.BOTTOM)
        
        note_label = ttk.Label(note_frame, 
                              text="참고: API 키는 로컬 시스템의 'data/api' 폴더에 저장됩니다.",
                              font=("", 9, "italic"))
        note_label.pack(side=tk.LEFT)
    
    def create_api_input_section(self, parent, title, description, status, save_func, delete_func):
        """API 입력 섹션 생성 (헤더와 입력 필드만 포함)"""
        # 섹션 프레임
        section_frame = ttk.LabelFrame(parent, text=title)
        section_frame.pack(fill=tk.BOTH, pady=5)
        
        # 설명 레이블
        desc_label = ttk.Label(section_frame, text=description)
        desc_label.pack(fill=tk.X, padx=10, pady=5)
        
        # API 입력 프레임
        input_frame = ttk.Frame(section_frame)
        input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # API 키 입력 필드
        ttk.Label(input_frame, text="API 키:").pack(side=tk.LEFT, padx=(0, 5))
        
        # API 키 변수 및 입력 필드
        api_key_var = tk.StringVar()
        api_entry = ttk.Entry(input_frame, textvariable=api_key_var, width=30, show="*")
        api_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 상태 표시 프레임
        status_frame = ttk.Frame(section_frame)
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 상태 레이블
        ttk.Label(status_frame, text="상태:").pack(side=tk.LEFT, padx=(0, 5))
        
        # 상태 텍스트 (색상 적용을 위해 Text 위젯 사용)
        status_text = tk.Text(status_frame, height=1, width=15, 
                                font=("TkDefaultFont", 9), borderwidth=0, 
                                bg=self.parent.cget('bg'))
        status_text.pack(side=tk.LEFT, fill=tk.X)
        status_text.insert(tk.END, status)
        
        # 읽기 전용으로 설정
        status_text.config(state=tk.DISABLED)
        
        # 텍스트 태그 생성 - 색상 설정용
        status_text.tag_configure("complete", foreground="green")
        status_text.tag_configure("empty", foreground="red")
        
        # 초기 상태에 따라 태그 적용
        status_text.config(state=tk.NORMAL)
        status_text.delete('1.0', tk.END)
        status_text.insert(tk.END, status)
        if status == "입력 완료":
            status_text.tag_add("complete", '1.0', tk.END)
            # API가 이미 저장된 경우 입력 필드 비활성화 및 내용 지우기
            api_entry.config(state="disabled")
            api_key_var.set("")  # 입력 필드 내용 지우기
        else:
            status_text.tag_add("empty", '1.0', tk.END)
        status_text.config(state=tk.DISABLED)
        
        # 버튼 프레임
        button_frame = ttk.Frame(section_frame)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # 저장/삭제 버튼
        save_button = ttk.Button(button_frame, text="저장", 
                               command=lambda: save_func(api_key_var.get(), status_text, api_entry, api_key_var))
        save_button.pack(side=tk.LEFT, padx=(0, 5))
        
        delete_button = ttk.Button(button_frame, text="삭제", 
                                 command=lambda: delete_func(status_text, api_entry, api_key_var))
        delete_button.pack(side=tk.LEFT)
        
        # 참조 저장 (객체 유지를 위해)
        setattr(self, f"{title.lower().replace(' ', '_')}_entry", api_entry)
        setattr(self, f"{title.lower().replace(' ', '_')}_status", status_text)
        setattr(self, f"{title.lower().replace(' ', '_')}_var", api_key_var)
    
    def check_api_status(self, api_file):
        """
        API 파일 존재 여부 확인
        
        Args:
            api_file (str): API 파일 경로
            
        Returns:
            str: 상태 메시지
        """
        if os.path.exists(api_file):
            try:
                with open(api_file, 'r') as f:
                    data = json.load(f)
                    if data.get('api_key'):
                        return "입력 완료"
            except:
                pass
        return "비어 있음"
    
    def update_status_text(self, status_text, new_status):
        """
        상태 텍스트 업데이트 및 색상 적용
        
        Args:
            status_text (tk.Text): 상태 텍스트 위젯
            new_status (str): 새 상태 메시지
        """
        # 텍스트 위젯을 수정 가능하게 설정
        status_text.config(state=tk.NORMAL)
        
        # 기존 내용 삭제
        status_text.delete('1.0', tk.END)
        
        # 새 내용 삽입
        status_text.insert(tk.END, new_status)
        
        # 태그 적용
        if new_status == "입력 완료":
            status_text.tag_add("complete", '1.0', tk.END)
        else:
            status_text.tag_add("empty", '1.0', tk.END)
        
        # 다시 읽기 전용으로 설정
        status_text.config(state=tk.DISABLED)
    
    def save_api_key(self, api_file, api_key, status_text, entry_widget, key_var):
        """
        API 키 저장
        
        Args:
            api_file (str): 저장할 파일 경로
            api_key (str): API 키
            status_text (tk.Text): 상태 텍스트 위젯
            entry_widget (ttk.Entry): 입력 필드 위젯
            key_var (tk.StringVar): 입력 필드 변수
        """
        try:
            if not api_key or api_key.strip() == "":
                messagebox.showerror("오류", "API 키를 입력해주세요.")
                return False
            
            # API 키와 저장 시간 함께 저장
            data = {
                "api_key": api_key,
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(api_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            # 상태 업데이트
            self.update_status_text(status_text, "입력 완료")
            
            # 입력 필드 비활성화 및 내용 지우기
            entry_widget.config(state="disabled")
            key_var.set("")  # 입력 필드 내용 지우기
            
            self.logger.info(f"API 키가 {api_file}에 저장되었습니다.")
            return True
        except Exception as e:
            self.logger.error(f"API 키 저장 중 오류: {e}")
            messagebox.showerror("오류", f"API 키 저장 중 오류가 발생했습니다: {e}")
            return False
    
    def delete_api_key(self, api_file, status_text, entry_widget, key_var):
        """
        API 키 삭제
        
        Args:
            api_file (str): 삭제할 파일 경로
            status_text (tk.Text): 상태 텍스트 위젯
            entry_widget (ttk.Entry): 입력 필드 위젯
            key_var (tk.StringVar): 입력 필드 변수
        """
        try:
            # 파일이 없으면 이미 삭제된 상태
            if not os.path.exists(api_file):
                self.update_status_text(status_text, "비어 있음")
                return True
            
            # 삭제 확인
            if not messagebox.askyesno("확인", "API 키를 삭제하시겠습니까?"):
                return False
            
            # 파일 삭제
            os.remove(api_file)
            
            # 상태 업데이트
            self.update_status_text(status_text, "비어 있음")
            
            # 입력 필드 활성화
            entry_widget.config(state="normal")
            key_var.set("")  # 입력 필드 내용 지우기
            
            self.logger.info(f"API 키가 {api_file}에서 삭제되었습니다.")
            return True
        except Exception as e:
            self.logger.error(f"API 키 삭제 중 오류: {e}")
            messagebox.showerror("오류", f"API 키 삭제 중 오류가 발생했습니다: {e}")
            return False
    
    # GPT API 키 관련 함수
    def save_gpt_api(self, api_key, status_text, entry_widget, key_var):
        """GPT API 키 저장"""
        if self.save_api_key(self.gpt_api_file, api_key, status_text, entry_widget, key_var):
            messagebox.showinfo("성공", "GPT API 키가 성공적으로 저장되었습니다.")
    
    def delete_gpt_api(self, status_text, entry_widget, key_var):
        """GPT API 키 삭제"""
        if self.delete_api_key(self.gpt_api_file, status_text, entry_widget, key_var):
            messagebox.showinfo("성공", "GPT API 키가 삭제되었습니다.")
    
    # Perplexity API 키 관련 함수
    def save_perplexity_api(self, api_key, status_text, entry_widget, key_var):
        """Perplexity API 키 저장"""
        if self.save_api_key(self.perplexity_api_file, api_key, status_text, entry_widget, key_var):
            messagebox.showinfo("성공", "Perplexity API 키가 성공적으로 저장되었습니다.")
    
    def delete_perplexity_api(self, status_text, entry_widget, key_var):
        """Perplexity API 키 삭제"""
        if self.delete_api_key(self.perplexity_api_file, status_text, entry_widget, key_var):
            messagebox.showinfo("성공", "Perplexity API 키가 삭제되었습니다.")
    
    def cleanup(self):
        """리소스 정리"""
        # 현재는 특별히 해제할 자원이 없음
        self.logger.info("API 관리 리소스 정리 완료")
        pass