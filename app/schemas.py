import base64
import binascii
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator

# Photos are stored inline as base64 data URLs. SVG is deliberately excluded:
# it can carry scripts, and none of the allowed rasters can.
_PHOTO_DATA_URL = re.compile(r"^data:image/(png|jpeg|webp|gif);base64,")
# ≈1.5 MB decoded — plenty for an avatar, small enough to keep payloads sane.
MAX_PHOTO_CHARS = 2_000_000


def validate_photo(value: str | None) -> str | None:
    """Shared check for every write path that accepts a photo."""
    if value is None:
        return None
    if len(value) > MAX_PHOTO_CHARS:
        raise ValueError(f"Photo must be at most {MAX_PHOTO_CHARS} characters (about 1.5 MB decoded)")
    match = _PHOTO_DATA_URL.match(value)
    if match is None:
        raise ValueError("Photo must be a data URL of type image/png, image/jpeg, image/webp, or image/gif")
    if match.end() == len(value):
        raise ValueError("Photo payload is empty")
    try:
        base64.b64decode(value[match.end() :], validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Photo payload is not valid base64") from None
    return value


AddressType = Literal["Home", "Work", "Other"]

_ADDRESS_EXAMPLE = {
    "type": "Work",
    "street": "1 Market St, Suite 400",
    "city": "San Francisco",
    "state": "CA",
    "postal_code": "94105",
    "country": "USA",
}


class AddressBase(BaseModel):
    """One postal address belonging to a contact."""

    type: AddressType = Field(
        default="Home",
        description="What kind of address this is: Home, Work, or Other.",
        examples=["Work"],
    )
    street: str | None = Field(
        default=None,
        max_length=300,
        description="Street address, including unit or suite.",
        examples=["1 Market St, Suite 400"],
    )
    city: str | None = Field(default=None, max_length=120, description="City or locality.", examples=["San Francisco"])
    state: str | None = Field(
        default=None,
        max_length=120,
        description="State, province, or region.",
        examples=["CA"],
    )
    postal_code: str | None = Field(
        default=None,
        max_length=20,
        description="Postal or ZIP code.",
        examples=["94105"],
    )
    country: str | None = Field(default=None, max_length=120, description="Country name.", examples=["USA"])


class AddressCreate(AddressBase):
    """An address as sent by clients when creating or replacing a contact."""


class AddressRead(AddressBase):
    """A stored address, as returned inside every contact response."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Server-assigned identifier.", examples=[1])


class ContactBase(BaseModel):
    """Fields shared by every contact request and response."""

    first_name: str = Field(
        min_length=1,
        max_length=100,
        description="Given name. Required, must not be blank.",
        examples=["Ada"],
    )
    last_name: str = Field(
        min_length=1,
        max_length=100,
        description="Family name. Required, must not be blank.",
        examples=["Lovelace"],
    )
    email: EmailStr = Field(
        max_length=320,
        description=(
            "Primary email address. Required and unique across all contacts; "
            "compared case-insensitively and stored lowercased."
        ),
        examples=["ada@example.com"],
    )
    phone: str | None = Field(
        default=None,
        max_length=40,
        description="Phone number. Stored verbatim — any format is accepted.",
        examples=["+1-415-555-0101"],
    )
    company: str | None = Field(
        default=None,
        max_length=200,
        description="Employer or organisation name.",
        examples=["Analytical Engines"],
    )
    job_title: str | None = Field(
        default=None,
        max_length=200,
        description="Role held at the company.",
        examples=["Mathematician"],
    )
    notes: str | None = Field(
        default=None,
        description="Free-form notes about the contact. No length limit.",
        examples=["Met at the SF hackathon."],
    )
    photo: str | None = Field(
        default=None,
        description=(
            "Contact photo as a base64 data URL (image/png, image/jpeg, "
            "image/webp, or image/gif). At most 2,000,000 characters."
        ),
        examples=["data:image/png;base64,iVBORw0KGgo="],
    )


_FULL_EXAMPLE = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "phone": "+1-415-555-0101",
    "company": "Analytical Engines",
    "job_title": "Mathematician",
    "addresses": [_ADDRESS_EXAMPLE],
    "notes": "Met at the SF hackathon.",
}
_MINIMAL_EXAMPLE = {"first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com"}


class _ValidatesPhoto(BaseModel):
    """Write-side photo validation. Read models skip re-checking stored data."""

    @field_validator("photo", check_fields=False)
    @classmethod
    def _photo_is_a_safe_image(cls, value: str | None) -> str | None:
        return validate_photo(value)


class _AcceptsAddresses(BaseModel):
    """The nested address list every write body accepts, capped per contact."""

    addresses: list[AddressCreate] = Field(
        default_factory=list,
        max_length=10,
        description="The contact's postal addresses, at most 10. Replaces the stored list.",
        examples=[[_ADDRESS_EXAMPLE]],
    )


class ContactCreate(ContactBase, _AcceptsAddresses, _ValidatesPhoto):
    """Body of `POST /api/v1/contacts`. Only the two names and email are required."""

    model_config = ConfigDict(json_schema_extra={"examples": [_FULL_EXAMPLE, _MINIMAL_EXAMPLE]})


class ContactReplace(ContactBase, _AcceptsAddresses, _ValidatesPhoto):
    """
    Body of `PUT /api/v1/contacts/{contact_id}`.

    This is a full replacement: any optional field you omit is set back to `null`,
    and an omitted address list becomes empty. Use `PATCH` to change some fields.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [_FULL_EXAMPLE]})


