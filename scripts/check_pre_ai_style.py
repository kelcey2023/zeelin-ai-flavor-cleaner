#!/usr/bin/env python3
"""Flag explainable AI-flavor symptoms; never estimate an AI probability."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path


CORE_RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "lexicon" / "core-rules.jsonl"


class RuleBankError(ValueError):
    """The requested rule bank could not be checked reliably."""


# Conservative public default: contextual style preferences never hard-block.
GENERAL_HARD_CODES = frozenset({
    "missing-subject", "mixed-construction", "incorrect-negation",
    "invalid-quantity", "correlative-mismatch",
    "context-capacity-metaphor", "context-training-confusion",
    "actor-target-reversal", "bad-collocation-cost",
})
PROFILES = ("general", "zeelin")

Rule = tuple[str, str, re.Pattern[str], str]

RULES: tuple[Rule, ...] = (
    (
        "template-opening",
        "high",
        re.compile(r"^.{0,16}随着.{0,40}(?:发展|普及|演进|崛起|加速)"),
        "开头先写谁在何时做了什么，不先概括行业趋势。",
    ),
    (
        "template-opening",
        "high",
        re.compile(
            r"^.{0,20}(?:在.{0,16}的今天|当.{0,16}成为|近年来，?.{0,16}正在)"
        ),
        "删除通用时代背景，直接进入本文独有的事件。",
    ),
    (
        "generic-ending",
        "medium",
        re.compile(
            r"(?:未来|接下来|让我们).{0,30}(?:值得|仍需|持续)?(?:关注|期待|拭目以待)[。！!]?$"
        ),
        "结尾回到本文独有的人、价格、选择、结果或尚未解决的矛盾。",
    ),
    (
        "inventory-ending",
        "medium",
        re.compile(
            r"目前(?:已经)?(?:明确|能够确认)(?:的信息|的)?(?:包括|是)"
            r".{0,240}(?:尚未|仍未|没有).{0,120}"
            r"(?:答案|公布|明确|给出)",
            re.DOTALL,
        ),
        "不要在结尾重新盘点全部“已知/未知”；停在最后一项具体事实或一个直接后果。",
    ),
    (
        "symmetric-transition",
        "medium",
        re.compile(r"不仅.{0,80}(?:更|而且).{0,80}"),
        "检查对称转折是否只是模板；能直说两项事实时就拆开写。",
    ),
    (
        "symmetric-transition",
        "medium",
        re.compile(r"一方面.{0,120}另一方面"),
        "检查两方面是否真有并列关系，避免为了结构整齐而硬分层。",
    ),
    (
        "editor-stage-direction",
        "high",
        re.compile(
            r"(?:更可靠的判断来自|后续评价可以落在|把它解读为|"
            r"可以从以下几个维度|值得注意的是|不难发现|由此可见|"
            r"需要分开(?:理解|看)|不能被写成)"
        ),
        "删除写给编辑看的判断提示，直接陈述有来源的事实或判断。",
    ),
    (
        "editorial-framing",
        "high",
        re.compile(
            r"(?:(?:本文|文章|这篇文章|稿件|这段|这里)(?:只|仅)?(?:把|将)"
            r"[^。！？\n]{0,32}(?:写成|作为|当作)|本文(?:只|暂)?(?:按|作为)"
            r"[^。！？\n]{0,24}(?:处理|讨论))"
        ),
        "不要在正文解释作者准备怎样定性材料。直接写测试发现了什么，再写法院、监管机构或当事人的明确状态。",
    ),
    (
        "editorial-dissection",
        "high",
        re.compile(
            r"(?:这句话[，,][^。！？\n]{0,24}(?:没有|不含|少了)"
            r"[^。！？\n]{0,12}(?:个字|二字)|"
            r"这里有[一二三四五六七八九十0-9]+个不能省掉的限定|"
            r"(?:必须加|不能省掉的)限定(?:词)?)"
        ),
        "删除逐字讲解、限定词点名和课堂式提示。直接写原话的条件、时间范围与已发生结果。",
    ),
    (
        "evidence-process-commentary",
        "high",
        re.compile(
            r"(?:数字(?:是|确实是)(?:真的|真实(?:的)?|准确(?:的)?)"
            r"[，,；;。]?因果(?:没|没有|并不)(?:那么|这么)?简单|"
            r"(?:现在|目前)?还?没有(?:一个)?可靠(?:的)?比例|"
            r"(?:一个)?(?:经常|常常|反复)被引用的数字(?:也)?需要"
            r"(?:放回|回到)(?:原文|报告|语境))"
        ),
        "删除数字核验过程和审稿提醒。直接写统计主体、对象、时间、范围、定义，以及来源是否检验因果。",
    ),
    (
        "decorative-modifier",
        "high",
        re.compile(r"(?:工作|岗位|职位|职业)[^。！？；\n]{0,8}整齐(?:地)?(?:消失|减少|退出)"),
        "删除没有说明范围、速度或方式的修辞性副词。直接写岗位如何减少、合并、转移或消失。",
    ),
    (
        "empty-case-summary",
        "high",
        re.compile(r"变化(?:并不|不会|不是)?只朝(?:着)?一个方向(?:走|发展|发生)"),
        "案例已给出具体结果时，删除万能总结；若存在另一方向，直接补充第二项事实。",
    ),
    (
        "abstract-landing",
        "high",
        re.compile(
            r"(?:版权|侵权|法律|责任|判断|重点|关键|焦点|结论|问题|"
            r"风险|价值|影响|处罚|罚款|讨论|争议|审查|复核)"
            r"[^。！？；\n]{0,18}(?:落(?:在|到)|回到)[^。！？；\n]{1,32}"
        ),
        "不要把抽象判断、责任、审查或处罚写成“落在/落到/回到”某处。写清谁判断什么、审查什么、谁承担责任、谁受到处罚。",
    ),
    (
        "production-leak",
        "high",
        re.compile(
            r"(?:事件先摆出(?:来)?|普通人该怎么看|普通人该看懂什么|"
            r"盯.{0,8}个结果就够了|发布前自检|标题公式|标题池|"
            r"高点击版|稳妥版|搜索版|朋友圈版|知识库样本)"
        ),
        "删除写作过程、策划口令和版本标签；它们只供内部使用。",
    ),
    (
        "source-leadin",
        "medium",
        re.compile(
            r"(?:据[^，。；\n]{1,20}报道|[^，。；\s\n]{2,18}报道称|"
            r"外媒援引[^，。；\n]{0,20}(?:称|报道)|消息源称|"
            r"(?:公司|平台|企业|校方|学区|学校|监管机构|政府|法院)"
            r"(?:官网|官方网站|公开页面|公告|博客|文件)"
            r"(?:写明|显示|称|表示|说明)[，,]|"
            r"(?:公司|平台|企业|校方|学区|学校)"
            r"在(?:官网|官方网站|公开页面)(?:明确)?"
            r"(?:承诺|写明|说明)[，,]|"
            r"(?:官网|官方网站|公开页面|页面|公告|文件)"
            r"(?:写明|显示|称|表示|说明)[，,])"
        ),
        "直接写主体及其动作，例如“学区承诺……”；来源放在事实之后或文末，不用“公开页面写明”代替主体。",
    ),
    (
        "disclosure-checklist",
        "high",
        re.compile(
            r"(?:公司|平台|企业|校方|学区|学校|厂商)"
            r"[^。！？\n]{0,20}(?:没有|尚未|未)"
            r"(?:披露|公布|说明|交代)"
            r"[^。！？\n]{1,60}(?:也|同时)?(?:没有|尚未|未)"
            r"(?:披露|公布|说明|交代)"
        ),
        "不要连续盘点“没有披露/没有公布”。保留会改变判断的一项事实，或直接写已经发生的动作及其影响。",
    ),
    (
        "awkward-event-label",
        "high",
        re.compile(r"此次动作(?:同时)?(?:包含|涉及|包括)"),
        "“此次动作”是编辑标签。直接写公司调整了哪些岗位、办公安排或产品功能。",
    ),
    (
        "proof-demand",
        "high",
        re.compile(
            r"(?:公司|平台|企业|校方|学区|学校|团队|管理层)"
            r"[^。！？\n]{0,20}(?:仍需|需要|还要)"
            r"用[^。！？\n]{0,24}(?:数据|指标|结果)"
            r"[^。！？\n]{0,24}证明"
        ),
        "不要替编辑列出公司“需要用数据证明”的任务。写已经发生的服务变化，或写读者会直接遇到的等待、转人工和申诉结果。",
    ),
    (
        "layout-marker",
        "high",
        re.compile(
            r"(?:AI生成的场景示意，不作为新闻现场照片|事件场景示意|"
            r"配图(?:建议|\s*[0-9一二三四五])|建议位置|素材卡|影响卡|"
            r"判断图|链路图|时间线：节点分开排布|image2提示词|画面内容)"
        ),
        "删除排版、制图和素材说明，确认它们没有进入正文、标题或图片文字。",
    ),
    (
        "qa-marker",
        "high",
        re.compile(
            r"(?:facts? checked|source verified|QA passed|审核通过|"
            r"校验完成|事实已核|已核查)",
            re.IGNORECASE,
        ),
        "删除内部校验标记；校验结果应体现在事实准确性中，不写进成稿。",
    ),
    (
        "template-cliche",
        "high",
        re.compile(
            r"(?:未来已来|让我们拭目以待|这场变革才刚刚开始|"
            r"正在迎来前所未有的变革|从工具到伙伴|生产关系的重构|"
            r"价值跃迁|值得深思|某种程度上|"
            r"重塑生态|(?:先)?按下(?:了)?(?:试点的)?[“\"]?暂停键[”\"]?|"
            r"暂告一段落)"
        ),
        "删除通用口号、悬空大词和“暂停键”式制作腔，直接写谁暂停了什么、何时暂停以及触发动作。",
    ),
    (
        "contextual-terminology",
        "medium",
        re.compile(r"(?:新质生产力|底层逻辑)"),
        "先核对是否为政策原称、正式术语或有具体所指的概念。仅在没有新增信息、用大词代替解释时改写；不能见词就删。",
    ),
    (
        "ai-metaphor",
        "high",
        re.compile(
            r"(?:搜索框|对话框|模型|应用|平台).{0,10}(?:变成|成为).{0,8}"
            r"(?:答案|流量|能力|服务).{0,5}(?:入口|出口|引擎)"
        ),
        "不要把产品关系压成“X变成Y入口/引擎”；改写为具体功能和使用动作。",
    ),
    (
        "ai-metaphor",
        "high",
        re.compile(r"(?:价格表|融资|成本|产品).{0,10}(?:第一层|第二层)"),
        "不要用抽象“层”代替关系；按中文语境改成“一个方面”或直接说明。",
    ),
    (
        "model-layer-context",
        "medium",
        re.compile(r"模型[^。！？；\n]{0,10}(?:第一层|第二层)"),
        "核对“层”是否指实际网络层或已定义的架构层；真实技术分层可以保留，仅改写没有具体所指的比喻。",
    ),
    (
        "ai-metaphor",
        "high",
        re.compile(
            r"(?:同一笔账|这笔账|摆在台面(?:上)?|摊在台面(?:上)?|"
            r"第?[一二三四五六七八九十0-9]+本(?:是[^。！？；\n]{0,12})?账)"
        ),
        "删除账本和台面的套话，直接写成本、责任、价格或数据。",
    ),
    (
        "banned-same-wall",
        "high",
        re.compile(r"同一堵墙"),
        "禁用“同一堵墙”；根据事实直接说明具体限制、障碍或问题，不要换成另一种墙的比喻，也不要补造共同原因。",
    ),
    (
        "personification",
        "high",
        re.compile(
            r"(?:账|市场|数据|模型|产品|系统|价格|搜索框|资本|算法|技术)"
            r".{0,8}(?:开口|说话|沉默|呼吸|醒来|奔跑|长出|吞噬)"
        ),
        "正文叙述禁止新增或保留拟人表达；改成可观察的动作、数据或结果。有来源的直接引语另做人工核对。",
    ),
    (
        "unnatural-collocation",
        "high",
        re.compile(r"(?:覆盖|横跨).{0,12}(?:办公|产品|服务)?入口"),
        "“覆盖入口”搭配不当；改写为“在五个办公入口提供”或列出具体端。",
    ),
    (
        "unnatural-collocation",
        "high",
        re.compile(
            r"(?:把|将).{0,20}(?:稳定地)?送到.{0,24}(?:网页|手机|桌面端|API)"
        ),
        "软件能力不“送到”终端；按语义改成“应用到”“接入”或“提供”。",
    ),
    (
        "unnatural-collocation",
        "high",
        re.compile(r"体验差异越容易被放大"),
        "改成“体验差异越大”，不要把静态差异写成会被放大的对象。",
    ),
    (
        "unnatural-collocation",
        "medium",
        re.compile(r"(?:融资是新闻|成本差才是|覆盖五个办公入口)"),
        "检查名词与谓语搭配，并补足符合中文语境的逻辑关系。",
    ),
    (
        "missing-conjunction",
        "high",
        re.compile(r"公开认错能够.{0,30}，(?!但是)用户?信任最终仍"),
        "两个分句存在转折，请明确写出“但是”等连接词。",
    ),
    (
        "missing-subject",
        "high",
        re.compile(r"(?:^|[。！？；\n])\s*通过[^。！？；\n]{1,60}[，,]\s*(?:使|让)"),
        "“通过……使/让……”容易让介词结构吞掉主语；保留明确主语，或改成“……使……”。",
    ),
    (
        "mixed-construction",
        "high",
        re.compile(
            r"(?:原因是[^。！？；\n]{1,80}?(?:造成|导致|引起)的(?=[。！？；\n]|$)|"
            r"本着[^。！？；\n]{1,60}为原则|"
            r"旨在[^。！？；\n]{1,60}为目的)"
        ),
        "句子混用了两套结构；只能保留“原因是/由……造成”“本着/以……为原则”“旨在/以……为目的”中的一套。",
    ),
    (
        "redundant-expression",
        "high",
        re.compile(
            r"(?:凯旋归来|亲眼目睹|过分溺爱|非常酷爱|"
            r"大约近|约近|(?:大约|约)[^，。！？；\n]{1,12}左右|"
            r"长达[^，。！？；\n]{1,20}之久)"
        ),
        "删除重复表达；同一层意思只保留一次。",
    ),
    (
        "incorrect-negation",
        "high",
        re.compile(
            r"(?:避免|防止)[^，。！？；\n]{0,16}不再(?:发生|出现|重演)"
        ),
        "核对实际要防止的事件及否定层级；若要防止事件重演，应写“避免再次发生”，不能机械删否定词。",
    ),
    (
        "negation-context",
        "medium",
        re.compile(r"不能否认[^。！？；\n]{0,50}没有"),
        "把多重否定还原为肯定陈述后核对事实。“不能否认……没有……”本身可以成立，不得自动把“没有”改成“有”。",
    ),
    (
        "invalid-quantity",
        "high",
        re.compile(
            r"(?:减少|下降|降低|缩减|下跌)(?:了)?(?:约|近|大约)?\s*"
            r"(?:\d+(?:\.\d+)?|[两三四五六七八九十]+)\s*倍"
        ),
        "下降、减少不能用正倍数表示；改成下降比例、减少量或“降至原来的几分之几”，并核对原始数据。",
    ),
    (
        "correlative-mismatch",
        "high",
        re.compile(
            r"(?:只有[^。！？；\n]{1,60}[，,]\s*就|"
            r"(?:虽然|尽管)[^。！？；\n]{1,60}[，,]\s*(?:因此|所以))"
        ),
        "关联词关系不匹配；按真实关系使用“只有……才……”或“虽然……但是……”。",
    ),
    (
        "two-sided-mismatch",
        "medium",
        re.compile(
            r"(?:是否|能否)[^，。！？；\n]{0,50}[，,]\s*是"
            r"[^。！？；\n]{0,30}(?:成功|有效|达标|通过|完成|提高|改善)"
            r"[^。！？；\n]{0,12}(?:关键|条件|标准|基础)"
        ),
        "核对两种情况与结论是否对应；“是否达标是验收标准”等句子可以成立。只有实际逻辑不对应时才改写，不以两面词的数量判错。",
    ),
    (
        "unnatural-collocation",
        "high",
        re.compile(
            r"(?:提高(?:了)?(?:用户|客户|员工|团队|个人)?(?:的)?"
            r"(?:使用|工作|学习|消费)?习惯(?=[，。！？；\n]|$)|"
            r"开展(?:了)?[^，。！？；\n]{0,12}目标(?=[，。！？；\n]|$)|"
            r"树立(?:了)?节约(?!意识|观念)|"
            r"巨大的暴雨(?=[，。！？；\n]|$)|"
            r"歌声[^，。！？；\n]{0,8}响起了目光)"
        ),
        "主谓、动宾或修饰关系搭配不当；先确认主体和动作，再改成“提高水平、养成习惯、制定目标、树立节约意识”等自然搭配。",
    ),
    (
        "unclear-business-relationship",
        "high",
        re.compile(
            r"(?:整合|纳入|并入|放进|放到)[^，。！？；\n]{0,20}"
            r"(?:同一|统一)(?:架构|结构)(?:下|中)?"
        ),
        "不要用“同一架构/结构”代替实际关系；写清共用的技术平台、软件、组织或流程，信源未说明时不要补写。",
    ),
    (
        "money-as-agent",
        "high",
        re.compile(
            r"(?:\d+(?:\.\d+)?(?:亿|万)?(?:美元|元|人民币)|资金|融资|预算)"
            r"[^，。！？；\n]{0,12}(?:给了|给予|带给)"
            r"[^，。！？；\n]{0,30}(?:能力|底气|空间|资格)"
        ),
        "资金不能写成授予能力的行动者；有来源的用途写“资金用于……”，否则只写融资或现金变化。",
    ),
    (
        "unclear-state-transition",
        "high",
        re.compile(
            r"(?:产品|服务|功能|项目)?[^，。！？；\n]{0,4}"
            r"(?:从)?候补名单[^，。！？；\n]{0,12}"
            r"(?:走向|进入|转向|成为)[^，。！？；\n]{0,12}(?:正式)?推送"
        ),
        "候补名单包含用户或申请记录；写清谁加入名单、谁收到推送、谁执行推送。",
    ),
    (
        "unclear-privacy-metaphor",
        "high",
        re.compile(
            r"(?:医疗|健康|数据)?隐私[^，。！？；\n]{0,10}"
            r"(?:不能|不应|不是)[^，。！？；\n]{0,8}"
            r"(?:只)?(?:看|取决于)[^，。！？；\n]{0,5}(?:一个|某个)?开关"
        ),
        "不要把隐私压成“看一个开关”；只按信源写清数据收集、保存、授权、共享、删除或退出机制。",
    ),
    (
        "misplaced-geographic-qualifier",
        "high",
        re.compile(
            r"向美国用户[^，。！？；\n]{0,20}(?:推送|开放)"
            r"[^，。！？；\n]{0,24}(?:ChatGPT\s*Health|\bHealth\b)",
            re.IGNORECASE,
        ),
        "核对地域限定的真实对象；“美国医院的患者门户”不能扩大成“美国用户”。若资格确实限于美国，必须保留并注明来源。",
    ),
)

ABSTRACT_NOUN_PATTERN = re.compile(
    r"(?:生态|格局|维度|层面|价值|逻辑|趋势|变革|重塑|赋能|意义|本质|路径|图景|叙事|势能)"
)
EVENT_SIGNAL = re.compile(
    r"(?:\d{1,4}年|\d{1,2}月\d{1,2}日|\d+(?:\.\d+)?(?:元|美元|人|%|％|万|亿|英亩)|"
    r"发布|上线|下线|宣布|回应|降价|涨价|关闭|开放|推出|更新|删除|裁员|融资|收购|起诉)"
)


def split_paragraphs(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]


def _finding(
    code: str, severity: str, message: str, excerpt: str, offset: int
) -> dict[str, object]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "excerpt": excerpt,
        "offset": offset,
    }


def _load_bank(path: Path) -> list[tuple[dict[str, object], re.Pattern[str]]]:
    """Load only reviewed rules; never substitute the synthetic candidate bank."""
    required = {
        "id", "expression", "match_type", "severity", "category", "reason",
        "rewrite_guidance", "exceptions", "source_ids", "evidence_type", "review_status",
    }
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise RuleBankError(f"无法读取核心规则库 {path}：{exc}") from exc
    result = []
    ids = set()
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            rule = json.loads(line)
            if not isinstance(rule, dict):
                raise ValueError("规则必须为 JSON 对象")
            missing = required.difference(rule)
            if missing:
                raise ValueError(f"缺少字段：{', '.join(sorted(missing))}")
            if not isinstance(rule["id"], str) or not rule["id"] or rule["id"] in ids:
                raise ValueError("id 必须非空且唯一")
            ids.add(rule["id"])
            if rule["review_status"] != "reviewed":
                continue
            if rule["severity"] not in {"high", "medium", "low"}:
                raise ValueError("severity 必须为 high / medium / low")
            if rule["match_type"] not in {"literal", "regex"}:
                raise ValueError("match_type 必须为 literal / regex")
            if not isinstance(rule["expression"], str) or not rule["expression"]:
                raise ValueError("expression 必须为非空字符串")
            if not isinstance(rule["source_ids"], list):
                raise ValueError("source_ids 必须为数组")
            expression = rule["expression"]
            pattern = re.compile(re.escape(expression) if rule["match_type"] == "literal" else expression)
            if pattern.match(""):
                raise ValueError("规则不能匹配空字符串")
            result.append((rule, pattern))
        except (TypeError, ValueError, re.error) as exc:
            raise RuleBankError(f"核心规则库 {path} 第 {number} 行无效：{exc}") from exc
    if not result:
        raise RuleBankError(f"核心规则库 {path} 没有任何 reviewed 规则；检查尚未完成。")
    return result


def _bank_findings(text: str, path: Path) -> list[dict[str, object]]:
    result = []
    for rule, pattern in _load_bank(path):
        for match in pattern.finditer(text):
            item = _finding(
                str(rule["category"]), str(rule["severity"]),
                f'{rule["reason"]} {rule["rewrite_guidance"]}',
                match.group(0), match.start(),
            )
            item.update({
                "rule_id": rule["id"],
                "source_ids": rule["source_ids"],
                "evidence_type": rule["evidence_type"],
                "review_status": rule["review_status"],
                "exceptions": rule["exceptions"],
            })
            result.append(item)
    return result


def _protected_spans(text: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Return excluded code/URL spans and quotation spans without changing offsets.

    Quotation recognition is syntactic, not proof of attribution. Quoted findings
    remain visible and require a person to verify the quote or official term.
    """
    excluded: list[tuple[int, int]] = []
    quotes: list[tuple[int, int]] = []
    opened: tuple[str, int, int] | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if opened:
            marker, count, start = opened
            if re.match(rf"^ {{0,3}}{re.escape(marker)}{{{count},}}[ \t]*(?:\r?\n)?$", line):
                excluded.append((start, offset + len(line)))
                opened = None
        elif fence:
            opened = (fence.group(1)[0], len(fence.group(1)), offset)
        elif re.match(r"^ {0,3}>", line):
            quotes.append((offset, offset + len(line)))
        offset += len(line)
    if opened:
        excluded.append((opened[2], len(text)))
    for pattern in (
        r"(?<!`)(`+)(?!`)[^\n]*?(?<!`)\1(?!`)",
        r'https?://[^\s<>()\[\]"“”。，！？；]+',
    ):
        excluded.extend((m.start(), m.end()) for m in re.finditer(pattern, text))
    for pattern in (r"“[^”]*”", r"‘[^’]*’", r"「[^」]*」", r"『[^』]*』", r"《[^》]*》", r"〈[^〉]*〉", r'"[^"\n]*"'):
        quotes.extend((m.start(), m.end()) for m in re.finditer(pattern, text))
    return excluded, quotes


