# Dataset split — frozen 27 November 2026

The 32-case dataset is split into a development set (20 cases) and a
held-out set (12 cases). The campaign transcripts in
`datasets/campaign/` are a separate slice and are part of neither set.
`datasets/split.json` is the machine-readable source of truth; the
lists below match it.

## Rules from the freeze onward

- Prompt and validator tuning may use ONLY the dev 20.
- The held-out 12 are opened only for final evaluation runs, after the
  configuration is frozen.
- The campaign transcripts are also out of tuning: they are authored,
  run, and reported, never iterated against.

## Disclosure: tuning before the freeze used all 32

This split was frozen after the first build round, and that round's
fixes were driven by failures observed across all 32 cases, not only
the dev 20. The fixes were: offline timing-pattern corrections
(singular units, "this morning" false positives, overlapping matches),
the conditional-pricing discriminator fix, two stopword additions, and
the currency-evidence fallback (the last one driven by a gpt-4o-mini
run over the full set). The held-out numbers in the final report are
therefore not a clean-room measurement, and the report and README say
so. Post-freeze code changes are feature work, not tuning: the
speaker/timestamp proof fields, the provider fallback path, and the
reporting code. None of them was adjusted against held-out or campaign
results.

## Dev set (20)

bakery_sourdough_clean, bike_shop_tuneup_clean, cafe_cake_conditional,
cafe_soup_temporal, cake_wedding_starting_price,
dry_cleaner_suit_missing, electronics_battery_uncertain,
garden_centre_seedlings_uncertain, grocery_eggs_ambiguous,
grocery_milk_confusion, hardware_screws_ambiguous,
optician_frames_missing, pet_store_dogfood_clean,
pharmacy_antihistamine_missing, plumber_callout_contradiction,
salon_timing_contradiction, salon_toner_confusion, shoe_store_temporal,
toy_store_kite_uncertain, tyre_shop_conditional

## Held-out set (12)

bookstore_boxset_ambiguous, florist_delivery_fee_inference,
florist_roses_clean, florist_roses_conditional,
furniture_chair_contradiction, grocery_oatmilk_correction,
hardware_paint_temporal, music_store_strings_missing,
pharmacy_d2d3_confusion, pharmacy_vitamind_uncertain,
salon_balayage_conditional, tyre_shop_contradiction
