import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createDraft } from '../api'
import type { Draft } from '../types'
import { ScreenStart } from './ScreenStart'

vi.mock('../api', () => ({
  createDraft: vi.fn(),
}))

const mockCreateDraft = vi.mocked(createDraft)

const sampleDraft: Draft = {
  id: 'draft-1',
  title: 'AI 윤리 입문',
  intro: '소개',
  goals: '',
  outcomes: ['목표 1'],
  weeks: [{ title: '1주', summary: '요약' }],
  grading: [{ name: '과제', weight: 100 }],
  suggestions: [],
  sources_used: [],
  warnings: [],
  created_at: '',
  updated_at: '',
}

describe('ScreenStart', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('과목 이름만으로 초안을 요청할 수 있다', async () => {
    mockCreateDraft.mockResolvedValue(sampleDraft)
    const onCreated = vi.fn()
    render(<ScreenStart onCreated={onCreated} />)

    await userEvent.type(screen.getByLabelText('과목 이름'), 'AI 윤리 입문')
    await userEvent.click(screen.getByRole('button', { name: '초안 만들기' }))

    expect(mockCreateDraft).toHaveBeenCalledWith('AI 윤리 입문', '', [])
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(sampleDraft))
  })

  it('자료를 올리지 않아도 진행할 수 있다', async () => {
    mockCreateDraft.mockResolvedValue(sampleDraft)
    render(<ScreenStart onCreated={vi.fn()} />)

    await userEvent.type(screen.getByLabelText('과목 이름'), '자료구조')
    await userEvent.click(screen.getByRole('button', { name: '초안 만들기' }))

    expect(mockCreateDraft).toHaveBeenCalledWith('자료구조', '', [])
  })

  it('올린 자료가 요청에 함께 전달된다', async () => {
    mockCreateDraft.mockResolvedValue(sampleDraft)
    render(<ScreenStart onCreated={vi.fn()} />)

    await userEvent.type(screen.getByLabelText('과목 이름'), 'AI 윤리 입문')
    const file = new File(['윤리 장 내용'], '원고.txt', { type: 'text/plain' })
    await userEvent.upload(screen.getByLabelText('참고 자료 업로드'), file)
    await userEvent.click(screen.getByRole('button', { name: '초안 만들기' }))

    expect(mockCreateDraft).toHaveBeenCalledWith('AI 윤리 입문', '', [file])
  })

  it('과목 이름이 없으면 오류를 안내하고 요청하지 않는다', async () => {
    render(<ScreenStart onCreated={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: '초안 만들기' }))

    expect(mockCreateDraft).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('과목 이름을 입력해 주세요')
  })
})
