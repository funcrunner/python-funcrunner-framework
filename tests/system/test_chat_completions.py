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


def test_sends_webhook_response(openai_proxy, application, test_webserver):
    client: OpenAI = openai_proxy
    app: FuncRunnerApp = application

    # Use the webhook URL provided by the test_webserver fixture.
    webhook_url = test_webserver.url

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": "Generate a greeting for the first president of the United States."}],
        tool_choice="required",
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
        ],
    )

    # Assert that we received a valid chat response.
    assert response.choices[0].message

    timeout = time.time() + 30
    while time.time() < timeout:
        message = app._dequeue_message()
        if message:
            if message.object == ExecType.OPENAI_CHAT_COMPLETION:
                results = app._process_queue_message(message)
                app._submit_openai_chat_results(results, response.model_dump())
                app._delete_message(message)
                break
            else:
                app._delete_message(message)
        # time.sleep(1)

    timeout = time.time() + 10
    while time.time() < timeout:
        if test_webserver.received_payloads:
            break
        time.sleep(0.5)

    # Assert that at least one webhook payload was received.
    assert len(test_webserver.received_payloads) > 0, "No webhook payload was received by the test webserver."