"""The example instances as a tree, and editing them."""

import json
import os
import shutil

import pytest

from semforge.cooked.examples import build_examples, flatten, set_value
from semforge.errors import PackageError
from semforge.package import load
from semforge.validate import validate_package


@pytest.fixture
def package(tmp_path, corpus):
    target = tmp_path / 'pkg'
    target.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], target / name)
    for extra in ('context.jsonld', 'semforge.yaml'):
        shutil.copy(f'{corpus.path}/{extra}', target / extra)
    return load(str(target))


def _cases(roots):
    """Every example node, whether it sits in a suite or loose."""
    return [n for _, n in flatten(roots) if n.kind == 'example']


def _find(nodes, label, kind=None):
    return next(n for _, n in flatten(nodes)
                if n.label == label and (kind is None or n.kind == kind))


# --- the tree ----------------------------------------------------------------

def test_every_entity_appears(corpus):
    tree = build_examples(corpus)
    entities = {n.label for _, n in flatten(tree) if n.kind == 'entity'}
    assert {'urn:filter:1', 'urn:plasmacutter:1', 'urn:cartridge:1'} <= entities


def test_an_entity_shows_its_type(corpus):
    node = _find(build_examples(corpus), 'urn:filter:1', 'entity')
    assert 'Filter' in node.detail


def test_attributes_hang_under_their_entity(corpus):
    node = _find(build_examples(corpus), 'urn:filter:1', 'entity')
    assert {c.label for c in node.children} >= {'hasStrength', 'hasCartridge'}


def test_a_single_instance_is_folded_into_its_attribute(corpus):
    """Showing one instance as a child of itself doubles the depth for nothing."""
    node = _find(build_examples(corpus), 'urn:filter:2', 'entity')
    state = next(c for c in node.children if c.label == 'hasState')
    assert state.children == []
    assert state.editable and state.value


def test_an_instance_with_sub_attributes_is_not_folded(corpus):
    """plasmacutter:1's hasState carries hasXXXWorkpiece, which must stay reachable."""
    node = _find(build_examples(corpus), 'urn:plasmacutter:1', 'entity')
    state = next(c for c in node.children if c.label == 'hasState')
    assert state.children
    nested = [c for c in state.children[0].children if c.kind == 'attribute']
    assert any(c.label == 'hasXXXWorkpiece' for c in nested)


def test_a_repeated_attribute_keeps_its_observations(corpus):
    """urn:filter:1 carries four hasStrength observations."""
    node = _find(build_examples(corpus), 'urn:filter:1', 'entity')
    strength = next(c for c in node.children if c.label == 'hasStrength')
    assert len(strength.children) == 4
    assert '4 observations' in strength.detail


def test_the_timestamp_is_on_the_row_not_a_child(corpus):
    """Inside a series the observedAt IS the row's identity.

    Repeating it as a child is one more level to expand for something already
    on the line.
    """
    node = _find(build_examples(corpus), 'urn:filter:1', 'entity')
    strength = next(c for c in node.children if c.label == 'hasStrength')
    assert all('2024-02-28T13:52' in c.detail for c in strength.children)
    assert not [m for c in strength.children for m in c.children
                if m.kind == 'meta' and m.label == 'observedAt']


def test_metadata_outside_a_series_is_still_a_child(corpus):
    """A lone instance's observedAt has no row of its own to sit on."""
    node = _find(build_examples(corpus), 'urn:cartridge:1', 'entity')
    used = next(c for c in node.children if c.label == 'isUsedFrom')
    assert used.value


def test_a_violating_entity_is_marked_and_carries_the_message(corpus):
    """A minCount violation is about an attribute that is NOT there, so there
    is no attribute node to hang it on -- the entity carries it or it is lost."""
    tree = build_examples(corpus, validate_package(corpus))
    node = _find(tree, 'urn:cutter:1', 'entity')
    assert node.severity == 'violation'
    assert 'violation(s)' in node.detail
    assert node.messages and any('Count' in m for m in node.messages)


def test_a_clean_entity_is_not_marked(corpus):
    tree = build_examples(corpus, validate_package(corpus))
    node = _find(tree, 'urn:plasmacutter:1', 'entity')
    assert node.severity == ''


def test_without_a_report_nothing_is_marked(corpus):
    assert all(n.severity == '' for _, n in flatten(build_examples(corpus)))


