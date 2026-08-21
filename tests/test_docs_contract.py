import json,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
DOCS=["architecture.md","timing-and-data-model.md","pin-allocation.md","preliminary-power-budget.md","validation-plan.md","review-gates.md","resonance-architecture.md","resonance-safety-boundary.md","resonance-hypotheses.md","emergence-architecture.md"]
class DocsContractTest(unittest.TestCase):
 def test_all_docs_warn(self):
  for name in DOCS:self.assertIn("ENGINEERING REVIEW ONLY",(ROOT/"docs"/name).read_text(encoding="utf-8"))
 def test_gates_and_gpio_are_complete(self):
  design=json.loads((ROOT/"hardware/design-manifest.json").read_text(encoding="utf-8")); gates=(ROOT/"docs/review-gates.md").read_text(encoding="utf-8"); pins=(ROOT/"docs/pin-allocation.md").read_text(encoding="utf-8")
  for gate in design["review_gates"]:self.assertIn(gate,gates)
  for gpio,net in design["gpio_allocation"].items():self.assertIn(gpio,pins);self.assertIn(net,pins)
 def test_numeric_contracts(self):
  timing=(ROOT/"docs/timing-and-data-model.md").read_text(encoding="utf-8"); validation=(ROOT/"docs/validation-plan.md").read_text(encoding="utf-8"); power=(ROOT/"docs/preliminary-power-budget.md").read_text(encoding="utf-8")
  for token in ("1 microsecond","100 microseconds","1 millisecond","250 nanoseconds","500 nanoseconds"):self.assertIn(token,timing)
  self.assertIn("24-hour",validation);self.assertIn("45-second",validation)
  for column in ("Nominal","Peak","Source","Confidence","Margin","Measurement hook"):self.assertIn(column,power)
if __name__=="__main__":unittest.main()
