import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from structures import Letter
from classifier import classify_letter

def test_classify_urgent():
    content = [
        "От кого: user@partner.ru\n",
        "Кому: it-support@company.ru\n",
        "Тема: Срочно: падает сервер\n",
        "\n",
        "Все остановлено!\n"
    ]
    letter = Letter(content)
    assert classify_letter(letter) == "urgent"

def test_classify_spam():
    content = [
        "From: spammer@casino.com\n",
        "To: it-support@company.ru\n",
        "Subject: Выигрыш миллион долларов!\n",
        "\n",
        "Забирай свой выигрыш.\n"
    ]
    letter = Letter(content)
    assert classify_letter(letter) == "spam"

def test_classify_alerts():
    content = [
        "From: alerts@grafana.internal\n",
        "To: it-support@company.ru\n",
        "Subject: High CPU usage\n",
        "\n",
        "CPU is above 90%.\n"
    ]
    letter = Letter(content)
    assert classify_letter(letter) == "alerts"

def test_classify_newsletters():
    content = [
        "From: pr@company.ru\n",
        "To: all@company.ru\n",
        "Subject: Еженедельный дайджест новостей\n",
        "\n",
        "Читайте наши новости.\n"
    ]
    letter = Letter(content)
    assert classify_letter(letter) == "newsletters"

def test_classify_hr_documents():
    content = [
        "From: hr@company.ru\n",
        "To: it-support@company.ru\n",
        "Subject: Согласование отпуска\n",
        "\n",
        "Прошу согласовать отпуск.\n"
    ]
    letter = Letter(content)
    assert classify_letter(letter) == "hr_documents"

def test_classify_support_requests():
    content = [
        "From: s.volkov@partner.ru\n",
        "To: it-support@company.ru\n",
        "Subject: Вопрос по принтеру\n",
        "\n",
        "Как настроить принтер?\n"
    ]
    letter = Letter(content)
    assert classify_letter(letter) == "support_requests"

def test_date_parsing():
    content = [
        "From: a@b.ru\n",
        "Date: 28.01.2025 18:19\n",
        "\n",
        "Text\n"
    ]
    letter = Letter(content)
    assert letter.date is not None
    assert letter.date.year == 2025
    assert letter.date.month == 1
    assert letter.date.day == 28
