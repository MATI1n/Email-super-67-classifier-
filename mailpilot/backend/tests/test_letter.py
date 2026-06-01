"""Тесты парсера письма (app.letter.Letter)."""
from app.letter import Letter


def test_parse_english_headers():
    raw = ("Subject: браузер Chrome зависает\n"
           "From: s.volkov@partner.ru\n\n"
           "Здравствуйте!\nChrome не открывает файлы.\n")
    L = Letter(raw)
    assert L.subject == "браузер Chrome зависает"
    assert L.from_email == "s.volkov@partner.ru"
    assert "Chrome не открывает файлы." in L.text
    assert "Subject:" not in L.text  # заголовки вырезаны из тела


def test_parse_russian_headers_and_name():
    raw = ("От кого: John Smith <john.smith@globaltech.com>\n"
           "Кому: it-support@company.ru\n"
           "Дата: 03.04.2025 11:08\n"
           "Тема: URGENT: Запрос\n\n"
           "Текст обращения.")
    L = Letter(raw)
    assert L.from_email == "john.smith@globaltech.com"
    assert L.from_name == "John Smith"
    assert L.to == "it-support@company.ru"
    assert L.subject == "URGENT: Запрос"
    assert L.date is not None  # дата распознана dateparser


def test_missing_date_is_still_meaningful():
    """В отличие от строгой базовой проверки — письмо без даты валидно."""
    L = Letter("Subject: Тест\nFrom: a@b.ru\n\nТело письма тут.")
    assert L.date is None
    assert L.is_meaningful is True


def test_fallback_sender_from_body():
    L = Letter("Subject: без отправителя\n\nПишите на user@mail.ru за деталями.")
    assert L.from_email == "user@mail.ru"


def test_empty_is_not_meaningful():
    assert Letter("").is_meaningful is False
    assert Letter("\n\n   \n").is_meaningful is False


def test_display_name_fallbacks():
    assert Letter("From: vasya@corp.ru\n\nтекст").display_name() == "vasya"
    assert Letter("Subject: x\n\nтекст").display_name() == "Неизвестный отправитель"
