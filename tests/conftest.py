import os
import threading
import time
from enum import Enum
from typing import Any

import anthropic
import openai
import pytest
from dotenv import load_dotenv
from flask import Flask, request, jsonify

from funcrunner.app import FuncRunnerApp

load_dotenv()

USE_LOCAL_SERVICES = os.getenv("USE_LOCAL_SERVICES", "false").lower() == "true"


class StatusEnum(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@pytest.fixture(scope="function")
def application():
    app = FuncRunnerApp(enable_local_services=USE_LOCAL_SERVICES)
    app.enable_local_services = USE_LOCAL_SERVICES

    @app.schedule("0/15 * * * *")
    def test_task():
        print("This is a scheduled task test!")

    # Function with a string parameter
    @app.function()
    def greet(name: str):
        return f"Hello, {name}! Love, Func Runner."

    @app.function(name="greet_in_spanish")
    def greet_es(nombre: str):
        return f"Hola, {nombre}! Te Amo, Func Runner."

    # Function with a number parameter
    @app.function()
    def add_numbers(a: int, b: float):
        return a + b

    # Function with a boolean parameter
    @app.function()
    def check_status(is_active: bool):
        return "Active" if is_active else "Inactive"

    # Function with an array parameter
    @app.function()
    def list_summary(items: list[str]):
        return f"You have {len(items)} items."

    # Function with an object parameter as a dict
    @app.function()
    def user_info(user: dict[str, Any]):
        return f"User {user['username']} is {user['age']} years old."

    # Function with an enum parameter
    @app.function()
    def review_status(status: StatusEnum):
        if isinstance(status, str):
            status = StatusEnum(status)
        return f"The review status is {status.value}."

    return app

@pytest.fixture(scope="function")
def openai_proxy(application):
    app: FuncRunnerApp = application

    api_key = os.getenv("FUNCRUNNER_API_KEY")

    client = openai.OpenAI(
        api_key=api_key,
        base_url=f"{app.proxy_host}/v1",
    )
    return client

@pytest.fixture(scope="function")
def anthropic_proxy(application):
    app: FuncRunnerApp = application
    api_key = os.getenv("ANTHROPIC_FR_API_KEY")
    client = anthropic.Client(
        api_key=api_key,
        base_url=app.proxy_host,
    )
    return client

@pytest.fixture(scope="function")
def assistant(openai_proxy):
    assistant = openai_proxy.beta.assistants.create(
        model="gpt-3.5-turbo-1106",
        tools=[{"type": "file_search"}, {"type": "code_interpreter"}]
    )
    yield assistant

    openai_proxy.beta.assistants.delete(assistant.id)


@pytest.fixture(scope="session")
def test_webserver():
    """
    A fixture that starts a temporary Flask server to receive webhooks.

    The server listens on a fixed port (5002) and defines a /webhook endpoint.
    Received webhook payloads are stored in the 'received_payloads' list.
    """
    app = Flask(__name__)
    received_payloads = []

    @app.route('/webhook', methods=['POST'])
    def webhook():
        data = request.get_json()
        print("Test webserver received webhook:", data)
        received_payloads.append(data)
        return jsonify({"status": "received"}), 200

    # Choose a port for the test webserver.
    port = 5002

    # Define a function to run the app. We disable the reloader to avoid spawning extra processes.
    def run_server():
        app.run(port=port, debug=False, use_reloader=False)

    # Start the Flask server in a background thread.
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Give the server a moment to start up.
    time.sleep(1)

    # Create a simple object to return the necessary properties.
    class WebhookServer:
        pass

    test_server = WebhookServer()
    test_server.url = f"http://localhost:{port}/webhook"
    test_server.received_payloads = received_payloads

    # Yield the test server object to the test.
    yield test_server

    # Teardown can be performed here if needed. With Flask's built-in server,
    # shutdown can be more complicated. In tests, it's often acceptable to let the
    # daemon thread exit when the process ends.