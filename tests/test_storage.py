from lumi.storage import NotesStore


def test_notes_can_be_created_searched_updated_and_deleted(tmp_path):
    store = NotesStore(tmp_path / "test.db")
    note_id = store.save_note("Идея", "Сделать помощницу Lumi")

    assert store.list_notes()[0]["title"] == "Идея"
    assert len(store.list_notes("помощницу")) == 1

    store.save_note("Новая идея", "Обновлённый текст", note_id)
    note = store.list_notes()[0]
    assert note["title"] == "Новая идея"
    assert note["body"] == "Обновлённый текст"

    store.delete_note(note_id)
    assert store.list_notes() == []
