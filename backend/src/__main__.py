import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.exceptions import HTTPException

from src.api import api_router
from src.api.errors.handlers import http_error_handler, validation_error_handler
from src.clients.llm import LLMClient
from src.config.settings import LLMSettings, Settings
from src.context import AppContext
from src.db.session import create_engine
from src.services.llm_generator import LLMGenerator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_engine(app.state.settings.database.url)
    client = None
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        app.state.context = AppContext(settings=app.state.settings, session_factory=factory)
        if app.state.settings.app.llm_enabled:
            try:
                llm_settings = LLMSettings()
                llm_settings.llm_timeout_seconds = min(llm_settings.llm_timeout_seconds,
                                                       app.state.settings.app.generation_timeout_seconds)
                client = LLMClient(llm_settings)
                app.state.context.generator = LLMGenerator(client, app.state.settings.app.generation_timeout_seconds)
            except ValueError:
                logging.getLogger(__name__).warning('LLM configuration invalid; using template generator')
        yield
    finally:
        try:
            if client is not None:
                await client.aclose()
        finally:
            await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    prefix = settings.app.api_prefix
    app = FastAPI(
        title='A-courses',
        version='0.3.0',
        openapi_url=f'{prefix}/openapi.json',
        docs_url=f'{prefix}/docs',
        redoc_url=f'{prefix}/redoc',
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        headers = {}
        if not prefix or request.url.path == prefix or request.url.path.startswith(f'{prefix}/'):
            headers['Cache-Control'] = 'no-store'
        return JSONResponse(status_code=500, content={
            'code': 'internal_error', 'message': 'Внутренняя ошибка сервера',
        }, headers=headers)

    @app.middleware('http')
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        if not prefix or request.url.path == prefix or request.url.path.startswith(f'{prefix}/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    app.state.settings = settings
    app.mount('/demo-files', StaticFiles(directory=Path(__file__).parent / 'config' / 'demo' / 'files'), name='demo-files')
    app.include_router(api_router, prefix=prefix)
    return app


if __name__ == '__main__':
    app = create_app()
    uvicorn.run(app, host=app.state.settings.app.host, port=app.state.settings.app.port)