def _intersects(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < right and end > left for left, right in spans)


def _contextualize(
    finding: dict[str, object], text: str,
    excluded: list[tuple[int, int]], quotes: list[tuple[int, int]],
) -> dict[str, object] | None:
    start = int(finding["offset"])
    end = start + len(str(finding["excerpt"]))
    if _intersects(start, end, excluded):
        return None
    item = dict(finding)
    # Built-in legacy rules also have traceable identifiers, but no fabricated
    # web citations. User-defined rules preserve their own provenance fields.
    item.setdefault("rule_id", f'legacy:{item["code"]}')
    item.setdefault("source_ids", ["legacy-user-preferences"])
    item.setdefault("evidence_type", "existing_skill_rule")
    item.setdefault("review_status", "reviewed")
    trimmed = len(str(item["excerpt"])) - len(str(item["excerpt"]).lstrip(" \t\r\n。！？；"))
    inside_quote = any(left <= start + trimmed and end <= right for left, right in quotes)
    if inside_quote:
        if item["severity"] == "high":
            item["severity"] = "medium"
        item["context"] = "quotation_or_term"
        item["message"] = "位于引语、引用段或带引号术语中：核对原文和来源，不擅改引语；若只是修辞性加引号，仍需按正文规则复核。 " + str(item["message"])
    # Speech output is an observable function, not automatically personification.
    if item["code"] == "personification" and re.search(r"(?:模型|系统|技术|算法|产品)[^。！？；\n]{0,8}(?:开口|说话)", str(item["excerpt"])):
        item["severity"] = "medium"
        item["message"] = "先核对主语、宾语和语音功能。“识别人类说话的声音”中说话者是人；真实语音识别、生成或朗读功能也可成立。不能仅因技术主体附近出现“说话”判为拟人，确认只有空泛拟人时再改写。"
    if item["code"] == "correlative-mismatch" and re.match(
        r"只有(?:[一二两三四五六七八九十百千万\d几数]+|少数|极少|少量|很少|这么多|那么多|一点|一些)",
        str(item["excerpt"]),
    ):
        item["severity"] = "medium"
        item["message"] = "核对“只有”是否表示数量少，例如“只有一次失败，就让团队停止测试”是数量陈述，不是“只有……才……”条件关联。仅在实际表达必要或充分条件却配错关联词时修改。"
    return item


