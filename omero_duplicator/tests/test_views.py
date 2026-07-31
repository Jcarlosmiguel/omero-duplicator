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

"""Tests for omero_duplicator.views.

No real OMERO server/login involved - the view functions are driven via
their raw (undecorated) form. Both login_required and render_response
use functools.update_wrapper, so __wrapped__ chains back to the actual
view logic - see unwrap() below. This is deliberate: the async job
design means "a duplicate completes" is two separate requests
(run_duplicate then check_duplicate), which isn't something a real
OMERO login makes any easier to test - what matters here is each
function's own branching, not OMERO's plumbing underneath it.
"""

import json
from unittest.mock import MagicMock, patch

import Ice
import omero.cmd
import pytest

from omero_duplicator import views


class FakeSession(dict):
    """A real Django session supports `.modified = True` alongside normal
    dict access (views.py sets it after every mutation) - a plain dict
    doesn't allow arbitrary attributes, so a bare {} won't do here."""


class FakeRequest:
    """Minimal stand-in for a Django request with a session dict - enough
    for every view/helper here."""

    def __init__(self, method="GET", get_params=None, post_params=None):
        self.method = method
        self.GET = get_params or {}
        self.POST = post_params or {}
        self.session = FakeSession()


def unwrap(view):
    while hasattr(view, "__wrapped__"):
        view = view.__wrapped__
    return view


raw_index = unwrap(views.index)
raw_run_duplicate = unwrap(views.run_duplicate)
raw_check_duplicate = unwrap(views.check_duplicate)


# --- _categorize_class ---------------------------------------------------

@pytest.mark.parametrize("class_name,expected", [
    ("ImageAnnotationLink", "Annotations"),
    ("MapAnnotation", "Annotations"),
    ("Roi", "ROIs"),
    ("Rectangle", "ROIs"),
    ("Fileset", "Fileset"),
    ("IndexingJob", "Fileset"),
    ("Instrument", "Microscope metadata"),
    ("Channel", "Microscope metadata"),
    ("SomethingElseEntirely", "Other"),
])
def test_categorize_class(class_name, expected):
    assert views._categorize_class(class_name) == expected


# --- _categorize_duplicates -----------------------------------------------

def test_categorize_duplicates_groups_counts_and_keeps_ids():
    duplicates = {
        "ome.model.core.Image": [780497],
        "ome.model.roi.Roi": [223954, 223955],
        "ome.model.containers.Dataset": [],  # empty - must be skipped
    }
    result = views._categorize_duplicates(duplicates)

    assert result["ROIs"] == [("Roi", 2, [223954, 223955])]
    assert result["Other"] == [("Image", 1, [780497])]
    assert "Dataset" not in result


def test_categorize_duplicates_orders_categories_consistently():
    duplicates = {
        "x.Roi": [1],
        "x.Instrument": [2],
        "x.ImageAnnotationLink": [3],
    }
    result = views._categorize_duplicates(duplicates)
    assert list(result.keys()) == [
        "Annotations", "ROIs", "Microscope metadata",
    ]


# --- _extract_new_ids ------------------------------------------------------

def test_extract_new_ids_finds_matching_type():
    duplicates = {
        "ome.model.core.Image": [1, 2],
        "ome.model.containers.Project": [9],
    }
    assert views._extract_new_ids(duplicates, "Project") == [9]


def test_extract_new_ids_returns_empty_when_absent():
    assert views._extract_new_ids({}, "Project") == []
    assert views._extract_new_ids(None, "Project") == []


# --- _job_store --------------------------------------------------------

def test_job_store_creates_and_reuses_same_dict():
    request = FakeRequest()
    store = views._job_store(request)
    store["abc"] = {"obj_type": "Project"}
    assert views._job_store(request) is store
    assert request.session[views.JOB_SESSION_KEY]["abc"]["obj_type"] == (
        "Project"
    )


# --- _new_object_links / _build_result ------------------------------------

def test_new_object_links_matches_omero_web_show_url_convention():
    links = views._new_object_links("Project", [804])
    assert links == [{"id": 804, "url": "/webclient/?show=project-804"}]


def test_build_result_dry_run():
    rsp = MagicMock(spec=["duplicates"])
    rsp.duplicates = {"ome.model.containers.Project": [51]}
    result = views._build_result(
        conn=None, obj_type="Project", obj_ids=[51], dry_run=True, rsp=rsp
    )
    assert result["success"] == (
        "Preview only - nothing was changed. Would duplicate Project:51."
    )
    assert "new_objects" not in result
    assert result["breakdown"]["Other"] == [("Project", 1, [51])]


def test_build_result_real_duplicate_includes_new_object_link():
    rsp = MagicMock(spec=["duplicates"])
    rsp.duplicates = {"ome.model.containers.Project": [52]}
    result = views._build_result(
        conn=None, obj_type="Project", obj_ids=[51], dry_run=False, rsp=rsp
    )
    assert result["success"] == "Duplicated Project:51 -> new Project:52"
    assert result["new_objects"] == [
        {"id": 52, "url": "/webclient/?show=project-52"}
    ]


def test_build_result_fileset_conflict_lists_siblings():
    rsp = omero.cmd.ERR()
    rsp.message = (
        "within Fileset[10] may not duplicate Image[20] without "
        "Image[21] also"
    )
    conn = MagicMock()
    conn.getQueryService.return_value.projection.return_value = [
        [MagicMock(val=20)], [MagicMock(val=21)],
    ]
    result = views._build_result(
        conn, "Image", [20], dry_run=False, rsp=rsp
    )
    assert result["finished"] is True
    assert "20,21" in result["error"]


