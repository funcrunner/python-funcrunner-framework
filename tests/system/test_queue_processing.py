import datetime
from time import sleep

from openai import OpenAI

from funcrunner.app import FuncRunnerApp
from funcrunner.models import ExecType


def test_queue_path(openai_proxy, application, assistant):
    client: OpenAI = openai_proxy

    app: FuncRunnerApp = application
    app.assistant_id = assistant.id
    app._configure_assistant()

    thread = client.beta.threads.create(messages=[
        {
            "role": "user",
            "content": "Create a greeting for Matthew"
        }
    ])

    run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=app.assistant_id)

    expiration = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=30)

    while datetime.datetime.now(datetime.UTC) < expiration:
        message = app._dequeue_message()
        if message and message.object == ExecType.OPENAI_RUN:
            if message.body["run_id"] == run.id:
                run_result = app._process_queue_message(message)

                app._submit_openai_run_results(run_result)
                app._delete_message(message)
                break
        sleep(1)


    while datetime.datetime.now(datetime.UTC) < expiration:
        run = client.beta.threads.runs.retrieve(run_id=run.id, thread_id=thread.id)
        if run.status == "completed":
            break
        else:
            sleep(1)

    messages = client.beta.threads.messages.list(thread_id=thread.id)
    assert len(messages.data) == 2

    latest_message = messages.data[0]
    assert latest_message.content[0].text.value


def test_queue_path_es(openai_proxy, application, assistant):
    client: OpenAI = openai_proxy

    app: FuncRunnerApp = application
    app.assistant_id = assistant.id
    app._configure_assistant()

    thread = client.beta.threads.create(messages=[
        {
            "role": "user",
            "content": "Create a greeting for Mateo in Spanish"
        }
    ])

    run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=app.assistant_id)

    expiration = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=30)

    while datetime.datetime.now(datetime.UTC) < expiration:
        message = app._dequeue_message()
        if message and message.object == ExecType.OPENAI_RUN:
            if message.body["run_id"] == run.id:
                run_result = app._process_queue_message(message)

                app._submit_openai_run_results(run_result)
                app._delete_message(message)
                break
            sleep(1)

    while datetime.datetime.now(datetime.UTC) < expiration:
        run = client.beta.threads.runs.retrieve(run_id=run.id, thread_id=thread.id)
        if run.status == "completed":
            break
        else:
            sleep(1)

    messages = client.beta.threads.messages.list(thread_id=thread.id)
    assert len(messages.data) == 2

    latest_message = messages.data[0]
    assert latest_message.content[0].text.value
