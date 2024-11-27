import os
from enum import Enum
from typing import Any

import openai
import pytest
from dotenv import load_dotenv

from funcrunner.app import FuncRunnerApp

load_dotenv()


class StatusEnum(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@pytest.fixture(scope="function")
def application():
    app = FuncRunnerApp()

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
def openai_proxy():
    api_key = os.getenv("FUNCRUNNER_API_KEY")

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://proxy.funcrunner.com/v1",
    )
    return client

@pytest.fixture(scope="function")
def assistant(openai_proxy):
    assistant = openai_proxy.beta.assistants.create(
        model="gpt-4-turbo",
        tools=[{"type": "file_search"}, {"type": "code_interpreter"}]
    )
    yield assistant

    openai_proxy.beta.assistants.delete(assistant.id)
