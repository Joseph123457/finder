from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from jean_finder import __app_name__, __version__
from jean_finder.core.config import AppConfig
from jean_finder.core.database import Database
from jean_finder.core.indexer import Indexer, IndexProgress
from jean_finder.core.searcher import SearchHit, Searcher


# ----- 결과 테이블 모델 ------------------------------------------------------

COLUMNS = ("파일명", "스니펫", "폴더", "수정일")


class ResultModel(QAbstractTableModel):
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._hits: List[SearchHit] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._hits)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return COLUMNS[section]
        return section + 1

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        hit = self._hits[index.row()]
        if role == Qt.DisplayRole:
            col = index.column()
            if col == 0:
                return hit.filename
            if col == 1:
                return hit.snippet
            if col == 2:
                return hit.folder
            if col == 3:
                return hit.mtime_iso
        if role == Qt.ToolTipRole:
            return hit.path
        return None

    def set_hits(self, hits: List[SearchHit]) -> None:
        self.beginResetModel()
        self._hits = hits
        self.endResetModel()

    def hit(self, row: int) -> Optional[SearchHit]:
        if 0 <= row < len(self._hits):
            return self._hits[row]
        return None


# ----- 인덱싱 워커 스레드 ----------------------------------------------------


class IndexWorker(QObject):
    progress = Signal(object)  # IndexProgress
    finished = Signal(object)  # IndexProgress
    failed = Signal(str)

    def __init__(self, cfg: AppConfig, roots: List[Path], force: bool = False):
        super().__init__()
        self.cfg = cfg
        self.roots = roots
        self.force = force

    @Slot()
    def run(self) -> None:
        try:
            db = Database(self.cfg.db_path)
            try:
                for r in self.roots:
                    db.add_scan_root(r)
                indexer = Indexer(db, enable_ocr=self.cfg.enable_ocr)
                final = indexer.index_roots(
                    self.roots,
                    progress_cb=lambda p: self.progress.emit(_snapshot(p)),
                    force=self.force,
                )
                self.finished.emit(final)
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


def _snapshot(p: IndexProgress) -> IndexProgress:
    return IndexProgress(
        total_seen=p.total_seen,
        indexed=p.indexed,
        skipped=p.skipped,
        failed=p.failed,
        current_path=p.current_path,
        warnings=list(p.warnings),
    )


# ----- 스캔 진행 다이얼로그 --------------------------------------------------


class ScanDialog(QDialog):
    def __init__(self, parent: QWidget, cfg: AppConfig, roots: List[Path]):
        super().__init__(parent)
        self.setWindowTitle("폴더 스캔 중…")
        self.resize(520, 140)
        self.cfg = cfg
        self.roots = roots

        self.label = QLabel("준비 중…")
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # busy
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

        self.thread = QThread(self)
        self.worker = IndexWorker(cfg, roots)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.thread.start()

        self.final_progress: Optional[IndexProgress] = None

    @Slot(object)
    def _on_progress(self, p: IndexProgress) -> None:
        self.label.setText(
            f"seen={p.total_seen}  indexed={p.indexed}  skip={p.skipped}  fail={p.failed}\n"
            f"{(p.current_path or '')[-80:]}"
        )

    @Slot(object)
    def _on_finished(self, p: IndexProgress) -> None:
        self.final_progress = p
        self.thread.quit()
        self.thread.wait()
        self.accept()

    @Slot(str)
    def _on_failed(self, msg: str) -> None:
        self.thread.quit()
        self.thread.wait()
        QMessageBox.critical(self, "스캔 실패", msg)
        self.reject()

    def closeEvent(self, event) -> None:
        if self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(2000)
        super().closeEvent(event)


