"""Analytics page: what staff ask, what the policies don't cover, and how answers are rated.

The figures come from GET /analytics, which needs the admin token (ADMIN_TOKEN in .env).
"""

import streamlit as st

from ui import api_client
from ui.api_client import ApiError, QuestionCount
from ui.formatting import fallback_label, percent, seconds

st.set_page_config(page_title="PolicyPal analytics", page_icon="📘")
st.title("Analytics")
st.caption("Policies here are **fictional sample data** for Binaan Maju Sdn Bhd.")

client = api_client.make_client()
token = st.text_input("Admin token", type="password", key="analytics_token")
days = st.selectbox(
    "Period", [7, 30, 90, 365], index=1, key="period", format_func=lambda d: f"Last {d} days"
)
if not token:
    st.info("Enter the admin token to see analytics.")
    st.stop()

try:
    report = client.analytics(days, token=token)
except ApiError as exc:
    st.error(str(exc))
    st.stop()


def question_table(rows: list[QuestionCount], empty: str) -> None:
    if not rows:
        st.caption(empty)
        return
    st.dataframe(
        [
            {
                "Question": row["question"],
                "Times asked": row["count"],
                "Last asked": row["last_asked"],
            }
            for row in rows
        ],
        hide_index=True,
    )


feedback, latency = report["feedback"], report["avg_latency_ms"]
questions, refused, voted, helpful = st.columns(4)
questions.metric("Questions", str(report["total_questions"]))
refused.metric("Refused", f"{report['refused']} ({percent(report['refusal_rate'])})")
voted.metric("Feedback rate", percent(feedback["feedback_rate"]))
helpful.metric("Helpful", percent(feedback["helpful_rate"]))
st.caption(
    f"{feedback['up']} 👍 and {feedback['down']} 👎. Feedback rate = answers with a vote ÷ all "
    "answers; helpful = 👍 ÷ votes. A dash means there is nothing to count yet."
)

overall, ai, quoted = st.columns(3)
overall.metric("Avg time (all)", seconds(latency["overall"]))
ai.metric("Avg time (AI)", seconds(latency["llm"]))
quoted.metric("Avg time (quoted)", seconds(latency["extractive"]))

st.subheader("Top questions")
question_table(report["top_questions"], "No questions in this period yet.")

st.subheader("Unanswered questions")
st.caption("Questions the policies didn't cover, so the assistant refused.")
question_table(report["unanswered_questions"], "No refused questions in this period.")

st.subheader("Fallbacks to quoted policy text")
st.caption("Answers where the AI model couldn't be used, so the policy text was quoted.")
if report["fallbacks"]:
    st.dataframe(
        [
            {"Reason": fallback_label(row["reason"]), "Answers": row["count"]}
            for row in report["fallbacks"]
        ],
        hide_index=True,
    )
else:
    st.caption("No fallbacks in this period.")
