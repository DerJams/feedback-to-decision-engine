# Opportunity Brief - SoundCloud Android

_Generated 2026-06-20 from 3,000 app store reviews (2,927 English after filter, 1,387 issues extracted, 90 clusters, 21 ranked themes above size 10)._

## Headline

Two findings, and they do not agree:

- **Prevalence:** `excessive ads` is the single most-mentioned complaint by a wide margin - **208 reviews** raise it, the next-largest theme is roughly 70% as common.
- **Priority:** when reach is combined with severity and strategic fit, `playback pauses during songs` ranks **#1**, and `excessive ads` drops to **#3**.

Why the divergence is the headline insight: reviewers complain about ads more often than anything else, but they describe ads as repeated friction ("medium" severity), not as something that breaks the product. Playback pauses and country-availability gaps appear less often but reviewers describe them at higher severity and they hit core_listening - the part of SoundCloud that actually has to work. Acting on ad load is also a lower-confidence opportunity (see the strategic_fit rationale in `config/weights.yaml`): reducing ads is a direct revenue lever, not a defect fix, and the retention gains it might produce are hard to attribute. So the brief reads the way a priorities argument actually goes in a room: yes, ads are the loudest complaint; no, ads are not the highest-leverage thing to do this quarter.

## Method & limitations

Extraction uses Anthropic `claude-haiku-4-5` against a neutral schema (no specific complaints named in the prompt, so themes surface from reviewer language). Clustering is local: sentence-transformers embeddings, sentiment-partitioned agglomerative at cosine threshold 0.45, medoid labels. Scoring weights are auditable - frequency 0.4, severity 0.4, strategic_fit 0.2; per-feature-area fit values and the severity scale live in `config/weights.yaml`. Frequency is log-scaled so the heavy-tailed size distribution does not collapse mid-tier themes to near-zero. Volume floor: clusters with fewer than 10 issues are excluded from this ranked output.

**Limitations.** A single similarity threshold cannot fit every concept's natural granularity. A few low-rank clusters - notably theme 13 (_same songs repeat frequently_) and theme 18 (_missing original artist information_) - blend two related but directionally different concerns ("songs auto-repeating" vs. "can't manually repeat"; missing metadata vs. obscure-artist catalog complaints). A centroid_sim display floor (0.82) drops the worst off-theme quotes from the render, but cannot rewrite the cluster boundary itself - so a residual quote that leans the other direction may still surface in those two blocks.

## Ranked opportunities

### 1. playback pauses during songs - score 0.895

**Reach:** 72 reviews &nbsp;|&nbsp; **Mean severity:** 2.81 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** core_listening x72

**Score breakdown:** freq +0.321 | severity +0.374 | fit +0.200

> "Constantly pausing in the middle of songs" - review `09c43170-988c-43d6-b7e0-d0c7982bc80a` (1★)
>
> "U cannot even listen to a single song anymore...it will stop randomly..just so u buy premium and it will not stop anymore...from the best music FREE app, it became the WORST MUSIC PAID APP...do not install" - review `168a9227-c19e-45f4-bfa0-5ae8b8103172` (1★)
>
> "I like it but every time I try to listen to music now after the last update it keeps skipping" - review `2d9614f2-5643-4d42-a384-0efa78b5f940` (1★)

**What I'd do:** Instrument session-level playback events (buffer stalls, decoder errors, route changes) and correlate with device, OS, and network to isolate the top contributor before shipping a fix.

### 2. songs unavailable in user's country - score 0.875

**Reach:** 147 reviews &nbsp;|&nbsp; **Mean severity:** 2.41 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** core_listening x93, discovery x44

**Score breakdown:** freq +0.374 | severity +0.322 | fit +0.179

> "Many songs aren't available in my country" - review `8770fe52-2d02-4dea-ac43-8f2af39dab04` (4★)
>
> "it's says songs not available on your country" - review `e7a3930a-8637-4af4-8c40-8def8e9c874d` (1★)
>
> "every time I wanna play a song it keeps saying not available in your country" - review `dbc9e582-5fe7-40a6-bda5-6dbb1a471a83` (1★)

**What I'd do:** Replace the silent dead-end with clear regional-availability messaging at the moment of attempted play, plus an inline "similar available now" recommendation row to redirect the session.

