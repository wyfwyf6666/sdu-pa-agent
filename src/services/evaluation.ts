import axios from 'axios'
import { API_BASE_URL } from '@/config'
import {
  LeaderboardItem,
  UrbanGovEvalPerTaskResult,
  UrbanGovEvalSummary,
  UrbanGovEvalTask
} from '@/types/urbanGovEval'

export type {
  LeaderboardItem,
  UrbanGovEvalPerTaskResult,
  UrbanGovEvalSummary,
  UrbanGovEvalTask
}

const URBAN_GOV_EVAL_BASE = `${API_BASE_URL}/api/v1/urban-gov-eval`
const DOC_DOWNLOAD_BASE = `${API_BASE_URL}/api/v1/documents/download?filename=`

// -------------- 模拟数据，用于前端展示 --------------
const MOCK_TASKS: UrbanGovEvalTask[] = [
  {
    task_id: 'ug-001',
    title: '城市更新：老旧小区综合改造资金方案',
    domain: '城市更新',
    task_type: 'policy_analysis',
    language: 'zh',
    difficulty: 'medium',
    time_ref: '2024Q4',
    query:
      '结合近期老旧小区改造资金管理办法，明确补贴范围、配套资金比例、绩效考核与工期节点，形成街道可执行的方案。',
    deliverable: '资金方案+办理步骤+绩效节点',
    output_format: 'markdown',
    reference_report: 'ref/ug-001.md',
    criteria: [
      { id: 'c1', name: '政策点覆盖', description: '覆盖补贴对象、额度、申请流程', dimension: 'completeness', weight: 0.24, reference_score: 9, reference_comment: '官方公开稿' },
      { id: 'c2', name: '可操作性', description: '指导街道落地、分工清晰', dimension: 'actionability', weight: 0.2, reference_score: 8.5 },
      { id: 'c3', name: '表述准确性', description: '避免曲解条款', dimension: 'accuracy', weight: 0.18, reference_score: 9.2 },
      { id: 'c4', name: '条理与格式', description: 'Markdown 结构清晰', dimension: 'clarity', weight: 0.15, reference_score: 8.8 },
      { id: 'c5', name: '风险提示', description: '提示实施风险与兜底方案', dimension: 'risk', weight: 0.13, reference_score: 8.6 },
      { id: 'c6', name: '进度与验收', description: '进度与验收节点明确', dimension: 'actionability', weight: 0.1, reference_score: 8.4 }
    ],
    fact_expectation: {
      expected_pairs: 6,
      min_authority_ratio: 0.65,
      min_timeliness_ratio: 0.7
    },
    task_metrics: [{ metric: 'step_coverage', description: '办理步骤覆盖率', reference_value: 0.9 }]
  },
  {
    task_id: 'ug-002',
    title: '公共安全：地铁火灾 30 分钟联动演练',
    domain: '公共安全',
    task_type: 'scenario_simulation',
    language: 'zh',
    difficulty: 'hard',
    time_ref: '2024Q3',
    query:
      '模拟地铁火灾事故 30 分钟处置，输出指挥、消防、地铁公司、医院、交警的行动要点、依赖关系，并给出复盘指标。',
    deliverable: '按时间轴列出的行动清单',
    output_format: 'markdown',
    reference_report: 'ref/ug-002.md',
    criteria: [
      { id: 'c1', name: '时间线完整', description: '覆盖事故发现至疏散完毕的关键节点', dimension: 'completeness', weight: 0.28, reference_score: 9 },
      { id: 'c2', name: '多部门协调', description: '明确角色与依赖关系', dimension: 'coordination', weight: 0.28, reference_score: 8.7 },
      { id: 'c3', name: '可执行性', description: '指令具体、可落地', dimension: 'actionability', weight: 0.22, reference_score: 8.8 },
      { id: 'c4', name: '安全合规', description: '遵循预案与法规', dimension: 'compliance', weight: 0.12, reference_score: 9.1 },
      { id: 'c5', name: '复盘指标', description: '事后复盘指标与改进点', dimension: 'clarity', weight: 0.1, reference_score: 8.5 }
    ],
    fact_expectation: {
      expected_pairs: 7,
      min_authority_ratio: 0.7,
      min_timeliness_ratio: 0.7
    },
    task_metrics: [{ metric: 'timeline_density', description: '关键节点粒度', reference_value: 12 }]
  },
  {
    task_id: 'ug-003',
    title: '数字政务：政务热线工单提效',
    domain: '数字治理',
    task_type: 'process_optimization',
    language: 'zh',
    difficulty: 'medium',
    time_ref: '2024Q4',
    query: '针对市级 12345 热线重复工单、跨部门流转慢的问题，输出分级派单与督办策略，并给出考核指标。',
    deliverable: '流程优化方案+指标表',
    output_format: 'markdown',
    reference_report: 'ref/ug-004.md',
    criteria: [
      { id: 'c1', name: '流程拆解', description: '识别卡点与责任主体', dimension: 'completeness', weight: 0.3, reference_score: 8.8 },
      { id: 'c2', name: '指标设计', description: '时效、满意度、闭环率等指标合理', dimension: 'actionability', weight: 0.22, reference_score: 8.7 },
      { id: 'c3', name: '数据与治理', description: '利用数据赋能调度与预警', dimension: 'accuracy', weight: 0.2, reference_score: 8.9 },
      { id: 'c4', name: '协同机制', description: '跨部门协同与督办闭环', dimension: 'coordination', weight: 0.15, reference_score: 8.6 },
      { id: 'c5', name: '风险与合规', description: '隐私、安全与舆情风险提示', dimension: 'risk', weight: 0.13, reference_score: 8.4 }
    ],
    fact_expectation: {
      expected_pairs: 5,
      min_authority_ratio: 0.65,
      min_timeliness_ratio: 0.65
    },
    task_metrics: [{ metric: 'sla_improvement', description: '平均办结时长改善', reference_value: 0.2 }]
  },
  {
    task_id: 'ug-004',
    title: '交通出行：早高峰拥堵疏解方案',
    domain: '城市交通',
    task_type: 'scenario_simulation',
    language: 'zh',
    difficulty: 'hard',
    time_ref: '2024Q3',
    query: '针对主城区三条主干道早高峰拥堵，给出信号配时、公交优先、潮汐车道与诱导分流的组合方案。',
    deliverable: '按路口/时段的组合措施清单',
    output_format: 'markdown',
    reference_report: 'ref/ug-005.md',
    criteria: [
      { id: 'c1', name: '诊断准确', description: '识别瓶颈路口与时段', dimension: 'accuracy', weight: 0.25, reference_score: 8.9 },
      { id: 'c2', name: '组合可行性', description: '多措施联动的可行性与副作用', dimension: 'actionability', weight: 0.25, reference_score: 8.7 },
      { id: 'c3', name: '数据支撑', description: '是否给出可观测的量化指标', dimension: 'completeness', weight: 0.2, reference_score: 8.5 },
      { id: 'c4', name: '安全保障', description: '行人/公交/非机动车安全提示', dimension: 'risk', weight: 0.15, reference_score: 8.6 },
      { id: 'c5', name: '沟通与引导', description: '公众告知与引导策略', dimension: 'clarity', weight: 0.15, reference_score: 8.4 }
    ],
    fact_expectation: {
      expected_pairs: 6,
      min_authority_ratio: 0.62,
      min_timeliness_ratio: 0.65
    },
    task_metrics: [{ metric: 'congestion_reduction', description: '预测拥堵指数降低幅度', reference_value: 0.15 }]
  },
  {
    task_id: 'ug-005',
    title: '民生服务：跨省异地就医报销对话',
    domain: '医疗保障',
    task_type: 'multi_turn_qa',
    language: 'zh',
    difficulty: 'easy',
    time_ref: '2024Q2',
    query:
      '用户咨询跨省异地就医报销比例、备案流程及材料，开展 3 轮问答并给出办理清单和注意事项。',
    deliverable: '多轮问答+结尾清单',
    output_format: 'dialogue',
    reference_report: 'ref/ug-003.md',
    criteria: [
      { id: 'c1', name: '轮次连贯', description: '上下文衔接、澄清意图', dimension: 'coherence', weight: 0.28, reference_score: 8.9 },
      { id: 'c2', name: '政策准确', description: '报销比例、备案要求准确', dimension: 'accuracy', weight: 0.32, reference_score: 9.3 },
      { id: 'c3', name: '服务友好', description: '语气与提示友好', dimension: 'friendliness', weight: 0.2, reference_score: 8.5 },
      { id: 'c4', name: '总结清晰', description: '收尾清单明确可执行', dimension: 'clarity', weight: 0.2, reference_score: 8.7 }
    ],
    fact_expectation: {
      expected_pairs: 4,
      min_authority_ratio: 0.55,
      min_timeliness_ratio: 0.6
    },
    task_metrics: [{ metric: 'turn_relevance', description: '多轮相关性', reference_value: 0.9 }]
  },
  {
    task_id: 'ug-006',
    title: '环境治理：黑臭水体专项整治行动',
    domain: '环境治理',
    task_type: 'action_plan',
    language: 'zh',
    difficulty: 'medium',
    time_ref: '2024Q3',
    query:
      '针对城区三条黑臭水体，提出截污纳管、源头管控、应急抽排与长效运维的分阶段治理方案，并列出关键监测指标。',
    deliverable: '分阶段行动计划+指标表',
    output_format: 'markdown',
    reference_report: 'ref/ug-006.md',
    criteria: [
      { id: 'c1', name: '问题诊断', description: '污染成因与分段诊断', dimension: 'completeness', weight: 0.25, reference_score: 8.7 },
      { id: 'c2', name: '措施闭环', description: '源头、管网、应急、运维闭环', dimension: 'actionability', weight: 0.25, reference_score: 8.8 },
      { id: 'c3', name: '监测指标', description: 'COD、氨氮、黑臭感官等指标设置', dimension: 'accuracy', weight: 0.2, reference_score: 8.6 },
      { id: 'c4', name: '时序与责任', description: '阶段目标、责任单位与里程碑', dimension: 'clarity', weight: 0.15, reference_score: 8.5 },
      { id: 'c5', name: '风险管控', description: '汛期、溯源、舆情等风险提示', dimension: 'risk', weight: 0.15, reference_score: 8.4 }
    ],
    fact_expectation: {
      expected_pairs: 6,
      min_authority_ratio: 0.66,
      min_timeliness_ratio: 0.68
    },
    task_metrics: [{ metric: 'water_quality_drop', description: '黑臭指标下降幅度预期', reference_value: 0.25 }]
  },
  {
    task_id: 'ug-007',
    title: '社会治理：群租房矛盾化解与多方协商',
    domain: '社会治理',
    task_type: 'process_optimization',
    language: 'zh',
    difficulty: 'medium',
    time_ref: '2024Q3',
    query:
      '针对老城区群租房扰民、消防隐患与租户纠纷，设计街道、房管、消防、社区多方协商与执法流程，并给出居民沟通话术。',
    deliverable: '协同流程+沟通话术+风险提示',
    output_format: 'markdown',
    reference_report: 'ref/ug-007.md',
    criteria: [
      { id: 'c1', name: '角色分工', description: '街道/房管/消防/社区职责清晰', dimension: 'coordination', weight: 0.25, reference_score: 8.6 },
      { id: 'c2', name: '程序合规', description: '执法程序、告知书、取证合法', dimension: 'compliance', weight: 0.22, reference_score: 8.7 },
      { id: 'c3', name: '沟通引导', description: '居民沟通话术与安置提示', dimension: 'clarity', weight: 0.18, reference_score: 8.4 },
      { id: 'c4', name: '风险防控', description: '消防、信访、舆情风险预案', dimension: 'risk', weight: 0.2, reference_score: 8.5 },
      { id: 'c5', name: '执行可行', description: '时序安排与资源配置合理', dimension: 'actionability', weight: 0.15, reference_score: 8.5 }
    ],
    fact_expectation: {
      expected_pairs: 5,
      min_authority_ratio: 0.64,
      min_timeliness_ratio: 0.65
    },
    task_metrics: [{ metric: 'dispute_resolution', description: '预期纠纷化解比例', reference_value: 0.35 }]
  },
  {
    task_id: 'ug-008',
    title: '营商环境：园区招商政策包与审批提速',
    domain: '营商环境',
    task_type: 'policy_analysis',
    language: 'zh',
    difficulty: 'medium',
    time_ref: '2024Q4',
    query:
      '为高新技术产业园编制招商政策包，包含税收减免、用地支持、研发补贴、人才落户及一站式审批提速方案。',
    deliverable: '政策清单+审批提速方案',
    output_format: 'markdown',
    reference_report: 'ref/ug-008.md',
    criteria: [
      { id: 'c1', name: '政策完整', description: '税收/用地/补贴/人才覆盖', dimension: 'completeness', weight: 0.26, reference_score: 8.9 },
      { id: 'c2', name: '合规与边界', description: '符合上位法与财政约束', dimension: 'compliance', weight: 0.22, reference_score: 8.6 },
      { id: 'c3', name: '可执行性', description: '办理路径与责任部门清晰', dimension: 'actionability', weight: 0.22, reference_score: 8.7 },
      { id: 'c4', name: '竞争力', description: '对标兄弟城市，体现吸引力', dimension: 'accuracy', weight: 0.15, reference_score: 8.5 },
      { id: 'c5', name: '风险管控', description: '防范政策套利与负面舆情', dimension: 'risk', weight: 0.15, reference_score: 8.4 }
    ],
    fact_expectation: {
      expected_pairs: 5,
      min_authority_ratio: 0.65,
      min_timeliness_ratio: 0.65
    },
    task_metrics: [{ metric: 'approval_time_reduction', description: '审批平均提速比例', reference_value: 0.25 }]
  }
]

