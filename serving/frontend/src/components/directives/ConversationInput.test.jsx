import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ConversationInput from './ConversationInput'

describe('ConversationInput', () => {
  const defaultProps = {
    onSubmit: vi.fn(),
    submitting: false,
    disabled: false,
    commentMode: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders textarea and send button', () => {
    render(<ConversationInput {...defaultProps} />)

    expect(screen.getByRole('textbox')).toBeDefined()
    expect(screen.getAllByRole('button').length).toBeGreaterThan(0)
  })

  it('renders mode buttons when not in commentMode', () => {
    render(<ConversationInput {...defaultProps} />)

    expect(screen.getByText('Chat')).toBeDefined()
    expect(screen.getByText('New Work')).toBeDefined()
    expect(screen.getByText('Directive')).toBeDefined()
  })

  it('hides mode buttons in commentMode', () => {
    render(<ConversationInput {...defaultProps} commentMode={true} />)

    expect(screen.queryByText('Chat')).toBeNull()
    expect(screen.queryByText('New Work')).toBeNull()
    expect(screen.queryByText('Directive')).toBeNull()
  })

  it('updates textarea value on input', () => {
    render(<ConversationInput {...defaultProps} />)

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: 'Hello world' } })

    expect(textarea.value).toBe('Hello world')
  })

  it('submits with chat mode by default', () => {
    const onSubmit = vi.fn()
    render(<ConversationInput {...defaultProps} onSubmit={onSubmit} />)

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: 'Build feature' } })

    const buttons = screen.getAllByRole('button')
    const sendButton = buttons.find(b => b.className.includes('conv-send-btn'))
    fireEvent.click(sendButton)

    expect(onSubmit).toHaveBeenCalledWith('Build feature', 'chat', { priority: undefined })
  })

  it('submits with Cmd+Enter', () => {
    const onSubmit = vi.fn()
    render(<ConversationInput {...defaultProps} onSubmit={onSubmit} />)

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: 'Test submit' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })

    expect(onSubmit).toHaveBeenCalledWith('Test submit', 'chat', { priority: undefined })
  })

  it('submits with Ctrl+Enter', () => {
    const onSubmit = vi.fn()
    render(<ConversationInput {...defaultProps} onSubmit={onSubmit} />)

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: 'Test submit' } })
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true })

    expect(onSubmit).toHaveBeenCalledWith('Test submit', 'chat', { priority: undefined })
  })

  it('clears text after submit', () => {
    const onSubmit = vi.fn()
    render(<ConversationInput {...defaultProps} onSubmit={onSubmit} />)

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: 'Some text' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })

    expect(textarea.value).toBe('')
  })

  it('does not submit when text is empty', () => {
    const onSubmit = vi.fn()
    render(<ConversationInput {...defaultProps} onSubmit={onSubmit} />)

    const textarea = screen.getByRole('textbox')
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('does not submit when disabled', () => {
    const onSubmit = vi.fn()
    render(<ConversationInput {...defaultProps} onSubmit={onSubmit} disabled={true} />)

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: 'Test' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('does not submit when submitting', () => {
    const onSubmit = vi.fn()
    render(<ConversationInput {...defaultProps} onSubmit={onSubmit} submitting={true} />)

    const textarea = screen.getByRole('textbox')
    expect(textarea.disabled).toBe(true)
  })

  it('changes mode on mode button click', () => {
    const onSubmit = vi.fn()
    render(<ConversationInput {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.click(screen.getByText('New Work'))

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: 'Work item' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })

    expect(onSubmit).toHaveBeenCalledWith('Work item', 'new_work', { priority: undefined })
  })

  it('forces NEW_WORK mode in commentMode', () => {
    const onSubmit = vi.fn()
    render(<ConversationInput {...defaultProps} onSubmit={onSubmit} commentMode={true} />)

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: 'Comment' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })

    expect(onSubmit).toHaveBeenCalledWith('Comment', 'new_work', { priority: undefined })
  })

  it('shows correct placeholder for chat mode', () => {
    render(<ConversationInput {...defaultProps} />)
    const textarea = screen.getByRole('textbox')
    expect(textarea.placeholder).toContain('Type a message')
  })

  it('shows correct placeholder for directive mode', () => {
    render(<ConversationInput {...defaultProps} />)
    fireEvent.click(screen.getByText('Directive'))
    const textarea = screen.getByRole('textbox')
    expect(textarea.placeholder).toContain('Focus on testing')
  })

  it('shows correct placeholder for new work mode', () => {
    render(<ConversationInput {...defaultProps} />)
    fireEvent.click(screen.getByText('New Work'))
    const textarea = screen.getByRole('textbox')
    expect(textarea.placeholder).toContain('Describe what you want')
  })

  it('shows correct placeholder for comment mode', () => {
    render(<ConversationInput {...defaultProps} commentMode={true} />)
    const textarea = screen.getByRole('textbox')
    expect(textarea.placeholder).toContain('Add context')
  })

  it('hides options row in directive mode', () => {
    render(<ConversationInput {...defaultProps} />)
    fireEvent.click(screen.getByText('Directive'))
    expect(screen.queryByText('Options')).toBeNull()
  })

  it('shows options toggle in chat mode', () => {
    render(<ConversationInput {...defaultProps} />)
    expect(screen.getByText('Options')).toBeDefined()
  })

  it('toggles priority select on options click', () => {
    render(<ConversationInput {...defaultProps} />)

    const optionsBtn = screen.getByText('Options')
    fireEvent.click(optionsBtn)

    expect(screen.getByDisplayValue('Priority')).toBeDefined()
  })

  it('submits with selected priority', () => {
    const onSubmit = vi.fn()
    render(<ConversationInput {...defaultProps} onSubmit={onSubmit} />)

    fireEvent.click(screen.getByText('Options'))

    const select = screen.getByDisplayValue('Priority')
    fireEvent.change(select, { target: { value: 'P0' } })

    const textarea = screen.getByRole('textbox')
    fireEvent.change(textarea, { target: { value: 'Urgent work' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })

    expect(onSubmit).toHaveBeenCalledWith('Urgent work', 'chat', { priority: 'P0' })
  })

  it('disables mode buttons while submitting', () => {
    render(<ConversationInput {...defaultProps} submitting={true} />)

    const modeButtons = ['Chat', 'New Work', 'Directive'].map(label => screen.getByText(label))
    modeButtons.forEach(btn => {
      expect(btn.disabled).toBe(true)
    })
  })

  it('shows spinner in send button while submitting', () => {
    const { container } = render(<ConversationInput {...defaultProps} submitting={true} />)

    const spinner = container.querySelector('.directive-spinner')
    expect(spinner).not.toBeNull()
  })

  it('shows Send icon when not submitting', () => {
    const { container } = render(<ConversationInput {...defaultProps} submitting={false} />)

    const spinner = container.querySelector('.directive-spinner')
    expect(spinner).toBeNull()
  })
})
