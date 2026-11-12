"""Targeted corrected stored audit for the v115 audit-schema error.

The first stored audit is preserved as an audit-harness failure. This wrapper
does not rerun either native child: it executes the same stdlib audit source
with the one corrected field spelling and writes a separate result/capture.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = (HERE / "audit_stored.py").read_text(encoding="utf-8")
source = source.replace("p['engineering_n_eval']==100", "p['evaluation_scenes']==100")
source = source.replace("stored_audit_result.json", "stored_audit_result_corrected.json")
code = compile(source, str(HERE / "audit_stored.py"), "exec")
globals_for_audit = {"__name__": "__main__", "__file__": str(HERE / "audit_stored.py")}
exec(code, globals_for_audit)
