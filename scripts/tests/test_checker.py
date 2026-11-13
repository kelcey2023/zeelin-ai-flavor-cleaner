from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
SKILL_ROOT = SCRIPTS.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checker = load_module("check_pre_ai_style")

    def test_flags_template_opening_and_generic_ending(self):
        text = (
            "随着人工智能的快速发展，行业正在发生变化。\n\n"
            "这不仅改变产品，更重塑生态。\n\n"
            "未来值得我们持续关注。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("template-opening", codes)
        self.assertIn("generic-ending", codes)

    def test_flags_known_unknown_inventory_ending(self):
        bad = (
            "7月18日，公司把月费从30美元降到22美元。\n\n"
            "目前能够确认的是，新价8月生效；至于机器人能解决多少问题，"
            "公司没有给出答案。"
        )
        good = (
            "7月18日，公司把月费从30美元降到22美元。\n\n"
            "年付客户要等到下一次续费，已经支付的费用不退。"
        )
        bad_codes = {item["code"] for item in self.checker.check_text(bad)}
        good_codes = {item["code"] for item in self.checker.check_text(good)}
        self.assertIn("inventory-ending", bad_codes)
        self.assertNotIn("inventory-ending", good_codes)

    def test_does_not_flag_concrete_news_lead(self):
        text = "7月18日晚，某公司把基础套餐从99元降到69元。第二天，老用户也能直接续费。"
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertNotIn("template-opening", codes)
        self.assertNotIn("delayed-event-entry", codes)

    def test_does_not_flag_concrete_event_lead_with_acreage(self):
        text = (
            "OpenAI把创作者请进纽约州北部占地140英亩的度假村，"
            "木屋、蜂蜜、养蜂课与ChatGPT Work同框。"
            "观众追问的是谁付房费、是否要求发帖，以及活动如何安排。"
        ) * 4
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertNotIn("delayed-event-entry", codes)

    def test_flags_editor_stage_directions(self):
        text = (
            "把它解读为某款模型失败都缺少依据。"
            "更可靠的判断来自用户能够感受到的产品层面。"
            "后续评价可以落在几个可观察指标上。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("editor-stage-direction", codes)

    def test_flags_evidence_boundary_as_editor_instruction(self):
        bad = "这两项信息需要分开理解。26名用户不能被写成已经受同一故障影响。"
        good = "现有日志没有显示未授权访问，但故障原因仍未公布。"
        bad_codes = {item["code"] for item in self.checker.check_text(bad)}
        good_codes = {item["code"] for item in self.checker.check_text(good)}
        self.assertIn("editor-stage-direction", bad_codes)
        self.assertNotIn("editor-stage-direction", good_codes)

    def test_flags_known_ai_metaphors_and_personification(self):
        text = (
            "搜索框已经变成答案入口。模型价格表只是第一层。"
            "这笔账要摆在台面上，同一笔账最终会开口说话。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("ai-metaphor", codes)
        self.assertIn("personification", codes)

    def test_flags_numbered_ledger_and_editorial_word_dissection(self):
        text = (
            "看Meta的人力变化，要算四本账。"
            "这句话，没有“已经”两个字。"
            "这里有三个不能省掉的限定：如果、理论上、未来。"
            "所以，“Google落后”必须加限定词。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("ai-metaphor", codes)
        self.assertIn("editorial-dissection", codes)

    def test_flags_known_collocation_problems(self):
        text = (
            "优选模型覆盖五个办公入口，还要把模型稳定地送到网页和API。"
            "体验差异越容易被放大。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("unnatural-collocation", codes)

    def test_flags_unspecified_shared_architecture(self):
        text = (
            "公司将食品生产、矿业和运输自动化业务整合到同一架构下。"
            "三类业务随后被放进同一结构。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("unclear-business-relationship", codes)

    def test_flags_money_written_as_the_agent_that_grants_ability(self):
        text = "17亿美元给了公司采购设备、招聘工程师和部署项目的能力。"
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("money-as-agent", codes)

    def test_flags_candidate_list_written_as_a_moving_product_state(self):
        text = "产品从候补名单走向正式推送。"
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("unclear-state-transition", codes)

    def test_flags_privacy_written_as_looking_at_one_switch(self):
        text = "医疗隐私不能只看一个开关。"
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("unclear-privacy-metaphor", codes)

    def test_flags_us_user_scope_added_to_chatgpt_health_push(self):
        text = "OpenAI近日开始向美国用户推送ChatGPT Health。"
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("misplaced-geographic-qualifier", codes)

    def test_accepts_specific_relationship_use_and_modifier_scope(self):
        text = (
            "三类业务共用一套调度软件。"
            "17亿美元用于采购设备、招聘工程师和部署项目。"
            "此前加入候补名单的用户开始收到推送。"
            "隐私审查分别核对数据收集、保存、授权、共享和删除规则。"
            "OpenAI近日开始向用户推送ChatGPT Health。"
            "符合条件的用户可以从侧边栏进入Health，连接Apple Health、"
            "美国医院的部分患者门户、One Medical或Function Health。"
        )
        forbidden = {
            "unclear-business-relationship",
            "money-as-agent",
            "unclear-state-transition",
            "unclear-privacy-metaphor",
            "misplaced-geographic-qualifier",
        }
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertFalse(codes & forbidden)

    def test_flags_preposition_lead_that_swallows_the_subject(self):
        codes = {
            item["code"]
            for item in self.checker.check_text("通过学习，使我取得了进步。")
        }
        self.assertIn("missing-subject", codes)

    def test_flags_blended_sentence_patterns(self):
        text = (
            "原因是系统超时造成的。"
            "公司本着稳定为原则，旨在降低成本为目的。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("mixed-construction", codes)

    def test_flags_redundant_fixed_expressions(self):
        text = "大约近五十名用户亲眼目睹了团队凯旋归来。项目长达三年之久。"
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("redundant-expression", codes)

    def test_flags_incorrect_negation_and_decrease_multiplier(self):
        text = "公司要避免故障不再发生，并把投诉量减少两倍。"
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("incorrect-negation", codes)
        self.assertIn("invalid-quantity", codes)

    def test_flags_correlative_and_two_sided_mismatches(self):
        text = "只有升级，就能使用。是否升级，是产品成功的关键。"
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("correlative-mismatch", codes)
        self.assertIn("two-sided-mismatch", codes)

    def test_flags_common_verb_object_collocation_errors(self):
        text = "团队提高习惯、开展目标，还要求员工树立节约。"
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("unnatural-collocation", codes)

    def test_accepts_corrected_language_error_examples(self):
        text = (
            "学习使我取得了进步。系统超时是主要原因。"
            "公司以稳定为原则，目标是降低成本。"
            "近五十名用户看到了变化。"
            "公司要避免故障再次发生，并把投诉量减少50%。"
            "只有升级，才能使用。是否升级，关系到产品能否成功。"
            "团队帮助用户养成习惯、制定目标，并树立节约意识。"
        )
        forbidden = {
            "missing-subject",
            "mixed-construction",
            "redundant-expression",
            "incorrect-negation",
            "invalid-quantity",
            "correlative-mismatch",
            "two-sided-mismatch",
            "unnatural-collocation",
        }
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertFalse(codes & forbidden)

    def test_language_rules_do_not_overflag_valid_near_matches(self):
        text = (
            "平台通过更新，使用户能够继续登录。"
            "原因是用户造成的误解，并非系统故障。"
            "团队开展围绕年度目标的讨论，提高养成良好习惯的效率。"
            "居民生活水平改善，一片巨大的暴雨云团正在向东移动。"
            "是否升级，是产品决策的关键因素。"
            "销量增至原来的两倍。"
        )
        forbidden = {
            "missing-subject",
            "mixed-construction",
            "unnatural-collocation",
            "two-sided-mismatch",
            "invalid-quantity",
        }
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertFalse(codes & forbidden)

    def test_accepts_user_preferred_collocations_and_conjunction(self):
        text = (
            "模型价格表只是一个方面。"
            "还要把模型稳定地应用到网页、手机、桌面端和API。"
            "不同终端的体验差异越大，用户越容易察觉。"
            "管理层的公开认错能够缓解部分情绪，但是用户信任最终仍要靠连续交付恢复。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertNotIn("unnatural-collocation", codes)
        self.assertNotIn("missing-conjunction", codes)
        self.assertNotIn("ai-metaphor", codes)

    def test_flags_production_leaks(self):
        text = (
            "事件先摆出来，再说普通人该怎么看。"
            "发布前自检：标题公式已经确定。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("production-leak", codes)

    def test_flags_source_leadin_layout_and_qa_markers(self):
        text = (
            "据TechCrunch报道，公司昨晚发布了新版本。"
            "配图2建议放在这里。facts checked。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("source-leadin", codes)
        self.assertIn("layout-marker", codes)
        self.assertIn("qa-marker", codes)

    def test_flags_generated_scene_disclaimer_and_generic_alt_label(self):
        text = (
            "AI生成的场景示意，不作为新闻现场照片。"
            "事件场景示意"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("layout-marker", codes)

    def test_flags_disclosure_checklist_pause_key_and_official_page_leadin(self):
        text = (
            "公司没有披露具体裁员人数，也没有公布AI将接管哪些工单。"
            "此次动作同时包含组织重整、返岗要求和技术投入，"
            "公司仍需用实际服务数据证明缩减后的团队完成了同等质量的工作。"
            "学生数据和教学角色没有谈清，试点先按下暂停键。"
            "学区公开页面写明，机器人不会录音录像。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("disclosure-checklist", codes)
        self.assertIn("awkward-event-label", codes)
        self.assertIn("proof-demand", codes)
        self.assertIn("template-cliche", codes)
        self.assertIn("source-leadin", codes)

    def test_accepts_direct_actor_action_result_for_same_facts(self):
        text = (
            "Uber把客服团队缩减10%，并要求部分远程员工到中心办公室。"
            "用户会直接感受到等待时间、转人工速度和申诉处理结果的变化。"
            "纽约州教育部门要求学区补交学生数据协议，并说明机器人在课堂上的用途。"
            "学区随后暂停试点。"
            "萨拉曼卡学区承诺，机器人不采集可识别学生身份的信息，"
            "不录音录像，也不向Realbotix传送数据。"
        )
        forbidden = {
            "disclosure-checklist",
            "awkward-event-label",
            "proof-demand",
            "template-cliche",
            "source-leadin",
        }
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertFalse(codes & forbidden)

    def test_flags_bare_official_page_as_the_sentence_subject(self):
        text = "页面写明，司机通常会在7个工作日内收到决定。"
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("source-leadin", codes)

    def test_flags_editorial_framing_and_abstract_landing_collocation(self):
        text = (
            "本文把它写成产品测试发现，法律结论与长期规则需要另行判断。"
            "版权判断落在具体表达上，责任落在平台的处置流程上。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("editorial-framing", codes)
        self.assertIn("abstract-landing", codes)

    def test_accepts_direct_facts_and_explicit_copyright_review_objects(self):
        text = (
            "一次产品测试发现了这个问题，法院尚未认定平台需要承担何种责任。"
            "判断是否侵权，要审查模型生成的具体内容、训练材料来源、授权范围和使用方式。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertNotIn("editorial-framing", codes)
        self.assertNotIn("abstract-landing", codes)

    def test_flags_product_reference_framing_and_abstract_return_to_text(self):
        text = (
            "本文只把它作为产品设计参照。"
            "版权审查仍要回到具体文本，最终复核需要回到文本本身。"
        )
        codes = {item["code"] for item in self.checker.check_text(text)}
        self.assertIn("editorial-framing", codes)
        self.assertIn("abstract-landing", codes)

    def test_flags_template_cliches_without_banning_plain_facts(self):
        bad = "未来已来，这场变革才刚刚开始，技术正在重塑生态。"
        good = "7月18日，公司把月费从99元降到69元。"
        bad_codes = {item["code"] for item in self.checker.check_text(bad)}
        good_codes = {item["code"] for item in self.checker.check_text(good)}
        self.assertIn("template-cliche", bad_codes)
        self.assertNotIn("template-cliche", good_codes)

    def test_finding_schema_is_explainable(self):
        findings = self.checker.check_text("随着技术的发展，未来值得持续关注。")
        self.assertTrue(findings)
        for finding in findings:
            self.assertTrue(
                {"code", "severity", "message", "excerpt", "offset", "rule_id", "source_ids"}
                .issubset(finding),
            )


if __name__ == "__main__":
    unittest.main()
