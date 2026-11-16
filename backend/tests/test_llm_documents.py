import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from src.clients.llm import LLMClient
from src.clients.llm_schemas import MaterialInput


def test_document_without_description_reaches_provider():
    client = LLMClient.__new__(LLMClient)
    client.settings = SimpleNamespace(llm_model='model', llm_temperature=0, llm_max_tokens=100)
    client._requests = 0
    client._usage_totals = {'input_tokens': 0, 'output_tokens': 0, 'neurons': 0}
    client._usage_counts = dict.fromkeys(client._usage_totals, 0)
    requests = []

    async def request(method, path, **kwargs):
        requests.append(kwargs['json'])
        return {'result': {'response': 'Документ посвящён теме бюджета.'}}

    client._request = request
    material = MaterialInput(id=uuid4(), kind='document', title='Бюджет', access_type='unknown',
                             source_version='1')
    result = asyncio.run(client.generate_document_description(material))

    assert result.status == 'succeeded'
    assert result.text == 'Документ посвящён теме бюджета.'
    assert json.loads(requests[0]['messages'][1]['content'])['material']['kind'] == 'document'
