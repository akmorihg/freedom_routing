const DEFAULT_BACKEND_HOST = "/api";

const getBackendCandidates = () => {
  const candidates = [
    process.env.REACT_APP_BACKEND_API_URL,
    process.env.REACT_APP_API_URL,
    DEFAULT_BACKEND_HOST,
  ];

  return [...new Set(candidates.filter(Boolean))];
};

export const BACKEND_API_URL = getBackendCandidates()[0];
let activeBackendBaseUrl = BACKEND_API_URL;
let backendDiscoveryPromise = null;
export const getActiveBackendApiUrl = () => activeBackendBaseUrl;

const buildQuery = (params = {}) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    search.append(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : "";
};

const parseJsonSafely = (raw) => {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (_error) {
    return null;
  }
};

const fetchWithTimeout = async (url, options = {}, timeoutMs = 20000) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
};

const discoverBackendBaseUrl = async () => {
  if (backendDiscoveryPromise) return backendDiscoveryPromise;

  backendDiscoveryPromise = (async () => {
    const candidates = getBackendCandidates();
    for (const candidate of candidates) {
      try {
        const response = await fetchWithTimeout(`${candidate}/health`, { method: "GET" }, 5000);
        if (response.ok) {
          activeBackendBaseUrl = candidate;
          return activeBackendBaseUrl;
        }
      } catch (_error) {
        // try next candidate
      }
    }

    throw new Error(`Backend is unreachable. Tried: ${candidates.join(", ")}`);
  })();

  try {
    return await backendDiscoveryPromise;
  } finally {
    backendDiscoveryPromise = null;
  }
};

