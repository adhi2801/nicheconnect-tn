"""Reading Meta's signed_request (item 29, D-134): genuine ones pass, nothing else."""

import base64
import json

from hypothesis import given
from hypothesis import strategies as st

from app.modules.profiles.meta_signed_request import sign, user_id_from

SECRET = "test-meta-app-secret"
GOOD = {"algorithm": "HMAC-SHA256", "user_id": "17841400000000001", "issued_at": 1}


def test_a_genuine_request_gives_its_user():
    assert user_id_from(sign(GOOD, SECRET), SECRET) == "17841400000000001"


def test_a_numeric_user_id_is_read_as_text():
    assert user_id_from(sign(GOOD | {"user_id": 42}, SECRET), SECRET) == "42"


def test_another_secret_is_refused():
    assert user_id_from(sign(GOOD, "another"), SECRET) is None


def test_another_algorithm_is_refused():
    assert user_id_from(sign(GOOD | {"algorithm": "none"}, SECRET), SECRET) is None


def test_a_payload_swapped_under_a_genuine_signature_is_refused():
    signature, _ = sign(GOOD, SECRET).split(".")
    forged = (
        base64.urlsafe_b64encode(json.dumps(GOOD | {"user_id": "1"}).encode())
        .decode()
        .rstrip("=")
    )

    assert user_id_from(f"{signature}.{forged}", SECRET) is None


def test_odd_user_ids_are_refused():
    for user_id in (None, True, "", "abc", "1" * 65, ["1"], {"id": 1}):
        assert user_id_from(sign(GOOD | {"user_id": user_id}, SECRET), SECRET) is None


@given(st.text(max_size=300))
def test_no_string_but_a_signed_one_ever_passes(text):
    assert user_id_from(text, SECRET) is None


@given(st.integers(min_value=0, max_value=200), st.characters(codec="ascii"))
def test_changing_any_one_character_breaks_it(position, replacement):
    genuine = sign(GOOD, SECRET)
    position %= len(genuine)
    if genuine[position] == replacement:
        return
    tampered = genuine[:position] + replacement + genuine[position + 1 :]

    assert user_id_from(tampered, SECRET) in (None, "17841400000000001")
    # Only a change base64 reads as the same bytes may survive; never another user.


def test_an_oversized_request_is_refused_before_any_work():
    assert user_id_from("a" * 5000 + "." + "b", SECRET) is None
