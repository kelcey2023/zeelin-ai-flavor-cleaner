# 表达库说明

## 四种性质

| 类别 | 如何处理 |
|---|---|
| 明确语法或概念错误 | 核对事实后修正 |
| 文风偏好 | 根据体裁与用户选择调整，不能宣称全民禁语 |
| 待核语境提示 | 检查完整句、相邻句、术语和引语 |
| 合成候选 | 仅供检索和测试，未审核前不进入默认规则 |

## 文件与数量

core-rules.jsonl是初始63条核心规则；后续允许增加、修正或移除。旧风格与语法模式位于检查器中，初始有47个正则，不能把它们与命中次数混算。

expansion-seeds.json含100个母句式、50种对象、20种属性，可生成100000条唯一表达。压缩候选和CSV在本地生成，不需要下载或加载全表才能使用技能。这些是合成组合，单条未逐一语义核验；不代表全网真实语料或100000条独立规则。

sources.json记录公开资料和匿名编辑反馈，明确资料能支持什么、不能支持什么。外部来源不为所有构造例句背书。

## 主要字段

- id：规则编号。
- expression、match_type：字面表达或匹配模式。
- severity：high或medium等优先级，不是AI概率。
- category、reason：问题类别和理由。
- rewrite_guidance：修改方向，不是自动替换文本。
- exceptions：可能成立的语境。
- source_ids、evidence_type：来源及证据性质。
- review_status：核心使用reviewed；合成候选保持pending。
- example_bad、example_good：构造的待审句与正常句，用于行为检查，不作为新闻事实。
- scope：规则适用范围（如有），需与general/zeelin模式的实际行为一致。
- family_id：候选所属母句式。同家族变体不是独立证据。
- auto_block：合成候选必须为false。

## 检索与验证

~~~sh
python scripts/lexicon.py query "上下文"
python scripts/lexicon.py validate
python scripts/lexicon.py build --csv-path candidates.csv
python scripts/lexicon.py query "搜索助手的使用成本" --kind candidate --limit 10
python scripts/lexicon.py validate --with-candidates
~~~

在项目根目录执行，或使用脚本的完整路径。写稿只检索所需的少量规则，不加载十万条全文。

## 候选入库条件

1. 有实际原句、上下文及可解释缺陷；不能只说“看着像AI”。
2. 分清个人偏好、语法错误和事实概念错误。
3. 有修改方向和一个应保留的正常反例；复杂规则应补充更多边界例。
4. 记录来源性质，真实例句和自行构造不得混淆。
5. 确认修改不反转否定、不改变数字、不扩大范围、不补写事实。
6. 测试后由维护者审核。默认不自动合并，不凭点赞数决定禁用。

匿名用户反馈可作为编辑偏好依据，但不是语言规范认证。报告误判与提出新规则同样重要。具体投稿方式见 [贡献指南](../CONTRIBUTING.md)。

