import copy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "ai-agent-education.coursespec.yaml"


@pytest.fixture
def example_data():
    return yaml.safe_load(EXAMPLE.read_text("utf-8"))


@pytest.fixture
def minimal():
    def make(**overrides):
        data = {
            "coursespec": "0.1",
            "id": "mini",
            "title": "미니 과정",
            "outcomes": [{"id": "lo1", "statement": "무언가를 할 수 있다"}],
            "units": [
                {"id": "u1", "title": "1단원", "items": [
                    {"id": "p1", "type": "page", "title": "읽기", "content": "본문", "outcomes": ["lo1"],
                     "completion": {"mode": "view"}},
                    {"id": "a1", "type": "assignment", "title": "과제", "outcomes": ["lo1"],
                     "grading": {"max": 10}, "completion": {"mode": "submit"}},
                ]},
            ],
        }
        data.update(copy.deepcopy(overrides))
        return data

    return make
