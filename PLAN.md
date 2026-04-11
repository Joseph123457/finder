# 제안탐색기 (JeAn Finder) 개발계획서

> **목적**: 특정 폴더 안 문서들의 **본문 내용**을 검색하는 윈도우 프로그램.
> Everything이 파일명을 찾는다면, 제안탐색기는 파일 **내용**을 찾는다.

---

## 1. 요구사항 정리

### 1.1 기능 요구사항
- 사용자가 지정한 폴더(들)를 스캔 → 문서 본문 텍스트 추출 → 인덱스에 저장
- 검색어 입력 시 인덱스에서 일치 파일을 빠르게 찾음
- 지원 포맷: **PDF, HWP, HWPX, DOC, DOCX, PPT, PPTX, XLS, XLSX**
- 스캔본 PDF는 **OCR**로 텍스트 추출 (한국어 + 영어)
- 검색 결과에 표시:
  - 파일명
  - 파일 경로(전체)
  - 수정 날짜
  - 검색어가 나온 본문 조각 (앞 10글자 + 검색어 + 뒤 10글자)
- 기본 정렬: **수정 날짜 최신순**
- 결과 항목 **우클릭** → "폴더 열기"로 해당 파일이 있는 탐색기 창을 연다
- UI는 Everything과 유사한 단순 레이아웃(상단 검색창, 하단 결과 리스트)

### 1.2 비기능 요구사항
- **배포**: 사용자는 파이썬 설치 없이 **셋업 exe 하나만 실행**하면 설치 완료
- **OS**: Windows 10/11 (64bit)
- **초기 스캔 규모**: 파일 10,000개 수준, 초기 스캔은 느려도 됨
- **검색 속도**: 인덱스 구축 후 검색은 **1~2초 이내** 목표
- **오프라인 동작**: 인터넷 없이 동작 (OCR 엔진 포함)

### 1.3 불확실성 / 리스크 (솔직 공개)
| 항목 | 리스크 | 대응 |
|---|---|---|
| 구형 HWP 추출 | pyhwp/olefile로 완벽 추출 어려움. 복잡한 문서는 텍스트 누락 가능 | 2단계에서 실제 파일로 테스트 후 판단. 필요시 대안 모색 |
| OCR 속도 | Tesseract는 페이지당 수 초. 스캔본 PDF 많으면 초기 스캔 수 시간 ~ 하루 | "OCR 사용" 옵션을 체크박스로 제공. 먼저 텍스트 PDF만 빠르게 처리 |
| OCR 정확도 | 문서 품질에 따라 70~95%로 편차 큼 | 인식률이 낮으면 검색 누락 가능성 안내 |
| 설치 파일 크기 | Tesseract + 한국어 언어팩 + Python + 라이브러리 전체 묶으면 500MB~1GB 예상 | 실제 빌드 후 확인. 크기가 문제면 Tesseract만 별도 설치로 분리 검토 |
| 첫 스캔 시간 | 10,000개 파일 + OCR이면 수 시간 | 백그라운드 스캔 + 진행률 표시 |

---

## 2. 기술 스택 (확정)

| 영역 | 선택 | 이유 |
|---|---|---|
| 언어 | **Python 3.11+** | 라이브러리 풍부, 빠른 개발 |
| GUI | **PySide6** | Qt 기반, 상용 이용 가능, 테이블 뷰 강력 |
| PDF 텍스트 | **PyMuPDF (fitz)** | 빠르고 정확, 한국어 문제 적음 |
| Word (.docx) | **python-docx** | 표준 라이브러리 |
| Word (.doc 구형) | **olefile** 또는 변환 스킵 | 구형 doc은 제한적 지원 (리스크 표시) |
| Excel (.xlsx) | **openpyxl** | 표준 |
| Excel (.xls 구형) | **xlrd** (구버전) | 제한적 |
| PowerPoint (.pptx) | **python-pptx** | 표준 |
| HWPX | **zipfile + xml.etree** (직접 파싱) | HWPX는 ZIP+XML 구조, 라이브러리 불필요 |
| HWP (구형) | **olefile** + 자체 텍스트 추출 | 2단계에서 품질 검증 후 확정 |
| OCR | **Tesseract 5.x + pytesseract** | 오픈소스 표준, 한국어 지원 |
| OCR 전처리 | **Pillow, pdf2image** | PDF → 이미지 변환 |
| 검색 인덱스 | **SQLite FTS5** | 파이썬 내장, 전문 검색 지원, 별도 서버 불필요 |
| 스캔 병렬화 | **concurrent.futures.ProcessPoolExecutor** | CPU 병렬 처리 |
| 파일 감시 | (선택) **watchdog** | 2차 버전에서 자동 재인덱싱 |
| exe 빌드 | **PyInstaller** | 표준 도구 |
| 셋업 파일 | **Inno Setup** | 무료, 한국어 지원, 표준 윈도우 셋업 마법사 생성 |

