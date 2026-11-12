"""Finalize only closed v106 native and stored-audit evidence; never run RFL."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MODES = ('dq', 'patch-adaptive')
AUDIT_CAPTURE = HERE / 'evidence_stored_audit_kernel_return_revised'
AUDIT_SOURCE = HERE / 'audit_dense_kernel_return_revised.py'
AUDIT_RESULT = HERE / 'stored_audit_kernel_return_revised_result.json'


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode('ascii')).hexdigest()


def meta(path):
    checksum = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            size += len(block)
            checksum.update(block)
    return {'bytes': size, 'sha256': checksum.hexdigest()}


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.write('\n')


def indexed(path):
    return {'path': path.relative_to(ROOT).as_posix(), **meta(path)}


def seconds_between(started, completed):
    return (datetime.fromisoformat(completed) - datetime.fromisoformat(started)).total_seconds()


def preserved_audit_failure(capture_name, source_name, launcher_name, error_fragment, cause, successor):
    capture = HERE / capture_name
    claim = read(capture / 'claim.json')
    receipt = read(capture / 'exit.json')
    assert receipt['native_exit_code'] == 1 and receipt['input_bytes_unchanged']
    assert claim['input_binding_before'] == receipt['input_binding_after']
    assert not claim['automatic_retry'] and not receipt['automatic_retry']
    for name in (source_name, launcher_name):
        path = HERE / name
        assert meta(path) == claim['input_binding_before'][path.relative_to(ROOT).as_posix()]
    for name, field in (('stdout.log', 'stdout'), ('stderr.log', 'stderr')):
        assert meta(capture / name) == receipt[field]
    assert error_fragment in (capture / 'stderr.log').read_text(encoding='utf-8')
    return {
        'native_exit_code_preserved': 1, 'elapsed_seconds': receipt['elapsed_seconds'],
        'cause': cause, 'successor_change': successor,
        'claim': indexed(capture / 'claim.json'), 'exit': indexed(capture / 'exit.json'),
        'stdout': indexed(capture / 'stdout.log'), 'stderr': indexed(capture / 'stderr.log'),
        'audit_source': indexed(HERE / source_name), 'audit_launcher': indexed(HERE / launcher_name),
        'input_bytes_unchanged': True, 'automatic_retry': False}


def role_diagnostics(child):
    entries = child['ordered_curves']
    if entries is None:
        return []
    result = []
    assert [entry['role'] for entry in entries] == ['reference', 'treatment']
    for index, entry in enumerate(entries):
        curve = entry['ordered_curve']
        assert len(curve) == 466 and [point['epoch'] for point in curve] == list(range(466))
        values = [float.fromhex(point['mean_hex']) for point in curve]
        result.append({
            'mode': child['mode'], 'role': entry['role'], 'checkpoints': len(curve),
            'first_mean_hex': curve[0]['mean_hex'], 'last_mean_hex': curve[-1]['mean_hex'],
            'minimum_mean_hex': min(values).hex(), 'maximum_mean_hex': max(values).hex(),
            'final_numeric_entry_count': entry['numeric_entry_count'],
            'final_decision_entry_count': entry['decision_entry_count'],
            'final_composite_sha256': entry['full_composite_sha256'],
            'full_ordered_curve': {
                'path': AUDIT_RESULT.relative_to(ROOT).as_posix(),
                'json_pointer': '/children/' + str(indexed_child_index(child))
                    + '/ordered_curves/' + str(index) + '/ordered_curve',
                'canonical_sha256': digest(curve)},
            'interpretation': 'One deterministic engineering input stream, not a seed-level effect estimate.'})
    return result


def indexed_child_index(child):
    return MODES.index(child['mode'])


def main():
    output_names = ('result_summary.json', 'source_binding.json', 'README.md')
    assert all(not (HERE / name).exists() for name in output_names), 'exclusive report output exists'
    contract = read(HERE / 'contract.json')
    native_claim = read(HERE / 'evidence/claim.json')
    native_exit = read(HERE / 'evidence/exit.json')
    audit_claim = read(AUDIT_CAPTURE / 'claim.json')
    audit_exit = read(AUDIT_CAPTURE / 'exit.json')
    audit = read(AUDIT_RESULT)
    assert audit_exit['native_exit_code'] == 0 and audit_exit['input_bytes_unchanged']
    assert audit_exit['stored_audit_result'] == meta(AUDIT_RESULT)
    assert audit_claim['input_binding_before'] == audit_exit['input_binding_after']
    assert audit['audit_source'] == meta(AUDIT_SOURCE)
    assert native_exit['input_bytes_unchanged']
    pins = native_claim['input_binding_before']
    assert pins == native_exit['input_binding_after']
    assert native_claim['parent_commit'] == contract['parent_commit']
    assert native_claim['serial_children'] and native_claim['planned_modes'] == list(MODES)
    assert not native_claim['automatic_retry'] and not native_exit['automatic_retry']
    assert not audit_claim['automatic_retry'] and not audit_exit['automatic_retry']
    assert audit['native_child_receipts_preserved'] == native_exit['child_receipts']
    assert audit['input_binding_pins'] == len(pins)
    assert not audit['scientific_qualification'] and not audit['old_checker_RFL_execution']
    assert not audit['runtime_identity_reconstructed']

    first_failure = preserved_audit_failure(
        'evidence_stored_audit', 'audit_dense.py', 'execute_audit.py',
        "AssertionError: ('unknown tag', 'ORIGINAL_SOURCE')",
        'ORIGINAL_SOURCE was collected for later source verification but fell through the tag dispatch.',
        'The dispatch revision changed tag handling and namespace transport only; first audit and native workload bytes remained unchanged.')
    second_failure = preserved_audit_failure(
        'evidence_stored_audit_dispatch_revised', 'audit_dense_dispatch_revised.py',
        'execute_audit_dispatch_revised.py', "assert total.hex()==r['return_hex']",
        'The dispatch audit used a naive reward fold for episode return, unlike the original kernel float(sum(...)) return semantics; one ULP differed at the recorded epoch 258 receipt.',
        'A new audit restores the exact original kernel episode-return calculation at both return checks. No tolerance was added; chronological TD/B1 reversed return folds and ordered bank addition remain unchanged. No native workload rerun.')

    frozen_path = ROOT / contract['frozen_manifest']
    frozen = read(frozen_path)
    assert meta(frozen_path) == pins[contract['frozen_manifest']]
    assert len(frozen['sources']) == 313
    assert all(pins[name]['sha256'] == sha for name, sha in frozen['sources'].items())
    receipts = native_exit['child_receipts']
    children = audit['children']
    assert [entry['mode'] for entry in receipts] == list(MODES)[:len(receipts)]
    assert [entry['mode'] for entry in children] == [entry['mode'] for entry in receipts]
    assert all((receipt['child_exit_code'] == 0) == child['complete']
               for receipt, child in zip(receipts, children))
    complete = len(children) == 2 and all(child['complete'] for child in children)
    assert complete == native_exit['completed'] == audit['complete_two_serial_architectures']

    measured = []
    all_curves = []
    native_artifacts = []
    for receipt, child in zip(receipts, children):
        folder = HERE / 'evidence' / child['mode']
        summary_path = folder / 'child_summary.json'
        summary = read(summary_path)
        assert receipt == read(folder / 'exit.json')
        assert meta(summary_path) == receipt['child_summary.json']
        assert summary['completed'] == child['complete']
        assert summary['mode'] == child['mode']
        assert summary['peaks'] == child['peaks']
        assert summary['records'] == child['records']
        assert summary['uncompressed_bytes'] == child['uncompressed_bytes']
        assert summary['canonical_sha256'] == child['canonical_sha256']
        assert summary['compressed_bytes'] == child['compressed_meta']['bytes']
        assert receipt['raw.jsonl.gz'] == child['compressed_meta']
        assert summary['wall_seconds'] == child['instrumented_wall_seconds']
        assert summary['cpu_seconds'] == child['cpu_seconds']
        for name, field in (('stdout.log', 'stdout'), ('stderr.log', 'stderr')):
            assert meta(folder / name) == receipt[field]
        all_curves.extend(role_diagnostics(child))
        source_captures = child['tag_inventory'].get('ORIGINAL_SOURCE', 0)
        prepared_pairs = child['tag_inventory'].get('CURVE_PREPARED', 0)
        assert source_captures in (0, 1) and prepared_pairs in (0, 1)
        measured.append({
            'mode': child['mode'], 'complete': child['complete'],
            'native_exit_code': receipt['child_exit_code'],
            'started_at_utc': receipt['started_at_utc'], 'completed_at_utc': receipt['completed_at_utc'],
            'instrumented_wall_seconds': summary['wall_seconds'],
            'cpu_seconds': summary['cpu_seconds'],
            'capture_encode_seconds': summary['encode_seconds'],
            'capture_write_seconds': summary['write_seconds'],
            'counts': summary['counts'], 'canonical_records': summary['records'],
            'uncompressed_bytes': summary['uncompressed_bytes'],
            'gzip_bytes': summary['compressed_bytes'],
            'canonical_sha256': summary['canonical_sha256'],
            'gzip_sha256': child['compressed_meta']['sha256'],
            'Win32_peaks_and_sampled_host_reserve': summary['peaks'],
            'resource_samples': len(child['resource_samples']),
            'complete_checkpoint_banks': child['complete_banks'],
            'chronological_TD_receipts': child['tag_inventory'].get('CORE_EPISODE', 0),
            'complete_retained_handle_checkpoint_links': child['retained_actual_handle_checkpoint_links'],
            'closed_external_projections': child['external_closed_projections_checked'],
            'actual_loaded_source_pins': child['loaded_source_pins'] or None,
            'loaded_source_inventory_captured': bool(child['loaded_source_pins']),
            'extra_completed_owned_source_captures': source_captures,
            'extra_completed_source_install_transactions': source_captures,
            'whole_therapy_transactions_from_verified_prepared_pairs': prepared_pairs,
            'verified_owner_receipts': child['original_owner_receipts_verified'],
            'TD_and_policy_diagnostics': child['TD_and_policy_diagnostics'],
            'native_failure_preserved': child['native_failure_preserved'],
            'terminal_budget_failure_boundary': child.get('terminal_budget_failure_boundary'),
            'partial_count_evidence': child.get('partial_count_evidence'),
            'source_work_note': 'Completed source capture is extra factual/install work, not a science population. '
                'If failure precedes source issuance, raw records and actual call counts retain any partial work.'})
        native_artifacts.append({
            'mode': child['mode'], 'claim': indexed(folder / 'claim.json'),
            'exit': indexed(folder / 'exit.json'), 'summary': indexed(summary_path),
            'raw': {'path': (folder / 'raw.jsonl.gz').relative_to(ROOT).as_posix(),
                    **child['compressed_meta']},
            'stdout': {'path': (folder / 'stdout.log').relative_to(ROOT).as_posix(), **receipt['stdout']},
            'stderr': {'path': (folder / 'stderr.log').relative_to(ROOT).as_posix(), **receipt['stderr']}})

    if complete:
        assert len(all_curves) == 4
        assert audit['total_raw_rollouts'] == 188262
        assert audit['total_chronological_TD_receipts'] == 1860
        assert audit['total_owner_receipts'] == 28
        assert sum(child['complete_banks'] for child in children) == 1864
    totals = {
        'actual_rollouts': audit['total_raw_rollouts'], 'actual_steps': audit['total_steps'],
        'actual_B1_calls': sum(child['actual_counts'].get('B1', 0) for child in children),
        'actual_transaction_calls': sum(child['actual_counts'].get('transaction', 0) for child in children),
        'completed_chronological_TD_receipts': audit['total_chronological_TD_receipts'],
        'verified_owner_receipts': audit['total_owner_receipts'],
        'complete_checkpoint_banks': sum(child['complete_banks'] for child in children),
        'complete_role_curves': len(all_curves),
        'extra_completed_owned_source_captures': sum(entry['extra_completed_owned_source_captures'] for entry in measured),
        'extra_completed_source_install_transactions': sum(entry['extra_completed_source_install_transactions'] for entry in measured),
        'whole_therapy_transactions_from_verified_prepared_pairs': sum(entry['whole_therapy_transactions_from_verified_prepared_pairs'] for entry in measured),
        'serial_children_instrumented_wall_seconds_sum': sum(entry['instrumented_wall_seconds'] for entry in measured),
        'serial_children_cpu_seconds_sum': sum(entry['cpu_seconds'] for entry in measured),
        'parent_elapsed_seconds': seconds_between(native_exit['started_at_utc'], native_exit['completed_at_utc']),
        'stored_audit_elapsed_seconds': audit_exit['elapsed_seconds'],
        'uncompressed_bytes': sum(entry['uncompressed_bytes'] for entry in measured),
        'gzip_bytes': sum(entry['gzip_bytes'] for entry in measured),
        'maximum_process_peak_working_set_bytes': max((entry['Win32_peaks_and_sampled_host_reserve']['peak_working_set_bytes'] for entry in measured), default=None),
        'maximum_process_peak_commit_bytes': max((entry['Win32_peaks_and_sampled_host_reserve']['peak_commit_bytes'] for entry in measured), default=None),
        'minimum_sampled_available_physical_bytes': min((entry['Win32_peaks_and_sampled_host_reserve']['minimum_available_physical_bytes'] for entry in measured), default=None)}
    status = ('COMPLETE_TWO_ARCHITECTURE_T465_N100_DECLARED_ENGINEERING_WORKLOAD_STORED_VERIFIED'
              if complete else 'PARTIAL_DECLARED_ENGINEERING_WORKLOAD_NATIVE_FAILURE_PRESERVED_STORED_VERIFIED')
    limits = [
        'Full T465/N100 extent for exactly the predeclared deterministic EngineeringEpisode stream; not keyed Xi domain or seed-level inference.',
        'Instrumented wall/CPU include observer, capture, serialization and constructor work; no subtraction or production-time extrapolation.',
        'Win32 process peaks are actual counters; host available RAM is sampled at declared boundaries, not a continuous host-wide minimum.',
        'NoWrite also learns; policy improvement, numeric TD response and B1 responsibility are distinct.',
        'Does not transfer F1 qualification or qualify arbitrary k/shape, full fair family, whole-ruler aggregate calibration/threshold/weights or final 400/200 analysis.',
        'Stored audit verifies complete recorded content; runtime identity is not reconstructed from serialized bytes.',
        'Any native failure/partial remains failure/partial; no automatic retry, old fixture rerun or executed source rewrite.']
    result = {
        'schema': 'V106_DENSE_RESOURCE_WORKLOAD_FINALIZED_ENGINEERING_RESULT',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'parent_commit': contract['parent_commit'], 'status': status,
        'complete_two_serial_architectures': complete,
        'extent': {'T': 465, 'N_eval': 100, 'grid': list(range(466)),
                   'declared_structural_totals_not_actual_unless_complete': contract['structural_totals'],
                   'source_scene': contract['source_scene'],
                   'episode_formula': contract['episode_formula'], 'coordinate_formula': contract['coordinate_formula']},
        'totals': totals, 'children': measured, 'role_curve_diagnostics': all_curves,
        'source_binding': 'source_binding.json',
        'full_audited_curves_and_resources': AUDIT_RESULT.name,
        'preserved_first_stored_audit_failure': first_failure,
        'preserved_second_stored_audit_failure': second_failure,
        'claim_limits': limits, 'budget': contract['budget'],
        'declared_budget_met_by_complete_workload': complete,
        'old_native_fixture_checker_reruns': 0, 'new_science_or_workload_keys': 0,
        'RNG_keyderive_DP_nativecalibration': 0, 'formal_keyed_permit_issued_or_stream_executed': False,
        'formal_Protocol_Curve_train_curve_or_collection_executed': False,
        'automation': 'Disabled per latest direct human instruction; no automation tool called.',
        'scientific_qualification': False, 'valid_original_mechanism_refutation': False,
        'research_status': 'UNEVALUATED_COLLECTION_CLOSED_RESEARCH_INCOMPLETE'}
    binding = {
        'schema': 'V106_DECLARED_NATIVE_AND_STORED_EVIDENCE_INDEX_NOT_A_NATIVE_RECEIPT',
        'parent_commit': contract['parent_commit'], 'contract': indexed(HERE / 'contract.json'),
        'native_parent_claim': indexed(HERE / 'evidence/claim.json'),
        'native_parent_exit': indexed(HERE / 'evidence/exit.json'),
        'native_children': native_artifacts,
        'stored_audit_claim': indexed(AUDIT_CAPTURE / 'claim.json'),
        'stored_audit_exit': indexed(AUDIT_CAPTURE / 'exit.json'),
        'stored_audit_result': indexed(AUDIT_RESULT),
        'preserved_first_stored_audit_failure': first_failure,
        'preserved_second_stored_audit_failure': second_failure,
        'finalizer_source': indexed(Path(__file__)),
        'native_declared_input_binding': {
            'index_path': (HERE / 'evidence/claim.json').relative_to(ROOT).as_posix(),
            'json_pointer': '/input_binding_before', 'pins': len(pins),
            'declared_bytes': sum(pin['bytes'] for pin in pins.values()),
            'canonical_mapping_sha256': digest(pins),
            'native_before_after_equal': True, 'independent_stored_current_bytes_verified': True},
        'original_frozen_manifest': {
            **indexed(frozen_path), 'source_count': len(frozen['sources']),
            'source_digest': frozen['sources_digest'],
            'all_manifest_members_equal_native_claim_pins': True},
        'actual_loaded_source_inventory': [
            {'mode': child['mode'], 'actual_pins': child['loaded_source_pins'] or None,
             'record_path': (HERE / 'evidence' / child['mode'] / 'raw.jsonl.gz').relative_to(ROOT).as_posix(),
             'record_tag': 'ACTUAL_LOADED_SOURCE_INVENTORY',
             'complete_inventory_present': bool(child['loaded_source_pins'])}
            for child in children],
        'audit_declared_input_pins': len(audit_claim['input_binding_before']),
        'audit_before_after_equal': True, 'native_and_audit_automatic_retry': False,
        'scope': 'Only declared native/audit evidence and original 313 manifest, not all repository tracked bytes or a 13 GB audit.',
        'independent_expert_or_science_gate': False, 'runtime_identity_reconstructed': False}
    save(HERE / 'source_binding.json', binding)
    save(HERE / 'result_summary.json', result)
    lines = [
        '# V106 — full-scale declared engineering workload', '',
        'Status: `' + status + '`.', '',
        'The planned extent is T=465, all integer checkpoints 0–465, and all 100 locked evaluation scenes. '
        'DQ and patch-adaptive run serially on the fixed deterministic engineering input; both NoWrite and treatment continue learning.', '',
        '| Mode | Native exit | Complete banks | TD episodes | Wall seconds | CPU seconds | Peak working set MiB | Gzip MiB |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for child in measured:
        lines.append('| {mode} | {native_exit_code} | {complete_checkpoint_banks} | {chronological_TD_receipts} | '
                     '{instrumented_wall_seconds:.3f} | {cpu_seconds:.3f} | {ram:.2f} | {gzip:.2f} |'.format(
                         **child, ram=child['Win32_peaks_and_sampled_host_reserve']['peak_working_set_bytes'] / 2**20,
                         gzip=child['gzip_bytes'] / 2**20))
    lines += ['', 'Actual recorded totals: {actual_rollouts} rollouts, {actual_steps} steps, '
              '{actual_B1_calls} B1 calls, {actual_transaction_calls} transaction calls, '
              '{complete_role_curves} complete role curves.'.format(**totals), '',
              'Additional fresh source capture/install work is explicitly counted in `result_summary.json`; '
              'these are not additional scientific seeds or a new scientific population.', '',
              'Read `result_summary.json` for actual resource totals and curve diagnostics; '
              '`' + AUDIT_RESULT.name + '` retains all complete ordered curves, raw-content validation and sampled resources; '
              '`source_binding.json` links original native/audit receipts and exact input pins.', '',
              'The first stored audit exited 1 on an ORIGINAL_SOURCE tag-dispatch error. '
              'The separate dispatch audit also exited 1 because its naive episode-return fold differed from the original kernel float(sum(...)) semantics. '
              'Both sources and complete failure captures remain unchanged. The kernel-return revision restores the exact original calculation without tolerance; '
              'chronological TD/B1 reversed folds and ordered bank addition are unchanged. This separate audit version/capture is not a native workload retry. '
              'Any partial or failure is retained without retry. Instrumented timing is not production timing. '
              'This is a full-scale execution/resource check for the exact declared stream, not F1 transfer, '
              'keyed-domain qualification, full-family scientific validation or a final V0.3 result. '
              'No new keys, RNG, DP, calibration, formal keyed stream or scientific collection were run. '
              'Automation remains disabled.', '']
    with (HERE / 'README.md').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write('\n'.join(lines))
    print(canonical({'status': status, 'totals': totals,
                     'report': indexed(HERE / 'result_summary.json'),
                     'source_binding': indexed(HERE / 'source_binding.json')}))


if __name__ == '__main__':
    main()
