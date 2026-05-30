export interface AxisPointDto {
    movie_id: number
    title: string
    score: number
    vote_count: number
}

export interface AxisDistributionDto {
    concept_id: string
    concept_name: string
    positive_label: string
    negative_label: string
    points: AxisPointDto[]
}
