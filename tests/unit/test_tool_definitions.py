from typing import Any

from funcrunner.tool_definitions import build_tool_definition


def test_string_method():
    def greet(name: str) -> str:
        pass

    definition = build_tool_definition(greet)
    spec = definition.model_dump(exclude_none=True, by_alias=True)
    assert spec == {
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


def test_list_method():
    def list_summary(items: list[str]):
        pass

    definition = build_tool_definition(list_summary)
    spec = definition.model_dump(exclude_none=True, by_alias=True)
    assert spec == {
        'function': {
            'description': 'Description not given',
            'name': 'list_summary',
            'parameters': {
                'additionalProperties': False,
                'properties': {
                    'items': {
                        'description': 'Description not given',
                        'type': 'array',
                        'items': {
                            'type': 'string',
                            'description': 'Description not given'
                        }
                    }
                },
                'required': ['items'],
                'type': 'object'
            },
            'strict': True
        },
        'type': 'function'
    }


def test_dict_method():
    def update_user(user: dict[str, Any]) -> str:
        pass

    definition = build_tool_definition(update_user)
    spec = definition.model_dump(exclude_none=True, by_alias=True)
    assert spec == {
        'function': {
            'description': 'Description not given',
            'name': 'update_user',
            'parameters': {
                'additionalProperties': False,
                'properties': {
                    'user': {
                        'additionalProperties': False,
                        'properties': {},
                        'required': [],
                        'type': 'object'
                    }
                },
                'required': ['user'],
                'type': 'object'
            },
            'strict': True
        },
        'type': 'function'
    }