def test_a_relationship_target_is_readable(corpus):
    node = _find(build_examples(corpus), 'urn:filter:2', 'entity')
    rel = next(c for c in node.children if c.label == 'hasCartridge')
    assert 'urn:cartridge:2' in rel.value


def test_an_iri_value_is_shown_as_the_iri_not_the_wrapper(corpus):
    """`{"@id": "base:state_ON"}` reads as base:state_ON."""
    node = _find(build_examples(corpus), 'urn:filter:2', 'entity')
    state = next(c for c in node.children if c.label == 'hasState')
    assert state.value == 'base:state_ON'


def test_the_instance_validation_reads_is_marked(corpus):
    """Attributes resolve to the latest observedAt before validation.

    Editing a superseded observation changes the file and nothing else, which
    without a marker reads as the editor being broken.
    """
    node = _find(build_examples(corpus), 'urn:filter:1', 'entity')
    strength = next(c for c in node.children if c.label == 'hasStrength')
    marks = [c.detail.split(' · ')[-1] for c in strength.children]
    assert marks.count('current') == 1
    assert marks.count('superseded') == 3
    assert marks[-1] == 'current', 'the latest observedAt is the current one'


# --- editing -----------------------------------------------------------------

def test_editing_a_value_produces_a_minimal_diff(package):
    with open(package.sources['model']) as handle:
        before = handle.read()

    path, old, new = set_value(
        package, 'urn:filter:1',
        ['iffBaseEntities:hasStrength', 0, 'value'], '0.95')

    with open(path) as handle:
        after = handle.read()
    assert (old, new) == ('0.9', '0.95')

    changed = [line for line in after.splitlines()
               if line not in before.splitlines()]
    assert len(changed) == 1, f'expected one changed line, got {changed}'


def test_a_value_is_parsed_as_json_when_it_can_be(package):
    """Typing 42 should give a number, not the string "42".

    A Property whose value arrives as a string where a number was meant is the
    difference between a range constraint passing and failing.
    """
    set_value(package, 'urn:filter:1',
              ['iffBaseEntities:hasStrength', 0, 'value'], '42')
    with open(package.sources['model']) as handle:
        document = json.load(handle)
    entity = next(e for e in document if e['id'] == 'urn:filter:1')
    assert entity['iffBaseEntities:hasStrength'][0]['value'] == 42


def test_an_iri_value_can_be_written_as_a_node_reference(package):
    set_value(package, 'urn:filter:1',
              ['iffBaseEntities:hasState', 0, 'value'],
              '{"@id": "base:state_OFF"}')
    with open(package.sources['model']) as handle:
        document = json.load(handle)
    entity = next(e for e in document if e['id'] == 'urn:filter:1')
    assert entity['iffBaseEntities:hasState'][0]['value'] == \
        {'@id': 'base:state_OFF'}


def test_a_plain_string_stays_a_string(package):
    set_value(package, 'urn:cartridge:1',
              ['iffBaseEntities:isUsedFrom', 0, 'value'], 'not-json')
    with open(package.sources['model']) as handle:
        document = json.load(handle)
    entity = next(e for e in document if e['id'] == 'urn:cartridge:1')
    assert entity['iffBaseEntities:isUsedFrom'][0]['value'] == 'not-json'


def test_the_edit_moves_the_verdict(package):
    """The reason to edit data here rather than in the JSON."""
    before = validate_package(load(package.path))
    assert not [r for r in before.violations if r.attribute == 'hasStrength']

    # Index 3 is the CURRENT observation; editing an older one would change
    # the file and leave the verdict alone, which is the point of the marker.
    set_value(package, 'urn:filter:1',
              ['iffBaseEntities:hasStrength', 3, 'value'], '999')

    after = validate_package(load(package.path))
    fired = [r for r in after.violations if r.attribute == 'hasStrength']
    assert fired, 'a strength above the maximum should now violate'


def test_editing_a_superseded_observation_leaves_the_verdict_alone(package):
    """Not a bug: the current view resolves to the latest observedAt."""
    set_value(package, 'urn:filter:1',
              ['iffBaseEntities:hasStrength', 0, 'value'], '999')
    after = validate_package(load(package.path))
    assert not [r for r in after.violations if r.attribute == 'hasStrength']


def test_an_unknown_entity_is_named_in_the_error(package):
    with pytest.raises(PackageError) as exc:
        set_value(package, 'urn:nope:1', ['x', 0, 'value'], '1')
    assert 'urn:nope:1' in str(exc.value)


