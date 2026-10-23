# End-to-end evaluation: golden set, ollama

The full pipeline, as `/ask` runs it (search, threshold, LLM, citation checks), without saving answers. A refusal is the mode `refused`; an extractive fallback counts as an answer.

## Configuration

| Setting | Value |
|---|---|
| Date (UTC) | 2026-10-23 15:26 |
| Commit | 7f3b687 |
| Question set | golden (52 questions: 40 answerable, 12 should be refused) |
| Policies | 8 sample policies from Markdown (119 chunks) |
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
| Refusal accuracy | 82.7% |
| Balanced accuracy | 85.8% |
| Answerable questions answered | 32/40 (80.0%) |
| Should-refuse questions refused | 11/12 (91.7%) |
| Refused before the LLM was asked | 19 |
| Questions the LLM was asked | 33 |
| Answers with a valid citation | 31/33 (93.9%) |
| Refused by the LLM | 0 |
| Fell back to quoting: llm_no_valid_citation | 2 |
| Quoted without an LLM (extractive mode) | 0 |
| Expected section cited (LLM answers) | 28/31 (90.3%) |
| Expected section cited (quoted answers) | 1/1 (100.0%) |
| Warm-up answer (not counted below) | 29.1 s |

## Answer time by mode

| Mode | Questions | Median | Mean | Max |
|---|---|---|---|---|
| extractive | 2 | 9.3 s | 9.3 s | 10.7 s |
| llm | 31 | 14.2 s | 14.2 s | 30.7 s |
| refused | 19 | 30 ms | 37 ms | 82 ms |
| LLM generation only | 33 | 13.3 s | 13.9 s | 30.6 s |

## By question type

| Question type | Answered | Expected section cited, no fallback | Refused |
|---|---|---|---|
| plain (10) | 6/10 (60.0%) | 5/10 (50.0%) | |
| look-alike (9) | 8/9 (88.9%) | 7/9 (77.8%) | |
| table (7) | 7/7 (100.0%) | 6/7 (85.7%) | |
| amendment (8) | 7/8 (87.5%) | 6/8 (75.0%) | |
| two-section (6) | 4/6 (66.7%) | 4/6 (66.7%) | |
| uncovered-topic (10) | | | 10/10 (100.0%) |
| missing-detail (2) | | | 1/2 (50.0%) |

## Error analysis

Every question with a wrong refusal, a fallback, a missing expected citation, or an answer where a refusal was expected.

