"""Regression checks: article identity and summary shutdown, no live DB/API calls."""
import unittest
from itertools import permutations
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from models import Item, Feed, Rule
from schemas import AIRequest
from services.dedup import canonical_article_url, find_duplicates
from services import ai_service
from services.digest import generate_digest
from routers.ai import process_item, summarize_batch
from routers.items import list_items


def item(id, title, url, feed_id=None, **kwargs):
    return Item(id=id, title=title, link=url, feed_id=feed_id or id,
                created_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
                content="Publisher excerpt", **kwargs)


class ArticleIdentityTests(unittest.TestCase):
    def test_tracking_is_removed_but_article_query_is_kept(self):
        self.assertEqual(canonical_article_url("https://www.example.com/story/?id=7&utm_source=rss#top"),
                         canonical_article_url("http://example.com/story?id=7"))
        self.assertNotEqual(canonical_article_url("https://example.com/watch?v=abc"),
                            canonical_article_url("https://example.com/watch?v=xyz"))

    def test_repeated_link_groups_different_headlines_even_same_feed(self):
        a = item(1, "First headline", "https://example.com/article?utm_source=rss", feed_id=5)
        b = item(2, "An entirely different updated headline", "https://example.com/article#new", feed_id=5)
        self.assertEqual(find_duplicates([a, b]), {1: [2]})

    def test_three_snl_headlines_stay_one_group(self):
        headlines = [
            "‘SNL’ Promotes Keri Powers & Rebecca Schwartz",
            "‘SNL’ Promotes Keri Powers to Sole Head of Talent Department, Rebecca Schwartz Upped to Producer",
            "‘SNL’ Promotes Keri Powers and Rebecca Schwartz Ahead of Season 52 Premiere",
        ]
        items = [item(i + 1, h, "https://publisher" + str(i) + ".example/article") for i, h in enumerate(headlines)]
        for order in permutations(items):
            self.assertEqual(find_duplicates(list(order)), {order[0].id: [i.id for i in order[1:]]})

    def test_homepage_not_a_shared_article(self):
        self.assertEqual(canonical_article_url("https://example.com/"), "")
        self.assertEqual(find_duplicates([item(1, "Football match report", "https://example.com/"),
                                          item(2, "Space telescope discovers planet", "https://example.com/")]), {})

    def test_old_repeat_headline_not_grouped(self):
        a = item(1, "Today's most read stories", "https://example.com/monday")
        b = item(2, a.title, "https://other.example/friday")
        b.created_at -= timedelta(days=4)
        self.assertEqual(find_duplicates([a, b]), {})

    def test_generic_short_titles_do_not_use_containment(self):
        self.assertEqual(find_duplicates([item(1, "The new season", "https://a.example/1"),
                                          item(2, "A new season for the Mars rover scientific team", "https://b.example/2")]), {})


class SummaryShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_rejects_before_fetching_or_calling_model(self):
        with patch.object(ai_service, "_get_content", new_callable=AsyncMock) as fetch, \
             patch.object(ai_service, "_call_llm", new_callable=AsyncMock) as model:
            with self.assertRaisesRegex(ValueError, "disabled"):
                await ai_service.summarize_item("Title", "Text", link="https://example.com/story")
            fetch.assert_not_called()
            model.assert_not_called()

    async def test_single_and_batch_api_reject_even_stale_clients(self):
        db = AsyncMock()
        for request in [process_item(AIRequest(item_id=1, action="summarize"), db), summarize_batch([1, 2], db)]:
            with self.assertRaises(HTTPException) as caught:
                await request
            self.assertEqual(caught.exception.status_code, 410)
        db.get.assert_not_called()
        db.execute.assert_not_called()
        db.commit.assert_not_called()

    async def test_digest_ignores_legacy_enabled_setting_and_cached_summary(self):
        session = Mock()
        story = item(1, "A story", "https://example.com/a", ai_summary="Old AI summary")
        session.execute.return_value.all.return_value = [(story, Feed(id=1, title="Publisher"), "News")]
        with patch.object(ai_service, "_call_llm", new_callable=AsyncMock) as model:
            result = await generate_digest(session, summarize_items=True, api_key="test-only")
            self.assertEqual(result["News"][0]["summary"], "")
            self.assertEqual(result["News"][0]["content"], "Publisher excerpt")
            model.assert_not_called()
            session.commit.assert_not_called()

    async def test_section_filter_uses_only_selected_category_ids(self):
        db = AsyncMock()
        rows = Mock()
        rows.all.return_value = []
        db.execute.return_value = rows
        await list_items(category_ids="3,11", limit=100, db=db)
        query = db.execute.call_args.args[0].compile()
        self.assertIn([3, 11], query.params.values())
        for bad in ["", "1,nope", "-1", ",", "0", ",".join(["1"] * 101)]:
            with self.assertRaises(HTTPException) as caught:
                await list_items(category_ids=bad, limit=100, db=db)
            self.assertEqual(caught.exception.status_code, 422)


class RuleShutdownTests(unittest.TestCase):
    def test_old_summary_rule_skips_ai_but_keeps_other_actions(self):
        from tasks import _apply_rules
        story = item(1, "A story", "https://example.com/a")
        rule = Rule(id=1, category_ids=[], actions=["summarize", "save_to_notes"])
        session = Mock()
        with patch("tasks.evaluate_rule", return_value=True), patch("tasks.get_rule_actions", return_value=rule.actions), patch("tasks._run_async") as run:
            _apply_rules(session, story, [rule])
            run.assert_not_called()
            self.assertEqual(session.add.call_count, 1)
            self.assertEqual(story.matched_rules, [1])


if __name__ == "__main__":
    unittest.main()