### 3. excessive ads - score 0.837

**Reach:** 208 reviews &nbsp;|&nbsp; **Mean severity:** 2.46 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** monetization x186, core_listening x19

**Score breakdown:** freq +0.400 | severity +0.328 | fit +0.109

> "because all u do is give ads u fool" - review `aa95b04e-18af-4b8f-8f17-fdd23df6897d` (1★)
>
> "sooooo much adds but tellax is crazy 🤪" - review `f8603647-bc0c-4cee-b160-b83608a12f03` (5★)
>
> "a lot of ads, but it works really well!" - review `c336c478-ee10-485e-99d0-4bef9ab1712a` (4★)

**What I'd do:** Run a controlled experiment on slightly reduced ad load for long-tenured free users (e.g. >90 days retained), measuring net revenue including any uplift in premium conversion. Do not change ad load without that test.

### 4. offline playback unavailable - score 0.805

**Reach:** 37 reviews &nbsp;|&nbsp; **Mean severity:** 2.59 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** core_listening x32, monetization x5

**Score breakdown:** freq +0.272 | severity +0.346 | fit +0.186

> "my playlist song is not play without internet that not fair please without internet play my music thank you" - review `ba52820c-ee0e-477b-9552-e87058120e4d` (3★)
>
> "Why does the music can't play when offline anymore? And even after updating, you need to be online to play the music, and also the memory data keeps on stacking, WHY?" - review `81d2f0ff-31f9-4d35-aba8-85bff6541a48` (1★)
>
> "it not allow songs to play offline as Spotify do it mostly don't contain latest songs available it contains copies improve if kindly" - review `23caef52-da26-4c6f-89cb-47c481c578a8` (3★)

**What I'd do:** Audit failed-download attempts to separate rights-flagged tracks from cache/storage failures; ship the dominant pattern's fix and surface the rights case as a clear in-app message.

### 5. playlist not playing - score 0.795

**Reach:** 33 reviews &nbsp;|&nbsp; **Mean severity:** 2.67 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** core_listening x23, discovery x5

**Score breakdown:** freq +0.264 | severity +0.356 | fit +0.176

> "it's amazing sometimes my Spotify playlist of 15 hours deletes so if I put it here it does not truly recommend it is not that pay and ads stuff I love it" - review `027b4a3f-ad3d-4707-be11-1c5147f2ef6e` (4★)
>
> "trash , junk app, when I play songs from my likes playlist, it automatically switch to other playlists playing songs I don't want to hear, over and over again, what a junk , even though I tapped on my likes playlist several times, it still..." - review `71979c79-08d1-4e9b-a0b6-83f1ecd4b027` (1★)

**What I'd do:** Likely shares root cause with playback pauses; bundle both into a single playback-reliability workstream and instrument the two surfaces together.

### 6. app crashes - score 0.786

**Reach:** 72 reviews &nbsp;|&nbsp; **Mean severity:** 2.81 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** other x56, core_listening x15

**Score breakdown:** freq +0.321 | severity +0.374 | fit +0.091

> "I changed my five star to 1 star review because you keep blocking IP addresses and app crashes constantly so I can no longer use your platform 👏👏👏🙄👍" - review `7c05cc2b-a67c-41d7-ad45-86a964af2726` (1★)
>
> "zero stars. Terrible now. Was good a decade ago. All my liked songs got deleted. any good experice is overpriced. crashes constantly. Recover my liked songs @soundcloud !" - review `d069507f-d182-41e0-8527-2a7caa617541` (1★)
>
> "crashes constantly. and they recently updated the android auto app to a single sine wave track slider that really messes with my brain (being an engineer). the primary button placement and solid fill was a good call, though" - review `6b202108-9d1e-4ec0-9094-1e1b035206fc` (1★)

**What I'd do:** Pull Crashlytics top stack signatures by OS / device combo and fix the three with the highest crashes-per-DAU. Standard work, but unblocks every other theme above it.

### 7. liked songs disappearing from playlist - score 0.779

**Reach:** 24 reviews &nbsp;|&nbsp; **Mean severity:** 2.71 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** core_listening x18, account x4

**Score breakdown:** freq +0.241 | severity +0.361 | fit +0.177

