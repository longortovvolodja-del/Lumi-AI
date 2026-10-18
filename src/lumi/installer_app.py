"""Branded Lumi AI Windows installer bootstrapper.

The visible installer is a PySide6 application. It delegates the actual file
installation to the bundled Inno Setup engine so Windows shortcuts, registry
entries and normal uninstall support remain intact.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QProgressBar,
    QStackedWidget, QVBoxLayout, QWidget,
)

APP_NAME = "Lumi AI"
DEFAULT_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / APP_NAME


def resource_path(*parts: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root.joinpath(*parts)


def version_text() -> str:
    path = resource_path("payload", "installer-version.txt")
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.1.1"


class InstallerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Установка Lumi AI")
        self.setMinimumSize(760, 500)
        self.resize(820, 540)
        icon_path = resource_path("assets", "lumi-app-icon.png")
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #070d20; color: #eaf3ff; }
            QLabel { color: #eaf3ff; }
            QLabel#muted { color: #9eb4d6; }
            QLabel#brand { color: #ffffff; font-size: 31px; font-weight: 800; }
            QLabel#accent { color: #59e5ff; }
            QFrame#panel { background: #0b1530; border: 1px solid #173b72; border-radius: 18px; }
            QLineEdit { background: #081126; border: 1px solid #244b82; border-radius: 9px; padding: 10px; color: #f4f8ff; }
            QCheckBox { spacing: 9px; color: #dbe9ff; }
            QCheckBox::indicator { width: 17px; height: 17px; }
            QPushButton { background: #10264b; border: 1px solid #28558d; border-radius: 10px; padding: 11px 20px; color: #eaf3ff; font-weight: 600; }
            QPushButton:hover { border-color: #55dfff; background: #15325d; }
            QPushButton#primary { background: #174ff5; border: 1px solid #63eaff; color: white; }
            QPushButton#primary:hover { background: #2365ff; }
            QPushButton:disabled { color: #7186a7; background: #101a30; border-color: #1d2b44; }
            QProgressBar { background: #061026; border: 1px solid #244b82; border-radius: 7px; min-height: 14px; text-align: center; color: white; }
            QProgressBar::chunk { border-radius: 6px; background: #12cfff; }
        """)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(22, 22, 22, 22)
        outer.setSpacing(14)

        header = QHBoxLayout()
        self.mini_logo = QLabel("✦")
        self.mini_logo.setStyleSheet("font-size: 24px; color: #60e9ff;")
        header.addWidget(self.mini_logo)
        title = QLabel("LUMI <span style='color:#b68cff'>AI</span>")
        title.setStyleSheet("font-size: 17px; font-weight: 800; letter-spacing: 2px;")
        header.addWidget(title)
        header.addStretch()
        self.version_label = QLabel(f"Версия {version_text()}")
        self.version_label.setObjectName("muted")
        header.addWidget(self.version_label)
        outer.addLayout(header)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(26, 24, 26, 24)
        panel_layout.setSpacing(24)

        art = QLabel()
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art.setMinimumWidth(245)
        art_path = resource_path("assets", "Lumi AI_ Неоновый помощник-лисёнок.png")
        icon_path = resource_path("assets", "lumi-app-icon.png")
        art_source = art_path if art_path.is_file() else icon_path
        if art_source.is_file():
            pixmap = QPixmap(str(art_source))
            art.setPixmap(pixmap.scaled(260, 340, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            art.setText("🦊")
            art.setStyleSheet("font-size: 100px;")
        panel_layout.addWidget(art, 0)

        self.pages = QStackedWidget()
        self.welcome_page = QWidget()
        welcome = QVBoxLayout(self.welcome_page)
        welcome.setContentsMargins(0, 10, 0, 0)
        welcome.setSpacing(14)
        headline = QLabel("Добро пожаловать\nв Lumi AI")
        headline.setObjectName("brand")
        headline.setWordWrap(True)
        welcome.addWidget(headline)
        tagline = QLabel("Твой умный помощник с неоновым лисёнком")
        tagline.setObjectName("accent")
        tagline.setWordWrap(True)
        tagline.setStyleSheet("font-size: 15px; font-weight: 600;")
        welcome.addWidget(tagline)
        body = QLabel("Lumi AI готова поселиться на твоём компьютере. Выбери папку установки и нажми кнопку ниже.")
        body.setObjectName("muted")
        body.setWordWrap(True)
        welcome.addWidget(body)
        welcome.addSpacing(8)
        welcome.addWidget(QLabel("Папка установки"))
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(str(DEFAULT_DIR))
        path_row.addWidget(self.path_edit, 1)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self.choose_directory)
        path_row.addWidget(browse)
        welcome.addLayout(path_row)
        self.desktop_checkbox = QCheckBox("Создать ярлык на рабочем столе")
        self.desktop_checkbox.setChecked(True)
        welcome.addWidget(self.desktop_checkbox)
        welcome.addStretch()
        self.install_button = QPushButton("Установить Lumi AI  →")
        self.install_button.setObjectName("primary")
        self.install_button.clicked.connect(self.begin_install)
        welcome.addWidget(self.install_button, 0, Qt.AlignmentFlag.AlignRight)
        self.pages.addWidget(self.welcome_page)

        self.progress_page = QWidget()
        progress = QVBoxLayout(self.progress_page)
        progress.setContentsMargins(0, 16, 0, 0)
        progress.setSpacing(15)
        self.progress_title = QLabel("Устанавливаем Lumi AI…")
        self.progress_title.setObjectName("brand")
        self.progress_title.setWordWrap(True)
        progress.addWidget(self.progress_title)
        self.status_label = QLabel("Подготовка установщика")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        progress.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        progress.addWidget(self.progress_bar)
        self.progress_note = QLabel("Не закрывай это окно, пока установка не завершится.")
        self.progress_note.setObjectName("muted")
        self.progress_note.setWordWrap(True)
        progress.addWidget(self.progress_note)
        progress.addStretch()
        self.finish_button = QPushButton("Готово")
        self.finish_button.setObjectName("primary")
        self.finish_button.setEnabled(False)
        self.finish_button.clicked.connect(self.finish)
        progress.addWidget(self.finish_button, 0, Qt.AlignmentFlag.AlignRight)
        self.pages.addWidget(self.progress_page)

        panel_layout.addWidget(self.pages, 1)
        outer.addWidget(panel, 1)
        footer = QLabel("Lumi AI  •  Установка без лишних сложностей")
        footer.setObjectName("muted")
        outer.addWidget(footer)
        self.setCentralWidget(root)
        self.process: subprocess.Popen | None = None
        self.install_target: Path | None = None
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(250)
        self.poll_timer.timeout.connect(self.check_install_process)

    def choose_directory(self) -> None:
        current = self.path_edit.text().strip() or str(DEFAULT_DIR)
        selected = QFileDialog.getExistingDirectory(self, "Выбери папку установки Lumi AI", current)
        if selected:
            self.path_edit.setText(selected)

    def begin_install(self) -> None:
        raw_dir = self.path_edit.text().strip()
        if not raw_dir:
            QMessageBox.warning(self, "Lumi AI", "Укажи папку установки.")
            return
        target = Path(raw_dir).expanduser()
        if not target.is_absolute():
            QMessageBox.warning(self, "Lumi AI", "Путь установки должен быть абсолютным.")
            return
        internal_setup = resource_path("payload", "Lumi-Internal-Setup.exe")
        if not internal_setup.is_file():
            QMessageBox.critical(self, "Lumi AI", "Не найден внутренний модуль установки. Скачай установщик заново.")
            return
        self.install_target = target
        args = [
            str(internal_setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
            f"/DIR={target}",
        ]
        if self.desktop_checkbox.isChecked():
            args.append("/TASKS=desktopicon")
        else:
            args.append("/TASKS=")
        self.install_button.setEnabled(False)
        self.pages.setCurrentWidget(self.progress_page)
        self.status_label.setText("Копируем файлы и создаём ярлыки…")
        self.progress_bar.setRange(0, 0)
        try:
            self.process = subprocess.Popen(args, close_fds=True)
        except OSError as exc:
            self.status_label.setText("Не удалось запустить установку.")
            self.progress_note.setText(str(exc))
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.finish_button.setEnabled(True)
            return
        self.poll_timer.start()

    def check_install_process(self) -> None:
        if self.process is None:
            return
        code = self.process.poll()
        if code is None:
            return
        self.poll_timer.stop()
        if code == 0:
            self.progress_title.setText("Lumi AI установлена! ✨")
            self.status_label.setText("Установка завершена успешно. Lumi AI готова к запуску.")
            self.progress_note.setText("Нажми «Готово», чтобы открыть Lumi AI.")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.finish_button.setEnabled(True)
            self.finish_button.setText("Запустить Lumi AI  →")
        else:
            self.progress_title.setText("Не удалось завершить установку")
            self.status_label.setText(f"Установщик завершился с кодом {code}.")
            self.progress_note.setText("Попробуй запустить установщик ещё раз. Если ошибка повторится, сообщи этот код.")
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.finish_button.setEnabled(True)
            self.finish_button.setText("Закрыть")

    def finish(self) -> None:
        if self.process and self.process.poll() == 0 and self.install_target:
            app = self.install_target / "Lumi.exe"
            if app.is_file():
                try:
                    subprocess.Popen([str(app)], cwd=str(self.install_target))
                except OSError:
                    pass
        self.close()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    window = InstallerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
