# V186：冻结决策层两因素定位

只读V185已经完成的8模型，新增H1、去经验评分修正、两者结合三种冻结执行；原完整/Q银行只读复用。24bank、3072回合，上限786432真实步，0训练。保留历史特征，no_empirical_override只关闭root的加法修正。

入口run_fixed.py，评价器evaluation_fixed.py。首次pure_check.py exit1：从AST提取函数时漏掉evaluate的torch.no_grad装饰器，未进入native/模型读取。原失败检查与evaluation.py/run.py字节保留；新纯检查pure_check_wire.py首次0验证固定评价器与原函数AST相同。不是训练失败或native重试。

解释须限定为冻结执行差异，不是训练消融或最终采用某变体。每个变体都跑，不按效果补种子或重跑。
