# Changelog

## 0.1.0 (July 2026)

- Initial release.
- Duplicate a Dataset, Image, or Project (or a comma-separated list of
  IDs) from a form in OMERO.web, with a dry-run preview.
- Friendly handling of the Fileset-conflict case: looks up sibling
  Image IDs and tells the user what to enter instead of surfacing a
  raw `graph-fail` error.
- "Open with Duplicator" support: pre-fills Type/ID from the
  webclient tree's current selection, opens in a new tab.
