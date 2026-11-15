"""CourseSpec — LMS 중립 과정 설계서와 퍼블리셔."""

from .spec import Spec, SpecError, load_spec

__all__ = ["Spec", "SpecError", "load_spec"]
__version__ = "0.3.0"
