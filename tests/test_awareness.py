"""The awareness document and the docs must not drift apart.

The injected text is what an agent actually reads. If it disagrees with the documentation,
the documentation is wrong -- so the claims that matter are pinned here, in both places.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestTheAwarenessDocument:
    def test_it_exists_and_says_what_the_thing_is(self):
        from jevqueue.awareness import SHORT_AWARENESS

        assert "decision layer" in SHORT_AWARENESS
        assert "jevqueue_decide" in SHORT_AWARENESS

    def test_it_tells_the_agent_what_to_do_with_a_refusal(self):
        from jevqueue.awareness import SHORT_AWARENESS

        assert "Do not retry" in SHORT_AWARENESS
        assert "human" in SHORT_AWARENESS
        assert "already done" in SHORT_AWARENESS

    def test_it_states_that_the_gate_fails_open(self):
        from jevqueue.awareness import SHORT_AWARENESS

        assert "fails open" in SHORT_AWARENESS

    def test_it_claims_no_generated_tokens_because_that_is_the_measured_fact(self):
        from jevqueue.awareness import SHORT_AWARENESS

        assert "no generated tokens" in SHORT_AWARENESS

    def test_the_short_version_is_short(self):
        """It is injected into every session, so every paragraph costs tokens always."""
        from jevqueue.awareness import SHORT_AWARENESS

        assert len(SHORT_AWARENESS) < 2500, "the injected document is too long to inject"

    def test_the_long_version_is_the_full_document(self):
        from jevqueue.awareness import AWARENESS, SHORT_AWARENESS

        assert len(AWARENESS) > len(SHORT_AWARENESS)
        for phrase in ("Do not retry", "fails open", "jevqueue_decide"):
            assert phrase in AWARENESS
            assert phrase in SHORT_AWARENESS


class TestTheSessionHook:
    def _run(self, event: str) -> str:
        import json
        import subprocess
        import sys

        hook = ROOT / "hooks" / "jevqueue_session.py"
        payload = json.dumps({"session_id": "t", "hook_event_name": event}).encode()
        result = subprocess.run(
            [sys.executable, str(hook)], input=payload, capture_output=True, timeout=60
        )
        assert result.returncode == 0
        return result.stdout.decode("utf-8", "replace")

    def test_it_injects_context_for_claude_code(self):
        import json

        out = self._run("SessionStart")
        data = json.loads(out)
        output = data["hookSpecificOutput"]

        assert output["hookEventName"] == "SessionStart"
        assert "jevqueue_decide" in output["additionalContext"]

    def test_it_injects_context_for_gemini(self):
        import json

        out = self._run("BeforeAgent")
        data = json.loads(out)
        output = data["hookSpecificOutput"]

        assert output["hookEventName"] == "BeforeAgent"
        assert "jevqueue_decide" in output["additionalContext"]

    def test_a_broken_payload_is_survivable(self):
        import subprocess
        import sys

        hook = ROOT / "hooks" / "jevqueue_session.py"
        result = subprocess.run(
            [sys.executable, str(hook)], input=b"not json", capture_output=True, timeout=60
        )

        assert result.returncode == 0


class TestTheDocs:
    def test_the_install_page_covers_every_agent_the_readme_claims(self):
        install = (ROOT / "docs" / "install.md").read_text(encoding="utf-8")
        for agent in ("Claude Code", "Codex", "Gemini", "opencode", "Cursor", "Windsurf",
                      "Kiro", "Cline", "OpenClaw", "Copilot"):
            assert agent in install, f"the install page does not mention {agent}"

    def test_the_install_page_says_how_to_test_it(self):
        install = (ROOT / "docs" / "install.md").read_text(encoding="utf-8")

        assert "python -m jevqueue" in install
        assert "jevqueue status" in install
        assert "jevqueue decide" in install

    def test_the_benefits_page_states_the_measured_token_numbers(self):
        benefits = (ROOT / "docs" / "benefits.md").read_text(encoding="utf-8")

        assert "215" in benefits
        assert "0" in benefits
        assert "static_tools" in benefits

    def test_the_benefits_page_is_honest_about_the_limits(self):
        benefits = (ROOT / "docs" / "benefits.md").read_text(encoding="utf-8")

        assert "not a planner" in benefits
        assert "not an authorization layer" in benefits
        assert "fails open" in benefits
        # The routing saving is real; the writing half is not improved.
        assert "not the writing half" in benefits

    def test_the_readme_links_the_new_pages(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        assert "docs/install.md" in readme
        assert "docs/benefits.md" in readme