def test_an_unknown_path_is_refused(package):
    with pytest.raises((PackageError, KeyError, IndexError)):
        set_value(package, 'urn:filter:1',
                  ['iffBaseEntities:nothingHere', 0, 'value'], '1')


def test_the_file_still_parses_after_an_edit(package):
    set_value(package, 'urn:filter:1',
              ['iffBaseEntities:hasStrength', 0, 'value'], '0.5')
    with open(package.sources['model']) as handle:
        json.load(handle)
    assert load(package.path).model


# --- per datasetId -----------------------------------------------------------

def test_one_dataset_shows_the_series_under_the_attribute(corpus):
    """No dataset row when there is only one: it would be depth for nothing."""
    node = _find(build_examples(corpus), 'urn:filter:1', 'entity')
    strength = next(c for c in node.children if c.label == 'hasStrength')
    assert strength.dataset_id == '@none'
    assert strength.observations == 4 and strength.is_series
    assert all(c.kind == 'instance' for c in strength.children)
    assert strength.value == '0.6', 'the row shows what validation reads'


def test_several_datasets_get_a_row_each(package):
    """Different datasetIds are different attributes sharing a name.

    The dedup resolves within a datasetId and never across, so listing them
    flat would conflate two things that behave differently.
    """
    from semforge.cooked.examples import add_observation

    add_observation(package, 'urn:filter:1', ['iffBaseEntities:hasStrength'],
                    'urn:sensor:B', '1.0', '2024-02-28T14:00:00.000Z')
    add_observation(load(package.path), 'urn:filter:1',
                    ['iffBaseEntities:hasStrength'], 'urn:sensor:B', '1.5',
                    '2024-02-28T14:01:00.000Z')

    node = _find(build_examples(load(package.path)), 'urn:filter:1', 'entity')
    strength = next(c for c in node.children if c.label == 'hasStrength')
    assert '2 datasets' in strength.detail
    datasets = {c.dataset_id: c for c in strength.children}
    assert set(datasets) == {'@none', 'urn:sensor:B'}
    assert datasets['@none'].value == '0.6'
    assert datasets['urn:sensor:B'].value == '1.5'
    assert datasets['urn:sensor:B'].observations == 2


def test_each_dataset_resolves_its_own_current(package):
    """The latest observedAt WITHIN a datasetId, not across all of them."""
    from semforge.cooked.examples import add_observation

    # Newer than everything in @none, but a different dataset.
    add_observation(package, 'urn:filter:1', ['iffBaseEntities:hasStrength'],
                    'urn:sensor:B', '1.0', '2025-01-01T00:00:00.000Z')

    node = _find(build_examples(load(package.path)), 'urn:filter:1', 'entity')
    strength = next(c for c in node.children if c.label == 'hasStrength')
    datasets = {c.dataset_id: c for c in strength.children}
    assert datasets['@none'].value == '0.6', \
        'a newer observation in another dataset must not supersede this one'


def test_the_current_index_addresses_the_whole_attribute(package):
    """It is an edit path into the JSON array, not a position within a group.

    The two coincide only when there is a single datasetId, which is what made
    the first version crash on the second dataset.
    """
    from semforge.cooked.examples import add_observation

    add_observation(package, 'urn:filter:1', ['iffBaseEntities:hasStrength'],
                    'urn:sensor:B', '1.0', '2024-02-28T14:00:00.000Z')
    node = _find(build_examples(load(package.path)), 'urn:filter:1', 'entity')
    strength = next(c for c in node.children if c.label == 'hasStrength')
    sensor = next(c for c in strength.children
                  if c.dataset_id == 'urn:sensor:B')
    assert sensor.path[-2] == 4, 'index 4 is where it sits in the array'


# --- adding observations -----------------------------------------------------

def test_an_observation_joins_its_own_series(package):
    from semforge.cooked.examples import add_observation

    _, count = add_observation(
        package, 'urn:filter:1', ['iffBaseEntities:hasStrength'], '@none',
        '0.55', '2024-02-28T13:52:36.000Z')
    assert count == 5

    node = _find(build_examples(load(package.path)), 'urn:filter:1', 'entity')
    strength = next(c for c in node.children if c.label == 'hasStrength')
    assert strength.value == '0.55', 'the newest observation becomes current'


