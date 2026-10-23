# Retrieval evaluation: golden set

Search only (no LLM). Hit rate@k: the share of answerable questions with an expected section in the top k results. Refusals: a question is refused when its best match is below the threshold, as in the app.

## Configuration

| Setting | Value |
|---|---|
| Date (UTC) | 2026-10-23 15:25 |
| Commit | 7f3b687 |
| Question set | golden (52 questions: 40 answerable, 12 should be refused) |
| Policies | 8 sample policies from Markdown (119 chunks); 8 sample policies from PDF (119 chunks) |
| Embedding model | BAAI/bge-small-en-v1.5 |
| Query instruction | on and off (both reported) |
| Top k | 5 |
| Threshold | from the dev set: 0.69 with the instruction, 0.71 without |
| LLM | none (search only) |
| CPU | Intel(R) Core(TM) i5-10300H CPU @ 2.50GHz (8 logical CPUs) |
| RAM | 11.6 GiB visible |
| Operating system | Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.41 |
| Python | 3.12.14 |
| Docker | Docker Desktop 4.86.0 (236216), engine 29.7.2 |

## Results

| | Markdown, instruction on | Markdown, instruction off | PDF, instruction on | PDF, instruction off |
|---|---|---|---|---|
| Section hit@1 | 35/40 (87.5%) | 35/40 (87.5%) | 35/40 (87.5%) | 34/40 (85.0%) |
| Section hit@3 | 39/40 (97.5%) | 39/40 (97.5%) | 39/40 (97.5%) | 40/40 (100.0%) |
| Section hit@5 | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) |
| Document hit@1 | 38/40 (95.0%) | 38/40 (95.0%) | 38/40 (95.0%) | 38/40 (95.0%) |
| Document hit@3 | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) |
| Document hit@5 | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) | 40/40 (100.0%) |
| Both sections in the top 5 (two-section questions) | 6/6 (100.0%) | 6/6 (100.0%) | 6/6 (100.0%) | 6/6 (100.0%) |
| Threshold | 0.69 | 0.71 | 0.69 | 0.71 |
| Refusal accuracy | 82.7% | 84.6% | 84.6% | 86.5% |
| Balanced accuracy | 85.8% | 87.1% | 87.1% | 88.3% |
| Answerable questions answered | 32/40 (80.0%) | 33/40 (82.5%) | 33/40 (82.5%) | 34/40 (85.0%) |
| Should-refuse questions refused | 11/12 (91.7%) | 11/12 (91.7%) | 11/12 (91.7%) | 11/12 (91.7%) |
| Search time per question (median / mean) | 19 ms / 21 ms | 18 ms / 19 ms | 20 ms / 21 ms | 19 ms / 20 ms |

## Section hit@1 by question type

| Question type | Markdown, instruction on | Markdown, instruction off | PDF, instruction on | PDF, instruction off |
|---|---|---|---|---|
| plain (10) | 9/10 (90.0%) | 9/10 (90.0%) | 9/10 (90.0%) | 9/10 (90.0%) |
| look-alike (9) | 6/9 (66.7%) | 6/9 (66.7%) | 6/9 (66.7%) | 6/9 (66.7%) |
| table (7) | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) |
| amendment (8) | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) | 6/8 (75.0%) |
| two-section (6) | 6/6 (100.0%) | 6/6 (100.0%) | 6/6 (100.0%) | 6/6 (100.0%) |

## Section hit@5 by question type

| Question type | Markdown, instruction on | Markdown, instruction off | PDF, instruction on | PDF, instruction off |
|---|---|---|---|---|
| plain (10) | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) |
| look-alike (9) | 9/9 (100.0%) | 9/9 (100.0%) | 9/9 (100.0%) | 9/9 (100.0%) |
| table (7) | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) |
| amendment (8) | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) |
| two-section (6) | 6/6 (100.0%) | 6/6 (100.0%) | 6/6 (100.0%) | 6/6 (100.0%) |

## Refusals by question type (should be refused)

| Question type | Markdown, instruction on | Markdown, instruction off | PDF, instruction on | PDF, instruction off |
|---|---|---|---|---|
| uncovered-topic (10) | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) | 10/10 (100.0%) |
| missing-detail (2) | 1/2 (50.0%) | 1/2 (50.0%) | 1/2 (50.0%) | 1/2 (50.0%) |

