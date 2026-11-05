"""A switched-on feature reaching a share of accounts first (item 92, D-160).

How large services ship safely: turn a feature on for 5% of accounts, watch
it, then 25%, then everyone, and back to 0 at once if it misbehaves.

Each account has a bucket from 0 to 99 for each feature, worked out from a
keyed hash of the feature's name and the account's id. A feature at 10%
reaches buckets 0 to 9, so:

- an account in at 10% is still in at 25% (nobody flickers out as it grows);
- buckets for different features are unrelated (the same 5% are not the
  first to meet everything);
- the key is the app's secret, so nobody can work out, or choose, which
  accounts are first.

The share is a setting (`FEATURE_ROLLOUT`), read only for the features whose
routes honour it (`settings.ROLLOUT_FEATURES`); the app refuses to start with
any other name, so a share can never be set on a feature that would ignore it.
"""

import hashlib
import hmac
import uuid

from app.core.config import settings

BUCKETS = 100


def bucket(feature: str, account_id: uuid.UUID) -> int:
    """This account's place, 0 to 99, in this feature's rollout."""
    digest = hmac.new(
        settings.secret_key.get_secret_value().encode(),
        f"rollout:{feature}:{account_id}".encode(),
        hashlib.sha256,
    ).digest()
    return int.from_bytes(digest[:8], "big") % BUCKETS


def share(feature: str) -> int:
    """The percentage of accounts a feature reaches when it is on: 100 unless set."""
    return settings.feature_rollout.get(feature, BUCKETS)


def includes(feature: str, account_id: uuid.UUID) -> bool:
    """Whether this account is within the feature's share."""
    return bucket(feature, account_id) < share(feature)
