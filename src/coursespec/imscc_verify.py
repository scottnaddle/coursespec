"""IMS Common Cartridge 1.3 패키지 로컬 검증.

네트워크를 쓰지 않는다. 저장소(또는 패키지 데이터)에 포함된 공식 1EdTech XSD 로
매니페스트와 과제·토론·웹링크·QTI 리소스를 검증하고, ZIP 안의 파일 참조와
Canvas/Moodle 가져오기 호환성 규칙을 점검한다.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path

from lxml import etree

CC_NS = "http://www.imsglobal.org/xsd/imsccv1p3/imscp_v1p1"
LOM_NS = "http://ltsc.ieee.org/xsd/imsccv1p3/LOM/manifest"
ASSIGN_NS = "http://www.imsglobal.org/xsd/imscc_extensions/assignment"
DISCUSSION_NS = "http://www.imsglobal.org/xsd/imsccv1p3/imsdt_v1p3"
WEBLINK_NS = "http://www.imsglobal.org/xsd/imsccv1p3/imswl_v1p3"
QTI_NS = "http://www.imsglobal.org/xsd/ims_qtiasiv1p2"

CP_XSD = "ccv1p3_imscp_v1p2_v1p0.xsd"
RESOURCE_XSD = {
    "assignment_xmlv1p0": (
        "cc_extresource_assignmentv1p0_v1p0.xsd",
        f"{{{ASSIGN_NS}}}assignment",
    ),
    "imsdt_xmlv1p3": ("ccv1p3_imsdt_v1p3.xsd", f"{{{DISCUSSION_NS}}}topic"),
    "imswl_xmlv1p3": ("ccv1p3_imswl_v1p3.xsd", f"{{{WEBLINK_NS}}}webLink"),
    "imsqti_xmlv1p2/imscc_xmlv1p3/assessment": (
        "ccv1p3_qtiasiv1p2p1_v1p0.xsd",
        f"{{{QTI_NS}}}questestinterop",
    ),
}
KNOWN_TYPES = {
    "webcontent",
    "imsqti_xmlv1p2/imscc_xmlv1p3/assessment",
    "imsqti_xmlv1p2/imscc_xmlv1p3/question-bank",
    "associatedcontent/imscc_xmlv1p3/learning-application-resource",
    "imsdt_xmlv1p3",
    "imswl_xmlv1p3",
    "imsbasiclti_xmlv1p3",
    "idpfepub_epubv3p0",
    "imsapip_zipv1p0",
    "imsiwb_iwbv1p0",
    "assignment_xmlv1p0",
}
NCNAME = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]*$")


@dataclass
class VerifyResult:
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_text(self) -> str:
        lines = [f"검증: {self.path}"]
        for e in self.errors:
            lines.append(f"✗ {e}")
        for w in self.warnings:
            lines.append(f"! {w}")
        lines.append(f"오류 {len(self.errors)}건, 경고 {len(self.warnings)}건")
        return "\n".join(lines)


@lru_cache(maxsize=1)
def schema_root() -> Path:
    """소스 체크아웃의 schema/imscc 또는 설치된 패키지 데이터의 경로."""
    candidates = [Path(__file__).resolve().parents[2] / "schema" / "imscc"]
    try:
        packaged = resources.files("coursespec").joinpath("schema", "imscc")
        candidates.append(Path(str(packaged)))
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    for candidate in candidates:
        if (candidate / CP_XSD).is_file():
            return candidate
    raise FileNotFoundError(
        "schema/imscc 를 찾을 수 없습니다. 공식 CC 1.3 XSD 가 설치되어 있는지 확인하세요."
    )


class _LocalResolver(etree.Resolver):
    """공식 스키마의 http(s) URL 을 로컬 XSD 파일로 바꾼다 (네트워크 금지)."""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def resolve(self, url: str, public_id: str, context):  # type: ignore[override]
        name = url.rstrip("/").rsplit("/", 1)[-1]
        for candidate in (self.root / name, self.root / "LOM" / name):
            if candidate.is_file():
                return self.resolve_filename(str(candidate), context)
        return None


def _parser(root: Path) -> etree.XMLParser:
    parser = etree.XMLParser(no_network=True, resolve_entities=False, load_dtd=False)
    parser.resolvers.add(_LocalResolver(root))
    return parser


@lru_cache(maxsize=8)
def _xml_schema(name: str) -> etree.XMLSchema:
    root = schema_root()
    doc = etree.parse(str(root / name), _parser(root))
    return etree.XMLSchema(doc)


def _safe_href(href: str) -> str | None:
    if not href or href.startswith(("/", "\\")) or "://" in href:
        return None
    if re.match(r"^[A-Za-z]:", href):  # Windows 절대 경로
        return None
    clean = href.replace("\\", "/")
    parts = clean.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    return clean


def _validate_resource_xml(
    zf: zipfile.ZipFile, href: str, xsd: str, expected: str, result: VerifyResult
) -> None:
    try:
        data = zf.read(href)
    except KeyError:
        return  # 파일 없음은 앞에서 오류로 기록했다.
    try:
        doc = etree.fromstring(data, _parser(schema_root()))
    except etree.XMLSyntaxError as exc:
        result.errors.append(f"{href}: XML 구문 오류 ({exc})")
        return
    if doc.tag != expected:
        result.errors.append(f"{href}: 루트 요소가 {expected} 가 아닙니다 ({doc.tag}).")
        return
    schema = _xml_schema(xsd)
    if not schema.validate(doc):
        for err in schema.error_log:
            result.errors.append(f"{href}: XSD 검증 실패 (line {err.line}): {err.message}")


def verify_imscc(path: str | Path) -> VerifyResult:
    """IMS Common Cartridge 1.3 ZIP 을 검증한다. warnings 는 가져오기 힌트다."""
    package = Path(path)
    result = VerifyResult(package)
    if not package.is_file():
        result.errors.append("패키지 파일이 없습니다.")
        return result
    if not zipfile.is_zipfile(package):
        result.errors.append("ZIP 파일이 아닙니다.")
        return result

    with zipfile.ZipFile(package) as zf:
        names = set(zf.namelist())
        if "imsmanifest.xml" not in names:
            result.errors.append("ZIP 루트에 imsmanifest.xml 이 없습니다 (감싸는 폴더가 있으면 안 됩니다).")
            return result
        try:
            manifest_bytes = zf.read("imsmanifest.xml")
            manifest = etree.fromstring(manifest_bytes, _parser(schema_root()))
        except etree.XMLSyntaxError as exc:
            result.errors.append(f"imsmanifest.xml: XML 구문 오류 ({exc})")
            return result

        _check_metadata(manifest, result)
        _check_identifiers(manifest, result)
        _check_resources(zf, names, manifest, result)
        _check_manifest_xsd(manifest, result)
        _check_compatibility(names, manifest, result)

    return result


def _child(el: etree._Element, ns: str, name: str) -> etree._Element | None:
    return el.find(f"{{{ns}}}{name}")


def _check_metadata(manifest: etree._Element, result: VerifyResult) -> None:
    if manifest.tag != f"{{{CC_NS}}}manifest":
        result.errors.append(f"imsmanifest.xml 의 루트가 CC 1.3 manifest 가 아닙니다 ({manifest.tag}).")
        return
    metadata = _child(manifest, CC_NS, "metadata")
    if metadata is None:
        result.errors.append("manifest/metadata 가 없습니다.")
        return
    schema = _child(metadata, CC_NS, "schema")
    version = _child(metadata, CC_NS, "schemaversion")
    if schema is None or (schema.text or "").strip() != "IMS Common Cartridge":
        result.errors.append("metadata/schema 는 'IMS Common Cartridge' 여야 합니다.")
    if version is None or (version.text or "").strip() != "1.3.0":
        result.errors.append("metadata/schemaversion 은 '1.3.0' 이어야 합니다.")
    if _child(metadata, LOM_NS, "lom") is None:
        result.errors.append("manifest/metadata 에 LOM 메타데이터(lomimscc:lom)가 없습니다.")


def _check_identifiers(manifest: etree._Element, result: VerifyResult) -> None:
    seen: dict[str, str] = {}
    for el in manifest.iter():
        if not isinstance(el.tag, str):
            continue
        value = el.get("identifier")
        if value is None:
            continue
        if not NCNAME.match(value):
            result.errors.append(
                f"XML 식별자 '{value}' 가 xs:ID(NCName) 규칙에 맞지 않습니다. 문자로 시작하고 콜론을 쓰지 마세요."
            )
        if value in seen:
            result.errors.append(
                f"XML 식별자 '{value}' 가 중복됩니다 ({seen[value]} / {el.tag})."
            )
        else:
            seen[value] = el.tag


def _check_resources(
    zf: zipfile.ZipFile, names: set[str], manifest: etree._Element, result: VerifyResult
) -> None:
    resources = manifest.findall(f"{{{CC_NS}}}resources/{{{CC_NS}}}resource")
    resource_ids = {r.get("identifier") for r in resources if r.get("identifier")}
    if not resources:
        result.warnings.append("manifest/resources 에 리소스가 없습니다. 가져올 활동이 없습니다.")

    for item in manifest.iter(f"{{{CC_NS}}}item"):
        ref = item.get("identifierref")
        if ref and ref not in resource_ids:
            result.errors.append(f"item '{item.get('identifier')}' 의 identifierref '{ref}' 가 리소스에 없습니다.")

    for resource in resources:
        rid = resource.get("identifier", "(식별자 없음)")
        rtype = resource.get("type", "")
        if rtype not in KNOWN_TYPES:
            result.errors.append(f"리소스 '{rid}' 의 type '{rtype}' 은 CC 1.3 허용 목록에 없습니다.")

        hrefs: list[str] = []
        href = resource.get("href")
        if href:
            hrefs.append(href)
        hrefs.extend(f.get("href", "") for f in resource.findall(f"{{{CC_NS}}}file"))
        hrefs = list(dict.fromkeys(hrefs))

        valid_hrefs: list[str] = []
        for raw in hrefs:
            safe = _safe_href(raw)
            if safe is None:
                result.errors.append(f"리소스 '{rid}' 의 href '{raw}' 가 절대 경로이거나 '..' 를 포함합니다.")
                continue
            valid_hrefs.append(safe)
            if safe not in names:
                result.errors.append(f"리소스 '{rid}' 가 가리키는 파일 '{safe}' 이 ZIP 안에 없습니다.")

        spec = RESOURCE_XSD.get(rtype)
        if spec:
            candidates = [h for h in valid_hrefs if h.lower().endswith(".xml")]
            if not candidates:
                candidates = valid_hrefs
            if not candidates:
                result.errors.append(f"리소스 '{rid}' ({rtype}) 에 검증할 XML 파일이 없습니다.")
            for xml_href in candidates:
                _validate_resource_xml(zf, xml_href, spec[0], spec[1], result)


def _check_manifest_xsd(manifest: etree._Element, result: VerifyResult) -> None:
    schema = _xml_schema(CP_XSD)
    if not schema.validate(manifest):
        for err in schema.error_log:
            result.errors.append(f"imsmanifest.xml: XSD 검증 실패 (line {err.line}): {err.message}")


def _check_compatibility(names: set[str], manifest: etree._Element, result: VerifyResult) -> None:
    organizations = manifest.findall(f"{{{CC_NS}}}organizations/{{{CC_NS}}}organization")
    if not organizations:
        result.errors.append("organization 이 없습니다.")
        return
    if len(organizations) > 1:
        result.errors.append("organization 은 하나만 허용됩니다.")
    org = organizations[0]
    if org.get("structure") != "rooted-hierarchy":
        result.errors.append("organization structure 는 'rooted-hierarchy' 여야 합니다.")
    top = org.find(f"{{{CC_NS}}}item")
    if top is None:
        result.errors.append("organization 아래에 최상위 item 이 없습니다.")
        return
    if top.find(f"{{{CC_NS}}}title") is not None:
        result.errors.append("organization 의 최상위 item 에는 title 을 넣을 수 없습니다.")
    modules = top.findall(f"{{{CC_NS}}}item")
    if not modules:
        result.errors.append("조직에 단원(모듈) item 이 없습니다.")
    for module in modules:
        if module.find(f"{{{CC_NS}}}title") is None:
            result.errors.append(f"단원 item '{module.get('identifier')}' 에 title 이 없습니다.")
        if not module.findall(f"{{{CC_NS}}}item"):
            result.warnings.append(f"단원 '{module.get('identifier')}' 에 활동 item 이 없습니다.")

    if "course_settings/canvas_export.txt" in names:
        result.warnings.append(
            "Canvas 전용 내보내기 파일(course_settings/canvas_export.txt)이 있습니다. "
            "이 패키지는 Moodle·Canvas 공용 CC 1.3 이며 Canvas 카트리지가 아닙니다."
        )
