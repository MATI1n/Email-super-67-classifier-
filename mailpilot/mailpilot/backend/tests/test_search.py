"""Тесты умного поиска: BM25, семантический канал, гибрид (RRF)."""
import pytest

from app.config import settings
from app.search import HybridSearch, tokenize
from app.store import MailStore


@pytest.fixture(scope="module")
def search():
    s = MailStore(settings.data_dir)
    s.load()
    return HybridSearch(s), s


def test_tokenize_drops_stopwords():
    toks = tokenize("Здравствуйте, не могу войти в систему")
    assert "не" not in toks and "в" not in toks
    assert "войти" in toks and "систему" in toks


def test_empty_query_returns_nothing(search):
    hs, _ = search
    assert hs.search("   ") == []


def test_finds_relevant_email(search):
    hs, store = search
    hits = hs.search("не могу войти доступ", top_k=5)
    assert hits
    subjects = " ".join(store.get(h.doc_id).subject.lower() for h in hits)
    assert "войти" in subjects or "доступ" in subjects


def test_hybrid_uses_both_channels(search):
    hs, _ = search
    hits = hs.search("оплата счета бухгалтерия", top_k=5)
    assert hits
    # Хотя бы один результат подтверждён обоими каналами.
    assert any(set(h.channels) == {"bm25", "semantic"} for h in hits)


def test_semantic_morphology(search):
    """Семантический канал (символьные триграммы) ловит словоформы."""
    hs, _ = search
    # «оплате» — другая форма слова «оплата», которого нет дословно.
    vec_hits = hs.vector.search("оплате договора", 5)
    assert vec_hits


def test_vector_mode_label(search):
    hs, _ = search
    assert hs.vector_mode in ("local-mock", "coderun")
