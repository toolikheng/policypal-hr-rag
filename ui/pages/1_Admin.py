"""Admin page: upload policies, re-ingest the folders and see the documents.

Uploading and re-ingesting need the admin token (ADMIN_TOKEN in .env), a shared demo
token rather than a user login. Each action stores its result in st.session_state and
reruns the page, so the result is shown in one place.
"""

import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.formatting import reingest_notice, safe_markdown, upload_summary

st.set_page_config(page_title="PolicyPal admin", page_icon="📘")
st.title("Admin")
st.caption("Policies here are **fictional sample data** for Binaan Maju Sdn Bhd.")

state = st.session_state
state.setdefault("notice", None)  # (NoticeLevel, message) from the last action
state.setdefault("conflict", None)  # a 409 upload: {filename, data, message, conflict}

client = api_client.make_client()
token = st.text_input("Admin token", type="password", key="admin_token")
if not token:
    st.info("Enter the admin token to upload or re-ingest policies.")


def upload(filename: str, data: bytes, replace: bool) -> None:
    state.notice, state.conflict = None, None
    try:
        result = client.upload(filename, data, token=token, replace=replace)
    except ApiError as exc:
        if exc.status_code == 409:
            state.conflict = {
                "filename": filename,
                "data": data,
                "message": str(exc),
                "conflict": exc.conflict,
            }
        else:
            state.notice = ("error", str(exc))
    else:
        state.notice = ("success", upload_summary(result))
    st.rerun()


def reingest() -> None:
    state.notice, state.conflict = None, None
    try:
        state.notice = reingest_notice(client.reingest(token=token))
    except ApiError as exc:
        state.notice = ("error", str(exc))
    st.rerun()


if state.notice:
    kind, message = state.notice
    # Messages can include a document's title, which comes from the uploaded file.
    show = {"success": st.success, "warning": st.warning, "error": st.error}[kind]
    show(safe_markdown(message))

st.subheader("Upload a policy")
file = st.file_uploader("Policy file (.md or .pdf)", key="policy_file")
if st.button("Upload", key="upload", disabled=not (token and file)):
    upload(file.name, file.getvalue(), replace=False)

if state.conflict:
    st.warning(safe_markdown(state.conflict["message"]))
    # Only an uploaded policy can be replaced; a built-in sample never can.
    if state.conflict["conflict"] == "name_taken" and st.button(
        "Replace existing policy", key="replace", disabled=not token
    ):
        upload(state.conflict["filename"], state.conflict["data"], replace=True)

st.subheader("Re-ingest")
st.caption("Re-scans the sample and upload folders. Unchanged files are skipped.")
if st.button("Re-ingest all", key="reingest", disabled=not token):
    reingest()

st.subheader("Documents")
try:
    documents = client.list_documents()
except ApiError as exc:
    st.error(str(exc))
else:
    st.dataframe(
        [
            {
                "Title": document["title"],
                "Slug": document["slug"],
                "Origin": document["origin"],
                "Type": document["file_type"],
                "Chunks": document["chunks"],
                "Updated": document["updated_at"],
            }
            for document in documents
        ],
        hide_index=True,
    )
