from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


class StorageService(ABC):
    @abstractmethod
    async def save_upload(
        self,
        file_data: BinaryIO,
        filename: str,
        user_id: str,
    ) -> str:
        pass

    @abstractmethod
    async def save_processed(
        self,
        file_data: BinaryIO,
        filename: str,
        user_id: str,
    ) -> str:
        pass

    @abstractmethod
    async def get_file_path(self, storage_path: str) -> Path:
        pass

    @abstractmethod
    async def file_exists(self, storage_path: str) -> bool:
        pass

    @abstractmethod
    async def delete_file(self, storage_path: str) -> None:
        pass

    @abstractmethod
    def get_file_url(self, storage_path: str) -> str:
        pass
