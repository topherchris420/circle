"""Guard against lossy re-encoding of documentation (e.g. em dash or +/- turned into '?')."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUSPICIOUS = [
    re.compile(r"\w\*{0,2} \? [A-Z]"),      # "ONLY ? NOT": a dash lost between words
    re.compile(r"(?<![\w?])\?\d"),          # "?2 microseconds": a lost +/- or <=
    re.compile(r"\?{4,}"),                  # "????": lost box-drawing characters
]


class DocsEncodingTest(unittest.TestCase):
    def test_markdown_has_no_replacement_question_marks(self):
        offenders = []
        for path in sorted(list(ROOT.glob("*.md")) + list(ROOT.glob("docs/**/*.md")) + list(ROOT.glob("experiments/**/*.md"))):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if any(p.search(line) for p in SUSPICIOUS):
                    offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:80]}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
