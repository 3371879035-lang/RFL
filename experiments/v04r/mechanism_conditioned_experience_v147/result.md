# V0.4：经验接收现在区分“实际经过的机制是否改变”

2026-11-07（Asia/Shanghai）

## 已实现的新接口

新增`conditioned_experience.py`：`ConditionedObservationLoop`在真实native观察通过原类型、issuer/consumer、主任务chronology、reference/参数和当前L-root检查后，比较该轨迹实际咨询的自有机制：P的base-option点，以及每一步prestate/a_cmd对应的X点。

使用真实source的protected I和消费者当前R，不从JSON恢复观察身份，不用成败/分数决定是否接收。原绑定检查和获准后普通TD计算体AST逐项保持；旧v144接口/所有执行字节不改。

新方法返回显式`ObservationTransferResult(applied, reason, observation_id, mechanism_changes)`：不适用时一次消费并返回拒收回执，0TD/0事务/0external-clock增量，不把主学习器关死；原始观察仍保留。合法经验正常学习一次。不是把旧None返回值悄悄说成没变。

## 两条真正的运行时来源

所有私有source均为原v144 nominal class，主失败调查内、K执行前真实注册；完整回合后真实签发NativeTrialObservation。新主类只是显式子类，既不伪造原类型，也不恢复旧issued身份。新contract/来源/capture，旧fixture/checker/native/银行不重跑。

| 实际观察与后续修改 | 旧接收器 | 新条件接收器 |
|---|---|---|
| 观察中RIGHT经旧X转为WAIT并SUCCESS；主学习器已删除这个RIGHT映射 | 接收，把RIGHT从约.395抬到.6275 | **拒收，保持约.395** |
| 观察为RIGHT/TRAP；主学习器只改了这条轨迹没咨询的WAIT映射 | 接收，RIGHT约-.07→-.545 | **正常接收，同样约-.07→-.545** |

第一条观察是真的成功，不是伪造数据；但那个成功发生在旧执行器下，不能直接解释为当前RIGHT的结果。第二条虽然失败，却仍适用于当前被观察的机制，应该保留学习。

因此这里拒绝的不是“成功”或“失败”，而是**跨已改变机制的不合适归用**。也没有把任何P/X变化都当作丢弃全部经验的理由。

## 接口修正不等于回报提高

每case的Legacy/Conditioned三个后续主任务raw完全相同。受影响case普通L值不同；未受影响case每任务后完整R+L/I也精确相同。**这轮没有测出任务回报提升，不能把工程合法性改进包装成总体收益。**

4条观察（包括1条明确拒收）都一次消费；实际4次重复请求全部拒绝，0native工作、状态不变。拒收主学习器没有关闭，仍实际执行后面两回合，最后SUCCESS，不是失败/不适用就科学STOP。

## 旧结果是否受影响

另做了严格限于这项新条件的stdlib只读记录核对：v144实际6条摄入、v145实际2条摄入均未发现所咨询自有P/X冲突——它们实际RIGHT经验没有经过当时修改的WAIT点。不是重跑旧checker/native，不从记录重建运行时身份，也不升级旧结果为全域资格。没有改写任何旧正/零/负证据。

## 真实工作与限制

native首次0，新stdlib检查首次0：16rollout/68step/47TX、148 canonical、333声明输入前后同。12主任务＋4全新真实私有来源；16原生普通更新＋3获准外部更新，共19数值TX＋19策略TX，另3checkpoint物化/2来源安装（4edits）/4实际X修正。拒收省去的只是该次2个普通学习事务，没有重跑K/重取draw；2.953秒是instrumented harness，不是生产计时。

原成功诊断0、alpha1/2、epsilon1/10不变。没有新keys/RNG/keyderive/DP/校准/正式collector/保留或旁损bank。原313/API/guard/law/registry/全部旧执行字节与85旧账本值/266 provenance保留，不宣称全面tracked审计。

资格只覆盖本轮两种真实X路径：代码有P比较，但没有实际P变更实验；外部环境变化、瞬态遮蔽、异常/partial总域、完整动力学一致性仍未资格。这里没有证明原B1 whole-law/完整keyed研究或通用强化反馈学习完成。后续反馈入口应使用明确的条件回执，而不是继续无条件灌入机制已变的经验。