class ContactUpdate(_ValidatesPhoto):
    """
    Body of `PATCH /api/v1/contacts/{contact_id}`.

    Every field is optional. Only the fields actually present in the request are
    written; omitted fields keep their current value. Sending an explicit `null`
    clears that field.
    """

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"phone": "+1-415-555-0199", "job_title": "Chief Engineer"}]}
    )

    first_name: str | None = Field(default=None, min_length=1, max_length=100, description="New given name.")
    last_name: str | None = Field(default=None, min_length=1, max_length=100, description="New family name.")
    email: EmailStr | None = Field(
        default=None,
        max_length=320,
        description="New email address. Must not belong to another contact.",
    )
    phone: str | None = Field(default=None, max_length=40, description="New phone number.")
    company: str | None = Field(default=None, max_length=200, description="New company.")
    job_title: str | None = Field(default=None, max_length=200, description="New job title.")
    notes: str | None = Field(default=None, description="New notes; replaces the existing text.")
    addresses: list[AddressCreate] | None = Field(
        default=None,
        max_length=10,
        description="Replaces the whole address list when present; omit to keep it.",
    )
    photo: str | None = Field(
        default=None,
        description="New photo as a base64 data URL; an explicit `null` removes it.",
    )


class ContactRead(ContactBase):
    """A stored contact, as returned by every contact endpoint."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    **_FULL_EXAMPLE,
                    "id": 1,
                    "full_name": "Ada Lovelace",
                    "created_at": "2026-08-19T16:22:58.189507Z",
                    "updated_at": "2026-08-19T16:22:58.189511Z",
                }
            ]
        },
    )

    id: int = Field(description="Server-assigned identifier.", examples=[1])
    addresses: list[AddressRead] = Field(
        default_factory=list,
        description="The contact's postal addresses, oldest first.",
        examples=[[{**_ADDRESS_EXAMPLE, "id": 1}]],
    )
    created_at: datetime = Field(
        description="UTC timestamp of when the contact was created.",
        examples=["2026-08-19T16:22:58.189507Z"],
    )
    updated_at: datetime = Field(
        description="UTC timestamp of the last modification.",
        examples=["2026-08-19T16:22:58.189511Z"],
    )

    @field_validator("created_at", "updated_at")
    @classmethod
    def _as_utc(cls, value: datetime) -> datetime:
        # SQLite discards tzinfo on write; the stored values are UTC, so label
        # them as such rather than emitting an ambiguous naive timestamp.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    @computed_field(description="Convenience concatenation of first and last name.", examples=["Ada Lovelace"])
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class ContactPage(BaseModel):
    """One page of contacts plus the totals a client needs to paginate."""

    items: list[ContactRead] = Field(description="Contacts on this page, ordered by the requested sort.")
    total: int = Field(
        description="Total contacts matching the query, ignoring `limit` and `offset`.",
        examples=[42],
    )
    limit: int = Field(description="Page size that was applied.", examples=[50])
    offset: int = Field(description="Number of records skipped.", examples=[0])


class HealthResponse(BaseModel):
    """Result of the liveness probe."""

    status: str = Field(description="Always `ok` when the service can serve traffic.", examples=["ok"])
    database: str = Field(description="Active SQLAlchemy dialect.", examples=["sqlite"])
    contacts: int = Field(description="Number of contacts currently stored.", examples=[3])


class RootResponse(BaseModel):
    """Discovery document listing the API's entry points."""

    name: str = Field(description="Human-readable service name.", examples=["Contacts API"])
    version: str = Field(description="Service version.", examples=["0.1.0"])
    docs: str = Field(description="Path to the Swagger UI.", examples=["/docs"])
    redoc: str = Field(description="Path to the ReDoc UI.", examples=["/redoc"])
    openapi: str = Field(description="Path to the OpenAPI 3.1 document.", examples=["/openapi.json"])
    contacts: str = Field(description="Base path of the contacts collection.", examples=["/api/v1/contacts"])
    health: str = Field(description="Path to the liveness probe.", examples=["/health"])


class ErrorResponse(BaseModel):
    """Shape of every non-validation error returned by the API."""

    detail: str = Field(
        description="Human-readable explanation of the failure.",
        examples=["Contact 42 not found"],
    )
