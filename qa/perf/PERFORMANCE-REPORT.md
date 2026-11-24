# ARC performance and finishing pass: before/after report

24 November 2026. Measured on this Windows 10 computer in Playwright's headless Chromium. "Before" is the
previous production build (kept in `work/dist-before`, served on port 4174); "after" is the current build
(port 4173). Both builds were measured with the same script (`scripts/perf_report.py`) under the same conditions, and every
scenario starts a new browser, so the cache is cold. Raw results: `qa/perf/before.json` and `qa/perf/after.json`.
Table: `qa/perf/summary.txt` (`scripts/perf_summary.py before after`).

**No physical phone was tested.** "Phone size" means a 390×844 viewport at DPR 2 with touch, running on the
computer. "Phone slow" adds emulated throttling: 1.6 Mbps down, 0.75 Mbps up, 150 ms round trip, and the CPU
slowed 4×. Neither measures a phone's decoder, GPU, memory limits or radio.

## What changed

1. **Bounded turntable cache.** Before, every loaded turntable frame was kept as a decoded 1200×900 image. That
   was 144 frames on first view and 288 once all finishes had been viewed: about 622 MB and 1.24 GB of pixels
   (calculated). Now:
   - each frame is kept as its compressed file;
   - decoded copies are cropped to the viewer and scaled to its size, never larger than the file, and are kept
     only for:
     - the two frames being drawn;
     - a ring around the current angle, longer in the direction of travel;
     - the angle a keyboard turn or flick is heading for;
     - anchors every 6th frame on desktop or every 12th at phone size;
     - one frame at the current angle for each other finish, so switching is instant;
   - everything else is released (`ImageBitmap.close()`), and the list is cut to the budget, nearest first.
   - The budget is 36 decoded frames on desktop and 24 at phone size (`CACHE` in `src/components/Configurator.tsx`).
   - The page publishes its live count on the canvas (`data-decoded`, `data-budget`, `data-decoded-by`), and
     `scripts/qa_cache.py` checks it while turning and switching.

   Turning is unchanged: neighbouring frames blend while moving and it rests on one sharp frame.
2. **Lighter turntable files.** There is a new 960×720 set (`public/spin-s/`, about 6 MB per finish instead of 8.3–8.7 MB),
   chosen whenever it is not enlarged by more than 10%. That covers phones and standard-density desktop screens;
   high-density desktops still get the 1200×900 set. Trials and the choice of size are described below.
3. **Journey memory.**
   - Decoded frames are capped at 28 on desktop and 24 at phone size: a window of ±10 or ±8 frames plus anchors
     every 24th, down from ±12 plus anchors every 12th.
   - Frames are never decoded larger than the file.
   - When the journey is off screen it keeps only 2–3 frames, and fetching pauses until it comes back.
4. **Cold loading.**
   - The turntable's placeholder `<img>` no longer downloads with the opening screen. It was 100 KB fighting the
     opening frame on slow connections. A lazy `<img>` would still load on phones, so live mode now has no
     placeholder; the canvas fades in with its first frame.
   - The turntable fetches the frame at the current angle on its own first, then three at a time.
   - The journey's fine frames are now fetched nearest to the reader's position first, at low priority.
5. **Opening-frame failure.** If the opening journey frame fails, its near-identical neighbour is fetched straight
   away and shown, and the opening frame is retried twice in the background. Before, the canvas stayed hidden for
   good. A turntable frame that fails is replaced by the nearest angle that loaded.
6. **Layout.**
   - The desktop finish panel now starts level with the top of the viewer, with no empty gap above it.
   - On phones the gap between the configurator subtitle and the viewer is smaller.

## Results (same conditions, cold cache)

