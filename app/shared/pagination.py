from __future__ import annotations

from typing import Generic, Sequence, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

T = TypeVar("T")


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-indexed page number"),
        page_size: int = Query(25, ge=1, le=100, description="Items per page, max 100"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int


async def paginate(
    db: AsyncSession,
    stmt: Select,
    params: PaginationParams,
) -> tuple[Sequence, int]:
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()
    paged_stmt = stmt.offset(params.offset).limit(params.page_size)
    items = (await db.execute(paged_stmt)).scalars().all()
    return items, total


def build_response(
    items: Sequence,
    total: int,
    params: PaginationParams,
) -> dict:
    total_pages = (
        (total + params.page_size - 1) // params.page_size
        if total > 0
        else 0
    )
    return {
        "items": list(items),
        "page": params.page,
        "page_size": params.page_size,
        "total": total,
        "total_pages": total_pages,
    }
