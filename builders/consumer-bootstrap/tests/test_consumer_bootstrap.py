from __future__ import annotations

import io
import json
import py_compile
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
PACKET_WORKFLOW_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "packet-workflow" / "scripts"
REWORD_SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / "builders"
    / "packet-workflow"
    / "retained-skills"
    / "reword-recent-commits"
    / "scripts"
)
GIT_SPLIT_SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / "builders"
    / "packet-workflow"
    / "retained-skills"
    / "git-split-and-commit"
    / "scripts"
)
for candidate in (SCRIPT_DIR, PACKET_WORKFLOW_SCRIPT_DIR, REWORD_SCRIPT_DIR, GIT_SPLIT_SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import collect_recent_commits as reword_collect
import collect_worktree_context as worktree_collect
import init_consumer_codex as bootstrap


def create_skill_dir(root: Path, name: str) -> Path:
    skill_dir = root / name
    (skill_dir / "agents").mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill\n---\n",
        encoding="utf-8",
    )
    (skill_dir / "agents" / "openai.yaml").write_text(
        'display_name: "Test"\n',
        encoding="utf-8",
    )
    return skill_dir


def create_agent_file(root: Path, name: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    agent_path = root / f"{name}.toml"
    agent_path.write_text(
        "\n".join(
            [
                f'name = "{name.replace("-", "_")}"',
                'description = "test agent"',
                'developer_instructions = """',
                "Do not edit files.",
                '"""',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return agent_path


def create_consumer_repo(
    root: Path,
    *,
    include_readme: bool = True,
    root_agents_text: str | None = None,
    codex_agents_text: str | None = None,
    existing_profile: bool = False,
    include_vendor: bool = True,
    vendor_skill_names: list[str] | None = None,
    vendor_agent_names: list[str] | None = None,
    root_skill_names: list[str] | None = None,
    root_agent_names: list[str] | None = None,
    legacy_skill_names: list[str] | None = None,
    legacy_agent_names: list[str] | None = None,
) -> Path:
    repo = root / "consumer"
    repo.mkdir()
    (repo / ".git").mkdir()
    if include_readme:
        (repo / "README.md").write_text("# Consumer Repo\n", encoding="utf-8")
    if include_vendor:
        vendor_skill_root = (
            repo / ".codex" / "vendor" / "packetflow_foundry" / ".agents" / "skills"
        )
        vendor_skill_root.mkdir(parents=True)
        for skill_name in vendor_skill_names or []:
            create_skill_dir(vendor_skill_root, skill_name)
        vendor_agent_root = (
            repo / ".codex" / "vendor" / "packetflow_foundry" / ".codex" / "agents"
        )
        vendor_agent_root.mkdir(parents=True)
        for agent_name in vendor_agent_names or []:
            create_agent_file(vendor_agent_root, agent_name)
    if root_agents_text is not None:
        (repo / "AGENTS.md").write_text(root_agents_text, encoding="utf-8")
    if codex_agents_text is not None:
        codex_agents_path = repo / ".codex" / "AGENTS.md"
        codex_agents_path.parent.mkdir(parents=True, exist_ok=True)
        codex_agents_path.write_text(codex_agents_text, encoding="utf-8")
    if existing_profile:
        profile_path = repo / bootstrap.PROJECT_PROFILE_RELATIVE
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text("{}", encoding="utf-8")
    for skill_name in root_skill_names or []:
        create_skill_dir(repo / bootstrap.ROOT_SKILLS_RELATIVE, skill_name)
    for agent_name in root_agent_names or []:
        create_agent_file(repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE, agent_name)
    for skill_name in legacy_skill_names or []:
        create_skill_dir(repo / bootstrap.LEGACY_PROJECT_SKILLS_RELATIVE, skill_name)
    for agent_name in legacy_agent_names or []:
        create_agent_file(repo / bootstrap.LEGACY_PROJECT_AGENTS_RELATIVE, agent_name)
    return repo


def run_bootstrap_main(
    repo: Path,
    *,
    symlink_side_effect: Exception | None = None,
) -> tuple[int, str, str, mock.Mock]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    symlink_mock = mock.Mock()
    if symlink_side_effect is not None:
        symlink_mock.side_effect = symlink_side_effect

    with (
        mock.patch.object(sys, "argv", ["init_consumer_codex.py", "--repo-root", str(repo)]),
        mock.patch.object(Path, "symlink_to", symlink_mock),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        code = bootstrap.main()

    return code, stdout.getvalue(), stderr.getvalue(), symlink_mock


class ConsumerBootstrapTests(unittest.TestCase):
    def test_script_compiles(self) -> None:
        py_compile.compile(
            str(SCRIPT_DIR / "init_consumer_codex.py"),
            doraise=True,
        )

    def test_init_creates_codex_scaffold_without_root_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )
            vendor_skill_dir = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
            )
            vendor_wrapper_files = sorted(
                str(path.relative_to(vendor_skill_dir)).replace("\\", "/")
                for path in vendor_skill_dir.rglob("*")
                if path.is_file()
            )
            self.assertEqual(vendor_wrapper_files, ["SKILL.md", "agents/openai.yaml"])
            vendor_agent_dir = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
            )
            vendor_agent_files = sorted(
                path.name for path in vendor_agent_dir.iterdir() if path.is_file()
            )
            self.assertEqual(vendor_agent_files, ["vendor-agent.toml"])

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertIn("root AGENTS.md: not present", stdout)
            self.assertIn(".codex/AGENTS.md: created", stdout)
            self.assertIn(".codex/agents: ready", stdout)
            self.assertIn("agent bridge:", stdout)
            self.assertIn("vendor-agent", stdout)
            self.assertIn(".agents/skills: ready", stdout)
            self.assertIn("skill bridge:", stdout)
            self.assertIn("vendor-skill", stdout)
            self.assertEqual(symlink_mock.call_count, 2)
            self.assertFalse((repo / "AGENTS.md").exists())
            self.assertTrue((repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE).is_dir())
            self.assertTrue((repo / bootstrap.ROOT_SKILLS_RELATIVE).is_dir())

            codex_agents = (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn(bootstrap.BOOTSTRAP_MARKER_START, codex_agents)
            self.assertIn(".codex/agents/", codex_agents)
            self.assertIn(
                ".codex/vendor/packetflow_foundry/.codex/agents/",
                codex_agents,
            )
            self.assertIn(".agents/skills/", codex_agents)
            self.assertIn("thin discovery-wrapper surface", codex_agents)
            self.assertIn(
                ".codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/",
                codex_agents,
            )
            self.assertIn(
                ".codex/project/profiles/default/profile.json",
                codex_agents,
            )
            self.assertIn(
                ".codex/project/profiles/<skill-name>/profile.json",
                codex_agents,
            )

            profile = json.loads(
                (repo / bootstrap.PROJECT_PROFILE_RELATIVE).read_text(encoding="utf-8")
            )
            self.assertEqual(profile["kind"], bootstrap.PROJECT_LOCAL_PROFILE_KIND)
            self.assertEqual(
                profile["profile_path"],
                bootstrap.PROJECT_PROFILE_RELATIVE.as_posix(),
            )
            self.assertEqual(profile["repo_match"]["root_markers"], [".git", "README.md"])
            self.assertIn("project-local scaffold", profile["summary"].lower())
            self.assertTrue(
                any(
                    "not a reusable foundry overlay" in note
                    for note in profile["notes"]
                )
            )
            self.assertTrue(
                any(
                    ".codex/project/profiles/<skill-name>/profile.json" in note
                    for note in profile["notes"]
                )
            )
            self.assertEqual(stderr.strip(), "")

    def test_root_markers_skip_readme_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                include_readme=False,
                vendor_skill_names=["vendor-skill"],
            )

            code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(code, 0)

            profile = json.loads(
                (repo / bootstrap.PROJECT_PROFILE_RELATIVE).read_text(encoding="utf-8")
            )
            self.assertEqual(profile["repo_match"]["root_markers"], [".git"])

    def test_existing_agents_files_append_once_then_stay_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                root_agents_text="# Root AGENTS\n",
                codex_agents_text="# Local Codex AGENTS\n",
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )

            first_code, first_stdout, _, _ = run_bootstrap_main(repo)
            self.assertEqual(first_code, 0)
            create_skill_dir(repo / bootstrap.ROOT_SKILLS_RELATIVE, "vendor-skill")
            create_agent_file(repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE, "vendor-agent")
            (repo / bootstrap.PROJECT_PROFILE_RELATIVE).unlink()

            second_code, second_stdout, _, _ = run_bootstrap_main(repo)

            self.assertEqual(second_code, 0)
            self.assertIn("root AGENTS.md: appended foundry block", first_stdout)
            self.assertIn(".codex/AGENTS.md: appended foundry block", first_stdout)
            self.assertIn("root AGENTS.md: unchanged", second_stdout)
            self.assertIn(".codex/AGENTS.md: unchanged", second_stdout)
            self.assertIn("skipped agent bridge:", second_stdout)
            self.assertIn("skipped skill bridge:", second_stdout)

            root_agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
            codex_agents = (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(root_agents.count(bootstrap.BOOTSTRAP_MARKER_START), 1)
            self.assertEqual(codex_agents.count(bootstrap.BOOTSTRAP_MARKER_START), 1)

    def test_existing_agents_with_foundry_keywords_stay_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                root_agents_text=(
                    "# Root AGENTS\n\nVendor path: .codex/vendor/packetflow_foundry\n"
                ),
                codex_agents_text="# Local Codex AGENTS\n\npacketflow_foundry note\n",
                vendor_skill_names=["vendor-skill"],
            )

            root_before = (repo / "AGENTS.md").read_text(encoding="utf-8")
            codex_before = (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8")

            code, stdout, _, _ = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertIn("root AGENTS.md: unchanged", stdout)
            self.assertIn(".codex/AGENTS.md: unchanged", stdout)
            self.assertEqual((repo / "AGENTS.md").read_text(encoding="utf-8"), root_before)
            self.assertEqual(
                (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8"),
                codex_before,
            )

    def test_generated_profile_is_reader_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(Path(tmp), vendor_skill_names=["vendor-skill"])
            code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(code, 0)

            profile_path = repo / bootstrap.PROJECT_PROFILE_RELATIVE
            worktree_profile = worktree_collect.load_repo_profile(profile_path)
            reword_profile = reword_collect.load_repo_profile_document(profile_path)

            self.assertEqual(worktree_profile["kind"], bootstrap.PROJECT_LOCAL_PROFILE_KIND)
            self.assertEqual(
                reword_profile["profile_path"],
                bootstrap.PROJECT_PROFILE_RELATIVE.as_posix(),
            )

    def test_skill_specific_project_profile_is_preferred_by_vendored_collector_logic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(Path(tmp), vendor_skill_names=["vendor-skill"])
            code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(code, 0)

            skill_profile = (
                repo
                / ".codex"
                / "project"
                / "profiles"
                / "reword-recent-commits"
                / "profile.json"
            )
            skill_profile.parent.mkdir(parents=True, exist_ok=True)
            skill_profile.write_text("{}", encoding="utf-8")

            self.assertEqual(
                reword_collect.default_repo_profile_path(repo),
                skill_profile.resolve(),
            )
            self.assertEqual(
                reword_collect.resolve_profile_path(
                    ".codex/project/profiles/reword-recent-commits/profile.json",
                    repo,
                ),
                skill_profile.resolve(),
            )

    def test_existing_root_skill_and_agent_skip_vendor_bridges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
                root_skill_names=["vendor-skill"],
                root_agent_names=["vendor-agent"],
            )

            code, stdout, _, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("skipped agent bridge:", stdout)
            self.assertIn("vendor-agent", stdout)
            self.assertIn("skipped skill bridge:", stdout)
            self.assertIn("vendor-skill", stdout)

    def test_legacy_project_skills_are_bridged_with_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["shared-skill"],
                legacy_skill_names=["shared-skill", "legacy-only"],
            )

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 2)
            self.assertIn("legacy skill bridge:", stdout)
            self.assertIn("legacy-only", stdout)
            self.assertIn("shared-skill", stderr)
            self.assertIn("Legacy `.codex/project/skills/` is deprecated", stderr)

    def test_legacy_project_agents_are_bridged_with_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_agent_names=["shared-agent"],
                legacy_agent_names=["shared-agent", "legacy-only"],
            )

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 2)
            self.assertIn("legacy agent bridge:", stdout)
            self.assertIn("legacy-only.toml", stdout)
            self.assertIn("shared-agent", stderr)
            self.assertIn("Legacy `.codex/project/agents/` is deprecated", stderr)

    def test_conflicting_generated_output_aborts_without_touching_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                root_agents_text="# Root AGENTS\n",
                codex_agents_text="# Local Codex AGENTS\n",
                existing_profile=True,
                vendor_skill_names=["vendor-skill"],
            )

            code, _, stderr, _ = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertIn("Refusing to overwrite existing bootstrap outputs", stderr)
            self.assertNotIn(
                bootstrap.BOOTSTRAP_MARKER_START,
                (repo / "AGENTS.md").read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                bootstrap.BOOTSTRAP_MARKER_START,
                (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8"),
            )
            self.assertFalse((repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE).exists())

    def test_symlink_failure_produces_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(Path(tmp), vendor_skill_names=["vendor-skill"])

            code, _, stderr, _ = run_bootstrap_main(
                repo,
                symlink_side_effect=OSError("no symlink permission"),
            )

            self.assertEqual(code, 1)
            self.assertIn("Failed to create directory symlink", stderr)
            self.assertIn("Enable Windows Developer Mode", stderr)

    def test_missing_vendor_subtree_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(Path(tmp), include_vendor=False)

            code, _, stderr, _ = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertIn("Missing PacketFlow Foundry vendor subtree", stderr)
            self.assertFalse((repo / ".codex" / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()