**중요**: Tesseract 엔진 자체는 파이썬 라이브러리가 아니라 별도 exe 바이너리입니다. PyInstaller 빌드 시 Tesseract 실행파일과 한국어 언어 데이터(kor.traineddata)를 함께 패키징해야 합니다.

---

## 3. 폴더 구조

```
C:\Projects\finder\
├── PLAN.md                    # 이 문서
├── README.md                  # 사용자용 간단 설명
├── requirements.txt           # 파이썬 의존성
├── pyproject.toml             # 프로젝트 메타
│
├── src/
│   └── jean_finder/
│       ├── __init__.py
│       ├── main.py            # 진입점
│       │
│       ├── core/              # 핵심 로직 (GUI 독립)
│       │   ├── __init__.py
│       │   ├── config.py      # 설정 (DB 위치, OCR 경로 등)
│       │   ├── database.py    # SQLite FTS5 관리
│       │   ├── scanner.py     # 폴더 순회, 파일 디스패치
│       │   ├── indexer.py     # 스캔 오케스트레이션
│       │   └── searcher.py    # 검색 쿼리 + 스니펫 추출
│       │
│       ├── extractors/        # 포맷별 텍스트 추출기
│       │   ├── __init__.py
│       │   ├── base.py        # 추상 베이스
│       │   ├── pdf.py         # PyMuPDF + OCR 폴백
│       │   ├── docx.py
│       │   ├── xlsx.py
│       │   ├── pptx.py
│       │   ├── hwpx.py
│       │   ├── hwp.py         # 구형 HWP (리스크 있음)
│       │   └── registry.py    # 확장자 → 추출기 매핑
│       │
│       ├── ocr/
│       │   ├── __init__.py
│       │   └── tesseract.py   # Tesseract 래퍼
│       │
│       └── gui/
│           ├── __init__.py
│           ├── main_window.py # 메인 창
│           ├── search_bar.py  # 상단 검색창
│           ├── result_view.py # 결과 테이블 + 우클릭 메뉴
│           ├── scan_dialog.py # 폴더 추가/스캔 진행 다이얼로그
│           └── settings_dialog.py
│
├── tests/
│   ├── test_extractors/
│   │   └── samples/           # 테스트용 샘플 문서
│   └── test_searcher.py
│
├── resources/
│   ├── icon.ico
│   └── tesseract/             # 빌드 시 Tesseract 바이너리 복사 위치
│
├── build/                     # PyInstaller 빌드 산출물
└── installer/
    ├── setup.iss              # Inno Setup 스크립트
    └── output/                # 최종 setup.exe 출력 위치
```

---

## 4. 데이터 모델 (SQLite FTS5)

```sql
-- 파일 메타데이터
CREATE TABLE files (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,     -- 전체 경로
    filename    TEXT NOT NULL,
    folder      TEXT NOT NULL,             -- 부모 폴더
    ext         TEXT NOT NULL,             -- 확장자 (소문자)
    size        INTEGER NOT NULL,
    mtime       INTEGER NOT NULL,          -- 수정시각 (unix epoch)
    indexed_at  INTEGER NOT NULL,          -- 인덱싱 시각
    hash        TEXT,                      -- 내용 해시 (재스캔 스킵용)
    status      TEXT NOT NULL              -- ok / error / unsupported
);

CREATE INDEX idx_files_mtime ON files(mtime DESC);
CREATE INDEX idx_files_folder ON files(folder);

-- 전문 검색 (FTS5)
CREATE VIRTUAL TABLE file_contents USING fts5(
    content,
    content_rowid = id,
    tokenize = 'unicode61'
);

-- 스캔 대상 폴더
CREATE TABLE scan_roots (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    added_at    INTEGER NOT NULL,
    last_scan   INTEGER
);
```

**스니펫 추출**: FTS5의 `snippet()` 함수로 검색어 주변 텍스트를 얻음. 요구사항은 "앞 10자 + 뒤 10자"이지만, FTS5 snippet은 단어 단위라 글자 수가 정확히 10자가 아닐 수 있음. → 검색 후 파이썬에서 문자 단위로 재가공하여 정확히 앞/뒤 10자로 맞춤.

