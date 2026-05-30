// 极简 fetch 封装:统一 baseURL + Authorization + 401 处理
// 不引入 axios,纯原生 fetch,零依赖。

const BASE_URL = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const TOKEN_KEY = 'access_token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

function buildUrl(path, params) {
  const u = new URL(path.startsWith('http') ? path : BASE_URL + path)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') u.searchParams.append(k, v)
    })
  }
  return u.toString()
}

async function request(method, path, { body, params, form, headers = {} } = {}) {
  const token = getToken()
  const finalHeaders = { ...headers }
  let payload

  if (form) {
    // application/x-www-form-urlencoded
    payload = new URLSearchParams(form)
  } else if (body !== undefined) {
    finalHeaders['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  if (token) finalHeaders['Authorization'] = `Bearer ${token}`

  let resp
  try {
    resp = await fetch(buildUrl(path, params), { method, headers: finalHeaders, body: payload })
  } catch (e) {
    throw new ApiError(0, '网络错误,请检查后端是否启动', null)
  }

  let data = null
  const ct = resp.headers.get('content-type') || ''
  if (ct.includes('application/json')) {
    try { data = await resp.json() } catch { /* empty */ }
  } else {
    try { data = await resp.text() } catch { /* empty */ }
  }

  if (!resp.ok) {
    if (resp.status === 401) {
      clearToken()
      // 触发跳转,但 router 实例在 utils 里不一定可用,改成事件
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    }
    const detail = (data && (data.detail || data.message)) || resp.statusText
    throw new ApiError(resp.status, detail, data)
  }
  return data
}

export class ApiError extends Error {
  constructor(status, detail, raw) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
    this.raw = raw
  }
}

export const api = {
  get: (p, params) => request('GET', p, { params }),
  post: (p, body) => request('POST', p, { body }),
  postForm: (p, form) => request('POST', p, { form }),
  patch: (p, body) => request('PATCH', p, { body }),
  put: (p, body) => request('PUT', p, { body }),
  delete: (p) => request('DELETE', p),
}
