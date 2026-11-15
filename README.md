# Premierium radio logos

The US radio station logos the Premierium Android TV app shows, built and cleaned here every day by
`.github/workflows/radio-logos.yml`. The box reads everything with no key.

- **Release `radio-logos`**: `radio_logos.tsv.gz` (call sign | band | frequency | logo address, plus a line `=<name>` for each clean copy),
  and the job's caches (`radio_logos_cache.json.gz`, `radio_logos_clean.json.gz`).
- **`logos/`**: the clean see-through copies, `logos/<first 2>/<name>.png`, where `<name>` is the first 16 letters of the SHA-1 of the
  logo's address. A logo that was already see-through, or has a colored ground of its own, has no copy here: the box uses it as it is.
- `build_radio_logos.py` builds the table (Wikipedia first, TuneIn second); `clean_logos.py` takes a plain white ground off a picture;
  `clean_job.py` runs the cleaning over every logo; `fcc_calls.tsv.gz` is a copy of the app's FCC station list.
- `seed/` holds the last table and cache of the old job (on the app's private repo), used once by the first run.

Tests: `python -m unittest test_build_radio_logos test_clean_logos` (needs numpy, pillow and scipy; `test_logos/` holds seven real logos).

The logos belong to their stations; they are copied here only so the app can show them without a white box.
