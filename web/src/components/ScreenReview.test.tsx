import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { acceptSuggestion, createDesign, handoff, skipSuggestion, updateDraft } from '../api'
import type { Draft } from '../types'
import { ScreenReview } from './ScreenReview'

vi.mock('../api', () => ({
  updateDraft: vi.fn(),
  handoff: vi.fn(),
  createDesign: vi.fn(),
  acceptSuggestion: vi.fn(),
  skipSuggestion: vi.fn(),
  regenerateDraft: vi.fn(),
}))

const mockUpdateDraft = vi.mocked(updateDraft)
const mockHandoff = vi.mocked(handoff)
const mockCreateDesign = vi.mocked(createDesign)
const mockAcceptSuggestion = vi.mocked(acceptSuggestion)
const mockSkipSuggestion = vi.mocked(skipSuggestion)

const draft: Draft = {
  id: 'd1',
  title: '원래 제목',
  intro: '소개 문장',
  goals: '',
  outcomes: ['목표 1'],
  weeks: [{ title: '1주차 주제', summary: '요약' }],
  grading: [{ name: '과제', weight: 100 }],
  suggestions: [
    { id: 's1', text: '주차 제목을 다듬는 제안', target: '주차 1 제목', status: 'pending' },
  ],
  sources_used: [],
  warnings: [],
  created_at: '',
  updated_at: '',
}

describe('ScreenReview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('편집한 제목이 저장·인계에 그대로 반영되고 과정 지도로 넘어간다', async () => {
    mockUpdateDraft.mockResolvedValue({ ...draft, title: '고친 제목' })
    mockHandoff.mockResolvedValue({ text: '# 고친 제목\n' })
    mockCreateDesign.mockResolvedValue({
      design_id: 'g1',
      map: {
        design_id: 'g1',
        title: '고친 제목',
        confirmed: false,
        can_confirm: true,
        summary: { unit_count: 1, outcome_count: 1, grading: '과제 100%', max_per_unit_label: '4시간' },
        outcomes: [],
        units: [],
        notices: [],
      },
    })
    const onUpdated = vi.fn()
    const onDesigned = vi.fn()
    render(
      <ScreenReview draft={draft} onUpdated={onUpdated} onStartNew={vi.fn()} onDesigned={onDesigned} />,
    )

    const titleInput = screen.getByLabelText('과정 이름')
    await userEvent.clear(titleInput)
    await userEvent.type(titleInput, '고친 제목')

    await userEvent.click(screen.getByRole('button', { name: '이 초안으로 과정 설계하기' }))

    await waitFor(() =>
      expect(mockUpdateDraft).toHaveBeenCalledWith(
        'd1',
        expect.objectContaining({ title: '고친 제목' }),
      ),
    )
    await waitFor(() => expect(mockHandoff).toHaveBeenCalledWith('d1'))
    await waitFor(() =>
      expect(mockCreateDesign).toHaveBeenCalledWith('d1'),
    )
    await waitFor(() => expect(onDesigned).toHaveBeenCalledWith(expect.objectContaining({ design_id: 'g1' })))
  })

  it('제안은 수락 전에 본문을 바꾸지 않는다', () => {
    render(
      <ScreenReview
        draft={draft}
        onUpdated={vi.fn()}
        onStartNew={vi.fn()}
        onDesigned={vi.fn()}
      />,
    )

    expect(screen.getByLabelText('1주차 제목')).toHaveValue('1주차 주제')
    expect(mockAcceptSuggestion).not.toHaveBeenCalled()
    expect(mockUpdateDraft).not.toHaveBeenCalled()
  })

  it('넣기를 누르면 그 제안만 수락 API 로 반영한다', async () => {
    mockAcceptSuggestion.mockResolvedValue({
      ...draft,
      suggestions: [{ ...draft.suggestions[0], status: 'accepted' }],
    })
    const onUpdated = vi.fn()
    render(
      <ScreenReview draft={draft} onUpdated={onUpdated} onStartNew={vi.fn()} onDesigned={vi.fn()} />,
    )

    await userEvent.click(screen.getByRole('button', { name: '넣기' }))

    await waitFor(() => expect(mockAcceptSuggestion).toHaveBeenCalledWith('d1', 's1'))
    expect(mockSkipSuggestion).not.toHaveBeenCalled()
  })

  it('건너뛰기를 누르면 수락 없이 건너뛴다', async () => {
    mockSkipSuggestion.mockResolvedValue({
      ...draft,
      suggestions: [{ ...draft.suggestions[0], status: 'skipped' }],
    })
    render(
      <ScreenReview draft={draft} onUpdated={vi.fn()} onStartNew={vi.fn()} onDesigned={vi.fn()} />,
    )

    await userEvent.click(screen.getByRole('button', { name: '건너뛰기' }))

    await waitFor(() => expect(mockSkipSuggestion).toHaveBeenCalledWith('d1', 's1'))
    expect(mockAcceptSuggestion).not.toHaveBeenCalled()
  })
})
