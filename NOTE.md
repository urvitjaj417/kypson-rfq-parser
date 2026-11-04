# RFQ parser notes

## Approach

`parse.py` is a small rule-based parser using only the Python standard library. It first identifies the product category from specific phrases (for example, jumbo/bulk bag means `fibc`, while shrink/stretch wrap means `film`). It then extracts the order quantity and unit while ignoring numbers introduced by capacity, filling weight, or per-bag wording. Indian formats such as `1,50,000`, `2.5 lac`, `15K`, and `40 hazaar` are converted before the result is returned. GSM, micron/mic, and location are extracted independently so that a missing field becomes `None`. Location extraction uses delivery/location prepositions and the final comma-separated segment rather than a fixed city list.

The returned dictionary contains exactly the six requested keys. Missing quantities default to `0` because the task requires a numeric quantity and does not define a null value for that field.

## Local test result

The supplied PDF did not include Kypson's `score.py`, so I could not calculate the official score. I created 50 labeled examples in `my_tests.jsonl`, including all seven categories, Hinglish, common typos, number formats, missing fields, and capacity/fill-weight traps. The examples were checked by a local comparison script; the official score should be recorded here after running the provided `score.py`:

```text
python score.py my_tests.jsonl
```

## Known limitations

1. A generic product word with no category signal falls back to `film`; a production parser should instead use a review queue for low-confidence cases.
2. A location embedded in unusual prose without a preposition or separator may not be identified reliably.
3. New product spellings and local abbreviations can still be missed because this version intentionally has no external model or API dependency.

With 1,000 real labeled examples, I would measure field-level precision/recall, add error-driven aliases and context rules, and keep a held-out test split so that improvements are not tuned only to the training messages. In production I would monitor missing-field rates, low-confidence samples, corrections by buyers or operators, and changes in category/quantity distributions. Those checks would show whether the parser remains useful after new cities, spellings, and product types appear.

## Tools used

I used Python 3 and its standard library for implementation and local checks, plus an AI coding assistant to help draft test variations. I reviewed the generated code, corrected the parsing rules, and checked the edge cases myself; no API or external data source is used at runtime.
