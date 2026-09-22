import json
from unittest.mock import Mock

import httplib2
import pytest
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpRequest

from resume_tailor_harness.gmail.client import fetch_recent_messages
from resume_tailor_harness.gmail.errors import (
    GmailApiError,
    GmailNotConnected,
    GmailScopeMissing,
)
from resume_tailor_harness.gmail.requests import execute_read


def _error(status, reason="backendError"):
    return HttpError(
        httplib2.Response({"status": status}),
        json.dumps(
            {"error": {"message": "provider details", "errors": [{"reason": reason}]}}
        ).encode(),
    )


@pytest.mark.parametrize(
    "failure", [429, 503, "rateLimitExceeded", "userRateLimitExceeded", "network"]
)
def test_real_sdk_retries_transient_reads(failure):
    http = Mock()
    status = failure if isinstance(failure, int) else 403
    error = _error(status, failure if isinstance(failure, str) else "backendError")
    first = TimeoutError() if failure == "network" else (error.resp, error.content)
    http.request.side_effect = [
        first,
        (httplib2.Response({"status": 200}), b'{"messages": []}'),
    ]
    request = HttpRequest(
        http,
        lambda _, content: json.loads(content),
        "https://gmail.googleapis.com/test",
    )
    request._sleep = lambda _: None
    assert execute_read(request) == {"messages": []}
    assert http.request.call_count == 2


@pytest.mark.parametrize(
    "status,reason,expected",
    [
        (401, "authError", GmailNotConnected),
        (403, "insufficientPermissions", GmailScopeMissing),
        (429, "rateLimitExceeded", GmailApiError),
        (503, "backendError", GmailApiError),
    ],
)
def test_errors_are_actionable_and_do_not_expose_provider_payload(
    status, reason, expected
):
    request = Mock()
    request.execute.side_effect = _error(status, reason)
    with pytest.raises(expected) as caught:
        execute_read(request)
    assert "provider details" not in str(caught.value)


def test_listing_pages_and_deleted_message_do_not_abort_scan():
    service = Mock()
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.side_effect = [
        {"messages": [{"id": "deleted"}], "nextPageToken": "page2"},
        {"messages": [{"id": "kept"}]},
    ]
    messages.get.return_value.execute.side_effect = [
        _error(404),
        {"payload": {"headers": [{"name": "Subject", "value": "Interview"}]}},
    ]
    result = fetch_recent_messages(service, max_results=600)
    assert [email.message_id for email in result] == ["kept"]
    assert messages.list.call_args_list[0].kwargs["maxResults"] == 500
    assert messages.list.call_args_list[1].kwargs["pageToken"] == "page2"


def test_incomplete_metadata_scan_is_not_reported_as_success():
    service = Mock()
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.return_value = {"messages": [{"id": "m1"}]}
    messages.get.return_value.execute.side_effect = _error(503)
    with pytest.raises(GmailApiError):
        fetch_recent_messages(service)


def test_sdk_retries_are_bounded():
    http = Mock()
    error = _error(503)
    http.request.return_value = (error.resp, error.content)
    request = HttpRequest(
        http,
        lambda _, content: json.loads(content),
        "https://gmail.googleapis.com/test",
    )
    request._sleep = lambda _: None
    with pytest.raises(GmailApiError):
        execute_read(request)
    assert http.request.call_count == 4


def test_permission_failure_is_not_retried():
    http = Mock()
    error = _error(403, "insufficientPermissions")
    http.request.return_value = (error.resp, error.content)
    request = HttpRequest(
        http,
        lambda _, content: json.loads(content),
        "https://gmail.googleapis.com/test",
    )
    with pytest.raises(GmailScopeMissing):
        execute_read(request)
    assert http.request.call_count == 1
