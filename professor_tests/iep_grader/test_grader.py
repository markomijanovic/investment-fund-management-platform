import json
from typing import Any

import pytest
import requests


def test_grader_case(grader_case, request):
    case = grader_case
    response = None
    url = case.url
    set_up_data = None

    try:
        request.node._iep_phase = "setup"
        url, set_up_data, skip_test = case.preparation_function(
            case.url,
            case.headers,
            case.data,
            case.files,
        )
        request.node._iep_request_info = {
            "method": case.method,
            "url": url,
            "headers": _redact_headers(case.headers),
        }

        if skip_test:
            pytest.skip("Skipped by the original test preparation function")

        request.node._iep_phase = "request"
        response = requests.request(
            method=case.method,
            url=url,
            headers=case.headers,
            json=case.data,
            files=case.files,
            timeout=float(request.config.option.request_timeout),
        )
        request.node._iep_response_info = {
            "status_code": response.status_code,
            "body": _safe_json(response),
        }
    except requests.Timeout as exc:
        pytest.fail(
            f"HTTP request timed out after {request.config.option.request_timeout}s. "
            f"method={case.method} url={url}"
        )
    except requests.RequestException as exc:
        pytest.fail(f"HTTP request failed. method={case.method} url={url} error={exc}")
    finally:
        request.node._iep_phase = getattr(request.node, "_iep_phase", "cleanup")
        for file_handle in case.files.values():
            try:
                file_handle.close()
            except Exception:
                pass

    request.node._iep_phase = "status_check"
    assert response.status_code == case.expected_status_code, (
        "Invalid status code\n"
        f"  method:   {case.method}\n"
        f"  url:      {url}\n"
        f"  expected: {case.expected_status_code}\n"
        f"  received: {response.status_code}\n"
        f"  body:     {_pretty(_safe_json(response))}"
    )

    request.node._iep_phase = "json_parse"
    if case.expected_response is not None:
        try:
            received_response = response.json()
        except ValueError as exc:
            pytest.fail(
                "Response body is not valid JSON\n"
                f"  method: {case.method}\n"
                f"  url:    {url}\n"
                f"  body:   {response.text}"
            )
        expected_response = case.expected_response
    else:
        received_response = {}
        expected_response = {}

    request.node._iep_response_info = {
        "status_code": response.status_code,
        "body": received_response if case.expected_response is not None else _safe_json(response),
    }

    request.node._iep_phase = "comparison"
    try:
        case.test_and_cleanup_function(set_up_data, expected_response, received_response)
    except AssertionError as exc:
        pytest.fail(
            "Response comparison failed\n"
            f"  method:   {case.method}\n"
            f"  url:      {url}\n"
            f"  expected: {_pretty(expected_response)}\n"
            f"  received: {_pretty(received_response)}\n"
            f"  error:    {exc}"
        )


def _safe_json(response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


def _pretty(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _redact_headers(headers):
    redacted = dict(headers or {})
    if "Authorization" in redacted:
        redacted["Authorization"] = "Bearer <redacted>"
    return redacted
