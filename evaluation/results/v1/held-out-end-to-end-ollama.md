# End-to-end evaluation: held-out set, ollama

The full pipeline, as `/ask` runs it (search, threshold, LLM, citation checks), without saving answers. A refusal is the mode `refused`; an extractive fallback counts as an answer.

## Configuration

| Setting | Value |
|---|---|
| Date (UTC) | 2026-10-23 15:37 |
| Commit | 9dc7dbb |
| Question set | held-out (10 questions: 8 answerable, 2 should be refused) |
| Policies | 8 sample policies from Markdown + upload training-and-development-policy (130 chunks) |
| Embedding model | BAAI/bge-small-en-v1.5 |
| Query instruction | on |
| Top k | 5 |
| Threshold | 0.69 (from the dev set) |
| LLM | llama3.2:3b (ollama) |
| CPU | Intel(R) Core(TM) i5-10300H CPU @ 2.50GHz (8 logical CPUs) |
| RAM | 11.6 GiB visible |
| Operating system | Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.41 |
| Python | 3.12.14 |
| Docker | Docker Desktop 4.86.0 (236216), engine 29.7.2 |

## Results

| | Value |
|---|---|
| Refusal accuracy | 70.0% |
| Balanced accuracy | 43.8% |
| Answerable questions answered | 7/8 (87.5%) |
| Should-refuse questions refused | 0/2 (0.0%) |
| Refused before the LLM was asked | 1 |
| Questions the LLM was asked | 9 |
| Answers with a valid citation | 7/9 (77.8%) |
| Refused by the LLM | 0 |
| Fell back to quoting: llm_no_valid_citation | 2 |
| Quoted without an LLM (extractive mode) | 0 |
| Expected section cited (LLM answers) | 5/5 (100.0%) |
| Expected section cited (quoted answers) | 2/2 (100.0%) |
| Warm-up answer (not counted below) | 5.5 s |

## Answer time by mode

| Mode | Questions | Median | Mean | Max |
|---|---|---|---|---|
| extractive | 2 | 5.4 s | 5.4 s | 6.2 s |
| llm | 7 | 9.2 s | 9.3 s | 19.0 s |
| refused | 1 | 36 ms | 36 ms | 36 ms |
| LLM generation only | 9 | 8.6 s | 8.4 s | 18.9 s |

## By question type

| Question type | Answered | Expected section cited, no fallback | Refused |
|---|---|---|---|
| plain (3) | 2/3 (66.7%) | 2/3 (66.7%) | |
| look-alike (3) | 3/3 (100.0%) | 1/3 (33.3%) | |
| table (1) | 1/1 (100.0%) | 1/1 (100.0%) | |
| two-section (1) | 1/1 (100.0%) | 1/1 (100.0%) | |
| missing-detail (2) | | | 0/2 (0.0%) |

## Error analysis

Every question with a wrong refusal, a fallback, a missing expected citation, or an answer where a refusal was expected.

| ID | Type | Question | Expected | Answer | Reason |
|---|---|---|---|---|---|
| h03 | look-alike | If the company asks me to attend training on my rest day, do I get anything for it? | training-and-development-policy — 3. Training Days | [extractive] No AI summary available — the most relevant policy passages are below. [1] Training and Development Policy — 3. Training Days > 3.1 Every employee should complete at least five days (40 hours) of training each calendar year. Training hours… | fell back to quoting the policy (llm_no_valid_citation). Note: Clause 3.3; Overtime 5 (rest-day rate) and Overtime 8 (time off in lieu) look similar. |
| h04 | plain | The company paid for my course and now I want to resign. Do I have to pay anything back? | training-and-development-policy — 7. Training Bond | [refused] I couldn't find this in the policies. | refused before the LLM was asked (best similarity 0.656). Note: Conversational; the word "bond" is not in the question. |
| h05 | look-alike | Do I get time off to sit a professional exam? | training-and-development-policy — 6. Professional Certifications | [extractive] No AI summary available — the most relevant policy passages are below. [1] Training and Development Policy — 6. Professional Certifications > 6.1 Examination fees for professional certifications approved by the HOD are reimbursed once the … | fell back to quoting the policy (llm_no_valid_citation). Note: Exam leave (6.2) competes with the Leave Policy's leave types. |
| h09 | missing-detail | What happens to my training bond if my position is made redundant? | (should be refused) | [llm] According to policy [1], if an employee is made redundant, the bond period is terminated, and the employee is no longer required to repay the sponsorship. | answered (llm) instead of refusing. Note: Clause 7.3 covers resignation and dismissal for misconduct only; redundancy is not covered. |
| h10 | missing-detail | Who pays for the construction safety induction card? | (should be refused) | [llm] The construction safety induction card is issued free of charge to site-based employees who have completed the Company's two-day site safety induction. [1] | answered (llm) instead of refusing. Note: Clause 8.1 requires the card but does not say who pays for it. |

## Not measured

Whether the answer text is correct and complete is not checked automatically: that needs a person or an LLM judge. The error analysis shows each answer that went wrong so it can be read. A missing-detail question counts as answered when the model explains the gap instead of using the refusal sentence.

## Limitations

- The question sets are small, so one question moves a rate by several percentage points.
- The questions were written by the person who built the system, who knows the policies.
  They were committed before any run, and the held-out Training policy is tested separately.
- The policies and questions are fictional sample data in English.
