Title: Robustness: UTF-8 logging, improved numeric detection, CLI logging + tests

This PR applies small robustness improvements that don't change the kernel's decision logic:

- Open outcome log in UTF-8 to avoid errors when writing non-ASCII characters (accents).
- Improve numeric detection regex in local_heuristic_analyzer to capture single digits, decimals, and percentages (r"\d+([.,]\d+)?%?").
- Replace prints in the CLI with a minimal logging setup to improve observability.
- Add pytest tests for numeric detection in tests/test_local_heuristic.py.

No behavioral changes in routing logic; these are defensive/maintenance fixes.
