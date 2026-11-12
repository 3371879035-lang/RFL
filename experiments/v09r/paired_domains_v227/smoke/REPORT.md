# V227 paired-domain result

Common completed rounds: 1. Actual charged steps: 49152.
Wall seconds: 66.1 / cap 1800.
All rows below use fixed weights; greedy and epsilon=.1 are separate. No cross-domain score comparison.

## generic, epsilon=0.0
|Group|Initial score|Final score|Initial success|Final success|Final distance|
|---|---:|---:|---:|---:|---:|
|RL-plain|0.000000|0.000000|0/4|0/4|1.1702736962683369|
|RL-outer|0.000000|0.000000|0/4|0/4|1.1915691119778957|
|F0|0.000000|0.000000|0/4|0/4|1.3536105325700047|
|F-RP|0.000000|0.000000|0/4|0/4|1.1740884356084962|
|F-R|0.000000|0.000000|0/4|0/4|1.552249013360139|
|N227|0.000000|0.000000|0/4|0/4|1.058175520257656|

## generic, epsilon=0.1
|Group|Initial score|Final score|Initial success|Final success|Final distance|
|---|---:|---:|---:|---:|---:|
|RL-plain|0.000000|0.000000|0/4|0/4|0.9551155793276351|
|RL-outer|0.000000|0.000000|0/4|0/4|1.0822563828777143|
|F0|0.000000|0.000000|0/4|0/4|1.0373297135303432|
|F-RP|0.000000|0.000000|0/4|0/4|0.9373157457470775|
|F-R|0.000000|0.000000|0/4|0/4|1.5053273734538757|
|N227|0.000000|0.000000|0/4|0/4|0.8219653898711061|

## pursuit, epsilon=0.0
|Group|Initial score|Final score|Initial success|Final success|Final distance|
|---|---:|---:|---:|---:|---:|
|RL-plain|42.000000|93.750000|0/4|0/4|None|
|RL-outer|42.000000|61.500000|0/4|0/4|None|
|F0|46.875000|21.000000|0/4|0/4|None|
|F-RP|42.000000|66.750000|0/4|0/4|None|
|F-R|42.000000|71.250000|0/4|0/4|None|
|N227|42.000000|44.625000|0/4|0/4|None|

## pursuit, epsilon=0.1
|Group|Initial score|Final score|Initial success|Final success|Final distance|
|---|---:|---:|---:|---:|---:|
|RL-plain|44.625000|50.625000|0/4|0/4|None|
|RL-outer|44.625000|116.875000|0/4|0/4|None|
|F0|73.375000|61.750000|0/4|0/4|None|
|F-RP|44.625000|77.500000|0/4|0/4|None|
|F-R|44.625000|73.500000|0/4|0/4|None|
|N227|44.625000|72.625000|0/4|0/4|None|

## Limits
- Fixed-weight evaluation, not extra-test inference service
- Same compact backbone; not literal historical agents
- Three seeds in the long run; episode counts are not independent training seeds
- No saturation or general superiority inference
- F0 goal-related factual prediction is not absence of a goal preference
