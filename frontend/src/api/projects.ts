import api from './client'
import type { Project, CreateProjectRequest, UpdateProjectRequest } from './types/project'

export async function listProjects(): Promise<Project[]> {
  const response = await api.get('/projects')
  return response.data
}

export async function createProject(payload: CreateProjectRequest): Promise<Project> {
  const response = await api.post('/projects', payload)
  return response.data
}

export async function getProject(id: string): Promise<Project> {
  const response = await api.get(`/projects/${id}`)
  return response.data
}

export async function updateProject(id: string, payload: UpdateProjectRequest): Promise<Project> {
  const response = await api.patch(`/projects/${id}`, payload)
  return response.data
}

export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/projects/${id}`)
}

export const projectsApi = {
  list: listProjects,
  create: createProject,
  get: getProject,
  update: updateProject,
  delete: deleteProject,
}