## Error analysis

Every question that was not perfect: the expected section was not ranked first, an answerable question would be refused, or a question that should be refused would be answered. The reason combines what happened with the note written with the question.

### Markdown, instruction on

| ID | Type | Question | Expected | Retrieved (top 3) | Reason |
|---|---|---|---|---|---|
| g01 | plain | If a public holiday falls in the middle of my week of annual leave, is that day taken from my leave balance? | leave-policy — 4.1 Annual Leave Entitlement | leave-policy — 9. Public Holidays (0.742); leave-policy — 4.3 Carry Forward of Annual Leave (0.713); leave-policy — 4.5 Joining or Leaving Part-Way Through the Year (0.692) | expected section ranked 5; ranked first: another section of the same policy. Note: The answer is the last paragraph of 4.1, below the entitlement table. |
| g02 | look-alike | I'm sick today and the doctor gave me an MC. By when must I tell my superior, and when do I upload the MC? | leave-policy — 5.1 Sick Leave (Outpatient) | medical-claims-policy — 3.4 Medical Certificates (0.642); leave-policy — 5.1 Sick Leave (Outpatient) (0.633); medical-claims-policy — 4.3 Hospital Admission Procedure (0.614) | expected section ranked 2; ranked first: a look-alike section in another policy; refused: best similarity 0.642 is below the threshold 0.69. Note: Medical Claims 3.4 "Medical Certificates" and Leave 5.3 also talk about MCs. |
| g10 | plain | Can I claim physiotherapy, and is there a yearly cap? | medical-claims-policy — 7. Exclusions | medical-claims-policy — 7. Exclusions (0.688); expense-claims-policy — 6. Professional Memberships (0.662); medical-claims-policy — 5. Dental Benefits (0.651) | refused: best similarity 0.688 is below the threshold 0.69. Note: Hidden in the exclusions list, item (d) (RM500 with a doctor's referral). |
| g11 | two-section | I'm a site technician and I worked on a Sunday to finish a job. At what rate is that paid? | overtime-policy — 3. Normal Working Hours; overtime-policy — 5. Overtime Rates | overtime-policy — 5. Overtime Rates (0.682); overtime-policy — 3. Normal Working Hours (0.627); work-from-home-policy — 5.2 Internet and Utilities Allowance (0.598) | refused: best similarity 0.682 is below the threshold 0.69. Note: Needs section 3 (Sunday is the rest day) and section 5 (rest day 2.0 times the hourly rate). |
| g16 | amendment | What was the car mileage rate for the first 500 km before the 2025 change? | expense-claims-policy — 3.1 Mileage for Using Your Own Vehicle; expense-claims-policy — 10. Amendment History | expense-claims-policy — 10. Amendment History (0.681); expense-claims-policy — 3.1 Mileage for Using Your Own Vehicle (0.634); travel-policy — 8. Amendment History (0.561) | refused: best similarity 0.681 is below the threshold 0.69. Note: Asks for the old value (RM0.60) from the amendment note. |
| g20 | look-alike | Can I claim a parking fine I got while visiting a client's office? | expense-claims-policy — 7. Items That Cannot Be Claimed | expense-claims-policy — 3.2 Tolls and Parking (0.710); expense-claims-policy — 3.3 Taxi and E-hailing (0.651); expense-claims-policy — 7. Items That Cannot Be Claimed (0.649) | expected section ranked 3; ranked first: another section of the same policy. Note: Section 3.2 "Tolls and Parking" sounds right, but fines are excluded in section 7. |
| g22 | amendment | How much allowance do I get if I stay with relatives instead of a hotel on an outstation trip? | travel-policy — 4. Accommodation; travel-policy — 8. Amendment History | travel-policy — 5.1 Outstation Meal Allowance (0.726); travel-policy — 6.1 Overseas Daily Allowance (0.697); travel-policy — 4. Accommodation (0.695) | expected section ranked 3; ranked first: another section of the same policy. Note: Raised from RM50 to RM60 in version 3.0; the old value is only in the amendment history. |
| g23 | look-alike | I'm driving my own car to a project site 400 km away. Is there any limit on what I can claim for mileage? | travel-policy — 3.2 Using Your Own Vehicle for Outstation Travel | expense-claims-policy — 3.1 Mileage for Using Your Own Vehicle (0.782); travel-policy — 3.2 Using Your Own Vehicle for Outstation Travel (0.727); travel-policy — 5.2 Remote Site Allowance (0.652) | expected section ranked 2; ranked first: a look-alike section in another policy. Note: Expense Claims 3.1 has the mileage rates, but the cap for trips over 350 km is in Travel 3.2. |
| g28 | plain | A colleague keeps making sexual jokes about me. Who can I report it to? | code-of-conduct — 5.2 Anti-Harassment | code-of-conduct — 5.2 Anti-Harassment (0.608); code-of-conduct — 5.2 Anti-Harassment (0.581); expense-claims-policy — 4.1 Client Entertainment (0.529) | refused: best similarity 0.608 is below the threshold 0.69. Note: A long section split into two chunks. |
| g29 | plain | Am I allowed to post photos of our project site on Instagram? | code-of-conduct — 7.2 Social Media | code-of-conduct — 7.2 Social Media (0.587); travel-policy — 5.2 Remote Site Allowance (0.518); code-of-conduct — 7.3 Confidential Information (0.516) | refused: best similarity 0.587 is below the threshold 0.69. Note: The words "social media" are not in the question. |
| g30 | two-section | What happens if I'm late three times in a month, and can I appeal against a warning? | code-of-conduct — 5.3 Attendance and Punctuality; code-of-conduct — 9. Disciplinary Action | code-of-conduct — 5.3 Attendance and Punctuality (0.634); code-of-conduct — 9. Disciplinary Action (0.583); travel-policy — 7. Claims After Travel (0.552) | refused: best similarity 0.634 is below the threshold 0.69. Note: Needs 5.3 (a verbal warning) and 9 (appeal in writing within seven days). |
| g38 | plain | Can I use the free Wi-Fi at a coffee shop when I'm working from home? | work-from-home-policy — 8. Information Security | work-from-home-policy — 8. Information Security (0.623); work-from-home-policy — 5.1 Company Equipment (0.601); work-from-home-policy — 1. Purpose (0.590) | refused: best similarity 0.623 is below the threshold 0.69. Note: The answer is "only through the VPN" (8.1). |
| g51 | missing-detail | What is the hotel limit per night for a business trip to Singapore? | (should be refused) | travel-policy — 4. Accommodation (0.761); travel-policy — 8. Amendment History (0.661); expense-claims-policy — 4.1 Client Entertainment (0.628) | answered: best similarity 0.761 reaches the threshold 0.69. Note: Travel 4 gives hotel limits for Malaysian locations only; there is no overseas hotel limit. |

### Markdown, instruction off

| ID | Type | Question | Expected | Retrieved (top 3) | Reason |
|---|---|---|---|---|---|
| g01 | plain | If a public holiday falls in the middle of my week of annual leave, is that day taken from my leave balance? | leave-policy — 4.1 Annual Leave Entitlement | leave-policy — 9. Public Holidays (0.767); leave-policy — 4.3 Carry Forward of Annual Leave (0.743); leave-policy — 4.5 Joining or Leaving Part-Way Through the Year (0.725) | expected section ranked 4; ranked first: another section of the same policy. Note: The answer is the last paragraph of 4.1, below the entitlement table. |
| g02 | look-alike | I'm sick today and the doctor gave me an MC. By when must I tell my superior, and when do I upload the MC? | leave-policy — 5.1 Sick Leave (Outpatient) | medical-claims-policy — 3.4 Medical Certificates (0.662); leave-policy — 5.1 Sick Leave (Outpatient) (0.658); medical-claims-policy — 4.3 Hospital Admission Procedure (0.653) | expected section ranked 2; ranked first: a look-alike section in another policy; refused: best similarity 0.662 is below the threshold 0.71. Note: Medical Claims 3.4 "Medical Certificates" and Leave 5.3 also talk about MCs. |
| g11 | two-section | I'm a site technician and I worked on a Sunday to finish a job. At what rate is that paid? | overtime-policy — 3. Normal Working Hours; overtime-policy — 5. Overtime Rates | overtime-policy — 5. Overtime Rates (0.707); overtime-policy — 3. Normal Working Hours (0.646); overtime-policy — 7. Meal and Transport Allowances for Overtime (0.624) | refused: best similarity 0.707 is below the threshold 0.71. Note: Needs section 3 (Sunday is the rest day) and section 5 (rest day 2.0 times the hourly rate). |
| g16 | amendment | What was the car mileage rate for the first 500 km before the 2025 change? | expense-claims-policy — 3.1 Mileage for Using Your Own Vehicle; expense-claims-policy — 10. Amendment History | expense-claims-policy — 10. Amendment History (0.702); expense-claims-policy — 3.1 Mileage for Using Your Own Vehicle (0.654); travel-policy — 8. Amendment History (0.580) | refused: best similarity 0.702 is below the threshold 0.71. Note: Asks for the old value (RM0.60) from the amendment note. |
| g20 | look-alike | Can I claim a parking fine I got while visiting a client's office? | expense-claims-policy — 7. Items That Cannot Be Claimed | expense-claims-policy — 3.2 Tolls and Parking (0.723); expense-claims-policy — 3.3 Taxi and E-hailing (0.664); expense-claims-policy — 7. Items That Cannot Be Claimed (0.660) | expected section ranked 3; ranked first: another section of the same policy. Note: Section 3.2 "Tolls and Parking" sounds right, but fines are excluded in section 7. |
| g22 | amendment | How much allowance do I get if I stay with relatives instead of a hotel on an outstation trip? | travel-policy — 4. Accommodation; travel-policy — 8. Amendment History | travel-policy — 5.1 Outstation Meal Allowance (0.734); travel-policy — 4. Accommodation (0.717); travel-policy — 6.1 Overseas Daily Allowance (0.703) | expected section ranked 2; ranked first: another section of the same policy. Note: Raised from RM50 to RM60 in version 3.0; the old value is only in the amendment history. |
| g23 | look-alike | I'm driving my own car to a project site 400 km away. Is there any limit on what I can claim for mileage? | travel-policy — 3.2 Using Your Own Vehicle for Outstation Travel | expense-claims-policy — 3.1 Mileage for Using Your Own Vehicle (0.798); travel-policy — 3.2 Using Your Own Vehicle for Outstation Travel (0.735); travel-policy — 5.2 Remote Site Allowance (0.672) | expected section ranked 2; ranked first: a look-alike section in another policy. Note: Expense Claims 3.1 has the mileage rates, but the cap for trips over 350 km is in Travel 3.2. |
| g28 | plain | A colleague keeps making sexual jokes about me. Who can I report it to? | code-of-conduct — 5.2 Anti-Harassment | code-of-conduct — 5.2 Anti-Harassment (0.636); code-of-conduct — 5.2 Anti-Harassment (0.608); expense-claims-policy — 4.1 Client Entertainment (0.557) | refused: best similarity 0.636 is below the threshold 0.71. Note: A long section split into two chunks. |
| g29 | plain | Am I allowed to post photos of our project site on Instagram? | code-of-conduct — 7.2 Social Media | code-of-conduct — 7.2 Social Media (0.599); travel-policy — 5.2 Remote Site Allowance (0.529); code-of-conduct — 7.3 Confidential Information (0.529) | refused: best similarity 0.599 is below the threshold 0.71. Note: The words "social media" are not in the question. |
| g30 | two-section | What happens if I'm late three times in a month, and can I appeal against a warning? | code-of-conduct — 5.3 Attendance and Punctuality; code-of-conduct — 9. Disciplinary Action | code-of-conduct — 5.3 Attendance and Punctuality (0.672); code-of-conduct — 9. Disciplinary Action (0.606); travel-policy — 7. Claims After Travel (0.593) | refused: best similarity 0.672 is below the threshold 0.71. Note: Needs 5.3 (a verbal warning) and 9 (appeal in writing within seven days). |
| g38 | plain | Can I use the free Wi-Fi at a coffee shop when I'm working from home? | work-from-home-policy — 8. Information Security | work-from-home-policy — 8. Information Security (0.659); work-from-home-policy — 5.1 Company Equipment (0.636); work-from-home-policy — 6. Working Hours and Overtime (0.604) | refused: best similarity 0.659 is below the threshold 0.71. Note: The answer is "only through the VPN" (8.1). |
| g51 | missing-detail | What is the hotel limit per night for a business trip to Singapore? | (should be refused) | travel-policy — 4. Accommodation (0.772); travel-policy — 8. Amendment History (0.675); expense-claims-policy — 4.1 Client Entertainment (0.638) | answered: best similarity 0.772 reaches the threshold 0.71. Note: Travel 4 gives hotel limits for Malaysian locations only; there is no overseas hotel limit. |

### PDF, instruction on

| ID | Type | Question | Expected | Retrieved (top 3) | Reason |
|---|---|---|---|---|---|
| g01 | plain | If a public holiday falls in the middle of my week of annual leave, is that day taken from my leave balance? | leave-policy — 4.1 Annual Leave Entitlement | leave-policy — 9. Public Holidays (0.742); leave-policy — 4.3 Carry Forward of Annual Leave (0.712); leave-policy — 4.5 Joining or Leaving Part-Way Through the Year (0.692) | expected section ranked 4; ranked first: another section of the same policy. Note: The answer is the last paragraph of 4.1, below the entitlement table. |
| g02 | look-alike | I'm sick today and the doctor gave me an MC. By when must I tell my superior, and when do I upload the MC? | leave-policy — 5.1 Sick Leave (Outpatient) | medical-claims-policy — 3.4 Medical Certificates (0.642); leave-policy — 5.1 Sick Leave (Outpatient) (0.630); medical-claims-policy — 4.3 Hospital Admission Procedure (0.614) | expected section ranked 2; ranked first: a look-alike section in another policy; refused: best similarity 0.642 is below the threshold 0.69. Note: Medical Claims 3.4 "Medical Certificates" and Leave 5.3 also talk about MCs. |
| g10 | plain | Can I claim physiotherapy, and is there a yearly cap? | medical-claims-policy — 7. Exclusions | medical-claims-policy — 7. Exclusions (0.688); expense-claims-policy — 6. Professional Memberships (0.662); medical-claims-policy — 5. Dental Benefits (0.651) | refused: best similarity 0.688 is below the threshold 0.69. Note: Hidden in the exclusions list, item (d) (RM500 with a doctor's referral). |
| g11 | two-section | I'm a site technician and I worked on a Sunday to finish a job. At what rate is that paid? | overtime-policy — 3. Normal Working Hours; overtime-policy — 5. Overtime Rates | overtime-policy — 5. Overtime Rates (0.686); overtime-policy — 3. Normal Working Hours (0.617); work-from-home-policy — 5.2 Internet and Utilities Allowance (0.598) | refused: best similarity 0.686 is below the threshold 0.69. Note: Needs section 3 (Sunday is the rest day) and section 5 (rest day 2.0 times the hourly rate). |
| g20 | look-alike | Can I claim a parking fine I got while visiting a client's office? | expense-claims-policy — 7. Items That Cannot Be Claimed | expense-claims-policy — 3.2 Tolls and Parking (0.710); expense-claims-policy — 3.3 Taxi and E-hailing (0.651); expense-claims-policy — 7. Items That Cannot Be Claimed (0.649) | expected section ranked 3; ranked first: another section of the same policy. Note: Section 3.2 "Tolls and Parking" sounds right, but fines are excluded in section 7. |
| g22 | amendment | How much allowance do I get if I stay with relatives instead of a hotel on an outstation trip? | travel-policy — 4. Accommodation; travel-policy — 8. Amendment History | travel-policy — 5.1 Outstation Meal Allowance (0.732); travel-policy — 4. Accommodation (0.693); travel-policy — 6.1 Overseas Daily Allowance (0.691) | expected section ranked 2; ranked first: another section of the same policy. Note: Raised from RM50 to RM60 in version 3.0; the old value is only in the amendment history. |
| g23 | look-alike | I'm driving my own car to a project site 400 km away. Is there any limit on what I can claim for mileage? | travel-policy — 3.2 Using Your Own Vehicle for Outstation Travel | expense-claims-policy — 3.1 Mileage for Using Your Own Vehicle (0.779); travel-policy — 3.2 Using Your Own Vehicle for Outstation Travel (0.727); expense-claims-policy — 10. Amendment History (0.674) | expected section ranked 2; ranked first: a look-alike section in another policy. Note: Expense Claims 3.1 has the mileage rates, but the cap for trips over 350 km is in Travel 3.2. |
| g28 | plain | A colleague keeps making sexual jokes about me. Who can I report it to? | code-of-conduct — 5.2 Anti-Harassment | code-of-conduct — 5.2 Anti-Harassment (0.608); code-of-conduct — 5.2 Anti-Harassment (0.581); expense-claims-policy — 4.1 Client Entertainment (0.528) | refused: best similarity 0.608 is below the threshold 0.69. Note: A long section split into two chunks. |
| g29 | plain | Am I allowed to post photos of our project site on Instagram? | code-of-conduct — 7.2 Social Media | code-of-conduct — 7.2 Social Media (0.587); travel-policy — 5.2 Remote Site Allowance (0.518); code-of-conduct — 7.3 Confidential Information (0.516) | refused: best similarity 0.587 is below the threshold 0.69. Note: The words "social media" are not in the question. |
| g30 | two-section | What happens if I'm late three times in a month, and can I appeal against a warning? | code-of-conduct — 5.3 Attendance and Punctuality; code-of-conduct — 9. Disciplinary Action | code-of-conduct — 5.3 Attendance and Punctuality (0.634); code-of-conduct — 9. Disciplinary Action (0.583); travel-policy — 7. Claims After Travel (0.552) | refused: best similarity 0.634 is below the threshold 0.69. Note: Needs 5.3 (a verbal warning) and 9 (appeal in writing within seven days). |
| g38 | plain | Can I use the free Wi-Fi at a coffee shop when I'm working from home? | work-from-home-policy — 8. Information Security | work-from-home-policy — 8. Information Security (0.623); work-from-home-policy — 5.1 Company Equipment (0.601); work-from-home-policy — 1. Purpose (0.590) | refused: best similarity 0.623 is below the threshold 0.69. Note: The answer is "only through the VPN" (8.1). |
| g51 | missing-detail | What is the hotel limit per night for a business trip to Singapore? | (should be refused) | travel-policy — 4. Accommodation (0.754); travel-policy — 8. Amendment History (0.653); travel-policy — 3.1 Air Travel (0.624) | answered: best similarity 0.754 reaches the threshold 0.69. Note: Travel 4 gives hotel limits for Malaysian locations only; there is no overseas hotel limit. |

### PDF, instruction off

| ID | Type | Question | Expected | Retrieved (top 3) | Reason |
|---|---|---|---|---|---|
| g01 | plain | If a public holiday falls in the middle of my week of annual leave, is that day taken from my leave balance? | leave-policy — 4.1 Annual Leave Entitlement | leave-policy — 9. Public Holidays (0.767); leave-policy — 4.3 Carry Forward of Annual Leave (0.742); leave-policy — 4.1 Annual Leave Entitlement (0.729) | expected section ranked 3; ranked first: another section of the same policy. Note: The answer is the last paragraph of 4.1, below the entitlement table. |
| g02 | look-alike | I'm sick today and the doctor gave me an MC. By when must I tell my superior, and when do I upload the MC? | leave-policy — 5.1 Sick Leave (Outpatient) | medical-claims-policy — 3.4 Medical Certificates (0.662); medical-claims-policy — 4.3 Hospital Admission Procedure (0.653); leave-policy — 5.1 Sick Leave (Outpatient) (0.650) | expected section ranked 3; ranked first: a look-alike section in another policy; refused: best similarity 0.662 is below the threshold 0.71. Note: Medical Claims 3.4 "Medical Certificates" and Leave 5.3 also talk about MCs. |
| g11 | two-section | I'm a site technician and I worked on a Sunday to finish a job. At what rate is that paid? | overtime-policy — 3. Normal Working Hours; overtime-policy — 5. Overtime Rates | overtime-policy — 5. Overtime Rates (0.709); overtime-policy — 3. Normal Working Hours (0.632); work-from-home-policy — 5.2 Internet and Utilities Allowance (0.623) | refused: best similarity 0.709 is below the threshold 0.71. Note: Needs section 3 (Sunday is the rest day) and section 5 (rest day 2.0 times the hourly rate). |
| g20 | look-alike | Can I claim a parking fine I got while visiting a client's office? | expense-claims-policy — 7. Items That Cannot Be Claimed | expense-claims-policy — 3.2 Tolls and Parking (0.723); expense-claims-policy — 3.3 Taxi and E-hailing (0.664); expense-claims-policy — 7. Items That Cannot Be Claimed (0.660) | expected section ranked 3; ranked first: another section of the same policy. Note: Section 3.2 "Tolls and Parking" sounds right, but fines are excluded in section 7. |
| g22 | amendment | How much allowance do I get if I stay with relatives instead of a hotel on an outstation trip? | travel-policy — 4. Accommodation; travel-policy — 8. Amendment History | travel-policy — 5.1 Outstation Meal Allowance (0.737); travel-policy — 4. Accommodation (0.719); travel-policy — 6.1 Overseas Daily Allowance (0.698) | expected section ranked 2; ranked first: another section of the same policy. Note: Raised from RM50 to RM60 in version 3.0; the old value is only in the amendment history. |
| g23 | look-alike | I'm driving my own car to a project site 400 km away. Is there any limit on what I can claim for mileage? | travel-policy — 3.2 Using Your Own Vehicle for Outstation Travel | expense-claims-policy — 3.1 Mileage for Using Your Own Vehicle (0.795); travel-policy — 3.2 Using Your Own Vehicle for Outstation Travel (0.735); expense-claims-policy — 10. Amendment History (0.692) | expected section ranked 2; ranked first: a look-alike section in another policy. Note: Expense Claims 3.1 has the mileage rates, but the cap for trips over 350 km is in Travel 3.2. |
| g26 | amendment | When was the ban on facilitation payments added to the Code of Conduct? | code-of-conduct — 10. Amendment History | code-of-conduct — 4.3 Bribery and Facilitation Payments (0.764); code-of-conduct — 10. Amendment History (0.759); code-of-conduct — 4.2 Giving Gifts and Hospitality (0.641) | expected section ranked 2; ranked first: another section of the same policy. Note: Only the amendment history gives the version and date (2.1, 1 September 2024). |
| g28 | plain | A colleague keeps making sexual jokes about me. Who can I report it to? | code-of-conduct — 5.2 Anti-Harassment | code-of-conduct — 5.2 Anti-Harassment (0.636); code-of-conduct — 5.2 Anti-Harassment (0.608); expense-claims-policy — 4.1 Client Entertainment (0.558) | refused: best similarity 0.636 is below the threshold 0.71. Note: A long section split into two chunks. |
| g29 | plain | Am I allowed to post photos of our project site on Instagram? | code-of-conduct — 7.2 Social Media | code-of-conduct — 7.2 Social Media (0.599); travel-policy — 5.2 Remote Site Allowance (0.529); code-of-conduct — 7.3 Confidential Information (0.529) | refused: best similarity 0.599 is below the threshold 0.71. Note: The words "social media" are not in the question. |
| g30 | two-section | What happens if I'm late three times in a month, and can I appeal against a warning? | code-of-conduct — 5.3 Attendance and Punctuality; code-of-conduct — 9. Disciplinary Action | code-of-conduct — 5.3 Attendance and Punctuality (0.672); code-of-conduct — 9. Disciplinary Action (0.606); travel-policy — 7. Claims After Travel (0.593) | refused: best similarity 0.672 is below the threshold 0.71. Note: Needs 5.3 (a verbal warning) and 9 (appeal in writing within seven days). |
| g38 | plain | Can I use the free Wi-Fi at a coffee shop when I'm working from home? | work-from-home-policy — 8. Information Security | work-from-home-policy — 8. Information Security (0.659); work-from-home-policy — 5.1 Company Equipment (0.636); work-from-home-policy — 5.2 Internet and Utilities Allowance (0.605) | refused: best similarity 0.659 is below the threshold 0.71. Note: The answer is "only through the VPN" (8.1). |
| g51 | missing-detail | What is the hotel limit per night for a business trip to Singapore? | (should be refused) | travel-policy — 4. Accommodation (0.768); travel-policy — 8. Amendment History (0.667); travel-policy — 3.1 Air Travel (0.635) | answered: best similarity 0.768 reaches the threshold 0.71. Note: Travel 4 gives hotel limits for Malaysian locations only; there is no overseas hotel limit. |

## Limitations

- The question sets are small, so one question moves a rate by several percentage points.
- The questions were written by the person who built the system, who knows the policies.
  They were committed before any run, and the held-out Training policy is tested separately.
- The policies and questions are fictional sample data in English.
