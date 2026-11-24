"""Prints a side-by-side summary of perf_report.py results. Usage: <python> scripts/perf_summary.py before after"""
import json
import pathlib
import sys

DIR = pathlib.Path(__file__).resolve().parent.parent / "qa" / "perf"
labels = sys.argv[1:] or ["before"]
data = {l: {r["scenario"]: r for r in json.loads((DIR / f"{l}.json").read_text())["runs"]} for l in labels}


def mb(b):
    return f"{b / 1e6:.2f} MB" if b is not None else "-"


def ms(v):
    return f"{v / 1000:.2f} s" if v is not None else "-"


ROWS = [
    ("Opening visible", lambda r: ms(r["opening_visible_ms"])),
    ("  transfer before opening", lambda r: mb(r["transfer_before_opening"]["total"])),
    ("  turntable bytes before opening", lambda r: mb(r["transfer_before_opening"]["spin"])),
    ("Journey complete (cold)", lambda r: ms(r["journey_complete_ms"])),
    ("  transfer at top", lambda r: mb(r["transfer_at_top"]["total"])),
    ("Turntable usable after jump", lambda r: ms(r["turntable_usable_ms_after_jump"])),
    ("Selected finish complete after jump", lambda r: ms(r["selected_finish_complete_ms_after_jump"])),
    ("  configurator initial transfer", lambda r: mb(r["transfer_configurator_initial"]["total"])),
    ("Finish change shown (silver, ember, graphite)",
     lambda r: ", ".join(f"{v['shown_ms']} ms" if v["shown_ms"] is not None else "-" for v in r["finish_changes"].values())),
    ("  finish change transfer (silver, ember)",
     lambda r: ", ".join(mb(r["finish_changes"][f]["transfer"]["total"]) for f in ("silver", "ember"))),
    ("Total transfer (all viewed)", lambda r: mb(r["transfer_total"]["total"])),
    ("Process memory at top (working set / private)",
     lambda r: f"{r['memory_at_top']['working_set_mb']:.0f} / {r['memory_at_top']['private_mb']:.0f} MB"),
    ("Process memory configurator",
     lambda r: f"{r['memory_configurator_initial']['working_set_mb']:.0f} / {r['memory_configurator_initial']['private_mb']:.0f} MB"),
    ("Process memory all finishes viewed",
     lambda r: f"{r['memory_all_finishes_viewed']['working_set_mb']:.0f} / {r['memory_all_finishes_viewed']['private_mb']:.0f} MB"),
    ("Turntable decoded (frames / MB)", lambda r: decoded(r)),
    ("Turntable canvas", lambda r: "x".join(map(str, r["turn_stats_warm"]["turnCanvas"]))),
    ("Slow drag (median / max / spikes)",
     lambda r: f"{r['drag_slow']['median']} / {r['drag_slow']['max']} / {r['drag_slow']['spikes_over_4x_median']}" if "drag_slow" in r else "-"),
    ("Fast drag (changing frames / median / max / spikes)",
     lambda r: f"{r['drag_fast']['changing']} / {r['drag_fast']['median']} / {r['drag_fast']['max']} / {r['drag_fast']['spikes_over_4x_median']}" if "drag_fast" in r else "-"),
    ("Page errors", lambda r: str(len(r["errors"]))),
]


def decoded(r):
    t = r["turn_stats_warm"]["turn"] or {}
    if "decoded" in t:
        return f"{t['decoded']} (budget {t['budget']}) / {int(t['decodedBytes']) / 1e6:.1f} MB"
    # Before: every loaded frame stays decoded as an image element (1200 x 900 x 4 bytes, calculated).
    n = sum(r["transfer_total"]["spinFiles"].values())
    return f"{n} retained (calc.) / {n * 1200 * 900 * 4 / 1e6:.0f} MB"


for scen in ("desktop", "phone-slow", "phone-warm"):
    runs = {l: data[l].get(scen) for l in labels}
    if not any(runs.values()):
        continue
    print(f"\n== {scen}")
    print(f"{'':52}" + "".join(f"{l:>30}" for l in labels))
    for name, fn in ROWS:
        vals = []
        for l in labels:
            try:
                vals.append(fn(runs[l]) if runs[l] else "-")
            except (KeyError, TypeError):
                vals.append("-")
        print(f"{name:52}" + "".join(f"{v:>30}" for v in vals))
