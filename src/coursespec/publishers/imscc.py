"""IMS Common Cartridge 1.3 내보내기 (네트워크 호출 없음).

설계서를 Moodle·Canvas 등이 가져올 수 있는 이동식 ZIP 으로 만든다.
표준 CC 1.3 에 없는 기능(배지·완료 조건·선수조건·성적 가중치·날짜 등)은
조용히 버리지 않고 변환 보고서(info/warn/loss)에 남긴다.
"""

from __future__ import annotations

import html as _html
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree

from ..imscc_verify import (
    ASSIGN_NS,
    CC_NS,
    DISCUSSION_NS,
    LOM_NS,
    QTI_NS,
    VerifyResult,
    verify_imscc,
)
from ..plan import Conversion, Severity
from ..render import to_html
from ..spec import Spec

SUBMISSION = {"text": "html", "file": "file", "url": "url"}
PROFILE = {
    ("multichoice", False): "cc.multiple_choice.v0p1",
    ("multichoice", True): "cc.multiple_response.v0p1",
    ("truefalse", False): "cc.true_false.v0p1",
    ("shortanswer", False): "cc.fib.v0p1",
    ("essay", False): "cc.essay.v0p1",
}
NCNAME_BAD = re.compile(r"[^A-Za-z0-9._-]")


@dataclass
class ExportResult:
    path: Path
    conversions: list[Conversion]
    verify: VerifyResult
    resource_count: int = 0

    def counts(self) -> dict[str, int]:
        return {s: sum(c.severity == s for c in self.conversions) for s in ("info", "warn", "loss")}

    def to_text(self) -> str:
        counts = self.counts()
        lines = [
            f"내보내기 → imscc  (리소스 {self.resource_count}개, 파일 {self.path})",
            "",
        ]
        if self.conversions:
            lines.append("변환 보고서")
            mark = {"info": "  ·", "warn": "  !", "loss": "  ✗"}
            for c in self.conversions:
                lines.append(f"{mark[c.severity]} [{c.where}] {c.message}")
            lines.append(
                f"  info {counts['info']}건, warn {counts['warn']}건, loss {counts['loss']}건"
            )
            lines.append("")
        lines.append(self.verify.to_text())
        return "\n".join(lines)


def _q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def _num(value: float | int) -> str:
    return f"{value:g}"