| ID | Type | Question | Expected | Answer | Reason |
|---|---|---|---|---|---|
| g01 | plain | If a public holiday falls in the middle of my week of annual leave, is that day taken from my leave balance? | leave-policy — 4.1 Annual Leave Entitlement | [llm] According to policy excerpt [1] 9.3, if a public holiday falls on a rest day, the next working day is a paid holiday. However, this does not directly answer the question. I couldn't find this in the policies. | no expected section cited; cited: leave-policy — 9. Public Holidays. Note: The answer is the last paragraph of 4.1, below the entitlement table. |
| g02 | look-alike | I'm sick today and the doctor gave me an MC. By when must I tell my superior, and when do I upload the MC? | leave-policy — 5.1 Sick Leave (Outpatient) | [refused] I couldn't find this in the policies. | refused before the LLM was asked (best similarity 0.642). Note: Medical Claims 3.4 "Medical Certificates" and Leave 5.3 also talk about MCs. |
| g10 | plain | Can I claim physiotherapy, and is there a yearly cap? | medical-claims-policy — 7. Exclusions | [refused] I couldn't find this in the policies. | refused before the LLM was asked (best similarity 0.688). Note: Hidden in the exclusions list, item (d) (RM500 with a doctor's referral). |
| g11 | two-section | I'm a site technician and I worked on a Sunday to finish a job. At what rate is that paid? | overtime-policy — 3. Normal Working Hours; overtime-policy — 5. Overtime Rates | [refused] I couldn't find this in the policies. | refused before the LLM was asked (best similarity 0.682). Note: Needs section 3 (Sunday is the rest day) and section 5 (rest day 2.0 times the hourly rate). |
| g16 | amendment | What was the car mileage rate for the first 500 km before the 2025 change? | expense-claims-policy — 3.1 Mileage for Using Your Own Vehicle; expense-claims-policy — 10. Amendment History | [refused] I couldn't find this in the policies. | refused before the LLM was asked (best similarity 0.681). Note: Asks for the old value (RM0.60) from the amendment note. |
| g17 | table | What is the client entertainment limit per occasion for an M2 manager? | expense-claims-policy — 4.1 Client Entertainment | [extractive] No AI summary available — the most relevant policy passages are below. [1] Expense Claims Policy — 4.1 Client Entertainment > 4.1.1 Entertainment of clients, consultants and business partners must have a clear business purpose. The claim m… | fell back to quoting the policy (llm_no_valid_citation). Note: Table row "M1 and M2" (RM300). |
| g20 | look-alike | Can I claim a parking fine I got while visiting a client's office? | expense-claims-policy — 7. Items That Cannot Be Claimed | [llm] No, parking at the employee's own usual workplace is not reimbursed [1]. | no expected section cited; cited: expense-claims-policy — 3.2 Tolls and Parking. Note: Section 3.2 "Tolls and Parking" sounds right, but fines are excluded in section 7. |
| g22 | amendment | How much allowance do I get if I stay with relatives instead of a hotel on an outstation trip? | travel-policy — 4. Accommodation; travel-policy — 8. Amendment History | [llm] According to policy excerpt [1] 5.1.3, where meals are provided free, for example by a client or at a conference, the allowance is reduced by one third for each main meal provided. However, this excerpt does not directly address the lodgin… | no expected section cited; cited: travel-policy — 5.1 Outstation Meal Allowance. Note: Raised from RM50 to RM60 in version 3.0; the old value is only in the amendment history. |
| g28 | plain | A colleague keeps making sexual jokes about me. Who can I report it to? | code-of-conduct — 5.2 Anti-Harassment | [refused] I couldn't find this in the policies. | refused before the LLM was asked (best similarity 0.608). Note: A long section split into two chunks. |
| g29 | plain | Am I allowed to post photos of our project site on Instagram? | code-of-conduct — 7.2 Social Media | [refused] I couldn't find this in the policies. | refused before the LLM was asked (best similarity 0.587). Note: The words "social media" are not in the question. |
| g30 | two-section | What happens if I'm late three times in a month, and can I appeal against a warning? | code-of-conduct — 5.3 Attendance and Punctuality; code-of-conduct — 9. Disciplinary Action | [refused] I couldn't find this in the policies. | refused before the LLM was asked (best similarity 0.634). Note: Needs 5.3 (a verbal warning) and 9 (appeal in writing within seven days). |
| g38 | plain | Can I use the free Wi-Fi at a coffee shop when I'm working from home? | work-from-home-policy — 8. Information Security | [refused] I couldn't find this in the policies. | refused before the LLM was asked (best similarity 0.623). Note: The answer is "only through the VPN" (8.1). |
| g51 | missing-detail | What is the hotel limit per night for a business trip to Singapore? | (should be refused) | [extractive] No AI summary available — the most relevant policy passages are below. [1] Travel Policy — 4. Accommodation > 4.1 Hotel room limits per night, including service charge and tax: > > \| Grade \| Kuala Lumpur, Penang and Johor Bahru \| Other tow… | answered (extractive) instead of refusing. Note: Travel 4 gives hotel limits for Malaysian locations only; there is no overseas hotel limit. |

## Not measured

Whether the answer text is correct and complete is not checked automatically: that needs a person or an LLM judge. The error analysis shows each answer that went wrong so it can be read. A missing-detail question counts as answered when the model explains the gap instead of using the refusal sentence.

## Limitations

- The question sets are small, so one question moves a rate by several percentage points.
- The questions were written by the person who built the system, who knows the policies.
  They were committed before any run, and the held-out Training policy is tested separately.
- The policies and questions are fictional sample data in English.