def test_a_new_dataset_id_starts_its_own_series(package):
    from semforge.cooked.examples import add_observation

    add_observation(package, 'urn:filter:1', ['iffBaseEntities:hasStrength'],
                    'urn:sensor:B', '1.0', '2024-02-28T14:00:00.000Z')
    with open(package.sources['model']) as handle:
        document = json.load(handle)
    entity = next(e for e in document if e['id'] == 'urn:filter:1')
    added = entity['iffBaseEntities:hasStrength'][-1]
    assert added['datasetId'] == 'urn:sensor:B'
    assert added['value'] == 1.0


def test_the_default_dataset_is_not_written_out(package):
    """`@none` IS the default instance; writing it would be a different thing."""
    from semforge.cooked.examples import add_observation

    add_observation(package, 'urn:filter:1', ['iffBaseEntities:hasStrength'],
                    '@none', '0.55', '2024-02-28T13:52:36.000Z')
    with open(package.sources['model']) as handle:
        document = json.load(handle)
    entity = next(e for e in document if e['id'] == 'urn:filter:1')
    assert 'datasetId' not in entity['iffBaseEntities:hasStrength'][-1]


def test_the_type_is_carried_over(package):
    """A Property whose new instance is a Relationship is a different attribute."""
    from semforge.cooked.examples import add_observation

    add_observation(package, 'urn:filter:1', ['iffBaseEntities:hasStrength'],
                    '@none', '0.55', '2024-02-28T13:52:36.000Z')
    with open(package.sources['model']) as handle:
        document = json.load(handle)
    entity = next(e for e in document if e['id'] == 'urn:filter:1')
    assert entity['iffBaseEntities:hasStrength'][-1]['type'] == 'Property'


def test_adding_to_a_single_valued_attribute_makes_it_a_series(package):
    from semforge.cooked.examples import add_observation

    _, count = add_observation(
        package, 'urn:filter:2', ['iffBaseEntities:hasStrength'], '@none',
        '0.7', '2024-03-01T00:00:00.000Z')
    assert count == 2
    node = _find(build_examples(load(package.path)), 'urn:filter:2', 'entity')
    strength = next(c for c in node.children if c.label == 'hasStrength')
    assert strength.is_series and strength.value == '0.7'


def test_adding_to_an_unknown_attribute_is_refused(package):
    from semforge.cooked.examples import add_observation

    with pytest.raises(PackageError) as exc:
        add_observation(package, 'urn:filter:1', ['iffBaseEntities:nope'],
                        '@none', '1', None)
    assert 'nope' in str(exc.value)


def test_a_new_observation_can_move_the_verdict(package):
    from semforge.cooked.examples import add_observation

    add_observation(package, 'urn:filter:1', ['iffBaseEntities:hasStrength'],
                    '@none', '999', '2030-01-01T00:00:00.000Z')
    after = validate_package(load(package.path))
    assert [r for r in after.violations if r.attribute == 'hasStrength']


# --- the declared suite ------------------------------------------------------

def test_the_tree_has_two_sections(corpus):
    """Tests and Main are judged by different rules, so they are separate.

    A case declares what it is for and passes or fails; the main model declares
    nothing and cannot fail -- it is where a violation is tried on purpose.
    """
    from semforge.cooked.examples import build_suite

    sections = build_suite(corpus)
    assert [n.label for n in sections] == ['Tests', 'Main']
    assert all(n.kind == 'group' for n in sections)

    tests, main = sections
    assert '6 case(s)' in tests.detail and 'all ok' in tests.detail
    assert 'not failures' in main.detail
    assert {n.kind for n in main.children} == {'example'}


def test_cases_are_grouped_by_suite(corpus):
    from semforge.cooked.examples import build_suite

    tests = build_suite(corpus)[0]
    suites = {n.label: n for n in tests.children}
    assert {'test_StateOnCutterShape', 'test_WorkpieceShape',
            'test_FilterShape', 'test_CartridgeShape'} <= set(suites)
    assert suites['test_StateOnCutterShape'].kind == 'suite'
    assert '2 case(s)' in suites['test_StateOnCutterShape'].detail
    assert {c.label for c in suites['test_StateOnCutterShape'].children} == \
        {'filter-on.jsonld', 'filter-off.jsonld'}


def test_the_shipped_model_is_under_main(corpus):
    from semforge.cooked.examples import build_suite

    main = build_suite(corpus)[1]
    documents = {n.label: n for n in main.children}
    assert 'model-instance.jsonld' in documents
    assert 'the model as shipped' in documents['model-instance.jsonld'].detail


