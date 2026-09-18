from datetime  import datetime
from jwt       import decode
from data      import get_employee
from data      import set_is_employee_registered
from utilities import equals
from utilities import set_up_pass_function
from utilities import set_up_delete_test
from utilities import set_up_delete_error_test
from utilities import run_tests


def user_register_equals(set_up_data, expected_response, received_response):
    equals(set_up_data, expected_response, received_response)
    set_is_employee_registered(True)


# ---------------------------------------------------------------------------
# Token validation helpers
# ---------------------------------------------------------------------------

def token_test(
    response,
    user,
    token_field,
    secret,
    expected_type,
    expected_subject,
    expected_forename,
    expected_surname,
    roles_field,
    expected_role,
    expected_expires_delta,
):
    assert token_field in response, (
        f"Login response error, {token_field} field missing for user {user}."
    )

    token = decode(response[token_field], key=secret, algorithms=["HS256"], leeway=60)

    assert "nbf"       in token, f"{token_field} error for user {user}, field nbf is missing."
    assert "type"      in token, f"{token_field} error for user {user}, field type is missing."
    assert "exp"       in token, f"{token_field} error for user {user}, field exp is missing."
    assert "sub"       in token, f"{token_field} error for user {user}, field sub is missing."
    assert "forename"  in token, f"{token_field} error for user {user}, field forename is missing."
    assert "surname"   in token, f"{token_field} error for user {user}, field surname is missing."
    assert roles_field in token, f"{token_field} error for user {user}, field {roles_field} is missing."

    nbf      = token["nbf"]
    typ      = token["type"]
    exp      = token["exp"]
    sub      = token["sub"]
    forename = token["forename"]
    surname  = token["surname"]
    roles    = token[roles_field]

    assert typ      == expected_type,     (f"{token_field} error for user {user}, field type has an incorrect value, " f"expected {expected_type}, got {typ}.")
    assert sub      == expected_subject,  (f"{token_field} error for user {user}, field sub has an incorrect value, " f"expected {expected_subject}, got {sub}.")
    assert forename == expected_forename, (f"{token_field} error for user {user}, field forename has an incorrect value, " f"expected {expected_forename}, got {forename}.")
    assert surname  == expected_surname,  (f"{token_field} error for user {user}, field surname has an incorrect value, " f"expected {expected_surname}, got {surname}.")

    assert (roles == expected_role) or (expected_role in roles), ( f"{token_field} error for user {user}, field {roles_field} has an incorrect value, " f"expected {expected_role}, got {roles}.")

    expires_delta = datetime.fromtimestamp(exp) - datetime.fromtimestamp(nbf)
    assert expires_delta.total_seconds() == expected_expires_delta, (
        f"{token_field} error for user {user}, expiration has an incorrect value, "
        f"expected {expected_expires_delta}, got {expires_delta.total_seconds()}."
    )


# ---------------------------------------------------------------------------
# Director token wrappers
# ---------------------------------------------------------------------------

def director_token_test(response, token_field, secret, expected_type, roles_field, expected_role, expected_expires_delta):
    token_test(
        response               = response,
        user                   = "director",
        token_field            = token_field,
        secret                 = secret,
        expected_type          = expected_type,
        expected_subject       = "onlymoney@gmail.com",
        expected_forename      = "Scrooge",
        expected_surname       = "McDuck",
        roles_field            = roles_field,
        expected_role          = expected_role,
        expected_expires_delta = expected_expires_delta,
    )


def director_access_token_test_wrapper(response, secret, roles_field, expected_role):
    director_token_test(
        response               = response,
        token_field            = "accessToken",
        secret                 = secret,
        expected_type          = "access",
        roles_field            = roles_field,
        expected_role          = expected_role,
        expected_expires_delta = 60 * 60,
    )


def director_access_token_test(jwt_secret, roles_field, director_role):
    def implementation(set_up_data, expected_response, received_response):
        director_access_token_test_wrapper(
            response      = received_response,
            secret        = jwt_secret,
            roles_field   = roles_field,
            expected_role = director_role,
        )
    return implementation


# ---------------------------------------------------------------------------
# Employee token wrappers
# ---------------------------------------------------------------------------

def employee_token_test(response, token_field, secret, expected_type, roles_field, expected_role, expected_expires_delta):
    token_test(
        response               = response,
        user                   = get_employee()["forename"] + get_employee()["surname"],
        token_field            = token_field,
        secret                 = secret,
        expected_type          = expected_type,
        expected_subject       = get_employee()["email"],
        expected_forename      = get_employee()["forename"],
        expected_surname       = get_employee()["surname"],
        roles_field            = roles_field,
        expected_role          = expected_role,
        expected_expires_delta = expected_expires_delta,
    )


def employee_access_token_test_wrapper(response, secret, roles_field, expected_role):
    employee_token_test(
        response               = response,
        token_field            = "accessToken",
        secret                 = secret,
        expected_type          = "access",
        roles_field            = roles_field,
        expected_role          = expected_role,
        expected_expires_delta = 60 * 60,
    )


def employee_access_token_test(jwt_secret, roles_field, employee_role):
    def implementation(set_up_data, expected_response, received_response):
        employee_access_token_test_wrapper(
            response      = received_response,
            secret        = jwt_secret,
            roles_field   = roles_field,
            expected_role = employee_role,
        )
    return implementation


def employee_delete_equals(set_up_data, expected_response, received_response):
    equals(set_up_data, expected_response, received_response)
    set_is_employee_registered(False)


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

