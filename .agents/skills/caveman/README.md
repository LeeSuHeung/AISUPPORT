# caveman

Talk like smart caveman. Same brain, fewer tokens.

## What it does

Compress every model response to caveman-style prose. Drops articles, filler,
pleasantries, and hedging. Keeps negation, numbers, units, technical details,
code blocks, error strings, and symbols exact. The published benchmark reports
65% fewer output tokens for chat-style prose and 8.5% for agentic coding runs;
input and reasoning tokens are unchanged, so results depend on workload.
AISUPPORT activates full mode at the start of every task; the mode persists
until changed or stopped.

Six intensity levels:

| Level | What change |
|-------|-------------|
| `lite` | Drop filler/hedging. Sentences stay full. Professional but tight. |
| `full` | Default. Drop articles, fragments OK, short synonyms. |
| `ultra` | Bare fragments. Keep standard acronyms; do not invent abbreviations or causal arrows. |
| `wenyan-lite` | Classical Chinese register, light compression. |
| `wenyan-full` | Maximum 文言文. 80-90% character reduction, not token reduction. |
| `wenyan-ultra` | Extreme classical compression. |

Auto-clarity rule: caveman drops to normal prose for security warnings, irreversible-action confirmations, multi-step sequences where fragment ambiguity risks misread, and when user repeats a question. Resumes after the clear part.

## How to control

```
/caveman              # full mode (default)
/caveman lite         # lighter compression
/caveman ultra        # extreme compression
/caveman wenyan-lite  # classical Chinese, light
/caveman wenyan-full  # classical Chinese, full
/caveman wenyan-ultra # classical Chinese, extreme
/caveman off          # back to normal prose
stop caveman          # back to normal prose
```

## Example output

Question: "Why does my React component re-render?"

Normal prose:
> Your component re-renders because you create a new object reference each render. Wrapping it in `useMemo` will fix the issue.

Caveman (full):
> New object ref each render. Inline object prop = new ref = re-render. Wrap in `useMemo`.

Caveman (ultra):
> Inline object prop. New ref. Re-render. `useMemo`.

Persisted content such as code comments, documentation, commits, issues, and
third-party messages uses normal prose rather than caveman fragments.

## See also

- [`SKILL.md`](./SKILL.md) — full LLM-facing instructions
- [Caveman README](../../README.md) — repo overview, install, benchmarks
