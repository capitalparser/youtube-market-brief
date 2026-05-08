import pytest

from youtube_market_brief._clients.llm import extract_fenced_json


def test_extract_fenced_json_block():
    text = """assistant prelude
```json
{"a": 1, "b": [2, 3]}
```
trailing words
"""
    obj = extract_fenced_json(text)
    assert obj == {"a": 1, "b": [2, 3]}


def test_extract_unfenced_balanced_braces_fallback():
    text = 'noisy preamble {"x": "ok"} trailing.'
    obj = extract_fenced_json(text)
    assert obj == {"x": "ok"}


def test_extract_invalid_raises():
    with pytest.raises(ValueError):
        extract_fenced_json("no braces here")
