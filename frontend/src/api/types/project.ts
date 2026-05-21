export interface Project {
  id: string
  user_id: string
  title: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface CreateProjectRequest {
  title: string
  description?: string
}

export interface UpdateProjectRequest {
  title?: string
  description?: string
}
