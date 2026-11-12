# V0.3 shifted-stream 复核结果

日期：2026-10-14（Asia/Shanghai）。这是用户要求的又一次有限 V0.3 实验，不是把后来形成的 400/200 确认方案重新启动。

## 设计

- 已知四 context 持久错误机制，fresh source/pair/capture；DQ 与修订 patch 各自构造，source mode 在 arms 前绑定。
- scene 固定为 [0,2,0,42,1]，error_flag=0、cause_rank=42；它是预先声明的描述，不是新的缺陷家族。
- 每个架构训练 64 个 chronological episode；每个整数 checkpoint（0..64）先用原锁定的100个场景评估，再训练下一回合。
- 训练坐标使用固定 r=e+7 移位流；alpha、epsilon、Q*、普通 TD、NoWrite 和完整 I/R+L 语义不变。
- 两个架构串行各运行一次；无 retry、无新 key、无正式 collector。旧 400/200、465/466 horizon 与晚窗资格没有被借用。

## 实际结果

| mode | 反馈组高于 NoWrite 的 checkpoint | 首次持续相等 | 最终均值 | wholeCollateral paired difference |
|---|---:|---:|---:|---:|
| DQ | e=0..11（12个） | e=12 | 0.7642000000000008 | 0x0.0p+0 |
| 修订 patch | e=0..11（12个） | e=12 | 0.7642000000000008 | 0x0.0p+0 |

两种 mode 的反馈组在前 12 个 checkpoint 都比 NoWrite 高 0.0384000000000001；从 e=12 到 e=64 逐点精确相等，没有负差。因此，这次移位训练流复核再次观察到“即时更新带来早期效率优势”，但没有观察到后续普通学习速度继续加快或最终均值提高。

DQ 的普通数值内容发生变化（10个数值变化诊断摘要）；修订 patch 的 L 数值路径没有新增数值项，但有 7个 visited-D 策略内容变化。后者仍与已有 Q* 先验驱动的策略改进分开记录，不能全称为新价值知识。

同一真实 pair 的 wholeCollateral 共享区域为4920个场景，paired difference 仍精确为零；这是局部 no-owner-consult 结果，不是一般零伤害或统计等效。

## 完整性与限制

- native 两个 child 均 exit 0；总计57458 raw rollouts、328140 steps、256 chronological TD receipts、4 owner receipts。
- 输入绑定保持不变；旧 v03 源、旧 v112、API/guard/law/registry/F0/F1/dev_lock 不改。
- 第一次 stored audit 因字段名错误（期待 engineering_n_eval，实际是 evaluation_scenes）失败；第二次因仍期待旧 v112 motivation 文本失败；两次错误原样保留。
- 第三次定向修正版只改这两个审阅器绑定文字/字段，成功完成存储审阅；它没有重跑 native，也没有调用旧 checker/RFL。
- 这是 H64 的已知机制早期曲线复核，不是独立 seed 总体、全 family、正式 400/200、F1 资格或 V0.4 旧门槛。正收益、非空 L、APPLIED 状态都不是本次实验的必需门槛。

## 阶段结论

这次结果再次支持 V0.3 当前局部结论：在简单固定环境中，给定责任反馈后的合法持久更新能让模型更早处于较好表现，属于优化效率改善；即使 NoWrite 后来追平，也不抹掉早期优势。V0.3 不需要再因没有最终优势而追加同类实验。

随后按用户“V0.3后开启V0.4”的要求，转入 V0.4 局部工程；自动安排任务目前由用户关闭，本实验没有恢复或修改它。

完整机器索引见 result_summary.json 和 source_binding.json。
