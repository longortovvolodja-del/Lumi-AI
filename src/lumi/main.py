"""Lumi desktop app: neon sidebar, local notes and planned AI sections."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import json
import urllib.error
import urllib.request

from PySide6.QtCore import Qt, QSize, QThread, Signal, QSettings, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QInputDialog, QMenu,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSizePolicy,
    QScrollArea, QStackedWidget, QTextEdit, QTextBrowser, QVBoxLayout, QWidget, QCheckBox, QToolButton,
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
/* Labels must not paint their own opaque background; this caused black bars
   behind settings text and inside each chat message row. */
QLabel { background: transparent; }
QLabel#section, QLabel#pageSubtitle, QLabel#muted, QLabel#pageTitle,
QLabel#subtitle, QLabel#brand { background: transparent; }
QWidget#navPanel { background: #020D30; border-right: 1px solid #20263B; }
QWidget#contentPanel { background: #0A0C16; }
QFrame#historyPanel { background: #080F26; border: 1px solid #1D2B4A; border-radius: 14px; }
QScrollArea#chatTranscript { background: #0C1222; border: 1px solid #202B45; border-radius: 16px; }
QWidget#chatTranscriptContent { background: transparent; }
QFrame#composer { background: #10182B; border: 1px solid #263653; border-radius: 14px; }
QTextBrowser#lumiMessage { background: #121E38; border: 1px solid #254B6B; border-radius: 12px; padding: 10px; color: #EAF6FF; }
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


NOTES_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "Найти заметки или показать список заметок. Возвращает идентификаторы, названия и даты, но не полное содержимое.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Необязательная фраза для поиска по названию и тексту"}},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_note",
            "description": "Прочитать полное содержимое одной заметки по её ID. Сначала используй list_notes, если ID неизвестен.",
            "parameters": {
                "type": "object",
                "properties": {"note_id": {"type": "integer", "description": "ID заметки"}},
                "required": ["note_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": "Создать новую локальную заметку с названием и содержимым.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Название заметки"},
                    "body": {"type": "string", "description": "Полный текст заметки"},
                },
                "required": ["title", "body"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_note",
            "description": "Обновить название и/или текст существующей заметки. Сначала найди и прочитай нужную заметку.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer", "description": "ID заметки для изменения"},
                    "title": {"type": "string", "description": "Новое название; если не указано, оставить прежнее"},
                    "body": {"type": "string", "description": "Новый полный текст; если не указан, оставить прежний"},
                },
                "required": ["note_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "Запросить удаление заметки по ID. Приложение обязательно попросит пользователя подтвердить удаление.",
            "parameters": {
                "type": "object",
                "properties": {"note_id": {"type": "integer", "description": "ID заметки для удаления"}},
                "required": ["note_id"],
                "additionalProperties": False,
            },
        },
    },
]


class AnyModelRequestWorker(QThread):
    """Stream an AnyModel chat/tool response away from the UI thread."""
    succeeded = Signal(object)
    failed = Signal(str)
    token_received = Signal(str)
    transport_status = Signal(str)

    def __init__(self, api_key: str, model_id: str, messages: list[dict], tools: list[dict] | None = None) -> None:
        super().__init__()
        self.api_key, self.model_id, self.messages = api_key, model_id, messages
        self.tools = tools or NOTES_TOOL_DEFINITIONS

    def run(self) -> None:
        payload_data = {"model": self.model_id, "messages": self.messages, "stream": True}
        if self.tools:
            payload_data["tools"] = self.tools
            payload_data["tool_choice"] = "auto"
        payload = json.dumps(payload_data, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            "https://anymodel.org/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            },
            method="POST",
        )
        try:
            content_parts: list[str] = []
            tool_calls: dict[int, dict] = {}
            finish_reason = None
            with urllib.request.urlopen(request, timeout=90) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/event-stream" not in content_type:
                    # Report the actual transport: a JSON response is inherently
                    # buffered, so the UI cannot stream it even if stream=True was sent.
                    self.transport_status.emit(
                        f"Поток не предоставлен сервером (Content-Type: {content_type or 'не указан'}); получен обычный ответ."
                    )
                    data = json.loads(response.read().decode("utf-8"))
                else:
                    self.transport_status.emit("Потоковая передача SSE подключена.")
                    # Some OpenAI-compatible gateways send the whole SSE body at once;
                    # line-by-line parsing below cannot fix server-side buffering.
                    # Keep consuming individual events as soon as the socket exposes them.
                    pass
                if "text/event-stream" not in content_type:
                    message = dict(data["choices"][0]["message"])
                    answer = message.get("content")
                    if isinstance(answer, list):
                        message["content"] = "\n".join(
                            str(part.get("text", "")) if isinstance(part, dict) else str(part)
                            for part in answer
                        )
                    if not message.get("tool_calls") and not str(message.get("content") or "").strip():
                        raise ValueError("Сервис вернул пустой ответ без вызова инструмента.")
                    self.succeeded.emit(message)
                    return

                # Read SSE one line at a time. response.read(2048) may wait for
                # a large buffer or EOF on some gateways, making streaming appear broken.
                stream_done = False
                while not stream_done:
                    raw_line = response.readline()
                    if not raw_line:
                        break
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or line.startswith(":") or not line.startswith("data:"):
                        continue
                    data_text = line[5:].strip()
                    if data_text == "[DONE]":
                        stream_done = True
                        continue
                    try:
                        packet = json.loads(data_text)
                    except json.JSONDecodeError:
                        continue
                    choices = packet.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    piece = delta.get("content")
                    if isinstance(piece, str) and piece:
                        content_parts.append(piece)
                        self.token_received.emit(piece)
                    for item in delta.get("tool_calls") or []:
                        index = int(item.get("index", 0))
                        target = tool_calls.setdefault(index, {
                            "id": "", "type": "function",
                            "function": {"name": "", "arguments": ""},
                        })
                        if item.get("id"):
                            target["id"] += str(item["id"])
                        if item.get("type"):
                            target["type"] = item["type"]
                        function = item.get("function") or {}
                        if function.get("name"):
                            target["function"]["name"] += str(function["name"])
                        if function.get("arguments"):
                            target["function"]["arguments"] += str(function["arguments"])
                    if choice.get("finish_reason") is not None:
                        finish_reason = choice.get("finish_reason")

            message = {"role": "assistant", "content": "".join(content_parts) or None}
            if tool_calls:
                message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
            if not message.get("tool_calls") and not str(message.get("content") or "").strip():
                raise ValueError(f"Сервис вернул пустой ответ без вызова инструмента (finish_reason={finish_reason}).")
            self.succeeded.emit(message)
        except urllib.error.HTTPError as exc:
            try: detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception: detail = str(exc)
            if exc.code == 403 and ("1010" in detail or "error code: 1010" in detail.lower()):
                self.failed.emit(
                    "AnyModel отклонил HTTP-запрос (403 / 1010). "
                    "Это ответ защитного слоя сервера, а не ошибка ID модели. "
                    "Проверьте тот же ключ и запрос в официальном клиенте AnyModel; "
                    "если там работает, обратитесь в поддержку AnyModel по поводу блокировки клиента."
                )
            else:
                self.failed.emit(f"Ошибка API HTTP {exc.code}: {detail}")
        except urllib.error.URLError as exc:
            self.failed.emit(f"Не удалось подключиться к AnyModel: {exc.reason}")
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.failed.emit(f"Не удалось прочитать ответ AnyModel: {exc}")
        except Exception as exc:
            self.failed.emit(f"Ошибка запроса: {exc}")


class MarkdownMessageBrowser(QTextBrowser):
    """Markdown bubble whose height follows rendered content instead of clipping it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.document().setDocumentMargin(0)
        self.setStyleSheet(
            "QTextBrowser#lumiMessage { background: #121E38; border: 1px solid #254B6B; "
            "border-radius: 12px; padding: 10px; color: #EAF6FF; }"
            "QTextBrowser#lumiMessage a { color: #7CEEFF; }"
        )
        self.setMinimumHeight(48)
        self.setMaximumWidth(900)
        self.setMinimumWidth(0)
        self.setMarkdown("")

    @staticmethod
    def _normalize_markdown(markdown: str) -> str:
        import re

        text = str(markdown).replace("\\r\\n", "\n").replace("\\n", "\n")
        # Separate a bold section title from the numbered item that a model
        # sometimes appends on the same line, avoiding a merged list section.
        text = re.sub(
            r"(?<!\n)(\*\*[^*\n]{2,60}\*\*)\s+(?=(?:[1-9]\d?\.)\s)",
            r"\1\n\n",
            text,
        )
        return text
    def set_markdown(self, markdown: str) -> None:
        self.setMarkdown(self._normalize_markdown(markdown))
        self._fit_to_document()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_to_document()

    def _fit_to_document(self) -> None:
        # Reflow at the actual viewport width so long Markdown lines wrap and
        # the widget grows vertically as tokens arrive.
        width = max(80, self.viewport().width())
        self.document().setTextWidth(width)
        height = int(self.document().size().height() + 24)
        self.setMinimumHeight(max(48, height))
        self.setFixedHeight(max(48, height))


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
        try:
            self.chat_sessions: list[dict[str, object]] = json.loads(str(self.settings.value("chat/sessions", "[]")))
        except (TypeError, ValueError, json.JSONDecodeError):
            self.chat_sessions = []
        self.active_chat_session: dict[str, object] | None = None
        self.active_chat_title = "Новый чат"
        self.api_worker: AnyModelRequestWorker | None = None
        self._tool_round_active = False
        self._tool_round_count = 0
        self._activity_events: list[dict[str, str]] = []
        self._activity_started_at = 0.0
        self._activity_container: QFrame | None = None
        self._activity_header: QToolButton | None = None
        self._activity_details: QWidget | None = None
        self._activity_details_layout: QVBoxLayout | None = None
        self._activity_duration_label: QLabel | None = None
        self._pending_activity_duration: QLabel | None = None
        self._activity_message_widget: QWidget | None = None
        self._activity_message_layout: QVBoxLayout | None = None
        self.current_note_id: int | None = None
        self.nav_buttons: dict[str, QPushButton] = {}
        self.sidebar_collapsed = False
        self.chat_history_collapsed = False
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

    def _toggle_chat_history(self) -> None:
        self.chat_history_collapsed = not self.chat_history_collapsed
        self.chat_history_panel.setVisible(not self.chat_history_collapsed and self.pages.currentIndex() == 0)
        self.history_toggle_button.setText("›" if self.chat_history_collapsed else "‹")
        self.history_toggle_button.setToolTip("Развернуть список чатов" if self.chat_history_collapsed else "Свернуть список чатов")

    def _expand_sidebar(self) -> None:
        if self.sidebar_collapsed:
            self._set_sidebar_collapsed(False)

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        self.sidebar_collapsed = collapsed
        self.nav_panel.setFixedWidth(68 if collapsed else 248)
        if hasattr(self, "chat_history_panel"):
            self.chat_history_panel.setVisible(not self.chat_history_collapsed and self.pages.currentIndex() == 0)
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
        self.chat_history_panel.setFixedWidth(300)
        history_layout = QVBoxLayout(self.chat_history_panel)
        history_layout.setContentsMargins(12, 14, 12, 12)
        history_layout.setSpacing(12)
        history_heading = QHBoxLayout()
        history_title = QLabel("Твои чаты")
        history_title.setObjectName("section")
        history_heading.addWidget(history_title, 1)
        self.history_toggle_button = QPushButton("‹")
        self.history_toggle_button.setObjectName("navToggle")
        self.history_toggle_button.setToolTip("Свернуть список чатов")
        self.history_toggle_button.clicked.connect(self._toggle_chat_history)
        history_heading.addWidget(self.history_toggle_button)
        history_layout.addLayout(history_heading)

        self.new_chat_button = QPushButton("＋  Новый чат")
        self.new_chat_button.setObjectName("primaryButton")
        self.new_chat_button.setToolTip("Начать новый чат")
        self.new_chat_button.clicked.connect(self._new_chat_visual)
        history_layout.addWidget(self.new_chat_button)

        self.chat_search = QLineEdit()
        self.chat_search.setPlaceholderText("⌕  Поиск по чатам")
        self.chat_search.textChanged.connect(self._filter_chat_history)
        history_layout.addWidget(self.chat_search)

        self.chat_history_list = QListWidget()
        self.chat_history_list.setObjectName("chatHistoryList")
        self.chat_history_list.itemDoubleClicked.connect(self._open_chat_session)
        self.chat_history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_history_list.customContextMenuRequested.connect(self._show_chat_context_menu)
        self._refresh_chat_history()
        history_layout.addWidget(self.chat_history_list, 1)
        history_hint = QLabel("История чатов хранится локально на этом компьютере.")
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
        self.chat_history_panel.setVisible(not self.chat_history_collapsed)
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
            QMessageBox.warning(self, "Нужен API-ключ", "Добавь ключ AnyModel в Модели ИИ → Облачные модели.")
            return
        if self.api_worker is not None and self.api_worker.isRunning():
            return
        self._add_user_message(text)
        self.chat_input.clear()
        self.chat_messages.append({"role": "user", "content": text})
        if self.active_chat_title == "Новый чат":
            title = " ".join(text.split())
            self.active_chat_title = title[:42] + ("…" if len(title) > 42 else "")
        self._commit_active_chat()
        self.send_chat_button.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.chat_status.setText("●  Lumi думает…")
        self.chat_status.setStyleSheet("color: #B8A5FF; font-size: 9pt;")
        model = str(self.settings.value("anymodel/model", "xai/grok-4.6"))
        messages = [{"role": "system", "content": self._effective_system_prompt()}] + list(self.chat_messages)
        self._tool_round_active = True
        self._tool_round_count = 0
        self._activity_events = [{"title": "Запрос принят", "detail": "Сообщение передано выбранной облачной модели.", "status": "ok"}]
        self._activity_started_at = time.perf_counter()
        self._create_live_activity_block()
        self._streaming_text = ""
        self._streaming_widget = None
        self.api_worker = AnyModelRequestWorker(key, model, messages)
        self.api_worker.token_received.connect(self._on_cloud_chunk)
        self.api_worker.transport_status.connect(self._on_transport_status)
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

    def _record_activity(self, title: str, detail: str, status: str = "ok") -> None:
        """Store a concise record of a real action and refresh the live chat activity block."""
        self._activity_events.append({
            "title": str(title),
            "detail": str(detail),
            "status": status if status in {"ok", "error", "cancelled", "running"} else "ok",
        })
        self._refresh_live_activity_details()

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        if seconds < 60:
            return f"{seconds:.1f} с"
        minutes, remaining = divmod(int(seconds), 60)
        return f"{minutes} мин {remaining} с"

    def _create_live_activity_block(self) -> QWidget:
        """Create one assistant message shell for logo, activity log, answer and duration."""
        wrapper = QWidget()
        wrapper.setObjectName("lumiAssistantMessage")
        wrapper.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        wrapper.setStyleSheet("QWidget#lumiAssistantMessage { background: transparent; }")
        wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        message_layout = QVBoxLayout(wrapper)
        message_layout.setContentsMargins(0, 0, 0, 4)
        message_layout.setSpacing(4)

        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(24, 0, 0, 0)
        avatar = QLabel()
        avatar.setFixedSize(112, 52)
        avatar.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        avatar.setStyleSheet("background: transparent;")
        avatar.setAutoFillBackground(False)
        avatar.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        avatar.setPixmap(QPixmap(str(resource_path("assets/Люми — неоновый лисий логотип.png"))).scaled(
            108, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        logo_row.addWidget(avatar, 0, Qt.AlignmentFlag.AlignLeft)
        logo_row.addStretch(1)
        message_layout.addLayout(logo_row)

        container = QFrame()
        container.setObjectName("activityBlock")
        container.setStyleSheet(
            "QFrame#activityBlock { background: #111D37; border: 1px solid #34517A; "
            "border-radius: 12px; }"
            "QToolButton { background: transparent; border: none; color: #DCE8FF; "
            "text-align: left; padding: 10px 14px; font-weight: 600; }"
            "QLabel { background: transparent; color: #D9E2F8; }"
            "QWidget#lumiResponseContent { background: transparent; }"
        )
        activity_layout = QVBoxLayout(container)
        activity_layout.setContentsMargins(0, 0, 0, 10)
        activity_layout.setSpacing(0)
        header = QToolButton()
        header.setText("…  Люми выполняет задачу")
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        header.setCheckable(True)
        header.setChecked(False)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(14, 0, 14, 12)
        details_layout.setSpacing(10)
        details.setVisible(False)
        header.toggled.connect(details.setVisible)
        activity_layout.addWidget(header)
        activity_layout.addWidget(details)

        activity_row = QHBoxLayout()
        activity_row.setContentsMargins(76, 0, 24, 0)
        activity_row.setSpacing(0)
        activity_row.addWidget(container, 1)
        message_layout.addLayout(activity_row)

        self._activity_container = container
        self._activity_header = header
        self._activity_details = details
        self._activity_details_layout = details_layout
        self._activity_message_widget = wrapper
        self._activity_message_layout = message_layout
        self._refresh_live_activity_details()
        self._append_chat_message(wrapper)
        return wrapper

    def _refresh_live_activity_details(self) -> None:
        """Rebuild the expandable details from real action events while keeping the same block."""
        details_layout = self._activity_details_layout
        if details_layout is None:
            return
        while details_layout.count():
            item = details_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                child_layout = item.layout()
                while child_layout.count():
                    child = child_layout.takeAt(0)
                    if child.widget() is not None:
                        child.widget().deleteLater()
        for event in self._activity_events:
            line = QHBoxLayout()
            line.setSpacing(9)
            status = str(event.get("status", "ok"))
            symbol = "✓" if status == "ok" else ("✕" if status == "error" else ("↶" if status == "cancelled" else "…"))
            marker = QLabel(symbol)
            marker.setFixedWidth(16)
            marker.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            marker.setStyleSheet("color: #7CEEFF; font-weight: 700;" if status == "ok" else ("color: #FFB2B2;" if status in {"error", "cancelled"} else "color: #B8A5FF;"))
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            title = QLabel(str(event.get("title", "Действие")))
            title.setStyleSheet("font-weight: 600; color: #F2F4FF;")
            title.setWordWrap(True)
            detail = QLabel(str(event.get("detail", "")))
            detail.setStyleSheet("font-size: 9pt; color: #9EACC9;")
            detail.setWordWrap(True)
            text_col.addWidget(title)
            if detail.text():
                text_col.addWidget(detail)
            line.addWidget(marker)
            line.addLayout(text_col, 1)
            details_layout.addLayout(line)
        if self._activity_header is not None and self._activity_started_at:
            self._activity_header.setText("…  Люми выполняет задачу")
        if self._activity_container is not None:
            self._activity_container.adjustSize()

    def _finish_live_activity(self, *, success: bool) -> None:
        """Close the live log; duration is shown once, beneath Lumi's response."""
        if not self._activity_started_at:
            return
        elapsed = time.perf_counter() - self._activity_started_at
        if self._activity_header is not None:
            self._activity_header.setText("✓  Действия выполнены  ▾" if success else "!  Выполнение завершено  ▾")
        self._activity_started_at = 0.0
        # Keep the log available for inspection, but do not repeat the duration in its header.
        self._activity_header = None
        self._activity_details = None
        self._activity_details_layout = None
        self._activity_duration_label = QLabel(f"Completed in {self._format_elapsed(elapsed)}")
        self._activity_duration_label.setObjectName("muted")
        self._activity_duration_label.setStyleSheet("color: #8D97B8; font-size: 9pt;")
        self._activity_duration_label.setContentsMargins(76, 0, 24, 4)
        self._pending_activity_duration = self._activity_duration_label

    def _append_pending_activity_duration(self) -> None:
        """Place elapsed-time caption inside the same assistant message shell."""
        label = self._pending_activity_duration
        if label is None:
            return
        if self._activity_message_layout is not None and self._activity_message_widget is not None:
            label.setContentsMargins(88, 2, 36, 4)
            activity_layout = self._activity_container.layout() if self._activity_container is not None else None
            if activity_layout is not None:
                activity_layout.addWidget(label)
            else:
                self._activity_message_layout.addWidget(label)
        else:
            self._append_chat_message(label)
        self._pending_activity_duration = None
        self._activity_container = None
        self._activity_message_widget = None
        self._activity_message_layout = None

    def _start_tool_followup(self) -> None:
        """Ask the model to continue after a tool result, without unlocking the chat."""
        key = str(self.settings.value("anymodel/api_key", "")).strip()
        model = str(self.settings.value("anymodel/model", "xai/grok-4.6"))
        messages = [{"role": "system", "content": self._effective_system_prompt()}] + list(self.chat_messages)
        self._streaming_text = ""
        self._streaming_widget = None
        self.api_worker = AnyModelRequestWorker(key, model, messages)
        self.api_worker.token_received.connect(self._on_cloud_chunk)
        self.api_worker.transport_status.connect(self._on_transport_status)
        self.api_worker.succeeded.connect(self._on_cloud_response)
        self.api_worker.failed.connect(self._on_cloud_error)
        self.api_worker.finished.connect(self._on_cloud_request_finished)
        self.api_worker.start()

    @staticmethod
    def _describe_tool_action(name: str, arguments: dict) -> str:
        """Describe the actual tool call without exposing secrets or full note bodies."""
        if name == "list_notes":
            query = str(arguments.get("query", "")).strip()
            return f"Поиск заметок по фразе «{query}»." if query else "Запрошен список сохранённых заметок."
        if name == "read_note":
            return f"Запрошено чтение заметки с ID {arguments.get('note_id', '?')}."
        if name == "create_note":
            return f"Создание заметки «{str(arguments.get('title', 'Без названия'))[:100]}»."
        if name == "update_note":
            parts = []
            if "title" in arguments:
                parts.append("изменение названия")
            if "body" in arguments:
                parts.append("изменение текста")
            return f"Заметка ID {arguments.get('note_id', '?')}: {', '.join(parts) or 'запрошено обновление'}."
        if name == "delete_note":
            return f"Запрошено удаление заметки с ID {arguments.get('note_id', '?')}."
        return "Переданы аргументы зарегистрированному инструменту."

    @staticmethod
    def _tool_result_title(name: str, result: dict) -> str:
        if not result.get("ok"):
            return "Действие отменено" if result.get("cancelled") else "Инструмент завершился с ошибкой"
        return {
            "list_notes": "Результат поиска заметок",
            "read_note": "Заметка прочитана",
            "create_note": "Заметка создана",
            "update_note": "Заметка обновлена",
            "delete_note": "Заметка удалена",
        }.get(name, "Инструмент выполнен")

    @staticmethod
    def _tool_result_detail(name: str, result: dict) -> str:
        if not result.get("ok"):
            return str(result.get("error", "Операция не выполнена."))
        if name == "list_notes":
            notes = result.get("notes", [])
            names = ", ".join(str(note.get("title", "Без названия")) for note in notes[:5])
            suffix = "…" if result.get("truncated") else ""
            return f"Найдено заметок: {result.get('count', len(notes))}. {names}{suffix}".strip()
        if name == "read_note":
            note = result.get("note", {})
            return f"Прочитано: «{note.get('title', 'Без названия')}» (ID {note.get('id', '?')})."
        if name in {"create_note", "update_note"}:
            note = result.get("note", {})
            return f"«{note.get('title', 'Без названия')}» (ID {note.get('id', '?')}); сохранение проверено."
        if name == "delete_note":
            return f"Удаление заметки «{result.get('title', 'Без названия')}» проверено."
        return "Операция успешно завершена и подтверждена результатом инструмента."

    def _run_note_tool(self, name: str, arguments: dict) -> dict:
        """Run one explicitly registered note tool and return a JSON-safe result."""
        try:
            if name == "list_notes":
                query = str(arguments.get("query", "")).strip()
                notes = self.store.list_notes(query)
                return {
                    "ok": True,
                    "count": len(notes),
                    "notes": [
                        {"id": int(note["id"]), "title": str(note["title"]), "updated_at": str(note["updated_at"])}
                        for note in notes[:100]
                    ],
                    "truncated": len(notes) > 100,
                }
            if name == "read_note":
                note_id = int(arguments["note_id"])
                note = next((item for item in self.store.list_notes() if int(item["id"]) == note_id), None)
                if note is None:
                    return {"ok": False, "error": f"Заметка с ID {note_id} не найдена."}
                return {"ok": True, "note": note}
            if name == "create_note":
                title = str(arguments.get("title", "")).strip()
                body = str(arguments.get("body", ""))
                if not title:
                    return {"ok": False, "error": "Для новой заметки нужно название."}
                note_id = self.store.save_note(title, body)
                note = next((item for item in self.store.list_notes() if int(item["id"]) == note_id), None)
                if note is None:
                    return {"ok": False, "error": "Запись не найдена после сохранения."}
                self._reload_notes()
                return {"ok": True, "action": "created", "note": note}
            if name == "update_note":
                note_id = int(arguments["note_id"])
                note = next((item for item in self.store.list_notes() if int(item["id"]) == note_id), None)
                if note is None:
                    return {"ok": False, "error": f"Заметка с ID {note_id} не найдена."}
                title = str(arguments["title"]) if "title" in arguments else str(note["title"])
                body = str(arguments["body"]) if "body" in arguments else str(note["body"])
                self.store.save_note(title, body, note_id)
                updated = next((item for item in self.store.list_notes() if int(item["id"]) == note_id), None)
                if updated is None:
                    return {"ok": False, "error": "Не удалось проверить изменённую заметку."}
                self._reload_notes()
                return {"ok": True, "action": "updated", "note": updated}
            if name == "delete_note":
                note_id = int(arguments["note_id"])
                note = next((item for item in self.store.list_notes() if int(item["id"]) == note_id), None)
                if note is None:
                    return {"ok": False, "error": f"Заметка с ID {note_id} не найдена."}
                answer = QMessageBox.question(
                    self,
                    "Подтверждение удаления",
                    f"Люми просит удалить заметку «{note['title']}» (ID {note_id}).\n\nУдалить её безвозвратно?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return {"ok": False, "cancelled": True, "error": "Пользователь отменил удаление."}
                self.store.delete_note(note_id)
                still_exists = any(int(item["id"]) == note_id for item in self.store.list_notes())
                if still_exists:
                    return {"ok": False, "error": "После удаления заметка всё ещё найдена."}
                self._reload_notes()
                return {"ok": True, "action": "deleted", "note_id": note_id, "title": str(note["title"])}
            return {"ok": False, "error": f"Инструмент «{name}» не зарегистрирован."}
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": f"Некорректные аргументы инструмента: {exc}"}
        except Exception as exc:
            return {"ok": False, "error": f"Не удалось выполнить инструмент: {exc}"}

    def _on_transport_status(self, status: str) -> None:
        """Show whether AnyModel actually returned an SSE stream or a buffered JSON response."""
        if not status:
            return
        self._record_activity("Передача ответа", status, "running" if "SSE" in status else "error")

    def _clear_streaming_message(self) -> None:
        """Clear only the streamed answer bubble while preserving the activity shell."""
        widget = self._streaming_widget
        if widget is None:
            return
        if widget is self._activity_message_widget:
            response_widget = getattr(widget, "_lumi_response_widget", None)
            if response_widget is not None:
                response_widget.setParent(None)
                response_widget.deleteLater()
            widget._lumi_bubble = None
            widget._lumi_response_widget = None
        else:
            widget.deleteLater()
        self._streaming_widget = None
        self._streaming_text = ""

    def _on_cloud_chunk(self, chunk: str) -> None:
        """Render streamed text in the existing Lumi bubble as soon as tokens arrive."""
        if not chunk:
            return
        self._streaming_text = getattr(self, "_streaming_text", "") + chunk
        if self._streaming_widget is None:
            self._streaming_widget = self._add_lumi_message("", show_logo=True)
        bubble = getattr(self._streaming_widget, "_lumi_bubble", None)
        if bubble is not None:
            bubble.set_markdown(self._streaming_text)
            # Keep the latest token visible without forcing users back down if they scrolled up.
            bar = self.chat_transcript.verticalScrollBar()
            if bar.maximum() - bar.value() <= 80:
                QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _on_cloud_response(self, message: object) -> None:
        if not isinstance(message, dict):
            self._on_cloud_error("Не удалось прочитать ответ модели: неожиданный формат.")
            return
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            # Tool-call rounds are not user-facing final answers. Remove any partial
            # text bubble if the provider streamed commentary before the tool call.
            self._clear_streaming_message()
            self._tool_round_count += 1
            if self._tool_round_count > 6:
                self._tool_round_active = False
                self._finish_live_activity(success=False)
                self._add_lumi_message("Я остановила цепочку действий: достигнут безопасный лимит вызовов инструментов. Попробуй уточнить задачу.", show_logo=True)
                self._append_pending_activity_duration()
                self.chat_status.setText("●  Остановлено")
                self._commit_active_chat()
                return
            assistant_message = {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls,
            }
            self.chat_messages.append(assistant_message)
            for call in tool_calls:
                call_id = str(call.get("id", ""))
                function = call.get("function") or {}
                name = str(function.get("name", ""))
                raw_arguments = function.get("arguments", "{}")
                try:
                    arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                    if not isinstance(arguments, dict):
                        raise ValueError("Ожидался объект аргументов.")
                    self._record_activity(
                        f"Вызов инструмента: {name}",
                        self._describe_tool_action(name, arguments),
                        "running",
                    )
                    result = self._run_note_tool(name, arguments)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    result = {"ok": False, "error": f"Не удалось разобрать аргументы инструмента: {exc}"}
                ok = bool(result.get("ok"))
                self._record_activity(
                    self._tool_result_title(name, result),
                    self._tool_result_detail(name, result),
                    "ok" if ok else ("cancelled" if result.get("cancelled") else "error"),
                )
                self.chat_messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            self._commit_active_chat()
            self.chat_status.setText("●  Выполняю действие…")
            self._start_tool_followup()
            return

        answer = str(message.get("content") or "").strip()
        if not answer:
            self._on_cloud_error("Модель вернула пустой ответ.")
            return
        self._tool_round_active = False
        self._finish_live_activity(success=True)
        self.chat_messages.append({"role": "assistant", "content": answer})
        self._commit_active_chat()
        if self._streaming_widget is None:
            self._add_lumi_message(answer, show_logo=True)
        else:
            bubble = getattr(self._streaming_widget, "_lumi_bubble", None)
            if bubble is not None:
                bubble.set_markdown(answer)
        self._streaming_widget = None
        self._streaming_text = ""
        self._append_pending_activity_duration()
        self.chat_status.setText("●  AnyModel · Grok 4.6")
        self.chat_status.setStyleSheet("color: #7CEEFF; font-size: 9pt;")

    def _on_cloud_error(self, message: str) -> None:
        self._clear_streaming_message()
        self._tool_round_active = False
        self._finish_live_activity(success=False)
        self._add_lumi_message(message, show_logo=True)
        self._append_pending_activity_duration()
        self.chat_status.setText("●  Ошибка подключения")
        self.chat_status.setStyleSheet("color: #FF9C9C; font-size: 9pt;")
        if self.chat_messages and self.chat_messages[-1].get("role") == "user":
            self.chat_messages.pop()
            self._commit_active_chat()

    def _on_cloud_request_finished(self) -> None:
        if not self._tool_round_active:
            self.chat_input.setEnabled(True)
            self.send_chat_button.setEnabled(True)
            self.chat_input.setFocus()

    def _add_lumi_message(self, text: str, *, show_logo: bool = True) -> QWidget:
        """Add a response bubble that wraps text and resizes to rendered Markdown."""
        message_text = str(text).replace("\\r\\n", "\n").replace("\\n", "\n")
        row_widget = QWidget()
        row_widget.setObjectName("lumiResponseContent")
        row_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        row_widget.setStyleSheet("QWidget#lumiResponseContent { background: transparent; }")
        row_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_layout = QVBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        if show_logo and self._activity_message_widget is None:
            logo_row = QHBoxLayout()
            logo_row.setContentsMargins(24, 0, 0, 0)
            logo_row.setSpacing(0)
            avatar = QLabel()
            avatar.setFixedSize(112, 52)
            avatar.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            avatar.setStyleSheet("background: transparent;")
            avatar.setAutoFillBackground(False)
            avatar.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            avatar.setPixmap(QPixmap(str(resource_path("assets/Люми — неоновый лисий логотип.png"))).scaled(
                108, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ))
            logo_row.addWidget(avatar, 0, Qt.AlignmentFlag.AlignLeft)
            logo_row.addStretch(1)
            row_layout.addLayout(logo_row)

        bubble_row = QHBoxLayout()
        bubble_row.setContentsMargins(12, 0, 12, 0)
        bubble_row.setSpacing(0)
        bubble = MarkdownMessageBrowser()
        bubble.setObjectName("lumiMessage")
        bubble.set_markdown(message_text)
        bubble_row.addWidget(bubble, 1, Qt.AlignmentFlag.AlignTop)
        row_layout.addLayout(bubble_row)
        row_widget._lumi_bubble = bubble
        if self._activity_message_layout is not None and self._activity_message_widget is not None:
            activity_layout = self._activity_container.layout() if self._activity_container is not None else None
            if activity_layout is not None:
                activity_layout.addWidget(row_widget)
            self._activity_message_widget._lumi_bubble = bubble
            self._activity_message_widget._lumi_response_widget = row_widget
            return self._activity_message_widget
        self._append_chat_message(row_widget)
        return row_widget

    def display_lumi_response(self, text: str) -> None:
        """Entry point for the internal AI/API layer to display a returned response."""
        self._add_lumi_message(text, show_logo=True)

    def _new_chat_visual(self) -> None:
        self._commit_active_chat()
        self.chat_messages = []
        self.active_chat_session = None
        self.active_chat_title = "Новый чат"
        self._clear_chat_transcript()
        self._add_lumi_message("Привет! ✨ Я Люми — твоя неоновая помощница с лисьим характером. Чем займёмся?", show_logo=True)
        self._refresh_chat_history()
        self.chat_input.clear()

    def _commit_active_chat(self) -> None:
        if not self.chat_messages:
            return
        if self.active_chat_session is None:
            self.active_chat_session = {"title": self.active_chat_title, "messages": list(self.chat_messages)}
            self.chat_sessions.insert(0, self.active_chat_session)
        else:
            self.active_chat_session["title"] = self.active_chat_title
            self.active_chat_session["messages"] = list(self.chat_messages)
            if self.active_chat_session in self.chat_sessions:
                self.chat_sessions.remove(self.active_chat_session)
            self.chat_sessions.insert(0, self.active_chat_session)
        self._persist_chat_sessions()
        self._refresh_chat_history()

    def _persist_chat_sessions(self) -> None:
        self.settings.setValue("chat/sessions", json.dumps(self.chat_sessions, ensure_ascii=False))

    def _clear_chat_transcript(self) -> None:
        while self.chat_messages_layout.count():
            item = self.chat_messages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.chat_messages_layout.addStretch(1)

    def _refresh_chat_history(self) -> None:
        self.chat_history_list.clear()
        for index, session in enumerate(self.chat_sessions):
            item = QListWidgetItem(str(session.get("title", "Чат")))
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(str(session.get("title", "Чат")))
            self.chat_history_list.addItem(item)
        if not self.chat_sessions:
            empty = QListWidgetItem("История появится после создания чата")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.chat_history_list.addItem(empty)

    def _open_chat_session(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or index < 0 or index >= len(self.chat_sessions):
            return
        target = self.chat_sessions[index]
        self._commit_active_chat()
        self.active_chat_session = target
        self.chat_messages = [dict(message) for message in target.get("messages", [])]
        self.active_chat_title = str(target.get("title", "Чат"))
        self._clear_chat_transcript()
        for message in self.chat_messages:
            if message.get("role") == "user":
                self._add_user_message(str(message.get("content", "")))
            elif message.get("role") == "assistant" and message.get("content"):
                self._add_lumi_message(str(message.get("content", "")), show_logo=True)
        self._refresh_chat_history()

    def _show_chat_context_menu(self, position) -> None:
        item = self.chat_history_list.itemAt(position)
        if item is None:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or index < 0 or index >= len(self.chat_sessions):
            return
        menu = QMenu(self)
        rename_action = menu.addAction("Переименовать")
        delete_action = menu.addAction("Удалить чат")
        chosen = menu.exec(self.chat_history_list.mapToGlobal(position))
        if chosen == rename_action:
            current = str(self.chat_sessions[index].get("title", "Чат"))
            title, accepted = QInputDialog.getText(self, "Переименовать чат", "Название:", text=current)
            title = title.strip()
            if accepted and title:
                self.chat_sessions[index]["title"] = title[:80]
                if self.active_chat_session is self.chat_sessions[index]:
                    self.active_chat_title = title[:80]
                self._persist_chat_sessions()
                self._refresh_chat_history()
        elif chosen == delete_action:
            answer = QMessageBox.question(self, "Удалить чат", f"Удалить чат «{self.chat_sessions[index].get('title', 'Чат')}»?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                target = self.chat_sessions.pop(index)
                if self.active_chat_session is target:
                    self.active_chat_session = None
                    self.active_chat_title = "Новый чат"
                    self.chat_messages = []
                    self._clear_chat_transcript()
                self._persist_chat_sessions()
                self._refresh_chat_history()

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
            "Выбирай локальные модели для работы на компьютере или облачные модели для вычислений на сервере. "
            "Облачные запросы могут тарифицироваться провайдером."
        )
        description.setObjectName("pageSubtitle")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(description)

        self.model_choice = QComboBox()
        self.model_choice.addItem("Grok 4.6 — основная модель", "xai/grok-4.6")
        saved_model = str(self.settings.value("anymodel/model", "xai/grok-4.6"))
        saved_index = self.model_choice.findData(saved_model)
        self.model_choice.setCurrentIndex(saved_index if saved_index >= 0 else 0)
        self.model_choice.currentIndexChanged.connect(
            lambda _index: self.settings.setValue("anymodel/model", self.model_choice.currentData())
        )
        card_layout.addWidget(self.model_choice)

        self.model_file_label = QLabel("Локальные модели можно выбрать как файл GGUF; запуск локального движка будет добавлен отдельно.")
        self.model_file_label.setObjectName("muted")
        self.model_file_label.setWordWrap(True)
        card_layout.addWidget(self.model_file_label)

        model_buttons = QHBoxLayout()
        choose_model = QPushButton("Выбрать файл модели…")
        choose_model.clicked.connect(self._choose_model_file)
        model_buttons.addWidget(choose_model)

        self.enable_model_button = QPushButton("Облачные модели")
        self.enable_model_button.setObjectName("primaryButton")
        self.enable_model_button.clicked.connect(self._show_cloud_model_settings)
        model_buttons.addWidget(self.enable_model_button)

        self.disable_model_button = QPushButton("Локальные модели")
        self.disable_model_button.clicked.connect(self._set_local_mode)
        model_buttons.addWidget(self.disable_model_button)
        card_layout.addLayout(model_buttons)

        compatibility_button = QPushButton("Проверить совместимость")
        compatibility_button.clicked.connect(self._model_placeholder)
        card_layout.addWidget(compatibility_button)

        cloud_card = QFrame()
        cloud_card.setObjectName("card")
        cloud_layout = QVBoxLayout(cloud_card)
        cloud_layout.setContentsMargins(22, 18, 22, 18)
        cloud_layout.setSpacing(10)
        cloud_title_row = QHBoxLayout()
        cloud_title = QLabel("Облачные модели · AnyModel")
        cloud_title.setObjectName("section")
        cloud_title_row.addWidget(cloud_title, 1)
        back_to_models = QPushButton("← Все модели")
        back_to_models.clicked.connect(self._show_local_model_overview)
        cloud_title_row.addWidget(back_to_models)
        cloud_layout.addLayout(cloud_title_row)
        cloud_description = QLabel("Для слабых компьютеров: вычисления выполняются на сервере. Нужны интернет и API-ключ; использование может быть платным.")
        cloud_description.setObjectName("pageSubtitle")
        cloud_description.setWordWrap(True)
        cloud_layout.addWidget(cloud_description)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText(
            "Ключ сохранён — введи новый для замены" if str(self.settings.value("anymodel/api_key", "")).strip()
            else "Вставь API-ключ AnyModel"
        )
        cloud_layout.addWidget(self.api_key_input)
        self.cloud_mode_choice = QCheckBox("Использовать облачную модель (может быть платно)")
        self.cloud_mode_choice.setChecked(str(self.settings.value("ai/mode", "local")) == "cloud")
        cloud_layout.addWidget(self.cloud_mode_choice)
        save_cloud_button = QPushButton("Сохранить настройки моделей")
        save_cloud_button.setObjectName("primaryButton")
        save_cloud_button.clicked.connect(self._save_api_settings)
        cloud_layout.addWidget(save_cloud_button, 0, Qt.AlignmentFlag.AlignLeft)
        cloud_hint = QLabel("Локальный режим остаётся выбранным по умолчанию. Реальный запуск локальных моделей пока не реализован.")
        cloud_hint.setObjectName("muted")
        cloud_hint.setWordWrap(True)
        cloud_layout.addWidget(cloud_hint)
        self.cloud_settings_card = cloud_card
        self.models_overview_card = card
        cloud_card.setVisible(False)
        layout.addWidget(card)
        layout.addWidget(cloud_card)
        layout.addStretch(1)
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

    def _show_cloud_model_settings(self) -> None:
        self._show_page("models")
        self.models_overview_card.setVisible(False)
        self.cloud_settings_card.setVisible(True)

    def _show_local_model_overview(self) -> None:
        self.models_overview_card.setVisible(True)
        self.cloud_settings_card.setVisible(False)

    def _effective_system_prompt(self) -> str:
        base = (
            "Твоё имя — Люми (Lumi). Ты — дружелюбная, умная лисичка-помощница с собственной "
            "индивидуальностью. Ты любознательная, сообразительная, внимательная и находчивая. "
            "Ты умеешь находить нестандартные решения и проявляешь смекалку. Ты уверенная, но не "
            "высокомерная; добрая, но не навязчивая; весёлая, но умеешь быть серьёзной, когда это нужно. "
            "Всегда сохраняй свою личность и имя независимо от темы разговора. "
            "Общайся естественно, тепло, вежливо и уважительно. Отвечай по существу: на простые вопросы "
            "кратко, а сложные объясняй понятно и достаточно подробно. Не начинай каждый ответ с приветствия, "
            "не представляйся повторно без необходимости и не повторяй постоянно, что ты лисичка или помощница. "
            "Иногда можешь проявить лёгкую игривость, озорство или пошутить, если это подходит настроению и теме. "
            "Не превращай каждый ответ в ролевую игру и не злоупотребляй эмодзи. "
            "Не соглашайся автоматически: вежливо указывай на ошибки и предлагай более удачные решения. "
            "Признавай неопределённость, задавай уточняющие вопросы при необходимости и не выдумывай факты. "
            "В сложных задачах действуй последовательно и объясняй полезные выводы, не раскрывая скрытые внутренние рассуждения. "
            "В технических вопросах ставь на первое место точность и практическую пользу. "
            "Не утверждай, что выполнила действие, если оно фактически не было выполнено."
        )
        tools_guidance = (
            "ИНСТРУМЕНТЫ И ВОЗМОЖНОСТИ ПРИЛОЖЕНИЯ:\n"
            "Ты работаешь внутри Lumi AI. Приложение может предоставлять встроенные инструменты, а подключённые "
            "плагины могут добавлять дополнительные. Используй только инструменты, которые действительно перечислены "
            "в текущем запросе или доступны через предусмотренный механизм обнаружения инструментов. "
            "Если доступен каталог/реестр инструментов, сначала проверь его, когда это нужно для задачи. "
            "Учитывай название, описание, назначение, входные параметры, результат и разрешения каждого инструмента. "
            "Не считай, что инструмент существует, только потому что он упомянут в этом промпте. "
            "Если приложение предоставляет инструменты заметок, используй их для поиска, просмотра списка, чтения, "
            "создания и редактирования заметок по просьбе пользователя. При просьбе сохранить информацию из текущего "
            "разговора используй соответствующий инструмент и подходящее содержимое беседы. "
            "Перед изменением заметки найди нужную запись и убедись, что выбрана правильная. "
            "Не удаляй данные и не выполняй потенциально разрушительные действия без ясного намерения пользователя; "
            "при неоднозначности сначала уточни. Соблюдай разрешения инструментов и плагинов и не пытайся обходить их. "
            "После вызова инструмента оцени фактический результат. Сообщай об успехе только если инструмент подтвердил "
            "успешное выполнение; при ошибке честно объясни её. Если нужного инструмента нет, скажи об ограничении и "
            "не притворяйся, что действие выполнено. "
            "Плагины могут добавлять новые возможности, но их наличие, назначение и доступность определяются реестром "
            "инструментов приложения, а не предположениями. Дополнительные инструкции могут задавать рабочие привычки "
            "и формат ответов, но не должны отменять твою личность, честность, уважение и правила безопасности."
        )
        extra = str(self.settings.value("personality/extra_prompt", "")).strip()
        developer = str(self.settings.value("personality/developer_prompt", "")).strip()
        parts = [base, tools_guidance]
        if extra:
            parts.append("Дополнительные инструкции пользователя (сохраняй личность Люми и соблюдай правила использования инструментов):\n" + extra)
        if developer:
            parts.append("Дополнительные инструкции разработчика; личность Люми, честность и правила доступа к инструментам сохраняются:\n" + developer)
        return "\n\n".join(parts)

    def _save_personality_settings(self) -> None:
        self.settings.setValue("personality/extra_prompt", self.extra_prompt_input.toPlainText().strip())
        QMessageBox.information(self, "Сохранено", "Дополнительные инструкции сохранены. Основная личность Люми не изменена.")

    def _set_local_mode(self) -> None:
        self.settings.setValue("ai/mode", "local")
        if hasattr(self, "cloud_settings_card"):
            self.cloud_settings_card.setVisible(False)
            self.models_overview_card.setVisible(True)
        self.chat_status.setText("●  Локальный режим")
        self.chat_status.setStyleSheet("color: #7CEEFF; font-size: 9pt;")
        QMessageBox.information(self, "Локальный режим", "Lumi переключена в локальный режим. Облачные запросы не отправляются.")

    def _save_api_settings(self) -> None:
        key = self.api_key_input.text().strip()
        if key:
            self.settings.setValue("anymodel/api_key", key)
        self.settings.setValue("anymodel/model", self.model_choice.currentData())
        mode = "cloud" if self.cloud_mode_choice.isChecked() else "local"
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
            "Настройки", "Настройки приложения и дополнительные инструкции для Люми."
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

        personality_card = QFrame()
        personality_card.setObjectName("card")
        personality_layout = QVBoxLayout(personality_card)
        personality_layout.setContentsMargins(22, 22, 22, 22)
        personality_layout.setSpacing(10)
        personality_title = QLabel("Личность Люми")
        personality_title.setObjectName("section")
        personality_layout.addWidget(personality_title)
        personality_description = QLabel(
            "Основная личность Люми хранится в приложении и всегда добавляется к облачному запросу. "
            "Дополнительные инструкции уточняют поведение, но не заменяют её характер."
        )
        personality_description.setObjectName("pageSubtitle")
        personality_description.setWordWrap(True)
        personality_layout.addWidget(personality_description)
        self.extra_prompt_input = QTextEdit()
        self.extra_prompt_input.setPlaceholderText("Дополнительные инструкции: предпочтения, формат ответов и рабочие привычки…")
        self.extra_prompt_input.setPlainText(str(self.settings.value("personality/extra_prompt", "")))
        self.extra_prompt_input.setMinimumHeight(110)
        personality_layout.addWidget(self.extra_prompt_input)
        save_prompt_button = QPushButton("Сохранить дополнительные инструкции")
        save_prompt_button.setObjectName("primaryButton")
        save_prompt_button.clicked.connect(self._save_personality_settings)
        personality_layout.addWidget(save_prompt_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(personality_card)
        layout.addStretch(1)

        # Keep all settings reachable on short windows instead of clipping controls.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

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
        if key == "models" and hasattr(self, "models_overview_card"):
            self._show_local_model_overview()
        if hasattr(self, "chat_history_panel"):
            self.chat_history_panel.setVisible(self.sidebar_collapsed and key == "chat")
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
