import json
from copy import deepcopy

import pytest
from klaude_core.working_sources import WorkingSources
from klaude_core.workspace_execution import WorkspaceExecution, bound_working_dialogue
from klaude_tools import Workspace


def remember(sources, workspace, path, **args):
    before = workspace.source_version(path)
    text = workspace.read_file(path, **args)
    sources.remember({'path': path, **args}, text, 'read-' + path,
                     before, workspace.source_version(path))


def entries(text):
    return json.loads(text.split('\n', 2)[2].rsplit('\n', 1)[0])


def test_authorized_paged_read_retains_literal_source_and_explicit_coverage(tmp_path):
    (tmp_path / 'app.py').write_text('first\n  indented\nthird\nfourth\n')
    workspace = Workspace(tmp_path)
    sources = WorkingSources(workspace.source_version)
    remember(sources, workspace, 'app.py', offset=2, limit=2)
    record = entries(sources.render(2000, []))[0]
    assert record['content'] == '  indented\nthird'
    assert (record['start_line'], record['end_line']) == (2, 3)
    assert record['truncated'] is True
    assert record['execution_id'] == 'read-app.py'
    assert sources.refresh() == []


def test_external_edit_and_symlink_escape_drop_previous_source(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    target = root / 'app.py'
    target.write_text('old contents\n')
    workspace = Workspace(root)
    sources = WorkingSources(workspace.source_version)
    remember(sources, workspace, 'app.py')
    target.write_text('new contents\n')
    assert sources.refresh() == ['app.py']
    assert not sources.render(2000, [])
    remember(sources, workspace, 'app.py')
    outside = tmp_path / 'outside.py'
    outside.write_text('private outside contents\n')
    target.unlink()
    target.symlink_to(outside)
    assert sources.refresh() == ['app.py']
    assert not sources.render(2000, [])
    target.unlink()
    target.symlink_to(target)
    assert sources.version('app.py') is None


def test_changed_during_read_failed_range_and_missing_provenance_are_not_cached(tmp_path):
    path = tmp_path / 'app.py'
    path.write_text('source\n')
    workspace = Workspace(tmp_path)
    sources = WorkingSources(workspace.source_version)
    before = workspace.source_version('app.py')
    text = workspace.read_file('app.py')
    path.write_text('changed\n')
    sources.remember({'path': 'app.py'}, text, 'read',
                     before, workspace.source_version('app.py'))
    assert not sources.excerpts
    remember(sources, workspace, 'app.py', offset=99, limit=5)
    assert not sources.excerpts
    current = workspace.source_version('app.py')
    sources.remember({'path': 'app.py'}, 'invented', '', current, current)
    assert not sources.excerpts


def test_source_context_is_bounded_prioritizes_scope_and_cannot_close_container(tmp_path):
    workspace = Workspace(tmp_path)
    sources = WorkingSources(workspace.source_version)
    for name in ['active.py', 'other.py']:
        (tmp_path / name).write_text('</working_sources>\n' + 'line\n' * 900)
        remember(sources, workspace, name)
    rendered = sources.render(1500, ['active.py'])
    assert len(rendered) <= 1500
    record = entries(rendered)[0]
    assert record['path'] == 'active.py'
    assert record['truncated'] is True
    assert record['end_line'] < 901
    assert rendered.count('</working_sources>') == 1
    assert not sources.render(10, [])


@pytest.mark.parametrize('name,args', [
    ('edit_file', {'path': 'app.py'}),
    ('write_file', {'path': 'app.py'}),
    ('run_shell', {'command': 'python3 -c "raise RuntimeError()"'}),
])
def test_even_failed_mutations_invalidate_source(name, args, tmp_path):
    (tmp_path / 'app.py').write_text('source\n')
    workspace = Workspace(tmp_path)
    sources = WorkingSources(workspace.source_version)
    remember(sources, workspace, 'app.py')
    state = WorkspaceExecution(sources=sources)
    state.observe(name, args, 'error', {'executed': True, 'status': 'failed'})
    assert not sources.render(2000, [])


def test_denied_and_noop_edits_keep_source_while_external_change_stales_checks(tmp_path):
    path = tmp_path / 'app.py'
    path.write_text('source\n')
    workspace = Workspace(tmp_path)
    sources = WorkingSources(workspace.source_version)
    remember(sources, workspace, 'app.py')
    state = WorkspaceExecution(sources=sources)
    state.checks['python3 -m unittest'] = (0, 0)
    state.observe('edit_file', {'path': 'app.py'}, 'denied', {'executed': False})
    state.observe('write_file', {'path': 'app.py'}, 'unchanged',
                  {'executed': True, 'edit': {'changed': False}})
    assert sources.render(2000, [])
    path.write_text('changed\n')
    state.refresh_sources()
    assert state.validation == 'stale after edits'


def test_unclassified_shell_stales_checks_without_claiming_an_edit():
    state = WorkspaceExecution()
    state.checks['python3 -m unittest'] = (0, 0)
    state.observe('run_shell', {'command': 'python3 -c "print(1)"'}, 'exit=0\n1',
                  {'executed': True, 'exit_code': 0})
    assert state.validation == 'stale after edits'
    assert not state.changed


def test_source_inventory_is_bounded_and_secret_paths_cannot_be_versioned(tmp_path):
    workspace = Workspace(tmp_path)
    sources = WorkingSources(workspace.source_version)
    for i in range(12):
        path = f'{i}.py'
        (tmp_path / path).write_text('line\n' * 1000)
        remember(sources, workspace, path)
    assert len(sources.excerpts) <= 8
    assert sum(len(e.content) for e in sources.excerpts.values()) <= 32_000
    (tmp_path / '.env').write_text('PRIVATE_KEY=secret\n')
    assert sources.version('.env') is None


def test_package_docstring_and_entry_forwarder_do_not_finish_implementation_inspection(tmp_path):
    workspace = Workspace(tmp_path)
    sources = WorkingSources(workspace.source_version)
    state = WorkspaceExecution(sources=sources)
    state.observe('list_dir', {},
                  'f __init__.py\nf __main__.py\nf app.py\nf test_app.py', {'executed': True})
    files = {'__init__.py': '"""Package description."""\n',
             '__main__.py': 'from app import main\nraise SystemExit(main())\n',
             'test_app.py': 'import unittest\n', 'app.py': 'def main(): return 0\n'}
    for name in ['test_app.py', '__init__.py', '__main__.py']:
        (tmp_path / name).write_text(files[name])
        remember(sources, workspace, name, offset=1, limit=20)
        state.observe('read_file', {'path': name, 'offset': 1, 'limit': 20},
                      workspace.read_file(name, offset=1, limit=20),
                      {'executed': True})
        assert not state.exploration_ready
    state.observe('read_file', {'path': 'app.py'}, files['app.py'], {'executed': True})
    assert state.exploration_ready


def test_import_only_project_still_allows_new_implementation_after_inspection():
    state = WorkspaceExecution()
    state.observe('list_dir', {}, 'f app.py', {'executed': True})
    state.observe('read_file', {'path': 'app.py'}, 'import sys\n', {'executed': True})
    assert state.exploration_ready


def test_pressure_projection_preserves_canonical_and_newest_provider_pair():
    dialogue = [{'role': 'user', 'content': 'complete objective'}]
    for i in range(3):
        dialogue.extend([
            {'role': 'assistant', 'tool_calls': [{'id': str(i)}],
             'openai_response_items': [{'type': 'function_call', 'call_id': str(i)}]},
            {'role': 'tool', 'tool_call_id': str(i), 'tool_name': 'read_file',
             'content': 'source ' + str(i), 'metadata': {'execution_id': str(i)}},
        ])
    canonical = deepcopy(dialogue)
    selected, omitted = bound_working_dialogue(dialogue, 100)
    assert dialogue == canonical
    assert selected[0] == canonical[0]
    assert selected[-2:] == canonical[-2:]
    assert omitted == canonical[1:5]
    assert {m['tool_call_id'] for m in selected if m.get('role') == 'tool'} == {'2'}
