import asyncio
import copy
import json
import unittest
from unittest.mock import patch

from config import Settings
from research import analyze, collect_sources, parse_plan, parse_report, pipeline, public_url
from validation import AnalysisError


def report():
    return {"score": 20, "sufficient": True, "claims": [{"claim": "Твердження", "verdict": "підтверджено",
        "explanation": "Є два докази", "source_ids": [1, 2]}], "limits": "Незалежність потребує перевірки."}


def search():
    return {"results": [{"url": "https://one.example.org/article", "title": "A", "raw_content": "Докази з першого джерела. " * 100},
        {"url": "https://two.example.net/article", "title": "B", "raw_content": "Докази з другого джерела. " * 100}]}


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.sources = collect_sources([search()])

    def test_real_citations_are_clickable_and_duplicate_results_removed(self):
        sources = collect_sources([search(), search()])
        self.assertEqual(len(sources), 2)
        result = parse_report(report(), sources)
        self.assertEqual(result["score"], 20)
        self.assertEqual(result["segments"][1]["url"], sources[0]["url"])

    def test_snippets_alone_never_produce_score(self):
        sources = copy.deepcopy(self.sources)
        for source in sources: source["extracted"] = False
        self.assertIsNone(parse_report(report(), sources)["score"])

    def test_unknown_source_ids_and_unverified_claim_hide_score(self):
        value = report(); value["claims"][0]["source_ids"].append(999)
        self.assertIsNone(parse_report(value, self.sources)["score"])
        value = report(); value["claims"][0]["verdict"] = "недостатньо даних"
        self.assertIsNone(parse_report(value, self.sources)["score"])

    def test_one_domain_not_enough(self):
        self.sources[1]["url"] = "https://one.example.org/another"
        self.assertIsNone(parse_report(report(), self.sources)["score"])

    def test_partial_research_hides_score_and_discloses_limit(self):
        result = parse_report(report(), self.sources, "Перевірено лише початок сторінки")
        self.assertIsNone(result["score"])
        self.assertIn("лише початок", result["segments"][-1]["text"])

    def test_bad_schema_boolean_score_and_missing_limits_rejected(self):
        for update in ({"score": True}, {"score": 101}, {"limits": ""}, {"claims": []}, {"sufficient": "yes"}):
            with self.assertRaises(AnalysisError): parse_report({**report(), **update}, self.sources)

    def test_generated_urls_never_become_sources(self):
        value = report(); value["claims"][0]["explanation"] = "Вигадано https://fake.example.org/x"
        result = parse_report(value, self.sources)
        self.assertNotIn("https://fake", str(result))

    def test_source_number_matches_citation_if_only_second_source_used(self):
        value = report(); value["claims"][0]["source_ids"] = [2]
        result = parse_report(value, self.sources)
        self.assertEqual(result["sources"][0]["id"], 2)
        self.assertEqual(result["segments"][1]["text"], "[2]")

    def test_url_guards_and_original_not_independent(self):
        for url in ("http://127.0.0.1/a", "http://169.254.169.254", "file:///etc/passwd", "https://user:pass@x.example.org", "http://localhost", "http://x.local", "https://example.org:8080"):
            self.assertIsNone(public_url(url), url)
        self.assertEqual(len(collect_sources([search()], "https://one.example.org/article")), 1)

    def test_plan_queries_deduplicate_and_reject_missing_claim(self):
        self.assertEqual(parse_plan({"claim": "Test", "queries": ["Test", "test"]})[1], ["Test"])
        for data in ({"claim": "", "queries": []}, {"claim": "Test", "queries": []}, {"claim": "Test", "queries": [None]}):
            with self.assertRaises(AnalysisError): parse_plan(data)


class Content:
    def __init__(self, value): self.body = json.dumps(value).encode()
    async def iter_chunked(self, size): yield self.body


class Response:
    def __init__(self, value, status=200): self.status = status; self.content = Content(value)
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass


class FakeSession:
    def __init__(self, error=None, extract=None, empty=False, truncated=False):
        self.calls = []; self.error = error; self.extract = extract; self.empty = empty; self.truncated = truncated
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def post(self, url, **kwargs):
        payload = kwargs["json"]; self.calls.append((url, payload))
        if self.error: return Response({}, self.error)
        if url.endswith("/extract"):
            return Response({"results": [] if self.extract is None else [{"url": payload["urls"][0], "raw_content": self.extract}]})
        if url.endswith("/search"): return Response({"results": []} if self.empty else search())
        value = {"claim": "Твердження", "queries": ["підтвердження", "спростування"]} if payload["model"].startswith("qwen/") else report()
        return Response({"choices": [{"finish_reason": "length" if self.truncated else "stop", "message": {"content": json.dumps(value)}}]})


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_has_two_model_calls_two_basic_searches_and_no_paid_fallback(self):
        session = FakeSession()
        result = await pipeline(session, Settings(), "text", "Матеріал", None)
        self.assertEqual(result["score"], 20)
        self.assertEqual(len(session.calls), 4)
        searches = [p for url, p in session.calls if url.endswith("/search")]
        self.assertEqual(len(searches), 2)
        self.assertTrue(all(p["search_depth"] == "basic" and p["auto_parameters"] is False for p in searches))
        self.assertEqual(session.calls[-1][1]["model"], "openai/gpt-oss-120b")
        self.assertFalse(session.calls[-1][1]["stream"])

    async def test_photo_only_sent_to_vision_model(self):
        session = FakeSession()
        await pipeline(session, Settings(), "photo", "", b"jpeg")
        self.assertEqual(session.calls[0][1]["messages"][1]["content"][1]["type"], "image_url")
        self.assertNotIn("image_url", json.dumps(session.calls[-1][1]))

    async def test_unreadable_url_never_guessed(self):
        session = FakeSession()
        with self.assertRaises(AnalysisError): await pipeline(session, Settings(), "link", "https://article.example.org", None)
        self.assertEqual(len(session.calls), 1)

    async def test_long_page_discloses_truncation_and_hides_score(self):
        session = FakeSession(extract="Довга стаття " * 1000)
        result = await pipeline(session, Settings(), "link", "https://article.example.org", None)
        self.assertIsNone(result["score"])
        self.assertIn("4000", result["segments"][-1]["text"])

    async def test_no_sources_is_unknown_without_extra_model_call(self):
        session = FakeSession(empty=True)
        result = await pipeline(session, Settings(), "text", "Матеріал", None)
        self.assertIsNone(result["score"])
        self.assertEqual(len(session.calls), 3)

    async def test_quota_error_not_retried_and_has_clear_message(self):
        session = FakeSession(error=429)
        with patch("research.aiohttp.ClientSession", return_value=session):
            with self.assertRaisesRegex(AnalysisError, "квота"):
                await analyze(Settings(), "text", "Матеріал")
        self.assertEqual(len(session.calls), 1)

    async def test_truncated_model_output_rejected_before_search(self):
        session = FakeSession(truncated=True)
        with self.assertRaises(AnalysisError): await pipeline(session, Settings(), "text", "Матеріал", None)
        self.assertEqual(len(session.calls), 1)

    async def test_whole_request_timeout(self):
        async def slow(*args): await asyncio.sleep(1)
        with patch("research.pipeline", side_effect=slow), patch("research.aiohttp.ClientSession", return_value=FakeSession()):
            with self.assertRaisesRegex(AnalysisError, "вчасно"):
                await analyze(Settings(timeout=0.01), "text", "Матеріал")

    async def test_partial_search_error_is_disclosed(self):
        class PartialSession(FakeSession):
            def post(self, url, **kwargs):
                if url.endswith("/search") and kwargs["json"]["query"] == "спростування":
                    return Response({}, 429)
                return super().post(url, **kwargs)
        result = await pipeline(PartialSession(), Settings(), "text", "Матеріал", None)
        self.assertIsNone(result["score"])
        self.assertIn("покриття неповне", result["segments"][-1]["text"])
