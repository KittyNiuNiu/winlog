# Frontend image: builds the app with Node (version pinned in .nvmrc and package.json
# "engines") and serves the production build with nginx.

# --- Build stage ---
FROM node:26.13.0-alpine AS build

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# --- Serve stage: static files only, no Node at runtime ---
FROM nginx:1.30.6-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
