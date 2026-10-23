# Retrieval evaluation: held-out set

Search only (no LLM). Hit rate@k: the share of answerable questions with an expected section in the top k results. Refusals: a question is refused when its best match is below the threshold, as in the app.

## Configuration

| Setting | Value |
|---|---|
| Date (UTC) | 2026-10-23 15:36 |
| Commit | 9dc7dbb |
| Question set | held-out (10 questions: 8 answerable, 2 should be refused) |
| Policies | 8 sample policies from Markdown + upload training-and-development-policy (130 chunks); 8 sample policies from PDF + upload training-and-development-policy (130 chunks) |
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
| Section hit@1 | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) |
| Section hit@3 | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) |
| Section hit@5 | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) |
| Document hit@1 | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) |
| Document hit@3 | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) |
| Document hit@5 | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) | 8/8 (100.0%) |
| Both sections in the top 5 (two-section questions) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |
| Threshold | 0.69 | 0.71 | 0.69 | 0.71 |
| Refusal accuracy | 70.0% | 70.0% | 70.0% | 70.0% |
| Balanced accuracy | 43.8% | 43.8% | 43.8% | 43.8% |
| Answerable questions answered | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) | 7/8 (87.5%) |
| Should-refuse questions refused | 0/2 (0.0%) | 0/2 (0.0%) | 0/2 (0.0%) | 0/2 (0.0%) |
| Search time per question (median / mean) | 19 ms / 20 ms | 22 ms / 23 ms | 24 ms / 24 ms | 23 ms / 24 ms |

## Section hit@1 by question type

| Question type | Markdown, instruction on | Markdown, instruction off | PDF, instruction on | PDF, instruction off |
|---|---|---|---|---|
| plain (3) | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) |
| look-alike (3) | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) |
| table (1) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |
| two-section (1) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |

## Section hit@5 by question type

| Question type | Markdown, instruction on | Markdown, instruction off | PDF, instruction on | PDF, instruction off |
|---|---|---|---|---|
| plain (3) | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) |
| look-alike (3) | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) |
| table (1) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |
| two-section (1) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |

## Refusals by question type (should be refused)

| Question type | Markdown, instruction on | Markdown, instruction off | PDF, instruction on | PDF, instruction off |
|---|---|---|---|---|
| missing-detail (2) | 0/2 (0.0%) | 0/2 (0.0%) | 0/2 (0.0%) | 0/2 (0.0%) |

## Error analysis

Every question that was not perfect: the expected section was not ranked first, an answerable question would be refused, or a question that should be refused would be answered. The reason combines what happened with the note written with the question.

### Markdown, instruction on

| ID | Type | Question | Expected | Retrieved (top 3) | Reason |
|---|---|---|---|---|---|
| h04 | plain | The company paid for my course and now I want to resign. Do I have to pay anything back? | training-and-development-policy — 7. Training Bond | training-and-development-policy — 7. Training Bond (0.656); training-and-development-policy — 5. External Course Sponsorship (0.646); leave-policy — 4.4 Encashment of Unused Annual Leave (0.634) | refused: best similarity 0.656 is below the threshold 0.69. Note: Conversational; the word "bond" is not in the question. |
| h09 | missing-detail | What happens to my training bond if my position is made redundant? | (should be refused) | training-and-development-policy — 7. Training Bond (0.742); training-and-development-policy — 3. Training Days (0.646); training-and-development-policy — 8. Mandatory Safety Training for Site Employees (0.640) | answered: best similarity 0.742 reaches the threshold 0.69. Note: Clause 7.3 covers resignation and dismissal for misconduct only; redundancy is not covered. |
| h10 | missing-detail | Who pays for the construction safety induction card? | (should be refused) | training-and-development-policy — 8. Mandatory Safety Training for Site Employees (0.717); training-and-development-policy — 5. External Course Sponsorship (0.630); expense-claims-policy — 6. Professional Memberships (0.614) | answered: best similarity 0.717 reaches the threshold 0.69. Note: Clause 8.1 requires the card but does not say who pays for it. |

### Markdown, instruction off