> "It keeps removing my liked songs bru, hundreds at a time ts pmo" - review `757868b0-5abd-4da3-a4e0-62f46caf2a51` (2★)
>
> "sound cloud have removed all my likes songs 🎵" - review `f343378e-96e4-428d-9681-cae7556a997a` (1★)
>
> "I'm not sure if this is a bug but when I was liking songs the songs wouldn't appear in the list for some reason... great app though! 24/3/26 update I came back to SoundCloud but the log in won't work and the help center is useless. I can't..." - review `249ba095-da91-4e3d-9b21-72e147fc34f2` (1★)

**What I'd do:** Separate rights-removal (track left the catalog) from data-loss (sync bug). Harden the sync flow if data-loss; add a visible "no longer available" marker if rights, so users aren't blindsided.

### 8. sign in or login fails - score 0.755

**Reach:** 42 reviews &nbsp;|&nbsp; **Mean severity:** 2.95 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** account x42

**Score breakdown:** freq +0.282 | severity +0.394 | fit +0.080

> "doesn't let me sign in or login" - review `02884e3b-a114-4ea9-ac1a-94dadd956a26` (1★)
>
> "can't sign into my account, says it's lost. quite frustrating! won't let me sign in with Facebook either, as I have used this for years!" - review `9a0d4ff4-9f25-4c9b-90a0-83d2424ee32c` (1★)
>
> "abandoned app. impossible to login." - review `0f7f21af-df6b-4068-a0da-1d33f3a410ec` (1★)

**What I'd do:** Segment auth-funnel telemetry by provider (Google / Apple / email) and OS version. The cluster size suggests one provider regressed recently.

### 9. missing download feature - score 0.748

**Reach:** 29 reviews &nbsp;|&nbsp; **Mean severity:** 2.52 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** core_listening x18, monetization x8

**Score breakdown:** freq +0.255 | severity +0.336 | fit +0.158

> "we should be able to download songs" - review `afcbd711-bee5-4106-88d6-a2d058485ee0` (1★)
>
> "if only I could download from this app" - review `a0d51b3e-0842-4d77-885b-5b5485909991` (3★)
>
> "I love it but why can't I Download a song on it" - review `c2f85ffe-62e5-4958-906e-5be87574ffbc` (5★)

**What I'd do:** Split complaints by tier. Free users asking for downloads = paywall-expectation issue (better premium-badging); premium users asking = feature exists but isn't discoverable enough.

### 10. songs behind premium paywall - score 0.745

**Reach:** 36 reviews &nbsp;|&nbsp; **Mean severity:** 2.64 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** monetization x27, core_listening x7

**Score breakdown:** freq +0.270 | severity +0.352 | fit +0.123

> "500× better than spotify just wish so many songs werent behind premium" - review `e89f6acc-c2c8-40b9-91ce-470df7ac68f7` (5★)
>
> "SoundCloud is better than YouTube music and Spotify but I have three complaints,why do some songs require me to have SoundCloud Go+ and my songs keep stopping for no reason and the ads are so annoying,I get you need money but it's very ann..." - review `2333a079-c28e-44f5-9728-70e9b202ad07` (4★)
>
> "some songs you have to pay for" - review `ceb62922-1451-4654-9e60-43cfe2f4eaf5` (4★)

**What I'd do:** Move the premium-only indicator upstream from play attempt to search and browse, so users self-select before hitting a wall - the surprise is the source of the complaint, not the paywall itself.

### 11. subscription cancellation not working - score 0.708

**Reach:** 27 reviews &nbsp;|&nbsp; **Mean severity:** 2.70 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** monetization x18, account x8

**Score breakdown:** freq +0.249 | severity +0.360 | fit +0.098

> "will not let me cancel my subscription to Go despite following every instruction, continuing to charge me against my will" - review `926b44fe-fe2e-4a3b-a6a1-7c2acaafbacf` (1★)
>
> "great app barely any ads unlimited, one issue i cannot cancel my subscription" - review `c28e7985-b879-4e99-abf6-ec245956856d` (3★)
>
> "Imposible to cancel your premium subscription" - review `8060ce22-8a8a-4876-8794-171050c439e3` (1★)

**What I'd do:** Audit the cancel flow end-to-end for steps that aren't legally required (retention prompts, multi-confirmation). Compliance and brand-trust risk make this worth a fast fix.

