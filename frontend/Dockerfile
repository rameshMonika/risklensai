# --- build stage ---
FROM node:20-slim AS build

WORKDIR /app

# Dependencies first, isolated in their own layer.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite bakes VITE_* vars in at build time, not runtime -- see the
# dev-vs-prod build tradeoff noted in the infra plan (Part 2): each
# environment gets its own image build with its own API URL baked in,
# since CI/CD (and any runtime env-substitution scheme) is out of scope
# for this pass.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# --- serve stage ---
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