def test_a_root_says_what_the_example_is_for_and_how_it_did(corpus):
    from semforge.cooked.examples import build_suite

    roots = {n.label: n for n in _cases(build_suite(corpus))}
    good = roots['filter-on.jsonld']
    assert 'good' in good.detail and 'valid' in good.detail
    assert 'ok' in good.detail and good.severity == ''
    assert good.messages and 'healthy baseline' in good.messages[0]


def test_a_bad_example_that_fires_is_ok_not_a_failure(corpus):
    """`bad` means "expected to violate"; violating is the pass condition."""
    from semforge.cooked.examples import build_suite

    roots = {n.label: n for n in _cases(build_suite(corpus))}
    bad = roots['filter-off.jsonld']
    assert bad.severity == '' and 'ok' in bad.detail
    entity = next(c for c in bad.children if c.kind == 'entity')
    assert entity.severity == 'violation'


def test_included_subobjects_are_editable_and_say_what_they_reach(corpus):
    """A subobject is an ordinary JSON-LD file.

    Refusing to edit it was a restriction the format does not have, and it read
    as the tree being broken. What is true is that an edit reaches every case
    that includes the file, so each row carries that list and the command asks
    before writing.
    """
    from semforge.cooked.examples import build_suite, flatten

    roots = {n.label: n for n in _cases(build_suite(corpus))}
    node = roots['filter-on.jsonld']
    includes = [c for c in node.children if c.kind == 'include']
    assert {c.label for c in includes} == {
        'workpiece-steel.jsonld', 'cartridge-fresh.jsonld', 'filter-on.jsonld'}

    rows = [n for include in includes for _, n in flatten([include])
            if n.kind == 'attribute']
    assert rows
    assert any(n.editable for n in rows), 'included rows are still locked'

    workpiece = next(c for c in includes if c.label == 'workpiece-steel.jsonld')
    assert len(workpiece.shared_by) == 3, workpiece.shared_by
    assert 'shared by 3 cases' in workpiece.detail
    assert all(len(n.shared_by) == 3
               for _, n in flatten([workpiece]) if n.kind == 'attribute')

    # A file only one case includes needs no warning.
    only = next(c for c in includes if c.label == 'filter-on.jsonld')
    assert len(only.shared_by) == 1


def test_editing_an_included_entity_writes_to_its_own_file(corpus, tmp_path):
    """The edit lands in the subobject, not in the case that includes it."""
    import shutil

    from semforge.cooked.examples import build_suite, flatten, set_value
    from semforge.package import load

    target = tmp_path / 'pkg'
    shutil.copytree(corpus.path, target, symlinks=False)
    package = load(str(target))

    row = next(n for _, n in flatten(build_suite(package))
               if n.kind == 'attribute' and n.entity == 'urn:workpiece:1'
               and n.label == 'hasHeight' and n.shared_by and n.editable)
    path, old, new = set_value(package, row.entity, row.path, '0.42',
                               file=row.file)
    assert path.endswith('workpiece-steel.jsonld')
    assert new == '0.42' and old != new
    assert '0.42' in open(path, encoding='utf-8').read()


def test_the_examples_own_entities_stay_editable(corpus):
    from semforge.cooked.examples import build_suite

    roots = {n.label: n for n in _cases(build_suite(corpus))}
    node = roots['too-high.jsonld']
    entity = next(c for c in node.children if c.kind == 'entity')
    assert any(c.editable for c in entity.children)


def test_a_broken_example_is_reported_not_raised(tmp_path, corpus):
    import shutil

    target = tmp_path / 'pkg'
    shutil.copytree(corpus.path, target, symlinks=False)
    for stale in (target / 'examples').glob('test_*'):
        shutil.rmtree(stale)
    suite = target / 'examples' / 'test_Nothing' / 'bad'
    suite.mkdir(parents=True)
    (suite / 'expectations.yaml').write_text(
        'examples:\n  - path: nope.jsonld\n    expect: invalid\n')

    from semforge.cooked.examples import build_suite

    broken = _cases(build_suite(load(str(target))))[0]
    assert broken.severity == 'violation'
    assert 'error' in broken.detail and 'nope' in broken.detail


# --- composition -------------------------------------------------------------