---

## 5. 개발 단계 (Milestone)

### ✅ M1. 프로젝트 초기화 (0.5일)
- [ ] `C:\Projects\finder` 폴더 및 구조 생성
- [ ] 가상환경 `.venv` 생성
- [ ] `requirements.txt` 작성 및 설치
- [ ] Git 초기화
- [ ] `main.py`에 "Hello JeAn Finder" 출력 확인

**완료 기준**: `python -m jean_finder` 실행 시 에러 없이 종료

---

### M2. 텍스트 추출기 구현 (2~3일)
각 포맷 추출기를 순서대로 구현 + 단위 테스트.

- [ ] `base.py`: 추상 추출기 인터페이스 정의
- [ ] `registry.py`: 확장자 → 추출기 매핑
- [ ] `pdf.py` (PyMuPDF만, OCR은 M5에서 추가)
- [ ] `docx.py`
- [ ] `xlsx.py`
- [ ] `pptx.py`
- [ ] `hwpx.py` (ZIP 풀어서 section*.xml 파싱)
- [ ] `hwp.py` (olefile 기반, **실제 HWP 파일로 검증 필수**)
- [ ] 각 추출기별 `tests/test_extractors/samples/`에 샘플 파일 배치 후 테스트

**완료 기준**:
- 각 포맷 샘플 파일에서 텍스트가 추출되어 콘솔에 출력됨
- HWP 추출 품질 체크리스트 작성 (어떤 요소가 되고 안 되는지 명확히 기록)

**⚠️ HWP 검증 지점**: 사용자님이 제공할 실제 HWP 파일 5~10개로 테스트. 추출 실패/품질 미흡한 경우 대안 검토(예: 한글 설치 여부 확인 후 COM 자동화).

---

### M3. 인덱서 + 검색 엔진 (2일)
- [ ] `database.py`: SQLite 스키마 생성 + CRUD
- [ ] `scanner.py`: 폴더 재귀 순회 + 확장자 필터
- [ ] `indexer.py`: 파일 → 추출기 → DB 저장 파이프라인
- [ ] `searcher.py`: FTS5 검색 + 스니펫 추출 (앞/뒤 10자)
- [ ] 병렬 처리 (`ProcessPoolExecutor`) 적용
- [ ] 진행률 콜백 (GUI 연동 준비)
- [ ] CLI로 스캔/검색 동작 확인

**완료 기준**:
```bash
python -m jean_finder scan C:\TestDocs
python -m jean_finder search "검색어"
# → 경로, 수정날짜, 스니펫 출력
```

---

### M4. GUI 구현 (2~3일)
- [ ] `main_window.py`: Everything 스타일 레이아웃
  - 상단: 검색창 + "폴더 추가" 버튼 + "설정" 버튼
  - 하단: 결과 테이블 (컬럼: 파일명 / 스니펫 / 폴더 / 수정일)
  - 하단 상태바: 인덱싱된 파일 수, 진행률
- [ ] 실시간 검색 (입력할 때마다 debounce 후 쿼리)
- [ ] 기본 정렬: 수정일 DESC, 컬럼 헤더 클릭 시 재정렬
- [ ] 결과 우클릭 메뉴:
  - "폴더 열기" → `os.startfile(folder)` 또는 `explorer /select,"path"`
  - "파일 열기"
  - "경로 복사"
- [ ] 더블클릭 → 파일 열기
- [ ] 스캔 다이얼로그: 진행률 바, 현재 처리 파일명 표시, 취소 가능

**완료 기준**: 개발 PC에서 실제 폴더 스캔 → 검색 → 폴더 열기까지 end-to-end 동작

---

### M5. OCR 통합 (1~2일)
- [ ] `ocr/tesseract.py`: pytesseract 래퍼
- [ ] `extractors/pdf.py`에 OCR 폴백 로직 추가
  - PyMuPDF로 먼저 텍스트 추출 시도
  - 추출된 글자 수가 임계치(예: 페이지당 20자) 미만이면 스캔본으로 판단
  - 해당 페이지를 `pdf2image`로 이미지화 → Tesseract로 OCR
- [ ] 설정 다이얼로그에 "OCR 사용" 체크박스
- [ ] OCR 진행 시 페이지별 로그

**완료 기준**: 스캔본 PDF에서 텍스트가 추출되어 검색 가능

---

### M6. 패키징 + 배포 (1~2일)
- [ ] PyInstaller spec 파일 작성
  - Tesseract 바이너리 + `kor.traineddata`, `eng.traineddata` 번들
  - PySide6 플러그인 포함
  - 아이콘 지정
