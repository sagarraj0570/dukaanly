# Stage 1: Build the React application
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Production Web Server (SPA)
FROM nginx:alpine-slim

# Minimal SPA configuration supporting client-side routing
RUN echo 'server {' \
    '    listen 80;' \
    '    server_name _;' \
    '    root /usr/share/nginx/html;' \
    '    index index.html;' \
    '    location / {' \
    '        try_files $uri $uri/ /index.html;' \
    '    }' \
    '    location ~* \.(?:css|js|woff2?|svg|png|jpg|jpeg|gif|ico)$ {' \
    '        expires 1y;' \
    '        add_header Cache-Control "public, immutable";' \
    '    }' \
    '}' > /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
