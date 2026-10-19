import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "fireworks_match_agent", ROOT / "tools" / "fireworks_match_agent.py",
)
match_agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(match_agent)


class MatchReportTests(unittest.TestCase):
    def test_string_and_list_evidence_render_as_sentences_not_characters(self):
        report = match_agent.render_markdown(
            {
                "match_analyses": [{
                    "match_id": "match-1",
                    "likely_causes": [
                        {"cause": "Late deposits", "confidence": "medium",
                         "evidence": "No deposits after round 800"},
                    ],
                    "recommended_experiment": None,
                }],
                "recurring_patterns": [{
                    "pattern": "Losses after round 800",
                    "confidence": "high",
                    "evidence": ["Two losses stopped depositing after round 800"],
                }],
            },
            {"created_at": "now", "model": "test", "match_count": 1},
        )
        self.assertIn("Late deposits (medium confidence): No deposits after round 800", report)
        self.assertIn("Two losses stopped depositing after round 800", report)
        self.assertNotIn("N; o;  ; d; e", report)


if __name__ == "__main__":
    unittest.main()
