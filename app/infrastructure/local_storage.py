import os
import shutil
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.infrastructure.storage import StorageService

settings = get_settings()


class LocalStorage(StorageService):
    async def save_upload(
        self,
        file_data: BinaryIO,
        filename: str,
        user_id: str,
    ) -> str:
        upload_dir = Path(settings.upload_dir)
        user_dir = upload_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        dest = user_dir / filename
        with open(dest, "wb") as f:
            shutil.copyfileobj(file_data, f)
        return str(dest.relative_to(upload_dir))

    async def save_processed(
        self,
        file_data: BinaryIO,
        filename: str,
        user_id: str,
    ) -> str:
        processed_dir = Path(settings.processed_dir)
        user_dir = processed_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        dest = user_dir / filename
        with open(dest, "wb") as f:
            shutil.copyfileobj(file_data, f)
        return str(dest.relative_to(processed_dir))

    async def get_file_path(self, storage_path: str) -> Path:
        base = Path(settings.upload_dir)
        path = (base / storage_path).resolve()
        try:
            path.relative_to(base.resolve())
        except ValueError:
            raise FileNotFoundError(f"Storage path outside upload directory: {storage_path}")
        if not path.exists():
            raise FileNotFoundError(f"File not found: {storage_path}")
        return path

    async def file_exists(self, storage_path: str) -> bool:
        base = Path(settings.upload_dir)
        path = (base / storage_path).resolve()
        try:
            path.relative_to(base.resolve())
        except ValueError:
            return False
        return path.exists()

    async def delete_file(self, storage_path: str) -> None:
        base = Path(settings.upload_dir)
        path = (base / storage_path).resolve()
        try:
            path.relative_to(base.resolve())
        except ValueError:
            return
        if path.exists():
            path.unlink()
            try:
                path.parent.rmdir()
            except OSError:
                pass

    def get_file_url(self, storage_path: str) -> str:
        return f"/media/file?path={storage_path}"
