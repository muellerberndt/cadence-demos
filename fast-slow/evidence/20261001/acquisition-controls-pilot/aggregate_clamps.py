"""Read-only aggregation of already verified, same-snapshot clamp diagnostics."""

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rms(values):
    assert values
    return math.sqrt(math.fsum(value * value for value in values) / len(values))


def summarize(pairs, layout):
    free = [value for f, _ in pairs for value in f["past_errors"]]
    full = [value for _, c in pairs for value in c["past_errors"]]
    context = [c["state"][j] - f["state"][j] for f, c in pairs for j in (0, 1)]
    latent_indices = [0, 1] + (list(range(4, 8)) if layout == "interaction" else [])
    latent = [c["state"][j] - f["state"][j] for f, c in pairs for j in latent_indices]
    result = {
        "matched_rows": len(pairs),
        "past_only_p_residual_rms": rms(free),
        "past_plus_future_p_residual_rms": rms(full),
        "full_to_free_p_residual_rms_ratio": rms(full) / rms(free),
        "p_residual_delta_rms": rms([b - a for a, b in zip(free, full)]),
        "context_state_delta_rms": rms(context),
        "unclamped_latent_state_delta_rms": rms(latent),
    }
    if layout == "interaction":
        result["interaction_state_delta_rms"] = rms(
            [c["state"][j] - f["state"][j] for f, c in pairs for j in range(4, 8)]
        )
    return result


def main():
    protocol = json.loads((ROOT / "protocol.json").read_text())
    verification = json.loads((ROOT / "verification.json").read_text())
    assert verification["valid"] and verification["fresh_query_replay"]
    assert sha(ROOT / "protocol.json") == verification["protocol_sha256"]
    source_hashes = {
        "protocol.json": sha(ROOT / "protocol.json"),
        "verification.json": sha(ROOT / "verification.json"),
        "pilot-summary.json": sha(ROOT / "pilot-summary.json"),
    }
    rows, missing, groups, report_totals, statuses = [], [], defaultdict(list), Counter(), Counter()
    gates = Counter()
    gate_mae = defaultdict(list)
    for spec in protocol["cases"]:
        if spec["role"] != "development":
            continue
        case = ROOT / "results" / spec["id"]
        for arm in ("ordinary", "observer"):
            report_path = case / arm / "report.json"
            report = json.loads(report_path.read_text())
            source_hashes[str(report_path.relative_to(ROOT))] = sha(report_path)
            assert report["sources_unchanged"]
            statuses[report["status"]] += 1
            for key in (
                "admissions", "admitted_presentations", "attempted_updates",
                "attempted_presentations", "calls", "refusals", "interrupted_calls",
                "errored_calls", "unknown_work_calls",
            ):
                report_totals[key] += report[key]
            for score in report["gates"]:
                group = "mixed" if spec["condition"] == "balanced_mixed" else "fixed"
                gates[f"{group}_completed"] += 1
                gates[f"{group}_passed"] += int(score["passed"])
                gate_mae[group].extend(v for pair in score["per_gain_future_mae"].values() for v in pair)
            for update in (32, 128):
                path = case / arm / f"gate-{update}.json"
                meta = {key: spec[key] for key in ("id", "condition", "layout", "parameter_prior")}
                meta.update(arm=arm, update=update)
                if not path.exists():
                    missing.append(meta)
                    continue
                source_hashes[str(path.relative_to(ROOT))] = sha(path)
                gate = json.loads(path.read_text())
                forecasts = {q["row"]: q for q in gate["queries"] if q["kind"] == "forecast"}
                full = [q for q in gate["queries"] if q["kind"] == "full_clamp_diagnostic"]
                assert len(full) == (8 if spec["condition"] == "balanced_mixed" else 4)
                pairs = [(forecasts[q["row"]], q) for q in full]
                for free, clamped in pairs:
                    assert free["qualified"] and clamped["qualified"]
                    assert free["before_sha256"] == free["after_sha256"] == clamped["before_sha256"] == clamped["after_sha256"]
                    assert free["state"][2:4] == clamped["state"][2:4]
                pair_complete = (case / ("observer" if arm == "ordinary" else "ordinary") / f"gate-{update}.json").exists()
                rows.append(dict(meta, paired_arm_checkpoint_available=pair_complete, **summarize(pairs, spec["layout"])))
                if pair_complete:
                    groups[(spec["condition"], spec["layout"], arm, update)].append((spec["parameter_prior"], pairs))
    aggregates = []
    for (condition, layout, arm, update), entries in sorted(groups.items()):
        pairs = [pair for _, group in entries for pair in group]
        aggregates.append({
            "condition": condition, "layout": layout, "arm": arm, "update": update,
            "included_priors": sorted(prior for prior, _ in entries),
            **summarize(pairs, layout),
        })
    result = {
        "schema": "cadence-acquisition-clamp-diagnostic-v1",
        "analysis_source_sha256": sha(Path(__file__)),
        "source_hashes": source_hashes,
        "all_verified_queries_reused_without_learning": True,
        "totals": dict(report_totals), "arm_statuses": dict(statuses),
        "gates": dict(gates),
        "head_mae_ranges": {key: [min(vals), max(vals)] for key, vals in gate_mae.items()},
        "rows": rows,
        "missing_checkpoints": missing,
        "aggregates_matched_between_arms": aggregates,
        "limits": [
            "Post hoc descriptive diagnosis; no new solver calls or learning.",
            "RMS uses the same diagnostic rows and frozen parameters for past-only and past+future queries.",
            "Grouped RMS pools coordinate squares, only including prior/checkpoints available in both arms; all other rows remain separately listed.",
            "Hidden delta includes M; interaction layout additionally includes its unclamped I states. P stays actually clamped in both queries; H is excluded.",
            "Adding the future witness can alter latent states and residuals through ordinary equilibrium coupling as well as residual-observing edges.",
            "P reads raw previous inputs and M. Actual P clamps and raw inputs are identical across each pair, so any P-residual change is mediated by the measured M-state change at these fixed parameters.",
            "Current P residual is retrospective posterior model mismatch, not a stored historical forecast innovation; M can already revise under the actual present clamp in both queries.",
            "Feature shift is measured, not proven to cause acquisition failure. Large learned residual coefficients do not prove useful future-free inference.",
            "Only seed2 development results; censored exposure and unavailable gates are not imputed.",
        ],
    }
    output = ROOT / "diagnostics" / "clamp-diagnostic.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"path": str(output), "sha256": sha(output), "rows": len(rows), "groups": len(aggregates), "missing": len(missing)}))


if __name__ == "__main__":
    main()
