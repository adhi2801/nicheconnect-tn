"""The database owner, for the few tests that need more than the app's login (item 97, D-100).

CI runs the suite as the app's own login (`nicheconnect_app`), which may read
and write rows and nothing more, so any code that quietly needs the owner
fails there. A test that genuinely needs the owner, to make a scratch
schema, to show a trigger refusing, or to set the triggers aside while it
cleans up, says so:

- with the `owner` marker, when the test's own `db` session must be the
  owner's (CI runs those tests in a second pass, as the owner);
- or through `owner_engine` below, for work beside the test's session.

`OWNER_DATABASE_URL` names the owner. On a laptop it is unset, DATABASE_URL
is already the owner, and both are the same.
"""

import os

from sqlalchemy import create_engine

from app.db.session import engine

OWNER_DATABASE_URL = os.environ.get("OWNER_DATABASE_URL")

owner_engine = create_engine(OWNER_DATABASE_URL) if OWNER_DATABASE_URL else engine
