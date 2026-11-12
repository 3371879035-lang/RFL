"""A96 prospective protocol identity, namespace and one-use key sets."""
MEASUREMENT_PROFILE = "v03r-a96-dense-measurement-v1"
MANIFEST_SCHEMA = "f0-a96-dense-measurement-v1"
LOCK_SCHEMA = "f1-a96-dense-design-threshold-v1"
STAGE_ROOT = "experiments/v03r/a96_dense"
STAGE_SEEDS = {"smoke": tuple(range(2026101100, 2026101105)),
               "dev_baseline": tuple(range(2026101110, 2026101142))}
ENGINEERING_KEYS = {"smoke": tuple(range(2026101200, 2026101205)),
                    "dev_baseline": tuple(range(2026101205, 2026101237))}
SPENT_SCIENTIFIC_SEEDS = tuple(range(5)) + tuple(range(2026100800, 2026100805)) + tuple(range(1000, 1032)) + tuple(range(2026100900, 2026100905)) + tuple(range(2026100910, 2026100942))
PROTOCOL_FILES = ("docs/rebuild/34-A96-DENSE-MEASUREMENT.md",
                  "docs/rebuild/a96_dense_measurement_contract.json", "docs/rebuild/a96_seed_registry.json",
                  "scripts/launch_a96_pipeline.ps1",
                  STAGE_ROOT + "/pipeline/preregistration.json",
                  STAGE_ROOT + "/pipeline/parent_snapshot.json")
