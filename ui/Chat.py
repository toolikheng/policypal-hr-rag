"""PolicyPal chat page: ask HR policy questions; answers cite the policy and section.

Streamlit runs this script again from the top on every click, so everything that must
last (the conversation, votes, fetched sections) lives in st.session_state.
Text is shown as Markdown through safe_markdown() (no images load by themselves); HTML is
never allowed.
"""

import streamlit as st

from ui import api_client
from ui.api_client import Answer, ApiError, PolicyPalApi
from ui.formatting import badge, safe_markdown, section_text, source_label

st.set_page_config(page_title="PolicyPal", page_icon="📘")
st.title("PolicyPal")
st.caption(
    "HR policy assistant for Binaan Maju Sdn Bhd — **fictional sample data**, "
    "not real company policies."
)

state = st.session_state
state.setdefault("conversation_id", None)
state.setdefault("turns", [])  # [{"question": str, "answer": Answer}]
state.setdefault("votes", {})  # message_id -> "up" / "down"
# (turn index, citation number) -> the full section's text, fetched once when opened.
state.setdefault("sections", {})


def show_health(client: PolicyPalApi) -> None:
    """Warn when the API can't answer properly; stop the page if it can't be reached."""
    try:
        health = client.health()
    except ApiError as exc:
        st.error(str(exc))
        st.stop()
    if health["status"] == "degraded":
        st.warning("The AI model isn't ready: answers will quote the policy text.")
    elif health["status"] != "ok":
        st.error(f"The API is running but not ready: database is {health['database']}.")


def show_turn(client: PolicyPalApi, index: int, question: str, answer: Answer) -> None:
    with st.chat_message("user"):
        st.markdown(safe_markdown(question))
    with st.chat_message("assistant"):
        st.caption(badge(answer))
        st.markdown(safe_markdown(answer["answer"]))
        for citation in answer["citations"]:
            show_source(client, index, citation)
        show_feedback(client, index, answer["message_id"])


def show_source(client: PolicyPalApi, index: int, citation: dict) -> None:
    key = (index, citation["number"])
    with st.expander(source_label(citation)):
        st.markdown(safe_markdown(citation["text"]))
        if key not in state.sections and st.button(
            "View full section", key=f"section-{index}-{citation['number']}"
        ):
            try:
                document = client.get_document(citation["document_id"])
            except ApiError as exc:
                st.error(str(exc))
            else:
                state.sections[key] = section_text(document, citation["section"])
        if key in state.sections:
            st.markdown("**Full section**")
            st.markdown(safe_markdown(state.sections[key]))


def show_feedback(client: PolicyPalApi, index: int, message_id: str) -> None:
    if message_id in state.votes:
        st.caption("Thanks for your feedback.")
        return
    up, down, _ = st.columns([1, 1, 8])
    for column, rating, label in ((up, "up", "👍"), (down, "down", "👎")):
        if column.button(label, key=f"{rating}-{index}", help=f"Rate this answer {rating}"):
            try:
                client.feedback(message_id, rating)
            except ApiError as exc:
                st.error(str(exc))
            else:
                state.votes[message_id] = rating
                st.rerun()


client = api_client.make_client()
show_health(client)

for index, turn in enumerate(state.turns):
    show_turn(client, index, turn["question"], turn["answer"])

question = st.chat_input("Ask about leave, claims, overtime, travel, probation…")
if question:
    with st.spinner("Searching the policies… (an AI answer can take a minute on a CPU)"):
        try:
            answer = client.ask(question, state.conversation_id)
        except ApiError as exc:
            st.error(str(exc))
        else:
            state.conversation_id = answer["conversation_id"]
            state.turns.append({"question": question, "answer": answer})
            st.rerun()
