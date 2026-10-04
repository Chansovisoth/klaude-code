# Stockroom benchmark fixture

[stockroom.json](stockroom.json) preserves the exact prompt, six baseline files,
model settings, and independent acceptance script used in both evaluation
passes. Prompt and acceptance SHA-256 values are included. No requirement or
acceptance case has been removed to improve a score.

Materialize a fresh project and its external evaluator from the repository root:

```bash
python3 - <<'PY'
import json
from pathlib import Path

fixture = json.loads(Path('docs/benchmarks/stockroom.json').read_text())
run = Path('/tmp/klaude-stockroom-benchmark')
run.mkdir(exist_ok=False)
for name, contents in fixture['baseline'].items():
    path = run / 'project' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
(run / 'config').mkdir()
(run / 'data').mkdir()
(run / 'config/config.toml').write_text(fixture['config'])
(run / 'task.txt').write_text(fixture['prompt'])
(run / 'acceptance.py').write_text(fixture['acceptance_script'])
(run / 'original_test_stockroom.py').write_text(
    fixture['baseline']['tests/test_stockroom.py']
)
PY
```

From that project, use the repository's real CLI with isolated storage. Replace
the repository path if needed; run each model against a fresh fixture.

```bash
cd /tmp/klaude-stockroom-benchmark/project
KLAUDE_CONFIG_DIR=/tmp/klaude-stockroom-benchmark/config \
KLAUDE_DATA_DIR=/tmp/klaude-stockroom-benchmark/data \
uv run --project /home/klaude/klaude-code --frozen klaude ask \
  "$(cat ../task.txt)" --model qwen3.5:4b
python3 ../acceptance.py "$PWD"
python3 -m unittest discover -s .. -p original_test_stockroom.py -v
```

Use `qwen2.5-coder:3b` for the second model. The benchmark's projects remain
outside Git to avoid Klaude's automatic commits. For an interactive comparison,
launch the documented `klaude chat --model MODEL` alias with the same isolated
environment, rename the session `/rename TEST KLAUDE FEATURES`, and submit the
exact task text.

The thirteen cases include positive success controls. An unsupported importer
can pass rejection cases accidentally; that does **not** establish feature
success. Also run the original two tests against the generated implementation
using the untouched baseline assertions, as the second validation command does.
Even all thirteen passing cases would
still require review of atomic storage/history, unchanged behavior, generated
tests, and README completeness. The evaluator is external feedback and must not
be supplied before the autonomous first attempt.

Observed results and limitations: [small-model evaluation](../small-model-evaluation.md).
