import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

vi.mock('../../../services/workorderApi', () => ({
  default: {
    interpret: vi.fn(),
    prioritize: vi.fn(),
  },
}))

vi.mock('../../../services/workorderMockAdapter', () => ({
  WORKORDER_MOCKS_ENABLED: false,
  getMockInterpretation: vi.fn(),
}))

import WorkOrderApiService from '../../../services/workorderApi'
import CreateWOView from '../CreateWOView'

describe('CreateWOView', () => {
  it('shows deterministic API error fallback when interpret endpoint is unavailable', async () => {
    WorkOrderApiService.interpret.mockResolvedValue({ ok: false, error: 'network' })

    render(<CreateWOView onAddWorkOrder={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText(/RTU-001/i), {
      target: { value: 'The condenser fan is oscillating and noisy.' },
    })
    fireEvent.click(screen.getByRole('button', { name: /interpret with ai/i }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Interpretation service is unavailable')
    })
  })
})
