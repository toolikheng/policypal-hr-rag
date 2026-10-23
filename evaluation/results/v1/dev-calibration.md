# Threshold calibration: dev set

Search only (no LLM). For each query-instruction setting, every threshold from 0.50 to 0.85 is tried on the dev set's best-match similarities; the threshold with the best balanced accuracy is chosen (the middle of a tied range). These numbers choose settings; they are not the system's reported quality (see the golden-set reports).

## Configuration

| Setting | Value |
|---|---|
| Date (UTC) | 2026-10-23 15:22 |
| Commit | bebd8b0 |
| Question set | dev (20 questions: 12 answerable, 8 should be refused) |
| Policies | 8 sample policies from Markdown (119 chunks) |
| Embedding model | BAAI/bge-small-en-v1.5 |
| Query instruction | on and off (both measured) |
| Top k | 5 |
| Threshold | chosen here, one for each instruction setting |
| LLM | none (search only) |
| CPU | Intel(R) Core(TM) i5-10300H CPU @ 2.50GHz (8 logical CPUs) |
| RAM | 11.6 GiB visible |
| Operating system | Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.41 |
| Python | 3.12.14 |
| Docker | Docker Desktop 4.86.0 (236216), engine 29.7.2 |

## Chosen thresholds

| | Instruction on | Instruction off |
|---|---|---|
| Chosen threshold | 0.69 | 0.71 |
| Refusal accuracy | 95.0% | 95.0% |
| Balanced accuracy | 95.8% | 95.8% |
| Answerable questions answered | 11/12 (91.7%) | 11/12 (91.7%) |
| Should-refuse questions refused | 8/8 (100.0%) | 8/8 (100.0%) |
| Lowest best similarity, answerable | 0.649 | 0.676 |
| Highest best similarity, should refuse | 0.689 | 0.706 |
| Section hit@1 | 12/12 (100.0%) | 11/12 (91.7%) |
| Section hit@3 | 12/12 (100.0%) | 12/12 (100.0%) |
| Section hit@5 | 12/12 (100.0%) | 12/12 (100.0%) |
| Document hit@1 | 12/12 (100.0%) | 12/12 (100.0%) |
| Document hit@3 | 12/12 (100.0%) | 12/12 (100.0%) |
| Document hit@5 | 12/12 (100.0%) | 12/12 (100.0%) |

## Query instruction (decided on the dev set only)

Keep the query instruction on: turning it off is not better on the dev set.

## Sweep: instruction on

| Threshold | Answerable answered | False refusals | Should-refuse refused | False answers | Balanced accuracy |
|---|---|---|---|---|---|
| 0.5 | 12 | 0 | 0 | 8 | 50.0% |
| 0.51 | 12 | 0 | 0 | 8 | 50.0% |
| 0.52 | 12 | 0 | 0 | 8 | 50.0% |
| 0.53 | 12 | 0 | 0 | 8 | 50.0% |
| 0.54 | 12 | 0 | 0 | 8 | 50.0% |
| 0.55 | 12 | 0 | 0 | 8 | 50.0% |
| 0.56 | 12 | 0 | 0 | 8 | 50.0% |
| 0.57 | 12 | 0 | 0 | 8 | 50.0% |
| 0.58 | 12 | 0 | 1 | 7 | 56.2% |
| 0.59 | 12 | 0 | 3 | 5 | 68.8% |
| 0.6 | 12 | 0 | 3 | 5 | 68.8% |
| 0.61 | 12 | 0 | 3 | 5 | 68.8% |
| 0.62 | 12 | 0 | 3 | 5 | 68.8% |
| 0.63 | 12 | 0 | 4 | 4 | 75.0% |
| 0.64 | 12 | 0 | 4 | 4 | 75.0% |
| 0.65 | 11 | 1 | 6 | 2 | 83.3% |
| 0.66 | 11 | 1 | 6 | 2 | 83.3% |
| 0.67 | 11 | 1 | 6 | 2 | 83.3% |
| 0.68 | 11 | 1 | 7 | 1 | 89.6% |
| 0.69 | 11 | 1 | 8 | 0 | 95.8% |
| 0.7 | 9 | 3 | 8 | 0 | 87.5% |
| 0.71 | 8 | 4 | 8 | 0 | 83.3% |
| 0.72 | 8 | 4 | 8 | 0 | 83.3% |
| 0.73 | 7 | 5 | 8 | 0 | 79.2% |
| 0.74 | 5 | 7 | 8 | 0 | 70.8% |
| 0.75 | 5 | 7 | 8 | 0 | 70.8% |
| 0.76 | 4 | 8 | 8 | 0 | 66.7% |
| 0.77 | 4 | 8 | 8 | 0 | 66.7% |
| 0.78 | 4 | 8 | 8 | 0 | 66.7% |
| 0.79 | 3 | 9 | 8 | 0 | 62.5% |
| 0.8 | 3 | 9 | 8 | 0 | 62.5% |
| 0.81 | 2 | 10 | 8 | 0 | 58.3% |
| 0.82 | 0 | 12 | 8 | 0 | 50.0% |
| 0.83 | 0 | 12 | 8 | 0 | 50.0% |
| 0.84 | 0 | 12 | 8 | 0 | 50.0% |
| 0.85 | 0 | 12 | 8 | 0 | 50.0% |

