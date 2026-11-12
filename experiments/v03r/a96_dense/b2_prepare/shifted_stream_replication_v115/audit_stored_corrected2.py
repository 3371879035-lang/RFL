"""Second targeted stored-audit correction: v115 source motivation wording."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = (HERE / "audit_stored.py").read_text(encoding="utf-8")
source = source.replace("p['engineering_n_eval']==100", "p['evaluation_scenes']==100")
source = source.replace("'Result-informed recovery-ruler engineering canary, not blind scientific family or benefit screening'",
                        "'Human-requested fresh replication of the known four-context mechanism with fixed shifted training order; not a new defect family, blind scientific population or benefit screen'")
source = source.replace("stored_audit_result.json", "stored_audit_result_corrected2.json")
code = compile(source, str(HERE / "audit_stored.py"), "exec")
exec(code, {"__name__": "__main__", "__file__": str(HERE / "audit_stored.py")})
