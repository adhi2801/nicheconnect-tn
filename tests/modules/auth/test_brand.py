import pytest
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.modules.auth.models.brand import Brand


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_create_and_query_brand(db):
    brand = Brand(name="Acme", email="acme@example.com")
    db.add(brand)
    db.flush()

    fetched = db.query(Brand).filter_by(email="acme@example.com").one()
    assert fetched.name == "Acme"
    assert fetched.id is not None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_duplicate_email_raises_integrity_error(db):
    db.add(Brand(name="First", email="dup@example.com"))
    db.flush()

    db.add(Brand(name="Second", email="dup@example.com"))
    with pytest.raises(IntegrityError):
        db.flush()
