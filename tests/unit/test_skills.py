from __future__ import annotations

from pathlib import Path

from coding_agent.app.system_prompt import build_system_prompt
from coding_agent.skills.bank import MAX_ACTIVE, SkillBank, reset_skills
from coding_agent.skills.pack import (
    MAX_BODY,
    discover_skills,
    ensure_user_skills,
    parse_skill_md,
)


def _write_skill(root: Path, name: str, body: str, description: str = "desc") -> None:
    dest = root / name
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}\n",
        encoding="utf-8",
    )


def test_discover_skips_dir_without_skill_md(tmp_path: Path) -> None:
    (tmp_path / ".wavecode" / "skills" / "empty").mkdir(parents=True)
    _write_skill(tmp_path / ".wavecode" / "skills", "ok", "hello")
    found = discover_skills(tmp_path)
    assert found["ok"].body.strip() == "hello"
    assert "empty" not in found


def test_workspace_overrides_user(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    _write_skill(home / ".wavecode" / "skills", "dup", "from-user")
    _write_skill(tmp_path / ".wavecode" / "skills", "dup", "from-ws")
    found = discover_skills(tmp_path)
    assert found["dup"].body.strip() == "from-ws"


def test_bad_frontmatter_is_skipped(tmp_path: Path) -> None:
    dest = tmp_path / ".wavecode" / "skills" / "bad"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("---\n- not: a mapping\n---\nbody\n", encoding="utf-8")
    assert "bad" not in discover_skills(tmp_path)


def test_body_clipped_and_ninth_rejected(tmp_path: Path) -> None:
    root = tmp_path / ".wavecode" / "skills"
    for i in range(MAX_ACTIVE + 1):
        _write_skill(root, f"s{i}", "x" * (MAX_BODY + 50) if i == 0 else "b")
    bank = SkillBank()
    bank.set_workdir(tmp_path)
    assert len(bank.discover()["s0"].body) == MAX_BODY
    for i in range(MAX_ACTIVE):
        kind, _ = bank.replace_active([f"s{j}" for j in range(i + 1)])
        assert kind == "note"
    kind, body = bank.replace_active([f"s{i}" for i in range(MAX_ACTIVE + 1)])
    assert kind == "warn"
    assert "8" in body


def test_apply_opens_list_and_rejects_name_args(tmp_path: Path) -> None:
    _write_skill(tmp_path / ".wavecode" / "skills", "pytest-style", "# run pytest")
    bank = reset_skills()
    bank.set_workdir(tmp_path)
    assert bank.apply("")[0] == "pick"
    listed = bank.list_text()
    assert "pytest-style" in listed
    assert "发行" not in listed
    assert "~/.wavecode" not in listed
    assert ".wavecode/skills" not in listed
    assert bank.apply("pytest-style")[0] == "warn"
    assert bank.apply("-pytest-style")[0] == "warn"
    assert bank.apply("clear")[0] == "warn"
    assert bank.active == ()
    kind, _ = bank.replace_active(["pytest-style"])
    assert kind == "note"
    listed = bank.list_text()
    assert "[✓]" in listed
    assert "发行" not in listed
    assert "[x]" not in listed
    bodies = bank.active_bodies()
    assert bodies[0][0] == "pytest-style"
    assert "run pytest" in bodies[0][1]
    assert bank.replace_active([])[0] == "note"
    assert bank.active == ()
    kind, _ = bank.apply("nope")
    assert kind == "warn"
    for banned in ("吉祥物", "鲸鱼娘", "鲸鱼酿"):
        assert banned not in bank.list_text()


def test_ensure_user_skills_creates_dir(tmp_path: Path) -> None:
    dest = ensure_user_skills(home=tmp_path)
    assert dest.is_dir()
    assert dest == tmp_path / ".wavecode" / "skills"
    assert not (dest / "README.txt").is_file()


def test_system_prompt_catalog_and_active() -> None:
    text = build_system_prompt(
        workspace_root="/tmp/ws",
        tool_names=["read_file"],
        skill_catalog=[("pytest-style", "how to test")],
        active_skills=[("pytest-style", "always run pytest")],
    )
    assert "Available skills" in text
    assert "pytest-style: how to test" in text
    assert "## Active skills" in text
    assert "always run pytest" in text


def test_session_rebuild_keeps_history_and_reset_keeps_skill(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from coding_agent.agent.session import AgentSession
    from coding_agent.context.estimator import HeuristicTokenEstimator
    from coding_agent.context.manager import ContextManager
    from coding_agent.context.policy import TruncatingContextPolicy
    from coding_agent.context.store import ConversationStore
    from coding_agent.domain.messages import ChatMessage, Role
    from coding_agent.tools.builtin import all_builtin_tools
    from coding_agent.tools.registry import ToolRegistry
    from coding_agent.tools.workspace import Workspace
    from fakes.sink import RecordingSink

    _write_skill(tmp_path / ".wavecode" / "skills", "pytest-style", "ALWAYS PYTEST")
    bank = reset_skills()
    bank.set_workdir(tmp_path)
    bank.replace_active(["pytest-style"])
    registry = ToolRegistry()
    for tool in all_builtin_tools():
        registry.register(tool)
    estimator = HeuristicTokenEstimator()
    store = ConversationStore(ChatMessage(role=Role.SYSTEM, content="old"))
    store.append(ChatMessage(role=Role.USER, content="hello"))
    context = ContextManager(
        store=store,
        policy=TruncatingContextPolicy(
            send_budget=10_000, tool_output_max_chars=1000, estimator=estimator
        ),
        estimator=estimator,
        send_budget=10_000,
    )
    loop = SimpleNamespace(
        executor=SimpleNamespace(workspace=Workspace(tmp_path)),
        registry=registry,
    )
    session = AgentSession(loop, context, RecordingSink())  # type: ignore[arg-type]
    session.rebuild_system()
    assert "ALWAYS PYTEST" in (store.all()[0].content or "")
    assert store.all()[1].content == "hello"
    session.reset()
    assert len(store.all()) == 1
    assert "ALWAYS PYTEST" in (store.all()[0].content or "")


def test_parse_without_frontmatter() -> None:
    pack = parse_skill_md("# just body\n", "plain")
    assert pack is not None
    assert pack.title == "plain"
    assert pack.description == "no description"
    assert "just body" in pack.body


def test_builtin_skill_is_package_data() -> None:
    from importlib.resources import files

    packs = files("coding_agent.skills.packs")
    assert packs.joinpath("frontend-design").joinpath("SKILL.md").is_file()
    assert packs.joinpath("tdd").joinpath("SKILL.md").is_file()


def test_builtin_skills_are_discoverable() -> None:
    from coding_agent.skills.pack import BUILTIN_SKILL_NAMES, BUILTIN_SKILLS

    found = discover_skills(include_user=False)
    assert set(found) == {"frontend-design", "tdd"}
    assert {p.name for p in BUILTIN_SKILLS.iterdir() if p.is_dir()} == set(BUILTIN_SKILL_NAMES)
    pack = found["frontend-design"]
    assert pack.root == BUILTIN_SKILLS / "frontend-design"
    assert (BUILTIN_SKILLS / "frontend-design" / "SKILL.md").is_file()
    assert "token" in pack.body.lower() or "签名" in pack.body
    tdd = found["tdd"]
    assert tdd.root == BUILTIN_SKILLS / "tdd"
    assert "先红后绿" in tdd.body or "失败测试" in tdd.body
    for banned in ("吉祥物", "鲸鱼娘", "鲸鱼酿"):
        assert banned not in pack.body
        assert banned not in pack.description
        assert banned not in tdd.body
        assert banned not in tdd.description


def test_stale_builtin_skill_dirs_are_ignored(tmp_path: Path, monkeypatch) -> None:
    from coding_agent.skills import pack as pack_mod

    packs = tmp_path / "packs"
    _write_skill(packs, "frontend-design", "keep")
    _write_skill(packs, "code-review", "stale")
    _write_skill(packs, "debug", "stale")
    monkeypatch.setattr(pack_mod, "BUILTIN_SKILLS", packs)
    found = discover_skills(include_user=False)
    assert set(found) == {"frontend-design"}
    assert "stale" not in found["frontend-design"].body


def test_replace_active_and_workspace_overrides_builtin(tmp_path: Path) -> None:
    _write_skill(tmp_path / ".wavecode" / "skills", "frontend-design", "WS BODY")
    bank = reset_skills()
    bank.set_workdir(tmp_path)
    kind, _ = bank.replace_active(["frontend-design", "nope"])
    assert kind == "note"
    assert bank.active == ("frontend-design",)
    assert "WS BODY" in bank.active_bodies()[0][1]
    too_many = [f"x{i}" for i in range(MAX_ACTIVE + 1)]
    for name in too_many:
        _write_skill(tmp_path / ".wavecode" / "skills", name, "b")
    kind, body = bank.replace_active(too_many)
    assert kind == "warn"
    assert "8" in body
    assert bank.replace_active([]) == ("note", "已卸下全部 skill")
    assert bank.active == ()
