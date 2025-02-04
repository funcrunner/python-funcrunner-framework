import datetime
import os
import time
from unittest.mock import MagicMock

import anthropic

from funcrunner.app import FuncRunnerApp
from funcrunner.models import ExecType


def test_sends_basic_message(anthropic_proxy):
    client: anthropic.Client = anthropic_proxy

    resp = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Who was the first president of the United States?"}],
    )

    assert resp


def test_tool_injection(anthropic_proxy, application):
    app: FuncRunnerApp = application
    app.api_key = os.getenv("ANTHROPIC_FR_API_KEY")
    app._configure_auto_tools()

    greet_mock = MagicMock(return_value="Greetings from Func Runner, George Washington!")
    app.function_registry["greet"] = greet_mock

    client: anthropic.Client = anthropic_proxy

    resp = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Generate a greeting for the first president of the United States."}],
    )

    expiration = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=30)

    while datetime.datetime.now(datetime.UTC) < expiration:
        message = app._dequeue_message()
        if message and message.object == ExecType.ANTHROPIC_MESSAGE:
            app._process_queue_message(message)
            app._delete_message(message)
            break
        time.sleep(1)

    assert greet_mock.call_count > 0

def test_handles_basic_tool_call(anthropic_proxy, application):

    app: FuncRunnerApp = application
    app.api_key = os.getenv("ANTHROPIC_FR_API_KEY")

    greet_mock = MagicMock(return_value="Greetings from Func Runner, George Washington!")
    app.function_registry["greet"] = greet_mock

    client: anthropic.Client = anthropic_proxy

    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Generate a greeting for the first president of the United States."}],
        tools=[
            {
                'description': 'Description not given',
                'name': 'greet',
                'input_schema': {
                    'additionalProperties': False,
                    'properties': {
                        'name': {
                            'description': 'Description not given',
                            'type': 'string'
                        }
                    },
                    'required': ['name'],
                    'type': 'object'
                }
            }
        ]
    )

    expiration = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=30)

    while datetime.datetime.now(datetime.UTC) < expiration:
        message = app._dequeue_message()
        if message and message.object == ExecType.ANTHROPIC_MESSAGE:
            app._process_queue_message(message)
            app._delete_message(message)
            break
        time.sleep(1)

    assert greet_mock.call_count > 0

def test_sends_webhook_response(anthropic_proxy, application, test_webserver):
    app: FuncRunnerApp = application
    app.api_key = os.getenv("ANTHROPIC_FR_API_KEY")

    client: anthropic.Client = anthropic_proxy

    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Generate a greeting for the first president of the United States."}],
        tools=[
            {
                'description': 'Description not given',
                'name': 'greet',
                'input_schema': {
                    'additionalProperties': False,
                    'properties': {
                        'name': {
                            'description': 'Description not given',
                            'type': 'string'
                        }
                    },
                    'required': ['name'],
                    'type': 'object'
                }
            }
        ]
    )

    timeout = time.time() + 30
    while time.time() < timeout:
        message = app._dequeue_message()
        if message:
            if message.object == ExecType.ANTHROPIC_MESSAGE:
                results = app._process_queue_message(message)
                app._submit_anthropic_message_results(results, response.model_dump())
                app._delete_message(message)
                break
            else:
                app._delete_message(message)

    timeout = time.time() + 10
    while time.time() < timeout:
        if test_webserver.received_payloads:
            break
        time.sleep(0.5)

    # Assert that at least one webhook payload was received.
    assert len(test_webserver.received_payloads) > 0, "No webhook payload was received by the test webserver."