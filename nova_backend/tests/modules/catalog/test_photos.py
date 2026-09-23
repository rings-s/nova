"""Business photos: upload, the rules around them, and who may see them.
Needs Postgres. Files go to a temporary store per test.
"""

import io
import time
from uuid import uuid4

import pytest
from PIL import Image

from app.core.security import Principal, PrincipalKind, get_principal
from app.integrations.storage import LocalImageStore
from app.modules.catalog import dependencies as catalog_dependencies
from app.modules.catalog.domain import MAX_GALLERY_PHOTOS
from app.modules.identity.domain import MembershipRole
from app.modules.identity.models import Membership, User

DISCOVERY = "/api/v1/discovery"


@pytest.fixture
def store(tmp_path, monkeypatch) -> LocalImageStore:
    store = LocalImageStore(tmp_path)
    monkeypatch.setattr(catalog_dependencies, "get_image_store", lambda: store)
    return store


def _jpeg(color=(180, 90, 60), size=(800, 600)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="JPEG")
    return out.getvalue()


def _photos(tenant_id, business_id) -> str:
    return f"/api/v1/tenants/{tenant_id}/catalog/businesses/{business_id}/photos"


async def _upload(client, business, kind="gallery", data=None):
    return await client.post(
        _photos(business.tenant_id, business.id),
        params={"kind": kind},
        content=data if data is not None else _jpeg(),
        headers={"content-type": "image/jpeg"},
    )


@pytest.fixture
async def listed(tenant_factory, business_factory, location_factory):
    business = await business_factory(await tenant_factory())
    await location_factory(business)
    return business


async def test_an_upload_is_stored_re_encoded_and_listed(client, store, listed):
    response = await _upload(client, listed, kind="cover")

    assert response.status_code == 201, response.text
    photo = response.json()
    assert photo["kind"] == "cover"
    assert (photo["width"], photo["height"]) == (800, 600)
    assert set(photo["urls"]) == {"large", "thumb"}
    stored = list(store.root.rglob("*.webp"))
    assert len(stored) == 2

    listing = await client.get(_photos(listed.tenant_id, listed.id))
    assert [p["id"] for p in listing.json()] == [photo["id"]]


async def test_a_listed_business_serves_its_photos_to_anyone(client, store, listed):
    photo = (await _upload(client, listed, kind="cover")).json()

    served = await client.get(f"{DISCOVERY}/photos/{photo['id']}/large")

    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"
    assert "immutable" in served.headers["cache-control"]
    with Image.open(io.BytesIO(served.content)) as image:
        assert image.format == "WEBP"


async def test_search_cards_and_the_storefront_carry_the_photos(client, store, listed):
    cover = (await _upload(client, listed, kind="cover")).json()
    gallery = (await _upload(client, listed)).json()

    storefront = (await client.get(f"{DISCOVERY}/businesses/{listed.slug}")).json()
    cards = (await client.get(f"{DISCOVERY}/businesses", params={"q": listed.name_en})).json()

    assert [p["id"] for p in storefront["photos"]] == [cover["id"], gallery["id"]]
    card = next(c for c in cards["items"] if c["business_id"] == str(listed.id))
    assert card["cover_url"] == f"/api/v1/discovery/photos/{cover['id']}/thumb"


async def test_an_unlisted_business_shows_its_photos_only_through_signed_links(
    client, store, tenant_factory, business_factory
):
    hidden = await business_factory(await tenant_factory(), is_listed=False)
    photo = (await _upload(client, hidden, kind="cover")).json()

    public = await client.get(f"{DISCOVERY}/photos/{photo['id']}/large")
    signed = await client.get(photo["urls"]["large"])

    assert public.status_code == 404
    assert signed.status_code == 200
    assert signed.headers["cache-control"].startswith("private")


@pytest.mark.parametrize("tamper", ["signature", "expired", "other_photo"])
async def test_a_signed_link_cannot_be_forged_or_reused(
    client, store, tenant_factory, business_factory, tamper
):
    hidden = await business_factory(await tenant_factory(), is_listed=False)
    photo = (await _upload(client, hidden, kind="cover")).json()
    other = (await _upload(client, hidden)).json()
    url = photo["urls"]["large"]
    path, query = url.split("?")
    params = dict(pair.split("=") for pair in query.split("&"))
    if tamper == "signature":
        params["sig"] = "0" * 64
    elif tamper == "expired":
        params["exp"] = str(int(time.time()) - 10)
    else:
        path = path.replace(photo["id"], other["id"])

    response = await client.get(path, params=params)

    assert response.status_code == 404


async def test_a_new_cover_replaces_the_old_one_and_its_files(client, store, listed):
    first = (await _upload(client, listed, kind="cover")).json()
    second = (await _upload(client, listed, kind="cover", data=_jpeg((10, 200, 10)))).json()

    photos = (await client.get(_photos(listed.tenant_id, listed.id))).json()

    assert [p["id"] for p in photos] == [second["id"]]
    assert not any(first["id"] in str(path) for path in store.root.rglob("*.webp"))
    old = await client.get(f"{DISCOVERY}/photos/{first['id']}/large")
    assert old.status_code == 404


async def test_deleting_a_photo_removes_it_and_its_files(client, store, listed):
    photo = (await _upload(client, listed)).json()

    deleted = await client.delete(
        f"/api/v1/tenants/{listed.tenant_id}/catalog/photos/{photo['id']}"
    )

    assert deleted.status_code == 204
    assert list(store.root.rglob("*.webp")) == []
    assert (await client.get(_photos(listed.tenant_id, listed.id))).json() == []


async def test_the_gallery_has_a_limit(client, store, listed):
    for _ in range(MAX_GALLERY_PHOTOS):
        assert (await _upload(client, listed, data=_jpeg(size=(40, 40)))).status_code == 201

    over = await _upload(client, listed, data=_jpeg(size=(40, 40)))

    assert over.status_code == 409
    assert over.json()["error"]["code"] == "gallery_full"


async def test_a_file_that_is_not_an_image_is_refused(client, store, listed):
    response = await _upload(client, listed, data=b"<svg onload=alert(1)>")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_image"
    assert list(store.root.rglob("*")) == []


async def test_an_oversized_upload_is_refused(client, store, listed, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "media_max_upload_bytes", 1000)

    response = await _upload(client, listed)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "photo_too_large"


async def test_a_receptionist_cannot_change_the_photos(
    app, client, store, db_session, as_owner, listed
):
    user = User(email=f"desk-{uuid4().hex[:8]}@example.com", full_name="Desk", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    async with as_owner():
        db_session.add(
            Membership(
                user_id=user.id, tenant_id=listed.tenant_id, role=MembershipRole.RECEPTIONIST
            )
        )
        await db_session.flush()
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=user.id, kind=PrincipalKind.STAFF, tenant_ids=frozenset({listed.tenant_id})
    )

    response = await _upload(client, listed)
    looked = await client.get(_photos(listed.tenant_id, listed.id))

    assert response.status_code == 403
    assert looked.status_code == 200  # staff may still see them
