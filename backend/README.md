# Альфа-Курс: backend

API для поиска учебных материалов, персональных рекомендаций и построения карт обучения.

## Настройка

Перед запуском скопируйте `.env.example` в `.env` и настройте в нём Cloudflare Workers AI для работы LLM.

Значения по умолчанию предназначены только для локальной разработки: для другого окружения задайте уникальные `JWT_SECRET` и пароль PostgreSQL. Если база уже создана, изменение переменных PostgreSQL в `.env` не изменит учётные данные существующего volume.

Для работы LLM:

1. Зарегистрируйтесь в [Cloudflare](https://dash.cloudflare.com/), откройте Workers AI и выберите **Use REST API**.
2. Создайте токен через **Create a Workers AI API Token** и скопируйте его и Account ID. Подробнее — в [инструкции Cloudflare](https://developers.cloudflare.com/workers-ai/get-started/rest-api/).
3. В `.env` задайте `CLOUDFLARE_API_TOKEN` и `CLOUDFLARE_ACCOUNT_ID`. LLM включена по умолчанию (`LLM_ENABLED=true`), модель уже указана в `.env.example`. Если `.env` был создан ранее, проверьте в нём значение `LLM_ENABLED`.

## Запуск

Установите Docker с Compose. Для запуска нужны файлы `compose.demo.yaml` и настроенный `.env` в одной папке. Выполните в этой папке:

```sh
docker compose -f compose.demo.yaml up -d
```

Compose скачает образы backend и frontend, запустит PostgreSQL, применит миграции и загрузит демоданные до запуска API. Сайт доступен на `http://localhost:8080`, документация API — на `http://localhost:8000/api/v1/docs`. Для первой загрузки нужна пустая база; данные сохраняются в Docker volume. Образы собраны для `linux/arm64`.

### Сборка из исходников

В корне проекта выполните:

```sh
docker compose -f compose.yaml up -d --build
docker compose -f compose.yaml exec -T backend python -m src.load_demo
docker compose -f compose.yaml exec -T backend python -m src.sync_materials
docker compose -f compose.yaml exec -T backend python -m src.import_material_annotations
docker compose -f compose.yaml exec -T backend python -m src.sync_materials
```

Первая команда собирает backend, запускает PostgreSQL и применяет миграции; остальные загружают демоданные в пустую базу и синхронизируют каталог.

## Тестовые данные

Общий пароль демо-аккаунтов — `0123456789`; при загрузке вводить его не нужно. Например, можно войти как `cold@example.com`; остальные аккаунты и состав набора перечислены в [описании демоданных](docs/demo_data.md). Материалы, цены и ссылки синтетические; повторная загрузка набора v2 не меняет данные и ранее установленные пароли.

## [Документация проекта](docs/)

[Назначение решения](docs/purpose.md), [архитектура](docs/architecture.md).
