"""Lumi desktop app: neon sidebar, local notes and planned AI sections."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import json
import urllib.error
import urllib.request

from PySide6.QtCore import Qt, QSize, QThread, Signal, QSettings, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton, QSizePolicy,
    QScrollArea, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from lumi import __version__
from lumi.storage import NotesStore


def resource_path(relative_path: str) -> Path:
    """Resolve bundled assets in source runs and PyInstaller builds."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return bundle_root / relative_path


def installed_version() -> str:
    """Read the installed marker so beta builds display their full version."""
    if getattr(sys, "frozen", False):
        marker = Path(sys.executable).resolve().parent / "version.txt"
        try:
            value = marker.read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            pass
    return __version__


STYLE = """
QMainWindow, QWidget {
    background: #0A0C16; color: #F2F4FF;
    font-family: Segoe UI, sans-serif; font-size: 10pt;
}
QWidget#navPanel { background: #020D30; border-right: 1px solid #20263B; }
QWidget#contentPanel { background: #0A0C16; }
QFrame#historyPanel { background: #080F26; border: 1px solid #1D2B4A; border-radius: 14px; }
QFrame#chatTranscript { background: #0C1222; border: 1px solid #202B45; border-radius: 16px; }
QFrame#composer { background: #10182B; border: 1px solid #263653; border-radius: 14px; }
QLabel#lumiMessage { background: #121E38; border: 1px solid #254B6B; border-radius: 12px; padding: 14px; color: #EAF6FF; }
QListWidget#chatHistoryList { background: transparent; border: none; padding: 2px; }
QLabel#brand { color: #7CEEFF; font-size: 18pt; font-weight: 700; }
QLabel#subtitle { color: #8D97B8; font-size: 9pt; }
QLabel#section { color: #8CEBFF; font-size: 12pt; font-weight: 600; }
QLabel#muted { color: #929BB8; }
QLabel#pageTitle { color: #F5F6FF; font-size: 20pt; font-weight: 650; }
QLabel#pageSubtitle { color: #9AA5C6; font-size: 10pt; }
QLineEdit, QTextEdit, QListWidget {
    background: #111626; border: 1px solid #27314A; border-radius: 9px;
    padding: 9px; selection-background-color: #354E8C;
}
QLineEdit:focus, QTextEdit:focus, QListWidget:focus { border: 1px solid #3AD9F2; }
QPushButton {
    background: #182238; border: 1px solid #2A3C5A; border-radius: 9px;
    padding: 9px 12px; min-height: 20px;
}
QPushButton:hover { background: #202E49; border-color: #3BBDD2; }
QPushButton:pressed { background: #151D30; }
QPushButton:disabled { color: #69738F; background: #111626; border-color: #20283A; }
QPushButton#navButton {
    text-align: left; background: #01071B; border: 1px solid transparent;
    color: #A9B2CC; padding: 11px 12px; min-height: 24px;
}
QPushButton#navButton:hover { background: #101B38; color: #E8F9FF; }
QPushButton#navButton:checked {
    background: #15263A; border: 1px solid #24546A; color: #83F0FF;
}
QPushButton#navToggle { background: transparent; border: none; padding: 4px; min-width: 28px; min-height: 28px; }
QPushButton#navToggle:hover { background: #101B38; }
QPushButton#primaryButton {
    background: #173B50; border: 1px solid #267C98; color: #D9FAFF;
}
QPushButton#primaryButton:hover { background: #20536A; }
QListWidget::item { padding: 9px; border-radius: 6px; }
QListWidget::item:selected { background: #1A2B46; color: #8CEBFF; }
QMenuBar { background: #0E1120; color: #DCE4FF; }
QMenuBar::item:selected, QMenu::item:selected { background: #1A2B46; }
QMenu { background: #111626; border: 1px solid #27314A; }
QFrame#card { background: #101625; border: 1px solid #242E46; border-radius: 14px; }
"""


class AnyModelRequestWorker(QThread):
    """Perform AnyModel HTTP requests away from the UI thread."""
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, api_key: str, model_id: str, messages: list[dict[str, str]]) -> None:
        super().__init__()
        self.api_key, self.model_id, self.messages = api_key, model_id, messages

    def run(self) -> None:
        payload = json.dumps({"model": self.model_id, "messages": self.messages, "stream": False}).encode("utf-8")
        request = urllib.request.Request(
            "https://anymodel.org/v1/chat/completions", data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"]
            if isinstance(answer, list):
                answer = "\\n".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in answer)
            answer = str(answer).strip()
            if not answer:
                raise ValueError("Сервис вернул пустой ответ.")
            self.succeeded.emit(answer)
        except urllib.error.HTTPError as exc:
            try: detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception: detail = str(exc)
            self.failed.emit(f"Ошибка API HTTP {exc.code}: {detail}")
        except urllib.error.URLError as exc:
            self.failed.emit(f"Не удалось подключиться к AnyModel: {exc.reason}")
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.failed.emit(f"Не удалось прочитать ответ AnyModel: {exc}")
        except Exception as exc:
            self.failed.emit(f"Ошибка запроса: {exc}")


class LumiWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Lumi AI — твоя умная помощница")
        self.setWindowIcon(QIcon(str(resource_path("assets/lumi-app-icon.png"))))
        self.resize(1120, 720)
        self.setMinimumSize(850, 560)
        self.store = NotesStore()
        self.settings = QSettings("LumiAI", "Lumi")
        self.chat_messages: list[dict[str, str]] = []
        self.api_worker: AnyModelRequestWorker | None = None
        self.current_note_id: int | None = None
        self.nav_buttons: dict[str, QPushButton] = {}
        self.sidebar_collapsed = False
        self._build_ui()
        self._reload_notes()
        self._show_page("chat")

    def _asset_icon(self, name: str) -> QIcon:
        return QIcon(str(resource_path(f"assets/{name}")))

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        nav = QWidget()
        nav.setObjectName("navPanel")
        nav.setFixedWidth(248)
        self.nav_panel = nav
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(14, 20, 14, 16)
        nav_layout.setSpacing(7)

        brand_row = QHBoxLayout()
        logo = QPushButton()
        logo.setObjectName("navToggle")
        logo.setFixedSize(42, 42)
        logo.setIcon(self._asset_icon("lumi-app-icon.png"))
        logo.setIconSize(QSize(40, 40))
        logo.setCursor(Qt.CursorShape.PointingHandCursor)
        logo.setToolTip("Нажми, чтобы развернуть панель")
        logo.clicked.connect(self._expand_sidebar)
        self.brand_logo_button = logo
        self.brand_text_widget = QWidget()
        brand_text = QVBoxLayout(self.brand_text_widget)
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand = QLabel()
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        brand.setPixmap(QPixmap(str(resource_path("assets/lumi-ai-logo.png"))).scaled(
            130, 42, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        brand.setToolTip("Lumi AI")
        subtitle = QLabel("Твоя умная помощница")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        brand_text.addWidget(brand)
        brand_text.addWidget(subtitle)
        brand_row.addWidget(logo)
        brand_row.addWidget(self.brand_text_widget, 1)
        self.sidebar_toggle = QPushButton("‹")
        self.sidebar_toggle.setObjectName("navToggle")
        self.sidebar_toggle.setToolTip("Свернуть боковую панель")
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        brand_row.addWidget(self.sidebar_toggle)
        nav_layout.addLayout(brand_row)
        nav_layout.addSpacing(24)

        nav_caption = QLabel("РАБОЧЕЕ ПРОСТРАНСТВО")
        nav_caption.setObjectName("muted")
        nav_caption.setStyleSheet("font-size: 8pt; letter-spacing: 1px;")
        nav_layout.addWidget(nav_caption)
        self.nav_caption = nav_caption

        self._add_nav(nav_layout, "chat", "Чат с лисичкой", "lumi-tray-icon.png")
        self._add_nav(nav_layout, "notes", "Заметки", "notes-icon.png")
        self._add_nav(nav_layout, "models", "Модели ИИ", "ai-icon.png")
        self._add_nav(nav_layout, "discord", "Discord", "discord-icon.png")
        nav_layout.addStretch()

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #20263B;")
        nav_layout.addWidget(divider)
        self._add_nav(nav_layout, "settings", "Настройки", "settings-icon.png")

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(10, 10, 10, 10)
        status_logo = QLabel()
        status_logo.setPixmap(QPixmap(str(resource_path("assets/lumi-tray-icon.png"))).scaled(
            30, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        status_text = QVBoxLayout()
        status_name = QLabel("Lumi рядом")
        status_name.setStyleSheet("font-weight: 600;")
        status_hint = QLabel(f"Версия {installed_version()}")
        status_hint.setObjectName("muted")
        status_text.addWidget(status_name)
        status_text.addWidget(status_hint)
        status_layout.addWidget(status_logo)
        status_layout.addLayout(status_text, 1)
        nav_layout.addWidget(status_card)
        self.status_card = status_card

        content = QWidget()
        content.setObjectName("contentPanel")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 18)
        content_layout.setSpacing(16)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_chat_page())
        self.pages.addWidget(self._build_notes_page())
        self.pages.addWidget(self._build_models_page())
        self.pages.addWidget(self._build_info_page(
            "discord", "Discord", "Связь Lumi с твоим сервером — когда будешь готов.",
            "Интеграция Discord пока не подключена. В будущем здесь можно будет настроить бота "
            "и отдельно выбрать, к каким заметкам ему разрешён доступ.",
            "discord-icon.png",
        ))
        self.pages.addWidget(self._build_settings_page())
        content_layout.addWidget(self.pages, 1)

        root_layout.addWidget(nav)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

        about = QAction("О Lumi", self)
        about.triggered.connect(self._show_about)
        self.menuBar().addAction(about)

    def _add_nav(self, layout: QVBoxLayout, key: str, label: str, icon_name: str) -> None:
        button = QPushButton(label)
        button.setObjectName("navButton")
        button.setProperty("navLabel", label)
        button.setCheckable(True)
        button.setIcon(self._asset_icon(icon_name))
        button.setIconSize(QSize(23, 23))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda checked=False, page=key: self._show_page(page))
        layout.addWidget(button)
        self.nav_buttons[key] = button

    def _toggle_sidebar(self) -> None:
        self._set_sidebar_collapsed(not self.sidebar_collapsed)

    def _expand_sidebar(self) -> None:
        if self.sidebar_collapsed:
            self._set_sidebar_collapsed(False)

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        self.sidebar_collapsed = collapsed
        self.nav_panel.setFixedWidth(68 if collapsed else 248)
        nav_layout = self.nav_panel.layout()
        nav_layout.setContentsMargins(7 if collapsed else 14, 14 if collapsed else 20, 7 if collapsed else 14, 12 if collapsed else 16)
        nav_layout.setSpacing(7)
        self.brand_text_widget.setVisible(not collapsed)
        self.sidebar_toggle.setVisible(not collapsed)
        self.nav_caption.setVisible(not collapsed)
        self.status_card.setVisible(not collapsed)
        self.brand_logo_button.setToolTip("Нажми, чтобы развернуть панель" if collapsed else "Lumi AI")
        for button in self.nav_buttons.values():
            label = str(button.property("navLabel"))
            button.setText("" if collapsed else label)
            button.setToolTip(label if collapsed else "")
            button.setStyleSheet("text-align: center; padding: 10px 4px;" if collapsed else "")

    def _page_heading(self, title: str, subtitle: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        desc = QLabel(subtitle)
        desc.setObjectName("pageSubtitle")
        desc.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(desc)
        return layout

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(14)

        self.chat_history_panel = QFrame()
        self.chat_history_panel.setObjectName("historyPanel")
        self.chat_history_panel.setFixedWidth(238)
        history_layout = QVBoxLayout(self.chat_history_panel)
        history_layout.setContentsMargins(12, 14, 12, 12)
        history_layout.setSpacing(12)
        history_title = QLabel("Твои чаты")
        history_title.setObjectName("section")
        history_layout.addWidget(history_title)

        self.new_chat_button = QPushButton("＋  Новый чат")
        self.new_chat_button.setObjectName("primaryButton")
        self.new_chat_button.setToolTip("Начать новый чат (пока демонстрационный режим)")
        self.new_chat_button.clicked.connect(self._new_chat_visual)
        history_layout.addWidget(self.new_chat_button)

        self.chat_search = QLineEdit()
        self.chat_search.setPlaceholderText("⌕  Поиск по чатам")
        self.chat_search.textChanged.connect(self._filter_chat_history)
        history_layout.addWidget(self.chat_search)

        self.chat_history_list = QListWidget()
        self.chat_history_list.setObjectName("chatHistoryList")
        self.chat_history_list.addItem("История появится здесь")
        self.chat_history_list.item(0).setFlags(Qt.ItemFlag.NoItemFlags)
        history_layout.addWidget(self.chat_history_list, 1)
        history_hint = QLabel("Сохранение истории будет добавлено отдельно.")
        history_hint.setObjectName("muted")
        history_hint.setWordWrap(True)
        history_layout.addWidget(history_hint)
        outer.addWidget(self.chat_history_panel)

        chat_area = QWidget()
        layout = QVBoxLayout(chat_area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        heading = QHBoxLayout()
        heading_text = QVBoxLayout()
        title = QLabel("Чат с Lumi")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Твоя неоновая помощница с лисьим характером")
        subtitle.setObjectName("pageSubtitle")
        heading_text.addWidget(title)
        heading_text.addWidget(subtitle)
        heading.addLayout(heading_text, 1)
        self.chat_status = QLabel("●  ИИ ещё не подключён")
        self.chat_status.setStyleSheet("color: #D7B879; font-size: 9pt;")
        heading.addWidget(self.chat_status, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(heading)

        # Scrollable transcript: messages move, while the composer stays fixed below.
        self.chat_transcript = QScrollArea()
        self.chat_transcript.setObjectName("chatTranscript")
        self.chat_transcript.setWidgetResizable(True)
        self.chat_transcript.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_transcript.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_transcript.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.chat_transcript.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.chat_transcript_content = QWidget()
        self.chat_transcript_content.setObjectName("chatTranscriptContent")
        transcript_layout = QVBoxLayout(self.chat_transcript_content)
        transcript_layout.setContentsMargins(22, 22, 22, 22)
        transcript_layout.setSpacing(14)
        transcript_layout.addStretch(1)
        # Keep the message layout reusable for responses received from Lumi's internal AI API.
        self.chat_messages_layout = transcript_layout
        self.chat_transcript.setWidget(self.chat_transcript_content)
        self._add_lumi_message(
            "Привет! ✨\n"
            "Я Lumi — твоя неоновая помощница с лисьим характером.\n\n"
            "Сейчас мы готовим мой чат. На этом этапе можно проверить оформление, "
            "а подключение настоящей локальной модели будет отдельной задачей.",
            show_logo=True,
        )
        layout.addWidget(self.chat_transcript, 1)

        composer = QFrame()
        composer.setObjectName("composer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(12, 8, 12, 8)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Напиши сообщение Lumi…")
        self.chat_input.returnPressed.connect(self._send_chat_message)
        self.send_chat_button = QPushButton("Отправить  ➤")
        self.send_chat_button.setObjectName("primaryButton")
        self.send_chat_button.clicked.connect(self._send_chat_message)
        composer_layout.addWidget(self.chat_input, 1)
        composer_layout.addWidget(self.send_chat_button)
        layout.addWidget(composer)
        footnote = QLabel("Локальный режим выбран по умолчанию. Облако включается только в настройках.")
        footnote.setObjectName("muted")
        layout.addWidget(footnote)
        outer.addWidget(chat_area, 1)
        self.chat_history_panel.setVisible(False)
        return page

    def _send_chat_message(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        if str(self.settings.value("ai/mode", "local")) != "cloud":
            self._add_user_message(text)
            self.chat_input.clear()
            self._add_lumi_message(
                "Я получила сообщение, но сейчас выбран локальный режим. Локальный движок ещё не подключён. "
                "Чтобы использовать Grok 4.6, отдельно включи AnyModel в настройках. Сейчас сообщение в интернет не отправлено.",
                show_logo=True,
            )
            self.chat_status.setText("●  Локальный режим")
            self.chat_status.setStyleSheet("color: #7CEEFF; font-size: 9pt;")
            return
        key = str(self.settings.value("anymodel/api_key", "")).strip()
        if not key:
            QMessageBox.warning(self, "Нужен API-ключ", "Добавь ключ AnyModel в Настройки → Подключение ИИ.")
            return
        if self.api_worker is not None and self.api_worker.isRunning():
            return
        self._add_user_message(text)
        self.chat_input.clear()
        self.chat_messages.append({"role": "user", "content": text})
        self.send_chat_button.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.chat_status.setText("●  Lumi думает…")
        self.chat_status.setStyleSheet("color: #B8A5FF; font-size: 9pt;")
        model = str(self.settings.value("anymodel/model", "xai/grok-4.6"))
        self.api_worker = AnyModelRequestWorker(key, model, list(self.chat_messages))
        self.api_worker.succeeded.connect(self._on_cloud_response)
        self.api_worker.failed.connect(self._on_cloud_error)
        self.api_worker.finished.connect(self._on_cloud_request_finished)
        self.api_worker.start()

    def _add_user_message(self, text: str) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(24, 0, 0, 0)
        row_layout.addStretch(1)
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextFormat(Qt.TextFormat.PlainText)
        bubble.setStyleSheet("background: #202847; border: 1px solid #394A78; border-radius: 12px; padding: 12px; color: #F2F4FF;")
        bubble.setMaximumWidth(760)
        bubble.setMinimumHeight(44)
        bubble.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_layout.addWidget(bubble, 1)
        self._append_chat_message(row)

    def _append_chat_message(self, widget: QWidget) -> None:
        """Append a message and follow it only when the reader was already at the bottom."""
        bar = self.chat_transcript.verticalScrollBar()
        follow_latest = bar.maximum() - bar.value() <= 32
        # Insert before the trailing stretch so messages stay packed at the top.
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, widget)
        if follow_latest:
            QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _on_cloud_response(self, answer: str) -> None:
        self.chat_messages.append({"role": "assistant", "content": answer})
        self._add_lumi_message(answer, show_logo=True)
        self.chat_status.setText("●  AnyModel · Grok 4.6")
        self.chat_status.setStyleSheet("color: #7CEEFF; font-size: 9pt;")

    def _on_cloud_error(self, message: str) -> None:
        self._add_lumi_message(message, show_logo=True)
        self.chat_status.setText("●  Ошибка подключения")
        self.chat_status.setStyleSheet("color: #FF9C9C; font-size: 9pt;")
        if self.chat_messages and self.chat_messages[-1].get("role") == "user":
            self.chat_messages.pop()

    def _on_cloud_request_finished(self) -> None:
        self.chat_input.setEnabled(True)
        self.send_chat_button.setEnabled(True)
        self.chat_input.setFocus()

    def _add_lumi_message(self, text: str, *, show_logo: bool = True) -> QWidget:
        """Add a Lumi response bubble; safe to call with plain text returned by the internal AI API.

        QLabel wraps long lines to the available width. Real newline characters from the
        API are preserved. Normalize literal backslash-n sequences too, for older/mock
        responses that may contain escaped newlines.
        """
        message_text = str(text).replace("\\r\\n", "\n").replace("\\n", "\n")
        row_widget = QWidget()
        row_layout = QVBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        if show_logo:
            logo_row = QHBoxLayout()
            logo_row.setContentsMargins(24, 0, 0, 0)
            avatar = QLabel()
            avatar.setFixedSize(126, 62)
            avatar.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            avatar.setStyleSheet("background: transparent;")
            avatar.setAutoFillBackground(False)
            avatar.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            avatar.setPixmap(QPixmap(str(resource_path("assets/Люми — неоновый лисий логотип.png"))).scaled(
                122, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
            logo_row.addWidget(avatar, 0, Qt.AlignmentFlag.AlignLeft)
            logo_row.addStretch(1)
            row_layout.addLayout(logo_row)

        bubble_row = QHBoxLayout()
        bubble_row.setContentsMargins(76 if show_logo else 24, 0, 0, 0)
        bubble = QLabel(message_text)
        bubble.setObjectName("lumiMessage")
        bubble.setWordWrap(True)
        bubble.setTextFormat(Qt.TextFormat.PlainText)
        bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bubble.setMaximumWidth(900)
        bubble.setMinimumWidth(0)
        bubble.setMinimumHeight(48)
        bubble.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        bubble_row.addWidget(bubble, 1)
        row_layout.addLayout(bubble_row)
        self._append_chat_message(row_widget)
        return row_widget

    def display_lumi_response(self, text: str) -> None:
        """Entry point for the internal AI/API layer to display a returned response."""
        self._add_lumi_message(text, show_logo=True)

    def _new_chat_visual(self) -> None:
        self.chat_history_list.clear()
        self.chat_history_list.addItem("Новый чат — пока пусто")
        self.chat_history_list.item(0).setFlags(Qt.ItemFlag.NoItemFlags)

    def _filter_chat_history(self, query: str) -> None:
        needle = query.strip().casefold()
        for index in range(self.chat_history_list.count()):
            item = self.chat_history_list.item(index)
            item.setHidden(bool(needle) and needle not in item.text().casefold())

    def _build_notes_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(14)
        layout.addLayout(self._page_heading("Твои заметки", "Идеи и важная информация остаются на твоём компьютере."))
        row = QHBoxLayout()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("⌕  Найти заметку…")
        self.search.textChanged.connect(self._reload_notes)
        left_layout.addWidget(self.search)
        self.notes_list = QListWidget()
        self.notes_list.currentRowChanged.connect(self._select_note)
        left_layout.addWidget(self.notes_list, 1)
        controls = QHBoxLayout()
        new_button = QPushButton("＋ Новая")
        new_button.clicked.connect(self._new_note)
        delete_button = QPushButton("Удалить")
        delete_button.clicked.connect(self._delete_note)
        controls.addWidget(new_button)
        controls.addWidget(delete_button)
        left_layout.addLayout(controls)

        editor = QFrame()
        editor.setObjectName("card")
        edit_layout = QVBoxLayout(editor)
        edit_layout.setContentsMargins(16, 16, 16, 16)
        edit_heading = QLabel("Редактор заметки")
        edit_heading.setObjectName("section")
        edit_layout.addWidget(edit_heading)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Название заметки")
        self.body_edit = QTextEdit()
        self.body_edit.setPlaceholderText("Запиши сюда идею, план или важную информацию…")
        edit_layout.addWidget(self.title_edit)
        checklist_toolbar = QHBoxLayout()
        add_checklist_button = QPushButton("☷  Добавить блок задач")
        add_checklist_button.setToolTip("Вставить список задач с чекбоксами в заметку")
        add_checklist_button.clicked.connect(self._insert_checklist)
        toggle_check_button = QPushButton("☑  Отметить / снять")
        toggle_check_button.setToolTip("Переключить чекбокс в текущей строке")
        toggle_check_button.clicked.connect(self._toggle_current_checkbox)
        checklist_toolbar.addWidget(add_checklist_button)
        checklist_toolbar.addWidget(toggle_check_button)
        checklist_toolbar.addStretch(1)
        edit_layout.addLayout(checklist_toolbar)
        edit_layout.addWidget(self.body_edit, 1)
        self.status = QLabel("Заметки сохраняются на этом компьютере.")
        self.status.setObjectName("muted")
        save_button = QPushButton("✓  Сохранить заметку")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save_note)
        edit_layout.addWidget(self.status)
        edit_layout.addWidget(save_button)
        row.addWidget(left, 2)
        row.addWidget(editor, 3)
        layout.addLayout(row, 1)
        return page

    def _build_models_page(self) -> QWidget:
        """Model-management UI scaffold; runtime integration will be added later."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(18)
        layout.addLayout(self._page_heading(
            "Модели ИИ", "Локальный режим остаётся основным. Облачные модели доступны только по твоему выбору."
        ))

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(14)

        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(self._asset_icon("ai-icon.png").pixmap(64, 64))
        card_layout.addWidget(icon)

        status_title = QLabel("Grok 4.6 — основная облачная модель")
        status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_title.setStyleSheet("font-size: 16pt; font-weight: 650; color: #B8A5FF;")
        card_layout.addWidget(status_title)

        description = QLabel(
            "Grok 4.6 — основная модель для общения. Grok Build 0.1 предназначен для специализированных задач разработки. "
            "Облачный выбор не отключает локальный режим по умолчанию."
        )
        description.setObjectName("pageSubtitle")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(description)

        self.model_choice = QComboBox()
        self.model_choice.addItem("Grok 4.6 — основная модель", "xai/grok-4.6")
        self.model_choice.addItem("Grok Build 0.1 — инструмент разработки", "xai/grok-build-0.1")
        saved_model = str(self.settings.value("anymodel/model", "xai/grok-4.6"))
        saved_index = self.model_choice.findData(saved_model)
        self.model_choice.setCurrentIndex(saved_index if saved_index >= 0 else 0)
        self.model_choice.currentIndexChanged.connect(
            lambda _index: self.settings.setValue("anymodel/model", self.model_choice.currentData())
        )
        card_layout.addWidget(self.model_choice)

        self.model_file_label = QLabel("Grok 4.6 — основной помощник. Grok Build 0.1 — отдельный специализированный вариант для разработки.")
        self.model_file_label.setObjectName("muted")
        self.model_file_label.setWordWrap(True)
        card_layout.addWidget(self.model_file_label)

        model_buttons = QHBoxLayout()
        choose_model = QPushButton("Выбрать файл модели…")
        choose_model.clicked.connect(self._choose_model_file)
        model_buttons.addWidget(choose_model)

        self.enable_model_button = QPushButton("Открыть настройки подключения")
        self.enable_model_button.setObjectName("primaryButton")
        self.enable_model_button.clicked.connect(lambda: self._show_page("settings"))
        model_buttons.addWidget(self.enable_model_button)

        self.disable_model_button = QPushButton("Локальный режим")
        self.disable_model_button.clicked.connect(self._set_local_mode)
        model_buttons.addWidget(self.disable_model_button)
        card_layout.addLayout(model_buttons)

        compatibility_button = QPushButton("Проверить совместимость")
        compatibility_button.clicked.connect(self._model_placeholder)
        card_layout.addWidget(compatibility_button)

        layout.addWidget(card, 1)
        return page

    def _choose_model_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выбери файл локальной модели",
            "",
            "Модели GGUF (*.gguf);;Все файлы (*.*)",
        )
        if path:
            self.model_file_label.setText(f"Выбран файл: {path}")
            QMessageBox.information(
                self,
                "Файл выбран",
                "Файл запомнен только для этого окна. Загрузка, проверка и запуск модели ещё не подключены.",
            )

    def _model_placeholder(self) -> None:
        QMessageBox.information(self, "Локальные модели Lumi AI",
            "Выбор и запуск локального движка ещё не реализованы. Локальный режим остаётся режимом по умолчанию.")

    def _set_local_mode(self) -> None:
        self.settings.setValue("ai/mode", "local")
        self.chat_status.setText("●  Локальный режим")
        self.chat_status.setStyleSheet("color: #7CEEFF; font-size: 9pt;")
        QMessageBox.information(self, "Локальный режим", "Lumi переключена в локальный режим. Облачные запросы не отправляются.")

    def _save_api_settings(self) -> None:
        key = self.api_key_input.text().strip()
        if key:
            self.settings.setValue("anymodel/api_key", key)
        self.settings.setValue("anymodel/model", self.model_choice.currentData())
        mode = str(self.ai_mode_choice.currentData())
        self.settings.setValue("ai/mode", mode)
        self.api_key_input.clear()
        self.api_key_input.setPlaceholderText("Ключ сохранён локально — введи новый для замены" if self.settings.value("anymodel/api_key", "") else "Вставь API-ключ AnyModel")
        self.chat_status.setText("●  AnyModel включён" if mode == "cloud" else "●  Локальный режим")
        self.chat_status.setStyleSheet("color: #B8A5FF; font-size: 9pt;" if mode == "cloud" else "color: #7CEEFF; font-size: 9pt;")
        QMessageBox.information(self, "Настройки сохранены",
            "Настройки сохранены на этом компьютере. Ключ не добавляется в исходный код. " +
            ("Облачные запросы включены по твоему выбору." if mode == "cloud" else "Локальный режим оставлен по умолчанию."))

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(18)
        layout.addLayout(self._page_heading(
            "Настройки", "Локальный режим включён по умолчанию. AnyModel подключается только по твоему выбору."
        ))

        updates_card = QFrame()
        updates_card.setObjectName("card")
        updates_layout = QVBoxLayout(updates_card)
        updates_layout.setContentsMargins(22, 22, 22, 22)
        updates_layout.setSpacing(10)

        updates_title = QLabel("Обновления приложения")
        updates_title.setObjectName("section")
        updates_layout.addWidget(updates_title)
        updates_description = QLabel(
            "Lumi проверяет только последние стабильные релизы GitHub. Бета-сборки "
            "не предлагаются обновлятором. При обновлении откроется отдельное окно "
            "с этапами проверки, загрузки и установки."
        )
        updates_description.setObjectName("pageSubtitle")
        updates_description.setWordWrap(True)
        updates_layout.addWidget(updates_description)

        current_version = QLabel(f"Установленная версия: {installed_version()}")
        current_version.setObjectName("muted")
        updates_layout.addWidget(current_version)

        update_button = QPushButton("Проверить обновления")
        update_button.setObjectName("primaryButton")
        update_button.clicked.connect(self._start_updater)
        updates_layout.addWidget(update_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(updates_card)

        api_card = QFrame()
        api_card.setObjectName("card")
        api_layout = QVBoxLayout(api_card)
        api_layout.setContentsMargins(22, 22, 22, 22)
        api_layout.setSpacing(10)
        api_title = QLabel("Подключение ИИ")
        api_title.setObjectName("section")
        api_layout.addWidget(api_title)
        api_description = QLabel(
            "Единый API AnyModel для совместимых моделей. Ключ сохраняется в локальных настройках Lumi и не записывается в репозиторий. "
            "В облачном режиме сообщения передаются сервису."
        )
        api_description.setObjectName("pageSubtitle")
        api_description.setWordWrap(True)
        api_layout.addWidget(api_description)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText(
            "Ключ сохранён — введи новый для замены" if str(self.settings.value("anymodel/api_key", "")).strip()
            else "Вставь API-ключ AnyModel"
        )
        api_layout.addWidget(self.api_key_input)
        self.ai_mode_choice = QComboBox()
        self.ai_mode_choice.addItem("Локальный режим (по умолчанию)", "local")
        self.ai_mode_choice.addItem("Облачный режим AnyModel", "cloud")
        self.ai_mode_choice.setCurrentIndex(1 if str(self.settings.value("ai/mode", "local")) == "cloud" else 0)
        api_layout.addWidget(self.ai_mode_choice)
        save_api_button = QPushButton("Сохранить подключение")
        save_api_button.setObjectName("primaryButton")
        save_api_button.clicked.connect(self._save_api_settings)
        api_layout.addWidget(save_api_button, 0, Qt.AlignmentFlag.AlignLeft)
        local_hint = QLabel("В локальном режиме ключ не используется и сообщения не уходят в интернет. Настоящий локальный движок подключим отдельным этапом.")
        local_hint.setObjectName("muted")
        local_hint.setWordWrap(True)
        api_layout.addWidget(local_hint)
        layout.addWidget(api_card)

        model_card = QFrame()
        model_card.setObjectName("card")
        model_layout = QVBoxLayout(model_card)
        model_layout.setContentsMargins(22, 22, 22, 22)
        model_layout.setSpacing(10)
        model_title = QLabel("Поведение ИИ")
        model_title.setObjectName("section")
        model_layout.addWidget(model_title)
        model_description = QLabel(
            "Основная облачная модель — Grok 4.6. Grok Build 0.1 — специализированный вариант для разработки. "
            "Локальный режим остаётся режимом по умолчанию."
        )
        model_description.setObjectName("pageSubtitle")
        model_description.setWordWrap(True)
        model_layout.addWidget(model_description)

        self.autostart_model_checkbox = QPushButton("Вернуться в локальный режим")
        self.autostart_model_checkbox.clicked.connect(self._set_local_mode)
        model_layout.addWidget(self.autostart_model_checkbox, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(model_card)
        layout.addStretch(1)
        return page

    def _build_info_page(self, key: str, title: str, subtitle: str, body: str, icon_name: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(18)
        layout.addLayout(self._page_heading(title, subtitle))
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)
        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(QPixmap(str(resource_path(f"assets/{icon_name}"))).scaled(
            72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        card_layout.addWidget(icon)
        heading = QLabel("Скоро в Lumi")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet("font-size: 16pt; font-weight: 650; color: #B8A5FF;")
        card_layout.addWidget(heading)
        desc = QLabel(body)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setObjectName("pageSubtitle")
        card_layout.addWidget(desc)
        layout.addWidget(card, 1)
        return page

    def _show_page(self, key: str) -> None:
        indexes = {"chat": 0, "notes": 1, "models": 2, "discord": 3, "settings": 4}
        titles = {
            "chat": "Чат с лисичкой", "notes": "Заметки", "models": "Модели ИИ",
            "discord": "Discord", "settings": "Настройки",
        }
        if key not in indexes:
            return
        self.pages.setCurrentIndex(indexes[key])
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)

    def _reload_notes(self, *_: object) -> None:
        if not hasattr(self, "notes_list"):
            return
        selected_id = self.current_note_id
        self.notes_list.blockSignals(True)
        self.notes_list.clear()
        self._note_ids: list[int] = []
        for note in self.store.list_notes(self.search.text()):
            self._note_ids.append(note["id"])
            self.notes_list.addItem(note["title"])
        self.notes_list.blockSignals(False)
        if selected_id in self._note_ids:
            self.notes_list.setCurrentRow(self._note_ids.index(selected_id))
        elif self._note_ids:
            self.notes_list.setCurrentRow(0)
        else:
            self.current_note_id = None
            self.title_edit.clear()
            self.body_edit.clear()

    def _select_note(self, row: int) -> None:
        if row < 0 or row >= len(getattr(self, "_note_ids", [])):
            return
        note_id = self._note_ids[row]
        note = next((item for item in self.store.list_notes() if item["id"] == note_id), None)
        if note is None:
            return
        self.current_note_id = note_id
        self.title_edit.setText(note["title"])
        self.body_edit.setPlainText(note["body"])

    def _new_note(self) -> None:
        self.current_note_id = None
        self.notes_list.clearSelection()
        self.title_edit.clear()
        self.body_edit.clear()
        self.title_edit.setFocus()
        self.status.setText("Новая заметка")

    def _insert_checklist(self) -> None:
        cursor = self.body_edit.textCursor()
        text_before = self.body_edit.toPlainText()[:cursor.position()]
        if text_before and not text_before.endswith("\n"):
            cursor.insertText("\n")
        cursor.insertText("☐ Задача 1\n☐ Задача 2\n☐ Задача 3")
        self.body_edit.setTextCursor(cursor)
        self.body_edit.setFocus()

    def _toggle_current_checkbox(self) -> None:
        cursor = self.body_edit.textCursor()
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        line = cursor.selectedText()
        if line.startswith("☐ "):
            updated = "☑ " + line[2:]
        elif line.startswith("☑ "):
            updated = "☐ " + line[2:]
        else:
            updated = "☐ " + line
        cursor.insertText(updated)
        self.body_edit.setTextCursor(cursor)
        self.body_edit.setFocus()

    def _save_note(self) -> None:
        note_id = self.store.save_note(
            self.title_edit.text(), self.body_edit.toPlainText(), self.current_note_id
        )
        self.current_note_id = note_id
        self._reload_notes()
        if note_id in self._note_ids:
            self.notes_list.setCurrentRow(self._note_ids.index(note_id))
        self.status.setText("Сохранено локально ✓")

    def _delete_note(self) -> None:
        if self.current_note_id is None:
            return
        answer = QMessageBox.question(self, "Удалить заметку", "Точно удалить выбранную заметку?")
        if answer == QMessageBox.StandardButton.Yes:
            self.store.delete_note(self.current_note_id)
            self.current_note_id = None
            self._reload_notes()

    def _start_updater(self) -> None:
        updater = Path(sys.executable).resolve().parent / "LumiUpdater.exe"
        if not updater.is_file():
            QMessageBox.warning(
                self, "Обновление Lumi AI",
                "Обновлятор ещё не включён в эту сборку. Скачай последнюю сборку после завершения настройки обновлений.",
            )
            return
        answer = QMessageBox.question(
            self, "Проверить обновления",
            "Lumi проверит наличие новой версии. Приложение закроется на время установки. Продолжить?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            subprocess.Popen([str(updater), "--update"], cwd=str(updater.parent))
        except OSError as exc:
            QMessageBox.critical(self, "Обновление Lumi AI", f"Не удалось запустить обновлятор:\n{exc}")
            return
        QApplication.quit()

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "О Lumi",
            f"Lumi {__version__}\nТвоя умная помощница.\n\n"
            "Заметки работают локально. Подключение ИИ и Discord планируется отдельными этапами.",
        )


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Lumi")
    app.setOrganizationName("Lumi")
    app.setWindowIcon(QIcon(str(resource_path("assets/lumi-app-icon.png"))))
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    window = LumiWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
