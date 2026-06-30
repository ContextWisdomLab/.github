from scripts.ci.render_opencode_prompt_template import render_prompt


def test_render_prompt_replaces_only_explicit_placeholders():
    text = (
        "Review PR #${PR_NUMBER} in ${OPENCODE_SOURCE_WORKDIR} with "
        "${model_candidate}.\n"
        "`python3 scripts/ci/sandboxed_verify.py --repo-root "
        '"$OPENCODE_SOURCE_WORKDIR" -- <verification command>`\n'
        "$(echo should_not_run)\n"
    )

    rendered = render_prompt(
        text,
        {
            "PR_NUMBER": "193",
            "OPENCODE_SOURCE_WORKDIR": "/tmp/pr-head",
            "PROMPT_MODEL_CANDIDATE": "github-models/openai/o4-mini",
        },
    )

    assert "Review PR #193 in /tmp/pr-head" in rendered
    assert "github-models/openai/o4-mini" in rendered
    assert '"$OPENCODE_SOURCE_WORKDIR"' in rendered
    assert "`python3 scripts/ci/sandboxed_verify.py" in rendered
    assert "$(echo should_not_run)" in rendered
