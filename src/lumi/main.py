"""Lumi desktop app: neon sidebar, local notes and planned AI sections."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QFont, QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
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


class LumiWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Lumi AI — твоя умная помощница")
        self.setWindowIcon(QIcon(str(resource_path("assets/lumi-app-icon.png"))))
        self.resize(1120, 720)
        self.setMinimumSize(850, 560)
        self.store = NotesStore()
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
        brand = QLabel("Lumi AI")
        brand.setObjectName("brand")
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
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(16)
        layout.addLayout(self._page_heading(
            "Привет! Я Lumi ✨", "Твоя неоновая помощница с лисьим характером."
        ))
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(14)
        mascot = QLabel()
        mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mascot.setPixmap(QPixmap(str(resource_path("assets/lumi-tray-icon.png"))).scaled(
            104, 104, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        card_layout.addWidget(mascot)
        welcome = QLabel("Рада тебя видеть!")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setStyleSheet("font-size: 17pt; font-weight: 650; color: #8CEBFF;")
        card_layout.addWidget(welcome)
        intro = QLabel(
            "Это будет наше место для общения. Сейчас в Lumi уже работают локальные заметки, "
            "а подключение настоящего ИИ и отправка сообщений появятся отдельным этапом."
        )
        intro.setObjectName("pageSubtitle")
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        intro.setMaximumWidth(580)
        card_layout.addWidget(intro, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(card, 1)
        chat_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Чат с ИИ пока готовится…")
        self.chat_input.setEnabled(False)
        send_button = QPushButton("Отправить")
        send_button.setObjectName("primaryButton")
        send_button.setEnabled(False)
        chat_row.addWidget(self.chat_input, 1)
        chat_row.addWidget(send_button)
        layout.addLayout(chat_row)
        note = QLabel("ИИ пока не подключён — кнопка отправки станет активной после интеграции модели.")
        note.setObjectName("muted")
        layout.addWidget(note)
        return page

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
            "Модели ИИ", "Выбирай модель под возможности компьютера. Управление пока работает как макет."
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

        status_title = QLabel("Локальная модель не подключена")
        status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_title.setStyleSheet("font-size: 16pt; font-weight: 650; color: #B8A5FF;")
        card_layout.addWidget(status_title)

        description = QLabel(
            "Здесь появятся каталог моделей, размер загрузки, требования к памяти и проверка совместимости. "
            "Пока можно выбрать файл модели на компьютере — это не запускает и не загружает модель."
        )
        description.setObjectName("pageSubtitle")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(description)

        self.model_choice = QComboBox()
        self.model_choice.addItems([
            "Выбери модель (пока заглушка)",
            "Небольшая модель — для слабых ПК",
            "Сбалансированная модель — для обычных ПК",
            "Большая модель — для мощных ПК",
        ])
        self.model_choice.setToolTip("Варианты пока демонстрационные; реальные модели появятся позже.")
        card_layout.addWidget(self.model_choice)

        self.model_file_label = QLabel("Файл модели: не выбран")
        self.model_file_label.setObjectName("muted")
        self.model_file_label.setWordWrap(True)
        card_layout.addWidget(self.model_file_label)

        model_buttons = QHBoxLayout()
        choose_model = QPushButton("Выбрать файл модели…")
        choose_model.clicked.connect(self._choose_model_file)
        model_buttons.addWidget(choose_model)

        self.enable_model_button = QPushButton("Включить модель")
        self.enable_model_button.setObjectName("primaryButton")
        self.enable_model_button.clicked.connect(self._model_placeholder)
        model_buttons.addWidget(self.enable_model_button)

        self.disable_model_button = QPushButton("Отключить")
        self.disable_model_button.setEnabled(False)
        self.disable_model_button.clicked.connect(self._model_placeholder)
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
        QMessageBox.information(
            self,
            "Модели Lumi AI",
            "Этот элемент интерфейса пока заглушка. Подключение движка, загрузка и управление моделью "
            "будут реализованы отдельным этапом.",
        )

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(18)
        layout.addLayout(self._page_heading(
            "Настройки", "Обновления и параметры Lumi будут собраны здесь."
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

        model_card = QFrame()
        model_card.setObjectName("card")
        model_layout = QVBoxLayout(model_card)
        model_layout.setContentsMargins(22, 22, 22, 22)
        model_layout.setSpacing(10)
        model_title = QLabel("Поведение ИИ")
        model_title.setObjectName("section")
        model_layout.addWidget(model_title)
        model_description = QLabel(
            "В будущем здесь можно будет выбрать модель по умолчанию и решить, запускать ли её вместе с Lumi. "
            "Пока эти настройки не влияют на работу приложения."
        )
        model_description.setObjectName("pageSubtitle")
        model_description.setWordWrap(True)
        model_layout.addWidget(model_description)

        self.autostart_model_checkbox = QPushButton("Настройка запуска модели — скоро")
        self.autostart_model_checkbox.setEnabled(False)
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
