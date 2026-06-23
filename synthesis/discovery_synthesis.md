# SoundCloud mobile - discovery synthesis

_Early discovery, June 2026. Data: public App Store + Google Play reviews, 90-day lookback (2026-03-23 to 2026-06-20)._

## What this is, and what it isn't

This is early discovery on the SoundCloud mobile app, drawn entirely from **public app-store reviews** on iOS and Android over a ~90-day window. It's intended to point a mobile update at the right problems - **not** to size opportunities or prescribe fixes. App-store reviewers self-select to the extremes (the angry and the delighted), so the pain signal is **directional, not representative of the user base.** There are no internal tickets, no product telemetry, and no NPS / survey overlay in this corpus.

## How to read this

The pipeline is: scrape reviews -> per-review LLM issue extraction -> local sentence-embedding clustering of issue themes -> transparent scoring. The score is a documented weighted sum (`0.40 * normalized_frequency + 0.40 * normalized_severity + 0.20 * strategic_fit`); the `strategic_fit` weights live in [`config/weights.yaml`](../config/weights.yaml) with a one-line rationale for each value. **The ranking is contestable by design** - if a number looks wrong, the weight that produced it is one file away. See [`evals/results.md`](../evals/results.md) for the extraction validation against a hand-labeled gold set.

## Validation

Extraction quality was measured before any synthesis was written:

- **Review-level detection: 94%** (45 / 48); **0 missed reviews**, **3 false positives** flagged on benign text.
- **Feature_area accuracy: 57% strict / 83% hierarchical (same parent).** The strict-vs-hierarchical gap is driven by reviews whose original gold label was bucketed as `other` / "App functionality" before the taxonomy added `stability` and `downloads`; the model resolved many of those to the finer categories.
- Gold set size = 50; intersection with the current extraction = 48 (2 reviews aged out of the 90-day window between labeling and the latest ingest).

Headline read: detection is reliable, hierarchical categorization is reliable, strict categorization is where the model and gold disagree most - and that disagreement traces to a known schema improvement, not extraction noise.

## Headline finding: the loudest complaint is not the top product bet

The most-mentioned theme is **not** the highest-priority theme under any sensible weighting.

| Rank | By prevalence (raw size) | | By priority (score) |
|---:|---|---|---|
| 1  | **excessive ads** (316 mentions) | -> | **app crashes** (0.901) |
| 2  | app crashes (101) | -> | playback stops unexpectedly (0.869) |
| 3  | missing songs in catalog (92) | -> | songs unavailable in some countries (0.857) |
| 4  | songs unavailable in some countries (87) | -> | **excessive ads** (0.828) |
| 5  | playback stops unexpectedly (66) | -> | missing songs in catalog (0.804) |
| 6  | playlists disappearing (52) | -> | playlists disappearing (0.789) |
| 7  | login failure (49) | -> | offline playback unavailable (0.781) |
| 8  | subscription cost too high (41) | -> | login failure (0.746) |
| 9  | offline playback unavailable (36) | -> | poor audio quality (0.736) |
| 10 | paywall on songs (36) | -> | download functionality unavailable (0.734) |
| 11 | app quality (30) | -> | app performance issues (0.730) |
| 12 | pricing increase (26) | -> | regional content restrictions (0.726) |

`excessive ads` is mentioned **3.1x more often than the next theme** (316 vs 101) but ranks **#4 on priority**. Two things pull it down:

1. **Severity skews medium, not high** (mean severity 2.40 / 3.0 vs 2.87 for `app crashes`). Reviewers complain about ads loudly, but few say it's an unusable-app blocker the way a crash does.
2. **`monetization` has a deliberately discounted strategic_fit of 0.50.** The [rationale in `weights.yaml`](../config/weights.yaml) is explicit: ad-load is a direct revenue lever, not a defect, so even a top-reach monetization theme is a lower-confidence opportunity to act on - the reach is real but the recommended action is not obvious.

**Both of those are reader-contestable.** Raise the monetization fit or change the severity weighting and ads will climb. The point of this section is not "don't address ads" - it's that volume alone shouldn't decide a product bet, and the scoring makes the trade explicit.

## Schema-gap finding: the top priority used to be invisible