def _rule_findings(text: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for number, (code, severity, pattern, message) in enumerate(RULES, 1):
        for match in pattern.finditer(text):
            finding = _finding(code, severity, message, match.group(0), match.start())
            finding["rule_id"] = f"legacy:{code}:{number}"
            findings.append(finding)
    return findings


def _structural_findings(text: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    paragraphs = split_paragraphs(text)

    if len(text) >= 260:
        lead_offset = text.find(paragraphs[0]) if paragraphs else 0
        lead = text[lead_offset:lead_offset + 180]
        if lead and not EVENT_SIGNAL.search(lead):
            findings.append(
                _finding(
                    "delayed-event-entry",
                    "medium",
                    "前两段没有日期、数字或可观察动作；检查是否把背景写在事件前面。",
                    lead[:80],
                    lead_offset,
                )
            )

    if len(paragraphs) >= 4:
        lengths = [len(item) for item in paragraphs]
        mean = statistics.fmean(lengths)
        if mean >= 20 and statistics.pstdev(lengths) < max(6, mean * 0.12):
            findings.append(
                _finding(
                    "uniform-paragraphs",
                    "medium",
                    "连续段落长度过于整齐，检查是否每段都套用同一功能。",
                    paragraphs[0][:80],
                    text.find(paragraphs[0]),
                )
            )

    if len(text) >= 300:
        abstract_matches = list(ABSTRACT_NOUN_PATTERN.finditer(text))
        density = len(abstract_matches) * 1000 / len(text)
        if density >= 18:
            first = abstract_matches[0]
            findings.append(
                _finding(
                    "abstract-noun-density",
                    "medium",
                    "抽象名词偏密；把部分“生态、格局、维度、路径”换成具体主体和动作。",
                    first.group(0),
                    first.start(),
                )
            )

    symmetric = [
        finding
        for finding in _rule_findings(text)
        if finding["code"] == "symmetric-transition"
    ]
    if len(symmetric) >= 2:
        first = symmetric[0]
        findings.append(
            _finding(
                "consecutive-symmetric-transitions",
                "medium",
                "同一篇连续使用多组对称转折，结构可能显得由模板驱动。",
                str(first["excerpt"]),
                int(first["offset"]),
            )
        )
    return findings


def check_text(
    text: str, *, bank_path: Path | None = None, profile: str = "general"
) -> list[dict[str, object]]:
    """Return review hints without modifying text; profile controls style severity."""
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile!r}; choose general or zeelin")
    excluded, quotes = _protected_spans(text)
    characters = list(text)
    for start, end in excluded:
        for offset in range(start, end):
            if characters[offset] not in "\r\n":
                characters[offset] = "\0"
    scan_text = "".join(characters)
    findings = _rule_findings(scan_text)
    findings.extend(_structural_findings(scan_text))
    findings.extend(_bank_findings(scan_text, Path(bank_path) if bank_path is not None else CORE_RULES_PATH))
    unique = {}
    for finding in findings:
        finding = _contextualize(finding, text, excluded, quotes)
        if finding is None:
            continue
        finding["profile"] = profile
        finding["rule_scope"] = "general" if finding["code"] in GENERAL_HARD_CODES else "style_or_context"
        if profile == "general" and finding["severity"] == "high" and finding["code"] not in GENERAL_HARD_CODES:
            finding["severity"] = "medium"
            finding["message"] = "文风或语境提示，不是通用语法禁令。 " + str(finding["message"])
        key = (
            finding["rule_id"],
            finding["offset"],
            finding["excerpt"],
        )
        unique[key] = finding
    return sorted(
        unique.values(),
        key=lambda item: (int(item["offset"]), str(item["code"])),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Review Chinese writing with explicit, contextual rules; never estimate AI probability."
    )
    parser.add_argument("path", nargs="?", type=Path, help="UTF-8 text file")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--profile", choices=PROFILES, default="general",
                        help="general keeps style hints advisory; zeelin applies the optional editorial preferences")
    parser.add_argument(
        "--fail-on",
        choices=("none", "high", "medium"),
        default="none",
        help="return 1 when findings meet the chosen severity",
    )
    args = parser.parse_args(argv)

    if args.path:
        text = args.path.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    try:
        findings = check_text(text, profile=args.profile)
    except RuleBankError as exc:
        if args.as_json:
            print(json.dumps({"error": "rule_bank_unavailable", "message": str(exc)}, ensure_ascii=False))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    else:
        for item in findings:
            print(
                f"{item['severity'].upper()} {item['code']} "
                f"@{item['offset']}: {item['excerpt']} — {item['message']}"
            )
        print(f"RESULT: {len(findings)} finding(s)")

    severities = {str(item["severity"]) for item in findings}
    if args.fail_on == "high" and "high" in severities:
        return 1
    if args.fail_on == "medium" and severities.intersection({"high", "medium"}):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
