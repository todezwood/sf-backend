from app.crud import count_contacts, create_contact
from app.database import SessionLocal
from app.schemas import AddressCreate, ContactCreate

SAMPLE_CONTACTS = [
    ContactCreate(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        phone="+1-415-555-0101",
        company="Analytical Engines",
        job_title="Mathematician",
        addresses=[
            AddressCreate(type="Work", city="San Francisco", state="CA", country="USA"),
            AddressCreate(type="Home", city="London", country="UK"),
        ],
        notes="First programmer.",
    ),
    ContactCreate(
        first_name="Grace",
        last_name="Hopper",
        email="grace@example.com",
        phone="+1-415-555-0102",
        company="US Navy",
        job_title="Rear Admiral",
        addresses=[AddressCreate(type="Home", city="Arlington", state="VA", country="USA")],
    ),
    ContactCreate(
        first_name="Alan",
        last_name="Turing",
        email="alan@example.com",
        phone="+44-20-5555-0103",
        company="Bletchley Park",
        job_title="Cryptanalyst",
        addresses=[AddressCreate(type="Work", city="London", country="UK")],
    ),
]


def seed_if_empty() -> int:
    """Insert sample contacts when the database has none. Returns rows added."""
    with SessionLocal() as db:
        if count_contacts(db) > 0:
            return 0
        for contact in SAMPLE_CONTACTS:
            create_contact(db, contact)
        return len(SAMPLE_CONTACTS)
