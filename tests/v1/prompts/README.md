# v1 criterion 1 fixtures

Ten varied ideas (English/Spanish, vague/precise, grammar/free text, supported/unsupported content).
`craftctl interpret-suite` creates a throwaway project per prompt, dispatches the interpreter with the
real provider, validates the proposal against `expect`, and writes `tests/v1/results/<date>.json`.
Pass = every prompt yields a valid spec and asks at most `max_questions`; `unknown_mentions` must
appear in the handoff's unknowns rather than be faked as content.

Expected keys: min_items, min_blocks, recipes_min, drops_min, tab (bool), max_questions,
vanilla_ingredient (an ingredient id that must appear), unknown_mentions (substring expected in unknowns).
