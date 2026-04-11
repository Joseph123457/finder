from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from jean_finder.core.config import AppConfig
from jean_finder.ocr.tesseract import probe


class SettingsDialog(QDialog):
    def __init__(self, parent, cfg: AppConfig):
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.cfg = cfg
        self.resize(460, 240)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.ocr_cb = QCheckBox("스캔본 PDF에 OCR 사용 (느림)")
        self.ocr_cb.setChecked(cfg.enable_ocr)
        form.addRow(self.ocr_cb)

        self.snippet_spin = QSpinBox()
        self.snippet_spin.setRange(3, 40)
        self.snippet_spin.setValue(cfg.snippet_radius)
        form.addRow("스니펫 앞/뒤 글자 수", self.snippet_spin)

        # Tesseract 상태
        info = probe()
        if info["available"]:
            status_text = f"Tesseract OK\n{info['cmd']}"
        else:
            status_text = f"Tesseract 없음\n{info['error']}"
            self.ocr_cb.setEnabled(False)
        status = QLabel(status_text)
        status.setWordWrap(True)
        form.addRow("OCR 엔진", status)

        db_info = QLabel(f"인덱스 DB: {cfg.db_path}")
        db_info.setWordWrap(True)
        form.addRow(db_info)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def apply_to(self, cfg: AppConfig) -> None:
        cfg.enable_ocr = self.ocr_cb.isChecked()
        cfg.snippet_radius = self.snippet_spin.value()
