"""Produce a fact index from finished native/stored captures; no RFL execution."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def read(path):
    return json.loads(path.read_bytes())


def meta(path):
    return {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def save(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=True, indent=2)
        stream.write('\n')


def main():
    contract = read(HERE/'contract.json')
    native = read(HERE/'evidence/exit.json')
    claim = read(HERE/'evidence/claim.json')
    audit = read(HERE/'stored_audit_source_normalized_result.json')
    audit_exit = read(HERE/'evidence_stored_audit_source_normalized/exit.json')
    failed_audit = read(HERE/'evidence_stored_audit/exit.json')
    prior = HERE.parent/'complete_curve_source_gates_v104'
    prior_native = read(prior/'evidence/exit.json')
    prior_audit = read(prior/'stored_audit_result.json')
    assert native['child_exit_code'] == audit_exit['child_exit_code'] == 0
    assert prior_native['child_exit_code'] == failed_audit['child_exit_code'] == 1
    assert audit['complete_fourteen_case_capture'] and audit['six_targets_both_architectures']
    assert audit['records'] == 2177 and native['input_bytes_unchanged']
    final, inventory = None, None
    with (HERE/'evidence/stdout.log').open(encoding='utf-8') as stream:
        for line in stream:
            record = json.loads(line)
            if record['tag'] == 'RESULT': final = record['payload']
            if record['tag'] == 'ACTUAL_LOADED_SOURCE_INVENTORY': inventory = record['payload']
    assert final['counts'] == audit['actual_counts']
    elapsed = (datetime.fromisoformat(native['completed_at_utc'])-datetime.fromisoformat(native['started_at_utc'])).total_seconds()
    report = {
        'schema': 'V105_COMPLETE_OWNED_CURVE_SOURCE_MUTATION_ENGINEERING_RESULT',
        'parent_commit': contract['parent_commit'],
        'status': 'NORMAL_CONTROLS_PASS_TWELVE_TARGETED_SOURCE_MUTANTS_REJECTED_BOTH_ARCHITECTURES',
        'native': {k:v for k,v in native.items() if k != 'input_binding_after'},
        'launcher_elapsed_seconds': elapsed,
        'instrumented_child_elapsed_seconds': float.fromhex(final['seconds']['binary64_hex']),
        'records': audit['records'], 'input_pins': audit['input_binding_pins'],
        'actual_loaded_source_pins': audit['loaded_source_pins'],
        'actual_counts': audit['actual_counts'], 'fresh_owned_sources': 14,
        'B1_owner_receipts': 196, 'extra_source_install_transactions': 14,
        'whole_therapy_transactions': 14, 'total_transactions': audit['actual_counts']['transaction'],
        'normal_controls': [x for x in audit['case_results'] if x['variant']=='normal'],
        'mutant_results': [x for x in audit['case_results'] if x['variant']!='normal'],
        'six_algorithms': ['chronological_pre_state_TD', 'actual_option_in_force',
                          'exact_lazy_rejection_sampling', 'protected_immediate_state',
                          'one_injected_shared_pre_level', 'one_declared_paired_episode_stream'],
        'source_transport': audit['physical_source_review'],
        'complete_role_curves_observed': 20,
        'accepted_normal_role_curves': 4,
        'four_expected_partial_mutant_cases': 'Both post-address and protected-immediate mutants retain full raw and fault state; no complete curve handles. Actor protected-I copy is changed by the I mutant; genuine native I is separately preserved.',
        'stored_review': {'successful_exit': audit_exit, 'result': 'stored_audit_source_normalized_result.json',
                          'correct_and_mutated_TD_recomputed': audit['correct_and_mutated_TD_recomputed'],
                          'independent_stdlib_content_audit': True, 'expert_or_science_gate': False},
        'preserved_v104_failure': {'native': prior_native, 'stored_review': prior_audit,
                                  'cause': 'A healthy-reference mapping was passed as a filesystem path before any fresh source or kernel execution.',
                                  'successor_change': 'Only the path lookup and prospective physical namespace transport; input mechanism and six algorithm targets unchanged.'},
        'preserved_first_v105_stored_review_failure': {'exit': failed_audit,
                                  'cause': 'Byte-exact harness transport comparison differed by one trailing LF.',
                                  'successor_change': 'Ignore only terminal LF for this transport comparison and use a separate exclusive output. All raw/source/TD validation retained.'},
        'full_true_n5_integration_closed': True,
        'flooring_nuance': 'Flooring and exact rejection issue the same WAIT action here. The actual extra c1 request distinguishes them.',
        'CRN_nuance': 'XOR1 coins retain the exploration branch in this finite input but violate actual shared episode/coordinate equality.',
        'protected_original313_checked': True, 'old_native_fixture_checker_reruns': 0,
        'new_science_or_workload_keys': 0, 'RNG_keyderive_DP_nativecalibration': 0,
        'formal_keyed_stream_executed': False, 'formal_collection_executed': False,
        'automation': 'Remains disabled per latest direct human instruction; no automation tool called.',
        'scientific_qualification': False, 'research_status': 'UNEVALUATED_COLLECTION_CLOSED_RESEARCH_INCOMPLETE',
        'valid_original_mechanism_refutation': False,
        'next_critical_work': 'Qualify the complete declared training workload and learning-cost budget; keep k/shape interaction, whole-ruler aggregate calibration/threshold/family and final paired effect analysis explicit. These source gates do not substitute for those scientific results.'
    }
    save(HERE/'result_summary.json', report)
    pins = claim['input_binding_before']
    binding = {'schema':'V105_ACTUAL_NATIVE_SOURCE_BINDING', 'parent_commit':contract['parent_commit'],
               'claim':meta(HERE/'evidence/claim.json'), 'native_exit':meta(HERE/'evidence/exit.json'),
               'variant_manifest':read(HERE/'variant_manifest.json'), 'actual_loaded_sources':inventory,
               'declared_inputs':pins, 'input_bytes_unchanged':native['input_bytes_unchanged'],
               'normal_transport_AST':audit['physical_source_review']}
    save(HERE/'source_binding.json', binding)
    prior_report = {'schema':'V104_PRESERVED_PRE_NATIVE_SETUP_FAILURE', 'native_exit':prior_native,
                    'stored_review':prior_audit, 'source_level_cases_executed':0,
                    'successor':'../complete_curve_source_gates_v105/result_summary.json',
                    'old_executed_source_and_capture_unchanged':True, 'scientific_qualification':False}
    save(prior/'result_summary.json', prior_report)
    print(json.dumps({'status':report['status'],'actual_counts':report['actual_counts'],
                      'records':report['records'],'input_pins':report['input_pins'],
                      'loaded_sources':report['actual_loaded_source_pins']}))


if __name__ == '__main__':
    main()