### 12. sound quality is poor - score 0.701

**Reach:** 11 reviews &nbsp;|&nbsp; **Mean severity:** 2.36 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** core_listening x11

**Score breakdown:** freq +0.186 | severity +0.315 | fit +0.200

> "terrible sound quality and unmoderated volume" - review `cfe34c53-38bd-401e-91db-49a802daceb5` (1★)
>
> "Only good for not having an ad. there's still lot of bugs in app. the sound quality isn't the best. Overall ui looks cheap." - review `e4592229-6abf-4aad-96a4-bf9458fdf2f7` (3★)
>
> "average app. too expensive. poor sound quality" - review `5f138a8a-d92d-4667-a030-74533df4b408` (3★)

**What I'd do:** Correlate complaints with upload bitrate, network conditions, and device audio output. High strategic fit but ambiguous root cause - diagnose before prescribing.

### 13. same songs repeat frequently - score 0.696

**Reach:** 14 reviews &nbsp;|&nbsp; **Mean severity:** 2.29 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** core_listening x10, discovery x4

**Score breakdown:** freq +0.203 | severity +0.305 | fit +0.189

> "Love this app, it just has a bad habit of repeating the same songs over and over again." - review `aa44f293-314b-4e66-9ce5-073bae440446` (4★)
>
> "you can't repeat the songs. Why is that? if I could listen to a song more than one time I'd give it a five star." - review `6aca5977-e4e5-4b6c-b9dc-a61115e36fef` (4★)

**What I'd do:** Check recommendation-diversity metrics on the personalized queue, especially for free users; the model may be overfitting on a narrow signal (recent likes? short history?).

### 14. app performance degradation over time - score 0.688

**Reach:** 27 reviews &nbsp;|&nbsp; **Mean severity:** 2.63 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** other x21, core_listening x5

**Score breakdown:** freq +0.249 | severity +0.351 | fit +0.087

> "bloated mess of an app I remember this running fine years ago but it's totally a mess. compared to youtube music this thing seriously chugs and stutters just doing menial things as you play a song. it's a great platform to find indie music..." - review `30fd3eb8-3e93-4544-bc68-d68dd9037893` (2★)
>
> "all went down hill when Spotify bought them. app is buggy outdated and not worth the extra cost they added to Go and Go+ which I have payed for for about half a year. honestly a shame and the devs need to actually be payed to fix the app" - review `0a6de76b-3952-4c07-a21e-1ae2bbc3c96b` (1★)
>
> "This app lags so much it's mad annoying" - review `7354ec38-a262-4ad5-a33d-a7f430bae1fb` (2★)

**What I'd do:** Profile memory and cache behavior over long-running sessions and across cold starts. Classic leak / cache-bloat shape worth ruling out first.

### 15. account creation fails - score 0.666

**Reach:** 11 reviews &nbsp;|&nbsp; **Mean severity:** 3.00 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** account x11

**Score breakdown:** freq +0.186 | severity +0.400 | fit +0.080

> "Tried everything to create an account and I also sent a message for help. After 20 minutes of trying everything I couldn't open an account and did not receive any feed back." - review `356fa6fd-20e6-4aa8-ba70-304d7d0d62aa` (1★)
>
> "Unable to create an account. An error kept on popping up. Uninstalled." - review `86788d7f-4a65-4867-b366-a13851972d9f` (1★)
>
> "can't even create an account EVERY EMAIL I USE the app says the same thing (Something unexpected happened try again later) I've tried for a week and it done this several times different emails (yes I have multiple) I really like this app l..." - review `3f5aaf4b-de28-437b-a1cd-208a6715d713` (1★)

**What I'd do:** Audit signup conversion by referrer, provider, and OS version. New-user failure is disproportionately costly to growth, so worth a dedicated review.

### 16. low quality songs in catalog - score 0.664

**Reach:** 13 reviews &nbsp;|&nbsp; **Mean severity:** 2.31 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** discovery x6, core_listening x4

**Score breakdown:** freq +0.198 | severity +0.308 | fit +0.158

> "only duplicates and low quality songs available 🫤" - review `a1f66aba-848f-4215-a7e3-c454fc1c43e7` (1★)