type MockModelKey =
  | 'qwen3-8b-it-t'
  | 'qwen3-8b-it-sft-t'
  | 'qwen3-8b-it-sft-dpo-t'
  | 'qwen3-8b-it-a'
  | 'qwen3-8b-it-sft-a'
  | 'qwen3-8b-it-sft-dpo-a'
  | 'qwen-max'

const NOW = () => new Date().toISOString()

// 模型档：轻微差异，让榜单有区分度
const MODEL_BASE = {
  'qwen3-8b-it-t': { race: 82.0, ca: 70.5, ec: 74.0, task: 77.5 },
  'qwen3-8b-it-sft-t': { race: 84.5, ca: 77.8, ec: 73.2, task: 80.2 },
  'qwen3-8b-it-sft-dpo-t': { race: 87.2, ca: 80.6, ec: 76.4, task: 79.0 },
  'qwen3-8b-it-a': { race: 83.1, ca: 73.5, ec: 81.2, task: 76.0 },
  'qwen3-8b-it-sft-a': { race: 85.6, ca: 77.4, ec: 84.5, task: 78.6 },
  'qwen3-8b-it-sft-dpo-a': { race: 88.4, ca: 81.8, ec: 86.7, task: 81.3 },
  'qwen-max': { race: 96.8, ca: 98.2, ec: 97.5, task: 91.4 }
} satisfies Record<MockModelKey, { race: number; ca: number; ec: number; task: number }>

