import type { ChatTurn } from './api/generated/models'

export type { ChatTurn }

export type DisplayMessage = ChatTurn & { key: string }
