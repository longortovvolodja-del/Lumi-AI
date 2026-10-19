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
    """Centered multi-step installer with a persistent left artwork panel."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Установка Lumi AI")
        self.setFixedSize(900, 570)
        icon_path = resource_path("assets", "lumi-app-icon.png")
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #070d20; color: #eaf3ff; }
            QLabel { color: #eaf3ff; }
            QLabel#muted { color: #9eb4d6; }
            QLabel#brand { color: #ffffff; font-size: 25px; font-weight: 800; }
            QLabel#accent { color: #59e5ff; }
            QFrame#panel { background: #0b1530; border: 1px solid #173b72; border-radius: 18px; }
            QLineEdit { background: #081126; border: 1px solid #244b82; border-radius: 9px; padding: 10px; color: #f4f8ff; }
            QCheckBox { spacing: 9px; color: #dbe9ff; }
            QCheckBox::indicator { width: 17px; height: 17px; }
            QPushButton { background: #10264b; border: 1px solid #28558d; border-radius: 10px; padding: 10px 18px; color: #eaf3ff; font-weight: 600; }
            QPushButton:hover { border-color: #55dfff; background: #15325d; }
            QPushButton#primary { background: #174ff5; border: 1px solid #63eaff; color: white; }
            QPushButton#primary:hover { background: #2365ff; }
            QPushButton:disabled { color: #7186a7; background: #101a30; border-color: #1d2b44; }
            QProgressBar { background: #061026; border: 1px solid #244b82; border-radius: 7px; min-height: 14px; text-align: center; color: white; }
            QProgressBar::chunk { border-radius: 6px; background: #12cfff; }
        """)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 20, 20, 18)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("LUMI <span style='color:#b68cff'>AI</span>")
        title.setStyleSheet("font-size: 17px; font-weight: 800; letter-spacing: 2px;")
        header.addWidget(title)
        header.addStretch()
        self.version_label = QLabel(f"Версия {version_text()}")
        self.version_label.setObjectName("muted")
        header.addWidget(self.version_label)
        outer.addLayout(header)

        self.panel = QFrame()
        self.panel.setObjectName("panel")
        panel_layout = QHBoxLayout(self.panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(22)

        self.art = QLabel()
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art.setMinimumWidth(260)
        self.art.setMaximumWidth(300)
        self.left_art_path = resource_path("assets", "панель загрузки установки слева.png")
        self.fallback_art_path = resource_path("assets", "Lumi AI_ Неоновый помощник-лисёнок.png")
        self.refresh_left_art()
        panel_layout.addWidget(self.art, 0)

        self.pages = QStackedWidget()
        self.pages.setMinimumWidth(470)
        self.pages.addWidget(self.make_welcome_page())
        self.pages.addWidget(self.make_folder_page())
        self.pages.addWidget(self.make_agreement_page())
        self.pages.addWidget(self.make_install_page())
        self.pages.addWidget(self.make_finish_page())
        panel_layout.addWidget(self.pages, 1)
        outer.addWidget(self.panel, 1)

        footer = QHBoxLayout()
        self.step_dots = QLabel()
        self.step_dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step_dots.setStyleSheet("font-size: 20px; letter-spacing: 8px; color: #536b91;")
        footer.addWidget(self.step_dots, 1)
        outer.addLayout(footer)
        self.setCentralWidget(root)

        self.process: subprocess.Popen | None = None
        self.install_target: Path | None = None
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(250)
        self.poll_timer.timeout.connect(self.check_install_process)
        self.update_step_dots()
        self.center_on_screen()

    def center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def refresh_left_art(self) -> None:
        if self.pages_current_is_finish():
            self.art.hide()
            return
        self.art.show()
        source = self.left_art_path if self.left_art_path.is_file() else self.fallback_art_path
        if source.is_file():
            pixmap = QPixmap(str(source))
            self.art.setPixmap(pixmap.scaled(280, 450, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation))
        else:
            self.art.setText("LUMI AI")

    def pages_current_is_finish(self) -> bool:
        return hasattr(self, "pages") and self.pages.currentIndex() == 4

    def make_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addStretch()
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_path = resource_path("assets", "installer-welcome.png")
        if welcome_path.is_file():
            image.setPixmap(QPixmap(str(welcome_path)).scaled(
                430, 310, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            image.setText("Добро пожаловать в Lumi AI")
            image.setObjectName("brand")
        layout.addWidget(image, 1)
        layout.addStretch()
        buttons = QHBoxLayout()
        buttons.addStretch()
        next_button = QPushButton("Далее  →")
        next_button.setObjectName("primary")
        next_button.clicked.connect(lambda: self.go_to_step(1))
        buttons.addWidget(next_button)
        layout.addLayout(buttons)
        return page

    def make_folder_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        heading = QLabel("Папка установки")
        heading.setObjectName("brand")
        layout.addWidget(heading)
        description = QLabel("Выбери, куда установить Lumi AI.")
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.addSpacing(20)
        layout.addWidget(QLabel("Путь установки"))
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(str(DEFAULT_DIR))
        path_row.addWidget(self.path_edit, 1)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self.choose_directory)
        path_row.addWidget(browse)
        layout.addLayout(path_row)
        self.desktop_checkbox = QCheckBox("Создать ярлык на рабочем столе")
        self.desktop_checkbox.setChecked(True)
        layout.addWidget(self.desktop_checkbox)
        layout.addStretch()
        buttons = QHBoxLayout()
        back = QPushButton("← Назад")
        back.clicked.connect(lambda: self.go_to_step(0))
        buttons.addWidget(back)
        buttons.addStretch()
        next_button = QPushButton("Далее  →")
        next_button.setObjectName("primary")
        next_button.clicked.connect(self.validate_folder_and_continue)
        buttons.addWidget(next_button)
        layout.addLayout(buttons)
        return page

    def make_agreement_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        heading = QLabel("Пользовательское соглашение")
        heading.setObjectName("brand")
        layout.addWidget(heading)
        note = QLabel("Здесь пока будет заглушка соглашения. Текст добавим позже.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.agreement_checkbox = QCheckBox("Я принимаю пользовательское соглашение")
        self.agreement_checkbox.setChecked(False)
        layout.addWidget(self.agreement_checkbox)
        buttons = QHBoxLayout()
        back = QPushButton("← Назад")
        back.clicked.connect(lambda: self.go_to_step(1))
        buttons.addWidget(back)
        buttons.addStretch()
        self.agreement_next = QPushButton("Далее  →")
        self.agreement_next.setObjectName("primary")
        self.agreement_next.setEnabled(False)
        self.agreement_checkbox.toggled.connect(self.agreement_next.setEnabled)
        self.agreement_next.clicked.connect(lambda: self.go_to_step(3))
        buttons.addWidget(self.agreement_next)
        layout.addLayout(buttons)
        return page

    def make_install_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        self.progress_title = QLabel("Устанавливаем Lumi AI…")
        self.progress_title.setObjectName("brand")
        self.progress_title.setWordWrap(True)
        layout.addWidget(self.progress_title)
        self.status_label = QLabel("Подготовка установщика")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)
        self.progress_note = QLabel("Не закрывай это окно, пока установка не завершится.")
        self.progress_note.setObjectName("muted")
        self.progress_note.setWordWrap(True)
        layout.addWidget(self.progress_note)
        layout.addStretch()
        self.finish_button = QPushButton("Ожидание…")
        self.finish_button.setObjectName("primary")
        self.finish_button.setEnabled(False)
        self.finish_button.clicked.connect(self.finish)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.finish_button)
        layout.addLayout(row)
        return page

    def make_finish_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addStretch()
        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = resource_path("assets", "lumi-logo.png")
        if logo_path.is_file():
            logo.setPixmap(QPixmap(str(logo_path)).scaled(
                420, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText("LUMI AI")
            logo.setObjectName("brand")
        layout.addWidget(logo, 1)
        self.finish_message = QLabel("Установка завершена!")
        self.finish_message.setObjectName("brand")
        self.finish_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.finish_message)
        layout.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        self.done_button = QPushButton("Готово")
        self.done_button.setObjectName("primary")
        self.done_button.clicked.connect(self.finish)
        row.addWidget(self.done_button)
        layout.addLayout(row)
        return page

    def update_step_dots(self) -> None:
        if hasattr(self, "step_dots"):
            index = self.pages.currentIndex() if hasattr(self, "pages") else 0
            self.step_dots.setText("  ".join("●" if i == index else "○" for i in range(5)))
            self.step_dots.setVisible(index != 4)

    def go_to_step(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.update_step_dots()
        self.refresh_left_art()

    def choose_directory(self) -> None:
        current = self.path_edit.text().strip() or str(DEFAULT_DIR)
        selected = QFileDialog.getExistingDirectory(self, "Выбери папку установки Lumi AI", current)
        if selected:
            self.path_edit.setText(selected)

    def validate_folder_and_continue(self) -> None:
        raw_dir = self.path_edit.text().strip()
        if not raw_dir:
            QMessageBox.warning(self, "Lumi AI", "Укажи папку установки.")
            return
        target = Path(raw_dir).expanduser()
        if not target.is_absolute():
            QMessageBox.warning(self, "Lumi AI", "Путь установки должен быть абсолютным.")
            return
        self.install_target = target
        self.go_to_step(2)

    def begin_install(self) -> None:
        if not self.install_target:
            self.go_to_step(1)
            return
        internal_setup = resource_path("payload", "Lumi-Internal-Setup.exe")
        if not internal_setup.is_file():
            QMessageBox.critical(self, "Lumi AI", "Не найден внутренний модуль установки. Скачай установщик заново.")
            self.go_to_step(2)
            return
        target = self.install_target
        args = [
            str(internal_setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
            f"/DIR={target}",
        ]
        if self.desktop_checkbox.isChecked():
            args.append("/TASKS=desktopicon")
        else:
            args.append("/TASKS=")
        self.finish_button.setEnabled(False)
        self.go_to_step(3)
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
            self.finish_button.setText("Закрыть")
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
            self.progress_title.setText("Lumi AI установлена!")
            self.status_label.setText("Установка завершена успешно. Lumi AI готова к запуску.")
            self.progress_note.setText("Нажми «Готово», чтобы открыть Lumi AI.")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.finish_button.setEnabled(True)
            self.finish_button.setText("Перейти к завершению  →")
            self.finish_button.clicked.disconnect()
            self.finish_button.clicked.connect(lambda: self.show_finish(True))
        else:
            self.progress_title.setText("Не удалось завершить установку")
            self.status_label.setText(f"Установщик завершился с кодом {code}.")
            self.progress_note.setText("Попробуй запустить установщик ещё раз. Если ошибка повторится, сообщи этот код.")
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.finish_button.setEnabled(True)
            self.finish_button.setText("Закрыть")
            self.finish_button.clicked.disconnect()
            self.finish_button.clicked.connect(self.close)

    def show_finish(self, success: bool = True) -> None:
        self.go_to_step(4)
        self.finish_message.setText("Установка завершена успешно!" if success else "Установка завершена")

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
