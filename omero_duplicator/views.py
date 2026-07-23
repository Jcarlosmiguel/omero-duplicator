#!/usr/bin/env python
#
# Copyright (c) 2026 Joao Miguel.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import re

import omero
import omero.callbacks
import omero.sys
from omeroweb.webclient.decorators import login_required, render_response

# Matches the text OMERO puts in a graph-fail response's `message` when an
# Image can't be duplicated on its own because it shares a Fileset (the same
# source file produced more than one OMERO Image) with others.
FILESET_CONFLICT_RE = re.compile(
    r"within Fileset\[(\d+)\] may not duplicate Image\[(\d+)\] without Image\[(\d+)\] also"
)

VALID_TYPES = ("Dataset", "Image", "Project")


def _get_fileset_image_ids(conn, fileset_id):
    query = "select i.id from Image i where i.fileset.id = :fid"
    params = omero.sys.ParametersI()
    params.addLong("fid", int(fileset_id))
    results = conn.getQueryService().projection(query, params, conn.SERVICE_OPTS)
    return [r[0].val for r in results]


def _submit_duplicate(conn, obj_type, obj_ids, dry_run):
    req = omero.cmd.Duplicate()
    req.targetObjects = {obj_type: obj_ids}
    req.dryRun = dry_run

    handle = conn.c.sf.submit(req)
    cb = omero.callbacks.CmdCallbackI(conn.c, handle)
    try:
        while not cb.block(500):
            pass
        return cb.getResponse()
    finally:
        cb.close(True)


def _extract_new_ids(duplicates, obj_type):
    if not duplicates:
        return []
    for key, ids in duplicates.items():
        if key.endswith(".%s" % obj_type) and ids:
            return list(ids)
    return []


@login_required()
@render_response()
def index(request, conn=None, **kwargs):
    # Pre-fill from an "Open with Duplicator" launch (see
    # static/omero_duplicator/openwith.js), which passes the object(s)
    # selected in the webclient tree as obj_type/obj_id query params.
    context = {"template": "omero_duplicator/index.html"}
    obj_type = request.GET.get("obj_type", "")
    obj_id = request.GET.get("obj_id", "")
    if obj_type in VALID_TYPES:
        context["obj_type"] = obj_type
    if obj_id:
        context["obj_id"] = obj_id
    return context


@login_required()
@render_response()
def run_duplicate(request, conn=None, **kwargs):
    obj_type = request.POST.get("obj_type", "").strip()
    obj_id = request.POST.get("obj_id", "").strip()
    dry_run = request.POST.get("dry_run") == "1"

    context = {
        "template": "omero_duplicator/index.html",
        "obj_type": obj_type,
        "obj_id": obj_id,
        "dry_run": dry_run,
        "submitted": True,
    }

    id_parts = [p.strip() for p in obj_id.split(",") if p.strip()]
    if obj_type not in VALID_TYPES or not id_parts or not all(p.isdigit() for p in id_parts):
        context["error"] = "Please provide a valid type and a numeric ID (or comma-separated IDs)."
        return context
    obj_ids = [int(p) for p in id_parts]

    try:
        rsp = _submit_duplicate(conn, obj_type, obj_ids, dry_run)
    except Exception as exc:
        context["error"] = "Unexpected error talking to OMERO: %s" % exc
        return context

    if isinstance(rsp, omero.cmd.ERR):
        message = getattr(rsp, "message", "") or ""
        conflict = FILESET_CONFLICT_RE.search(message)
        if conflict:
            fileset_id = conflict.group(1)
            sibling_ids = _get_fileset_image_ids(conn, fileset_id)
            if sibling_ids:
                context["error"] = (
                    "This slide is part of a group of %d related images stored "
                    "together (the same original file produced all of them). "
                    "OMERO requires duplicating them together. Set Type to Image "
                    "and enter this as the ID: %s"
                    % (len(sibling_ids), ",".join(str(i) for i in sibling_ids))
                )
            else:
                context["error"] = (
                    "This slide is part of a group of related images and can't "
                    "be duplicated on its own."
                )
        else:
            context["error"] = "OMERO couldn't complete this: %s" % (message or rsp.name)
        return context

    new_ids = _extract_new_ids(rsp.duplicates, obj_type)
    original_str = ",".join(str(i) for i in obj_ids)
    if dry_run:
        # A dry run's "duplicates" report echoes the original IDs
        # themselves (nothing new actually gets created), so there's no
        # real "new ID" to show yet - just confirm what would happen.
        context["success"] = "Preview only - nothing was changed. Would duplicate %s:%s." % (obj_type, original_str)
    elif new_ids:
        context["success"] = "Duplicated %s:%s -> new %s:%s" % (
            obj_type,
            original_str,
            obj_type,
            ",".join(str(i) for i in new_ids),
        )
    else:
        context["success"] = "Duplicate created."

    return context