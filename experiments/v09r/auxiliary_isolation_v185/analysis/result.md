# V185：辅助学习隔离实测

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

## 固定读出的配对差

|组|隔离后−前，Q读出|隔离后−前，完整读出|隔离后完整−Q|隔离后Q−纯RL|
|---|---:|---:|---:|---:|
|F-RP|+101.315|-11.799|-134.324|+0.000|
|F-R|+28.862|-8.915|-57.582|-75.388|

逐seed差值：
- F-RP isolation_effect_fixed_Q: [69.1796875, 117.17578125, 103.6796875, 115.2265625]
- F-RP isolation_effect_fixed_full: [-8.81640625, -16.20703125, -14.55859375, -7.61328125]
- F-RP isolated_full_minus_ownQ: [-102.984375, -151.21875, -129.78125, -153.3125]
- F-RP isolated_Q_minus_pureRL: [0.0, 0.0, 0.0, 0.0]
- F-R isolation_effect_fixed_Q: [26.05859375, 40.40234375, 16.6484375, 32.33984375]
- F-R isolation_effect_fixed_full: [-10.75, -10.0703125, -11.078125, -3.76171875]
- F-R isolated_full_minus_ownQ: [-71.65625, -71.921875, -37.35546875, -49.39453125]
- F-R isolated_Q_minus_pureRL: [-34.859375, -76.29296875, -86.05078125, -104.34765625]

## 核心参数/完整训练轨迹与纯RL的精确比较

```json
[
  {
    "seed": 93001,
    "arm": "F-R",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": null,
    "full_training_physical_rows_match_pureRL": null
  },
  {
    "seed": 93001,
    "arm": "F-RP",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": true,
    "full_training_physical_rows_match_pureRL": true
  },
  {
    "seed": 93002,
    "arm": "F-R",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": null,
    "full_training_physical_rows_match_pureRL": null
  },
  {
    "seed": 93002,
    "arm": "F-RP",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": true,
    "full_training_physical_rows_match_pureRL": true
  },
  {
    "seed": 93003,
    "arm": "F-R",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": null,
    "full_training_physical_rows_match_pureRL": null
  },
  {
    "seed": 93003,
    "arm": "F-RP",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": true,
    "full_training_physical_rows_match_pureRL": true
  },
  {
    "seed": 93004,
    "arm": "F-R",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": null,
    "full_training_physical_rows_match_pureRL": null
  },
  {
    "seed": 93004,
    "arm": "F-RP",
    "factual_heads_parameter_content_changed": true,
    "final_core_bitwise_matches_pureRL": true,
    "full_training_physical_rows_match_pureRL": true
  }
]
```

## 实际新增工作

```json
{
  "training_steps": 1048576,
  "evaluation_episodes": 9216,
  "evaluation_steps": 255990,
  "all_environment_steps": 1304566,
  "completed_training_episodes": 31072,
  "source_instances": 40296,
  "optimizer_steps": 8072,
  "factual_updates": 8072,
  "wall_seconds": 434.7988798000006
}
```

恢复基线不是反馈增量。全局方案仍未完成；不把隔离修复的结果归因给未实施的检索/决策改进。