def test_includes_are_merged_before_the_example(corpus):
    """The example wins where both describe the same entity.

    That is what lets bad/ swap in a filter that is OFF over the one the good
    case includes.
    """
    from semforge.expect.store import Example, compose
    from semforge.validate.orchestrator import validate_graphs

    off = compose(corpus, Example(
        path='test_StateOnCutterShape/bad/filter-off.jsonld',
        include=['subobjects/workpiece-steel.jsonld',
                 'subobjects/cartridge-fresh.jsonld',
                 'subobjects/filter-off.jsonld']))
    report = validate_graphs(off, corpus.shapes, corpus.knowledge, strict=False)
    assert [r.shape.rsplit('/', 1)[-1] for r in report.violations] == \
        ['StateOnCutterShape']


def test_every_example_file_is_declared(corpus):
    """A file that exists and is never run suggests coverage the suite lacks."""
    from semforge.expect import load_expectations
    from semforge.expect.store import discover

    declared = {e.path for e in load_expectations(corpus.path).examples}
    found = {f for f in discover(corpus.path)
             if not f.startswith('subobjects')}
    assert found == declared


def test_a_missing_include_names_itself(corpus):
    from semforge.expect.store import Example, compose

    with pytest.raises(PackageError) as exc:
        compose(corpus, Example(
            path='test_WorkpieceShape/good/at-the-limits.jsonld',
            include=['subobjects/nothing.jsonld']))
    assert 'nothing.jsonld' in str(exc.value)


def test_the_group_comes_from_the_folder_but_decides_nothing(corpus):
    from semforge.expect import load_expectations

    examples = load_expectations(corpus.path).examples
    assert {e.group for e in examples} == {'good', 'bad'}
    # A folder name groups; `expect` is what says the case must violate.
    for example in examples:
        if example.group == 'bad':
            assert example.expect == 'invalid'


# --- one file per directory --------------------------------------------------

def test_each_case_is_declared_next_to_itself(corpus):
    """A central list means every new case edits one shared file.

    Two people adding a test to different shapes would collide over it; this is
    what makes a suite something you can add, move or delete on its own.
    """
    from semforge.expect import load_expectations

    for example in load_expectations(corpus.path).examples:
        assert example.source.endswith('expectations.yaml')
        declared_in = os.path.dirname(example.source)
        assert os.path.exists(os.path.join(declared_in,
                                           os.path.basename(example.path)))


def test_a_case_knows_its_suite(corpus):
    from semforge.expect import load_expectations

    suites = {e.suite for e in load_expectations(corpus.path).examples}
    assert suites == {'test_StateOnCutterShape', 'test_WorkpieceShape',
                      'test_FilterShape', 'test_CartridgeShape'}


def test_a_new_suite_needs_no_central_edit(tmp_path, corpus):
    """The point of the layout: dropping in a directory is enough."""
    import shutil

    from semforge.expect import load_expectations

    target = tmp_path / 'pkg'
    shutil.copytree(corpus.path, target, symlinks=False)
    before = len(load_expectations(str(target)).examples)

    suite = target / 'examples' / 'test_MachineShape' / 'bad'
    suite.mkdir(parents=True)
    shutil.copy(
        target / 'examples' / 'test_FilterShape' / 'bad' /
        'without-cartridge.jsonld', suite / 'no-state.jsonld')
    (suite / 'expectations.yaml').write_text(
        'examples:\n'
        '  - path: no-state.jsonld\n'
        '    expect: invalid\n')

    after = load_expectations(str(target))
    assert len(after.examples) == before + 1
    assert 'test_MachineShape' in {e.suite for e in after.examples}


def test_paths_are_relative_to_the_declaring_file(corpus):
    """So a suite can be renamed or moved without editing anything inside it."""
    from semforge.expect import load_expectations

    example = next(e for e in load_expectations(corpus.path).examples
                   if e.suite == 'test_CartridgeShape')
    assert example.path == \
        'test_CartridgeShape/bad/shared-by-two-filters.jsonld'
    with open(example.source) as handle:
        assert 'path: shared-by-two-filters.jsonld' in handle.read()


def test_includes_stay_relative_to_examples(corpus):
    """A subobject is shared; it does not belong to the suite that uses it."""
    from semforge.expect import load_expectations

    for example in load_expectations(corpus.path).examples:
        for included in example.include:
            assert included.startswith('subobjects/')
            assert os.path.exists(
                os.path.join(corpus.path, 'examples', included))


