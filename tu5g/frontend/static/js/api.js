/**
 * TU5G Platform - API Client Infrastructure
 */
"use strict";

const TU5G_API = (function () {
  const BASE_URL = "/api";

  async function request(endpoint, options = {}) {
    const url = endpoint.startsWith("http") 
      ? endpoint 
      : `${BASE_URL}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;
    
    const defaultHeaders = {
      "Content-Type": "application/json",
      "Accept": "application/json"
    };

    const token = localStorage.getItem("tu5g_auth_token");
    if (token) {
      defaultHeaders["Authorization"] = `Bearer ${token}`;
    }

    const config = {
      method: options.method || "GET",
      headers: { ...defaultHeaders, ...options.headers },
      ...options
    };

    if (config.body && typeof config.body === "object" && !(config.body instanceof FormData)) {
      config.body = JSON.stringify(config.body);
    }

    try {
      const response = await fetch(url, config);
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.message || data.error || `HTTP error! status: ${response.status}`);
      }

      return data;
    } catch (error) {
      console.error(`API Error [${options.method || "GET"} ${endpoint}]:`, error);
      throw error;
    }
  }

  return {
    get: (endpoint, headers) => request(endpoint, { method: "GET", headers }),
    post: (endpoint, body, headers) => request(endpoint, { method: "POST", body, headers }),
    put: (endpoint, body, headers) => request(endpoint, { method: "PUT", body, headers }),
    delete: (endpoint, headers) => request(endpoint, { method: "DELETE", headers }),
    request
  };
})();

window.TU5G_API = TU5G_API;
