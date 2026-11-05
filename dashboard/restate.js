// Browser copy of src/restate.py: applies a user's rules to one company-quarter.
// Kept identical to the Python version; tests/test_dashboard_parity.py checks every quarter.
function restateRecord(rec, rules, def) {
  const flags = rec.validation_failed ? ["Extraction did not tie to reported totals"] : [];
  const shares = rec.shares;
  const steps = [];
  let consCore = rec.ffo.amount;
  for (const line of rec.rule_lines) {
    const cat = line.category, amt = line.amount;
    const info = def.categories[cat] || def.categories.other;
    let applied, reason;
    if (cat === "noncontrolling_interest") {
      applied = true; reason = "Noncontrolling interests' share of the adjustments; applied as the company did";
    } else {
      const t = rules.treatments[cat] || rules.treatments.other || "keep_costs";
      reason = def.treatment_reasons[t];
      if (t === info.default) reason += " (" + info.why + ")";
      if (amt === 0) { applied = false; reason += "; zero this quarter"; }
      else if (t === "apply") applied = true;
      else if (t === "keep_all") applied = false;
      else { applied = amt < 0; reason += amt < 0 ? "; gain/recovery removed" : "; company add-back reversed"; }
      if (amt !== 0 && (!def.categories[cat] || def.categories[cat].provisional))
        flags.push("Review: '" + line.label + "' (" + cat + ") handled by a provisional rule");
    }
    if (applied) consCore += amt;
    steps.push(Object.assign({}, line, { applied, effect: applied ? amt : 0, reason }));
  }
  let capex = [], capexSource = null;
  if (rules.capex.deduct) {
    capex = rec.capex_recon.slice();
    capexSource = capex.length ? "affo_reconciliation" : null;
    const d = rec.capex_disclosed;
    if (!capex.length && d && rules.capex.use_capex_table && d.basis === "quarter" && d.amount) {
      capex = [Object.assign({}, d, { amount: -Math.abs(d.amount) })];
      capexSource = "capex_table";
      flags.push("Recurring capex taken from a separate table (page " + (d.page || "") + "): the company's own AFFO does not deduct it");
    } else if (!capex.length && d && d.basis !== "quarter") {
      flags.push("Recurring capex only disclosed on a '" + d.basis + "' basis; Conservative AFFO not computed");
    } else if (!capex.length) {
      flags.push("No recurring capex disclosed; Conservative AFFO not computed");
    }
  }
  const consAffo = capex.length ? consCore + capex.reduce((a, c) => a + c.amount, 0) : null;
  const ps = (x) => (x == null || !shares ? null : Math.round((x / shares) * 1e4) / 1e4);
  return { steps, cons_core: consCore, cons_core_ps: ps(consCore), cons_affo: consAffo, cons_affo_ps: ps(consAffo),
           capex, capex_source: capexSource, flags };
}

function rulesFromPreset(preset, def) {
  const how = def.presets[preset];
  const treatments = {};
  Object.entries(def.categories).forEach(([c, v]) => { treatments[c] = how === "default" ? v.default : how; });
  return { treatments, capex: Object.assign({}, def.capex) };
}

if (typeof module !== "undefined") module.exports = { restateRecord, rulesFromPreset };
