"""LMS별 퍼블리셔. 새 LMS를 지원하려면 plan_<lms>(spec, start, ...) -> Plan 을 추가한다."""

from .canvas import plan_canvas
from .moodle import plan_moodle
from .openmaic import plan_openmaic

TARGETS = {"moodle": plan_moodle, "canvas": plan_canvas, "openmaic": plan_openmaic}

__all__ = ["TARGETS", "plan_canvas", "plan_moodle", "plan_openmaic"]
