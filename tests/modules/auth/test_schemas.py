import pytest
from pydantic import ValidationError

from app.modules.auth.schemas import OtpRequestIn, OtpVerifyIn


def error_messages(exc_info) -> dict[str, str]:
    return {str(error["loc"][0]): error["msg"] for error in exc_info.value.errors()}


@pytest.mark.parametrize(
    "typed",
    [
        "9876543210",
        "+919876543210",
        "+91 98765 43210",
        "98765-43210",
        "(98765) 43210",
        "919876543210",
        "09876543210",
        "  9876543210  ",
    ],
)
def test_common_ways_of_typing_a_mobile_are_normalised(typed):
    assert OtpRequestIn(phone=typed).phone == "+919876543210"


@pytest.mark.parametrize(
    "typed",
    [
        "5876543210",  # Indian mobiles start 6-9
        "987654321",  # 9 digits
        "98765432101",  # 11 digits, no leading 0
        "+14155550123",  # not Indian
        "+9198765432a0",
        "",
        "phone",
        "+91",
    ],
)
def test_invalid_mobile_is_rejected_with_a_friendly_message(typed):
    with pytest.raises(ValidationError) as exc_info:
        OtpRequestIn(phone=typed)

    assert error_messages(exc_info) == {
        "phone": "Enter a valid 10-digit Indian mobile number"
    }


def test_mobile_given_as_a_number_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        OtpRequestIn(phone=9876543210)

    assert "phone" in error_messages(exc_info)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError) as exc_info:
        OtpRequestIn(phone="9876543210", role="admin")

    assert "role" in error_messages(exc_info)


def test_valid_verify_request():
    body = OtpVerifyIn(phone="98765 43210", code=" 042917 ", role="brand")

    assert body.phone == "+919876543210"
    assert body.code == "042917"
    assert body.role == "brand"


@pytest.mark.parametrize("code", ["12345", "1234567", "12a456", "", "١٢٣٤٥٦", 123456])
def test_code_must_be_six_plain_digits(code):
    with pytest.raises(ValidationError) as exc_info:
        OtpVerifyIn(phone="9876543210", code=code, role="creator")

    assert error_messages(exc_info) == {"code": "Enter the 6-digit code we sent you"}


@pytest.mark.parametrize("role", ["admin", "Brand", ""])
def test_unknown_role_is_rejected(role):
    with pytest.raises(ValidationError) as exc_info:
        OtpVerifyIn(phone="9876543210", code="123456", role=role)

    assert "role" in error_messages(exc_info)


@pytest.mark.parametrize("missing", ["phone", "code", "role"])
def test_verify_fields_are_required(missing):
    values = {"phone": "9876543210", "code": "123456", "role": "creator"}
    del values[missing]

    with pytest.raises(ValidationError) as exc_info:
        OtpVerifyIn(**values)

    assert missing in error_messages(exc_info)
