import { ExemplarCard } from './ExemplarCard'
import type { ClusterDto } from '@/api/dto/snapshots'
import type { MovieDto } from '@/api/dto/movies'

interface ClusterDetailProps {
  cluster: ClusterDto
  movieMap: Map<number, MovieDto>
  onMovieClick: (movieId: number) => void
}

/**
 * Expanded cluster detail showing a grid of exemplar movie cards.
 *
 * @param cluster     - The cluster whose exemplars to display.
 * @param movieMap    - Map from movie ID to MovieDto for looking up posters/titles.
 * @param onMovieClick - Called with the TMDB ID when a card is clicked.
 * @returns Grid of ExemplarCard components.
 */
export function ClusterDetail({ cluster, movieMap, onMovieClick }: ClusterDetailProps) {
  const movies = cluster.exemplar_movie_ids
    .map((id) => movieMap.get(id))
    .filter((m): m is MovieDto => m !== undefined)

  return (
    <div className="grid grid-cols-4 gap-2 p-3">
      {movies.map((movie) => (
        <ExemplarCard key={movie.id} movie={movie} onClick={onMovieClick} />
      ))}
    </div>
  )
}
