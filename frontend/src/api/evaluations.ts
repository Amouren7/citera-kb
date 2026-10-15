import { http, unwrap, V1 } from './client'
import { cleanParams, normalizePaged } from './normalize'
import type {
  EvalCompareResponse,
  EvalDataset,
  EvalItem,
  EvalRunResponse,
  EvalRunSummary,
  Paginated,
  RetrievalMode,
} from './types'

export interface RunEvaluationInput {
  dataset_id: number
  modes: RetrievalMode[]
  top_k: number
}

export const evaluationsApi = {
  /** GET /api/v1/evaluations/datasets */
  async datasets(): Promise<EvalDataset[]> {
    const raw = await unwrap<unknown>(http.get(`${V1}/evaluations/datasets`, { silent: true }))
    if (Array.isArray(raw)) return raw as EvalDataset[]
    const paged = normalizePaged<EvalDataset>(raw, 'datasets')
    return paged.items
  },

  /** GET /api/v1/evaluations/datasets/{id}/items */
  async items(id: number, query: { page?: number; page_size?: number } = {}): Promise<Paginated<EvalItem>> {
    const raw = await unwrap<unknown>(
      http.get(`${V1}/evaluations/datasets/${id}/items`, { params: cleanParams({ ...query }), silent: true }),
    )
    return normalizePaged<EvalItem>(raw, 'items', 'eval_items')
  },

  /** POST /api/v1/evaluations/run（同步执行，可能较慢） */
  async run(input: RunEvaluationInput): Promise<EvalRunResponse> {
    const raw = await unwrap<unknown>(
      http.post(`${V1}/evaluations/run`, input, { timeout: 300000, silent: true }),
    )
    return raw as EvalRunResponse
  },

  /** GET /api/v1/evaluations/runs */
  async runs(query: { page?: number; page_size?: number } = {}): Promise<Paginated<EvalRunSummary>> {
    const raw = await unwrap<unknown>(
      http.get(`${V1}/evaluations/runs`, { params: cleanParams({ ...query }), silent: true }),
    )
    return normalizePaged<EvalRunSummary>(raw, 'runs')
  },

  /** GET /api/v1/evaluations/runs/compare?ids=1,2,3 */
  async compare(ids: number[]): Promise<EvalCompareResponse> {
    const raw = await unwrap<unknown>(
      http.get(`${V1}/evaluations/runs/compare`, { params: { ids: ids.join(',') }, silent: true }),
    )
    return raw as EvalCompareResponse
  },
}
