import base64

BASE = "/api/v1/contacts"

PHOTO = "data:image/png;base64," + base64.b64encode(b"not-a-real-png").decode()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"


def test_create_contact(client, payload):
    response = client.post(BASE, json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["email"] == "ada@example.com"
    assert body["full_name"] == "Ada Lovelace"
    assert body["created_at"] and body["updated_at"]


def test_create_requires_valid_email(client, payload):
    response = client.post(BASE, json={**payload, "email": "not-an-email"})
    assert response.status_code == 422


def test_create_requires_names(client, payload):
    response = client.post(BASE, json={**payload, "first_name": ""})
    assert response.status_code == 422


def test_duplicate_email_conflicts(client, payload):
    assert client.post(BASE, json=payload).status_code == 201
    response = client.post(BASE, json={**payload, "email": "ADA@example.com"})
    assert response.status_code == 409


def test_get_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.get(f"{BASE}/{contact_id}")
    assert response.status_code == 200
    assert response.json()["id"] == contact_id


def test_get_missing_contact_returns_404(client):
    assert client.get(f"{BASE}/9999").status_code == 404


def test_list_pagination_and_total(client, payload):
    for index in range(5):
        client.post(BASE, json={**payload, "email": f"user{index}@example.com"})

    response = client.get(BASE, params={"limit": 2, "offset": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2 and body["offset"] == 2


def test_list_search(client, payload):
    client.post(BASE, json=payload)
    client.post(
        BASE,
        json={**payload, "first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com", "company": "US Navy"},
    )

    hits = client.get(BASE, params={"search": "hopper"}).json()
    assert hits["total"] == 1
    assert hits["items"][0]["last_name"] == "Hopper"

    by_company = client.get(BASE, params={"search": "navy"}).json()
    assert by_company["total"] == 1

    misses = client.get(BASE, params={"search": "nobody"}).json()
    assert misses["total"] == 0


def test_list_sorting(client, payload):
    client.post(BASE, json={**payload, "last_name": "Zhang", "email": "z@example.com"})
    client.post(BASE, json={**payload, "last_name": "Adams", "email": "a@example.com"})

    names = [
        item["last_name"]
        for item in client.get(BASE, params={"sort_by": "last_name", "order": "asc"}).json()["items"]
    ]
    assert names == ["Adams", "Zhang"]


def test_list_rejects_bad_sort_field(client):
    assert client.get(BASE, params={"sort_by": "; DROP TABLE contacts"}).status_code == 422


def test_patch_updates_only_sent_fields(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"phone": "+1-000-000-0000"})
    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "+1-000-000-0000"
    assert body["first_name"] == "Ada"
    assert body["company"] == "Analytical Engines"


def test_patch_duplicate_email_conflicts(client, payload):
    first = client.post(BASE, json=payload).json()["id"]
    client.post(BASE, json={**payload, "email": "grace@example.com"})
    response = client.patch(f"{BASE}/{first}", json={"email": "grace@example.com"})
    assert response.status_code == 409


def test_patch_same_email_is_allowed(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"email": payload["email"]})
    assert response.status_code == 200


def test_put_replaces_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.put(
        f"{BASE}/{contact_id}",
        json={"first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Grace Hopper"
    assert body["company"] is None  # omitted fields are cleared by PUT


def test_put_missing_contact_returns_404(client):
    response = client.put(
        f"{BASE}/9999",
        json={"first_name": "A", "last_name": "B", "email": "ab@example.com"},
    )
    assert response.status_code == 404


def test_delete_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    assert client.delete(f"{BASE}/{contact_id}").status_code == 204
    assert client.get(f"{BASE}/{contact_id}").status_code == 404
    assert client.delete(f"{BASE}/{contact_id}").status_code == 404


def test_root_lists_entrypoints(client):
    body = client.get("/").json()
    assert body["contacts"] == BASE


def test_create_contact_with_photo(client, payload):
    response = client.post(BASE, json={**payload, "photo": PHOTO})
    assert response.status_code == 201
    assert response.json()["photo"] == PHOTO


def test_photo_rejects_svg_data_url(client, payload):
    svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg/>").decode()
    response = client.post(BASE, json={**payload, "photo": svg})
    assert response.status_code == 422


def test_photo_rejects_empty_payload(client, payload):
    response = client.post(BASE, json={**payload, "photo": "data:image/png;base64,"})
    assert response.status_code == 422


def test_photo_rejects_invalid_base64(client, payload):
    response = client.post(BASE, json={**payload, "photo": "data:image/png;base64,%%not-base64%%"})
    assert response.status_code == 422


def test_put_without_photo_clears_it(client, payload):
    contact_id = client.post(BASE, json={**payload, "photo": PHOTO}).json()["id"]
    response = client.put(
        f"{BASE}/{contact_id}",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["photo"] is None  # PUT is a full replace


def test_photo_rejects_oversize_payload(client, payload):
    huge = "data:image/png;base64," + "A" * 2_000_000
    response = client.post(BASE, json={**payload, "photo": huge})
    assert response.status_code == 422


def test_patch_preserves_photo_when_omitted(client, payload):
    contact_id = client.post(BASE, json={**payload, "photo": PHOTO}).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"job_title": "Chief Engineer"})
    assert response.status_code == 200
    assert response.json()["photo"] == PHOTO


def test_patch_null_clears_photo(client, payload):
    contact_id = client.post(BASE, json={**payload, "photo": PHOTO}).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"photo": None})
    assert response.status_code == 200
    assert response.json()["photo"] is None


def test_init_db_adds_photo_column_to_legacy_table():
    from sqlalchemy import inspect

    from app.database import Base, engine, init_db

    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE contacts (id INTEGER PRIMARY KEY, first_name VARCHAR(100),"
            " last_name VARCHAR(100), email VARCHAR(320))"
        )

    init_db()

    columns = {column["name"] for column in inspect(engine).get_columns("contacts")}
    assert "photo" in columns


def test_put_replaces_existing_photo(client, payload):
    contact_id = client.post(BASE, json={**payload, "photo": PHOTO}).json()["id"]
    new_photo = "data:image/jpeg;base64," + base64.b64encode(b"another-image").decode()
    response = client.put(f"{BASE}/{contact_id}", json={**payload, "photo": new_photo})
    assert response.status_code == 200
    assert response.json()["photo"] == new_photo