const mockOverall = (m: { race: number; ca: number; ec: number; task: number }) =>
  Number(((m.race * 0.45 + m.ca * 0.2 + m.ec * 0.15 + m.task * 0.2)).toFixed(2))

const DEFAULT_BASE = { race: 82.0, ca: 75.0, ec: 73.0, task: 78.0 }

const MOCK_LEADERBOARD: LeaderboardItem[] = (Object.keys(MODEL_BASE) as MockModelKey[]).map(
  (k) => ({
    model_name: k,
    overall_score: mockOverall(MODEL_BASE[k]),
    race_score: MODEL_BASE[k].race,
    citation_accuracy: MODEL_BASE[k].ca,
    effective_citations_norm: MODEL_BASE[k].ec,
    task_metrics_norm: MODEL_BASE[k].task,
    updated_at: NOW()
  })
).sort((a, b) => b.overall_score - a.overall_score)

const buildMockSummary = (
  model: MockModelKey,
  tasks: UrbanGovEvalTask[] = MOCK_TASKS
): UrbanGovEvalSummary => {
  const base = MODEL_BASE[model]
  const domainMap: Record<
    string,
    { task_count: number; race: number; ca: number; ec: number; task: number }
  > = {}
  tasks.forEach((t) => {
    const delta = taskOffset(t.task_id)
    if (!domainMap[t.domain]) {
      domainMap[t.domain] = { task_count: 0, race: 0, ca: 0, ec: 0, task: 0 }
    }
    const entry = domainMap[t.domain]
    entry.task_count += 1
    entry.race += base.race + delta
    entry.ca += base.ca + delta / 2
    entry.ec += base.ec + delta / 2
    entry.task += base.task + delta
  })
  const domain_breakdown = Object.entries(domainMap).map(([domain, val]) => {
    const count = val.task_count || 1
    const race = val.race / count
    const ca = val.ca / count
    const ec = val.ec / count
    const task = val.task / count
    return {
      domain,
      task_count: count,
      race,
      citation_accuracy: ca,
      effective_citations_norm: ec,
      task_metrics_norm: task,
      overall: mockOverall({ race, ca, ec, task })
    }
  })

  return {
    model_name: model,
    generated_at: NOW(),
    normalization_method: 'ratio',
    task_count: tasks.length,
    race_score: base.race,
    citation_accuracy: base.ca,
    effective_citations_norm: base.ec,
    task_metrics_norm: base.task,
    overall_score: mockOverall(base),
    race_ci: { lower: base.race - 1.2, upper: base.race + 1.2 },
    citation_accuracy_ci: { lower: base.ca - 1.5, upper: base.ca + 1.5 },
    overall_ci: { lower: mockOverall(base) - 1.1, upper: mockOverall(base) + 1.1 },
    metrics: {
      sar: Number((0.78 + (base.ec - 70) / 200).toFixed(2)),
      tt: Number((0.74 + (base.task - 75) / 220).toFixed(2))
    },
    domain_breakdown,
    references: {
      judge_model: 'Qwen3-8B-Instruct',
      answer_model: model,
      normalization: 'ratio'
    }
  }
}

