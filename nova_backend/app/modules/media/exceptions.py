"""media · DOMAIN layer — module errors.

The validation rules live in `domain.py` beside the checks they guard
(`UnsupportedMediaTypeError`, `MediaTooLargeError`,
`MediaUploadUrlExpiredError`); this file holds the rest.
"""

from app.core.exceptions import ConflictError, NotFoundError


class MediaAssetNotFoundError(NotFoundError):
    code = "media_asset_not_found"

    def __init__(self, asset_id: object) -> None:
        super().__init__(f"Media asset '{asset_id}' was not found.")


class MediaNotUploadedError(ConflictError):
    """The row exists but the bytes do not.

    Returned rather than silently marking the asset ready: a storefront
    rendering a logo that was never uploaded is worse than an honest error at
    the moment of upload.
    """

    code = "media_not_uploaded"

    def __init__(self, asset_id: object) -> None:
        super().__init__(f"No file has been uploaded for asset '{asset_id}' yet.")
