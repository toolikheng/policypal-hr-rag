"""PolicyPal chat page (placeholder until Phase 3: shows whether the API is healthy)."""

import os

import httpx
import streamlit as st

from ui.api_client import ApiError, PolicyPalClient

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="PolicyPal", page_icon="📘")
st.title("PolicyPal")
st.caption(
    "HR policy assistant for Binaan Maju Sdn Bhd — **fictional sample data**, "
    "not real company policies."
)

client = PolicyPalClient(httpx.Client(base_url=API_URL, timeout=5))
try:
    health = client.health()
except ApiError as exc:
    st.error(str(exc))
else:
    if health["status"] == "ok":
        st.success(f"API is healthy (version {health['version']}).")
    elif health["status"] == "degraded":
        st.warning("API is up, but the AI model isn't ready: answers will quote the policy text.")
    else:
        st.warning(f"API is running but not ready: database is {health['database']}.")

st.info("The chat interface arrives in a later phase.")
