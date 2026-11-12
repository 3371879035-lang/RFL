# V187：真实转移残差反馈实测

4个配对训练种子，全部表格使用同末点j0..127场景。

|版本|组|冻结读出|平均分|存活步数|宝箱|
|---|---|---|---:|---:|---:|
|V183|RL-RP|full|165.102|86.109|0.359|
|V183|F0|full|34.750|20.172|0.045|
|V183|F-RP|full|47.462|26.303|0.080|
|V183|F-RP|Q|58.636|34.533|0.068|
|V183|F-R|full|46.531|25.031|0.090|
|V183|F-R|Q|54.580|30.918|0.082|
|V184|F-RP|full|42.576|23.566|0.072|
|V184|F-RP|Q|63.786|35.623|0.104|
|V184|F-R|full|41.047|23.328|0.061|
|V184|F-R|Q|60.852|34.578|0.090|
|V185|F-RP|full|30.777|17.914|0.039|
|V185|F-RP|Q|165.102|86.109|0.359|
|V185|F-R|full|32.132|18.947|0.037|
|V185|F-R|Q|89.714|47.049|0.191|
|V187|F-RP|full|166.989|87.107|0.363|
|V187|F-RP|Q|165.102|86.109|0.359|
|V187|F-R|full|86.276|45.799|0.176|
|V187|F-R|Q|89.714|47.049|0.191|

## 固定读出的配对差

|组|读出修订后−前，Q读出|读出修订后−前，完整读出|新反馈−Q|保留Q−纯RL|
|---|---:|---:|---:|---:|
|F-RP|+0.000|+136.212|+1.888|+0.000|
|F-R|+0.000|+54.145|-3.438|-75.388|

逐seed差值：
- F-RP readout_revision_effect_fixed_Q: [0.0, 0.0, 0.0, 0.0]
- F-RP readout_revision_effect_fixed_full: [107.171875, 161.01171875, 127.51171875, 149.15234375]
- F-RP grounded_full_minus_ownQ: [4.1875, 9.79296875, -2.26953125, -4.16015625]
- F-RP protected_Q_minus_pureRL: [0.0, 0.0, 0.0, 0.0]
- F-R readout_revision_effect_fixed_Q: [0.0, 0.0, 0.0, 0.0]
- F-R readout_revision_effect_fixed_full: [68.19140625, 73.98828125, 33.2421875, 41.15625]
- F-R grounded_full_minus_ownQ: [-3.46484375, 2.06640625, -4.11328125, -8.23828125]
- F-R protected_Q_minus_pureRL: [-34.859375, -76.29296875, -86.05078125, -104.34765625]

## 核心参数/完整训练轨迹与纯RL的精确比较

```json
[
  {
    "seed": 93001,
    "arm": "F-R",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": null,
    "full_training_physical_rows_match_pureRL": null,
    "final_core_matches_V185": true,
    "full_training_physical_rows_match_V185": true
  },
  {
    "seed": 93001,
    "arm": "F-RP",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": true,
    "full_training_physical_rows_match_pureRL": true,
    "final_core_matches_V185": true,
    "full_training_physical_rows_match_V185": true
  },
  {
    "seed": 93002,
    "arm": "F-R",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": null,
    "full_training_physical_rows_match_pureRL": null,
    "final_core_matches_V185": true,
    "full_training_physical_rows_match_V185": true
  },
  {
    "seed": 93002,
    "arm": "F-RP",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": true,
    "full_training_physical_rows_match_pureRL": true,
    "final_core_matches_V185": true,
    "full_training_physical_rows_match_V185": true
  },
  {
    "seed": 93003,
    "arm": "F-R",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": null,
    "full_training_physical_rows_match_pureRL": null,
    "final_core_matches_V185": true,
    "full_training_physical_rows_match_V185": true
  },
  {
    "seed": 93003,
    "arm": "F-RP",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": true,
    "full_training_physical_rows_match_pureRL": true,
    "final_core_matches_V185": true,
    "full_training_physical_rows_match_V185": true
  },
  {
    "seed": 93004,
    "arm": "F-R",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": null,
    "full_training_physical_rows_match_pureRL": null,
    "final_core_matches_V185": true,
    "full_training_physical_rows_match_V185": true
  },
  {
    "seed": 93004,
    "arm": "F-RP",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": true,
    "full_training_physical_rows_match_pureRL": true,
    "final_core_matches_V185": true,
    "full_training_physical_rows_match_V185": true
  }
]
```

## 实际新增工作

```json
{
  "training_steps": 1048576,
  "evaluation_episodes": 9216,
  "evaluation_steps": 367236,
  "all_environment_steps": 1415812,
  "completed_training_episodes": 31072,
  "source_instances": 40296,
  "optimizer_steps": 8072,
  "factual_updates": 8072,
  "wall_seconds": 306.97416449999946
}
```

恢复基线不是反馈增量。四种子固定候选，不按效果调参；训练Q控制不等于已证明反馈接管训练的效果。
