import unittest
from unittest.mock import patch, Mock
import numpy as np
from test_reader_refresh import item
from services.dedup import find_duplicates
from services.digest import generate_digest
from models import Feed


class SemanticTests(unittest.TestCase):
    def test_semantic_paraphrase_and_original_article_links(self):
        stories = [item(1, "Apple unveils new virtual reality headset", "https://a.example/1"),
                   item(2, "Apple introduces its latest VR headset", "https://b.example/2")]
        vectors = {1: np.array([1., 0.]), 2: np.array([.9, .43589])}
        with patch("services.dedup.embeddings_for_items", return_value=vectors):
            self.assertEqual(find_duplicates(stories), {1: [2]})
            self.assertEqual(find_duplicates(stories[::-1]), {2: [1]})

    def test_contradictions_not_hidden_even_with_near_identical_embeddings(self):
        for a, b in [
            ("Arsenal beat Chelsea 2-1", "Arsenal lose to Chelsea 2-1"),
            ("Earthquake kills 20 people in Chile", "Earthquake kills 30 people in Chile"),
            ("Senate approves new climate bill", "Senate rejects new climate bill"),
            ("NASA confirms water on Mars", "NASA has not confirmed water on Mars"),
        ]:
            stories = [item(1, a, "https://a.example/1"), item(2, b, "https://b.example/2")]
            with patch("services.dedup.embeddings_for_items", return_value={1: np.array([1.]), 2: np.array([1.])}):
                self.assertEqual(find_duplicates(stories), {}, (a, b))

    def test_missing_model_keeps_canonical_link_matching(self):
        with patch("services.dedup.embeddings_for_items", return_value={}):
            self.assertEqual(find_duplicates([item(1, "Title", "https://a.example/1"),
                                              item(2, "Different", "https://a.example/1?utm_source=rss")]), {1: [2]})


class DigestMatchingTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_canonical_dedup_keeps_best_ranked_and_fills_slots(self):
        stories = [item(1, "First title", "https://a.example/1"),
                   item(2, "Other headline", "https://a.example/1?utm_source=rss"),
                   item(3, "Independent story", "https://c.example/3")]
        session = Mock()
        session.execute.return_value.all.return_value = [
            (s, Feed(id=s.feed_id, title="Source"), "News" if s.id == 1 else "Tech") for s in stories
        ]
        with patch("services.digest.embeddings_for_items", return_value={}):
            digest = await generate_digest(session)
        self.assertEqual([s["id"] for rows in digest.values() for s in rows], [1, 3])
