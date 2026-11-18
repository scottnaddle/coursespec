import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  applyChangeRequest,
  confirmDesign,
  discardChangeRequest,
  requestChange,
  submitEdits,
} from '../api'
import type { CourseMap } from '../types'
import { ScreenCourseMap } from './ScreenCourseMap'

vi.mock('../api', () => ({
  applyChangeRequest: vi.fn(),
  confirmDesign: vi.fn(),
  discardChangeRequest: vi.fn(),
  requestChange: vi.fn(),
  submitEdits: vi.fn(),
}))

const mockSubmitEdits = vi.mocked(submitEdits)
const mockRequestChange = vi.mocked(requestChange)
const mockApplyChangeRequest = vi.mocked(applyChangeRequest)
const mockDiscardChangeRequest = vi.mocked(discardChangeRequest)
const mockConfirmDesign = vi.mocked(confirmDesign)

const baseMap: CourseMap = {
  design_id: 'd1',
  title: 'AI 에이전트 시대의 교육',
  confirmed: false,
  can_confirm: true,
  summary: {
    unit_count: 2,
    outcome_count: 1,
    grading: '과제 60% · 퀴즈 40%',
    max_per_unit_label: '4시간',
  },
  outcomes: [
    { index: 1, label: '목표 1 · 이해', statement: '에이전트를 설명할 수 있다.', level: '이해' },
  ],
  units: [
    {
      id: 'w1',
      index: 1,
      title: 'AI 에이전트란 무엇인가',
      summary: '자율성의 단계를 살펴 봅니다.',
      total_minutes: 55,
      items: [
        {
          id: 'w1-reading',
          kind: '읽기',
          title: '스킬에서 에이전트까지',
          minutes: 40,
          due_day: null,
          due_label: null,
          note: null,
        },
        {
          id: 'w1-quiz',
          kind: '퀴즈',
          title: '1주차 확인 퀴즈',
          minutes: 15,
          due_day: 7,
          due_label: '7일차 마감',
          note: null,
        },
      ],
    },
    {
      id: 'w2',
      index: 2,
      title: '수업 속 에이전트 시나리오',
      summary: '시나리오를 설계합니다.',
      total_minutes: 60,
      items: [
        {
          id: 'w2-asg',
          kind: '과제',
          title: '내 수업 에이전트 시나리오',
          minutes: 60,
          due_day: 14,
          due_label: '14일차 마감',
          note: null,
        },
      ],
    },
  ],
  notices: [],
}

function renderScreen(map: CourseMap = baseMap) {
  const onChange = vi.fn()
  render(<ScreenCourseMap map={map} onChange={onChange} />)
  return onChange
}