const requestToBase = async (baseUrl, path, { method = "GET", body, headers = {} } = {}) => {
  const url = `${baseUrl}${path}`;
  let response;
  try {
    response = await fetchWithTimeout(url, {
      method,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(`Request timed out after 20000ms (${url})`);
    }
    throw error;
  }

  const raw = await response.text();
  const data = parseJsonSafely(raw);
  const contentType = response.headers.get("content-type") || "";
  const trimmedRaw = typeof raw === "string" ? raw.trim() : "";
  const htmlLike =
    contentType.includes("text/html") ||
    trimmedRaw.startsWith("<!DOCTYPE") ||
    trimmedRaw.startsWith("<html");

  if (!response.ok) {
    const detail = data?.detail;
    const message =
      (typeof detail === "string" && detail) ||
      (detail && typeof detail === "object" && JSON.stringify(detail)) ||
      (htmlLike && `Received HTML from ${baseUrl}${path}. Check backend URL or proxy setup.`) ||
      `Request failed: ${response.status}`;
    throw new Error(`${message} (${baseUrl}${path})`);
  }

  if (raw && data === null) {
    if (htmlLike) {
      throw new Error(`Received HTML from ${baseUrl}${path}. Check backend URL or proxy setup.`);
    }
    throw new Error(`Expected JSON from ${baseUrl}${path} but received non-JSON response.`);
  }

  activeBackendBaseUrl = baseUrl;
  return data;
};

const request = async (path, options = {}) => {
  const candidates = [
    activeBackendBaseUrl,
    ...(getBackendCandidates().filter((candidate) => candidate !== activeBackendBaseUrl)),
  ];

  let lastError = null;
  const attemptErrors = [];

  for (const candidate of candidates) {
    try {
      return await requestToBase(candidate, path, options);
    } catch (error) {
      lastError = error;
      attemptErrors.push(`${candidate}${path} -> ${String(error?.message || error)}`);
      // Try next candidate on connectivity / bad target errors
      if (
        error?.name === "TypeError" ||
        /Failed to fetch|NetworkError|ERR_CONNECTION_REFUSED|non-JSON|Received HTML|aborted|timed out/i.test(
          String(error?.message || ""),
        )
      ) {
        continue;
      }
      throw error;
    }
  }

  // Final attempt after active health discovery
  try {
    const discovered = await discoverBackendBaseUrl();
    return await requestToBase(discovered, path, options);
  } catch (error) {
    const details = attemptErrors.length ? ` Tried: ${attemptErrors.join(" | ")}` : "";
    throw new Error(`${String(lastError?.message || error?.message || "Backend request failed.")}${details}`);
  }
};

// Managers
export const listManagers = (params = {}) =>
  request(`/managers${buildQuery({
    expand_position: true,
    expand_city: true,
    expand_skills: true,
    ...params,
  })}`);

export const createManager = (payload, params = {}) =>
  request(
    `/managers${buildQuery({
      expand_position: true,
      expand_city: true,
      expand_skills: true,
      ...params,
    })}`,
    { method: "POST", body: payload },
  );

export const updateManager = (managerId, payload, params = {}) =>
  request(
    `/managers/${managerId}${buildQuery({
      expand_position: true,
      expand_city: true,
      expand_skills: true,
      ...params,
    })}`,
    { method: "PUT", body: payload },
  );

export const deleteManager = (managerId) =>
  request(`/managers/${managerId}`, { method: "DELETE" });

export const listManagerPositions = () => request("/managers/positions");
export const createManagerPosition = (payload) =>
  request("/managers/positions", { method: "POST", body: payload });

export const listSkills = () => request("/managers/skills");
export const createSkill = (payload) => request("/managers/skills", { method: "POST", body: payload });

// Tickets
export const listTickets = (params = {}) =>
  request(`/tickets${buildQuery({
    expand: true,
    include_attachments: false,
    include_attachment_type: false,
    include_attachment_url: false,
    ...params,
  })}`);

export const createTicket = (payload, params = {}) =>
  request(
    `/tickets${buildQuery({
      expand: true,
      include_attachments: true,
      include_attachment_type: true,
      include_attachment_url: false,
      ...params,
    })}`,
    { method: "POST", body: payload },
  );

export const updateTicket = (ticketId, payload, params = {}) =>
  request(
    `/tickets/${ticketId}${buildQuery({
      expand: true,
      include_attachments: true,
      include_attachment_type: true,
      include_attachment_url: false,
      ...params,
    })}`,
    { method: "PUT", body: payload },
  );

export const deleteTicket = (ticketId) => request(`/tickets/${ticketId}`, { method: "DELETE" });

export const listClientSegments = () => request("/tickets/segments");
export const createClientSegment = (payload) =>
  request("/tickets/segments", { method: "POST", body: payload });

export const listGenders = () => request("/tickets/genders");
export const createGender = (payload) => request("/tickets/genders", { method: "POST", body: payload });

// Location / business units
export const listOffices = (params = {}) =>
  request(`/location/offices${buildQuery({ expand_city: true, ...params })}`);

export const createOffice = (payload) => request("/location/offices", { method: "POST", body: payload });

export const updateOffice = (officeId, payload) =>
  request(`/location/offices/${officeId}`, { method: "PUT", body: payload });

export const deleteOffice = (officeId) => request(`/location/offices/${officeId}`, { method: "DELETE" });

export const listCountries = () => request("/location/countries");
export const createCountry = (payload) => request("/location/countries", { method: "POST", body: payload });

export const listRegions = () => request("/location/regions");
export const createRegion = (payload) => request("/location/regions", { method: "POST", body: payload });

export const listCities = (params = {}) => request(`/location/cities${buildQuery(params)}`);
export const createCity = (payload) => request("/location/cities", { method: "POST", body: payload });

export const listAddresses = (params = {}) => request(`/location/addresses${buildQuery(params)}`);
export const createAddress = (payload) =>
  request("/location/addresses", { method: "POST", body: payload });

// Ticket Assignments
export const listTicketAssignments = () => request("/tickets/assignments");

// Ticket Analysis (separate from tickets)
export const listTicketAnalyses = () => request("/tickets/analysis");

// AI Service helpers (called via /ai proxy)
const AI_BASE = process.env.REACT_APP_AI_API_URL || "/ai";

const aiRequest = async (path, method = "POST") => {
  const url = `${AI_BASE}${path}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 300000); // 5 min timeout for long-running AI ops
  try {
    const response = await fetch(url, {
      method,
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    clearTimeout(timer);
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(data?.detail || `AI request failed: ${response.status}`);
    }
    return data;
  } catch (err) {
    clearTimeout(timer);
    if (err?.name === "AbortError") throw new Error(`AI request timed out (${url})`);
    throw err;
  }
};

export const triggerAnalyzeFromDb = () => aiRequest("/ai/analyze-from-db");
export const triggerRoutingFromDb = () => aiRequest("/routing/assign-from-db");