def test_a_suite_needs_no_particular_name(tmp_path, corpus):
    """test_<Shape> reads well; nothing depends on it.

    A suite is a directory holding good/ and bad/ -- the suite is whatever sits
    above them, whatever it is called.
    """
    import shutil

    from semforge.expect import load_expectations

    target = tmp_path / 'pkg'
    shutil.copytree(corpus.path, target, symlinks=False)
    shutil.move(str(target / 'examples' / 'test_WorkpieceShape'),
                str(target / 'examples' / 'dimensions'))

    suites = {e.suite for e in load_expectations(str(target)).examples}
    assert 'dimensions' in suites and 'test_WorkpieceShape' not in suites


def test_a_case_outside_good_or_bad_is_assumed_to_conform(tmp_path, corpus):
    """The weaker position, and worth naming.

    A suite with no bad case cannot tell a constraint that is satisfied from
    one that could never fire -- which is what --coverage reports.
    """
    import shutil

    from semforge.expect import load_expectations

    target = tmp_path / 'pkg'
    shutil.copytree(corpus.path, target, symlinks=False)
    loose = target / 'examples' / 'scratch'
    loose.mkdir()
    shutil.copy(
        target / 'examples' / 'test_WorkpieceShape' / 'good' /
        'at-the-limits.jsonld', loose / 'a-workpiece.jsonld')
    (loose / 'expectations.yaml').write_text(
        'examples:\n  - path: a-workpiece.jsonld\n')

    example = next(e for e in load_expectations(str(target)).examples
                   if e.suite == 'scratch')
    assert example.expect == 'valid'
    assert example.group == '', 'no good/bad distinction was drawn'


# --- building legal NGSI-LD --------------------------------------------------

def test_the_kind_decides_which_key_carries_the_payload():
    """A pairing that cannot mean anything is refused rather than written.

    Writing `{"object": …}` where the model says Property is not a typo that
    fails loudly: the SPARQL rule's join predicate correctly refuses the row,
    silently, and the tests stay green because a constraint that never runs
    looks exactly like one that passes.
    """
    from semforge.ngsild import attribute

    assert attribute('Property', 0.6) == {'type': 'Property', 'value': 0.6}
    assert attribute('Relationship', 'urn:x:1') == \
        {'type': 'Relationship', 'object': 'urn:x:1'}
    assert attribute('JsonProperty', {}) == {'type': 'JsonProperty', 'json': {}}
    assert attribute('ListProperty', []) == \
        {'type': 'ListProperty', 'valueList': []}


@pytest.mark.parametrize('kind,value', [
    ('Relationship', 42),
    ('Relationship', {'value': 'urn:x:1'}),
    ('ListProperty', 'not a list'),
    ('JsonProperty', 'not json'),
    ('Property', {'a': 1}),
    ('Nonsense', 1),
])
def test_an_impossible_pairing_is_refused(kind, value):
    from semforge.ngsild import attribute

    with pytest.raises(PackageError):
        attribute(kind, value)


def test_an_iri_reference_is_a_legal_property_value():
    from semforge.ngsild import attribute

    assert attribute('Property', {'@id': 'base:state_ON'})['value'] == \
        {'@id': 'base:state_ON'}


def test_metadata_lands_in_the_right_place():
    from semforge.ngsild import attribute

    built = attribute('Property', 1, observedAt='2024-01-01T00:00:00.000Z',
                      datasetId='urn:d:1')
    assert list(built) == ['type', 'value', 'observedAt', 'datasetId']


def test_the_kind_is_read_off_the_shapes(corpus):
    """Better than asking the author, who is who the model exists to help."""
    from semforge.ngsild import kind_for_shape

    assert kind_for_shape(corpus, 'Cutter', 'hasFilter') == 'Relationship'
    assert kind_for_shape(corpus, 'Filter', 'hasStrength') == 'Property'
    assert kind_for_shape(corpus, 'Filter', 'hasCartridge') == 'Relationship'
    assert kind_for_shape(corpus, 'Filter', 'nothingLikeThis') is None


def test_adding_an_attribute_infers_its_kind(package):
    from semforge.cooked.examples import add_attribute

    # CutterShape declares hasOutWorkpiece as a relationship, and
    # urn:plasmacutter:1 does not carry it yet.
    _, kind = add_attribute(package, 'urn:plasmacutter:1',
                            'iffBaseEntities:hasOutWorkpiece',
                            value='urn:workpiece:1')
    assert kind == 'Relationship'
    with open(package.sources['model']) as handle:
        document = json.load(handle)
    entity = next(e for e in document if e['id'] == 'urn:plasmacutter:1')
    assert 'object' in entity['iffBaseEntities:hasOutWorkpiece']