The previous extraction schema had no `stability` or `downloads` feature_area; reviews like "keeps crashing and overheating my phone" or "can't download song" were bucketed as `other` / "App functionality" and dissolved into a heterogeneous catch-all. With those two enums added:

- **`app crashes` is now the #1 priority theme overall** (score 0.901, size 101, 97% `stability`). It would previously have been split across `core_listening` (playback complaints) and `other` (generic "app broken").
- **4 of the top 11 priority themes are stability or downloads** that the expanded taxonomy surfaced: `app crashes` (#1, stability), `offline playback unavailable` (#7, downloads), `download functionality unavailable` (#10, downloads), `app performance issues` (#11, stability).
- Corpus-wide, `other` fell from **19.4% -> 15.2%** of all extracted issues; `stability` + `downloads` together now capture **17.3%**.

This was validated, not just asserted: the [eval's hierarchical feature_area accuracy of 83%](../evals/results.md) confirms that the cases where strict accuracy drops are exactly the `other` -> `stability` / `downloads` re-resolutions, not random misclassifications.

## Top opportunities (top 7 by priority score)

Each row's score is `0.40 * freq_norm + 0.40 * sev_norm + 0.20 * strategic_fit`. The three numbers underneath are the per-component contributions - they sum to the score.

---

### #1 - `app crashes`  (score 0.901, size 101)

- **freq** 0.80 → +0.321  |  **sev** mean 2.87 → +0.383  |  **fit** 0.99 → +0.197
- feature_areas: stability 98 · core_listening 1 · other 2
- platform: android 80 · ios 21

> "the app keeps crashing"
> — Android, 1★

> "keeps crashing and overheating my phone"
> — Android, 3★

> "I changed my five star to 1 star review because you keep blocking IP addresses and app crashes constantly so I can no longer use your platform"
> — Android, 1★

---

### #2 - `playback stops unexpectedly`  (score 0.869, size 66)

- **freq** 0.73 → +0.292  |  **sev** mean 2.83 → +0.378  |  **fit** 1.00 → +0.199
- feature_areas: core_listening 55 · stability 10 · downloads 1
- platform: android 58 · ios 8

> "always stops, after one or two track it plays whatever it wants.... And the f ing advertisment!!!!"
> — Android, 1★

> "U cannot even listen to a single song anymore...it will stop randomly..just so u buy premium and it will not stop anymore...from the best music FREE app, it became the WORST MUSIC PAID APP...do not install"
> — Android, 1★

> "Ever since they started making money from ads, the app doesn't work as expected anymore. Full of bugs! Will stop playing randomly and it's a pain to make it start playing again."
> — iOS, 1★

---

### #3 - `songs unavailable in some countries`  (score 0.857, size 87)

- **freq** 0.78 → +0.311  |  **sev** mean 2.71 → +0.362  |  **fit** 0.92 → +0.185
- feature_areas: core_listening 65 · downloads 11 · discovery 4 · other 3 · monetization 2 · account 1 · stability 1
- platform: android 74 · ios 13

> "some songs aren't available :("
> — Android, 4★

> "it would be pretty great if all songs would be available in all countries"
> — Android, 4★

> "good app but recent april update suddenly pause playing song. and some more glitch happen. 2 star deducted for country unavailable many song."
> — Android, 3★

---

### #4 - `excessive ads`  (score 0.828, size 316)

- **freq** 1.00 → +0.400  |  **sev** mean 2.40 → +0.319  |  **fit** 0.54 → +0.108
- feature_areas: monetization 272 · core_listening 26 · other 12 · stability 5 · social 1
- platform: android 194 · ios 122

> "too much ads :/"
> — Android, 3★

> "not even YouTube has this many ads"
> — Android, 2★

> "too many ads but overall nice app. would recommend but not entirely, copyrighted songs cannot be found here which is a bummer but as I said, overall nice app and listening to music here is just nice and chill."
> — Android, 4★

---

### #5 - `missing songs in catalog`  (score 0.804, size 92)

- **freq** 0.79 → +0.315  |  **sev** mean 2.37 → +0.316  |  **fit** 0.87 → +0.174
- feature_areas: core_listening 42 · discovery 41 · downloads 4 · other 3 · monetization 2
- platform: android 67 · ios 25

> "you have songs s**** supply does not have"
> — Android, 5★

> "No ads🔥🔥. Just like YT music Premium but better but some songs are not there still AWESOME app."
> — Android, 5★

> "The songs l look for are not there or some from Spotify there is soo many songs for example if l search for songs they are many of them 😔 l thought l would enjoy using this app but never mind"
> — Android, 3★

(Note: this cluster spans related catalog-completeness sub-themes - "incomplete music catalog", "missing lyrics feature", "liked songs disappeared". Surfaced as one theme rather than over-split; see Limitations.)

---

### #6 - `playlists disappearing`  (score 0.789, size 52)

- **freq** 0.69 → +0.276  |  **sev** mean 2.48 → +0.331  |  **fit** 0.91 → +0.183
- feature_areas: core_listening 33 · discovery 9 · downloads 4 · stability 3 · other 2 · monetization 1
- platform: android 33 · ios 19

> "I spend hours playing songs next and building my list because I want yall to erase it randomly"
> — iOS, 1★

> "I've been using sound cloud more often but things have 100% changed. My sounds keep getting deleted from playlists and not like there getting deleted from SoundCloud like there just vanishing from my playlist and I have to keep adding them. Also half the songs that r popular r on go+ so just use Spotify atp"
> — iOS, 2★

> "Love sound cloud however, I wish I could find a playlist with total dopamine fix and wish it could introduce more music without me having to search search search"
> — iOS, 5★

---

### #7 - `offline playback unavailable`  (score 0.781, size 36)

- **freq** 0.63 → +0.251  |  **sev** mean 2.78 → +0.370  |  **fit** 0.80 → +0.160
- feature_areas: downloads 36 _(100%)_
- platform: android 26 · ios 10

> "I really wish i would be able to listen to music when I go out of service"
> — iOS, 5★

> "without net why it's not playing 🤡😔"
> — Android, 1★

> "Paid 6 bucks for offline use and offline its no use. Will not be wasting anymore money. Seems this the case with everything after 2019. 3 days later STOLE MY MONEY AND CANT USE OFFLINE AT ALL. REFUND? LOL NOPE."
> — Android, 1★

## iOS vs Android - per-theme share (matched US-only window)

A naïve all-reviews comparison here would confound platform with country: Android in this corpus is 100% US, while iOS is multi-country (us, gb, ca, au) because the iTunes RSS feed caps per `(app, country)`. The only way to compare platforms cleanly is to restrict both sides to US users on the date range where both platforms have data.

**Matched window: 2026-06-03 → 2026-06-20 (17 days, US only)** - the iOS-US slice is the limiting side.

| Platform | Reviews (matched) | Extracted issues (matched) |
|---|---:|---:|
| Android (US) | 703 | 318 |
| iOS (US)     | 475 | 180 |

Each theme's share = (members from that platform within the matched window) / (that platform's total extracted issues in the matched window). Columns are comparable.

| Rank | Theme | A. share | iOS share | Skew |
|---:|---|---:|---:|---|
| 1  | app crashes | 5.35% (17) | 5.00% (9) | ~ even (Android 1.1x) |
| 2  | playback stops unexpectedly | 5.03% (16) | 1.11% (2) | **Android 4.5x** |
| 3  | songs unavailable in some countries | 6.29% (20) | 3.33% (6) | Android 1.9x |
| 4  | excessive ads | 15.41% (49) | 26.67% (48) | **iOS 1.7x** |
| 5  | missing songs in catalog | 5.66% (18) | 3.33% (6) | Android 1.7x |
| 6  | playlists disappearing | 3.14% (10) | 4.44% (8) | iOS 1.4x |
| 7  | offline playback unavailable | 0.94% (3) | 3.33% (6) | **iOS 3.5x** |
| 8  | login failure | 1.26% (4) | 0.56% (1) | Android 2.3x |
| 9  | poor audio quality | 1.26% (4) | 0.56% (1) | Android 2.3x |
| 10 | download functionality unavailable | 1.57% (5) | 0.56% (1) | Android 2.8x |
| 11 | app performance issues | 1.57% (5) | 0.00% (0) | Android only |
| 12 | regional content restrictions | 1.57% (5) | 0.56% (1) | Android 2.8x |

All twelve top-priority themes had at least 3 members on at least one platform in the matched window; none were dropped for insufficient sample.

**Observations (matched US-only window, descriptive):**

- **`excessive ads` is more represented on iOS than on Android among matched US users** (26.67% vs 15.41% of each platform's issues; iOS 1.7x). This is the largest and most robust cross-platform signal in the matched window - ads are the single most-mentioned theme on both platforms, but they crowd out other complaints on iOS to a greater degree.
- **`playback stops unexpectedly` is strongly more represented on Android** (5.03% vs 1.11%; Android 4.5x), as is `songs unavailable in some countries` (1.9x) and `missing songs in catalog` (1.7x).
- **`offline playback unavailable` is more represented on iOS** in the matched window (3.5x), though the underlying counts are small (6 iOS, 3 Android) - directional only.
- **`app crashes` is near-even between the two platforms among US users in the matched window** (5.35% vs 5.00%). Worth noting because it contradicts what the unmatched-sample view suggested, which is exactly why platform comparisons need to control for country.
- **`app performance issues` and `download functionality unavailable` are Android-only or near-Android-only** in the matched window, but the iOS counts are 0 or 1, so this is a "no signal on iOS in this window" finding rather than a confident asymmetry.

No mechanism (device fragmentation, OS behavior, etc.) is asserted - this dataset can describe where complaints fall, not why.

**Secondary note - full-sample view, as a sanity check:** Across the full 88-day, multi-country sample (Android n=1,330 issues, iOS n=514 issues), the iOS ads skew is **1.6x** vs the matched-window **1.7x** - similar magnitude, so the headline ads finding is robust to the country / window controls rather than an artifact of sampling. Other skews in the full sample (e.g. Android `regional content restrictions` 6.6x, `app performance issues` 3.1x) are larger than in the matched window because the full sample mixes US Android against international iOS, conflating platform and country. The matched window is the primary view above for that reason; the full sample is reported here only to confirm the ads-skew direction.

**Caveat - treat the matched-window table as directional:**

The matched window is clean (US-only on both sides, identical 17-day date range) but **small and short**: 703 Android-US reviews / 475 iOS-US reviews, 17 days, June 2026 only. Several of the per-theme cells in the table are single-digit counts. The comparison is good enough to surface where platforms diverge in *direction* and to spot where the unmatched view was misleading, but it is not enough to size any platform-specific bet. The deliberate next step before a platform-targeted product decision would be a larger matched pull - either a longer iOS-US window or a country-matched non-US pull on both platforms.

## Limitations and method notes

- **Public reviews only.** No internal tickets, no product telemetry, no NPS or survey overlay. App-store reviewers self-select to extremes; this is pain signal, not prevalence in the user base.
- **90-day lookback** (2026-03-23 → 2026-06-20). Themes that come and go faster than that, or that are pre-90-day, will be under-counted or missed.
- **iOS US window cap.** As noted above, iOS US is 17 days deep vs Android 88 days - any US-specific platform comparison is asymmetric.
- **Gold n = 48, not 50.** Two of the 50 hand-labeled gold reviews aged out of the current ingest window between labeling and the latest extraction; intersection scoring is on n = 48. The 2 missing IDs are noted at the top of [`evals/results.md`](../evals/results.md).
- **`strategic_fit` weights are product judgments, not measurements.** Each value in [`config/weights.yaml`](../config/weights.yaml) has a one-line rationale you can disagree with. The ranking inherits whatever priors are encoded there; that's the legibility argument, not a hidden assumption.
- **One mixed-granularity cluster.** `missing songs in catalog` (rank #5, size 92) spans related catalog-completeness sub-themes - "incomplete music catalog", "missing lyrics feature", "liked songs disappeared". The clustering threshold (cosine 0.45) merged them; tightening would fragment the long tail elsewhere. Surfaced as one theme with the sub-themes noted, rather than over-split.
- **This is discovery.** The synthesis surfaces *where* users hurt and ranks themes against an explicit, contestable prior. It does not prescribe fixes, design solutions, or set targets - that's a PRD's job, downstream.