| Desktop 1440×900, unthrottled | Before | After |
| --- | --- | --- |
| Opening visible | 0.25 s | 0.28 s |
| Turntable bytes before opening | 0.10 MB | 0 |
| Journey fully loaded | 0.86 s | 0.70 s |
| Turntable usable after jumping to it | 0.41 s | 0.45 s |
| Selected finish fully loaded | 2.22 s | 0.72 s |
| Configurator initial transfer | 12.40 MB | 8.95 MB |
| Finish change shown (silver / ember / graphite) | 17 / 16 / 15 ms | 14 / 6 / 19 ms |
| Finish change transfer (silver / ember) | 6.39 / 6.57 MB | 4.59 / 4.71 MB |
| Total transfer, everything viewed | 38.24 MB | 31.04 MB |
| Browser memory, working set at the configurator | 1,082 MB | 447 MB |
| Browser memory, working set after all finishes viewed | 1,104 MB | 471 MB |
| Turntable decoded frames | 288 retained (1,244 MB calc.) | 30 (budget 36), 52.5 MB |

| Phone size, throttled (slow 4G-like, CPU 4×) | Before | After |
| --- | --- | --- |
| Opening visible | 3.35 s | 3.03 s |
| Transfer before the opening appears | 0.32 MB | 0.22 MB |
| Journey fully loaded (while reading the opening) | 52.2 s | 51.8 s |
| Turntable usable after jumping to it | 0.51 s * | 0.68 s |
| Selected finish fully loaded | 59.0 s | 31.4 s |
| Finish change shown | 67–70 ms | 13–28 ms |
| Total transfer, everything viewed | 35.46 MB | 28.26 MB |
| Browser memory, working set at the configurator | 1,138 MB | 384 MB |
| Browser memory, working set after all finishes viewed | 1,170 MB | 423 MB |
| Turntable decoded frames | 288 retained (1,244 MB calc.) | 19 (budget 24), 33.3 MB |

\* Before, the turntable's first frame had already downloaded with the opening screen, which made the opening
about 0.3 s slower on this profile. After, it loads only when the viewer approaches. A reader scrolling normally
starts it 400 px early, so in practice it is usually ready before it is seen; the 0.68 s is for an instant jump.

The unthrottled phone-size run follows the same pattern: working set 1,146 → 385 MB at the configurator,
selected finish 1.85 → 0.49 s, total 35.5 → 28.3 MB. See `summary.txt`.

"Working set" is the summed memory of all the headless Chromium processes (Windows `Get-Process`). It is
the real measured process memory, separate from the decoded-frame budget above, which is the page's own count of
the pixels it holds. Private bytes moved less (337 → 237 MB desktop), because Chromium holds decoded images
largely in shared memory. Neither number predicts a phone browser's limits.

**Turning smoothness** (desktop, canvas change per animation frame):
- Slow drag: unchanged, median 1.33 → 1.37, max 3.25 → 3.26, no jumps.
- Very fast flick, a full turn in a third of a second: each input event moves about 5 frames on either build, so
  both show occasional jumps. Over four repeats (`work/fastdrag.py`) the jump counts were 15, 3, 0 and 9 before
  and 5, 0, 0 and 0 after. The single run in the table above happened to show 16 jumps after; this test is noisy.

## Visual quality

- **Files:** `work/asset_compare.py` compares each candidate against the 1440 px master renders, drawn the way
  the site draws them (same crop and high-quality resize):

  | Graphite at site size | PSNR vs master |
  | --- | --- |
  | Previous 1200 q85 | 43.7–48.9 dB |
  | 960 q85 (chosen) | 41.0–46.1 dB |
  | 840 q85 | 41.6–47.0 dB |
  | 960 q70 | 40.0–44.2 dB |

  Lowering the quality setting barely reduced file size because the transparency channel dominates, so the size
  of the image was the useful lever. 960 was chosen over 840 because 840 would be enlarged about 8% on standard
  desktop screens. Front lettering, rear, rubber texture and a blended pair are in
  `qa/screenshots/v9/asset-compare-graphite.png`.
- **The website, before vs after:** `scripts/qa_visual_compare.py` screenshots the live viewer for Graphite and
  Ember at the front, side, rear and mid-blend, on desktop and at phone size. The difference is 35–42 dB PSNR,
  mean 0.6–1.3 levels out of 255: framing, colour, shadow and lettering are the same, and the remaining
  difference is sub-pixel resampling. Sheet: `qa/screenshots/v9/compare-sheet.png`; pairs:
  `qa/screenshots/v9/compare-*.png`.

## Checks run (all on this computer, headless Chromium)

- `npm run build`: clean.
- `scripts/qa_interactions.py` (production build): **60/60**. It covers reduced motion, `?static`, keyboard,
  touch, the cart and console errors.
