import { useMutation } from '@tanstack/react-query'

export type StageStatus = 'done' | 'current' | 'todo'

export const stageStatus = (done: boolean, available: boolean): StageStatus =>
  done ? 'done' : available ? 'current' : 'todo'

/** A playground action: clears the error first, shows failures, and refreshes App A's state. */
export function useAction<T>(
  common: { setError: (message: string | null) => void; onSettled: () => void },
  fn: () => Promise<T>,
  onOk?: (value: T) => void,
) {
  return useMutation({
    mutationFn: fn,
    onMutate: () => common.setError(null),
    onSuccess: (value) => onOk?.(value),
    onError: (err) => common.setError(err.message),
    onSettled: common.onSettled,
  })
}
