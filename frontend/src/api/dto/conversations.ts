export interface MessageDto {
    id: string
    role: 'user' | 'assistant'
    content: string
    created_at: string
}

export interface ConversationDto {
    id: string
    current_cluster_snapshot_id: string | null
    messages: MessageDto[]
    created_at: string
}

export interface SendMessageResponse {
    message: MessageDto
    cluster_snapshot_id: string
}
