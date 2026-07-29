# Changelog

## Unreleased

- Detailed dry-run/duplicate report: shows a grouped breakdown of exactly
  what would be (or was) duplicated - Annotations, ROIs, Fileset, and
  Microscope metadata, with an "Other" catch-all for anything not in those
  categories - instead of just a one-line summary.
- "Skip annotations" and "Skip ROIs" options, for a duplicate that doesn't
  need to carry those along.

Both suggested by [Tom Boissonnet](https://github.com/Tom-TBT) on the
[image.sc forum thread](https://forum.image.sc/t/omero-web-plugin-for-the-duplicator/121966) -
thank you!

## 0.1.0 (July 2026)

- Initial release.
- Duplicate a Dataset, Image, or Project (or a comma-separated list of
  IDs) from a form in OMERO.web, with a dry-run preview.
- Friendly handling of the Fileset-conflict case: looks up sibling
  Image IDs and tells the user what to enter instead of surfacing a
  raw `graph-fail` error.
- "Open with Duplicator" support: pre-fills Type/ID from the
  webclient tree's current selection, opens in a new tab.
