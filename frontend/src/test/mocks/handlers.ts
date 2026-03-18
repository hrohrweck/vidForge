import { http, HttpResponse } from 'msw'

const API_BASE = 'http://localhost:8000/api'

export const handlers = [
  http.post(`${API_BASE}/auth/login`, () => {
    return HttpResponse.json({
      access_token: 'test-token',
      token_type: 'bearer'
    })
  }),
  
  http.post(`${API_BASE}/auth/register`, () => {
    return HttpResponse.json({
      id: '1',
      email: 'test@example.com',
      is_active: true,
      is_superuser: false
    })
  }),
  
  http.get(`${API_BASE}/auth/me`, ({ request }) => {
    const auth = request.headers.get('Authorization')
    if (!auth) {
      return new HttpResponse(null, { status: 401 })
    }
    
    if (auth.includes('superuser')) {
      return HttpResponse.json({
        id: '1',
        email: 'admin@example.com',
        is_active: true,
        is_superuser: true
      })
    }
    
    return HttpResponse.json({
      id: '1',
      email: 'test@example.com',
      is_active: true,
      is_superuser: false
    })
  }),
  
  http.get(`${API_BASE}/jobs`, ({ request }) => {
    const auth = request.headers.get('Authorization')
    if (!auth) {
      return new HttpResponse(null, { status: 401 })
    }
    
    return HttpResponse.json([
      {
        id: '1',
        status: 'completed',
        progress: 100,
        input_data: { prompt: 'test' },
        output_path: '/uploads/output1.mp4',
        preview_path: null,
        thumbnail_path: '/uploads/thumb1.jpg',
        error_message: null,
        created_at: '2024-01-01T00:00:00Z',
        started_at: '2024-01-01T00:01:00Z',
        completed_at: '2024-01-01T00:05:00Z'
      }
    ])
  }),
  
  http.post(`${API_BASE}/jobs`, () => {
    return HttpResponse.json({
      id: '2',
      status: 'pending',
      progress: 0,
      input_data: {},
      created_at: '2024-01-01T00:00:00Z'
    }, { status: 200 })
  }),
  
  http.post(`${API_BASE}/jobs/batch`, () => {
    return HttpResponse.json({
      created_count: 2,
      job_ids: ['3', '4']
    })
  }),
  
  http.post(`${API_BASE}/jobs/batch/csv`, () => {
    return HttpResponse.json({
      created_count: 3,
      job_ids: ['5', '6', '7']
    })
  }),
  
  http.get(`${API_BASE}/jobs/:id`, ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      status: 'pending',
      progress: 50,
      input_data: { prompt: 'test' },
      created_at: '2024-01-01T00:00:00Z'
    })
  }),
  
  http.delete(`${API_BASE}/jobs/:id`, () => {
    return HttpResponse.json({ status: 'deleted' })
  }),
  
  http.get(`${API_BASE}/templates`, () => {
    return HttpResponse.json([
      {
        id: '1',
        name: 'Test Template',
        description: 'A test template',
        config: {
          inputs: [
            { name: 'prompt', type: 'text', required: true },
            { name: 'style', type: 'select', options: ['realistic', 'anime'] }
          ]
        },
        is_builtin: true,
        created_at: '2024-01-01T00:00:00Z'
      }
    ])
  }),
  
  http.get(`${API_BASE}/templates/:id`, ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      name: 'Test Template',
      description: 'A test template',
      config: {
        inputs: [
          { name: 'prompt', type: 'text', required: true }
        ]
      },
      is_builtin: true,
      created_at: '2024-01-01T00:00:00Z'
    })
  }),
  
  http.post(`${API_BASE}/templates`, () => {
    return HttpResponse.json({
      id: '2',
      name: 'Custom Template',
      description: 'A custom template',
      config: {},
      is_builtin: false,
      created_at: '2024-01-01T00:00:00Z'
    })
  }),
  
  http.get(`${API_BASE}/admin/users`, ({ request }) => {
    const auth = request.headers.get('Authorization')
    if (!auth || !auth.includes('superuser')) {
      return new HttpResponse(null, { status: 403 })
    }
    return HttpResponse.json([
      {
        id: '1',
        email: 'user@example.com',
        is_active: true,
        is_superuser: false,
        created_at: '2024-01-01T00:00:00Z'
      }
    ])
  }),
  
  http.get(`${API_BASE}/admin/stats`, ({ request }) => {
    const auth = request.headers.get('Authorization')
    if (!auth || !auth.includes('superuser')) {
      return new HttpResponse(null, { status: 403 })
    }
    return HttpResponse.json({
      total_users: 10,
      total_jobs: 50,
      active_jobs: 5
    })
  }),
  
  http.post(`${API_BASE}/admin/users/:id/toggle-active`, () => {
    return HttpResponse.json({ status: 'success' })
  }),
  
  http.get(`${API_BASE}/styles`, () => {
    return HttpResponse.json([
      {
        id: '1',
        name: 'Realistic',
        category: 'default',
        params: {},
        created_at: '2024-01-01T00:00:00Z'
      }
    ])
  }),
  
  http.get(`${API_BASE}/users/settings`, () => {
    return HttpResponse.json({
      storage_backend: 'local',
      preferences: {}
    })
  }),
  
  http.put(`${API_BASE}/users/settings`, () => {
    return HttpResponse.json({ status: 'success' })
  })
]
