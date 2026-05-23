export interface MovieDto {
    id: number
    title: string
    release_year: number | null
    runtime: number | null
    vote_average: number | null
    vote_count: number | null
    bayesian_rating: number | null
    overview: string | null
    poster_url: string | null
    genres: string[]
    director: string | null
    top_cast: string[]
    original_language: string | null
    trailer_youtube_key: string | null
    umap_x: number | null
    umap_y: number | null
}
