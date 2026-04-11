# JeAn Finder (제안탐색기)

폴더 안 문서들의 **본문 내용**을 검색하는 Windows 프로그램. Everything이 파일명을 찾는다면, 제안탐색기는 파일 **내용**을 찾는다.

## 지원 포맷
PDF, HWP, HWPX, DOC/DOCX, PPT/PPTX, XLS/XLSX. 스캔본 PDF는 Tesseract OCR로 처리(선택).

## 개발 환경 실행

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# CLI
python -m jean_finder scan "C:\내문서"
python -m jean_finder search "검색어"
python -m jean_finder stats

# GUI
python -m jean_finder gui
```

## 테스트

```bash
pytest
```

## 패키징 (개발자용)

```bash
# 1. Tesseract 5.x + kor.traineddata + eng.traineddata 를 resources/tesseract/ 에 배치 (OCR 필요 시)
# 2. PyInstaller 로 빌드
pyinstaller build.spec
# -> dist/JeAnFinder/ 폴더 생성

# 3. Inno Setup 컴파일러로 설치 파일 생성
cd installer
iscc setup.iss
# -> installer/output/JeAnFinder_Setup_0.1.0.exe
```

## 구성 경로

- 인덱스 DB: `%LOCALAPPDATA%\JeAnFinder\index.db`
- Tesseract 경로는 `JF_TESSERACT_CMD` 환경변수 또는 번들 내부에서 자동 탐색

## 알려진 제약

- **구형 HWP(.hwp)**: 표/그림이 많은 비표준 문서는 텍스트 추출이 누락될 수 있음. HWPX(.hwpx) 권장.
- **OCR 속도**: 페이지당 수 초. 스캔본 PDF가 많으면 초기 스캔에 수 시간 소요 가능.
- **검색어 최소 길이**: trigram 토크나이저 사용으로 3자 이상 입력 권장.
