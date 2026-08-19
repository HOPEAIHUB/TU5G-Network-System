# Production-ready Nginx image for serving the TU5G frontend
FROM nginx:1.25-alpine

# Remove default nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration for frontend serving
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy HTML templates, static files, and assets to the nginx root directory
# We copy with directory structure and handle potential absence of files gracefully
COPY . /usr/share/nginx/html/

# Expose port 80 for HTTP traffic
EXPOSE 80

# Production-grade healthcheck using wget (bundled with alpine)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1
