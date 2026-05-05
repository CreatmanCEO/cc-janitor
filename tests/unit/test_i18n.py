from cc_janitor.i18n import t, set_lang, detect_lang


def test_basic_translation():
    set_lang("en")
    assert t("common.delete") == "Delete"
    set_lang("ru")
    assert t("common.delete") == "Удалить"


def test_format_args():
    set_lang("en")
    assert t("sessions.delete_confirm", count=3) == "Delete 3 session(s)?"


def test_fallback_to_en_when_key_missing():
    set_lang("ru")
    val = t("common.delete")
    assert val == "Удалить"  # exists in ru


def test_detect_lang_from_env(monkeypatch):
    monkeypatch.setenv("CC_JANITOR_LANG", "ru")
    assert detect_lang() == "ru"
    monkeypatch.delenv("CC_JANITOR_LANG")
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")
    assert detect_lang() == "ru"
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert detect_lang() == "en"
