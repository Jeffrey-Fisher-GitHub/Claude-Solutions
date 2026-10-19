"""Render every month of the two years (in parallel), the timelapse, and preview images.

    python3 src/render_all.py            # skips months already rendered
"""
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render as R  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VID = ROOT / "videos"


def months():
    days = json.loads((ROOT / "data" / "days.json").read_text())["days"]
    groups = {}
    for d in days:
        dt = date.fromisoformat(d["date"])
        groups.setdefault((dt.year, dt.month), []).append(d["day"])
    out = []
    for i, ((y, m), ds) in enumerate(sorted(groups.items()), 1):
        name = f"month-{i:02d}_{date(y, m, 1).strftime('%Y-%m')}_days-{ds[0]:03d}-{ds[-1]:03d}.mp4"
        out.append((ds[0], ds[-1], VID / name))
    return out


def job(args):
    d0, d1, out = args
    t = time.time()
    tmp = out.with_suffix(".part.mp4")
    r = R.Renderer()
    R.render_days(r, d0, d1, tmp)
    tmp.rename(out)
    return out.name, round(time.time() - t)


def main():
    VID.mkdir(exist_ok=True)
    todo = [m for m in months() if not m[2].exists()]
    print(f"{len(todo)} months to render", flush=True)
    with ProcessPoolExecutor(2) as ex:
        futs = [ex.submit(job, m) for m in todo]
        for f in as_completed(futs):
            print("done", *f.result(), flush=True)
    tl = VID / "two-years-timelapse.mp4"
    if not tl.exists():
        R.render_timelapse(R.Renderer(), tl)
        print("done timelapse", flush=True)


if __name__ == "__main__":
    main()
