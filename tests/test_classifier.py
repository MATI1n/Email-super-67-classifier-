import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from structures import Letter, Category
from collections import Counter
from classifier import classify_letter, classify_file, DEFAULT_CATEGORIES
from pathlib import Path
from os import listdir
from tqdm.contrib.concurrent import process_map


@pytest.mark.parametrize("category", DEFAULT_CATEGORIES)
def test_classify_categories_dynamic(category: Category):
    if not category.keywords:
        pytest.skip(f"No keywords for {category.name}")
    keyword = category.keywords[0]
    content = [
        f"From: user@example.com\n",
        f"To: it-support@company.ru\n",
        f"Subject: Test subject for {category.name}\n",
        f"\n",
        f"Here is a test containing {keyword}.\n"
    ]
    letter = Letter(content)
    assert classify_letter(letter) == category.name


def test_classify_support_requests():
    content = [
        "From: s.volkov@partner.ru\n",
        "To: it-support@company.ru\n",
        "Subject: Вопрос по принтеру\n",
        "\n",
        "Как настроить принтер?\n"
    ]
    letter = Letter(content)
    assert classify_letter(letter) == "unknown"


def test_date_parsing():
    content = [
        "From: a@b.ru\n",
        "Date: 28.01.2025 18:19\n",
        "\n",
        "Text\n"
    ]
    letter = Letter(content)
    assert letter.date is not None
    assert letter.sent_from_email == "a@b.ru"
    assert letter.date.year == 2025
    assert letter.date.month == 1
    assert letter.date.day == 28


def test_classify_file_not_path():
    assert classify_file("") == "errors"


def test_classify_file_mock_path():
    assert classify_file(Path()) == "errors"


def test_classify_file_empty():
    assert classify_file(Path("tests/data/empty.txt")) == "errors"


def test_classify_file_wrong_format():
    assert classify_file(Path("tests/data/format.json")) == "errors"


def test_classify_file_unknown():
    assert classify_file(Path("tests/data/unknown.txt")) == "unknown"


def test_classify_file_spam():
    assert classify_file(Path("tests/data/spam.txt")) == "spam"


def test_classify_file_urgent():
    assert classify_file(Path("tests/data/urgent.txt")) == "urgent"


def test_classify_file_alerts():
    assert classify_file(Path("tests/data/alerts.txt")) == "alerts"


def test_classify_file_hr_documents():
    assert classify_file(Path("tests/data/hr_documents.txt")) == "hr_documents"


def test_classify_file_newsletters():
    assert classify_file(Path("tests/data/newsletters.txt")) == "newsletters"


def test_stats():
    file_paths = [Path("tests/data") / file_path for file_path in listdir("tests/data")]

    categories = process_map(classify_file, file_paths, max_workers=1, desc="Classifying test letters")

    stats = Counter(categories)

    assert stats == {'errors': 2, 'spam': 1, 'unknown': 1, 'urgent': 1, 'alerts': 1, 'hr_documents': 1,
                     'newsletters': 1}
