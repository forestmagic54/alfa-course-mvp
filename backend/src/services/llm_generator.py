import asyncio
from dataclasses import replace

from src.services.recommendation_stubs import (
    GeneratedText,
    GenerationInput,
    StubGenerator,
)


class LLMGenerator:
    def __init__(self, client, timeout: float):
        self.client = client
        self.timeout = timeout
        self.fallback = StubGenerator()

    async def generate(self, data: GenerationInput):
        result = await self.fallback.generate(data)
        items = dict(result.items)

        async def describe(item):
            material = (data.facts or {}).get(item.material_id)
            if material is None or not material.public_description or not material.public_description.strip():
                return
            try:
                method = (self.client.generate_article_description if item.kind == 'article'
                          else self.client.generate_course_description)
                response = await method(material, data.profile)
                if (response.status == 'succeeded' and response.material_id == material.id
                        and response.source_version == material.source_version
                        and isinstance(response.text, str) and response.text.strip()):
                    default = items[item.material_id]
                    items[item.material_id] = GeneratedText(item.kind, response.text, None, default.transition_text)
            except Exception:
                pass

        tasks = [asyncio.create_task(describe(item)) for item in data.ranking if item.kind in ('article', 'course')]
        try:
            if tasks:
                await asyncio.wait(tasks, timeout=self.timeout * 0.9)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        return replace(result, items=items)
