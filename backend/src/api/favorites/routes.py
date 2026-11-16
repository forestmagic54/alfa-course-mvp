from collections.abc import Awaitable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, Security
from fastapi.security import HTTPBearer

from src.api.dependencies import AccountDep
from src.api.errors.schemas import Error
from src.api.favorites.schemas import (
    FavoriteFolder,
    FavoriteFolderInput,
    FavoriteMaterial,
)
from src.api.service_dependencies import FavoriteServiceDep
from src.services.favorites import DefaultFolderProtected, FavoriteNotFound

router = APIRouter(tags=['Избранное'])
security = [Security(HTTPBearer(auto_error=False))]


async def result[T](operation: Awaitable[T]) -> T:
    try:
        return await operation
    except FavoriteNotFound:
        raise HTTPException(404) from None
    except DefaultFolderProtected:
        raise HTTPException(409, detail={'code': 'default_folder_protected',
                                         'message': 'Папка по умолчанию защищена'}) from None


@router.get('/me/favorite-folders', operation_id='listFavoriteFolders', response_model=list[FavoriteFolder],
            responses={401: {'model': Error}}, dependencies=security)
async def list_folders(service: FavoriteServiceDep, account: AccountDep):
    return await service.list_folders(account.id)


@router.post('/me/favorite-folders', operation_id='createFavoriteFolder', response_model=FavoriteFolder,
             status_code=201, responses={code: {'model': Error} for code in (401, 422)}, dependencies=security)
async def create_folder(body: FavoriteFolderInput, service: FavoriteServiceDep, account: AccountDep):
    return await service.create_folder(account.id, body.name)


@router.patch('/me/favorite-folders/{folder_id}', operation_id='renameFavoriteFolder', response_model=FavoriteFolder,
              responses={code: {'model': Error} for code in (401, 404, 409, 422)}, dependencies=security)
async def rename_folder(folder_id: UUID, body: FavoriteFolderInput, service: FavoriteServiceDep, account: AccountDep):
    return await result(service.change_folder(account.id, folder_id, body.name))


@router.delete('/me/favorite-folders/{folder_id}', operation_id='deleteFavoriteFolder', status_code=204,
               responses={code: {'model': Error} for code in (401, 404, 409, 422)}, dependencies=security)
async def delete_folder(folder_id: UUID, service: FavoriteServiceDep, account: AccountDep):
    await result(service.change_folder(account.id, folder_id, None))
    return Response(status_code=204)


@router.get('/me/favorite-folders/{folder_id}/materials', operation_id='listFavoriteMaterials',
            response_model=list[FavoriteMaterial], response_model_exclude_unset=True,
            responses={code: {'model': Error} for code in (401, 404, 422)}, dependencies=security)
async def list_materials(folder_id: UUID, service: FavoriteServiceDep, account: AccountDep):
    return await result(service.list_materials(account.id, folder_id))


@router.put('/me/favorite-folders/{folder_id}/materials/{material_id}', operation_id='addFavoriteMaterial',
            status_code=204, responses={code: {'model': Error} for code in (401, 404, 422)}, dependencies=security)
async def add_material(folder_id: UUID, material_id: UUID, service: FavoriteServiceDep, account: AccountDep):
    await result(service.change_material(account.id, folder_id, material_id, add=True))
    return Response(status_code=204)


@router.delete('/me/favorite-folders/{folder_id}/materials/{material_id}', operation_id='removeFavoriteMaterial',
               status_code=204, responses={code: {'model': Error} for code in (401, 404, 422)}, dependencies=security)
async def remove_material(folder_id: UUID, material_id: UUID, service: FavoriteServiceDep, account: AccountDep):
    await result(service.change_material(account.id, folder_id, material_id, add=False))
    return Response(status_code=204)
