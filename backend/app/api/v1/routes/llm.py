"""LLM 相关基础配置的 CRUD 接口：Provider / Model / ModelSettings。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.llm import ModelCategoryKey
from app.schemas.common import ApiResponse, PaginatedData, created_response, empty_response, success_response
from app.schemas.llm import (
    ImageGenerationOptionsRead,
    ModelCreate,
    ModelRead,
    ModelSettingsRead,
    ModelSettingsUpdate,
    ModelUpdate,
    ProviderCreate,
    ProviderRead,
    ProviderSupportedRead,
    VideoGenerationOptionsRead,
    ProviderUpdate,
)
from app.services.llm.manage import (
    create_model as create_model_service,
    create_provider as create_provider_service,
    delete_model as delete_model_service,
    delete_provider as delete_provider_service,
    get_model as get_model_service,
    get_model_settings as get_model_settings_service,
    get_provider as get_provider_service,
    get_image_generation_options as get_image_generation_options_service,
    get_video_generation_options as get_video_generation_options_service,
    list_supported_providers as list_supported_providers_service,
    list_models_paginated,
    list_providers_paginated,
    update_model as update_model_service,
    update_model_settings as update_model_settings_service,
    update_provider as update_provider_service,
)

router = APIRouter()

# 列表排序允许的字段（避免注入）
PROVIDER_ORDER_FIELDS = {"name", "created_at", "updated_at"}
MODEL_ORDER_FIELDS = {"name", "category", "created_at", "updated_at"}
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100


# ---------- Provider ----------


@router.get(
    "/providers",
    response_model=ApiResponse[PaginatedData[ProviderRead]],
    summary="列出模型供应商（分页）",
)
async def list_providers(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None, description="关键字，过滤 name/description"),
    order: str | None = Query(None, description="排序字段：name, created_at, updated_at"),
    is_desc: bool = Query(False, description="是否倒序"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
) -> ApiResponse[PaginatedData[ProviderRead]]:
    return await list_providers_paginated(
        db,
        q=q,
        order=order,
        is_desc=is_desc,
        page=page,
        page_size=page_size,
        allow_fields=PROVIDER_ORDER_FIELDS,
    )


@router.get(
    "/providers/supported",
    response_model=ApiResponse[list[ProviderSupportedRead]],
    summary="列出系统支持的供应商能力",
)
async def list_supported_providers(
    category: ModelCategoryKey | None = Query(None, description="按模型类别过滤：text/image/video"),
) -> ApiResponse[list[ProviderSupportedRead]]:
    items = list_supported_providers_service(category=category)
    return success_response(items)


@router.get(
    "/image-generation-options",
    response_model=ApiResponse[ImageGenerationOptionsRead],
    summary="获取当前默认图片模型的关键帧规格选项",
)
async def get_image_generation_options(
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ImageGenerationOptionsRead]:
    data = await get_image_generation_options_service(db)
    return success_response(data)


@router.get(
    "/video-generation-options",
    response_model=ApiResponse[VideoGenerationOptionsRead],
    summary="获取当前默认视频模型的动态比例选项",
)
async def get_video_generation_options(
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[VideoGenerationOptionsRead]:
    data = await get_video_generation_options_service(db)
    return success_response(data)


@router.post(
    "/providers",
    response_model=ApiResponse[ProviderRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建模型供应商",
)
async def create_provider(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProviderRead]:
    provider = await create_provider_service(db, body=body)
    return created_response(ProviderRead.model_validate(provider))


@router.get(
    "/providers/{provider_id}",
    response_model=ApiResponse[ProviderRead],
    summary="获取单个模型供应商",
)
async def get_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProviderRead]:
    provider = await get_provider_service(db, provider_id=provider_id)
    return success_response(ProviderRead.model_validate(provider))


@router.patch(
    "/providers/{provider_id}",
    response_model=ApiResponse[ProviderRead],
    summary="更新模型供应商",
)
async def update_provider(
    provider_id: str,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProviderRead]:
    provider = await update_provider_service(db, provider_id=provider_id, body=body)
    return success_response(ProviderRead.model_validate(provider))


@router.delete(
    "/providers/{provider_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    summary="删除模型供应商",
)
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await delete_provider_service(db, provider_id=provider_id)
    return empty_response()


# ---------- Provider/Model Test ----------


@router.post(
    "/providers/{provider_id}/test",
    response_model=ApiResponse[dict],
    summary="测试供应商连接",
    description="使用供应商的 API Key 和 Base URL 发送一个简单的 LLM 请求来验证连接。",
)
async def test_provider_connection(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """测试供应商连接是否可用。"""
    from app.models.llm import Provider
    from app.services.llm.test_connection import test_provider_connection_service

    provider = await db.get(Provider, provider_id)
    if not provider:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

    result = await test_provider_connection_service(provider)
    return success_response(result)


@router.post(
    "/models/{model_id}/test",
    response_model=ApiResponse[dict],
    summary="测试模型生成",
    description="使用指定模型发送一个简单的 LLM 请求来验证生成能力。",
)
async def test_model_generation(
    model_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """测试模型是否能正常生成。"""
    from app.models.llm import Model, Provider
    from app.services.llm.test_connection import test_model_connection_service
    from fastapi import HTTPException

    model = await db.get(Model, model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")

    provider = await db.get(Provider, model.provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider not found for model: {model_id}")

    result = await test_model_connection_service(model, provider)
    return success_response(result)


# ---------- Model ----------


@router.get(
    "/models",
    response_model=ApiResponse[PaginatedData[ModelRead]],
    summary="列出模型（分页）",
)
async def list_models(
    db: AsyncSession = Depends(get_db),
    provider_id: str | None = Query(None, description="按供应商过滤"),
    category: ModelCategoryKey | None = Query(None, description="按模型类别过滤"),
    q: str | None = Query(None, description="关键字，过滤 name/description"),
    order: str | None = Query(None, description="排序字段：name, category, created_at, updated_at"),
    is_desc: bool = Query(False, description="是否倒序"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
) -> ApiResponse[PaginatedData[ModelRead]]:
    return await list_models_paginated(
        db,
        provider_id=provider_id,
        category=category,
        q=q,
        order=order,
        is_desc=is_desc,
        page=page,
        page_size=page_size,
        allow_fields=MODEL_ORDER_FIELDS,
    )


@router.post(
    "/models",
    response_model=ApiResponse[ModelRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建模型",
)
async def create_model(
    body: ModelCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ModelRead]:
    model = await create_model_service(db, body=body)
    return created_response(ModelRead.model_validate(model))


@router.get(
    "/models/{model_id}",
    response_model=ApiResponse[ModelRead],
    summary="获取单个模型",
)
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ModelRead]:
    model = await get_model_service(db, model_id=model_id)
    return success_response(ModelRead.model_validate(model))


@router.patch(
    "/models/{model_id}",
    response_model=ApiResponse[ModelRead],
    summary="更新模型",
)
async def update_model(
    model_id: str,
    body: ModelUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ModelRead]:
    model = await update_model_service(db, model_id=model_id, body=body)
    return success_response(ModelRead.model_validate(model))


@router.delete(
    "/models/{model_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    summary="删除模型",
)
async def delete_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await delete_model_service(db, model_id=model_id)
    return empty_response()


# ---------- ModelSettings（单例） ----------


@router.get(
    "/model-settings",
    response_model=ApiResponse[ModelSettingsRead],
    summary="获取模型全局设置（单例）",
)
async def get_model_settings(
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ModelSettingsRead]:
    settings = await get_model_settings_service(db)
    return success_response(ModelSettingsRead.model_validate(settings))


@router.put(
    "/model-settings",
    response_model=ApiResponse[ModelSettingsRead],
    summary="更新模型全局设置（单例）",
)
async def update_model_settings(
    body: ModelSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ModelSettingsRead]:
    settings = await update_model_settings_service(db, body=body)
    return success_response(ModelSettingsRead.model_validate(settings))
