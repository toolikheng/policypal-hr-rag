# Threshold calibration: dev set

Search only (no LLM). For each query-instruction setting, every threshold from 0.50 to 0.85 is tried on the dev set's best-match similarities; the threshold with the best balanced accuracy is chosen (the middle of a tied range). These numbers choose settings; they are not the system's reported quality (see the golden-set reports).

## Configuration

| Setting | Value |
|---|---|
| Date (UTC) | 2026-10-23 15:50 |
| Commit | e84baca |
| Question set | dev (40 questions: 24 answerable, 16 should be refused) |
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
| Refusal accuracy | 87.5% | 87.5% |
| Balanced accuracy | 88.5% | 88.5% |
| Answerable questions answered | 20/24 (83.3%) | 20/24 (83.3%) |
| Should-refuse questions refused | 15/16 (93.8%) | 15/16 (93.8%) |
| Lowest best similarity, answerable | 0.597 | 0.618 |
| Highest best similarity, should refuse | 0.742 | 0.743 |
| Section hit@1 | 19/24 (79.2%) | 18/24 (75.0%) |
| Section hit@3 | 22/24 (91.7%) | 21/24 (87.5%) |
| Section hit@5 | 23/24 (95.8%) | 23/24 (95.8%) |
| Document hit@1 | 23/24 (95.8%) | 23/24 (95.8%) |
| Document hit@3 | 24/24 (100.0%) | 24/24 (100.0%) |
| Document hit@5 | 24/24 (100.0%) | 24/24 (100.0%) |

## Query instruction (decided on the dev set only)

Keep the query instruction on: turning it off is not better on the dev set.

## Sweep: instruction on

| Threshold | Answerable answered | False refusals | Should-refuse refused | False answers | Balanced accuracy |
|---|---|---|---|---|---|
| 0.5 | 24 | 0 | 0 | 16 | 50.0% |
| 0.51 | 24 | 0 | 0 | 16 | 50.0% |
| 0.52 | 24 | 0 | 0 | 16 | 50.0% |
| 0.53 | 24 | 0 | 1 | 15 | 53.1% |
| 0.54 | 24 | 0 | 1 | 15 | 53.1% |
| 0.55 | 24 | 0 | 1 | 15 | 53.1% |
| 0.56 | 24 | 0 | 3 | 13 | 59.4% |
| 0.57 | 24 | 0 | 4 | 12 | 62.5% |
| 0.58 | 24 | 0 | 5 | 11 | 65.6% |
| 0.59 | 24 | 0 | 7 | 9 | 71.9% |
| 0.6 | 23 | 1 | 7 | 9 | 69.8% |
| 0.61 | 22 | 2 | 8 | 8 | 70.8% |
| 0.62 | 22 | 2 | 8 | 8 | 70.8% |
| 0.63 | 22 | 2 | 10 | 6 | 77.1% |
| 0.64 | 22 | 2 | 10 | 6 | 77.1% |
| 0.65 | 21 | 3 | 12 | 4 | 81.2% |
| 0.66 | 20 | 4 | 12 | 4 | 79.2% |
| 0.67 | 20 | 4 | 13 | 3 | 82.3% |
| 0.68 | 20 | 4 | 14 | 2 | 85.4% |
| 0.69 | 20 | 4 | 15 | 1 | 88.5% |
| 0.7 | 18 | 6 | 15 | 1 | 84.4% |
| 0.71 | 17 | 7 | 15 | 1 | 82.3% |
| 0.72 | 14 | 10 | 15 | 1 | 76.0% |
| 0.73 | 12 | 12 | 15 | 1 | 71.9% |
| 0.74 | 9 | 15 | 15 | 1 | 65.6% |
| 0.75 | 8 | 16 | 16 | 0 | 66.7% |
| 0.76 | 6 | 18 | 16 | 0 | 62.5% |
| 0.77 | 6 | 18 | 16 | 0 | 62.5% |
| 0.78 | 5 | 19 | 16 | 0 | 60.4% |
| 0.79 | 4 | 20 | 16 | 0 | 58.3% |
| 0.8 | 3 | 21 | 16 | 0 | 56.2% |
| 0.81 | 2 | 22 | 16 | 0 | 54.2% |
| 0.82 | 0 | 24 | 16 | 0 | 50.0% |
| 0.83 | 0 | 24 | 16 | 0 | 50.0% |
| 0.84 | 0 | 24 | 16 | 0 | 50.0% |
| 0.85 | 0 | 24 | 16 | 0 | 50.0% |