## Sweep: instruction off

| Threshold | Answerable answered | False refusals | Should-refuse refused | False answers | Balanced accuracy |
|---|---|---|---|---|---|
| 0.5 | 12 | 0 | 0 | 8 | 50.0% |
| 0.51 | 12 | 0 | 0 | 8 | 50.0% |
| 0.52 | 12 | 0 | 0 | 8 | 50.0% |
| 0.53 | 12 | 0 | 0 | 8 | 50.0% |
| 0.54 | 12 | 0 | 0 | 8 | 50.0% |
| 0.55 | 12 | 0 | 0 | 8 | 50.0% |
| 0.56 | 12 | 0 | 0 | 8 | 50.0% |
| 0.57 | 12 | 0 | 0 | 8 | 50.0% |
| 0.58 | 12 | 0 | 0 | 8 | 50.0% |
| 0.59 | 12 | 0 | 0 | 8 | 50.0% |
| 0.6 | 12 | 0 | 2 | 6 | 62.5% |
| 0.61 | 12 | 0 | 3 | 5 | 68.8% |
| 0.62 | 12 | 0 | 3 | 5 | 68.8% |
| 0.63 | 12 | 0 | 3 | 5 | 68.8% |
| 0.64 | 12 | 0 | 3 | 5 | 68.8% |
| 0.65 | 12 | 0 | 3 | 5 | 68.8% |
| 0.66 | 12 | 0 | 3 | 5 | 68.8% |
| 0.67 | 12 | 0 | 4 | 4 | 75.0% |
| 0.68 | 11 | 1 | 5 | 3 | 77.1% |
| 0.69 | 11 | 1 | 6 | 2 | 83.3% |
| 0.7 | 11 | 1 | 7 | 1 | 89.6% |
| 0.71 | 11 | 1 | 8 | 0 | 95.8% |
| 0.72 | 10 | 2 | 8 | 0 | 91.7% |
| 0.73 | 8 | 4 | 8 | 0 | 83.3% |
| 0.74 | 8 | 4 | 8 | 0 | 83.3% |
| 0.75 | 6 | 6 | 8 | 0 | 75.0% |
| 0.76 | 5 | 7 | 8 | 0 | 70.8% |
| 0.77 | 4 | 8 | 8 | 0 | 66.7% |
| 0.78 | 4 | 8 | 8 | 0 | 66.7% |
| 0.79 | 4 | 8 | 8 | 0 | 66.7% |
| 0.8 | 3 | 9 | 8 | 0 | 62.5% |
| 0.81 | 2 | 10 | 8 | 0 | 58.3% |
| 0.82 | 2 | 10 | 8 | 0 | 58.3% |
| 0.83 | 0 | 12 | 8 | 0 | 50.0% |
| 0.84 | 0 | 12 | 8 | 0 | 50.0% |
| 0.85 | 0 | 12 | 8 | 0 | 50.0% |

## Each question

| ID | Type | Best similarity (on) | Best similarity (off) | Expected section rank (on) | Expected section rank (off) |
|---|---|---|---|---|---|
| d01 | plain | 0.817 | 0.821 | 1 | 1 |
| d02 | table | 0.724 | 0.741 | 1 | 1 |
| d03 | look-alike | 0.808 | 0.799 | 1 | 1 |
| d04 | plain | 0.697 | 0.720 | 1 | 1 |
| d05 | amendment | 0.785 | 0.807 | 1 | 1 |
| d06 | look-alike | 0.739 | 0.748 | 1 | 1 |
| d07 | plain | 0.737 | 0.761 | 1 | 1 |
| d08 | table | 0.810 | 0.823 | 1 | 1 |
| d09 | two-section | 0.708 | 0.723 | 1 | 1 |
| d10 | look-alike | 0.649 | 0.676 | 1 | 1 |
| d11 | amendment | 0.699 | 0.723 | 1 | 1 |
| d12 | two-section | 0.753 | 0.760 | 1 | 2 |
| d13 | uncovered-topic | 0.575 | 0.610 | - | - |
| d14 | uncovered-topic | 0.625 | 0.661 | - | - |
| d15 | uncovered-topic | 0.581 | 0.590 | - | - |
| d16 | uncovered-topic | 0.645 | 0.679 | - | - |
| d17 | uncovered-topic | 0.649 | 0.693 | - | - |
| d18 | uncovered-topic | 0.674 | 0.688 | - | - |
| d19 | uncovered-topic | 0.585 | 0.590 | - | - |
| d20 | missing-detail | 0.689 | 0.706 | - | - |
