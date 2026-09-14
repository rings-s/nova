"""Media rules — docs/07 section 9, docs/08 section 15.

Filenames arrive from clients, so the sanitiser is the interesting part: it is
the only thing between an attacker-controlled string and a storage path.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationDomainError
from app.modules.media.domain import (
    MediaAssetKind,
    MediaTooLargeError,
    MediaUploadUrlExpiredError,
    UnsupportedMediaTypeError,
    assert_path_belongs_to_tenant,
    build_webdav_path,
    sanitize_file_name,
    sign_upload_authorisation,
    validate_content_type,
    validate_size,
    verify_upload_authorisation,
)

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
TENANT = uuid4()
BUSINESS = uuid4()
ASSET = uuid4()
SECRET = "media-secret"


class TestContentTypeAndSize:
    def test_accepts_an_image(self):
        assert validate_content_type("image/jpeg") == "image/jpeg"

    def test_normalises_charset_and_case(self):
        assert validate_content_type("IMAGE/PNG; charset=binary") == "image/png"

    def test_rejects_anything_not_on_the_allowlist(self):
        for bad in ("application/x-msdownload", "text/html", "image/svg+xml"):
            with pytest.raises(UnsupportedMediaTypeError):
                validate_content_type(bad)

    def test_rejects_a_file_over_the_limit(self):
        with pytest.raises(MediaTooLargeError):
            validate_size(200, max_bytes=100)

    def test_rejects_an_empty_file(self):
        with pytest.raises(ValidationDomainError):
            validate_size(0, max_bytes=100)


class TestFilenameSanitising:
    def test_keeps_an_ordinary_name(self):
        assert sanitize_file_name("portfolio.jpg", content_type="image/jpeg") == "portfolio.jpg"

    def test_strips_path_traversal(self):
        cleaned = sanitize_file_name("../../etc/passwd", content_type="image/png")
        assert "/" not in cleaned and ".." not in cleaned

    def test_strips_windows_separators(self):
        cleaned = sanitize_file_name(r"C:\evil\shell.png", content_type="image/png")
        assert "\\" not in cleaned and ":" not in cleaned

    def test_replaces_spaces_and_quotes(self):
        cleaned = sanitize_file_name('my "best" work.jpg', content_type="image/jpeg")
        assert '"' not in cleaned and " " not in cleaned

    def test_strips_direction_marks(self):
        # A right-to-left override can make "gnp.exe" render as "exe.png".
        cleaned = sanitize_file_name("photo\u202egnp.exe", content_type="image/png")
        assert "\u202e" not in cleaned

    def test_an_empty_name_still_produces_something(self):
        assert sanitize_file_name("...", content_type="image/png") == "file.png"

    def test_adds_an_extension_when_missing(self):
        assert sanitize_file_name("logo", content_type="image/webp") == "logo.webp"

    def test_truncates_an_absurdly_long_name_keeping_the_extension(self):
        cleaned = sanitize_file_name("a" * 500 + ".jpg", content_type="image/jpeg")
        assert len(cleaned) <= 120
        assert cleaned.endswith(".jpg")


class TestPathConvention:
    def test_matches_the_documented_layout(self):
        path = build_webdav_path(
            tenant_id=TENANT,
            business_id=BUSINESS,
            kind=MediaAssetKind.PORTFOLIO,
            asset_id=ASSET,
            file_name="shot.jpg",
        )
        assert path == f"/nova-media/{TENANT}/{BUSINESS}/portfolio/{ASSET}/shot.jpg"

    def test_tenant_id_leads_the_path(self):
        path = build_webdav_path(
            tenant_id=TENANT,
            business_id=BUSINESS,
            kind=MediaAssetKind.LOGO,
            asset_id=ASSET,
            file_name="logo.png",
        )
        assert path.startswith(f"/nova-media/{TENANT}/")

    def test_a_path_in_another_tenants_folder_is_refused(self):
        other = build_webdav_path(
            tenant_id=uuid4(),
            business_id=BUSINESS,
            kind=MediaAssetKind.LOGO,
            asset_id=ASSET,
            file_name="logo.png",
        )
        with pytest.raises(ValidationDomainError):
            assert_path_belongs_to_tenant(other, tenant_id=TENANT)

    def test_a_traversal_inside_the_right_prefix_is_still_refused(self):
        sneaky = f"/nova-media/{TENANT}/../{uuid4()}/logo/x/logo.png"
        with pytest.raises(ValidationDomainError):
            assert_path_belongs_to_tenant(sneaky, tenant_id=TENANT)


class TestUploadAuthorisation:
    def _sign(self, path: str, expires_at: datetime, secret: str = SECRET) -> str:
        return sign_upload_authorisation(
            asset_id=ASSET,
            tenant_id=TENANT,
            webdav_path=path,
            expires_at=expires_at,
            secret=secret,
        )

    def test_a_valid_token_verifies(self):
        expires = NOW + timedelta(minutes=15)
        token = self._sign("/nova-media/x", expires)
        verify_upload_authorisation(
            token,
            asset_id=ASSET,
            tenant_id=TENANT,
            webdav_path="/nova-media/x",
            expires_at=expires,
            secret=SECRET,
            now=NOW,
        )

    def test_an_expired_token_is_refused(self):
        expires = NOW - timedelta(seconds=1)
        with pytest.raises(MediaUploadUrlExpiredError):
            verify_upload_authorisation(
                self._sign("/nova-media/x", expires),
                asset_id=ASSET,
                tenant_id=TENANT,
                webdav_path="/nova-media/x",
                expires_at=expires,
                secret=SECRET,
                now=NOW,
            )

    def test_a_token_cannot_be_moved_to_another_path(self):
        # The signature covers the path, so a client cannot alter where its own
        # file claims to live.
        expires = NOW + timedelta(minutes=15)
        with pytest.raises(ValidationDomainError):
            verify_upload_authorisation(
                self._sign("/nova-media/mine", expires),
                asset_id=ASSET,
                tenant_id=TENANT,
                webdav_path="/nova-media/theirs",
                expires_at=expires,
                secret=SECRET,
                now=NOW,
            )

    def test_a_forged_token_is_refused(self):
        expires = NOW + timedelta(minutes=15)
        with pytest.raises(ValidationDomainError):
            verify_upload_authorisation(
                self._sign("/nova-media/x", expires, secret="wrong"),
                asset_id=ASSET,
                tenant_id=TENANT,
                webdav_path="/nova-media/x",
                expires_at=expires,
                secret=SECRET,
                now=NOW,
            )