def test_adding_an_attribute_that_is_already_there_is_refused(package):
    from semforge.cooked.examples import add_attribute

    with pytest.raises(PackageError) as exc:
        add_attribute(package, 'urn:filter:1', 'iffBaseEntities:hasStrength',
                      value=1)
    assert 'add an observation' in str(exc.value)


def test_a_new_entity_is_legal_ngsi_ld(package):
    from semforge.cooked.examples import add_entity

    add_entity(package, 'urn:filter:77', 'iffBaseEntities:Filter')
    with open(package.sources['model']) as handle:
        document = json.load(handle)
    added = document[-1]
    assert list(added)[:3] == ['@context', 'id', 'type']
    assert added['@context'].startswith('https://')


def test_a_duplicate_entity_is_refused(package):
    from semforge.cooked.examples import add_entity

    with pytest.raises(PackageError) as exc:
        add_entity(package, 'urn:filter:1', 'iffBaseEntities:Filter')
    assert 'already declares' in str(exc.value)


def test_an_edit_lands_in_the_file_it_came_from(tmp_path, corpus):
    """The suite view shows entities from example files.

    Editing one has to write where it came from; the first version wrote every
    edit into model-instance.jsonld regardless.
    """
    import shutil

    from semforge.cooked.examples import add_attribute
    from semforge.cooked.knowledge import add_attribute_term

    target = tmp_path / 'pkg'
    shutil.copytree(corpus.path, target, symlinks=False)
    package = load(str(target))

    # Declared before used: an attribute the knowledge has never heard of is
    # refused now, which is test_vocabulary.py's story.
    add_attribute_term(package, 'hasDepth', 'Property',
                       'iffBaseEntities:Workpiece')
    package = load(str(target))

    before = open(package.sources['model']).read()
    case = 'test_WorkpieceShape/good/at-the-limits.jsonld'
    source, _ = add_attribute(package, 'urn:workpiece:1',
                              'iffBaseEntities:hasDepth', value=3, file=case)

    assert source.endswith('at-the-limits.jsonld')
    assert open(package.sources['model']).read() == before


def test_every_node_knows_its_file(corpus):
    from semforge.cooked.examples import build_suite

    for _, node in flatten(build_suite(corpus)):
        if node.kind in ('entity', 'attribute', 'instance', 'dataset'):
            assert node.file, f'{node.kind} {node.label} has no file'


def test_every_payload_can_be_edited_not_only_the_scalar_ones(corpus, tmp_path):
    """A JsonProperty's `json` and a ListProperty's `valueList` are values too.

    They showed a value and refused to change it, which is the worst of both --
    and the input parses JSON, so a list and an object go in as such.
    """
    import shutil

    from semforge.cooked.examples import build_suite, flatten, set_value
    from semforge.package import load

    target = tmp_path / 'pkg'
    shutil.copytree(corpus.path, target, symlinks=False)
    package = load(str(target))

    for label, written in (('hasJSON', '{"a": 1, "b": [2, 3]}'),
                           ('hasList', '[4, 5, 6]')):
        row = next(n for _, n in flatten(build_suite(package))
                   if n.label == label and n.kind in ('attribute', 'instance')
                   and n.editable)
        path, _, after = set_value(package, row.entity, row.path, written,
                                   file=row.file)
        assert after == written
        assert written.replace(' ', '') in \
            open(path, encoding='utf-8').read().replace(' ', '').replace('\n', '')


def test_a_row_is_read_only_only_when_it_has_no_value_of_its_own(corpus):
    """What is left after includes and payloads became editable.

    A container row -- an attribute whose instances carry sub-attributes -- has
    no single value, so there is nothing to put in an input box. Anything else
    refusing to be edited would be a bug.
    """
    from semforge.cooked.examples import build_suite, flatten

    for _, node in flatten(build_suite(corpus)):
        if node.kind not in ('attribute', 'dataset', 'instance', 'meta'):
            continue
        if node.editable:
            continue
        assert node.children, f'{node.label} is locked and has nothing beneath it'
        assert not node.value, f'{node.label} shows a value it will not change'
