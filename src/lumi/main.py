"""Initial Lumi desktop app: local notes and a model-manager placeholder."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lumi import __version__
from lumi.storage import NotesStore


STYLE = """
QMainWindow, QWidget {
    background: #080D25;
    color: #F4F3FF;
    font-family: Segoe UI, sans-serif;
    font-size: 10pt;
}
QLineEdit, QTextEdit, QListWidget {
    background: #10183A;
    border: 1px solid #263B85;
    border-radius: 9px;
    padding: 8px;
    selection-background-color: #6655E8;
}
QPushButton {
    background: #302B75;
    border: 1px solid #6255D9;
    border-radius: 9px;
    padding: 9px 13px;
}
QPushButton:hover { background: #443AA0; }
QPushButton:pressed { background: #24205C; }
QLabel#brand { color: #78F3FF; font-size: 19pt; font-weight: 700; }
QLabel#muted { color: #A7B6F4; }
QListWidget::item { padding: 8px; border-radius: 6px; }
QListWidget::item:selected { background: #302B75; }
"""


class LumiWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Lumi — твоя умная помощница")
        self.resize(1000, 650)
        self.store = NotesStore()
        self.current_note_id: int | None = None
        self._build_ui()
        self._reload_notes()

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        header = QHBoxLayout()
        brand = QLabel("✦ Lumi")
        brand.setObjectName("brand")
        subtitle = QLabel("Твоя умная помощница")
        subtitle.setObjectName("muted")
        header.addWidget(brand)
        header.addWidget(subtitle)
        header.addStretch()
        self.model_button = QPushButton("Модели ИИ")
        self.model_button.clicked.connect(self._show_models_info)
        header.addWidget(self.model_button)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        sidebar = QWidget()
        side_layout = QVBoxLayout(sidebar)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти заметку…")
        self.search.textChanged.connect(self._reload_notes)
        side_layout.addWidget(self.search)
        self.notes_list = QListWidget()
        self.notes_list.currentRowChanged.connect(self._select_note)
        side_layout.addWidget(self.notes_list)
        buttons = QHBoxLayout()
        new_button = QPushButton("＋ Новая")
        new_button.clicked.connect(self._new_note)
        delete_button = QPushButton("Удалить")
        delete_button.clicked.connect(self._delete_note)
        buttons.addWidget(new_button)
        buttons.addWidget(delete_button)
        side_layout.addLayout(buttons)

        editor = QWidget()
        edit_layout = QVBoxLayout(editor)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Название заметки")
        self.body_edit = QTextEdit()
        self.body_edit.setPlaceholderText("Запиши сюда идею, план или важную информацию…")
        edit_layout.addWidget(self.title_edit)
        edit_layout.addWidget(self.body_edit, 1)
        save_row = QHBoxLayout()
        self.status = QLabel("Заметки сохраняются на этом компьютере.")
        self.status.setObjectName("muted")
        save_button = QPushButton("Сохранить заметку")
        save_button.clicked.connect(self._save_note)
        save_row.addWidget(self.status, 1)
        save_row.addWidget(save_button)
        edit_layout.addLayout(save_row)

        splitter.addWidget(sidebar)
        splitter.addWidget(editor)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)

        footer = QLabel(f"Lumi {__version__} · локальные заметки · ранняя версия")
        footer.setObjectName("muted")
        outer.addWidget(footer)
        self.setCentralWidget(root)

        about = QAction("О Lumi", self)
        about.triggered.connect(self._show_about)
        self.menuBar().addAction(about)

    def _reload_notes(self, *_: object) -> None:
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
        answer = QMessageBox.question(
            self, "Удалить заметку", "Точно удалить выбранную заметку?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.store.delete_note(self.current_note_id)
            self.current_note_id = None
            self._reload_notes()

    def _show_models_info(self) -> None:
        QMessageBox.information(
            self,
            "Модели ИИ",
            "Менеджер моделей будет добавлен следующим этапом.\n\n"
            "Он проверит память компьютера, покажет доступные GGUF-модели "
            "и позволит скачать и переключить модель. Пока локальный ИИ ещё не подключён.",
        )

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "О Lumi",
            f"Lumi {__version__}\nТвоя умная помощница.\n\n"
            "Это ранняя версия: заметки работают локально, "
            "ИИ и Discord будут подключены отдельными этапами.",
        )


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Lumi")
    app.setOrganizationName("Lumi")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    window = LumiWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
