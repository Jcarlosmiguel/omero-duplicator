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
from collections import OrderedDict

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

# Ignoring a linked-to class (e.g. Annotation) directly does not work as
# expected under OMERO's group permissions - the *link* class has to be
# ignored instead (confirmed against the real omero-cli-duplicate plugin's
# own --help text). Roi is the exception: it has no separate link class, so
# ignoring it directly works.
ANNOTATION_LINK_TYPES = ("ImageAnnotationLink", "DatasetAnnotationLink", "ProjectAnnotationLink")
ROI_TYPES = ("Roi",)

# Groups the dotted class-path keys in an omero.cmd.Duplicate response's
# `duplicates` dict (e.g. "ome.model.core.Image") into a human-readable
# report, instead of the flat one-line summary shown before - see
# notes/forum-feedback-plan.md for why. Order here is also the order
# categories are shown in, when present.
_ANNOTATION_SUFFIXES = ("AnnotationLink", "Annotation")
_ROI_CLASSES = {"Roi", "Rectangle", "Ellipse", "Line", "Point", "Polygon", "Polyline", "Mask", "Label"}
_FILESET_CLASSES = {"Fileset", "FilesetEntry", "FilesetJobLink", "OriginalFile", "JobOriginalFileLink"}
_MICROSCOPE_CLASSES = {
    "Instrument", "Microscope", "Detector", "DetectorSettings", "Objective", "ObjectiveSettings",
    "LogicalChannel", "Channel", "Filter", "FilterSet", "Laser", "LightSource", "LightSourceSettings",
    "Dichroic", "StageLabel", "ImagingEnvironment", "TransmittanceRange", "Arc", "LightEmittingDiode",
}
_CATEGORY_ORDER = ("Annotations", "ROIs", "Fileset", "Microscope metadata", "Other")


def _get_fileset_image_ids(conn, fileset_id):
    query = "select i.id from Image i where i.fileset.id = :fid"
    params = omero.sys.ParametersI()
    params.addLong("fid", int(fileset_id))
    results = conn.getQueryService().projection(query, params, conn.SERVICE_OPTS)
    return [r[0].val for r in results]


def _categorize_class(class_name):
    if class_name.endswith(_ANNOTATION_SUFFIXES):
        return "Annotations"
    if class_name in _ROI_CLASSES:
        return "ROIs"
    if class_name in _FILESET_CLASSES or class_name.endswith("Job"):
        return "Fileset"
    if class_name in _MICROSCOPE_CLASSES:
        return "Microscope metadata"
    return "Other"


def _categorize_duplicates(duplicates):
    """Turns a Duplicate response's raw `duplicates` dict into an ordered
    {category: [(class_name, count), ...]} report. Deliberately keeps
    unmatched classes in an "Other" bucket rather than dropping them - the
    exact set of types OMERO duplicates can vary by server version/config,
    and silently hiding unknown ones would make the report misleading
    rather than just incomplete.
    """
    grouped = OrderedDict((cat, []) for cat in _CATEGORY_ORDER)
    for key, ids in (duplicates or {}).items():
        if not ids:
            continue
        class_name = key.rsplit(".", 1)[-1]
        grouped[_categorize_class(class_name)].append((class_name, len(ids)))
    return OrderedDict((cat, sorted(items)) for cat, items in grouped.items() if items)


def _submit_duplicate(conn, obj_type, obj_ids, dry_run, types_to_ignore=None):
    req = omero.cmd.Duplicate()
    req.targetObjects = {obj_type: obj_ids}
    req.dryRun = dry_run
    if types_to_ignore:
        req.typesToIgnore = list(types_to_ignore)

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
    skip_annotations = request.POST.get("skip_annotations") == "1"
    skip_rois = request.POST.get("skip_rois") == "1"

    types_to_ignore = []
    if skip_annotations:
        types_to_ignore.extend(ANNOTATION_LINK_TYPES)
    if skip_rois:
        types_to_ignore.extend(ROI_TYPES)

    context = {
        "template": "omero_duplicator/index.html",
        "obj_type": obj_type,
        "obj_id": obj_id,
        "dry_run": dry_run,
        "skip_annotations": skip_annotations,
        "skip_rois": skip_rois,
        "submitted": True,
    }

    id_parts = [p.strip() for p in obj_id.split(",") if p.strip()]
    if obj_type not in VALID_TYPES or not id_parts or not all(p.isdigit() for p in id_parts):
        context["error"] = "Please provide a valid type and a numeric ID (or comma-separated IDs)."
        return context
    obj_ids = [int(p) for p in id_parts]

    try:
        rsp = _submit_duplicate(conn, obj_type, obj_ids, dry_run, types_to_ignore=types_to_ignore)
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
    context["breakdown"] = _categorize_duplicates(rsp.duplicates)
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