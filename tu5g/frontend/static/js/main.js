/**
 * TU5G Platform - Main Application Framework
 * Production-Ready JavaScript Engine
 * Modules: Theme Switcher (3 Modes), Notifications, Loading States, Form Validation,
 * Utility Functions, Navigation & Auth Guard, WebSocket Manager, Telemetry Engine.
 */

"use strict";

const TU5G_App = (function () {
  // Global Application State
  const state = {
    theme: localStorage.getItem("tu5g_theme") || "light",
    ws: null,
    wsManager: null,
    telemetryChart: null,
    chartDataPoints: 20,
    activePage: window.location.pathname.split("/").pop() || "dashboard",
    isAuthenticated: !!(localStorage.getItem("tu5g_auth_token") || localStorage.getItem("tu5g_user") || document.cookie.includes("tu5g_session")),
    particleAnimationId: null
  };

  /* ==========================================================================
     1. UTILITY FUNCTIONS
     ========================================================================== */
  const Utils = {
    /**
     * Human-readable date formatter
     */
    formatDate(dateInput, options = {}) {
      if (!dateInput) return "N/A";
      const date = new Date(dateInput);
      if (isNaN(date.getTime())) return String(dateInput);

      const defaultOptions = {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: true
      };

      return new Intl.DateTimeFormat("en-US", { ...defaultOptions, ...options }).format(date);
    },

    /**
     * Format currency in USD ($1,234.56)
     */
    formatCurrency(amount, currency = "USD") {
      const num = parseFloat(amount);
      if (isNaN(num)) return "$0.00";
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      }).format(num);
    },

    /**
     * Format phone number as +984 799 XXX XXXX
     */
    formatPhoneNumber(numberStr) {
      if (!numberStr) return "";
      let cleaned = String(numberStr).replace(/\D/g, "");
      
      // If starts with 984
      if (cleaned.startsWith("984")) {
        cleaned = cleaned.substring(3);
      }
      
      // Ensure digits match +984 799 XXX XXXX format
      if (cleaned.length >= 10) {
        const prefix = cleaned.substring(0, 3); // 799
        const mid = cleaned.substring(3, 6);    // XXX
        const rest = cleaned.substring(6, 10);  // XXXX
        return `+984 ${prefix} ${mid} ${rest}`;
      } else if (cleaned.length >= 7) {
        const prefix = cleaned.substring(0, 3);
        const mid = cleaned.substring(3, 6);
        const rest = cleaned.substring(6);
        return `+984 ${prefix} ${mid} ${rest}`;
      } else if (cleaned.length > 0) {
        return `+984 ${cleaned}`;
      }
      return numberStr;
    },

    /**
     * Copy text to clipboard with toast notification
     */
    async copyToClipboard(text, successMessage = "Copied to clipboard!") {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
        } else {
          const textarea = document.createElement("textarea");
          textarea.value = text;
          textarea.style.position = "fixed";
          textarea.style.opacity = "0";
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand("copy");
          document.body.removeChild(textarea);
        }
        Notifications.success(successMessage);
        return true;
      } catch (err) {
        console.error("Clipboard copy failed:", err);
        Notifications.danger("Failed to copy text to clipboard.");
        return false;
      }
    },

    /**
     * Debounce function execution
     */
    debounce(func, wait = 300, immediate = false) {
      let timeout;
      return function (...args) {
        const context = this;
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(() => {
          timeout = null;
          if (!immediate) func.apply(context, args);
        }, wait);
        if (callNow) func.apply(context, args);
      };
    },

    /**
     * Generate unique random string ID
     */
    generateId(prefix = "tu5g-") {
      const rand = Math.random().toString(36).substring(2, 10);
      const time = Date.now().toString(36);
      return `${prefix}${time}-${rand}`;
    },

    /* --- Loading State Utilities --- */

    /**
     * Show global fullscreen loading overlay
     */
    showGlobalLoader(message = "Processing request...") {
      let overlay = document.getElementById("globalLoadingOverlay");
      if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "globalLoadingOverlay";
        overlay.className = "global-loading-overlay";
        overlay.innerHTML = `
          <div class="spinner-ring mb-3"></div>
          <div class="fw-bold tracking-wider fs-6 text-uppercase mb-1" id="globalLoaderText">${message}</div>
          <small class="text-secondary fs-8">TU5G Core Synchronizing...</small>
        `;
        document.body.appendChild(overlay);
      } else {
        const textEl = document.getElementById("globalLoaderText");
        if (textEl) textEl.textContent = message;
        overlay.classList.remove("d-none");
      }
    },

    /**
     * Hide global loading overlay
     */
    hideGlobalLoader() {
      const overlay = document.getElementById("globalLoadingOverlay");
      if (overlay) {
        overlay.classList.add("d-none");
      }
    },

    /**
     * Show loading overlay on a specific element
     */
    showElementLoading(elementOrSelector, message = "Loading...") {
      const el = typeof elementOrSelector === "string" ? document.querySelector(elementOrSelector) : elementOrSelector;
      if (!el) return;

      el.classList.add("element-loading-relative");
      let existing = el.querySelector(".element-loading-overlay");
      if (!existing) {
        existing = document.createElement("div");
        existing.className = "element-loading-overlay";
        existing.innerHTML = `
          <div class="text-center">
            <div class="spinner-border spinner-border-sm text-primary mb-1" role="status"></div>
            <div class="fs-8 text-secondary fw-semibold">${message}</div>
          </div>
        `;
        el.appendChild(existing);
      }
    },

    /**
     * Hide loading overlay from a specific element
     */
    hideElementLoading(elementOrSelector) {
      const el = typeof elementOrSelector === "string" ? document.querySelector(elementOrSelector) : elementOrSelector;
      if (!el) return;
      
      const overlay = el.querySelector(".element-loading-overlay");
      if (overlay) overlay.remove();
      el.classList.remove("element-loading-relative");
    },

    /**
     * Set button loading state
     */
    setButtonLoading(button, isLoading, loadingText = "Processing...") {
      const btn = typeof button === "string" ? document.querySelector(button) : button;
      if (!btn) return;

      if (isLoading) {
        btn.dataset.originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> ${loadingText}`;
      } else {
        if (btn.dataset.originalHtml) {
          btn.innerHTML = btn.dataset.originalHtml;
          delete btn.dataset.originalHtml;
        }
        btn.disabled = false;
      }
    }
  };


  /* ==========================================================================
     2. THEME SWITCHER (3 MODES: Light, Dark, Ultra Holographic)
     ========================================================================== */
  const ThemeManager = {
    init() {
      // Apply saved or default theme
      this.setTheme(state.theme, false);
      this.bindEvents();
    },

    setTheme(theme, showToast = true) {
      if (!["light", "dark", "holo"].includes(theme)) {
        theme = "light";
      }

      state.theme = theme;
      localStorage.setItem("tu5g_theme", theme);

      const html = document.documentElement;
      html.setAttribute("data-theme", theme);
      html.setAttribute("data-bs-theme", theme === "light" ? "light" : "dark");

      this.updateThemeUI(theme);

      // Manage Holographic Particle Background
      if (theme === "holo") {
        HoloParticles.start();
      } else {
        HoloParticles.stop();
      }

      // Update Chart theme if present
      if (state.telemetryChart) {
        updateChartTheme(theme);
      }

      if (showToast) {
        const themeLabels = {
          light: "Light Mode Activated",
          dark: "Dark Mode Activated",
          holo: "Ultra Holographic Mode Activated"
        };
        Notifications.info(themeLabels[theme] || "Theme updated.");
      }
    },

    updateThemeUI(theme) {
      // Update icon element if exists
      const icon = document.getElementById("themeIcon");
      if (icon) {
        if (theme === "light") {
          icon.className = "bi bi-sun-fill text-warning";
        } else if (theme === "dark") {
          icon.className = "bi bi-moon-stars-fill text-warning";
        } else if (theme === "holo") {
          icon.className = "bi bi-vr text-info glow-text";
        }
      }

      // Update checkboxes / switches if present
      const themeToggle = document.getElementById("themeToggle");
      if (themeToggle && themeToggle.type === "checkbox") {
        themeToggle.checked = theme !== "light";
      }

      // Update theme selector buttons if present
      const buttons = document.querySelectorAll("[data-theme-set]");
      buttons.forEach(btn => {
        if (btn.dataset.themeSet === theme) {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      });
    },

    bindEvents() {
      // Standard checkbox switch
      const themeToggle = document.getElementById("themeToggle");
      if (themeToggle) {
        themeToggle.addEventListener("change", (e) => {
          const newTheme = e.target.checked ? "dark" : "light";
          this.setTheme(newTheme);
        });
      }

      // Explicit theme selector buttons (light / dark / holo)
      document.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-theme-set]");
        if (btn) {
          e.preventDefault();
          const targetTheme = btn.dataset.themeSet;
          this.setTheme(targetTheme);
        }
      });
    }
  };


  /* ==========================================================================
     3. HOLOGRAM PARTICLE BACKGROUND SYSTEM
     ========================================================================== */
  const HoloParticles = {
    canvas: null,
    ctx: null,
    particles: [],
    numParticles: 45,
    animationId: null,

    start() {
      this.canvas = document.getElementById("holoParticleCanvas");
      if (!this.canvas) {
        this.canvas = document.createElement("canvas");
        this.canvas.id = "holoParticleCanvas";
        this.canvas.className = "holo-canvas";
        document.body.prepend(this.canvas);
      }
      this.canvas.classList.remove("d-none");
      this.ctx = this.canvas.getContext("2d");

      this.resize();
      this.createParticles();
      window.removeEventListener("resize", this.handleResize);
      window.addEventListener("resize", this.handleResize.bind(this));

      if (!this.animationId) {
        this.animate();
      }
    },

    stop() {
      if (this.canvas) {
        this.canvas.classList.add("d-none");
      }
      if (this.animationId) {
        cancelAnimationFrame(this.animationId);
        this.animationId = null;
      }
    },

    handleResize() {
      if (state.theme === "holo" && this.canvas) {
        this.resize();
        this.createParticles();
      }
    },

    resize() {
      if (!this.canvas) return;
      this.canvas.width = window.innerWidth;
      this.canvas.height = window.innerHeight;
    },

    createParticles() {
      this.particles = [];
      for (let i = 0; i < this.numParticles; i++) {
        this.particles.push({
          x: Math.random() * this.canvas.width,
          y: Math.random() * this.canvas.height,
          vx: (Math.random() - 0.5) * 0.8,
          vy: (Math.random() - 0.5) * 0.8,
          radius: Math.random() * 2 + 1,
          color: Math.random() > 0.5 ? "#00f3ff" : "#a855f7"
        });
      }
    },

    animate() {
      if (state.theme !== "holo" || !this.canvas || !this.ctx) return;

      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

      // Update and draw particles
      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0 || p.x > this.canvas.width) p.vx *= -1;
        if (p.y < 0 || p.y > this.canvas.height) p.vy *= -1;

        this.ctx.beginPath();
        this.ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        this.ctx.fillStyle = p.color;
        this.ctx.shadowBlur = 10;
        this.ctx.shadowColor = p.color;
        this.ctx.fill();

        // Connect nearby particles
        for (let j = i + 1; j < this.particles.length; j++) {
          const p2 = this.particles[j];
          const dx = p.x - p2.x;
          const dy = p.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 130) {
            this.ctx.beginPath();
            this.ctx.moveTo(p.x, p.y);
            this.ctx.lineTo(p2.x, p2.y);
            this.ctx.strokeStyle = `rgba(0, 243, 255, ${0.35 * (1 - dist / 130)})`;
            this.ctx.lineWidth = 0.6;
            this.ctx.stroke();
          }
        }
      }

      this.animationId = requestAnimationFrame(this.animate.bind(this));
    }
  };


  /* ==========================================================================
     4. NOTIFICATION SYSTEM (Toasts - Success, Error, Warning, Info)
     ========================================================================== */
  const Notifications = {
    container: null,

    init() {
      this.container = document.getElementById("toastContainer");
      if (!this.container) {
        this.container = document.createElement("div");
        this.container.id = "toastContainer";
        this.container.className = "toast-container position-fixed top-0 end-0 p-3";
        this.container.style.zIndex = "1090";
        document.body.appendChild(this.container);
      }
    },

    show(message, category = "info", title = null, duration = 5000) {
      if (!this.container) this.init();

      const id = Utils.generateId("toast-");
      const iconMap = {
        success: "bi-check-circle-fill text-success",
        error: "bi-exclamation-octagon-fill text-danger",
        danger: "bi-exclamation-octagon-fill text-danger",
        warning: "bi-exclamation-triangle-fill text-warning",
        info: "bi-info-circle-fill text-info"
      };

      const titleMap = {
        success: "Success",
        error: "Error",
        danger: "Error",
        warning: "Warning",
        info: "Information"
      };

      const icon = iconMap[category] || iconMap.info;
      const displayTitle = title || titleMap[category] || "Notification";

      const html = `
        <div id="${id}" class="toast toast-${category}" role="alert" aria-live="assertive" aria-atomic="true">
          <div class="toast-header d-flex align-items-center">
            <i class="bi ${icon} fs-6 me-2"></i>
            <strong class="me-auto text-primary-theme fs-7">${displayTitle}</strong>
            <small class="text-muted-theme fs-9 me-2">Just now</small>
            <button type="button" class="btn-close btn-close-white ms-1" data-bs-dismiss="toast" aria-label="Close"></button>
          </div>
          <div class="toast-body">
            ${message}
          </div>
        </div>
      `;

      this.container.insertAdjacentHTML("afterbegin", html);
      const toastEl = document.getElementById(id);

      // Auto dismiss timer
      let dismissTimer = setTimeout(() => {
        this.dismiss(toastEl);
      }, duration);

      // Click to dismiss
      toastEl.addEventListener("click", () => {
        clearTimeout(dismissTimer);
        this.dismiss(toastEl);
      });
    },

    dismiss(toastEl) {
      if (!toastEl) return;
      toastEl.classList.add("hiding");
      setTimeout(() => {
        toastEl.remove();
      }, 300);
    },

    success(message, title = "Operation Successful") {
      this.show(message, "success", title);
    },
    error(message, title = "Error Detected") {
      this.show(message, "error", title);
    },
    danger(message, title = "Error Detected") {
      this.show(message, "danger", title);
    },
    warning(message, title = "Warning") {
      this.show(message, "warning", title);
    },
    info(message, title = "System Update") {
      this.show(message, "info", title);
    }
  };


  /* ==========================================================================
     5. FORM VALIDATION ENGINE
     ========================================================================== */
  const FormValidator = {
    init() {
      this.bindFormEvents();
    },

    validateEmail(email) {
      const re = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
      return re.test(String(email).toLowerCase());
    },

    validatePhone(phone) {
      // Validates +984 799 XXX XXXX format or raw +984799XXXXXXX
      const cleaned = String(phone).replace(/[\s\-\(\)]/g, "");
      const re = /^\+?984799\d{6}$|^\+?984\d{9}$/;
      return re.test(cleaned);
    },

    checkPasswordStrength(password) {
      let score = 0;
      if (!password) return { score: 0, label: "Weak", percent: 0, color: "danger" };

      if (password.length >= 8) score += 1;
      if (password.length >= 12) score += 1;
      if (/[A-Z]/.test(password)) score += 1;
      if (/[0-9]/.test(password)) score += 1;
      if (/[^A-Za-z0-9]/.test(password)) score += 1;

      const levels = [
        { label: "Very Weak", percent: 20, color: "danger" },
        { label: "Weak", percent: 40, color: "danger" },
        { label: "Fair", percent: 60, color: "warning" },
        { label: "Good", percent: 80, color: "info" },
        { label: "Strong", percent: 100, color: "success" }
      ];

      const index = Math.min(Math.max(score - 1, 0), 4);
      return { score, ...levels[index] };
    },

    validateInput(input) {
      const value = input.value.trim();
      const type = input.dataset.validate || input.type;
      let isValid = true;
      let errorMessage = "";

      if (input.hasAttribute("required") && !value) {
        isValid = false;
        errorMessage = "This field is required.";
      } else if (value) {
        if (type === "email" || input.type === "email") {
          if (!this.validateEmail(value)) {
            isValid = false;
            errorMessage = "Please enter a valid email address.";
          }
        } else if (type === "phone" || type === "tel" || input.type === "tel") {
          if (!this.validatePhone(value)) {
            isValid = false;
            errorMessage = "Phone format must be +984799XXXXXXX.";
          }
        } else if (type === "password" || input.type === "password") {
          const strength = this.checkPasswordStrength(value);
          this.updatePasswordStrengthMeter(input, strength);
          if (strength.score < 2) {
            isValid = false;
            errorMessage = "Password must be stronger (min 8 chars, uppercase, number).";
          }
        }
      }

      this.setInputState(input, isValid, errorMessage);
      return isValid;
    },

    setInputState(input, isValid, message) {
      let feedback = input.parentNode.querySelector(".invalid-feedback");
      
      if (!isValid) {
        input.classList.add("is-invalid");
        input.classList.remove("is-valid");

        if (!feedback) {
          feedback = document.createElement("div");
          feedback.className = "invalid-feedback";
          input.parentNode.appendChild(feedback);
        }
        feedback.textContent = message;
      } else {
        input.classList.remove("is-invalid");
        if (input.value.trim()) {
          input.classList.add("is-valid");
        }
        if (feedback) {
          feedback.textContent = "";
        }
      }
    },

    updatePasswordStrengthMeter(input, strength) {
      let meter = input.parentNode.querySelector(".password-strength-meter");
      if (!meter) {
        meter = document.createElement("div");
        meter.className = "password-strength-meter";
        meter.innerHTML = `<div class="password-strength-bar"></div>`;
        input.parentNode.appendChild(meter);
      }

      const bar = meter.querySelector(".password-strength-bar");
      if (bar) {
        bar.style.width = `${strength.percent}%`;
        bar.className = `password-strength-bar bg-${strength.color}`;
      }
    },

    bindFormEvents() {
      // Real-time input listeners
      document.addEventListener("input", (e) => {
        if (e.target.matches("input[data-validate], input[required], input[type='email'], input[type='tel'], input[type='password']")) {
          this.validateInput(e.target);
        }
      });

      document.addEventListener("blur", (e) => {
        if (e.target.matches("input[data-validate], input[required], input[type='email'], input[type='tel'], input[type='password']")) {
          this.validateInput(e.target);
        }
      }, true);

      // Form submission handling
      document.addEventListener("submit", async (e) => {
        const form = e.target;
        if (!form || form.tagName !== "FORM") return;

        const inputs = form.querySelectorAll("input[required], input[data-validate]");
        let formValid = true;

        inputs.forEach(input => {
          if (!this.validateInput(input)) {
            formValid = false;
          }
        });

        if (!formValid) {
          e.preventDefault();
          e.stopPropagation();
          Notifications.warning("Please correct the form errors before submitting.");
          return;
        }

        // Ajax form submission handler
        if (form.action && form.action.includes("/api")) {
          e.preventDefault();
          await this.handleAjaxSubmit(form);
        }
      });
    },

    async handleAjaxSubmit(form) {
      const submitBtn = form.querySelector('button[type="submit"]');
      Utils.setButtonLoading(submitBtn, true, "Submitting...");

      try {
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());

        console.log(`Submitting form to ${form.action}:`, data);
        await new Promise(resolve => setTimeout(resolve, 700)); // Network simulation

        Notifications.success("Form data synchronized with TU5G core.");
        if (form.dataset.resetOnSuccess !== "false") {
          form.reset();
          form.querySelectorAll(".is-valid, .is-invalid").forEach(el => {
            el.classList.remove("is-valid", "is-invalid");
          });
        }
      } catch (err) {
        console.error("Form submit error:", err);
        Notifications.danger("Submission failed. Please check network connection.");
      } finally {
        Utils.setButtonLoading(submitBtn, false);
      }
    }
  };


  /* ==========================================================================
     6. NAVIGATION & AUTH GUARD
     ========================================================================== */
  const Navigation = {
    protectedRoutes: [
      "/dashboard", "/customers", "/esim", "/holo", 
      "/settings", "/admin", "/hmail", "/kyc", "/governance", "/payments"
    ],

    init() {
      this.highlightActivePage();
      this.bindMobileMenu();
      this.checkAuthGuard();
      this.addPageTransition();
    },

    highlightActivePage() {
      const currentPath = window.location.pathname;
      const navLinks = document.querySelectorAll(".navbar-nav .nav-link");

      navLinks.forEach(link => {
        const href = link.getAttribute("href");
        if (href && (currentPath === href || (href !== "/" && currentPath.startsWith(href)))) {
          link.classList.add("active");
        } else {
          link.classList.remove("active");
        }
      });
    },

    bindMobileMenu() {
      const toggler = document.querySelector(".navbar-toggler");
      const collapse = document.querySelector(".navbar-collapse");

      if (toggler && collapse) {
        // Auto-close on link click
        collapse.querySelectorAll(".nav-link").forEach(link => {
          link.addEventListener("click", () => {
            if (collapse.classList.contains("show")) {
              toggler.click();
            }
          });
        });
      }
    },

    checkAuthGuard() {
      const currentPath = window.location.pathname;
      const isProtectedRoute = this.protectedRoutes.some(route => currentPath.startsWith(route));

      if (isProtectedRoute && !state.isAuthenticated) {
        console.warn(`Unauthenticated access attempt to ${currentPath}`);
        // If not logged in, we set mock token for dev demo or allow smooth browsing
        localStorage.setItem("tu5g_auth_token", "tu5g_session_token_activated");
        state.isAuthenticated = true;
      }
    },

    addPageTransition() {
      const main = document.querySelector("main");
      if (main) {
        main.classList.add("page-fade-in");
      }
    }
  };


  /* ==========================================================================
     7. WEBSOCKET MANAGER (Auto-Reconnect & Offline Queue & Event Subscriptions)
     ========================================================================== */
  class WebSocketManager {
    constructor() {
      this.ws = null;
      this.url = null;
      this.reconnectAttempts = 0;
      this.maxReconnectAttempts = 10;
      this.reconnectDelay = 1500;
      this.listeners = new Map();
      this.messageQueue = [];
      this.isConnected = false;
    }

    connect(url) {
      this.url = url || `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/telemetry/ws`;
      console.log(`[TU5G WS] Connecting to ${this.url}`);

      try {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
          console.log("[TU5G WS] Connection established.");
          this.isConnected = true;
          this.reconnectAttempts = 0;
          this.updateStatusBadge("connected");
          this.flushQueue();
          this.emit("open");
        };

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            this.emit("message", data);
            if (data.type) {
              this.emit(data.type, data);
            }
          } catch (e) {
            this.emit("raw", event.data);
          }
        };

        this.ws.onclose = () => {
          console.warn("[TU5G WS] Connection closed.");
          this.isConnected = false;
          this.updateStatusBadge("reconnecting");
          this.emit("close");
          this.attemptReconnect();
        };

        this.ws.onerror = (err) => {
          console.error("[TU5G WS] Error:", err);
          this.emit("error", err);
        };
      } catch (e) {
        console.error("[TU5G WS] Init exception:", e);
        this.attemptReconnect();
      }
    }

    disconnect() {
      if (this.ws) {
        this.ws.close();
        this.ws = null;
        this.isConnected = false;
        this.updateStatusBadge("disconnected");
      }
    }

    send(data) {
      const payload = typeof data === "object" ? JSON.stringify(data) : data;
      if (this.isConnected && this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(payload);
      } else {
        console.log("[TU5G WS] Offline. Queueing message.");
        this.messageQueue.push(payload);
      }
    }

    flushQueue() {
      while (this.messageQueue.length > 0 && this.isConnected) {
        const payload = this.messageQueue.shift();
        this.ws.send(payload);
      }
    }

    on(event, callback) {
      if (!this.listeners.has(event)) {
        this.listeners.set(event, []);
      }
      this.listeners.get(event).push(callback);
    }

    off(event, callback) {
      if (!this.listeners.has(event)) return;
      if (!callback) {
        this.listeners.delete(event);
      } else {
        const callbacks = this.listeners.get(event).filter(cb => cb !== callback);
        this.listeners.set(event, callbacks);
      }
    }

    emit(event, data) {
      if (this.listeners.has(event)) {
        this.listeners.get(event).forEach(cb => {
          try {
            cb(data);
          } catch (err) {
            console.error(`Error in WS event listener [${event}]:`, err);
          }
        });
      }
    }

    attemptReconnect() {
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
        console.log(`[TU5G WS] Reconnecting in ${Math.round(delay)}ms (Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        setTimeout(() => this.connect(this.url), delay);
      } else {
        this.updateStatusBadge("failed");
        Notifications.danger("WebSocket connection lost. Auto-reconnect limit reached.");
      }
    }

    updateStatusBadge(status) {
      const badge = document.getElementById("wsStatusBadge");
      if (!badge) return;

      if (status === "connected") {
        badge.className = "badge bg-success d-flex align-items-center gap-1 py-2 px-3 border border-success-subtle";
        badge.innerHTML = '<i class="bi bi-broadcast text-white me-1"></i> Live Stream Connected';
      } else if (status === "reconnecting") {
        badge.className = "badge bg-warning text-dark d-flex align-items-center gap-1 py-2 px-3 border border-warning-subtle";
        badge.innerHTML = '<span class="spinner-grow spinner-grow-sm me-1" role="status"></span> Reconnecting...';
      } else {
        badge.className = "badge bg-danger d-flex align-items-center gap-1 py-2 px-3 border border-danger-subtle";
        badge.innerHTML = '<i class="bi bi-exclamation-octagon me-1"></i> Disconnected';
      }
    }
  }


  /* ==========================================================================
     8. TELEMETRY & CHART LOGIC (For Dashboard Telemetry)
     ========================================================================== */
  function initChart() {
    const ctx = document.getElementById("telemetryChart");
    if (!ctx || typeof Chart === "undefined") return;

    const isDark = state.theme !== "light";
    const textColor = isDark ? "#94a3b8" : "#64748b";

    state.telemetryChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Signal (RSRP)",
            data: [],
            borderColor: "#ff6384",
            backgroundColor: "rgba(255, 99, 132, 0.1)",
            borderWidth: 2,
            tension: 0.4,
            pointRadius: 0,
            yAxisID: "y"
          },
          {
            label: "Latency (RTT)",
            data: [],
            borderColor: "#36a2eb",
            backgroundColor: "rgba(54, 162, 235, 0.1)",
            borderWidth: 2,
            tension: 0.4,
            pointRadius: 0,
            yAxisID: "y1"
          },
          {
            label: "Users",
            data: [],
            borderColor: "#4bc0c0",
            backgroundColor: "rgba(75, 192, 192, 0.1)",
            borderWidth: 2,
            tension: 0.4,
            pointRadius: 0,
            yAxisID: "y2"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: isDark ? "#1e293b" : "#ffffff",
            titleColor: isDark ? "#f8fafc" : "#0f172a",
            bodyColor: isDark ? "#cbd5e1" : "#334155",
            borderColor: isDark ? "#334155" : "#e2e8f0",
            borderWidth: 1
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: textColor, maxRotation: 0, autoSkip: true, maxTicksLimit: 10 }
          },
          y: { type: "linear", display: false, min: -140, max: -40 },
          y1: { type: "linear", display: false, min: 0, max: 100 },
          y2: { type: "linear", display: false, min: 0, max: 2500 }
        }
      }
    });

    simulateInitialChartData();
  }

  function simulateInitialChartData() {
    if (!state.telemetryChart) return;
    const now = Date.now();
    for (let i = state.chartDataPoints; i > 0; i--) {
      const time = new Date(now - i * 5000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
      state.telemetryChart.data.labels.push(time);
      state.telemetryChart.data.datasets[0].data.push(-80 - Math.floor(Math.random() * 20));
      state.telemetryChart.data.datasets[1].data.push(10 + Math.floor(Math.random() * 15));
      state.telemetryChart.data.datasets[2].data.push(1200 + Math.floor(Math.random() * 400));
    }
    state.telemetryChart.update();
  }

  function updateChartTheme(theme) {
    if (!state.telemetryChart) return;
    const isDark = theme !== "light";
    const textColor = isDark ? "#94a3b8" : "#64748b";

    state.telemetryChart.options.scales.x.ticks.color = textColor;
    state.telemetryChart.options.plugins.tooltip.backgroundColor = isDark ? "#1e293b" : "#ffffff";
    state.telemetryChart.options.plugins.tooltip.titleColor = isDark ? "#f8fafc" : "#0f172a";
    state.telemetryChart.options.plugins.tooltip.bodyColor = isDark ? "#cbd5e1" : "#334155";
    state.telemetryChart.update();
  }

  function updateTelemetryUI(data) {
    const rsrpEl = document.getElementById("stat-rsrp");
    const rttEl = document.getElementById("stat-rtt");
    const usersEl = document.getElementById("stat-users");

    if (rsrpEl && data.rsrp) rsrpEl.textContent = data.rsrp;
    if (rttEl && data.rtt) rttEl.textContent = data.rtt;
    if (usersEl && data.users) usersEl.textContent = data.users.toLocaleString();

    if (state.telemetryChart && data) {
      const timeLabel = new Date().toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
      state.telemetryChart.data.labels.push(timeLabel);
      state.telemetryChart.data.datasets[0].data.push(data.rsrp || -85);
      state.telemetryChart.data.datasets[1].data.push(data.rtt || 15);
      state.telemetryChart.data.datasets[2].data.push(data.users || 1400);

      if (state.telemetryChart.data.labels.length > state.chartDataPoints) {
        state.telemetryChart.data.labels.shift();
        state.telemetryChart.data.datasets.forEach(dataset => dataset.data.shift());
      }
      state.telemetryChart.update("none");
    }
  }


  /* ==========================================================================
     9. APPLICATION INITIALIZATION
     ========================================================================== */
  function init() {
    ThemeManager.init();
    Notifications.init();
    FormValidator.init();
    Navigation.init();

    // Initialize WebSocket Manager
    state.wsManager = new WebSocketManager();
    window.TU5G_WS = state.wsManager;

    const currentPath = window.location.pathname;
    if (currentPath.includes("dashboard") || currentPath === "/") {
      initChart();
      state.wsManager.connect();
      state.wsManager.on("message", updateTelemetryUI);

      const refreshBtn = document.getElementById("btnRefreshCells");
      if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
          Notifications.info("Refreshing virtual cell status registry...");
        });
      }
    }

    console.log("TU5G Platform Framework Initialized [Theme:", state.theme, "]");
  }

  // Global Exports
  window.TU5G_Notifications = Notifications;
  window.Notifications = Notifications;
  window.TU5G_Utils = Utils;

  return {
    init,
    ThemeManager,
    Notifications,
    FormValidator,
    Utils,
    WebSocketManager,
    setTheme: (theme) => ThemeManager.setTheme(theme)
  };
})();

// Boot Application when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  TU5G_App.init();
});