const mockCriterionScore = (criterionId: string, weight: number, base: number, delta: number) => {
  const target = Math.max(6.5, Math.min(9.7, base + delta))
  return {
    criterion_id: criterionId,
    weight,
    target_score: target,
    reference_score: base,
    gap: Number((target - base).toFixed(2)),
    normalized_score: target * weight
  }
}

const taskOffset = (taskId: string) => {
  // 稳定的轻微扰动，让不同题目分数有差异
  const seed = taskId.split('').reduce((acc, ch) => acc + ch.charCodeAt(0), 0)
  return ((seed % 7) - 3) * 0.3
}

const domainPlaybook: Record<
  string,
  { context: string; strategies: string[]; risks: string[]; indicators: string[] }
> = {
  城市更新: {
    context: '老旧片区更新需兼顾“资金统筹—居民协商—物业接管”三条线，保障改造可持续。',
    strategies: [
      '梳理拆改建台账与“一户一策”，同步居民议事与设计复核',
      '财政补助+居民共建+社会资本分层投入，明确审批链条',
      '物业接管与社区网格联动，约定巡检与满意度回访'
    ],
    risks: ['征收补偿争议', '施工扰民与安全隐患', '竣工后运维责任不清'],
    indicators: ['改造覆盖率≥90%', '居民满意度≥85%', '物业问题闭环时长≤2天']
  },
  公共安全: {
    context: '极端天气或突发事件处置需形成“预警-指挥-响应-复盘”闭环，避免信息割裂。',
    strategies: [
      '建立“预警-指挥-响应”三级联动与事件刻度表',
      '多部门同频演练：消防、水务、交警、街道同步通信',
      '明确信息公开与舆情引导，保留复盘数据'
    ],
    risks: ['部门协同延迟', '应急物资不足', '公众恐慌与谣言扩散'],
    indicators: ['响应时间≤5分钟', '泵站启停成功率≥95%', '舆情投诉24小时内反馈率']
  },
  数字治理: {
    context: '数字政务须以工单驱动跨部门协同，突出“数据支撑+指标监测+流程固化”。',
    strategies: [
      '依托12345与电子证照汇聚数据，构建跨部门工单总线',
      '设置流程时限监控与风险预警，沉淀标准处方库',
      '提供“可视化驾驶舱+线下督办”双轨推进'
    ],
    risks: ['数据共享壁垒', '重复建设导致体验割裂', '算法黑箱引发质疑'],
    indicators: ['重复工单下降≥30%', '跨部门平均时长下降≥20%', '线上满意度≥90%']
  },
  城市交通: {
    context: '城市交通调度强调“潮汐研判-信号协同-公共运力保障”，需强化多部门联动。',
    strategies: [
      '根据潮汐流量编制滚动信号配时与公交加班方案',
      '构建“路警地铁”联合指挥，与气象、城管共享积水点',
      '建立重大节点“限流+接驳+信息推送”组合拳'
    ],
    risks: ['指挥口径不一致', '排水能力不足', '群众绕行指引滞后'],
    indicators: ['平均车速提升≥10%', '积水点处置≤30分钟', '重大客流零滞留']
  },
  医疗保障: {
    context: '医疗保障诉求多关涉备案、报销与窗口服务，需兼顾制度口径与群众体验。',
    strategies: [
      '梳理异地就医备案、比例、材料清单并做流程图',
      '建立“医保+卫健+医院”协同，设置绿色窗口',
      '通过智能客服与线下宣讲同步解答高频疑问'
    ],
    risks: ['政策口径频繁调整', '跨省结算延迟', '隐私数据保护不足'],
    indicators: ['备案办理时长≤2个工作日', '报销到账≤10个工作日', '满意度≥90%']
  },
  环境治理: {
    context: '环境治理需要“溯源-治理-运维”一体推进，强化监测与公众参与。',
    strategies: [
      '先溯源污染与水文，制定“源头截污+雨污分流+生态修复”路径',
      '落地监测因子与责任分解，明确运维与巡查频次',
      '建立公众监督与信息公开，配套预警阈值'
    ],
    risks: ['汛期突发溢流', '跨部门责任不清', '长期运维投入不足'],
    indicators: ['COD/氨氮达标率≥95%', '公众投诉下降≥40%', '监测设备完好率≥98%']
  },
  社会治理: {
    context: '社会治理场景强调基层统筹、群众参与与安全合规的闭环处理。',
    strategies: [
      '用“街道党工委+综治中心”统筹执法、调解与宣传',
      '建立居民议事与心理疏导机制，提供差异化安置方案',
      '制定入户排查、消防整改、法律文书的闭环流程'
    ],
    risks: ['群体性事件升级', '取证不规范', '舆情负面发酵'],
    indicators: ['纠纷调解成功率≥85%', '消防隐患整改率≥95%', '舆情响应≤2小时']
  },
  营商环境: {
    context: '营商类诉求需突出“政策兑现+审批提速+服务跟踪”，保障承诺可执行。',
    strategies: [
      '梳理税收、用地、人才等政策包，形成“拿地即开工”清单',
      '搭建一站式审批枢纽，压缩环评、能评、施工许可时长',
      '建立企业服务经理制度，定期复盘诉求'
    ],
    risks: ['政策兑现滞后', '审批信息孤岛', '招商承诺与执行脱节'],
    indicators: ['审批提速≥30%', '政策兑现率≥95%', '企业满意度≥90%']
  },
  默认: {
    context: '综合类政务事项需要明确责任链路与进度节点，强化信息公开与复盘。',
    strategies: [
      '梳理政策依据与责任单位，形成执行路线图',
      '强化数据支撑与过程监控，设置量化指标',
      '建立反馈闭环与风险提示'
    ],
    risks: ['资源未统筹', '沟通机制缺失', '评估缺乏依据'],
    indicators: ['关键任务按期完成', '投诉闭环率≥90%', '信息公开及时率≥95%']
  }
}

