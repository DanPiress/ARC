"""Plan where the journey frames sit along the camera move, so each step changes the picture by the same amount.

The first journey was rendered with 48 frames per chapter transition, eased (dense at the chapters, sparse in the
middle), so mid-transition neighbouring frames differed a lot and the page's cross-fade showed double images.
This reads the measured change between the old frames (work/ghost-<device>.json from work/journey_ghost.py),
turns it into visual change per unit of camera progress, and places frames at equal visual steps.

  <python> design/arc-v4/plan_journey.py [frames]   -> src/data/journeyFrames.json

The JSON holds, per device, the camera progress of every frame (0..1 across the whole journey, chapter i at i/3)
and the chapter frame indices. render_scene.py renders exactly these; the page maps scroll to camera progress,
then to a fractional frame index through this table.
"""
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 193
OLD_STEPS = 48
SEGS = 3


def ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * t)


plan = {}
for dev in ("desktop", "phone"):
    steps = [r["step"] for r in json.loads((ROOT / "work" / f"ghost-{dev}.json").read_text())]
    # Cumulative visual distance at each old frame, against camera progress within its segment.
    seg_c, seg_d = [], []
    for s in range(SEGS):
        cs, ds, d = [], [], 0.0
        for j in range(OLD_STEPS + 1):
            k = s * OLD_STEPS + j
            cs.append(ease(j / OLD_STEPS))
            ds.append(d)
            if j < OLD_STEPS:
                d += max(steps[k], 0.05)
        seg_c.append(cs)
        seg_d.append(ds)
    lengths = [ds[-1] for ds in seg_d]
    total = sum(lengths)
    # Frames per segment in proportion to its visual length (each segment keeps both chapter frames).
    inner = TOTAL - 1
    counts = [max(8, round(inner * L / total)) for L in lengths]
    counts[-1] += inner - sum(counts)
    progress, keys = [0.0], [0]
    for s in range(SEGS):
        cs, ds = seg_c[s], seg_d[s]
        for m in range(1, counts[s] + 1):
            target = ds[-1] * m / counts[s]
            j = next(i for i in range(1, len(ds)) if ds[i] >= target - 1e-9)
            f = (target - ds[j - 1]) / (ds[j] - ds[j - 1]) if ds[j] > ds[j - 1] else 1.0
            c = cs[j - 1] + (cs[j] - cs[j - 1]) * f
            progress.append(round((s + c) / SEGS, 6))
        keys.append(len(progress) - 1)
    step = [lengths[s] / counts[s] for s in range(SEGS)]
    print(f"{dev}: {len(progress)} frames, per transition {counts}, keys {keys}; "
          f"visual step {', '.join(f'{x:.2f}' for x in step)} (was max {max(steps):.2f}, mean {sum(steps[:-1]) / (len(steps) - 1):.2f})")
    plan[dev] = {"progress": progress, "keys": keys}

out = ROOT / "src" / "data" / "journeyFrames.json"
out.write_text(json.dumps(plan, separators=(",", ":")))
print("wrote", out)
