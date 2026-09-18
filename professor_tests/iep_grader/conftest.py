import html
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import requests

import authentication_tests
import data as grader_data
import level0_tests
import level1_tests
import level2_tests
import level3_tests
import utilities

AUTHENTICATION_FACTOR = 0.1
LEVEL_ORDER = {
    "authentication": -1,
    "level0": 0,
    "level1": 1,
    "level2": 2,
    "level3": 3,
    "all": 99,
}
LEVEL_COMPONENTS = ["level0", "level1", "level2", "level3"]


@dataclass
class GraderTestCase:
    component: str
    index: int
    method: str
    url: str
    preparation_function: Any
    headers: Dict[str, Any]
    data: Any
    files: Dict[str, Any]
    expected_status_code: int
    expected_response: Any
    test_and_cleanup_function: Any
    weight: float
    score_multiplier: float = 1.0
    name: str = ""

    @property
    def possible_points(self) -> float:
        return float(self.weight)

    @property
    def earned_points(self) -> float:
        return float(self.weight) * float(self.score_multiplier)

    @property
    def display_name(self) -> str:
        return self.name or f"{self.component}_{self.index + 1:03d}"


def pytest_addoption(parser):
    group = parser.getgroup("iep-grader")
    group.addoption(
        "--type",
        action="store",
        default="all",
        choices=list(LEVEL_ORDER.keys()),
        help="Which group of IEP tests to run.",
    )
    group.addoption("--authentication-url", action="store", default=None)
    group.addoption("--jwt-secret", action="store", default=None)
    group.addoption("--roles-field", action="store", default=None)
    group.addoption("--employee-role", action="store", default=None)
    group.addoption("--director-role", action="store", default=None)
    group.addoption("--with-authentication", action="store_true", default=False)
    group.addoption("--employee-url", action="store", default=None)
    group.addoption("--director-url", action="store", default=None)
    group.addoption(
        "--with-blockchain",
        action="store_true",
        default=False,
        help=(
            "Assume the director service is running with BLOCKCHAIN_ENABLED=true. Tests "
            "deploy a voting contract and send real votes via web3. When omitted, the "
            "director is assumed to run with BLOCKCHAIN_ENABLED=false, and tests use the "
            "immediate {uuid, approved} /decision payload instead."
        ),
    )
    group.addoption("--provider-url", action="store", default=None)
    group.addoption(
        "--grade-report-file",
        action="store",
        default="grade_report.json",
        help="Where to write a machine-readable grading report.",
    )
    group.addoption(
        "--request-timeout",
        action="store",
        type=float,
        default=5.0,
        help="Timeout, in seconds, for every HTTP request made by the grader.",
    )
    group.addoption(
        "--service-timeout",
        action="store",
        type=float,
        default=60.0,
        help="Maximum number of seconds to wait for configured services before tests start.",
    )
    group.addoption(
        "--wait-for-services",
        action="store_true",
        default=False,
        help="Wait until configured service URLs respond before running tests.",
    )
    group.addoption(
        "--grade-exit-zero",
        action="store_true",
        default=False,
        help="Write the grade report but exit with status 0 even when tests fail. Useful for LMS/CI pipelines that read grade_report.json.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "weight(value): grading weight of this test")
    config.addinivalue_line("markers", "component(name): project component/level")
    config.addinivalue_line("markers", "stateful: test depends on state produced by earlier grader tests")
    config._iep_results = []

    timeout = float(config.option.request_timeout)

    def timed_request(*args, **kwargs):
        kwargs.setdefault("timeout", timeout)
        return requests.request(*args, **kwargs)

    # Patch utilities.request so all HTTP calls in setup/login functions
    # also respect the configured timeout.
    utilities.request = timed_request


def _require(config, *option_names: str):
    missing = [name for name in option_names if getattr(config.option, name) in (None, "")]
    if missing:
        pretty = ", ".join("--" + name.replace("_", "-") for name in missing)
        raise pytest.UsageError(f"Missing required option(s): {pretty}")


def _create_and_initialize_account(provider_url):
    try:
        from web3 import Account, Web3, HTTPProvider
    except ModuleNotFoundError as exc:
        raise pytest.UsageError(
            "--with-blockchain requires the web3 package. Install requirements-pytest.txt first."
        ) from exc
    web3 = Web3(HTTPProvider(provider_url))
    private_key = "0x" + secrets.token_hex(32)
    account = Account.from_key(private_key)
    address = account.address
    web3.eth.send_transaction({
        "from":     web3.eth.accounts[0],
        "to":       address,
        "value":    web3.to_wei(2, "ether"),
        "gasPrice": 1,
    })
    return private_key, address


def _collect_from_runner(module, runner_name: str, *args) -> List[list]:
    """Call an existing run_*_tests function, but capture its internal test table.

    The original modules imported run_tests directly using
    `from utilities import run_tests`, so we patch that module-level symbol.
    """
    captured = []
    original = module.run_tests

    def capture(tests):
        captured.extend(tests)
        return 0

    module.run_tests = capture
    try:
        getattr(module, runner_name)(*args)
    finally:
        module.run_tests = original
    return captured


def _selected_level_includes(selected: str, component: str) -> bool:
    if selected == "all":
        return True
    if selected == "authentication":
        return component == "authentication"
    if component == "authentication":
        return False
    return LEVEL_ORDER[selected] >= LEVEL_ORDER[component]


def _slug(value: Any, max_len: int = 80) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"https?://[^/]+", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if len(text) > max_len:
        text = text[:max_len].rstrip("_")
    return text or "case"


def _case_name(component: str, index: int, test: list) -> str:
    method = _slug(test[0], 12)
    path = _slug(test[1].split("?")[0].rstrip("/").split("/")[-1], 24)
    status = test[6]
    expected = test[7]
    reason = ""
    if isinstance(expected, dict):
        reason = expected.get("message") or expected.get("msg") or ""
    elif expected is None:
        reason = "success"
    reason_slug = _slug(reason, 45) if reason else "response"
    return f"{component}_{index + 1:03d}_{method}_{path}_{status}_{reason_slug}"


def _reset_original_global_state() -> None:
    # Keep generated pytest cases deterministic when collection happens more than once.
    try:
        grader_data.set_is_employee_registered(False)
    except Exception:
        pass


def _build_cases(config) -> List[GraderTestCase]:
    opt = config.option
    selected = opt.type
    cases: List[GraderTestCase] = []

    _reset_original_global_state()

    blockchain_enabled = opt.with_blockchain

    # Create 3 voter accounts (odd number) for blockchain voting tests
    voter_private_keys: List[str] = []
    if blockchain_enabled:
        _require(config, "provider_url")
        for _ in range(3):
            pk, _ = _create_and_initialize_account(opt.provider_url)
            voter_private_keys.append(pk)

    def add(component: str, raw_tests: List[list], multiplier: float = 1.0):
        for index, test in enumerate(raw_tests):
            cases.append(GraderTestCase(
                component=component,
                index=index,
                method=test[0],
                url=test[1],
                preparation_function=test[2],
                headers=test[3],
                data=test[4],
                files=test[5],
                expected_status_code=test[6],
                expected_response=test[7],
                test_and_cleanup_function=test[8],
                weight=float(test[9]),
                score_multiplier=multiplier,
                name=_case_name(component, index, test),
            ))

    if opt.with_authentication and _selected_level_includes(selected, "authentication"):
        _require(config, "authentication_url", "jwt_secret", "roles_field",
                 "employee_role", "director_role")
        add("authentication", _collect_from_runner(
            authentication_tests,
            "run_authentication_tests",
            opt.authentication_url,
            opt.jwt_secret,
            opt.roles_field,
            opt.employee_role,
            opt.director_role,
        ))

    level_multiplier = 1.0 if opt.with_authentication else 1 - AUTHENTICATION_FACTOR

    if _selected_level_includes(selected, "level0"):
        _require(config, "employee_url")
        if opt.with_authentication:
            _require(config, "authentication_url")
        add("level0", _collect_from_runner(
            level0_tests,
            "run_level0_tests",
            opt.with_authentication,
            opt.authentication_url,
            opt.employee_url,
        ), level_multiplier)

    if _selected_level_includes(selected, "level1"):
        _require(config, "employee_url", "director_url")
        if opt.with_authentication:
            _require(config, "authentication_url")
        if blockchain_enabled:
            _require(config, "provider_url")
        add("level1", _collect_from_runner(
            level1_tests,
            "run_level1_tests",
            opt.with_authentication,
            opt.authentication_url,
            opt.employee_url,
            opt.director_url,
            blockchain_enabled,
            voter_private_keys,
            opt.provider_url,
        ), level_multiplier)

    if _selected_level_includes(selected, "level2"):
        _require(config, "employee_url", "director_url")
        if opt.with_authentication:
            _require(config, "authentication_url")
        if blockchain_enabled:
            _require(config, "provider_url")
        add("level2", _collect_from_runner(
            level2_tests,
            "run_level2_tests",
            opt.with_authentication,
            opt.authentication_url,
            opt.employee_url,
            opt.director_url,
            blockchain_enabled,
            voter_private_keys,
            opt.provider_url,
        ), level_multiplier)

    if _selected_level_includes(selected, "level3"):
        _require(config, "employee_url", "director_url")
        if opt.with_authentication:
            _require(config, "authentication_url")
        if blockchain_enabled:
            _require(config, "provider_url")
        add("level3", _collect_from_runner(
            level3_tests,
            "run_level3_tests",
            opt.with_authentication,
            opt.authentication_url,
            opt.employee_url,
            opt.director_url,
            blockchain_enabled,
            voter_private_keys,
            opt.provider_url,
        ), level_multiplier)

    return cases


def _service_urls(config) -> List[str]:
    options = [
        config.option.authentication_url,
        config.option.employee_url,
        config.option.director_url,
    ]
    return [url.rstrip("/") for url in options if url]


def pytest_collection_modifyitems(config, items):
    if not config.option.wait_for_services:
        return
    import time
    timeout = float(config.option.service_timeout)
    deadline = time.monotonic() + timeout
    urls = _service_urls(config)
    if not urls:
        return
    remaining = set(urls)
    while remaining and time.monotonic() < deadline:
        for url in list(remaining):
            try:
                # Any HTTP response means the service is reachable.
                requests.get(url, timeout=float(config.option.request_timeout))
                remaining.remove(url)
            except requests.RequestException:
                pass
        if remaining:
            time.sleep(1)
    if remaining:
        raise pytest.UsageError(
            "Timed out waiting for service(s): " + ", ".join(sorted(remaining))
        )


def pytest_generate_tests(metafunc):
    if "grader_case" in metafunc.fixturenames:
        cases = _build_cases(metafunc.config)
        params = []
        for case in cases:
            marks = [
                pytest.mark.weight(case.possible_points),
                pytest.mark.component(case.component),
                pytest.mark.stateful,
            ]
            params.append(pytest.param(
                case,
                id=f"{case.display_name}_w{case.possible_points:g}",
                marks=marks,
            ))
        metafunc.parametrize("grader_case", params)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    # Stash the clean failure message (no pytest/library stack frames) so the
    # HTML report can render it directly instead of the full traceback.
    if call.excinfo is not None:
        report._iep_clean_message = str(call.excinfo.value).strip()

    if report.when not in ("setup", "call", "teardown"):
        return
    case = item.funcargs.get("grader_case") if hasattr(item, "funcargs") else None
    if case is None:
        return

    if report.when == "setup" and report.failed:
        _record_result(item, report, case, phase="pytest_setup")
    elif report.when == "call":
        phase = getattr(item, "_iep_phase", "call")
        _record_result(item, report, case, phase=phase)
    elif report.when == "teardown" and report.failed:
        _record_result(item, report, case, phase="pytest_teardown")


def _record_result(item, report, case: GraderTestCase, phase: str) -> None:
    if getattr(item, "_iep_recorded", False):
        return
    item._iep_recorded = True
    request_info  = getattr(item, "_iep_request_info", {})
    response_info = getattr(item, "_iep_response_info", {})
    item.config._iep_results.append({
        "nodeid":                item.nodeid,
        "name":                  case.display_name,
        "component":             case.component,
        "index":                 case.index + 1,
        "stateful":              True,
        "method":                request_info.get("method", case.method),
        "url":                   request_info.get("url", case.url),
        "expected_status_code":  case.expected_status_code,
        "received_status_code":  response_info.get("status_code"),
        "expected_response":     case.expected_response,
        "received_response":     response_info.get("body"),
        "weight":                case.weight,
        "score_multiplier":      case.score_multiplier,
        "possible_points":       case.possible_points,
        "earned_points":         case.earned_points,
        "outcome":               report.outcome,
        "phase":                 phase,
        "longrepr":              str(report.longrepr) if report.failed else "",
    })


def pytest_html_results_table_html(report, data):
    """Replace pytest-html's default traceback dump with the clean,
    pre-formatted failure message test_grader.py already builds (method,
    URL, expected vs. received status/body) -- no internal stack frames."""
    message = getattr(report, "_iep_clean_message", None)
    if message is None:
        return
    data.clear()
    data.append(
        '<div style="border-left: 4px solid #d32f2f; padding: 8px 12px; '
        'background: #fff5f5;">'
        '<pre style="white-space: pre-wrap; word-break: break-word; '
        'font-family: Consolas, Menlo, monospace; font-size: 13px; '
        'line-height: 1.5; margin: 0;">'
        f"{html.escape(message)}"
        "</pre></div>"
    )


def pytest_sessionfinish(session, exitstatus):
    results = getattr(session.config, "_iep_results", [])
    by_component: Dict[str, Dict[str, float]] = {}
    possible = 0.0
    earned   = 0.0

    for result in results:
        if result["outcome"] == "skipped":
            continue
        component = result["component"]
        by_component.setdefault(component, {"earned": 0.0, "possible": 0.0})
        possible_points = float(result["possible_points"])
        by_component[component]["possible"] += possible_points
        possible += possible_points
        if result["outcome"] == "passed":
            earned_points = float(result["earned_points"])
            by_component[component]["earned"] += earned_points
            earned += earned_points

    summary = {
        "schema_version": 2,
        "earned":         earned,
        "possible":       possible,
        "percentage":     (earned / possible * 100.0) if possible else 0.0,
        "stateful_suite": True,
        "notes": [
            "Tests are generated from the original row-based grader.",
            "Some tests intentionally depend on state produced by earlier tests, such as registered users and created orders.",
            "Skipped tests are not included in possible points.",
        ],
        "components": {
            name: {
                "earned":     values["earned"],
                "possible":   values["possible"],
                "percentage": (values["earned"] / values["possible"] * 100.0) if values["possible"] else 0.0,
            }
            for name, values in by_component.items()
        },
        "tests": results,
    }

    path = Path(session.config.option.grade_report_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    session.config._iep_summary = summary

    if session.config.option.grade_exit_zero:
        session.exitstatus = 0


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    summary = getattr(config, "_iep_summary", None)
    if not summary:
        return
    terminalreporter.write_sep("=", "IEP grading summary")
    for component, values in summary["components"].items():
        terminalreporter.write_line(
            f"{component}: {values['earned']:.2f}/{values['possible']:.2f} ({values['percentage']:.2f}%)"
        )
    terminalreporter.write_line(
        f"TOTAL: {summary['earned']:.2f}/{summary['possible']:.2f} ({summary['percentage']:.2f}%)"
    )
    terminalreporter.write_line(f"JSON report: {config.option.grade_report_file}")
