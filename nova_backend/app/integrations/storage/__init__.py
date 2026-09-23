"""Where stored files live.

`ImageStore` is the only operations NOVA uses; `LocalImageStore` keeps files
on a local directory (a named volume in compose). A deployment that needs
object storage adds an S3-compatible adapter satisfying the same Protocol —
nothing that stores or serves a photo changes.
"""

from app.integrations.storage.local import ImageStore, LocalImageStore

__all__ = ["ImageStore", "LocalImageStore"]
