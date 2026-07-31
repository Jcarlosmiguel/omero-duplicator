# Changelog

## Unreleased

- Added a real test suite (`omero_duplicator/tests/test_views.py`, 29
  tests) - previously had none, which is what let the flake8/rst-lint CI
  failures below go unnoticed for as long as they did.
- Detailed dry-run/duplicate report: shows a grouped breakdown of exactly
  what would be (or was) duplicated - Annotations, ROIs, Fileset, and
  Microscope metadata, with an "Other" catch-all for anything not in those
  categories - instead of just a one-line summary. Each entry shows the
  raw duplicated IDs on hover, so "2 Datasets" is never ambiguous with
  "Dataset with id 2".
- "Skip annotations" and "Skip ROIs" options, for a duplicate that doesn't
  need to carry those along.
- The duplicate submission no longer blocks the request until it
  completes - it now submits the job and returns immediately, and the
  page polls for completion in the background. This avoids the request
  timing out on a real production server for large/slow duplicates, and
  the page now shows a "Duplicating..." status while it's running instead
  of no feedback at all.
- A completed (non-preview) duplicate now links directly to the new
  object(s), instead of just naming their IDs in text.
- The plugin's page no longer extends the full webclient container
  template - it now uses the lighter OMERO.web header/content layout,
  dropping the unused tree/metadata-panel space and their background API
  calls that came with it.
- Removed `"target": "_blank"` from the `open_with` config example in the
  README - kept only as a private preference on my own site, not as part
  of this project's own suggested config.

Suggested by [Tom Boissonnet](https://github.com/Tom-TBT) and
[Will Moore](https://github.com/will-moore) on the
[image.sc forum thread](https://forum.image.sc/t/omero-web-plugin-for-the-duplicator/121966) -
thank you both!

## 0.1.0 (July 2026)

- Initial release.
- Duplicate a Dataset, Image, or Project (or a comma-separated list of
  IDs) from a form in OMERO.web, with a dry-run preview.
- Friendly handling of the Fileset-conflict case: looks up sibling
  Image IDs and tells the user what to enter instead of surfacing a
  raw `graph-fail` error.
- "Open with Duplicator" support: pre-fills Type/ID from the
  webclient tree's current selection, opens in a new tab.
