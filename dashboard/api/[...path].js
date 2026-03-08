const isBodyAllowed = (method) => {
  if (!method) return false
  const normalized = method.toUpperCase()
  return normalized !== 'GET' && normalized !== 'HEAD'
}

const normalizeBaseUrl = (value) => {
  if (typeof value !== 'string') return ''
  return value.replace(/\/+$/, '')
}

const toRequestBody = (req, method) => {
  if (!isBodyAllowed(method)) return undefined

  const rawBody = req.body
  if (rawBody === undefined || rawBody === null) return undefined
  if (Buffer.isBuffer(rawBody)) return rawBody
  if (typeof rawBody === 'string') return rawBody

  const contentType = String(req.headers['content-type'] || '').toLowerCase()
  if (contentType.includes('application/json')) {
    return JSON.stringify(rawBody)
  }
  if (contentType.includes('application/x-www-form-urlencoded')) {
    return new URLSearchParams(rawBody).toString()
  }
  return JSON.stringify(rawBody)
}

export default async function handler(req, res) {
  const baseUrl = normalizeBaseUrl(process.env.BACKEND_API_URL)
  if (!baseUrl) {
    res.status(500).json({
      error: 'Missing BACKEND_API_URL environment variable on server.',
    })
    return
  }

  const pathSegments = req.query.path
  const resolvedPath = Array.isArray(pathSegments)
    ? pathSegments.join('/')
    : pathSegments || ''
  const upstreamUrl = new URL(`/api/${resolvedPath}`, `${baseUrl}/`)

  for (const [key, value] of Object.entries(req.query)) {
    if (key === 'path') continue
    if (Array.isArray(value)) {
      for (const item of value) {
        upstreamUrl.searchParams.append(key, item)
      }
      continue
    }
    if (typeof value === 'string') {
      upstreamUrl.searchParams.set(key, value)
    }
  }

  const headers = new Headers()
  for (const [key, value] of Object.entries(req.headers)) {
    if (value === undefined) continue
    if (Array.isArray(value)) {
      for (const item of value) {
        headers.append(key, item)
      }
      continue
    }
    headers.set(key, value)
  }

  headers.delete('host')
  headers.delete('content-length')
  if (!headers.has('ngrok-skip-browser-warning')) {
    headers.set('ngrok-skip-browser-warning', 'true')
  }

  const method = req.method || 'GET'
  let upstreamResponse
  try {
    upstreamResponse = await fetch(upstreamUrl, {
      method,
      headers,
      body: toRequestBody(req, method),
      redirect: 'manual',
    })
  } catch (error) {
    res.status(502).json({
      error: 'Failed to reach upstream API.',
      details: error instanceof Error ? error.message : 'Unknown error',
    })
    return
  }

  res.status(upstreamResponse.status)

  upstreamResponse.headers.forEach((value, key) => {
    if (key.toLowerCase() === 'transfer-encoding') return
    res.setHeader(key, value)
  })

  const setCookie = upstreamResponse.headers.getSetCookie?.()
  if (setCookie && setCookie.length > 0) {
    res.setHeader('set-cookie', setCookie)
  }

  const payload = Buffer.from(await upstreamResponse.arrayBuffer())
  res.send(payload)
}
