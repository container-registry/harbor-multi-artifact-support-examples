const BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8080').replace(/\/+$/, '')

async function request(path, options = {}) {
  const res = await fetch(`${BASE}/api${path}`, {
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    ...options,
  })
  if (!res.ok) throw new Error(`${options.method || 'GET'} ${path} failed: ${res.status}`)
  return res.status === 204 ? null : res.json()
}

export function listTodos() {
  return request('/todos')
}

export function createTodo(title) {
  return request('/todos', { method: 'POST', body: JSON.stringify({ title }) })
}

export function updateTodo(id, patch) {
  return request(`/todos/${id}`, { method: 'PATCH', body: JSON.stringify(patch) })
}

export function removeTodo(id) {
  return request(`/todos/${id}`, { method: 'DELETE' })
}

export function clearCompleted() {
  return request('/todos?completed=true', { method: 'DELETE' })
}
