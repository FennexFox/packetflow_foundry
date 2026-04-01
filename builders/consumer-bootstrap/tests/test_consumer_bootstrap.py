from __future__ import annotations

import io
import json
import py_compile
import shutil
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
    gitignore_text: str | None = None,
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
    if gitignore_text is not None:
        (repo / ".gitignore").write_text(gitignore_text, encoding="utf-8")
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
    bridge_mode: str = bootstrap.BRIDGE_MODE_COPY,
) -> tuple[int, str, str, mock.Mock]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    symlink_mock = mock.Mock()

    with (
        mock.patch.object(
            sys,
            "argv",
            [
                "init_consumer_codex.py",
                "--repo-root",
                str(repo),
                "--bridge-mode",
                bridge_mode,
            ],
        ),
        mock.patch.object(Path, "symlink_to", symlink_mock),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        code = bootstrap.main()

    return code, stdout.getvalue(), stderr.getvalue(), symlink_mock


def relative_files(root: Path) -> list[str]:
    return sorted(
        str(path.relative_to(root)).replace("\\", "/")
        for path in root.rglob("*")
        if path.is_file()
    )


def rewrite_line_endings(path: Path, newline: bytes) -> None:
    content = path.read_bytes()
    normalized = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    path.write_bytes(normalized.replace(b"\n", newline))


def alternate_newline(content: bytes) -> bytes:
    return b"\n" if b"\r\n" in content else b"\r\n"


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
            self.assertIn("bridge mode: copy", stdout)
            self.assertIn("root AGENTS.md: not present", stdout)
            self.assertIn(".codex/AGENTS.md: created", stdout)
            self.assertIn(".gitignore: created with .codex/tmp/", stdout)
            self.assertIn(".codex/agents: ready", stdout)
            self.assertIn("copied agent bridge:", stdout)
            self.assertIn("vendor-agent", stdout)
            self.assertIn(".agents/skills: ready", stdout)
            self.assertIn("copied skill bridge:", stdout)
            self.assertIn("vendor-skill", stdout)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertFalse((repo / "AGENTS.md").exists())
            self.assertTrue((repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE).is_dir())
            self.assertTrue((repo / bootstrap.ROOT_SKILLS_RELATIVE).is_dir())
            self.assertEqual(
                (repo / ".gitignore").read_text(encoding="utf-8"),
                ".codex/tmp/\n",
            )
            self.assertTrue((repo / bootstrap.BRIDGE_STATE_RELATIVE).is_file())

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
                gitignore_text="bin/\n",
                root_agents_text="# Root AGENTS\n",
                codex_agents_text="# Local Codex AGENTS\n",
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )

            first_code, first_stdout, _, _ = run_bootstrap_main(repo)
            self.assertEqual(first_code, 0)

            second_code, second_stdout, _, _ = run_bootstrap_main(repo)

            self.assertEqual(second_code, 0)
            self.assertIn("root AGENTS.md: appended foundry block", first_stdout)
            self.assertIn(".codex/AGENTS.md: appended foundry block", first_stdout)
            self.assertIn(".gitignore: appended .codex/tmp/", first_stdout)
            self.assertIn("root AGENTS.md: unchanged", second_stdout)
            self.assertIn(".codex/AGENTS.md: unchanged", second_stdout)
            self.assertIn(".gitignore: unchanged", second_stdout)

            root_agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
            codex_agents = (repo / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
            gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
            self.assertEqual(root_agents.count(bootstrap.BOOTSTRAP_MARKER_START), 1)
            self.assertEqual(codex_agents.count(bootstrap.BOOTSTRAP_MARKER_START), 1)
            self.assertEqual(gitignore.count(".codex/tmp/"), 1)

    def test_existing_gitignore_with_codex_tmp_stays_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                gitignore_text="bin/\n.codex/tmp\n",
                vendor_skill_names=["vendor-skill"],
            )

            before = (repo / ".gitignore").read_text(encoding="utf-8")

            code, stdout, _, _ = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertIn(".gitignore: unchanged", stdout)
            self.assertEqual((repo / ".gitignore").read_text(encoding="utf-8"), before)

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
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("legacy copied skill bridge:", stdout)
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
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("legacy copied agent bridge:", stdout)
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

    def test_copy_alias_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )

            code, stdout, stderr, symlink_mock = run_bootstrap_main(
                repo,
                bridge_mode=bootstrap.BRIDGE_MODE_COPY_ON_FAIL,
            )

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("bridge mode: copy", stdout)
            self.assertIn("copied agent bridge:", stdout)
            self.assertIn("copied skill bridge:", stdout)
            self.assertEqual(stderr.strip(), "")

    def test_copied_vendor_skill_rewrites_wrapper_paths_to_vendor_subtree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
            )
            vendor_skill = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
                / "SKILL.md"
            )
            vendor_skill.write_text(
                "\n".join(
                    [
                        "---",
                        "name: vendor-skill",
                        "description: test skill",
                        "---",
                        "",
                        "Use `../../../builders/packet-workflow/retained-skills/vendor-skill/SKILL.md`.",
                        "Run `python ../../../builders/packet-workflow/scripts/init_packet_skill.py`.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            code, _, _, _ = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            copied_skill = repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill" / "SKILL.md"
            copied_text = copied_skill.read_text(encoding="utf-8")
            self.assertIn(
                "../../../.codex/vendor/packetflow_foundry/builders/packet-workflow/retained-skills/vendor-skill/SKILL.md",
                copied_text,
            )
            self.assertIn(
                "python ../../../.codex/vendor/packetflow_foundry/builders/packet-workflow/scripts/init_packet_skill.py",
                copied_text,
            )
            self.assertNotIn(
                "Use `../../../builders/packet-workflow/retained-skills/vendor-skill/SKILL.md`.",
                copied_text,
            )

    def test_default_copy_creates_managed_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("bridge mode: copy", stdout)
            self.assertIn("copied agent bridge:", stdout)
            self.assertIn("copied skill bridge:", stdout)
            self.assertEqual(stderr.strip(), "")

            vendor_agent = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "vendor-agent.toml"
            )
            copied_agent = repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml"
            self.assertEqual(
                copied_agent.read_text(encoding="utf-8"),
                vendor_agent.read_text(encoding="utf-8"),
            )

            copied_skill = repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill"
            self.assertEqual(relative_files(copied_skill), ["SKILL.md", "agents/openai.yaml"])

            bridge_state = json.loads(
                (repo / bootstrap.BRIDGE_STATE_RELATIVE).read_text(encoding="utf-8")
            )
            self.assertEqual(bridge_state["kind"], bootstrap.BRIDGE_STATE_KIND)
            self.assertEqual(bridge_state["version"], bootstrap.BRIDGE_STATE_VERSION)
            self.assertIn("vendor-agent.toml", bridge_state["agents"])
            self.assertIn("vendor-skill", bridge_state["skills"])
            self.assertIn("raw_sha256", bridge_state["agents"]["vendor-agent.toml"])
            self.assertIn("lf_sha256", bridge_state["agents"]["vendor-agent.toml"])
            self.assertIn(
                "raw_sha256",
                bridge_state["skills"]["vendor-skill"]["files"]["SKILL.md"],
            )
            self.assertIn(
                "lf_sha256",
                bridge_state["skills"]["vendor-skill"]["files"]["SKILL.md"],
            )

    def test_copy_refreshes_managed_copies_when_vendor_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )

            first_code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(first_code, 0)

            vendor_agent = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "vendor-agent.toml"
            )
            vendor_agent.write_text(
                vendor_agent.read_text(encoding="utf-8") + "# updated\n",
                encoding="utf-8",
            )
            vendor_skill = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
                / "agents"
                / "openai.yaml"
            )
            vendor_skill.write_text('display_name: "Updated"\n', encoding="utf-8")

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("refreshed copied agent bridge:", stdout)
            self.assertIn("refreshed copied skill bridge:", stdout)
            self.assertEqual(stderr.strip(), "")

            copied_agent = repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml"
            copied_skill = (
                repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill" / "agents" / "openai.yaml"
            )
            self.assertIn("# updated", copied_agent.read_text(encoding="utf-8"))
            self.assertEqual(
                copied_skill.read_text(encoding="utf-8"),
                'display_name: "Updated"\n',
            )

    def test_copy_ignores_line_ending_only_target_changes_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )

            first_code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(first_code, 0)

            copied_agent = repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml"
            copied_skill = (
                repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill" / "agents" / "openai.yaml"
            )

            rewrite_line_endings(copied_agent, alternate_newline(copied_agent.read_bytes()))
            rewrite_line_endings(copied_skill, alternate_newline(copied_skill.read_bytes()))
            expected_agent_bytes = copied_agent.read_bytes()
            expected_skill_bytes = copied_skill.read_bytes()

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertNotIn("refreshed copied agent bridge:", stdout)
            self.assertNotIn("refreshed copied skill bridge:", stdout)
            self.assertNotIn("skipped agent bridge:", stdout)
            self.assertNotIn("skipped skill bridge:", stdout)
            self.assertEqual(stderr.strip(), "")
            self.assertEqual(copied_agent.read_bytes(), expected_agent_bytes)
            self.assertEqual(copied_skill.read_bytes(), expected_skill_bytes)

    def test_sync_managed_file_copy_recreates_missing_target_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source_path = create_agent_file(repo_root / "vendor", "vendor-agent")
            target_path = repo_root / "consumer" / "vendor-agent.toml"
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
            state_group = {
                "vendor-agent.toml": bootstrap.build_file_copy_state_entry(repo_root, source_path)
            }

            target_path.unlink()

            with mock.patch.object(bootstrap, "write_bytes", wraps=bootstrap.write_bytes) as write_mock:
                status, detail, notice = bootstrap.sync_managed_file_copy(
                    repo_root,
                    source_path,
                    target_path,
                    bridge_name="vendor-agent.toml",
                    state_group=state_group,
                )

            self.assertEqual(status, "copied")
            self.assertEqual(detail, f"{target_path.as_posix()} <- {source_path.as_posix()}")
            self.assertIsNone(notice)
            self.assertEqual(write_mock.call_count, 1)
            self.assertEqual(
                target_path.read_text(encoding="utf-8"),
                source_path.read_text(encoding="utf-8"),
            )

    def test_sync_managed_directory_copy_restores_missing_files_and_prunes_stale_managed_files(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source_root = create_skill_dir(repo_root / "vendor", "vendor-skill")
            obsolete_source_file = source_root / "obsolete.txt"
            obsolete_source_file.write_text("obsolete\n", encoding="utf-8")
            target_root = repo_root / "consumer" / "vendor-skill"
            shutil.copytree(source_root, target_root)
            copied_files = bootstrap.build_skill_bridge_files(
                repo_root,
                source_root,
                target_root,
            )
            state_group = {
                "vendor-skill": bootstrap.build_directory_copy_state_entry(
                    repo_root,
                    source_root,
                    copied_files,
                )
            }

            missing_file = target_root / "agents" / "openai.yaml"
            stale_file = target_root / "obsolete.txt"
            obsolete_source_file.unlink()
            missing_file.unlink()

            status, detail, notice = bootstrap.sync_managed_directory_copy(
                repo_root,
                source_root,
                target_root,
                bridge_name="vendor-skill",
                state_group=state_group,
            )

            self.assertEqual(status, "refreshed")
            self.assertEqual(detail, f"{target_root.as_posix()} <- {source_root.as_posix()}")
            self.assertIsNone(notice)
            self.assertTrue(missing_file.is_file())
            self.assertFalse(stale_file.exists())

    def test_copy_keeps_locally_added_skill_files_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
            )

            first_code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(first_code, 0)

            copied_skill_root = repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill"
            copied_skill = copied_skill_root / "agents" / "openai.yaml"
            local_file = copied_skill_root / "local-notes.txt"
            local_file.write_text("local override\n", encoding="utf-8")

            vendor_skill = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
                / "agents"
                / "openai.yaml"
            )
            vendor_skill.write_text('display_name: "Updated"\n', encoding="utf-8")

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("skipped skill bridge:", stdout)
            self.assertIn("modified locally", stderr)
            self.assertTrue(local_file.is_file())
            self.assertEqual(
                copied_skill.read_text(encoding="utf-8"),
                'display_name: "Test"\n',
            )

    def test_copy_rejects_symlinked_skill_wrapper_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
            )
            symlinked_file = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
                / "agents"
                / "openai.yaml"
            )
            real_is_symlink = Path.is_symlink

            def fake_is_symlink(path: Path) -> bool:
                if path == symlinked_file:
                    return True
                return real_is_symlink(path)

            with mock.patch.object(Path, "is_symlink", fake_is_symlink):
                code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertNotIn("copied skill bridge:", stdout)
            self.assertIn("unsupported symlinked file", stderr)
            self.assertFalse(
                (repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill").exists()
            )
            self.assertFalse((repo / bootstrap.BRIDGE_STATE_RELATIVE).exists())

    def test_copy_rejects_linked_skill_root_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
            )
            linked_root = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
            )
            real_has_reparse_point = bootstrap.path_has_reparse_point

            def fake_has_reparse_point(path: Path) -> bool:
                if path == linked_root:
                    return True
                return real_has_reparse_point(path)

            with mock.patch.object(bootstrap, "path_has_reparse_point", fake_has_reparse_point):
                code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertNotIn("copied skill bridge:", stdout)
            self.assertIn("unsupported linked directory", stderr)
            self.assertFalse(
                (repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill").exists()
            )
            self.assertFalse((repo / bootstrap.BRIDGE_STATE_RELATIVE).exists())

    def test_copy_rejects_symlinked_agent_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_agent_names=["vendor-agent"],
            )
            symlinked_file = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "vendor-agent.toml"
            )
            real_is_symlink = Path.is_symlink

            def fake_is_symlink(path: Path) -> bool:
                if path == symlinked_file:
                    return True
                return real_is_symlink(path)

            with mock.patch.object(Path, "is_symlink", fake_is_symlink):
                code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertNotIn("copied agent bridge:", stdout)
            self.assertIn("unsupported symlinked file", stderr)
            self.assertFalse(
                (repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml").exists()
            )
            self.assertFalse((repo / bootstrap.BRIDGE_STATE_RELATIVE).exists())

    def test_copy_errors_cleanly_for_external_agent_source_path_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = create_consumer_repo(
                root,
                vendor_agent_names=["vendor-agent"],
            )
            vendor_agent = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "vendor-agent.toml"
            )
            external_root = root / "external"
            external_agent = create_agent_file(external_root, "external-agent")
            real_resolve = Path.resolve

            def fake_resolve(path: Path, *args: object, **kwargs: object) -> Path:
                if path == vendor_agent:
                    return external_agent.resolve()
                return real_resolve(path, *args, **kwargs)

            with mock.patch.object(Path, "resolve", fake_resolve):
                code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertNotIn("copied agent bridge:", stdout)
            self.assertIn("resolves outside the agent root", stderr)
            self.assertFalse(
                (repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml").exists()
            )
            self.assertFalse((repo / bootstrap.BRIDGE_STATE_RELATIVE).exists())

    def test_copy_errors_cleanly_for_external_skill_source_path_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = create_consumer_repo(
                root,
                vendor_skill_names=["vendor-skill"],
            )
            vendor_skill = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
            )
            external_skill = create_skill_dir(root / "external-skills", "vendor-skill")
            real_resolve = Path.resolve

            def fake_resolve(path: Path, *args: object, **kwargs: object) -> Path:
                if path == vendor_skill:
                    return external_skill.resolve()
                return real_resolve(path, *args, **kwargs)

            with mock.patch.object(Path, "resolve", fake_resolve):
                code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertNotIn("copied skill bridge:", stdout)
            self.assertIn("resolves outside the skill root", stderr)
            self.assertFalse(
                (repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill").exists()
            )
            self.assertFalse((repo / bootstrap.BRIDGE_STATE_RELATIVE).exists())

    def test_copy_persists_agent_bridge_state_before_skill_pass_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_agent_names=["vendor-agent"],
            )
            root_agent = (
                repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml"
            )
            state_path = repo / bootstrap.BRIDGE_STATE_RELATIVE

            with mock.patch.object(
                bootstrap,
                "create_skill_bridges",
                side_effect=RuntimeError("simulated skill bridge failure"),
            ):
                code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertEqual(stdout.strip(), "")
            self.assertIn("simulated skill bridge failure", stderr)
            self.assertTrue(root_agent.is_file())
            bridge_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("vendor-agent.toml", bridge_state["agents"])

            vendor_agent = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "vendor-agent.toml"
            )
            vendor_agent.write_text(
                vendor_agent.read_text(encoding="utf-8") + "# upstream change\n",
                encoding="utf-8",
            )

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("refreshed copied agent bridge:", stdout)
            self.assertEqual(stderr.strip(), "")
            self.assertIn("# upstream change\n", root_agent.read_text(encoding="utf-8"))

    def test_copy_persists_agent_bridge_state_before_later_agent_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_agent_names=["alpha-agent", "vendor-agent"],
            )
            root_agent = (
                repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "alpha-agent.toml"
            )
            state_path = repo / bootstrap.BRIDGE_STATE_RELATIVE
            real_sync = bootstrap.sync_managed_file_copy

            def fake_sync_managed_file_copy(
                repo_root: Path,
                source_path: Path,
                target_path: Path,
                *,
                bridge_name: str,
                state_group: dict[str, object],
            ) -> tuple[str, str, str | None]:
                if bridge_name == "vendor-agent.toml":
                    raise RuntimeError("simulated later agent bridge failure")
                return real_sync(
                    repo_root,
                    source_path,
                    target_path,
                    bridge_name=bridge_name,
                    state_group=state_group,
                )

            with mock.patch.object(
                bootstrap,
                "sync_managed_file_copy",
                side_effect=fake_sync_managed_file_copy,
            ):
                code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertEqual(stdout.strip(), "")
            self.assertIn("simulated later agent bridge failure", stderr)
            self.assertTrue(root_agent.is_file())
            bridge_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("alpha-agent.toml", bridge_state["agents"])
            self.assertNotIn("vendor-agent.toml", bridge_state["agents"])

            vendor_agent = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "alpha-agent.toml"
            )
            vendor_agent.write_text(
                vendor_agent.read_text(encoding="utf-8") + "# upstream change\n",
                encoding="utf-8",
            )

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("refreshed copied agent bridge:", stdout)
            self.assertEqual(stderr.strip(), "")
            self.assertIn("# upstream change\n", root_agent.read_text(encoding="utf-8"))

    def test_copy_persists_skill_bridge_state_before_later_skill_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["alpha-skill", "vendor-skill"],
            )
            root_skill = repo / bootstrap.ROOT_SKILLS_RELATIVE / "alpha-skill" / "SKILL.md"
            state_path = repo / bootstrap.BRIDGE_STATE_RELATIVE
            real_sync = bootstrap.sync_managed_directory_copy

            def fake_sync_managed_directory_copy(
                repo_root: Path,
                source_root: Path,
                target_root: Path,
                *,
                bridge_name: str,
                state_group: dict[str, object],
            ) -> tuple[str, str, str | None]:
                if bridge_name == "vendor-skill":
                    raise RuntimeError("simulated later skill bridge failure")
                return real_sync(
                    repo_root,
                    source_root,
                    target_root,
                    bridge_name=bridge_name,
                    state_group=state_group,
                )

            with mock.patch.object(
                bootstrap,
                "sync_managed_directory_copy",
                side_effect=fake_sync_managed_directory_copy,
            ):
                code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertEqual(stdout.strip(), "")
            self.assertIn("simulated later skill bridge failure", stderr)
            self.assertTrue(root_skill.is_file())
            bridge_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("alpha-skill", bridge_state["skills"])
            self.assertNotIn("vendor-skill", bridge_state["skills"])

            vendor_skill = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "alpha-skill"
                / "SKILL.md"
            )
            vendor_skill.write_text(
                "---\nname: alpha-skill\ndescription: updated skill\n---\n",
                encoding="utf-8",
            )

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("refreshed copied skill bridge:", stdout)
            self.assertEqual(stderr.strip(), "")
            self.assertIn("updated skill", root_skill.read_text(encoding="utf-8"))

    def test_copy_skips_locally_modified_managed_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )

            first_code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(first_code, 0)

            copied_agent = repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml"
            copied_skill = repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill" / "SKILL.md"
            copied_agent.write_text("# local edit\n", encoding="utf-8")
            copied_skill.write_text("local skill override\n", encoding="utf-8")

            vendor_agent = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "vendor-agent.toml"
            )
            vendor_agent.write_text(
                vendor_agent.read_text(encoding="utf-8") + "# upstream change\n",
                encoding="utf-8",
            )

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("skipped agent bridge:", stdout)
            self.assertIn("skipped skill bridge:", stdout)
            self.assertIn("modified locally", stderr)
            self.assertEqual(copied_agent.read_text(encoding="utf-8"), "# local edit\n")
            self.assertEqual(copied_skill.read_text(encoding="utf-8"), "local skill override\n")

    def test_existing_vendor_symlink_bridges_are_migrated_to_managed_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )
            vendor_agent = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "vendor-agent.toml"
            )
            vendor_skill = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
            )
            root_agent = repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml"
            root_skill = repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill"
            root_agent.parent.mkdir(parents=True, exist_ok=True)
            root_agent.write_text(vendor_agent.read_text(encoding="utf-8"), encoding="utf-8")
            shutil.copytree(vendor_skill, root_skill)

            real_is_symlink = Path.is_symlink
            real_resolve = Path.resolve
            real_unlink = Path.unlink

            def fake_is_symlink(path: Path) -> bool:
                if path in {root_agent, root_skill}:
                    return True
                return real_is_symlink(path)

            def fake_resolve(path: Path, *args: object, **kwargs: object) -> Path:
                if path == root_agent:
                    return vendor_agent.resolve()
                if path == root_skill:
                    return vendor_skill.resolve()
                return real_resolve(path, *args, **kwargs)

            def fake_unlink(path: Path, *args: object, **kwargs: object) -> None:
                if path == root_agent:
                    real_unlink(path, *args, **kwargs)
                    return None
                if path == root_skill:
                    shutil.rmtree(path)
                    return None
                real_unlink(path, *args, **kwargs)
                return None

            with (
                mock.patch.object(Path, "is_symlink", fake_is_symlink),
                mock.patch.object(Path, "resolve", fake_resolve),
                mock.patch.object(Path, "unlink", fake_unlink),
            ):
                code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("migrated copied agent bridge:", stdout)
            self.assertIn("migrated copied skill bridge:", stdout)
            self.assertEqual(stderr.strip(), "")
            self.assertTrue((repo / bootstrap.BRIDGE_STATE_RELATIVE).is_file())

    def test_copy_prunes_deleted_managed_vendor_entries_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )

            first_code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(first_code, 0)

            vendor_agent = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "vendor-agent.toml"
            )
            vendor_skill = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
            )
            vendor_agent.unlink()
            shutil.rmtree(vendor_skill)

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("removed agent bridge:", stdout)
            self.assertIn("removed skill bridge:", stdout)
            self.assertEqual(stderr.strip(), "")
            self.assertFalse(
                (repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml").exists()
            )
            self.assertFalse((repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill").exists())
            self.assertFalse((repo / bootstrap.BRIDGE_STATE_RELATIVE).exists())

    def test_copy_keeps_locally_modified_deleted_managed_entries_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )

            first_code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(first_code, 0)

            copied_agent = repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml"
            copied_skill = repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill" / "SKILL.md"
            copied_agent.write_text("# local edit\n", encoding="utf-8")
            copied_skill.write_text("local skill override\n", encoding="utf-8")

            vendor_agent = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "vendor-agent.toml"
            )
            vendor_skill = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
            )
            vendor_agent.unlink()
            shutil.rmtree(vendor_skill)

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("skipped agent bridge:", stdout)
            self.assertIn("skipped skill bridge:", stdout)
            self.assertIn("after upstream deletion", stderr)
            self.assertEqual(copied_agent.read_text(encoding="utf-8"), "# local edit\n")
            self.assertEqual(copied_skill.read_text(encoding="utf-8"), "local skill override\n")
            bridge_state = json.loads(
                (repo / bootstrap.BRIDGE_STATE_RELATIVE).read_text(encoding="utf-8")
            )
            self.assertIn("vendor-agent.toml", bridge_state["agents"])
            self.assertIn("vendor-skill", bridge_state["skills"])

    def test_copy_keeps_symlinked_skill_files_after_upstream_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
            )

            first_code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(first_code, 0)

            vendor_skill = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
            )
            copied_skill = repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill" / "SKILL.md"
            shutil.rmtree(vendor_skill)

            real_is_symlink = Path.is_symlink
            real_hash_state_from_path = bootstrap.hash_state_from_path

            def fake_is_symlink(path: Path) -> bool:
                if path == copied_skill:
                    return True
                return real_is_symlink(path)

            def fake_hash_state_from_path(path: Path) -> dict[str, str]:
                if path == copied_skill:
                    raise OSError("symlink targets should not be hashed during prune")
                return real_hash_state_from_path(path)

            with (
                mock.patch.object(Path, "is_symlink", fake_is_symlink),
                mock.patch.object(bootstrap, "hash_state_from_path", fake_hash_state_from_path),
            ):
                code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertIn("skipped skill bridge:", stdout)
            self.assertIn("after upstream deletion", stderr)
            self.assertTrue(copied_skill.is_file())
            bridge_state = json.loads(
                (repo / bootstrap.BRIDGE_STATE_RELATIVE).read_text(encoding="utf-8")
            )
            self.assertIn("vendor-skill", bridge_state["skills"])

    def test_copy_migrates_legacy_hash_state_for_line_ending_only_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(
                Path(tmp),
                vendor_skill_names=["vendor-skill"],
                vendor_agent_names=["vendor-agent"],
            )

            first_code, _, _, _ = run_bootstrap_main(repo)
            self.assertEqual(first_code, 0)

            state_path = repo / bootstrap.BRIDGE_STATE_RELATIVE
            bridge_state = json.loads(state_path.read_text(encoding="utf-8"))
            agent_state = bridge_state["agents"]["vendor-agent.toml"]
            agent_state.pop("raw_sha256", None)
            agent_state.pop("lf_sha256", None)
            for metadata in bridge_state["skills"]["vendor-skill"]["files"].values():
                metadata.pop("raw_sha256", None)
                metadata.pop("lf_sha256", None)
            state_path.write_text(json.dumps(bridge_state, indent=2), encoding="utf-8")

            vendor_agent = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".codex"
                / "agents"
                / "vendor-agent.toml"
            )
            vendor_skill = (
                repo
                / ".codex"
                / "vendor"
                / "packetflow_foundry"
                / ".agents"
                / "skills"
                / "vendor-skill"
                / "agents"
                / "openai.yaml"
            )
            copied_agent = repo / bootstrap.PROJECT_AGENT_DISCOVERY_RELATIVE / "vendor-agent.toml"
            copied_skill = (
                repo / bootstrap.ROOT_SKILLS_RELATIVE / "vendor-skill" / "agents" / "openai.yaml"
            )
            expected_agent_bytes = copied_agent.read_bytes()
            expected_skill_bytes = copied_skill.read_bytes()

            rewrite_line_endings(vendor_agent, alternate_newline(vendor_agent.read_bytes()))
            rewrite_line_endings(vendor_skill, alternate_newline(vendor_skill.read_bytes()))

            code, stdout, stderr, symlink_mock = run_bootstrap_main(repo)

            self.assertEqual(code, 0)
            self.assertEqual(symlink_mock.call_count, 0)
            self.assertNotIn("refreshed copied agent bridge:", stdout)
            self.assertNotIn("refreshed copied skill bridge:", stdout)
            self.assertNotIn("skipped agent bridge:", stdout)
            self.assertNotIn("skipped skill bridge:", stdout)
            self.assertEqual(stderr.strip(), "")
            self.assertEqual(copied_agent.read_bytes(), expected_agent_bytes)
            self.assertEqual(copied_skill.read_bytes(), expected_skill_bytes)

            migrated_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("raw_sha256", migrated_state["agents"]["vendor-agent.toml"])
            self.assertIn("lf_sha256", migrated_state["agents"]["vendor-agent.toml"])
            self.assertIn(
                "raw_sha256",
                migrated_state["skills"]["vendor-skill"]["files"]["agents/openai.yaml"],
            )
            self.assertIn(
                "lf_sha256",
                migrated_state["skills"]["vendor-skill"]["files"]["agents/openai.yaml"],
            )

    def test_missing_vendor_subtree_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = create_consumer_repo(Path(tmp), include_vendor=False)

            code, _, stderr, _ = run_bootstrap_main(repo)

            self.assertEqual(code, 1)
            self.assertIn("Missing PacketFlow Foundry vendor subtree", stderr)
            self.assertFalse((repo / ".codex" / "AGENTS.md").exists())


if __name__ == "__main__":
    unittest.main()

