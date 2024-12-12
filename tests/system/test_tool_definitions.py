def test_auto_update(application, assistant):
    application.assistant_id = assistant.id
    application._configure_assistant()