| ID | Type | Question | Expected | Retrieved (top 3) | Reason |
|---|---|---|---|---|---|
| h04 | plain | The company paid for my course and now I want to resign. Do I have to pay anything back? | training-and-development-policy — 7. Training Bond | training-and-development-policy — 7. Training Bond (0.666); training-and-development-policy — 5. External Course Sponsorship (0.654); leave-policy — 4.4 Encashment of Unused Annual Leave (0.637) | refused: best similarity 0.666 is below the threshold 0.71. Note: Conversational; the word "bond" is not in the question. |
| h09 | missing-detail | What happens to my training bond if my position is made redundant? | (should be refused) | training-and-development-policy — 7. Training Bond (0.760); training-and-development-policy — 3. Training Days (0.673); training-and-development-policy — 8. Mandatory Safety Training for Site Employees (0.661) | answered: best similarity 0.760 reaches the threshold 0.71. Note: Clause 7.3 covers resignation and dismissal for misconduct only; redundancy is not covered. |
| h10 | missing-detail | Who pays for the construction safety induction card? | (should be refused) | training-and-development-policy — 8. Mandatory Safety Training for Site Employees (0.742); training-and-development-policy — 5. External Course Sponsorship (0.660); expense-claims-policy — 6. Professional Memberships (0.659) | answered: best similarity 0.742 reaches the threshold 0.71. Note: Clause 8.1 requires the card but does not say who pays for it. |

### PDF, instruction on

| ID | Type | Question | Expected | Retrieved (top 3) | Reason |
|---|---|---|---|---|---|
| h04 | plain | The company paid for my course and now I want to resign. Do I have to pay anything back? | training-and-development-policy — 7. Training Bond | training-and-development-policy — 7. Training Bond (0.656); training-and-development-policy — 5. External Course Sponsorship (0.644); leave-policy — 4.4 Encashment of Unused Annual Leave (0.634) | refused: best similarity 0.656 is below the threshold 0.69. Note: Conversational; the word "bond" is not in the question. |
| h09 | missing-detail | What happens to my training bond if my position is made redundant? | (should be refused) | training-and-development-policy — 7. Training Bond (0.742); training-and-development-policy — 3. Training Days (0.646); training-and-development-policy — 8. Mandatory Safety Training for Site Employees (0.640) | answered: best similarity 0.742 reaches the threshold 0.69. Note: Clause 7.3 covers resignation and dismissal for misconduct only; redundancy is not covered. |
| h10 | missing-detail | Who pays for the construction safety induction card? | (should be refused) | training-and-development-policy — 8. Mandatory Safety Training for Site Employees (0.717); training-and-development-policy — 5. External Course Sponsorship (0.629); expense-claims-policy — 6. Professional Memberships (0.614) | answered: best similarity 0.717 reaches the threshold 0.69. Note: Clause 8.1 requires the card but does not say who pays for it. |

### PDF, instruction off

| ID | Type | Question | Expected | Retrieved (top 3) | Reason |
|---|---|---|---|---|---|
| h04 | plain | The company paid for my course and now I want to resign. Do I have to pay anything back? | training-and-development-policy — 7. Training Bond | training-and-development-policy — 7. Training Bond (0.666); training-and-development-policy — 5. External Course Sponsorship (0.650); leave-policy — 4.4 Encashment of Unused Annual Leave (0.637) | refused: best similarity 0.666 is below the threshold 0.71. Note: Conversational; the word "bond" is not in the question. |
| h09 | missing-detail | What happens to my training bond if my position is made redundant? | (should be refused) | training-and-development-policy — 7. Training Bond (0.760); training-and-development-policy — 3. Training Days (0.673); training-and-development-policy — 8. Mandatory Safety Training for Site Employees (0.661) | answered: best similarity 0.760 reaches the threshold 0.71. Note: Clause 7.3 covers resignation and dismissal for misconduct only; redundancy is not covered. |
| h10 | missing-detail | Who pays for the construction safety induction card? | (should be refused) | training-and-development-policy — 8. Mandatory Safety Training for Site Employees (0.742); expense-claims-policy — 6. Professional Memberships (0.659); training-and-development-policy — 5. External Course Sponsorship (0.658) | answered: best similarity 0.742 reaches the threshold 0.71. Note: Clause 8.1 requires the card but does not say who pays for it. |

## Limitations

- The question sets are small, so one question moves a rate by several percentage points.
- The questions were written by the person who built the system, who knows the policies.
  They were committed before any run, and the held-out Training policy is tested separately.
- The policies and questions are fictional sample data in English.