const domainSources: Record<string, string[]> = {
  城市更新: [
    '城市更新治理模式的比较与选择.pdf',
    '城市更新治理模式政策利弊及原因分析——基于广州、深圳、佛山三地城市更新制度的比较.pdf',
    '城市更新和风貌保护的城市设计与城市治理实践.pdf'
  ],
  公共安全: [
    '城市公共安全协同治理的模式构建与路径探索.pdf',
    '国务院办公厅关于印发国家城市轨道交通运营突发事件应急预案的通知.pdf',
    '国务院办公厅关于保障城市轨道交通安全运行的意见.pdf'
  ],
  数字治理: [
    '《智慧城管——杭州市上城区智能化城市治理研究》大数据时代社会治理智能化研究.pdf',
    '城市间环境治理合作：行动、网络及其演变——基于长三角30个城市的府际协议数据分析.pdf',
    '财政分权、政策协同与大气污染治理效率——基于京津冀及周边地区城市群面板数据分析.pdf'
  ],
  城市交通: [
    '城市交通拥堵治理模式理论的新进展.pdf',
    '城市交通拥堵的成因及治理问题研究.pdf',
    '国务院办公厅关于进一步加强城市轨道交通规划建设管理的意见.pdf'
  ],
  医疗保障: [
    '国务院办公厅关于城市公立医院综合改革试点的指导意见.pdf',
    '城市市容和环境卫生管理条例.pdf',
    '中华人民共和国城市居民委员会组织法.pdf'
  ],
  环境治理: [
    '城市黑臭水体污染现状、治理技术与对策.pdf',
    '城市河道生态治理综述.pdf',
    '“碳中和”视角下的城市治理与可持续发展.pdf'
  ],
  社会治理: [
    '“三方联动”视阈下城市社区治理再思考——基于武汉创新社区治理样本的分析.pdf',
    '“党建+”在城市社区治理中的独特功能和实现形式.pdf',
    '城市基层治理的社会化机制——以深圳市Z街“网格化管理社会化服务”项目为例.pdf'
  ],
  营商环境: [
    '“互联网+政务服务”平台如何优化城市营商环境？——基于互动治理的视角.pdf',
    '城市工业园区存量更新中的利益博弈与治理创新——深圳、常州高新区两种模式的比较_.pdf',
    'PPP模式下政府和民营企业的契约关系及其治理——以中国城市基础设施PPP为例.pdf'
  ]
}

const DEFAULT_SOURCE = '2000年以来城市治理重心下移：研究脉络与发展动向——以CNKI检索论文为研究对象.pdf'

const docTitleFromName = (filename: string) => filename.replace(/\.[^.]+$/, '')

const policyKeywords = ['国务院', '政府', '通知', '意见', '条例', '法规', '批复', '规划', '实施方案', '指导', '准则', '办法']

const inferAuthorityByName = (filename: string) =>
  policyKeywords.some((keyword) => filename.includes(keyword))

const inferTimelinessByName = (filename: string) => {
  const match = filename.match(/20(\d{2})/)
  if (!match) return false
  const year = Number(`20${match[1]}`)
  const currentYear = new Date().getFullYear()
  return year >= currentYear - 4
}

