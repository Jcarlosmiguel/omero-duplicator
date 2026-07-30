# omero-duplicator

An OMERO.web plugin that adds a **Duplicator** page for duplicating a
Dataset, Image, or Project directly from the browser — no CLI
required, no separate login (it uses your existing OMERO.web
session).

Wraps `omero.cmd.Duplicate`, the same server-side operation the
[`omero-cli-duplicate`](https://github.com/ome/omero-cli-duplicate)
CLI plugin uses, behind a simple form: pick a type, enter an ID (or a
comma-separated list of IDs), Preview (dry run) or Duplicate for real.

## Why

The CLI plugin this is built on requires shell access and knowing
OMERO's object-ID/fileset model. This plugin is for users who just
want to click a button in the browser they already use every day.

## Features

- **Preview before committing** — a dry run shows exactly what would
  be duplicated, with no changes made.
- **Fileset conflicts are explained, not just raised.** OMERO refuses
  to duplicate a single Image that shares a Fileset with other Images
  (the same source file produced more than one Image — e.g. a
  multi-series acquisition). Instead of a raw `graph-fail` error, this
  plugin looks up every Image in that Fileset and tells you exactly
  which comma-separated ID list to use instead.
- **"Open with Duplicator"** — select a Project/Dataset/Image (or
  several) in the webclient tree and open it directly with Duplicator;
  the Type and ID field(s) are pre-filled from your selection. Opens
  in a new tab, so the tree/selection you were working from stays
  visible.
- **Cheap on disk.** Duplicating doesn't copy pixel data — OMERO
  hard-links the original files. Duplicating a Dataset/Project
  cascades correctly through its full hierarchy.

## Requirements

- OMERO.web 5.x (developed against `omero-web-standalone:5.32`)
- OMERO.server 5.6.3+ (for `omero.cmd.Duplicate` graph support)
- Python 3.9+

## Installing

Not yet published to PyPI. Install directly from GitHub for now:

```bash
pip install git+https://github.com/Jcarlosmiguel/omero-duplicator.git
```

Register the app and (optionally) a nav-bar link and "Open with"
entry:

```bash
omero config append omero.web.apps '"omero_duplicator"'

omero config append omero.web.ui.top_links '["Duplicator", "omero_duplicator_index", {"title": "Duplicate a Dataset, Image, or Project (opens in a new tab)", "target": "_blank"}]'

omero config append omero.web.open_with '["omero_duplicator", "omero_duplicator_index", {"supported_objects": ["images", "datasets", "projects"], "script_url": "omero_duplicator/openwith.js", "label": "Duplicator"}]'
```

Restart `omero-web`.

If you're running OMERO.web in Docker from a pre-built image (e.g.
`omero-web-standalone`), install the package at image-build time
rather than into a running container, so it survives a redeploy —
add to your `omero-web` image's Dockerfile:

```dockerfile
RUN pip install git+https://github.com/Jcarlosmiguel/omero-duplicator.git
```

### Development install

```bash
git clone https://github.com/Jcarlosmiguel/omero-duplicator.git
pip install -e ./omero-duplicator
```

## Usage

Enter a **Type** (Dataset, Image, or Project) and an **ID**. Multiple
IDs are accepted as a comma-separated list — needed if you're
duplicating several Images that share a Fileset (see Features above).

- **Preview** runs a dry run: no changes are made, just a report of
  what would happen.
- **Duplicate for real** performs the duplication and reports both the
  original ID(s) and the newly created ID(s), e.g.
  `Duplicated Dataset:1 -> new Dataset:10`.

## Known limitations

- No way to give a duplicate a different name at creation time —
  neither this plugin, the CLI plugin, nor the underlying
  `omero.cmd.Duplicate` request supports it. A duplicate keeps its
  source's exact name.
- File *attachments* (separate from pixel data) are fully copied by
  OMERO, not hard-linked — only the pixel data itself benefits from
  the disk-space saving described above.

## License

GNU Affero General Public License v3 (AGPL-3.0) — see [LICENSE](LICENSE).

## Copyright

Copyright (C) 2026 Joao Miguel.
