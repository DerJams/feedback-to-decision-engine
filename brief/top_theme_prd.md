# PRD (draft): playback pauses during songs

_Draft, 2026-06-20. Source theme: cluster `c_0003`, ranked **#1 of 21** in the current opportunity brief._

## 1. Problem statement

On SoundCloud Android, playback is frequently interrupted mid-song without user input - unprompted pauses, stalls, drops, and unexpected skips. Reviewers describe sessions broken by these interruptions in the part of the product where reliability is non-negotiable - actually listening to music.

## 2. Evidence

- **Reach:** 72 reviews carry this theme (cluster `c_0003`, sentiment negative).
- **Mean severity:** 2.81 / 3.00 (distribution: high=58, medium=14).
- **Feature areas:** core_listening x72 - this cluster is concentrated in core_listening, not spread across surfaces.

**Representative verbatim quotes** (centroid_sim &ge; 0.82, cited by review_id):

> "Constantly pausing in the middle of songs" - review `09c43170-988c-43d6-b7e0-d0c7982bc80a` (1★) _(sim 0.87)_
>
> "U cannot even listen to a single song anymore...it will stop randomly..just so u buy premium and it will not stop anymore...from the best music FREE app, it became the WORST MUSIC PAID APP...do not install" - review `168a9227-c19e-45f4-bfa0-5ae8b8103172` (1★) _(sim 0.86)_
>
> "I like it but every time I try to listen to music now after the last update it keeps skipping" - review `2d9614f2-5643-4d42-a384-0efa78b5f940` (1★) _(sim 0.85)_

## 3. Why now

- **Top weighted score.** Ranks **#1 of 21** at score 0.895 (freq +0.321 | severity +0.374 | fit +0.200). See `config/weights.yaml` for the weight rationale.
- **Sits entirely in core_listening**, the feature area with the highest strategic_fit weight (1.0) - the explicit reasoning in `config/weights.yaml` is that playback IS the product.
- **Prevalence-vs-priority.** `excessive ads` is the most-mentioned theme overall (208 reviews vs. 72 here) but ranks **#3** because reviewers describe it as repeated friction (mean severity 2.46) rather than as something that breaks the product, and its strategic_fit is lower (monetization weight 0.5). Playback reliability is the higher-leverage place to spend this quarter's cycles.

## 4. Goals &amp; success metrics _(DRAFT - all targets TBD with data/eng)_

Candidate metrics to instrument and baseline. No numeric targets are asserted here; each must be set after a baseline read with data and eng.

- **Playback completion rate.** Share of playback sessions that finish the intended track without an unprompted pause/stall event. _Target: TBD (set with data/eng after baseline)._
- **Mean uninterrupted-play minutes per session.** Time between playback start and first unprompted pause/stall. _Target: TBD (set with data/eng after baseline)._
- **Pause-language review mention rate.** Weekly share of new reviews matching playback-pause language (pause / stall / stop / interrupt) - the metric this brief actually surfaces. _Target: TBD (set with data/eng after baseline)._
- **Cluster reach in the next quarterly refresh.** Size of cluster `c_0003` on a re-pulled review set (currently 72 reviews). _Target: TBD (set with data/eng after baseline)._

## 5. Non-goals

**Explicit out of scope** (own clusters; addressed separately):

- `excessive ads` (theme #3) - distinct cluster, distinct driver.
- `songs unavailable in user's country` (theme #2) - rights / geo gating, not playback-engine reliability.
- `sign in or login fails` (theme #8) - auth flow, separate workstream.
- `low quality songs in catalog` (theme #16) and `missing original artist information` (theme #18) - catalog quality, outside the app team's lane.

**(Draft)** overlap clusters that may share root cause and should be re-scoped during discovery rather than carved off here:

- `playlist not playing` (theme #5) - the brief's recommendation already calls out a likely shared root cause; eng discovery should confirm and either bundle or split.
- `app crashes` (theme #6) - distinct symptom, but a crash-induced playback halt may be reported by users as a "pause"; need to disambiguate in instrumentation.

## 6. Solution direction _(DRAFT - hypotheses to investigate, not chosen)_

No solution committed. The cluster's text suggests four hypotheses worth ruling in or out before any design work:

- **(Draft, needs eng discovery)** Network / buffer-triggered stalls. Pauses concentrated under poor connectivity. Reproduce on throttled networks and instrument buffer-underrun events.
- **(Draft, needs eng discovery)** Background / lifecycle pauses. Backgrounding, audio-route change (BT or wired headphone connect / disconnect), or OS interruption mishandled. Reproduce via state transitions on the top device classes.
- **(Draft, needs eng discovery)** Ad-insertion transition artefacts. Mid-roll insertion failing to resume playback cleanly; some "pause" reports may be ad-transition bugs - which would also lower the perceived severity of the `excessive ads` cluster if fixed.
- **(Draft, needs eng discovery)** Decoder / codec edge cases. Specific track formats failing decode mid-play on particular device families.

## 7. Open questions

Questions the review data does not answer; instrumentation or eng input required:

- Are pauses concentrated on specific OS versions, device classes, or markets?
- Do they correlate with ad-insertion points (i.e. is this a transition bug masquerading as a playback bug)?
- Are they whole-session breaks or sub-second micro-stutters? Reviewer language conflates the two.
- What is the relationship to `playlist not playing` (theme #5)? Shared root cause or independent symptoms?
- How does cluster reach trend across review timestamps and app_version bands? (Both fields are in the raw scrape and not yet analyzed.)

---

_Draft PRD, generated locally from `data/scored_themes.jsonl`, `data/clusters.jsonl`, and `data/extracted_issues.jsonl`. All quotes verbatim and cited by review_id; representativeness floor `centroid_sim >= 0.82` applied. See `brief/opportunity_brief.md` for the full ranked set and the Method &amp; limitations note._