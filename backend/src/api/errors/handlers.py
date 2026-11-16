from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = []
    for error in exc.errors():
        location = error['loc']
        if location and location[0] in ('body', 'query', 'path', 'header', 'cookie'):
            location = location[1:]
        fields.append({'field': '.'.join(map(str, location)), 'message': 'Некорректное значение'})
    return JSONResponse(status_code=422, content={
        'code': 'validation_error', 'message': 'Проверьте указанные поля', 'fields': fields,
    })


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    defaults = {
        401: ('unauthorized', 'Требуется авторизация'),
        404: ('not_found', 'Ресурс не найден'),
        409: ('conflict', 'Конфликт запроса'),
        422: ('validation_error', 'Проверьте указанные поля'),
        503: ('service_unavailable', 'Сервис временно недоступен'),
    }
    code, message = defaults.get(exc.status_code, ('http_error', 'Ошибка запроса'))
    if isinstance(exc.detail, dict) and isinstance(exc.detail.get('code'), str) and isinstance(exc.detail.get('message'), str):
        code, message = exc.detail['code'], exc.detail['message']
    return JSONResponse(status_code=exc.status_code, content={'code': code, 'message': message}, headers=exc.headers)