**What I'd do:** Catalog quality is largely outside the app team's lane (rights, labels, creators). Flag to content/partnerships rather than treating as a product defect.

### 17. customer support unresponsive to concerns - score 0.642

**Reach:** 13 reviews &nbsp;|&nbsp; **Mean severity:** 2.85 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** other x10, account x3

**Score breakdown:** freq +0.198 | severity +0.379 | fit +0.065

> "used to be a fan. I have snippets and tracks uploaded from the 2010s. when I tried recently to download MY TRACKS THAT I CREATED, they hit me with the new subscription paywall. I tried talking to someone and got nowhere. I deleted the app..." - review `aa6fdb88-398a-44cc-b164-39533dba29e8` (2★)
>
> "Tried everything to create an account and I also sent a message for help. After 20 minutes of trying everything I couldn't open an account and did not receive any feed back." - review `356fa6fd-20e6-4aa8-ba70-304d7d0d62aa` (1★)

**What I'd do:** Sample these reviews into the support team's QA queue; the action is operational (response SLA, routing), not a product change.

### 18. missing original artist information - score 0.631

**Reach:** 13 reviews &nbsp;|&nbsp; **Mean severity:** 2.15 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** discovery x11, account x1

**Score breakdown:** freq +0.198 | severity +0.287 | fit +0.146

> "good app but lack of original artist and need a feature - sleep timer" - review `75d4d08d-5263-47af-8be4-6d15665c46ed` (3★)

**What I'd do:** Audit metadata coverage on the most-played long-tail tracks; if the gap is user-uploaded content, add an artist-tag prompt at upload to push correction upstream.

### 19. price increase - score 0.629

**Reach:** 16 reviews &nbsp;|&nbsp; **Mean severity:** 2.38 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** monetization x16

**Score breakdown:** freq +0.212 | severity +0.317 | fit +0.100

> "another price increase? ridiculous" - review `2a998935-2000-4173-8a43-5c16d43bef73` (1★)
>
> "was a five star app, now with every update it just gets worse and worse connectivity issues, GUI issues, crashing issues I'm on a flagship phone (Samsung) been a loyal customer for a long time and I hate this app more and more with each up..." - review `c24019b6-c480-4f29-a556-d34674989357` (2★)
>
> "If your going to keep raising prices. Let's at least make the app better because the platform has always been horrible! but theres amazing music on there!" - review `14ec2198-c0bc-4336-b234-2abdc06bd6ae` (1★)

**What I'd do:** Watch retention by cohort post-increase. Price is a strategy call, not a product fix; the brief's job is to surface that the complaint exists and is growing.

### 20. lack of support for paid features - score 0.614

**Reach:** 10 reviews &nbsp;|&nbsp; **Mean severity:** 2.60 / 3.00 &nbsp;|&nbsp; **Sentiment:** negative &nbsp;|&nbsp; **Feature areas:** monetization x7, other x3

**Score breakdown:** freq +0.180 | severity +0.347 | fit +0.088

_No quote met the length / severity filter and the centroid_sim floor (0.82). The cluster is real signal but does not contain a sharp, on-theme review to quote._

**What I'd do:** Triage premium-tier support tickets separately; paying users hitting friction is a higher-cost churn signal than free-tier complaints. Tighten the SLA on this segment.

### 21. absence of ads - score 0.426

**Reach:** 10 reviews &nbsp;|&nbsp; **Mean severity:** 1.10 / 3.00 &nbsp;|&nbsp; **Sentiment:** positive &nbsp;|&nbsp; **Feature areas:** monetization x10

**Score breakdown:** freq +0.180 | severity +0.147 | fit +0.100

> "its unbelievable,no ads at all" - review `86ce0114-c53b-43ed-90f6-e8a3855b6aeb` (5★)
>
> "this app is the goat, it doesn't have are for every 1 song or everytime I skip a song" - review `fd957765-beb6-409c-8e29-6c1be5f156d5` (5★)

**What I'd do:** Positive-signal cluster (subscriber praise). Not an action item - useful as marketing/retention proof that the premium tier delivers on its core promise.

---

_Generated by the local pipeline. All quotes verbatim from `data/extracted_issues.jsonl`; the review_id values trace back to the original Google Play scrape in `data/soundcloud_reviews.jsonl`._