def test_build_result_generic_err_falls_back_to_message():
    rsp = omero.cmd.ERR()
    rsp.message = "something unrelated went wrong"
    result = views._build_result(
        None, "Image", [1], dry_run=False, rsp=rsp
    )
    assert result["error"] == (
        "OMERO couldn't complete this: something unrelated went wrong"
    )


# --- index() ---------------------------------------------------------

def test_index_prefills_valid_type_and_id():
    request = FakeRequest(
        get_params={"obj_type": "Dataset", "obj_id": "42"}
    )
    context = raw_index(request, conn=None)
    assert context["obj_type"] == "Dataset"
    assert context["obj_id"] == "42"


def test_index_ignores_invalid_type():
    request = FakeRequest(
        get_params={"obj_type": "NotARealType", "obj_id": "42"}
    )
    context = raw_index(request, conn=None)
    assert "obj_type" not in context
    assert context["obj_id"] == "42"


# --- run_duplicate() -------------------------------------------------

def test_run_duplicate_rejects_invalid_type():
    request = FakeRequest(
        post_params={"obj_type": "Bogus", "obj_id": "1", "dry_run": "1"}
    )
    response = raw_run_duplicate(request, conn=None)
    assert "error" in json.loads(response.content)


def test_run_duplicate_rejects_non_numeric_id():
    request = FakeRequest(
        post_params={"obj_type": "Project", "obj_id": "abc", "dry_run": "1"}
    )
    response = raw_run_duplicate(request, conn=None)
    assert "error" in json.loads(response.content)


def test_run_duplicate_submits_and_stores_job():
    request = FakeRequest(post_params={
        "obj_type": "Project", "obj_id": "51,52", "dry_run": "1",
        "skip_annotations": "1", "skip_rois": "0",
    })
    fake_handle = MagicMock()
    fake_handle.__str__.return_value = "fake-job-id"

    with patch.object(
        views, "_submit_duplicate", return_value=fake_handle
    ) as mock_submit:
        response = raw_run_duplicate(request, conn="conn-stub")

    body = json.loads(response.content)
    assert body == {"job_id": "fake-job-id"}
    mock_submit.assert_called_once_with(
        "conn-stub", "Project", [51, 52], True,
        types_to_ignore=list(views.ANNOTATION_LINK_TYPES),
    )
    assert request.session[views.JOB_SESSION_KEY]["fake-job-id"] == {
        "obj_type": "Project", "obj_ids": [51, 52], "dry_run": True,
    }


def test_run_duplicate_handles_submit_exception():
    request = FakeRequest(
        post_params={"obj_type": "Project", "obj_id": "51", "dry_run": "1"}
    )
    with patch.object(
        views, "_submit_duplicate", side_effect=RuntimeError("boom")
    ):
        response = raw_run_duplicate(request, conn=None)
    assert "boom" in json.loads(response.content)["error"]


# --- check_duplicate() ------------------------------------------------

def test_check_duplicate_unknown_job():
    request = FakeRequest(get_params={"job_id": "nope"})
    response = raw_check_duplicate(request, conn=None)
    assert json.loads(response.content) == {
        "finished": True, "error": "Unknown or expired job."
    }


def test_check_duplicate_still_running():
    request = FakeRequest(get_params={"job_id": "job-1"})
    request.session[views.JOB_SESSION_KEY] = {
        "job-1": {"obj_type": "Project", "obj_ids": [51], "dry_run": True}
    }
    fake_cb = MagicMock()
    fake_cb.getResponse.return_value = None

    with patch.object(
        omero.cmd.HandlePrx, "checkedCast", return_value=MagicMock()
    ), patch.object(
        views.omero.callbacks, "CmdCallbackI", return_value=fake_cb
    ):
        response = raw_check_duplicate(request, conn=MagicMock())

    assert json.loads(response.content) == {"finished": False}
    fake_cb.close.assert_called_once_with(False)
    # Still tracked - not popped while running.
    assert "job-1" in request.session[views.JOB_SESSION_KEY]


def test_check_duplicate_finished_success_pops_job():
    request = FakeRequest(get_params={"job_id": "job-1"})
    request.session[views.JOB_SESSION_KEY] = {
        "job-1": {"obj_type": "Project", "obj_ids": [51], "dry_run": True}
    }
    fake_rsp = MagicMock(spec=["duplicates"])
    fake_rsp.duplicates = {"ome.model.containers.Project": [51]}
    fake_cb = MagicMock()
    fake_cb.getResponse.return_value = fake_rsp

    with patch.object(
        omero.cmd.HandlePrx, "checkedCast", return_value=MagicMock()
    ), patch.object(
        views.omero.callbacks, "CmdCallbackI", return_value=fake_cb
    ):
        response = raw_check_duplicate(request, conn=MagicMock())

    body = json.loads(response.content)
    assert body["finished"] is True
    assert body["success"] == (
        "Preview only - nothing was changed. Would duplicate Project:51."
    )
    fake_cb.close.assert_called_once_with(True)
    assert "job-1" not in request.session[views.JOB_SESSION_KEY]


def test_check_duplicate_handle_gone_reports_cleanly():
    request = FakeRequest(get_params={"job_id": "job-1"})
    request.session[views.JOB_SESSION_KEY] = {
        "job-1": {"obj_type": "Project", "obj_ids": [51], "dry_run": True}
    }

    with patch.object(
        omero.cmd.HandlePrx,
        "checkedCast",
        side_effect=Ice.ObjectNotExistException(),
    ):
        response = raw_check_duplicate(request, conn=MagicMock())

    assert json.loads(response.content) == {
        "finished": True, "error": "Job result is no longer available."
    }
    assert "job-1" not in request.session[views.JOB_SESSION_KEY]