- [ ] `pyinstaller build.spec` 로 `dist\JeAnFinder\` 폴더 생성 확인
- [ ] Inno Setup 스크립트 (`setup.iss`) 작성
  - 설치 경로: `C:\Program Files\JeAnFinder`
  - 시작 메뉴 바로가기, 바탕화면 바로가기
  - 언인스톨러 자동 포함
- [ ] `iscc setup.iss` 로 `installer\output\JeAnFinder_Setup.exe` 생성
- [ ] **깨끗한 가상머신 또는 다른 PC에서 설치 → 실행 → 기본 시나리오 테스트**

**완료 기준**: 파이썬 없는 PC에 셋업 exe 설치 → 정상 동작

---

### (선택) M7. 품질 개선
- [ ] 파일 감시 (watchdog) — 폴더 변경 시 자동 재인덱싱
- [ ] 검색 결과 하이라이팅
- [ ] 다크 모드
- [ ] 필터 (확장자별, 날짜 범위)
- [ ] 인덱스 통계 / 관리 화면

---

## 6. 예상 일정

| 단계 | 소요 (실제 개발 시간) |
|---|---|
| M1. 초기화 | 반나절 |
| M2. 추출기 | 2~3일 |
| M3. 인덱서/검색 | 2일 |
| M4. GUI | 2~3일 |
| M5. OCR | 1~2일 |
| M6. 패키징 | 1~2일 |
| **합계** | **약 9~13일** |

Claude Code와 함께 진행하면 체감 시간은 이보다 짧을 수 있지만, 테스트·디버깅 시간을 여유있게 잡는 것이 안전합니다.

---

## 7. Claude Code 진행 시 권장 순서

각 마일스톤은 **독립 세션**으로 진행하는 것을 권장합니다.
- 세션 1: M1 + M2 (추출기가 되는지 먼저 확인 — 가장 불확실한 HWP 포함)
- 세션 2: M3 (DB + 검색)
- 세션 3: M4 (GUI)
- 세션 4: M5 (OCR)
- 세션 5: M6 (패키징)

**각 세션 시작 시 Claude Code에게 전달할 내용**:
1. `PLAN.md` 전체
2. 이번 세션에서 진행할 마일스톤 번호
3. 직전 마일스톤의 산출물 상태

---

## 8. 확인이 필요한 열린 질문

1. **HWP 테스트 파일**: M2에서 사용할 실제 HWP 파일 5~10개 준비 부탁드립니다. (다양한 종류가 좋음 — 표 있는 것, 그림 있는 것, 단순 텍스트 등)
2. **기본 스캔 폴더**: 처음 실행 시 기본 추가할 폴더가 있나요? 아니면 사용자가 직접 추가해야 하나요?
3. **아이콘**: 프로그램 아이콘 이미지 있으신가요? 없으면 임시 아이콘으로 시작하고 나중에 교체 가능합니다.
4. **프로그램 영문명**: 패키징 시 내부 이름으로 `JeAnFinder`를 가안으로 썼습니다. 다른 이름 원하시면 알려주세요.
5. **구형 .doc / .xls / .ppt** 파일도 지원 필요하세요? (현대 포맷보다 처리가 까다롭고 라이브러리 지원이 제한적입니다)

---

## 9. 할루시네이션 방지 체크포인트

이 계획서에서 "확실하다"고 쓴 부분과 "불확실하다"고 쓴 부분을 다시 명시합니다:

**✅ 확실 (표준 라이브러리, 실무 검증됨)**:
- PyMuPDF로 일반 PDF 텍스트 추출
- python-docx, openpyxl, python-pptx 로 Office 포맷 추출
- SQLite FTS5 전문 검색
- PySide6 GUI
- PyInstaller + Inno Setup 패키징
- Tesseract 한국어 OCR 동작 (정확도는 별개)

**⚠️ 불확실 (실측 필요)**:
- 구형 HWP(.hwp) 추출 품질 — M2에서 실제 파일로 검증
- 구형 .doc/.xls/.ppt 추출 — 필요 여부부터 결정
- 최종 설치 파일 크기 — 빌드 후 실측
- OCR 전체 스캔 소요 시간 — 실제 문서 양과 품질에 좌우
- Tesseract 한국어 OCR 정확도 — 문서 품질에 따라 편차 큼

개발 중 위 불확실 영역에서 예상과 다른 결과가 나오면 **즉시 공유하고 대안을 논의**합니다.