- `scripts/qa_turntable_loading.py` (dev server, StrictMode): **25/25**, after one deliberate update: no
  turntable file may load while the viewer is far below, where the previous check expected only the placeholder
  still.
- `scripts/qa_cache.py`, new: **42/42** on both the production build and the dev server (StrictMode). It checks:
  - the journey and turntable budgets hold through fast and slow scrolling, flicks, keyboard turns past zero
    (angle wrapping), finish switches and a viewport resize;
  - the journey releases its frames off screen and re-decodes on return;
  - the opening journey frame being blocked (the journey still appears, from its neighbouring frame);
  - the turntable's first frame being blocked, with slow loading and rapid finish switches;
  - deep links: `/#configure` and `/#stage-2` open at that section (desktop, phone size, reduced motion), and a reload keeps the browser's restored position.
- `scripts/qa_screens.py` → `qa/screenshots/v9/`: no horizontal overflow and no errors on desktop or phone size.

## Still to check on a real phone

None of these can be established on this computer:
- scrolling feel and frame pacing of the journey on iOS Safari and Android Chrome;
- turntable rotation and flicks with a finger;
- finish switching;
- memory pressure: whether iOS discards the tab or canvas memory on a 3–4 GB phone;
- a page reload mid-scroll;
- loading over real mobile data;
- touch scrolling through the sticky journey.

This needs a hosted preview: a `localhost` address on the computer cannot be opened from a phone. Nothing has been
hosted yet.

The platform's orange rim was not changed. That needs a lighting change re-rendered consistently across all 145
frames of both journeys, plus a frame verified first, and it was optional in the brief.

## Journey frame pass (193 planned frames)

24 November 2026, after the background render finished (GPU idle). Raw results: `qa/perf/journey-<label>.json`
(`scripts/perf_journey.py`). "old" is the previous build with 145 frames (`work/dist-v1`); "new" is the current
build. Both ran in headless Chromium on this computer, interleaved, under the same conditions.

**Frames** (`work/journey_ghost.py`, mean absolute difference 0–255):

| set | largest step | mean step | worst cross-fade error | mean cross-fade error |
| --- | --- | --- | --- | --- |
| desktop-s, old 145 | 11.16 | 6.20 | 7.98 | 4.45 |
| desktop-s, new 193 | 6.56 | 5.39 | 4.44 | 3.73 |
| phone, old 145 | 18.47 | 8.68 | 15.10 | 6.42 |
| phone, new 193 | 8.39 | 7.13 | 5.91 | 4.77 |

**Scrolling** ("misses": animation frames that showed the nearest decoded frame because the needed pair was not
decoded yet; "slow": animation frames over 25 ms):

| scenario | old misses | old slow | new misses | new slow |
| --- | --- | --- | --- | --- |
| desktop 1440×900, steady | 0 / 267 | 0 | 0 / 262 | 0 |
| desktop 1440×900, fast | 76 / 107 | 13 | 0 / 121 | 0 |
| desktop 1920×1080, steady | 0 / 343 | 0 | 43 / 296 | 0 |
| desktop 1920×1080, fast | 43 / 132 | 1 | 94 / 130 | 0 |
| phone size, steady | 0 / 288 | 0 | 0–24 / 288 | 9–18 |
| phone size, fast | 2–11 / 125 | 2–13 | ~90 / 122 | 17–22 |

Outcome: the 1440×900 desktop journey is clearly smoother. At 1920×1080 and phone size the new set asks for up to
1.8× more decodes per scroll distance in its busiest segments, and this computer's software canvas does not keep up
on fast scrolls. Because neighbouring frames are now much closer, a miss shows a smaller jump than before.

Tried and not kept (same frames, same conditions): unlimited parallel decodes (phone fast misses 16 but slow frames
38); the old symmetric ±8/±10 window (slow frames 15–38); a cap of 10 (no better); decoding without the resize step
(slow frames 59, as the canvas then scales every draw). Removing the new Why ARC section made no difference. The
current settings (direction-weighted window, six decodes at a time) had the fewest slow frames on desktop.
Physical-phone measurements are still needed before tuning phone decoding further.
