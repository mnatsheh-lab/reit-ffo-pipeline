"""The dashboard's in-browser rules engine (dashboard/restate.js) must give exactly the same
results as src/restate.py, for every stored company-quarter and every preset."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.build_dashboard import record
from src.restate import DEFINITION, restate

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


def preset_rules(name):
    how = DEFINITION["presets"][name]
    return {"treatments": {c: (v["default"] if how == "default" else how) for c, v in DEFINITION["categories"].items()},
            "capex": dict(DEFINITION["capex"])}


@unittest.skipIf(NODE is None, "node not installed")
class ParityTests(unittest.TestCase):
    def test_python_and_browser_agree(self):
        files = sorted((ROOT / "output" / "extractions").glob("*.json"))
        if not files:
            self.skipTest("no extractions committed")
        docs = [json.loads(p.read_text()) for p in files]
        records = [record(d) for d in docs]
        rule_sets = {name: preset_rules(name) for name in DEFINITION["presets"]}
        rule_sets["No capex"] = {**preset_rules("Conservative"), "capex": {"deduct": False, "use_capex_table": True}}
        rule_sets["No capex tables"] = {**preset_rules("Conservative"), "capex": {"deduct": True, "use_capex_table": False}}
        with tempfile.TemporaryDirectory() as d:
            Path(d, "in.json").write_text(json.dumps({"records": records, "rules": rule_sets, "def": DEFINITION}))
            script = (f"const {{restateRecord}} = require({json.dumps(str(ROOT / 'dashboard' / 'restate.js'))});"
                      f"const x = require({json.dumps(str(Path(d, 'in.json')))});"
                      "const out = {}; for (const [n, r] of Object.entries(x.rules)) out[n] = x.records.map(rec => restateRecord(rec, r, x.def));"
                      "console.log(JSON.stringify(out));")
            js = json.loads(subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True).stdout)
        checked = 0
        for name, rules in rule_sets.items():
            for doc, rec, j in zip(docs, records, js[name]):
                p = restate(doc["extraction"], rules)
                key = f"{rec['ticker']} {rec['quarter']} [{name}]"
                self.assertAlmostEqual(p["conservative_core_ffo"], j["cons_core"], delta=0.5, msg=key)
                if p["conservative_affo"] is None:
                    self.assertIsNone(j["cons_affo"], key)
                else:
                    self.assertAlmostEqual(p["conservative_affo"], j["cons_affo"], delta=0.5, msg=key)
                self.assertEqual([s["applied"] for s in p["steps"]], [s["applied"] for s in j["steps"]], key)
                self.assertEqual(p["flags"][:1] and p["flags"][0][:20], j["flags"][:1] and j["flags"][0][:20], key)
                checked += 1
        self.assertGreater(checked, 0)

    def test_presets_mean_what_they_say(self):
        """'NAREIT FFO only' must equal NAREIT FFO; 'As reported' must equal the company's own core metric
        wherever the company's core section is fully captured and nothing sits in its AFFO section."""
        for p in sorted((ROOT / "output" / "extractions").glob("*.json")):
            e = json.loads(p.read_text())["extraction"]
            nareit = restate(e, preset_rules("NAREIT FFO only"))
            moved = [l for sec, l in __import__("src.restate", fromlist=["rule_lines"]).rule_lines(e) if sec == "affo" and l["amount"]]
            self.assertAlmostEqual(nareit["conservative_core_ffo"],
                                   e["ffo_total"]["amount"] + sum(l["amount"] for sec, l in __import__("src.restate", fromlist=["rule_lines"]).rule_lines(e) if l["category"] == "noncontrolling_interest"),
                                   delta=0.5, msg=p.name)
            if e.get("core_total") and not moved:
                reported = restate(e, preset_rules("As reported"))
                self.assertAlmostEqual(reported["conservative_core_ffo"], e["core_total"]["amount"], delta=1.5, msg=p.name)


if __name__ == "__main__":
    unittest.main()