## Sweep: instruction off

| Threshold | Answerable answered | False refusals | Should-refuse refused | False answers | Balanced accuracy |
|---|---|---|---|---|---|
| 0.5 | 24 | 0 | 0 | 16 | 50.0% |
| 0.51 | 24 | 0 | 0 | 16 | 50.0% |
| 0.52 | 24 | 0 | 0 | 16 | 50.0% |
| 0.53 | 24 | 0 | 1 | 15 | 53.1% |
| 0.54 | 24 | 0 | 1 | 15 | 53.1% |
| 0.55 | 24 | 0 | 1 | 15 | 53.1% |
| 0.56 | 24 | 0 | 1 | 15 | 53.1% |
| 0.57 | 24 | 0 | 1 | 15 | 53.1% |
| 0.58 | 24 | 0 | 1 | 15 | 53.1% |
| 0.59 | 24 | 0 | 2 | 14 | 56.2% |
| 0.6 | 24 | 0 | 6 | 10 | 68.8% |
| 0.61 | 24 | 0 | 7 | 9 | 71.9% |
| 0.62 | 23 | 1 | 7 | 9 | 69.8% |
| 0.63 | 23 | 1 | 7 | 9 | 69.8% |
| 0.64 | 22 | 2 | 8 | 8 | 70.8% |
| 0.65 | 22 | 2 | 8 | 8 | 70.8% |
| 0.66 | 21 | 3 | 8 | 8 | 68.8% |
| 0.67 | 21 | 3 | 10 | 6 | 75.0% |
| 0.68 | 20 | 4 | 11 | 5 | 76.0% |
| 0.69 | 20 | 4 | 12 | 4 | 79.2% |
| 0.7 | 20 | 4 | 14 | 2 | 85.4% |
| 0.71 | 20 | 4 | 15 | 1 | 88.5% |
| 0.72 | 19 | 5 | 15 | 1 | 86.5% |
| 0.73 | 16 | 8 | 15 | 1 | 80.2% |
| 0.74 | 13 | 11 | 15 | 1 | 74.0% |
| 0.75 | 10 | 14 | 16 | 0 | 70.8% |
| 0.76 | 7 | 17 | 16 | 0 | 64.6% |
| 0.77 | 6 | 18 | 16 | 0 | 62.5% |
| 0.78 | 6 | 18 | 16 | 0 | 62.5% |
| 0.79 | 6 | 18 | 16 | 0 | 62.5% |
| 0.8 | 3 | 21 | 16 | 0 | 56.2% |
| 0.81 | 2 | 22 | 16 | 0 | 54.2% |
| 0.82 | 2 | 22 | 16 | 0 | 54.2% |
| 0.83 | 0 | 24 | 16 | 0 | 50.0% |
| 0.84 | 0 | 24 | 16 | 0 | 50.0% |
| 0.85 | 0 | 24 | 16 | 0 | 50.0% |

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
| d21 | plain | 0.712 | 0.726 | 1 | 1 |
| d22 | table | 0.734 | 0.740 | 1 | 1 |
| d23 | look-alike | 0.798 | 0.795 | 1 | 1 |
| d24 | amendment | 0.724 | 0.748 | 2 | 2 |
| d25 | amendment | 0.774 | 0.793 | 2 | 2 |
| d26 | plain | 0.656 | 0.655 | 3 | 4 |
| d27 | look-alike | 0.597 | 0.618 | 1 | 1 |
| d28 | table | 0.713 | 0.736 | 1 | 1 |
| d29 | two-section | 0.752 | 0.753 | 1 | 1 |
| d30 | plain | 0.601 | 0.633 | not found | not found |
| d31 | two-section | 0.719 | 0.732 | 4 | 4 |
| d32 | look-alike | 0.741 | 0.758 | 1 | 1 |
| d33 | uncovered-topic | 0.565 | 0.593 | - | - |
| d34 | uncovered-topic | 0.558 | 0.584 | - | - |
| d35 | uncovered-topic | 0.663 | 0.695 | - | - |
| d36 | uncovered-topic | 0.529 | 0.526 | - | - |
| d37 | uncovered-topic | 0.555 | 0.599 | - | - |
| d38 | uncovered-topic | 0.627 | 0.668 | - | - |
| d39 | uncovered-topic | 0.605 | 0.633 | - | - |
| d40 | missing-detail | 0.742 | 0.743 | - | - |