const MODEL_STYLE_CONFIG: Record<
  string,
  { header: string; summary: string; warning: string; follow: string }
> = {
  'qwen3-8b-it-t': {
    header: '【街道统筹专员批示】',
    summary: '请依照既定责任链条执行，强调过程留痕与节点追溯。',
    warning: '注意资金拨付与施工进度同步，防止“只建不管”断点。',
    follow: '纳入周调度与月度评估，及时通报办理情况。'
  },
  'qwen3-8b-it-sft-t': {
    header: '【政策研究室意见】',
    summary: '建议以结构化表格梳理目标、责任、指标，方便横向复制。',
    warning: '警惕指标体系与基层执行标准不匹配导致的反复修改。',
    follow: '同步编制模板文本，供街乡复制推广。'
  },
  'qwen3-8b-it-sft-dpo-t': {
    header: '【风险专班提示】',
    summary: '围绕“现状—短板—举措”提出分析型意见，突出瓶颈点。',
    warning: '重点关注跨部门联动滞后及演练复盘缺失的风险。',
    follow: '按季度滚动复盘，必要时提级协调解决卡点。'
  },
  'qwen3-8b-it-a': {
    header: '【12345 受理回复】',
    summary: '以群众视角说明办理流程，突出便民举措与材料清单。',
    warning: '避免宣传口径与实际办理路径不一致引发投诉。',
    follow: '保持热线、门户公告与窗口同步更新。'
  },
  'qwen3-8b-it-sft-a': {
    header: '【质控督导反馈】',
    summary: '按照查检结果给出整改清单，突出可追溯性与质控节点。',
    warning: '关注验收标准、资料归档不到位导致的复审风险。',
    follow: '执行“签字背书+影像留痕”，确保整改闭环。'
  },
  'qwen3-8b-it-sft-dpo-a': {
    header: '【改革牵引建议】',
    summary: '聚焦牵引性任务，强调对比“现状 vs 目标”并提出牵引动作。',
    warning: '防止指标导向与实际改善脱节，及时纠偏。',
    follow: '将绩效结果与下一批次资源分配挂钩。'
  },
  'qwen-max': {
    header: '【市政府办公厅秘书处批示】',
    summary: '结合全市运行调度情况，统筹部门、街道与平台支撑，形成批示性意见。',
    warning: '统筹信息发布节奏与现场调度，预防群体性风险。',
    follow: '依托城市运行平台动态监测并形成日报。'
  },
  default: {
    header: '【综合专班意见】',
    summary: '请按照职责链条推进事项，确保数据留痕与责任明确。',
    warning: '注意部门协同与信息公开不到位引发的二次投诉风险。',
    follow: '纳入“周调度+月通报”机制，必要时提级协调。'
  }
}

const buildMockCandidateAnswer = (
  task: UrbanGovEvalTask,
  modelName: string,
  base: { race: number; ca: number; ec: number; task: number },
  referenceDocs: string[]
) => {
  const play = domainPlaybook[task.domain] ?? domainPlaybook['默认']
  const style = MODEL_STYLE_CONFIG[modelName] ?? MODEL_STYLE_CONFIG['default']
  const docs = referenceDocs.length > 0 ? referenceDocs : [DEFAULT_SOURCE]
  const docLines = docs.map((doc, idx) => `【资料${idx + 1}】${docTitleFromName(doc)}`).join('\n')
  const measures = play.strategies.map((line) => `- ${line}`).join('\n')
  const indicators = play.indicators.map((line) => `- ${line}`).join('\n')
  const risks = ['- ' + style.warning, ...play.risks.map((line) => `- ${line}`)].join('\n')
  const follow = [`- ${style.follow}`, '- 将进展纳入“周调度+月通报”机制并及时公开信息'].join('\n')

  return [
    `${style.header}`,
    `一、事项概览`,
    `- 事项名称：${task.title}`,
    `- 输出要求：${task.deliverable}`,
    `- 时间参考：${task.time_ref}`,
    `- 情况说明：${play.context}`,
    `- 任务诉求：${task.query}`,
    `二、办理要点`,
    measures,
    `三、指标与支撑`,
    indicators,
    `四、风险提示`,
    risks,
    `五、后续安排`,
    follow,
    `六、依据资料`,
    docLines
  ].join('\n')
}