describe('ScreenCourseMap', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('주차와 활동이 화면에 보인다', () => {
    renderScreen()
    expect(screen.getByRole('heading', { name: '과정 지도 초안이 준비되었습니다' })).toBeInTheDocument()
    expect(screen.getByText('1주차')).toBeInTheDocument()
    expect(screen.getByText('2주차')).toBeInTheDocument()
    expect(screen.getByText('스킬에서 에이전트까지')).toBeInTheDocument()
    expect(screen.getByText('1주차 확인 퀴즈')).toBeInTheDocument()
    expect(screen.getByText(/7일차 마감/)).toBeInTheDocument()
    expect(screen.getByText('목표 1 · 이해')).toBeInTheDocument()
    expect(screen.getByText('과제 60% · 퀴즈 40%')).toBeInTheDocument()
    // YAML 흔적이 보이지 않는다
    expect(screen.queryByText(/coursespec:/i)).not.toBeInTheDocument()
  })

  it('경고·오류가 없으면 배너가 보이지 않는다', () => {
    renderScreen()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('경고가 있으면 쉬운 문장으로 보이고 코드는 보이지 않는다', () => {
    renderScreen({
      ...baseMap,
      notices: [
        { severity: 'warning', message: '평가 비중 합계가 100이 아닙니다.', where: '평가 비중' },
      ],
    })
    expect(screen.getByRole('alert')).toHaveTextContent('평가 비중 합계가 100이 아닙니다.')
    expect(screen.queryByText(/W1\d\d/)).not.toBeInTheDocument()
  })

  it('오류가 있으면 확정 버튼이 비활성화되고 이유를 알려 준다', () => {
    renderScreen({
      ...baseMap,
      can_confirm: false,
      notices: [{ severity: 'error', message: '참조한 활동이 없습니다.', where: '2주차' }],
    })
    const button = screen.getByRole('button', { name: '이 설계로 확정' })
    expect(button).toBeDisabled()
    expect(button.title).toContain('고친 뒤')
  })

  it('주차 제목 편집이 검증된 편집 요청으로 본낸다', async () => {
    mockSubmitEdits.mockResolvedValue(baseMap)
    renderScreen()

    await userEvent.click(screen.getAllByRole('button', { name: '이 주차 편집' })[0])
    const titleInput = screen.getByLabelText('주차 제목')
    await userEvent.clear(titleInput)
    await userEvent.type(titleInput, '에이전트 기초')
    await userEvent.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() =>
      expect(mockSubmitEdits).toHaveBeenCalledWith(
        'd1',
        expect.arrayContaining([
          expect.objectContaining({
            action: 'update_unit',
            unit_id: 'w1',
            title: '에이전트 기초',
          }),
        ]),
      ),
    )
  })

  it('수정 요청은 미리 보기를 거쳐 적용한다', async () => {
    mockRequestChange.mockResolvedValue({
      request_id: 'r1',
      summary: ["2주차 제목을 '새 제목'(으)로 바꿉니다."],
    })
    mockApplyChangeRequest.mockResolvedValue(baseMap)
    renderScreen()

    await userEvent.click(screen.getByRole('button', { name: '수정 요청' }))
    await userEvent.type(
      screen.getByLabelText('바꾸고 싶은 내용'),
      "2주차 제목을 '새 제목'로 바꿔 주세요",
    )
    await userEvent.click(screen.getByRole('button', { name: '미리 보기' }))

    await waitFor(() => expect(screen.getByText("2주차 제목을 '새 제목'(으)로 바꿉니다.")).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: '적용' }))

    await waitFor(() => expect(mockApplyChangeRequest).toHaveBeenCalledWith('d1', 'r1'))
  })

  it('수정 요청 취소는 저장해 둔 요청을 버리고 설계서를 바꾸지 않는다', async () => {
    mockRequestChange.mockResolvedValue({ request_id: 'r9', summary: ['3주차에 토론 추가'] })
    mockDiscardChangeRequest.mockResolvedValue({ discarded: true })
    renderScreen()

    await userEvent.click(screen.getByRole('button', { name: '수정 요청' }))
    await userEvent.type(screen.getByLabelText('바꾸고 싶은 내용'), '3주차에 토론 추가')
    await userEvent.click(screen.getByRole('button', { name: '미리 보기' }))
    await waitFor(() =>
      expect(screen.getAllByText('3주차에 토론 추가').length).toBeGreaterThan(0),
    )
    await userEvent.click(screen.getByRole('button', { name: '취소' }))

    await waitFor(() => expect(mockDiscardChangeRequest).toHaveBeenCalledWith('d1', 'r9'))
    expect(mockApplyChangeRequest).not.toHaveBeenCalled()
  })

  it('오류가 없으면 확정할 수 있다', async () => {
    mockConfirmDesign.mockResolvedValue({ confirmed: true, message: '설계가 확정되었습니다.' })
    renderScreen()

    await userEvent.click(screen.getByRole('button', { name: '이 설계로 확정' }))
    await waitFor(() => expect(mockConfirmDesign).toHaveBeenCalledWith('d1'))
    expect(await screen.findByRole('status')).toHaveTextContent('설계가 확정되었습니다')
  })
})
