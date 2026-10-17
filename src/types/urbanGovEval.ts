export interface EvaluationCriterion {
  id: string
  name: string
  description: string
  dimension: string
  weight: number
  reference_score: number
  reference_comment?: string
}

export interface FactExpectation {
  expected_pairs: number
  min_authority_ratio: number
  min_timeliness_ratio: number
}

export interface TaskMetricDefinition {
  metric: string
  description?: string
  reference_value?: number
}

export interface UrbanGovEvalTask {
  task_id: string
  title: string
  domain: string
  task_type: string
  language: string
  difficulty: string
  time_ref: string
  query: string
  deliverable: string
  output_format: string
  reference_report: string
  criteria: EvaluationCriterion[]
  fact_expectation?: FactExpectation
  task_metrics: TaskMetricDefinition[]
}

export interface ConfidenceInterval {
  lower: number
  upper: number
}

export interface RaceDimensionScore {
  dimension: string
  weighted_score: number
  normalized_score: number
}

export interface RaceResult {
  method: string
  target_total: number
  reference_total: number
  normalized_score: number
  ratio_score: number
  relative_advantage_score: number
  dimension_scores: RaceDimensionScore[]
}

export interface CriterionScore {
  criterion_id: string
  name: string
  dimension: string
  weight: number
  target_score: number
  reference_score: number
  gap: number
  explanation: string
  reference_comment?: string
}

export interface FactPairResult {
  statement: string
  citation: string
  normalized_citation: string
  support: boolean
  authority: boolean
  timeliness: boolean
  misuse: boolean
  notes?: string
}

export interface FactMetrics {
  total_pairs: number
  supported_pairs: number
  authoritative_pairs: number
  timely_pairs: number
  misuse_pairs: number
  citation_accuracy: number
  effective_citations: number
  source_authority_ratio: number
  timeliness_ratio: number
  misuse_rate: number
  pairs: FactPairResult[]
}

export interface TaskMetricScore {
  metric: string
  value: number
  normalized: number
  description?: string
  reference_value?: number
  direction: 'higher_is_better' | 'lower_is_better'
}

export interface DomainScore {
  domain: string
  task_count: number
  race: number
  citation_accuracy: number
  effective_citations_norm: number
  task_metrics_norm: number
  overall: number
}

export interface UrbanGovEvalSummary {
  model_name: string
  generated_at: string
  normalization_method: string
  task_count: number
  race_score: number
  citation_accuracy: number
  effective_citations_norm: number
  task_metrics_norm: number
  overall_score: number
  race_ci: ConfidenceInterval
  citation_accuracy_ci: ConfidenceInterval
  overall_ci: ConfidenceInterval
  metrics: Record<string, any>
  domain_breakdown: DomainScore[]
  references: Record<string, any>
}

export interface UrbanGovEvalPerTaskResult {
  model_name: string
  task_id: string
  generated_at: string
  normalization_method: string
  race: RaceResult
  criteria: CriterionScore[]
  fact: FactMetrics
  task_metrics: TaskMetricScore[]
  metadata: Record<string, any>
}

export interface LeaderboardItem {
  model_name: string
  overall_score: number
  race_score: number
  citation_accuracy: number
  effective_citations_norm: number
  task_metrics_norm: number
  updated_at: string
}
