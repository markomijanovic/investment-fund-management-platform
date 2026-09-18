# IEP pytest grader

This package runs the IEP investment-fund project grader through `pytest`. It tests three
services — authentication, employee, director — and exercises the full business flow: register,
log in, create buy/sell orders, approve/reject them (optionally via an on-chain vote), search,
and report.

Both **authentication** and **blockchain voting** are optional features of the graded
implementation. The grader detects and adapts to all four combinations; see
[Combinations](#combinations) below.

- [Install](#install)
- [Combinations](#combinations)
- [CLI options reference](#cli-options-reference)
- [Output formats](#output-formats)
- [Stateful tests](#stateful-tests)
- [Deployment modes](#deployment-modes)
- [Test reference](#test-reference) — what every test case does, request/response, by component

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-pytest.txt
```

`requirements.txt` pins `eth-typing<5` alongside `web3==6.5.0` — `web3` 6.5.0 bundles a pytest
plugin (`web3.tools.pytest_ethereum`) that imports `eth_typing.ContractName`, which was removed in
`eth-typing` 5.0.0. Without the pin, a plain `pip install` can leave `pytest` unable to even start
(`ImportError: cannot import name 'ContractName'`).

## Combinations

The grader provides four valid combinations:

### 1. Authentication + blockchain (full implementation)

Needs Ganache running and reachable at `--provider-url`.

```bash
pytest -q --type all \
  --authentication-url http://127.0.0.1:5000 \
  --jwt-secret super-secret-key-change-in-production \
  --roles-field role --employee-role employee --director-role director \
  --with-authentication \
  --employee-url http://127.0.0.1:5001 \
  --director-url http://127.0.0.1:5002 \
  --with-blockchain --provider-url http://127.0.0.1:8545 \
  --grade-report-file grade_report.json
```

98 tests; 179 possible points, 179 earned if everything passes.

### 2. Authentication, no blockchain

```bash
pytest -q --type all \
  --authentication-url http://127.0.0.1:5000 \
  --jwt-secret super-secret-key-change-in-production \
  --roles-field role --employee-role employee --director-role director \
  --with-authentication \
  --employee-url http://127.0.0.1:5001 \
  --director-url http://127.0.0.1:5002 \
  --grade-report-file grade_report.json
```

98 tests; 180 possible points, 180 earned if everything passes (level1's report check has one
more point-bearing row in this mode — see the [level1 test reference](#3-level1_testspy)).

### 3. Blockchain, no authentication

No auth service or MySQL needed at all — don't even start them. The `authentication` component
and every auth-error row in level0/level1 are skipped entirely. The full weight of level0–3 (118 points) still counts toward
`possible`, but `earned` is capped at 90% of it —
a flat 10% penalty on whatever you actually score, not a 10x point dilution. Pass every business-
logic test and you'll see `106.20/118.00 (90.00%)`, not `100%`.

```bash
pytest -q --type all \
  --employee-url http://127.0.0.1:5001 \
  --director-url http://127.0.0.1:5002 \
  --with-blockchain --provider-url http://127.0.0.1:8545 \
  --grade-report-file grade_report.json
```

63 tests (51 run + 12 skipped); 118.00 possible points, 106.20 earned if everything passes.

### 4. No authentication, no blockchain (business logic only)

Only Mongo and Redis need to be running — no MySQL, no auth service, no Ganache. Same 90% cap on
earned points as combination 3 above.

```bash
pytest -q --type all \
  --employee-url http://127.0.0.1:5001 \
  --director-url http://127.0.0.1:5002 \
  --grade-report-file grade_report.json
```

63 tests (51 run + 12 skipped); 119.00 possible points, 107.10 earned if everything passes.

## CLI options reference

### Service URLs and credentials

| Option | Required when | Description |
|---|---|---|
| `--authentication-url URL` | `--with-authentication` is set, or `--type authentication` | Base URL of the auth service. |
| `--employee-url URL` | level0–3 selected (i.e. almost always) | Base URL of the employee service. |
| `--director-url URL` | level1–3 selected | Base URL of the director service. |
| `--provider-url URL` | `--with-blockchain` is set | Ganache JSON-RPC URL, used both to fund 3 fresh voter accounts and to sign/send their votes. |
| `--jwt-secret SECRET` | `--with-authentication` is set | Must match `JWT_SECRET_KEY` configured on the auth/employee/director services — used to independently decode and verify issued tokens. |
| `--roles-field NAME` | `--with-authentication` is set | Name of the JWT claim holding the user's role (e.g. `role`). |
| `--employee-role NAME` | `--with-authentication` is set | Value of that claim for an employee token (e.g. `employee`). |
| `--director-role NAME` | `--with-authentication` is set | Value of that claim for a director token (e.g. `director`). |

### Mode toggles

| Option | Default | Description |
|---|---|---|
| `--with-authentication` | off | See [Combinations](#combinations). |
| `--with-blockchain` | off | See [Combinations](#combinations). |
| `--type {all,authentication,level0,level1,level2,level3}` | `all` | Restrict to one component, or `all` for everything up to and including the chosen level (e.g. `--type level2` runs level0+level1+level2 but not level3 — level inclusion is cumulative; `authentication` runs only the auth component). |

### Reporting

| Option | Default | Description |
|---|---|---|
| `--grade-report-file PATH` | `grade_report.json` | Where to write the machine-readable grade report (see [Output formats](#output-formats)). Always written, even on failure. |
| `--grade-exit-zero` | off | Exit with status 0 after writing the grade report, even if tests fail. Useful for LMS/CI pipelines that read `grade_report.json` and shouldn't treat a low grade as an infrastructure failure. |
| `--html=report.html --self-contained-html` | — | Standard `pytest-html` flags; produces a self-contained, student-readable HTML report. The grader's `conftest.py` overrides the default failure rendering with a clean message box (no internal stack frames) — see `pytest_html_results_table_html` in `conftest.py`. |
| `--junitxml=junit.xml` | — | Standard pytest flag; JUnit XML for GitLab CI/GitHub Actions/Jenkins/Moodle. |
| `--json-report --json-report-file pytest_report.json` | — | Standard `pytest-json-report` flags; raw pytest-shaped JSON (different schema from `--grade-report-file`). |

### Networking / timing

| Option | Default | Description |
|---|---|---|
| `--request-timeout SECONDS` | `5.0` | Timeout for every HTTP request the grader makes. |
| `--wait-for-services` | off | Wait until all configured service URLs respond before running any test. |
| `--service-timeout SECONDS` | `60.0` | Max wait time used with `--wait-for-services`. |

`grade_report.json` schema: total possible/earned points, per-component possible/earned points,
and per-test outcome, weight, score multiplier, possible points, earned points, method, URL,
expected status, received status, expected response, received response, and failure phase
(`setup` / `request` / `status_check` / `json_parse` / `comparison` / `cleanup`). `possible_points`
is always the test's full weight; `earned_points` is `weight × score_multiplier`, so a passed test
without `--with-authentication` still counts its full weight toward `possible` but only 90% of it
toward `earned` (see [Combinations](#combinations)).

## Output formats

```bash
# Grading JSON (always on, controlled via --grade-report-file)
pytest -q ... --grade-report-file grade_report.json

# JUnit XML
pytest -q ... --junitxml=junit.xml

# Student-readable HTML
pytest -q ... --html=report.html --self-contained-html

# Raw pytest JSON report
pytest -q ... --json-report --json-report-file pytest_report.json
```

All of these can be combined in one invocation.

## Stateful tests

This is an integration-test suite, not a unit-test suite: later tests depend on data created by
earlier ones (registered users, created orders, approved/rejected assets). Run components in the
generated order (`--type all`, or rely on the cumulative ordering of `--type levelN`) and avoid
parallelizing with `pytest-xdist` unless the suite is redesigned for per-test data isolation.

## Deployment modes

The grader only needs URLs — it doesn't care how the services were started. Point
`--employee-url`/`--director-url`/`--authentication-url` at wherever they're actually running.

Example local-process / Docker Compose URLs:

```text
http://127.0.0.1:5000   (authentication)
http://127.0.0.1:5001   (employee)
http://127.0.0.1:5002   (director)
```

Example Kubernetes in-namespace URLs:

```text
http://authentication:5000
http://employee:5001
http://director:5002
```

## Test reference

Detailed reference for every test case: what it does, what request it sends, and what response it
expects. Tests run in five components, in this order, and are **stateful** — later components
depend on data created by earlier ones:

1. [`authentication_tests.py`](#1-authentication_testspy) — `/register`, `/login`, `/delete` on the auth service
2. [`level0_tests.py`](#2-level0_testspy) — `/search`, `/create_buy_order`, `/create_sell_order` on the employee service
3. [`level1_tests.py`](#3-level1_testspy) — `/pending_orders`, `/decision`, `/report` on the director service
4. [`level2_tests.py`](#4-level2_testspy) — full buy → approve → sell → approve → report cycle for one asset
5. [`level3_tests.py`](#5-level3_testspy) — rejection flow, more assets, search filter variety, multi-category reports

When `--with-authentication` is **omitted**, component 1 contributes zero tests, and every
"auth error" row described below (both the "no header" and "wrong role" flavors) is **skipped**
rather than run. All other rows in level0–3 still run, just without ever attempting to log in or attach an
`Authorization` header.

Where a test's expected result depends on `--with-blockchain`, that's called out below.

Dynamic fields (`id`, `buying_date`, `selling_date`, pending-order `uuid`) can't be pinned to an
exact value, so result fixtures in `data.py` mark them with `ANY_OBJECT_ID` / `ANY_DATE` /
`ANY_UUID` sentinels. The comparator (`evaluate_fields` in `utilities.py`) checks those fields for
presence and correct format instead of exact equality, and checks every other field exactly.

---

### 1. `authentication_tests.py`

Runs entirely against the **auth service**, and only when `--with-authentication` is passed (see
above). Registers the test employee (`john@gmail.com`) partway through, and deletes them again at
the end — so by the end of this component, the employee is unregistered and must be re-registered
by the first employee-role request in level0.

#### `/register` validation errors (tests 1–17, weight 1 each)

Each row sends a partial/invalid registration body and expects `400` with a specific message. The
validation order is: missing forename → missing surname → missing email → missing password →
invalid email format → invalid password length → duplicate email.

| # | Body | Expected message |
|---|------|-------------------|
| 1 | `{}` | `Field forename is missing.` |
| 2 | `{"forename": ""}` | `Field forename is missing.` |
| 3 | `{"forename": " "}` | `Field surname is missing.` |
| 4 | `{"forename": " ", "surname": ""}` | `Field surname is missing.` |
| 5 | `{"forename": " ", "surname": " "}` | `Field email is missing.` |
| 6 | `..., "email": ""` | `Field email is missing.` |
| 7 | `..., "email": " "` | `Field password is missing.` |
| 8 | `..., "password": ""` | `Field password is missing.` |
| 9 | `email: " "` (valid forename/surname) | `Invalid email.` |
| 10 | `email: "john"` | `Invalid email.` |
| 11 | `email: "john@"` | `Invalid email.` |
| 12 | `email: "john@gmail"` | `Invalid email.` |
| 13 | `email: "john@gmail."` | `Invalid email.` |
| 14 | `email: "john@gmail.a"` | `Invalid email.` |
| 15 | valid email, `password: " "` | `Invalid password.` |
| 16 | valid email, `password: "aaaaaaa"` (7 chars) | `Invalid password.` |
| 17 | valid fields, email = `onlymoney@gmail.com` (the seeded director's email) | `Email already exists.` |

#### `/login` validation errors (tests 18–28, weight 1 each)

| # | Body | Expected message |
|---|------|-------------------|
| 18 | `{}` | `Field email is missing.` |
| 19 | `{"email": ""}` | `Field email is missing.` |
| 20 | `{"email": " "}` | `Field password is missing.` |
| 21 | `email: " ", password: ""` | `Field password is missing.` |
| 22 | `email: "john"` | `Invalid email.` |
| 23 | `email: "john@"` | `Invalid email.` |
| 24 | `email: "john@gmail"` | `Invalid email.` |
| 25 | `email: "john@gmail."` | `Invalid email.` |
| 26 | `email: "john@gmail.a"` | `Invalid email.` |
| 27 | `john@gmail.com`, wrong password | `Invalid credentials.` |
| 28 | correct email, but employee isn't registered yet | `Invalid credentials.` |

#### `/delete` without auth (test 29, weight 1)

`POST /delete` with no `Authorization` header → `401 {"msg": "Missing Authorization Header"}`.

#### Successful registration (test 30, weight 3)

`POST /register` with the employee fixture (`forename: John, surname: Doe, email: john@gmail.com,
password: aA123456`) → `200`, no body. Marks the employee as registered for subsequent logins.

#### Director login token check (test 31, weight 3)

`POST /login` as `onlymoney@gmail.com` / `evenmoremoney` (the seeded director) → `200
{"accessToken": ...}`. The token is decoded with the configured JWT secret and checked for:
`nbf`, `exp` (1 hour after `nbf`), `type: "access"`, `sub: "onlymoney@gmail.com"`,
`forename: "Scrooge"`, `surname: "McDuck"`, and the configured roles field equal to the director
role.

#### Employee login token check (test 32, weight 7)

Same as above, but for the just-registered employee: `sub` = employee email, `forename`/`surname`
= John/Doe, roles field = employee role.

#### Successful delete (test 33, weight 2)

`POST /delete` with the employee's token → `200`, no body. Marks the employee unregistered again.

#### Post-delete checks (tests 34–35, weight 3 and 2)

- Login with the now-deleted employee's credentials → `400 {"message": "Invalid credentials."}`.
- Re-using the *old* (now invalid) token on `/delete` again → `400 {"message": "Unknown user."}`.

---

### 2. `level0_tests.py`

Runs against the **employee service**. By the end, three BUY orders are pending in Redis:
`AssetAlpha`, `AssetBeta`, `AssetZeta` (none approved yet).

#### `/search` auth errors (tests 1–2, weight 1 each — skipped without `--with-authentication`)

- No `Authorization` header → `401 {"msg": "Missing Authorization Header"}`.
- Valid **director** token (wrong role) → `401 {"msg": "Missing Authorization Header"}`.

#### `/search` empty result (test 3, weight 3)

`POST /search` with an empty filter body, as the employee → `200 {"assets": []}` (nothing has been
bought yet).

#### `/create_buy_order` auth errors (tests 4–5, weight 1 each — skipped without `--with-authentication`)

Same pattern as `/search`'s auth errors.

#### `/create_buy_order` validation errors (tests 6–13, weight 1 each)

Validation order: missing `name` → missing `categories` → missing `buying_price` → missing `info`
→ empty `categories` list → non-positive `buying_price`.

| # | Body | Expected message |
|---|------|-------------------|
| 6 | `{}` | `Field name is missing.` |
| 7 | `{"name": ""}` | `Field name is missing.` |
| 8 | `{"name": "A"}` | `Field categories is missing.` |
| 9 | `{"name": "A", "categories": ["C"]}` | `Field buying_price is missing.` |
| 10 | `..., "buying_price": 100` | `Field info is missing.` |
| 11 | `categories: [], buying_price: 100, info: {}` | `Categories list is empty.` |
| 12 | `categories: ["C"], buying_price: 0, info: {}` | `Invalid buying price.` |
| 13 | `categories: ["C"], buying_price: -100, info: {}` | `Invalid buying price.` |

#### `/create_buy_order` success (tests 14–16, weight 2 each)

Creates three pending BUY orders (each `200`, no body):

| # | Asset | Categories | Price | Info |
|---|-------|-----------|-------|------|
| 14 | AssetAlpha | Technology, Finance | 50000 | `{region: EU, risk_level: high}` |
| 15 | AssetBeta | Real Estate | 120000 | `{location: NYC, floors: 5}` |
| 16 | AssetZeta | Energy | 80000 | `{region: APAC, risk_level: medium}` |

(AssetZeta is never approved/rejected in any later test — it's left pending to prove level1's
content checks don't just count orders, they validate each one's fields by name.)

#### `/create_sell_order` auth errors (tests 17–18, weight 1 each — skipped without `--with-authentication`)

Same pattern as above.

#### `/create_sell_order` validation errors (tests 19–22, weight 1 each)

Validation order: missing `id` → invalid `id` format / not found. (`selling_price` is checked
*after* `id`, so these fixtures supply a valid-looking `selling_price` to make sure the test
actually reaches the id check rather than tripping the earlier one.)

| # | Body | Expected message |
|---|------|-------------------|
| 19 | `{}` | `Field id is missing.` |
| 20 | `{"id": ""}` | `Field id is missing.` |
| 21 | `id: "not-valid-objectid", selling_price: 20000` | `Invalid id.` |
| 22 | `id: "5f43a0d1c2a4b12345678901"` (well-formed but nonexistent), `selling_price: 20000` | `Invalid id.` |

---

### 3. `level1_tests.py`

Runs against the **director service**. Test counts/weights differ slightly by director mode.

#### `/pending_orders` auth errors (tests 1–2, weight 1 each — skipped without `--with-authentication`)

No header → `401`. Valid employee token (wrong role) → `401 {"msg": "Missing Authorization
Header"}`.

#### `/pending_orders` content check (test 3, weight 5)

`GET /pending_orders` as director → `200`. Asserts the BUY order list is **exactly**
`{AssetAlpha, AssetBeta, AssetZeta}` (no more, no fewer), and for each one, every field
(`categories`, `buying_price`, `info`) matches the level0 fixture exactly, plus `uuid` is a real
UUID and `order_type` is `"BUY"`.

#### `/decision` auth errors (tests 4–5, weight 1 each — skipped without `--with-authentication`)

Same auth pattern.

#### `/decision` validation errors shared by both modes (tests 6–8, weight 1 each)

These checks (missing/invalid `uuid`) happen before the blockchain/no-blockchain branch:

| # | Body | Expected message |
|---|------|-------------------|
| 6 | `{}` | `Field uuid is missing.` |
| 7 | `{"uuid": "not-a-uuid"}` | `Invalid uuid.` |
| 8 | `{"uuid": "550e8400-e29b-41d4-a716-446655440000"}` (well-formed, not in Redis) | `Invalid uuid.` |

#### `/decision` validation + success — **blockchain mode** (tests 9–12, weight 1/1/1/5)

| # | Body (uuid = a real pending order) | Expected |
|---|---|---|
| 9 | `voters: []` | `400 {"message": "Field voters is missing."}` |
| 10 | `voters: ["not-an-address"]` | `400 {"message": "Invalid voter address."}` |
| 11 | `voters:` 2 valid addresses (even count) | `400 {"message": "Even number of voters."}` |
| 12 | `voters:` 3 valid addresses, targeting **AssetBeta** specifically | `200`, response validated by `evaluate_decision_response(provider_url)`: `approve_transaction`/`reject_transaction` are well-formed unsigned transactions (valid Ethereum `to` address, valid hex call data) targeting the *same* address, and the two transaction objects aren't identical. No assumption is made about the contract's ABI/function names/argument encoding — the project spec doesn't dictate the contract's internal design, so students' contracts can differ. The check then inspects the chain directly (via `provider_url`) for a real contract-creation transaction whose receipt deployed a contract at that exact `to` address, confirming `/decision` actually performed an on-chain deployment rather than just returning a plausible-looking address. |

#### `/decision` validation + success — **no-blockchain mode** (tests 9–12, weight 1/1/5/2)

| # | Body (uuid = a real pending order) | Expected |
|---|---|---|
| 9 | no `approved` field | `400 {"message": "Field approved is missing."}` |
| 10 | `approved: "yes"` (not boolean) | `400 {"message": "Invalid decision."}` |
| 11 | `approved: true`, targeting **AssetBeta** specifically | `200`, no body |
| 12 | `GET /pending_orders` afterward | `200`; asserts `AssetBeta` is **no longer** in the list — proving the decision actually applied, not just returned 200 |

#### `/report` auth errors (tests 13–14, weight 1 each — skipped without `--with-authentication`)

Same auth pattern.

#### `/report` content (test 15, weight 3)

`GET /report` as director.

- **Blockchain mode**: AssetBeta's contract above is still awaiting votes (never sent in level1),
  so nothing has been finalized yet → `200 {"statistics": []}`.
- **No-blockchain mode**: AssetBeta was approved synchronously above, so it already shows up →
  `200 {"statistics": [{"category": "Real Estate", "spent": 120000, "earned": 0}]}`.

---

### 4. `level2_tests.py`

Full buy → approve → sell → approve → report cycle for **AssetAlpha**.

#### Step 1: Director approves AssetAlpha's BUY order (weight 5)

Finds AssetAlpha's pending BUY order specifically (errors out if it's not found — no silent
fallback to "any other order"). Blockchain mode: 2 of 3 voters approve, response validated by
`evaluate_decision_response`. No-blockchain mode: `{uuid, approved: true}`, `200` no body.

#### Step 2: Search for AssetAlpha after approval (weight 5)

Polls `POST /search` (no filter) until `AssetAlpha` appears (fails if it never does within 30s).
Once found, every field is checked against the `get_asset_alpha()` fixture: `name`, `categories`,
`buying_price`, `info` exactly; `id` and `buying_date` checked for presence + valid format.

#### Step 3: Create sell order for AssetAlpha (weight 2)

Looks up AssetAlpha's `id` via `/search`, then `POST /create_sell_order` with
`selling_price: 75000` → `200`, no body.

#### Steps 4–5: Sell order validation (weight 1 each)

- Missing `selling_price` → `400 {"message": "Field selling_price is missing."}`.
- `selling_price: 0` → `400 {"message": "Invalid selling price."}`.

#### Step 6: Director approves AssetAlpha's SELL order (weight 5)

Same pattern as step 1, but for the pending SELL order.

#### Step 7: Search confirms the sale (weight 5)

Polls until AssetAlpha has a `selling_price` field. Validates every field against
`get_asset_alpha_sold()` (adds `selling_price: 75000` and a valid `selling_date` to the bought
fixture).

#### Step 8: Report check (weight 5)

`GET /report` → exact match against `get_report_alpha_sold(with_blockchain)`:

- Always: `Finance` and `Technology` each `{spent: 50000, earned: 75000}` (from AssetAlpha).
- No-blockchain mode only: also `Real Estate {spent: 120000, earned: 0}` (AssetBeta, approved back
  in level1).

---

### 5. `level3_tests.py`

Covers a rejection flow, a second and third asset, search-filter variety (including nested
`info_filters`), and multi-category report checks.

#### Step 1: Create buy order for AssetGamma (weight 1)

`AssetGamma`: category `Technology`, price `30000`.

#### Step 2: Director **rejects** AssetGamma (weight 2)

Blockchain mode: 2 of 3 voters reject. No-blockchain mode: `{uuid, approved: false}`.

#### Step 3: AssetGamma absent after rejection (weight 3)

`POST /search` (no filter); blockchain mode sleeps 10s first to let the event listener process the
vote. Asserts `AssetGamma` is **not** in the results.

#### Step 4: Create buy order for AssetDelta (weight 1)

`AssetDelta`: categories `Finance`, `Real Estate`; price `200000`; info
`{sector: commercial, floors: 10}`.

#### Step 5: Director approves AssetDelta (weight 2)

Same approve pattern as level2's AssetAlpha.

#### Step 6: Search by name filter (weight 3)

`{"name": "Delta"}` — polls until found, then full-field check against `get_asset_delta()`.

#### Step 7: Search by category filter (weight 3)

`{"category": "Real Estate"}` → asserts `AssetDelta` present (full fields checked) **and**
`AssetAlpha` absent (it's Technology/Finance, not Real Estate).

#### Step 8: Search by `buying_date` filter (weight 3)

`{"buying_date": "2020-01-01T00:00:00.000Z"}` (i.e. "bought after 2020") → both `AssetAlpha`
(sold, full fields via `get_asset_alpha_sold()`) and `AssetDelta` are expected, since both were
bought well after that date.

#### Step 9: Search by `selling_date` filter (weight 3)

`{"selling_date": "2099-01-01T00:00:00.000Z"}` (i.e. "sold before 2099") → `AssetAlpha` expected
(it's the only sold asset).

#### Step 10: Search by `info_filters` (weight 3)

`[{"field": "sector", "operator": "eq", "value": "commercial"}]` → `AssetDelta` expected.

#### Step 11: Report with multiple categories (weight 5)

`GET /report` → exact match against `get_report_full(with_blockchain)`:

| Category | spent | earned |
|----------|-------|--------|
| Technology | 50000 | 75000 |
| Finance | 250000 (AssetAlpha 50000 + AssetDelta 200000) | 75000 |
| Real Estate | 200000, or 320000 in no-blockchain mode (+ AssetBeta's 120000) | 0 |

(Order matches the spec's sort: `earned` descending, then `spent` ascending, then `category`
ascending.)

#### Step 12: Create buy order for AssetEpsilon (weight 1)

`AssetEpsilon`: categories `Energy`, `Technology`; price `95000`; **nested** info object:
`{"geo": {"country": "Germany", "city": "Berlin"}, "specs": {"power_mw": 50, "renewable": true}}`.
Exists to exercise `info_filters` dot-path queries against more than one level of nesting.

#### Step 13: Director approves AssetEpsilon (weight 2)

Same approve pattern as before.

#### Step 14: Search confirms AssetEpsilon, full nested-field check (weight 3)

`POST /search` (no filter), polls until found, then validates every field — including the nested
`info.geo` and `info.specs` objects — exactly against `get_asset_epsilon()`.

#### Step 15: Search with a nested `info_filters` field (weight 3)

`info_filters: [{"field": "geo.country", "operator": "eq", "value": "Germany"}]` →
`AssetEpsilon` expected (full fields checked).

#### Step 16: Search combining two nested `info_filters` (AND semantics) (weight 3)

```json
"info_filters": [
  {"field": "specs.power_mw",  "operator": "gt", "value": 10},
  {"field": "specs.renewable", "operator": "eq", "value": true}
]
```

Both conditions must hold simultaneously → `AssetEpsilon` expected.

#### Step 17: Search combining a top-level filter with a nested `info_filters` field (weight 3)

`{"category": "Energy", "info_filters": [{"field": "geo.city", "operator": "eq", "value":
"Berlin"}]}` — confirms `category` and `info_filters` AND together: `AssetEpsilon` expected (full
fields checked), and `AssetDelta` (Finance/Real Estate, not Energy) must be **absent**.

#### Step 18: Report after AssetEpsilon (weight 5)

`GET /report` → exact match against `get_report_full_with_epsilon(with_blockchain)`. Demonstrates
that approving a new asset both grows an existing category's total and introduces a brand new one:

| Category | spent | earned |
|----------|-------|--------|
| Technology | 145000 (AssetAlpha 50000 + AssetEpsilon 95000) | 75000 |
| Finance | 250000 | 75000 |
| Energy | 95000 (AssetEpsilon, new category) | 0 |
| Real Estate | 200000, or 320000 in no-blockchain mode | 0 |