# ----- 메인 윈도우 -----------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self.cfg.ensure_dirs()
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.resize(1100, 650)

        self.db = Database(cfg.db_path)
        self.searcher = Searcher(self.db, snippet_radius=cfg.snippet_radius)

        self._build_ui()
        self._refresh_status()

    # ---- UI 구성 -------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(8, 8, 8, 8)

        # 상단: 검색창 + 버튼
        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("파일 내용을 검색하세요… (3자 이상)")
        self.search_edit.textChanged.connect(self._schedule_search)
        self.search_edit.returnPressed.connect(self._run_search_now)

        self.add_folder_btn = QPushButton("폴더 추가 및 스캔")
        self.add_folder_btn.clicked.connect(self._on_add_folder)

        self.rescan_btn = QPushButton("전체 재스캔")
        self.rescan_btn.clicked.connect(lambda: self._start_scan(force=True))

        self.settings_btn = QPushButton("설정")
        self.settings_btn.clicked.connect(self._on_settings)

        top.addWidget(self.search_edit, 1)
        top.addWidget(self.add_folder_btn)
        top.addWidget(self.rescan_btn)
        top.addWidget(self.settings_btn)
        v.addLayout(top)

        # 결과 테이블
        self.model = ResultModel(self)
        self.table = QTableView(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.doubleClicked.connect(self._on_double_clicked)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(2, 260)

        v.addWidget(self.table, 1)

        # 상태바
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.status_label = QLabel("")
        self.status.addWidget(self.status_label, 1)

        # debounce 타이머
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._run_search_now)

    # ---- 검색 ----------------------------------------------------------

    def _schedule_search(self) -> None:
        self._search_timer.start()

    def _run_search_now(self) -> None:
        text = self.search_edit.text().strip()
        if len(text) < 3:
            self.model.set_hits([])
            self._refresh_status(extra=f"검색: '{text}' (3자 이상 입력)" if text else None)
            return
        hits = self.searcher.search(text, limit=500)
        self.model.set_hits(hits)
        self._refresh_status(extra=f"'{text}' 결과 {len(hits)}건")

    def _refresh_status(self, extra: Optional[str] = None) -> None:
        stats = self.db.stats()
        roots = self.db.list_scan_roots()
        parts = [
            f"인덱스: {stats['ok']}/{stats['total']} 파일",
            f"폴더: {len(roots)}",
        ]
        if extra:
            parts.append(extra)
        self.status_label.setText("   |   ".join(parts))

    # ---- 폴더 추가 / 스캔 ----------------------------------------------

    def _on_settings(self) -> None:
        from jean_finder.gui.settings_dialog import SettingsDialog

        dlg = SettingsDialog(self, self.cfg)
        if dlg.exec() == QDialog.Accepted:
            dlg.apply_to(self.cfg)
            self.searcher.snippet_radius = self.cfg.snippet_radius
            self._refresh_status(extra="설정 저장됨")

    def _on_add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "스캔할 폴더 선택")
        if not folder:
            return
        root = Path(folder).resolve()
        self._start_scan(roots=[root], force=False)

    def _start_scan(self, roots: Optional[List[Path]] = None, force: bool = False) -> None:
        if roots is None:
            existing = self.db.list_scan_roots()
            if not existing:
                QMessageBox.information(
                    self, "스캔할 폴더 없음", "먼저 '폴더 추가 및 스캔'으로 폴더를 등록하세요."
                )
                return
            roots = [Path(p) for p in existing]

        # 인덱싱 중에는 동일 DB에 두 connection이 붙게 되는데 WAL 모드라 읽기는 허용된다.
        # 단, 본 창의 커넥션은 검색용으로 유지한다.
        dlg = ScanDialog(self, self.cfg, roots)
        dlg.exec()
        if dlg.final_progress is not None:
            p = dlg.final_progress
            self._refresh_status(
                extra=f"스캔 완료: indexed={p.indexed} skip={p.skipped} fail={p.failed}"
            )
            if p.warnings:
                preview = "\n".join(p.warnings[:10])
                more = f"\n…({len(p.warnings) - 10}건 추가)" if len(p.warnings) > 10 else ""
                QMessageBox.warning(self, "경고", preview + more)
            self._run_search_now()

    # ---- 우클릭/더블클릭 ----------------------------------------------

    def _on_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        hit = self.model.hit(index.row())
        if hit is None:
            return
        menu = QMenu(self)

        act_open_folder = QAction("폴더 열기", self)
        act_open_folder.triggered.connect(lambda: self._reveal_in_explorer(hit.path))
        menu.addAction(act_open_folder)

        act_open_file = QAction("파일 열기", self)
        act_open_file.triggered.connect(lambda: self._open_file(hit.path))
        menu.addAction(act_open_file)

        act_copy = QAction("경로 복사", self)
        act_copy.setShortcut(QKeySequence.Copy)
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(hit.path))
        menu.addAction(act_copy)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_double_clicked(self, index: QModelIndex) -> None:
        hit = self.model.hit(index.row())
        if hit is not None:
            self._open_file(hit.path)

    # ---- 파일 탐색기 연동 ----------------------------------------------

    @staticmethod
    def _reveal_in_explorer(path: str) -> None:
        p = Path(path)
        if sys.platform == "win32":
            # explorer /select, "C:\\...\\file"
            try:
                subprocess.Popen(["explorer", f"/select,{p}"])
                return
            except OSError:
                pass
        # fallback: 부모 폴더 열기
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

    @staticmethod
    def _open_file(path: str) -> None:
        p = Path(path)
        if sys.platform == "win32":
            try:
                os.startfile(str(p))  # type: ignore[attr-defined]
                return
            except OSError:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def closeEvent(self, event) -> None:
        try:
            self.db.close()
        except Exception:
            pass
        super().closeEvent(event)


def run_app(cfg: AppConfig) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow(cfg)
    win.show()
    return app.exec()
