from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
import datetime

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.infrastructure.database import get_db
from app.features.presets.schemas import PresetCreate, PresetResponse, PresetUpdate
from app.features.presets.service import get_builtin_presets, get_user_presets, create_preset, update_preset, delete_preset

router = APIRouter(prefix="/presets", tags=["Presets"])


@router.get("", response_model=list[PresetResponse])
async def list_presets(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    builtin = await get_builtin_presets()
    user_presets = await get_user_presets(db, current_user.id)

    results = []
    for p in builtin:
        results.append(PresetResponse(
            id=p["id"],
            user_id=current_user.id,
            name=p["name"],
            description=p.get("description"),
            is_builtin=True,
            settings=p.get("settings", {}),
            created_at=datetime.datetime.now(datetime.timezone.utc),
            updated_at=datetime.datetime.now(datetime.timezone.utc),
        ))

    for p in user_presets:
        results.append(PresetResponse.model_validate(p))

    return results


@router.post("", response_model=PresetResponse, status_code=status.HTTP_201_CREATED)
async def create_preset_endpoint(
    data: PresetCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    preset = await create_preset(db, current_user.id, data.name, data.description, data.settings)
    return PresetResponse.model_validate(preset)


@router.patch("/{preset_id}", response_model=PresetResponse)
async def update_preset_endpoint(
    preset_id: UUID,
    data: PresetUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    preset = await update_preset(
        db,
        preset_id,
        current_user.id,
        data.name,
        data.description,
        data.settings,
    )
    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return PresetResponse.model_validate(preset)


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset_endpoint(
    preset_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_preset(db, preset_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Preset not found")