const buildMockPerTask = (
  model: string,
  task: UrbanGovEvalTask,
  baseOverride?: { race: number; ca: number; ec: number; task: number }
): UrbanGovEvalPerTaskResult => {
  const base = baseOverride || (isMockModel(model) ? MODEL_BASE[model] : DEFAULT_BASE)
  const offset = taskOffset(task.task_id)
  const sources = domainSources[task.domain] ?? [DEFAULT_SOURCE]
  const criterionScores = task.criteria.map((c) => {
    const delta = (Math.random() - 0.5) * 1.2 + offset
    const cs = mockCriterionScore(c.id, c.weight, c.reference_score, delta)
    return {
      ...cs,
      name: c.name,
      dimension: c.dimension,
      explanation: `${c.dimension}：模型输出较参考${cs.gap >= 0 ? '提升' : '略低'}，关键要点 ${
        cs.gap >= 0 ? '覆盖充分' : '有遗漏'
      }。`,
      reference_comment: c.reference_comment
    }
  })
  const playForFacts = domainPlaybook[task.domain] ?? domainPlaybook['默认']
  const factPairs = Array.from({ length: task.fact_expectation?.expected_pairs ?? 4 }).map((_, idx) => {
    const filename = sources[idx % sources.length]
    const citation = `${DOC_DOWNLOAD_BASE}${encodeURIComponent(filename)}`
    const normalized = filename
    const docTitle = docTitleFromName(filename)
    const strategy = playForFacts.strategies[idx % playForFacts.strategies.length]
    const support = idx % 5 !== 4
    const authority = inferAuthorityByName(filename)
    const timeliness = inferTimelinessByName(filename)
    const misuse = !support
    const baseNote = support ? '引用内容与方案要点一致' : '该引用与题目关键点不完全匹配，建议人工复核'
    return {
      statement: `【引用《${docTitle}》】${strategy}，支撑“${task.title}”的执行路径。`,
      citation,
      normalized_citation: normalized,
      support,
      authority,
      timeliness,
      misuse,
      notes: `${baseNote}；知识库引用《${docTitle}》`
    }
  })

  const factTotal = factPairs.length
  const supported = factPairs.filter((p) => p.support).length
  const authoritative = factPairs.filter((p) => p.authority && p.support).length
  const timely = factPairs.filter((p) => p.timeliness && p.support).length
  const misuse = factPairs.filter((p) => p.misuse).length

  const raceScore = base.race + (Math.random() * 2 - 1) + offset
  const ratioScore = raceScore
  const relativeScore = raceScore - 1.5

  return {
    model_name: model,
    task_id: task.task_id,
    generated_at: NOW(),
    normalization_method: 'ratio',
    race: {
      method: 'auto-judge',
      target_total: raceScore,
      reference_total: task.criteria.reduce((sum, c) => sum + c.reference_score * c.weight, 0),
      normalized_score: Number(raceScore.toFixed(2)),
      ratio_score: Number(ratioScore.toFixed(2)),
      relative_advantage_score: Number(relativeScore.toFixed(2)),
      dimension_scores: [
        { dimension: 'completeness', weighted_score: ratioScore * 0.4, normalized_score: ratioScore * 0.4 },
        { dimension: 'actionability', weighted_score: ratioScore * 0.3, normalized_score: ratioScore * 0.3 },
        { dimension: 'accuracy', weighted_score: ratioScore * 0.2, normalized_score: ratioScore * 0.2 },
        { dimension: 'clarity', weighted_score: ratioScore * 0.1, normalized_score: ratioScore * 0.1 }
      ]
    },
    criteria: criterionScores,
    fact: {
      total_pairs: factTotal,
      supported_pairs: supported,
      authoritative_pairs: authoritative,
      timely_pairs: timely,
      misuse_pairs: misuse,
      citation_accuracy: Number(((supported / factTotal) * 100).toFixed(2)),
      effective_citations: supported,
      source_authority_ratio: Number(((supported ? authoritative / supported : 0) * 100).toFixed(2)),
      timeliness_ratio: Number(((supported ? timely / supported : 0) * 100).toFixed(2)),
      misuse_rate: Number(((misuse / factTotal) * 100).toFixed(2)),
      pairs: factPairs
    },
    task_metrics: task.task_metrics.map((m) => {
      const val = m.reference_value ?? 1
      const simulated = val * (0.9 + Math.random() * 0.2)
      return {
        metric: m.metric,
        description: m.description,
        reference_value: m.reference_value,
        value: Number(simulated.toFixed(3)),
        normalized: Number((base.task + (Math.random() - 0.5) * 2).toFixed(2)),
        direction: 'higher_is_better'
      }
    }),
    metadata: {
      title: task.title,
      domain: task.domain,
      task_type: task.task_type,
      difficulty: task.difficulty,
      time_ref: task.time_ref,
      reference_report: task.reference_report,
      candidate_answer: buildMockCandidateAnswer(task, model, base, sources.slice(0, 3)),
      reference_answer_excerpt: `参考报告 ${task.reference_report} 聚焦 ${task.deliverable} 与 ${task.query.slice(0, 40)}…`,
      prompt_messages: [
        { role: 'system', content: '你是熟悉城市治理和公共管理的专家，需输出可执行方案并标注风险。' },
        { role: 'user', content: task.query }
      ],
      tokens: 3800 + Math.round(Math.random() * 400),
      latency_ms: 1200 + Math.round(Math.random() * 300),
      judge_model: 'Qwen3-8B-Instruct'
    }
  }
}

const MOCK_SUMMARY: Record<MockModelKey, UrbanGovEvalSummary> = {
  'qwen3-8b-it-t': buildMockSummary('qwen3-8b-it-t', MOCK_TASKS),
  'qwen3-8b-it-sft-t': buildMockSummary('qwen3-8b-it-sft-t', MOCK_TASKS),
  'qwen3-8b-it-sft-dpo-t': buildMockSummary('qwen3-8b-it-sft-dpo-t', MOCK_TASKS),
  'qwen3-8b-it-a': buildMockSummary('qwen3-8b-it-a', MOCK_TASKS),
  'qwen3-8b-it-sft-a': buildMockSummary('qwen3-8b-it-sft-a', MOCK_TASKS),
  'qwen3-8b-it-sft-dpo-a': buildMockSummary('qwen3-8b-it-sft-dpo-a', MOCK_TASKS),
  'qwen-max': buildMockSummary('qwen-max', MOCK_TASKS)
}

const MOCK_PER_TASK: Record<string, UrbanGovEvalPerTaskResult> = {}
;(Object.keys(MOCK_SUMMARY) as MockModelKey[]).forEach((model) => {
  MOCK_TASKS.forEach((task) => {
    const cacheKey = `${model}::${task.task_id}`
    MOCK_PER_TASK[cacheKey] = buildMockPerTask(model, task)
  })
})

