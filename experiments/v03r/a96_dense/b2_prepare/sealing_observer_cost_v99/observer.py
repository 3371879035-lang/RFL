"""Sparse profiling dispatch; it does not suppress a native or forbidden event.

The handler remains the complete capture/budget implementation. Uninteresting
Python frames bypass it. Code objects are held strongly beside integer identity
keys, preventing identity reuse. No original module or profile is patched.
"""


def interesting(code):
    path = code.co_filename.replace('\\', '/')
    name, qualname = code.co_name, code.co_qualname
    return (
        (path.endswith('rfl_rebuild/env/kernel.py') and name in ('step', 'rollout', 'sample'))
        or (path.endswith('rfl_rebuild/learner/store.py') and name == 'apply_transaction')
        or (path.endswith('rfl_rebuild/b1/runner.py') and name in
            ('run_patch_law', 'run_dq_law', 'run_process_law', 'run_controller_law'))
        or (path.endswith('rfl_rebuild/b2/training.py') and name in
            ('derive', 'key', 'mix', 'train_curve', 'pre_level'))
        or (path.endswith('rfl_rebuild/solve/dp.py') and name == 'solve_reference')
        or (path.endswith('random.py') and name in ('__init__', 'random', 'randrange'))
        or qualname in ('FutureTrainingProtocol.__init__', 'Curve.__init__')
        or (path.endswith('/ruler.py') and name == '_ordinary_bank')
    )


def make_observer(handler):
    """Dispatch exactly the frames on which the v98 handler can take an action.

    Handler receives original frame/event/arg without rewriting. This component
    is not a security sandbox; a future native harness must still bind its full
    handler, inventory, restoration, call counts and real partial capture.
    """
    cache = {}

    def observe(frame, event, arg):
        code = frame.f_code
        key = id(code)
        item = cache.get(key)
        if item is None:
            item = (code, interesting(code))
            cache[key] = item
        if item[1]:
            handler(frame, event, arg)

    observe.code_inventory = cache
    return observe
