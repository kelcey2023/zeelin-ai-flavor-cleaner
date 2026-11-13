# Zeelin AI Flavor Cleaner

**中文去 AI 味与语病审校：定位问题表达，说明原因，保留正常反例。**

用于中文文章、科技稿和公众号内容的写作与审校。提供可直接安装的技能、无需联网的检查脚本，以及面向普通用户的投稿入口。

[提交问题表达](https://github.com/kelcey2023/zeelin-ai-flavor-cleaner/issues/new?template=expression.yml) · [报告误判](https://github.com/kelcey2023/zeelin-ai-flavor-cleaner/issues/new?template=false-positive.yml) · [补充改写案例](https://github.com/kelcey2023/zeelin-ai-flavor-cleaner/issues/new?template=rewrite.yml)

## 它解决什么问题

- 套话和机械结构：空泛总结、无依据的意义拔高、反复提醒、强行排比。
- 中文语病：搭配、成分、语序、指代、否定、数量与修饰范围。
- 技术解释失准：容量与材料混同、调用次数与费用混同、消耗对象缺失。
- 误判：保护技术术语、正常省略、直接引语、报告题名和代码。

检查结果是编辑线索，不是“AI检测”。本项目不输出AI概率，不承诺绕过检测器，不自动改写原文。

## 两个例子

| 待审表达 | 为什么需要检查 | 如何处理 |
|---|---|---|
| 上下文窗口像一次能摊开的材料。 | 容量与材料内容混作同类，比喻没有解释技术含义 | 查对应产品定义，写清单次处理的信息容量和计量口径 |
| 智能体为什么会多次消耗？ | 独立标题没有说明消耗对象 | 根据材料区分模型调用次数、token用量、额度、金额或时间 |

“智能体为什么会多次消耗输入token？”宾语完整，不能只因“多次消耗”判错。也不能从“三次模型调用”推出“费用增加三倍”。

例句只演示审校方法，不是任何具体产品的事实声明。

## 现在包含什么

- **63条初始核心规则**：含问题说明、修改方向、例外、来源性质和正反例。
- **47个既有检查模式**：保留可解释定位，公共模式将文风偏好作为语境提示。
- **24类语病、48组构造例句**：[中文语病硬审](references/chinese-language-errors.md)。
- **100种母句式及生成器**：可以重建100000条不重复的合成候选。
- **11项外部资料记录**：明确已读范围和适用边界，不把英语研究当中文禁词证据。

这些数字描述首发内容，后续以实际词库和版本记录为准。

### 关于“十万条”

100000 = 100种母句式 × 50类工具/系统名称 × 20种属性。

它们是合成的候选表达，**不是十万条独立验证的禁令，不是全网采集的十万条真实例句**。所有候选保持待审，不默认参与判错。仓库提供种子和生成工具，避免把大表格当成日常写作的上下文。

## 作为技能使用

1. 点击上方 **Code → Download ZIP** 并解压。
2. 将包含 SKILL.md 的项目目录命名为 zeelin-ai-flavor-cleaner，放入所用工具的技能目录。
3. 调用技能时提供原稿、信源和希望保留的风格。

例如：

> 使用 zeelin-ai-flavor-cleaner 审校这篇文章。先核对事实和适用范围，再处理中文语病与机械表达。不要新增经历、采访、产品功能或因果。

默认采用公共审校模式。需要本项目的公众号风格时，明确要求“使用 Zeelin 公众号风格”，并读取 [风格配置](profiles/zeelin-wechat.md)。

## 本地检查

要求 Python 3.11 或更新版本。核心工具只使用Python标准库，无需API密钥。

在项目目录中执行：

~~~sh
python scripts/check_pre_ai_style.py article.txt --json
python scripts/check_pre_ai_style.py article.txt --fail-on high
~~~

选择公众号风格：

~~~sh
python scripts/check_pre_ai_style.py article.txt --profile zeelin --json
~~~

- general：默认，语法与事实概念问题优先；文风偏好作为提示。
- zeelin：在语境保护基础上，启用更严格的公众号编辑偏好。
- high：必须核对和处理；不能为了清零破坏事实。
- medium：结合完整句和相邻句判断，合法用法可以保留。
- 引语和题名仍提示核对，不自动修改原话。给自己的套话加引号不能代替审校。

退出码：0表示未达到指定拦截级别；1表示有达到该级别的命中；2表示核心规则库不可用或无效。退出码0不等于文章不存在语病。

## 查词库、生成候选

~~~sh
python scripts/lexicon.py query "上下文"
python scripts/lexicon.py validate
python scripts/lexicon.py build --csv-path candidates.csv
python scripts/lexicon.py query "搜索助手的使用成本" --kind candidate --limit 10
python scripts/lexicon.py validate --with-candidates
~~~

CSV只用于查看和筛选；修改导出表不会直接改变生效规则。候选生成可离线复现。详细字段与审核条件见 [表达库说明](references/lexicon-guide.md)。

## 不会写代码，也能参与

在首页选择提交入口，提供原句、上下文和你觉得不妥的原因即可。修改建议和正常反例可以由维护者协助补齐。

审核流程：

**投稿 → 去重 → 核对语境与来源 → 补正反例 → 测试 → 收录或说明原因**

请特别欢迎“这句话其实没错”的反馈。收录数量和点赞数都不能替代语义判断。规则升级前需要维护者审核；候选不会自动变成禁用词。

详见 [贡献指南](CONTRIBUTING.md) 和 [贡献者](CONTRIBUTORS.md)。

## 验证

~~~sh
python -m unittest discover -s scripts/tests -p "test_*.py"
python scripts/lexicon.py build
python scripts/lexicon.py validate --with-candidates
~~~

自动测试用于检查已覆盖的行为，不能证明任意文章都不会误报。否定纠错、跨句省略和复杂引用仍需人工复核。

## 许可与来源

程序和相关代码采用 [MIT](LICENSE)。原创规则数据、技能说明与文档采用 [CC BY 4.0](DATA_LICENSE.md)。第三方文章、标准和研究仍适用各自权利；本项目只提供必要说明和来源链接，不重新许可第三方全文。

[研究资料](references/web-research.md)区分语言规范、研究、编辑经验和产品文档。网络链接可能更新，涉及当前产品机制时应重新核验。