function isMockModel(model: string): model is MockModelKey {
  return (MODEL_BASE as Record<string, unknown>)[model] !== undefined
}

function createMockPerTask(modelName: string, taskId: string) {
  const task = MOCK_TASKS.find((t) => t.task_id === taskId) ?? MOCK_TASKS[0]
  if (!task) return null
  const result = buildMockPerTask(modelName, task)
  const cacheKey = `${modelName}::${taskId}`
  MOCK_PER_TASK[cacheKey] = result
  return result
}

const mergeWithMockTasks = (remote: UrbanGovEvalTask[] | undefined) => {
  // 1) 先合并去重，强制包含所有 Mock 题目
  const merged: UrbanGovEvalTask[] = []
  const idSet = new Set<string>()
  ;(remote ?? []).forEach((t) => {
    if (!idSet.has(t.task_id)) {
      merged.push(t)
      idSet.add(t.task_id)
    }
  })
  MOCK_TASKS.forEach((t) => {
    if (!idSet.has(t.task_id)) {
      merged.push(t)
      idSet.add(t.task_id)
    }
  })

  // 2) 按领域分组，做轮询拣选，保证类别分布更均衡
  const domainBuckets: Record<string, UrbanGovEvalTask[]> = {}
  merged.forEach((task) => {
    if (!domainBuckets[task.domain]) domainBuckets[task.domain] = []
    domainBuckets[task.domain].push(task)
  })
  Object.values(domainBuckets).forEach((list) => {
    // 轻度洗牌每个领域
    for (let i = list.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[list[i], list[j]] = [list[j], list[i]]
    }
  })

  const domainNames = Object.keys(domainBuckets)
  const balanced: UrbanGovEvalTask[] = []
  let keep = true
  let idx = 0
  while (keep) {
    keep = false
    for (let d = 0; d < domainNames.length; d++) {
      const domain = domainNames[(d + idx) % domainNames.length]
      const bucket = domainBuckets[domain]
      if (bucket[idx]) {
        balanced.push(bucket[idx])
        keep = true
      }
    }
    idx++
    // 防止极端过长，最多取前 40 条
    if (balanced.length >= 40) break
  }
  return balanced
}

// -------------- 真实请求 + 兜底 --------------

export async function fetchUrbanGovEvalTasks(): Promise<UrbanGovEvalTask[]> {
  try {
    const res = await axios.get<UrbanGovEvalTask[]>(`${URBAN_GOV_EVAL_BASE}/tasks`)
    if (Array.isArray(res.data) && res.data.length > 0) {
      return mergeWithMockTasks(res.data)
    }
  } catch (err) {
    // ignore and fallback
  }
  return mergeWithMockTasks(undefined)
}

export async function runUrbanGovEval(
  modelName: string,
  normalization: 'ratio' | 'relative' = 'ratio',
  taskLimit?: number
) {
  const payload: Record<string, string | number> = {
    model_name: modelName,
    normalization_method: normalization
  }
  if (typeof taskLimit === 'number') {
    payload.task_limit = taskLimit
  }
  try {
    const res = await axios.post<UrbanGovEvalSummary>(`${URBAN_GOV_EVAL_BASE}/run`, payload)
    return res.data
  } catch (err) {
    if (isMockModel(modelName)) {
      return MOCK_SUMMARY[modelName]
    }
    throw err
  }
}

export async function fetchUrbanGovEvalSummary(modelName: string) {
  try {
    const res = await axios.get<UrbanGovEvalSummary>(`${URBAN_GOV_EVAL_BASE}/summary/${modelName}`)
    if (res.data) return res.data
  } catch (err) {
    if (isMockModel(modelName)) {
      return MOCK_SUMMARY[modelName]
    }
    throw err
  }
  if (isMockModel(modelName)) {
    return MOCK_SUMMARY[modelName]
  }
  throw new Error('未找到模型评测摘要')
}

export async function fetchUrbanGovEvalLeaderboard() {
  try {
    const res = await axios.get<LeaderboardItem[]>(`${URBAN_GOV_EVAL_BASE}/leaderboard`)
    const data = Array.isArray(res.data) ? res.data : []
    // 确保内置模型都展示
    const merged = [...data]
    const existing = new Set(merged.map((i) => i.model_name))
    MOCK_LEADERBOARD.forEach((item) => {
      if (!existing.has(item.model_name)) merged.push(item)
    })
    if (merged.length > 0) {
      return merged.sort((a, b) => b.overall_score - a.overall_score)
    }
  } catch (err) {
  }
  return MOCK_LEADERBOARD
}

export async function fetchUrbanGovEvalPerTask(modelName: string, taskId: string) {
  try {
    const res = await axios.get<UrbanGovEvalPerTaskResult>(
      `${URBAN_GOV_EVAL_BASE}/per-task/${modelName}/${taskId}`
    )
    if (res.data) return res.data
  } catch (err) {
    const key = `${modelName}::${taskId}`
    if (MOCK_PER_TASK[key]) {
      return MOCK_PER_TASK[key]
    }
    const generated = createMockPerTask(modelName, taskId)
    if (generated) return generated
    throw err
  }
  const key = `${modelName}::${taskId}`
  if (MOCK_PER_TASK[key]) {
    return MOCK_PER_TASK[key]
  }
  const generated = createMockPerTask(modelName, taskId)
  if (generated) return generated
  throw new Error('未找到评测题目结果')
}
