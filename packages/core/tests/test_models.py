from semanticcache_core.models import ChatMessage, ChatRequest


def req(*pairs: tuple[str, str], model: str = "gpt-4o-mini", **kw: object) -> ChatRequest:
    return ChatRequest(model=model, messages=[ChatMessage(role=r, content=c) for r, c in pairs], **kw)


def test_query_text_is_the_last_user_message() -> None:
    r = req(("system", "Be brief"), ("user", "first"), ("assistant", "ok"), ("user", "second"))
    assert r.query_text() == "second"


def test_multimodal_content_reduces_to_its_text_parts() -> None:
    m = ChatMessage(
        role="user",
        content=[{"type": "text", "text": "hi"}, {"type": "image_url", "image_url": {"url": "x"}}],
    )
    assert m.text() == "hi"


def test_scope_ignores_case_whitespace_and_the_question_itself() -> None:
    a = req(("system", "Be brief"), ("user", "How do I reset my password?"))
    b = req(("system", "  be   BRIEF "), ("user", "something completely different"))
    assert a.scope_key() == b.scope_key()


def test_scope_separates_models_system_prompts_and_history() -> None:
    base = req(("system", "Be brief"), ("user", "q"))
    assert base.scope_key() != req(("system", "Be brief"), ("user", "q"), model="gpt-4o").scope_key()
    assert base.scope_key() != req(("system", "Be verbose"), ("user", "q")).scope_key()
    with_history = req(("system", "Be brief"), ("user", "earlier"), ("assistant", "a"), ("user", "q"))
    assert base.scope_key() != with_history.scope_key()
    assert (
        with_history.scope_key()
        != req(
            ("system", "Be brief"), ("user", "other earlier"), ("assistant", "a"), ("user", "q")
        ).scope_key()
    )


def test_scope_separates_output_shape_params() -> None:
    base = req(("user", "q"))
    assert base.scope_key() != req(("user", "q"), response_format={"type": "json_object"}).scope_key()
    assert base.scope_key() != req(("user", "q"), max_tokens=10).scope_key()
    assert base.scope_key() != req(("user", "q"), tools=[{"type": "function"}]).scope_key()
