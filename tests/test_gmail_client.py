import json
from unittest.mock import Mock

import httplib2
import pytest
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpRequest

from resume_tailor_harness.gmail.client import (
    RECRUITING_QUERY,
    batch_read_messages,
    fetch_recent_messages,
)
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


def test_recruiting_search_includes_archive_deduplicates_and_orders_by_receipt():
    service = Mock()
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.side_effect = [
        {"messages": [{"id": "older"}, {"id": "shared"}]},
        {"messages": [{"id": "archived"}, {"id": "shared"}]},
    ]
    messages.get.return_value.execute.side_effect = [
        {"internalDate": "100"},
        {"internalDate": "200"},
        {"internalDate": "300"},
    ]
    result = fetch_recent_messages(service, max_results=2, include_recruiting=True)
    assert [email.message_id for email in result] == ["archived", "shared", "older"]
    assert [email.recruiting_candidate for email in result] == [True, True, False]
    assert messages.get.call_count == 3
    assert messages.list.call_args_list[0].kwargs["labelIds"] == ["INBOX"]
    assert messages.list.call_args_list[1].kwargs["q"] == RECRUITING_QUERY
    assert "labelIds" not in messages.list.call_args_list[1].kwargs
    for exclusion in ("-in:sent", "-in:drafts", "-in:spam", "-in:trash"):
        assert exclusion in RECRUITING_QUERY


def test_scan_limit_reports_incomplete_results():
    service = Mock()
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}],
        "nextPageToken": "page2",
    }
    messages.get.return_value.execute.return_value = {}
    warnings = []
    assert (
        len(fetch_recent_messages(service, max_results=1, on_warning=warnings.append))
        == 1
    )
    assert len(warnings) == 1
    assert "scan limit" in warnings[0]


def test_recruiting_search_failure_does_not_claim_complete_sync():
    service = Mock()
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.side_effect = [{"messages": []}, _error(503)]
    with pytest.raises(GmailApiError):
        fetch_recent_messages(service, include_recruiting=True)


def test_batch_retries_only_failed_parts():
    service = Mock()
    good, transient, missing = Mock(), Mock(), Mock()
    transient.execute.return_value = {"id": "retry"}
    missing.execute.side_effect = _error(404)
    requests = {"good": good, "retry": transient, "deleted": missing}
    service.users.return_value.messages.return_value.get.side_effect = lambda **kwargs: (
        requests[kwargs["id"]]
    )

    def batch(callback):
        result = Mock()

        def execute():
            callback("good", {"id": "good"}, None)
            callback("retry", None, _error(503))
            callback("deleted", None, _error(404))

        result.execute.side_effect = execute
        return result

    service.new_batch_http_request.side_effect = batch
    assert batch_read_messages(service, list(requests)) == {
        "good": {"id": "good"},
        "retry": {"id": "retry"},
        "deleted": None,
    }
    good.execute.assert_not_called()
    transient.execute.assert_called_once_with(num_retries=3)
