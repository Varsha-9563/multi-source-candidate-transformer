import json
import tempfile
import unittest
from pathlib import Path

from candidate_transformer.cli import run


ROOT = Path(__file__).resolve().parents[1]

FIXTURE_CSV = (
    "name,email,phone,current_company,title,location\n"
    "Ananya Sharma,ananya.sharma@example.com,9876543210,Acme Analytics,Data Engineering Intern,Bengaluru Karnataka India\n"
)

FIXTURE_NOTES = (
    "Ananya Sharma is a Data Engineering Intern at Acme Analytics, based in Bengaluru.\n"
    "Email: ananya.sharma@example.com\n"
    "Phone: +91 98765 43210\n"
    "Skills include Python, SQL, and PySpark.\n"
)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        # each test gets its own isolated temp directory + fixture files,
        # so this suite never depends on samples/recruiter.csv or any
        # other file that might change as the demo dataset evolves.
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)

        self.csv_path = tmp_path / "recruiter.csv"
        self.csv_path.write_text(FIXTURE_CSV, encoding="utf-8")

        self.notes_path = tmp_path / "notes.txt"
        self.notes_path.write_text(FIXTURE_NOTES, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_pipeline_builds_canonical_profile(self):
        output = run(str(self.csv_path), str(self.notes_path), None)

        self.assertEqual(output["full_name"], "Ananya Sharma")
        self.assertIn("ananya.sharma@example.com", output["emails"])
        self.assertIn("+919876543210", output["phones"])
        self.assertTrue(any(skill["name"] == "Python" for skill in output["skills"]))
        self.assertGreater(output["overall_confidence"], 0.6)
        self.assertTrue(output["provenance"])

    def test_custom_projection(self):
        output = run(
            str(self.csv_path),
            str(self.notes_path),
            str(ROOT / "configs" / "custom_output.json"),
        )

        self.assertEqual(output["full_name"], "Ananya Sharma")
        self.assertEqual(output["primary_email"], "ananya.sharma@example.com")
        self.assertIn("Python", output["skills"])
        self.assertIn("overall_confidence", output)
        self.assertNotIn("provenance", output)

    def test_missing_notes_does_not_crash(self):
        missing_notes = Path(self.tmp.name) / "missing.txt"
        output = run(str(self.csv_path), str(missing_notes), None)

        self.assertEqual(output["full_name"], "Ananya Sharma")
        self.assertEqual(output["skills"], [])
        self.assertTrue(output["warnings"])

    def test_invalid_github_url_logs_warning(self):
        output = run(
            str(self.csv_path),
            str(self.notes_path),
            None,
            "not-a-github-url",
        )

        self.assertTrue(any("GitHub URL" in item["message"] for item in output["warnings"]))

    def test_conflicting_phones_are_kept_and_skill_aliases_normalize(self):
        csv_path = Path(self.tmp.name) / "candidate_conflict.csv"
        csv_path.write_text(
            "name,email,phone,current_company,title,location\n"
            "Ananya Sharma,ananya.sharma@example.com,9123456780,Acme Analytics,Intern,Bengaluru India\n",
            encoding="utf-8",
        )
        notes_path = Path(self.tmp.name) / "notes_conflict.txt"
        notes_path.write_text(
            "Ananya Sharma phone +91 98765 43210. Skills: JS and JavaScript.",
            encoding="utf-8",
        )

        output = run(str(csv_path), str(notes_path), None)

        self.assertIn("+919123456780", output["phones"])
        self.assertIn("+919876543210", output["phones"])
        self.assertTrue(any(skill["name"] == "JavaScript" for skill in output["skills"]))


if __name__ == "__main__":
    unittest.main()