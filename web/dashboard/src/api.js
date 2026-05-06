import axios from "axios";

const INSPECTOR_BASE =
  process.env.REACT_APP_INSPECTOR_BASE || "http://localhost:5002";
const APPROVAL_BASE =
  process.env.REACT_APP_APPROVAL_BASE || "http://localhost:5001";

const api = {
  /**
   * Fetch global memory items for a session.
   * @param {string} session
   * @returns {Promise<Array>}
   */
  inspect: (session) =>
    axios
      .get(`${INSPECTOR_BASE}/api/inspect_json`, { params: { session } })
      .then((r) => r.data.items || []),

  /**
   * Semantic search within a session's global namespace.
   * @param {string} session
   * @param {string} q
   * @returns {Promise<Array>}
   */
  search: (session, q) =>
    axios
      .get(`${INSPECTOR_BASE}/api/search_json`, { params: { session, q } })
      .then((r) => r.data.items || []),

  /**
   * List all approval requests.
   * @returns {Promise<Array>}
   */
  listApprovals: () =>
    axios
      .get(`${APPROVAL_BASE}/api/requests`)
      .then((r) => (Array.isArray(r.data) ? r.data : [])),
};

export default api;
