# V227 paired-domain result

Common completed rounds: 123. Actual charged steps: 18137088.
Wall seconds: 10108.8 / cap 10800.
All rows below use fixed weights; greedy and epsilon=.1 are separate. No cross-domain score comparison.

## generic, epsilon=0.0
|Group|Initial score|Final score|Initial success|Final success|Final distance|
|---|---:|---:|---:|---:|---:|
|RL-plain|0.000000|0.833333|0/96|80/96|0.26126839137749885|
|RL-outer|0.000000|0.875000|0/96|84/96|0.2319626226716839|
|F0|0.000000|0.697917|0/96|67/96|0.37784795770974805|
|F-RP|0.000000|0.854167|0/96|82/96|0.23158640652716242|
|F-R|0.000000|0.729167|0/96|70/96|0.36904674873750487|
|N227|0.000000|0.833333|0/96|80/96|0.22719308299069926|

## generic, epsilon=0.1
|Group|Initial score|Final score|Initial success|Final success|Final distance|
|---|---:|---:|---:|---:|---:|
|RL-plain|0.000000|0.697917|0/96|67/96|0.30618992623942665|
|RL-outer|0.000000|0.718750|0/96|69/96|0.29279375135822006|
|F0|0.000000|0.625000|0/96|60/96|0.400182438517914|
|F-RP|0.000000|0.739583|0/96|71/96|0.29985253550880925|
|F-R|0.000000|0.614583|0/96|59/96|0.419796227925895|
|N227|0.000000|0.718750|0/96|69/96|0.29124865917258175|

## pursuit, epsilon=0.0
|Group|Initial score|Final score|Initial success|Final success|Final distance|
|---|---:|---:|---:|---:|---:|
|RL-plain|39.338542|362.697917|0/96|18/96|None|
|RL-outer|39.338542|431.177083|0/96|20/96|None|
|F0|36.609375|53.130208|0/96|0/96|None|
|F-RP|39.338542|461.395833|0/96|27/96|None|
|F-R|39.338542|544.208333|0/96|25/96|None|
|N227|39.338542|479.869792|0/96|15/96|None|

## pursuit, epsilon=0.1
|Group|Initial score|Final score|Initial success|Final success|Final distance|
|---|---:|---:|---:|---:|---:|
|RL-plain|41.463542|195.963542|0/96|2/96|None|
|RL-outer|41.463542|263.901042|0/96|8/96|None|
|F0|41.916667|55.286458|0/96|0/96|None|
|F-RP|41.463542|279.989583|0/96|7/96|None|
|F-R|41.463542|314.515625|0/96|4/96|None|
|N227|41.463542|284.937500|0/96|5/96|None|

## Limits
- Fixed-weight evaluation, not extra-test inference service
- Same compact backbone; not literal historical agents
- Three seeds in the long run; episode counts are not independent training seeds
- No saturation or general superiority inference
- F0 goal-related factual prediction is not absence of a goal preference
