from utilities import equals
from utilities import run_tests
from utilities import set_up_authorization_error_request
from utilities import skip_unless_with_authentication
from utilities import set_up_director_headers
from utilities import set_up_employee_headers
from data      import get_buy_order0
from data      import get_buy_order1
from data      import get_buy_order2
from data      import get_buy_order_error0
from data      import get_buy_order_error1
from data      import get_buy_order_error2
from data      import get_buy_order_error3
from data      import get_buy_order_error4
from data      import get_buy_order_error5
from data      import get_buy_order_error6
from data      import get_buy_order_error7
from data      import get_sell_order_error0
from data      import get_sell_order_error1
from data      import get_sell_order_error2
from data      import get_sell_order_error3
from data      import get_search_empty


def run_level0_tests(with_authentication, authentication_url, employee_url):

    tests = [
        # ------------------------------------------------------------------
        # /search auth errors (tests 1-2, weight 1 each)
        # ------------------------------------------------------------------
        ["post", employee_url + "/search", set_up_authorization_error_request(with_authentication),                                                                {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],
        ["post", employee_url + "/search", skip_unless_with_authentication(with_authentication, set_up_director_headers(with_authentication, authentication_url)), {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],

        # ------------------------------------------------------------------
        # /search empty result (test 3, weight 3)
        # ------------------------------------------------------------------
        ["post", employee_url + "/search", set_up_employee_headers(with_authentication, authentication_url), {}, {}, {}, 200, get_search_empty(), equals, 3],

        # ------------------------------------------------------------------
        # /create_buy_order auth errors (tests 4-5, weight 1 each)
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_buy_order", set_up_authorization_error_request(with_authentication),                                                                {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],
        ["post", employee_url + "/create_buy_order", skip_unless_with_authentication(with_authentication, set_up_director_headers(with_authentication, authentication_url)), {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],

        # ------------------------------------------------------------------
        # /create_buy_order validation errors (tests 6-13, weight 1 each)
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order_error0(), {}, 400, {"message": "Field name is missing."},           equals, 1],
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order_error1(), {}, 400, {"message": "Field name is missing."},           equals, 1],
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order_error2(), {}, 400, {"message": "Field categories is missing."},     equals, 1],
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order_error3(), {}, 400, {"message": "Field buying_price is missing."},   equals, 1],
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order_error4(), {}, 400, {"message": "Field info is missing."},           equals, 1],
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order_error5(), {}, 400, {"message": "Categories list is empty."},        equals, 1],
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order_error6(), {}, 400, {"message": "Invalid buying price."},            equals, 1],
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order_error7(), {}, 400, {"message": "Invalid buying price."},            equals, 1],

        # ------------------------------------------------------------------
        # /create_buy_order success (tests 14-16, weight 2 each)
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order0(), {}, 200, None, equals, 2],
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order1(), {}, 200, None, equals, 2],
        ["post", employee_url + "/create_buy_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_buy_order2(), {}, 200, None, equals, 2],

        # ------------------------------------------------------------------
        # /create_sell_order auth errors (tests 17-18, weight 1 each)
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_sell_order", set_up_authorization_error_request(with_authentication),                                                                {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],
        ["post", employee_url + "/create_sell_order", skip_unless_with_authentication(with_authentication, set_up_director_headers(with_authentication, authentication_url)), {}, {}, {}, 401, {"msg": "Missing Authorization Header"}, equals, 1],

        # ------------------------------------------------------------------
        # /create_sell_order validation errors (tests 19-22, weight 1 each)
        # ------------------------------------------------------------------
        ["post", employee_url + "/create_sell_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_sell_order_error0(), {}, 400, {"message": "Field id is missing."}, equals, 1],
        ["post", employee_url + "/create_sell_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_sell_order_error1(), {}, 400, {"message": "Field id is missing."}, equals, 1],
        ["post", employee_url + "/create_sell_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_sell_order_error2(), {}, 400, {"message": "Invalid id."},          equals, 1],
        ["post", employee_url + "/create_sell_order", set_up_employee_headers(with_authentication, authentication_url), {}, get_sell_order_error3(), {}, 400, {"message": "Invalid id."},          equals, 1],
    ]

    percentage = run_tests(tests)
    return percentage