def run_authentication_tests(authentication_url, jwt_secret, roles_field, employee_role, director_role):
    tokens = []

    tests = [
        # ------------------------------------------------------------------
        # /register validation errors  (tests 1-17)
        # ------------------------------------------------------------------
        ["post", authentication_url + "/register", set_up_pass_function, {}, {},                                                                                              { }, 400, {"message": "Field forename is missing."}, equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": ""},                                                                                { }, 400, {"message": "Field forename is missing."}, equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": " "},                                                                               { }, 400, {"message": "Field surname is missing."},  equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": " ", "surname": ""},                                                                { }, 400, {"message": "Field surname is missing."},  equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": " ", "surname": " "},                                                               { }, 400, {"message": "Field email is missing."},    equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": " ", "surname": " ", "email": ""},                                                  { }, 400, {"message": "Field email is missing."},    equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": " ", "surname": " ", "email": " "},                                                 { }, 400, {"message": "Field password is missing."}, equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": " ", "surname": " ", "email": " ", "password": ""},                                 { }, 400, {"message": "Field password is missing."}, equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": "John", "surname": "Doe", "email": " ",            "password": " "},                { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": "John", "surname": "Doe", "email": "john",         "password": " "},                { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": "John", "surname": "Doe", "email": "john@",        "password": " "},                { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": "John", "surname": "Doe", "email": "john@gmail",   "password": " "},                { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": "John", "surname": "Doe", "email": "john@gmail.",  "password": " "},                { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": "John", "surname": "Doe", "email": "john@gmail.a", "password": " "},                { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": "John", "surname": "Doe", "email": "john@gmail.com", "password": " "},              { }, 400, {"message": "Invalid password."},          equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": "John", "surname": "Doe", "email": "john@gmail.com", "password": "aaaaaaa"},        { }, 400, {"message": "Invalid password."},          equals, 1],
        ["post", authentication_url + "/register", set_up_pass_function, {}, {"forename": "John", "surname": "Doe", "email": "onlymoney@gmail.com", "password": "Aaaaaaaa1"}, { }, 400, {"message": "Email already exists."},      equals, 1],

        # ------------------------------------------------------------------
        # /login validation errors  (tests 18-27)
        # ------------------------------------------------------------------
        ["post", authentication_url + "/login", set_up_pass_function, {}, {},                                                                         { }, 400, {"message": "Field email is missing."},    equals, 1],
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": ""},                                                              { }, 400, {"message": "Field email is missing."},    equals, 1],
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": " "},                                                             { }, 400, {"message": "Field password is missing."}, equals, 1],
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": " ", "password": ""},                                             { }, 400, {"message": "Field password is missing."}, equals, 1],
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": "john",        "password": " "},                                  { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": "john@",       "password": " "},                                  { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": "john@gmail",  "password": " "},                                  { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": "john@gmail.", "password": " "},                                  { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": "john@gmail.a","password": " "},                                  { }, 400, {"message": "Invalid email."},             equals, 1],
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": "john@gmail.com", "password": "wrongpass123"},                    { }, 400, {"message": "Invalid credentials."},       equals, 1],
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": get_employee()["email"], "password": get_employee()["password"]}, { }, 400, {"message": "Invalid credentials."},       equals, 1],

        # ------------------------------------------------------------------
        # /delete without auth header  (test 28)
        # ------------------------------------------------------------------
        ["post", authentication_url + "/delete", set_up_pass_function, {}, {}, { }, 401, {"msg": "Missing Authorization Header"}, equals, 1],

        # ------------------------------------------------------------------
        # Successful /register for employee  (test 29, weight 3)
        # ------------------------------------------------------------------
        ["post", authentication_url + "/register", set_up_pass_function, {}, get_employee(), { }, 200, None, user_register_equals, 3],

        # ------------------------------------------------------------------
        # Director login - validate token  (test 30, weight 3)
        # ------------------------------------------------------------------
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": "onlymoney@gmail.com", "password": "evenmoremoney"}, { }, 200, {}, director_access_token_test(jwt_secret, roles_field, director_role), 3],

        # ------------------------------------------------------------------
        # Employee login - validate token  (test 31, weight 7)
        # ------------------------------------------------------------------
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": get_employee()["email"], "password": get_employee()["password"]}, { }, 200, {}, employee_access_token_test(jwt_secret, roles_field, employee_role), 7],

        # ------------------------------------------------------------------
        # Successful /delete for employee  (test 32, weight 2)
        # ------------------------------------------------------------------
        ["post", authentication_url + "/delete", set_up_delete_test(True, authentication_url, tokens), {}, {}, { }, 200, None, employee_delete_equals, 2],

        # ------------------------------------------------------------------
        # Login after delete fails  (test 33, weight 3)
        # ------------------------------------------------------------------
        ["post", authentication_url + "/login", set_up_pass_function, {}, {"email": get_employee()["email"], "password": get_employee()["password"]}, { }, 400, {"message": "Invalid credentials."}, equals, 3],

        # ------------------------------------------------------------------
        # Delete again fails with "Unknown user."  (test 34, weight 2)
        # ------------------------------------------------------------------
        ["post", authentication_url + "/delete", set_up_delete_error_test(True, tokens, 0), {}, {}, { }, 400, {"message": "Unknown user."}, equals, 2],
    ]

    percentage = run_tests(tests)
    return percentage
