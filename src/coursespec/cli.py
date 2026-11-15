"""coursespec 명령줄 도구.

    coursespec validate   SPEC
    coursespec lint       SPEC
    coursespec plan       SPEC --target moodle|canvas --start YYYY-MM-DD [--course-id N] [--json]
    coursespec plan       SPEC --target openmaic [--server NAME] [--regenerate] [--json]
    coursespec diff       SPEC --target moodle --course-id N --start YYYY-MM-DD --outline FILE [--json]
    coursespec export     SPEC --format imscc [--out FILE] [--force]
    coursespec verify     PACKAGE.imscc
    coursespec verify-lms SPEC --target canvas --snapshot FILE [--verify-steps FILE] [--json]
    coursespec patch      SPEC PATCH.json|- [--dry-run]
    coursespec tutor-pack SPEC [--start YYYY-MM-DD] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .lint import lint
from .patch import PatchError, patch_file
from .publishers import TARGETS
from .spec import SpecError, load_spec
from .tutor import skill_md, tutor_pack


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="coursespec", description="LMS 중립 과정 설계서 도구")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "lint"):
        p = sub.add_parser(name)
        p.add_argument("spec", nargs="+", help="설계서 파일 (여러 개 가능)")

    p = sub.add_parser("plan", help="배포·생성 계획 (네트워크 호출 없음)")
    p.add_argument("spec")
    p.add_argument("--target", choices=sorted(TARGETS), required=True)
    p.add_argument("--start", type=date.fromisoformat, help="과정 시작일 YYYY-MM-DD (LMS 대상은 필수)")
    p.add_argument("--course-id", type=int, help="기존 강좌에 배포")
    p.add_argument("--category-id", type=int, default=1, help="moodle: 새 강좌 카테고리")
    p.add_argument("--visible", type=int, choices=[0, 1], default=0, help="moodle: 새 강좌 공개 여부 (기본 0)")
    p.add_argument(
        "--enable-completion",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="moodle: 새 강좌의 완료 추적 (기본 켜짐)",
    )
    p.add_argument("--account-id", type=int, help="canvas: 새 강좌를 만들 계정")
    p.add_argument("--canvas-quiz", choices=["new", "classic"], default="new", help="canvas: 퀴즈 API (기본 new)")
    p.add_argument("--post-import", action="store_true", help="canvas: 가져온 IMSCC 강좌를 제목으로 찾아 보완")
    p.add_argument("--server", help="openmaic: 수업 기록에 남길 서버 이름")
    p.add_argument("--regenerate", action="store_true", help="openmaic: 이미 생성된 수업도 다시 생성")
    p.add_argument("--json", action="store_true", help="실행기용 JSON 출력")
    p.add_argument("--force", action="store_true", help="린트 오류가 있어도 계획 생성")

    p = sub.add_parser("diff", help="LMS 스냅샷과 설계서의 차이 계획 (네트워크 호출 없음)")
    p.add_argument("spec")
    p.add_argument("--target", choices=["moodle"], required=True)
    p.add_argument("--course-id", type=int, required=True)
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--outline", required=True, help="get_course_outline 결과 JSON")
    p.add_argument("--gradebook", help="gradebook_overview 결과 JSON (선택)")
    p.add_argument("--record", help="마지막 배포 기록 JSON (선택)")
    p.add_argument("--accept-drift", action="store_true", help="LMS 에서 직접 바뀐 값을 덮어쓴다")
    p.add_argument("--json", action="store_true", help="실행기용 JSON 출력")
    p.add_argument("--force", action="store_true", help="린트 오류가 있어도 차이 계획 생성")

    p = sub.add_parser("export", help="IMS Common Cartridge 등 패키지 내보내기 (네트워크 호출 없음)")
    p.add_argument("spec")
    p.add_argument("--format", choices=["imscc"], default="imscc")
    p.add_argument("--out", help="출력 파일 (기본: <설계서 id>.imscc)")
    p.add_argument("--force", action="store_true", help="린트 오류가 있어도 내보내기")

    p = sub.add_parser("verify", help="내보낸 패키지 로컬 검증")
    p.add_argument("package")

    p = sub.add_parser("verify-lms", help="LMS 가져오기 스냅샷과 설계서 비교 (네트워크 호출 없음)")
    p.add_argument("spec")
    p.add_argument("--target", choices=["canvas"], required=True)
    p.add_argument("--snapshot", required=True, help="실행기가 읽어 둔 Canvas REST 스냅샷 JSON")
    p.add_argument("--verify-steps", help="REST plan verify=True 단계 실행 결과 JSON (선택)")
    p.add_argument("--json", action="store_true", help="실행기용 JSON 출력")

    p = sub.add_parser("patch", help="검증된 JSON Patch 로 설계서 수정")
    p.add_argument("spec")
    p.add_argument("patch", help="RFC 6902 연산 배열 JSON 파일, '-' 이면 표준 입력")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("tutor-pack", help="학습자 튜터용 강좌 설정 생성")
    p.add_argument("spec")
    p.add_argument("--start", type=date.fromisoformat)
    p.add_argument("--out", help="tutor-pack.json 과 SKILL.md 를 쓸 디렉터리 (없으면 JSON 을 출력)")
    args = ap.parse_args(argv)

    if args.cmd == "patch":
        return _patch(args)
    if args.cmd == "verify":
        return _verify(args)
    if args.cmd in ("validate", "lint"):
        return _check_specs(args)

    try:
        spec = load_spec(args.spec)
    except SpecError as exc:
        _print_errors(str(exc), exc.errors)
        return 2

    if args.cmd == "verify-lms":
        return _verify_lms(args, spec)

    findings = lint(spec)
    errors = [f for f in findings if f.is_error]

    if errors and not getattr(args, "force", False):
        _print_errors(
            "린트 오류가 있어 진행하지 않았습니다 (plan·export 는 --force 로 무시).",
            [str(f) for f in errors],
        )
        return 1

    if args.cmd == "export":
        return _export(args, spec)

    if args.cmd == "diff":
        return _diff(args, spec)

    if args.cmd == "tutor-pack":
        pack = tutor_pack(spec, args.start)
        if args.out:
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / "tutor-pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", "utf-8")
            (out / "SKILL.md").write_text(skill_md(spec, pack), "utf-8")
            print(f"✓ {out / 'tutor-pack.json'}, {out / 'SKILL.md'}")
        else:
            print(json.dumps(pack, ensure_ascii=False, indent=2))
        return 0

    if args.target in ("moodle", "canvas") and args.start is None:
        _print_errors(f"--target {args.target} 에는 --start 가 필요합니다.", [])
        return 2
    if args.target == "moodle":
        kwargs = {
            "course_id": args.course_id,
            "category_id": args.category_id,
            "visible": args.visible,
            "enablecompletion": 1 if args.enable_completion else 0,
        }
    elif args.target == "canvas":
        kwargs = {
            "course_id": args.course_id,
            "account_id": args.account_id,
            "quiz_api": args.canvas_quiz,
            "post_import": args.post_import,
        }
    else:
        kwargs = {"server": args.server, "regenerate": args.regenerate}
    try:
        plan = TARGETS[args.target](spec, args.start, **kwargs)
    except ValueError as exc:
        _print_errors(str(exc), [])
        return 2
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) if args.json else plan.to_text())
    return 0


def _check_specs(args: argparse.Namespace) -> int:
    status = 0
    multiple = len(args.spec) > 1
    for name in args.spec:
        try:
            spec = load_spec(name)
        except SpecError as exc:
            _print_errors(f"{name}: {exc}", exc.errors)
            return 2
        if args.cmd == "validate":
            print(
                f"✓ 스키마 통과: {spec.id} "
                f"(단원 {len(spec.units)}개, 활동 {len(spec.items)}개, 자료 {len(spec.materials)}개)"
            )
            continue
        if multiple:
            print(f"# {name}")
        findings = lint(spec)
        errors = [f for f in findings if f.is_error]
        for f in findings:
            print(f"{'✗' if f.is_error else '!'} {f}")
        print(f"오류 {len(errors)}건, 경고 {len(findings) - len(errors)}건")
        if errors:
            status = 1
    return status


def _read_json(path: str, label: str):
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except OSError as exc:
        _print_errors(f"{label} 파일을 읽지 못했습니다: {exc}", [])
    except json.JSONDecodeError as exc:
        _print_errors(f"{label} JSON 구문 오류: {exc}", [])
    return None


def _diff(args: argparse.Namespace, spec) -> int:
    from .diff import diff_moodle

    outline = _read_json(args.outline, "--outline")
    if outline is None:
        return 2
    gradebook = _read_json(args.gradebook, "--gradebook") if args.gradebook else None
    if args.gradebook and gradebook is None:
        return 2
    record = _read_json(args.record, "--record") if args.record else None
    if args.record and record is None:
        return 2
    try:
        result = diff_moodle(
            spec,
            args.start,
            args.course_id,
            outline,
            gradebook=gradebook,
            record=record,
            accept_drift=args.accept_drift,
        )
    except ValueError as exc:
        _print_errors(str(exc), [])
        return 2
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) if args.json else result.to_text())
    return 2 if result.blocked else 0


def _export(args: argparse.Namespace, spec) -> int:
    from .publishers.imscc import export_imscc

    out = Path(args.out) if args.out else Path(f"{spec.id}.imscc")
    try:
        result = export_imscc(spec, out)
    except OSError as exc:
        _print_errors(f"내보내지 못했습니다: {exc}", [])
        return 2
    print(result.to_text())
    return 0 if not result.verify.errors else 1


def _verify(args: argparse.Namespace) -> int:
    from .imscc_verify import verify_imscc

    try:
        result = verify_imscc(Path(args.package))
    except OSError as exc:
        _print_errors(f"검증하지 못했습니다: {exc}", [])
        return 2
    print(result.to_text())
    return 0 if not result.errors else 1


def _verify_lms(args: argparse.Namespace, spec) -> int:
    from .canvas_verify import verify_canvas

    snapshot = _read_json(args.snapshot, "--snapshot")
    if snapshot is None:
        return 2
    steps = _read_json(args.verify_steps, "--verify-steps") if args.verify_steps else None
    if args.verify_steps and steps is None:
        return 2
    try:
        result = verify_canvas(spec, snapshot, verify_steps=steps)
    except ValueError as exc:
        _print_errors(str(exc), [])
        return 2
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) if args.json else result.to_text())
    return 0 if result.ok else 1


def _patch(args: argparse.Namespace) -> int:
    raw = sys.stdin.read() if args.patch == "-" else Path(args.patch).read_text("utf-8")
    try:
        ops = json.loads(raw)
        if not isinstance(ops, list):
            raise PatchError("패치는 연산의 배열이어야 합니다.")
        findings = patch_file(args.spec, ops, dry_run=args.dry_run)
    except json.JSONDecodeError as exc:
        _print_errors(f"패치 JSON 구문 오류: {exc}", [])
        return 2
    except PatchError as exc:
        _print_errors(f"패치를 적용하지 않았습니다: {exc}", exc.errors)
        return 1
    print(f"✓ 패치 {'검증' if args.dry_run else '적용'} 완료 ({len(ops)}개 연산, 경고 {len(findings)}건)")
    for f in findings:
        print(f"! {f}")
    return 0


def _print_errors(message: str, errors: list[str]) -> None:
    print(f"✗ {message}", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
