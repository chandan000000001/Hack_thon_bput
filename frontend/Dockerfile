# Build stage: compile the Vite SPA with VITE_* vars baked in at build time.
FROM node:20-alpine AS build
WORKDIR /app

ARG VITE_USE_MOCK=false
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ARG VITE_SUPABASE_URL=https://YOUR-PROJECT.supabase.co
ARG VITE_SUPABASE_ANON_KEY=your-anon-key
ENV VITE_USE_MOCK=$VITE_USE_MOCK \
    VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Serve stage: Nginx with SPA fallback.
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
