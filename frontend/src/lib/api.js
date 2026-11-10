async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'content-type': 'application/json' },
    ...options
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* body was not JSON */
    }
    throw new Error(detail);
  }

  return response;
}

export const api = {
  health: () => request('/api/health').then((r) => r.json()),
  sources: () => request('/api/sources').then((r) => r.json()),
  cases: () => request('/api/cases').then((r) => r.json()),
  createCase: (title, scope_note) =>
    request('/api/cases', {
      method: 'POST',
      body: JSON.stringify({ title, scope_note })
    }).then((r) => r.json()),
  case: (id) => request(`/api/cases/${id}`).then((r) => r.json()),
  graph: (id) => request(`/api/cases/${id}/graph`).then((r) => r.json()),
  audit: (id) => request(`/api/cases/${id}/audit`).then((r) => r.json()),
  report: (id) => request(`/api/cases/${id}/report`).then((r) => r.text()),
  collect: (id, payload) =>
    request(`/api/cases/${id}/collect`, {
      method: 'POST',
      body: JSON.stringify(payload)
    }).then((r) => r.json())
};

export function inferType(target) {
  const value = target.trim();
  if (/^https?:\/\//i.test(value)) return 'url';
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(value)) return 'ip';
  if (value.includes('.') && !value.includes(' ')) return 'domain';
  return 'organization';
}
