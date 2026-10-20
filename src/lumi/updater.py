"""Visual Windows updater for Lumi AI.

Only GitHub's latest stable release is considered. Beta prereleases are excluded
by the /releases/latest API endpoint. The updater runs from a temporary copy so
the installed LumiUpdater.exe can be safely replaced by the installer.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)
import urllib.error
import urllib.request

REPO = "longortovvolodja-del/Lumi-AI"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
APP_NAME = "Lumi AI"
APP_EXE = "Lumi.exe"


def _http(url: str, *, timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Lumi-AI-Updater", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _installed_program() -> tuple[Path | None, str | None]:
    """Find the installed Lumi directory without depending on registry state."""
    import winreg

    roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, root in roots:
        try:
            with winreg.OpenKey(hive, root) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, index)) as subkey:
                            name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            if name != APP_NAME and not name.startswith(APP_NAME + " "):
                                continue
                            try:
                                location = Path(winreg.QueryValueEx(subkey, "InstallLocation")[0])
                            except OSError:
                                location = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / APP_NAME
                            if (location / APP_EXE).is_file():
                                return location, None
                    except OSError:
                        continue
        except OSError:
            continue
    default = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / APP_NAME
    return (default, None) if (default / APP_EXE).is_file() else (None, None)


def _version_key(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(int(number) for number in numbers) or (0,)


class UpdateWorker(QObject):
    status = Signal(str)
    progress = Signal(int)
    checked = Signal(str, str, bool)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, install_dir: Path, *, install: bool = False) -> None:
        super().__init__()
        self.install_dir = install_dir
        self.install = install
        self.release: dict = {}

    def run(self) -> None:
        try:
            self.status.emit("Проверяем последнюю стабильную версию…")
            self.progress.emit(8)
            self.release = json.loads(_http(LATEST_API).decode("utf-8"))
            latest = str(self.release.get("tag_name", "")).removeprefix("v")
            version_path = self.install_dir / "version.txt"
            installed = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else "0.0.0"
            if not latest or not re.fullmatch(r"\d+\.\d+\.\d+", latest):
                raise RuntimeError("GitHub вернул некорректную версию стабильного релиза.")
            installed_base = installed.split("-", 1)[0]
            installed_is_beta = "-beta" in installed.lower()
            is_current_or_newer = _version_key(installed_base) >= _version_key(latest)
            beta_needs_stable = installed_is_beta and _version_key(installed_base) == _version_key(latest)
            if is_current_or_newer and not beta_needs_stable:
                self.checked.emit(installed, latest, False)
                self.finished.emit()
                return
            self.checked.emit(installed, latest, True)
            if not self.install:
                self.finished.emit()
                return

            assets = self.release.get("assets", [])
            installer = next((item for item in assets if item.get("name", "").startswith("Lumi-Setup-") and item.get("name", "").endswith(".exe")), None)
            checksums = next((item for item in assets if item.get("name") == "SHA256SUMS.txt"), None)
            if not installer or not checksums:
                raise RuntimeError("В стабильном релизе нет установщика или SHA256SUMS.txt.")

            self.status.emit("Загружаем установщик обновления…")
            self.progress.emit(18)
            installer_name = installer["name"]
            checksum_text = _http(checksums["browser_download_url"]).decode("utf-8", errors="replace")
            expected = None
            for line in checksum_text.splitlines():
                parts = line.strip().split()
                if len(parts) == 2 and parts[1].lstrip("*") == installer_name:
                    expected = parts[0].lower()
                    break
            if not expected or not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise RuntimeError("Не удалось найти корректную SHA-256 контрольную сумму.")

            data = _http(installer["browser_download_url"], timeout=180)
            self.progress.emit(62)
            self.status.emit("Проверяем целостность загруженного файла…")
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError("SHA-256 не совпала. Обновление отменено.")
            temp_root = Path(tempfile.gettempdir()) / "LumiAI-Update"
            temp_root.mkdir(parents=True, exist_ok=True)
            installer_path = temp_root / installer_name
            installer_path.write_bytes(data)
            self.progress.emit(72)
            self.status.emit("Запускаем установку стабильной версии…")
            # Tell the branded bootstrapper to bypass its interactive wizard,
            # install into the detected existing directory, and leave app launch to this updater.
            result = subprocess.run(
                [
                    str(installer_path),
                    "--silent-update",
                    "--install-dir",
                    str(self.install_dir),
                ],
                check=False,
            )
            try:
                installer_path.unlink(missing_ok=True)
            except OSError:
                pass
            if result.returncode != 0:
                raise RuntimeError(f"Установщик завершился с кодом {result.returncode}.")
            self.progress.emit(100)
            self.status.emit(f"Lumi AI успешно обновлена до версии {latest}.")
            self.checked.emit(installed, latest, True)
            self.finished.emit()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                self.failed.emit("Стабильных релизов пока нет. Попробуй позже.")
            else:
                self.failed.emit(f"GitHub вернул ошибку HTTP {exc.code}.")
            self.finished.emit()
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            self.failed.emit(f"Не удалось обновить Lumi AI: {exc}")
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(f"Не удалось обновить Lumi AI: {exc}")
            self.finished.emit()


class UpdaterWindow(QMainWindow):
    def __init__(self, install_dir: Path) -> None:
        super().__init__()
        self.install_dir = install_dir
        self.latest_version = ""
        self.update_available = False
        self.update_started = False
        self.worker_thread: QThread | None = None
        self.worker: UpdateWorker | None = None
        self.setWindowTitle("Lumi AI — обновление")
        self.setFixedSize(520, 340)
        icon = install_dir / "assets" / "lumi-app-icon.png"
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #080d20; color: #edf4ff; }
            QLabel#brand { font-size: 22px; font-weight: 800; color: #65e8ff; }
            QLabel#muted { color: #9eb1d0; }
            QFrame#panel { background: #0c1730; border: 1px solid #1d3d6b; border-radius: 16px; }
            QProgressBar { background: #071126; border: 1px solid #244b82; border-radius: 7px; min-height: 15px; text-align: center; }
            QProgressBar::chunk { border-radius: 6px; background: #12cfff; }
            QPushButton { background: #10264b; border: 1px solid #28558d; border-radius: 9px; padding: 9px 16px; }
            QPushButton#primary { background: #174ff5; border-color: #63eaff; font-weight: 700; }
            QPushButton:disabled { color: #6f82a4; background: #101a30; }
        """)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        title = QLabel("LUMI <span style='color:#b68cff'>AI</span>")
        title.setObjectName("brand")
        layout.addWidget(title)
        panel = QFrame()
        panel.setObjectName("panel")
        inside = QVBoxLayout(panel)
        inside.setContentsMargins(18, 18, 18, 18)
        inside.setSpacing(12)
        self.heading = QLabel("Обновление приложения")
        self.heading.setStyleSheet("font-size: 15px; font-weight: 700;")
        inside.addWidget(self.heading)
        self.status_label = QLabel("Подготовка обновлятора…")
        self.status_label.setWordWrap(True)
        inside.addWidget(self.status_label)
        self.version_label = QLabel("Установленная версия проверяется…")
        self.version_label.setObjectName("muted")
        inside.addWidget(self.version_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        inside.addWidget(self.progress)
        layout.addWidget(panel, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.update_button = QPushButton("Обновить")
        self.update_button.setObjectName("primary")
        self.update_button.setVisible(False)
        self.update_button.clicked.connect(self.begin_install)
        buttons.addWidget(self.update_button)
        self.close_button = QPushButton("Закрыть")
        self.close_button.setVisible(False)
        self.close_button.clicked.connect(self.close_and_return)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.setCentralWidget(root)
        QTimer.singleShot(150, self.check_latest)

    def start_worker(self, *, install: bool) -> None:
        self.worker_thread = QThread(self)
        self.worker = UpdateWorker(self.install_dir, install=install)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.status.connect(self.status_label.setText)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.checked.connect(self.on_checked)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.on_worker_finished)
        self.worker_thread.start()

    def check_latest(self) -> None:
        self.update_button.setVisible(False)
        self.close_button.setVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("Проверяем последнюю стабильную версию…")
        self.start_worker(install=False)

    def on_checked(self, installed: str, latest: str, available: bool) -> None:
        self.latest_version = latest
        self.update_available = available
        self.version_label.setText(f"Установлена: {installed}    Последняя стабильная: {latest}")
        if available and not self.update_started:
            self.heading.setText("Доступно обновление")
            self.status_label.setText(f"Доступна стабильная версия {latest}. Бета-версии не устанавливаются.")
            self.update_button.setText("Обновить сейчас")
            self.update_button.setVisible(True)
            self.close_button.setVisible(True)
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
        elif not available:
            self.heading.setText("Установлена последняя версия")
            self.status_label.setText(f"Lumi AI {installed} уже является последней стабильной версией.")
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.close_button.setText("Вернуться в Lumi AI")
            self.close_button.setVisible(True)

    def on_failed(self, message: str) -> None:
        self.heading.setText("Не удалось выполнить обновление")
        self.status_label.setText(message)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.close_button.setText("Вернуться в Lumi AI")
        self.close_button.setVisible(True)

    def begin_install(self) -> None:
        if self.update_started:
            return
        self.update_started = True
        self.update_button.setEnabled(False)
        self.close_button.setVisible(False)
        self.heading.setText("Обновление Lumi AI")
        self.status_label.setText("Закрываем Lumi AI и готовим установку…")
        self.progress.setRange(0, 100)
        self.progress.setValue(5)
        QTimer.singleShot(400, self.install_latest)

    def install_latest(self) -> None:
        # The main app is expected to have exited before the installer replaces its files.
        self.start_worker(install=True)

    def on_worker_finished(self) -> None:
        if self.worker_thread:
            self.worker_thread.deleteLater()
        if self.update_started and self.progress.value() >= 100:
            self.heading.setText("Обновление завершено")
            self.status_label.setText(f"Lumi AI обновлена до версии {self.latest_version}. Запускаем приложение…")
            QTimer.singleShot(1800, self.launch_app_and_close)
        elif self.update_started:
            self.update_button.setVisible(False)
            self.close_button.setVisible(True)
            self.update_started = False
            self.update_button.setEnabled(True)

    def close_and_return(self) -> None:
        self.launch_app()
        self.close()

    def launch_app(self) -> None:
        app_exe = self.install_dir / APP_EXE
        try:
            if app_exe.is_file():
                subprocess.Popen([str(app_exe)], cwd=str(self.install_dir))
        except OSError as exc:
            QMessageBox.warning(self, "Lumi AI", f"Не удалось запустить Lumi AI:\\n{exc}")

    def launch_app_and_close(self) -> None:
        self.launch_app()
        self.close()


def _handoff_to_temporary_copy() -> bool:
    """Run a temp copy so the installer can replace the installed updater executable."""
    if not getattr(sys, "frozen", False) or "--perform-update" in sys.argv:
        return False
    source = Path(sys.executable).resolve()
    temp_dir = Path(tempfile.gettempdir()) / "LumiAI-Updater"
    temp_dir.mkdir(parents=True, exist_ok=True)
    target = temp_dir / "LumiUpdater.exe"
    shutil.copy2(source, target)
    subprocess.Popen([str(target), "--perform-update"], cwd=str(temp_dir), close_fds=True)
    return True


def main() -> int:
    if _handoff_to_temporary_copy():
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName("Lumi AI Updater")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    install_dir, _ = _installed_program()
    if install_dir is None:
        QMessageBox.warning(None, APP_NAME, "Установленная Lumi AI не найдена. Сначала установи Lumi AI.")
        return 1
    window = UpdaterWindow(install_dir)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
