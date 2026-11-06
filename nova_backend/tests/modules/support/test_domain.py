"""support · the field rules of a follow-up. No database."""

from uuid import uuid4

from app.modules.support.domain import MAX_TEXT_LENGTH, chat_reference, clip_text


def test_text_is_trimmed_cut_to_length_and_blank_is_nothing() -> None:
    assert clip_text("  my nails chipped  ") == "my nails chipped"
    assert clip_text("   ") is None
    assert clip_text(None) is None
    assert clip_text("x" * (MAX_TEXT_LENGTH + 50)) == "x" * MAX_TEXT_LENGTH


def test_one_conversation_is_one_reference_and_the_session_id_is_not_kept() -> None:
    person, business = uuid4(), uuid4()
    reference = chat_reference(person, business, "session-1")

    assert reference == chat_reference(person, business, "session-1")
    assert len(reference) == 64
    assert "session-1" not in reference
    # Another session, person or business is another conversation.
    assert reference != chat_reference(person, business, "session-2")
    assert reference != chat_reference(uuid4(), business, "session-1")
    assert reference != chat_reference(person, None, "session-1")