class _PackageBuilder:
    def __init__(self, spec: Spec, base_dir: Path) -> None:
        self.spec = spec
        self.base_dir = base_dir
        self.files: dict[str, bytes] = {}
        self.resources: list[dict[str, Any]] = []
        self.units: list[tuple[str, str, list[tuple[str, str]]]] = []
        self.ids: set[str] = set()
        self.conversions: list[Conversion] = []

    def note(self, where: str, severity: Severity, message: str) -> None:
        c = Conversion(where, severity, message)
        if c not in self.conversions:
            self.conversions.append(c)

    def uid(self, prefix: str, value: str) -> str:
        cleaned = NCNAME_BAD.sub("_", value)
        if not cleaned or not re.match(r"[A-Za-z_]", cleaned):
            cleaned = "_" + cleaned
        candidate = f"{prefix}{cleaned}"
        base = candidate
        n = 2
        while candidate in self.ids:
            candidate = f"{base}_{n}"
            n += 1
        self.ids.add(candidate)
        return candidate

    def add_resource(self, identifier: str, rtype: str, href: str) -> None:
        self.resources.append({"identifier": identifier, "type": rtype, "href": href})

    def build(self) -> tuple[bytes, dict[str, bytes]]:
        for unit in self.spec.units:
            activities: list[tuple[str, str]] = []
            for item in unit.get("items", []):
                exported = self._export_item(item)
                if exported:
                    activities.append(exported)
            self.units.append((self.uid("unit_", unit["id"]), unit["title"], activities))
        self._course_notes()
        manifest = self._manifest()
        return manifest, self.files

    # -- 개별 활동 -------------------------------------------------------

    def _export_item(self, item: dict[str, Any]) -> tuple[str, str] | None:
        itype = item["type"]
        if itype == "page":
            return self._export_page(item)
        if itype == "file":
            return self._export_file(item)
        if itype in ("assignment", "peer_review"):
            return self._export_assignment(item)
        if itype == "quiz":
            return self._export_quiz(item)
        if itype == "discussion":
            return self._export_discussion(item)
        if itype in ("wiki", "glossary"):
            return self._export_wiki(item)
        if itype == "interactive_lecture":
            return self._export_lecture(item)
        if itype in ("survey", "h5p"):
            message = (
                "설문은 표준 CC 1.3 리소스로 표현할 수 없어 내보내지 않습니다."
                if itype == "survey"
                else "H5P는 표준 CC 1.3 리소스로 표현할 수 없어 내보내지 않습니다."
            )
            self.note(item["id"], "loss", message)
            return None
        raise ValueError(itype)  # pragma: no cover - 스키마가 막는다

    def _export_page(self, item: dict[str, Any]) -> tuple[str, str]:
        parts = [to_html(item.get("intro"))]
        body = to_html(item.get("content"), item.get("content_format", "markdown"))
        if body:
            parts.append(body)
        if item.get("video_url"):
            url = _html.escape(item["video_url"], quote=True)
            parts.append(f'<p><a href="{url}">동영상 보기</a></p>')
            self.note(item["id"], "info", "동영상은 링크로 넣었습니다. 임베드 여부는 가져온 LMS에서 정합니다.")
        content = "\n".join(p for p in parts if p) or f"<p>{_html.escape(item['title'])}</p>"
        href = f"web_resources/{item['id']}.html"
        self.files[href] = content.encode("utf-8")
        rid = self.uid("res_", item["id"])
        self.add_resource(rid, "webcontent", href)
        self._date_note(item)
        return item["title"], rid

    def _export_file(self, item: dict[str, Any]) -> tuple[str, str] | None:
        if "material" in item:
            material = self.spec.materials.get(item["material"])
            if material is not None and "learner" not in material.get("uses", []):
                self.note(
                    item["id"],
                    "loss",
                    f"자료 '{material['id']}'은 학습자 배포(uses: learner)가 허용되지 않아 파일을 넣지 않았습니다.",
                )
                return None
            if material is None:
                self.note(item["id"], "loss", f"자료 '{item['material']}'이 매니페스트에 없어 파일을 넣지 않았습니다.")
                return None
            source = material["source"]
        else:
            source = item["source"]

        resolved = self._resolve(source)
        if resolved is None:
            if source.startswith(("http://", "https://")):
                self.note(item["id"], "warn", "URL 자료는 네트워크를 호출하지 않으므로 패키지에 넣지 않았습니다.")
            else:
                self.note(item["id"], "warn", f"파일 '{source}'을(를) 찾을 수 없어 내보내지 않았습니다.")
            return None

        filename = item.get("filename") or resolved.name
        safe_name = NCNAME_BAD.sub("_", filename) or "file"
        href = f"files/{item['id']}/{safe_name}"
        self.files[href] = resolved.read_bytes()
        rid = self.uid("res_", item["id"])
        self.add_resource(rid, "webcontent", href)
        self.note(item["id"], "info", f"파일 '{source}'을(를) 패키지에 포함했습니다.")
        return item["title"], rid

    def _resolve(self, source: str) -> Path | None:
        if source.startswith(("http://", "https://")):
            return None
        path = Path(source)
        if path.is_absolute():
            return None
        base = self.base_dir.resolve()
        candidate = (base / path).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def _export_assignment(self, item: dict[str, Any]) -> tuple[str, str]:
        if item["type"] == "peer_review":
            self.note(
                item["id"],
                "loss",
                "동료평가의 평가 점수·평가 마감은 표준 CC 1.3에 없어 일반 과제로 내보냅니다.",
            )
        root = etree.Element(_q(ASSIGN_NS, "assignment"), nsmap={None: ASSIGN_NS})
        root.set("identifier", self.uid("asg_", item["id"]))
        etree.SubElement(root, _q(ASSIGN_NS, "title")).text = item["title"]

        text_parts = [to_html(item.get("intro"))]
        hint = self._date_hint(item)
        if hint:
            text_parts.append(hint)
        text_html = "\n".join(p for p in text_parts if p)
        if text_html:
            text = etree.SubElement(root, _q(ASSIGN_NS, "text"))
            text.set("texttype", "text/html")
            text.text = text_html

        instructor = etree.SubElement(root, _q(ASSIGN_NS, "instructor_text"))
        instructor.set("texttype", "text/plain")
        instructor.text = ""

        grading = item.get("grading", {})
        if grading.get("max") is not None:
            gradable = etree.SubElement(root, _q(ASSIGN_NS, "gradable"))
            gradable.set("points_possible", _num(grading["max"]))
            gradable.text = "true"

        types = item.get("submission", {}).get("types", ["text"])
        formats = [SUBMISSION[t] for t in types if t in SUBMISSION]
        if formats:
            container = etree.SubElement(root, _q(ASSIGN_NS, "submission_formats"))
            seen: set[str] = set()
            for fmt in formats:
                if fmt in seen:
                    continue
                seen.add(fmt)
                fmt_el = etree.SubElement(container, _q(ASSIGN_NS, "format"))
                fmt_el.set("type", fmt)

        if "rubric" in item:
            self.note(item["id"], "info", "루브릭은 표준 CC 1.3 과제 확장에 없어 패키지에 포함되지 않습니다.")
        self._date_note(item)
        href = f"assignments/{item['id']}.xml"
        self.files[href] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
        rid = self.uid("res_", item["id"])
        self.add_resource(rid, "assignment_xmlv1p0", href)
        return item["title"], rid

    def _export_quiz(self, item: dict[str, Any]) -> tuple[str, str] | None:
        questions = item.get("questions", [])
        if not questions:
            self.note(item["id"], "loss", "문항이 없는 퀴즈는 CC QTI 시험으로 내보내지 않습니다.")
            return None

        root = etree.Element(_q(QTI_NS, "questestinterop"), nsmap={None: QTI_NS})
        assessment = etree.SubElement(root, _q(QTI_NS, "assessment"))
        assessment.set("ident", self.uid("quiz_", item["id"]))
        assessment.set("title", item["title"])
        self._qti_profile(assessment, "cc.assessment.v0p1")

        section = etree.SubElement(assessment, _q(QTI_NS, "section"))
        section.set("ident", "section_1")
        has_choice_feedback = False
        for pos, question in enumerate(questions, 1):
            has_choice_feedback = self._qti_item(section, pos, question) or has_choice_feedback
        if has_choice_feedback:
            self.note(item["id"], "info", "보기별 피드백은 CC QTI 프로필에 포함하지 않았습니다.")
        self._date_note(item)

        href = f"assessments/{item['id']}.xml"
        self.files[href] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
        rid = self.uid("res_", item["id"])
        self.add_resource(rid, "imsqti_xmlv1p2/imscc_xmlv1p3/assessment", href)
        return item["title"], rid

    def _qti_item(self, section: etree._Element, pos: int, q: dict[str, Any]) -> bool:
        qtype = q["type"]
        multiple = bool(q.get("multiple"))
        profile = PROFILE.get((qtype, multiple), "cc.essay.v0p1")
        mark = _num(q.get("mark", 1))

        item = etree.SubElement(section, _q(QTI_NS, "item"))
        item.set("ident", f"q{pos}")
        item.set("title", q.get("name") or f"문항 {pos}")
        itemmeta = etree.SubElement(item, _q(QTI_NS, "itemmetadata"))
        self._qti_profile(itemmeta, profile)

        presentation = etree.SubElement(item, _q(QTI_NS, "presentation"))
        self._qti_material(presentation, to_html(q["text"]), "text/html")
        answers = [a for a in q.get("accepted_answers", []) if a]
        choice_feedback = False

        if qtype == "multichoice":
            choices = q.get("choices", [])
            response = etree.SubElement(presentation, _q(QTI_NS, "response_lid"))
            response.set("ident", "response1")
            response.set("rcardinality", "Multiple" if multiple else "Single")
            render = etree.SubElement(response, _q(QTI_NS, "render_choice"))
            labels: list[tuple[str, dict[str, Any]]] = []
            for n, choice in enumerate(choices, 1):
                cid = f"c{n}"
                labels.append((cid, choice))
                label = etree.SubElement(render, _q(QTI_NS, "response_label"))
                label.set("ident", cid)
                self._qti_material(label, choice["text"], "text/plain")
                choice_feedback = choice_feedback or bool(choice.get("feedback"))
            correct = [cid for cid, choice in labels if choice.get("correct")]
            self._qti_scoring(item, response, correct, multiple, mark)
        elif qtype == "truefalse":
            response = etree.SubElement(presentation, _q(QTI_NS, "response_lid"))
            response.set("ident", "response1")
            response.set("rcardinality", "Single")
            render = etree.SubElement(response, _q(QTI_NS, "render_choice"))
            for cid, text in (("c1", "참"), ("c2", "거짓")):
                label = etree.SubElement(render, _q(QTI_NS, "response_label"))
                label.set("ident", cid)
                self._qti_material(label, text, "text/plain")
            correct = ["c1"] if q.get("answer") else ["c2"]
            self._qti_scoring(item, response, correct, False, mark)
        elif qtype == "shortanswer":
            response = etree.SubElement(presentation, _q(QTI_NS, "response_str"))
            response.set("ident", "response1")
            response.set("rcardinality", "Single")
            fib = etree.SubElement(response, _q(QTI_NS, "render_fib"))
            fib.set("rows", "1")
            fib.set("columns", "80")
            self._qti_fib_scoring(item, response, answers, bool(q.get("case_sensitive")), mark)
        else:  # essay
            response = etree.SubElement(presentation, _q(QTI_NS, "response_str"))
            response.set("ident", "response1")
            response.set("rcardinality", "Single")
            fib = etree.SubElement(response, _q(QTI_NS, "render_fib"))
            fib.set("rows", "10")
            fib.set("columns", "80")
            resp = etree.SubElement(item, _q(QTI_NS, "resprocessing"))
            outcomes = etree.SubElement(resp, _q(QTI_NS, "outcomes"))
            self._qti_decvar(outcomes, mark)
            condition = etree.SubElement(resp, _q(QTI_NS, "respcondition"))
            condvar = etree.SubElement(condition, _q(QTI_NS, "conditionvar"))
            etree.SubElement(condvar, _q(QTI_NS, "other"))

        if q.get("feedback"):
            self.note(q.get("name") or f"문항 {pos}", "info", "일반 피드백은 CC QTI 프로필에 포함하지 않았습니다.")
        return choice_feedback

    def _qti_profile(self, parent: etree._Element, profile: str) -> None:
        meta = etree.SubElement(parent, _q(QTI_NS, "qtimetadata"))
        field = etree.SubElement(meta, _q(QTI_NS, "qtimetadatafield"))
        etree.SubElement(field, _q(QTI_NS, "fieldlabel")).text = "cc_profile"
        etree.SubElement(field, _q(QTI_NS, "fieldentry")).text = profile

    def _qti_material(self, parent: etree._Element, text: str, texttype: str) -> None:
        material = etree.SubElement(parent, _q(QTI_NS, "material"))
        mattext = etree.SubElement(material, _q(QTI_NS, "mattext"))
        mattext.set("texttype", texttype)
        mattext.text = text

    def _qti_decvar(self, parent: etree._Element, mark: str) -> None:
        decvar = etree.SubElement(parent, _q(QTI_NS, "decvar"))
        decvar.set("varname", "SCORE")
        decvar.set("vartype", "Decimal")
        decvar.set("minvalue", "0")
        decvar.set("maxvalue", mark)

    def _qti_scoring(
        self,
        item: etree._Element,
        response: etree._Element,
        correct: list[str],
        multiple: bool,
        mark: str,
    ) -> None:
        resp = etree.SubElement(item, _q(QTI_NS, "resprocessing"))
        outcomes = etree.SubElement(resp, _q(QTI_NS, "outcomes"))
        self._qti_decvar(outcomes, mark)
        condition = etree.SubElement(resp, _q(QTI_NS, "respcondition"))
        condvar = etree.SubElement(condition, _q(QTI_NS, "conditionvar"))
        respident = response.get("ident", "response1")
        if multiple and len(correct) > 1:
            group = etree.SubElement(condvar, _q(QTI_NS, "and"))
            for cid in correct:
                etree.SubElement(group, _q(QTI_NS, "varequal")).text = cid
                group[-1].set("respident", respident)
        elif correct:
            varequal = etree.SubElement(condvar, _q(QTI_NS, "varequal"))
            varequal.set("respident", respident)
            varequal.text = correct[0]
        else:
            etree.SubElement(condvar, _q(QTI_NS, "other"))
        setvar = etree.SubElement(condition, _q(QTI_NS, "setvar"))
        setvar.set("varname", "SCORE")
        setvar.set("action", "Set")
        setvar.text = mark if correct else "0"

    def _qti_fib_scoring(
        self,
        item: etree._Element,
        response: etree._Element,
        answers: list[str],
        case_sensitive: bool,
        mark: str,
    ) -> None:
        resp = etree.SubElement(item, _q(QTI_NS, "resprocessing"))
        outcomes = etree.SubElement(resp, _q(QTI_NS, "outcomes"))
        self._qti_decvar(outcomes, mark)
        condition = etree.SubElement(resp, _q(QTI_NS, "respcondition"))
        condvar = etree.SubElement(condition, _q(QTI_NS, "conditionvar"))
        respident = response.get("ident", "response1")
        case = "Yes" if case_sensitive else "No"

        def varequal(parent: etree._Element, answer: str) -> None:
            el = etree.SubElement(parent, _q(QTI_NS, "varequal"))
            el.set("respident", respident)
            el.set("case", case)
            el.text = answer

        if len(answers) > 1:
            group = etree.SubElement(condvar, _q(QTI_NS, "or"))
            for answer in answers:
                varequal(group, answer)
        elif answers:
            varequal(condvar, answers[0])
        else:
            etree.SubElement(condvar, _q(QTI_NS, "other"))
        setvar = etree.SubElement(condition, _q(QTI_NS, "setvar"))
        setvar.set("varname", "SCORE")
        setvar.set("action", "Set")
        setvar.text = mark if answers else "0"

    def _export_discussion(self, item: dict[str, Any]) -> tuple[str, str]:
        root = etree.Element(_q(DISCUSSION_NS, "topic"), nsmap={None: DISCUSSION_NS})
        etree.SubElement(root, _q(DISCUSSION_NS, "title")).text = item["title"]
        body = to_html(item.get("intro")) or to_html(item.get("content"), item.get("content_format", "markdown"))
        text = etree.SubElement(root, _q(DISCUSSION_NS, "text"))
        text.set("texttype", "text/html")
        text.text = body or f"<p>{_html.escape(item['title'])}</p>"
        if item.get("discussion", {}).get("style") == "qanda":
            self.note(item["id"], "info", "Q&A 형식은 CC 토론 리소스에 없어 일반 토론으로 가져옵니다.")
        self._date_note(item)
        href = f"discussions/{item['id']}.xml"
        self.files[href] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
        rid = self.uid("res_", item["id"])
        self.add_resource(rid, "imsdt_xmlv1p3", href)
        return item["title"], rid

    def _export_wiki(self, item: dict[str, Any]) -> tuple[str, str]:
        parts = [f"<h1>{_html.escape(item['title'])}</h1>", to_html(item.get("intro"))]
        if item.get("content") is not None:
            parts.append(to_html(item.get("content"), item.get("content_format", "markdown")))
        content = "\n".join(p for p in parts if p)
        href = f"web_resources/{item['id']}.html"
        self.files[href] = content.encode("utf-8")
        rid = self.uid("res_", item["id"])
        self.add_resource(rid, "webcontent", href)
        if item["type"] == "wiki":
            message = "위키는 일반 웹콘텐츠 페이지로 내보냅니다. 학생 편집 기능은 손실됩니다."
        else:
            message = "용어집은 일반 웹콘텐츠 페이지로 내보냅니다. 용어집 자동 링크 기능은 손실됩니다."
        self.note(item["id"], "warn", message)
        return item["title"], rid

    def _export_lecture(self, item: dict[str, Any]) -> tuple[str, str] | None:
        exports = item.get("lecture", {}).get("exports", {})
        for kind in ("html", "video"):
            source = exports.get(kind)
            if not source:
                continue
            resolved = self._resolve(source)
            if resolved is None:
                self.note(item["id"], "warn", f"내보낸 수업 파일 '{source}'을(를) 찾을 수 없습니다.")
                continue
            if kind == "html":
                href = f"web_resources/{item['id']}.html"
                self.files[href] = resolved.read_bytes()
            else:
                safe_name = NCNAME_BAD.sub("_", resolved.name) or "lecture"
                href = f"files/{item['id']}/{safe_name}"
                self.files[href] = resolved.read_bytes()
            rid = self.uid("res_", item["id"])
            self.add_resource(rid, "webcontent", href)
            what = "HTML" if kind == "html" else "동영상"
            self.note(
                item["id"],
                "warn",
                f"인터랙티브 강의를 내보낸 {what}로 넣었습니다. AI 교사·급우와의 상호작용과 AI 채점은 손실됩니다.",
            )
            return item["title"], rid
        self.note(
            item["id"],
            "loss",
            "인터랙티브 강의의 HTML·동영상 내보내기(lecture.exports)가 없어 내보내지 않았습니다.",
        )
        return None

    # -- 공통 ------------------------------------------------------------

    def _date_hint(self, item: dict[str, Any]) -> str:
        bits = []
        if item.get("opens_day"):
            bits.append(f"공개 {item['opens_day']}일차")
        if item.get("due_day"):
            bits.append(f"마감 {item['due_day']}일차")
        if item.get("cutoff_day"):
            bits.append(f"최종 마감 {item['cutoff_day']}일차")
        return f"<p>{_html.escape(' · '.join(bits))}</p>" if bits else ""

    def _date_note(self, item: dict[str, Any]) -> None:
        if any(item.get(k) for k in ("opens_day", "due_day", "cutoff_day")):
            self.note(
                item["id"],
                "info",
                "공개일·마감일은 표준 CC 1.3에 없어 패키지에 날짜로 들어가지 않습니다 (본문 힌트만 포함).",
            )

    def _course_notes(self) -> None:
        if any(item.get("completion", {}).get("mode", "none") != "none" for _, _, item in self.spec.iter_items()):
            self.note("course", "info", "완료 조건은 표준 CC 1.3에 없어 패키지에 포함되지 않습니다.")
        if any(item.get("requires") for _, _, item in self.spec.iter_items()) or any(
            unit.get("requires") for unit in self.spec.units
        ):
            self.note("course", "info", "선수조건은 표준 CC 1.3에 없어 패키지에 포함되지 않습니다.")
        if self.spec.categories:
            self.note("grading", "info", "성적 카테고리와 가중치는 표준 CC 1.3에 없어 패키지에 포함되지 않습니다.")
        for badge in self.spec.badges:
            self.note(badge["id"], "loss", "배지는 표준 CC 1.3에 없어 내보내지 않습니다.")

    def _manifest(self) -> bytes:
        root = etree.Element(_q(CC_NS, "manifest"), nsmap={None: CC_NS, "lomimscc": LOM_NS})
        root.set("identifier", self.uid("man_", self.spec.id))

        metadata = etree.SubElement(root, _q(CC_NS, "metadata"))
        etree.SubElement(metadata, _q(CC_NS, "schema")).text = "IMS Common Cartridge"
        etree.SubElement(metadata, _q(CC_NS, "schemaversion")).text = "1.3.0"
        etree.SubElement(metadata, _q(LOM_NS, "lom"))

        organizations = etree.SubElement(root, _q(CC_NS, "organizations"))
        organization = etree.SubElement(organizations, _q(CC_NS, "organization"))
        organization.set("identifier", self.uid("org_", "1"))
        organization.set("structure", "rooted-hierarchy")
        etree.SubElement(organization, _q(CC_NS, "title")).text = self.spec.title

        top = etree.SubElement(organization, _q(CC_NS, "item"))
        top.set("identifier", "LearningModules")
        self.ids.add("LearningModules")
        for unit_id, title, activities in self.units:
            unit = etree.SubElement(top, _q(CC_NS, "item"))
            unit.set("identifier", unit_id)
            etree.SubElement(unit, _q(CC_NS, "title")).text = title
            for activity_title, resource_id in activities:
                activity = etree.SubElement(unit, _q(CC_NS, "item"))
                activity.set("identifier", self.uid("it_", resource_id[4:]))
                activity.set("identifierref", resource_id)
                etree.SubElement(activity, _q(CC_NS, "title")).text = activity_title

        resources = etree.SubElement(root, _q(CC_NS, "resources"))
        for resource in self.resources:
            el = etree.SubElement(resources, _q(CC_NS, "resource"))
            el.set("identifier", resource["identifier"])
            el.set("type", resource["type"])
            el.set("href", resource["href"])
            file_el = etree.SubElement(el, _q(CC_NS, "file"))
            file_el.set("href", resource["href"])

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def export_imscc(
    spec: Spec, dest: str | Path, *, base_dir: Path | None = None
) -> ExportResult:
    """설계서를 IMS Common Cartridge 1.3 ZIP 으로 쓰고 같은 검증을 실행한다."""
    destination = Path(dest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    root = base_dir if base_dir is not None else (spec.path.parent if spec.path else Path.cwd())

    builder = _PackageBuilder(spec, Path(root))
    manifest, files = builder.build()

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("imsmanifest.xml", manifest)
        for name, data in sorted(files.items()):
            zf.writestr(name, data)

    return ExportResult(
        path=destination,
        conversions=builder.conversions,
        verify=verify_imscc(destination),
        resource_count=len(builder.resources),
    )
