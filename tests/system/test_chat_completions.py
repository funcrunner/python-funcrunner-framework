import datetime
import time
from unittest.mock import MagicMock

from openai import OpenAI

from funcrunner.app import FuncRunnerApp
from funcrunner.models import ExecType


def test_sends_basic_message(openai_proxy):
    client: OpenAI = openai_proxy

    assert not client.base_url == "https://api.openai.com"

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Who was the first president of the United States"}],
    )

    assert response.choices[0].message

def test_handles_basic_tool_call(openai_proxy, application):
    client: OpenAI = openai_proxy
    app: FuncRunnerApp = application

    greet_mock = MagicMock(return_value="Greetings from Func Runner, George Washington!")
    app.function_registry["greet"] = greet_mock

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": "Generate a greeting for the first president of the United States."}],
        tools=[
            {
                'function': {
                    'description': 'Description not given',
                    'name': 'greet',
                    'parameters': {
                        'additionalProperties': False,
                        'properties': {
                            'name': {
                                'description': 'Description not given',
                                'type': 'string'
                            }
                        },
                        'required': ['name'],
                        'type': 'object'
                    },
                    'strict': True
                },
                'type': 'function'
            }
        ]
    )

    expiration = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=30)

    while datetime.datetime.now(datetime.UTC) < expiration:
        message = app._dequeue_message()
        if message and message.object == ExecType.OPENAI_CHAT_COMPLETION:
            app._process_queue_message(message)
            app._delete_message(message)
            break
        time.sleep(1)

    assert greet_mock.call_count > 0